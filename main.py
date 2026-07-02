import logging
import time
import string
import random
import asyncio
import signal
import os
import fcntl
from typing import Optional
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes,
)
from telegram.error import Conflict, BadRequest, NetworkError

import aiohttp as _aiohttp

from config import (
    BOT_TOKEN, OWNER_ID, VERSION, DEV_LINK,
    CHANNEL_USERNAME, CHANNEL_LINK, GROUP_LINK, SUPPORT_LINK,
    BOT_LINK, BOT_USERNAME, BOT_PHOTO_URL, BOT_PHOTO,
    API_TIMEOUT, REFERRAL_CREDITS, LOCK_FILE,
    GATE_URLS, GATE_SITES, PREMIUM_GATES, FORCE_CHANNELS,
    get_bin_info,
)
from mass import get_mass_handlers   # /au  /mss  /mpp2  + result buttons

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOGGING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger  = logging.getLogger(__name__)
MAX_MSG = 4000

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
# PLAN HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_styled_plan(raw_plan: str) -> str:
    p = raw_plan.upper()
    if p == "CORE":  return "𝗖𝗼𝗿𝗲"
    if p == "ELITE": return "𝗘𝗹𝗶𝘁𝗲"
    if p == "ROOT":  return "𝗥𝗼𝗼𝘁"
    return "𝗧𝗿𝗶𝗮𝗹"

def get_plan_icon(raw_plan: str) -> str:
    p = raw_plan.upper()
    if p in ("CORE", "ELITE", "ROOT"): return "👑"
    return "🆓"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# USER DATA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DEFAULT_CREDITS = 150

def get_user_data(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> dict:
    uid = str(user_id)
    if "user_data" not in context.bot_data:
        context.bot_data["user_data"] = {}
    if uid not in context.bot_data["user_data"]:
        context.bot_data["user_data"][uid] = {
            "name":                 "User",
            "first_name":           "User",
            "last_name":            "",
            "username":             "",
            "language_code":        "en",
            "joined":               datetime.now().strftime("%Y-%m-%d %H:%M"),
            "last_active":          datetime.now().strftime("%Y-%m-%d %H:%M"),
            "credits":              DEFAULT_CREDITS,
            "plan":                 "TRIAL",
            "expires":              0,
            "credits_before_prem":  DEFAULT_CREDITS,   # restored when premium ends
            "total_refs":           0,
            "total_checks":         0,
            "approved_checks":      0,
            "declined_checks":      0,
            "last_gate":            "N/A",
            "last_card":            "N/A",
            "codes_redeemed":       0,
            "keys_redeemed":        0,
        }
    return context.bot_data["user_data"][uid]

def _update_user_meta(ud: dict, user) -> None:
    ud["first_name"]  = user.first_name or "User"
    ud["last_name"]   = user.last_name or ""
    ud["name"]        = user.full_name or user.first_name or "User"
    ud["last_active"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    if user.username:
        ud["username"] = user.username
    if getattr(user, "language_code", None):
        ud["language_code"] = user.language_code

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AUTO-EXPIRE PREMIUM  (call before any premium-sensitive action)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def check_and_expire_premium(
    ud: dict, user_id: int, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    """
    Returns True if premium was just expired (so caller can send a notice).
    Restores pre-premium credits when expiry happens.
    """
    raw_plan = ud.get("plan", "TRIAL").upper()
    if raw_plan == "TRIAL":
        return False
    if ud.get("expires", 0) > time.time():
        return False

    # Premium has lapsed — restore credits and downgrade
    restored = ud.get("credits_before_prem", DEFAULT_CREDITS)
    ud["plan"]    = "TRIAL"
    ud["expires"] = 0
    ud["credits"] = restored

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "🦇 <b>Batman Card Checker</b>\n"
                "━━━━━━━━━━━━━━━━━\n"
                "⏰ <b>Pʀᴇᴍɪᴜᴍ Exᴘɪʀᴇᴅ</b>\n\n"
                f"Yᴏᴜʀ ᴘʀᴇᴍɪᴜᴍ ᴘʟᴀɴ ʜᴀs ᴇɴᴅᴇᴅ.\n"
                f"Cʀᴇᴅɪᴛꜱ Rᴇsᴛᴏʀᴇᴅ ➺ <b>{restored}</b>\n\n"
                "Rᴇɴᴇᴡ ᴡɪᴛʜ /plan\n"
                "━━━━━━━━━━━━━━━━━"
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass
    return True

def is_user_premium(ud: dict) -> bool:
    return ud.get("plan", "TRIAL").upper() != "TRIAL" and ud.get("expires", 0) > time.time()

def get_referral_link(user_id: int) -> str:
    return f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"

def gen_receipt() -> str:
    return f"Batman{random.randint(100000, 999999)}-CHK"

def gen_code(length: int = 10) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# KEYBOARDS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def kb_main(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡️ " + B("CHECKER"),  callback_data="mgates"),
         InlineKeyboardButton("💎 " + B("BUY NOW"),  callback_data="mprice")],
        [InlineKeyboardButton("📢 " + B("UPDATES") + " ➺", url=CHANNEL_LINK),
         InlineKeyboardButton("👥 " + B("GROUP")   + " ➺", url=GROUP_LINK)],
        [InlineKeyboardButton("🔗 " + B("REFER & EARN"), callback_data="mrefer")],
        [InlineKeyboardButton("🛟 " + B("SUPPORT") + " ➺", url=SUPPORT_LINK)],
    ])

def kb_back(cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 " + B("BACK"), callback_data=cb)]])

def kb_price() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔷 " + B("10$ — CORE"),  callback_data="pay10"),
         InlineKeyboardButton("🔶 " + B("15$ — ELITE"), callback_data="pay15")],
        [InlineKeyboardButton("💠 " + B("30$ — ROOT"),  callback_data="pay30")],
        [InlineKeyboardButton("🛟 " + B("SUPPORT") + " ➺", url=SUPPORT_LINK)],
        [InlineKeyboardButton("🔙 " + B("BACK"), callback_data="bmain")],
    ])

def kb_payment() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛟 " + B("SUPPORT") + " ➺", url=SUPPORT_LINK)],
        [InlineKeyboardButton("🔙 " + B("BACK"), callback_data="mprice")],
    ])

