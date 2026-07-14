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
# LOGGING & CONFIG
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger  = logging.getLogger(__name__)
MAX_MSG = 4000

BOT_LOCAL_PHOTO = "photo.jpg"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CUSTOM EMOJI IDS — From mst.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Main emojis
DECLINED_EMOJI_ID = "4956612582816351459"
CARD_EMOJI_ID     = "5800709991627232190"
USER_EMOJI_ID     = "4958689671950369798"
TIME_EMOJI_ID     = "5382194935057372936"
DEV_EMOJI_ID      = "6267091732861555879"
PRO_EMOJI_ID      = "6298678524379137990"

# Hit-log emojis
HIT_RESP_EMOJI_ID = "5839116473951328489"

# Progress-message emojis
PROG_GATE_EMOJI_ID     = "5341715473882955310"
PROG_PROGRESS_EMOJI_ID = "5258113901106580375"
PROG_LIVE_EMOJI_ID     = "5427168083074628963"
PROG_DEAD_EMOJI_ID     = "4958526153955476488"
PROG_ERRORS_EMOJI_ID   = "4956611513369494230"

# Button emoji IDs
BTN_ALL_EMOJI_ID  = "4956324463525233747"
BTN_STOP_EMOJI_ID = "6179444193518162239"

# Pool of live emoji IDs
LIVE_EMOJI_IDS = [
    "5801154993188770160", "4956739572114392015", "5285221724634239278",
    "5287777298894835685", "5285024405246725814", "5287547831677112267",
    "5287658362660474522", "5285186510197381130", "5803233241963959320",
    "5462902520215002477", "5787435351521889877", "5323674506705785412",
    "5801005158959683238", "5436143465211640305", "5800688138833629633",
    "5891044423856296980", "5436068999068662274", "5427168083074628963",
]

# Plan emojis
PLAN_EMOJIS = {
    "CORE":   "5379869575338812919",
    "ELITE":  "5836898273666798437",
    "ROOT":   "4956420911310832630",
    "CUSTOM": "5445027583588593750",
    "TRIAL":  "6298678524379137990",
}

# Additional UI emojis
BANNED_EMOJI_ID    = "4958526153955476488"
ACTIVE_EMOJI_ID    = "5427168083074628963"
SCAN_EMOJI_ID      = "5258113901106580375"
GATE_EMOJI_ID      = "5341715473882955310"
INFO_EMOJI_ID      = "4956611513369494230"
CREDITS_EMOJI_ID   = "5800709991627232190"
JOIN_EMOJI_ID      = "4956324463525233747"
VERIFY_EMOJI_ID    = "5427168083074628963"
BACK_EMOJI_ID      = "6179444193518162239"
CLOSE_EMOJI_ID     = "4956612582816351459"
NEXT_EMOJI_ID      = "5258113901106580375"
PREV_EMOJI_ID      = "6179444193518162239"
ARROW_EMOJI_ID     = "4956324463525233747"
PREMIUM_EMOJI_ID   = "5379869575338812919"
DIAMOND_EMOJI_ID   = "5836898273666798437"
CHANNEL_EMOJI_ID   = "4956324463525233747"
GROUP_EMOJI_ID     = "4958689671950369798"
SUPPORT_EMOJI_ID   = "5382194935057372936"
PROFILE_EMOJI_ID   = "4958689671950369798"
PRICING_EMOJI_ID   = "5800709991627232190"
GATES_EMOJI_ID     = "5341715473882955310"
AUTH_EMOJI_ID      = "6267091732861555879"
CHARGE_EMOJI_ID    = "5800709991627232190"
MASS_EMOJI_ID      = "5258113901106580375"
TOOLS_EMOJI_ID     = "4956611513369494230"
ACCOUNT_EMOJI_ID   = "4958689671950369798"
CONNECT_EMOJI_ID   = "4956324463525233747"
CMD_EMOJI_ID       = "4956324463525233747"
REFERRAL_EMOJI_ID  = "4956324463525233747"
PING_EMOJI_ID      = "5382194935057372936"
BIN_EMOJI_ID       = "5341715473882955310"
FEEDBACK_EMOJI_ID  = "4956611513369494230"
REDEEM_EMOJI_ID    = "5379869575338812919"
LOCK_EMOJI_ID      = "4956612582816351459"
CHECK_EMOJI_ID     = "5427168083074628963"
CROSS_EMOJI_ID     = "4958526153955476488"
PAGE_EMOJI_ID      = "4956324463525233747"
COOLDOWN_EMOJI_ID  = "5382194935057372936"
MAINTENANCE_EMOJI_ID = "4956611513369494230"
PROOF_EMOJI_ID     = "5800709991627232190"
RAW_EMOJI_ID       = "4956611513369494230"
APPROVED_EMOJI_ID  = "5427168083074628963"
TIMEOUT_EMOJI_ID   = "5382194935057372936"
ERROR_EMOJI_ID     = "4956611513369494230"
PRO_EMOJI_ID_ALT   = "6267091732861555879"
DAYS_EMOJI_ID      = "5382194935057372936"
EXPIRES_EMOJI_ID   = "5382194935057372936"
RECEIPT_EMOJI_ID   = "4956324463525233747"
GRANTED_EMOJI_ID   = "5427168083074628963"
SUBMITTED_EMOJI_ID = "5427168083074628963"
UNDER_REVIEW_EMOJI_ID = "5258113901106580375"
BONUS_EMOJI_ID     = "5427168083074628963"
EARNED_EMOJI_ID    = "5800709991627232190"
SHARE_EMOJI_ID     = "4956324463525233747"
STRIPE_EMOJI_ID    = "5341715473882955310"
PAYPAL_EMOJI_ID    = "5800709991627232190"
SHOPIFY_EMOJI_ID   = "5341715473882955310"
PAYU_EMOJI_ID      = "5341715473882955310"
BRAINTREE_EMOJI_ID = "6267091732861555879"
SEARCH_EMOJI_ID    = "5258113901106580375"
LINK_EMOJI_ID      = "4956324463525233747"
TOTAL_EMOJI_ID     = "4956324463525233747"
PLAN_BTN_EMOJI_ID  = "5379869575338812919"
UNLIMITED_EMOJI_ID = "5427168083074628963"
ACTIVATED_EMOJI_ID = "5427168083074628963"
SAVE_EMOJI_ID      = "4956611513369494230"
HISTORY_EMOJI_ID   = "4956324463525233747"
RATE_EMOJI_ID      = "4956611513369494230"
LAST_GATE_EMOJI_ID = "5341715473882955310"
LAST_BIN_EMOJI_ID  = "5341715473882955310"
CODES_EMOJI_ID     = "4956324463525233747"
KEYS_EMOJI_ID      = "5379869575338812919"
PROGRESS_BAR_EMOJI_ID = "5258113901106580375"
JOINED_EMOJI_ID    = "5427168083074628963"
NOT_JOINED_EMOJI_ID = "4958526153955476488"
USAGE_EMOJI_ID     = "4956611513369494230"
EXAMPLE_EMOJI_ID   = "4956611513369494230"
MODULE_EMOJI_ID    = "5341715473882955310"
UPGRADE_EMOJI_ID   = "5836898273666798437"
NO_CREDITS_EMOJI_ID = "4958526153955476488"
HELP_EMOJI_ID      = "4956611513369494230"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CUSTOM EMOJI HELPER FUNCTIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def ce(emoji_id: str, fallback: str = "") -> str:
    """Create a custom emoji tag for use in messages."""
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'

def get_random_live_emoji() -> str:
    """Get a random live emoji ID."""
    return random.choice(LIVE_EMOJI_IDS)

def get_plan_emoji_id(plan_name: str) -> str:
    """Get the emoji ID for a plan."""
    if not plan_name:
        return PRO_EMOJI_ID
    normalized = plan_name.upper().strip()
    if normalized in PLAN_EMOJIS:
        return PLAN_EMOJIS[normalized]
    for key, eid in PLAN_EMOJIS.items():
        if key in normalized:
            return eid
    return PRO_EMOJI_ID

def get_plan_emoji_tag(plan_name: str) -> str:
    """Get a full custom emoji tag for a plan."""
    return ce(get_plan_emoji_id(plan_name), "✦")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FORCE-JOIN CHANNELS & GROUPS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FORCE_JOIN_LIST = [
    ("Batcardchk",      "https://t.me/Batcardchk",      "Main Channel"),
    ("batcardchkGroup", "https://t.me/batcardchkGroup",  "Main Group"),
]

_config_fc = [(u, l) for u, l in FORCE_CHANNELS]
for _fc_entry in FORCE_JOIN_LIST:
    _uname = _fc_entry[0]
    if not any(_uname == u for u, _ in _config_fc):
        _config_fc.append((_uname, _fc_entry[1]))

