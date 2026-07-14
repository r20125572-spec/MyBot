import logging
import time
import string
import random
import asyncio
import signal
import os
import fcntl
from html import escape
from typing import Optional
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes,
)
from telegram.error import Conflict, BadRequest, NetworkError, Forbidden

import aiohttp as _aiohttp

from config import (
    BOT_TOKEN, OWNER_ID, VERSION, DEV_LINK,
    CHANNEL_USERNAME, CHANNEL_LINK, GROUP_LINK, SUPPORT_LINK,
    BOT_LINK, BOT_USERNAME, BOT_PHOTO_URL, BOT_PHOTO,
    API_TIMEOUT, REFERRAL_CREDITS, LOCK_FILE,
    GATE_URLS, GATE_SITES, PREMIUM_GATES, FORCE_CHANNELS,
    get_bin_info, kb_result,
)
from mass import get_mass_handlers
from b3 import get_b3_handler
from chk import get_chk_handler

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CUSTOM EMOJI CONFIGURATION (from mst.py)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# ── Core Emoji IDs ──
DECLINED_EMOJI_ID    = "4956612582816351459"
CARD_EMOJI_ID        = "5800709991627232190"
USER_EMOJI_ID        = "4958689671950369798"
TIME_EMOJI_ID        = "5382194935057372936"
DEV_EMOJI_ID         = "6267091732861555879"
PRO_EMOJI_ID         = "6298678524379137990"

# ── Status Emoji IDs ──
HIT_RESP_EMOJI_ID    = "5839116473951328489"
BANNED_EMOJI_ID      = "4956612582816351459"
ACTIVE_EMOJI_ID      = "5427168083074628963"

# ── UI Emoji IDs ──
CHECK_EMOJI_ID       = "5800709991627232190"
GATE_EMOJI_ID        = "5341715473882955310"
PROGRESS_EMOJI_ID    = "5258113901106580375"
LIVE_EMOJI_ID_UI     = "5427168083074628963"
DEAD_EMOJI_ID        = "4958526153955476488"
ERROR_EMOJI_ID       = "4956611513369494230"

# ── Button Emoji IDs ──
BTN_BACK_EMOJI_ID    = "6179444193518162239"
BTN_VERIFY_EMOJI_ID  = "5427168083074628963"
BTN_APPROVE_EMOJI_ID = "5427168083074628963"
BTN_DECLINE_EMOJI_ID = "4958526153955476488"
BTN_CLOSE_EMOJI_ID   = "4956612582816351459"

# ── Channel/Group Emoji IDs ──
CHANNEL_EMOJI_ID     = "5341715473882955310"
GROUP_EMOJI_ID       = "4958689671950369798"

# ── Plan Emoji IDs ──
PLAN_EMOJIS = {
    "CORE":   "5379869575338812919",
    "ELITE":  "5836898273666798437",
    "ROOT":   "4956420911310832630",
    "CUSTOM": "5445027583588593750",
}

# ── Live Hit Emoji Pool (random selection) ──
LIVE_EMOJI_IDS = [
    "5801154993188770160", "4956739572114392015", "5285221724634239278",
    "5287777298894835685", "5285024405246725814", "5287547831677112267",
    "5287658362660474522", "5285186510197381130", "5803233241963959320",
    "5462902520215002477", "5787435351521889877", "5323674506705785412",
    "5801005158959683238", "5436143465211640305", "5800688138833629633",
    "5891044423856296980", "5436068999068662274", "5427168083074628963",
]