def kb_gate_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 " + B("AUTH"),    callback_data="mauth"),
         InlineKeyboardButton("💳 " + B("CHARGE"),  callback_data="mcharge"),
         InlineKeyboardButton("👑 " + B("PREMIUM"), callback_data="mmass")],
        [InlineKeyboardButton("🔙 " + B("BACK"), callback_data="bmain")],
    ])

def kb_auth_gates() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔹 " + B("BRAINTREE"), callback_data="ib3")],
        [InlineKeyboardButton("🔙 " + B("BACK"), callback_data="mgates")],
    ])

def kb_charge_gates() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔹 " + B("STRIPE"),  callback_data="ichk"),
         InlineKeyboardButton("🔸 " + B("PAYPAL"),  callback_data="ipp")],
        [InlineKeyboardButton("🟣 " + B("SHOPIFY"), callback_data="ish"),
         InlineKeyboardButton("🔺 " + B("PAYU"),    callback_data="ipyu")],
        [InlineKeyboardButton("🔙 " + B("BACK"), callback_data="mgates")],
    ])

def kb_premium_gates() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👑 " + B("STRIPE AUTH"), callback_data="iau")],
        [InlineKeyboardButton("👑 " + B("STRIPE MASS"), callback_data="imss")],
        [InlineKeyboardButton("👑 " + B("PAYPAL MASS"), callback_data="impp2")],
        [InlineKeyboardButton("🔙 " + B("BACK"), callback_data="mgates")],
    ])

def kb_upgrade() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 " + B("BUY PREMIUM"), callback_data="mprice")],
        [InlineKeyboardButton("🛟 " + B("SUPPORT") + " ➺", url=SUPPORT_LINK)],
    ])

# ── Card result bottom buttons ─────────────────────────────────────────────
# Trial/Free  → one BUY NOW button
# Premium     → one channel link button (BatmanCardXChk)
def kb_card_result(plan: str) -> InlineKeyboardMarkup:
    p = plan.upper()
    if p in ("CORE", "ELITE", "ROOT"):
        # Premium user — show channel link so they can share the result
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "🦇 " + B("BATMANCARDXCHK") + " ➺",
                url=CHANNEL_LINK
            )]
        ])
    else:
        # Trial / free user — show BUY NOW
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("💎 " + B("BUY NOW"), callback_data="mprice")]
        ])

