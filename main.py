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

from mst import get_bin_handler as get_bin_lookup_handler

from config import (
    BOT_TOKEN, OWNER_ID, VERSION, DEV_LINK,
    CHANNEL_USERNAME, CHANNEL_LINK, GROUP_LINK, SUPPORT_LINK,
    BOT_LINK, BOT_USERNAME, BOT_PHOTO_URL, BOT_PHOTO,
    API_TIMEOUT, REFERRAL_CREDITS, LOCK_FILE,
    GATE_URLS, GATE_SITES, PREMIUM_GATES, FORCE_CHANNELS,
    get_bin_info, kb_result,
    # ── Custom emoji helpers ──
    tg_emoji, get_plan_emoji_id, get_random_live_emoji,
    E_CARD, E_USER, E_TIME, E_DEV, E_PRO,
    E_LIVE, E_DECLINED, E_ERRORS, E_PROGRESS, E_GATE,
    PLAN_EMOJIS, PRO_EMOJI_ID,
)
from mass import get_mass_handlers
from b3 import get_b3_handler
from chk import get_chk_handler

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOGGING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger  = logging.getLogger(__name__)
MAX_MSG = 4000

BOT_LOCAL_PHOTO = "photo.jpg"

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
    ban_status   = f"{E_ERRORS} Banned" if ud.get("banned", False) else f"{E_LIVE} Active"

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
        f"{E_DEV} 𝗩𝗲𝗿𝘀𝗶𝗼𝗻 ➔ {VERSION}  |  <a href='{DEV_LINK}'>𝗕𝗮𝘁𝗺𝗮𝗻</a> {E_PRO}",
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
    ban_status    = f"{E_ERRORS} Banned" if ud.get("banned", False) else f"{E_LIVE} Active"
    approval_rate = f"{(approved / total_checks * 100):.1f}%" if total_checks > 0 else "N/A"

    if premium and expires > now:
        exp_date     = datetime.fromtimestamp(expires).strftime("%Y-%m-%d %H:%M")
        rem_d        = int((expires - now) / 86400)
        rem_h        = int(((expires - now) % 86400) / 3600)
        expire_line  = f"✰ <b>𝐄𝐱𝐩𝐢𝐫𝐞𝐬</b>   ➔ {exp_date}\n✰ <b>𝐓𝐢𝐦𝐞 𝐋𝐞𝐟𝐭</b>  ➔ {rem_d}d {rem_h}h"
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
        "━━━━━━━━━━━━━━━━━━━━",
        f"{E_DEV} 𝗩𝗲𝗿𝘀𝗶𝗼𝗻 ➔ {VERSION}  |  <a href='{DEV_LINK}'>𝗕𝗮𝘁𝗺𝗮𝗻</a> {E_PRO}",
    ]
    return "\n".join(lines)

def gate_info_text(gate_name: str, cmd: str, cost: int) -> str:
    return (
        f"━━━━━━━━━━━━━━━━━\n<b>{gate_name}</b>\n━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Cᴏsᴛ</b>    ➺ {cost} Credit(s) per check\n\n"
        f"<b>Uꜱᴀɢᴇ:</b>\n<code>/{cmd} cc|mm|yy|cvv</code>\n\n"
        f"<b>Exᴀᴍᴘʟᴇ:</b>\n<code>/{cmd} 4111111111111111|12|2026|123</code>\n\n"
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
# FORCE SUBSCRIBE
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
        f"⭅ <b>𝗝𝗢𝗜𝗡 𝗥𝗘𝗤𝗨𝗜𝗥𝗘𝗗</b> ⭆",
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

def kb_force_sub(not_joined: list) -> InlineKeyboardMarkup:
    rows = []
    for uname, link, label in not_joined:
        rows.append([InlineKeyboardButton(f"{label}  ➺  @{uname}", url=link)])
    rows.append([InlineKeyboardButton("✅  I Joined All — Verify Now", callback_data="check_sub")])
    return InlineKeyboardMarkup(rows)

async def send_force_join_photo(msg, not_joined: list):
    caption  = _force_join_text(not_joined)
    keyboard = kb_force_sub(not_joined)
    try:
        if os.path.exists(BOT_LOCAL_PHOTO):
            with open(BOT_LOCAL_PHOTO, "rb") as f:
                await msg.reply_photo(photo=f, caption=caption, parse_mode="HTML", reply_markup=keyboard)
            return
        if BOT_PHOTO_URL:
            await msg.reply_photo(photo=BOT_PHOTO_URL, caption=caption, parse_mode="HTML", reply_markup=keyboard)
            return
    except Exception:
        pass
    await msg.reply_text(caption, reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True)

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
                f"<b>{E_ERRORS} Bᴀɴɴᴇᴅ</b>\n━━━━━━━━━━━━━━━━━\n"
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
# CARD CHECK RESULT  (single gate)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def build_check_result(card_raw: str, gate_name: str, raw_response: str,
                       bin_data: dict, username: str, plan: str,
                       time_taken: str, is_approved: bool,
                       is_timeout: bool = False, is_error: bool = False) -> str:
    if is_timeout:
        status_emoji = E_ERRORS
        status_label = "Tɪᴍᴇᴏᴜᴛ"
    elif is_error:
        status_emoji = E_ERRORS
        status_label = "Eʀʀᴏʀ"
    elif is_approved:
        live_eid     = get_random_live_emoji()
        status_emoji = tg_emoji(live_eid, "✅")
        status_label = "Aᴘᴘʀᴏᴠᴇᴅ"
    else:
        status_emoji = E_DECLINED
        status_label = "Dᴇᴄʟɪɴᴇᴅ"

    plan_emoji_id = get_plan_emoji_id(plan)
    plan_emoji    = tg_emoji(plan_emoji_id, "⭐")
    plan_label    = get_styled_plan(plan)

    bin_txt = "N/A"
    if bin_data and not bin_data.get("error"):
        scheme  = str(bin_data.get("scheme",  "N/A")).upper()
        bank    = bin_data.get("bank",    "N/A")
        country = str(bin_data.get("country", "N/A")).upper()
        flag    = bin_data.get("country_emoji", "")
        bin_txt = f"{scheme} - {bank} - {flag} {country}".strip("- ")

    uname_display = f"{escape(username)} {plan_emoji} ({plan_label})"

    lines = [
        f"<b>{status_emoji} {status_label}</b>",
        "━━━━━━━━━━━━━━━━━",
        f"{E_CARD} <code>{card_raw}</code>",
        f"<b>Gᴀᴛᴇ</b> ➺ {gate_name}",
        f"<b>Rᴀᴡ</b>  ➺ {escape(raw_response)}",
        f"<b>Iɴꜰᴏ</b> ➺ {bin_txt}",
        "━━━━━━━━━━━━━━━━━",
        f"{E_TIME} <b>{time_taken}s</b>",
        f"{E_USER} {uname_display}",
        f"{E_DEV} Batman {E_PRO}",
        "━━━━━━━━━━━━━━━━━",
        f"📢 <a href='{CHANNEL_LINK}'>@Batcardchk</a>",
    ]
    return "\n".join(lines)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# KEYBOARDS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def kb_main(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("GATES"),          callback_data="mgates"),
         InlineKeyboardButton(B("PRICING"),        callback_data="mprice")],
        [InlineKeyboardButton(B("CONNECT") + " ↗", url=CHANNEL_LINK),
         InlineKeyboardButton("👤 " + B("PROFILE"), callback_data="mprofile")],
        [InlineKeyboardButton("📋 " + B("CMD"),    callback_data="cmd_pg_1")],
        [InlineKeyboardButton(B("SUPPORT") + " ↗", url=SUPPORT_LINK)],
    ])

