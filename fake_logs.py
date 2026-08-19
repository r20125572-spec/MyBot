"""
fake_logs.py  v4  —  Owner-only advanced fake CHARGED hit stream.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Wire into main.py with exactly 2 lines:

    import fake_logs                  # ← near other imports at top
    fake_logs.register(app)           # ← inside main(), before run_polling()

sh.py / database.py are NOT touched.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FEATURES  (all 100% owner-only — completely silent to everyone else)

  /fakeon  — full control panel in your DM

  ➕ Add Target  — forward a msg FROM your channel/group, OR paste
                   its @username or invite link (t.me/+…)
                   Supports MULTIPLE targets — logs go to all of them
  👥 Manage IDs  — add, toggle, remove fake checker usernames
  🔗 Buttons     — 3 configurable link buttons on every fake log
  ⚡ Speed       — Slow / Normal / Fast
  📊 Stats       — per-ID hit counts + total
  ▶️ Start / ⛔ Stop
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import asyncio
import html
import logging
import os
import random
import time
from urllib.parse import urlparse

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
from telegram.error import RetryAfter, TelegramError

logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIG
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OWNER_ID        = int(os.environ.get("OWNER_ID", "0"))
_DEFAULT_BOT_URL = "https://t.me/Batxchk_bot"
_MAX_SEND_ATTEMPTS = 3

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EMOJI IDs  (hardcoded — zero dependency on sh.py)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_CHARGED_EIDS = [
    "5801154993188770160", "4956739572114392015", "5285221724634239278",
    "5287777298894835685", "5285024405246725814", "5287547831677112267",
    "5287658362660474522", "5285186510197381130", "5803233241963959320",
    "5462902520215002477", "5787435351521889877", "5323674506705785412",
    "5801005158959683238", "5436143465211640305", "5800688138833629633",
    "5891044423856296980", "5436068999068662274", "5427168083074628963",
]
_CHECK_EID = "5839116473951328489"   # ✅
_PRO_EID   = "6280484433027931563"   # ⭐

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BOT-DATA KEYS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_K_ACTIVE   = "fakelogs_active"   # bool
_K_TARGETS  = "fl_targets"        # list[{id, title, enabled}]
_K_IDS      = "fl_ids"            # list[{uid, display, link, enabled, count}]
_K_LINKS    = "fl_links"          # list[3 × {text, url}]
_K_SPEED    = "fl_speed"          # "slow"|"normal"|"fast"
_K_STATE    = "fl_state"          # awaiting-input state string | None
_K_EDIT_IDX = "fl_edit_idx"       # int | None  (link slot being edited)
_K_STATS    = "fl_delivery_stats" # delivery health and error counters
_JOB        = "fake_hit_stream"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SPEED PRESETS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_SPEEDS = {
    "slow":   (90, 180),
    "normal": (40,  80),
    "fast":   (18,  35),
}
_SPEED_LABELS = {
    "slow":   "🐢 Slow  (1.5–3 min)",
    "normal": "🚶 Normal (40–80 s)",
    "fast":   "🏃 Fast  (18–35 s)",
}
_PRICES = [
    "1.99", "2.99", "3.99", "4.99", "5.00",
    "7.99", "9.99", "12.99", "14.99", "19.99",
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BOT-DATA HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _read_env_target() -> int | str | None:
    """Read the optional fake-log target once at startup.

    A configured environment target is added automatically, so deploying with
    FAKE_LOG_CHANNEL_ID=-100... or @publicchannel works without panel setup.
    """
    raw = (
        os.environ.get("FAKE_LOG_CHANNEL_ID", "").strip()
        or os.environ.get("FAKE_LOG_CHANNEL", "").strip()
    )
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        if raw.startswith("@") and len(raw) > 1:
            return raw
        if raw.startswith("https://t.me/") and not raw.startswith("https://t.me/+"):
            username = raw.removeprefix("https://t.me/").split("/", 1)[0]
            if username:
                return f"@{username.lstrip('@')}"
        logger.error(
            "[FAKELOGS] Invalid fake-log target %r. Use a negative Telegram "
            "channel/group ID or a public @username.", raw,
        )
        return raw


_ENV_TARGET_ID = _read_env_target()


def _target_issue(chat_id: object) -> str:
    """Return an actionable configuration error, or an empty string."""
    if isinstance(chat_id, int):
        if chat_id > 0:
            return (
                f"{chat_id} is a positive user-style ID, not a channel/group ID. "
                "Use the target chat's negative ID (usually -100...) or forward "
                "a message from that chat to /fakeon → Add Target."
            )
        return ""
    if isinstance(chat_id, str):
        if chat_id.startswith("@") and len(chat_id) > 1:
            return ""
        if chat_id.startswith("https://t.me/+"):
            return (
                "Invite links cannot be used as send targets. Forward any message "
                "from the private channel/group to /fakeon → Add Target."
            )
        return (
            "Target must be a negative numeric channel/group ID or a public "
            "@channelusername."
        )
    return "Target is empty or invalid."


def _targets(bd: dict) -> list:
    return bd.setdefault(_K_TARGETS, [])


def _sync_environment_target(bd: dict) -> None:
    """Make the environment-configured target available in the multi-target list.

    Also migrates the v3 single-channel value when bot_data survives a module
    upgrade. Existing owner-managed targets are never overwritten.
    """
    targets = _targets(bd)
    candidates = [
        (_ENV_TARGET_ID, "Environment target"),
        (bd.pop("fakelogs_channel_id", None), "Migrated target"),
    ]
    existing_ids = {target.get("id") for target in targets}
    for chat_id, title in candidates:
        if chat_id is not None and chat_id not in existing_ids:
            targets.append({
                "id": chat_id,
                "title": title,
                "enabled": True,
                "source": "environment" if chat_id == _ENV_TARGET_ID else "migration",
            })
            existing_ids.add(chat_id)
            logger.info("[FAKELOGS] Added %s (%s).", title, chat_id)


def _ids(bd: dict) -> list:
    return bd.setdefault(_K_IDS, [])

def _speed(bd: dict) -> str:
    return bd.get(_K_SPEED, "normal")

def _links(bd: dict) -> list:
    lnks = bd.get(_K_LINKS)
    if not lnks or len(lnks) < 3:
        lnks = [
            {"text": "𝘽𝘼𝙏 ✘ 𝘾𝙃𝙆", "url": _DEFAULT_BOT_URL},
            {"text": "",             "url": ""},
            {"text": "",             "url": ""},
        ]
        bd[_K_LINKS] = lnks
    return lnks


def _delivery_stats(bd: dict) -> dict:
    defaults = {
        "generated": 0,
        "sent": 0,
        "failed": 0,
        "last_error": "",
        "last_error_at": 0,
        "last_sent_at": 0,
    }
    stats = bd.setdefault(_K_STATS, {})
    for key, value in defaults.items():
        stats.setdefault(key, value)
    return stats


def _record_delivery(
    bd: dict, target: dict, *, succeeded: bool, error: str = "",
) -> None:
    """Persist concise per-target and overall delivery health data."""
    now = int(time.time())
    stats = _delivery_stats(bd)
    if succeeded:
        target["sent"] = target.get("sent", 0) + 1
        target["last_sent_at"] = now
        target["last_error"] = ""
        stats["sent"] += 1
        stats["last_sent_at"] = now
        return

    target["failed"] = target.get("failed", 0) + 1
    target["last_error"] = error[:240]
    target["last_error_at"] = now
    stats["failed"] += 1
    stats["last_error"] = error[:240]
    stats["last_error_at"] = now


def _is_valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _clear(bd: dict) -> None:
    bd[_K_STATE]    = None
    bd[_K_EDIT_IDX] = None

def _stop_job(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    for j in ctx.job_queue.get_jobs_by_name(_JOB):
        j.schedule_removal()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FAKE LOG MESSAGE + BUTTON BUILDER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _generate_hit(entry: dict, bd: dict) -> str:
    """Generate the next synthetic hit from an enabled checker identity."""
    _delivery_stats(bd)["generated"] += 1
    price = random.choice(_PRICES)
    eid   = random.choice(_CHARGED_EIDS)
    href  = html.escape(str(entry.get("link", "")), quote=True)
    name  = html.escape(str(entry.get("display", "Unknown")))
    ulink = f'<a href="{href}">{name}</a>'
    return (
        f'<b>HIT ➛ CHARGED '
        f'<tg-emoji emoji-id="{eid}">💎</tg-emoji></b>\n'
        f'<b>Gate ➛ Shopify • {price} USD</b>\n'
        f'<b><tg-emoji emoji-id="{_CHECK_EID}">✅</tg-emoji>'
        f' <code>ORDER_PAID</code></b>\n'
        f'<b>User ➛ {ulink}'
        f' <tg-emoji emoji-id="{_PRO_EID}">⭐</tg-emoji></b>'
    )


def _log_kb(bd: dict) -> InlineKeyboardMarkup:
    row = [
        InlineKeyboardButton(lnk["text"], url=lnk["url"])
        for lnk in _links(bd)
        if lnk.get("text", "").strip() and lnk.get("url", "").strip()
    ]
    if not row:
        row = [InlineKeyboardButton("𝘽𝘼𝙏 ✘ 𝘾𝙃𝙆", url=_DEFAULT_BOT_URL)]
    return InlineKeyboardMarkup([row])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DELIVERY ENGINE + BACKGROUND JOB
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _retry_after_seconds(value: object) -> float:
    """Handle PTB versions where RetryAfter uses seconds or timedelta."""
    if hasattr(value, "total_seconds"):
        return float(value.total_seconds())
    try:
        return float(value)
    except (TypeError, ValueError):
        return 1.0


async def _send_with_retry(
    ctx: ContextTypes.DEFAULT_TYPE,
    target: dict,
    text: str,
    keyboard: InlineKeyboardMarkup,
) -> bool:
    """Send once per target, retrying temporary Telegram/API failures."""
    target_id = target["id"]
    issue = _target_issue(target_id)
    if issue:
        _record_delivery(ctx.bot_data, target, succeeded=False, error=issue)
        logger.error("[FAKELOGS] Target %s rejected: %s", target_id, issue)
        return False
    last_error = ""
    for attempt in range(1, _MAX_SEND_ATTEMPTS + 1):
        try:
            await ctx.bot.send_message(
                chat_id=target_id,
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
            _record_delivery(ctx.bot_data, target, succeeded=True)
            logger.info(
                "[FAKELOGS] Delivered fake hit to %s on attempt %s.",
                target_id, attempt,
            )
            return True
        except RetryAfter as exc:
            last_error = f"Rate limited: {exc}"
            delay = min(_retry_after_seconds(exc.retry_after), 30.0)
        except TelegramError as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            delay = min(0.75 * attempt, 3.0)
        except Exception as exc:  # Capture unexpected transport/runtime failures too.
            last_error = f"{type(exc).__name__}: {exc}"
            delay = min(0.75 * attempt, 3.0)

        logger.warning(
            "[FAKELOGS] Delivery failed for chat=%s attempt=%s/%s: %s",
            target_id, attempt, _MAX_SEND_ATTEMPTS, last_error,
        )
        if attempt < _MAX_SEND_ATTEMPTS:
            await asyncio.sleep(delay)

    _record_delivery(ctx.bot_data, target, succeeded=False, error=last_error)
    logger.error("[FAKELOGS] Giving up on chat=%s: %s", target_id, last_error)
    return False


async def _job(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    bd = ctx.bot_data
    if not bd.get(_K_ACTIVE):
        return

    _sync_environment_target(bd)
    active_targets = [t for t in _targets(bd) if t.get("enabled", True)]
    active_ids     = [e for e in _ids(bd)     if e.get("enabled", True)]
    lo, hi = _SPEEDS[_speed(bd)]

    if not active_targets or not active_ids:
        reason = "No active targets." if not active_targets else "No enabled fake IDs."
        _delivery_stats(bd)["last_error"] = reason
        _delivery_stats(bd)["last_error_at"] = int(time.time())
        logger.warning("[FAKELOGS] Stream remains active but cannot send: %s", reason)
    else:
        entry = random.choice(active_ids)
        text = _generate_hit(entry, bd)
        delivered = 0
        for target in active_targets:
            if await _send_with_retry(ctx, target, text, _log_kb(bd)):
                delivered += 1

        # A hit counts only when it reached at least one configured destination.
        if delivered:
            entry["count"] = entry.get("count", 0) + 1
        # propagate into total_charged so /me & /status reflect it
        uid_str = str(entry.get("uid", ""))
        if delivered and uid_str and uid_str.lstrip("-").isdigit():
            ud_store = bd.setdefault("user_data", {})
            if uid_str in ud_store:
                ud_store[uid_str]["total_charged"] = (
                    ud_store[uid_str].get("total_charged", 0) + 1
                )

    if bd.get(_K_ACTIVE):
        ctx.job_queue.run_once(_job, random.uniform(lo, hi), name=_JOB)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# UI — MAIN PANEL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _main_text(bd: dict) -> str:
    _sync_environment_target(bd)
    active      = bd.get(_K_ACTIVE, False)
    tgts        = _targets(bd)
    id_list     = _ids(bd)
    delivery    = _delivery_stats(bd)
    on_t        = sum(1 for t in tgts    if t.get("enabled", True))
    on_i        = sum(1 for e in id_list if e.get("enabled", True))
    btn_ct      = sum(1 for l in _links(bd) if l.get("text") and l.get("url"))
    status      = "🟢 RUNNING" if active else "🔴 STOPPED"
    tgt_str     = f"{on_t}/{len(tgts)} active" if tgts else "<i>none — add a target first</i>"
    return (
        f"<b>🎭 Fake Logs Control Panel</b>\n"
        f"──────────────────\n"
        f"<b>Status  ➛</b> {status}\n"
        f"<b>Targets ➛</b> {tgt_str}\n"
        f"<b>IDs     ➛</b> {on_i}/{len(id_list)} enabled\n"
        f"<b>Speed   ➛</b> {_SPEED_LABELS[_speed(bd)]}\n"
        f"<b>Buttons ➛</b> {btn_ct}/3 configured\n"
        f"<b>Delivery ➛</b> {delivery['sent']} sent • {delivery['failed']} failed\n"
        f"──────────────────"
    )

def _main_kb(bd: dict) -> InlineKeyboardMarkup:
    active = bd.get(_K_ACTIVE, False)
    lbl    = "⛔ Stop Logs" if active else "▶️ Start Logs"
    cb     = "fl_stop"      if active else "fl_start"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Add Target",  callback_data="fl_addtarget"),
            InlineKeyboardButton("📋 Targets",     callback_data="fl_targetlist"),
        ],
        [
            InlineKeyboardButton("👤 Add ID",      callback_data="fl_addid"),
            InlineKeyboardButton("👥 Manage IDs",  callback_data="fl_ids"),
        ],
        [
            InlineKeyboardButton("🔗 Buttons",     callback_data="fl_links"),
            InlineKeyboardButton("⚡ Speed",        callback_data="fl_speed"),
            InlineKeyboardButton("📊 Stats",        callback_data="fl_show"),
        ],
        [InlineKeyboardButton("🧪 Test Send", callback_data="fl_test")],
        [InlineKeyboardButton(lbl, callback_data=cb)],
    ])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# UI — TARGETS PANEL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _targets_text(bd: dict) -> str:
    tgts = _targets(bd)
    if not tgts:
        return (
            "<b>📋 Target Channels / Groups</b>\n"
            "──────────────────\n"
            "No targets added yet.\n\n"
            "<b>To add a target:</b>\n"
            "1️⃣ Tap <b>➕ Add Target</b>\n"
            "2️⃣ <b>Forward</b> any message from your channel/group\n"
            "   <i>— or —</i>\n"
            "   Type its <b>@username</b> or <b>invite link</b>\n"
            "   e.g. <code>@mychannel</code> or <code>https://t.me/+abc123</code>\n\n"
            "<i>Bot must be admin in the target channel/group.</i>"
        )
    lines = ["<b>📋 Target Channels / Groups</b>", "──────────────────"]
    for t in tgts:
        icon = "🟢" if t.get("enabled", True) else "🔴"
        source = " <i>(env)</i>" if t.get("source") == "environment" else ""
        failures = t.get("failed", 0)
        health = f" • {failures} error{'s' if failures != 1 else ''}" if failures else ""
        issue = _target_issue(t.get("id"))
        warning = f"\n   ⚠️ {html.escape(issue)}" if issue else ""
        lines.append(
            f"{icon} {html.escape(str(t.get('title', 'Unknown')))}{source}"
            f"  <code>{html.escape(str(t.get('id', '')))}</code>{health}{warning}"
        )
    lines.append("──────────────────")
    return "\n".join(lines)

def _targets_kb(bd: dict) -> InlineKeyboardMarkup:
    tgts = _targets(bd)
    rows = []
    for i, t in enumerate(tgts):
        on  = t.get("enabled", True)
        tog = "🟢 ON" if on else "🔴 OFF"
        rows.append([
            InlineKeyboardButton(t.get("title", f"ID {t['id']}")[:28],
                                 callback_data="fl_noop"),
            InlineKeyboardButton(tog,            callback_data=f"fltgon_{i}"),
            InlineKeyboardButton("❌",           callback_data=f"fltgrm_{i}"),
        ])
    rows.append([
        InlineKeyboardButton("➕ Add Target", callback_data="fl_addtarget"),
        InlineKeyboardButton("🔙 Back",       callback_data="fl_panel"),
    ])
    return InlineKeyboardMarkup(rows)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# UI — IDs PANEL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _ids_text(bd: dict) -> str:
    id_list = _ids(bd)
    if not id_list:
        return (
            "<b>👥 Fake Checker IDs</b>\n──────────────────\n"
            "No IDs added yet.\n\n"
            "Tap <b>➕ Add ID</b> then send:\n"
            "<code>123456789 @username</code>  or  <code>@username</code>"
        )
    lines = ["<b>👥 Fake Checker IDs</b>", "──────────────────"]
    for e in id_list:
        icon = "🟢" if e.get("enabled", True) else "🔴"
        ct   = e.get("count", 0)
        lines.append(f"{icon} {e['display']} — {ct} hit{'s' if ct != 1 else ''}")
    lines.append("──────────────────")
    return "\n".join(lines)

def _ids_kb(bd: dict) -> InlineKeyboardMarkup:
    id_list = _ids(bd)
    rows = []
    for i, e in enumerate(id_list):
        on  = e.get("enabled", True)
        tog = "🟢 ON" if on else "🔴 OFF"
        rows.append([
            InlineKeyboardButton(e["display"][:24], callback_data="fl_noop"),
            InlineKeyboardButton(tog,               callback_data=f"flion_{i}"),
            InlineKeyboardButton("❌",              callback_data=f"flirm_{i}"),
        ])
    rows.append([
        InlineKeyboardButton("➕ Add ID", callback_data="fl_addid"),
        InlineKeyboardButton("🔙 Back",   callback_data="fl_panel"),
    ])
    return InlineKeyboardMarkup(rows)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# UI — SPEED PANEL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _speed_text() -> str:
    return (
        "<b>⚡ Fake Log Speed</b>\n──────────────────\n"
        "How fast fake hits appear.\n"
        "All gaps are <b>randomised</b> — no fixed pattern.\n"
        "──────────────────"
    )

def _speed_kb(bd: dict) -> InlineKeyboardMarkup:
    cur  = _speed(bd)
    rows = [
        [InlineKeyboardButton(
            ("✅ " if k == cur else "    ") + lbl,
            callback_data=f"flspd_{k}",
        )]
        for k, lbl in _SPEED_LABELS.items()
    ]
    rows.append([InlineKeyboardButton("🔙 Back", callback_data="fl_panel")])
    return InlineKeyboardMarkup(rows)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# UI — STATS PANEL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _stats_text(bd: dict) -> str:
    id_list = _ids(bd)
    delivery = _delivery_stats(bd)
    lines = ["<b>📊 Fake Log Stats</b>", "──────────────────"]
    total = 0
    for e in id_list:
        icon   = "🟢" if e.get("enabled", True) else "🔴"
        ct     = e.get("count", 0)
        total += ct
        tag    = "" if e.get("enabled", True) else " <i>(off)</i>"
        lines.append(f"{icon} {e['display']} — <b>{ct}</b>{tag}")
    lines += [
        "──────────────────",
        f"<b>Total fake hits ➛ {total}</b>",
        f"<b>Generated ➛ {delivery['generated']}</b>",
        f"<b>Delivered ➛ {delivery['sent']}</b>",
        f"<b>Failed ➛ {delivery['failed']}</b>",
        f"<b>Speed ➛ {_SPEED_LABELS[_speed(bd)]}</b>",
    ]
    if delivery.get("last_error"):
        lines.append(
            f"<b>Last error ➛</b> <code>{html.escape(delivery['last_error'])}</code>"
        )
    return "\n".join(lines)

def _stats_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑 Clear Stats", callback_data="fl_clrstats")],
        [InlineKeyboardButton("🔙 Back",        callback_data="fl_panel")],
    ])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# UI — LINK BUTTONS PANEL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _links_text(bd: dict) -> str:
    lnks = _links(bd)
    lines = [
        "<b>🔗 Log Message Buttons</b>",
        "──────────────────",
        "These buttons appear on every fake log message.",
        "You can have up to 3. Empty slots are hidden.",
        "──────────────────",
    ]
    for i, lnk in enumerate(lnks, 1):
        txt = lnk.get("text", "").strip() or "<i>empty</i>"
        url = lnk.get("url",  "").strip() or "<i>empty</i>"
        lines.append(f"<b>Button {i}</b>  📝 {txt}\n         🔗 {url}")
    lines.append("──────────────────")
    return "\n".join(lines)

def _links_kb(bd: dict) -> InlineKeyboardMarkup:
    lnks = _links(bd)
    rows = []
    for i, lnk in enumerate(lnks):
        label = lnk.get("text", "").strip() or f"Button {i+1} (empty)"
        rows.append([InlineKeyboardButton(f"✏️ {label[:30]}", callback_data=f"flledit_{i}")])
    rows.append([InlineKeyboardButton("🔙 Back", callback_data="fl_panel")])
    return InlineKeyboardMarkup(rows)

def _link_edit_text(idx: int, bd: dict) -> str:
    lnk = _links(bd)[idx]
    txt = lnk.get("text", "").strip() or "<i>empty</i>"
    url = lnk.get("url",  "").strip() or "<i>empty</i>"
    return (
        f"<b>✏️ Edit Button {idx+1}</b>\n"
        f"──────────────────\n"
        f"<b>Text ➛</b> {txt}\n"
        f"<b>URL  ➛</b> {url}\n"
        f"──────────────────"
    )

def _link_edit_kb(idx: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📝 Set Text", callback_data=f"fllt_{idx}"),
            InlineKeyboardButton("🔗 Set URL",  callback_data=f"fllu_{idx}"),
        ],
        [
            InlineKeyboardButton("🗑 Clear",    callback_data=f"fllc_{idx}"),
            InlineKeyboardButton("🔙 Back",     callback_data="fl_links"),
        ],
    ])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND HANDLERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _cmd_fakeon(upd: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if upd.effective_user.id != OWNER_ID:
        return
    bd = ctx.bot_data
    _sync_environment_target(bd)
    _clear(bd)
    await upd.message.reply_text(
        _main_text(bd), parse_mode="HTML", reply_markup=_main_kb(bd),
    )

async def _cmd_fakeoff(upd: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if upd.effective_user.id != OWNER_ID:
        return
    ctx.bot_data[_K_ACTIVE] = False
    _stop_job(ctx)
    _clear(ctx.bot_data)
    await upd.message.reply_text("<b>⛔ Fake logs stopped.</b>", parse_mode="HTML")


async def _cmd_getid(upd: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Save the current channel/group as a fake-log target for the owner."""
    if upd.effective_user.id != OWNER_ID:
        return

    chat = upd.effective_chat
    if chat.type == "private":
        await upd.message.reply_text(
            "<b>⚠️ Run /getid inside the target channel or group.</b>\n"
            "Or open /fakeon in DM and use <b>➕ Add Target</b> to forward a post.",
            parse_mode="HTML",
        )
        return

    bd = ctx.bot_data
    _sync_environment_target(bd)
    targets = _targets(bd)
    if any(target.get("id") == chat.id for target in targets):
        await upd.message.reply_text(
            f"<b>✅ This chat is already a fake-log target.</b>\n"
            f"<code>{chat.id}</code>",
            parse_mode="HTML",
        )
        return

    title = chat.title or chat.username or str(chat.id)
    targets.append({
        "id": chat.id,
        "title": title,
        "enabled": True,
        "source": "getid",
    })
    await upd.message.reply_text(
        f"<b>✅ Fake-log target saved.</b>\n"
        f"<b>Title ➛</b> {html.escape(title)}\n"
        f"<b>ID ➛</b> <code>{chat.id}</code>\n\n"
        f"Open /fakeon in DM, then tap <b>🧪 Test Send</b>.",
        parse_mode="HTML",
    )


