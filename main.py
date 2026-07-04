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

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOGGING & CONFIG
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
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
    return "👑" if raw_plan.upper() in ("CORE", "ELITE", "ROOT") else ""

def get_user_data(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> dict:
    uid = str(user_id)
    if "user_data" not in context.bot_data: context.bot_data["user_data"] = {}
    if uid not in context.bot_data["user_data"]:
        context.bot_data["user_data"][uid] = {
            "name": "User", "first_name": "User", "last_name": "", "username": "",
            "language_code": "en", "joined": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "last_active": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "credits": 150, "plan": "TRIAL", "expires": 0, "pre_premium_credits": 0,
            "total_refs": 0, "total_checks": 0, "approved_checks": 0, "declined_checks": 0,
            "last_gate": "N/A", "last_card": "N/A", "codes_redeemed": 0, "keys_redeemed": 0,
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
    is_prem = raw_plan != "TRIAL"
    if is_prem and ud.get("expires", 0) <= time.time():
        ud["plan"] = "TRIAL"
        ud["credits"] = ud.get("pre_premium_credits", 150)
        ud["expires"] = 0
        ud["pre_premium_credits"] = 0
        return False
    return is_prem

def gen_code(length: int = 10) -> str: return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))
def gen_receipt() -> str: return f"Batman{random.randint(100000, 999999)}-CHK"
def get_referral_link(user_id: int) -> str: return f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"

