import logging
import time
import string
import random
import asyncio
import signal
import os
import fcntl
import json
from io import BytesIO
from html import escape
from typing import Optional
from datetime import datetime
from telegram import Update, TelegramObject
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes,
)
from telegram.error import Conflict, BadRequest, NetworkError, Forbidden, TimedOut, RetryAfter
from telegram.request import HTTPXRequest

import aiohttp as _aiohttp

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
from mass import get_mass_handlers
from b3 import get_b3_handler
from chk import get_chk_handler
from sh import (
    get_sh_handler, _check_card_with_retry, SITE_RETRIES, SITE_TIMEOUT,
    run_mass_batch, create_msh_session, MSH_SESSIONS,
    cb_msh_result, cb_msh_stop, _load_sites, _load_proxies,
    probe_all_sites, get_working_sites, start_probe_background,
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
            "banned": False,
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
    raw_plan = ud.get("plan", "TRIAL").upper()
    is_prem  = raw_plan != "TRIAL"
    if is_prem and ud.get("expires", 0) <= time.time():
        ud["plan"]                = "TRIAL"
        ud["credits"]             = ud.get("pre_premium_credits", 150)
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

def get_referral_link(user_id: int) -> str:
    return f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"

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
        f"<b><a href='{CHANNEL_LINK}'>[❆]</a> Welcome to CardXChk Bot 💎</b>\n"
        f"────────────\n"
        f"<b>User</b>    ➳ {uname}\n"
        f"<b>User ID</b> ➳ <code>{user.id}</code>\n"
        f"<b>Access</b>  ➳ {access}\n"
        f"<b>Credits</b> ➳ {credits}\n"
        f"<b>Joined</b>  ➳ {joined}\n"
        f"────────────\n"
        f"Choose an option below.\n"
        f"────────────\n"
        f"{E_DEV} <b>Dev</b>     ➳ <a href='{DEV_LINK}'>Batamanchk</a> {E_PRO}\n"
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

async def check_force_sub(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> list:
    if user_id == OWNER_ID:
        return []
    cached = _force_sub_cache.get(user_id)
    if cached and cached[0] and time.time() - cached[1] < 300:
        return []

    not_joined = []
    for uname, link, label in FORCE_JOIN_FULL:
        try:
            member = await context.bot.get_chat_member(f"@{uname}", user_id)
            if member.status in ("left", "kicked", "restricted"):
                not_joined.append((uname, link, label))
        except Forbidden:
            pass
        except BadRequest as e:
            err = str(e).lower()
            if any(x in err for x in ("not found", "user_not_participant", "participant", "not a member")):
                not_joined.append((uname, link, label))
        except Exception:
            pass

    if not not_joined:
        _force_sub_cache[user_id] = (True, time.time())
    else:
        _force_sub_cache.pop(user_id, None)
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

    if is_timeout:
        status_line = (
            f'<b><a href="{CHANNEL_LINK}">[❆]</a> Timeout '
            f'{tg_emoji(DECLINED_EMOJI_ID, "⏱")}</b>'
        )
    elif is_error:
        status_line = (
            f'<b><a href="{CHANNEL_LINK}">[❆]</a> Error '
            f'{tg_emoji(DECLINED_EMOJI_ID, "⚠️")}</b>'
        )
    elif is_approved:
        live_eid    = get_random_live_emoji()
        status_line = (
            f'<b><a href="{CHANNEL_LINK}">[❆]</a> Live '
            f'<tg-emoji emoji-id="{live_eid}">✅</tg-emoji></b>'
        )
    else:
        status_line = (
            f'<b><a href="{CHANNEL_LINK}">[❆]</a> Declined '
            f'<tg-emoji emoji-id="{DECLINED_EMOJI_ID}">❌</tg-emoji></b>'
        )

    plan_emoji_id = get_plan_emoji_id(plan)
    plan_emoji    = tg_emoji(plan_emoji_id, "⭐")
    plan_label    = get_styled_plan(plan)

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
        f'<b>Gate ➳ {gate_name}</b>\n'
        f'<b>──────────</b>\n'
        f'<b>Resp ➳ {escape(raw_response)}</b>\n'
        f'<b>Info ➳ {bin_txt}</b>\n'
        f'<b>──────────</b>\n'
        f'<b><tg-emoji emoji-id="{TIME_EMOJI_ID}">⏱</tg-emoji> ➳ {time_taken}s</b>\n'
        f'<b><tg-emoji emoji-id="{USER_EMOJI_ID}">👤</tg-emoji> ➳ {uname_display} '
        f'{plan_emoji} ({plan_label})</b>\n'
        f'<b><tg-emoji emoji-id="{DEV_EMOJI_ID}">⚡</tg-emoji> ➳ '
        f'<a href="{DEV_LINK}">Batamanchk</a> '
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
        [_btn("⭐ " + B("10$ — CORE"),  cb="pay10", style="primary"),
         _btn("⭐ " + B("15$ — ELITE"), cb="pay15", style="primary"),
         _btn("⭐ " + B("30$ — ROOT"),  cb="pay30", style="primary")],
        [_btn("🆘 " + B("SUPPORT"),     url=SUPPORT_LINK, style="primary")],
        [_btn("🔙 " + B("BACK"),        cb="bmain")],
    ])