FORCE_JOIN_FULL: list[tuple[str, str, str]] = []
_label_map = {e[0]: e[2] for e in FORCE_JOIN_LIST}
for _uname, _link in _config_fc:
    _label = _label_map.get(_uname, f"@{_uname}")
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
# COOLDOWN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SINGLE_CHECK_COOLDOWN = 20

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
# UI — USER CONTROL HUB (/start compact view) — CUSTOM EMOJIS
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
    plan_emoji   = get_plan_emoji_tag(raw_plan)
    uname        = escape(f"@{user.username}" if user.username else user.first_name or "User")
    joined       = ud.get("joined", datetime.now().strftime("%Y-%m-%d")).split(" ")[0]
    last_active  = ud.get("last_active", "N/A")
    total_refs   = ud.get("total_refs", 0)
    total_checks = ud.get("total_checks", 0)
    ban_status   = ce(BANNED_EMOJI_ID, "X") + " Banned" if ud.get("banned", False) else ce(ACTIVE_EMOJI_ID, "✓") + " Active"

    if premium and expires > now:
        exp_date    = datetime.fromtimestamp(expires).strftime("%Y-%m-%d")
        rem_d       = int((expires - now) / 86400)
        rem_h       = int(((expires - now) % 86400) / 3600)
        expire_line = f"{ce(EXPIRES_EMOJI_ID, '◆')} <b>𝐄𝐱𝐩𝐢𝐫𝐞𝐬</b>   ➔ {exp_date} ({rem_d}d {rem_h}h)"
    else:
        expire_line = f"{ce(EXPIRES_EMOJI_ID, '◆')} <b>𝐄𝐱𝐩𝐢𝐫𝐞𝐬</b>   ➔ Never (Trial)"

    lines = [
        f"{ce(ARROW_EMOJI_ID, '⬅')} <b>𝗨𝗦𝗘𝗥 𝗖𝗢𝗡𝗧𝗥𝗢𝗟 𝗛𝗨𝗕</b> {ce(ARROW_EMOJI_ID, '➡')}",
        "━━━━━━━━━━━━━━━━━━━━",
        f"{ce(USER_EMOJI_ID, '◆')} <b>𝐔𝐬𝐞𝐫𝐧𝐚𝐦𝐞</b>  ➔ {uname} {plan_emoji}".rstrip(),
        f"{ce(INFO_EMOJI_ID, '◆')} <b>𝐔𝐬𝐞𝐫 𝐈𝐃</b>   ➔ <code>{user.id}</code>",
        f"{ce(PREMIUM_EMOJI_ID, '◆')} <b>𝐀𝐜𝐜𝐞𝐬𝐬</b>    ➔ {get_styled_plan(raw_plan)}",
        f"{ce(ACTIVE_EMOJI_ID, '◆')} <b>𝐒𝐭𝐚𝐭𝐮𝐬</b>    ➔ {ban_status}",
        f"{ce(CREDITS_EMOJI_ID, '◆')} <b>𝐂𝐫𝐞𝐝𝐢𝐭𝐬</b>   ➔ {credits}",
        f"{ce(JOINED_EMOJI_ID, '◆')} <b>𝐉𝐨𝐢𝐧𝐞𝐝</b>    ➔ {joined}",
        expire_line,
        "━━━━━━━━━━━━━━━━━━━━",
        f"{ce(TIME_EMOJI_ID, '◆')} <b>𝐋𝐚𝐬𝐭 𝐀𝐜𝐭𝐢𝐯𝐞</b> ➔ {last_active}",
        f"{ce(TOTAL_EMOJI_ID, '◆')} <b>𝐓𝐨𝐭𝐚𝐥 𝐂𝐡𝐞𝐜𝐤𝐬</b> ➔ {total_checks}",
        f"{ce(REFERRAL_EMOJI_ID, '◆')} <b>𝐑𝐞𝐟𝐞𝐫𝐫𝐚𝐥𝐬</b>  ➔ {total_refs} (+{total_refs * REFERRAL_CREDITS} credits)",
        "━━━━━━━━━━━━━━━━━━━━",
        f"𝗩𝗲𝗿𝘀𝗶𝗼𝗻 ➔ {VERSION}  |  <a href='{DEV_LINK}'>𝗕𝗮𝘁𝗺𝗮𝗻</a>",
    ]
    return "\n".join(lines)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# UI — FULL PROFILE — CUSTOM EMOJIS
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
    plan_emoji   = get_plan_emoji_tag(raw_plan)
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
    ban_status   = ce(BANNED_EMOJI_ID, "X") + " Banned" if ud.get("banned", False) else ce(ACTIVE_EMOJI_ID, "✓") + " Active"
    approval_rate = f"{(approved / total_checks * 100):.1f}%" if total_checks > 0 else "N/A"

    if premium and expires > now:
        exp_date    = datetime.fromtimestamp(expires).strftime("%Y-%m-%d")
        rem_d       = int((expires - now) / 86400)
        rem_h       = int(((expires - now) % 86400) / 3600)
        expire_line = f"{ce(EXPIRES_EMOJI_ID, '◆')} <b>𝐄𝐱𝐩𝐢𝐫𝐞𝐬</b>   ➔ {exp_date}\n{ce(TIME_EMOJI_ID, '◆')} <b>𝐓𝐢𝐦𝐞 𝐋𝐞𝐟𝐭</b>  ➔ {rem_d}d {rem_h}h"
        last_receipt = ud.get("last_receipt")
        if last_receipt:
            expire_line += f"\n{ce(RECEIPT_EMOJI_ID, '◆')} <b>𝐑𝐞𝐜𝐞𝐢𝐩𝐭</b>   ➔ <code>{last_receipt}</code>"
    else:
        expire_line = f"{ce(EXPIRES_EMOJI_ID, '◆')} <b>𝐄𝐱𝐩𝐢𝐫𝐞𝐬</b>   ➔ Never (Trial)"

    lines = [
        f"{ce(ARROW_EMOJI_ID, '⬅')} <b>𝗨𝗦𝗘𝗥 𝗣𝗥𝗢𝗙𝗜𝗟𝗘</b> {ce(ARROW_EMOJI_ID, '➡')}",
        "━━━━━━━━━━━━━━━━━━━━",
        f"{ce(USER_EMOJI_ID, '◆')} <b>𝐔𝐬𝐞𝐫𝐧𝐚𝐦𝐞</b>  ➔ {uname} {plan_emoji}".rstrip(),
        f"{ce(INFO_EMOJI_ID, '◆')} <b>𝐔𝐬𝐞𝐫 𝐈𝐃</b>   ➔ <code>{user.id}</code>",
        f"{ce(PREMIUM_EMOJI_ID, '◆')} <b>𝐀𝐜𝐜𝐞𝐬𝐬</b>    ➔ {get_styled_plan(raw_plan)}",
        f"{ce(ACTIVE_EMOJI_ID, '◆')} <b>𝐒𝐭𝐚𝐭𝐮𝐬</b>    ➔ {ban_status}",
        f"{ce(CREDITS_EMOJI_ID, '◆')} <b>𝐂𝐫𝐞𝐝𝐢𝐭𝐬</b>   ➔ {credits}",
        f"{ce(JOINED_EMOJI_ID, '◆')} <b>𝐉𝐨𝐢𝐧𝐞𝐝</b>    ➔ {joined}",
        expire_line,
        "━━━━━━━━━━━━━━━━━━━━",
        f"{ce(TIME_EMOJI_ID, '◆')} <b>𝐋𝐚𝐬𝐭 𝐀𝐜𝐭𝐢𝐯𝐞</b>  ➔ {last_active}",
        f"{ce(TOTAL_EMOJI_ID, '◆')} <b>𝐓𝐨𝐭𝐚𝐥 𝐂𝐡𝐞𝐜𝐤𝐬</b> ➔ {total_checks}",
        f"{ce(APPROVED_EMOJI_ID, '◆')} <b>𝐀𝐩𝐩𝐫𝐨𝐯𝐞ᴅ</b>   ➔ {approved}",
        f"{ce(DECLINED_EMOJI_ID, '◆')} <b>𝐃𝐞𝐜𝐥ɪɴᴇᴅ</b>    ➔ {declined}",
        f"{ce(RATE_EMOJI_ID, '◆')} <b>𝐀𝐩𝐩𝐫𝐨𝐯𝐚𝐥 𝐑𝐚𝐭𝐞</b> ➔ {approval_rate}",
        f"{ce(LAST_GATE_EMOJI_ID, '◆')} <b>𝐋𝐚𝐬𝐭 𝐆𝐚𝐭𝐞</b>   ➔ {last_gate}",
        f"{ce(LAST_BIN_EMOJI_ID, '◆')} <b>𝐋𝐚𝐬𝐭 𝐁𝐈𝐍</b>    ➔ <code>{last_card}</code>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"{ce(REFERRAL_EMOJI_ID, '◆')} <b>𝐑𝐞𝐟ᴇʀʀᴀʟꜱ</b>   ➔ {total_refs} (+{total_refs * REFERRAL_CREDITS} credits)",
        f"{ce(CODES_EMOJI_ID, '◆')} <b>𝐂ᴏᴅᴇꜱ</b>      ➔ {codes_red} redeemed",
        f"{ce(KEYS_EMOJI_ID, '◆')} <b>𝐊ᴇʏꜱ</b>       ➔ {keys_red} redeemed",
        "━━━━━━━━━━━━━━━━━━━━",
        f"𝗩𝗲𝗿𝘀𝗶𝗼𝗻 ➔ {VERSION}  |  <a href='{DEV_LINK}'>𝗕𝗮𝘁𝗺𝗮𝗻</a>",
    ]
    return "\n".join(lines)

