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
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
    get_bin_info, kb_result,
)
from mass import get_mass_handlers  # <-- ADDED IMPORT FOR MASS HANDLERS

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
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_styled_plan(raw_plan: str) -> str:
    p = raw_plan.upper()
    if p == "CORE":  return "Cᴏʀᴇ"
    if p == "ELITE": return "Eʟɪᴛᴇ"
    if p == "ROOT":  return "Rᴏᴏᴛ"
    return "Tʀɪᴀʟ"

def get_plan_icon(raw_plan: str) -> str:
    p = raw_plan.upper()
    if p in ("CORE", "ELITE", "ROOT"): return "👑"
    return ""

def get_user_data(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> dict:
    uid = str(user_id)
    if "user_data" not in context.bot_data:
        context.bot_data["user_data"] = {}
    if uid not in context.bot_data["user_data"]:
        context.bot_data["user_data"][uid] = {
            "name":            "User",
            "first_name":      "User",
            "last_name":       "",
            "username":        "",
            "language_code":   "en",
            "joined":          datetime.now().strftime("%Y-%m-%d %H:%M"),
            "last_active":     datetime.now().strftime("%Y-%m-%d %H:%M"),
            "credits":         150,
            "plan":            "TRIAL",
            "expires":         0,
            "total_refs":      0,
            "total_checks":    0,
            "approved_checks": 0,
            "declined_checks": 0,
            "last_gate":       "N/A",
            "last_card":       "N/A",
            "codes_redeemed":  0,
            "keys_redeemed":   0,
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

def gen_code(length: int = 10) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))

def gen_receipt() -> str:
    return f"Batman{random.randint(100000, 999999)}-CHK"

def is_user_premium(ud: dict) -> bool:
    return ud.get("plan", "TRIAL").upper() != "TRIAL" and ud.get("expires", 0) > time.time()

def get_referral_link(user_id: int) -> str:
    return f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"

def ui_profile(user, context: ContextTypes.DEFAULT_TYPE) -> str:
    ud       = get_user_data(user.id, context)
    raw_plan = ud.get("plan", "TRIAL").upper()
    expires  = ud.get("expires", 0)
    now      = time.time()
    if raw_plan != "TRIAL" and expires <= now:
        raw_plan = "TRIAL"; ud["plan"] = "TRIAL"; ud["expires"] = 0; expires = 0
    premium    = raw_plan != "TRIAL"
    credits    = "Unlimited" if premium else str(ud.get("credits", 150))
    uname      = f"@{user.username}" if user.username else user.first_name or "User"
    total_refs = ud.get("total_refs", 0)
    plan_icon  = get_plan_icon(raw_plan)

    lines = [
        f"[ 𖥷iТ ] Batman Card Checker",
        f"━━━━━━━━━━━━━━━━━",
        f"Uꜱᴇʀ    ➺ {uname} {plan_icon}".rstrip(),
        f"ID      ➺ <code>{user.id}</code>",
        f"Aᴄᴄᴇꜱꜱ  ➺ {get_styled_plan(raw_plan)}",
        f"Cʀᴇᴅɪᴛꜱ ➺ {credits}",
    ]
    if premium and expires > now:
        exp_date = datetime.fromtimestamp(expires).strftime("%Y-%m-%d %H:%M")
        rem_d    = int((expires - now) / 86400)
        rem_h    = int(((expires - now) % 86400) / 3600)
        lines.append(f"Exᴘɪʀᴇꜱ ➺ {exp_date}")
        lines.append(f"Lᴇꜰᴛ    ➺ {rem_d}d {rem_h}h")
        receipt = ud.get("last_receipt")
        if receipt:
            lines.append(f"Rᴇᴄᴇɪᴘᴛ ➺ <code>{receipt}</code>")
    lines.append(f"Rᴇꜰᴇʀʀᴀʟꜱ ➺ {total_refs} (+{total_refs * REFERRAL_CREDITS} credits)")
    lines.append(f"Jᴏɪɴᴇᴅ  ➺ {ud.get('joined', datetime.now().strftime('%Y-%m-%d'))}")
    lines.append(f"Dᴇᴠ     ➺ <a href='{DEV_LINK}'>Batman</a>")
    lines.append("━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)

def gate_info_text(gate_name: str, cmd: str, cost: int) -> str:
    return (
        f"━━━━━━━━━━━━━━━━━\n{gate_name}\n━━━━━━━━━━━━━━━━━\n\n"
        f"Cᴏsᴛ    ➺ {cost} Credit(s) per check\n\n"
        f"Uꜱᴀɢᴇ:\n<code>/{cmd} cc|mm|yy|cvv</code>\n\n"
        f"Exᴀᴍᴘʟᴇ:\n<code>/{cmd} 4111111111111111|12|2026|123</code>\n\n"
        f"━━━━━━━━━━━━━━━━━"
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FORCE SUBSCRIBE — SECURE SYSTEM
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
    rows.append([InlineKeyboardButton(
        "✅ I Joined — Verify Now", callback_data="check_sub"
    )])
    return InlineKeyboardMarkup(rows)

FORCE_SUB_TEXT = (
    "[ 𖥷iТ ] ➺ Jᴏɪɴ Rᴇǫᴜɪʀᴇᴅ\n"
    "━━━━━━━━━━━━━━━━━\n"
    "You must join our channel & group to use this bot.\n"
    "After joining press the ✅ Verify button below.\n"
    "━━━━━━━━━━━━━━━━━"
)

async def require_membership(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id    = update.effective_user.id
    not_joined = await check_force_sub(user_id, context)
    if not_joined:
        await update.message.reply_text(
            FORCE_SUB_TEXT,
            reply_markup=kb_force_sub(not_joined),
        )
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
        status = "Tɪᴍᴇᴏᴜᴛ"
    elif is_error:
        status = "Eʀʀᴏʀ"
    elif is_approved:
        status = "Aᴘᴘʀᴏᴠᴇᴅ"
    else:
        status = "Dᴇᴄʟɪɴᴇᴅ"

    plan_icon  = get_plan_icon(plan)
    plan_label = get_styled_plan(plan)

    bin_txt = "N/A"
    if bin_data and not bin_data.get("error"):
        scheme  = str(bin_data.get("scheme",  "N/A")).upper()
        bank    = bin_data.get("bank",    "N/A")
        country = str(bin_data.get("country", "N/A")).upper()
        flag    = bin_data.get("country_emoji", "")
        bin_txt = f"{scheme} - {bank} - {flag} {country}".strip()

    uname_display = f"{username} {plan_icon} ({plan_label})".strip()

    lines = [
        f"[ 𖥷iТ ] ➺ {status}",
        f"🔍 ➺ <code>{card_raw}</code>",
        f"Gᴀᴛᴇ ➺ {gate_name} 💳",
        f"Rᴀᴡ  ➺ {raw_response}",
        f"Iɴꜰᴏ ➺ {bin_txt}",
        f"Uꜱᴇʀ ➺ {uname_display}",
        f"Pʀᴏ  ➺ Batman | {time_taken}s",
    ]
    return "\n".join(lines)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# KEYBOARDS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def kb_main(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("CHECKER"),  callback_data="mgates"),
         InlineKeyboardButton(B("BUY NOW"), callback_data="mprice")],
        [InlineKeyboardButton(B("UPDATES") + " ➺", url=CHANNEL_LINK),
         InlineKeyboardButton(B("GROUP")   + " ➺", url=GROUP_LINK)],
        [InlineKeyboardButton("🔗 " + B("REFER & EARN"), callback_data="mrefer")],
        [InlineKeyboardButton(B("SUPPORT") + " ➺", url=SUPPORT_LINK)],
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

def kb_fb_owner(key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approve", callback_data=f"fb_ok_{key}"),
        InlineKeyboardButton("❌ Decline", callback_data=f"fb_no_{key}"),
    ]])

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
            text=(
                f"Rᴇꜰᴇʀʀᴀʟ Bᴏɴᴜꜱ\n"
                f"━━━━━━━━━━━━━━━━━\n"
                f"Someone joined via your link!\n"
                f"Cʀᴇᴅɪᴛꜱ Aᴅᴅᴇᴅ    ➺ +{REFERRAL_CREDITS}\n"
                f"Tᴏᴛᴀʟ Rᴇꜰᴇʀʀᴀʟꜱ ➺ {referrer_ud['total_refs']}\n"
                f"━━━━━━━━━━━━━━━━━"
            ),
        )
    except Exception:
        pass
    return True

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GATE PROCESSING
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
        await update.message.reply_text("Bot is under maintenance. Try again later.")
        return

    if not context.bot_data.get(f"{gate_key}_on", True):
        await update.message.reply_text(f"Gate [{gate_name}] is currently OFF.")
        return

    if not await require_membership(update, context):
        return

    ud      = get_user_data(user.id, context)
    premium = is_user_premium(ud)
    _update_user_meta(ud, user)

    if gate_key in PREMIUM_GATES and not premium:
        gate_label = {
            "au":   "Stripe Auth (/au)",
            "mss":  "Stripe Mass (/mss)",
            "mpp2": "PayPal Mass (/mpp2)",
        }.get(gate_key, gate_key.upper())
        await update.message.reply_text(
            f"[ 𖥷iТ ] ➺ Pʀᴇᴍɪᴜᴍ Oɴʟʏ\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"Gᴀᴛᴇ ➺ {gate_label}\n\n"
            f"Fʀᴇᴇ Gᴀᴛᴇꜱ:\n"
            f"/chk  ➺ Stripe Charge\n"
            f"/pp   ➺ PayPal Charge\n"
            f"/sh   ➺ Shopify Charge\n"
            f"/pyu  ➺ PayU Charge\n"
            f"/b3   ➺ Braintree Auth\n\n"
            f"Pʀᴇᴍɪᴜᴍ Gᴀᴛᴇꜱ:\n"
            f"/au   ➺ Stripe Auth\n"
            f"/mss  ➺ Stripe Mass\n"
            f"/mpp2 ➺ PayPal Mass\n\n"
            f"Pʀᴏ  ➺ Batman | /plan",
            parse_mode="HTML", reply_markup=kb_upgrade(),
        )
        return

    card_raw = None
    if context.args:
        card_raw = context.args[0].strip()
    elif update.message.reply_to_message and update.message.reply_to_message.text:
        card_raw = update.message.reply_to_message.text.strip()

    if not card_raw:
        await update.message.reply_text(
            f"Uꜱᴀɢᴇ: <code>/{gate_key} cc|mm|yy|cvv</code>", parse_mode="HTML")
        return

    if not premium:
        credits = ud.get("credits", 0)
        if credits <= 0:
            await update.message.reply_text(
                "[ 𖥷iТ ] ➺ Nᴏ Cʀᴇᴅɪᴛꜱ\n"
                "━━━━━━━━━━━━━━━━━\n"
                "Buy a plan: /plan\n"
                "Refer friends for free credits: /refer",
                reply_markup=kb_upgrade(),
            )
            return
        ud["credits"] = credits - 1

    api_url  = context.bot_data.get(f"gate_url_{gate_key}") or GATE_URLS.get(gate_key, "")
    site_url = GATE_SITES.get(gate_key, "example.com")
    bin_num  = card_raw[:6]

    if not api_url:
        await update.message.reply_text(
            f"Gate API not set. Owner: /seturl {gate_key} &lt;url&gt;", parse_mode="HTML")
        return

    msg        = await update.message.reply_text("[ 𖥷iТ ] ➺ Sᴄᴀɴɴɪɴɢ...")
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
        await msg.edit_text(text, parse_mode="HTML",
                            reply_markup=kb_result(), disable_web_page_preview=True)

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
                            reply_markup=kb_result(), disable_web_page_preview=True)
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
                            reply_markup=kb_result(), disable_web_page_preview=True)

