import logging
import time
import string
import random
import asyncio
import signal
import os
import fcntl
import json
import hmac
import hashlib
from io import BytesIO
from html import escape
from typing import Optional
from datetime import datetime
from telegram import Update, TelegramObject, MessageEntity, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes,
)
from telegram.error import Conflict, BadRequest, NetworkError, Forbidden, TimedOut, RetryAfter
from telegram.request import HTTPXRequest

import aiohttp as _aiohttp

import database as db   # PostgreSQL premium persistence (Railway)

from mst import get_bin_handler as get_bin_lookup_handler

from config import (
    BOT_TOKEN, OWNER_ID, VERSION, DEV_LINK,
    CHANNEL_USERNAME, CHANNEL_LINK, GROUP_LINK, SUPPORT_LINK,
    BOT_LINK, BOT_USERNAME,
    API_TIMEOUT, REFERRAL_CREDITS, LOCK_FILE,
    GATE_URLS, GATE_SITES, PREMIUM_GATES, FORCE_CHANNELS,
    get_bin_info, kb_result,
    tg_emoji, get_plan_emoji_id, get_random_live_emoji,
    E_CARD, E_USER, E_TIME, E_DEV, E_PRO,
    E_LIVE, E_DECLINED, E_ERRORS, E_PROGRESS, E_GATE,
    PLAN_EMOJIS, PRO_EMOJI_ID,
    # Button emoji IDs from mst.py
    BTN_ALL_EMOJI_ID, BTN_STOP_EMOJI_ID,
    PROG_GATE_EMOJI_ID, PROG_LIVE_EMOJI_ID, PROG_DEAD_EMOJI_ID,
    PROG_ERRORS_EMOJI_ID, PROG_PROGRESS_EMOJI_ID,
    CARD_EMOJI_ID, USER_EMOJI_ID, TIME_EMOJI_ID,
    DEV_EMOJI_ID, DECLINED_EMOJI_ID,
)
from sh import (
    cmd_sh,
    get_sh_handler, get_me_handler,
    _check_card_with_retry, SITE_RETRIES, SITE_TIMEOUT,
    run_mass_batch, create_msh_session, MSH_SESSIONS,
    cb_msh_result, cb_msh_stop, _load_sites, _load_proxies,
    probe_all_sites, get_working_sites, start_probe_background, stop_probe_background,
    _send_sticker, get_random_live_emoji,
)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOGGING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger  = logging.getLogger(__name__)
MAX_MSG = 4000

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PREMIUM PERSISTENCE
# Saves/restores premium users across bot restarts.
# File path can be absolute to a mounted volume on Railway.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PREMIUM_FILE = os.environ.get("PREMIUM_FILE", "premium_users.json")

def _save_premium_file(bot_data: dict) -> None:
    """Persist all active (non-expired) premium users to PREMIUM_FILE (JSON backup).
    For the full save (JSON + Postgres), use await _save_premium(bot_data) instead."""
    now       = time.time()
    all_users = bot_data.get("user_data", {})
    premium   = {}
    for uid_str, ud in all_users.items():
        plan    = ud.get("plan", "TRIAL").upper()
        expires = ud.get("expires", 0)
        if plan != "TRIAL" and expires > now:
            premium[uid_str] = {
                "plan":         plan,
                "expires":      expires,
                "name":         ud.get("name", ""),
                "username":     ud.get("username", ""),
                "last_receipt": ud.get("last_receipt", ""),
            }
    try:
        with open(PREMIUM_FILE, "w", encoding="utf-8") as f:
            json.dump(premium, f, indent=2)
        logger.info(f"[PREMIUM] JSON backup: {len(premium)} user(s) → {PREMIUM_FILE}")
    except Exception as exc:
        logger.warning(f"[PREMIUM] JSON save failed: {exc}")


async def _save_premium(bot_data: dict) -> None:
    """Save to JSON backup AND instantly write to Postgres.
    Call this (with await) after every plan grant or removal.
    The JSON write runs in a thread pool so it never blocks the event loop."""
    await asyncio.to_thread(_save_premium_file, bot_data)          # JSON backup (non-blocking)
    await db.save_all_now(bot_data.get("user_data", {}))           # Postgres instant save