def gate_info_text(gate_name: str, cmd: str, cost: int) -> str:
    return (
        f"━━━━━━━━━━━━━━━━━\n<b>{gate_name}</b>\n━━━━━━━━━━━━━━━━━\n\n"
        f"{ce(CREDITS_EMOJI_ID, '◆')} <b>Cᴏsᴛ</b>    ➺ {cost} Credit(s) per check\n\n"
        f"{ce(USAGE_EMOJI_ID, '◆')} <b>Uꜱᴀɢᴇ:</b>\n<code>/{cmd} cc|mm|yy|cvv</code>\n\n"
        f"{ce(EXAMPLE_EMOJI_ID, '◆')} <b>Exᴀᴍᴘʟᴇ:</b>\n<code>/{cmd} 4111111111111111|12|2026|123</code>\n\n"
        "━━━━━━━━━━━━━━━━━"
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SEND PHOTO HELPER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def send_with_photo(msg, caption: str, reply_markup=None, parse_mode="HTML"):
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
# FORCE SUBSCRIBE — CUSTOM EMOJIS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_force_sub_cache: dict[int, tuple[bool, float]] = {}

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
        f"{ce(LOCK_EMOJI_ID, '⬅')} <b>𝗝𝗢𝗜𝗡 𝗥𝗘𝗤𝗨𝗜𝗥𝗘𝗗</b> {ce(LOCK_EMOJI_ID, '➡')}",
        "━━━━━━━━━━━━━━━━━━━━",
        "To use this bot you must join <b>all</b> our",
        "channels and groups listed below.",
        "",
        f"{ce(PROGRESS_BAR_EMOJI_ID, '◆')} <b>Progress:</b>  {joined}/{total} joined",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    for uname, _link, label in not_joined:
        lines.append(f"  {ce(NOT_JOINED_EMOJI_ID, '✗')}  {label}  <code>@{uname}</code>")
    lines += [
        "━━━━━━━━━━━━━━━━━━━━",
        f"Click each button below to join,",
        f"then press {ce(VERIFY_EMOJI_ID, '✓')} <b>Verify</b>.",
    ]
    return "\n".join(lines)

def kb_force_sub(not_joined: list) -> InlineKeyboardMarkup:
    rows = []
    for uname, link, label in not_joined:
        rows.append([InlineKeyboardButton(
            f"{label}  ➺  @{uname}", 
            url=link,
            icon_custom_emoji_id=JOIN_EMOJI_ID
        )])
    rows.append([InlineKeyboardButton(
        f"  I Joined All — Verify Now", 
        callback_data="check_sub",
        icon_custom_emoji_id=VERIFY_EMOJI_ID
    )])
    return InlineKeyboardMarkup(rows)

async def send_force_join_photo(msg, not_joined: list):
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
# BAN CHECK — CUSTOM EMOJIS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def require_not_banned(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    if user_id == OWNER_ID:
        return True
    ud = get_user_data(user_id, context)
    if ud.get("banned", False):
        try:
            await update.message.reply_text(
                f"<b>[ 𖥷iТ ] ➺ Bᴀɴɴᴇᴅ</b> {ce(BANNED_EMOJI_ID, 'X')}\n"
                f"━━━━━━━━━━━━━━━━━\n"
                "You have been banned from using this bot.\n"
                "Contact support if you think this is a mistake.\n"
                "━━━━━━━━━━━━━━━━━",
                parse_mode="HTML"
            )
        except Exception:
            pass
        return False
    return True

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CARD CHECK RESULT UI — CUSTOM EMOJIS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def build_check_result(card_raw: str, gate_name: str, raw_response: str,
                       bin_data: dict, username: str, plan: str,
                       time_taken: str, is_approved: bool,
                       is_timeout: bool = False, is_error: bool = False) -> str:
    if is_timeout:
        status = "Tɪᴍᴇᴏᴜᴛ"
        status_emoji = ce(TIMEOUT_EMOJI_ID, "⏱")
    elif is_error:
        status = "Eʀʀᴏʀ"
        status_emoji = ce(ERROR_EMOJI_ID, "⚠")
    elif is_approved:
        status = "Aᴘᴘʀᴏᴠᴇᴅ"
        status_emoji = ce(get_random_live_emoji(), "✓")
    else:
        status = "Dᴇᴄʟɪɴᴇᴅ"
        status_emoji = ce(DECLINED_EMOJI_ID, "✗")

    plan_emoji  = get_plan_emoji_tag(plan)
    plan_label = get_styled_plan(plan)
    bin_txt    = "N/A"
    if bin_data and not bin_data.get("error"):
        scheme  = str(bin_data.get("scheme",  "N/A")).upper()
        bank    = bin_data.get("bank",    "N/A")
        country = str(bin_data.get("country", "N/A")).upper()
        flag    = bin_data.get("country_emoji", "")
        bin_txt = f"{scheme} - {bank} - {flag} {country}".strip()

    uname_display = f"{escape(username)} {plan_emoji} ({plan_label})".strip()
    lines = [
        f"<b>[ 𖥷iТ ] ➺ {status}</b> {status_emoji}",
        f"{ce(SEARCH_EMOJI_ID, '◆')} ➺ <code>{card_raw}</code>",
        f"{ce(GATE_EMOJI_ID, '◆')} <b>Gᴀᴛᴇ</b> ➺ {gate_name} {ce(CARD_EMOJI_ID, '◆')}",
        f"{ce(RAW_EMOJI_ID, '◆')} <b>Rᴀᴡ</b>  ➺ {escape(raw_response)}",
        f"{ce(INFO_EMOJI_ID, '◆')} <b>Iɴꜰᴏ</b> ➺ {bin_txt}",
        f"{ce(USER_EMOJI_ID, '◆')} <b>Uꜱᴇʀ</b> ➺ {uname_display}",
        f"{ce(DEV_EMOJI_ID, '◆')} <b>Pʀᴏ</b>  ➺ Batman | {time_taken}s",
        "━━━━━━━━━━━━━━━━━",
        f"{ce(CHANNEL_EMOJI_ID, '◆')} @Batcardchk",
    ]
    return "\n".join(lines)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# KEYBOARDS — CUSTOM EMOJI ICONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def kb_main(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("GATES"), callback_data="mgates", icon_custom_emoji_id=GATES_EMOJI_ID),
         InlineKeyboardButton(B("PRICING"), callback_data="mprice", icon_custom_emoji_id=PRICING_EMOJI_ID)],
        [InlineKeyboardButton(B("CONNECT") + " ↗", url=CHANNEL_LINK, icon_custom_emoji_id=CONNECT_EMOJI_ID),
         InlineKeyboardButton(B("PROFILE"), callback_data="mprofile", icon_custom_emoji_id=PROFILE_EMOJI_ID)],
        [InlineKeyboardButton(B("CMD"), callback_data="cmd_pg_1", icon_custom_emoji_id=CMD_EMOJI_ID)],
        [InlineKeyboardButton(B("SUPPORT") + " ↗", url=SUPPORT_LINK, icon_custom_emoji_id=SUPPORT_EMOJI_ID)],
    ])

def kb_back(cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(
        B("BACK"), callback_data=cb, icon_custom_emoji_id=BACK_EMOJI_ID
    )]])

def kb_price() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("10$ - CORE"), callback_data="pay10", icon_custom_emoji_id=PLAN_EMOJIS["CORE"]),
         InlineKeyboardButton(B("15$ - ELITE"), callback_data="pay15", icon_custom_emoji_id=PLAN_EMOJIS["ELITE"]),
         InlineKeyboardButton(B("30$ - ROOT"), callback_data="pay30", icon_custom_emoji_id=PLAN_EMOJIS["ROOT"])],
        [InlineKeyboardButton(B("SUPPORT") + " ➺", url=SUPPORT_LINK, icon_custom_emoji_id=SUPPORT_EMOJI_ID)],
        [InlineKeyboardButton(B("BACK"), callback_data="bmain", icon_custom_emoji_id=BACK_EMOJI_ID)],
    ])

def kb_payment() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("SUPPORT") + " ➺", url=SUPPORT_LINK, icon_custom_emoji_id=SUPPORT_EMOJI_ID)],
        [InlineKeyboardButton(B("BACK"), callback_data="mprice", icon_custom_emoji_id=BACK_EMOJI_ID)],
    ])

def kb_gate_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("AUTH"), callback_data="mauth", icon_custom_emoji_id=AUTH_EMOJI_ID),
         InlineKeyboardButton(B("CHARGE"), callback_data="mcharge", icon_custom_emoji_id=CHARGE_EMOJI_ID),
         InlineKeyboardButton(B("PREMIUM"), callback_data="mmass", icon_custom_emoji_id=PREMIUM_EMOJI_ID)],
        [InlineKeyboardButton(B("BACK"), callback_data="bmain", icon_custom_emoji_id=BACK_EMOJI_ID)],
    ])

def kb_auth_gates() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("BRAINTREE"), callback_data="ib3", icon_custom_emoji_id=BRAINTREE_EMOJI_ID)],
        [InlineKeyboardButton(B("BACK"), callback_data="mgates", icon_custom_emoji_id=BACK_EMOJI_ID)],
    ])

def kb_charge_gates() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("STRIPE"), callback_data="ichk", icon_custom_emoji_id=STRIPE_EMOJI_ID),
         InlineKeyboardButton(B("PAYPAL"), callback_data="ipp", icon_custom_emoji_id=PAYPAL_EMOJI_ID)],
        [InlineKeyboardButton(B("SHOPIFY"), callback_data="ish", icon_custom_emoji_id=SHOPIFY_EMOJI_ID),
         InlineKeyboardButton(B("PAYU"), callback_data="ipyu", icon_custom_emoji_id=PAYU_EMOJI_ID)],
        [InlineKeyboardButton(B("BACK"), callback_data="mgates", icon_custom_emoji_id=BACK_EMOJI_ID)],
    ])