# ── Special Font Map for Plan Normalization ──
SPECIAL_FONT_MAP = {
    'ᴀ': 'A', 'ʙ': 'B', 'ᴄ': 'C', 'ᴅ': 'D', 'ᴇ': 'E',
    'ꜰ': 'F', 'ɢ': 'G', 'ʜ': 'H', 'ɪ': 'I', 'ᴊ': 'J',
    'ᴋ': 'K', 'ʟ': 'L', 'ᴍ': 'M', 'ɴ': 'N', 'ᴏ': 'O',
    'ᴘ': 'P', 'ǫ': 'Q', 'ʀ': 'R', 'ꜱ': 'S', 'ᴛ': 'T',
    'ᴜ': 'U', 'ᴠ': 'V', 'ᴡ': 'W', 'x': 'X', 'ʏ': 'Y',
    'ᴢ': 'Z', 'Ɪ': 'I',
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EMOJI HELPER FUNCTIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def e(emoji_id: str, fallback: str = "✨") -> str:
    """Return a custom tg-emoji tag."""
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'

def get_random_live_emoji() -> str:
    """Return a random live emoji ID from the pool."""
    return random.choice(LIVE_EMOJI_IDS)

def get_plan_emoji_id(plan_name: str) -> str:
    """Return the emoji ID for a given plan name."""
    if not plan_name:
        return PRO_EMOJI_ID
    normalized = "".join(SPECIAL_FONT_MAP.get(c, c.upper()) for c in plan_name)
    if normalized in PLAN_EMOJIS:
        return PLAN_EMOJIS[normalized]
    for key, eid in PLAN_EMOJIS.items():
        if key in normalized:
            return eid
    return PRO_EMOJI_ID

def get_plan_emoji(plan_name: str) -> str:
    """Return full tg-emoji tag for a plan."""
    return e(get_plan_emoji_id(plan_name), "👑")

def build_user_link(user) -> str:
    """Build a clickable user link with custom emoji."""
    name = escape(user.full_name or user.first_name or "User")
    if user.username:
        return f'<a href="https://t.me/{user.username}">{name}</a>'
    return f'<a href="tg://user?id={user.id}">{name}</a>'

# ── Status Emoji Helpers ──
def e_banned() -> str:   return e(BANNED_EMOJI_ID, "🔴")
def e_active() -> str:   return e(ACTIVE_EMOJI_ID, "🟢")
def e_live() -> str:     return e(LIVE_EMOJI_ID_UI, "✅")
def e_dead() -> str:     return e(DEAD_EMOJI_ID, "❌")
def e_error() -> str:    return e(ERROR_EMOJI_ID, "⚠️")
def e_card() -> str:     return e(CARD_EMOJI_ID, "💳")
def e_user() -> str:     return e(USER_EMOJI_ID, "👤")
def e_time() -> str:     return e(TIME_EMOJI_ID, "⏱")
def e_dev() -> str:     return e(DEV_EMOJI_ID, "⚡")
def e_pro() -> str:     return e(PRO_EMOJI_ID, "⭐")
def e_gate() -> str:    return e(GATE_EMOJI_ID, "🛒")
def e_progress() -> str:  return e(PROGRESS_EMOJI_ID, "🔄")
def e_channel() -> str:  return e(CHANNEL_EMOJI_ID, "📢")
def e_group() -> str:    return e(GROUP_EMOJI_ID, "👥")
def e_back() -> str:    return e(BTN_BACK_EMOJI_ID, "🔙")
def e_verify() -> str:   return e(BTN_VERIFY_EMOJI_ID, "✅")
def e_approve() -> str:  return e(BTN_APPROVE_EMOJI_ID, "✅")
def e_decline() -> str:  return e(BTN_DECLINE_EMOJI_ID, "❌")
def e_close() -> str:   return e(BTN_CLOSE_EMOJI_ID, "✖")
def e_check() -> str:   return e(CHECK_EMOJI_ID, "💳")

def e_hit_resp() -> str:
    return e(HIT_RESP_EMOJI_ID, "✅")

def e_random_live() -> str:
    return e(get_random_live_emoji(), "✅")

# ── Decorative Symbols (no emoji, just Unicode) ──
SYM_ARROW   = "➔"
SYM_ARROW2  = "➺"
SYM_STAR    = "✰"
SYM_DASH    = "━"
SYM_BLOCK   = "⭅"
SYM_BLOCK2  = "⭆"

def divider() -> str:
    return SYM_DASH * 20

def header(title: str) -> str:
    return f"{SYM_BLOCK} <b>{title}</b> {SYM_BLOCK2}"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOGGING & CONFIG
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger  = logging.getLogger(__name__)
MAX_MSG = 4000

# Path to your bot photo — place photo.jpg next to bot.py
BOT_LOCAL_PHOTO = "photo.jpg"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FORCE-JOIN CHANNELS & GROUPS — ADD YOURS HERE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Format: ("username_without_@", "https://t.me/username", "Display Label")
#
# The bot MUST be admin in every channel/group listed here.
# Add as many as you need:
FORCE_JOIN_LIST = [
    ("Batcardchk",      "https://t.me/Batcardchk",      f"{e_channel()} Main Channel"),
    ("batcardchkGroup", "https://t.me/batcardchkGroup",  f"{e_group()} Main Group"),
    # ("YourChannel",   "https://t.me/YourChannel",      f"{e_channel()} Updates"),
    # ("YourGroup",     "https://t.me/YourGroup",        f"{e_group()} Support Group"),
]

# Merge with FORCE_CHANNELS from config.py (config entries appear first)
_config_fc = [(u, l) for u, l in FORCE_CHANNELS]
for _fc_entry in FORCE_JOIN_LIST:
    _uname = _fc_entry[0]
    if not any(_uname == u for u, _ in _config_fc):
        _config_fc.append((_uname, _fc_entry[1]))

# Full list used by the force-join system:
# [("username", "https://t.me/username", "Display Label"), ...]
FORCE_JOIN_FULL: list[tuple[str, str, str]] = []
_label_map = {e[0]: e[2] for e in FORCE_JOIN_LIST}
for _uname, _link in _config_fc:
    _label = _label_map.get(_uname, f"{e_channel()} @{_uname}")
    FORCE_JOIN_FULL.append((_uname, _link, _label))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# INSTANCE LOCK
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_lock_file_handle = None

def acquire_instance_lock() -> bool:
    global _lock_file_handle
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
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_styled_plan(raw_plan: str) -> str:
    p = raw_plan.upper()
    if p == "CORE":  return "Cᴏʀᴇ"
    if p == "ELITE": return "Eʟɪᴛᴇ"
    if p == "ROOT":  return "Rᴏᴏᴛ"
    return "Tʀɪᴀʟ"

def get_plan_icon(raw_plan: str) -> str:
    """Return custom plan emoji (tg-emoji) for premium plans."""
    if raw_plan.upper() in ("CORE", "ELITE", "ROOT"):
        return get_plan_emoji(raw_plan)
    return ""

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
        ud["plan"]               = "TRIAL"
        ud["credits"]            = ud.get("pre_premium_credits", 150)
        ud["expires"]            = 0
        ud["pre_premium_credits"] = 0
        return False
    return is_prem

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COOLDOWN — single-check commands (free/trial only)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SINGLE_CHECK_COOLDOWN = 20  # seconds between checks for trial users

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
    return f"Batman{random.randint(100000, 999999)}-CHK"

def get_referral_link(user_id: int) -> str:
    return f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# UI — USER CONTROL HUB (/start compact view)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def ui_profile(user, context: ContextTypes.DEFAULT_TYPE) -> str:
    ud        = get_user_data(user.id, context)
    raw_plan  = ud.get("plan", "TRIAL").upper()
    expires   = ud.get("expires", 0)
    now       = time.time()
    if raw_plan != "TRIAL" and expires <= now:
        raw_plan = "TRIAL"; ud["plan"] = "TRIAL"; ud["expires"] = 0; expires = 0
    premium      = raw_plan != "TRIAL"
    credits      = "Unlimited" if premium else str(ud.get("credits", 150))
    plan_icon    = get_plan_icon(raw_plan)
    uname        = escape(f"@{user.username}" if user.username else user.first_name or "User")
    joined       = ud.get("joined", datetime.now().strftime("%Y-%m-%d")).split(" ")[0]
    last_active  = ud.get("last_active", "N/A")
    total_refs   = ud.get("total_refs", 0)
    total_checks = ud.get("total_checks", 0)
    ban_status   = f"{e_banned()} Banned" if ud.get("banned", False) else f"{e_active()} Active"

    if premium and expires > now:
        exp_date    = datetime.fromtimestamp(expires).strftime("%Y-%m-%d")
        rem_d       = int((expires - now) / 86400)
        rem_h       = int(((expires - now) % 86400) / 3600)
        expire_line = f"{SYM_STAR} <b>Expires</b>   {SYM_ARROW} {exp_date} ({rem_d}d {rem_h}h)"
    else:
        expire_line = f"{SYM_STAR} <b>Expires</b>   {SYM_ARROW} Never (Trial)"

    lines = [
        header("USER CONTROL HUB"),
        divider(),
        f"{SYM_STAR} <b>Username</b>  {SYM_ARROW} {uname} {plan_icon}".rstrip(),
        f"{SYM_STAR} <b>User ID</b>   {SYM_ARROW} <code>{user.id}</code>",
        f"{SYM_STAR} <b>Access</b>    {SYM_ARROW} {get_styled_plan(raw_plan)}",
        f"{SYM_STAR} <b>Status</b>    {SYM_ARROW} {ban_status}",
        f"{SYM_STAR} <b>Credits</b>   {SYM_ARROW} {credits}",
        f"{SYM_STAR} <b>Joined</b>    {SYM_ARROW} {joined}",
        expire_line,
        divider(),
        f"{SYM_STAR} <b>Last Active</b> {SYM_ARROW} {last_active}",
        f"{SYM_STAR} <b>Total Checks</b> {SYM_ARROW} {total_checks}",
        f"{SYM_STAR} <b>Referrals</b>  {SYM_ARROW} {total_refs} (+{total_refs * REFERRAL_CREDITS} credits)",
        divider(),
        f"Version {SYM_ARROW} {VERSION}  |  <a href='{DEV_LINK}'>Batman</a>",
    ]
    return "\n".join(lines)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# UI — FULL PROFILE (PROFILE button expanded view)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def ui_full_profile(user, context: ContextTypes.DEFAULT_TYPE) -> str:
    ud           = get_user_data(user.id, context)
    raw_plan     = ud.get("plan", "TRIAL").upper()
    expires      = ud.get("expires", 0)
    now          = time.time()
    if raw_plan != "TRIAL" and expires <= now:
        raw_plan = "TRIAL"; ud["plan"] = "TRIAL"; ud["expires"] = 0; expires = 0
    premium      = raw_plan != "TRIAL"
    credits      = "Unlimited" if premium else str(ud.get("credits", 150))
    plan_icon    = get_plan_icon(raw_plan)
    uname        = escape(f"@{user.username}" if user.username else user.first_name or "User")
    joined       = ud.get("joined", "N/A")
    last_active  = ud.get("last_active", "N/A")
    total_refs   = ud.get("total_refs", 0)
    total_checks = ud.get("total_checks", 0)
    approved     = ud.get("approved_checks", 0)
    declined     = ud.get("declined_checks", 0)
    last_gate    = ud.get("last_gate", "N/A")
    last_card    = ud.get("last_card", "N/A")
    codes_red    = ud.get("codes_redeemed", 0)
    keys_red     = ud.get("keys_redeemed", 0)
    ban_status   = f"{e_banned()} Banned" if ud.get("banned", False) else f"{e_active()} Active"
    approval_rate = f"{(approved / total_checks * 100):.1f}%" if total_checks > 0 else "N/A"

    if premium and expires > now:
        exp_date    = datetime.fromtimestamp(expires).strftime("%Y-%m-%d %H:%M")
        rem_d       = int((expires - now) / 86400)
        rem_h       = int(((expires - now) % 86400) / 3600)
        expire_line = f"{SYM_STAR} <b>Expires</b>   {SYM_ARROW} {exp_date}\n{SYM_STAR} <b>Time Left</b>  {SYM_ARROW} {rem_d}d {rem_h}h"
        last_receipt = ud.get("last_receipt")
        if last_receipt:
            expire_line += f"\n{SYM_STAR} <b>Receipt</b>   {SYM_ARROW} <code>{last_receipt}</code>"
    else:
        expire_line = f"{SYM_STAR} <b>Expires</b>   {SYM_ARROW} Never (Trial)"

    lines = [
        header("USER PROFILE"),
        divider(),
        f"{SYM_STAR} <b>Username</b>  {SYM_ARROW} {uname} {plan_icon}".rstrip(),
        f"{SYM_STAR} <b>User ID</b>   {SYM_ARROW} <code>{user.id}</code>",
        f"{SYM_STAR} <b>Access</b>    {SYM_ARROW} {get_styled_plan(raw_plan)}",
        f"{SYM_STAR} <b>Status</b>    {SYM_ARROW} {ban_status}",
        f"{SYM_STAR} <b>Credits</b>   {SYM_ARROW} {credits}",
        f"{SYM_STAR} <b>Joined</b>    {SYM_ARROW} {joined}",
        expire_line,
        divider(),
        f"{SYM_STAR} <b>Last Active</b>  {SYM_ARROW} {last_active}",
        f"{SYM_STAR} <b>Total Checks</b> {SYM_ARROW} {total_checks}",
        f"{SYM_STAR} <b>Approved</b>   {SYM_ARROW} {approved}",
        f"{SYM_STAR} <b>Declined</b>    {SYM_ARROW} {declined}",
        f"{SYM_STAR} <b>Approval Rate</b> {SYM_ARROW} {approval_rate}",
        f"{SYM_STAR} <b>Last Gate</b>   {SYM_ARROW} {last_gate}",
        f"{SYM_STAR} <b>Last BIN</b>    {SYM_ARROW} <code>{last_card}</code>",
        divider(),
        f"{SYM_STAR} <b>Referrals</b>   {SYM_ARROW} {total_refs} (+{total_refs * REFERRAL_CREDITS} credits)",
        f"{SYM_STAR} <b>Codes</b>      {SYM_ARROW} {codes_red} redeemed",
        f"{SYM_STAR} <b>Keys</b>       {SYM_ARROW} {keys_red} redeemed",
        divider(),
        f"Version {SYM_ARROW} {VERSION}  |  <a href='{DEV_LINK}'>Batman</a>",
    ]
    return "\n".join(lines)

def gate_info_text(gate_name: str, cmd: str, cost: int) -> str:
    return (
        f"{divider()}\n<b>{gate_name}</b>\n{divider()}\n\n"
        f"<b>Cost</b>    {SYM_ARROW2} {cost} Credit(s) per check\n\n"
        f"<b>Usage:</b>\n<code>/{cmd} cc|mm|yy|cvv</code>\n\n"
        f"<b>Example:</b>\n<code>/{cmd} 4111111111111111|12|2026|123</code>\n\n"
        f"{divider()}"
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SEND PHOTO HELPER (local file → URL fallback → plain text)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def send_with_photo(msg, caption: str, reply_markup=None, parse_mode="HTML"):
    """Send the Batman card photo with caption. Falls back to text."""
    try:
        if os.path.exists(BOT_LOCAL_PHOTO):
            with open(BOT_LOCAL_PHOTO, "rb") as f:
                return await msg.reply_photo(
                    photo=f, caption=caption,
                    parse_mode=parse_mode, reply_markup=reply_markup,
                )
        if BOT_PHOTO_URL:
            return await msg.reply_photo(
                photo=BOT_PHOTO_URL, caption=caption,
                parse_mode=parse_mode, reply_markup=reply_markup,
            )
    except Exception:
        pass
    return await msg.reply_text(
        caption, parse_mode=parse_mode,
        reply_markup=reply_markup, disable_web_page_preview=True,
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FORCE SUBSCRIBE — checks every channel in FORCE_JOIN_FULL
# Cache: 5 minutes after a clean pass; busted on failure
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_force_sub_cache: dict[int, tuple[bool, float]] = {}

async def check_force_sub(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> list:
    """Return list of (username, link, label) the user has NOT joined."""
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
            # Bot is not admin in this chat — skip silently (can't check)
            pass
        except BadRequest as e:
            err = str(e).lower()
            if any(x in err for x in ("not found", "user_not_participant", "participant", "not a member")):
                # User has not joined this chat
                not_joined.append((uname, link, label))
            # else: chat not found or other config issue — skip silently
        except Exception:
            # Network glitch etc — skip silently, don't block the user
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
        header("JOIN REQUIRED"),
        divider(),
        "To use this bot you must join <b>all</b> our",
        "channels and groups listed below.",
        "",
        f"{e_progress()} <b>Progress:</b>  {joined}/{total} joined",
        divider(),
    ]
    for uname, _link, label in not_joined:
        lines.append(f"  {e_decline()}  {label}  <code>@{uname}</code>")
    lines += [
        divider(),
        f"{e_verify()} Click each button below to join,",
        f"   then press <b>{e_verify()} Verify</b>.",
    ]
    return "\n".join(lines)

def kb_force_sub(not_joined: list) -> InlineKeyboardMarkup:
    rows = []
    for uname, link, label in not_joined:
        rows.append([InlineKeyboardButton(f"{label}  {SYM_ARROW2}  @{uname}", url=link)])
    rows.append([InlineKeyboardButton(f"{e_verify()}  I Joined All — Verify Now", callback_data="check_sub")])
    return InlineKeyboardMarkup(rows)

async def send_force_join_photo(msg, not_joined: list):
    """Send Batman card photo with force-join caption on top."""
    caption  = _force_join_text(not_joined)
    keyboard = kb_force_sub(not_joined)
    try:
        if os.path.exists(BOT_LOCAL_PHOTO):
            with open(BOT_LOCAL_PHOTO, "rb") as f:
                await msg.reply_photo(
                    photo=f, caption=caption,
                    parse_mode="HTML", reply_markup=keyboard,
                )
            return
        if BOT_PHOTO_URL:
            await msg.reply_photo(
                photo=BOT_PHOTO_URL, caption=caption,
                parse_mode="HTML", reply_markup=keyboard,
            )
            return
    except Exception:
        pass
    await msg.reply_text(
        caption, reply_markup=keyboard,
        parse_mode="HTML", disable_web_page_preview=True,
    )

async def require_membership(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    not_joined = await check_force_sub(update.effective_user.id, context)
    if not_joined:
        await send_force_join_photo(update.message, not_joined)
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
                f"<b>[ 𖥷iТ ] {SYM_ARROW2} Banned {e_banned()}</b>\n{divider()}\n"
                "You have been banned from using this bot.\n"
                "Contact support if you think this is a mistake.\n" + divider(),
                parse_mode="HTML"
            )
        except Exception:
            pass
        return False
    return True

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CARD CHECK RESULT UI & DYNAMIC BUTTONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def build_check_result(card_raw: str, gate_name: str, raw_response: str,
                       bin_data: dict, username: str, plan: str,
                       time_taken: str, is_approved: bool,
                       is_timeout: bool = False, is_error: bool = False) -> str:
    if is_timeout:   status = "Timeout"
    elif is_error:   status = "Error"
    elif is_approved: status = "Approved"
    else:            status = "Declined"

    plan_icon  = get_plan_icon(plan)
    plan_label = get_styled_plan(plan)
    bin_txt    = "N/A"
    if bin_data and not bin_data.get("error"):
        scheme  = str(bin_data.get("scheme",  "N/A")).upper()
        bank    = bin_data.get("bank",    "N/A")
        country = str(bin_data.get("country", "N/A")).upper()
        flag    = bin_data.get("country_emoji", "")
        bin_txt = f"{scheme} - {bank} - {flag} {country}".strip()

    uname_display = f"{escape(username)} {plan_icon} ({plan_label})".strip()
    
    status_emoji = e_random_live() if is_approved else e_dead() if is_timeout or is_error else e_decline()
    
    lines = [
        f"<b>[ 𖥷iТ ] {SYM_ARROW2} {status}</b> {status_emoji}",
        f"{e_card()} {SYM_ARROW2} <code>{card_raw}</code>",
        f"<b>Gate</b> {SYM_ARROW2} {gate_name} {e_gate()}",
        f"<b>Raw</b>  {SYM_ARROW2} {escape(raw_response)}",
        f"<b>Info</b> {SYM_ARROW2} {bin_txt}",
        f"<b>User</b> {SYM_ARROW2} {uname_display}",
        f"<b>Pro</b>  {SYM_ARROW2} Batman | {time_taken}s",
        divider(),
        f"{e_channel()} @Batcardchk",
    ]
    return "\n".join(lines)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# KEYBOARDS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def kb_main(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("GATES"),          callback_data="mgates"),
         InlineKeyboardButton(B("PRICING"),        callback_data="mprice")],
        [InlineKeyboardButton(B("CONNECT") + f" {e_verify()}", url=CHANNEL_LINK),
         InlineKeyboardButton(f"{e_user()} " + B("PROFILE"), callback_data="mprofile")],
        [InlineKeyboardButton(f"{e_check()} " + B("CMD"),    callback_data="cmd_pg_1")],
        [InlineKeyboardButton(B("SUPPORT") + f" {e_verify()}", url=SUPPORT_LINK)],
    ])