def kb_back(cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 " + B("BACK"), callback_data=cb)]])

def kb_price() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("10$ - CORE"),  callback_data="pay10"),
         InlineKeyboardButton(B("15$ - ELITE"), callback_data="pay15"),
         InlineKeyboardButton(B("30$ - ROOT"),  callback_data="pay30")],
        [InlineKeyboardButton(B("SUPPORT") + " ➺", url=SUPPORT_LINK)],
        [InlineKeyboardButton("🔙 " + B("BACK"), callback_data="bmain")],
    ])

def kb_payment() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("SUPPORT") + " ➺", url=SUPPORT_LINK)],
        [InlineKeyboardButton("🔙 " + B("BACK"), callback_data="mprice")],
    ])

def kb_gate_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("AUTH"),    callback_data="mauth"),
         InlineKeyboardButton(B("CHARGE"),  callback_data="mcharge"),
         InlineKeyboardButton("👑 " + B("PREMIUM"), callback_data="mmass")],
        [InlineKeyboardButton("🔙 " + B("BACK"), callback_data="bmain")],
    ])

def kb_auth_gates() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("BRAINTREE"), callback_data="ib3")],
        [InlineKeyboardButton("🔙 " + B("BACK"), callback_data="mgates")],
    ])

def kb_charge_gates() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("STRIPE"),  callback_data="ichk"),
         InlineKeyboardButton(B("PAYPAL"),  callback_data="ipp")],
        [InlineKeyboardButton(B("SHOPIFY"), callback_data="ish"),
         InlineKeyboardButton(B("PAYU"),    callback_data="ipyu")],
        [InlineKeyboardButton("🔙 " + B("BACK"), callback_data="mgates")],
    ])

def kb_premium_gates() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("STRIPE AUTH")  + " 👑", callback_data="iau")],
        [InlineKeyboardButton(B("STRIPE MASS")  + " 👑", callback_data="imss")],
        [InlineKeyboardButton(B("PAYPAL MASS")  + " 👑", callback_data="impp2")],
        [InlineKeyboardButton("🔙 " + B("BACK"), callback_data="mgates")],
    ])

def kb_upgrade() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 " + B("BUY PREMIUM"), callback_data="mprice")],
        [InlineKeyboardButton(B("SUPPORT") + " ➺", url=SUPPORT_LINK)],
    ])

def kb_cooldown() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("Plans"), callback_data="mprice")],
    ])

def kb_fb_owner(key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approve", callback_data=f"fb_ok_{key}"),
        InlineKeyboardButton("❌ Decline", callback_data=f"fb_no_{key}"),
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
        f"<b>[+] {E_CARD} Charge Module</b>  (4)\n"
        f"<b>[+] {E_LIVE} Auth Module</b>    (1)\n"
        f"<b>[+] 👑 Mass Module</b>    (3)  <i>Premium</i>\n"
        f"<b>[+] 🛠 Tools</b>          (5)\n"
        f"<b>[+] {E_USER} Account</b>        (3)\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Use ▶ Next to explore each module</i>"
    ),
    2: (
        "⭅ <b>💳 𝗖𝗛𝗔𝗥𝗚𝗘 𝗠𝗢𝗗𝗨𝗟𝗘</b> ⭆\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>/chk</b>  ➔ Stripe Charge\n"
        "       Cost ➔ 1 Credit\n"
        "       Usage: <code>/chk cc|mm|yy|cvv</code>\n\n"
        "<b>/pp</b>   ➔ PayPal Charge\n"
        "       Cost ➔ 1 Credit\n"
        "       Usage: <code>/pp cc|mm|yy|cvv</code>\n\n"
        "<b>/sh</b>   ➔ Shopify Charge\n"
        "       Cost ➔ 1 Credit\n"
        "       Usage: <code>/sh cc|mm|yy|cvv</code>\n\n"
        "<b>/pyu</b>  ➔ PayU Charge\n"
        "       Cost ➔ 1 Credit\n"
        "       Usage: <code>/pyu cc|mm|yy|cvv</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Example: /chk 4111111111111111|12|2026|123</i>"
    ),
    3: (
        "⭅ <b>🔐 𝗔𝗨𝗧𝗛 𝗠𝗢𝗗𝗨𝗟𝗘</b> ⭆\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>/b3</b>   ➔ Braintree Auth\n"
        "       Cost ➔ 1 Credit\n"
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
        "<b>/au</b>   ➔ Stripe Auth Mass 👑\n"
        "       Cost ➔ Unlimited (Premium)\n"
        "       Usage: <code>/au cc|mm|yy|cvv</code>\n\n"
        "<b>/mss</b>  ➔ Stripe Mass Checker 👑\n"
        "       Cost ➔ Unlimited (Premium)\n"
        "       Usage: <code>/mss cc|mm|yy|cvv</code>\n\n"
        "<b>/mpp2</b> ➔ PayPal Mass Checker 👑\n"
        "       Cost ➔ Unlimited (Premium)\n"
        "       Usage: <code>/mpp2 cc|mm|yy|cvv</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Upgrade via /plan to unlock these gates</i>"
    ),
    5: (
        "⭅ <b>🛠 𝗧𝗢𝗢𝗟𝗦</b> ⭆\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>/bin</b>   ➔ BIN Lookup\n"
        "        Usage: <code>/bin 411111</code>\n\n"
        "<b>/ping</b>  ➔ Bot Speed Test\n"
        "        Usage: <code>/ping</code>\n\n"
        "<b>/rm</b>    ➔ Redeem Code / Key\n"
        "        Usage: <code>/rm CODE</code>\n\n"
        "<b>/fb</b>    ➔ Submit Feedback\n"
        "        Usage: <code>/fb</code> (reply to photo/video)\n\n"
        "<b>/refer</b> ➔ Refer & Earn\n"
        "        Usage: <code>/refer</code>\n"
        "━━━━━━━━━━━━━━━━━━━━"
    ),
    6: (
        "⭅ <b>👤 𝗔𝗖𝗖𝗢𝗨𝗡𝗧</b> ⭆\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>/start</b> ➔ Open Dashboard\n\n"
        "<b>/plan</b>  ➔ View Premium Plans\n\n"
        "<b>/refer</b> ➔ Referral Program\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>{E_PRO} How Credits Work</b>\n"
        "• Trial users start with 150 credits\n"
        "• Each gate check costs 1 credit\n"
        "• Earn credits by referring friends\n"
        "• Premium = Unlimited credits 👑\n"
        "━━━━━━━━━━━━━━━━━━━━"
    ),
}