async def cmd_chk(u, c):  await process_gate(u, c, "chk",  "Stripe Charge")
async def cmd_pp(u, c):   await process_gate(u, c, "pp",   "PayPal Charge")
async def cmd_sh(u, c):   await process_gate(u, c, "sh",   "Shopify Charge")
async def cmd_pyu(u, c):  await process_gate(u, c, "pyu",  "PayU Charge")
async def cmd_b3(u, c):   await process_gate(u, c, "b3",   "Braintree Auth")
async def cmd_au(u, c):   await process_gate(u, c, "au",   "Stripe Auth")
async def cmd_mss(u, c):  await process_gate(u, c, "mss",  "Stripe Mass")
async def cmd_mpp2(u, c): await process_gate(u, c, "mpp2", "PayPal Mass")

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
        f"[ 𖥷iТ ] ➺ Aᴄᴄᴇꜱꜱ Aᴄᴛɪᴠᴀᴛᴇᴅ\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"Uꜱᴇʀ     ➺ {display_name}\n"
        f"Aᴄᴄᴇꜱꜱ  ➺ {styled} 👑\n"
        f"Dᴀʏꜱ    ➺ {days}\n"
        f"Cʀᴇᴅɪᴛꜱ ➺ Unlimited\n"
        f"Exᴘɪʀᴇꜱ ➺ {exp_date}\n"
        f"Rᴇᴄᴇɪᴘᴛ ➺ <code>{receipt}</code>\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"Save this receipt ID.\n"
        f"Pʀᴏ ➺ Batman"
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
    ud["plan"]    = plan
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
        f"━━━━━━━━━━━━━━━━━\n"
        f"✅ Pʀᴇᴍɪᴜᴍ Gʀᴀɴᴛᴇᴅ\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"Uꜱᴇʀ     ➺ {uname_line}\n"
        f"ID       ➺ <code>{uid}</code>\n"
        f"Pʟᴀɴ     ➺ {get_styled_plan(plan)} 👑\n"
        f"Dᴀʏꜱ     ➺ {days}\n"
        f"Exᴘɪʀᴇꜱ  ➺ {exp_date}\n"
        f"Rᴇᴄᴇɪᴘᴛ  ➺ <code>{receipt}</code>\n"
        f"━━━━━━━━━━━━━━━━━",
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

    not_joined = await check_force_sub(user.id, context)
    if not_joined:
        await update.message.reply_text(
            FORCE_SUB_TEXT,
            reply_markup=kb_force_sub(not_joined),
        )
        return

    await update.message.reply_text(
        ui_profile(user, context),
        parse_mode="HTML",
        reply_markup=kb_main(user.id),
        disable_web_page_preview=True,
    )

async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_membership(update, context):
        return
    t   = time.time()
    msg = await update.message.reply_text("[ 𖥷iТ ] ➺ Pɪɴɢɪɴɢ...")
    await msg.edit_text(f"[ 𖥷iТ ] ➺ Pᴏɴɢ | {int((time.time() - t) * 1000)}ms")