def kb_premium_gates() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("STRIPE AUTH"), callback_data="iau", icon_custom_emoji_id=STRIPE_EMOJI_ID),
         InlineKeyboardButton(B("STRIPE MASS"), callback_data="imss", icon_custom_emoji_id=STRIPE_EMOJI_ID)],
        [InlineKeyboardButton(B("PAYPAL MASS"), callback_data="impp2", icon_custom_emoji_id=PAYPAL_EMOJI_ID)],
        [InlineKeyboardButton(B("BACK"), callback_data="mgates", icon_custom_emoji_id=BACK_EMOJI_ID)],
    ])

def kb_upgrade() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("BUY PREMIUM"), callback_data="mprice", icon_custom_emoji_id=DIAMOND_EMOJI_ID)],
        [InlineKeyboardButton(B("SUPPORT") + " ➺", url=SUPPORT_LINK, icon_custom_emoji_id=SUPPORT_EMOJI_ID)],
    ])

def kb_cooldown() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("Plans"), callback_data="mprice", icon_custom_emoji_id=PLAN_BTN_EMOJI_ID)],
    ])

def kb_fb_owner(key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Approve", callback_data=f"fb_ok_{key}", icon_custom_emoji_id=CHECK_EMOJI_ID),
        InlineKeyboardButton("Decline", callback_data=f"fb_no_{key}", icon_custom_emoji_id=CROSS_EMOJI_ID),
    ]])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CMD PAGES — CUSTOM EMOJIS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CMD_TOTAL_PAGES = 6

CMD_PAGES = {
    1: (
        f"{ce(CMD_EMOJI_ID, '⬅')} <b>𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦</b> {ce(CMD_EMOJI_ID, '➡')}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>Available Modules</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{ce(CHARGE_EMOJI_ID, '[+]')} <b>Charge Module</b>  (4)\n"
        f"{ce(AUTH_EMOJI_ID, '[+]')} <b>Auth Module</b>    (1)\n"
        f"{ce(PREMIUM_EMOJI_ID, '[+]')} <b>Mass Module</b>    (3)  <i>Premium</i>\n"
        f"{ce(TOOLS_EMOJI_ID, '[+]')} <b>Tools</b>          (5)\n"
        f"{ce(ACCOUNT_EMOJI_ID, '[+]')} <b>Account</b>        (3)\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Use {ce(NEXT_EMOJI_ID, '▶')} Next to explore each module</i>"
    ),
    2: (
        f"{ce(CHARGE_EMOJI_ID, '⬅')} <b>𝗖𝗛𝗔𝗥𝗚𝗘 𝗠𝗢𝗗𝗨𝗟𝗘</b> {ce(CHARGE_EMOJI_ID, '➡')}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{ce(STRIPE_EMOJI_ID, '◆')} <b>/chk</b>  ➔ Stripe Charge\n"
        "       Cost ➔ 1 Credit\n"
        "       Usage: <code>/chk cc|mm|yy|cvv</code>\n\n"
        f"{ce(PAYPAL_EMOJI_ID, '◆')} <b>/pp</b>   ➔ PayPal Charge\n"
        "       Cost ➔ 1 Credit\n"
        "       Usage: <code>/pp cc|mm|yy|cvv</code>\n\n"
        f"{ce(SHOPIFY_EMOJI_ID, '◆')} <b>/sh</b>   ➔ Shopify Charge\n"
        "       Cost ➔ 1 Credit\n"
        "       Usage: <code>/sh cc|mm|yy|cvv</code>\n\n"
        f"{ce(PAYU_EMOJI_ID, '◆')} <b>/pyu</b>  ➔ PayU Charge\n"
        "       Cost ➔ 1 Credit\n"
        "       Usage: <code>/pyu cc|mm|yy|cvv</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Example: /chk 4111111111111111|12|2026|123</i>"
    ),
    3: (
        f"{ce(AUTH_EMOJI_ID, '⬅')} <b>𝗔𝗨𝗧𝗛 𝗠𝗢𝗗𝗨𝗟𝗘</b> {ce(AUTH_EMOJI_ID, '➡')}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{ce(BRAINTREE_EMOJI_ID, '◆')} <b>/b3</b>   ➔ Braintree Auth\n"
        "       Cost ➔ 1 Credit\n"
        "       Usage: <code>/b3 cc|mm|yy|cvv</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{ce(INFO_EMOJI_ID, '◆')} <b>What is Auth?</b>\n"
        "Auth gates verify a card is live\n"
        "without making a real charge.\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Example: /b3 4111111111111111|12|2026|123</i>"
    ),
    4: (
        f"{ce(PREMIUM_EMOJI_ID, '⬅')} <b>𝗠𝗔𝗦𝗦 𝗠𝗢𝗗𝗨𝗟𝗘</b> {ce(PREMIUM_EMOJI_ID, '➡')}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{ce(LOCK_EMOJI_ID, '◆')} <b>Premium Plan Required</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{ce(STRIPE_EMOJI_ID, '◆')} <b>/au</b>   ➔ Stripe Auth Mass\n"
        "       Cost ➔ Unlimited (Premium)\n"
        "       Usage: <code>/au cc|mm|yy|cvv</code>\n\n"
        f"{ce(STRIPE_EMOJI_ID, '◆')} <b>/mss</b>  ➔ Stripe Mass Checker\n"
        "       Cost ➔ Unlimited (Premium)\n"
        "       Usage: <code>/mss cc|mm|yy|cvv</code>\n\n"
        f"{ce(PAYPAL_EMOJI_ID, '◆')} <b>/mpp2</b> ➔ PayPal Mass Checker\n"
        "       Cost ➔ Unlimited (Premium)\n"
        "       Usage: <code>/mpp2 cc|mm|yy|cvv</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Upgrade via /plan to unlock these gates</i>"
    ),
    5: (
        f"{ce(TOOLS_EMOJI_ID, '⬅')} <b>𝗧𝗢𝗢𝗟𝗦</b> {ce(TOOLS_EMOJI_ID, '➡')}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{ce(BIN_EMOJI_ID, '◆')} <b>/bin</b>   ➔ BIN Lookup\n"
        "        Usage: <code>/bin 411111</code>\n"
        "        <i>Get card info from first 6 digits</i>\n\n"
        f"{ce(PING_EMOJI_ID, '◆')} <b>/ping</b>  ➔ Bot Speed Test\n"
        "        Usage: <code>/ping</code>\n"
        "        <i>Check bot response time in ms</i>\n\n"
        f"{ce(REDEEM_EMOJI_ID, '◆')} <b>/rm</b>    ➔ Redeem Code / Key\n"
        "        Usage: <code>/rm CODE</code>\n"
        "        <i>Redeem credit codes or premium keys</i>\n\n"
        f"{ce(FEEDBACK_EMOJI_ID, '◆')} <b>/fb</b>    ➔ Submit Feedback\n"
        "        Usage: <code>/fb</code> (reply to photo/video)\n"
        "        <i>Send proof screenshots to owner</i>\n\n"
        f"{ce(REFERRAL_EMOJI_ID, '◆')} <b>/refer</b> ➔ Refer & Earn\n"
        "        Usage: <code>/refer</code>\n"
        "        <i>Get your referral link & earn credits</i>\n"
        "━━━━━━━━━━━━━━━━━━━━"
    ),
    6: (
        f"{ce(ACCOUNT_EMOJI_ID, '⬅')} <b>𝗔𝗖𝗖𝗢𝗨𝗡𝗧</b> {ce(ACCOUNT_EMOJI_ID, '➡')}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{ce(GATE_EMOJI_ID, '◆')} <b>/start</b> ➔ Open Dashboard\n"
        "         <i>View profile & all buttons</i>\n\n"
        f"{ce(PRICING_EMOJI_ID, '◆')} <b>/plan</b>  ➔ View Premium Plans\n"
        "         <i>See pricing & upgrade options</i>\n\n"
        f"{ce(REFERRAL_EMOJI_ID, '◆')} <b>/refer</b> ➔ Referral Program\n"
        "         <i>Earn credits for every invite</i>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{ce(INFO_EMOJI_ID, '◆')} <b>How Credits Work</b>\n"
        "• Trial users start with 150 credits\n"
        "• Each gate check costs 1 credit\n"
        "• Earn credits by referring friends\n"
        f"• Premium = Unlimited credits {ce(UNLIMITED_EMOJI_ID, '◆')}\n"
        "━━━━━━━━━━━━━━━━━━━━"
    ),
}