def kb_back(cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(f"{e_back()} " + B("BACK"), callback_data=cb)]])

def kb_price() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("10$ - CORE"),  callback_data="pay10"),
         InlineKeyboardButton(B("15$ - ELITE"), callback_data="pay15"),
         InlineKeyboardButton(B("30$ - ROOT"),  callback_data="pay30")],
        [InlineKeyboardButton(B("SUPPORT") + f" {SYM_ARROW2}", url=SUPPORT_LINK)],
        [InlineKeyboardButton(f"{e_back()} " + B("BACK"), callback_data="bmain")],
    ])

def kb_payment() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("SUPPORT") + f" {SYM_ARROW2}", url=SUPPORT_LINK)],
        [InlineKeyboardButton(f"{e_back()} " + B("BACK"), callback_data="mprice")],
    ])

def kb_gate_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("AUTH"),    callback_data="mauth"),
         InlineKeyboardButton(B("CHARGE"),  callback_data="mcharge"),
         InlineKeyboardButton(f"{get_plan_emoji('ROOT')} " + B("PREMIUM"), callback_data="mmass")],
        [InlineKeyboardButton(f"{e_back()} " + B("BACK"), callback_data="bmain")],
    ])

def kb_auth_gates() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("BRAINTREE"), callback_data="ib3")],
        [InlineKeyboardButton(f"{e_back()} " + B("BACK"), callback_data="mgates")],
    ])