async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_membership(update, context):
        return
    txt = (
        "[ 𖥷iТ ] Batman Premium Plans\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        "Aᴄᴄᴇꜱꜱ  ➺ Cᴏʀᴇ\nDᴀʏꜱ     ➺ 7\nCʀᴇᴅɪᴛꜱ ➺ Unlimited\nPʀɪᴄᴇ   ➺ 10$\n"
        "━━━━━━━━━━━━━━━━━\n"
        "Aᴄᴄᴇꜱꜱ  ➺ Eʟɪᴛᴇ\nDᴀʏꜱ     ➺ 15\nCʀᴇᴅɪᴛꜱ ➺ Unlimited\nPʀɪᴄᴇ   ➺ 15$\n"
        "━━━━━━━━━━━━━━━━━\n"
        "Aᴄᴄᴇꜱꜱ  ➺ Rᴏᴏᴛ\nDᴀʏꜱ     ➺ 30\nCʀᴇᴅɪᴛꜱ ➺ Unlimited\nPʀɪᴄᴇ   ➺ 30$\n"
        "━━━━━━━━━━━━━━━━━"
    )
    await update.message.reply_text(txt, reply_markup=kb_price())

async def cmd_refer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_membership(update, context):
        return
    user       = update.effective_user
    ud         = get_user_data(user.id, context)
    link       = get_referral_link(user.id)
    total_refs = ud.get("total_refs", 0)
    txt = (
        f"[ 𖥷iТ ] Rᴇꜰᴇʀʀᴀʟ\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"Lɪɴᴋ    ➺ <code>{link}</code>\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"Rᴇꜰᴇʀʀᴀʟꜱ ➺ {total_refs}\n"
        f"Eᴀʀɴᴇᴅ   ➺ {total_refs * REFERRAL_CREDITS} credits\n"
        f"Pᴇʀ Rᴇꜰ  ➺ +{REFERRAL_CREDITS} credits\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"Share your link to earn free credits!"
    )
    await update.message.reply_text(txt, parse_mode="HTML",
                                    reply_markup=kb_back("bmain"),
                                    disable_web_page_preview=True)

async def cmd_rm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_membership(update, context):
        return
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
            f"Redeemed +{codes[code]['value']} credits\nCʀᴇᴅɪᴛꜱ ➺ {ud['credits']}")
    elif code in keys and not keys[code]["used"]:
        keys[code]["used"] = True
        p, d    = keys[code]["plan"], keys[code]["days"]
        ud["keys_redeemed"] = ud.get("keys_redeemed", 0) + 1
        receipt = await send_activation_msg(uid, p, d, context)
        await update.message.reply_text(
            f"Activated {get_styled_plan(p)} for {d} days!\n"
            f"Rᴇᴄᴇɪᴘᴛ ➺ <code>{receipt}</code>", parse_mode="HTML")
    else:
        await update.message.reply_text("Invalid or already used code.")

async def cmd_bin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_membership(update, context):
        return
    bin_num = context.args[0].strip()[:6] if context.args else None
    if not bin_num or not bin_num.isdigit() or len(bin_num) < 6:
        await update.message.reply_text("Uꜱᴀɢᴇ: <code>/bin 411111</code>", parse_mode="HTML")
        return
    msg = await update.message.reply_text("[ 𖥷iТ ] ➺ Lᴏᴏᴋɪɴɢ ᴜᴘ...")
    try:
        bd = await get_bin_info(bin_num)
        if bd.get("error"):
            await msg.edit_text("BIN not found.")
            return
        txt = (
            f"[ 𖥷iТ ] ➺ BIN Lookup\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"BIN     ➺ <code>{bin_num}</code>\n"
            f"Scheme  ➺ {str(bd.get('scheme', 'N/A')).upper()}\n"
            f"Type    ➺ {str(bd.get('type',   'N/A')).upper()}\n"
            f"Bank    ➺ {bd.get('bank', 'N/A')}\n"
            f"Country ➺ {bd.get('country_emoji', '')} {str(bd.get('country', 'N/A')).upper()}\n"
            f"━━━━━━━━━━━━━━━━━"
        )
        await msg.edit_text(txt, parse_mode="HTML")
    except Exception as e:
        await msg.edit_text(f"Error: <code>{str(e)[:100]}</code>", parse_mode="HTML")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FEEDBACK SYSTEM  (/fb)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _fb_key(user_id: int) -> str:
    return f"{user_id}_{int(time.time())}_{random.randint(1000, 9999)}"

async def cmd_fb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_membership(update, context):
        return
    msg = update.message
    if msg.photo or msg.video:
        await handle_fb_media(update, context)
        return
    await msg.reply_text(
        "━━━━━━━━━━━━━━━━━\n"
        "📸 Fᴇᴇᴅʙᴀᴄᴋ\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        "Sᴇɴᴅ a photo or video WITH the caption /fb\n\n"
        "Exᴀᴍᴘʟᴇ:\n"
        "Attach screenshot → set caption → /fb → Send\n\n"
        "You can add a note after /fb:\n"
        "<code>/fb Great service!</code>\n"
        "━━━━━━━━━━━━━━━━━",
        parse_mode="HTML",
    )

async def handle_fb_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg  = update.message
    user = update.effective_user

    if not await require_membership(update, context):
        return

    if msg.photo:
        file_id   = msg.photo[-1].file_id
        file_type = "photo"
    elif msg.video:
        file_id   = msg.video.file_id
        file_type = "video"
    else:
        return

    raw_caption = (msg.caption or "").strip()
    user_note   = raw_caption
    bot_uname   = context.bot.username or ""
    for prefix in (f"/fb@{bot_uname}", "/fb"):
        if user_note.lower().startswith(prefix.lower()):
            user_note = user_note[len(prefix):].strip()
            break

    key       = _fb_key(user.id)
    uname     = f"@{user.username}" if user.username else user.first_name or "User"
    submitted = datetime.now().strftime("%Y-%m-%d %H:%M")

    context.bot_data.setdefault("fb_pending", {})[key] = {
        "file_id":   file_id,
        "file_type": file_type,
        "user_id":   user.id,
        "username":  uname,
        "name":      user.full_name or user.first_name or "User",
        "note":      user_note,
        "date":      submitted,
    }

    await msg.reply_text(
        "━━━━━━━━━━━━━━━━━\n"
        "Fᴇᴇᴅʙᴀᴄᴋ Sᴜʙᴍɪᴛᴛᴇᴅ ✅\n"
        "━━━━━━━━━━━━━━━━━\n"
        "Under review — you'll be notified once approved.\n"
        "━━━━━━━━━━━━━━━━━"
    )

    owner_caption = (
        f"[ 𖥷iТ ] ➺ Nᴇᴡ Fᴇᴇᴅʙᴀᴄᴋ\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"Uꜱᴇʀ ➺ {uname}\n"
        f"ID   ➺ {user.id}\n"
        f"Dᴀᴛᴇ ➺ {submitted}\n"
        f"Tʏᴘᴇ ➺ {file_type.capitalize()}\n"
    )
    if user_note:
        owner_caption += f"Nᴏᴛᴇ ➺ {user_note[:200]}\n"
    owner_caption += "━━━━━━━━━━━━━━━━━\nApprove to post to channel?"

    try:
        if file_type == "photo":
            await context.bot.send_photo(
                chat_id=OWNER_ID, photo=file_id,
                caption=owner_caption, reply_markup=kb_fb_owner(key),
            )
        else:
            await context.bot.send_video(
                chat_id=OWNER_ID, video=file_id,
                caption=owner_caption, reply_markup=kb_fb_owner(key),
            )
    except Exception as e:
        logger.error(f"Feedback notify owner failed: {e}")