def kb_cmd_nav(page: int) -> InlineKeyboardMarkup:
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(B("PREV"), callback_data=f"cmd_pg_{page - 1}", icon_custom_emoji_id=PREV_EMOJI_ID))
    nav_row.append(InlineKeyboardButton(f"{page}/{CMD_TOTAL_PAGES}", callback_data="cmd_pg_noop", icon_custom_emoji_id=PAGE_EMOJI_ID))
    if page < CMD_TOTAL_PAGES:
        nav_row.append(InlineKeyboardButton(B("NEXT") + " ▶", callback_data=f"cmd_pg_{page + 1}", icon_custom_emoji_id=NEXT_EMOJI_ID))
    return InlineKeyboardMarkup([
        nav_row,
        [InlineKeyboardButton(B("CLOSE"), callback_data="bmain", icon_custom_emoji_id=CLOSE_EMOJI_ID)],
    ])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# REFERRAL SYSTEM — CUSTOM EMOJIS
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
                f"<b>Rᴇꜰᴇʀʀᴀʟ Bᴏɴᴜꜱ</b> {ce(BONUS_EMOJI_ID, '◆')}\n"
                f"━━━━━━━━━━━━━━━━━\n"
                "Someone joined via your link!\n"
                f"{ce(CREDITS_EMOJI_ID, '◆')} <b>Cʀᴇᴅɪᴛꜱ Aᴅᴅᴇᴅ</b>    ➺ +{REFERRAL_CREDITS}\n"
                f"{ce(TOTAL_EMOJI_ID, '◆')} <b>Tᴏᴛᴀʟ Rᴇꜰᴇʀʀᴀʟꜱ</b> ➺ {referrer_ud['total_refs']}\n"
                "━━━━━━━━━━━━━━━━━"
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
        await update.message.reply_text(
            f"Bot is under maintenance {ce(MAINTENANCE_EMOJI_ID, '◆')}"
        )
        return
    if not context.bot_data.get(f"{gate_key}_on", True):
        await update.message.reply_text(f"Gate [{gate_name}] is currently OFF {ce(CROSS_EMOJI_ID, '✗')}.")
        return

    if not await require_membership(update, context): return

    ud      = get_user_data(user.id, context)
    premium = is_user_premium(ud)
    _update_user_meta(ud, user)

    if gate_key in PREMIUM_GATES and not premium:
        await update.message.reply_text(
            f"<b>[ 𖥷iТ ] ➺ Pʀᴇᴍɪᴜᴍ Oɴʟʏ</b> {ce(LOCK_EMOJI_ID, '◆')}\n"
            "━━━━━━━━━━━━━━━━━\nUse /plan to upgrade.",
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
            f"{ce(USAGE_EMOJI_ID, '◆')} Uꜱᴀɢᴇ: <code>/{gate_key} cc|mm|yy|cvv</code>", parse_mode="HTML"
        )
        return

    if not premium:
        credits = ud.get("credits", 0)
        if credits <= 0:
            await update.message.reply_text(
                f"<b>[ 𖥷iТ ] ➺ Nᴏ Cʀᴇᴅɪᴛꜱ</b> {ce(NO_CREDITS_EMOJI_ID, '◆')}\n"
                "━━━━━━━━━━━━━━━━━\n"
                "You have <b>0 credits</b> remaining.\n\n"
                f"{ce(DIAMOND_EMOJI_ID, '◆')} Upgrade to <b>Premium</b> for unlimited checks\n"
                "   with no cooldown and no credit limits.\n"
                "━━━━━━━━━━━━━━━━━",
                reply_markup=kb_upgrade(), parse_mode="HTML"
            )
            return

        remaining = get_cooldown_remaining(user.id, context)
        if remaining > 0:
            await update.message.reply_text(
                f"{ce(COOLDOWN_EMOJI_ID, '◆')} <b>Active cooldown !</b>\n\n"
                f"Please wait <b>{remaining:.1f} seconds</b> before continuing.\n\n"
                f"{ce(UPGRADE_EMOJI_ID, '◆')} <b>Purchase premium plan to use commands without cooldown.</b>",
                reply_markup=kb_cooldown(), parse_mode="HTML"
            )
            return

        set_cooldown(user.id, context)
        ud["credits"] = credits - 1

    api_url  = context.bot_data.get(f"gate_url_{gate_key}") or GATE_URLS.get(gate_key, "")
    site_url = GATE_SITES.get(gate_key, "example.com")
    bin_num  = card_raw[:6]

    if not api_url:
        await update.message.reply_text("Gate API not set.")
        return

    msg        = await update.message.reply_text(f"[ 𖥷iТ ] ➺ Sᴄᴀɴɴɪɴɢ... {ce(SCAN_EMOJI_ID, '◆')}")
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
            raw_response="Rᴇǫᴜᴇꜱᴛ Tɪᴍᴇᴏᴜᴛ", bin_data={},
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
# GATE ON/OFF (OWNER ONLY) — CUSTOM EMOJIS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _gate_toggle(update, context, gate: str, state: bool):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data[f"{gate}_on"] = state
    status_emoji = ce(CHECK_EMOJI_ID, '✓') if state else ce(CROSS_EMOJI_ID, '✗')
    await update.message.reply_text(f"Gate [{gate.upper()}] turned {'ON' if state else 'OFF'} {status_emoji}.")


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
# PREMIUM ACTIVATION — CUSTOM EMOJIS
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
    plan_emoji   = get_plan_emoji_tag(plan)

    txt = (
        f"<b>[ 𖥷iТ ] ➺ Aᴄᴄᴇꜱꜱ Aᴄᴛɪᴠᴀᴛᴇᴅ</b> {ce(ACTIVATED_EMOJI_ID, '◆')}\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"{ce(USER_EMOJI_ID, '◆')} <b>Uꜱᴇʀ</b>     ➺ {display_name}\n"
        f"{ce(PREMIUM_EMOJI_ID, '◆')} <b>Aᴄᴄᴇꜱꜱ</b>  ➺ {styled} {plan_emoji}\n"
        f"{ce(DAYS_EMOJI_ID, '◆')} <b>Dᴀʏꜱ</b>    ➺ {days}\n"
        f"{ce(UNLIMITED_EMOJI_ID, '◆')} <b>Cʀᴇᴅɪᴛꜱ</b> ➺ Unlimited\n"
        f"{ce(EXPIRES_EMOJI_ID, '◆')} <b>Exᴘɪʀᴇꜱ</b> ➺ {exp_date}\n"
        f"{ce(RECEIPT_EMOJI_ID, '◆')} <b>Rᴇᴄᴇɪᴘᴛ</b> ➺ <code>{receipt}</code>\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"{ce(SAVE_EMOJI_ID, '◆')} Save this receipt ID.\n"
        f"{ce(DEV_EMOJI_ID, '◆')} <b>Pʀᴏ</b> ➺ Batman"
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
    plan_emoji = get_plan_emoji_tag(plan)

    await update.message.reply_text(
        f"━━━━━━━━━━━━━━━━━\n"
        f"<b>Pʀᴇᴍɪᴜᴍ Gʀᴀɴᴛᴇᴅ</b> {ce(GRANTED_EMOJI_ID, '◆')}\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"{ce(USER_EMOJI_ID, '◆')} <b>Uꜱᴇʀ</b>     ➺ {uname_line}\n"
        f"{ce(INFO_EMOJI_ID, '◆')} <b>ID</b>       ➺ <code>{uid}</code>\n"
        f"{ce(PREMIUM_EMOJI_ID, '◆')} <b>Pʟᴀɴ</b>     ➺ {get_styled_plan(plan)} {plan_emoji}\n"
        f"{ce(DAYS_EMOJI_ID, '◆')} <b>Dᴀʏꜱ</b>     ➺ {days}\n"
        f"{ce(EXPIRES_EMOJI_ID, '◆')} <b>Exᴘɪʀᴇꜱ</b>  ➺ {exp_date}\n"
        f"{ce(RECEIPT_EMOJI_ID, '◆')} <b>Rᴇᴄᴇɪᴘᴛ</b>  ➺ <code>{receipt}</code>\n"
        "━━━━━━━━━━━━━━━━━",
        parse_mode="HTML",
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# USER COMMANDS — CUSTOM EMOJIS
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

    if ud.get("banned", False) and user.id != OWNER_ID:
        await update.message.reply_text(
            f"<b>[ 𖥷iТ ] ➺ Bᴀɴɴᴇᴅ</b> {ce(BANNED_EMOJI_ID, 'X')}\n"
            f"━━━━━━━━━━━━━━━━━\n"
            "You have been banned from using this bot.\n"
            "━━━━━━━━━━━━━━━━━",
            parse_mode="HTML"
        )
        return

    not_joined = await check_force_sub(user.id, context)
    if not_joined:
        await send_force_join_photo(update.message, not_joined)
        return

    await send_with_photo(update.message, ui_profile(user, context), reply_markup=kb_main(user.id))

async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_not_banned(update, context): return
    if not await require_membership(update, context): return
    t   = time.time()
    msg = await update.message.reply_text(f"[ 𖥷iТ ] ➺ Pɪɴɢɪɴɢ... {ce(PING_EMOJI_ID, '◆')}")
    await msg.edit_text(
        f"<b>[ 𖥷iТ ] ➺ Pᴏɴɢ</b> {ce(PING_EMOJI_ID, '◆')} | {int((time.time() - t) * 1000)}ms",
        parse_mode="HTML"
    )

async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_not_banned(update, context): return
    if not await require_membership(update, context): return
    txt = (
        f"<b>[ 𖥷iТ ] Batman Premium Plans</b> {ce(PRICING_EMOJI_ID, '◆')}\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"{ce(PLAN_EMOJIS['CORE'], '◆')} <b>Aᴄᴄᴇꜱꜱ</b>  ➺ Cᴏʀᴇ\n"
        f"{ce(DAYS_EMOJI_ID, '◆')} <b>Dᴀʏꜱ</b>     ➺ 7\n"
        f"{ce(UNLIMITED_EMOJI_ID, '◆')} <b>Cʀᴇᴅɪᴛꜱ</b> ➺ Unlimited\n"
        f"{ce(CREDITS_EMOJI_ID, '◆')} <b>Pʀɪᴄᴇ</b>   ➺ 10$\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"{ce(PLAN_EMOJIS['ELITE'], '◆')} <b>Aᴄᴄᴇꜱꜱ</b>  ➺ Eʟɪᴛᴇ\n"
        f"{ce(DAYS_EMOJI_ID, '◆')} <b>Dᴀʏꜱ</b>     ➺ 15\n"
        f"{ce(UNLIMITED_EMOJI_ID, '◆')} <b>Cʀᴇᴅɪᴛꜱ</b> ➺ Unlimited\n"
        f"{ce(CREDITS_EMOJI_ID, '◆')} <b>Pʀɪᴄᴇ</b>   ➺ 15$\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"{ce(PLAN_EMOJIS['ROOT'], '◆')} <b>Aᴄᴄᴇꜱꜱ</b>  ➺ Rᴏᴏᴛ\n"
        f"{ce(DAYS_EMOJI_ID, '◆')} <b>Dᴀʏꜱ</b>     ➺ 30\n"
        f"{ce(UNLIMITED_EMOJI_ID, '◆')} <b>Cʀᴇᴅɪᴛꜱ</b> ➺ Unlimited\n"
        f"{ce(CREDITS_EMOJI_ID, '◆')} <b>Pʀɪᴄᴇ</b>   ➺ 30$\n"
        f"━━━━━━━━━━━━━━━━━"
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
        f"<b>[ 𖥷iТ ] Rᴇꜰᴇʀʀᴀʟ</b> {ce(REFERRAL_EMOJI_ID, '◆')}\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"{ce(LINK_EMOJI_ID, '◆')} <b>Lɪɴᴋ</b>    ➺ <code>{link}</code>\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"{ce(TOTAL_EMOJI_ID, '◆')} <b>Rᴇꜰᴇʀʀᴀʟꜱ</b> ➺ {total_refs}\n"
        f"{ce(EARNED_EMOJI_ID, '◆')} <b>Eᴀʀɴᴇᴅ</b>   ➺ {total_refs * REFERRAL_CREDITS} credits\n"
        f"{ce(CREDITS_EMOJI_ID, '◆')} <b>Pᴇʀ Rᴇꜰ</b>  ➺ +{REFERRAL_CREDITS} credits\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"{ce(SHARE_EMOJI_ID, '◆')} Share your link to earn free credits!"
    )
    await update.message.reply_text(txt, parse_mode="HTML",
                                    reply_markup=kb_back("bmain"),
                                    disable_web_page_preview=True)

async def cmd_rm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_not_banned(update, context): return
    if not await require_membership(update, context): return
    if not context.args:
        await update.message.reply_text(
            f"{ce(USAGE_EMOJI_ID, '◆')} Uꜱᴀɢᴇ: /rm <code>CODE</code>",
            parse_mode="HTML"
        )
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
            f"Redeemed +{codes[code]['value']} credits {ce(BONUS_EMOJI_ID, '◆')}\n"
            f"{ce(CREDITS_EMOJI_ID, '◆')} <b>Cʀᴇᴅɪᴛꜱ</b> ➺ {ud['credits']}",
            parse_mode="HTML"
        )
    elif code in keys and not keys[code]["used"]:
        keys[code]["used"] = True
        p, d = keys[code]["plan"], keys[code]["days"]
        ud["keys_redeemed"] = ud.get("keys_redeemed", 0) + 1
        receipt = await send_activation_msg(uid, p, d, context)
        await update.message.reply_text(
            f"Activated {get_styled_plan(p)} for {d} days! {ce(ACTIVATED_EMOJI_ID, '◆')}\n"
            f"{ce(RECEIPT_EMOJI_ID, '◆')} <b>Rᴇᴄᴇɪᴘᴛ</b> ➺ <code>{receipt}</code>",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text(
            f"Invalid or already used code {ce(CROSS_EMOJI_ID, '✗')}"
        )

async def cmd_bin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_not_banned(update, context): return
    if not await require_membership(update, context): return
    bin_num = context.args[0].strip()[:6] if context.args else None
    if not bin_num or not bin_num.isdigit() or len(bin_num) < 6:
        await update.message.reply_text(
            f"{ce(USAGE_EMOJI_ID, '◆')} Uꜱᴀɢᴇ: <code>/bin 411111</code>",
            parse_mode="HTML"
        )
        return
    msg = await update.message.reply_text(
        f"[ 𖥷iТ ] ➺ Lᴏᴏᴋɪɴɢ ᴜᴘ... {ce(SEARCH_EMOJI_ID, '◆')}"
    )
    try:
        bd = await get_bin_info(bin_num)
        if bd.get("error"):
            await msg.edit_text(f"BIN not found {ce(CROSS_EMOJI_ID, '✗')}")
            return
        txt = (
            f"<b>[ 𖥷iТ ] ➺ BIN Lookup</b> {ce(BIN_EMOJI_ID, '◆')}\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"{ce(BIN_EMOJI_ID, '◆')} <b>BIN</b>     ➺ <code>{bin_num}</code>\n"
            f"{ce(INFO_EMOJI_ID, '◆')} <b>Scheme</b>  ➺ {str(bd.get('scheme', 'N/A')).upper()}\n"
            f"{ce(INFO_EMOJI_ID, '◆')} <b>Type</b>    ➺ {str(bd.get('type', 'N/A')).upper()}\n"
            f"{ce(INFO_EMOJI_ID, '◆')} <b>Bank</b>    ➺ {bd.get('bank', 'N/A')}\n"
            f"{ce(INFO_EMOJI_ID, '◆')} <b>Country</b> ➺ {bd.get('country_emoji', '')} {str(bd.get('country', 'N/A')).upper()}\n"
            f"━━━━━━━━━━━━━━━━━"
        )
        await msg.edit_text(txt, parse_mode="HTML")
    except Exception as e:
        await msg.edit_text(
            f"Error: <code>{str(e)[:100]}</code> {ce(ERROR_EMOJI_ID, '◆')}",
            parse_mode="HTML"
        )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FEEDBACK SYSTEM — CUSTOM EMOJIS
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
            await msg.reply_text(
                f"Invalid media type {ce(CROSS_EMOJI_ID, '✗')}"
            )
            return

        user_note = (msg.text or msg.caption or "").strip()
        bot_uname = context.bot.username or ""
        for prefix in (f"/fb@{bot_uname}", "/fb"):
            if user_note.lower().startswith(prefix.lower()):
                user_note = user_note[len(prefix):].strip()
                break

        key       = _fb_key(user.id)
        uname     = f"@{user.username}" if user.username else user.first_name or "User"
        submitted = datetime.now().strftime("%Y-%m-%d %H:%M")

        context.bot_data.setdefault("fb_pending", {})[key] = {
            "file_id": file_id, "file_type": file_type, "user_id": user.id,
            "username": uname, "name": user.full_name or user.first_name or "User",
            "note": user_note, "date": submitted,
        }
        await msg.reply_text(
            f"━━━━━━━━━━━━━━━━━\n"
            f"<b>Fᴇᴇᴅʙᴀᴄᴋ Sᴜʙᴍɪᴛᴛᴇᴅ</b> {ce(SUBMITTED_EMOJI_ID, '◆')}\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"{ce(UNDER_REVIEW_EMOJI_ID, '◆')} Under review.\n"
            f"━━━━━━━━━━━━━━━━━",
            parse_mode="HTML"
        )
    else:
        await msg.reply_text(
            f"{ce(PROOF_EMOJI_ID, '◆')} Reply to a photo or video with /fb\n"
            f"{ce(INFO_EMOJI_ID, '◆')} to submit feedback/proof."
        )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CALLBACK QUERY HANDLER — CUSTOM EMOJIS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = query.from_user

    if data == "bmain":
        if not await require_not_banned(update, context): return
        not_joined = await check_force_sub(user.id, context)
        if not_joined:
            await send_force_join_photo(query.message, not_joined)
            return
        ud = get_user_data(user.id, context)
        _update_user_meta(ud, user)
        await query.edit_message_text(
            ui_profile(user, context),
            reply_markup=kb_main(user.id),
            parse_mode="HTML"
        )

    elif data == "mprofile":
        ud = get_user_data(user.id, context)
        _update_user_meta(ud, user)
        await query.edit_message_text(
            ui_full_profile(user, context),
            reply_markup=kb_back("bmain"),
            parse_mode="HTML"
        )

    elif data == "mprice":
        await query.edit_message_text(
            f"<b>[ 𖥷iТ ] Batman Premium Plans</b> {ce(PRICING_EMOJI_ID, '◆')}\n"
            f"━━━━━━━━━━━━━━━━━\n\n"
            f"{ce(PLAN_EMOJIS['CORE'], '◆')} <b>Aᴄᴄᴇꜱꜱ</b>  ➺ Cᴏʀᴇ\n"
            f"{ce(DAYS_EMOJI_ID, '◆')} <b>Dᴀʏꜱ</b>     ➺ 7\n"
            f"{ce(UNLIMITED_EMOJI_ID, '◆')} <b>Cʀᴇᴅɪᴛꜱ</b> ➺ Unlimited\n"
            f"{ce(CREDITS_EMOJI_ID, '◆')} <b>Pʀɪᴄᴇ</b>   ➺ 10$\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"{ce(PLAN_EMOJIS['ELITE'], '◆')} <b>Aᴄᴄᴇꜱꜱ</b>  ➺ Eʟɪᴛᴇ\n"
            f"{ce(DAYS_EMOJI_ID, '◆')} <b>Dᴀʏꜱ</b>     ➺ 15\n"
            f"{ce(UNLIMITED_EMOJI_ID, '◆')} <b>Cʀᴇᴅɪᴛꜱ</b> ➺ Unlimited\n"
            f"{ce(CREDITS_EMOJI_ID, '◆')} <b>Pʀɪᴄᴇ</b>   ➺ 15$\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"{ce(PLAN_EMOJIS['ROOT'], '◆')} <b>Aᴄᴄᴇꜱꜱ</b>  ➺ Rᴏᴏᴛ\n"
            f"{ce(DAYS_EMOJI_ID, '◆')} <b>Dᴀʏꜱ</b>     ➺ 30\n"
            f"{ce(UNLIMITED_EMOJI_ID, '◆')} <b>Cʀᴇᴅɪᴛꜱ</b> ➺ Unlimited\n"
            f"{ce(CREDITS_EMOJI_ID, '◆')} <b>Pʀɪᴄᴇ</b>   ➺ 30$\n"
            f"━━━━━━━━━━━━━━━━━",
            reply_markup=kb_price(),
            parse_mode="HTML"
        )

    elif data == "pay10":
        await query.edit_message_text(
            f"{ce(SUPPORT_EMOJI_ID, '◆')} Contact support to purchase CORE plan\n"
            f"{ce(LINK_EMOJI_ID, '◆')} {SUPPORT_LINK}",
            reply_markup=kb_payment(),
            parse_mode="HTML"
        )
    elif data == "pay15":
        await query.edit_message_text(
            f"{ce(SUPPORT_EMOJI_ID, '◆')} Contact support to purchase ELITE plan\n"
            f"{ce(LINK_EMOJI_ID, '◆')} {SUPPORT_LINK}",
            reply_markup=kb_payment(),
            parse_mode="HTML"
        )
    elif data == "pay30":
        await query.edit_message_text(
            f"{ce(SUPPORT_EMOJI_ID, '◆')} Contact support to purchase ROOT plan\n"
            f"{ce(LINK_EMOJI_ID, '◆')} {SUPPORT_LINK}",
            reply_markup=kb_payment(),
            parse_mode="HTML"
        )

    elif data == "mgates":
        await query.edit_message_text(
            f"{ce(GATES_EMOJI_ID, '◆')} <b>Select Gate Type</b>\n"
            f"━━━━━━━━━━━━━━━━━",
            reply_markup=kb_gate_main(),
            parse_mode="HTML"
        )
    elif data == "mauth":
        await query.edit_message_text(
            f"{ce(AUTH_EMOJI_ID, '◆')} <b>Auth Gates</b>\n"
            f"━━━━━━━━━━━━━━━━━",
            reply_markup=kb_auth_gates(),
            parse_mode="HTML"
        )
    elif data == "mcharge":
        await query.edit_message_text(
            f"{ce(CHARGE_EMOJI_ID, '◆')} <b>Charge Gates</b>\n"
            f"━━━━━━━━━━━━━━━━━",
            reply_markup=kb_charge_gates(),
            parse_mode="HTML"
        )
    elif data == "mmass":
        ud = get_user_data(user.id, context)
        if not is_user_premium(ud):
            await query.edit_message_text(
                f"{ce(LOCK_EMOJI_ID, '◆')} <b>Pʀᴇᴍɪᴜᴍ Oɴʟʏ</b>\n"
                f"━━━━━━━━━━━━━━━━━\nUse /plan to upgrade.",
                reply_markup=kb_upgrade(),
                parse_mode="HTML"
            )
        else:
            await query.edit_message_text(
                f"{ce(PREMIUM_EMOJI_ID, '◆')} <b>Premium Gates</b>\n"
                f"━━━━━━━━━━━━━━━━━",
                reply_markup=kb_premium_gates(),
                parse_mode="HTML"
            )

    elif data == "ib3":
        await query.edit_message_text(
            gate_info_text("Braintree Auth", "b3", 1),
            reply_markup=kb_back("mauth"),
            parse_mode="HTML"
        )
    elif data == "ichk":
        await query.edit_message_text(
            gate_info_text("Stripe Charge", "chk", 1),
            reply_markup=kb_back("mcharge"),
            parse_mode="HTML"
        )
    elif data == "ipp":
        await query.edit_message_text(
            gate_info_text("PayPal Charge", "pp", 1),
            reply_markup=kb_back("mcharge"),
            parse_mode="HTML"
        )
    elif data == "ish":
        await query.edit_message_text(
            gate_info_text("Shopify Charge", "sh", 1),
            reply_markup=kb_back("mcharge"),
            parse_mode="HTML"
        )
    elif data == "ipyu":
        await query.edit_message_text(
            gate_info_text("PayU Charge", "pyu", 1),
            reply_markup=kb_back("mcharge"),
            parse_mode="HTML"
        )
    elif data == "iau":
        await query.edit_message_text(
            gate_info_text("Stripe Auth Mass", "au", 0),
            reply_markup=kb_back("mmass"),
            parse_mode="HTML"
        )
    elif data == "imss":
        await query.edit_message_text(
            gate_info_text("Stripe Mass Checker", "mss", 0),
            reply_markup=kb_back("mmass"),
            parse_mode="HTML"
        )
    elif data == "impp2":
        await query.edit_message_text(
            gate_info_text("PayPal Mass Checker", "mpp2", 0),
            reply_markup=kb_back("mmass"),
            parse_mode="HTML"
        )

    elif data.startswith("cmd_pg_"):
        try:
            page = int(data.split("_")[-1])
            if page in CMD_PAGES:
                await query.edit_message_text(
                    CMD_PAGES[page],
                    reply_markup=kb_cmd_nav(page),
                    parse_mode="HTML"
                )
        except (ValueError, IndexError):
            pass
    elif data == "cmd_pg_noop":
        pass

    elif data == "check_sub":
        not_joined = await check_force_sub(user.id, context)
        if not_joined:
            await query.answer(
                f"Please join all channels first {ce(NOT_JOINED_EMOJI_ID, '✗')}",
                show_alert=True
            )
            await query.edit_message_text(
                _force_join_text(not_joined),
                reply_markup=kb_force_sub(not_joined),
                parse_mode="HTML"
            )
        else:
            await query.edit_message_text(
                ui_profile(user, context),
                reply_markup=kb_main(user.id),
                parse_mode="HTML"
            )

    elif data.startswith("fb_ok_"):
        if user.id != OWNER_ID:
            await query.answer("No permission", show_alert=True)
            return
        key = data[6:]
        fb = context.bot_data.get("fb_pending", {}).pop(key, None)
        if fb:
            try:
                if fb["file_type"] == "photo":
                    await context.bot.send_photo(
                        chat_id=fb["user_id"],
                        photo=fb["file_id"],
                        caption=(
                            f"{ce(CHECK_EMOJI_ID, '◆')} <b>Feedback Approved</b>\n"
                            f"━━━━━━━━━━━━━━━━━\n"
                            f"Your feedback has been reviewed and approved.\n"
                            f"━━━━━━━━━━━━━━━━━"
                        ),
                        parse_mode="HTML"
                    )
                else:
                    await context.bot.send_video(
                        chat_id=fb["user_id"],
                        video=fb["file_id"],
                        caption=(
                            f"{ce(CHECK_EMOJI_ID, '◆')} <b>Feedback Approved</b>\n"
                            f"━━━━━━━━━━━━━━━━━\n"
                            f"Your feedback has been reviewed and approved.\n"
                            f"━━━━━━━━━━━━━━━━━"
                        ),
                        parse_mode="HTML"
                    )
            except Exception:
                pass
            await query.edit_message_text(
                f"{ce(CHECK_EMOJI_ID, '◆')} Feedback approved",
                parse_mode="HTML"
            )

    elif data.startswith("fb_no_"):
        if user.id != OWNER_ID:
            await query.answer("No permission", show_alert=True)
            return
        key = data[6:]
        fb = context.bot_data.get("fb_pending", {}).pop(key, None)
        if fb:
            try:
                await context.bot.send_message(
                    chat_id=fb["user_id"],
                    text=(
                        f"{ce(CROSS_EMOJI_ID, '✗')} <b>Feedback Declined</b>\n"
                        f"━━━━━━━━━━━━━━━━━\n"
                        f"Your feedback has been reviewed and declined.\n"
                        f"━━━━━━━━━━━━━━━━━"
                    ),
                    parse_mode="HTML"
                )
            except Exception:
                pass
            await query.edit_message_text(
                f"{ce(CROSS_EMOJI_ID, '✗')} Feedback declined",
                parse_mode="HTML"
            )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# OWNER COMMANDS — CUSTOM EMOJIS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_grant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args or len(context.args) < 3:
        await update.message.reply_text(
            f"{ce(USAGE_EMOJI_ID, '◆')} Usage: /grant <user_id|@username> <plan> <days>\n"
            f"{ce(INFO_EMOJI_ID, '◆')} Plans: CORE, ELITE, ROOT",
            parse_mode="HTML"
        )
        return
    target, plan, days = context.args[0], context.args[1].upper(), context.args[2]
    if not days.isdigit() or int(days) <= 0:
        await update.message.reply_text(
            f"Invalid days {ce(CROSS_EMOJI_ID, '✗')}",
            parse_mode="HTML"
        )
        return
    uid = await resolve_user(target, context)
    if not uid:
        await update.message.reply_text(
            f"User not found {ce(CROSS_EMOJI_ID, '✗')}",
            parse_mode="HTML"
        )
        return
    await _grant(uid, plan, int(days), update, context)

async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args:
        await update.message.reply_text(
            f"{ce(USAGE_EMOJI_ID, '◆')} Usage: /ban <user_id|@username>",
            parse_mode="HTML"
        )
        return
    uid = await resolve_user(context.args[0], context)
    if not uid:
        await update.message.reply_text(
            f"User not found {ce(CROSS_EMOJI_ID, '✗')}",
            parse_mode="HTML"
        )
        return
    ud = get_user_data(uid, context)
    ud["banned"] = True
    await update.message.reply_text(
        f"{ce(BANNED_EMOJI_ID, 'X')} User {uid} banned",
        parse_mode="HTML"
    )

async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args:
        await update.message.reply_text(
            f"{ce(USAGE_EMOJI_ID, '◆')} Usage: /unban <user_id|@username>",
            parse_mode="HTML"
        )
        return
    uid = await resolve_user(context.args[0], context)
    if not uid:
        await update.message.reply_text(
            f"User not found {ce(CROSS_EMOJI_ID, '✗')}",
            parse_mode="HTML"
        )
        return
    ud = get_user_data(uid, context)
    ud["banned"] = False
    await update.message.reply_text(
        f"{ce(ACTIVE_EMOJI_ID, '✓')} User {uid} unbanned",
        parse_mode="HTML"
    )

async def cmd_addcredits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            f"{ce(USAGE_EMOJI_ID, '◆')} Usage: /addcredits <user_id|@username> <amount>",
            parse_mode="HTML"
        )
        return
    uid = await resolve_user(context.args[0], context)
    if not uid:
        await update.message.reply_text(
            f"User not found {ce(CROSS_EMOJI_ID, '✗')}",
            parse_mode="HTML"
        )
        return
    try:
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text(
            f"Invalid amount {ce(CROSS_EMOJI_ID, '✗')}",
            parse_mode="HTML"
        )
        return
    ud = get_user_data(uid, context)
    ud["credits"] = ud.get("credits", 0) + amount
    await update.message.reply_text(
        f"{ce(CREDITS_EMOJI_ID, '◆')} Added {amount} credits to {uid}\n"
        f"{ce(INFO_EMOJI_ID, '◆')} Total: {ud['credits']}",
        parse_mode="HTML"
    )

async def cmd_genkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            f"{ce(USAGE_EMOJI_ID, '◆')} Usage: /genkey <plan> <days>\n"
            f"{ce(INFO_EMOJI_ID, '◆')} Plans: CORE, ELITE, ROOT",
            parse_mode="HTML"
        )
        return
    plan, days = context.args[0].upper(), context.args[1]
    if not days.isdigit() or int(days) <= 0:
        await update.message.reply_text(
            f"Invalid days {ce(CROSS_EMOJI_ID, '✗')}",
            parse_mode="HTML"
        )
        return
    code = gen_code(12)
    context.bot_data.setdefault("keys", {})[code] = {
        "plan": plan, "days": int(days), "used": False
    }
    await update.message.reply_text(
        f"{ce(KEYS_EMOJI_ID, '◆')} <b>Key Generated</b>\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"{ce(INFO_EMOJI_ID, '◆')} Plan: {get_styled_plan(plan)}\n"
        f"{ce(DAYS_EMOJI_ID, '◆')} Days: {days}\n"
        f"{ce(CODES_EMOJI_ID, '◆')} Key: <code>{code}</code>\n"
        f"━━━━━━━━━━━━━━━━━",
        parse_mode="HTML"
    )

