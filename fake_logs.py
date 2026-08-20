"""
fake_logs.py  v3  —  Owner-only advanced fake CHARGED hit stream.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

HOW TO WIRE INTO main.py (only 2 lines needed):

    # ── Near the top with your other imports ──
    import fake_logs

    # ── Inside main(), right before app.run_polling() ──
    fake_logs.register(app)

That is the ONLY change needed in main.py.
sh.py and database.py are NOT touched.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FEATURES
  • /fakeon  — open the full control panel (DM only, owner only)
  • /fakeoff — stop the stream
  • Set log channel ID directly from DM — no need to enter the channel
  • 3 fully configurable link buttons per fake log message
  • Manage fake user IDs: add / toggle / remove
  • Speed control: Slow / Normal / Fast
  • Stats panel with per-ID hit counts + total
  • Everything is owner-only and completely silent to all other users
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os
import random
import logging
import asyncio

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter, TimedOut

logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION  (read from environment — same vars as main.py)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OWNER_ID        = int(os.environ.get("OWNER_ID", "0"))
_DEFAULT_OWNER_FAKE_UID = "8283904645"
_DEFAULT_CHANNEL_ID = -1004361062205


def _read_channel_id() -> int:
    raw = os.environ.get("FAKE_LOG_CHANNEL_ID", "").strip()
    if not raw:
        return _DEFAULT_CHANNEL_ID
    try:
        value = int(raw)
    except ValueError:
        logger.error("[FAKELOGS] Invalid FAKE_LOG_CHANNEL_ID; using %s.", _DEFAULT_CHANNEL_ID)
        return _DEFAULT_CHANNEL_ID
    if value > 0:
        return _DEFAULT_CHANNEL_ID
    return value


_ENV_CHANNEL_ID = _read_channel_id()
_DEFAULT_BOT_URL = "https://t.me/Batxchk_bot"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CUSTOM EMOJI IDs  (hardcoded — zero dependency on sh.py)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_CHARGED_EMOJI_IDS = [
    "5801154993188770160", "4956739572114392015", "5285221724634239278",
    "5287777298894835685", "5285024405246725814", "5287547831677112267",
    "5287658362660474522", "5285186510197381130", "5803233241963959320",
    "5462902520215002477", "5787435351521889877", "5323674506705785412",
    "5801005158959683238", "5436143465211640305", "5800688138833629633",
    "5891044423856296980", "5436068999068662274", "5427168083074628963",
]
_HIT_RESP_EID = "5839116473951328489"   # ✅  green check custom emoji
_PRO_EID      = "6280484433027931563"   # ⭐  plan star custom emoji


def _rand_eid() -> str:
    return random.choice(_CHARGED_EMOJI_IDS)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BOT-DATA KEYS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_K_ACTIVE   = "fakelogs_active"      # bool  — is the stream running?
_K_CHANNEL  = "fakelogs_channel_id"  # int   — target channel/group ID
_K_IDS      = "fl_ids"              # list  — fake user ID entries
_K_SPEED    = "fl_speed"            # str   — "slow"|"normal"|"fast"
_K_LINKS    = "fl_links"            # list  — 3 button link dicts
_K_STATE    = "fl_state"            # str   — current awaiting-input state
_K_EDIT_IDX = "fl_edit_link_idx"    # int   — which link slot is being edited
_JOB        = "fake_hit_stream"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SPEED PRESETS  (min_delay, max_delay) in seconds
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_SPEEDS = {
    "slow":   (90,  180),   # 1.5 – 3 min
    "normal": (40,   80),   # 40 s – 1.5 min  ← default
    "fast":   (18,   35),   # 18 – 35 s
}
_SPEED_LABELS = {
    "slow":   "🐢 Slow  (1.5–3 min)",
    "normal": "🚶 Normal (40–80 s)",
    "fast":   "🏃 Fast  (18–35 s)",
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PRICE POOL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_PRICES = [
    # Edit this list to change the generated demo prices. Keep values below 10.
    "0.99", "1.49", "2.29", "2.99", "3.47",
    "4.19", "4.99", "5.47", "6.79", "8.99",
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BOT-DATA ACCESSORS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _get_ids(bd: dict) -> list:
    ids = bd.setdefault(_K_IDS, [])
    # IDs live only in bot_data memory. They are not written to a database/file.
    # Seed the default only on first initialization; removing the last ID must
    # leave the list empty instead of silently recreating it.
    if not bd.get("fl_ids_initialized"):
        bd["fl_ids_initialized"] = True
        if not ids:
            bd["fl_ids_seeded"] = True
            ids.append({
                "uid": _DEFAULT_OWNER_FAKE_UID,
                "display": f"user_{_DEFAULT_OWNER_FAKE_UID}",
                "link": f"tg://user?id={_DEFAULT_OWNER_FAKE_UID}",
                "enabled": True,
                "count": 0,
            })
    return ids


def _get_speed(bd: dict) -> str:
    return bd.get(_K_SPEED, "normal")


def _get_channel(bd: dict) -> int:
    return bd.get(_K_CHANNEL, _ENV_CHANNEL_ID)


def _get_links(bd: dict) -> list:
    """Return the 3 link-button configs, creating defaults on first call."""
    links = bd.get(_K_LINKS)
    if not links or len(links) < 3:
        links = [
            {"text": "𝘽𝘼𝙏 ✘ 𝘾𝙃𝙆", "url": _DEFAULT_BOT_URL},
            {"text": "",             "url": ""},
            {"text": "",             "url": ""},
        ]
        bd[_K_LINKS] = links
    return links


def _stop_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    job_queue = context.job_queue
    if job_queue is None:
        return
    for job in job_queue.get_jobs_by_name(_JOB):
        job.schedule_removal()


def _clear_state(bd: dict) -> None:
    bd[_K_STATE]    = None
    bd[_K_EDIT_IDX] = None


async def _validate_target(bot, target: int) -> str:
    """Return an actionable error, or an empty string when the target is usable."""
    if not isinstance(target, int) or target >= 0:
        return (
            "Target must be a Telegram channel/group ID beginning with -100. "
            "A private user/DM ID cannot receive the log stream."
        )
    try:
        chat = await bot.get_chat(target)
        if chat.type not in ("channel", "group", "supergroup"):
            return f"Target chat type is {chat.type!r}; choose a channel or group."

        me = await bot.get_me()
        member = await bot.get_chat_member(target, me.id)
        status = getattr(member, "status", "")
        if chat.type == "channel" and status not in ("administrator", "creator"):
            return "The bot must be an administrator of the target channel."
        if chat.type != "channel" and status in ("left", "kicked"):
            return "The bot is not a member of the target group."
        return ""
    except Forbidden:
        return "Telegram denied access. Add the bot as an administrator of the target channel."
    except BadRequest as exc:
        return f"Telegram rejected the target: {str(exc)[:300]}"
    except Exception as exc:
        return f"Could not verify the target chat: {str(exc)[:300]}"


async def _send_with_retry(context, target: int, text: str, reply_markup) -> None:
    """Send one event with bounded retries for temporary Telegram/network errors."""
    retry_delays = (1.0, 3.0, 8.0)
    for attempt, delay in enumerate(retry_delays, start=1):
        try:
            await context.bot.send_message(
                target, text,
                parse_mode="HTML",
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
            return
        except RetryAfter as exc:
            if attempt == len(retry_delays):
                raise
            wait_for = min(float(getattr(exc, "retry_after", delay)), 30.0)
            logger.warning(
                "[FAKELOGS] Telegram rate limit; retry %s/%s in %.1fs",
                attempt, len(retry_delays), wait_for,
            )
            await asyncio.sleep(wait_for)
        except (NetworkError, TimedOut, asyncio.TimeoutError) as exc:
            if attempt == len(retry_delays):
                raise
            logger.warning(
                "[FAKELOGS] temporary send failure; retry %s/%s in %.1fs: %s",
                attempt, len(retry_delays), delay, exc,
            )
            await asyncio.sleep(delay)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FAKE LOG MESSAGE BUILDER
# Produces a compact, clearly marked test event without payment data.
# Format:
#   🧪 TEST ONLY • NOT A REAL PAYMENT
#   HIT → CHARGED 💎
#   Gate → Shopify • 5.47 USD
#   ✅ TEST_ORDER_PAID
#   User → @username ⭐
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _build_log_text(id_entry: dict) -> str:
    price = random.choice(_PRICES)
    eid   = _rand_eid()
    ulink = f'<a href="{id_entry["link"]}">{id_entry["display"]}</a>'
    return (
        f'<b>🧪 TEST ONLY • NOT A REAL PAYMENT</b>\n'
        f'<b>HIT ➛ CHARGED '
        f'<tg-emoji emoji-id="{eid}">💎</tg-emoji></b>\n'
        f'<b>Gate ➛ Shopify • {price} USD</b>\n'
        f'<b><tg-emoji emoji-id="{_HIT_RESP_EID}">✅</tg-emoji>'
        f' <code>TEST_ORDER_PAID</code></b>\n'
        f'<b>User ➛ {ulink}'
        f' <tg-emoji emoji-id="{_PRO_EID}">⭐</tg-emoji></b>'
    )


def _build_log_buttons(bd: dict) -> InlineKeyboardMarkup:
    """Build the inline keyboard from the 3 configurable link slots."""
    links = _get_links(bd)
    row   = []
    for lnk in links:
        txt = lnk.get("text", "").strip()
        url = lnk.get("url",  "").strip()
        if txt and url:
            row.append(InlineKeyboardButton(txt, url=url))
    if not row:
        # fallback: always show at least the bot button
        row = [InlineKeyboardButton("𝘽𝘼𝙏 ✘ 𝘾𝙃𝙆", url=_DEFAULT_BOT_URL)]
    return InlineKeyboardMarkup([row])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BACKGROUND JOB — fires one fake log then reschedules itself
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _job(context: ContextTypes.DEFAULT_TYPE) -> None:
    bd = context.bot_data

    if not bd.get(_K_ACTIVE):
        return

    target = _get_channel(bd)
    if not target:
        logger.warning("[FAKELOGS] No channel ID set — stopping.")
        bd[_K_ACTIVE] = False
        return

    ids = [e for e in _get_ids(bd) if e.get("enabled", True)]
    lo, hi = _SPEEDS[_get_speed(bd)]

    if not isinstance(target, int) or target >= 0:
        bd["fl_last_error"] = (
            "Invalid target ID. Set FAKE_LOG_CHANNEL_ID to a negative channel/group ID."
        )
        bd[_K_ACTIVE] = False
        _stop_job(context)
        return

    if not ids:
        bd["fl_last_error"] = "No enabled display IDs are configured."
        bd[_K_ACTIVE] = False
        _stop_job(context)
        return

    entry = random.choice(ids)
    text  = _build_log_text(entry)
    try:
        await _send_with_retry(
            context, target, text, _build_log_buttons(bd)
        )
        entry["count"] = entry.get("count", 0) + 1
        bd["fl_last_error"] = ""
    except Exception as exc:
        bd["fl_failed"] = bd.get("fl_failed", 0) + 1
        bd["fl_last_error"] = str(exc)[:500]
        bd[_K_ACTIVE] = False
        _stop_job(context)
        logger.warning(f"[FAKELOGS] send failed (chat={target}); stream stopped: {exc}")
        return

    if bd.get(_K_ACTIVE):
        job_queue = context.job_queue
        if job_queue is None:
            bd["fl_failed"] = bd.get("fl_failed", 0) + 1
            bd["fl_last_error"] = (
                "Job queue is unavailable. Install python-telegram-bot[job-queue]."
            )
            bd[_K_ACTIVE] = False
            logger.error("[FAKELOGS] Job queue unavailable; stream stopped.")
            return
        try:
            job_queue.run_once(_job, random.uniform(lo, hi), name=_JOB)
        except Exception as exc:
            bd["fl_failed"] = bd.get("fl_failed", 0) + 1
            bd["fl_last_error"] = f"Could not schedule next event: {str(exc)[:400]}"
            bd[_K_ACTIVE] = False
            logger.warning("[FAKELOGS] scheduling failed; stream stopped: %s", exc)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# UI PANEL BUILDERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# ─── MAIN PANEL ──────────────────────────────────────────────────────────────

def _main_text(bd: dict) -> str:
    active  = bd.get(_K_ACTIVE, False)
    speed   = _get_speed(bd)
    ids     = _get_ids(bd)
    on_ct   = sum(1 for e in ids if e.get("enabled", True))
    status  = "🟢 RUNNING" if active else "🔴 STOPPED"
    target  = _get_channel(bd)
    cid_str = f"<code>{target}</code>" if target else "<i>not set — tap 📡 Channel to set</i>"

    links  = _get_links(bd)
    active_links = sum(1 for l in links if l.get("text") and l.get("url"))

    return (
        f"<b>🎭 Fake Logs Control Panel</b>\n"
        f"──────────────────\n"
        f"<b>Status  ➛</b> {status}\n"
        f"<b>Channel ➛</b> {cid_str}\n"
        f"<b>Speed   ➛</b> {_SPEED_LABELS[speed]}\n"
        f"<b>IDs     ➛</b> {on_ct}/{len(ids)} enabled\n"
        f"<b>Links   ➛</b> {active_links}/3 buttons configured\n"
        f"──────────────────"
    )


def _main_kb(bd: dict) -> InlineKeyboardMarkup:
    active = bd.get(_K_ACTIVE, False)
    lbl    = "⛔ Stop Logs" if active else "▶️ Start Logs"
    cb     = "fl_stop"      if active else "fl_start"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📋 IDs",      callback_data="fl_ids"),
            InlineKeyboardButton("⚡ Speed",    callback_data="fl_speed"),
            InlineKeyboardButton("📊 Stats",    callback_data="fl_show"),
        ],
        [
            InlineKeyboardButton("🔗 Links",    callback_data="fl_links"),
            InlineKeyboardButton("📡 Channel",  callback_data="fl_channel"),
        ],
        [InlineKeyboardButton(lbl, callback_data=cb)],
    ])


# ─── IDS PANEL ───────────────────────────────────────────────────────────────

def _ids_text(bd: dict) -> str:
    ids = _get_ids(bd)
    if not ids:
        return (
            "<b>📋 Fake Log IDs</b>\n──────────────────\n"
            "No IDs added yet.\n\n"
            "Tap <b>➕ Add ID</b> then send:\n"
            "<code>123456789 @username</code>  or just  <code>@username</code>\n\n"
            "<i>Added IDs are memory-only and reset when the bot restarts.</i>"
        )
    lines = ["<b>📋 Fake Log IDs</b>", "──────────────────"]
    for e in ids:
        icon = "🟢" if e.get("enabled", True) else "🔴"
        ct   = e.get("count", 0)
        lines.append(f"{icon} {e['display']}  —  {ct} fake hit{'s' if ct != 1 else ''}")
    lines.append("──────────────────\nToggle or remove IDs with the buttons below.")
    return "\n".join(lines)


def _ids_kb(bd: dict) -> InlineKeyboardMarkup:
    ids  = _get_ids(bd)
    rows = []
    for i, e in enumerate(ids):
        on  = e.get("enabled", True)
        tog = "🟢 ON" if on else "🔴 OFF"
        rows.append([
            InlineKeyboardButton(e["display"],  callback_data="fl_noop"),
            InlineKeyboardButton(tog,            callback_data=f"fltog_{i}"),
            InlineKeyboardButton("❌ Remove",   callback_data=f"flrem_{i}"),
        ])
    rows.append([
        InlineKeyboardButton("➕ Add ID", callback_data="fl_addid"),
        InlineKeyboardButton("🔙 Back",   callback_data="fl_panel"),
    ])
    return InlineKeyboardMarkup(rows)


# ─── SPEED PANEL ─────────────────────────────────────────────────────────────

def _speed_text() -> str:
    return (
        "<b>⚡ Fake Log Speed</b>\n──────────────────\n"
        "Choose how fast fake CHARGED hits appear in the channel.\n"
        "All delays are <b>randomised</b> — no fixed pattern.\n"
        "──────────────────"
    )


def _speed_kb(bd: dict) -> InlineKeyboardMarkup:
    cur  = _get_speed(bd)
    rows = []
    for key, label in _SPEED_LABELS.items():
        check = "✅ " if key == cur else "      "
        rows.append([InlineKeyboardButton(f"{check}{label}", callback_data=f"flspd_{key}")])
    rows.append([InlineKeyboardButton("🔙 Back", callback_data="fl_panel")])
    return InlineKeyboardMarkup(rows)


# ─── STATS PANEL ─────────────────────────────────────────────────────────────

def _show_text(bd: dict) -> str:
    ids   = _get_ids(bd)
    speed = _get_speed(bd)
    if not ids:
        return "<b>📊 Fake Log Stats</b>\n──────────────────\nNo IDs configured yet."
    lines = ["<b>📊 Fake Log Stats</b>", "──────────────────"]
    total = 0
    for e in ids:
        on     = "🟢" if e.get("enabled", True) else "🔴"
        ct     = e.get("count", 0)
        total += ct
        tag    = "" if e.get("enabled", True) else " <i>(off)</i>"
        lines.append(f"{on} {e['display']} — <b>{ct}</b> hit{'s' if ct != 1 else ''}{tag}")
    lines += [
        "──────────────────",
        f"<b>Total fake hits sent ➛ {total}</b>",
        f"<b>Speed ➛ {_SPEED_LABELS[speed]}</b>",
    ]
    failed = bd.get("fl_failed", 0)
    last_error = bd.get("fl_last_error", "")
    if failed:
        lines.append(f"<b>Failed deliveries ➛ {failed}</b>")
        if last_error:
            lines.append(f"<b>Last error ➛</b> <code>{last_error}</code>")
    return "\n".join(lines)


def _show_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑 Clear All Stats", callback_data="fl_clrstats")],
        [InlineKeyboardButton("🔙 Back",            callback_data="fl_panel")],
    ])


# ─── LINKS PANEL ─────────────────────────────────────────────────────────────

def _links_text(bd: dict) -> str:
    links = _get_links(bd)
    lines = [
        "<b>🔗 Fake Log Button Links</b>",
        "──────────────────",
        "These buttons appear on every fake log message.",
        "Up to 3 buttons — leave text/URL empty to hide a slot.",
        "──────────────────",
    ]
    for i, lnk in enumerate(links, 1):
        txt = lnk.get("text", "").strip() or "<i>empty</i>"
        url = lnk.get("url",  "").strip() or "<i>empty</i>"
        lines.append(f"<b>Link {i}</b>")
        lines.append(f"  📝 Text ➛ {txt}")
        lines.append(f"  🔗 URL  ➛ {url}")
    lines.append("──────────────────")
    return "\n".join(lines)


def _links_kb(bd: dict) -> InlineKeyboardMarkup:
    links = _get_links(bd)
    rows  = []
    for i, lnk in enumerate(links):
        label = lnk.get("text", "").strip() or f"Link {i+1} (empty)"
        rows.append([
            InlineKeyboardButton(f"✏️ {label}", callback_data=f"fledit_{i}"),
        ])
    rows.append([InlineKeyboardButton("🔙 Back", callback_data="fl_panel")])
    return InlineKeyboardMarkup(rows)


def _link_edit_text(idx: int, bd: dict) -> str:
    lnk  = _get_links(bd)[idx]
    txt  = lnk.get("text", "").strip() or "<i>empty</i>"
    url  = lnk.get("url",  "").strip() or "<i>empty</i>"
    return (
        f"<b>✏️ Edit Link {idx+1}</b>\n"
        f"──────────────────\n"
        f"<b>Current text ➛</b> {txt}\n"
        f"<b>Current URL  ➛</b> {url}\n"
        f"──────────────────\n"
        f"Choose what to update:"
    )


def _link_edit_kb(idx: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📝 Set Text", callback_data=f"fllt_{idx}"),
            InlineKeyboardButton("🔗 Set URL",  callback_data=f"fllu_{idx}"),
        ],
        [
            InlineKeyboardButton("🗑 Clear Slot", callback_data=f"fllc_{idx}"),
            InlineKeyboardButton("🔙 Back",       callback_data="fl_links"),
        ],
    ])


# ─── CHANNEL PANEL ───────────────────────────────────────────────────────────

def _channel_text(bd: dict) -> str:
    target  = _get_channel(bd)
    cid_str = f"<code>{target}</code>" if target else "<i>not configured</i>"
    return (
        f"<b>📡 Fake Log Channel</b>\n"
        f"──────────────────\n"
        f"<b>Current channel ID ➛</b> {cid_str}\n"
        f"──────────────────\n"
        f"<b>How to set it from here (easiest):</b>\n"
        f"Tap <b>✏️ Enter Channel ID</b> below, then type the\n"
        f"channel ID in this DM — e.g. <code>-1001234567890</code>\n\n"
        f"<b>How to get the ID:</b>\n"
        f"1. Add the bot as <b>admin</b> of your target channel\n"
        f"2. Forward any message from that channel to\n"
        f"   @userinfobot — it shows the channel ID\n"
        f"3. Paste that ID using the button below\n\n"
        f"<i>Or send /getid inside the channel (bot must be admin).</i>"
    )


def _channel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Enter Channel ID", callback_data="fl_setchannel")],
        [InlineKeyboardButton("🔙 Back",             callback_data="fl_panel")],
    ])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND HANDLERS  (all owner-only, completely silent to others)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _cmd_fakeon(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/fakeon — open the control panel. Owner-only, silent to everyone else."""
    if not update.effective_user or update.effective_user.id != OWNER_ID:
        return
    bd = context.bot_data
    _clear_state(bd)    # cancel any pending input waiting
    await update.message.reply_text(
        _main_text(bd),
        parse_mode="HTML",
        reply_markup=_main_kb(bd),
    )