async def _fb_approve(query, context: ContextTypes.DEFAULT_TYPE, key: str):
    fb = context.bot_data.get("fb_pending", {}).get(key)
    if not fb:
        await query.answer("Already handled or not found.", show_alert=True)
        return

    uname     = fb["username"]
    uid       = fb["user_id"]
    submitted = fb["date"]
    file_id   = fb["file_id"]
    file_type = fb["file_type"]
    user_note = fb.get("note", "")

    channel_caption = "━━━━━━━━━━━━━━━━━\n"
    if user_note:
        channel_caption += f"{user_note}\n━━━━━━━━━━━━━━━━━\n"
    channel_caption += (
        f"Uꜱᴇʀ ➺ {uname}\n"
        f"ID   ➺ {uid}\n"
        f"Dᴀᴛᴇ ➺ {submitted}\n"
        f"━━━━━━━━━━━━━━━━━"
    )

    posted = False
    try:
        if file_type == "photo":
            await context.bot.send_photo(
                chat_id=CHANNEL_USERNAME, photo=file_id, caption=channel_caption)
        else:
            await context.bot.send_video(
                chat_id=CHANNEL_USERNAME, video=file_id, caption=channel_caption)
        posted = True
    except Exception as e:
        logger.error(f"Feedback channel post failed: {e}")

    context.bot_data["fb_pending"].pop(key, None)

    status_line = "✅ Posted to channel!" if posted else "⚠️ Approved but post failed."
    try:
        await query.message.edit_caption(
            caption=(
                f"[ 𖥷iТ ] ➺ Fᴇᴇᴅʙᴀᴄᴋ Aᴘᴘʀᴏᴠᴇᴅ\n"
                f"━━━━━━━━━━━━━━━━━\n"
                f"Uꜱᴇʀ   ➺ {uname}\n"
                f"ID     ➺ {uid}\n"
                f"Sᴛᴀᴛᴜꜱ ➺ {status_line}\n"
                f"━━━━━━━━━━━━━━━━━"
            ),
            reply_markup=None,
        )
    except Exception:
        pass

    try:
        await context.bot.send_message(
            chat_id=uid,
            text=(
                "[ 𖥷iТ ] ➺ Fᴇᴇᴅʙᴀᴄᴋ Aᴄᴄᴇᴘᴛᴇᴅ ✅\n"
                "━━━━━━━━━━━━━━━━━\n"
                "Your feedback has been posted to the channel!\n"
                f"📢 {CHANNEL_LINK}\n"
                "━━━━━━━━━━━━━━━━━"
            ),
        )
    except Exception:
        pass

async def _fb_decline(query, context: ContextTypes.DEFAULT_TYPE, key: str):
    fb = context.bot_data.get("fb_pending", {}).get(key)
    if not fb:
        await query.answer("Already handled or not found.", show_alert=True)
        return

    uname = fb["username"]
    uid   = fb["user_id"]
    context.bot_data["fb_pending"].pop(key, None)

    try:
        await query.message.edit_caption(
            caption=(
                f"[ 𖥷iТ ] ➺ Fᴇᴇᴅʙᴀᴄᴋ Dᴇᴄʟɪɴᴇᴅ\n"
                f"━━━━━━━━━━━━━━━━━\n"
                f"Uꜱᴇʀ   ➺ {uname}\n"
                f"ID     ➺ {uid}\n"
                f"Sᴛᴀᴛᴜꜱ ➺ ❌ Declined — not posted\n"
                f"━━━━━━━━━━━━━━━━━"
            ),
            reply_markup=None,
        )
    except Exception:
        pass

    try:
        await context.bot.send_message(
            chat_id=uid,
            text=(
                "[ 𖥷iТ ] ➺ Fᴇᴇᴅʙᴀᴄᴋ Dᴇᴄʟɪɴᴇᴅ ❌\n"
                "━━━━━━━━━━━━━━━━━\n"
                "Your feedback was not approved this time.\n"
                "━━━━━━━━━━━━━━━━━"
            ),
        )
    except Exception:
        pass

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# OWNER COMMANDS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    target_id, target_name, target_username = None, "N/A", None
    target_last_name, target_lang = "", "N/A"

    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        ru               = update.message.reply_to_message.from_user
        target_id        = ru.id
        target_name      = ru.first_name or "N/A"
        target_last_name = ru.last_name or ""
        target_username  = ru.username
        target_lang      = ru.language_code or "N/A"
    elif context.args:
        raw = context.args[0].strip().lstrip("@")
        if raw.lstrip("-").isdigit():
            target_id = int(raw)
        else:
            try:
                chat             = await context.bot.get_chat(f"@{raw}")
                target_id        = chat.id
                target_name      = chat.first_name or "N/A"
                target_last_name = getattr(chat, "last_name", "") or ""
                target_username  = chat.username
            except Exception:
                pass
            if not target_id:
                raw_lower = raw.lower()
                for uid_str, ud in context.bot_data.get("user_data", {}).items():
                    stored = ud.get("username", "").lower().lstrip("@")
                    if stored and stored == raw_lower:
                        target_id       = int(uid_str)
                        target_name     = ud.get("name", "N/A")
                        target_username = ud.get("username")
                        target_lang     = ud.get("language_code", "N/A")
                        break

    if not target_id:
        await update.message.reply_text(
            "Uꜱᴀɢᴇ: /info @username | /info 123456789 | reply to user → /info")
        return

    if target_name == "N/A":
        try:
            chat             = await context.bot.get_chat(target_id)
            target_name      = chat.first_name or "N/A"
            target_last_name = getattr(chat, "last_name", "") or ""
            target_username  = chat.username
        except Exception:
            pass

    uid_str   = str(target_id)
    now       = time.time()
    udata     = context.bot_data.get("user_data", {}).get(uid_str, {})
    raw_plan  = udata.get("plan", "TRIAL").upper()
    expires   = udata.get("expires", 0)
    if raw_plan != "TRIAL" and expires <= now:
        raw_plan = "TRIAL"; expires = 0
    premium   = raw_plan != "TRIAL" and expires > now
    credits_d = "Unlimited" if premium else str(udata.get("credits", 150))

    full_name = f"{target_name} {target_last_name}".strip()
    uname_d   = f"@{target_username}" if target_username else "None"
    lang_d    = udata.get("language_code", target_lang) or "N/A"

    total_refs      = udata.get("total_refs", 0)
    total_checks    = udata.get("total_checks", 0)
    approved_checks = udata.get("approved_checks", 0)
    declined_checks = udata.get("declined_checks", 0)
    approval_rate   = f"{(approved_checks / total_checks * 100):.1f}%" if total_checks > 0 else "N/A"

    txt = (
        f"[ 𖥷iТ ] Uꜱᴇʀ Iɴꜰᴏ\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"Nᴀᴍᴇ       ➺ {full_name}\n"
        f"Uꜱᴇʀɴᴀᴍᴇ  ➺ {uname_d}\n"
        f"ID         ➺ <code>{target_id}</code>\n"
        f"Lᴀɴɢ       ➺ {lang_d.upper()}\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"Pʟᴀɴ       ➺ {get_styled_plan(raw_plan)}\n"
        f"Cʀᴇᴅɪᴛꜱ   ➺ {credits_d}\n"
        f"Sᴛᴀᴛᴜꜱ    ➺ {'Active' if premium else 'Trial'}\n"
    )
    if premium and expires > now:
        rem  = expires - now
        rstr = f"{int(rem // 86400)}d {int((rem % 86400) // 3600)}h"
        txt += (
            f"Exᴘɪʀᴇꜱ   ➺ {datetime.fromtimestamp(expires).strftime('%Y-%m-%d %H:%M')}\n"
            f"Rᴇᴍᴀɪɴɪɴɢ ➺ {rstr}\n"
        )
    last_receipt = udata.get("last_receipt")
    if last_receipt:
        txt += f"Rᴇᴄᴇɪᴘᴛ   ➺ <code>{last_receipt}</code>\n"
    txt += (
        f"━━━━━━━━━━━━━━━━━\n"
        f"Jᴏɪɴᴇᴅ      ➺ {udata.get('joined', 'N/A')}\n"
        f"Lᴀꜱᴛ Aᴄᴛɪᴠᴇ ➺ {udata.get('last_active', 'N/A')}\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"Tᴏᴛᴀʟ Cʜᴇᴄᴋꜱ ➺ {total_checks}\n"
        f"Aᴘᴘʀᴏᴠᴇᴅ     ➺ {approved_checks}\n"
        f"Dᴇᴄʟɪɴᴇᴅ     ➺ {declined_checks}\n"
        f"Rᴀᴛᴇ         ➺ {approval_rate}\n"
        f"Lᴀꜱᴛ Gᴀᴛᴇ   ➺ {udata.get('last_gate', 'N/A')}\n"
        f"Lᴀꜱᴛ BIN    ➺ <code>{udata.get('last_card', 'N/A')}</code>\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"Rᴇꜰᴇʀʀᴀʟꜱ   ➺ {total_refs}\n"
        f"Cᴏᴅᴇꜱ        ➺ {udata.get('codes_redeemed', 0)} redeemed\n"
        f"Kᴇʏꜱ         ➺ {udata.get('keys_redeemed', 0)} redeemed\n"
        f"━━━━━━━━━━━━━━━━━"
    )
    if len(txt) > MAX_MSG:
        for i in range(0, len(txt), MAX_MSG):
            await update.message.reply_text(txt[i:i+MAX_MSG], parse_mode="HTML")
    else:
        await update.message.reply_text(txt, parse_mode="HTML")