def ui_profile(user, context: ContextTypes.DEFAULT_TYPE) -> str:
    ud       = get_user_data(user.id, context)
    raw_plan = ud.get("plan", "TRIAL").upper()
    expires  = ud.get("expires", 0)
    now      = time.time()
    if raw_plan != "TRIAL" and expires <= now:
        raw_plan = "TRIAL"; ud["plan"] = "TRIAL"; ud["expires"] = 0; expires = 0
    premium    = raw_plan != "TRIAL"
    credits    = "Unlimited" if premium else str(ud.get("credits", 150))
    
    # Escape user input to prevent HTML crashes
    uname = escape(f"@{user.username}" if user.username else user.first_name or "User")
    total_refs = ud.get("total_refs", 0)
    plan_icon  = get_plan_icon(raw_plan)

    lines = [
        f"━━━━━━━━━━━━━━━━━",
        f"<b>Uꜱᴇʀ</b>    ➺ {uname} {plan_icon}".rstrip(),
        f"<b>ID</b>      ➺ <code>{user.id}</code>",
        f"<b>Aᴄᴄᴇꜱꜱ</b>  ➺ {get_styled_plan(raw_plan)}",
        f"<b>Cʀᴇᴅɪᴛꜱ</b> ➺ {credits}",
    ]
    if premium and expires > now:
        exp_date = datetime.fromtimestamp(expires).strftime("%Y-%m-%d %H:%M")
        rem_d    = int((expires - now) / 86400)
        rem_h    = int(((expires - now) % 86400) / 3600)
        lines.append(f"<b>Exᴘɪʀᴇꜱ</b> ➺ {exp_date}")
        lines.append(f"<b>Lᴇꜰᴛ</b>    ➺ {rem_d}d {rem_h}h")
        receipt = ud.get("last_receipt")
        if receipt: lines.append(f"<b>Rᴇᴄᴇɪᴘᴛ</b> ➺ <code>{receipt}</code>")
    lines.append(f"<b>Rᴇꜰᴇʀʀᴀʟꜱ</b> ➺ {total_refs} (+{total_refs * REFERRAL_CREDITS} credits)")
    lines.append(f"<b>Jᴏɪɴᴇᴅ</b>  ➺ {ud.get('joined', datetime.now().strftime('%Y-%m-%d'))}")
    lines.append(f"<b>Dᴇᴠ</b>     ➺ <a href='{DEV_LINK}'>Batman</a> | {VERSION}")
    lines.append("━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)

def gate_info_text(gate_name: str, cmd: str, cost: int) -> str:
    return (
        f"━━━━━━━━━━━━━━━━━\n<b>{gate_name}</b>\n━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Cᴏsᴛ</b>    ➺ {cost} Credit(s) per check\n\n"
        f"<b>Uꜱᴀɢᴇ:</b>\n<code>/{cmd} cc|mm|yy|cvv</code>\n\n"
        f"<b>Exᴀᴍᴘʟᴇ:</b>\n<code>/{cmd} 4111111111111111|12|2026|123</code>\n\n"
        f"━━━━━━━━━━━━━━━━━"
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FORCE SUBSCRIBE (WITH 5-MIN CACHE FOR ULTRA SPEED)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_force_sub_cache = {} # uid -> (bool is_joined, timestamp)

async def check_force_sub(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> list:
    if user_id == OWNER_ID: return []
    
    cached = _force_sub_cache.get(user_id)
    if cached and time.time() - cached[1] < 300:
        if cached[0]:
            return []
            
    not_joined = []
    for name, link in FORCE_CHANNELS:
        try:
            member = await context.bot.get_chat_member(f"@{name}", user_id)
            if member.status in ("left", "kicked"): not_joined.append((name, link))
        except Exception: not_joined.append((name, link))
    
    if not not_joined:
        _force_sub_cache[user_id] = (True, time.time())
        
    return not_joined

def kb_force_sub(not_joined: list) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(f"➺ Join @{name}", url=link)] for name, link in not_joined]
    rows.append([InlineKeyboardButton("✅ I Joined — Verify Now", callback_data="check_sub")])
    return InlineKeyboardMarkup(rows)

FORCE_SUB_TEXT = (
    "<b>[ 𖥷iТ ] ➺ Jᴏɪɴ Rᴇǫᴜɪʀᴇᴅ</b>\n"
    "━━━━━━━━━━━━━━━━━\n"
    "You must join our channel & group to use this bot.\n"
    "After joining press the ✅ Verify button below.\n"
    "━━━━━━━━━━━━━━━━━"
)

async def require_membership(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id    = update.effective_user.id
    not_joined = await check_force_sub(user_id, context)
    if not_joined:
        await update.message.reply_text(FORCE_SUB_TEXT, reply_markup=kb_force_sub(not_joined), parse_mode="HTML")
        return False
    return True

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CARD CHECK RESULT UI & DYNAMIC BUTTONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def kb_result(is_premium: bool) -> InlineKeyboardMarkup:
    if is_premium:
        return InlineKeyboardMarkup([[InlineKeyboardButton("Batcardchk", url=CHANNEL_LINK)]])
    else:
        return InlineKeyboardMarkup([[InlineKeyboardButton(B("BUY NOW"), callback_data="mprice")]])

def build_check_result(card_raw: str, gate_name: str, raw_response: str, bin_data: dict, username: str, plan: str, time_taken: str, is_approved: bool, is_timeout: bool = False, is_error: bool = False) -> str:
    if is_timeout: status = "Tɪᴍᴇᴏᴜᴛ"
    elif is_error: status = "Eʀʀᴏʀ"
    elif is_approved: status = "Aᴘᴘʀᴏᴠᴇᴅ"
    else: status = "Dᴇᴄʟɪɴᴇᴅ"

    plan_icon  = get_plan_icon(plan)
    plan_label = get_styled_plan(plan)
    bin_txt = "N/A"
    if bin_data and not bin_data.get("error"):
        scheme  = str(bin_data.get("scheme",  "N/A")).upper()
        bank    = bin_data.get("bank",    "N/A")
        country = str(bin_data.get("country", "N/A")).upper()
        flag    = bin_data.get("country_emoji", "")
        bin_txt = f"{scheme} - {bank} - {flag} {country}".strip()

    uname_display = f"{escape(username)} {plan_icon} ({plan_label})".strip()
    lines = [
        f"<b>[ 𖥷iТ ] ➺ {status}</b>",
        f"🔍 ➺ <code>{card_raw}</code>",
        f"<b>Gᴀᴛᴇ</b> ➺ {gate_name} 💳",
        f"<b>Rᴀᴡ</b>  ➺ {escape(raw_response)}",
        f"<b>Iɴꜰᴏ</b> ➺ {bin_txt}",
        f"<b>Uꜱᴇʀ</b> ➺ {uname_display}",
        f"<b>Pʀᴏ</b>  ➺ Batman | {time_taken}s",
        "━━━━━━━━━━━━━━━━━",
        "📢 @Batcardchk"
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
async def process_referral(new_user_id: int, referrer_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if new_user_id == referrer_id: return False
    referred_set = context.bot_data.setdefault("referred_users", set())
    if new_user_id in referred_set: return False
    referrer_ud = context.bot_data.get("user_data", {}).get(str(referrer_id))
    if referrer_ud is None: return False
    referred_set.add(new_user_id)
    referrer_ud["credits"]    = referrer_ud.get("credits", 0) + REFERRAL_CREDITS
    referrer_ud["total_refs"] = referrer_ud.get("total_refs", 0) + 1
    try:
        await context.bot.send_message(chat_id=referrer_id, text=(f"<b>Rᴇꜰᴇʀʀᴀʟ Bᴏɴᴜꜱ</b>\n━━━━━━━━━━━━━━━━━\nSomeone joined via your link!\n<b>Cʀᴇᴅɪᴛꜱ Aᴅᴅᴇᴅ</b>    ➺ +{REFERRAL_CREDITS}\n<b>Tᴏᴛᴀʟ Rᴇꜰᴇʀʀᴀʟꜱ</b> ➺ {referrer_ud['total_refs']}\n━━━━━━━━━━━━━━━━━"), parse_mode="HTML")
    except Exception: pass
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

async def process_gate(update: Update, context: ContextTypes.DEFAULT_TYPE, gate_key: str, gate_name: str):
    user = update.effective_user
    if context.bot_data.get("maintenance") and user.id != OWNER_ID:
        await update.message.reply_text("Bot is under maintenance."); return
    if not context.bot_data.get(f"{gate_key}_on", True):
        await update.message.reply_text(f"Gate [{gate_name}] is currently OFF."); return

    if not await require_membership(update, context): return

    ud      = get_user_data(user.id, context)
    premium = is_user_premium(ud)
    _update_user_meta(ud, user)

    if gate_key in PREMIUM_GATES and not premium:
        await update.message.reply_text(f"<b>[ 𖥷iТ ] ➺ Pʀᴇᴍɪᴜᴍ Oɴʟʏ</b>\n━━━━━━━━━━━━━━━━━\nUse /plan to upgrade.", parse_mode="HTML", reply_markup=kb_upgrade())
        return

    card_raw = None
    if context.args: card_raw = context.args[0].strip()
    elif update.message.reply_to_message and update.message.reply_to_message.text: card_raw = update.message.reply_to_message.text.strip()

    if not card_raw:
        await update.message.reply_text(f"Uꜱᴀɢᴇ: <code>/{gate_key} cc|mm|yy|cvv</code>", parse_mode="HTML"); return

    if not premium:
        credits = ud.get("credits", 0)
        if credits <= 0:
            await update.message.reply_text("<b>[ 𖥷iТ ] ➺ Nᴏ Cʀᴇᴅɪᴛꜱ</b>\n━━━━━━━━━━━━━━━━━\nBuy a plan: /plan", reply_markup=kb_upgrade(), parse_mode="HTML"); return
        ud["credits"] = credits - 1

    api_url  = context.bot_data.get(f"gate_url_{gate_key}") or GATE_URLS.get(gate_key, "")
    site_url = GATE_SITES.get(gate_key, "example.com")
    bin_num  = card_raw[:6]

    if not api_url:
        await update.message.reply_text(f"Gate API not set.", parse_mode="HTML"); return

    msg        = await update.message.reply_text("[ 𖥷iТ ] ➺ Sᴄᴀɴɴɪɴɢ...")
    start_time = time.time()
    uname = f"@{user.username}" if user.username else user.first_name or "User"
    plan  = ud.get("plan", "TRIAL")

    try:
        timeout = _aiohttp.ClientTimeout(total=API_TIMEOUT)
        async with _aiohttp.ClientSession(timeout=timeout) as session:
            results = await asyncio.gather(_api_request(session, api_url, card_raw, site_url), get_bin_info(bin_num), return_exceptions=True)
        data     = results[0] if not isinstance(results[0], Exception) else {}
        bin_data = results[1] if not isinstance(results[1], Exception) else {"error": True}
        if isinstance(results[0], Exception): raise results[0]

        raw_response = str(data.get("value") or data.get("message") or data.get("Response") or data.get("category") or "ERROR").strip()
        is_approved = any(w in raw_response.lower() for w in ["approved", "captured", "success", "charged", "true"])

        ud["total_checks"]    = ud.get("total_checks", 0) + 1
        ud["last_gate"]       = gate_name
        ud["last_card"]       = card_raw[:6] + "xxxxxxxxxx"
        ud["last_active"]     = datetime.now().strftime("%Y-%m-%d %H:%M")
        if is_approved: ud["approved_checks"] = ud.get("approved_checks", 0) + 1
        else: ud["declined_checks"] = ud.get("declined_checks", 0) + 1

        time_taken = f"{time.time() - start_time:.2f}"
        text = build_check_result(card_raw=card_raw, gate_name=gate_name, raw_response=raw_response, bin_data=bin_data, username=uname, plan=plan, time_taken=time_taken, is_approved=is_approved)
        await msg.edit_text(text, parse_mode="HTML", reply_markup=kb_result(premium), disable_web_page_preview=True)

    except asyncio.TimeoutError:
        if not premium: ud["credits"] = ud.get("credits", 0) + 1
        time_taken = f"{time.time() - start_time:.2f}"
        text = build_check_result(card_raw=card_raw, gate_name=gate_name, raw_response="Rᴇǫᴜᴇꜱᴛ Tɪᴍᴇᴏᴜᴛ", bin_data={}, username=uname, plan=plan, time_taken=time_taken, is_approved=False, is_timeout=True)
        await msg.edit_text(text, parse_mode="HTML", reply_markup=kb_result(premium), disable_web_page_preview=True)
    except Exception as e:
        if not premium: ud["credits"] = ud.get("credits", 0) + 1
        logger.error(f"Gate [{gate_key}] error: {e}")
        time_taken = f"{time.time() - start_time:.2f}"
        text = build_check_result(card_raw=card_raw, gate_name=gate_name, raw_response=str(e)[:120], bin_data={}, username=uname, plan=plan, time_taken=time_taken, is_approved=False, is_error=True)
        await msg.edit_text(text, parse_mode="HTML", reply_markup=kb_result(premium), disable_web_page_preview=True)

async def cmd_chk(u, c):  await process_gate(u, c, "chk",  "Stripe Charge")
async def cmd_pp(u, c):   await process_gate(u, c, "pp",   "PayPal Charge")
async def cmd_sh(u, c):   await process_gate(u, c, "sh",   "Shopify Charge")
async def cmd_pyu(u, c):  await process_gate(u, c, "pyu",  "PayU Charge")
async def cmd_b3(u, c):   await process_gate(u, c, "b3",   "Braintree Auth")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GATE ON/OFF CONTROLS (OWNER ONLY)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _gate_toggle(update, context, gate: str, state: bool):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data[f"{gate}_on"] = state
    await update.message.reply_text(f"Gate [{gate.upper()}] turned {'ON ✅' if state else 'OFF ❌'}.")

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
async def send_activation_msg(user_id: int, plan: str, days: int, context: ContextTypes.DEFAULT_TYPE) -> str:
    receipt  = gen_receipt()
    name, username = "Unknown", None
    try:
        chat     = await context.bot.get_chat(user_id)
        name     = chat.first_name or "Unknown"
        username = chat.username
    except Exception: pass

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

    txt = (f"<b>[ 𖥷iТ ] ➺ Aᴄᴄᴇꜱꜱ Aᴄᴛɪᴠᴀᴛᴇᴅ</b>\n━━━━━━━━━━━━━━━━━\n<b>Uꜱᴇʀ</b>     ➺ {display_name}\n<b>Aᴄᴄᴇꜱꜱ</b>  ➺ {styled} 👑\n<b>Dᴀʏꜱ</b>    ➺ {days}\n<b>Cʀᴇᴅɪᴛꜱ</b> ➺ Unlimited\n<b>Exᴘɪʀᴇꜱ</b> ➺ {exp_date}\n<b>Rᴇᴄᴇɪᴘᴛ</b> ➺ <code>{receipt}</code>\n━━━━━━━━━━━━━━━━━\nSave this receipt ID.\n<b>Pʀᴏ</b> ➺ Batman")
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

async def _grant(uid: int, plan: str, days: int, update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    except Exception: pass

    receipt    = await send_activation_msg(uid, plan, days, context)
    uname_line = f"@{display_uname}" if display_uname else display_name
    exp_date   = datetime.fromtimestamp(ud["expires"]).strftime("%Y-%m-%d %H:%M")

    await update.message.reply_text(f"━━━━━━━━━━━━━━━━━\n✅ <b>Pʀᴇᴍɪᴜᴍ Gʀᴀɴᴛᴇᴅ</b>\n━━━━━━━━━━━━━━━━━\n<b>Uꜱᴇʀ</b>     ➺ {uname_line}\n<b>ID</b>       ➺ <code>{uid}</code>\n<b>Pʟᴀɴ</b>     ➺ {get_styled_plan(plan)} 👑\n<b>Dᴀʏꜱ</b>     ➺ {days}\n<b>Exᴘɪʀᴇꜱ</b>  ➺ {exp_date}\n<b>Rᴇᴄᴇɪᴘᴛ</b>  ➺ <code>{receipt}</code>\n━━━━━━━━━━━━━━━━━", parse_mode="HTML")

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
            except Exception: pass

    not_joined = await check_force_sub(user.id, context)
    if not_joined:
        try:
            await update.message.reply_photo(photo=BOT_PHOTO_URL, caption=FORCE_SUB_TEXT, reply_markup=kb_force_sub(not_joined), parse_mode="HTML")
        except Exception:
            await update.message.reply_text(FORCE_SUB_TEXT, reply_markup=kb_force_sub(not_joined), parse_mode="HTML")
        return

    try:
        await update.message.reply_photo(photo=BOT_PHOTO_URL, caption=ui_profile(user, context), parse_mode="HTML", reply_markup=kb_main(user.id))
    except Exception:
        await update.message.reply_text(ui_profile(user, context), parse_mode="HTML", reply_markup=kb_main(user.id), disable_web_page_preview=True)

async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_membership(update, context): return
    t   = time.time()
    msg = await update.message.reply_text("[ 𖥷iТ ] ➺ Pɪɴɢɪɴɢ...")
    await msg.edit_text(f"<b>[ 𖥷iТ ] ➺ Pᴏɴɢ</b> | {int((time.time() - t) * 1000)}ms", parse_mode="HTML")

async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_membership(update, context): return
    txt = ("<b>[ 𖥷iТ ] Batman Premium Plans</b>\n━━━━━━━━━━━━━━━━━\n\n"
        "<b>Aᴄᴄᴇꜱꜱ</b>  ➺ Cᴏʀᴇ\n<b>Dᴀʏꜱ</b>     ➺ 7\n<b>Cʀᴇᴅɪᴛꜱ</b> ➺ Unlimited\n<b>Pʀɪᴄᴇ</b>   ➺ 10$\n━━━━━━━━━━━━━━━━━\n"
        "<b>Aᴄᴄᴇꜱꜱ</b>  ➺ Eʟɪᴛᴇ\n<b>Dᴀʏꜱ</b>     ➺ 15\n<b>Cʀᴇᴅɪᴛꜱ</b> ➺ Unlimited\n<b>Pʀɪᴄᴇ</b>   ➺ 15$\n━━━━━━━━━━━━━━━━━\n"
        "<b>Aᴄᴄᴇꜱꜱ</b>  ➺ Rᴏᴏᴛ\n<b>Dᴀʏꜱ</b>     ➺ 30\n<b>Cʀᴇᴅɪᴛꜱ</b> ➺ Unlimited\n<b>Pʀɪᴄᴇ</b>   ➺ 30$\n━━━━━━━━━━━━━━━━━")
    await update.message.reply_text(txt, reply_markup=kb_price(), parse_mode="HTML")

async def cmd_refer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_membership(update, context): return
    user = update.effective_user
    ud   = get_user_data(user.id, context)
    link = get_referral_link(user.id)
    total_refs = ud.get("total_refs", 0)
    txt = (f"<b>[ 𖥷iТ ] Rᴇꜰᴇʀʀᴀʟ</b>\n━━━━━━━━━━━━━━━━━\n<b>Lɪɴᴋ</b>    ➺ <code>{link}</code>\n━━━━━━━━━━━━━━━━━\n<b>Rᴇꜰᴇʀʀᴀʟꜱ</b> ➺ {total_refs}\n<b>Eᴀʀɴᴇᴅ</b>   ➺ {total_refs * REFERRAL_CREDITS} credits\n<b>Pᴇʀ Rᴇꜰ</b>  ➺ +{REFERRAL_CREDITS} credits\n━━━━━━━━━━━━━━━━━\nShare your link to earn free credits!")
    await update.message.reply_text(txt, parse_mode="HTML", reply_markup=kb_back("bmain"), disable_web_page_preview=True)

async def cmd_rm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_membership(update, context): return
    if not context.args:
        await update.message.reply_text("Uꜱᴀɢᴇ: /rm <code>CODE</code>", parse_mode="HTML"); return
    code  = context.args[0].upper()
    uid   = update.effective_user.id
    ud    = get_user_data(uid, context)
    codes = context.bot_data.get("codes", {})
    keys  = context.bot_data.get("keys",  {})
    if code in codes and not codes[code]["used"]:
        codes[code]["used"] = True
        ud["credits"]        = ud.get("credits", 0) + codes[code]["value"]
        ud["codes_redeemed"] = ud.get("codes_redeemed", 0) + 1
        await update.message.reply_text(f"Redeemed +{codes[code]['value']} credits\n<b>Cʀᴇᴅɪᴛꜱ</b> ➺ {ud['credits']}", parse_mode="HTML")
    elif code in keys and not keys[code]["used"]:
        keys[code]["used"] = True
        p, d    = keys[code]["plan"], keys[code]["days"]
        ud["keys_redeemed"] = ud.get("keys_redeemed", 0) + 1
        receipt = await send_activation_msg(uid, p, d, context)
        await update.message.reply_text(f"Activated {get_styled_plan(p)} for {d} days!\n<b>Rᴇᴄᴇɪᴘᴛ</b> ➺ <code>{receipt}</code>", parse_mode="HTML")
    else:
        await update.message.reply_text("Invalid or already used code.")

async def cmd_bin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_membership(update, context): return
    bin_num = context.args[0].strip()[:6] if context.args else None
    if not bin_num or not bin_num.isdigit() or len(bin_num) < 6:
        await update.message.reply_text("Uꜱᴀɢᴇ: <code>/bin 411111</code>", parse_mode="HTML"); return
    msg = await update.message.reply_text("[ 𖥷iТ ] ➺ Lᴏᴏᴋɪɴɢ ᴜᴘ...")
    try:
        bd = await get_bin_info(bin_num)
        if bd.get("error"):
            await msg.edit_text("BIN not found."); return
        txt = (f"<b>[ 𖥷iТ ] ➺ BIN Lookup</b>\n━━━━━━━━━━━━━━━━━\n<b>BIN</b>     ➺ <code>{bin_num}</code>\n<b>Scheme</b>  ➺ {str(bd.get('scheme', 'N/A')).upper()}\n<b>Type</b>    ➺ {str(bd.get('type', 'N/A')).upper()}\n<b>Bank</b>    ➺ {bd.get('bank', 'N/A')}\n<b>Country</b> ➺ {bd.get('country_emoji', '')} {str(bd.get('country', 'N/A')).upper()}\n━━━━━━━━━━━━━━━━━")
        await msg.edit_text(txt, parse_mode="HTML")
    except Exception as e:
        await msg.edit_text(f"Error: <code>{str(e)[:100]}</code>", parse_mode="HTML")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FEEDBACK SYSTEM  (/fb)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _fb_key(user_id: int) -> str:
    return f"{user_id}_{int(time.time())}_{random.randint(1000, 9999)}"

async def cmd_fb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_membership(update, context): return
    msg = update.message
    user = update.effective_user
    
    media_msg = None
    if msg.photo or msg.video:
        media_msg = msg
    elif msg.reply_to_message and (msg.reply_to_message.photo or msg.reply_to_message.video):
        media_msg = msg.reply_to_message

    if media_msg:
        if media_msg.photo:
            file_id, file_type = media_msg.photo[-1].file_id, "photo"
        elif media_msg.video:
            file_id, file_type = media_msg.video.file_id, "video"
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
        await msg.reply_text("━━━━━━━━━━━━━━━━━\n<b>Fᴇᴇᴅʙᴀᴄᴋ Sᴜʙᴍɪᴛᴛᴇᴅ ✅</b>\n━━━━━━━━━━━━━━━━━\nUnder review.\n━━━━━━━━━━━━━━━━━", parse_mode="HTML")

        owner_caption = f"<b>[ 𖥷iТ ] ➺ Nᴇᴡ Fᴇᴇᴅʙᴀᴄᴋ</b>\n━━━━━━━━━━━━━━━━━\n<b>Uꜱᴇʀ</b> ➺ {uname}\n<b>ID</b>   ➺ {user.id}\n<b>Dᴀᴛᴇ</b> ➺ {submitted}\n<b>Tʏᴘᴇ</b> ➺ {file_type.capitalize()}\n"
        if user_note: owner_caption += f"<b>Nᴏᴛᴇ</b> ➺ {user_note[:200]}\n"
        owner_caption += "━━━━━━━━━━━━━━━━━\nApprove to post to channel?"

        try:
            if file_type == "photo": await context.bot.send_photo(chat_id=OWNER_ID, photo=file_id, caption=owner_caption, reply_markup=kb_fb_owner(key), parse_mode="HTML")
            else: await context.bot.send_video(chat_id=OWNER_ID, video=file_id, caption=owner_caption, reply_markup=kb_fb_owner(key), parse_mode="HTML")
        except Exception as e: logger.error(f"Feedback notify owner failed: {e}")
        return

    await msg.reply_text("━━━━━━━━━━━━━━━━━\n📸 <b>Fᴇᴇᴅʙᴀᴄᴋ</b>\n━━━━━━━━━━━━━━━━━\n\nReply to a photo/video with <code>/fb</code>\nOR send photo/video with <code>/fb</code> as caption\n━━━━━━━━━━━━━━━━━", parse_mode="HTML")

async def _fb_approve(query, context: ContextTypes.DEFAULT_TYPE, key: str):
    fb = context.bot_data.get("fb_pending", {}).get(key)
    if not fb: await query.answer("Already handled.", show_alert=True); return
    uname, uid, submitted, file_id, file_type, user_note = fb["username"], fb["user_id"], fb["date"], fb["file_id"], fb["file_type"], fb.get("note", "")
    channel_caption = "━━━━━━━━━━━━━━━━━\n"
    if user_note: channel_caption += f"{user_note}\n━━━━━━━━━━━━━━━━━\n"
    channel_caption += f"<b>Uꜱᴇʀ</b> ➺ {uname}\n<b>ID</b>   ➺ {uid}\n<b>Dᴀᴛᴇ</b> ➺ {submitted}\n━━━━━━━━━━━━━━━━━"
    posted = False
    try:
        if file_type == "photo": await context.bot.send_photo(chat_id=CHANNEL_USERNAME, photo=file_id, caption=channel_caption, parse_mode="HTML")
        else: await context.bot.send_video(chat_id=CHANNEL_USERNAME, video=file_id, caption=channel_caption, parse_mode="HTML")
        posted = True
    except Exception as e: logger.error(f"Feedback channel post failed: {e}")
    context.bot_data["fb_pending"].pop(key, None)
    try: await query.message.edit_caption(caption=f"<b>[ 𖥷iТ ] ➺ Fᴇᴇᴅʙᴀᴄᴋ Aᴘᴘʀᴏᴠᴇᴅ</b>\n━━━━━━━━━━━━━━━━━\n{'✅ Posted' if posted else '⚠️ Post failed'}\n━━━━━━━━━━━━━━━━━", reply_markup=None, parse_mode="HTML")
    except Exception: pass
    try: await context.bot.send_message(chat_id=uid, text=f"<b>[ 𖥷iТ ] ➺ Fᴇᴇᴅʙᴀᴄᴋ Aᴄᴄᴇᴘᴛᴛᴇᴅ ✅</b>\n━━━━━━━━━━━━━━━━━\nPosted to channel!\n📢 {CHANNEL_LINK}\n━━━━━━━━━━━━━━━━━", parse_mode="HTML")
    except Exception: pass

async def _fb_decline(query, context: ContextTypes.DEFAULT_TYPE, key: str):
    fb = context.bot_data.get("fb_pending", {}).get(key)
    if not fb: await query.answer("Already handled.", show_alert=True); return
    uid = fb["user_id"]
    context.bot_data["fb_pending"].pop(key, None)
    try: await query.message.edit_caption(caption=f"<b>[ 𖥷iТ ] ➺ Fᴇᴇᴅʙᴀᴄᴋ Dᴇᴄʟɪɴᴇᴅ ❌</b>\n━━━━━━━━━━━━━━━━━", reply_markup=None, parse_mode="HTML")
    except Exception: pass
    try: await context.bot.send_message(chat_id=uid, text="<b>[ 𖥷iТ ] ➺ Fᴇᴇᴅʙᴀᴄᴋ Dᴇᴄʟɪɴᴇᴅ ❌</b>\n━━━━━━━━━━━━━━━━━", parse_mode="HTML")
    except Exception: pass

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# OWNER COMMANDS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    target_id, target_name, target_username, target_last_name, target_lang = None, "N/A", None, "", "N/A"

    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        ru = update.message.reply_to_message.from_user
        target_id, target_name, target_last_name, target_username, target_lang = ru.id, ru.first_name or "N/A", ru.last_name or "", ru.username, ru.language_code or "N/A"
    elif context.args:
        raw = " ".join(context.args).strip().lstrip("@")
        if raw.lstrip("-").isdigit(): target_id = int(raw)
        else:
            try:
                chat = await context.bot.get_chat(f"@{raw}")
                target_id, target_name, target_last_name, target_username = chat.id, chat.first_name or "N/A", getattr(chat, "last_name", "") or "", chat.username
            except Exception: pass
            if not target_id:
                raw_lower = raw.lower()
                for uid_str, ud in context.bot_data.get("user_data", {}).items():
                    if raw_lower in ud.get("username", "").lower().lstrip("@") or raw_lower in ud.get("name", "").lower():
                        target_id, target_name, target_username, target_lang = int(uid_str), ud.get("name", "N/A"), ud.get("username"), ud.get("language_code", "N/A")
                        break

    if not target_id: await update.message.reply_text("Uꜱᴀɢᴇ: /info @username | /info 123456789 | reply → /info"); return

    if target_name == "N/A":
        try:
            chat = await context.bot.get_chat(target_id)
            target_name, target_last_name, target_username = chat.first_name or "N/A", getattr(chat, "last_name", "") or "", chat.username
        except Exception: pass

    uid_str = str(target_id)
    now = time.time()
    udata = context.bot_data.get("user_data", {}).get(uid_str, {})
    raw_plan = udata.get("plan", "TRIAL").upper()
    expires = udata.get("expires", 0)
    if raw_plan != "TRIAL" and expires <= now: raw_plan = "TRIAL"; expires = 0
    premium = raw_plan != "TRIAL" and expires > now
    credits_d = "Unlimited" if premium else str(udata.get("credits", 150))

    full_name = f"{target_name} {target_last_name}".strip()
    uname_d = f"@{target_username}" if target_username else "None"
    lang_d = udata.get("language_code", target_lang) or "N/A"
    total_refs, total_checks, approved_checks, declined_checks = udata.get("total_refs", 0), udata.get("total_checks", 0), udata.get("approved_checks", 0), udata.get("declined_checks", 0)
    approval_rate = f"{(approved_checks / total_checks * 100):.1f}%" if total_checks > 0 else "N/A"

    txt = (f"<b>[ 𖥷iТ ] Uꜱᴇʀ Iɴꜰᴏ</b>\n━━━━━━━━━━━━━━━━━\n<b>Nᴀᴍᴇ</b>       ➺ {full_name}\n<b>Uꜱᴇʀɴᴀᴍᴇ</b>  ➺ {uname_d}\n<b>ID</b>         ➺ <code>{target_id}</code>\n<b>Lᴀɴɢ</b>       ➺ {lang_d.upper()}\n━━━━━━━━━━━━━━━━━\n<b>Pʟᴀɴ</b>       ➺ {get_styled_plan(raw_plan)}\n<b>Cʀᴇᴅɪᴛꜱ</b>   ➺ {credits_d}\n<b>Sᴛᴀᴛᴜꜱ</b>    ➺ {'Active' if premium else 'Trial'}\n")
    if premium and expires > now:
        rem = expires - now
        txt += f"<b>Exᴘɪʀᴇꜱ</b>   ➺ {datetime.fromtimestamp(expires).strftime('%Y-%m-%d %H:%M')}\n<b>Rᴇᴍᴀɪɴɪɴɢ</b> ➺ {int(rem // 86400)}d {int((rem % 86400) // 3600)}h\n"
    last_receipt = udata.get("last_receipt")
    if last_receipt: txt += f"<b>Rᴇᴄᴇɪᴘᴛ</b>   ➺ <code>{last_receipt}</code>\n"
    txt += (f"━━━━━━━━━━━━━━━━━\n<b>Jᴏɪɴᴇᴅ</b>      ➺ {udata.get('joined', 'N/A')}\n<b>Lᴀsᴛ Aᴄᴛɪᴠᴇ</b> ➺ {udata.get('last_active', 'N/A')}\n━━━━━━━━━━━━━━━━━\n<b>Tᴏᴛᴀʟ Cʜᴇᴄᴋꜱ</b> ➺ {total_checks}\n<b>Aᴘᴘʀᴏᴠᴇᴅ</b>     ➺ {approved_checks}\n<b>Dᴇᴄʟɪɴᴇᴅ</b>     ➺ {declined_checks}\n<b>Rᴀᴛᴇ</b>         ➺ {approval_rate}\n<b>Lᴀsᴛ Gᴀᴛᴇ</b>   ➺ {udata.get('last_gate', 'N/A')}\n<b>Lᴀsᴛ BIN</b>    ➺ <code>{udata.get('last_card', 'N/A')}</code>\n━━━━━━━━━━━━━━━━━\n<b>Rᴇꜰᴇʀʀᴀʟꜱ</b>   ➺ {total_refs}\n<b>Cᴏᴅᴇꜱ</b>        ➺ {udata.get('codes_redeemed', 0)} redeemed\n<b>Kᴇʏꜱ</b>         ➺ {udata.get('keys_redeemed', 0)} redeemed\n━━━━━━━━━━━━━━━━━")
    await update.message.reply_text(txt, parse_mode="HTML")

async def cmd_allcm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    await update.message.reply_text("<b>🦇 ALL COMMANDS</b>\n━━━━━━━━━━━━━━━━━\n\n🟢 <b>USER:</b>\n/start ➺ Start bot\n/plan ➺ View plans\n/bin ➺ BIN lookup\n/rm ➺ Redeem code\n/ping ➺ Speed check\n/refer ➺ Referral link\n/fb ➺ Submit feedback\n\n\n⚡ <b>FREE CHECKER:</b>\n/chk ➺ Stripe Charge\n/pp ➺ PayPal Charge\n/sh ➺ Shopify Charge\n/pyu ➺ PayU Charge\n/b3 ➺ Braintree Auth\n\n👑 <b>PREMIUM ONLY:</b>\n/au ➺ Stripe Mass\n/mss ➺ Stripe Mass\n/mpp2 ➺ PayPal Mass\n\n👑 <b>OWNER:</b>\n/info ➺ Full user info\n/find ➺ Search user\n/allcm ➺ This menu\n/gen ➺ Gen credits\n/key10 /key20 /key30 ➺ Gen keys\n/sub ➺ Grant premium\n/resub ➺ Remove premium\n/addcredits ➺ Add credits\n/seturl ➺ Set gate API URL\n/geturl ➺ View gate URLs\n/broadcast ➺ Message all users\n/killbot /onbot ➺ Maintenance mode\n/onsh /offsh /onchk /offchk /onpp /offpp (etc) ➺ Toggle Gates\n━━━━━━━━━━━━━━━━━", parse_mode="HTML")

async def cmd_find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args: await update.message.reply_text("Uꜱᴀɢᴇ: /find @username | /find 123456789"); return
    query = " ".join(context.args).strip().lstrip("@")
    all_users, now, matches, ql = context.bot_data.get("user_data", {}), time.time(), [], query.lower()
    for uid_str, ud in all_users.items():
        if ql in ud.get("username", "").lower().lstrip("@") or ql in ud.get("name", "").lower(): matches.append((uid_str, ud))
    if not matches: await update.message.reply_text(f"❌ No users found: <code>{query}</code>", parse_mode="HTML"); return
    blocks = []
    for uid_str, ud in matches[:10]:
        rp, ex = ud.get("plan", "TRIAL").upper(), ud.get("expires", 0)
        if rp != "TRIAL" and ex <= now: rp = "TRIAL"
        prem = rp != "TRIAL" and ex > now
        tl = f"{int((ex-now)//86400)}d {int(((ex-now)%86400)//3600)}h" if prem else "—"
        blocks.append(f"<b>Nᴀᴍᴇ</b> ➺ {ud.get('name','Unknown')}\n<b>Uꜱᴇʀ</b> ➺ @{ud.get('username', '—')}\n<b>ID</b> ➺ <code>{uid_str}</code>\n<b>Pʟᴀɴ</b> ➺ {get_styled_plan(rp)} {'✅' if prem else '⬜'}\n<b>Lᴇꜰᴛ</b> ➺ {tl}")
    txt = f"<b>🔍 Found {len(matches)} user(s)</b>\n━━━━━━━━━━━━━━━━━\n\n" + "\n\n━━━━━━━━━━━━━━━━━\n".join(blocks)
    await update.message.reply_text(txt, parse_mode="HTML")

async def cmd_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args: await update.message.reply_text("Uꜱᴀɢᴇ: /gen <credits>", parse_mode="HTML"); return
    try:
        amt = int(context.args[0])
        code = gen_code()
        context.bot_data.setdefault("codes", {})[code] = {"type": "credit", "value": amt, "used": False}
        await update.message.reply_text(f"<b>Cᴏᴅᴇ:</b> <code>{code}</code>\n<b>Cʀᴇᴅɪᴛꜱ:</b> {amt}", parse_mode="HTML")
    except ValueError: await update.message.reply_text("Invalid amount.")

async def _gen_key(update, context, plan: str, days: int):
    if update.effective_user.id != OWNER_ID: return
    code = "KEY-" + gen_code(12)
    context.bot_data.setdefault("keys", {})[code] = {"plan": plan, "days": days, "used": False}
    await update.message.reply_text(f"<b>Kᴇʏ:</b> <code>{code}</code>\n<b>Pʟᴀɴ:</b> {get_styled_plan(plan)} | <b>Dᴀʏꜱ:</b> {days}", parse_mode="HTML")

async def cmd_key10(u, c): await _gen_key(u, c, "CORE",  7)
async def cmd_key20(u, c): await _gen_key(u, c, "ELITE", 15)
async def cmd_key30(u, c): await _gen_key(u, c, "ROOT", 30)

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
        if not context.args: await update.message.reply_text("Uꜱᴀɢᴇ (reply): /sub <days>", parse_mode="HTML"); return
        try:
            days = int(context.args[0])
            if days <= 0: raise ValueError
        except ValueError: await update.message.reply_text("❌ Invalid days."); return
    else:
        if len(context.args) < 2: await update.message.reply_text("Uꜱᴀɢᴇ: /sub @user|ID days\nOr reply to user → /sub days"); return
        uid = await resolve_user(context.args[0], context)
        if not uid: await update.message.reply_text("❌ User not found."); return
        try:
            days = int(context.args[1])
            if days <= 0: raise ValueError
        except ValueError: await update.message.reply_text("❌ Invalid days."); return
    plan = "ROOT" if days >= 30 else "ELITE" if days >= 15 else "CORE"
    await _grant(uid, plan, days, update, context)

async def cmd_addcredits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    uid = None; amt = None
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        uid = update.message.reply_to_message.from_user.id
        if not context.args: await update.message.reply_text("Uꜱᴀɢᴇ (reply): /addcredits <amount>", parse_mode="HTML"); return
        try:
            amt = int(context.args[0])
            if amt <= 0: raise ValueError
        except ValueError: await update.message.reply_text("❌ Invalid amount."); return
    else:
        if len(context.args) < 2: await update.message.reply_text("Uꜱᴀɢᴇ: /addcredits @user|ID amount\nOr reply to user → /addcredits amount"); return
        uid = await resolve_user(context.args[0], context)
        if not uid: await update.message.reply_text("❌ User not found."); return
        try:
            amt = int(context.args[1])
            if amt <= 0: raise ValueError
        except ValueError: await update.message.reply_text("❌ Invalid amount."); return
    ud = get_user_data(uid, context)
    ud["credits"] = ud.get("credits", 0) + amt
    await update.message.reply_text(f"✅ Added {amt} credits to <code>{uid}</code>\nTotal: {ud['credits']}", parse_mode="HTML")

async def cmd_resub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args: await update.message.reply_text("Uꜱᴀɢᴇ: /resub @user|ID"); return
    uid = await resolve_user(context.args[0], context)
    if not uid: await update.message.reply_text("❌ User not found."); return
    ud = get_user_data(uid, context)
    ud["plan"] = "TRIAL"; ud["expires"] = 0
    await update.message.reply_text(f"✅ Removed premium from <code>{uid}</code>", parse_mode="HTML")

async def cmd_allplans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    now = time.time(); premium_users = []
    for uid_str, ud in context.bot_data.get("user_data", {}).items():
        if ud.get("plan", "TRIAL").upper() != "TRIAL" and ud.get("expires", 0) > now: premium_users.append((uid_str, ud))
    if not premium_users: await update.message.reply_text("No active premium users."); return
    txt = f"<b>👑 Premium Users ({len(premium_users)})</b>\n━━━━━━━━━━━━━━━━━\n\n"
    for uid_str, ud in premium_users[:20]:
        rem = int((ud["expires"] - now) // 86400)
        txt += f"• <code>{uid_str}</code> | {get_styled_plan(ud['plan'])} | {rem}d left\n"
    await update.message.reply_text(txt, parse_mode="HTML")

async def cmd_seturl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if len(context.args) < 2: await update.message.reply_text("Uꜱᴀɢᴇ: /seturl <gate> <url>"); return
    gate, url = context.args[0].lower(), context.args[1]
    if gate not in GATE_URLS: await update.message.reply_text(f"❌ Invalid gate."); return
    context.bot_data[f"gate_url_{gate}"] = url
    await update.message.reply_text(f"✅ Updated {gate} URL to:\n<code>{url}</code>", parse_mode="HTML")

async def cmd_geturl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    txt = "<b>🔗 Gate URLs</b>\n━━━━━━━━━━━━━━━━━\n"
    for gate in GATE_URLS:
        url = context.bot_data.get(f"gate_url_{gate}") or GATE_URLS.get(gate, "Not Set")
        txt += f"{gate.upper()} ➺ <code>{url}</code>\n"
    await update.message.reply_text(txt, parse_mode="HTML")

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args: await update.message.reply_text("Uꜱᴀɢᴇ: /broadcast <message>"); return
    msg_text = " ".join(context.args)
    all_users = context.bot_data.get("user_data", {})
    if not all_users: await update.message.reply_text("No users."); return
    sent, failed = 0, 0
    for uid_str in list(all_users.keys()):
        try:
            await context.bot.send_message(chat_id=int(uid_str), text=msg_text)
            sent += 1
        except Exception: failed += 1
    await update.message.reply_text(f"✅ <b>Bʀᴏᴏᴀᴅᴄᴀsᴛ Cᴏᴍᴘᴘʟᴇᴛᴇ!</b>\n<b>Sᴇɴᴛ</b>: {sent}\n<b>Fᴀɪʟᴇᴅ</b>: {failed}", parse_mode="HTML")

async def cmd_killbot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data["maintenance"] = True
    await update.message.reply_text("🛑 Bot turned OFF for users.")

async def cmd_onbot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data["maintenance"] = False
    await update.message.reply_text("✅ Bot turned ON for users.")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CALLBACK QUERY HANDLER (SMART PHOTO/TEXT FIX)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    data, user = query.data, query.from_user

    # SMART EDITOR: Automatically detects if message is Photo or Text to prevent crashes!
    async def edit_text(text: str, reply_markup=None):
        try:
            if query.message.photo:
                await query.edit_message_caption(caption=text, parse_mode="HTML", reply_markup=reply_markup)
            else:
                await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=reply_markup, disable_web_page_preview=True)
        except BadRequest as e:
            if "message is not modified" in str(e).lower(): pass
            else: logger.error(f"Callback edit error: {e}")
        except Exception as e:
            logger.error(f"Callback edit error: {e}")

    # Force join check for all buttons except check_sub itself
    if data != "check_sub":
        not_joined = await check_force_sub(user.id, context)
        if not_joined:
            await edit_text(FORCE_SUB_TEXT, reply_markup=kb_force_sub(not_joined))
            return

    ud = get_user_data(user.id, context)
    premium = is_user_premium(ud)

    if data == "check_sub":
        not_joined = await check_force_sub(user.id, context)
        if not_joined:
            await edit_text(FORCE_SUB_TEXT, reply_markup=kb_force_sub(not_joined))
        else:
            _update_user_meta(ud, user)
            await edit_text(ui_profile(user, context), reply_markup=kb_main(user.id))
            
    elif data == "bmain":
        await edit_text(ui_profile(user, context), reply_markup=kb_main(user.id))
    elif data == "mgates": 
        await edit_text("<b>Sᴇʟᴇᴄᴛ Gᴀᴛᴇ Cᴀᴛᴇɢᴏʀʏ</b>\n━━━━━━━━━━━━━━━━━", reply_markup=kb_gate_main())
    elif data == "mauth": 
        await edit_text("<b>Aᴜᴛʜ Gᴀᴛᴇs</b>\n━━━━━━━━━━━━━━━━━", reply_markup=kb_auth_gates())
    elif data == "mcharge": 
        await edit_text("<b>Cʜᴀʀɢᴇ Gᴀᴛᴇs</b>\n━━━━━━━━━━━━━━━━━", reply_markup=kb_charge_gates())
    elif data == "mmass":
        if not premium:
            await query.answer("Premium Gates require a premium plan!", show_alert=True)
            await edit_text("<b>Pʀᴇᴍɪᴜᴍ Gᴀᴛᴇs</b>\n━━━━━━━━━━━━━━━━━\nUpgrade: /plan", reply_markup=kb_upgrade())
            return
        await edit_text("<b>Pʀᴇᴍɪᴜᴍ Gᴀᴛᴇs 👑</b>\n━━━━━━━━━━━━━━━━━", reply_markup=kb_premium_gates())
    elif data == "mprice":
        txt = ("<b>[ 𖥷iТ ] Batman Premium Plans</b>\n━━━━━━━━━━━━━━━━━\n\n"
            "<b>Aᴄᴄᴇꜱꜱ</b>  ➺ Cᴏʀᴇ\n<b>Dᴀʏꜱ</b>     ➺ 7\n<b>Cʀᴇᴅɪᴛꜱ</b> ➺ Unlimited\n<b>Pʀɪᴄᴇ</b>   ➺ 10$\n━━━━━━━━━━━━━━━━━\n"
            "<b>Aᴄᴄᴇꜱꜱ</b>  ➺ Eʟɪᴛᴇ\n<b>Dᴀʏꜱ</b>     ➺ 15\n<b>Cʀᴇᴅɪᴛꜱ</b> ➺ Unlimited\n<b>Pʀɪᴄᴇ</b>   ➺ 15$\n━━━━━━━━━━━━━━━━━\n"
            "<b>Aᴄᴄᴇꜱꜱ</b>  ➺ Rᴏᴏᴛ\n<b>Dᴀʏꜱ</b>     ➺ 30\n<b>Cʀᴇᴅɪᴛꜱ</b> ➺ Unlimited\n<b>Pʀɪᴄᴇ</b>   ➺ 30$\n━━━━━━━━━━━━━━━━━")
        await edit_text(txt, reply_markup=kb_price())
    elif data == "mrefer":
        link = get_referral_link(user.id)
        total_refs = ud.get("total_refs", 0)
        txt = (f"<b>[ 𖥷iТ ] Rᴇꜰᴇʀʀᴀʟ</b>\n━━━━━━━━━━━━━━━━━\n<b>Lɪɴᴋ</b>    ➺ <code>{link}</code>\n━━━━━━━━━━━━━━━━━\n<b>Rᴇꜰᴇʀʀᴀʟꜱ</b> ➺ {total_refs}\n<b>Eᴀʀɴᴇᴅ</b>   ➺ {total_refs * REFERRAL_CREDITS} credits\n<b>Pᴇʀ Rᴇꜰ</b>  ➺ +{REFERRAL_CREDITS} credits\n━━━━━━━━━━━━━━━━━")
        await edit_text(txt, reply_markup=kb_back("bmain"))
    elif data.startswith("pay"): 
        await edit_text("<b>Pᴀʏᴍᴇɴᴛ</b>\n━━━━━━━━━━━━━━━━━\nTo purchase, contact support.", reply_markup=kb_payment())
    elif data.startswith("i"):
        gate_map = {
            "ichk": ("chk", "Stripe Charge"), "ipp": ("pp", "PayPal Charge"), 
            "ish": ("sh", "Shopify Charge"), "ipyu": ("pyu", "PayU Charge"), 
            "ib3": ("b3", "Braintree Auth"), "iau": ("au", "Stripe Auth"), 
            "imss": ("mss", "Stripe Mass"), "impp2": ("mpp2", "PayPal Mass")
        }
        if data in gate_map:
            g_key, g_name = gate_map[data]
            if g_key in PREMIUM_GATES and not premium:
                await query.answer("This gate is Premium Only!", show_alert=True)
                return
            await edit_text(gate_info_text(g_name, g_key, 1), reply_markup=kb_back("mgates"))
    elif data.startswith("fb_ok_"): 
        if user.id != OWNER_ID: return
        await _fb_approve(query, context, data.split("fb_ok_")[1])
    elif data.startswith("fb_no_"): 
        if user.id != OWNER_ID: return
        await _fb_decline(query, context, data.split("fb_no_")[1])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GLOBAL ERROR HANDLER & POST INIT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error = context.error
    if isinstance(error, Conflict):
        logger.critical("CONFLICT: Another bot instance is running. Waiting 10s before exit...")
        await asyncio.sleep(10)
        os._exit(1)
        return
    if isinstance(error, NetworkError):
        logger.warning(f"Network error (auto-retry): {error}"); return
    logger.error(f"Unhandled error: {type(error).__name__}: {error}", exc_info=context.error)

async def post_init(application: Application) -> None:
    logger.info("Cleaning up any existing webhook...")
    try: await application.bot.delete_webhook(drop_pending_updates=True)
    except Exception: pass

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN FUNCTION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def main():
    if not BOT_TOKEN:
        logger.error("FATAL: BOT_TOKEN is not set!"); return
    if not acquire_instance_lock():
        logger.warning("Another instance is running."); return

    try:
        app = Application.builder().token(BOT_TOKEN).concurrent_updates(True).post_init(post_init).build()
        app.add_error_handler(global_error_handler)

        # User Commands
        app.add_handler(CommandHandler("start", cmd_start))
        app.add_handler(CommandHandler("ping", cmd_ping))
        app.add_handler(CommandHandler("plan", cmd_plan))
        app.add_handler(CommandHandler("refer", cmd_refer))
        app.add_handler(CommandHandler("rm", cmd_rm))
        app.add_handler(CommandHandler("bin", cmd_bin))
        app.add_handler(CommandHandler("fb", cmd_fb))

        # Gate Commands
        app.add_handler(CommandHandler("chk", cmd_chk))
        app.add_handler(CommandHandler("pp", cmd_pp))
        app.add_handler(CommandHandler("sh", cmd_sh))
        app.add_handler(CommandHandler("pyu", cmd_pyu))
        app.add_handler(CommandHandler("b3", cmd_b3))

        # Owner Commands
        app.add_handler(CommandHandler("info", cmd_info))
        app.add_handler(CommandHandler("allcm", cmd_allcm))
        app.add_handler(CommandHandler("find", cmd_find))
        app.add_handler(CommandHandler("gen", cmd_gen))
        app.add_handler(CommandHandler("key10", cmd_key10))
        app.add_handler(CommandHandler("key20", cmd_key20))
        app.add_handler(CommandHandler("key30", cmd_key30))
        app.add_handler(CommandHandler("oneday", cmd_oneday))
        app.add_handler(CommandHandler("threeday", cmd_threeday))
        app.add_handler(CommandHandler("sub", cmd_sub))
        app.add_handler(CommandHandler("addcredits", cmd_addcredits))
        app.add_handler(CommandHandler("resub", cmd_resub))
        app.add_handler(CommandHandler("allplans", cmd_allplans))
        app.add_handler(CommandHandler("seturl", cmd_seturl))
        app.add_handler(CommandHandler("geturl", cmd_geturl))
        app.add_handler(CommandHandler("broadcast", cmd_broadcast))
        app.add_handler(CommandHandler("killbot", cmd_killbot))
        app.add_handler(CommandHandler("onbot", cmd_onbot))

        # Gate On/Off Commands
        for cmd, func in [
            ("onchk", cmd_onchk), ("offchk", cmd_offchk), ("onpp", cmd_onpp), ("offpp", cmd_offpp),
            ("onsh", cmd_onsh), ("offsh", cmd_offsh), ("onpyu", cmd_onpyu), ("offpyu", cmd_offpyu),
            ("onb3", cmd_onb3), ("offb3", cmd_offb3), ("onau", cmd_onau), ("offau", cmd_offau),
            ("onmss", cmd_onmss), ("offmss", cmd_offmss), ("onmpp2", cmd_onmpp2), ("offmpp2", cmd_offmpp2),
        ]:
            app.add_handler(CommandHandler(cmd, func))

        # MASS HANDLERS INTEGRATION
        for handler in get_mass_handlers():
            app.add_handler(handler)

        # Callbacks
        app.add_handler(CallbackQueryHandler(callback_handler))

        logger.info(f"Bot {BOT_USERNAME} started successfully!")
        app.run_polling(drop_pending_updates=True, close_loop=False, stop_signals=(signal.SIGINT, signal.SIGTERM))
    finally:
        release_instance_lock()

if __name__ == "__main__":
    main()