async def cmd_gencode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            f"{ce(USAGE_EMOJI_ID, '◆')} Usage: /gencode <credits>",
            parse_mode="HTML"
        )
        return
    try:
        credits = int(context.args[0])
    except ValueError:
        await update.message.reply_text(
            f"Invalid credits {ce(CROSS_EMOJI_ID, '✗')}",
            parse_mode="HTML"
        )
        return
    code = gen_code(10)
    context.bot_data.setdefault("codes", {})[code] = {
        "value": credits, "used": False
    }
    await update.message.reply_text(
        f"{ce(CODES_EMOJI_ID, '◆')} <b>Code Generated</b>\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"{ce(CREDITS_EMOJI_ID, '◆')} Credits: {credits}\n"
        f"{ce(CODES_EMOJI_ID, '◆')} Code: <code>{code}</code>\n"
        f"━━━━━━━━━━━━━━━━━",
        parse_mode="HTML"
    )

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    all_users = context.bot_data.get("user_data", {})
    total = len(all_users)
    premium = sum(1 for u in all_users.values() if is_user_premium(u))
    banned = sum(1 for u in all_users.values() if u.get("banned", False))
    total_checks = sum(u.get("total_checks", 0) for u in all_users.values())
    await update.message.reply_text(
        f"{ce(TOTAL_EMOJI_ID, '◆')} <b>Bot Stats</b>\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"{ce(USER_EMOJI_ID, '◆')} Total Users: {total}\n"
        f"{ce(PREMIUM_EMOJI_ID, '◆')} Premium: {premium}\n"
        f"{ce(BANNED_EMOJI_ID, 'X')} Banned: {banned}\n"
        f"{ce(TOTAL_EMOJI_ID, '◆')} Total Checks: {total_checks}\n"
        f"━━━━━━━━━━━━━━━━━",
        parse_mode="HTML"
    )