async def cmd_allcm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    txt = (
        "━━━━━━━━━━━━━━━━━\n🦇 ALL COMMANDS\n━━━━━━━━━━━━━━━━━\n\n"
        "🟢 USER:\n"
        "/start ➺ Start bot\n/plan ➺ View plans\n/bin ➺ BIN lookup\n"
        "/rm ➺ Redeem code\n/ping ➺ Speed check\n/refer ➺ Referral link\n"
        "/fb ➺ Submit feedback (photo/video)\n\n"
        "⚡ FREE CHECKER:\n"
        "/chk ➺ Stripe Charge\n/pp ➺ PayPal Charge\n/sh ➺ Shopify Charge\n"
        "/pyu ➺ PayU Charge\n/b3 ➺ Braintree Auth\n\n"
        "👑 PREMIUM ONLY:\n"
        "/au ➺ Stripe Auth\n/mss ➺ Stripe Mass\n/mpp2 ➺ PayPal Mass\n\n"
        "👑 OWNER:\n"
        "/info ➺ Full user info\n/find ➺ Search user\n/allcm ➺ This menu\n"
        "/gen ➺ Gen credits\n/key10 /key20 /key30 ➺ Gen keys\n"
        "/oneday /threeday ➺ Short keys\n"
        "/sub ➺ Grant premium\n/resub ➺ Remove premium\n"
        "/addcredits ➺ Add credits\n/allplans ➺ List premium users\n"
        "/seturl ➺ Set gate API URL\n/geturl ➺ View gate URLs\n"
        "/broadcast ➺ Message all users\n/killbot /onbot ➺ Maintenance mode\n"
        "━━━━━━━━━━━━━━━━━"
    )
    await update.message.reply_text(txt)

async def cmd_find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args:
        await update.message.reply_text(
            "Uꜱᴀɢᴇ: /find @username | /find 123456789 | /find Name")
        return
    query     = " ".join(context.args).strip().lstrip("@")
    all_users = context.bot_data.get("user_data", {})
    now       = time.time()
    matches   = []
    ql        = query.lower()
    is_id     = query.lstrip("-").isdigit()
    for uid_str, ud in all_users.items():
        if is_id:
            if uid_str == query:
                matches.append((uid_str, ud))
                break
        else:
            if ql in ud.get("username", "").lower().lstrip("@") or ql in ud.get("name", "").lower():
                matches.append((uid_str, ud))
    if not matches:
        await update.message.reply_text(f"❌ No users found: <code>{query}</code>", parse_mode="HTML")
        return
    MAX_R  = 10
    header = f"━━━━━━━━━━━━━━━━━\n🔍 Found {len(matches)} user(s)\n━━━━━━━━━━━━━━━━━\n\n"
    blocks = []
    for uid_str, ud in matches[:MAX_R]:
        rp = ud.get("plan", "TRIAL").upper()
        ex = ud.get("expires", 0)
        if rp != "TRIAL" and ex <= now: rp = "TRIAL"
        prem    = rp != "TRIAL" and ex > now
        tl      = f"{int((ex - now) // 86400)}d {int(((ex - now) % 86400) // 3600)}h" if prem and ex > now else "—"
        uname_l = f"@{ud['username']}" if ud.get("username") else "—"
        blocks.append(
            f"Nᴀᴍᴇ   ➺ {ud.get('name', 'Unknown')}\n"
            f"Uꜱᴇʀ   ➺ {uname_l}\n"
            f"ID     ➺ <code>{uid_str}</code>\n"
            f"Pʟᴀɴ   ➺ {get_styled_plan(rp)} {'✅' if prem else '⬜'}\n"
            f"Lᴇꜰᴛ   ➺ {tl}\n"
            f"Cʜᴇᴄᴋꜱ ➺ {ud.get('total_checks', 0)}\n"
        )
    footer = ("" if len(matches) <= MAX_R else f"(showing {MAX_R} of {len(matches)})\n") + "━━━━━━━━━━━━━━━━━"
    txt    = header + ("\n━━━━━━━━━━━━━━━━━\n").join(blocks) + "\n" + footer
    if len(txt) > MAX_MSG:
        for i in range(0, len(txt), MAX_MSG):
            await update.message.reply_text(txt[i:i+MAX_MSG], parse_mode="HTML")
    else:
        await update.message.reply_text(txt, parse_mode="HTML")

async def cmd_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args:
        await update.message.reply_text("Uꜱᴀɢᴇ: /gen &lt;credits&gt;", parse_mode="HTML"); return
    try:
        amt  = int(context.args[0])
        code = gen_code()
        context.bot_data.setdefault("codes", {})[code] = {"type": "credit", "value": amt, "used": False}
        await update.message.reply_text(f"Cᴏᴅᴇ: <code>{code}</code>\nCʀᴇᴅɪᴛꜱ: {amt}", parse_mode="HTML")
    except ValueError:
        await update.message.reply_text("Invalid amount.")

async def _gen_key(update, context, plan: str, days: int):
    if update.effective_user.id != OWNER_ID: return
    code = "KEY-" + gen_code(12)
    context.bot_data.setdefault("keys", {})[code] = {"plan": plan, "days": days, "used": False}
    await update.message.reply_text(
        f"Kᴇʏ: <code>{code}</code>\nPʟᴀɴ: {get_styled_plan(plan)} | Dᴀʏꜱ: {days}", parse_mode="HTML")

async def cmd_key10(u, c): await _gen_key(u, c, "CORE",  7)
async def cmd_key20(u, c): await _gen_key(u, c, "ELITE", 15)
async def cmd_key30(u, c): await _gen_key(u, c, "ROOT",  30)

async def cmd_oneday(update, context):
    if update.effective_user.id != OWNER_ID: return
    code = "KEY-" + gen_code(12)
    context.bot_data.setdefault("keys", {})[code] = {"plan": "CORE", "days": 1, "used": False}
    await update.message.reply_text(f"1 Day Code: <code>{code}</code>", parse_mode="HTML")