def kb_charge_gates() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("STRIPE"),       callback_data="ichk"),
         InlineKeyboardButton(B("PAYPAL"),       callback_data="ipp")],
        [InlineKeyboardButton(B("SHOPIFY"),      callback_data="ish"),
         InlineKeyboardButton(B("PAYU"),         callback_data="ipyu")],
        [InlineKeyboardButton(f"{e_back()} " + B("BACK"), callback_data="mgates")],
    ])

def kb_premium_gates() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("STRIPE AUTH")  + f" {get_plan_emoji('ELITE')}", callback_data="iau")],
        [InlineKeyboardButton(B("STRIPE MASS")  + f" {get_plan_emoji('ELITE')}", callback_data="imss")],
        [InlineKeyboardButton(B("PAYPAL MASS")  + f" {get_plan_emoji('ELITE')}", callback_data="impp2")],
        [InlineKeyboardButton(f"{e_back()} " + B("BACK"), callback_data="mgates")],
    ])

def kb_upgrade() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{get_plan_emoji('ELITE')} " + B("BUY PREMIUM"), callback_data="mprice")],
        [InlineKeyboardButton(B("SUPPORT") + f" {SYM_ARROW2}", url=SUPPORT_LINK)],
    ])

def kb_cooldown() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("Plans"), callback_data="mprice")],
    ])