async def _cmd_fakestatus(upd: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner-only delivery diagnostics, including the latest Telegram error."""
    if upd.effective_user.id != OWNER_ID:
        return
    _sync_environment_target(ctx.bot_data)
    await upd.message.reply_text(
        _stats_text(ctx.bot_data), parse_mode="HTML", reply_markup=_stats_kb(),
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CALLBACK HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _cb(upd: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = upd.callback_query
    if q.from_user.id != OWNER_ID:
        await q.answer("⛔ Owner only.", show_alert=True)
        return
    await q.answer()
    bd  = ctx.bot_data
    dat = q.data

    # ── Main panel ────────────────────────────────────────────────
    if dat == "fl_panel":
        _clear(bd)
        await q.edit_message_text(
            _main_text(bd), parse_mode="HTML", reply_markup=_main_kb(bd),
        )

    elif dat == "fl_start":
        _sync_environment_target(bd)
        active_targets = [t for t in _targets(bd) if t.get("enabled", True)]
        invalid_target = next(
            (_target_issue(t.get("id")) for t in active_targets if _target_issue(t.get("id"))),
            "",
        )
        if invalid_target:
            await q.answer(f"⚠️ {invalid_target}", show_alert=True)
            return
        if not active_targets:
            await q.answer("⚠️ Add at least one target channel/group first.", show_alert=True)
            return
        if not [e for e in _ids(bd) if e.get("enabled", True)]:
            await q.answer("⚠️ Add at least one fake ID first.", show_alert=True)
            return
        bd[_K_ACTIVE] = True
        _stop_job(ctx)
        ctx.job_queue.run_once(_job, 3, name=_JOB)
        await q.edit_message_text(
            _main_text(bd), parse_mode="HTML", reply_markup=_main_kb(bd),
        )

    elif dat == "fl_stop":
        bd[_K_ACTIVE] = False
        _stop_job(ctx)
        await q.edit_message_text(
            _main_text(bd), parse_mode="HTML", reply_markup=_main_kb(bd),
        )

    elif dat == "fl_noop":
        pass

    # ── Targets ───────────────────────────────────────────────────
    elif dat == "fl_targetlist":
        _sync_environment_target(bd)
        _clear(bd)
        await q.edit_message_text(
            _targets_text(bd), parse_mode="HTML", reply_markup=_targets_kb(bd),
        )

    elif dat == "fl_addtarget":
        bd[_K_STATE] = "awaiting_target"
        await q.edit_message_text(
            "<b>➕ Add Target Channel / Group</b>\n"
            "──────────────────\n"
            "<b>Method 1 — Forward a message:</b>\n"
            "Forward any message FROM your channel or group to this bot chat.\n"
            "Bot auto-detects the ID.\n\n"
            "<b>Method 2 — Type the username or link:</b>\n"
            "<code>@yourchannel</code>\n"
            "<code>https://t.me/+invitelink</code>\n\n"
            "<i>The bot must be admin in the target channel/group.</i>\n"
            "──────────────────\n"
            "Send /fakeon to cancel.",
            parse_mode="HTML",
        )

    elif dat.startswith("fltgon_"):
        try:
            idx = int(dat.split("_", 1)[1])
        except (ValueError, IndexError):
            return
        tgts = _targets(bd)
        if 0 <= idx < len(tgts):
            tgts[idx]["enabled"] = not tgts[idx].get("enabled", True)
        await q.edit_message_text(
            _targets_text(bd), parse_mode="HTML", reply_markup=_targets_kb(bd),
        )

    elif dat.startswith("fltgrm_"):
        try:
            idx = int(dat.split("_", 1)[1])
        except (ValueError, IndexError):
            return
        tgts = _targets(bd)
        if 0 <= idx < len(tgts):
            removed = tgts.pop(idx)
            await q.answer(f"✅ {removed.get('title','Target')} removed.")
        await q.edit_message_text(
            _targets_text(bd), parse_mode="HTML", reply_markup=_targets_kb(bd),
        )

    # ── IDs ───────────────────────────────────────────────────────
    elif dat == "fl_ids":
        _clear(bd)
        await q.edit_message_text(
            _ids_text(bd), parse_mode="HTML", reply_markup=_ids_kb(bd),
        )

    elif dat == "fl_addid":
        bd[_K_STATE] = "awaiting_id"
        await q.edit_message_text(
            "<b>👤 Add Fake Checker ID</b>\n"
            "──────────────────\n"
            "Send the user info in your next message:\n\n"
            "<code>123456789 @username</code>\n"
            "or just  <code>@username</code>\n\n"
            "<i>This appears as the checker on every fake hit log.</i>\n"
            "──────────────────\n"
            "Send /fakeon to cancel.",
            parse_mode="HTML",
        )

    elif dat.startswith("flion_"):
        try:
            idx = int(dat.split("_", 1)[1])
        except (ValueError, IndexError):
            return
        id_list = _ids(bd)
        if 0 <= idx < len(id_list):
            id_list[idx]["enabled"] = not id_list[idx].get("enabled", True)
        await q.edit_message_text(
            _ids_text(bd), parse_mode="HTML", reply_markup=_ids_kb(bd),
        )

    elif dat.startswith("flirm_"):
        try:
            idx = int(dat.split("_", 1)[1])
        except (ValueError, IndexError):
            return
        id_list = _ids(bd)
        if 0 <= idx < len(id_list):
            removed = id_list.pop(idx)
            await q.answer(f"✅ {removed['display']} removed.")
        await q.edit_message_text(
            _ids_text(bd), parse_mode="HTML", reply_markup=_ids_kb(bd),
        )

    # ── Speed ─────────────────────────────────────────────────────
    elif dat == "fl_speed":
        _clear(bd)
        await q.edit_message_text(
            _speed_text(), parse_mode="HTML", reply_markup=_speed_kb(bd),
        )

    elif dat.startswith("flspd_"):
        spd = dat.split("_", 1)[1]
        if spd in _SPEEDS:
            bd[_K_SPEED] = spd
            await q.answer(f"✅ {_SPEED_LABELS[spd]}")
        await q.edit_message_text(
            _speed_text(), parse_mode="HTML", reply_markup=_speed_kb(bd),
        )

    # ── Stats ─────────────────────────────────────────────────────
    elif dat == "fl_show":
        _clear(bd)
        await q.edit_message_text(
            _stats_text(bd), parse_mode="HTML", reply_markup=_stats_kb(),
        )

    elif dat == "fl_clrstats":
        for e in _ids(bd):
            e["count"] = 0
        for target in _targets(bd):
            target.pop("sent", None)
            target.pop("failed", None)
            target.pop("last_sent_at", None)
            target.pop("last_error", None)
            target.pop("last_error_at", None)
        bd[_K_STATS] = {
            "generated": 0, "sent": 0, "failed": 0,
            "last_error": "", "last_error_at": 0, "last_sent_at": 0,
        }
        await q.answer("✅ Stats cleared.")
        await q.edit_message_text(
            _stats_text(bd), parse_mode="HTML", reply_markup=_stats_kb(),
        )

    # ── Link buttons ──────────────────────────────────────────────
    elif dat == "fl_links":
        _clear(bd)
        await q.edit_message_text(
            _links_text(bd), parse_mode="HTML", reply_markup=_links_kb(bd),
        )

    elif dat == "fl_test":
        _sync_environment_target(bd)
        active_targets = [target for target in _targets(bd) if target.get("enabled", True)]
        if not active_targets:
            await q.answer("⚠️ Add or enable a target first.", show_alert=True)
            return
        invalid_target = next(
            (_target_issue(t.get("id")) for t in active_targets if _target_issue(t.get("id"))),
            "",
        )
        if invalid_target:
            await q.answer(f"⚠️ {invalid_target}", show_alert=True)
            return
        test_text = (
            "<b>🧪 Fake-log delivery test</b>\n"
            "<i>If you can read this, the target channel is configured correctly.</i>"
        )
        successes = 0
        for target in active_targets:
            if await _send_with_retry(ctx, target, test_text, _log_kb(bd)):
                successes += 1
        await q.answer(
            f"✅ Test delivered to {successes}/{len(active_targets)} target(s)."
            if successes else "❌ Test failed. Open 📊 Stats for details.",
            show_alert=True,
        )

    elif dat.startswith("flledit_"):
        try:
            idx = int(dat.split("_", 1)[1])
        except (ValueError, IndexError):
            return
        if 0 <= idx < 3:
            _clear(bd)
            bd[_K_EDIT_IDX] = idx
            await q.edit_message_text(
                _link_edit_text(idx, bd), parse_mode="HTML",
                reply_markup=_link_edit_kb(idx),
            )

    elif dat.startswith("fllt_"):
        try:
            idx = int(dat.split("_", 1)[1])
        except (ValueError, IndexError):
            return
        bd[_K_STATE]    = "awaiting_link_text"
        bd[_K_EDIT_IDX] = idx
        await q.edit_message_text(
            f"<b>📝 Set Text for Button {idx+1}</b>\n"
            f"──────────────────\n"
            f"Send the button label in your next message.\n"
            f"<b>Example:</b> <code>🔥 Join Channel</code>\n"
            f"──────────────────\nSend /fakeon to cancel.",
            parse_mode="HTML",
        )

    elif dat.startswith("fllu_"):
        try:
            idx = int(dat.split("_", 1)[1])
        except (ValueError, IndexError):
            return
        bd[_K_STATE]    = "awaiting_link_url"
        bd[_K_EDIT_IDX] = idx
        await q.edit_message_text(
            f"<b>🔗 Set URL for Button {idx+1}</b>\n"
            f"──────────────────\n"
            f"Send the full link in your next message.\n"
            f"<b>Examples:</b>\n"
            f"<code>https://t.me/+Oda5m4pBcOUyMTA0</code>\n"
            f"<code>https://t.me/yourchannel</code>\n"
            f"──────────────────\nSend /fakeon to cancel.",
            parse_mode="HTML",
        )

    elif dat.startswith("fllc_"):
        try:
            idx = int(dat.split("_", 1)[1])
        except (ValueError, IndexError):
            return
        lnks = _links(bd)
        if 0 <= idx < 3:
            lnks[idx] = (
                {"text": "𝘽𝘼𝙏 ✘ 𝘾𝙃𝙆", "url": _DEFAULT_BOT_URL}
                if idx == 0 else {"text": "", "url": ""}
            )
            await q.answer(f"✅ Button {idx+1} cleared.")
        _clear(bd)
        await q.edit_message_text(
            _links_text(bd), parse_mode="HTML", reply_markup=_links_kb(bd),
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MESSAGE CAPTURE  — handles all awaiting-input states
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _msg(upd: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if upd.effective_user.id != OWNER_ID:
        return

    bd    = ctx.bot_data
    state = bd.get(_K_STATE)
    msg   = upd.message

    if not state:
        return   # nothing waiting — pass through

    # ──────────────────────────────────────────────────────────────
    # awaiting_target: accept forwarded message OR typed text
    # ──────────────────────────────────────────────────────────────
    if state == "awaiting_target":
        # ── Method 1: forwarded message from channel/group ────────
        fwd_chat = getattr(msg, "forward_from_chat", None)
        if fwd_chat:
            cid   = fwd_chat.id
            title = fwd_chat.title or str(cid)
            tgts  = _targets(bd)
            if any(t["id"] == cid for t in tgts):
                _clear(bd)
                await msg.reply_text(
                    f"<b>⚠️ {title} is already in targets.</b>",
                    parse_mode="HTML",
                )
                return
            tgts.append({"id": cid, "title": title, "enabled": True})
            _clear(bd)
            await msg.reply_text(
                f"<b>✅ Target added!</b>\n"
                f"──────────────────\n"
                f"<b>Title ➛</b> {title}\n"
                f"<b>ID    ➛</b> <code>{cid}</code>\n\n"
                f"Use /fakeon to manage targets and start.",
                parse_mode="HTML",
            )
            return

        # ── Method 2: typed @username or invite link ──────────────
        raw = (msg.text or "").strip()
        if not raw:
            await msg.reply_text(
                "<b>❌ Please forward a message from the channel/group\n"
                "or type its @username / invite link.</b>",
                parse_mode="HTML",
            )
            return

        # Normalise: strip spaces, add @ prefix for plain usernames
        query = raw
        if raw.startswith("https://t.me/+") or raw.startswith("https://t.me/"):
            query = raw   # use as-is for invite links and t.me links
        elif raw.startswith("@"):
            query = raw
        elif not raw.startswith("http"):
            query = f"@{raw}"

        try:
            chat  = await ctx.bot.get_chat(query)
            cid   = chat.id
            title = chat.title or chat.username or str(cid)
        except Exception as exc:
            _clear(bd)
            await msg.reply_text(
                f"<b>❌ Could not resolve that channel/group.</b>\n"
                f"<i>{exc}</i>\n\n"
                f"<b>Tips:</b>\n"
                f"• Forward a message FROM the channel instead\n"
                f"• Make sure the bot is admin in that channel\n"
                f"• For private channels use the forward method",
                parse_mode="HTML",
            )
            return

        tgts = _targets(bd)
        if any(t["id"] == cid for t in tgts):
            _clear(bd)
            await msg.reply_text(
                f"<b>⚠️ {title} is already in targets.</b>", parse_mode="HTML",
            )
            return
        tgts.append({"id": cid, "title": title, "enabled": True})
        _clear(bd)
        await msg.reply_text(
            f"<b>✅ Target added!</b>\n"
            f"──────────────────\n"
            f"<b>Title ➛</b> {title}\n"
            f"<b>ID    ➛</b> <code>{cid}</code>\n\n"
            f"Use /fakeon to start.",
            parse_mode="HTML",
        )
        return

    # ──────────────────────────────────────────────────────────────
    # awaiting_id
    # ──────────────────────────────────────────────────────────────
    if state == "awaiting_id":
        raw   = (msg.text or "").strip()
        parts = raw.split()
        uid_val, uname_val = None, None
        for p in parts:
            if p.startswith("@"):
                uname_val = p
            elif p.lstrip("-").isdigit():
                uid_val = p

        if not uid_val and not uname_val:
            await msg.reply_text(
                "<b>❌ Could not parse.</b>\n"
                "Send: <code>123456789 @username</code>\n"
                "or just <code>@username</code>",
                parse_mode="HTML",
            )
            return

        display = uname_val or f"user_{uid_val}"
        link    = (
            f"https://t.me/{uname_val.lstrip('@')}"
            if uname_val else f"tg://user?id={uid_val}"
        )
        key     = uid_val or uname_val
        id_list = _ids(bd)

        if any(e["uid"] == key for e in id_list):
            _clear(bd)
            await msg.reply_text(
                f"<b>⚠️ {display} is already in the list.</b>", parse_mode="HTML",
            )
            return

        id_list.append({"uid": key, "display": display, "link": link,
                         "enabled": True, "count": 0})
        _clear(bd)
        await msg.reply_text(
            f"<b>✅ {display} added!</b>\n"
            f"Use /fakeon → 👥 Manage IDs to toggle or remove.",
            parse_mode="HTML",
        )
        return

    # ──────────────────────────────────────────────────────────────
    # awaiting_link_text / awaiting_link_url
    # ──────────────────────────────────────────────────────────────
    if state == "awaiting_link_text":
        idx  = bd.get(_K_EDIT_IDX, 0)
        lnks = _links(bd)
        raw  = (msg.text or "").strip()
        if 0 <= idx < 3:
            lnks[idx]["text"] = raw
        _clear(bd)
        await msg.reply_text(
            f"<b>✅ Button {idx+1} text set: </b>{raw}\n"
            f"Now set the URL: /fakeon → 🔗 Buttons → ✏️ → 🔗 Set URL",
            parse_mode="HTML",
        )
        return

    if state == "awaiting_link_url":
        idx  = bd.get(_K_EDIT_IDX, 0)
        lnks = _links(bd)
        raw  = (msg.text or "").strip()
        if not _is_valid_url(raw):
            await msg.reply_text(
                "<b>❌ URL must start with https:// or http://</b>\n"
                "Try again or send /fakeon to cancel.",
                parse_mode="HTML",
            )
            return
        if 0 <= idx < 3:
            lnks[idx]["url"] = raw
        _clear(bd)
        lnk_txt = lnks[idx].get("text", "") if 0 <= idx < 3 else ""
        await msg.reply_text(
            f"<b>✅ Button {idx+1} updated!</b>\n"
            f"<b>Text ➛</b> {lnk_txt or '<i>not set</i>'}\n"
            f"<b>URL  ➛</b> {raw}",
            parse_mode="HTML",
        )
        return


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# REGISTER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def register(app: Application) -> None:
    """Call this inside main() before app.run_polling()."""
    app.add_handler(CommandHandler("fakeon",  _cmd_fakeon))
    app.add_handler(CommandHandler("fakeoff", _cmd_fakeoff))
    app.add_handler(CommandHandler("getid", _cmd_getid))
    app.add_handler(CommandHandler("fakestatus", _cmd_fakestatus))

    app.add_handler(CallbackQueryHandler(
        _cb,
        pattern=(
            r"^(fl_panel|fl_start|fl_stop|fl_noop"
            r"|fl_targetlist|fl_addtarget"
            r"|fl_ids|fl_addid"
            r"|fl_speed|fl_show|fl_clrstats|fl_test"
            r"|fl_links"
            r"|fltgon_\d+|fltgrm_\d+"
            r"|flion_\d+|flirm_\d+"
            r"|flspd_\w+"
            r"|flledit_\d+|fllt_\d+|fllu_\d+|fllc_\d+)$"
        ),
    ))

    # message capture: forwards + plain text, owner only, any state
    app.add_handler(MessageHandler(
        (filters.TEXT | filters.FORWARDED) & filters.User(OWNER_ID) & ~filters.COMMAND,
        _msg,
    ))

    logger.info("[FAKELOGS] v4 registered — owner-only, multi-target, 3 link buttons.")