async def cmd_threeday(update, context):
    if update.effective_user.id != OWNER_ID: return
    code = "KEY-" + gen_code(12)
    context.bot_data.setdefault("keys", {})[code] = {"plan": "CORE", "days": 3, "used": False}
    await update.message.reply_text(f"3 Days Code: <code>{code}</code>", parse_mode="HTML")

async def cmd_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    uid = None; days = None
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        uid = update.message.reply_to_message.from_user.id
        if not context.args:
            await update.message.reply_text("Uꜱᴀɢᴇ (reply): /sub &lt;days&gt;", parse_mode="HTML"); return
        try:
            days = int(context.args[0])
            if days <= 0: raise ValueError
        except ValueError:
            await update.message.reply_text("❌ Invalid days."); return
    else:
        if len(context.args) < 2:
            await update.message.reply_text(
                "Uꜱᴀɢᴇ: /sub @user|ID days\nOr reply to user → /sub days"); return
        uid = await resolve_user(context.args[0], context)
        if not uid:
            await update.message.reply_text("❌ User not found."); return
        try:
            days = int(context.args[1])
            if days <= 0: raise ValueError
        except ValueError:
            await update.message.reply_text("❌ Invalid days."); return
    plan = "ROOT" if days >= 30 else "ELITE" if days >= 15 else "CORE"
    await _grant(uid, plan, days, update, context)

async def cmd_addcredits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    uid = None; amt = None
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        uid = update.message.reply_to_message.from_user.id
        if not context.args:
            await update.message.reply_text("Uꜱᴀɢᴇ (reply): /addcredits &lt;amount&gt;", parse_mode="HTML"); return
        try:
            amt = int(context.args[0])
            if amt <= 0: raise ValueError
        except ValueError:
            await update.message.reply_text("❌ Invalid amount."); return
    else:
        if len(context.args) < 2:
            await update.message.reply_text("Uꜱᴀɢᴇ: /addcredits @user|ID amount"); return
        uid = await resolve_user(context.args[0], context)
        if not uid:
            await update.message.reply_text("❌ User not found."); return
        try:
            amt = int(context.args[1])
            if amt <= 0: raise ValueError
        except ValueError:
            await update.message.reply_text("❌ Invalid amount."); return

    ud = get_user_data(uid, context)
    display_name  = ud.get("name", "Unknown")
    display_uname = ud.get("username", "")
    try:
        chat = await context.bot.get_chat(uid)
        display_name  = chat.first_name or display_name
        if chat.last_name: display_name = f"{display_name} {chat.last_name}"
        display_uname = chat.username or display_uname
        ud["name"] = display_name
        if display_uname: ud["username"] = display_uname
    except Exception:
        pass

    old = ud.get("credits", 0)
    ud["credits"] = old + amt
    uname_line = f"@{display_uname}" if display_uname else display_name

    try:
        await context.bot.send_message(chat_id=uid, text=(
            f"[ 𖥷iТ ] ➺ Cʀᴇᴅɪᴛꜱ Aᴅᴅᴇᴅ\n━━━━━━━━━━━━━━━━━\n"
            f"Aᴅᴅᴇᴅ   ➺ +{amt}\nBᴀʟᴀɴᴄᴇ ➺ {ud['credits']}\n━━━━━━━━━━━━━━━━━"
        ))
    except Exception:
        pass
    await update.message.reply_text(
        f"━━━━━━━━━━━━━━━━━\n✅ Cʀᴇᴅɪᴛꜱ Aᴅᴅᴇᴅ\n━━━━━━━━━━━━━━━━━\n"
        f"Uꜱᴇʀ ➺ {uname_line}\nID ➺ <code>{uid}</code>\n"
        f"Aᴅᴅᴇᴅ ➺ +{amt}\nPʀᴇᴠ ➺ {old}\nNᴇᴡ ➺ {ud['credits']}\n━━━━━━━━━━━━━━━━━",
        parse_mode="HTML",
    )

async def cmd_resub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args:
        await update.message.reply_text("Uꜱᴀɢᴇ: /resub &lt;@user or ID&gt;", parse_mode="HTML"); return
    uid = await resolve_user(context.args[0], context)
    if not uid:
        await update.message.reply_text("User not found."); return
    uid_str  = str(uid)
    all_data = context.bot_data.get("user_data", {})
    if uid_str not in all_data:
        await update.message.reply_text("User has no data."); return
    ud = all_data[uid_str]
    ud["plan"] = "TRIAL"; ud["expires"] = 0; ud["credits"] = 0
    try:
        await context.bot.send_message(chat_id=uid, text="Your premium has been removed. Account reset to Trial.")
    except Exception:
        pass
    await update.message.reply_text(f"Premium removed for <code>{uid}</code>.", parse_mode="HTML")

async def cmd_allplans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    all_users     = context.bot_data.get("user_data", {})
    now           = time.time()
    premium_users = [(u, d) for u, d in all_users.items()
                     if d.get("plan", "TRIAL").upper() != "TRIAL" and d.get("expires", 0) > now]
    if not premium_users:
        await update.message.reply_text("No active premium users."); return
    txt = f"[ 𖥷iТ ] Live Premium ➺ {len(premium_users)} Users\n━━━━━━━━━━━━━━━━━\n\n"
    for uid_str, ud in premium_users:
        rem = ud["expires"] - now
        txt += (
            f"Nᴀᴍᴇ ➺ {ud.get('name', 'Unknown')}\n"
            f"ID   ➺ <code>{uid_str}</code>\n"
            f"Pʟᴀɴ ➺ {get_styled_plan(ud['plan'])}\n"
            f"Lᴇꜰᴛ ➺ {int(rem // 86400)}d {int((rem % 86400) // 3600)}h\n"
            f"━━━━━━━━━━━━━━━━━\n"
        )
    if len(txt) > MAX_MSG:
        for i in range(0, len(txt), MAX_MSG):
            await update.message.reply_text(txt[i:i+MAX_MSG], parse_mode="HTML")
    else:
        await update.message.reply_text(txt, parse_mode="HTML")

async def cmd_seturl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if len(context.args) < 2:
        await update.message.reply_text("Uꜱᴀɢᴇ: /seturl &lt;gate&gt; &lt;url&gt;", parse_mode="HTML"); return
    gate = context.args[0].lower()
    url  = context.args[1]
    if gate not in GATE_URLS:
        await update.message.reply_text("Invalid gate."); return
    context.bot_data[f"gate_url_{gate}"] = url
    await update.message.reply_text(f"URL set for gate [{gate}].")