def kb_cmd_nav(page: int) -> InlineKeyboardMarkup:
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("◀ " + B("PREV"), callback_data=f"cmd_pg_{page - 1}"))
    nav_row.append(InlineKeyboardButton(f"📄 {page}/{CMD_TOTAL_PAGES}", callback_data="cmd_pg_noop"))
    if page < CMD_TOTAL_PAGES:
        nav_row.append(InlineKeyboardButton(B("NEXT") + " ▶", callback_data=f"cmd_pg_{page + 1}"))
    return InlineKeyboardMarkup([
        nav_row,
        [InlineKeyboardButton("✖ " + B("CLOSE"), callback_data="bmain")],
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
                f"<b>{E_LIVE} Rᴇꜰᴇʀʀᴀʟ Bᴏɴᴜꜱ</b>\n━━━━━━━━━━━━━━━━━\n"
                f"Someone joined via your link!\n"
                f"<b>Cʀᴇᴅɪᴛꜱ Aᴅᴅᴇᴅ</b>    ➺ +{REFERRAL_CREDITS}\n"
                f"<b>Tᴏᴛᴀʟ Rᴇꜰᴇʀʀᴀʟꜱ</b> ➺ {referrer_ud['total_refs']}\n"
                "━━━━━━━━━━━━━━━━━"
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
            f"<b>{E_ERRORS} Mᴀɪɴᴛᴇɴᴀɴᴄᴇ</b>\nBot is under maintenance.", parse_mode="HTML"
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
            f"<b>{E_PRO} Pʀᴇᴍɪᴜᴍ Oɴʟʏ</b>\n━━━━━━━━━━━━━━━━━\nUse /plan to upgrade.",
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
            f"<b>Uꜱᴀɢᴇ:</b> <code>/{gate_key} cc|mm|yy|cvv</code>", parse_mode="HTML"
        )
        return

    if not premium:
        credits = ud.get("credits", 0)
        if credits <= 0:
            await update.message.reply_text(
                f"<b>{E_DECLINED} Nᴏ Cʀᴇᴅɪᴛꜱ</b>\n━━━━━━━━━━━━━━━━━\n"
                "You have <b>0 credits</b> remaining.\n\n"
                f"{E_PRO} Upgrade to <b>Premium</b> for unlimited checks.\n"
                "━━━━━━━━━━━━━━━━━",
                reply_markup=kb_upgrade(), parse_mode="HTML"
            )
            return

        remaining = get_cooldown_remaining(user.id, context)
        if remaining > 0:
            await update.message.reply_text(
                f"<b>{E_ERRORS} Cᴏᴏʟᴅᴏᴡɴ</b>\n━━━━━━━━━━━━━━━━━\n"
                f"Please wait <b>{remaining:.1f}s</b> before your next check.\n\n"
                f"{E_PRO} <b>Premium removes all cooldowns.</b>\n"
                "━━━━━━━━━━━━━━━━━",
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
        f"{E_PROGRESS} <b>Sᴄᴀɴɴɪɴɢ...</b>", parse_mode="HTML"
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

async def cmd_pp(u, c):  await process_gate(u, c, "pp",  "PayPal Charge")
async def cmd_sh(u, c):  await process_gate(u, c, "sh",  "Shopify Charge")
async def cmd_pyu(u, c): await process_gate(u, c, "pyu", "PayU Charge")

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

    plan_emoji   = tg_emoji(get_plan_emoji_id(plan), "⭐")
    exp_date     = datetime.fromtimestamp(expires_ts).strftime("%Y-%m-%d %H:%M")
    display_name = f"@{username}" if username else name
    styled       = get_styled_plan(plan)

    txt = (
        f"<b>{E_LIVE} Aᴄᴄᴇꜱꜱ Aᴄᴛɪᴠᴀᴛᴇᴅ</b>\n━━━━━━━━━━━━━━━━━\n"
        f"<b>Uꜱᴇʀ</b>     ➺ {display_name}\n"
        f"<b>Aᴄᴄᴇꜱꜱ</b>  ➺ {styled} {plan_emoji}\n"
        f"<b>Dᴀʏꜱ</b>    ➺ {days}\n"
        f"<b>Cʀᴇᴅɪᴛꜱ</b> ➺ Unlimited\n"
        f"<b>Exᴘɪʀᴇꜱ</b> ➺ {exp_date}\n"
        f"<b>Rᴇᴄᴇɪᴘᴛ</b> ➺ <code>{receipt}</code>\n"
        f"━━━━━━━━━━━━━━━━━\nSave this receipt ID.\n{E_DEV} Batman {E_PRO}"
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
        f"<b>{E_LIVE} Pʀᴇᴍɪᴜᴍ Gʀᴀɴᴛᴇᴅ</b>\n━━━━━━━━━━━━━━━━━\n"
        f"<b>Uꜱᴇʀ</b>    ➺ {display_name} (@{display_uname or 'N/A'})\n"
        f"<b>Aᴄᴄᴇꜱꜱ</b> ➺ {get_styled_plan(plan)} {plan_emoji}\n"
        f"<b>Dᴀʏꜱ</b>   ➺ {days}\n"
        "━━━━━━━━━━━━━━━━━",
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
            "Uꜱᴀɢᴇ:\n/gen code <value>\n/gen key <plan> <days>"
        )
        return
    kind = context.args[0].lower()
    if kind == "code":
        try:    value = int(context.args[1])
        except: await update.message.reply_text("Value must be a number."); return
        code = gen_code()
        context.bot_data.setdefault("codes", {})[code] = {"value": value, "used": False}
        await update.message.reply_text(
            f"<b>{E_LIVE} Code Generated</b>\n━━━━━━━━━━━━━━━━━\n"
            f"<b>Code</b>   ➺ <code>{code}</code>\n"
            f"<b>Value</b>  ➺ {value} credits\n"
            "━━━━━━━━━━━━━━━━━",
            parse_mode="HTML"
        )
    elif kind == "key":
        if len(context.args) < 3:
            await update.message.reply_text("Uꜱᴀɢᴇ: /gen key <PLAN> <DAYS>"); return
        plan_arg = context.args[1].upper()
        try:    days = int(context.args[2])
        except: await update.message.reply_text("Days must be a number."); return
        key = gen_code(12)
        context.bot_data.setdefault("keys", {})[key] = {"plan": plan_arg, "days": days, "used": False}
        plan_emoji = tg_emoji(get_plan_emoji_id(plan_arg), "⭐")
        await update.message.reply_text(
            f"<b>{E_LIVE} Key Generated</b>\n━━━━━━━━━━━━━━━━━\n"
            f"<b>Key</b>   ➺ <code>{key}</code>\n"
            f"<b>Plan</b>  ➺ {get_styled_plan(plan_arg)} {plan_emoji}\n"
            f"<b>Days</b>  ➺ {days}\n"
            "━━━━━━━━━━━━━━━━━",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text("Unknown type. Use: code or key")

async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if len(context.args) < 3:
        await update.message.reply_text(
            f"<b>{E_DEV} Gʀᴀɴᴛ Pʀᴇᴍɪᴜᴍ</b>\n━━━━━━━━━━━━━━━━━\n"
            f"<b>Uꜱᴀɢᴇ:</b>\n"
            f"<code>/add @username PLAN DAYS</code>\n"
            f"<code>/add UserID PLAN DAYS</code>\n\n"
            f"<b>Pʟᴀɴs:</b>  CORE | ELITE | ROOT\n\n"
            f"<b>Exᴀᴍᴘʟᴇ:</b>\n"
            f"<code>/add @john ELITE 30</code>\n"
            f"<code>/add 123456789 ROOT 7</code>\n"
            f"━━━━━━━━━━━━━━━━━",
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
        await update.message.reply_text("Uꜱᴀɢᴇ: /rem @user|ID or reply → /rem"); return
    ud = get_user_data(target, context)
    ud["plan"] = "TRIAL"; ud["expires"] = 0
    await update.message.reply_text(
        f"<b>{E_DECLINED} Premium removed for <code>{target}</code>.</b>", parse_mode="HTML"
    )


async def cmd_resub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove a user's active premium. Aliases: /resub /rsub"""
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
                f"{E_ERRORS} <b>User not found:</b> <code>{raw}</code>\n"
                f"Try: <code>/resub @username</code> or <code>/resub UserID</code>",
                parse_mode="HTML"
            )
            return
    else:
        await update.message.reply_text(
            f"<b>{E_DEV} Rᴇᴍᴏᴠᴇ Pʀᴇᴍɪᴜᴍ</b>\n━━━━━━━━━━━━━━━━━\n"
            f"<b>Uꜱᴀɢᴇ:</b>\n"
            f"<code>/resub @username</code>\n"
            f"<code>/resub UserID</code>\n"
            f"Or reply to a user's message → <code>/resub</code>\n\n"
            f"<b>Aʟɪᴀꜱ:</b> /rsub works too\n"
            f"━━━━━━━━━━━━━━━━━",
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
        f"<b>{E_DECLINED} Pʀᴇᴍɪᴜᴍ Rᴇᴍᴏᴠᴇᴅ</b>\n━━━━━━━━━━━━━━━━━\n"
        f"<b>Uꜱᴇʀ</b>      ➺ {target_name} ({uname_d})\n"
        f"<b>ID</b>        ➺ <code>{target_id}</code>\n"
        f"<b>Pʟᴀɴ Wᴀꜱ</b> ➺ {old_plan_str}\n"
        f"<b>Dᴀʏꜱ Left</b> ➺ {rem_was}d (cancelled)\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"<b>Sᴛᴀᴛᴜꜱ</b>    ➺ Rᴇsᴇᴛ ᴛᴏ Tʀɪᴀʟ",
        parse_mode="HTML"
    )

    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=(
                f"<b>{E_ERRORS} Sᴜʙsᴄʀɪᴘᴛɪᴏɴ Cᴀɴᴄᴇʟʟᴇᴅ</b>\n━━━━━━━━━━━━━━━━━\n"
                f"Your <b>{old_plan_str}</b> premium has been removed by the admin.\n"
                f"Use /plan to purchase a new subscription.\n"
                f"━━━━━━━━━━━━━━━━━"
            ),
            parse_mode="HTML"
        )
    except Exception:
        pass

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args:
        await update.message.reply_text("Uꜱᴀɢᴇ: /broadcast <message>"); return
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
        f"<b>{E_LIVE} Broadcast Done</b>\n━━━━━━━━━━━━━━━━━\n"
        f"<b>Sent</b>   ➺ {sent}\n<b>Failed</b> ➺ {failed}\n"
        "━━━━━━━━━━━━━━━━━",
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
        await update.message.reply_text("Uꜱᴀɢᴇ: /ban @user|ID or reply → /ban"); return
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
                f"<b>{E_ERRORS} Bᴀɴɴᴇᴅ</b>\n━━━━━━━━━━━━━━━━━\n"
                "You have been banned from using this bot.\n"
                "Contact support if you think this is a mistake.\n"
                "━━━━━━━━━━━━━━━━━"
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
        await update.message.reply_text("Uꜱᴀɢᴇ: /unban @user|ID or reply → /unban"); return
    get_user_data(uid, context)["banned"] = False
    await update.message.reply_text(
        f"<b>{E_LIVE} User <code>{uid}</code> has been unbanned.</b>", parse_mode="HTML"
    )
    try:
        await context.bot.send_message(
            chat_id=uid,
            text=(
                f"<b>{E_LIVE} Uɴʙᴀɴɴᴇᴅ</b>\n━━━━━━━━━━━━━━━━━\n"
                "You can now use the bot again.\n━━━━━━━━━━━━━━━━━"
            ),
            parse_mode="HTML"
        )
    except Exception: pass

async def cmd_allcm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    await update.message.reply_text(
        "<b>🦇 ALL COMMANDS</b>\n━━━━━━━━━━━━━━━━━\n\n"

        f"<b>{E_DEV} OWNER ONLY:</b>\n"
        "/allcm ➺ Show all commands\n"
        "/allsub ➺ All live premium users\n"
        "/info [user] ➺ Full user info\n"
        "/gen code &lt;val&gt; ➺ Gen credit code\n"
        "/gen key &lt;plan&gt; &lt;days&gt; ➺ Gen premium key\n"
        "/add @user PLAN DAYS ➺ Grant premium\n"
        "/resub @user|ID ➺ Remove active premium\n"
        "/rsub @user|ID ➺ Same as /resub\n"
        "/rem &lt;user&gt; ➺ Remove premium (legacy)\n"
        "/ban &lt;user&gt; ➺ Ban user\n"
        "/unban &lt;user&gt; ➺ Unban user\n"
        "/broadcast &lt;msg&gt; ➺ Broadcast\n"
        "/maintenance on|off ➺ Maintenance mode\n"
        "/onchk /offchk ➺ Toggle Stripe gate\n"
        "/onpp /offpp ➺ Toggle PayPal gate\n"
        "/onsh /offsh ➺ Toggle Shopify gate\n"
        "/onpyu /offpyu ➺ Toggle PayU gate\n"
        "/onb3 /offb3 ➺ Toggle Braintree gate\n"
        "/onau /offau ➺ Toggle Stripe Auth\n"
        "/onmss /offmss ➺ Toggle Stripe Mass\n"
        "/onmpp2 /offmpp2 ➺ Toggle PayPal Mass\n"
        "━━━━━━━━━━━━━━━━━\n\n"

        f"<b>{E_PRO} PREMIUM USER COMMANDS:</b>\n"
        "/chk ➺ Stripe Charge\n"
        "/b3 ➺ Braintree Charge\n"
        "/pp ➺ PayPal Charge\n"
        "/sh ➺ Shopify Charge\n"
        "/pyu ➺ PayU Charge\n"
        "/au ➺ Stripe Auth Mass\n"
        "/mss ➺ Stripe Mass Check\n"
        "/mpp2 ➺ PayPal Mass Check\n"
        "━━━━━━━━━━━━━━━━━\n\n"

        f"<b>{E_LIVE} TRIAL / FREE USER COMMANDS:</b>\n"
        "/start ➺ Dashboard\n"
        "/plan ➺ View premium plans\n"
        "/sub ➺ My subscription info\n"
        "/bin ➺ BIN lookup\n"
        "/refer ➺ Referral link\n"
        "/rm ➺ Redeem code or key\n"
        "/ping ➺ Bot speed test\n"
        "/fb ➺ Send feedback\n"
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
    lines = [f"<b>{E_PRO} Lɪᴠᴇ Pʀᴇᴍɪᴜᴍ Uꜱᴇʀs ➺ {len(premium)}</b>\n━━━━━━━━━━━━━━━━━"]
    for idx, (uid_s, ud) in enumerate(premium, 1):
        uname_d = f"@{ud.get('username','')}" if ud.get("username") else ud.get("name", "?")
        plan    = ud.get("plan", "TRIAL").upper()
        expires = ud.get("expires", 0)
        rem_d   = int((expires - now) // 86400)
        rem_h   = int(((expires - now) % 86400) // 3600)
        lines.append(
            f"<b>{idx}.</b> <code>{uid_s}</code> | {uname_d}\n"
            f"    ➺ {get_styled_plan(plan)} | <b>{rem_d}d {rem_h}h left</b>"
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
            f"<b>{E_USER} All Users</b>\n━━━━━━━━━━━━━━━━━\n"
            f"<b>Total</b>   ➺ {total}\n"
            f"<b>Premium</b> ➺ {premium_count}\n"
            f"<b>Trial</b>   ➺ {trial_count}\n"
            f"<b>Banned</b>  ➺ {banned_count}\n"
            "━━━━━━━━━━━━━━━━━\n"
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
            "Uꜱᴀɢᴇ:\n/info — all users\n/info @username\n/info 123456789\nOr reply → /info"
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

    plan_emoji = tg_emoji(get_plan_emoji_id(raw_plan), "⭐")
    full_name  = f"{target_name} {target_last_name}".strip()
    uname_d    = f"@{target_username}" if target_username else "None"
    total_refs, total_checks = udata.get("total_refs", 0), udata.get("total_checks", 0)
    approved_checks = udata.get("approved_checks", 0)
    declined_checks = udata.get("declined_checks", 0)
    approval_rate   = f"{(approved_checks / total_checks * 100):.1f}%" if total_checks > 0 else "N/A"

    ban_icon = f"{E_ERRORS} Banned" if banned else f"{E_LIVE} Active"

    txt = (
        f"<b>{E_USER} Uꜱᴇʀ Iɴꜰᴏ</b>\n━━━━━━━━━━━━━━━━━\n"
        f"<b>Nᴀᴍᴇ</b>       ➺ {full_name}\n"
        f"<b>Uꜱᴇʀɴᴀᴍᴇ</b>  ➺ {uname_d}\n"
        f"<b>ID</b>         ➺ <code>{target_id}</code>\n"
        f"<b>Sᴛᴀᴛᴜꜱ</b>    ➺ {ban_icon}\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"<b>Pʟᴀɴ</b>       ➺ {get_styled_plan(raw_plan)} {plan_emoji}\n"
        f"<b>Cʀᴇᴅɪᴛꜱ</b>   ➺ {credits_d}\n"
    )
    if premium and expires > now:
        rem = expires - now
        txt += (
            f"<b>Exᴘɪʀᴇꜱ</b>   ➺ {datetime.fromtimestamp(expires).strftime('%Y-%m-%d %H:%M')}\n"
            f"<b>Rᴇᴍᴀɪɴɪɴɢ</b> ➺ {int(rem // 86400)}d {int((rem % 86400) // 3600)}h\n"
        )
    last_receipt = udata.get("last_receipt")
    if last_receipt: txt += f"<b>Rᴇᴄᴇɪᴘᴛ</b>   ➺ <code>{last_receipt}</code>\n"
    txt += (
        "━━━━━━━━━━━━━━━━━\n"
        f"<b>Jᴏɪɴᴇᴅ</b>      ➺ {udata.get('joined', 'N/A')}\n"
        f"<b>Lᴀsᴛ Aᴄᴛɪᴠᴇ</b> ➺ {udata.get('last_active', 'N/A')}\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"<b>Tᴏᴛᴀʟ Cʜᴇᴄᴋꜱ</b> ➺ {total_checks}\n"
        f"<b>Aᴘᴘʀᴏᴠᴇᴅ</b>     ➺ {approved_checks}\n"
        f"<b>Dᴇᴄʟɪɴᴇᴅ</b>     ➺ {declined_checks}\n"
        f"<b>Rᴀᴛᴇ</b>         ➺ {approval_rate}\n"
        f"<b>Lᴀsᴛ Gᴀᴛᴇ</b>   ➺ {udata.get('last_gate', 'N/A')}\n"
        f"<b>Lᴀsᴛ BIN</b>    ➺ <code>{udata.get('last_card', 'N/A')}</code>\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"<b>Rᴇꜰᴇʀʀᴀʟꜱ</b>   ➺ {total_refs}\n"
        f"<b>Cᴏᴅᴇꜱ</b>        ➺ {udata.get('codes_redeemed', 0)} redeemed\n"
        f"<b>Kᴇʏꜱ</b>         ➺ {udata.get('keys_redeemed', 0)} redeemed\n"
        "━━━━━━━━━━━━━━━━━"
    )
    action_kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"{E_ERRORS} Ban" if not banned else f"{E_LIVE} Unban",
                callback_data=f"owner_ban_{target_id}" if not banned else f"owner_unban_{target_id}"
            ),
            InlineKeyboardButton(f"{E_DECLINED} Remove Premium", callback_data=f"owner_resub_{target_id}"),
        ],
        [InlineKeyboardButton("🔙 Back", callback_data="owner_info_back")],
    ])
    await update.message.reply_text(txt, parse_mode="HTML", reply_markup=action_kb)

async def cmd_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args:
        state = context.bot_data.get("maintenance", False)
        await update.message.reply_text(
            f"Maintenance is currently: {'ON' if state else 'OFF'}\n"
            "Use: /maintenance on|off"
        )
        return
    arg = context.args[0].lower()
    if arg in ("on", "1", "true"):
        context.bot_data["maintenance"] = True
        await update.message.reply_text(
            f"<b>{E_ERRORS} Maintenance mode ON.</b> Users cannot use commands.", parse_mode="HTML"
        )
    elif arg in ("off", "0", "false"):
        context.bot_data["maintenance"] = False
        await update.message.reply_text(
            f"<b>{E_LIVE} Maintenance mode OFF.</b> Bot is live.", parse_mode="HTML"
        )
    else:
        await update.message.reply_text("Use: /maintenance on|off")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# USER COMMANDS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user     = update.effective_user
    ud       = get_user_data(user.id, context)
    now      = time.time()
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
            f"<b>Exᴘɪʀᴇꜱ</b>    ➺ {exp_str}\n"
            f"<b>Rᴇᴍᴀɪɴɪɴɢ</b>  ➺ <b>{rem_d} days {rem_h} hours</b>"
        )
    else:
        expire_line = "<b>Exᴘɪʀᴇꜱ</b>    ➺ Trial (no expiry)"

    joined = ud.get("joined", "N/A")
    txt = (
        f"<b>{E_USER} Mʏ Sᴜʙsᴄʀɪᴘᴛɪᴏɴ</b>\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"<b>Nᴀᴍᴇ</b>      ➺ {escape(uname)}\n"
        f"<b>ID</b>        ➺ <code>{user.id}</code>\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"<b>Pʟᴀɴ</b>      ➺ {get_styled_plan(raw_plan)} {plan_emoji}\n"
        f"<b>Cʀᴇᴅɪᴛꜱ</b>  ➺ {credits_d}\n"
        f"{expire_line}\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"<b>Jᴏɪɴᴇᴅ</b>    ➺ {joined}\n"
        f"━━━━━━━━━━━━━━━━━"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 Upgrade Plan", callback_data="mprice")],
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
            f"<b>{E_ERRORS} Bᴀɴɴᴇᴅ</b>\n━━━━━━━━━━━━━━━━━\n"
            "You have been banned from using this bot.\n━━━━━━━━━━━━━━━━━",
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
    msg = await update.message.reply_text(f"{E_PROGRESS} <b>Pɪɴɢɪɴɢ...</b>", parse_mode="HTML")
    ms  = int((time.time() - t) * 1000)
    await msg.edit_text(
        f"<b>{E_LIVE} Pᴏɴɢ</b>\n━━━━━━━━━━━━━━━━━\n"
        f"{E_TIME} <b>{ms}ms</b>\n━━━━━━━━━━━━━━━━━",
        parse_mode="HTML"
    )

async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_not_banned(update, context): return
    if not await require_membership(update, context): return

    core_e  = tg_emoji(PLAN_EMOJIS["CORE"],  "⭐")
    elite_e = tg_emoji(PLAN_EMOJIS["ELITE"], "⭐")
    root_e  = tg_emoji(PLAN_EMOJIS["ROOT"],  "⭐")

    txt = (
        f"<b>{core_e} Cᴏʀᴇ Plan</b>\n━━━━━━━━━━━━━━━━━\n"
        "<b>Dᴀʏꜱ</b>     ➺ 7\n"
        "<b>Cʀᴇᴅɪᴛꜱ</b> ➺ Unlimited\n"
        "<b>Pʀɪᴄᴇ</b>   ➺ 10$\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"<b>{elite_e} Eʟɪᴛᴇ Plan</b>\n━━━━━━━━━━━━━━━━━\n"
        "<b>Dᴀʏꜱ</b>     ➺ 15\n"
        "<b>Cʀᴇᴅɪᴛꜱ</b> ➺ Unlimited\n"
        "<b>Pʀɪᴄᴇ</b>   ➺ 15$\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"<b>{root_e} Rᴏᴏᴛ Plan</b>\n━━━━━━━━━━━━━━━━━\n"
        "<b>Dᴀʏꜱ</b>     ➺ 30\n"
        "<b>Cʀᴇᴅɪᴛꜱ</b> ➺ Unlimited\n"
        "<b>Pʀɪᴄᴇ</b>   ➺ 30$\n"
        "━━━━━━━━━━━━━━━━━"
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
        f"<b>{E_USER} Rᴇꜰᴇʀʀᴀʟ</b>\n━━━━━━━━━━━━━━━━━\n"
        f"<b>Lɪɴᴋ</b>    ➺ <code>{link}</code>\n━━━━━━━━━━━━━━━━━\n"
        f"<b>Rᴇꜰᴇʀʀᴀʟꜱ</b> ➺ {total_refs}\n"
        f"<b>Eᴀʀɴᴇᴅ</b>   ➺ {total_refs * REFERRAL_CREDITS} credits\n"
        f"<b>Pᴇʀ Rᴇꜰ</b>  ➺ +{REFERRAL_CREDITS} credits\n━━━━━━━━━━━━━━━━━\n"
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
        await update.message.reply_text("Uꜱᴀɢᴇ: /rm <code>CODE</code>", parse_mode="HTML")
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
            f"<b>{E_LIVE} Code Redeemed</b>\n━━━━━━━━━━━━━━━━━\n"
            f"<b>Credits Added</b> ➺ +{codes[code]['value']}\n"
            f"<b>Balance</b>       ➺ {ud['credits']}\n"
            "━━━━━━━━━━━━━━━━━",
            parse_mode="HTML"
        )
    elif code in keys and not keys[code]["used"]:
        keys[code]["used"] = True
        p, d = keys[code]["plan"], keys[code]["days"]
        ud["keys_redeemed"] = ud.get("keys_redeemed", 0) + 1
        receipt = await send_activation_msg(uid, p, d, context)
        plan_emoji = tg_emoji(get_plan_emoji_id(p), "⭐")
        await update.message.reply_text(
            f"<b>{E_LIVE} Key Redeemed</b>\n━━━━━━━━━━━━━━━━━\n"
            f"<b>Access</b>  ➺ {get_styled_plan(p)} {plan_emoji}\n"
            f"<b>Days</b>    ➺ {d}\n"
            f"<b>Receipt</b> ➺ <code>{receipt}</code>\n"
            "━━━━━━━━━━━━━━━━━",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text(
            f"<b>{E_ERRORS} Invalid or already used code.</b>", parse_mode="HTML"
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
            f"<b>{E_LIVE} Fᴇᴇᴅʙᴀᴄᴋ Sᴜʙᴍɪᴛᴛᴇᴅ</b>\n━━━━━━━━━━━━━━━━━\n"
            "Your feedback is under review.\n━━━━━━━━━━━━━━━━━",
            parse_mode="HTML"
        )

        owner_caption = (
            f"<b>{E_DEV} Nᴇᴡ Fᴇᴇᴅʙᴀᴄᴋ</b>\n━━━━━━━━━━━━━━━━━\n"
            f"<b>Uꜱᴇʀ</b> ➺ {uname}\n<b>ID</b>   ➺ {user.id}\n"
            f"<b>Dᴀᴛᴇ</b> ➺ {submitted}\n<b>Tʏᴘᴇ</b> ➺ {file_type.capitalize()}\n"
        )
        if user_note: owner_caption += f"<b>Nᴏᴛᴇ</b> ➺ {user_note[:200]}\n"
        owner_caption += "━━━━━━━━━━━━━━━━━\nApprove to post to channel?"

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
        f"<b>📸 Fᴇᴇᴅʙᴀᴄᴋ</b>\n━━━━━━━━━━━━━━━━━\n"
        "Reply to a photo/video with <code>/fb</code>\n"
        "OR send photo/video with <code>/fb</code> as caption.\n"
        "━━━━━━━━━━━━━━━━━",
        parse_mode="HTML"
    )

async def _fb_approve(query, context: ContextTypes.DEFAULT_TYPE, key: str):
    fb = context.bot_data.get("fb_pending", {}).get(key)
    if not fb: await query.answer("Already handled.", show_alert=True); return
    uname, uid, submitted = fb["username"], fb["user_id"], fb["date"]
    file_id, file_type, user_note = fb["file_id"], fb["file_type"], fb.get("note", "")
    channel_caption = "━━━━━━━━━━━━━━━━━\n"
    if user_note: channel_caption += f"{user_note}\n━━━━━━━━━━━━━━━━━\n"
    channel_caption += (
        f"<b>Uꜱᴇʀ</b> ➺ {uname}\n<b>ID</b>   ➺ {uid}\n"
        f"<b>Dᴀᴛᴇ</b> ➺ {submitted}\n━━━━━━━━━━━━━━━━━"
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
            caption=f"<b>{E_LIVE} Fᴇᴇᴅʙᴀᴄᴋ {'Posted ✅' if posted else 'Post Failed ⚠️'}</b>\n━━━━━━━━━━━━━━━━━",
            reply_markup=None, parse_mode="HTML"
        )
    except Exception: pass
    try:
        await context.bot.send_message(
            chat_id=uid,
            text=(
                f"<b>{E_LIVE} Fᴇᴇᴅʙᴀᴄᴋ Aᴄᴄᴇᴘᴛᴇᴅ</b>\n━━━━━━━━━━━━━━━━━\n"
                f"Posted to channel!\n📢 {CHANNEL_LINK}\n━━━━━━━━━━━━━━━━━"
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
            caption=f"<b>{E_DECLINED} Fᴇᴇᴅʙᴀᴄᴋ Dᴇᴄʟɪɴᴇᴅ</b>\n━━━━━━━━━━━━━━━━━",
            reply_markup=None, parse_mode="HTML"
        )
    except Exception: pass
    try:
        await context.bot.send_message(
            chat_id=uid,
            text=f"<b>{E_DECLINED} Fᴇᴇᴅʙᴀᴄᴋ Dᴇᴄʟɪɴᴇᴅ</b>\n━━━━━━━━━━━━━━━━━",
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

    await query.answer()

    # ── Force-sub verify ──
    if data == "check_sub":
        not_joined = await check_force_sub(user.id, context)
        if not_joined:
            await query.answer(
                f"You still need to join {len(not_joined)} channel(s)!", show_alert=True
            )
            return
        _force_sub_cache[user.id] = (True, time.time())
        await query.message.delete()
        await context.bot.send_message(
            chat_id=user.id,
            text=f"<b>{E_LIVE} Verified! Use /start.</b>",
            parse_mode="HTML"
        )
        return

    # ── Navigation ──
    if data == "bmain":
        await query.message.edit_text(
            ui_profile(user, context), parse_mode="HTML",
            reply_markup=kb_main(user.id), disable_web_page_preview=True
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
            f"<b>{E_GATE} Gᴀᴛᴇꜱ</b>\n━━━━━━━━━━━━━━━━━\nChoose a gate category:",
            parse_mode="HTML", reply_markup=kb_gate_main()
        )
        return
    if data == "mauth":
        await query.message.edit_text(
            f"<b>{E_LIVE} Aᴜᴛʜ Gᴀᴛᴇꜱ</b>\n━━━━━━━━━━━━━━━━━\n"
            "Auth gates verify without charging.\n━━━━━━━━━━━━━━━━━",
            parse_mode="HTML", reply_markup=kb_auth_gates()
        )
        return
    if data == "mcharge":
        await query.message.edit_text(
            f"<b>{E_CARD} Cʜᴀʀɢᴇ Gᴀᴛᴇꜱ</b>\n━━━━━━━━━━━━━━━━━\n"
            "Charge gates perform a real $0 charge.\n━━━━━━━━━━━━━━━━━",
            parse_mode="HTML", reply_markup=kb_charge_gates()
        )
        return
    if data == "mmass":
        ud = get_user_data(user.id, context)
        if not is_user_premium(ud):
            await query.message.edit_text(
                f"<b>{E_PRO} Pʀᴇᴍɪᴜᴍ Oɴʟʏ</b>\n━━━━━━━━━━━━━━━━━\n"
                "Mass checkers require a premium plan.\n━━━━━━━━━━━━━━━━━",
                parse_mode="HTML", reply_markup=kb_upgrade()
            )
            return
        await query.message.edit_text(
            f"<b>👑 Mᴀꜱꜱ Gᴀᴛᴇꜱ</b>\n━━━━━━━━━━━━━━━━━\n"
            "Premium mass checkers:\n━━━━━━━━━━━━━━━━━",
            parse_mode="HTML", reply_markup=kb_premium_gates()
        )
        return
    if data == "mprice":
        core_e  = tg_emoji(PLAN_EMOJIS["CORE"],  "⭐")
        elite_e = tg_emoji(PLAN_EMOJIS["ELITE"], "⭐")
        root_e  = tg_emoji(PLAN_EMOJIS["ROOT"],  "⭐")
        txt = (
            f"<b>{core_e} Cᴏʀᴇ</b> ➺ 7 days | 10$\n"
            f"<b>{elite_e} Eʟɪᴛᴇ</b> ➺ 15 days | 15$\n"
            f"<b>{root_e} Rᴏᴏᴛ</b> ➺ 30 days | 30$\n"
            "━━━━━━━━━━━━━━━━━\nAll plans: Unlimited credits"
        )
        await query.message.edit_text(txt, parse_mode="HTML", reply_markup=kb_price())
        return

    # ── Gate info callbacks ──
    gate_info_map = {
        "ib3":   ("Bʀᴀɪɴᴛʀᴇᴇ Auth 0$", "b3",  1),
        "ichk":  ("Sᴛʀɪᴘᴇ Charge 0$",   "chk", 1),
        "ipp":   ("Pᴀʏᴘᴀʟ Charge 0$",   "pp",  1),
        "ish":   ("Sʜᴏᴘɪꜰʏ Charge 0$",  "sh",  1),
        "ipyu":  ("Pᴀʏᴜ Charge 0$",      "pyu", 1),
        "iau":   ("Sᴛʀɪᴘᴇ Auth 0$",      "au",  0),
        "imss":  ("Sᴛʀɪᴘᴇ Mass",         "mss", 0),
        "impp2": ("Pᴀʏᴘᴀʟ Mass",         "mpp2",0),
    }
    if data in gate_info_map:
        gn, cmd, cost = gate_info_map[data]
        await query.message.edit_text(
            gate_info_text(gn, cmd, cost),
            parse_mode="HTML",
            reply_markup=kb_back("mgates")
        )
        return

    # ── Payment info ──
    pay_map = {
        "pay10": ("Cᴏʀᴇ",  10, 7,  "CORE"),
        "pay15": ("Eʟɪᴛᴇ", 15, 15, "ELITE"),
        "pay30": ("Rᴏᴏᴛ",  30, 30, "ROOT"),
    }
    if data in pay_map:
        plan_n, price, days, plan_key = pay_map[data]
        plan_emoji = tg_emoji(get_plan_emoji_id(plan_key), "⭐")
        await query.message.edit_text(
            f"<b>{plan_emoji} {plan_n} Plan</b>\n━━━━━━━━━━━━━━━━━\n"
            f"<b>Price</b>  ➺ ${price}\n"
            f"<b>Days</b>   ➺ {days}\n"
            f"<b>Credits</b> ➺ Unlimited\n"
            "━━━━━━━━━━━━━━━━━\n"
            "Contact support to purchase:",
            parse_mode="HTML", reply_markup=kb_payment()
        )
        return

    # ── CMD pagination ──
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

    # ── Owner inline actions ──
    if user.id == OWNER_ID:
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
        logger.critical("CONFLICT: Another bot instance is running! Shutting down.")
        os.kill(os.getpid(), signal.SIGTERM)
        return
    if isinstance(err, (NetworkError, Forbidden)):
        logger.warning(f"Network/Forbidden error: {err}")
        return
    logger.error(f"Unhandled exception: {err}", exc_info=err)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def main():
    if not acquire_instance_lock():
        logger.critical("Another instance is already running. Exiting.")
        return

    try:
        app = Application.builder().token(BOT_TOKEN).build()

        # ── User commands ──
        app.add_handler(CommandHandler("start",   cmd_start))
        app.add_handler(CommandHandler("ping",    cmd_ping))
        app.add_handler(CommandHandler("plan",    cmd_plan))
        app.add_handler(CommandHandler("sub",     cmd_sub))
        app.add_handler(CommandHandler("refer",   cmd_refer))
        app.add_handler(CommandHandler("rm",      cmd_rm))
        app.add_handler(get_bin_lookup_handler())
        app.add_handler(CommandHandler("fb",      cmd_fb))
        app.add_handler(CommandHandler("pp",      cmd_pp))
        app.add_handler(CommandHandler("sh",      cmd_sh))
        app.add_handler(CommandHandler("pyu",     cmd_pyu))
        app.add_handler(get_b3_handler())
        app.add_handler(get_chk_handler())
        for h in get_mass_handlers():
            app.add_handler(h)

        # ── Owner commands ──
        app.add_handler(CommandHandler("gen",         cmd_gen))
        app.add_handler(CommandHandler("add",         cmd_add))
        app.add_handler(CommandHandler("rem",         cmd_rem))
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
        app.add_handler(CommandHandler("onsh",    cmd_onsh))
        app.add_handler(CommandHandler("offsh",   cmd_offsh))
        app.add_handler(CommandHandler("onpyu",   cmd_onpyu))
        app.add_handler(CommandHandler("offpyu",  cmd_offpyu))
        app.add_handler(CommandHandler("onb3",    cmd_onb3))
        app.add_handler(CommandHandler("offb3",   cmd_offb3))
        app.add_handler(CommandHandler("onau",    cmd_onau))
        app.add_handler(CommandHandler("offau",   cmd_offau))
        app.add_handler(CommandHandler("onmss",   cmd_onmss))
        app.add_handler(CommandHandler("offmss",  cmd_offmss))
        app.add_handler(CommandHandler("onmpp2",  cmd_onmpp2))
        app.add_handler(CommandHandler("offmpp2", cmd_offmpp2))

        # ── Callbacks ──
        app.add_handler(CallbackQueryHandler(callback_handler))
        app.add_error_handler(error_handler)

        logger.info(f"Batman Bot {VERSION} starting...")
        app.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )
    finally:
        release_instance_lock()

if __name__ == "__main__":
    main()