def kb_fb_owner(key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(f"{e_approve()} Approve", callback_data=f"fb_ok_{key}"),
        InlineKeyboardButton(f"{e_decline()} Decline", callback_data=f"fb_no_{key}"),
    ]])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CMD PAGES  (user-facing commands only, no owner cmds)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CMD_TOTAL_PAGES = 6

CMD_PAGES = {
    1: (
        header("COMMANDS") + "\n"
        + divider() + "\n"
        "<b>Available Modules</b>\n"
        + divider() + "\n"
        f"<b>[+] {e_check()} Charge Module</b>  (4)\n"
        f"<b>[+] {e_gate()} Auth Module</b>    (1)\n"
        f"<b>[+] {get_plan_emoji('ROOT')} Mass Module</b>    (3)  <i>Premium</i>\n"
        f"<b>[+] {e_dev()} Tools</b>          (5)\n"
        f"<b>[+] {e_user()} Account</b>        (3)\n"
        + divider() + "\n"
        "<i>Use Next to explore each module</i>"
    ),
    2: (
        header(f"{e_check()} CHARGE MODULE") + "\n"
        + divider() + "\n"
        "<b>/chk</b>  " + f"{e_check()} Stripe Charge\n"
        "       Cost " + f"{e_check()} 1 Credit\n"
        "       Usage: <code>/chk cc|mm|yy|cvv</code>\n\n"
        "<b>/pp</b>   " + f"{e_check()} PayPal Charge\n"
        "       Cost " + f"{e_check()} 1 Credit\n"
        "       Usage: <code>/pp cc|mm|yy|cvv</code>\n\n"
        "<b>/sh</b>   " + f"{e_check()} Shopify Charge\n"
        "       Cost " + f"{e_check()} 1 Credit\n"
        "       Usage: <code>/sh cc|mm|yy|cvv</code>\n\n"
        "<b>/pyu</b>  " + f"{e_check()} PayU Charge\n"
        "       Cost " + f"{e_check()} 1 Credit\n"
        "       Usage: <code>/pyu cc|mm|yy|cvv</code>\n\n"
        + divider() + "\n"
        "<i>Example: /chk 4111111111111111|12|2026|123</i>"
    ),
    3: (
        header(f"{e_gate()} AUTH MODULE") + "\n"
        + divider() + "\n"
        "<b>/b3</b>   " + f"{e_gate()} Braintree Auth\n"
        "       Cost " + f"{e_check()} 1 Credit\n"
        "       Usage: <code>/b3 cc|mm|yy|cvv</code>\n\n"
        + divider() + "\n"
        "<b>What is Auth?</b>\n"
        "Auth gates verify a card is live\n"
        "without making a real charge.\n"
        + divider() + "\n"
        "<i>Example: /b3 4111111111111111|12|2026|123</i>"
    ),
    4: (
        header(f"{get_plan_emoji('ROOT')} MASS MODULE") + "\n"
        + divider() + "\n"
        f"{e_gate()} <b>Premium Plan Required</b>\n"
        + divider() + "\n"
        "<b>/au</b>   " + f"{e_check()} Stripe Auth Mass {get_plan_emoji('ELITE')}\n"
        "       Cost " + f"{e_check()} Unlimited (Premium)\n"
        "       Usage: <code>/au cc|mm|yy|cvv</code>\n\n"
        "<b>/mss</b>  " + f"{e_check()} Stripe Mass Checker {get_plan_emoji('ELITE')}\n"
        "       Cost " + f"{e_check()} Unlimited (Premium)\n"
        "       Usage: <code>/mss cc|mm|yy|cvv</code>\n\n"
        "<b>/mpp2</b> " + f"{e_check()} PayPal Mass Checker {get_plan_emoji('ELITE')}\n"
        "       Cost " + f"{e_check()} Unlimited (Premium)\n"
        "       Usage: <code>/mpp2 cc|mm|yy|cvv</code>\n"
        + divider() + "\n"
        "<i>Upgrade via /plan to unlock these gates</i>"
    ),
    5: (
        header(f"{e_dev()} TOOLS") + "\n"
        + divider() + "\n"
        "<b>/bin</b>   " + f"{e_check()} BIN Lookup\n"
        "        Usage: <code>/bin 411111</code>\n"
        "        <i>Get card info from first 6 digits</i>\n\n"
        "<b>/ping</b>  " + f"{e_time()} Bot Speed Test\n"
        "        Usage: <code>/ping</code>\n"
        "        <i>Check bot response time in ms</i>\n\n"
        "<b>/rm</b>    " + f"{e_verify()} Redeem Code / Key\n"
        "        Usage: <code>/rm CODE</code>\n"
        "        <i>Redeem credit codes or premium keys</i>\n\n"
        "<b>/fb</b>    " + f"{e_channel()} Submit Feedback\n"
        "        Usage: <code>/fb</code> (reply to photo/video)\n"
        "        <i>Send proof screenshots to owner</i>\n\n"
        "<b>/refer</b> " + f"{e_user()} Refer & Earn\n"
        "        Usage: <code>/refer</code>\n"
        "        <i>Get your referral link & earn credits</i>\n"
        + divider()
    ),
    6: (
        header(f"{e_user()} ACCOUNT") + "\n"
        + divider() + "\n"
        "<b>/start</b> " + f"{e_verify()} Open Dashboard\n"
        "         <i>View profile & all buttons</i>\n\n"
        "<b>/plan</b>  " + f"{e_check()} View Premium Plans\n"
        "         <i>See pricing & upgrade options</i>\n\n"
        "<b>/refer</b> " + f"{e_user()} Referral Program\n"
        "         <i>Earn credits for every invite</i>\n"
        + divider() + "\n"
        f"<b>{e_verify()} How Credits Work</b>\n"
        "• Trial users start with 150 credits\n"
        "• Each gate check costs 1 credit\n"
        "• Earn credits by referring friends\n"
        f"• Premium = Unlimited credits {get_plan_emoji('ELITE')}\n"
        + divider()
    ),
}