async def cmd_geturl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    lines = ["[ 𖥷iТ ] Gate URLs\n━━━━━━━━━━━━━━━━━"]
    for gate in GATE_URLS:
        url = context.bot_data.get(f"gate_url_{gate}") or GATE_URLS.get(gate) or "NOT SET"
        lines.append(f"{gate.upper()} ➺ <code>{url}</code>")
    lines.append("━━━━━━━━━━━━━━━━━")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    text = " ".join(context.args).strip() if context.args else ""
    if not text:
        await update.message.reply_text("Uꜱᴀɢᴇ: /broadcast &lt;message&gt;", parse_mode="HTML"); return

    all_users  = context.bot_data.get("user_data", {})
    status_msg = await update.message.reply_text("Broadcasting...")
    sent = 0; failed = 0; blocked = 0

    broadcast_text = (
        f"[ 𖥷iТ ] Batman Announcement\n━━━━━━━━━━━━━━━━━\n"
        f"{text}\n━━━━━━━━━━━━━━━━━\n"
        f"Pʀᴏ ➺ <a href='{BOT_LINK}'>Batman Card Checker</a>"
    )

    chan_ok = False
    try:
        await context.bot.send_message(
            chat_id=CHANNEL_USERNAME, text=broadcast_text,
            parse_mode="HTML", disable_web_page_preview=True)
        chan_ok = True
    except Exception as e:
        logger.warning(f"Broadcast channel failed: {e}")

    for uid_str in list(all_users.keys()):
        try:
            await context.bot.send_message(
                chat_id=int(uid_str), text=broadcast_text,
                parse_mode="HTML", disable_web_page_preview=True)
            sent += 1
        except Exception as e:
            err = str(e).lower()
            if "blocked" in err or "deactivated" in err or "not found" in err: blocked += 1
            else: failed += 1
        await asyncio.sleep(0.05)

    await status_msg.edit_text(
        f"[ 𖥷iТ ] Bʀᴏᴀᴅᴄᴀꜱᴛ\n━━━━━━━━━━━━━━━━━\n"
        f"Cʜᴀɴɴᴇʟ ➺ {'✅' if chan_ok else '❌'}\n━━━━━━━━━━━━━━━━━\n"
        f"Sᴇɴᴛ    ➺ {sent}\nBʟᴏᴄᴋᴇᴅ ➺ {blocked}\nFᴀɪʟᴇᴅ  ➺ {failed}\n━━━━━━━━━━━━━━━━━"
    )

async def cmd_killbot(update, context):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data["maintenance"] = True
    await update.message.reply_text("Bot is now in maintenance mode.")

async def cmd_onbot(update, context):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data["maintenance"] = False
    await update.message.reply_text("Bot is back online.")

async def _gate_toggle(update, context, gate: str, state: bool):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data[f"{gate}_on"] = state
    await update.message.reply_text(f"Gate [{gate}] turned {'ON' if state else 'OFF'}.")

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
# CALLBACK HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data  = query.data
    user  = query.from_user

    try:
        await query.answer()
    except Exception:
        pass

    async def edit(text: str, markup: InlineKeyboardMarkup):
        try:
            await query.message.edit_text(
                text=text, parse_mode="HTML",
                reply_markup=markup, disable_web_page_preview=True)
        except BadRequest as e:
            if "message is not modified" in str(e).lower():
                return
            try:
                await query.message.edit_caption(caption=text, parse_mode="HTML", reply_markup=markup)
            except Exception:
                await context.bot.send_message(
                    chat_id=query.message.chat_id, text=text,
                    parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)

    ud      = get_user_data(user.id, context)
    premium = is_user_premium(ud)

    if data == "check_sub":
        not_joined = await check_force_sub(user.id, context)
        if not_joined:
            try:
                await query.answer(
                    "❌ You haven't joined all channels/groups yet!\n"
                    "Join them and press Verify again.", show_alert=True)
            except Exception:
                pass
            try:
                await query.message.edit_reply_markup(reply_markup=kb_force_sub(not_joined))
            except Exception:
                pass
        else:
            try:
                await query.answer("✅ Verified! Welcome.", show_alert=False)
            except Exception:
                pass
            await edit(ui_profile(user, context), kb_main(user.id))
        return

    elif data == "bmain":
        await edit(ui_profile(user, context), kb_main(user.id))

    elif data == "mgates":
        await edit(
            "[ 𖥷iТ ] Sᴇʟᴇᴄᴛ Gᴀᴛᴇ Cᴀᴛᴇɢᴏʀʏ\n━━━━━━━━━━━━━━━━━\n"
            "Aᴜᴛʜ Gᴀᴛᴇꜱ   ➺ 1  (Free)\n"
            "Cʜᴀʀɢᴇ Gᴀᴛᴇꜱ ➺ 4  (Free)\n"
            "Pʀᴇᴍɪᴜᴍ Gᴀᴛᴇꜱ ➺ 3  (Premium)\n━━━━━━━━━━━━━━━━━",
            kb_gate_main())

    elif data == "mprice":
        await edit(
            "[ 𖥷iТ ] Batman Premium Plans\n━━━━━━━━━━━━━━━━━\n\n"
            "Aᴄᴄᴇꜱꜱ  ➺ Cᴏʀᴇ\nDᴀʏꜱ     ➺ 7\nCʀᴇᴅɪᴛꜱ ➺ Unlimited\nPʀɪᴄᴇ   ➺ 10$\n━━━━━━━━━━━━━━━━━\n"
            "Aᴄᴄᴇꜱꜱ  ➺ Eʟɪᴛᴇ\nDᴀʏꜱ     ➺ 15\nCʀᴇᴅɪᴛꜱ ➺ Unlimited\nPʀɪᴄᴇ   ➺ 15$\n━━━━━━━━━━━━━━━━━\n"
            "Aᴄᴄᴇꜱꜱ  ➺ Rᴏᴏᴛ\nDᴀʏꜱ     ➺ 30\nCʀᴇᴅɪᴛꜱ ➺ Unlimited\nPʀɪᴄᴇ   ➺ 30$\n━━━━━━━━━━━━━━━━━",
            kb_price())

    elif data == "mauth":
        await edit(
            "[ 𖥷iТ ] Auth Gates (Free)\n━━━━━━━━━━━━━━━━━\n\nBʀᴀɪɴᴛʀᴇᴇ Aᴜᴛʜ ➺ /b3\n━━━━━━━━━━━━━━━━━",
            kb_auth_gates())

    elif data == "mcharge":
        await edit(
            "[ 𖥷iТ ] Charge Gates (Free)\n━━━━━━━━━━━━━━━━━\n\n"
            "Sᴛʀɪᴘᴇ  ➺ /chk\nPᴀʏPᴀʟ  ➺ /pp\nSʜᴏᴘɪꜰʏ ➺ /sh\nPᴀʏU    ➺ /pyu\n━━━━━━━━━━━━━━━━━",
            kb_charge_gates())

    elif data == "mmass":
        if not premium:
            try: await query.answer("Premium Gates require a premium plan!", show_alert=True)
            except Exception: pass
            await edit(
                "[ 𖥷iТ ] Premium Gates\n━━━━━━━━━━━━━━━━━\n\n"
                "Upgrade: /plan", kb_upgrade())
            return
        await edit(
            "[ 𖥷iТ ] Premium Gates 👑\n━━━━━━━━━━━━━━━━━\n\n"
            "Sᴛʀɪᴘᴇ Aᴜᴛʜ ➺ /au\nSᴛʀɪᴘᴇ Mᴀꜱꜱ ➺ /mss\nPᴀʏPᴀʟ Mᴀꜱꜱ ➺ /mpp2\n━━━━━━━━━━━━━━━━━",
            kb_premium_gates())

    elif data == "mrefer":
        link       = get_referral_link(user.id)
        total_refs = ud.get("total_refs", 0)
        await edit(
            f"[ 𖥷iТ ] Rᴇꜰᴇʀʀᴀʟ\n━━━━━━━━━━━━━━━━━\n"
            f"Lɪɴᴋ    ➺ <code>{link}</code>\n━━━━━━━━━━━━━━━━━\n"
            f"Rᴇꜰᴇʀʀᴀʟꜱ ➺ {total_refs}\nEᴀʀɴᴇᴅ ➺ {total_refs * REFERRAL_CREDITS} credits\n"
            f"Pᴇʀ Rᴇꜰ ➺ +{REFERRAL_CREDITS} credits\n━━━━━━━━━━━━━━━━━\nShare your link!",
            kb_back("bmain"))

    elif data == "iau":
        if not premium:
            try: await query.answer("Stripe Auth is Premium only!", show_alert=True)
            except Exception: pass
            return
        await edit(gate_info_text("STRIPE AUTH 👑", "au", 1), kb_back("mmass"))

    elif data == "ib3":   await edit(gate_info_text("BRAINTREE AUTH", "b3",  1), kb_back("mauth"))
    elif data == "ichk":  await edit(gate_info_text("STRIPE CHARGE",  "chk", 1), kb_back("mcharge"))
    elif data == "ipp":   await edit(gate_info_text("PAYPAL CHARGE",  "pp",  1), kb_back("mcharge"))
    elif data == "ish":   await edit(gate_info_text("SHOPIFY CHARGE", "sh",  1), kb_back("mcharge"))
    elif data == "ipyu":  await edit(gate_info_text("PAYU CHARGE",    "pyu", 1), kb_back("mcharge"))

    elif data == "imss":
        if not premium:
            try: await query.answer("Stripe Mass is Premium only!", show_alert=True)
            except Exception: pass
            return
        await edit(gate_info_text("STRIPE MASS 👑", "mss", 2), kb_back("mmass"))

    elif data == "impp2":
        if not premium:
            try: await query.answer("PayPal Mass is Premium only!", show_alert=True)
            except Exception: pass
            return
        await edit(gate_info_text("PAYPAL MASS 👑", "mpp2", 2), kb_back("mmass"))

    elif data in ("pay10", "pay15", "pay30"):
        await edit(
            "[ 𖥷iТ ] Payment\n━━━━━━━━━━━━━━━━━\n\n"
            "To purchase a premium plan, contact support.\n\n━━━━━━━━━━━━━━━━━",
            kb_payment())

    elif data.startswith("fb_ok_") or data.startswith("fb_no_"):
        if query.from_user.id != OWNER_ID:
            try: await query.answer("Owner only.", show_alert=True)
            except Exception: pass
            return
        key = data[len("fb_ok_"):] if data.startswith("fb_ok_") else data[len("fb_no_"):]
        if data.startswith("fb_ok_"):
            await _fb_approve(query, context, key)
        else:
            await _fb_decline(query, context, key)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GLOBAL ERROR HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_conflict_shutting_down = False