def kb_payment() -> RawMarkup:
    return RawMarkup([
        [_btn("🆘 " + B("CONTACT SUPPORT"), url=SUPPORT_LINK, style="primary")],
        [_btn("🔙 " + B("BACK"), cb="mprice")],
    ])

def kb_gate_main() -> RawMarkup:
    return RawMarkup([
        [_btn("🔐 " + B("AUTH"),    cb="mauth",   style="primary"),
         _btn("💳 " + B("CHARGE"),  cb="mcharge", style="primary"),
         _btn("👑 " + B("PREMIUM"), cb="mmass",   style="primary")],
        [_btn("🔙 " + B("BACK"),    cb="bmain")],
    ])

def kb_auth_gates() -> RawMarkup:
    return RawMarkup([
        [_btn("🔐 " + B("BRAINTREE AUTH"), cb="ib3", style="primary")],
        [_btn("🔙 " + B("BACK"),           cb="mgates")],
    ])

def kb_charge_gates() -> RawMarkup:
    return RawMarkup([
        [_btn(B("Stripe"),  cb="ichk", style="primary"),
         _btn(B("PayPal"),  cb="ipp",  style="primary")],
        [_btn(B("Shopify"), cb="ish",  style="primary")],
        [_btn(B("Back"),    cb="mgates", style="danger")],
    ])