async def cmd_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    state = not context.bot_data.get("maintenance", False)
    context.bot_data["maintenance"] = state
    status = ce(CHECK_EMOJI_ID, 'ON') if state else ce(CROSS_EMOJI_ID, 'OFF')
    await update.message.reply_text(
        f"{ce(MAINTENANCE_EMOJI_ID, '◆')} Maintenance: {status}",
        parse_mode="HTML"
    )

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args:
        await update.message.reply_text(
            f"{ce(USAGE_EMOJI_ID, '◆')} Usage: /broadcast <message>",
            parse_mode="HTML"
        )
        return
    text = " ".join(context.args)
    all_users = context.bot_data.get("user_data", {})
    sent, failed = 0, 0
    for uid_str in all_users:
        try:
            await context.bot.send_message(
                chat_id=int(uid_str),
                text=f"{ce(CHANNEL_EMOJI_ID, '◆')} <b>Broadcast</b>\n━━━━━━━━━━━━━━━━━\n{text}\n━━━━━━━━━━━━━━━━━",
                parse_mode="HTML"
            )
            sent += 1
        except Exception:
            failed += 1
    await update.message.reply_text(
        f"{ce(CHECK_EMOJI_ID, '◆')} Sent: {sent}\n{ce(CROSS_EMOJI_ID, '✗')} Failed: {failed}",
        parse_mode="HTML"
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ERROR HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}", exc_info=context.error)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# POST INIT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def post_init(application):
    logger.info(f"Bot started {ce(ACTIVATED_EMOJI_ID, '◆')}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def main():
    if not acquire_instance_lock():
        logger.error("Another instance is already running!")
        return

    builder = Application.builder().token(BOT_TOKEN).post_init(post_init)
    app = builder.build()

    app.add_error_handler(error_handler)

    # User commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("ping", cmd_ping))
    app.add_handler(CommandHandler("plan", cmd_plan))
    app.add_handler(CommandHandler("refer", cmd_refer))
    app.add_handler(CommandHandler("rm", cmd_rm))
    app.add_handler(CommandHandler("bin", cmd_bin))
    app.add_handler(CommandHandler("fb", cmd_fb))

    # Gate commands
    app.add_handler(CommandHandler("pp", cmd_pp))
    app.add_handler(CommandHandler("sh", cmd_sh))
    app.add_handler(CommandHandler("pyu", cmd_pyu))

    # Owner commands
    app.add_handler(CommandHandler("grant", cmd_grant))
    app.add_handler(CommandHandler("ban", cmd_ban))
    app.add_handler(CommandHandler("unban", cmd_unban))
    app.add_handler(CommandHandler("addcredits", cmd_addcredits))
    app.add_handler(CommandHandler("genkey", cmd_genkey))
    app.add_handler(CommandHandler("gencode", cmd_gencode))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("maintenance", cmd_maintenance))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))

    # Gate on/off commands
    app.add_handler(CommandHandler("onchk", cmd_onchk))
    app.add_handler(CommandHandler("offchk", cmd_offchk))
    app.add_handler(CommandHandler("onpp", cmd_onpp))
    app.add_handler(CommandHandler("offpp", cmd_offpp))
    app.add_handler(CommandHandler("onsh", cmd_onsh))
    app.add_handler(CommandHandler("offsh", cmd_offsh))
    app.add_handler(CommandHandler("onpyu", cmd_onpyu))
    app.add_handler(CommandHandler("offpyu", cmd_offpyu))
    app.add_handler(CommandHandler("onb3", cmd_onb3))
    app.add_handler(CommandHandler("offb3", cmd_offb3))
    app.add_handler(CommandHandler("onau", cmd_onau))
    app.add_handler(CommandHandler("offau", cmd_offau))
    app.add_handler(CommandHandler("onmss", cmd_onmss))
    app.add_handler(CommandHandler("offmss", cmd_offmss))
    app.add_handler(CommandHandler("onmpp2", cmd_onmpp2))
    app.add_handler(CommandHandler("offmpp2", cmd_offmpp2))

    # External gate handlers (b3, chk, mass)
    for handler in get_b3_handler():
        app.add_handler(handler)
    for handler in get_chk_handler():
        app.add_handler(handler)
    for handler in get_mass_handlers():
        app.add_handler(handler)

    # Callback queries
    app.add_handler(CallbackQueryHandler(callback_handler))

    def shutdown(sig, frame):
        release_instance_lock()
        raise SystemExit

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        logger.info("Starting bot polling...")
        app.run_polling(drop_pending_updates=True)
    finally:
        release_instance_lock()

if __name__ == "__main__":
    main()