async def _cmd_fakeoff(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/fakeoff — stop the stream. Owner-only, silent to everyone else."""
    if not update.effective_user or update.effective_user.id != OWNER_ID:
        return
    context.bot_data[_K_ACTIVE] = False
    _stop_job(context)
    _clear_state(context.bot_data)
    await update.message.reply_text("<b>⛔ Fake logs stopped.</b>", parse_mode="HTML")


async def _cmd_getid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/getid — save current chat ID as the fake-log channel.
    Can be run inside any channel (bot must be admin) or from DM.
    From DM it shows the owner's own user ID — use the panel instead."""
    if not update.effective_user or update.effective_user.id != OWNER_ID:
        return
    chat = update.effective_chat
    if not chat or chat.type == "private":
        await update.message.reply_text(
            "<b>⚠️ /getid must be run in the target channel or group.</b>\n"
            "For a channel, add this bot as an administrator first.\n"
            "You can also set <code>FAKE_LOG_CHANNEL_ID=-100...</code> on Railway.",
            parse_mode="HTML",
        )
        return
    if chat.type not in ("channel", "group", "supergroup"):
        await update.message.reply_text(
            "<b>⚠️ This chat cannot be used as a log target.</b>",
            parse_mode="HTML",
        )
        return
    cid  = chat.id
    context.bot_data[_K_CHANNEL] = cid
    title = chat.title or "this DM"
    await update.message.reply_text(
        f"<b>📡 Chat ID saved!</b>\n"
        f"──────────────────\n"
        f"<b>ID    ➛</b> <code>{cid}</code>\n"
        f"<b>Title ➛</b> {title}\n\n"
        f"Fake logs will now go to this chat.\n"
        f"Use /fakeon to start.",
        parse_mode="HTML",
    )


async def _cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or not update.message:
        return
    await update.message.reply_text(
        "<b>Your Telegram user ID</b>\n"
        f"<code>{user.id}</code>\n\n"
        "Set this exact number as Railway variable <code>OWNER_ID</code>, "
        "then redeploy. Only that account can use /fakeon and /getid.",
        parse_mode="HTML",
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MASTER CALLBACK HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not q.from_user or q.from_user.id != OWNER_ID:
        await q.answer("⛔ Owner only.", show_alert=True)
        return
    await q.answer()

    bd  = context.bot_data
    dat = q.data

    # ── Main panel ──────────────────────────────────────────────────────────
    if dat == "fl_panel":
        _clear_state(bd)
        await q.edit_message_text(
            _main_text(bd), parse_mode="HTML",
            reply_markup=_main_kb(bd),
        )

    elif dat == "fl_start":
        enabled = [e for e in _get_ids(bd) if e.get("enabled", True)]
        if not enabled:
            await q.answer("⚠️ Enable at least one ID first (📋 IDs).", show_alert=True)
            return
        if not _get_channel(bd):
            await q.answer("⚠️ Set a channel ID first (📡 Channel).", show_alert=True)
            return
        target_error = await _validate_target(context.bot, _get_channel(bd))
        if target_error:
            bd[_K_ACTIVE] = False
            bd["fl_failed"] = bd.get("fl_failed", 0) + 1
            bd["fl_last_error"] = target_error
            await q.answer(f"⚠️ {target_error}", show_alert=True)
            await q.edit_message_text(
                _main_text(bd), parse_mode="HTML",
                reply_markup=_main_kb(bd),
            )
            return
        bd[_K_ACTIVE] = True
        _stop_job(context)
        # Send the first log immediately; _job schedules the next randomized
        # delivery and records any Telegram error for the Stats panel.
        await _job(context)
        if bd.get("fl_last_error"):
            await q.answer(
                f"⚠️ Telegram delivery failed: {bd['fl_last_error'][:180]}",
                show_alert=True,
            )
        await q.edit_message_text(
            _main_text(bd), parse_mode="HTML",
            reply_markup=_main_kb(bd),
        )

    elif dat == "fl_stop":
        bd[_K_ACTIVE] = False
        _stop_job(context)
        await q.edit_message_text(
            _main_text(bd), parse_mode="HTML",
            reply_markup=_main_kb(bd),
        )

    elif dat == "fl_noop":
        pass  # display-only label button

    # ── IDs panel ───────────────────────────────────────────────────────────
    elif dat == "fl_ids":
        _clear_state(bd)
        await q.edit_message_text(
            _ids_text(bd), parse_mode="HTML",
            reply_markup=_ids_kb(bd),
        )

    elif dat == "fl_addid":
        bd[_K_STATE] = "awaiting_id"
        await q.edit_message_text(
            "<b>➕ Add Fake Log ID</b>\n──────────────────\n"
            "Send the user info in your next message:\n\n"
            "<b>Format:</b>  <code>123456789 @username</code>\n"
            "or just:      <code>@username</code>\n\n"
            "<i>This name appears as the checker on every fake hit.</i>\n"
            "──────────────────\n"
            "Send /fakeon to cancel.",
            parse_mode="HTML",
        )

    elif dat.startswith("fltog_"):
        try:
            idx = int(dat.split("_", 1)[1])
        except (ValueError, IndexError):
            return
        ids = _get_ids(bd)
        if 0 <= idx < len(ids):
            ids[idx]["enabled"] = not ids[idx].get("enabled", True)
        await q.edit_message_text(
            _ids_text(bd), parse_mode="HTML",
            reply_markup=_ids_kb(bd),
        )

    elif dat.startswith("flrem_"):
        try:
            idx = int(dat.split("_", 1)[1])
        except (ValueError, IndexError):
            return
        ids = _get_ids(bd)
        if 0 <= idx < len(ids):
            removed = ids.pop(idx)
            await q.answer(f"✅ {removed['display']} removed.", show_alert=False)
        await q.edit_message_text(
            _ids_text(bd), parse_mode="HTML",
            reply_markup=_ids_kb(bd),
        )

    # ── Speed panel ─────────────────────────────────────────────────────────
    elif dat == "fl_speed":
        _clear_state(bd)
        await q.edit_message_text(
            _speed_text(), parse_mode="HTML",
            reply_markup=_speed_kb(bd),
        )

    elif dat.startswith("flspd_"):
        spd = dat.split("_", 1)[1]
        if spd in _SPEEDS:
            bd[_K_SPEED] = spd
            await q.answer(f"✅ Speed set to {_SPEED_LABELS[spd]}", show_alert=False)
        await q.edit_message_text(
            _speed_text(), parse_mode="HTML",
            reply_markup=_speed_kb(bd),
        )

    # ── Stats panel ─────────────────────────────────────────────────────────
    elif dat == "fl_show":
        _clear_state(bd)
        await q.edit_message_text(
            _show_text(bd), parse_mode="HTML",
            reply_markup=_show_kb(),
        )

    elif dat == "fl_clrstats":
        for e in _get_ids(bd):
            e["count"] = 0
        await q.answer("✅ Stats cleared.", show_alert=False)
        await q.edit_message_text(
            _show_text(bd), parse_mode="HTML",
            reply_markup=_show_kb(),
        )

    # ── Links panel ─────────────────────────────────────────────────────────
    elif dat == "fl_links":
        _clear_state(bd)
        await q.edit_message_text(
            _links_text(bd), parse_mode="HTML",
            reply_markup=_links_kb(bd),
        )

    elif dat.startswith("fledit_"):
        # Owner tapped on a link slot to edit it
        try:
            idx = int(dat.split("_", 1)[1])
        except (ValueError, IndexError):
            return
        if 0 <= idx < 3:
            _clear_state(bd)
            bd[_K_EDIT_IDX] = idx
            await q.edit_message_text(
                _link_edit_text(idx, bd), parse_mode="HTML",
                reply_markup=_link_edit_kb(idx),
            )

    elif dat.startswith("fllt_"):
        # Set Link TEXT for slot idx
        try:
            idx = int(dat.split("_", 1)[1])
        except (ValueError, IndexError):
            return
        bd[_K_STATE]    = "awaiting_link_text"
        bd[_K_EDIT_IDX] = idx
        await q.edit_message_text(
            f"<b>📝 Set Text for Link {idx+1}</b>\n"
            f"──────────────────\n"
            f"Send the button label text in your next message.\n\n"
            f"<b>Example:</b> <code>🔥 Join Channel</code>\n\n"
            f"<i>Keep it short — Telegram buttons have limited width.</i>\n"
            f"──────────────────\nSend /fakeon to cancel.",
            parse_mode="HTML",
        )

    elif dat.startswith("fllu_"):
        # Set Link URL for slot idx
        try:
            idx = int(dat.split("_", 1)[1])
        except (ValueError, IndexError):
            return
        bd[_K_STATE]    = "awaiting_link_url"
        bd[_K_EDIT_IDX] = idx
        await q.edit_message_text(
            f"<b>🔗 Set URL for Link {idx+1}</b>\n"
            f"──────────────────\n"
            f"Send the full URL in your next message.\n\n"
            f"<b>Examples:</b>\n"
            f"<code>https://t.me/yourchannel</code>\n"
            f"<code>https://t.me/yourgrouplink</code>\n"
            f"<code>https://t.me/Batxchk_bot</code>\n\n"
            f"<i>Must start with https:// or http://</i>\n"
            f"──────────────────\nSend /fakeon to cancel.",
            parse_mode="HTML",
        )

    elif dat.startswith("fllc_"):
        # Clear / reset link slot
        try:
            idx = int(dat.split("_", 1)[1])
        except (ValueError, IndexError):
            return
        links = _get_links(bd)
        if 0 <= idx < 3:
            # Slot 0 resets to bot default; others become empty
            if idx == 0:
                links[idx] = {"text": "𝘽𝘼𝙏 ✘ 𝘾𝙃𝙆", "url": _DEFAULT_BOT_URL}
            else:
                links[idx] = {"text": "", "url": ""}
            await q.answer(f"✅ Link {idx+1} cleared.", show_alert=False)
        _clear_state(bd)
        await q.edit_message_text(
            _links_text(bd), parse_mode="HTML",
            reply_markup=_links_kb(bd),
        )

    # ── Channel panel ────────────────────────────────────────────────────────
    elif dat == "fl_channel":
        _clear_state(bd)
        await q.edit_message_text(
            _channel_text(bd), parse_mode="HTML",
            reply_markup=_channel_kb(),
        )

    elif dat == "fl_setchannel":
        bd[_K_STATE] = "awaiting_channel"
        await q.edit_message_text(
            "<b>📡 Enter Channel ID</b>\n"
            "──────────────────\n"
            "Send the channel/group ID in your next message.\n\n"
            "<b>Format:</b>  <code>-1001234567890</code>\n\n"
            "<b>How to find the ID:</b>\n"
            "• Forward a message from your channel to @userinfobot\n"
            "• Or send /getid inside the channel (bot must be admin)\n\n"
            "<i>Channels always have negative IDs starting with -100</i>\n"
            "──────────────────\nSend /fakeon to cancel.",
            parse_mode="HTML",
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MESSAGE CAPTURE — handles all awaiting-input states
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _msg_capture(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Captures the owner's next plain-text message for any active input state.
    Completely silent and passes through if no state is active."""
    if not update.effective_user or update.effective_user.id != OWNER_ID:
        return

    bd    = context.bot_data
    state = bd.get(_K_STATE)

    if not state:
        return   # no active state — let other handlers process

    raw = (update.message.text or "").strip()

    # ── Add user ID ───────────────────────────────────────────────────────────
    if state == "awaiting_id":
        parts     = raw.split()
        uid_val   = None
        uname_val = None
        for p in parts:
            if p.startswith("@"):
                uname_val = p
            elif p.lstrip("-").isdigit():
                uid_val = p

        if not uid_val and not uname_val:
            await update.message.reply_text(
                "<b>❌ Could not parse.</b>\n"
                "Send: <code>123456789 @username</code>\n"
                "or just <code>@username</code>",
                parse_mode="HTML",
            )
            return

        display = uname_val or f"user_{uid_val}"
        link    = (
            f"https://t.me/{uname_val.lstrip('@')}"
            if uname_val
            else f"tg://user?id={uid_val}"
        )
        key_val = uid_val or uname_val

        ids = _get_ids(bd)
        for e in ids:
            if e["uid"] == key_val:
                _clear_state(bd)
                await update.message.reply_text(
                    f"<b>⚠️ {display} is already in the list.</b>",
                    parse_mode="HTML",
                )
                return

        ids.append({
            "uid":     key_val,
            "display": display,
            "link":    link,
            "enabled": True,
            "count":   0,
        })
        _clear_state(bd)
        await update.message.reply_text(
            f"<b>✅ {display} added to fake logs.</b>\n"
            f"Use /fakeon → 📋 IDs to manage.",
            parse_mode="HTML",
        )
        return

    # ── Set channel ID ────────────────────────────────────────────────────────
    if state == "awaiting_channel":
        cid_str = raw.lstrip("-").isdigit() and raw or raw.lstrip("-")
        if not raw.lstrip("-").isdigit():
            await update.message.reply_text(
                "<b>❌ Invalid channel ID.</b>\n"
                "It must be a number like <code>-1001234567890</code>\n"
                "Send /fakeon to cancel.",
                parse_mode="HTML",
            )
            return
        cid = int(raw)
        bd[_K_CHANNEL] = cid
        _clear_state(bd)
        await update.message.reply_text(
            f"<b>✅ Channel ID saved!</b>\n"
            f"──────────────────\n"
            f"<b>ID ➛</b> <code>{cid}</code>\n\n"
            f"Fake logs will go to this channel.\n"
            f"Use /fakeon to open the panel and start.",
            parse_mode="HTML",
        )
        return

    # ── Set link text ─────────────────────────────────────────────────────────
    if state == "awaiting_link_text":
        idx   = bd.get(_K_EDIT_IDX, 0)
        links = _get_links(bd)
        if 0 <= idx < 3:
            links[idx]["text"] = raw
        _clear_state(bd)
        await update.message.reply_text(
            f"<b>✅ Link {idx+1} text set to:</b> {raw}\n\n"
            f"Now set the URL with /fakeon → 🔗 Links → ✏️ Edit → 🔗 Set URL",
            parse_mode="HTML",
        )
        return

    # ── Set link URL ──────────────────────────────────────────────────────────
    if state == "awaiting_link_url":
        idx   = bd.get(_K_EDIT_IDX, 0)
        links = _get_links(bd)
        if not raw.startswith(("https://", "http://")):
            await update.message.reply_text(
                "<b>❌ URL must start with https:// or http://</b>\n"
                "Send the full URL again, or /fakeon to cancel.",
                parse_mode="HTML",
            )
            return
        if 0 <= idx < 3:
            links[idx]["url"] = raw
        _clear_state(bd)
        await update.message.reply_text(
            f"<b>✅ Link {idx+1} URL set!</b>\n"
            f"<b>Text ➛</b> {links[idx].get('text') or '<i>empty — set text too</i>'}\n"
            f"<b>URL  ➛</b> {raw}\n\n"
            f"Use /fakeon → 🔗 Links to review all 3 buttons.",
            parse_mode="HTML",
        )
        return


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# REGISTER  —  the ONLY function called from main.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def register(app: Application) -> None:
    """
    Register all fake-logs handlers into the PTB Application.

    Call this inside your main() function BEFORE app.run_polling():

        import fake_logs
        ...
        fake_logs.register(app)
        app.run_polling(...)

    Handlers are added BEFORE any generic catch-all so fl_* callbacks
    and the message-capture handler fire correctly.
    """
    # ── Commands ──────────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("myid",    _cmd_myid))
    app.add_handler(CommandHandler("fakeon",  _cmd_fakeon))
    app.add_handler(CommandHandler("fakeoff", _cmd_fakeoff))
    app.add_handler(CommandHandler("getid",   _cmd_getid))

    # ── Callback buttons ──────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(
        _cb,
        pattern=(
            r"^(fl_panel|fl_start|fl_stop|fl_noop"
            r"|fl_ids|fl_addid"
            r"|fl_speed|fl_show|fl_clrstats"
            r"|fl_links|fl_channel|fl_setchannel"
            r"|fltog_\d+|flrem_\d+"
            r"|flspd_\w+"
            r"|fledit_\d+|fllt_\d+|fllu_\d+|fllc_\d+)$"
        ),
    ))

    # ── Message capture (owner only, any active input state) ──────────────────
    app.add_handler(MessageHandler(
        filters.TEXT & filters.User(OWNER_ID) & ~filters.COMMAND,
        _msg_capture,
    ))

    logger.info("[FAKELOGS] Advanced fake logs module registered — owner only.")