def _load_premium_file(bot_data: dict) -> None:
    """Restore premium users from PREMIUM_FILE into bot_data on startup."""
    if not os.path.exists(PREMIUM_FILE):
        logger.info(f"[PREMIUM] {PREMIUM_FILE} not found — starting fresh.")
        return
    try:
        with open(PREMIUM_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
    except Exception as exc:
        logger.warning(f"[PREMIUM] Load failed: {exc}")
        return

    now       = time.time()
    user_data = bot_data.setdefault("user_data", {})
    restored  = 0
    for uid_str, pdata in saved.items():
        expires = pdata.get("expires", 0)
        if expires <= now:
            continue                       # already expired — skip
        plan = pdata.get("plan", "TRIAL").upper()
        if plan == "TRIAL":
            continue
        ud = user_data.setdefault(uid_str, {})
        ud["plan"]    = plan
        ud["expires"] = expires
        if pdata.get("name"):         ud.setdefault("name",         pdata["name"])
        if pdata.get("username"):     ud.setdefault("username",     pdata["username"])
        if pdata.get("last_receipt"): ud.setdefault("last_receipt", pdata["last_receipt"])
        restored += 1

    logger.info(f"[PREMIUM] Restored {restored} premium user(s) from {PREMIUM_FILE}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FORCE-JOIN LIST
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FORCE_JOIN_LIST = [
    ("Batcardchk",      "https://t.me/Batcardchk",      "📢 Main Channel"),
    ("batcardchkGroup", "https://t.me/batcardchkGroup",  "👥 Main Group"),
]

_config_fc = [(u, l) for u, l in FORCE_CHANNELS]
for _fc_entry in FORCE_JOIN_LIST:
    _uname = _fc_entry[0]
    if not any(_uname == u for u, _ in _config_fc):
        _config_fc.append((_uname, _fc_entry[1]))

FORCE_JOIN_FULL: list[tuple[str, str, str]] = []
_label_map = {e[0]: e[2] for e in FORCE_JOIN_LIST}
for _uname, _link in _config_fc:
    _label = _label_map.get(_uname, f"📢 @{_uname}")
    FORCE_JOIN_FULL.append((_uname, _link, _label))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# INSTANCE LOCK
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_lock_file_handle = None

def _stale_lock() -> bool:
    """Return True if the lock file exists but the recorded PID is dead."""
    try:
        with open(LOCK_FILE, "r") as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)          # signal 0 = just check existence
        return False             # process is alive → not stale
    except (FileNotFoundError, ValueError):
        return True              # no file or bad content → treat as stale
    except ProcessLookupError:
        return True              # PID doesn't exist → stale
    except PermissionError:
        return False             # PID exists, different owner → treat as live

def acquire_instance_lock() -> bool:
    global _lock_file_handle
    if _stale_lock():
        try:
            os.unlink(LOCK_FILE)
        except FileNotFoundError:
            pass
    try:
        _lock_file_handle = open(LOCK_FILE, "w")
        fcntl.flock(_lock_file_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_file_handle.write(str(os.getpid()))
        _lock_file_handle.flush()
        return True
    except (IOError, OSError):
        return False

def release_instance_lock():
    global _lock_file_handle
    if _lock_file_handle:
        try:
            fcntl.flock(_lock_file_handle, fcntl.LOCK_UN)
            _lock_file_handle.close()
            os.unlink(LOCK_FILE)
        except Exception:
            pass
        _lock_file_handle = None

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BOLD UNICODE FONT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def B(text: str) -> str:
    bold_map = {
        'A':'𝗔','B':'𝗕','C':'𝗖','D':'𝗗','E':'𝗘','F':'𝗙','G':'𝗚','H':'𝗛',
        'I':'𝗜','J':'𝗝','K':'𝗞','L':'𝗟','M':'𝗠','N':'𝗡','O':'𝗢','P':'𝗣',
        'Q':'𝗤','R':'𝗥','S':'𝗦','T':'𝗧','U':'𝗨','V':'𝗩','W':'𝗪','X':'𝗫',
        'Y':'𝗬','Z':'𝗭','a':'𝗮','b':'𝗯','c':'𝗰','d':'𝗱','e':'𝗲','f':'𝗳',
        'g':'𝗴','h':'𝗵','i':'𝗶','j':'𝗷','k':'𝗸','l':'𝗹','m':'𝗺','n':'𝗻',
        'o':'𝗼','p':'𝗽','q':'𝗾','r':'𝗿','s':'𝘀','t':'𝘁','u':'𝘂','v':'𝘃',
        'w':'𝘄','x':'𝘅','y':'𝘆','z':'𝘇','0':'𝟬','1':'𝟭','2':'𝟮','3':'𝟯',
        '4':'𝟰','5':'𝟱','6':'𝟲','7':'𝟳','8':'𝟴','9':'𝟵',
    }
    return "".join(bold_map.get(ch, ch) for ch in text)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RAW MARKUP — coloured buttons (mst.py style)
#
# Telegram Bot API supports "style" (primary=blue, danger=red)
# and "icon_custom_emoji_id" on inline keyboard buttons.
# python-telegram-bot passes reply_markup by calling .to_dict(),
# so this thin wrapper carries the raw API JSON straight through.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class RawMarkup(TelegramObject):
    """Coloured inline keyboard — passes style/icon_custom_emoji_id through PTB's encoder."""
    __slots__ = ("_data",)

    def __init__(self, inline_keyboard: list):
        super().__init__()
        self._data = {"inline_keyboard": inline_keyboard}

    def to_dict(self, api_kwargs=None) -> dict:
        return self._data

    def to_json(self) -> str:
        return json.dumps(self._data)


def _btn(text: str, *, cb: str = None, url: str = None,
         style: str = None, icon: str = None) -> dict:
    """Build a single raw button dict (mst.py style)."""
    d: dict = {"text": text}
    if cb:   d["callback_data"] = cb
    if url:  d["url"]           = url
    if style: d["style"]        = style
    if icon:  d["icon_custom_emoji_id"] = icon
    return d


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_styled_plan(raw_plan: str) -> str:
    p = raw_plan.upper()
    if p == "CORE":  return B("Core")
    if p == "ELITE": return B("Elite")
    if p == "ROOT":  return B("Root")
    return B("Trial")

def get_plan_icon(raw_plan: str) -> str:
    return "👑" if raw_plan.upper() in ("CORE", "ELITE", "ROOT") else ""

def get_user_data(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> dict:
    uid = str(user_id)
    if "user_data" not in context.bot_data:
        context.bot_data["user_data"] = {}
    if uid not in context.bot_data["user_data"]:
        context.bot_data["user_data"][uid] = {
            "name": "User", "first_name": "User", "last_name": "", "username": "",
            "language_code": "en", "joined": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "last_active": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "credits": 150, "plan": "TRIAL", "expires": 0, "pre_premium_credits": 0,
            "total_refs": 0, "total_checks": 0, "approved_checks": 0, "declined_checks": 0,
            "last_gate": "N/A", "last_card": "N/A", "codes_redeemed": 0, "keys_redeemed": 0,
            "banned": False, "total_charged": 0,
        }
    return context.bot_data["user_data"][uid]

def _update_user_meta(ud: dict, user) -> None:
    ud["first_name"]  = user.first_name or "User"
    ud["last_name"]   = user.last_name or ""
    ud["name"]        = user.full_name or user.first_name or "User"
    ud["last_active"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    if user.username: ud["username"] = user.username
    if getattr(user, "language_code", None): ud["language_code"] = user.language_code

def is_user_premium(ud: dict) -> bool:
    """Returns True if the user has an active (non-expired) premium plan.

    Side-effects on expiry:
      • plan  → "TRIAL"
      • credits → restored to pre_premium_credits (what they had before buying)
      • pre_premium_credits → 0
    Premium users NEVER have credits deducted — they get unlimited checks.
    """
    raw_plan = ud.get("plan", "TRIAL").upper()
    is_prem  = raw_plan != "TRIAL"
    if is_prem and ud.get("expires", 0) <= time.time():
        # Premium expired — restore saved credits
        saved = ud.get("pre_premium_credits", 0)
        ud["plan"]                = "TRIAL"
        ud["credits"]             = max(saved, 0)   # never go negative
        ud["expires"]             = 0
        ud["pre_premium_credits"] = 0
        return False
    return is_prem

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COOLDOWN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SINGLE_CHECK_COOLDOWN = 25

def get_cooldown_remaining(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> float:
    store     = context.bot_data.setdefault("cooldown_store", {})
    last      = store.get(user_id, 0)
    remaining = SINGLE_CHECK_COOLDOWN - (time.time() - last)
    return max(0.0, remaining)

def set_cooldown(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    context.bot_data.setdefault("cooldown_store", {})[user_id] = time.time()

def gen_code(length: int = 10) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))

def gen_receipt() -> str:
    return f"Batamanchk{random.randint(100000, 999999)}-CHK"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SECURE REFERRAL  — HMAC-signed tokens (no forgery)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_REF_SECRET: bytes = BOT_TOKEN.encode("utf-8")

def _ref_token(user_id: int) -> str:
    """Generate a short HMAC-SHA256 token for user_id.
    Format: {user_id}_{16-char hex signature}
    Anyone who guesses/modifies the user_id will get a bad signature."""
    msg = str(user_id).encode("utf-8")
    sig = hmac.new(_REF_SECRET, msg, hashlib.sha256).hexdigest()[:16]
    return f"{user_id}_{sig}"

def _verify_ref_token(token: str):
    """Return referrer_id (int) if the token is authentic, else None."""
    try:
        uid_str, sig = token.rsplit("_", 1)
        uid = int(uid_str)
        expected = hmac.new(_REF_SECRET, str(uid).encode("utf-8"), hashlib.sha256).hexdigest()[:16]
        if hmac.compare_digest(sig, expected):
            return uid
    except Exception:
        pass
    return None

def get_referral_link(user_id: int) -> str:
    return f"https://t.me/{BOT_USERNAME}?start=ref_{_ref_token(user_id)}"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# UI — USER CONTROL HUB  (/start)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def ui_profile(user, context: ContextTypes.DEFAULT_TYPE) -> str:
    ud           = get_user_data(user.id, context)
    raw_plan     = ud.get("plan", "TRIAL").upper()
    expires      = ud.get("expires", 0)
    now          = time.time()
    if raw_plan != "TRIAL" and expires <= now:
        raw_plan = "TRIAL"; ud["plan"] = "TRIAL"; ud["expires"] = 0; expires = 0
    premium      = raw_plan != "TRIAL"
    credits      = "Unlimited" if premium else str(ud.get("credits", 150))
    plan_emoji   = tg_emoji(get_plan_emoji_id(raw_plan), "⭐")
    uname        = escape(f"@{user.username}" if user.username else user.first_name or "User")
    joined       = ud.get("joined", datetime.now().strftime("%Y-%m-%d")).split(" ")[0]
    last_active  = ud.get("last_active", "N/A")
    total_refs   = ud.get("total_refs", 0)
    total_checks = ud.get("total_checks", 0)
    ban_status   = f"{E_ERRORS} {B('Banned')}" if ud.get("banned", False) else f"{E_LIVE} {B('Active')}"

    if premium and expires > now:
        exp_date    = datetime.fromtimestamp(expires).strftime("%Y-%m-%d")
        rem_d       = int((expires - now) / 86400)
        rem_h       = int(((expires - now) % 86400) / 3600)
        expire_line = f"✰ <b>𝐄𝐱𝐩𝐢𝐫𝐞𝐬</b>   ➔ {exp_date} ({rem_d}d {rem_h}h)"
    else:
        expire_line = "✰ <b>𝐄𝐱𝐩𝐢𝐫𝐞𝐬</b>   ➔ Never (Trial)"

    lines = [
        "⭅ <b>𝗨𝗦𝗘𝗥 𝗖𝗢𝗡𝗧𝗥𝗢𝗟 𝗛𝗨𝗕</b> ⭆",
        "━━━━━━━━━━━━━━━━━━━━",
        f"✰ <b>𝐔𝐬𝐞𝐫𝐧𝐚𝐦𝐞</b>  ➔ {uname} {plan_emoji}",
        f"✰ <b>𝐔𝐬𝐞𝐫 𝐈𝐃</b>   ➔ <code>{user.id}</code>",
        f"✰ <b>𝐀𝐜𝐜𝐞𝐬𝐬</b>    ➔ {get_styled_plan(raw_plan)}",
        f"✰ <b>𝐒𝐭𝐚𝐭𝐮𝐬</b>    ➔ {ban_status}",
        f"✰ <b>𝐂𝐫𝐞𝐝𝐢𝐭𝐬</b>   ➔ {credits}",
        f"✰ <b>𝐉𝐨𝐢𝐧𝐞𝐝</b>    ➔ {joined}",
        expire_line,
        "━━━━━━━━━━━━━━━━━━━━",
        f"✰ <b>𝐋𝐚𝐬𝐭 𝐀𝐜𝐭𝐢𝐯𝐞</b> ➔ {last_active}",
        f"✰ <b>𝐓𝐨𝐭𝐚𝐥 𝐂𝐡𝐞𝐜𝐤𝐬</b> ➔ {total_checks}",
        f"✰ <b>𝐑𝐞𝐟𝐞𝐫𝐫𝐚𝐥𝐬</b>  ➔ {total_refs} (+{total_refs * REFERRAL_CREDITS} credits)",
        "━━━━━━━━━━━━━━━━━━━━",
        f"{E_DEV} 𝗩𝗲𝗿𝘀𝗶𝗼𝗻 ➔ {VERSION}  |  <a href='{DEV_LINK}'>Batamanchk</a> {E_PRO}",
    ]
    return "\n".join(lines)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# UI — FULL PROFILE  (PROFILE button)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def ui_full_profile(user, context: ContextTypes.DEFAULT_TYPE) -> str:
    ud            = get_user_data(user.id, context)
    raw_plan      = ud.get("plan", "TRIAL").upper()
    expires       = ud.get("expires", 0)
    now           = time.time()
    if raw_plan != "TRIAL" and expires <= now:
        raw_plan = "TRIAL"; ud["plan"] = "TRIAL"; ud["expires"] = 0; expires = 0
    premium       = raw_plan != "TRIAL"
    credits       = "Unlimited" if premium else str(ud.get("credits", 150))
    plan_emoji    = tg_emoji(get_plan_emoji_id(raw_plan), "⭐")
    uname         = escape(f"@{user.username}" if user.username else user.first_name or "User")
    joined        = ud.get("joined", "N/A")
    last_active   = ud.get("last_active", "N/A")
    total_refs    = ud.get("total_refs", 0)
    total_checks  = ud.get("total_checks", 0)
    approved      = ud.get("approved_checks", 0)
    declined      = ud.get("declined_checks", 0)
    last_gate     = ud.get("last_gate", "N/A")
    last_card     = ud.get("last_card", "N/A")
    codes_red     = ud.get("codes_redeemed", 0)
    keys_red      = ud.get("keys_redeemed", 0)
    ban_status    = f"{E_ERRORS} {B('Banned')}" if ud.get("banned", False) else f"{E_LIVE} {B('Active')}"
    approval_rate = f"{(approved / total_checks * 100):.1f}%" if total_checks > 0 else "N/A"

    if premium and expires > now:
        exp_date     = datetime.fromtimestamp(expires).strftime("%Y-%m-%d %H:%M")
        rem_d        = int((expires - now) / 86400)
        rem_h        = int(((expires - now) % 86400) / 3600)
        expire_line  = (
            f"✰ <b>𝐄𝐱𝐩𝐢𝐫𝐞𝐬</b>   ➔ {exp_date}\n"
            f"✰ <b>𝐓𝐢𝐦𝐞 𝐋𝐞𝐟𝐭</b>  ➔ {rem_d}d {rem_h}h"
        )
        last_receipt = ud.get("last_receipt")
        if last_receipt:
            expire_line += f"\n✰ <b>𝐑𝐞𝐜𝐞𝐢𝐩𝐭</b>   ➔ <code>{last_receipt}</code>"
    else:
        expire_line = "✰ <b>𝐄𝐱𝐩𝐢𝐫𝐞𝐬</b>   ➔ Never (Trial)"

    lines = [
        "⭅ <b>𝗨𝗦𝗘𝗥 𝗣𝗥𝗢𝗙𝗜𝗟𝗘</b> ⭆",
        "━━━━━━━━━━━━━━━━━━━━",
        f"✰ <b>𝐔𝐬𝐞𝐫𝐧𝐚𝐦𝐞</b>  ➔ {uname} {plan_emoji}",
        f"✰ <b>𝐔𝐬𝐞𝐫 𝐈𝐃</b>   ➔ <code>{user.id}</code>",
        f"✰ <b>𝐀𝐜𝐜𝐞𝐬𝐬</b>    ➔ {get_styled_plan(raw_plan)}",
        f"✰ <b>𝐒𝐭𝐚𝐭𝐮𝐬</b>    ➔ {ban_status}",
        f"✰ <b>𝐂𝐫𝐞𝐝𝐢𝐭𝐬</b>   ➔ {credits}",
        f"✰ <b>𝐉𝐨𝐢𝐧𝐞𝐝</b>    ➔ {joined}",
        expire_line,
        "━━━━━━━━━━━━━━━━━━━━",
        f"✰ <b>𝐋𝐚𝐬𝐭 𝐀𝐜𝐭𝐢𝐯𝐞</b>  ➔ {last_active}",
        f"✰ <b>𝐓𝐨𝐭𝐚𝐥 𝐂𝐡𝐞𝐜𝐤𝐬</b> ➔ {total_checks}",
        f"✰ <b>𝐀𝐩𝐩𝐫𝐨𝐯𝐞𝐝</b>   ➔ {approved}",
        f"✰ <b>𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝</b>    ➔ {declined}",
        f"✰ <b>𝐀𝐩𝐩𝐫𝐨𝐯𝐚𝐥 𝐑𝐚𝐭𝐞</b> ➔ {approval_rate}",
        f"✰ <b>𝐋𝐚𝐬𝐭 𝐆𝐚𝐭𝐞</b>   ➔ {last_gate}",
        f"✰ <b>𝐋𝐚𝐬𝐭 𝐁𝐈𝐍</b>    ➔ <code>{last_card}</code>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"✰ <b>𝐑𝐞𝐟𝐞𝐫𝐫𝐚𝐥𝐬</b>   ➔ {total_refs} (+{total_refs * REFERRAL_CREDITS} credits)",
        f"✰ <b>𝐂𝐨𝐝𝐞𝐬</b>      ➔ {codes_red} redeemed",
        f"✰ <b>𝐊𝐞𝐲𝐬</b>       ➔ {keys_red} redeemed",
    ]

    # ── Daily mass limit section (trial users only) ───────────────
    if not premium:
        _today      = datetime.now().strftime("%Y-%m-%d")
        _msh_date   = ud.get("msh_daily_date", "")
        _msh_used   = ud.get("msh_daily_cards", 0) if _msh_date == _today else 0
        _msh_remain = max(0, 500 - _msh_used)
        _msh_status = (
            f"✅ Available ({_msh_remain} cards left)"
            if _msh_used == 0
            else (
                f"🔒 Used ({_msh_used}/500 cards) — resets tomorrow"
                if _msh_used >= 500
                else f"⚡ Partial ({_msh_used}/500 used, {_msh_remain} left)"
            )
        )
        lines += [
            "━━━━━━━━━━━━━━━━━━━━",
            "📊 <b>𝗠𝗔𝗦𝗦 𝗖𝗛𝗘𝗖𝗞𝗘𝗥 𝗟𝗜𝗠𝗜𝗧𝗦 (Trial)</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            f"✰ <b>𝐃𝐚𝐢𝐥𝐲 𝐋𝐢𝐦𝐢𝐭</b>  ➔ 500 cards / day",
            f"✰ <b>𝐔𝐬𝐞𝐝 𝐓𝐨𝐝𝐚𝐲</b>  ➔ {_msh_used} cards",
            f"✰ <b>𝐑𝐞𝐦𝐚𝐢𝐧𝐢𝐧𝐠</b>   ➔ {_msh_remain} cards",
            f"✰ <b>𝐒𝐭𝐚𝐭𝐮𝐬</b>     ➔ {_msh_status}",
            f"✰ <b>𝐂𝐫𝐞𝐝𝐢𝐭𝐬</b>    ➔ {ud.get('credits', 0)} (1 credit = 1 card)",
            "━━━━━━━━━━━━━━━━━━━━",
        ]
    else:
        lines.append("━━━━━━━━━━━━━━━━━━━━")

    lines.append(f"{E_DEV} 𝗩𝗲𝗿𝘀𝗶𝗼𝗻 ➔ {VERSION}  |  <a href='{DEV_LINK}'>Batamanchk</a> {E_PRO}")
    return "\n".join(lines)

def ui_start_screen(user, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Simple welcome screen shown on /start — minimal info, no deep details."""
    ud       = get_user_data(user.id, context)
    raw_plan = ud.get("plan", "TRIAL").upper()
    expires  = ud.get("expires", 0)
    now      = time.time()
    if raw_plan != "TRIAL" and expires <= now:
        raw_plan = "TRIAL"; ud["plan"] = "TRIAL"; ud["expires"] = 0
    premium  = raw_plan != "TRIAL"
    credits  = "∞" if premium else str(ud.get("credits", 150))
    uname    = escape(user.first_name or "User")
    joined   = ud.get("joined", datetime.now().strftime("%Y-%m-%d")).split(" ")[0]
    access   = get_styled_plan(raw_plan)

    return (
        f"<b><a href='{CHANNEL_LINK}'>[❆]</a> Welcome to Batmancardchk Bot 💎</b>\n"
        f"────────────\n"
        f"<b>User</b>    ➳ {uname}\n"
        f"<b>User ID</b> ➳ <code>{user.id}</code>\n"
        f"<b>Access</b>  ➳ {access}\n"
        f"<b>Credits</b> ➳ {credits}\n"
        f"<b>Joined</b>  ➳ {joined}\n"
        f"────────────\n"
        f"Choose an option below.\n"
        f"────────────\n"
        f"{E_DEV} <b>Dev</b>     ➳ <a href='{DEV_LINK}'>Batmancardchk</a> {E_PRO}\n"
        f"<b>Version</b> ➳ {VERSION}"
    )

def gate_info_text(gate_name: str, cmd: str, cost: int) -> str:
    return (
        f"━━━━━━━━━━━━━━━━━\n<b>{gate_name}</b>\n━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Cost</b>    ➳ {cost} Credit(s) per check\n\n"
        f"<b>Usage:</b>\n<code>/{cmd} cc|mm|yy|cvv</code>\n\n"
        f"<b>Example:</b>\n<code>/{cmd} 4111111111111111|12|2026|123</code>\n\n"
        "━━━━━━━━━━━━━━━━━"
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FORCE-SUB CACHE & HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_force_sub_cache: dict = {}
# Cache TTL constants (seconds)
_FS_PASS_TTL  = 300   # confirmed joined: recheck after 5 min
_FS_FAIL_TTL  = 30    # not joined yet: recheck after 30 s (fast re-verify)

async def check_force_sub(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> list:
    """
    Returns a list of (uname, link, label) tuples for channels the user
    has NOT yet joined.  Empty list = all joined → allow through.
    """
    if user_id == OWNER_ID:
        return []

    cached = _force_sub_cache.get(user_id)
    if cached:
        passed, ts, cached_list = cached
        ttl = _FS_PASS_TTL if passed else _FS_FAIL_TTL
        if time.time() - ts < ttl:
            return cached_list   # [] if passed, list of missing if not

    not_joined = []
    for uname, link, label in FORCE_JOIN_FULL:
        try:
            member = await context.bot.get_chat_member(f"@{uname}", user_id)
            if member.status in ("left", "kicked", "restricted"):
                not_joined.append((uname, link, label))
        except Forbidden:
            # Bot is not an admin of this channel — cannot verify membership.
            # Treat as NOT joined so users are forced to join (strict mode).
            logger.warning(
                f"[FORCE-SUB] Bot has no admin rights in @{uname}. "
                "Add the bot as administrator to enable membership checks."
            )
            not_joined.append((uname, link, label))
        except BadRequest as e:
            err = str(e).lower()
            # Telegram sends these when the user is not in the chat
            if any(x in err for x in (
                "user not found", "user_not_participant",
                "participant_id_invalid", "chat not found",
                "not a member", "not found",
            )):
                not_joined.append((uname, link, label))
        except Exception as exc:
            logger.debug(f"[FORCE-SUB] check error for @{uname}: {exc}")
            # Unknown error — don't block the user, skip this channel
            pass

    if not not_joined:
        _force_sub_cache[user_id] = (True, time.time(), [])
    else:
        _force_sub_cache[user_id] = (False, time.time(), not_joined)
    return not_joined

def _force_join_text(not_joined: list) -> str:
    total  = len(FORCE_JOIN_FULL)
    joined = total - len(not_joined)
    lines  = [
        "⭅ <b>𝗝𝗢𝗜𝗡 𝗥𝗘𝗤𝗨𝗜𝗥𝗘𝗗</b> ⭆",
        "━━━━━━━━━━━━━━━━━━━━",
        "To use this bot you must join <b>all</b> our",
        "channels and groups listed below.",
        "",
        f"📊 <b>Progress:</b>  {joined}/{total} joined",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    for uname, _link, label in not_joined:
        lines.append(f"  ✗  {label}  <code>@{uname}</code>")
    lines += [
        "━━━━━━━━━━━━━━━━━━━━",
        "👇 Click each button below to join,",
        "   then press <b>✅ Verify</b>.",
    ]
    return "\n".join(lines)

def kb_force_sub(not_joined: list) -> RawMarkup:
    rows = []
    for uname, link, label in not_joined:
        rows.append([_btn(f"{label}  ➳  @{uname}", url=link, style="primary")])
    rows.append([_btn("✅  I Joined All — Verify Now", cb="check_sub", style="primary")])
    return RawMarkup(rows)


async def require_membership(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    not_joined = await check_force_sub(update.effective_user.id, context)
    if not_joined:
        await update.message.reply_text(_force_join_text(not_joined), parse_mode="HTML", reply_markup=kb_force_sub(not_joined))
        return False
    return True

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BAN CHECK
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def require_not_banned(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    if user_id == OWNER_ID:
        return True
    ud = get_user_data(user_id, context)
    if ud.get("banned", False):
        try:
            await update.message.reply_text(
                f"<b>{E_ERRORS} {B('Banned')}</b>\n──────────\n"
                "You have been banned from using this bot.\n"
                "Contact support if you think this is a mistake.\n"
                "──────────",
                parse_mode="HTML"
            )
        except Exception:
            pass
        return False
    return True

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CARD CHECK RESULT  — mst.py _build_hit_dm() style
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def build_check_result(card_raw: str, gate_name: str, raw_response: str,
                       bin_data: dict, username: str, plan: str,
                       time_taken: str, is_approved: bool,
                       is_timeout: bool = False, is_error: bool = False) -> str:
    """Clean result card — mst.py style with [❆] status line and tg-emoji tags."""
    from config import (CHANNEL_LINK, CARD_EMOJI_ID, TIME_EMOJI_ID, USER_EMOJI_ID,
                        DEV_EMOJI_ID, PRO_EMOJI_ID, PROG_LIVE_EMOJI_ID, PROG_DEAD_EMOJI_ID)

    ch_link  = f'<a href="{CHANNEL_LINK}">[❆]</a>'
    live_eid = get_random_live_emoji()

    if is_timeout:
        status_line = '<b>⏱ TIMEOUT</b>'
        resp_te     = f'<tg-emoji emoji-id="{PROG_ERRORS_EMOJI_ID}">⏱</tg-emoji>'
    elif is_error:
        status_line = '<b>⚠️ ERROR</b>'
        resp_te     = f'<tg-emoji emoji-id="{PROG_ERRORS_EMOJI_ID}">⚠️</tg-emoji>'
    elif is_approved:
        status_line = (f'<b>{ch_link} HIT LIVE '
                       f'<tg-emoji emoji-id="{live_eid}">✅</tg-emoji></b>')
        resp_te     = f'<tg-emoji emoji-id="{PROG_LIVE_EMOJI_ID}">✅</tg-emoji>'
    else:
        status_line = (f'<b>{ch_link} DEAD DECLINED '
                       f'<tg-emoji emoji-id="{PROG_DEAD_EMOJI_ID}">❌</tg-emoji></b>')
        resp_te     = f'<tg-emoji emoji-id="{PROG_DEAD_EMOJI_ID}">❌</tg-emoji>'

    plan_emoji = tg_emoji(get_plan_emoji_id(plan), "⭐")
    plan_label = get_styled_plan(plan)

    bin_txt = "N/A"
    if bin_data and not bin_data.get("error"):
        scheme  = str(bin_data.get("scheme", "N/A")).upper()
        bank    = bin_data.get("bank", "N/A")
        country = str(bin_data.get("country", "N/A")).upper()
        flag    = bin_data.get("country_emoji", "")
        bin_txt = f"{scheme} - {bank} - {flag} {country}".strip("- ")

    uname_display = escape(username)

    return (
        f'{status_line}\n'
        f'\n'
        f'<b><tg-emoji emoji-id="{CARD_EMOJI_ID}">💳</tg-emoji></b>\n'
        f'<b>   ⤷ <code>{card_raw}</code></b>\n'
        f'<b>Gate ➛ {gate_name}</b>\n'
        f'<b>──────────</b>\n'
        f'<b>{resp_te} Resp ➛ {escape(raw_response)}</b>\n'
        f'<b>Bin ➛ <code>{bin_txt}</code></b>\n'
        f'<b>──────────</b>\n'
        f'<b><tg-emoji emoji-id="{TIME_EMOJI_ID}">⏱</tg-emoji> ➛ {time_taken}s</b>\n'
        f'<b><tg-emoji emoji-id="{USER_EMOJI_ID}">👤</tg-emoji> ➛ {uname_display} '
        f'{plan_emoji} ({plan_label})</b>\n'
        f'<b><tg-emoji emoji-id="{DEV_EMOJI_ID}">⚡</tg-emoji> ➛ '
        f'<a href="{DEV_LINK}">Batmancardchk</a> '
        f'<tg-emoji emoji-id="{PRO_EMOJI_ID}">⭐</tg-emoji></b>'
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# KEYBOARDS  — mst.py coloured button style
#   style="primary"  → blue button
#   style="danger"   → red button
#   (no style)       → default grey
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def kb_main(user_id: int) -> RawMarkup:
    return RawMarkup([
        [_btn(B("Checker"),  cb="mgates",    style="primary"),
         _btn(B("Buy Now"),  cb="mprice",    style="primary")],
        [_btn(B("Updates"),  url=CHANNEL_LINK, style="primary"),
         _btn(B("Referral"), cb="mreferral", style="primary")],
        [_btn(B("Profile"),  cb="mprofile",  style="primary"),
         _btn(B("Support"),  url=SUPPORT_LINK, style="primary")],
    ])

def kb_back(cb: str) -> RawMarkup:
    return RawMarkup([[_btn("🔙 " + B("BACK"), cb=cb, style="primary")]])

def kb_price() -> RawMarkup:
    return RawMarkup([
        [_btn("⭐ " + B("1.5$ — 1 Day"),  cb="pay1d", style="primary"),
         _btn("⭐ " + B("8$ — 7 Days"),   cb="pay10", style="primary")],
        [_btn("⭐ " + B("12$ — 15 Days"), cb="pay15", style="primary"),
         _btn("⭐ " + B("25$ — 30 Days"), cb="pay30", style="primary")],
        [_btn("🆘 " + B("SUPPORT"),       url=SUPPORT_LINK, style="primary")],
        [_btn("🔙 " + B("BACK"),          cb="bmain")],
    ])

def kb_payment() -> RawMarkup:
    return RawMarkup([
        [_btn("🆘 " + B("CONTACT SUPPORT"), url=SUPPORT_LINK, style="primary")],
        [_btn("🔙 " + B("BACK"), cb="mprice")],
    ])

def kb_gate_main() -> RawMarkup:
    return RawMarkup([
        [_btn("⚡ " + B("SHOPIFY MASS"), cb="imsh",  style="primary"),
         _btn("🔥 " + B("SHOPIFY SINGLE"), cb="ish", style="primary")],
        [_btn("🔙 " + B("BACK"),    cb="bmain")],
    ])


def kb_upgrade() -> RawMarkup:
    return RawMarkup([
        [_btn("💎 " + B("BUY PREMIUM"), cb="mprice",     style="primary")],
        [_btn("🆘 " + B("SUPPORT"),     url=SUPPORT_LINK)],
    ])

def kb_cooldown() -> RawMarkup:
    return RawMarkup([
        [_btn("💎 " + B("BUY PREMIUM") + " — No Cooldown", cb="mprice", style="primary")],
    ])

def kb_result_raw(is_premium: bool = False) -> RawMarkup:
    if is_premium:
        return RawMarkup([
            [_btn("🤖 " + B("Open Bot"), url=BOT_LINK,      style="primary"),
             _btn("📢 " + B("Channel"),  url=CHANNEL_LINK,  style="primary")],
        ])
    return RawMarkup([
        [_btn("💎 " + B("BUY PREMIUM") + " — Unlimited Checks", cb="mprice", style="primary")],
        [_btn("📢 @Batcardchk", url=CHANNEL_LINK)],
    ])

def kb_msh_result(task_id: str, has_approved: bool, is_premium: bool) -> RawMarkup:
    """End-of-check keyboard: download buttons + optional upgrade row."""
    rows = []
    # Row 1: download buttons
    dl_row = []
    if has_approved:
        dl_row.append(_btn("📄 Approved", cb=f"dl_approved_{task_id}", style="primary"))
    dl_row.append(_btn("📋 ALL Cards", cb=f"dl_all_{task_id}"))
    rows.append(dl_row)
    # Row 2: upgrade nudge for trial users
    if not is_premium:
        rows.append([_btn("💎 " + B("BUY PREMIUM") + " — Unlimited", cb="mprice", style="primary")])
    return RawMarkup(rows)

def kb_fb_owner(key: str) -> RawMarkup:
    return RawMarkup([[
        _btn("✅ Approve", cb=f"fb_ok_{key}", style="primary"),
        _btn("❌ Decline", cb=f"fb_no_{key}", style="danger"),
    ]])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CMD PAGES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CMD_TOTAL_PAGES = 5
CMD_PAGES = {
    1: (
        "⭅ <b>𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦</b> ⭆\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>Available Modules</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>[+] 🔥 Single Checker</b>  (2)\n"
        f"<b>[+] ⚡ Mass Checker</b>   (3)\n"
        f"<b>[+] 👑 Mass Module</b>    (4)  <i>Premium</i>\n"
        f"<b>[+] 🛠 Tools</b>          (4)\n"
        f"<b>[+] 👤 Account</b>        (3)\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Use ▶ Next to explore each module</i>"
    ),
    2: (
        "⭅ <b>🔥 𝗦𝗜𝗡𝗚𝗟𝗘 𝗖𝗛𝗘𝗖𝗞𝗘𝗥</b> ⭆\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>────────────</b>\n"
        "<b>Gate</b>    ➳ Shopify 0-20$\n"
        "<b>Command</b> ➳ <code>/sh</code>\n"
        "<b>Limit</b>   ➳ Unlimited\n"
        "<b>Type</b>    ➳ Single Checker\n"
        "<b>Cost</b>    ➳ ∞ (Premium)\n"
        "<b>Credits</b> ➳ ∞\n"
        "<b>Status</b>  ➳ ✅ Available\n"
        "<b>────────────</b>\n"
        "Usage: <code>/sh cc|mm|yy|cvv</code>"
    ),
    3: (
        "⭅ <b>⚡ 𝗠𝗔𝗦𝗦 𝗖𝗛𝗘𝗖𝗞𝗘𝗥</b> ⭆\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>────────────</b>\n"
        "<b>Gate</b>    ➳ Shopify 0-20$\n"
        "<b>Command</b> ➳ <code>/msh</code>\n"
        "<b>Limit</b>   ➳ Unlimited\n"
        "<b>Type</b>    ➳ Mass Checker\n"
        "<b>Stop</b>    ➳ Button\n"
        "<b>Cost</b>    ➳ ∞ (Premium)\n"
        "<b>Credits</b> ➳ ∞\n"
        "<b>Status</b>  ➳ ✅ Available\n"
        "<b>────────────</b>\n"
        "Reply to a .txt file → <code>/msh</code>"
    ),
    4: (
        "⭅ <b>👑 𝗠𝗔𝗦𝗦 𝗠𝗢𝗗𝗨𝗟𝗘</b> ⭆\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔒 <b>Premium Plan Required</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>/msh</b>  ➳ Shopify Mass 0-20$\n"
        "       Limit ➳ 5000 cards (trial: 1 credit = 1 card)\n"
        "       Reply to a .txt file → <code>/msh</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Upgrade via /plan to unlock these gates</i>"
    ),
    5: (
        "⭅ <b>🛠 𝗧𝗢𝗢𝗟𝗦</b> ⭆\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>/bin</b>   ➳ BIN Lookup\n"
        "        Usage: <code>/bin 411111</code>\n\n"
        "<b>/ping</b>  ➳ Bot Speed Test\n"
        "        Usage: <code>/ping</code>\n\n"
        "<b>/rm</b>    ➳ Redeem Code / Key\n"
        "        Usage: <code>/rm CODE</code>\n\n"
        "<b>/fb</b>    ➳ Submit Feedback\n"
        "        Usage: <code>/fb</code> (reply to photo/video)\n\n"
        "<b>/refer</b> ➳ Refer & Earn\n"
        "        Usage: <code>/refer</code>\n"
        "━━━━━━━━━━━━━━━━━━━━"
    ),
    6: (
        "⭅ <b>👤 𝗔𝗖𝗖𝗢𝗨𝗡𝗧</b> ⭆\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>/start</b> ➳ Open Dashboard\n\n"
        "<b>/plan</b>  ➳ View Premium Plans\n\n"
        "<b>/refer</b> ➳ Referral Program\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>{E_PRO} How Credits Work</b>\n"
        "• Trial users start with 150 credits\n"
        "• Each gate check costs 1 credit\n"
        "• Earn credits by referring friends\n"
        "• Premium = Unlimited credits 👑\n"
        "━━━━━━━━━━━━━━━━━━━━"
    ),
}

def kb_cmd_nav(page: int) -> RawMarkup:
    nav_row = []
    if page > 1:
        nav_row.append(_btn("◀ " + B("PREV"), cb=f"cmd_pg_{page - 1}", style="primary"))
    nav_row.append(_btn(f"📄 {page}/{CMD_TOTAL_PAGES}", cb="cmd_pg_noop"))
    if page < CMD_TOTAL_PAGES:
        nav_row.append(_btn(B("NEXT") + " ▶", cb=f"cmd_pg_{page + 1}", style="primary"))
    return RawMarkup([
        nav_row,
        [_btn("✖ " + B("CLOSE"), cb="bmain", style="danger")],
    ])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# REFERRAL SYSTEM
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def process_referral(new_user_id: int, referrer_id: int,
                            context: ContextTypes.DEFAULT_TYPE) -> bool:
    if new_user_id == referrer_id: return False
    referred_set = context.bot_data.setdefault("referred_users", set())
    if new_user_id in referred_set: return False
    referrer_ud = context.bot_data.get("user_data", {}).get(str(referrer_id))
    if referrer_ud is None: return False
    referred_set.add(new_user_id)
    referrer_ud["credits"]    = referrer_ud.get("credits", 0) + REFERRAL_CREDITS
    referrer_ud["total_refs"] = referrer_ud.get("total_refs", 0) + 1
    try:
        await context.bot.send_message(
            chat_id=referrer_id,
            text=(
                f"<b>{E_LIVE} {B('Referral Bonus')}</b>\n──────────\n"
                f"Someone joined via your link!\n"
                f"<b>Credits Added</b>   ➳ +{REFERRAL_CREDITS}\n"
                f"<b>Total Referrals</b> ➳ {referrer_ud['total_refs']}\n"
                "──────────"
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass
    return True

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GATE PROCESSING  (single checks)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _api_request(session, url: str, card: str, site: str) -> dict:
    if "{card}" in url:
        url = url.replace("{card}", card)
        async with session.get(url) as resp:
            try:    data = await resp.json(content_type=None)
            except: data = {"value": await resp.text()}
    else:
        async with session.get(url, params={"cc": card, "site": site}) as resp:
            try:    data = await resp.json(content_type=None)
            except: data = {"value": await resp.text()}
    return data if isinstance(data, dict) else {"value": str(data)}

async def process_gate(update: Update, context: ContextTypes.DEFAULT_TYPE,
                       gate_key: str, gate_name: str):
    user = update.effective_user
    if not await require_not_banned(update, context): return
    if context.bot_data.get("maintenance") and user.id != OWNER_ID:
        await update.message.reply_text(
            f"<b>{E_ERRORS} {B('Maintenance')}</b>\nBot is under maintenance.", parse_mode="HTML"
        )
        return
    if not context.bot_data.get(f"{gate_key}_on", True):
        await update.message.reply_text(
            f"<b>{E_DECLINED} Gate [{gate_name}] is currently OFF.</b>", parse_mode="HTML"
        )
        return

    if not await require_membership(update, context): return

    ud      = get_user_data(user.id, context)
    premium = is_user_premium(ud)
    _update_user_meta(ud, user)

    if gate_key in PREMIUM_GATES and not premium:
        await update.message.reply_text(
            f"<b>{E_PRO} {B('Premium Only')}</b>\n──────────\nUse /plan to upgrade.",
            parse_mode="HTML", reply_markup=kb_upgrade()
        )
        return

    card_raw = None
    if context.args:
        card_raw = context.args[0].strip()
    elif update.message.reply_to_message and update.message.reply_to_message.text:
        card_raw = update.message.reply_to_message.text.strip()

    if not card_raw:
        await update.message.reply_text(
            f"<b>Usage:</b> <code>/{gate_key} cc|mm|yy|cvv</code>", parse_mode="HTML"
        )
        return

    if not premium:
        credits = ud.get("credits", 0)
        if credits <= 0:
            # Out of credits — invite to upgrade, don't hard-block the UI
            await update.message.reply_text(
                f"<b>{E_PRO} {B('Credits Used Up!')}</b>\n──────────\n"
                f"You've used all your free credits.\n\n"
                f"<b>💎 Upgrade to Premium</b> for:\n"
                f"• Unlimited checks — no credit limit\n"
                f"• No cooldowns\n"
                f"• Mass checking without daily caps\n"
                f"──────────\n"
                f"Tap <b>Buy Now</b> below to get a plan.",
                reply_markup=kb_upgrade(), parse_mode="HTML"
            )
            return

        remaining = get_cooldown_remaining(user.id, context)
        if remaining > 0:
            await update.message.reply_text(
                f"<b>{E_ERRORS} {B('Cooldown')}</b>\n──────────\n"
                f"Please wait <b>{remaining:.1f}s</b> before your next check.\n\n"
                f"{E_PRO} <b>Premium removes all cooldowns.</b>\n"
                "──────────",
                reply_markup=kb_cooldown(), parse_mode="HTML"
            )
            return

        set_cooldown(user.id, context)
        ud["credits"] = credits - 1   # deduct 1 credit per single check

    api_url  = context.bot_data.get(f"gate_url_{gate_key}") or GATE_URLS.get(gate_key, "")
    site_url = GATE_SITES.get(gate_key, "example.com")
    bin_num  = card_raw[:6]

    if not api_url:
        await update.message.reply_text(
            f"<b>{E_ERRORS} Gate API not configured.</b>", parse_mode="HTML"
        )
        return

    _sp_html = f'<b>🔄 Gate ➳ {gate_name}</b>'
    msg = await update.message.reply_text(_sp_html, parse_mode="HTML")
    start_time = time.time()
    uname      = f"@{user.username}" if user.username else user.first_name or "User"
    plan       = ud.get("plan", "TRIAL")

    try:
        timeout = _aiohttp.ClientTimeout(total=API_TIMEOUT)
        async with _aiohttp.ClientSession(timeout=timeout) as session:
            results = await asyncio.gather(
                _api_request(session, api_url, card_raw, site_url),
                get_bin_info(bin_num),
                return_exceptions=True,
            )
        data     = results[0] if not isinstance(results[0], Exception) else {}
        bin_data = results[1] if not isinstance(results[1], Exception) else {"error": True}
        if isinstance(results[0], Exception): raise results[0]

        raw_response = str(
            data.get("value") or data.get("message") or
            data.get("Response") or data.get("category") or "ERROR"
        ).strip()
        is_approved = any(
            w in raw_response.lower()
            for w in ["approved", "captured", "success", "charged", "true"]
        )

        ud["total_checks"] = ud.get("total_checks", 0) + 1
        ud["last_gate"]    = gate_name
        ud["last_card"]    = card_raw[:6] + "xxxxxxxxxx"
        ud["last_active"]  = datetime.now().strftime("%Y-%m-%d %H:%M")
        if is_approved: ud["approved_checks"] = ud.get("approved_checks", 0) + 1
        else:           ud["declined_checks"]  = ud.get("declined_checks", 0) + 1

        time_taken = f"{time.time() - start_time:.2f}"
        text = build_check_result(
            card_raw=card_raw, gate_name=gate_name, raw_response=raw_response,
            bin_data=bin_data, username=uname, plan=plan,
            time_taken=time_taken, is_approved=is_approved,
        )
        await msg.edit_text(text, parse_mode="HTML",
                            reply_markup=kb_result_raw(premium),
                            disable_web_page_preview=True)

    except asyncio.TimeoutError:
        if not premium: ud["credits"] = ud.get("credits", 0) + 1
        time_taken = f"{time.time() - start_time:.2f}"
        text = build_check_result(
            card_raw=card_raw, gate_name=gate_name,
            raw_response="Request Timeout", bin_data={},
            username=uname, plan=plan, time_taken=time_taken,
            is_approved=False, is_timeout=True,
        )
        await msg.edit_text(text, parse_mode="HTML",
                            reply_markup=kb_result_raw(premium),
                            disable_web_page_preview=True)
    except Exception as e:
        if not premium: ud["credits"] = ud.get("credits", 0) + 1
        logger.error(f"Gate [{gate_key}] error: {e}")
        time_taken = f"{time.time() - start_time:.2f}"
        text = build_check_result(
            card_raw=card_raw, gate_name=gate_name,
            raw_response=str(e)[:120], bin_data={},
            username=uname, plan=plan, time_taken=time_taken,
            is_approved=False, is_error=True,
        )
        await msg.edit_text(text, parse_mode="HTML",
                            reply_markup=kb_result_raw(premium),
                            disable_web_page_preview=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GATE ON/OFF  (owner only)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _gate_toggle(update, context, gate: str, state: bool):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data[f"{gate}_on"] = state
    icon = E_LIVE if state else E_DECLINED
    await update.message.reply_text(
        f"<b>{icon} Gate [{gate.upper()}] turned {'ON' if state else 'OFF'}.</b>",
        parse_mode="HTML"
    )

async def cmd_onsh(u, c):    await _gate_toggle(u, c, "sh",   True)
async def cmd_offsh(u, c):   await _gate_toggle(u, c, "sh",   False)


async def cmd_updatesites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /updatesites — Owner only.
    Re-probe all sites and report how many are alive.
    Useful after updating sites.txt or when all cards come back Dead.
    """
    user = update.effective_user
    if user.id != OWNER_ID:
        await update.message.reply_text("❌ Owner only.", parse_mode="HTML")
        return

    from sh import _PROBE_IN_PROGRESS, PROBE_CONCURRENCY, PROBE_TIMEOUT
    if _PROBE_IN_PROGRESS:
        await update.message.reply_text(
            "⏳ <b>Site probe already running.</b> Please wait.", parse_mode="HTML")
        return

    all_sites = _load_sites()
    proxies   = _load_proxies()

    status_msg = await update.message.reply_text(
        f"🔍 <b>Probing {len(all_sites)} sites...</b>\n"
        f"Concurrency: {PROBE_CONCURRENCY} | Timeout: {PROBE_TIMEOUT}s per site\n"
        f"This may take 30–60 seconds.",
        parse_mode="HTML",
    )

    edit_count = [0]
    async def on_progress(done, total):
        edit_count[0] += 1
        if edit_count[0] % 3 != 0:   # only edit every 3rd callback (~every 150 sites)
            return
        try:
            await status_msg.edit_text(
                f"🔍 <b>Probing sites...</b>\n"
                f"Progress: {done}/{total}",
                parse_mode="HTML",
            )
        except Exception:
            pass

    working = await probe_all_sites(all_sites, proxies, on_progress=on_progress)

    await status_msg.edit_text(
        f"✅ <b>Site probe complete!</b>\n\n"
        f"Total sites: <b>{len(all_sites)}</b>\n"
        f"✅ Working: <b>{len(working)}</b>\n"
        f"❌ Dead (404): <b>{len(all_sites) - len(working)}</b>\n\n"
        f"Bot will now use only the {len(working)} working sites for checks.",
        parse_mode="HTML",
    )
async def cmd_onmsh(u, c):   await _gate_toggle(u, c, "msh",  True)
async def cmd_offmsh(u, c):  await _gate_toggle(u, c, "msh",  False)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PREMIUM ACTIVATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def send_activation_msg(user_id: int, plan: str, days: int,
                               context: ContextTypes.DEFAULT_TYPE) -> str:
    receipt  = gen_receipt()
    name, username = "Unknown", None
    try:
        chat     = await context.bot.get_chat(user_id)
        name     = chat.first_name or "Unknown"
        username = chat.username
    except Exception:
        pass

    ud = get_user_data(user_id, context)
    if ud.get("plan", "TRIAL").upper() == "TRIAL":
        ud["pre_premium_credits"] = ud.get("credits", 150)
    expires_ts = time.time() + days * 86400
    ud["name"]         = name
    ud["plan"]         = plan.upper()
    ud["expires"]      = expires_ts
    ud["last_receipt"] = receipt
    if username: ud["username"] = username

    # Persist premium immediately — JSON backup + instant Postgres write
    await _save_premium(context.bot_data)

    plan_emoji   = tg_emoji(get_plan_emoji_id(plan), "⭐")
    exp_date     = datetime.fromtimestamp(expires_ts).strftime("%Y-%m-%d %H:%M")
    display_name = f"@{username}" if username else name
    styled       = get_styled_plan(plan)

    txt = (
        f"<b>{E_LIVE} {B('Access Activated')}</b>\n──────────\n"
        f"<b>User</b>     ➳ {display_name}\n"
        f"<b>Access</b>   ➳ {styled} {plan_emoji}\n"
        f"<b>Days</b>     ➳ {days}\n"
        f"<b>Credits</b>  ➳ Unlimited\n"
        f"<b>Expires</b>  ➳ {exp_date}\n"
        f"<b>Receipt</b>  ➳ <code>{receipt}</code>\n"
        f"──────────\nSave this receipt ID.\n{E_DEV} Batamanchk {E_PRO}"
    )
    try: await context.bot.send_message(chat_id=user_id, text=txt, parse_mode="HTML")
    except Exception: pass
    return receipt

async def resolve_user(target: str, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    target = target.strip().lstrip("@")
    if target.lstrip("-").isdigit(): return int(target)
    for attempt in (f"@{target}", target):
        try: return (await context.bot.get_chat(attempt)).id
        except Exception: continue
    all_users    = context.bot_data.get("user_data", {})
    target_lower = target.lower()
    for uid_str, ud in all_users.items():
        stored = ud.get("username", "").lower().lstrip("@")
        if stored and stored == target_lower: return int(uid_str)
    return None

async def _grant(uid: int, plan: str, days: int,
                 update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud = get_user_data(uid, context)
    ud["plan"]    = plan
    ud["expires"] = time.time() + days * 86400

    display_name  = ud.get("name", "Unknown")
    display_uname = ud.get("username", "")
    try:
        chat = await context.bot.get_chat(uid)
        display_name  = chat.first_name or "Unknown"
        display_uname = chat.username or ""
    except Exception:
        pass

    # Persist so this grant survives a bot restart — JSON + Postgres
    await _save_premium(context.bot_data)

    plan_emoji = tg_emoji(get_plan_emoji_id(plan), "⭐")
    await update.message.reply_text(
        f"<b>{E_LIVE} {B('Premium Granted')}</b>\n──────────\n"
        f"<b>User</b>   ➳ {display_name} (@{display_uname or 'N/A'})\n"
        f"<b>Access</b> ➳ {get_styled_plan(plan)} {plan_emoji}\n"
        f"<b>Days</b>   ➳ {days}\n"
        "──────────",
        parse_mode="HTML"
    )
    await send_activation_msg(uid, plan, days, context)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# OWNER COMMANDS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            f"<b>{E_DEV} {B('Generate Code / Key')}</b>\n──────────\n"
            f"<b>Credit Code:</b>\n"
            f"<code>/gen code &lt;credits&gt;</code>\n"
            f"<code>/gen code &lt;credits&gt; &lt;count&gt;</code>\n\n"
            f"<b>Premium Key:</b>\n"
            f"<code>/gen key &lt;PLAN&gt; &lt;days&gt;</code>\n"
            f"<code>/gen key &lt;PLAN&gt; &lt;days&gt; &lt;count&gt;</code>\n\n"
            f"<b>Plans:</b>  CORE | ELITE | ROOT\n\n"
            f"<b>Examples:</b>\n"
            f"<code>/gen code 50</code>\n"
            f"<code>/gen code 100 5</code>\n"
            f"<code>/gen key ELITE 30</code>\n"
            f"<code>/gen key ROOT 7 3</code>\n"
            f"──────────\n"
            f"Users redeem with: <code>/rm CODE</code>",
            parse_mode="HTML"
        )
        return

    kind = context.args[0].lower()

    if kind == "code":
        try:
            value = int(context.args[1])
            if value <= 0: raise ValueError
        except (ValueError, IndexError):
            await update.message.reply_text(
                f"<b>{E_ERRORS} Credits value must be a positive number.</b>", parse_mode="HTML"
            )
            return
        count = 1
        if len(context.args) >= 3:
            try:
                count = int(context.args[2])
                if count <= 0 or count > 50: raise ValueError
            except ValueError:
                await update.message.reply_text(
                    f"<b>{E_ERRORS} Count must be 1–50.</b>", parse_mode="HTML"
                )
                return

        codes_store = context.bot_data.setdefault("codes", {})
        generated   = []
        for _ in range(count):
            code = gen_code()
            codes_store[code] = {"value": value, "used": False}
            generated.append(code)

        if count == 1:
            await update.message.reply_text(
                f"<b>{E_LIVE} {B('Code Generated')}</b>\n──────────\n"
                f"<b>Code</b>    ➳ <code>{generated[0]}</code>\n"
                f"<b>Credits</b> ➳ +{value}\n"
                f"──────────\n"
                f"Redeem: <code>/rm {generated[0]}</code>",
                parse_mode="HTML"
            )
        else:
            lines = [
                f"<b>{E_LIVE} {B('Codes Generated')}</b>",
                "──────────",
                f"<b>Credits each</b> ➳ +{value}",
                f"<b>Count</b>        ➳ {count}",
                "──────────",
            ]
            for i, c in enumerate(generated, 1):
                lines.append(f"<b>{i}.</b> <code>{c}</code>")
            lines += ["──────────", "Redeem with: <code>/rm CODE</code>"]
            await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    elif kind == "key":
        if len(context.args) < 3:
            await update.message.reply_text(
                f"<b>{E_ERRORS} Usage:</b> <code>/gen key PLAN DAYS [count]</code>",
                parse_mode="HTML"
            )
            return
        plan_arg = context.args[1].upper()
        if plan_arg not in ("CORE", "ELITE", "ROOT"):
            await update.message.reply_text(
                f"<b>{E_ERRORS} Invalid plan.</b> Use: <b>CORE</b>, <b>ELITE</b>, or <b>ROOT</b>",
                parse_mode="HTML"
            )
            return
        try:
            days = int(context.args[2])
            if days <= 0: raise ValueError
        except (ValueError, IndexError):
            await update.message.reply_text(
                f"<b>{E_ERRORS} Days must be a positive number.</b>", parse_mode="HTML"
            )
            return
        count = 1
        if len(context.args) >= 4:
            try:
                count = int(context.args[3])
                if count <= 0 or count > 50: raise ValueError
            except ValueError:
                await update.message.reply_text(
                    f"<b>{E_ERRORS} Count must be 1–50.</b>", parse_mode="HTML"
                )
                return

        keys_store = context.bot_data.setdefault("keys", {})
        plan_emoji = tg_emoji(get_plan_emoji_id(plan_arg), "⭐")
        generated  = []
        for _ in range(count):
            key = gen_code(12)
            keys_store[key] = {"plan": plan_arg, "days": days, "used": False}
            generated.append(key)

        if count == 1:
            await update.message.reply_text(
                f"<b>{E_LIVE} {B('Key Generated')}</b>\n──────────\n"
                f"<b>Key</b>    ➳ <code>{generated[0]}</code>\n"
                f"<b>Plan</b>   ➳ {get_styled_plan(plan_arg)} {plan_emoji}\n"
                f"<b>Days</b>   ➳ {days}\n"
                f"──────────\n"
                f"Redeem: <code>/rm {generated[0]}</code>",
                parse_mode="HTML"
            )
        else:
            lines = [
                f"<b>{E_LIVE} {B('Keys Generated')}</b>",
                "──────────",
                f"<b>Plan</b>  ➳ {get_styled_plan(plan_arg)} {plan_emoji}",
                f"<b>Days</b>  ➳ {days}",
                f"<b>Count</b> ➳ {count}",
                "──────────",
            ]
            for i, k in enumerate(generated, 1):
                lines.append(f"<b>{i}.</b> <code>{k}</code>")
            lines += ["──────────", "Redeem with: <code>/rm KEY</code>"]
            await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    else:
        await update.message.reply_text(
            f"<b>{E_ERRORS} Unknown type.</b> Use: <b>code</b> or <b>key</b>",
            parse_mode="HTML"
        )

async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if len(context.args) < 3:
        await update.message.reply_text(
            f"<b>{E_DEV} {B('Grant Premium')}</b>\n──────────\n"
            f"<b>Usage:</b>\n"
            f"<code>/add @username PLAN DAYS</code>\n"
            f"<code>/add UserID PLAN DAYS</code>\n\n"
            f"<b>Plans:</b>  CORE | ELITE | ROOT\n\n"
            f"<b>Example:</b>\n"
            f"<code>/add @john ELITE 30</code>\n"
            f"<code>/add 123456789 ROOT 7</code>\n"
            f"──────────",
            parse_mode="HTML"
        )
        return
    raw_target = context.args[0]
    uid = await resolve_user(raw_target, context)
    if not uid:
        await update.message.reply_text(
            f"{E_ERRORS} <b>User not found:</b> <code>{raw_target}</code>\n"
            f"Make sure the user has started the bot first.",
            parse_mode="HTML"
        )
        return
    plan_arg = context.args[1].upper()
    if plan_arg not in ("CORE", "ELITE", "ROOT"):
        await update.message.reply_text(
            f"{E_ERRORS} Invalid plan. Use: <b>CORE</b>, <b>ELITE</b>, or <b>ROOT</b>",
            parse_mode="HTML"
        )
        return
    try:
        days = int(context.args[2])
        if days <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text(f"{E_ERRORS} Days must be a positive number.", parse_mode="HTML")
        return
    await _grant(uid, plan_arg, days, update, context)


async def cmd_rem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    target = None
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target = update.message.reply_to_message.from_user.id
    elif context.args:
        target = await resolve_user(context.args[0], context)
    if not target:
        await update.message.reply_text(
            f"<b>Usage:</b> /rem @user|ID or reply → /rem", parse_mode="HTML"
        )
        return
    ud = get_user_data(target, context)
    ud["plan"] = "TRIAL"; ud["expires"] = 0
    await _save_premium(context.bot_data)
    await update.message.reply_text(
        f"<b>{E_DECLINED} Premium removed for <code>{target}</code>.</b>", parse_mode="HTML"
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# OWNER: /find <username|@username|ID>
#   Searches all bot users for a match and shows full
#   profile — plan, credits, bans, checks, join date.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    if not context.args:
        await update.message.reply_text(
            f"<b>{E_DEV} {B('Find User')}</b>\n──────────\n"
            f"<b>Usage:</b>\n"
            f"<code>/find @username</code>\n"
            f"<code>/find username</code>\n"
            f"<code>/find UserID</code>\n"
            f"──────────\n"
            f"Searches all registered bot users.",
            parse_mode="HTML"
        )
        return

    raw = context.args[0]
    now = time.time()

    # ── 1. Try numeric ID or @username via Telegram API ─────────────────
    uid = await resolve_user(raw, context)

    # ── 2. If not found, do a local username substring search ───────────
    if not uid:
        needle = raw.lstrip("@").lower()
        all_users = context.bot_data.get("user_data", {})
        matches = []
        for uid_str, ud in all_users.items():
            stored = ud.get("username", "").lower().lstrip("@")
            name   = ud.get("name", "").lower()
            if stored and needle in stored:
                matches.append((int(uid_str), ud))
            elif needle in name:
                matches.append((int(uid_str), ud))

        if not matches:
            await update.message.reply_text(
                f"{E_ERRORS} <b>No user found for:</b> <code>{raw}</code>\n"
                f"Make sure the user has started the bot first.",
                parse_mode="HTML"
            )
            return

        if len(matches) > 1:
            lines = [f"<b>{E_USER} {B('Multiple Matches')}</b>\n──────────"]
            for mid, mud in matches[:10]:
                ustr = f"@{mud.get('username','')}" if mud.get("username") else str(mid)
                plan = mud.get("plan", "TRIAL").upper()
                lines.append(f"• {mud.get('name','?')} — {ustr} — {get_styled_plan(plan)}")
            lines.append("──────────\nRefine your search to narrow down.")
            await update.message.reply_text("\n".join(lines), parse_mode="HTML")
            return

        uid = matches[0][0]

    # ── 3. Pull profile ──────────────────────────────────────────────────
    ud_t = get_user_data(uid, context)
    try:
        chat = await context.bot.get_chat(uid)
        ud_t["name"]     = chat.first_name or ud_t.get("name", "Unknown")
        ud_t["username"] = chat.username   or ud_t.get("username", "")
    except Exception:
        pass

    raw_plan = ud_t.get("plan", "TRIAL").upper()
    expires  = ud_t.get("expires", 0)
    if raw_plan != "TRIAL" and expires <= now:
        raw_plan = "TRIAL"; expires = 0
    premium    = raw_plan != "TRIAL" and expires > now
    plan_emoji = tg_emoji(get_plan_emoji_id(raw_plan), "⭐")
    uname_d    = f"@{ud_t.get('username','')}" if ud_t.get("username") else f"ID <code>{uid}</code>"
    ban_str    = f"{E_ERRORS} {B('Banned')}" if ud_t.get("banned") else f"{E_LIVE} {B('Active')}"

    if premium:
        rem = expires - now
        expire_line = (
            f"<b>Expires</b>    ➳ {datetime.fromtimestamp(expires).strftime('%Y-%m-%d %H:%M')}\n"
            f"<b>Remaining</b>  ➳ <b>{int(rem//86400)}d {int((rem%86400)//3600)}h</b>"
        )
    else:
        expire_line = f"<b>Expires</b>    ➳ Trial (no expiry)"

    txt = (
        f"<b>{E_USER} {B('User Found')}</b>\n──────────\n"
        f"<b>Name</b>      ➳ {ud_t.get('name','Unknown')}\n"
        f"<b>Username</b>  ➳ {uname_d}\n"
        f"<b>ID</b>        ➳ <code>{uid}</code>\n"
        f"<b>Status</b>    ➳ {ban_str}\n"
        f"──────────\n"
        f"<b>Plan</b>      ➳ {get_styled_plan(raw_plan)} {plan_emoji}\n"
        f"<b>Credits</b>   ➳ {ud_t.get('credits', 150)}\n"
        f"{expire_line}\n"
        f"──────────\n"
        f"<b>Joined</b>    ➳ {ud_t.get('joined', 'N/A')}\n"
        f"<b>Last Active</b> ➳ {ud_t.get('last_active', 'N/A')}\n"
        f"<b>Total Checks</b> ➳ {ud_t.get('total_checks', 0)}\n"
        f"<b>Total Refs</b>   ➳ {ud_t.get('total_refs', 0)}\n"
        f"──────────"
    )
    kb = RawMarkup([
        [
            _btn(f"{E_DECLINED} Ban",    cb=f"owner_ban_{uid}",   style="danger"),
            _btn(f"{E_LIVE} Unban",      cb=f"owner_unban_{uid}", style="primary"),
        ],
        [_btn(f"💎 Grant Plan via /sub {uid}", cb=f"find_sub_{uid}", style="primary")],
    ])
    await update.message.reply_text(txt, parse_mode="HTML", reply_markup=kb)


async def cmd_resub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return

    target_id = None
    target_name, target_uname = "Unknown", ""

    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        ru = update.message.reply_to_message.from_user
        target_id    = ru.id
        target_name  = ru.first_name or "Unknown"
        target_uname = ru.username or ""
    elif context.args:
        raw = context.args[0]
        target_id = await resolve_user(raw, context)
        if not target_id:
            await update.message.reply_text(
                f"{E_ERRORS} <b>User not found:</b> <code>{raw}</code>",
                parse_mode="HTML"
            )
            return
    else:
        await update.message.reply_text(
            f"<b>{E_DEV} {B('Remove Premium')}</b>\n──────────\n"
            f"<b>Usage:</b>\n"
            f"<code>/resub @username</code>\n"
            f"<code>/resub UserID</code>\n"
            f"Or reply to a user's message → <code>/resub</code>\n\n"
            f"<b>Alias:</b> /rsub works too\n"
            f"──────────",
            parse_mode="HTML"
        )
        return

    ud       = get_user_data(target_id, context)
    old_plan = ud.get("plan", "TRIAL").upper()
    old_exp  = ud.get("expires", 0)
    now      = time.time()

    if old_plan == "TRIAL" or old_exp <= now:
        try:
            chat = await context.bot.get_chat(target_id)
            target_name  = chat.first_name or "Unknown"
            target_uname = chat.username or ""
        except Exception:
            target_name  = ud.get("name", "Unknown")
            target_uname = ud.get("username", "")
        uname_d = f"@{target_uname}" if target_uname else f"<code>{target_id}</code>"
        await update.message.reply_text(
            f"{E_ERRORS} <b>{target_name}</b> ({uname_d}) has no active premium.",
            parse_mode="HTML"
        )
        return

    try:
        chat = await context.bot.get_chat(target_id)
        target_name  = chat.first_name or "Unknown"
        target_uname = chat.username or ""
    except Exception:
        target_name  = ud.get("name", "Unknown")
        target_uname = ud.get("username", "")

    ud["plan"]    = "TRIAL"
    ud["expires"] = 0
    await _save_premium(context.bot_data)

    uname_d      = f"@{target_uname}" if target_uname else f"<code>{target_id}</code>"
    old_plan_str = get_styled_plan(old_plan)
    rem_was      = int((old_exp - now) // 86400)

    await update.message.reply_text(
        f"<b>{E_DECLINED} {B('Premium Removed')}</b>\n──────────\n"
        f"<b>User</b>       ➳ {target_name} ({uname_d})\n"
        f"<b>ID</b>         ➳ <code>{target_id}</code>\n"
        f"<b>Plan Was</b>   ➳ {old_plan_str}\n"
        f"<b>Days Left</b>  ➳ {rem_was}d (cancelled)\n"
        f"──────────\n"
        f"<b>Status</b>     ➳ Reset to {B('Trial')}",
        parse_mode="HTML"
    )

    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=(
                f"<b>{E_ERRORS} {B('Subscription Cancelled')}</b>\n──────────\n"
                f"Your <b>{old_plan_str}</b> premium has been removed by the admin.\n"
                f"Use /plan to purchase a new subscription.\n"
                f"──────────"
            ),
            parse_mode="HTML"
        )
    except Exception:
        pass

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BROADCAST  —  /broadcast + /bstatus
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Settings
_BROADCAST_UPDATE_N    = 100   # refresh progress every N users
_BROADCAST_MAX_CONC    = 200   # max simultaneous sends (Telegram rate-safe)

# Lock — prevents two broadcasts running at the same time
_broadcast_lock = asyncio.Lock()


def _broadcast_status_text(total: int, done: int, sent: int,
                            blocked: int, failed: int,
                            finished: bool = False) -> str:
    """Build the live-updating broadcast status card."""
    header   = f"✅ <b>Broadcast Complete</b>" if finished else "📡 <b>Broadcasting…</b>"
    filled   = int((done / total) * 20) if total else 20
    bar      = "█" * filled + "░" * (20 - filled)
    pct      = f"{int(done / total * 100)}%" if total else "100%"
    return (
        f"{header}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"👥 <b>Total</b>   ➛ <b>{total}</b>\n"
        f"📨 <b>Sent</b>    ➛ <b>{sent}</b>\n"
        f"🚫 <b>Blocked</b> ➛ <b>{blocked}</b>\n"
        f"❌ <b>Failed</b>  ➛ <b>{failed}</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"<code>[{bar}]</code> {done}/{total}  ({pct})"
    )


async def _broadcast_worker(bot, status_msg, user_ids: list,
                             src_chat_id: int = None, src_msg_id: int = None,
                             text: str = None):
    """
    Core broadcast engine — runs as a background task.
    • Sends ALL messages concurrently, capped by semaphore.
    • Progress card refreshes every _BROADCAST_UPDATE_N users.
    • Releases _broadcast_lock when done.
    """
    total   = len(user_ids)
    sent    = blocked = failed = done = 0
    sem     = asyncio.Semaphore(_BROADCAST_MAX_CONC)
    counter_lock = asyncio.Lock()

    async def _send_one(uid: int):
        nonlocal sent, blocked, failed, done
        async with sem:
            try:
                if src_chat_id and src_msg_id:
                    # Native copy — no "Forwarded from" header
                    await bot.copy_message(
                        chat_id=uid,
                        from_chat_id=src_chat_id,
                        message_id=src_msg_id,
                    )
                else:
                    await bot.send_message(
                        chat_id=uid, text=text,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                async with counter_lock:
                    sent += 1
            except Forbidden:
                async with counter_lock:
                    blocked += 1
                    logging.debug(f"[broad] blocked by {uid}")
            except BadRequest as e:
                async with counter_lock:
                    failed += 1
                    logging.debug(f"[broad] bad request {uid}: {e}")
            except Exception as e:
                async with counter_lock:
                    failed += 1
                    logging.debug(f"[broad] error {uid}: {e}")
            finally:
                async with counter_lock:
                    done += 1

    # Fire every send concurrently (semaphore keeps it safe)
    tasks        = [asyncio.create_task(_send_one(uid)) for uid in user_ids]
    last_report  = 0

    # Live progress updater loop
    try:
        while True:
            await asyncio.sleep(0.3)
            async with counter_lock:
                cur_done, cur_sent = done, sent
                cur_blocked, cur_failed = blocked, failed
            if cur_done >= total:
                break
            if cur_done - last_report >= _BROADCAST_UPDATE_N:
                try:
                    await status_msg.edit_text(
                        _broadcast_status_text(
                            total, cur_done, cur_sent, cur_blocked, cur_failed
                        ),
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
                last_report = cur_done
    except Exception:
        pass

    # Wait for all sends to settle
    await asyncio.gather(*tasks, return_exceptions=True)

    async with counter_lock:
        fs, fb, ff = sent, blocked, failed

    # Final status card
    try:
        await status_msg.edit_text(
            _broadcast_status_text(total, total, fs, fb, ff, finished=True),
            parse_mode="HTML",
        )
    except Exception:
        pass

    # Release lock so a new broadcast can start
    if _broadcast_lock.locked():
        _broadcast_lock.release()

    logging.info(
        f"[broad] Done — total={total} sent={fs} blocked={fb} failed={ff}"
    )


async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /broadcast — owner only.

    Two modes:
      1. Reply to any message with /broadcast  → copies it natively (no 'Forwarded from')
      2. /broadcast <text>                     → sends a plain-text HTML message
    Runs in the BACKGROUND — other commands still work while it runs.
    """
    if update.effective_user.id != OWNER_ID:
        return

    # ── Usage check ──────────────────────────────────────────────────────────
    has_reply = bool(update.message.reply_to_message)
    has_args  = bool(context.args)

    if not has_reply and not has_args:
        await update.message.reply_text(
            "↩️ <b>Usage:</b>\n"
            "• Reply to any message with <b>/broadcast</b> — copies it to all users\n"
            "• <b>/broadcast</b> &lt;text&gt; — sends a text message to all users\n\n"
            "<i>No 'Forwarded from' header. Runs in background.</i>",
            parse_mode="HTML",
        )
        return

    # ── Duplicate-broadcast guard ────────────────────────────────────────────
    if _broadcast_lock.locked():
        await update.message.reply_text(
            "⚠️ A broadcast is already in progress.\n"
            "Use /bstatus to check, or wait for it to finish.",
        )
        return

    await _broadcast_lock.acquire()

    try:
        # Collect all known user IDs from bot_data
        all_users = list(context.bot_data.get("user_data", {}).keys())
        user_ids  = []
        for uid_str in all_users:
            try:
                user_ids.append(int(uid_str))
            except ValueError:
                pass

        total = len(user_ids)
        if total == 0:
            await update.message.reply_text("⚠️ No users found in user_data.")
            _broadcast_lock.release()
            return

        # Determine source
        src_chat_id = src_msg_id = None
        text        = None
        if has_reply:
            src_chat_id = update.message.reply_to_message.chat_id
            src_msg_id  = update.message.reply_to_message.message_id
        else:
            text = " ".join(context.args)

        # Initial status card
        status_msg = await update.message.reply_text(
            _broadcast_status_text(total, 0, 0, 0, 0),
            parse_mode="HTML",
        )

        # Confirm + launch in background
        await update.message.reply_text(
            f"🚀 <b>Broadcast started!</b>\n"
            f"Sending to <b>{total}</b> users in background…\n\n"
            f"<i>Progress updates every {_BROADCAST_UPDATE_N} users.</i>",
            parse_mode="HTML",
        )

        asyncio.create_task(
            _broadcast_worker(
                context.bot, status_msg, user_ids,
                src_chat_id=src_chat_id, src_msg_id=src_msg_id,
                text=text,
            )
        )

    except Exception as e:
        if _broadcast_lock.locked():
            _broadcast_lock.release()
        logging.error(f"[broad] Failed to start: {e}")
        await update.message.reply_text(f"❌ Error starting broadcast: {e}")


async def cmd_bstatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check whether a broadcast is currently running."""
    if update.effective_user.id != OWNER_ID:
        return
    if _broadcast_lock.locked():
        await update.message.reply_text(
            "📡 <b>Status:</b> Broadcast is currently running…",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            "✅ <b>Status:</b> No broadcast in progress.",
            parse_mode="HTML",
        )

async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    uid = None
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        uid = update.message.reply_to_message.from_user.id
    elif context.args:
        uid = await resolve_user(context.args[0], context)
    if not uid:
        await update.message.reply_text(
            f"<b>Usage:</b> /ban @user|ID or reply → /ban", parse_mode="HTML"
        )
        return
    if uid == OWNER_ID:
        await update.message.reply_text(f"{E_ERRORS} Cannot ban the owner.", parse_mode="HTML"); return
    get_user_data(uid, context)["banned"] = True
    await update.message.reply_text(
        f"<b>{E_ERRORS} User <code>{uid}</code> has been banned.</b>", parse_mode="HTML"
    )
    try:
        await context.bot.send_message(
            chat_id=uid,
            text=(
                f"<b>{E_ERRORS} {B('Banned')}</b>\n──────────\n"
                "You have been banned from using this bot.\n"
                "Contact support if you think this is a mistake.\n"
                "──────────"
            ),
            parse_mode="HTML"
        )
    except Exception: pass

async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    uid = None
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        uid = update.message.reply_to_message.from_user.id
    elif context.args:
        uid = await resolve_user(context.args[0], context)
    if not uid:
        await update.message.reply_text(
            f"<b>Usage:</b> /unban @user|ID or reply → /unban", parse_mode="HTML"
        )
        return
    get_user_data(uid, context)["banned"] = False
    await update.message.reply_text(
        f"<b>{E_LIVE} User <code>{uid}</code> has been unbanned.</b>", parse_mode="HTML"
    )
    try:
        await context.bot.send_message(
            chat_id=uid,
            text=(
                f"<b>{E_LIVE} {B('Unbanned')}</b>\n──────────\n"
                "You can now use the bot again.\n──────────"
            ),
            parse_mode="HTML"
        )
    except Exception: pass

async def cmd_allcm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    await update.message.reply_text(
        "<b>🦇 ALL COMMANDS</b>\n━━━━━━━━━━━━━━━━━\n\n"
        f"<b>{E_DEV} OWNER ONLY:</b>\n"
        "/allcm ➳ Show all commands\n"
        "/allsub ➳ All live premium users\n"
        "/info [user] ➳ Full user info\n"
        "/find @user|ID ➳ Search any user + full profile\n"
        "/gen code &lt;val&gt; [count] ➳ Gen credit code(s)\n"
        "/gen key &lt;plan&gt; &lt;days&gt; [count] ➳ Gen premium key(s)\n"
        "/1day [count] ➳ Gen 1-day CORE key(s)\n"
        "/add @user PLAN DAYS ➳ Grant premium\n"
        "/sub @user|ID ➳ View user sub + grant plan buttons\n"
        "/resub @user|ID ➳ Remove active premium\n"
        "/rsub @user|ID ➳ Same as /resub\n"
        "/rem &lt;user&gt; ➳ Remove premium (legacy)\n"
        "/ban &lt;user&gt; ➳ Ban user\n"
        "/unban &lt;user&gt; ➳ Unban user\n"
        "/broadcast &lt;msg&gt; ➳ Broadcast\n"
        "/maintenance on|off ➳ Maintenance mode\n"
        "/onsh /offsh ➳ Toggle Shopify gate\n"
        "/onmsh /offmsh ➳ Toggle Shopify Mass gate\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        f"<b>{E_PRO} PREMIUM USER COMMANDS:</b>\n"
        "/sh ➳ Shopify Single Checker\n"
        "/msh ➳ Shopify Mass 0-20$ (trial: 1cr=1card, limit 5000)\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        f"<b>{E_LIVE} TRIAL / FREE USER COMMANDS:</b>\n"
        "/start ➳ Dashboard\n/plan ➳ Premium plans\n"
        "/sub ➳ My subscription\n/sub @user|ID ➳ [Owner] View & grant plan\n/bin ➳ BIN lookup\n"
        "/refer ➳ Referral link\n/rm ➳ Redeem code or key\n"
        "/ping ➳ Bot speed test\n/fb ➳ Send feedback\n"
        "━━━━━━━━━━━━━━━━━",
        parse_mode="HTML"
    )

async def cmd_allsub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    now     = time.time()
    all_u   = context.bot_data.get("user_data", {})
    premium = [
        (uid_s, ud) for uid_s, ud in all_u.items()
        if ud.get("plan", "TRIAL").upper() != "TRIAL" and ud.get("expires", 0) > now
    ]
    if not premium:
        await update.message.reply_text(
            f"<b>{E_USER} No active premium users.</b>", parse_mode="HTML"
        )
        return

    premium.sort(key=lambda x: x[1].get("expires", 0))
    lines = [f"<b>{E_PRO} {B('Live Premium Users')} ➳ {len(premium)}</b>\n──────────"]
    for idx, (uid_s, ud) in enumerate(premium, 1):
        uname_d = f"@{ud.get('username','')}" if ud.get("username") else ud.get("name", "?")
        plan    = ud.get("plan", "TRIAL").upper()
        expires = ud.get("expires", 0)
        rem_d   = int((expires - now) // 86400)
        rem_h   = int(((expires - now) % 86400) // 3600)
        lines.append(
            f"<b>{idx}.</b> <code>{uid_s}</code> | {uname_d}\n"
            f"    ➳ {get_styled_plan(plan)} | <b>{rem_d}d {rem_h}h left</b>"
        )

    txt = "\n".join(lines)
    if len(txt) > 4000:
        chunk = ""
        for line in lines:
            if len(chunk) + len(line) + 1 > 4000:
                await update.message.reply_text(chunk, parse_mode="HTML")
                chunk = line + "\n"
            else:
                chunk += line + "\n"
        if chunk:
            await update.message.reply_text(chunk, parse_mode="HTML")
    else:
        await update.message.reply_text(txt, parse_mode="HTML")

async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    now = time.time()

    if not context.args and not (
        update.message.reply_to_message and update.message.reply_to_message.from_user
    ):
        all_users     = context.bot_data.get("user_data", {})
        if not all_users:
            await update.message.reply_text("No users found."); return
        total         = len(all_users)
        premium_count = sum(
            1 for ud in all_users.values()
            if ud.get("plan", "TRIAL").upper() != "TRIAL" and ud.get("expires", 0) > now
        )
        banned_count  = sum(1 for ud in all_users.values() if ud.get("banned", False))
        trial_count   = total - premium_count

        header = (
            f"<b>{E_USER} All Users</b>\n──────────\n"
            f"<b>Total</b>   ➳ {total}\n"
            f"<b>Premium</b> ➳ {premium_count}\n"
            f"<b>Trial</b>   ➳ {trial_count}\n"
            f"<b>Banned</b>  ➳ {banned_count}\n"
            "──────────\n"
        )
        lines = []
        for uid_str, ud in list(all_users.items())[:30]:
            rp   = ud.get("plan", "TRIAL").upper()
            ex   = ud.get("expires", 0)
            if rp != "TRIAL" and ex <= now: rp = "TRIAL"
            prem = rp != "TRIAL" and ex > now
            ban  = f"{E_ERRORS}" if ud.get("banned", False) else f"{E_LIVE}"
            uname_d = f"@{ud.get('username','')}" if ud.get("username") else ud.get("name", "?")
            rem  = f"{int((ex-now)//86400)}d" if prem else "—"
            lines.append(f"{ban} <code>{uid_str}</code> | {uname_d} | {get_styled_plan(rp)} | {rem}")
        txt = header + "\n".join(lines)
        if total > 30:
            txt += f"\n\n...and {total - 30} more. Use /info @user or /info ID."
        await update.message.reply_text(txt, parse_mode="HTML")
        return

    target_id, target_name, target_username = None, "N/A", None
    target_last_name, target_lang = "", "N/A"

    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        ru = update.message.reply_to_message.from_user
        target_id, target_name = ru.id, ru.first_name or "N/A"
        target_last_name, target_username, target_lang = ru.last_name or "", ru.username, ru.language_code or "N/A"
    elif context.args:
        raw = " ".join(context.args).strip().lstrip("@")
        if raw.lstrip("-").isdigit():
            target_id = int(raw)
        else:
            try:
                chat = await context.bot.get_chat(f"@{raw}")
                target_id, target_name = chat.id, chat.first_name or "N/A"
                target_last_name, target_username = getattr(chat, "last_name", "") or "", chat.username
            except Exception: pass
            if not target_id:
                raw_lower = raw.lower()
                for uid_str, ud in context.bot_data.get("user_data", {}).items():
                    if (raw_lower in ud.get("username", "").lower().lstrip("@") or
                            raw_lower in ud.get("name", "").lower()):
                        target_id = int(uid_str)
                        target_name, target_username = ud.get("name", "N/A"), ud.get("username")
                        target_lang = ud.get("language_code", "N/A")
                        break

    if not target_id:
        await update.message.reply_text(
            f"<b>Usage:</b>\n/info — all users\n/info @username\n/info 123456789\nOr reply → /info",
            parse_mode="HTML"
        )
        return

    if target_name == "N/A":
        try:
            chat = await context.bot.get_chat(target_id)
            target_name, target_last_name, target_username = (
                chat.first_name or "N/A", getattr(chat, "last_name", "") or "", chat.username
            )
        except Exception: pass

    uid_str  = str(target_id)
    udata    = context.bot_data.get("user_data", {}).get(uid_str, {})
    raw_plan = udata.get("plan", "TRIAL").upper()
    expires  = udata.get("expires", 0)
    if raw_plan != "TRIAL" and expires <= now: raw_plan = "TRIAL"; expires = 0
    premium  = raw_plan != "TRIAL" and expires > now
    credits_d = "Unlimited" if premium else str(udata.get("credits", 150))
    banned   = udata.get("banned", False)

    plan_emoji  = tg_emoji(get_plan_emoji_id(raw_plan), "⭐")
    full_name   = f"{target_name} {target_last_name}".strip()
    uname_d     = f"@{target_username}" if target_username else "None"
    total_refs  = udata.get("total_refs", 0)
    total_checks = udata.get("total_checks", 0)
    approved_checks = udata.get("approved_checks", 0)
    declined_checks = udata.get("declined_checks", 0)
    approval_rate   = f"{(approved_checks / total_checks * 100):.1f}%" if total_checks > 0 else "N/A"
    ban_icon        = f"{E_ERRORS} {B('Banned')}" if banned else f"{E_LIVE} {B('Active')}"

    txt = (
        f"<b>{E_USER} {B('User Info')}</b>\n──────────\n"
        f"<b>Name</b>       ➳ {full_name}\n"
        f"<b>Username</b>   ➳ {uname_d}\n"
        f"<b>ID</b>         ➳ <code>{target_id}</code>\n"
        f"<b>Status</b>     ➳ {ban_icon}\n"
        "──────────\n"
        f"<b>Plan</b>       ➳ {get_styled_plan(raw_plan)} {plan_emoji}\n"
        f"<b>Credits</b>    ➳ {credits_d}\n"
    )
    if premium and expires > now:
        rem = expires - now
        txt += (
            f"<b>Expires</b>    ➳ {datetime.fromtimestamp(expires).strftime('%Y-%m-%d %H:%M')}\n"
            f"<b>Remaining</b>  ➳ {int(rem // 86400)}d {int((rem % 86400) // 3600)}h\n"
        )
    last_receipt = udata.get("last_receipt")
    if last_receipt: txt += f"<b>Receipt</b>    ➳ <code>{last_receipt}</code>\n"
    txt += (
        "──────────\n"
        f"<b>Joined</b>      ➳ {udata.get('joined', 'N/A')}\n"
        f"<b>Last Active</b> ➳ {udata.get('last_active', 'N/A')}\n"
        "──────────\n"
        f"<b>Total Checks</b> ➳ {total_checks}\n"
        f"<b>Approved</b>     ➳ {approved_checks}\n"
        f"<b>Declined</b>     ➳ {declined_checks}\n"
        f"<b>Rate</b>         ➳ {approval_rate}\n"
        f"<b>Last Gate</b>    ➳ {udata.get('last_gate', 'N/A')}\n"
        f"<b>Last BIN</b>     ➳ <code>{udata.get('last_card', 'N/A')}</code>\n"
        "──────────\n"
        f"<b>Referrals</b>    ➳ {total_refs}\n"
        f"<b>Codes</b>        ➳ {udata.get('codes_redeemed', 0)} redeemed\n"
        f"<b>Keys</b>         ➳ {udata.get('keys_redeemed', 0)} redeemed\n"
        "──────────"
    )
    action_kb = RawMarkup([
        [
            _btn(f"{E_ERRORS} Ban"    if not banned else f"{E_LIVE} Unban",
                 cb=f"owner_ban_{target_id}" if not banned else f"owner_unban_{target_id}",
                 style="danger" if not banned else "primary"),
            _btn(f"{E_DECLINED} Remove Premium",
                 cb=f"owner_resub_{target_id}", style="danger"),
        ],
        [_btn("🔙 Back", cb="owner_info_back")],
    ])
    await update.message.reply_text(txt, parse_mode="HTML", reply_markup=action_kb)

async def cmd_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args:
        state = context.bot_data.get("maintenance", False)
        await update.message.reply_text(
            f"Maintenance is currently: <b>{'ON' if state else 'OFF'}</b>\n"
            "Use: /maintenance on|off",
            parse_mode="HTML"
        )
        return
    arg = context.args[0].lower()
    if arg in ("on", "1", "true"):
        context.bot_data["maintenance"] = True
        await update.message.reply_text(
            f"<b>{E_ERRORS} {B('Maintenance Mode ON.')}</b> Users cannot use commands.", parse_mode="HTML"
        )
    elif arg in ("off", "0", "false"):
        context.bot_data["maintenance"] = False
        await update.message.reply_text(
            f"<b>{E_LIVE} {B('Maintenance Mode OFF.')}</b> Bot is live.", parse_mode="HTML"
        )
    else:
        await update.message.reply_text("Use: /maintenance on|off")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# USER COMMANDS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    now  = time.time()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # OWNER: /sub @user | /sub ID | reply → /sub
    #   Shows target user's plan + inline buttons to grant
    #   CORE / ELITE / ROOT with preset days instantly.
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    has_target = bool(context.args) or (
        update.message.reply_to_message and
        update.message.reply_to_message.from_user
    )
    if user.id == OWNER_ID and has_target:
        # ── Resolve target ──────────────────────────────────
        if update.message.reply_to_message and update.message.reply_to_message.from_user:
            ru = update.message.reply_to_message.from_user
            target_id    = ru.id
            target_name  = ru.first_name or "Unknown"
            target_uname = ru.username or ""
        else:
            raw = context.args[0]
            target_id = await resolve_user(raw, context)
            if not target_id:
                await update.message.reply_text(
                    f"{E_ERRORS} <b>User not found:</b> <code>{raw}</code>\n"
                    f"Make sure the user has started the bot first.",
                    parse_mode="HTML"
                )
                return
            target_name, target_uname = "Unknown", ""
            try:
                chat = await context.bot.get_chat(target_id)
                target_name  = chat.first_name or "Unknown"
                target_uname = chat.username or ""
            except Exception:
                ud_t = get_user_data(target_id, context)
                target_name  = ud_t.get("name", "Unknown")
                target_uname = ud_t.get("username", "")

        # ── Current plan info ───────────────────────────────
        ud_t     = get_user_data(target_id, context)
        raw_plan = ud_t.get("plan", "TRIAL").upper()
        expires  = ud_t.get("expires", 0)
        if raw_plan != "TRIAL" and expires <= now:
            raw_plan = "TRIAL"; expires = 0
        premium    = raw_plan != "TRIAL" and expires > now
        plan_emoji = tg_emoji(get_plan_emoji_id(raw_plan), "⭐")
        uname_d    = f"@{target_uname}" if target_uname else f"<code>{target_id}</code>"

        if premium:
            rem = expires - now
            expire_line = (
                f"<b>Expires</b>   ➳ {datetime.fromtimestamp(expires).strftime('%Y-%m-%d %H:%M')}\n"
                f"<b>Remaining</b> ➳ <b>{int(rem//86400)}d {int((rem%86400)//3600)}h</b>"
            )
        else:
            expire_line = "<b>Expires</b>   ➳ Trial (no expiry)"

        txt = (
            f"<b>{E_USER} {B('User Subscription')}</b>\n──────────\n"
            f"<b>Name</b>     ➳ {target_name}\n"
            f"<b>Username</b> ➳ {uname_d}\n"
            f"<b>ID</b>       ➳ <code>{target_id}</code>\n"
            f"──────────\n"
            f"<b>Plan</b>     ➳ {get_styled_plan(raw_plan)} {plan_emoji}\n"
            f"{expire_line}\n"
            f"──────────\n"
            f"<b>Grant a Plan:</b>"
        )
        kb = RawMarkup([
            [
                _btn("⭐ CORE · 7d",   cb=f"ogs_CORE_7_{target_id}",
                     style="primary", icon=PROG_LIVE_EMOJI_ID),
                _btn("💎 ELITE · 15d", cb=f"ogs_ELITE_15_{target_id}",
                     style="primary", icon=PROG_LIVE_EMOJI_ID),
                _btn("👑 ROOT · 30d",  cb=f"ogs_ROOT_30_{target_id}",
                     style="primary", icon=PROG_LIVE_EMOJI_ID),
            ],
            [
                _btn("⭐ CORE · 15d",  cb=f"ogs_CORE_15_{target_id}",  style="primary"),
                _btn("💎 ELITE · 30d", cb=f"ogs_ELITE_30_{target_id}", style="primary"),
                _btn("👑 ROOT · 60d",  cb=f"ogs_ROOT_60_{target_id}",  style="primary"),
            ],
            [_btn(f"{E_DECLINED} Remove Plan", cb=f"owner_resub_{target_id}",
                  style="danger", icon=PROG_DEAD_EMOJI_ID)],
        ])
        await update.message.reply_text(txt, parse_mode="HTML", reply_markup=kb)
        return

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # REGULAR USER (and owner without args): own subscription
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    ud       = get_user_data(user.id, context)
    raw_plan = ud.get("plan", "TRIAL").upper()
    expires  = ud.get("expires", 0)
    if raw_plan != "TRIAL" and expires <= now:
        raw_plan = "TRIAL"; ud["plan"] = "TRIAL"; ud["expires"] = 0; expires = 0
    premium    = raw_plan != "TRIAL" and expires > now
    uname      = f"@{user.username}" if user.username else user.first_name or "User"
    plan_emoji = tg_emoji(get_plan_emoji_id(raw_plan), "⭐")
    credits_d  = "Unlimited" if premium else str(ud.get("credits", 150))

    if premium:
        rem     = expires - now
        rem_d   = int(rem // 86400)
        rem_h   = int((rem % 86400) // 3600)
        exp_str = datetime.fromtimestamp(expires).strftime("%Y-%m-%d %H:%M")
        expire_line = (
            f"<b>Expires</b>    ➳ {exp_str}\n"
            f"<b>Remaining</b>  ➳ <b>{rem_d} days {rem_h} hours</b>"
        )
    else:
        expire_line = "<b>Expires</b>    ➳ Trial (no expiry)"

    txt = (
        f"<b>{E_USER} {B('My Subscription')}</b>\n"
        f"──────────\n"
        f"<b>Name</b>      ➳ {escape(uname)}\n"
        f"<b>ID</b>        ➳ <code>{user.id}</code>\n"
        f"──────────\n"
        f"<b>Plan</b>      ➳ {get_styled_plan(raw_plan)} {plan_emoji}\n"
        f"<b>Credits</b>   ➳ {credits_d}\n"
        f"{expire_line}\n"
        f"──────────\n"
        f"<b>Joined</b>    ➳ {ud.get('joined', 'N/A')}\n"
        f"──────────"
    )
    kb = RawMarkup([
        [_btn("💎 " + B("Upgrade Plan"), cb="mprice", style="primary")],
    ]) if not premium else None
    await update.message.reply_text(txt, parse_mode="HTML", reply_markup=kb)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ud   = get_user_data(user.id, context)
    ud.setdefault("joined", datetime.now().strftime("%Y-%m-%d %H:%M"))
    ud.setdefault("total_refs", 0)
    _update_user_meta(ud, user)

    if context.args:
        arg = context.args[0]
        if arg.startswith("ref_"):
            # Secure HMAC token verification — prevents fake referral links
            referrer_id = _verify_ref_token(arg[4:])
            if referrer_id:
                await process_referral(user.id, referrer_id, context)

    if ud.get("banned", False) and user.id != OWNER_ID:
        await update.message.reply_text(
            f"<b>{E_ERRORS} {B('Banned')}</b>\n──────────\n"
            "You have been banned from using this bot.\n──────────",
            parse_mode="HTML"
        )
        return

    not_joined = await check_force_sub(user.id, context)
    if not_joined:
        await update.message.reply_text(_force_join_text(not_joined), parse_mode="HTML", reply_markup=kb_force_sub(not_joined))
        return

    await update.message.reply_text(ui_start_screen(user, context), parse_mode="HTML", reply_markup=kb_main(user.id), disable_web_page_preview=True)

MSH_LIMIT           = 5000   # absolute hard cap
TRIAL_MASS_DAY_LIMIT = 500   # trial users: max cards per day

async def cmd_msh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mass Shopify Checker — /msh  (new UI: Gate/Progress/Charged/Live/Dead/Errors/Time)."""
    user = update.effective_user
    if not await require_not_banned(update, context): return
    if context.bot_data.get("maintenance") and user.id != OWNER_ID:
        await update.message.reply_text("⚠️ Bot is under maintenance. Try again later.", parse_mode="HTML")
        return
    if not context.bot_data.get("msh_on", True):
        await update.message.reply_text(f"<b>{E_ERRORS} Shopify Mass gate is currently OFF.</b>", parse_mode="HTML")
        return
    if not await require_membership(update, context): return

    ud        = get_user_data(user.id, context)
    premium   = is_user_premium(ud)
    is_trial  = not premium and user.id != OWNER_ID
    today_str = datetime.now().strftime("%Y-%m-%d")
    _update_user_meta(ud, user)
    plan      = ud.get("plan", "TRIAL")

    if is_trial:
        last_date = ud.get("msh_daily_date", "")
        if last_date == today_str:
            used_today = ud.get("msh_daily_cards", 0)
            await update.message.reply_text(
                f"<b>{E_ERRORS} {B('Daily Limit Reached')}</b>\n──────────\n"
                f"You already used <b>/msh</b> today.\n\n"
                f"<b>Used Today:</b>  {used_today} / {TRIAL_MASS_DAY_LIMIT} cards\n"
                f"<b>Resets:</b>      Tomorrow midnight\n"
                f"──────────\n"
                f"💡 Upgrade to <b>Premium</b> for unlimited daily mass checking.",
                parse_mode="HTML", reply_markup=kb_upgrade()
            )
            return
        if ud.get("credits", 0) <= 0:
            # Trial user out of credits — friendly upgrade prompt
            await update.message.reply_text(
                f"<b>{E_PRO} {B('Credits Used Up!')}</b>\n──────────\n"
                f"You've used all your free credits.\n\n"
                f"<b>💎 Upgrade to Premium</b> for:\n"
                f"• Unlimited mass checking\n"
                f"• No daily card caps\n"
                f"• No credit limits ever\n"
                f"──────────\n"
                f"Tap <b>Buy Now</b> below to get a plan.",
                parse_mode="HTML", reply_markup=kb_upgrade()
            )
            return

    # ── Collect cards ───────────────────────────────────────────────
    cards = []
    doc = update.message.document or (
        update.message.reply_to_message.document
        if update.message.reply_to_message else None
    )
    if doc:
        if doc.mime_type not in ("text/plain", "application/octet-stream"):
            await update.message.reply_text("<b>❌ Please send a .txt file with cards (one per line).</b>", parse_mode="HTML")
            return
        try:
            file    = await doc.get_file()
            content = (await file.download_as_bytearray()).decode("utf-8", errors="ignore")
            cards   = [l.strip() for l in content.splitlines() if l.strip() and "|" in l]
        except Exception as e:
            await update.message.reply_text(f"<b>❌ Error reading file: {escape(str(e))}</b>", parse_mode="HTML")
            return
    else:
        txt = ""
        if update.message.reply_to_message:
            txt = (update.message.reply_to_message.text or update.message.reply_to_message.caption or "").strip()
        elif context.args:
            txt = " ".join(context.args)
        cards = [l.strip() for l in txt.splitlines() if l.strip() and "|" in l]

    if not cards:
        await update.message.reply_text(
            "<b>────────────</b>\n"
            "<b>Gate</b>    ➳ Shopify 0-20$\n"
            "<b>Command</b> ➳ <code>/msh</code>\n"
            "<b>Limit</b>   ➳ Unlimited\n"
            "<b>Type</b>    ➳ Mass Checker\n"
            "<b>Stop</b>    ➳ Button\n"
            "<b>Cost</b>    ➳ ∞ (Premium)\n"
            "<b>Credits</b> ➳ ∞\n"
            "<b>Status</b>  ➳ ✅ Available\n"
            "<b>────────────</b>",
            parse_mode="HTML"
        )
        return

    # ── Enforce limits ──────────────────────────────────────────────
    if len(cards) > MSH_LIMIT:
        cards = cards[:MSH_LIMIT]

    if is_trial:
        orig           = len(cards)
        trial_credits  = ud.get("credits", 0)
        eff_limit      = min(TRIAL_MASS_DAY_LIMIT, trial_credits)
        if orig > eff_limit:
            cards = cards[:eff_limit]
            reason = (f"{TRIAL_MASS_DAY_LIMIT} cards/day limit"
                      if eff_limit == TRIAL_MASS_DAY_LIMIT
                      else f"{trial_credits} credits")
            await update.message.reply_text(
                f"<b>{E_ERRORS} {B('Trial Limit Applied')}</b>\n──────────\n"
                f"You sent <b>{orig}</b> cards. Limit: <b>{reason}</b>.\n"
                f"Only <b>{eff_limit}</b> cards will be checked.\n──────────",
                parse_mode="HTML"
            )

    # ── Validate & format ───────────────────────────────────────────
    valid_cards = []   # list of (formatted_str, cc_number)
    for raw in cards:
        parts = raw.split("|")
        if len(parts) != 4: continue
        cc, mm, yy, cvv = [p.strip() for p in parts]
        mm = mm.zfill(2)
        if len(yy) == 4: yy = yy[2:]
        valid_cards.append((f"{cc}|{mm}|{yy}|{cvv}", cc))
    if not valid_cards:
        await update.message.reply_text("<b>❌ No valid cards found (need cc|mm|yy|cvv format).</b>", parse_mode="HTML")
        return

    total = len(valid_cards)

    # ── Load sites & proxies ────────────────────────────────────────
    sites   = _load_sites()
    proxies = _load_proxies()

    # ── Create session & send progress message ──────────────────────
    import random as _random
    import string as _string
    sid = "".join(_random.choices(_string.ascii_uppercase + _string.digits, k=8))

    # Post the initial progress message first so we have a message ID
    from sh import _progress_text as _pt, _msh_buttons
    sess = create_msh_session(
        sid=sid,
        chat_id=update.message.chat_id,
        user_id=user.id,
        msg_id=0,                        # filled after reply
        user_msg_id=update.message.message_id,
        total=total,
        user_obj=user,
        plan=plan,
    )
    init_html = _pt(sess)   # _progress_text returns HTML string — parse_mode="HTML"
    msg = await update.message.reply_text(
        init_html, parse_mode="HTML",
        reply_markup=_msh_buttons(sid, running=True),
        disable_web_page_preview=True,
    )
    sess["msg_id"] = msg.message_id

    # ── Fire mass batch in the background ───────────────────────────
    asyncio.create_task(
        run_mass_batch(context.bot, sid, valid_cards, user, plan, sites, proxies,
                       bot_data=context.bot_data)
    )

    # ── Deduct trial credits ────────────────────────────────────────
    if is_trial:
        ud["credits"]       = max(0, ud.get("credits", 0) - total)
        ud["msh_daily_date"]  = today_str
        ud["msh_daily_cards"] = total

    ud["total_checks"] = ud.get("total_checks", 0) + total
    ud["last_gate"]    = "Shopify | 0-20$"
    ud["last_active"]  = datetime.now().strftime("%Y-%m-%d %H:%M")


async def cmd_1day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner-only shortcut: /1day [count] — generate 1-day CORE premium keys."""
    if update.effective_user.id != OWNER_ID: return
    count = 1
    if context.args:
        try:
            count = int(context.args[0])
            if count <= 0 or count > 50: raise ValueError
        except ValueError:
            await update.message.reply_text(
                f"<b>{E_ERRORS} Usage:</b> <code>/1day [count]</code>\n"
                f"<b>Example:</b> <code>/1day 5</code>\n"
                f"Max 50 keys per call.",
                parse_mode="HTML"
            )
            return

    plan_emoji = tg_emoji(get_plan_emoji_id("CORE"), "⭐")
    keys_store = context.bot_data.setdefault("keys", {})
    generated  = []
    for _ in range(count):
        key = gen_code(12)
        keys_store[key] = {"plan": "CORE", "days": 1, "used": False}
        generated.append(key)

    if count == 1:
        await update.message.reply_text(
            f"<b>{E_LIVE} {B('1-Day Key Generated')}</b>\n──────────\n"
            f"<b>Key</b>    ➳ <code>{generated[0]}</code>\n"
            f"<b>Plan</b>   ➳ {B('Core')} {plan_emoji}\n"
            f"<b>Days</b>   ➳ 1\n"
            f"──────────\n"
            f"Redeem: <code>/rm {generated[0]}</code>",
            parse_mode="HTML"
        )
    else:
        lines = [
            f"<b>{E_LIVE} {B('1-Day Keys Generated')}</b>",
            "──────────",
            f"<b>Plan</b>  ➳ {B('Core')} {plan_emoji}",
            f"<b>Days</b>  ➳ 1",
            f"<b>Count</b> ➳ {count}",
            "──────────",
        ]
        for i, k in enumerate(generated, 1):
            lines.append(f"<b>{i}.</b> <code>{k}</code>")
        lines += ["──────────", "Redeem with: <code>/rm KEY</code>"]
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_not_banned(update, context): return
    if not await require_membership(update, context): return
    t   = time.time()
    msg = await update.message.reply_text(
        '<b>🔄 Pinging...</b>',
        parse_mode="HTML"
    )
    ms  = int((time.time() - t) * 1000)
    await msg.edit_text(
        f'<b>✅ {B("Pong")}</b>\n'
        f'──────────\n'
        f'<b>⏱ ➳ {ms}ms</b>\n'
        f'──────────',
        parse_mode="HTML"
    )

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Live leaderboard — top 5 users by lifetime CHARGED cards from this bot."""
    if not await require_not_banned(update, context): return
    if not await require_membership(update, context): return

    # ── Emoji IDs ────────────────────────────────────────────────────────────
    _EM = lambda eid, fb: f'<tg-emoji emoji-id="{eid}">{fb}</tg-emoji>'
    CROWN   = _EM("6181649972757271368", "⚜")
    DIAMOND = _EM("4958610528588008305", "💎")
    BLUE    = _EM("5416111497224920515", "🔵")   # rank 1
    WHITE1  = _EM("5415586905624420894", "⚪")   # rank 2
    WHITE2  = _EM("5415982270248918567", "⚪")   # rank 3
    TOP     = _EM("6170155021070506364", "🔝")   # all ranks
    DEV_E   = _EM("6267091732861555879", "⚡")   # dev line

    rank_markers = [BLUE, WHITE1, WHITE2, "4.", "5."]

    # ── Pull all users and sort by total_charged ──────────────────────────────
    user_data = context.bot_data.get("user_data", {})
    board = sorted(
        [
            {
                "display": (
                    f"@{ud['username']}" if ud.get("username")
                    else ud.get("first_name") or ud.get("name") or "User"
                ),
                "count": ud.get("total_charged", 0),
            }
            for ud in user_data.values()
            if ud.get("total_charged", 0) > 0
        ],
        key=lambda x: x["count"],
        reverse=True,
    )[:5]

    divider = "────────────"

    lines = [
        f"{CROWN} <b>Leaderboard</b> {DIAMOND}",
        divider,
    ]

    if not board:
        lines.append("No charge cards yet — be the first! 🎯")
    else:
        for i, entry in enumerate(board):
            marker = rank_markers[i]
            lines.append(
                f"{marker} {escape(entry['display'])} ➳ "
                f"<b>{entry['count']}</b> {DIAMOND} {TOP}"
            )

    # Pad to always show 5 slots (so layout is consistent even with few users)
    for i in range(len(board), 5):
        marker = rank_markers[i]
        lines.append(f"{marker} ———")

    lines += [
        divider,
        f"{DEV_E} Dev ➳@Batxchk_bot🦇",
    ]

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_not_banned(update, context): return
    if not await require_membership(update, context): return

    core_e  = tg_emoji(PLAN_EMOJIS["CORE"],  "⭐")
    elite_e = tg_emoji(PLAN_EMOJIS["ELITE"], "⭐")
    root_e  = tg_emoji(PLAN_EMOJIS["ROOT"],  "⭐")

    txt = (
        f"<b>{core_e} {B('Core')} Plan</b>\n──────────\n"
        "<b>Days</b>     ➳ 1\n"
        "<b>Credits</b>  ➳ Unlimited\n"
        "<b>Price</b>    ➳ 1.5$\n"
        "──────────\n"
        f"<b>{core_e} {B('Core')} Plan</b>\n──────────\n"
        "<b>Days</b>     ➳ 7\n"
        "<b>Credits</b>  ➳ Unlimited\n"
        "<b>Price</b>    ➳ 8$\n"
        "──────────\n"
        f"<b>{elite_e} {B('Elite')} Plan</b>\n──────────\n"
        "<b>Days</b>     ➳ 15\n"
        "<b>Credits</b>  ➳ Unlimited\n"
        "<b>Price</b>    ➳ 12$\n"
        "──────────\n"
        f"<b>{root_e} {B('Root')} Plan</b>\n──────────\n"
        "<b>Days</b>     ➳ 30\n"
        "<b>Credits</b>  ➳ Unlimited\n"
        "<b>Price</b>    ➳ 25$\n"
        "──────────"
    )
    await update.message.reply_text(txt, reply_markup=kb_price(), parse_mode="HTML")

async def cmd_refer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_not_banned(update, context): return
    if not await require_membership(update, context): return
    user       = update.effective_user
    ud         = get_user_data(user.id, context)
    link       = get_referral_link(user.id)
    total_refs = ud.get("total_refs", 0)
    txt = (
        f"<b>{E_USER} {B('Referral')}</b>\n──────────\n"
        f"<b>Link</b>      ➳ <code>{link}</code>\n──────────\n"
        f"<b>Referrals</b> ➳ {total_refs}\n"
        f"<b>Earned</b>    ➳ {total_refs * REFERRAL_CREDITS} credits\n"
        f"<b>Per Ref</b>   ➳ +{REFERRAL_CREDITS} credits\n──────────\n"
        "Share your link to earn free credits!"
    )
    await update.message.reply_text(
        txt, parse_mode="HTML",
        reply_markup=kb_back("bmain"),
        disable_web_page_preview=True,
    )

async def cmd_rm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_not_banned(update, context): return
    if not await require_membership(update, context): return
    if not context.args:
        await update.message.reply_text(
            f"<b>{E_CARD} {B('Redeem Code / Key')}</b>\n──────────\n"
            f"<b>Usage:</b> <code>/rm CODE</code>\n\n"
            f"Redeem a <b>credit code</b> to top up your balance,\n"
            f"or a <b>premium key</b> to activate a plan.\n"
            f"──────────",
            parse_mode="HTML"
        )
        return
    code  = context.args[0].upper().strip()
    uid   = update.effective_user.id
    ud    = get_user_data(uid, context)
    codes = context.bot_data.get("codes", {})
    keys  = context.bot_data.get("keys",  {})

    if code in codes:
        if codes[code]["used"]:
            await update.message.reply_text(
                f"<b>{E_ERRORS} Code Already Used</b>\n──────────\n"
                f"This code has already been redeemed.\n──────────",
                parse_mode="HTML"
            )
            return
        value              = codes[code]["value"]
        codes[code]["used"] = True
        ud["credits"]       = ud.get("credits", 0) + value
        ud["codes_redeemed"] = ud.get("codes_redeemed", 0) + 1
        await update.message.reply_text(
            f"<b>{E_LIVE} {B('Code Redeemed')}</b>\n──────────\n"
            f"<b>Code</b>           ➳ <code>{code}</code>\n"
            f"<b>Credits Added</b>  ➳ +{value}\n"
            f"<b>New Balance</b>    ➳ {ud['credits']}\n"
            "──────────",
            parse_mode="HTML"
        )
        return

    if code in keys:
        if keys[code]["used"]:
            await update.message.reply_text(
                f"<b>{E_ERRORS} Key Already Used</b>\n──────────\n"
                f"This key has already been redeemed.\n──────────",
                parse_mode="HTML"
            )
            return
        keys[code]["used"] = True
        p, d = keys[code]["plan"], keys[code]["days"]
        ud["keys_redeemed"] = ud.get("keys_redeemed", 0) + 1
        receipt    = await send_activation_msg(uid, p, d, context)
        plan_emoji = tg_emoji(get_plan_emoji_id(p), "⭐")
        await update.message.reply_text(
            f"<b>{E_LIVE} {B('Key Redeemed')}</b>\n──────────\n"
            f"<b>Key</b>     ➳ <code>{code}</code>\n"
            f"<b>Access</b>  ➳ {get_styled_plan(p)} {plan_emoji}\n"
            f"<b>Days</b>    ➳ {d}\n"
            f"<b>Receipt</b> ➳ <code>{receipt}</code>\n"
            "──────────\n"
            "Your plan is now active! Use /sub to check.",
            parse_mode="HTML"
        )
        return

    await update.message.reply_text(
        f"<b>{E_ERRORS} {B('Invalid Code')}</b>\n──────────\n"
        "This code or key is invalid.\n"
        "Make sure you typed it correctly (case-insensitive).\n"
        "──────────",
        parse_mode="HTML"
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FEEDBACK (/fb)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _fb_key(user_id: int) -> str:
    return f"{user_id}_{int(time.time())}_{random.randint(1000, 9999)}"

async def _process_fb_group(mgid: str, context: ContextTypes.DEFAULT_TYPE):
    """Called after a short delay to process a buffered media-group /fb submission."""
    await asyncio.sleep(1.5)   # wait for all album photos to arrive
    buf   = context.bot_data.get("fb_mg_buf", {})
    group = buf.pop(mgid, None)
    if not group:
        return

    file_ids  = group["file_ids"]
    user      = group["user"]
    user_note = group["user_note"]
    submitted = group["submitted"]
    uname     = f"@{user.username}" if user.username else user.first_name or "User"
    key       = _fb_key(user.id)

    context.bot_data.setdefault("fb_pending", {})[key] = {
        "file_ids": file_ids, "file_type": "photo",
        "user_id": user.id, "username": uname,
        "name": user.full_name or user.first_name or "User",
        "note": user_note, "date": submitted,
    }

    count         = len(file_ids)
    owner_caption = (
        f"<b>{E_DEV} {B('New Feedback')} ({count} photo{'s' if count > 1 else ''})</b>\n──────────\n"
        f"<b>User</b> ➳ {uname}\n<b>ID</b>   ➳ {user.id}\n"
        f"<b>Date</b> ➳ {submitted}\n"
    )
    if user_note:
        owner_caption += f"<b>Note</b> ➳ {user_note[:200]}\n"
    owner_caption += "──────────\nApprove ALL to post to channel?"

    try:
        if count == 1:
            await context.bot.send_photo(chat_id=OWNER_ID, photo=file_ids[0],
                                         caption=owner_caption,
                                         reply_markup=kb_fb_owner(key),
                                         parse_mode="HTML")
        else:
            # Send album (media groups can't carry inline keyboards in Telegram)
            media = [InputMediaPhoto(media=fid) for fid in file_ids]
            media[0] = InputMediaPhoto(media=file_ids[0],
                                       caption=owner_caption, parse_mode="HTML")
            await context.bot.send_media_group(chat_id=OWNER_ID, media=media)
            # Separate message carries the approve/decline buttons
            await context.bot.send_message(
                chat_id=OWNER_ID,
                text=f"☝️ <b>Approve all {count} photos above?</b>",
                reply_markup=kb_fb_owner(key),
                parse_mode="HTML",
            )
    except Exception as e:
        logger.error(f"Feedback notify owner failed: {e}")

async def cmd_fb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_not_banned(update, context): return
    if not await require_membership(update, context): return
    msg   = update.message
    user  = update.effective_user

    # ── resolve the media message ──────────────────────────────────────────────
    media_msg = None
    if msg.photo or msg.video:
        media_msg = msg
    elif msg.reply_to_message and (msg.reply_to_message.photo or msg.reply_to_message.video):
        media_msg = msg.reply_to_message

    if not media_msg:
        await msg.reply_text(
            f"<b>📸 {B('Feedback')}</b>\n──────────\n"
            "Send one or more photos with <code>/fb</code> as caption,\n"
            "or reply to a photo/video with <code>/fb</code>.\n"
            "──────────",
            parse_mode="HTML"
        )
        return

    # ── strip /fb prefix from caption / text ──────────────────────────────────
    user_note = (msg.text or msg.caption or "").strip()
    bot_uname = context.bot.username or ""
    for prefix in (f"/fb@{bot_uname}", "/fb"):
        if user_note.lower().startswith(prefix.lower()):
            user_note = user_note[len(prefix):].strip()
            break

    submitted = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ── media-group (album) — buffer and process after delay ──────────────────
    if media_msg.photo and media_msg.media_group_id:
        mgid = media_msg.media_group_id
        buf  = context.bot_data.setdefault("fb_mg_buf", {})
        if mgid not in buf:
            buf[mgid] = {
                "file_ids":  [],
                "user":      user,
                "user_note": user_note,
                "submitted": submitted,
                "task":      None,
            }
            # Acknowledge only on first photo of the album
            await msg.reply_text(
                f"<b>{E_LIVE} {B('Feedback Submitted')}</b>\n──────────\n"
                "All photos are under review.\n──────────",
                parse_mode="HTML"
            )
        buf[mgid]["file_ids"].append(media_msg.photo[-1].file_id)
        # Cancel old delayed task, schedule a fresh one
        old_task = buf[mgid].get("task")
        if old_task and not old_task.done():
            old_task.cancel()
        buf[mgid]["task"] = asyncio.create_task(_process_fb_group(mgid, context))
        return

    # ── single photo or video ──────────────────────────────────────────────────
    if media_msg.photo:
        file_id, file_type = media_msg.photo[-1].file_id, "photo"
    else:
        file_id, file_type = media_msg.video.file_id, "video"

    uname = f"@{user.username}" if user.username else user.first_name or "User"
    key   = _fb_key(user.id)

    context.bot_data.setdefault("fb_pending", {})[key] = {
        "file_ids": [file_id], "file_type": file_type, "user_id": user.id,
        "username": uname, "name": user.full_name or user.first_name or "User",
        "note": user_note, "date": submitted,
    }
    await msg.reply_text(
        f"<b>{E_LIVE} {B('Feedback Submitted')}</b>\n──────────\n"
        "Your feedback is under review.\n──────────",
        parse_mode="HTML"
    )

    owner_caption = (
        f"<b>{E_DEV} {B('New Feedback')}</b>\n──────────\n"
        f"<b>User</b> ➳ {uname}\n<b>ID</b>   ➳ {user.id}\n"
        f"<b>Date</b> ➳ {submitted}\n<b>Type</b> ➳ {file_type.capitalize()}\n"
    )
    if user_note:
        owner_caption += f"<b>Note</b> ➳ {user_note[:200]}\n"
    owner_caption += "──────────\nApprove to post to channel?"

    try:
        if file_type == "photo":
            await context.bot.send_photo(chat_id=OWNER_ID, photo=file_id,
                                         caption=owner_caption,
                                         reply_markup=kb_fb_owner(key),
                                         parse_mode="HTML")
        else:
            await context.bot.send_video(chat_id=OWNER_ID, video=file_id,
                                         caption=owner_caption,
                                         reply_markup=kb_fb_owner(key),
                                         parse_mode="HTML")
    except Exception as e:
        logger.error(f"Feedback notify owner failed: {e}")

async def _fb_approve(query, context: ContextTypes.DEFAULT_TYPE, key: str):
    fb = context.bot_data.get("fb_pending", {}).get(key)
    if not fb: await query.answer("Already handled.", show_alert=True); return
    uname, uid, submitted = fb["username"], fb["user_id"], fb["date"]
    file_type  = fb["file_type"]
    user_note  = fb.get("note", "")
    # support both old single-file_id and new file_ids list
    file_ids   = fb.get("file_ids") or ([fb["file_id"]] if fb.get("file_id") else [])

    channel_caption = "──────────\n"
    if user_note: channel_caption += f"{user_note}\n──────────\n"
    channel_caption += (
        f"<b>User</b> ➳ {uname}\n<b>ID</b>   ➳ {uid}\n"
        f"<b>Date</b> ➳ {submitted}\n──────────"
    )
    posted = False
    try:
        if file_type == "photo" and len(file_ids) > 1:
            # Post all photos as a media group to the channel
            media = [InputMediaPhoto(media=fid) for fid in file_ids]
            media[0] = InputMediaPhoto(media=file_ids[0],
                                       caption=channel_caption, parse_mode="HTML")
            await context.bot.send_media_group(chat_id=CHANNEL_USERNAME, media=media)
        elif file_type == "photo":
            await context.bot.send_photo(chat_id=CHANNEL_USERNAME, photo=file_ids[0],
                                         caption=channel_caption, parse_mode="HTML")
        else:
            await context.bot.send_video(chat_id=CHANNEL_USERNAME, video=file_ids[0],
                                         caption=channel_caption, parse_mode="HTML")
        posted = True
    except Exception as e:
        logger.error(f"Feedback channel post failed: {e}")
    context.bot_data["fb_pending"].pop(key, None)
    status_txt = f"{'Posted ✅' if posted else 'Post Failed ⚠️'}"
    try:
        await query.message.edit_caption(
            caption=f"<b>{E_LIVE} {B('Feedback')} {status_txt}</b>\n──────────",
            reply_markup=None, parse_mode="HTML"
        )
    except Exception:
        try:
            await query.message.edit_text(
                text=f"<b>{E_LIVE} {B('Feedback')} {status_txt}</b>\n──────────",
                reply_markup=None, parse_mode="HTML"
            )
        except Exception: pass
    try:
        await context.bot.send_message(
            chat_id=uid,
            text=(
                f"<b>{E_LIVE} {B('Feedback Accepted')}</b>\n──────────\n"
                f"Posted to channel!\n📢 {CHANNEL_LINK}\n──────────"
            ),
            parse_mode="HTML"
        )
    except Exception: pass

async def _fb_decline(query, context: ContextTypes.DEFAULT_TYPE, key: str):
    fb = context.bot_data.get("fb_pending", {}).get(key)
    if not fb: await query.answer("Already handled.", show_alert=True); return
    uid = fb["user_id"]
    context.bot_data["fb_pending"].pop(key, None)
    try:
        await query.message.edit_caption(
            caption=f"<b>{E_DECLINED} {B('Feedback Declined')}</b>\n──────────",
            reply_markup=None, parse_mode="HTML"
        )
    except Exception: pass
    try:
        await context.bot.send_message(
            chat_id=uid,
            text=f"<b>{E_DECLINED} {B('Feedback Declined')}</b>\n──────────",
            parse_mode="HTML"
        )
    except Exception: pass

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /sh GATE WRAPPER  — force-join + ban guard for Shopify
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _cmd_sh_gated(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Wrapper around sh.py's cmd_sh that enforces the force-join check.
    cmd_sh itself has no force-sub logic, so we gate it here to keep
    sh.py clean and avoid a circular import.
    """
    if not await require_not_banned(update, context): return
    if not await require_membership(update, context): return
    await cmd_sh(update, context)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CALLBACK QUERY HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user  = query.from_user
    data  = query.data

    # ── Answer policy ────────────────────────────────────────────────────────
    # Telegram allows EXACTLY ONE answer() per callback query.
    # Branches that need show_alert or a custom message handle their own answer().
    # All pure-navigation branches (edit_text / edit_caption only) are answered
    # silently right here so the loading indicator clears on the client.
    # Any branch that calls query.answer() itself MUST be listed below.
    _self_answering = (
        data == "check_sub"           or   # may show "still need to join" alert
        data.startswith("mshr:")      or   # new msh Live/All button — handles own answer
        data.startswith("mshs:")      or   # new msh Stop button — handles own answer
        data.startswith("stop_msh_")  or   # legacy stop (kept for old sessions)
        data.startswith("dl_approved_") or # legacy download
        data.startswith("dl_all_")    or   # legacy download
        data.startswith("ogs_")       or   # shows "granted!" alert
        data.startswith("owner_ban_") or
        data.startswith("owner_unban_") or
        data.startswith("owner_resub_") or
        data.startswith("find_sub_")  or
        data.startswith("fb_ok_")     or   # _fb_approve handles its own answer
        data.startswith("fb_no_")          # _fb_decline handles its own answer
    )
    if not _self_answering:
        try:
            await query.answer()
        except Exception:
            pass

    if data == "check_sub":
        not_joined = await check_force_sub(user.id, context)
        if not_joined:
            # Still missing channels — update the message with fresh status
            try:
                await query.message.edit_text(
                    _force_join_text(not_joined),
                    parse_mode="HTML",
                    reply_markup=kb_force_sub(not_joined),
                )
            except Exception:
                pass
            await query.answer(
                f"⚠️ Still need to join {len(not_joined)} channel(s)! Join then press Verify.",
                show_alert=True,
            )
            return
        # All joined — cache the pass, delete the gate message, show start screen
        _force_sub_cache[user.id] = (True, time.time(), [])
        await query.answer("✅ Verified! Welcome.", show_alert=False)
        try:
            await query.message.delete()
        except Exception:
            pass
        ud = get_user_data(user.id, context)
        _update_user_meta(ud, user)
        await context.bot.send_message(
            chat_id=user.id,
            text=ui_start_screen(user, context),
            parse_mode="HTML",
            reply_markup=kb_main(user.id),
            disable_web_page_preview=True,
        )
        return

    if data == "bmain":
        await query.message.edit_text(
            ui_start_screen(user, context), parse_mode="HTML",
            reply_markup=kb_main(user.id), disable_web_page_preview=True
        )
        return
    if data == "mreferral":
        ud_r       = get_user_data(user.id, context)
        link       = get_referral_link(user.id)
        total_refs = ud_r.get("total_refs", 0)
        await query.message.edit_text(
            f"<b>{E_USER} {B('Referral Program')}</b>\n──────────\n"
            f"<b>Link</b>      ➳ <code>{link}</code>\n──────────\n"
            f"<b>Referrals</b> ➳ {total_refs}\n"
            f"<b>Earned</b>    ➳ {total_refs * REFERRAL_CREDITS} credits\n"
            f"<b>Per Ref</b>   ➳ +{REFERRAL_CREDITS} credits\n──────────\n"
            "Share your link to earn free credits!",
            parse_mode="HTML",
            reply_markup=kb_back("bmain"),
            disable_web_page_preview=True,
        )
        return
    if data == "mprofile":
        await query.message.edit_text(
            ui_full_profile(user, context), parse_mode="HTML",
            reply_markup=kb_back("bmain"), disable_web_page_preview=True
        )
        return
    if data == "mgates":
        await query.message.edit_text(
            f"<b>{E_GATE} {B('Gates')}</b>\n──────────\nChoose a gate category:",
            parse_mode="HTML", reply_markup=kb_gate_main()
        )
        return
    if data == "mprice":
        core_e  = tg_emoji(PLAN_EMOJIS["CORE"],  "⭐")
        elite_e = tg_emoji(PLAN_EMOJIS["ELITE"], "⭐")
        root_e  = tg_emoji(PLAN_EMOJIS["ROOT"],  "⭐")
        txt = (
            f"<b>{core_e} {B('Core')}</b>  ➳ 1 day  | 1.5$\n"
            f"<b>{core_e} {B('Core')}</b>  ➳ 7 days | 8$\n"
            f"<b>{elite_e} {B('Elite')}</b> ➳ 15 days | 12$\n"
            f"<b>{root_e} {B('Root')}</b>   ➳ 30 days | 25$\n"
            "──────────\nAll plans: Unlimited credits"
        )
        await query.message.edit_text(txt, parse_mode="HTML", reply_markup=kb_price())
        return

    # ── Shopify Mass gate info (special layout) ──────────────────
    if data == "imsh":
        ud_i    = get_user_data(user.id, context)
        prem_i  = is_user_premium(ud_i)
        _today  = datetime.now().strftime("%Y-%m-%d")
        if prem_i:
            limit_line   = "Unlimited"
            status_line  = "✅ Available"
            credits_line = "∞"
        else:
            _used    = ud_i.get("msh_daily_cards", 0) if ud_i.get("msh_daily_date", "") == _today else 0
            _remain  = max(0, 500 - _used)
            _cr      = ud_i.get("credits", 0)
            limit_line   = f"500 cards / day"
            credits_line = str(_cr)
            if ud_i.get("msh_daily_date", "") == _today:
                status_line = f"🔒 Used today ({_used}/500)" if _used >= 500 else f"⚡ {_remain} cards left today"
            else:
                status_line = "✅ Available"
        await query.message.edit_text(
            f"<b>────────────</b>\n"
            f"<b>Gate</b>    ➳ Shopify 0-20$\n"
            f"<b>Command</b> ➳ <code>/msh</code>\n"
            f"<b>Limit</b>   ➳ {limit_line}\n"
            f"<b>Type</b>    ➳ Mass Checker\n"
            f"<b>Stop</b>    ➳ Button\n"
            f"<b>Cost</b>    ➳ {'∞ (Premium)' if prem_i else '1 credit / card'}\n"
            f"<b>Credits</b> ➳ {credits_line}\n"
            f"<b>Status</b>  ➳ {status_line}\n"
            f"<b>────────────</b>",
            parse_mode="HTML",
            reply_markup=kb_back("mgates")
        )
        return

    if data == "ish":
        ud_i   = get_user_data(user.id, context)
        prem_i = is_user_premium(ud_i)
        _cr    = ud_i.get("credits", 0)
        credits_line = "∞" if prem_i else str(_cr)
        status_line  = "✅ Available" if (prem_i or _cr > 0) else "🔒 No Credits"
        await query.message.edit_text(
            f"<b>────────────</b>\n"
            f"<b>Gate</b>    ➳ Shopify 0-20$\n"
            f"<b>Command</b> ➳ <code>/sh</code>\n"
            f"<b>Limit</b>   ➳ {'Unlimited' if prem_i else '1 card / check'}\n"
            f"<b>Type</b>    ➳ Single Checker\n"
            f"<b>Stop</b>    ➳ Automatic\n"
            f"<b>Cost</b>    ➳ {'∞ (Premium)' if prem_i else '1 Credit'}\n"
            f"<b>Credits</b> ➳ {credits_line}\n"
            f"<b>Status</b>  ➳ {status_line}\n"
            f"<b>────────────</b>",
            parse_mode="HTML",
            reply_markup=kb_back("mgates")
        )
        return

    # ── New msh Stop button (mshs:<sid>) ─────────────────────────
    if data.startswith("mshs:"):
        await cb_msh_stop(update, context)
        return

    # ── New msh Live/All button (mshr:<sid>:<kind>) ───────────────
    if data.startswith("mshr:"):
        await cb_msh_result(update, context)
        return

    # ── Legacy stop (old sessions before UI update) ───────────────
    if data.startswith("stop_msh_"):
        task_id = data[len("stop_msh_"):]
        tasks   = context.bot_data.get("msh_tasks", {})
        if task_id in tasks:
            tasks[task_id]["running"] = False
            await query.answer("⏹ Stopping...", show_alert=False)
        else:
            await query.answer("Task already finished.", show_alert=True)
        return

    # ── Legacy download: Approved ─────────────────────────────────
    if data.startswith("dl_approved_"):
        task_id = data[len("dl_approved_"):]
        results = context.bot_data.get("msh_results", {}).get(task_id)
        if not results or not results.get("approved"):
            await query.answer("No approved cards found or results expired.", show_alert=True)
            return
        await query.answer("Sending approved cards file…", show_alert=False)
        content  = "\n".join(results["approved"]).encode("utf-8")
        filename = f"approved_{task_id}.txt"
        try:
            await query.message.reply_document(
                document=BytesIO(content), filename=filename,
                caption=(f"<b>✅ Approved Cards</b>\nTotal: <b>{len(results['approved'])}</b> cards\nGate: Shopify 0-20$"),
                parse_mode="HTML"
            )
        except Exception:
            pass
        return

    # ── Legacy download: ALL ───────────────────────────────────────
    if data.startswith("dl_all_"):
        task_id = data[len("dl_all_"):]
        results = context.bot_data.get("msh_results", {}).get(task_id)
        if not results or not results.get("all"):
            await query.answer("Results expired or not found.", show_alert=True)
            return
        await query.answer("Sending all results file…", show_alert=False)
        content  = "\n".join(results["all"]).encode("utf-8")
        filename = f"all_results_{task_id}.txt"
        try:
            await query.message.reply_document(
                document=BytesIO(content), filename=filename,
                caption=(f"<b>📋 All Checked Cards</b>\nTotal: <b>{len(results['all'])}</b> cards\nGate: Shopify 0-20$"),
                parse_mode="HTML"
            )
        except Exception:
            pass
        return

    pay_map = {
        "pay1d": ("Core",  1.5, 1,  "CORE"),
        "pay10": ("Core",  8,   7,  "CORE"),
        "pay15": ("Elite", 12,  15, "ELITE"),
        "pay30": ("Root",  25,  30, "ROOT"),
    }
    if data in pay_map:
        plan_n, price, days, plan_key = pay_map[data]
        plan_emoji = tg_emoji(get_plan_emoji_id(plan_key), "⭐")
        await query.message.edit_text(
            f"<b>{plan_emoji} {B(plan_n)} Plan</b>\n──────────\n"
            f"<b>Price</b>   ➳ ${price}\n"
            f"<b>Days</b>    ➳ {days}\n"
            f"<b>Credits</b> ➳ Unlimited\n"
            "──────────\n"
            "Contact support to purchase:",
            parse_mode="HTML", reply_markup=kb_payment()
        )
        return

    if data.startswith("cmd_pg_"):
        if data == "cmd_pg_noop":
            return
        try:
            page = int(data.split("_")[-1])
        except ValueError:
            return
        page = max(1, min(CMD_TOTAL_PAGES, page))
        await query.message.edit_text(
            CMD_PAGES[page], parse_mode="HTML",
            reply_markup=kb_cmd_nav(page)
        )
        return

    if user.id == OWNER_ID:
        # ── /sub grant plan buttons: ogs_PLAN_DAYS_UID ──────────────
        if data.startswith("ogs_"):
            parts    = data.split("_")           # ["ogs","PLAN","DAYS","UID"]
            plan_key = parts[1]                  # CORE / ELITE / ROOT
            days     = int(parts[2])
            uid      = int(parts[3])
            ud_t     = get_user_data(uid, context)
            ud_t["plan"]    = plan_key
            ud_t["expires"] = time.time() + days * 86400
            plan_emoji = tg_emoji(get_plan_emoji_id(plan_key), "⭐")
            target_name = ud_t.get("name", f"User {uid}")
            exp_str = datetime.fromtimestamp(ud_t["expires"]).strftime("%Y-%m-%d %H:%M")
            # Persist grant immediately — JSON + Postgres
            await _save_premium(context.bot_data)
            try:
                await send_activation_msg(uid, plan_key, days, context)
            except Exception:
                pass
            await query.answer(f"✅ {plan_key} {days}d granted!", show_alert=True)
            try:
                await query.message.edit_text(
                    f"<b>{E_LIVE} {B('Plan Granted')}</b>\n──────────\n"
                    f"<b>User</b>    ➳ {target_name} (<code>{uid}</code>)\n"
                    f"<b>Plan</b>    ➳ {get_styled_plan(plan_key)} {plan_emoji}\n"
                    f"<b>Days</b>    ➳ {days}\n"
                    f"<b>Expires</b> ➳ {exp_str}\n"
                    f"──────────",
                    parse_mode="HTML"
                )
            except Exception:
                pass
            return
        # ── owner_ban / owner_unban / owner_resub ───────────────────
        if data.startswith("owner_ban_"):
            uid = int(data.split("_")[-1])
            get_user_data(uid, context)["banned"] = True
            await query.answer(f"Banned {uid}", show_alert=True)
            return
        if data.startswith("owner_unban_"):
            uid = int(data.split("_")[-1])
            get_user_data(uid, context)["banned"] = False
            await query.answer(f"Unbanned {uid}", show_alert=True)
            return
        if data.startswith("owner_resub_"):
            uid = int(data.split("_")[-1])
            ud  = get_user_data(uid, context)
            ud["plan"] = "TRIAL"; ud["expires"] = 0
            await _save_premium(context.bot_data)
            await query.answer(f"Premium removed for {uid}", show_alert=True)
            return
        if data.startswith("find_sub_"):
            uid = int(data.split("_")[-1])
            await query.answer(
                f"Use: /sub {uid}  to grant a plan.", show_alert=True
            )
            return
        if data == "owner_info_back":
            return
        if data.startswith("fb_ok_"):
            await _fb_approve(query, context, data[6:])
            return
        if data.startswith("fb_no_"):
            await _fb_decline(query, context, data[6:])
            return

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ERROR HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error
    if isinstance(err, Conflict):
        # Another session is still alive on Telegram's server.
        # Wait 30 s and let PTB retry — do NOT kill the process.
        logger.warning("CONFLICT detected — another session active. Waiting 30 s before retry...")
        await asyncio.sleep(30)
        return
    if isinstance(err, (NetworkError, Forbidden)):
        logger.warning(f"Network/Forbidden error: {err}")
        return
    logger.error(f"Unhandled exception: {err}", exc_info=err)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _post_shutdown(app: Application) -> None:
    """Final save → Postgres, stop prober, close DB pool."""
    # ── CRITICAL: save all premium users to Postgres before exit ──────────
    # Passing app.bot_data ensures no data is lost on Railway redeploy.
    await db.close_db(app.bot_data)
    try:
        await stop_probe_background()
        logger.info("[PROBE] Background prober stopped on shutdown.")
    except Exception as exc:
        logger.warning(f"[PROBE] shutdown cleanup error: {exc}")


async def _post_init(app: Application) -> None:
    """
    1. Auto-detect the real bot username from Telegram and patch config so
       referral links always point to the correct bot, regardless of what
       BOT_USERNAME is set to in config.py.
    2. Clear any existing webhook / long-poll session before polling starts.
       Sleep 5 s so Telegram can expire the old getUpdates session.
    3. Start background site prober so /sh and /msh only use alive sites.
    """
    # ── Load premium from JSON backup (always) ─────────────────────────────
    # Run in thread pool — json.load() on a large file would otherwise block
    # the event loop during startup.
    await asyncio.to_thread(_load_premium_file, app.bot_data)
    # ── Connect to Postgres & sync — all logic lives in database.py ────────
    await db.attach(app)

    # ── Startup DM to owner — confirms DB status so data loss is obvious ───
    try:
        now          = time.time()
        user_data    = app.bot_data.get("user_data", {})
        premium_cnt  = sum(
            1 for ud in user_data.values()
            if ud.get("plan", "TRIAL").upper() != "TRIAL"
            and ud.get("expires", 0) > now
        )
        db_status    = db.status_text()
        db_ok        = db.is_connected()
        lines = [
            f"<b>🤖 Bot Restarted</b>",
            f"━━━━━━━━━━━━━━━━━━━━",
            f"<b>Database ➛</b> {db_status}",
            f"<b>Premium users restored ➛</b> <code>{premium_cnt}</code>",
        ]
        if not db_ok:
            lines += [
                "",
                "<b>⚠️ Premium users will be LOST on next restart!</b>",
                "",
                "<b>Fix on Railway:</b>",
                "1. Your project → <b>+ New → Database → PostgreSQL</b>",
                "2. Click your bot service → Variables",
                "3. Add Reference → <code>DATABASE_URL</code>",
                "4. Redeploy the bot",
                "",
                f"Then send <code>/dbstatus</code> to confirm.",
            ]
        else:
            lines.append(f"\n<i>Send /dbstatus to force a save &amp; re-check.</i>")
        await app.bot.send_message(
            chat_id=OWNER_ID,
            text="\n".join(lines),
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.warning(f"[STARTUP] Could not DM owner: {exc}")

    # ── Auto-detect real bot username ──────────────────────────────────────
    try:
        import config as _cfg
        me = await app.bot.get_me()
        if me.username:
            _cfg.BOT_USERNAME = me.username
            _cfg.BOT_LINK     = f"https://t.me/{me.username}"
            logger.info(f"Bot identity confirmed: @{me.username} — referral link updated.")
    except Exception as exc:
        logger.warning(f"Could not fetch bot info: {exc}")

    # ── Clear stale webhook / long-poll session ────────────────────────────
    for attempt in range(1, 6):
        try:
            await app.bot.delete_webhook(drop_pending_updates=True)
            logger.info("Webhook cleared — waiting 5 s for old session to expire...")
            await asyncio.sleep(5)
            break
        except Exception as exc:
            logger.warning(f"delete_webhook attempt {attempt}/5 failed: {exc}")
            if attempt < 5:
                await asyncio.sleep(attempt * 2)
    else:
        logger.warning("Could not clear webhook after 5 attempts — continuing anyway.")

    # ── Start background site prober ──────────────────────────────────────
    # Runs in background: probes all sites, caches working ones, re-probes
    # every 30 min. /sh and /msh will only use confirmed-live sites.
    try:
        all_sites = _load_sites()
        proxies   = _load_proxies()
        start_probe_background(all_sites, proxies)
        logger.info(f"[PROBE] Background site prober started "
                    f"({len(all_sites)} sites, {len(proxies)} proxies)")
    except Exception as exc:
        logger.warning(f"[PROBE] Could not start background prober: {exc}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FAKE LOGS  (owner-only — invisible to all other users)
# /fakeon  → pick sender persona → starts stream to target channel
# /fakeoff → stops stream
# /getid   → owner runs this inside any chat to get its numeric ID
#
# Target channel: https://t.me/+BXmeotREVhllODFk
# Set FAKE_LOG_CHANNEL_ID env-var on Railway to the numeric ID,
# OR run /getid inside that channel to find out the ID.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from sh import MY_CHANNEL_LINK as _FL_CH_LINK

# ── Target channel — set via Railway env var ──────────────────────────────────
# Add FAKE_LOG_CHANNEL_ID to Railway → Variables with the numeric chat ID.
# Run /getid inside the channel to discover its ID.
_FL_CHANNEL_ID = int(os.environ.get("FAKE_LOG_CHANNEL_ID", "0"))

_FL_JOB     = "fake_hit_stream"
_FL_ACTIVE  = "fakelogs_active"
_FL_PERSONA = "fakelogs_persona_idx"

_FL_PERSONAS = [
    {"username": "Batxchk_bot", "link": "https://t.me/Batxchk_bot"},
    {"username": "lucifer2600", "link": "https://t.me/lucifer2600"},
    {"username": "krptonis",    "link": "https://t.me/krptonis"},
]

_FL_CHARGED_RESP = [
    "ORDER_PAID", "PAYMENT_AUTHORIZED", "APPROVED",
    "PAYMENT_ACCEPTED", "TRANSACTION_APPROVED",
    "CHARGED", "PURCHASE_COMPLETE", "AUTHORIZATION_APPROVED",
]
_FL_LIVE_RESP = [
    "INSUFFICIENT_FUNDS", "DO_NOT_HONOR", "RESTRICTED_CARD",
    "CALL_ISSUER", "CARD_VELOCITY_EXCEEDED", "PICKUP_CARD",
    "SECURITY_VIOLATION", "TRANSACTION_NOT_PERMITTED",
    "REFER_TO_CARD_ISSUER", "LIMITED_FUNDS",
]


def _fl_ch() -> str:
    return f'<a href="{_FL_CH_LINK}">[❆]</a>'


def _fl_charged_msg(persona: dict) -> str:
    resp  = random.choice(_FL_CHARGED_RESP)
    ulink = f'<a href="{persona["link"]}">@{persona["username"]}</a>'
    return (
        "<b>⭐</b>\n"
        f"<b>{_fl_ch()} HIT CHARGED 💎</b>\n"
        "<b>──────────</b>\n"
        f"<b>💎 Resp ➛ {resp}</b>\n"
        f"<b>👤 ➛ {ulink} ⭐</b>"
    )


def _fl_live_msg(persona: dict) -> str:
    resp  = random.choice(_FL_LIVE_RESP)
    ulink = f'<a href="{persona["link"]}">@{persona["username"]}</a>'
    return (
        "<b>⭐</b>\n"
        f"<b>{_fl_ch()} HIT LIVE ✅</b>\n"
        "<b>──────────</b>\n"
        f"<b>✅ Resp ➛ {resp}</b>\n"
        f"<b>👤 ➛ {ulink} ⭐</b>"
    )


async def _fl_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    bd = context.bot_data
    if not bd.get(_FL_ACTIVE):
        return
    persona    = _FL_PERSONAS[bd.get(_FL_PERSONA, 0)]
    target_cid = bd.get("fakelogs_channel_id", _FL_CHANNEL_ID)
    if not target_cid:
        logger.warning("[FAKELOGS] No channel ID set — stopping. "
                       "Set FAKE_LOG_CHANNEL_ID env var on Railway.")
        bd[_FL_ACTIVE] = False
        return
    if random.random() < 0.65:
        text       = _fl_charged_msg(persona)
        next_delay = random.uniform(8, 12)
    else:
        text       = _fl_live_msg(persona)
        next_delay = random.uniform(18, 30)
    try:
        await context.bot.send_message(
            target_cid, text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception as exc:
        logger.warning(f"[FAKELOGS] send failed (chat={target_cid}): {exc}")
    if bd.get(_FL_ACTIVE):
        context.job_queue.run_once(_fl_job, next_delay, name=_FL_JOB)


def _fl_stop(context: ContextTypes.DEFAULT_TYPE) -> None:
    for job in context.job_queue.get_jobs_by_name(_FL_JOB):
        job.schedule_removal()


async def _fakeon_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner only — /fakeon shows persona selector."""
    if update.effective_user.id != OWNER_ID:
        return
    target = context.bot_data.get("fakelogs_channel_id", _FL_CHANNEL_ID)
    if not target:
        await update.message.reply_text(
            "<b>⚠️ FAKE_LOG_CHANNEL_ID not set!</b>\n"
            "1. Add your bot as admin to the target channel\n"
            "2. Run <code>/getid</code> inside that channel\n"
            "3. Set <code>FAKE_LOG_CHANNEL_ID=&lt;id&gt;</code> on Railway",
            parse_mode="HTML"
        )
        return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"@{p['username']}", callback_data=f"fakelogs_{i}")]
        for i, p in enumerate(_FL_PERSONAS)
    ])
    await update.message.reply_text(
        "<b>🎭 Select fake sender ID:</b>",
        parse_mode="HTML", reply_markup=kb,
    )


async def _fakeon_select_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback: owner picked a persona — arm the stream."""
    q = update.callback_query
    if q.from_user.id != OWNER_ID:
        await q.answer("⛔ Owner only.", show_alert=True)
        return
    await q.answer()
    idx     = int(q.data.split("_")[-1])
    persona = _FL_PERSONAS[idx]
    _fl_stop(context)
    context.bot_data[_FL_ACTIVE]  = True
    context.bot_data[_FL_PERSONA] = idx
    # Store channel ID at start time so the job always uses the correct one
    context.bot_data["fakelogs_channel_id"] = (
        context.bot_data.get("fakelogs_channel_id") or _FL_CHANNEL_ID
    )
    context.job_queue.run_once(_fl_job, 2, name=_FL_JOB)
    await q.edit_message_text(
        f"<b>✅ Fake logs ON</b>\n"
        f"<b>Sender ➛ @{persona['username']}</b>\n"
        f"<b>Channel ID ➛ <code>{context.bot_data['fakelogs_channel_id']}</code></b>",
        parse_mode="HTML",
    )


async def _fakeoff_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner only — /fakeoff stops the stream."""
    if update.effective_user.id != OWNER_ID:
        return
    context.bot_data[_FL_ACTIVE] = False
    _fl_stop(context)
    await update.message.reply_text("<b>⛔ Fake logs OFF.</b>", parse_mode="HTML")


async def _dbstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner only — show live PostgreSQL connection status."""
    if update.effective_user.id != OWNER_ID:
        return
    now       = time.time()
    status    = db.status_text()
    connected = db.is_connected()
    user_data = context.bot_data.get("user_data", {})
    premium   = [(uid, ud) for uid, ud in user_data.items()
                 if ud.get("plan", "TRIAL").upper() != "TRIAL"
                 and ud.get("expires", 0) > now]
    lines = [
        f"<b>🗄 Database Status</b>",
        f"<b>──────────</b>",
        f"<b>DB ➛</b> {status}",
        f"<b>Premium users in memory ➛</b> <code>{len(premium)}</code>",
    ]
    if connected and premium:
        saved = await db.save_all_now(user_data)
        lines.append(f"<b>Just saved to Postgres ➛</b> <code>{saved}</code> user(s) ✅")
    if not connected:
        lines += [
            "",
            "<b>Fix:</b>",
            "1. Railway → your project → <b>+ New → Database → PostgreSQL</b>",
            "2. Click your bot service → Variables → Add Reference → DATABASE_URL",
            "3. Redeploy the bot",
        ]
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def _getid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner only — reply with the numeric chat ID of the current chat.
    Run this inside the target channel to discover its ID, then set
    FAKE_LOG_CHANNEL_ID=<id> on Railway and restart."""
    if update.effective_user.id != OWNER_ID:
        return
    chat = update.effective_chat
    cid  = chat.id
    # Store it automatically so /fakeon works right away without redeploy
    context.bot_data["fakelogs_channel_id"] = cid
    await update.message.reply_text(
        f"<b>📋 Chat ID: <code>{cid}</code></b>\n"
        f"<b>Title: {chat.title or 'DM'}</b>\n\n"
        f"Set <code>FAKE_LOG_CHANNEL_ID={cid}</code> on Railway to make this permanent.",
        parse_mode="HTML",
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    if not acquire_instance_lock():
        logger.critical("Another instance is already running. Exiting.")
        return

    try:
        # Regular API calls (send_message, edit_message, etc.)
        # Pool sized for 1000+ concurrent users — each outbound message needs
        # a connection slot; 512 ensures no queuing under peak load.
        _request = HTTPXRequest(
            connection_pool_size=512,
            connect_timeout=15.0,
            read_timeout=60.0,
            write_timeout=60.0,
            pool_timeout=120.0,
        )
        # Long-poll getUpdates — dedicated pool with generous read timeout.
        # Kept small because only ONE getUpdates call is in flight at a time.
        _get_updates_request = HTTPXRequest(
            connection_pool_size=8,
            connect_timeout=15.0,
            read_timeout=65.0,   # PTB polls for 30 s + 35 s buffer
            write_timeout=60.0,
            pool_timeout=120.0,
        )
        app = (
            Application.builder()
            .token(BOT_TOKEN)
            .request(_request)
            .get_updates_request(_get_updates_request)
            .concurrent_updates(1024)  # 1000+ users sending commands simultaneously
            .post_init(_post_init)
            .post_shutdown(_post_shutdown)
            .build()
        )

        app.add_handler(CommandHandler("start",   cmd_start))
        app.add_handler(CommandHandler("ping",    cmd_ping))
        app.add_handler(CommandHandler("status",  cmd_status))   # /status — live leaderboard
        app.add_handler(CommandHandler("plan",    cmd_plan))
        app.add_handler(CommandHandler("sub",     cmd_sub))
        app.add_handler(CommandHandler("refer",   cmd_refer))
        app.add_handler(CommandHandler("rm",      cmd_rm))
        app.add_handler(get_bin_lookup_handler())
        app.add_handler(CommandHandler("fb",      cmd_fb))
        app.add_handler(CommandHandler("sh",      _cmd_sh_gated))   # force-join gated
        app.add_handler(CommandHandler("msh",     cmd_msh))
        app.add_handler(get_me_handler())                           # /me — lifetime charged stats

        app.add_handler(CommandHandler("1day",        cmd_1day))
        app.add_handler(CommandHandler("gen",         cmd_gen))
        app.add_handler(CommandHandler("add",         cmd_add))
        app.add_handler(CommandHandler("rem",         cmd_rem))
        app.add_handler(CommandHandler("find",        cmd_find))
        app.add_handler(CommandHandler("resub",       cmd_resub))
        app.add_handler(CommandHandler("rsub",        cmd_resub))
        app.add_handler(CommandHandler("ban",         cmd_ban))
        app.add_handler(CommandHandler("unban",       cmd_unban))
        app.add_handler(CommandHandler("broadcast",   cmd_broadcast))
        app.add_handler(CommandHandler("bstatus",     cmd_bstatus))
        app.add_handler(CommandHandler("info",        cmd_info))
        app.add_handler(CommandHandler("allcm",       cmd_allcm))
        app.add_handler(CommandHandler("allsub",      cmd_allsub))
        app.add_handler(CommandHandler("maintenance", cmd_maintenance))
        app.add_handler(CommandHandler("updatesites", cmd_updatesites))
        app.add_handler(CommandHandler("onsh",    cmd_onsh))
        app.add_handler(CommandHandler("offsh",   cmd_offsh))
        app.add_handler(CommandHandler("onmsh",   cmd_onmsh))
        app.add_handler(CommandHandler("offmsh",  cmd_offmsh))

        # owner-only secret commands
        app.add_handler(CommandHandler("dbstatus", _dbstatus_cmd))
        # fake_logs — registered BEFORE the generic CallbackQueryHandler
        app.add_handler(CommandHandler("fakeon",  _fakeon_cmd))
        app.add_handler(CommandHandler("fakeoff", _fakeoff_cmd))
        app.add_handler(CommandHandler("getid",   _getid_cmd))
        app.add_handler(CallbackQueryHandler(_fakeon_select_cb, pattern=r"^fakelogs_\d+$"))

        app.add_handler(CallbackQueryHandler(callback_handler))
        app.add_error_handler(error_handler)

        logger.info(f"Batamanchk Bot {VERSION} starting...")
        app.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )
        return   # clean exit — no restart needed

    except KeyboardInterrupt:
        logger.info("Stopped by user (KeyboardInterrupt).")
        return
    except Exception as _crash_err:
        logger.error(f"Bot crashed: {_crash_err}", exc_info=True)
        raise   # re-raise so Railway sees the crash and auto-restarts
    finally:
        release_instance_lock()

if __name__ == "__main__":
    main()