def kb_cmd_nav(page: int) -> InlineKeyboardMarkup:
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("◀ " + B("PREV"), callback_data=f"cmd_pg_{page - 1}"))
    nav_row.append(InlineKeyboardButton(f"{e_check()} {page}/{CMD_TOTAL_PAGES}", callback_data="cmd_pg_noop"))
    if page < CMD_TOTAL_PAGES:
        nav_row.append(InlineKeyboardButton(B("NEXT") + " ▶", callback_data=f"cmd_pg_{page + 1}"))
    return InlineKeyboardMarkup([
        nav_row,
        [InlineKeyboardButton(f"{e_close()} " + B("CLOSE"), callback_data="bmain")],
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
                f"<b>Referral Bonus</b>\n{divider()}\n"
                f"Someone joined via your link!\n"
                f"<b>Credits Added</b>    {SYM_ARROW2} +{REFERRAL_CREDITS}\n"
                f"<b>Total Referrals</b> {SYM_ARROW2} {referrer_ud['total_refs']}\n"
                + divider()
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass
    return True

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GATE PROCESSING (SINGLE CHECKS)
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
        await update.message.reply_text("Bot is under maintenance."); return
    if not context.bot_data.get(f"{gate_key}_on", True):
        await update.message.reply_text(f"Gate [{gate_name}] is currently OFF."); return

    if not await require_membership(update, context): return

    ud      = get_user_data(user.id, context)
    premium = is_user_premium(ud)
    _update_user_meta(ud, user)

    if gate_key in PREMIUM_GATES and not premium:
        await update.message.reply_text(
            f"<b>[ 𖥷iТ ] {SYM_ARROW2} Premium Only</b>\n{divider()}\nUse /plan to upgrade.",
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
            f"Usage: <code>/{gate_key} cc|mm|yy|cvv</code>", parse_mode="HTML"
        )
        return

    if not premium:
        # ── Credit check ──
        credits = ud.get("credits", 0)
        if credits <= 0:
            await update.message.reply_text(
                f"<b>[ 𖥷iТ ] {SYM_ARROW2} No Credits {e_dead()}</b>\n"
                + divider() + "\n"
                "You have <b>0 credits</b> remaining.\n\n"
                f"{get_plan_emoji('ELITE')} Upgrade to <b>Premium</b> for unlimited checks\n"
                "   with no cooldown and no credit limits.\n"
                + divider(),
                reply_markup=kb_upgrade(), parse_mode="HTML"
            )
            return

        # ── Cooldown check (trial/free only) ──
        remaining = get_cooldown_remaining(user.id, context)
        if remaining > 0:
            await update.message.reply_text(
                f"{e_error()} <b>Active cooldown!</b>\n\n"
                f"Please wait <b>{remaining:.1f} seconds</b> before continuing.\n\n"
                f"{get_plan_emoji('ELITE')} <b>Purchase premium plan to use commands without cooldown.</b>",
                reply_markup=kb_cooldown(), parse_mode="HTML"
            )
            return

        # Stamp cooldown BEFORE the API call so spam is blocked
        set_cooldown(user.id, context)
        ud["credits"] = credits - 1

    api_url  = context.bot_data.get(f"gate_url_{gate_key}") or GATE_URLS.get(gate_key, "")
    site_url = GATE_SITES.get(gate_key, "example.com")
    bin_num  = card_raw[:6]

    if not api_url:
        await update.message.reply_text("Gate API not set."); return

    msg        = await update.message.reply_text(f"[ 𖥷iТ ] {SYM_ARROW2} Scanning...")
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
                            reply_markup=kb_result(premium),
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
                            reply_markup=kb_result(premium),
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
                            reply_markup=kb_result(premium),
                            disable_web_page_preview=True)

async def cmd_pp(u, c):   await process_gate(u, c, "pp",   "PayPal Charge")
async def cmd_sh(u, c):   await process_gate(u, c, "sh",   "Shopify Charge")
async def cmd_pyu(u, c):  await process_gate(u, c, "pyu",  "PayU Charge")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GATE ON/OFF (OWNER ONLY)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _gate_toggle(update, context, gate: str, state: bool):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data[f"{gate}_on"] = state
    on_emoji = e_live()
    off_emoji = e_dead()
    await update.message.reply_text(f"Gate [{gate.upper()}] turned {'ON ' + on_emoji if state else 'OFF ' + off_emoji}.")


async def cmd_onchk(u, c):   await _gate_toggle(u, c, "chk",  True)
async def cmd_offchk(u, c):  await _gate_toggle(u, c, "chk",  False)
async def cmd_onpp(u, c):    await _gate_toggle(u, c, "pp",   True)
async def cmd_offpp(u, c):   await _gate_toggle(u, c, "pp",   False)
async def cmd_onsh(u, c):    await _gate_toggle(u, c, "sh",   True)
async def cmd_offsh(u, c):   await _gate_toggle(u, c, "sh",   False)
async def cmd_onpyu(u, c):   await _gate_toggle(u, c, "pyu",  True)
async def cmd_offpyu(u, c):  await _gate_toggle(u, c, "pyu",  False)
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

    exp_date     = datetime.fromtimestamp(expires_ts).strftime("%Y-%m-%d %H:%M")
    display_name = f"@{username}" if username else name
    styled       = get_styled_plan(plan)
    plan_emoji   = get_plan_emoji(plan)

    txt = (
        f"<b>[ 𖥷iТ ] {SYM_ARROW2} Access Activated</b>\n{divider()}\n"
        f"<b>User</b>     {SYM_ARROW2} {display_name}\n"
        f"<b>Access</b>  {SYM_ARROW2} {styled} {plan_emoji}\n"
        f"<b>Days</b>    {SYM_ARROW2} {days}\n"
        f"<b>Credits</b> {SYM_ARROW2} Unlimited\n"
        f"<b>Expires</b> {SYM_ARROW2} {exp_date}\n"
        f"<b>Receipt</b> {SYM_ARROW2} <code>{receipt}</code>\n"
        + divider() + "\n"
        "Save this receipt ID.\n"
        f"<b>Pro</b> {SYM_ARROW2} Batman {e_dev()}"
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
        if chat.last_name: display_name = f"{display_name} {chat.last_name}"
        display_uname = chat.username or ""
        ud["name"] = display_name
        if display_uname: ud["username"] = display_uname
    except Exception:
        pass

    receipt    = await send_activation_msg(uid, plan, days, context)
    uname_line = f"@{display_uname}" if display_uname else display_name
    exp_date   = datetime.fromtimestamp(ud["expires"]).strftime("%Y-%m-%d %H:%M")
    plan_emoji = get_plan_emoji(plan)

    await update.message.reply_text(
        f"{divider()}\n{e_live()} <b>Premium Granted</b>\n{divider()}\n"
        f"<b>User</b>     {SYM_ARROW2} {uname_line}\n"
        f"<b>ID</b>       {SYM_ARROW2} <code>{uid}</code>\n"
        f"<b>Plan</b>     {SYM_ARROW2} {get_styled_plan(plan)} {plan_emoji}\n"
        f"<b>Days</b>     {SYM_ARROW2} {days}\n"
        f"<b>Expires</b>  {SYM_ARROW2} {exp_date}\n"
        f"<b>Receipt</b>  {SYM_ARROW2} <code>{receipt}</code>\n"
        + divider(),
        parse_mode="HTML",
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# USER COMMANDS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ud   = get_user_data(user.id, context)
    ud.setdefault("joined",     datetime.now().strftime("%Y-%m-%d %H:%M"))
    ud.setdefault("name",       user.full_name or user.first_name or "User")
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

    # Ban check
    if ud.get("banned", False) and user.id != OWNER_ID:
        await update.message.reply_text(
            f"<b>[ 𖥷iТ ] {SYM_ARROW2} Banned {e_banned()}</b>\n{divider()}\n"
            "You have been banned from using this bot.\n" + divider(),
            parse_mode="HTML"
        )
        return

    # Force-join check — shows photo + join buttons
    not_joined = await check_force_sub(user.id, context)
    if not_joined:
        await send_force_join_photo(update.message, not_joined)
        return

    # Show dashboard with Batman card photo on top
    await send_with_photo(update.message, ui_profile(user, context), reply_markup=kb_main(user.id))

async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_not_banned(update, context): return
    if not await require_membership(update, context): return
    t   = time.time()
    msg = await update.message.reply_text(f"[ 𖥷iТ ] {SYM_ARROW2} Pinging...")
    await msg.edit_text(f"<b>[ 𖥷iТ ] {SYM_ARROW2} Pong</b> | {e_time()} {int((time.time() - t) * 1000)}ms", parse_mode="HTML")

async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_not_banned(update, context): return
    if not await require_membership(update, context): return
    txt = (
        f"<b>[ 𖥷iТ ] Batman Premium Plans</b>\n{divider()}\n\n"
        f"<b>Access</b>  {SYM_ARROW2} Core\n<b>Days</b>     {SYM_ARROW2} 7\n"
        f"<b>Credits</b> {SYM_ARROW2} Unlimited\n<b>Price</b>   {SYM_ARROW2} 10$\n{divider()}\n"
        f"<b>Access</b>  {SYM_ARROW2} Elite\n<b>Days</b>     {SYM_ARROW2} 15\n"
        f"<b>Credits</b> {SYM_ARROW2} Unlimited\n<b>Price</b>   {SYM_ARROW2} 15$\n{divider()}\n"
        f"<b>Access</b>  {SYM_ARROW2} Root\n<b>Days</b>     {SYM_ARROW2} 30\n"
        f"<b>Credits</b> {SYM_ARROW2} Unlimited\n<b>Price</b>   {SYM_ARROW2} 30$\n{divider()}"
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
        f"<b>[ 𖥷iТ ] Referral</b>\n{divider()}\n"
        f"<b>Link</b>    {SYM_ARROW2} <code>{link}</code>\n{divider()}\n"
        f"<b>Referrals</b> {SYM_ARROW2} {total_refs}\n"
        f"<b>Earned</b>   {SYM_ARROW2} {total_refs * REFERRAL_CREDITS} credits\n"
        f"<b>Per Ref</b>  {SYM_ARROW2} +{REFERRAL_CREDITS} credits\n{divider()}\n"
        "Share your link to earn free credits!"
    )
    await update.message.reply_text(txt, parse_mode="HTML",
                                    reply_markup=kb_back("bmain"),
                                    disable_web_page_preview=True)

async def cmd_rm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_not_banned(update, context): return
    if not await require_membership(update, context): return
    if not context.args:
        await update.message.reply_text("Usage: /rm <code>CODE</code>", parse_mode="HTML")
        return
    code  = context.args[0].upper()
    uid   = update.effective_user.id
    ud    = get_user_data(uid, context)
    codes = context.bot_data.get("codes", {})
    keys  = context.bot_data.get("keys",  {})
    if code in codes and not codes[code]["used"]:
        codes[code]["used"] = True
        ud["credits"]        = ud.get("credits", 0) + codes[code]["value"]
        ud["codes_redeemed"] = ud.get("codes_redeemed", 0) + 1
        await update.message.reply_text(
            f"Redeemed +{codes[code]['value']} credits\n"
            f"<b>Credits</b> {SYM_ARROW2} {ud['credits']}",
            parse_mode="HTML"
        )
    elif code in keys and not keys[code]["used"]:
        keys[code]["used"] = True
        p, d = keys[code]["plan"], keys[code]["days"]
        ud["keys_redeemed"] = ud.get("keys_redeemed", 0) + 1
        receipt = await send_activation_msg(uid, p, d, context)
        await update.message.reply_text(
            f"Activated {get_styled_plan(p)} for {d} days!\n"
            f"<b>Receipt</b> {SYM_ARROW2} <code>{receipt}</code>",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text("Invalid or already used code.")

async def cmd_bin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_not_banned(update, context): return
    if not await require_membership(update, context): return
    bin_num = context.args[0].strip()[:6] if context.args else None
    if not bin_num or not bin_num.isdigit() or len(bin_num) < 6:
        await update.message.reply_text("Usage: <code>/bin 411111</code>", parse_mode="HTML")
        return
    msg = await update.message.reply_text(f"[ 𖥷iТ ] {SYM_ARROW2} Looking up...")
    try:
        bd = await get_bin_info(bin_num)
        if bd.get("error"):
            await msg.edit_text("BIN not found."); return
        txt = (
            f"<b>[ 𖥷iТ ] {SYM_ARROW2} BIN Lookup</b>\n{divider()}\n"
            f"<b>BIN</b>     {SYM_ARROW2} <code>{bin_num}</code>\n"
            f"<b>Scheme</b>  {SYM_ARROW2} {str(bd.get('scheme', 'N/A')).upper()}\n"
            f"<b>Type</b>    {SYM_ARROW2} {str(bd.get('type', 'N/A')).upper()}\n"
            f"<b>Bank</b>    {SYM_ARROW2} {bd.get('bank', 'N/A')}\n"
            f"<b>Country</b> {SYM_ARROW2} {bd.get('country_emoji', '')} {str(bd.get('country', 'N/A')).upper()}\n"
            f"{divider()}"
        )
        await msg.edit_text(txt, parse_mode="HTML")
    except Exception as e:
        await msg.edit_text(f"Error: <code>{str(e)[:100]}</code>", parse_mode="HTML")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FEEDBACK SYSTEM (/fb)
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
        if media_msg.photo:     file_id, file_type = media_msg.photo[-1].file_id, "photo"
        elif media_msg.video:   file_id, file_type = media_msg.video.file_id, "video"
        else:
            await msg.reply_text("Invalid media type."); return

        user_note = (msg.text or msg.caption or "").strip()
        bot_uname = context.bot.username or ""
        for prefix in (f"/fb@{bot_uname}", "/fb"):
            if