def kb_fb_owner(key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approve", callback_data=f"fb_ok_{key}"),
        InlineKeyboardButton("❌ Decline", callback_data=f"fb_no_{key}"),
    ]])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROFILE TEXT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def ui_profile(user, context: ContextTypes.DEFAULT_TYPE) -> str:
    ud       = get_user_data(user.id, context)
    raw_plan = ud.get("plan", "TRIAL").upper()
    expires  = ud.get("expires", 0)
    now      = time.time()
    if raw_plan != "TRIAL" and expires <= now:
        raw_plan = "TRIAL"
        ud["plan"]    = "TRIAL"
        ud["expires"] = 0
        ud["credits"] = ud.get("credits_before_prem", DEFAULT_CREDITS)
        expires = 0
    premium    = raw_plan != "TRIAL"
    credits    = "♾️ Unlimited" if premium else str(ud.get("credits", DEFAULT_CREDITS))
    uname      = f"@{user.username}" if user.username else user.first_name or "User"
    total_refs = ud.get("total_refs", 0)
    plan_icon  = get_plan_icon(raw_plan)

    lines = [
        "🦇 <b>Batman Card Checker</b>",
        "━━━━━━━━━━━━━━━━━",
        f"👤 <b>Uꜱᴇʀ</b>    ➺ {uname} {plan_icon}",
        f"🆔 <b>ID</b>      ➺ <code>{user.id}</code>",
        f"🎖 <b>Aᴄᴄᴇꜱꜱ</b>  ➺ <b>{get_styled_plan(raw_plan)}</b>",
        f"💳 <b>Cʀᴇᴅɪᴛꜱ</b> ➺ <b>{credits}</b>",
    ]
    if premium and expires > now:
        exp_date = datetime.fromtimestamp(expires).strftime("%Y-%m-%d %H:%M")
        rem_d    = int((expires - now) / 86400)
        rem_h    = int(((expires - now) % 86400) / 3600)
        lines.append(f"📅 <b>Exᴘɪʀᴇꜱ</b> ➺ {exp_date}")
        lines.append(f"⏳ <b>Lᴇꜰᴛ</b>    ➺ {rem_d}d {rem_h}h")
        receipt = ud.get("last_receipt")
        if receipt:
            lines.append(f"🧾 <b>Rᴇᴄᴇɪᴘᴛ</b> ➺ <code>{receipt}</code>")
    else:
        lines.append(f"📅 <b>Exᴘɪʀᴇꜱ</b> ➺ Never")
    lines.append(f"👥 <b>Rᴇꜰᴇʀʀᴀʟꜱ</b> ➺ {total_refs} (+{total_refs * REFERRAL_CREDITS} credits)")
    lines.append(f"📆 <b>Jᴏɪɴᴇᴅ</b>  ➺ {ud.get('joined', datetime.now().strftime('%Y-%m-%d'))}")
    lines.append(f"🔗 <b>Dᴇᴠ</b>     ➺ <a href='{DEV_LINK}'>𝗕𝗮𝘁𝗺𝗮𝗻</a>")
    lines.append("━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)

def gate_info_text(gate_name: str, cmd: str, cost: int) -> str:
    return (
        f"🦇 <b>Batman Card Checker</b>\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"<b>{gate_name}</b>\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"💳 <b>Cᴏsᴛ</b>    ➺ <b>{cost}</b> Credit(s) per check\n\n"
        f"📌 <b>Uꜱᴀɢᴇ:</b>\n<code>/{cmd} cc|mm|yy|cvv</code>\n\n"
        f"✏️ <b>Exᴀᴍᴘʟᴇ:</b>\n<code>/{cmd} 4111111111111111|12|2026|123</code>\n\n"
        f"━━━━━━━━━━━━━━━━━"
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FORCE SUBSCRIBE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def check_force_sub(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> list:
    if user_id == OWNER_ID:
        return []
    not_joined = []
    for name, link in FORCE_CHANNELS:
        try:
            member = await context.bot.get_chat_member(f"@{name}", user_id)
            if member.status in ("left", "kicked"):
                not_joined.append((name, link))
        except Exception:
            not_joined.append((name, link))
    return not_joined

def kb_force_sub(not_joined: list) -> InlineKeyboardMarkup:
    rows = []
    for name, link in not_joined:
        label = "📢 Join Channel" if "group" not in name.lower() else "💬 Join Group"
        rows.append([InlineKeyboardButton(f"{label} ➺ @{name}", url=link)])
    rows.append([InlineKeyboardButton("✅ I Joined — Verify Now", callback_data="check_sub")])
    return InlineKeyboardMarkup(rows)

FORCE_SUB_TEXT = (
    "🦇 <b>Batman Card Checker</b>\n"
    "━━━━━━━━━━━━━━━━━\n"
    "⚠️ <b>Jᴏɪɴ Rᴇǫᴜɪʀᴇᴅ</b>\n\n"
    "You must join our channel & group to use this bot.\n"
    "After joining press the ✅ Verify button below.\n"
    "━━━━━━━━━━━━━━━━━"
)

async def require_membership(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id    = update.effective_user.id
    not_joined = await check_force_sub(user_id, context)
    if not_joined:
        await update.message.reply_text(
            FORCE_SUB_TEXT, reply_markup=kb_force_sub(not_joined), parse_mode="HTML")
        return False
    return True

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CARD CHECK RESULT UI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def build_check_result(
    card_raw:     str,
    gate_name:    str,
    raw_response: str,
    bin_data:     dict,
    username:     str,
    plan:         str,
    time_taken:   str,
    is_approved:  bool,
    is_timeout:   bool = False,
    is_error:     bool = False,
) -> str:
    if is_timeout:
        status_icon = "⏳"
        status      = "Tɪᴍᴇᴏᴜᴛ"
    elif is_error:
        status_icon = "⚠️"
        status      = "Eʀʀᴏʀ"
    elif is_approved:
        status_icon = "✅"
        status      = "Aᴘᴘʀᴏᴠᴇᴅ"
    else:
        status_icon = "❌"
        status      = "Dᴇᴄʟɪɴᴇᴅ"

    plan_icon  = get_plan_icon(plan)
    plan_label = get_styled_plan(plan)

    bin_txt = "N/A"
    if bin_data and not bin_data.get("error"):
        scheme  = str(bin_data.get("scheme",  "N/A")).upper()
        bank    = bin_data.get("bank",    "N/A")
        country = str(bin_data.get("country", "N/A")).upper()
        flag    = bin_data.get("country_emoji", "")
        bin_txt = f"{scheme} — {bank} — {flag} {country}".strip()

    uname_display = f"{username} {plan_icon} ({plan_label})"

    lines = [
        f"🦇 <b>[ 𖥷iТ ] ➺ {status_icon} {status}</b>",
        f"━━━━━━━━━━━━━━━━━",
        f"🔍 <b>Cᴀʀᴅ</b> ➺ <code>{card_raw}</code>",
        f"🏦 <b>Gᴀᴛᴇ</b> ➺ <b>{gate_name}</b>",
        f"📩 <b>Rᴀᴡ</b>  ➺ {raw_response}",
        f"ℹ️ <b>Iɴꜰᴏ</b> ➺ {bin_txt}",
        f"👤 <b>Uꜱᴇʀ</b> ➺ {uname_display}",
        f"⚡ <b>Pʀᴏ</b>  ➺ 𝗕𝗮𝘁𝗺𝗮𝗻 | {time_taken}s",
        f"━━━━━━━━━━━━━━━━━",
    ]
    return "\n".join(lines)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# REFERRAL SYSTEM
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def process_referral(new_user_id: int, referrer_id: int,
                            context: ContextTypes.DEFAULT_TYPE) -> bool:
    if new_user_id == referrer_id:
        return False
    referred_set = context.bot_data.setdefault("referred_users", set())
    if new_user_id in referred_set:
        return False
    referrer_ud = context.bot_data.get("user_data", {}).get(str(referrer_id))
    if referrer_ud is None:
        return False
    referred_set.add(new_user_id)
    referrer_ud["credits"]    = referrer_ud.get("credits", 0) + REFERRAL_CREDITS
    referrer_ud["total_refs"] = referrer_ud.get("total_refs", 0) + 1
    try:
        await context.bot.send_message(
            chat_id=referrer_id,
            parse_mode="HTML",
            text=(
                "🦇 <b>Batman Card Checker</b>\n"
                "━━━━━━━━━━━━━━━━━\n"
                "🎉 <b>Rᴇꜰᴇʀʀᴀʟ Bᴏɴᴜꜱ!</b>\n\n"
                "Someone joined via your link!\n"
                f"💳 <b>Cʀᴇᴅɪᴛꜱ Aᴅᴅᴇᴅ</b>    ➺ <b>+{REFERRAL_CREDITS}</b>\n"
                f"👥 <b>Tᴏᴛᴀʟ Rᴇꜰᴇʀʀᴀʟꜱ</b> ➺ <b>{referrer_ud['total_refs']}</b>\n"
                "━━━━━━━━━━━━━━━━━"
            ),
        )
    except Exception:
        pass
    return True

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GATE PROCESSING  (single-card: chk pp sh pyu b3)
# /au /mss /mpp2 handled exclusively by mass.py
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

    if context.bot_data.get("maintenance") and user.id != OWNER_ID:
        await update.message.reply_text(
            "🔧 <b>Bot is under maintenance.</b> Try again later.", parse_mode="HTML")
        return

    if not context.bot_data.get(f"{gate_key}_on", True):
        await update.message.reply_text(
            f"⛔ Gate <b>[{gate_name}]</b> is currently OFF.", parse_mode="HTML")
        return

    if not await require_membership(update, context):
        return

    ud      = get_user_data(user.id, context)
    _update_user_meta(ud, user)
    await check_and_expire_premium(ud, user.id, context)
    premium = is_user_premium(ud)

    card_raw = None
    if context.args:
        card_raw = context.args[0].strip()
    elif update.message.reply_to_message and update.message.reply_to_message.text:
        card_raw = update.message.reply_to_message.text.strip()

    if not card_raw:
        await update.message.reply_text(
            f"📌 <b>Uꜱᴀɢᴇ:</b> <code>/{gate_key} cc|mm|yy|cvv</code>", parse_mode="HTML")
        return

    if not premium:
        credits = ud.get("credits", 0)
        if credits <= 0:
            await update.message.reply_text(
                "🦇 <b>Batman Card Checker</b>\n"
                "━━━━━━━━━━━━━━━━━\n"
                "❌ <b>Nᴏ Cʀᴇᴅɪᴛꜱ</b>\n\n"
                "Buy a plan: /plan\n"
                "Refer friends for free credits: /refer\n"
                "━━━━━━━━━━━━━━━━━",
                parse_mode="HTML",
                reply_markup=kb_upgrade(),
            )
            return
        ud["credits"] = credits - 1

    api_url  = context.bot_data.get(f"gate_url_{gate_key}") or GATE_URLS.get(gate_key, "")
    site_url = GATE_SITES.get(gate_key, "example.com")
    bin_num  = card_raw[:6]

    if not api_url:
        await update.message.reply_text(
            f"⚠️ Gate API not set.\nOwner: <code>/seturl {gate_key} &lt;url&gt;</code>",
            parse_mode="HTML")
        return

    msg        = await update.message.reply_text("🦇 <b>[ 𖥷iТ ] ➺ Sᴄᴀɴɴɪɴɢ...</b>", parse_mode="HTML")
    start_time = time.time()

    uname = f"@{user.username}" if user.username else user.first_name or "User"
    plan  = ud.get("plan", "TRIAL")

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
        if isinstance(results[0], Exception):
            raise results[0]

        raw_response = str(
            data.get("value") or data.get("message") or
            data.get("Response") or data.get("category") or "ERROR"
        ).strip()

        is_approved = any(w in raw_response.lower() for w in
                          ["approved", "captured", "success", "charged", "true"])

        ud["total_checks"]    = ud.get("total_checks", 0) + 1
        ud["last_gate"]       = gate_name
        ud["last_card"]       = card_raw[:6] + "xxxxxxxxxx"
        ud["last_active"]     = datetime.now().strftime("%Y-%m-%d %H:%M")
        if is_approved:
            ud["approved_checks"] = ud.get("approved_checks", 0) + 1
        else:
            ud["declined_checks"] = ud.get("declined_checks", 0) + 1

        time_taken = f"{time.time() - start_time:.2f}"
        text = build_check_result(
            card_raw=card_raw, gate_name=gate_name, raw_response=raw_response,
            bin_data=bin_data, username=uname, plan=plan,
            time_taken=time_taken, is_approved=is_approved,
        )
        await msg.edit_text(
            text, parse_mode="HTML",
            reply_markup=kb_card_result(plan),
            disable_web_page_preview=True,
        )

    except asyncio.TimeoutError:
        if not premium: ud["credits"] = ud.get("credits", 0) + 1
        time_taken = f"{time.time() - start_time:.2f}"
        text = build_check_result(
            card_raw=card_raw, gate_name=gate_name,
            raw_response="Rᴇǫᴜᴇꜱᴛ Tɪᴍᴇᴏᴜᴛ", bin_data={},
            username=uname, plan=plan, time_taken=time_taken,
            is_approved=False, is_timeout=True,
        )
        await msg.edit_text(
            text, parse_mode="HTML",
            reply_markup=kb_card_result(plan),
            disable_web_page_preview=True,
        )
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
        await msg.edit_text(
            text, parse_mode="HTML",
            reply_markup=kb_card_result(plan),
            disable_web_page_preview=True,
        )

# ── Single-card gate wrappers ──────────────────────────
async def cmd_chk(update, context):  await process_gate(update, context, "chk",  "Stripe Charge")
async def cmd_pp(update, context):   await process_gate(update, context, "pp",   "PayPal Charge")
async def cmd_sh(update, context):   await process_gate(update, context, "sh",   "Shopify Charge")
async def cmd_pyu(update, context):  await process_gate(update, context, "pyu",  "PayU Charge")
async def cmd_b3(update, context):   await process_gate(update, context, "b3",   "Braintree Auth")

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

    ud         = get_user_data(user_id, context)
    expires_ts = time.time() + days * 86400

    # Save credits before going premium so we can restore them later
    if ud.get("plan", "TRIAL").upper() == "TRIAL":
        ud["credits_before_prem"] = ud.get("credits", DEFAULT_CREDITS)

    ud["name"]         = name
    ud["plan"]         = plan.upper()
    ud["expires"]      = expires_ts
    ud["last_receipt"] = receipt
    if username:
        ud["username"] = username

    exp_date     = datetime.fromtimestamp(expires_ts).strftime("%Y-%m-%d %H:%M")
    display_name = f"@{username}" if username else name
    styled       = get_styled_plan(plan)

    txt = (
        "🦇 <b>Batman Card Checker</b>\n"
        "━━━━━━━━━━━━━━━━━\n"
        "🎉 <b>Aᴄᴄᴇꜱꜱ Aᴄᴛɪᴠᴀᴛᴇᴅ!</b>\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Uꜱᴇʀ</b>     ➺ {display_name}\n"
        f"🎖 <b>Aᴄᴄᴇꜱꜱ</b>  ➺ <b>{styled} 👑</b>\n"
        f"📆 <b>Dᴀʏꜱ</b>    ➺ <b>{days}</b>\n"
        f"💳 <b>Cʀᴇᴅɪᴛꜱ</b> ➺ <b>♾️ Unlimited</b>\n"
        f"⏰ <b>Exᴘɪʀᴇꜱ</b> ➺ {exp_date}\n"
        f"🧾 <b>Rᴇᴄᴇɪᴘᴛ</b> ➺ <code>{receipt}</code>\n"
        "━━━━━━━━━━━━━━━━━\n"
        "📌 Save this receipt ID.\n"
        "⚡ <b>Pʀᴏ</b> ➺ 𝗕𝗮𝘁𝗺𝗮𝗻"
    )
    try:
        await context.bot.send_message(chat_id=user_id, text=txt, parse_mode="HTML")
    except Exception:
        pass
    return receipt

async def resolve_user(target: str, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    target = target.strip().lstrip("@")
    if target.lstrip("-").isdigit():
        return int(target)
    for attempt in (f"@{target}", target):
        try:
            return (await context.bot.get_chat(attempt)).id
        except Exception:
            continue
    all_users    = context.bot_data.get("user_data", {})
    target_lower = target.lower()
    for uid_str, ud in all_users.items():
        stored = ud.get("username", "").lower().lstrip("@")
        if stored and stored == target_lower:
            return int(uid_str)
    return None

async def _grant(uid: int, plan: str, days: int,
                 update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud = get_user_data(uid, context)
    if ud.get("plan", "TRIAL").upper() == "TRIAL":
        ud["credits_before_prem"] = ud.get("credits", DEFAULT_CREDITS)
    ud["plan"]    = plan.upper()
    ud["expires"] = time.time() + days * 86400

    display_name  = ud.get("name", "Unknown")
    display_uname = ud.get("username", "")
    try:
        chat = await context.bot.get_chat(uid)
        display_name  = chat.first_name or "Unknown"
        if chat.last_name:
            display_name = f"{display_name} {chat.last_name}"
        display_uname = chat.username or ""
        ud["name"] = display_name
        if display_uname:
            ud["username"] = display_uname
    except Exception:
        pass

    receipt    = await send_activation_msg(uid, plan, days, context)
    uname_line = f"@{display_uname}" if display_uname else display_name
    exp_ts     = ud["expires"]
    exp_date   = datetime.fromtimestamp(exp_ts).strftime("%Y-%m-%d %H:%M")

    await update.message.reply_text(
        "🦇 <b>Batman Card Checker</b>\n"
        "━━━━━━━━━━━━━━━━━\n"
        "✅ <b>Gʀᴀɴᴛᴇᴅ</b>\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Uꜱᴇʀ</b>    ➺ {uname_line}\n"
        f"🆔 <b>ID</b>      ➺ <code>{uid}</code>\n"
        f"🎖 <b>Pʟᴀɴ</b>    ➺ <b>{get_styled_plan(plan)} 👑</b>\n"
        f"📆 <b>Dᴀʏꜱ</b>    ➺ <b>{days}</b>\n"
        f"⏰ <b>Exᴘɪʀᴇꜱ</b> ➺ {exp_date}\n"
        f"🧾 <b>Rᴇᴄᴇɪᴘᴛ</b> ➺ <code>{receipt}</code>\n"
        "━━━━━━━━━━━━━━━━━",
        parse_mode="HTML",
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# OWNER COMMANDS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    args = context.args
    if len(args) < 3:
        await update.message.reply_text(
            "📌 <b>Usage:</b> /add &lt;user_id|@username&gt; &lt;plan&gt; &lt;days&gt;\n"
            "Plans: <b>CORE  ELITE  ROOT</b>", parse_mode="HTML")
        return
    uid = await resolve_user(args[0], context)
    if not uid:
        await update.message.reply_text(f"❌ User not found: {args[0]}")
        return
    plan = args[1].upper()
    if plan not in ("CORE", "ELITE", "ROOT"):
        await update.message.reply_text("❌ Invalid plan. Use: CORE  ELITE  ROOT")
        return
    try:
        days = int(args[2])
    except ValueError:
        await update.message.reply_text("❌ Days must be a number.")
        return
    await _grant(uid, plan, days, update, context)

async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("📌 <b>Usage:</b> /remove &lt;user_id|@username&gt;", parse_mode="HTML")
        return
    uid = await resolve_user(context.args[0], context)
    if not uid:
        await update.message.reply_text(f"❌ User not found: {context.args[0]}")
        return
    ud = get_user_data(uid, context)
    restored = ud.get("credits_before_prem", DEFAULT_CREDITS)
    ud["plan"]    = "TRIAL"
    ud["expires"] = 0
    ud["credits"] = restored
    await update.message.reply_text(
        f"✅ Removed premium from <code>{uid}</code>.\n"
        f"💳 Credits restored to <b>{restored}</b>.", parse_mode="HTML")

async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner command: /info @username  or  /info user_id"""
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text(
            "📌 <b>Usage:</b> /info &lt;@username | user_id&gt;", parse_mode="HTML")
        return
    uid = await resolve_user(context.args[0], context)
    if not uid:
        await update.message.reply_text(f"❌ User not found: {context.args[0]}")
        return
    ud       = context.bot_data.get("user_data", {}).get(str(uid), {})
    raw_plan = ud.get("plan", "TRIAL").upper()
    now      = time.time()
    expires  = ud.get("expires", 0)
    # Auto-expire check
    if raw_plan != "TRIAL" and expires <= now:
        raw_plan = "TRIAL"
    premium  = raw_plan != "TRIAL" and expires > now
    credits  = "♾️ Unlimited" if premium else str(ud.get("credits", DEFAULT_CREDITS))
    uname    = f"@{ud.get('username','')}" if ud.get("username") else ud.get("name", "Unknown")
    exp_str  = datetime.fromtimestamp(expires).strftime("%Y-%m-%d %H:%M") if expires > 0 else "N/A"
    rem_str  = ""
    if premium and expires > now:
        rem_d = int((expires - now) / 86400)
        rem_h = int(((expires - now) % 86400) / 3600)
        rem_str = f"\n⏳ <b>Lᴇꜰᴛ</b>    ➺ <b>{rem_d}d {rem_h}h</b>"

    text = (
        "🦇 <b>Batman Card Checker — User Info</b>\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Nᴀᴍᴇ</b>    ➺ {uname}\n"
        f"🆔 <b>ID</b>      ➺ <code>{uid}</code>\n"
        f"🎖 <b>Pʟᴀɴ</b>    ➺ <b>{get_styled_plan(raw_plan)}</b> {get_plan_icon(raw_plan)}\n"
        f"💳 <b>Cʀᴇᴅɪᴛꜱ</b> ➺ <b>{credits}</b>\n"
        f"📅 <b>Exᴘɪʀᴇꜱ</b> ➺ {exp_str}"
        f"{rem_str}\n"
        f"📊 <b>Tᴏᴛᴀʟ Cʜᴇᴄᴋꜱ</b>    ➺ {ud.get('total_checks', 0)}\n"
        f"✅ <b>Aᴘᴘʀᴏᴠᴇᴅ</b>          ➺ {ud.get('approved_checks', 0)}\n"
        f"❌ <b>Dᴇᴄʟɪɴᴇᴅ</b>          ➺ {ud.get('declined_checks', 0)}\n"
        f"🏦 <b>Lᴀꜱᴛ Gᴀᴛᴇ</b>         ➺ {ud.get('last_gate', 'N/A')}\n"
        f"🃏 <b>Lᴀꜱᴛ Cᴀʀᴅ</b> (BIN)   ➺ <code>{ud.get('last_card', 'N/A')}</code>\n"
        f"👥 <b>Rᴇꜰᴇʀʀᴀʟꜱ</b>         ➺ {ud.get('total_refs', 0)}\n"
        f"📆 <b>Jᴏɪɴᴇᴅ</b>             ➺ {ud.get('joined', 'N/A')}\n"
        f"🕐 <b>Lᴀꜱᴛ Aᴄᴛɪᴠᴇ</b>       ➺ {ud.get('last_active', 'N/A')}\n"
        f"🧾 <b>Lᴀꜱᴛ Rᴇᴄᴇɪᴘᴛ</b>      ➺ <code>{ud.get('last_receipt', 'N/A')}</code>\n"
        "━━━━━━━━━━━━━━━━━"
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def cmd_seturl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if len(context.args) < 2:
        await update.message.reply_text("📌 <b>Usage:</b> /seturl &lt;gate_key&gt; &lt;url&gt;", parse_mode="HTML")
        return
    key = context.args[0].lower()
    url = context.args[1]
    context.bot_data[f"gate_url_{key}"] = url
    await update.message.reply_text(
        f"✅ URL set for gate <code>{key}</code>.", parse_mode="HTML")

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text(
            "📌 <b>Usage:</b> /broadcast &lt;your message here&gt;", parse_mode="HTML")
        return
    text    = " ".join(context.args)
    users   = context.bot_data.get("user_data", {})
    sent    = 0
    failed  = 0
    status_msg = await update.message.reply_text(
        f"📢 Broadcasting to <b>{len(users)}</b> users...", parse_mode="HTML")
    for uid_str in list(users.keys()):
        try:
            await context.bot.send_message(
                chat_id=int(uid_str), text=text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1
    await status_msg.edit_text(
        "🦇 <b>Broadcast Complete</b>\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"✅ <b>Sent</b>   ➺ {sent}\n"
        f"❌ <b>Failed</b> ➺ {failed}\n"
        "━━━━━━━━━━━━━━━━━",
        parse_mode="HTML",
    )

async def cmd_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    current = context.bot_data.get("maintenance", False)
    context.bot_data["maintenance"] = not current
    state = "🔴 ON" if not current else "🟢 OFF"
    await update.message.reply_text(
        f"🔧 <b>Maintenance mode:</b> <b>{state}</b>", parse_mode="HTML")

async def cmd_gate_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if len(context.args) < 2:
        await update.message.reply_text("📌 <b>Usage:</b> /gate &lt;gate_key&gt; on|off", parse_mode="HTML")
        return
    key   = context.args[0].lower()
    state = context.args[1].lower() == "on"
    context.bot_data[f"{key}_on"] = state
    icon  = "🟢 ON" if state else "🔴 OFF"
    await update.message.reply_text(
        f"🏦 Gate <code>{key}</code> is now <b>{icon}</b>.", parse_mode="HTML")

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    users = context.bot_data.get("user_data", {})
    total = len(users)
    now   = time.time()
    premium = sum(
        1 for ud in users.values()
        if ud.get("plan", "TRIAL").upper() != "TRIAL" and ud.get("expires", 0) > now
    )
    await update.message.reply_text(
        "🦇 <b>Batman Card Checker — Stats</b>\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"👥 <b>Total Users</b>  ➺ <b>{total}</b>\n"
        f"👑 <b>Premium</b>      ➺ <b>{premium}</b>\n"
        f"🆓 <b>Trial</b>        ➺ <b>{total - premium}</b>\n"
        "━━━━━━━━━━━━━━━━━",
        parse_mode="HTML",
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# USER COMMANDS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _send_start_photo(target, caption: str, reply_markup, parse_mode="HTML"):
    """
    Send the Batman bot photo with caption.
    target = update.message  (for /start)
    BOT_PHOTO can be a local file path OR a Telegram file_id string.
    """
    try:
        if BOT_PHOTO and os.path.isfile(BOT_PHOTO):
            with open(BOT_PHOTO, "rb") as f:
                await target.reply_photo(
                    photo=f, caption=caption,
                    parse_mode=parse_mode, reply_markup=reply_markup)
        elif BOT_PHOTO:
            # Assume it's a file_id or URL
            await target.reply_photo(
                photo=BOT_PHOTO, caption=caption,
                parse_mode=parse_mode, reply_markup=reply_markup)
        else:
            await target.reply_text(caption, parse_mode=parse_mode, reply_markup=reply_markup)
    except Exception:
        # Fallback to text if photo fails
        await target.reply_text(caption, parse_mode=parse_mode, reply_markup=reply_markup)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ud   = get_user_data(user.id, context)
    _update_user_meta(ud, user)
    await check_and_expire_premium(ud, user.id, context)

    if context.args and context.args[0].startswith("ref_"):
        try:
            ref_id = int(context.args[0][4:])
            await process_referral(user.id, ref_id, context)
        except ValueError:
            pass

    raw_plan = ud.get("plan", "TRIAL").upper()
    credits  = "♾️ Unlimited" if is_user_premium(ud) else str(ud.get("credits", DEFAULT_CREDITS))
    uname    = f"@{user.username}" if user.username else user.first_name or "User"

    caption = (
        "🦇 <b>Batman Card Checker</b>\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Uꜱᴇʀ</b>    ➺ {uname} {get_plan_icon(raw_plan)}\n"
        f"🆔 <b>ID</b>      ➺ <code>{user.id}</code>\n"
        f"🎖 <b>Aᴄᴄᴇꜱꜱ</b>  ➺ <b>{get_styled_plan(raw_plan)}</b>\n"
        f"💳 <b>Cʀᴇᴅɪᴛꜱ</b> ➺ <b>{credits}</b>\n"
        f"📆 <b>Jᴏɪɴᴇᴅ</b>  ➺ {ud.get('joined', datetime.now().strftime('%Y-%m-%d'))}\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"🔗 <b>Dᴇᴠ</b>     ➺ <a href='{DEV_LINK}'>𝗕𝗮𝘁𝗺𝗮𝗻</a>\n"
        f"📡 <b>Vᴇʀꜱɪᴏɴ</b> ➺ <b>{VERSION}</b>"
    )
    await _send_start_photo(update.message, caption, kb_main(user.id))

async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ud   = get_user_data(user.id, context)
    _update_user_meta(ud, user)
    await check_and_expire_premium(ud, user.id, context)
    await update.message.reply_text(
        ui_profile(user, context), parse_mode="HTML",
        reply_markup=kb_back("bmain"), disable_web_page_preview=True)

async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🦇 <b>Batman Card Checker</b>\n"
        "━━━━━━━━━━━━━━━━━\n"
        "💎 <b>Pʀᴇᴍɪᴜᴍ Pʟᴀɴꜱ</b>\n"
        "━━━━━━━━━━━━━━━━━\n"
        "🔷 <b>CORE</b>  ➺ $10 / 30 days\n"
        "🔶 <b>ELITE</b> ➺ $15 / 30 days\n"
        "💠 <b>ROOT</b>  ➺ $30 / 30 days\n"
        "━━━━━━━━━━━━━━━━━\n"
        "✅ All plans include <b>Unlimited credits</b>.\n"
        "📩 Contact support to purchase.",
        parse_mode="HTML",
        reply_markup=kb_price(),
    )

async def cmd_refer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    link = get_referral_link(user.id)
    ud   = get_user_data(user.id, context)
    await update.message.reply_text(
        "🦇 <b>Batman Card Checker</b>\n"
        "━━━━━━━━━━━━━━━━━\n"
        "🔗 <b>Rᴇꜰᴇʀ & Eᴀʀɴ</b>\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"🔗 <b>Yᴏᴜʀ Lɪɴᴋ</b> ➺ {link}\n"
        f"👥 <b>Rᴇꜰᴇʀʀᴀʟꜱ</b> ➺ <b>{ud.get('total_refs', 0)}</b>\n"
        f"💳 <b>Eᴀʀɴᴇᴅ</b>   ➺ <b>{ud.get('total_refs', 0) * REFERRAL_CREDITS}</b> credits\n"
        "━━━━━━━━━━━━━━━━━",
        parse_mode="HTML",
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🦇 <b>Batman Card Checker — Commands</b>\n"
        "━━━━━━━━━━━━━━━━━\n"
        "🆓 <b>Free Gates:</b>\n"
        "/chk <code>cc|mm|yy|cvv</code>  ➺ Stripe Charge\n"
        "/pp  <code>cc|mm|yy|cvv</code>  ➺ PayPal Charge\n"
        "/sh  <code>cc|mm|yy|cvv</code>  ➺ Shopify Charge\n"
        "/pyu <code>cc|mm|yy|cvv</code>  ➺ PayU Charge\n"
        "/b3  <code>cc|mm|yy|cvv</code>  ➺ Braintree Auth\n\n"
        "👑 <b>Premium Gates:</b>\n"
        "/au   ➺ Sᴛʀɪᴘᴇ Aᴜᴛʜ (mass + file)\n"
        "/mss  ➺ Sᴛʀɪᴘᴇ Mᴀss (mass + file)\n"
        "/mpp2 ➺ PᴀʏPᴀʟ Mᴀss (mass + file)\n\n"
        "📁 <b>File Support (Premium):</b>\n"
        "Upload .txt → send /au /mss /mpp2 as caption\n"
        "OR reply to any .txt file with the command.\n\n"
        "📋 <b>Other:</b>\n"
        "/profile  ➺ Your profile\n"
        "/plan     ➺ Buy premium\n"
        "/refer    ➺ Refer & earn credits\n"
        "━━━━━━━━━━━━━━━━━",
        parse_mode="HTML",
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CALLBACK QUERY HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cb_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data  = query.data
    user  = query.from_user

    ud = context.bot_data.get("user_data", {}).get(str(user.id), {})
    await check_and_expire_premium(ud, user.id, context)

    async def edit(text: str, kb=None, **kw):
        try:
            await query.edit_message_text(
                text, parse_mode="HTML", reply_markup=kb,
                disable_web_page_preview=True, **kw)
        except BadRequest:
            pass

    if data == "bmain":
        raw_plan = ud.get("plan", "TRIAL").upper()
        credits  = "♾️ Unlimited" if is_user_premium(ud) else str(ud.get("credits", DEFAULT_CREDITS))
        uname    = f"@{user.username}" if user.username else user.first_name or "User"
        caption = (
            "🦇 <b>Batman Card Checker</b>\n"
            "━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Uꜱᴇʀ</b>    ➺ {uname} {get_plan_icon(raw_plan)}\n"
            f"🆔 <b>ID</b>      ➺ <code>{user.id}</code>\n"
            f"🎖 <b>Aᴄᴄᴇꜱꜱ</b>  ➺ <b>{get_styled_plan(raw_plan)}</b>\n"
            f"💳 <b>Cʀᴇᴅɪᴛꜱ</b> ➺ <b>{credits}</b>\n"
            "━━━━━━━━━━━━━━━━━\n"
            f"🔗 <b>Dᴇᴠ</b>     ➺ <a href='{DEV_LINK}'>𝗕𝗮𝘁𝗺𝗮𝗻</a>\n"
            f"📡 <b>Vᴇʀꜱɪᴏɴ</b> ➺ <b>{VERSION}</b>"
        )
        await edit(caption, kb_main(user.id))

    elif data == "mgates":
        await edit(
            "🦇 <b>Batman Card Checker</b>\n"
            "━━━━━━━━━━━━━━━━━\n"
            "⚡ <b>Sᴇʟᴇᴄᴛ Gᴀᴛᴇ Cᴀᴛᴇɢᴏʀʏ</b>",
            kb_gate_main())

    elif data == "mauth":
        await edit(
            "🦇 <b>Batman Card Checker</b>\n"
            "━━━━━━━━━━━━━━━━━\n"
            "🔑 <b>Aᴜᴛʜ Gᴀᴛᴇꜱ</b>\n"
            "━━━━━━━━━━━━━━━━━\n"
            "/b3 ➺ Braintree Auth",
            kb_auth_gates())

    elif data == "mcharge":
        await edit(
            "🦇 <b>Batman Card Checker</b>\n"
            "━━━━━━━━━━━━━━━━━\n"
            "💳 <b>Cʜᴀʀɢᴇ Gᴀᴛᴇꜱ</b>\n"
            "━━━━━━━━━━━━━━━━━\n"
            "/chk ➺ Stripe  |  /pp ➺ PayPal\n"
            "/sh  ➺ Shopify  |  /pyu ➺ PayU",
            kb_charge_gates())

    elif data == "mmass":
        await edit(
            "🦇 <b>Batman Card Checker</b>\n"
            "━━━━━━━━━━━━━━━━━\n"
            "👑 <b>Pʀᴇᴍɪᴜᴍ Gᴀᴛᴇꜱ</b>\n"
            "━━━━━━━━━━━━━━━━━\n"
            "/au   ➺ Sᴛʀɪᴘᴇ Aᴜᴛʜ\n"
            "/mss  ➺ Sᴛʀɪᴘᴇ Mᴀss\n"
            "/mpp2 ➺ PᴀʏPᴀʟ Mᴀss\n\n"
            "📁 Supports file upload + reply-to-file.",
            kb_premium_gates())

    elif data == "mprice":
        await edit(
            "🦇 <b>Batman Card Checker</b>\n"
            "━━━━━━━━━━━━━━━━━\n"
            "💎 <b>Pʀᴇᴍɪᴜᴍ Pʟᴀɴꜱ</b>\n"
            "━━━━━━━━━━━━━━━━━\n"
            "🔷 <b>CORE</b>  ➺ $10 / 30 days\n"
            "🔶 <b>ELITE</b> ➺ $15 / 30 days\n"
            "💠 <b>ROOT</b>  ➺ $30 / 30 days\n"
            "━━━━━━━━━━━━━━━━━\n"
            "📩 Contact support to purchase.",
            kb_price())

    elif data == "mrefer":
        link = get_referral_link(user.id)
        await edit(
            "🦇 <b>Batman Card Checker</b>\n"
            "━━━━━━━━━━━━━━━━━\n"
            f"🔗 <b>Yᴏᴜʀ Lɪɴᴋ</b> ➺ {link}\n"
            f"👥 <b>Rᴇꜰᴇʀʀᴀʟꜱ</b> ➺ <b>{ud.get('total_refs', 0)}</b>\n"
            "━━━━━━━━━━━━━━━━━",
            kb_back("bmain"))

    elif data == "check_sub":
        not_joined = await check_force_sub(user.id, context)
        if not_joined:
            await query.answer("Please join all channels first!", show_alert=True)
        else:
            await edit(
                "🦇 <b>Batman Card Checker</b>\n"
                "━━━━━━━━━━━━━━━━━\n"
                "✅ <b>Vᴇʀɪꜰɪᴇᴅ!</b> You are now subscribed.\n"
                "Use /start to continue.\n"
                "━━━━━━━━━━━━━━━━━",
                kb_main(user.id))

    elif data in ("ib3", "ichk", "ipp", "ish", "ipyu", "iau", "imss", "impp2"):
        gate_map = {
            "ib3":   ("b3",   "Braintree Auth",  0),
            "ichk":  ("chk",  "Stripe Charge",   1),
            "ipp":   ("pp",   "PayPal Charge",   1),
            "ish":   ("sh",   "Shopify Charge",  1),
            "ipyu":  ("pyu",  "PayU Charge",     1),
            "iau":   ("au",   "Sᴛʀɪᴘᴇ Aᴜᴛʜ",    0),
            "imss":  ("mss",  "Sᴛʀɪᴘᴇ Mᴀss",    0),
            "impp2": ("mpp2", "PᴀʏPᴀʟ Mᴀss",    0),
        }
        cmd, name, cost = gate_map[data]
        await edit(gate_info_text(name, cmd, cost), kb_back("mgates"))

    elif data.startswith("pay"):
        plan_map = {"pay10": ("CORE", 30), "pay15": ("ELITE", 30), "pay30": ("ROOT", 30)}
        plan, days = plan_map.get(data, ("CORE", 30))
        await edit(
            "🦇 <b>Batman Card Checker</b>\n"
            "━━━━━━━━━━━━━━━━━\n"
            f"💎 <b>Pᴜʀᴄʜᴀꜱᴇ {get_styled_plan(plan)}</b>\n"
            "━━━━━━━━━━━━━━━━━\n"
            "Contact support with your user ID:\n"
            f"<code>{user.id}</code>\n"
            "━━━━━━━━━━━━━━━━━",
            kb_payment())

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# APPLICATION SETUP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def build_application() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()

    # ── User commands ─────────────────────────────────
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("help",    cmd_help))
    app.add_handler(CommandHandler("profile", cmd_profile))
    app.add_handler(CommandHandler("plan",    cmd_plan))
    app.add_handler(CommandHandler("refer",   cmd_refer))

    # ── Free single-card gates ────────────────────────
    app.add_handler(CommandHandler("chk",  cmd_chk))
    app.add_handler(CommandHandler("pp",   cmd_pp))
    app.add_handler(CommandHandler("sh",   cmd_sh))
    app.add_handler(CommandHandler("pyu",  cmd_pyu))
    app.add_handler(CommandHandler("b3",   cmd_b3))

    # ── Premium mass gates + result buttons ───────────
    for handler in get_mass_handlers():
        app.add_handler(handler)

    # ── Owner commands ────────────────────────────────
    app.add_handler(CommandHandler("add",         cmd_add))
    app.add_handler(CommandHandler("remove",      cmd_remove))
    app.add_handler(CommandHandler("info",        cmd_info))
    app.add_handler(CommandHandler("seturl",      cmd_seturl))
    app.add_handler(CommandHandler("broadcast",   cmd_broadcast))
    app.add_handler(CommandHandler("maintenance", cmd_maintenance))
    app.add_handler(CommandHandler("gate",        cmd_gate_toggle))
    app.add_handler(CommandHandler("stats",       cmd_stats))

    # ── Inline button callbacks ───────────────────────
    # result_ callbacks registered by get_mass_handlers() above
    app.add_handler(CallbackQueryHandler(cb_handler))

    return app

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENTRY POINT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def main():
    if not acquire_instance_lock():
        logger.error("Another instance is already running. Exiting.")
        return

    app = build_application()

    loop       = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _sig_handler(*_):
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _sig_handler)

    try:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
        )
        logger.info("🦇 Batman Card Checker — Bot started.")
        await stop_event.wait()
    except Conflict:
        logger.error("Telegram conflict: another bot instance is running with the same token.")
    except NetworkError as e:
        logger.error(f"Network error: {e}")
    finally:
        try:
            await app.updater.stop()
            await app.stop()
            await app.shutdown()
        except Exception:
            pass
        release_instance_lock()
        logger.info("Bot stopped.")

if __name__ == "__main__":
    asyncio.run(main())