async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    global _conflict_shutting_down
    error = context.error
    if isinstance(error, Conflict):
        if _conflict_shutting_down: return
        _conflict_shutting_down = True
        logger.critical("CONFLICT: Another bot instance is running. Waiting before exit...")
        if context.application and hasattr(context.application, "updater") and context.application.updater:
            try: await context.application.updater.stop()
            except Exception: pass
        await asyncio.sleep(45)
        release_instance_lock()
        os._exit(1)
        return
    if isinstance(error, NetworkError):
        logger.warning(f"Network error (auto-retry): {error}")
        return
    logger.error(f"Unhandled error: {type(error).__name__}: {error}", exc_info=context.error)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# POST-INIT / POST-SHUTDOWN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def post_init(application: Application) -> None:
    logger.info("Cleaning up any existing webhook...")
    for attempt in range(3):
        try:
            await application.bot.delete_webhook(drop_pending_updates=True)
            logger.info("Webhook deleted.")
            break
        except Exception as e:
            logger.warning(f"Webhook cleanup attempt {attempt+1}: {e}")
            await asyncio.sleep(2)
    try:
        await application.bot.get_updates(offset=-1, timeout=0, limit=1)
        logger.info("Update slot claimed.")
    except Exception as e:
        logger.warning(f"Update slot claim: {e}")
    await asyncio.sleep(2)

async def post_shutdown(application: Application) -> None:
    logger.info("Bot shutting down cleanly...")
    release_instance_lock()
    try:
        await application.bot.delete_webhook(drop_pending_updates=False)
    except Exception:
        pass

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def main():
    if not acquire_instance_lock():
        logger.critical("Another Batman Bot instance is already running. Exiting.")
        os._exit(1)

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .concurrent_updates(True)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    app.add_error_handler(global_error_handler)

    # User commands
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("ping",   cmd_ping))
    app.add_handler(CommandHandler("plan",   cmd_plan))
    app.add_handler(CommandHandler("rm",     cmd_rm))
    app.add_handler(CommandHandler("bin",    cmd_bin))
    app.add_handler(CommandHandler("refer",  cmd_refer))
    app.add_handler(CommandHandler("fb",     cmd_fb))

    # Gate commands
    app.add_handler(CommandHandler("chk",  cmd_chk))
    app.add_handler(CommandHandler("pp",   cmd_pp))
    app.add_handler(CommandHandler("sh",   cmd_sh))
    app.add_handler(CommandHandler("pyu",  cmd_pyu))
    app.add_handler(CommandHandler("b3",   cmd_b3))
    app.add_handler(CommandHandler("au",   cmd_au))
    app.add_handler(CommandHandler("mss",  cmd_mss))
    app.add_handler(CommandHandler("mpp2", cmd_mpp2))

    # Owner commands
    app.add_handler(CommandHandler("info",       cmd_info))
    app.add_handler(CommandHandler("find",       cmd_find))
    app.add_handler(CommandHandler("allcm",      cmd_allcm))
    app.add_handler(CommandHandler("gen",        cmd_gen))
    app.add_handler(CommandHandler("key10",      cmd_key10))
    app.add_handler(CommandHandler("key20",      cmd_key20))
    app.add_handler(CommandHandler("key30",      cmd_key30))
    app.add_handler(CommandHandler("oneday",     cmd_oneday))
    app.add_handler(CommandHandler("threeday",   cmd_threeday))
    app.add_handler(CommandHandler("sub",        cmd_sub))
    app.add_handler(CommandHandler("resub",      cmd_resub))
    app.add_handler(CommandHandler("addcredits", cmd_addcredits))
    app.add_handler(CommandHandler("allplans",   cmd_allplans))
    app.add_handler(CommandHandler("seturl",     cmd_seturl))
    app.add_handler(CommandHandler("geturl",     cmd_geturl))
    app.add_handler(CommandHandler("broadcast",  cmd_broadcast))
    app.add_handler(CommandHandler("killbot",    cmd_killbot))
    app.add_handler(CommandHandler("onbot",      cmd_onbot))

    for cmd, func in [
        ("onchk",  cmd_onchk),  ("offchk",  cmd_offchk),
        ("onpp",   cmd_onpp),   ("offpp",   cmd_offpp),
        ("onsh",   cmd_onsh),   ("offsh",   cmd_offsh),
        ("onpyu",  cmd_onpyu),  ("offpyu",  cmd_offpyu),
        ("onb3",   cmd_onb3),   ("offb3",   cmd_offb3),
        ("onau",   cmd_onau),   ("offau",   cmd_offau),
        ("onmss",  cmd_onmss),  ("offmss",  cmd_offmss),
        ("onmpp2", cmd_onmpp2), ("offmpp2", cmd_offmpp2),
    ]:
        app.add_handler(CommandHandler(cmd, func))

    # Register Mass Handlers (from mass.py)
    for handler in get_mass_handlers():  # <-- ADDED MASS HANDLER REGISTRATION
        app.add_handler(handler)

    app.add_handler(CallbackQueryHandler(callback_handler))

    app.add_handler(MessageHandler(
        (filters.PHOTO | filters.VIDEO) & filters.CaptionRegex(r"(?i)^/fb"),
        handle_fb_media,
    ))

    logger.info(f"Batman Bot {VERSION} starting — @{BOT_USERNAME}")
    app.run_polling(
        drop_pending_updates=True,
        close_loop=False,
        stop_signals=(signal.SIGINT, signal.SIGTERM),
    )

if __name__ == "__main__":
    main()