def kb_premium_gates() -> RawMarkup:
    return RawMarkup([
        [_btn(B("Shopify 0-20$"),          cb="imsh",  style="primary"),
         _btn(B("Stripe Auth") + " 👑",    cb="iau",   style="primary")],
        [_btn(B("Stripe Mass") + " 👑",    cb="imss",  style="primary"),
         _btn(B("PayPal Mass") + " 👑",    cb="impp2", style="primary")],
        [_btn(B("Back"),                    cb="mgates", style="danger")],
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
CMD_TOTAL_PAGES = 6
CMD_PAGES = {
    1: (
        "⭅ <b>𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦</b> ⭆\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>Available Modules</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>[+] 💳 Charge Module</b>  (3)\n"
        f"<b>[+] 🔐 Auth Module</b>    (1)\n"
        f"<b>[+] 👑 Mass Module</b>    (4)  <i>Premium</i>\n"
        f"<b>[+] 🛠 Tools</b>          (5)\n"
        f"<b>[+] 👤 Account</b>        (3)\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Use ▶ Next to explore each module</i>"
    ),
    2: (
        "⭅ <b>💳 𝗖𝗛𝗔𝗥𝗚𝗘 𝗠𝗢𝗗𝗨𝗟𝗘</b> ⭆\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>/chk</b>  ➳ Stripe Charge\n"
        "       Cost ➳ 1 Credit\n"
        "       Usage: <code>/chk cc|mm|yy|cvv</code>\n\n"
        "<b>/pp</b>   ➳ PayPal Charge\n"
        "       Cost ➳ 1 Credit\n"
        "       Usage: <code>/pp cc|mm|yy|cvv</code>\n\n"
        "<b>/sh</b>   ➳ Shopify Charge\n"
        "       Cost ➳ 1 Credit\n"
        "       Usage: <code>/sh cc|mm|yy|cvv</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Example: /chk 4111111111111111|12|2026|123</i>"
    ),
    3: (
        "⭅ <b>🔐 𝗔𝗨𝗧𝗛 𝗠𝗢𝗗𝗨𝗟𝗘</b> ⭆\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>/b3</b>   ➳ Braintree Auth\n"
        "       Cost ➳ 1 Credit\n"
        "       Usage: <code>/b3 cc|mm|yy|cvv</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>What is Auth?</b>\n"
        "Auth gates verify a card is live\n"
        "without making a real charge.\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Example: /b3 4111111111111111|12|2026|123</i>"
    ),
    4: (
        "⭅ <b>👑 𝗠𝗔𝗦𝗦 𝗠𝗢𝗗𝗨𝗟𝗘</b> ⭆\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔒 <b>Premium Plan Required</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>/msh</b>  ➳ Shopify Mass 0-20$\n"
        "       Limit ➳ 5000 cards (trial: 1 credit = 1 card)\n"
        "       Reply to a .txt file → <code>/msh</code>\n\n"
        "<b>/au</b>   ➳ Stripe Auth Mass 👑\n"
        "       Cost ➳ Unlimited (Premium)\n"
        "       Usage: <code>/au cc|mm|yy|cvv</code>\n\n"
        "<b>/mss</b>  ➳ Stripe Mass Checker 👑\n"
        "       Cost ➳ Unlimited (Premium)\n"
        "       Usage: <code>/mss cc|mm|yy|cvv</code>\n\n"
        "<b>/mpp2</b> ➳ PayPal Mass Checker 👑\n"
        "       Cost ➳ Unlimited (Premium)\n"
        "       Usage: <code>/mpp2 cc|mm|yy|cvv</code>\n"
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
            await update.message.reply_text(
                f"<b>{E_DECLINED} {B('No Credits')}</b>\n──────────\n"
                "You have <b>0 credits</b> remaining.\n\n"
                f"{E_PRO} Upgrade to <b>Premium</b> for unlimited checks.\n"
                "──────────",
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
        ud["credits"] = credits - 1

    api_url  = context.bot_data.get(f"gate_url_{gate_key}") or GATE_URLS.get(gate_key, "")
    site_url = GATE_SITES.get(gate_key, "example.com")
    bin_num  = card_raw[:6]

    if not api_url:
        await update.message.reply_text(
            f"<b>{E_ERRORS} Gate API not configured.</b>", parse_mode="HTML"
        )
        return

    msg        = await update.message.reply_text(
        f"<b><tg-emoji emoji-id=\"{PROG_PROGRESS_EMOJI_ID}\">🔄</tg-emoji> "
        f"Scanning...</b>", parse_mode="HTML"
    )
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

async def cmd_pp(u, c): await process_gate(u, c, "pp",  "PayPal Charge | 0$")
async def cmd_sh(u, c): await process_gate(u, c, "sh",  "Shopify Charge | 0$")

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

async def cmd_onchk(u, c):   await _gate_toggle(u, c, "chk",  True)
async def cmd_offchk(u, c):  await _gate_toggle(u, c, "chk",  False)
async def cmd_onpp(u, c):    await _gate_toggle(u, c, "pp",   True)
async def cmd_offpp(u, c):   await _gate_toggle(u, c, "pp",   False)
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
async def cmd_onb3(u, c):    await _gate_toggle(u, c, "b3",   True)
async def cmd_offb3(u, c):   await _gate_toggle(u, c, "b3",   False)
async def cmd_onau(u, c):    await _gate_toggle(u, c, "au",   True)
async def cmd_offau(u, c):   await _gate_toggle(u, c, "au",   False)
async def cmd_onmss(u, c):   await _gate_toggle(u, c, "mss",  True)
async def cmd_offmss(u, c):  await _gate_toggle(u, c, "mss",  False)
async def cmd_onmpp2(u, c):  await _gate_toggle(u, c, "mpp2", True)
async def cmd_offmpp2(u, c): await _gate_toggle(u, c, "mpp2", False)

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

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args:
        await update.message.reply_text(
            f"<b>Usage:</b> /broadcast &lt;message&gt;", parse_mode="HTML"
        )
        return
    msg_text  = " ".join(context.args)
    all_users = context.bot_data.get("user_data", {})
    sent = failed = 0
    for uid_str in all_users:
        try:
            await context.bot.send_message(
                chat_id=int(uid_str), text=msg_text, parse_mode="HTML",
                disable_web_page_preview=True
            )
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)
    await update.message.reply_text(
        f"<b>{E_LIVE} {B('Broadcast Done')}</b>\n──────────\n"
        f"<b>Sent</b>   ➳ {sent}\n<b>Failed</b> ➳ {failed}\n"
        "──────────",
        parse_mode="HTML"
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
        "/onchk /offchk ➳ Toggle Stripe gate\n"
        "/onpp /offpp ➳ Toggle PayPal gate\n"
        "/onsh /offsh ➳ Toggle Shopify gate\n"
        "/onmsh /offmsh ➳ Toggle Shopify Mass gate\n"
        "/onb3 /offb3 ➳ Toggle Braintree gate\n"
        "/onau /offau ➳ Toggle Stripe Auth\n"
        "/onmss /offmss ➳ Toggle Stripe Mass\n"
        "/onmpp2 /offmpp2 ➳ Toggle PayPal Mass\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        f"<b>{E_PRO} PREMIUM USER COMMANDS:</b>\n"
        "/chk ➳ Stripe Charge\n/b3 ➳ Braintree Charge\n"
        "/pp ➳ PayPal Charge\n/sh ➳ Shopify Charge\n"
        "/msh ➳ Shopify Mass 0-20$ (trial: 1cr=1card, limit 5000)\n"
        "/au ➳ Stripe Auth Mass\n"
        "/mss ➳ Stripe Mass Check\n/mpp2 ➳ PayPal Mass Check\n"
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
            try:
                referrer_id = int(arg[4:])
                await process_referral(user.id, referrer_id, context)
            except Exception:
                pass

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
            await update.message.reply_text(
                f"<b>{E_DECLINED} {B('No Credits')}</b>\n──────────\n"
                "You have <b>0 credits</b> remaining.\n\n"
                "💡 <b>1 credit = 1 card checked</b>\n"
                "Contact the owner to buy more credits,\n"
                "or upgrade to Premium for unlimited checks.\n──────────",
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
            f"<b>{E_GATE} {B('Mass Shopify Checker')}</b>\n──────────\n"
            f"<b>Gate</b>    ➳ Shopify 0-20$\n"
            f"<b>Command</b> ➳ <code>/msh</code>\n"
            f"<b>Limit</b>   ➳ 500/day (Trial) | 5000 (Premium)\n"
            f"<b>Buttons</b> ➳ Live · All · Stop\n"
            f"──────────\n"
            f"<b>How to use:</b>\n"
            f"• Reply to a .txt file (one <code>cc|mm|yy|cvv</code> per line)\n"
            f"• Or reply to a message containing cards",
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
    init_text = _pt(sess)
    msg = await update.message.reply_text(
        init_text,
        parse_mode="HTML",
        reply_markup=_msh_buttons(sid, running=True),
        disable_web_page_preview=True,
    )
    sess["msg_id"] = msg.message_id

    # ── Fire mass batch in the background ───────────────────────────
    asyncio.create_task(
        run_mass_batch(context.bot, sid, valid_cards, user, plan, sites, proxies)
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
        f'<b><tg-emoji emoji-id="{PROG_PROGRESS_EMOJI_ID}">🔄</tg-emoji> Pinging...</b>',
        parse_mode="HTML"
    )
    ms  = int((time.time() - t) * 1000)
    await msg.edit_text(
        f'<b><tg-emoji emoji-id="{PROG_LIVE_EMOJI_ID}">✅</tg-emoji> {B("Pong")}</b>\n'
        f'──────────\n'
        f'<b><tg-emoji emoji-id="{TIME_EMOJI_ID}">⏱</tg-emoji> ➳ {ms}ms</b>\n'
        f'──────────',
        parse_mode="HTML"
    )

async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_not_banned(update, context): return
    if not await require_membership(update, context): return

    core_e  = tg_emoji(PLAN_EMOJIS["CORE"],  "⭐")
    elite_e = tg_emoji(PLAN_EMOJIS["ELITE"], "⭐")
    root_e  = tg_emoji(PLAN_EMOJIS["ROOT"],  "⭐")

    txt = (
        f"<b>{core_e} {B('Core')} Plan</b>\n──────────\n"
        "<b>Days</b>     ➳ 7\n"
        "<b>Credits</b>  ➳ Unlimited\n"
        "<b>Price</b>    ➳ 10$\n"
        "──────────\n"
        f"<b>{elite_e} {B('Elite')} Plan</b>\n──────────\n"
        "<b>Days</b>     ➳ 15\n"
        "<b>Credits</b>  ➳ Unlimited\n"
        "<b>Price</b>    ➳ 15$\n"
        "──────────\n"
        f"<b>{root_e} {B('Root')} Plan</b>\n──────────\n"
        "<b>Days</b>     ➳ 30\n"
        "<b>Credits</b>  ➳ Unlimited\n"
        "<b>Price</b>    ➳ 30$\n"
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

async def cmd_fb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_not_banned(update, context): return
    if not await require_membership(update, context): return
    msg       = update.message
    user      = update.effective_user
    media_msg = None
    if msg.photo or msg.video:
        media_msg = msg
    elif msg.reply_to_message and (msg.reply_to_message.photo or msg.reply_to_message.video):
        media_msg = msg.reply_to_message

    if media_msg:
        if media_msg.photo:   file_id, file_type = media_msg.photo[-1].file_id, "photo"
        elif media_msg.video: file_id, file_type = media_msg.video.file_id, "video"
        else:
            await msg.reply_text("Invalid media type."); return

        user_note = (msg.text or msg.caption or "").strip()
        bot_uname = context.bot.username or ""
        for prefix in (f"/fb@{bot_uname}", "/fb"):
            if user_note.lower().startswith(prefix.lower()):
                user_note = user_note[len(prefix):].strip(); break

        key       = _fb_key(user.id)
        uname     = f"@{user.username}" if user.username else user.first_name or "User"
        submitted = datetime.now().strftime("%Y-%m-%d %H:%M")

        context.bot_data.setdefault("fb_pending", {})[key] = {
            "file_id": file_id, "file_type": file_type, "user_id": user.id,
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
        if user_note: owner_caption += f"<b>Note</b> ➳ {user_note[:200]}\n"
        owner_caption += "──────────\nApprove to post to channel?"

        try:
            if file_type == "photo":
                await context.bot.send_photo(chat_id=OWNER_ID, photo=file_id,
                                             caption=owner_caption, reply_markup=kb_fb_owner(key),
                                             parse_mode="HTML")
            else:
                await context.bot.send_video(chat_id=OWNER_ID, video=file_id,
                                             caption=owner_caption, reply_markup=kb_fb_owner(key),
                                             parse_mode="HTML")
        except Exception as e:
            logger.error(f"Feedback notify owner failed: {e}")
        return

    await msg.reply_text(
        f"<b>📸 {B('Feedback')}</b>\n──────────\n"
        "Reply to a photo/video with <code>/fb</code>\n"
        "OR send photo/video with <code>/fb</code> as caption.\n"
        "──────────",
        parse_mode="HTML"
    )

async def _fb_approve(query, context: ContextTypes.DEFAULT_TYPE, key: str):
    fb = context.bot_data.get("fb_pending", {}).get(key)
    if not fb: await query.answer("Already handled.", show_alert=True); return
    uname, uid, submitted = fb["username"], fb["user_id"], fb["date"]
    file_id, file_type, user_note = fb["file_id"], fb["file_type"], fb.get("note", "")
    channel_caption = "──────────\n"
    if user_note: channel_caption += f"{user_note}\n──────────\n"
    channel_caption += (
        f"<b>User</b> ➳ {uname}\n<b>ID</b>   ➳ {uid}\n"
        f"<b>Date</b> ➳ {submitted}\n──────────"
    )
    posted = False
    try:
        if file_type == "photo":
            await context.bot.send_photo(chat_id=CHANNEL_USERNAME, photo=file_id,
                                         caption=channel_caption, parse_mode="HTML")
        else:
            await context.bot.send_video(chat_id=CHANNEL_USERNAME, video=file_id,
                                         caption=channel_caption, parse_mode="HTML")
        posted = True
    except Exception as e:
        logger.error(f"Feedback channel post failed: {e}")
    context.bot_data["fb_pending"].pop(key, None)
    try:
        await query.message.edit_caption(
            caption=f"<b>{E_LIVE} {B('Feedback')} {'Posted ✅' if posted else 'Post Failed ⚠️'}</b>\n──────────",
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
            await query.answer(
                f"You still need to join {len(not_joined)} channel(s)!", show_alert=True
            )
            return
        _force_sub_cache[user.id] = (True, time.time())
        await query.answer()   # dismiss loading indicator before deleting the message
        await query.message.delete()
        await context.bot.send_message(
            chat_id=user.id,
            text=f"<b>{E_LIVE} Verified! Use /start.</b>",
            parse_mode="HTML"
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
    if data == "mauth":
        await query.message.edit_text(
            f"<b>🔐 {B('Auth Gates')}</b>\n──────────\n"
            "Auth gates verify without charging.\n──────────",
            parse_mode="HTML", reply_markup=kb_auth_gates()
        )
        return
    if data == "mcharge":
        await query.message.edit_text(
            f"<b>💳 {B('Charge Gates')}</b>\n──────────\n"
            "Charge gates perform a real $0 charge.\n──────────",
            parse_mode="HTML", reply_markup=kb_charge_gates()
        )
        return
    if data == "mmass":
        # All users can see the mass gate menu; premium is enforced per-command
        await query.message.edit_text(
            f"<b>👑 {B('Mass Gates')}</b>\n──────────\n"
            "Select a mass gate below.\n"
            "👑 gates require premium.\n──────────",
            parse_mode="HTML", reply_markup=kb_premium_gates()
        )
        return
    if data == "mprice":
        core_e  = tg_emoji(PLAN_EMOJIS["CORE"],  "⭐")
        elite_e = tg_emoji(PLAN_EMOJIS["ELITE"], "⭐")
        root_e  = tg_emoji(PLAN_EMOJIS["ROOT"],  "⭐")
        txt = (
            f"<b>{core_e} {B('Core')}</b>  ➳ 7 days | 10$\n"
            f"<b>{elite_e} {B('Elite')}</b> ➳ 15 days | 15$\n"
            f"<b>{root_e} {B('Root')}</b>   ➳ 30 days | 30$\n"
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
            reply_markup=kb_back("mmass")
        )
        return

    gate_info_map = {
        "ib3":   ("Braintree Auth | 0$", "b3",  1),
        "ichk":  ("Stripe Charge | 0$",  "chk", 1),
        "ipp":   ("PayPal Charge | 0$",  "pp",  1),
        "ish":   ("Shopify Charge | 0$", "sh",  1),
        "iau":   ("Stripe Auth | 0$",    "au",  0),
        "imss":  ("Stripe Mass",         "mss", 0),
        "impp2": ("PayPal Mass",         "mpp2",0),
    }
    if data in gate_info_map:
        gn, cmd, cost = gate_info_map[data]
        await query.message.edit_text(
            gate_info_text(gn, cmd, cost),
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
        "pay10": ("Core",  10, 7,  "CORE"),
        "pay15": ("Elite", 15, 15, "ELITE"),
        "pay30": ("Root",  30, 30, "ROOT"),
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
async def _post_init(app: Application) -> None:
    """
    1. Auto-detect the real bot username from Telegram and patch config so
       referral links always point to the correct bot, regardless of what
       BOT_USERNAME is set to in config.py.
    2. Clear any existing webhook / long-poll session before polling starts.
       Sleep 5 s so Telegram can expire the old getUpdates session.
    3. Start background site prober so /sh and /msh only use alive sites.
    """
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


def main():
    if not acquire_instance_lock():
        logger.critical("Another instance is already running. Exiting.")
        return

    try:
        # Regular API calls (send_message, edit_message, etc.)
        # Large pool so many users sending/receiving at the same time never queue
        _request = HTTPXRequest(
            connection_pool_size=64,
            connect_timeout=10.0,
            read_timeout=30.0,
            write_timeout=30.0,
            pool_timeout=60.0,
        )
        # Long-poll getUpdates — separate pool, generous read timeout
        _get_updates_request = HTTPXRequest(
            connection_pool_size=8,
            connect_timeout=10.0,
            read_timeout=65.0,   # PTB polls for 30 s + 35 s buffer
            write_timeout=30.0,
            pool_timeout=60.0,
        )
        app = (
            Application.builder()
            .token(BOT_TOKEN)
            .request(_request)
            .get_updates_request(_get_updates_request)
            .concurrent_updates(512)   # handle 512 updates simultaneously
            .post_init(_post_init)
            .build()
        )

        app.add_handler(CommandHandler("start",   cmd_start))
        app.add_handler(CommandHandler("ping",    cmd_ping))
        app.add_handler(CommandHandler("plan",    cmd_plan))
        app.add_handler(CommandHandler("sub",     cmd_sub))
        app.add_handler(CommandHandler("refer",   cmd_refer))
        app.add_handler(CommandHandler("rm",      cmd_rm))
        app.add_handler(get_bin_lookup_handler())
        app.add_handler(CommandHandler("fb",      cmd_fb))
        app.add_handler(CommandHandler("pp",      cmd_pp))
        app.add_handler(get_sh_handler())
        app.add_handler(get_b3_handler())
        app.add_handler(get_chk_handler())
        app.add_handler(CommandHandler("msh",     cmd_msh))
        for h in get_mass_handlers():
            app.add_handler(h)

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
        app.add_handler(CommandHandler("info",        cmd_info))
        app.add_handler(CommandHandler("allcm",       cmd_allcm))
        app.add_handler(CommandHandler("allsub",      cmd_allsub))
        app.add_handler(CommandHandler("maintenance", cmd_maintenance))
        app.add_handler(CommandHandler("onchk",   cmd_onchk))
        app.add_handler(CommandHandler("offchk",  cmd_offchk))
        app.add_handler(CommandHandler("onpp",    cmd_onpp))
        app.add_handler(CommandHandler("offpp",   cmd_offpp))
        app.add_handler(CommandHandler("updatesites", cmd_updatesites))
        app.add_handler(CommandHandler("onsh",    cmd_onsh))
        app.add_handler(CommandHandler("offsh",   cmd_offsh))
        app.add_handler(CommandHandler("onmsh",   cmd_onmsh))
        app.add_handler(CommandHandler("offmsh",  cmd_offmsh))
        app.add_handler(CommandHandler("onb3",    cmd_onb3))
        app.add_handler(CommandHandler("offb3",   cmd_offb3))
        app.add_handler(CommandHandler("onau",    cmd_onau))
        app.add_handler(CommandHandler("offau",   cmd_offau))
        app.add_handler(CommandHandler("onmss",   cmd_onmss))
        app.add_handler(CommandHandler("offmss",  cmd_offmss))
        app.add_handler(CommandHandler("onmpp2",  cmd_onmpp2))
        app.add_handler(CommandHandler("offmpp2", cmd_offmpp2))

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
