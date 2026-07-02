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
    rows.append([InlineKeyboardButton("✅ I Joined — Verify Now", callback_data="check_sub")])
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
        await update.message.reply_text(FORCE_SUB_TEXT, reply_markup=kb_force_sub(not_joined))
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
# GATE PROCESSING  (single-card gates only: chk pp sh pyu b3)
# /au /mss /mpp2 are handled exclusively by mass.py
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

    # card from inline args OR reply-to-text
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

# ── Single-card gate command wrappers ──────────────────
# NOTE: /au /mss /mpp2 are intentionally NOT here — they are
#       mass-checking commands registered exclusively from mass.py.
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
        f"[ 𖥷iТ ] ➺ Gʀᴀɴᴛᴇᴅ\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"Uꜱᴇʀ    ➺ {uname_line}\n"
        f"ID      ➺ <code>{uid}</code>\n"
        f"Pʟᴀɴ    ➺ {get_styled_plan(plan)} 👑\n"
        f"Dᴀʏꜱ    ➺ {days}\n"
        f"Exᴘɪʀᴇꜱ ➺ {exp_date}\n"
        f"Rᴇᴄᴇɪᴘᴛ ➺ <code>{receipt}</code>\n"
        f"━━━━━━━━━━━━━━━━━",
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
            "Usage: /add <user_id|@username> <plan> <days>\n"
            "Plans: CORE  ELITE  ROOT", parse_mode="HTML")
        return
    uid = await resolve_user(args[0], context)
    if not uid:
        await update.message.reply_text(f"User not found: {args[0]}")
        return
    plan = args[1].upper()
    if plan not in ("CORE", "ELITE", "ROOT"):
        await update.message.reply_text("Invalid plan. Use: CORE  ELITE  ROOT")
        return
    try:
        days = int(args[2])
    except ValueError:
        await update.message.reply_text("Days must be an integer.")
        return
    await _grant(uid, plan, days, update, context)

async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /remove <user_id|@username>")
        return
    uid = await resolve_user(context.args[0], context)
    if not uid:
        await update.message.reply_text(f"User not found: {context.args[0]}")
        return
    ud = get_user_data(uid, context)
    ud["plan"]    = "TRIAL"
    ud["expires"] = 0
    await update.message.reply_text(
        f"✅ Removed premium from <code>{uid}</code>.", parse_mode="HTML")

async def cmd_seturl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /seturl <gate_key> <url>")
        return
    key = context.args[0].lower()
    url = context.args[1]
    context.bot_data[f"gate_url_{key}"] = url
    await update.message.reply_text(f"✅ URL set for gate <code>{key}</code>.", parse_mode="HTML")

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast <message>")
        return
    text    = " ".join(context.args)
    users   = context.bot_data.get("user_data", {})
    sent    = 0
    failed  = 0
    for uid_str in users:
        try:
            await context.bot.send_message(chat_id=int(uid_str), text=text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1
    await update.message.reply_text(f"✅ Sent: {sent}  ❌ Failed: {failed}")

async def cmd_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    current = context.bot_data.get("maintenance", False)
    context.bot_data["maintenance"] = not current
    state = "ON 🔴" if not current else "OFF 🟢"
    await update.message.reply_text(f"Maintenance mode: {state}")

async def cmd_gate_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner: /gate <key> on|off"""
    if update.effective_user.id != OWNER_ID:
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /gate <gate_key> on|off")
        return
    key   = context.args[0].lower()
    state = context.args[1].lower() == "on"
    context.bot_data[f"{key}_on"] = state
    await update.message.reply_text(
        f"Gate <code>{key}</code> is now {'ON 🟢' if state else 'OFF 🔴'}.", parse_mode="HTML")

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    users = context.bot_data.get("user_data", {})
    total = len(users)
    premium = sum(
        1 for ud in users.values()
        if ud.get("plan", "TRIAL").upper() != "TRIAL" and ud.get("expires", 0) > time.time()
    )
    await update.message.reply_text(
        f"[ 𖥷iТ ] Stats\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"Total users  ➺ {total}\n"
        f"Premium      ➺ {premium}\n"
        f"━━━━━━━━━━━━━━━━━",
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# USER COMMANDS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ud   = get_user_data(user.id, context)
    _update_user_meta(ud, user)

    if context.args and context.args[0].startswith("ref_"):
        try:
            ref_id = int(context.args[0][4:])
            await process_referral(user.id, ref_id, context)
        except ValueError:
            pass

    text = (
        f"[ 𖥷iТ ] Batman Card Checker\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"Wᴇʟᴄᴏᴍᴇ, {user.first_name}!\n\n"
        f"Tʜᴇ #𝟭 Cᴀʀᴅ Cʜᴇᴄᴋɪɴɢ Bᴏᴛ\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"Vᴇʀsɪᴏɴ ➺ {VERSION}\n"
        f"Pʀᴏ     ➺ Batman"
    )
    await update.message.reply_text(text, reply_markup=kb_main(user.id))

async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    _update_user_meta(get_user_data(user.id, context), user)
    await update.message.reply_text(
        ui_profile(user, context), parse_mode="HTML",
        reply_markup=kb_back("bmain"), disable_web_page_preview=True)

async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"[ 𖥷iТ ] ➺ Pʀᴇᴍɪᴜᴍ Pʟᴀɴꜱ\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"Cᴏʀᴇ  ➺ $10 / 30 days\n"
        f"Eʟɪᴛᴇ ➺ $15 / 30 days\n"
        f"Rᴏᴏᴛ  ➺ $30 / 30 days\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"All plans include unlimited credits.\n"
        f"Contact support to purchase.",
        reply_markup=kb_price(),
    )

async def cmd_refer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    link = get_referral_link(user.id)
    ud   = get_user_data(user.id, context)
    await update.message.reply_text(
        f"[ 𖥷iТ ] ➺ Rᴇꜰᴇʀ & Eᴀʀɴ\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"Yᴏᴜʀ Lɪɴᴋ ➺ {link}\n"
        f"Rᴇꜰᴇʀʀᴀʟꜱ ➺ {ud.get('total_refs', 0)}\n"
        f"Eᴀʀɴᴇᴅ   ➺ {ud.get('total_refs', 0) * REFERRAL_CREDITS} credits\n"
        f"━━━━━━━━━━━━━━━━━",
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "[ 𖥷iТ ] ➺ Cᴏᴍᴍᴀɴᴅꜱ\n"
        "━━━━━━━━━━━━━━━━━\n"
        "<b>Free Gates:</b>\n"
        "/chk cc|mm|yy|cvv  ➺ Stripe Charge\n"
        "/pp  cc|mm|yy|cvv  ➺ PayPal Charge\n"
        "/sh  cc|mm|yy|cvv  ➺ Shopify Charge\n"
        "/pyu cc|mm|yy|cvv  ➺ PayU Charge\n"
        "/b3  cc|mm|yy|cvv  ➺ Braintree Auth\n\n"
        "<b>Premium Gates:</b>\n"
        "/au  cc|mm|yy|cvv  ➺ Sᴛʀɪᴘᴇ Aᴜᴛʜ (mass + file)\n"
        "/mss cc|mm|yy|cvv  ➺ Sᴛʀɪᴘᴇ Mᴀss (mass + file)\n"
        "/mpp2 cc|mm|yy|cvv ➺ PᴀʏPᴀʟ Mᴀss (mass + file)\n\n"
        "<b>File support (premium):</b>\n"
        "Upload a .txt file → send /au /mss /mpp2 as caption,\n"
        "OR reply to a file with the command.\n\n"
        "<b>Other:</b>\n"
        "/profile  ➺ Your profile\n"
        "/plan     ➺ Buy premium\n"
        "/refer    ➺ Refer & earn\n"
        "━━━━━━━━━━━━━━━━━"
    )
    await update.message.reply_text(text, parse_mode="HTML")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CALLBACK QUERY HANDLER (inline buttons)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cb_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data  = query.data
    user  = query.from_user

    async def edit(text: str, kb=None, **kw):
        try:
            await query.edit_message_text(
                text, parse_mode="HTML", reply_markup=kb,
                disable_web_page_preview=True, **kw)
        except BadRequest:
            pass

    if data == "bmain":
        text = (
            f"[ 𖥷iТ ] Batman Card Checker\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"Wᴇʟᴄᴏᴍᴇ, {user.first_name}!\n\n"
            f"Tʜᴇ #𝟭 Cᴀʀᴅ Cʜᴇᴄᴋɪɴɢ Bᴏᴛ\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"Vᴇʀsɪᴏɴ ➺ {VERSION}\n"
            f"Pʀᴏ     ➺ Batman"
        )
        await edit(text, kb_main(user.id))
    elif data == "mgates":
        await edit(
            "[ 𖥷iТ ] ➺ Sᴇʟᴇᴄᴛ Gᴀᴛᴇ Cᴀᴛᴇɢᴏʀʏ\n━━━━━━━━━━━━━━━━━",
            kb_gate_main())
    elif data == "mauth":
        await edit(
            "[ 𖥷iТ ] ➺ Aᴜᴛʜ Gᴀᴛᴇꜱ\n━━━━━━━━━━━━━━━━━\n/b3 ➺ Braintree Auth",
            kb_auth_gates())
    elif data == "mcharge":
        await edit(
            "[ 𖥷iТ ] ➺ Cʜᴀʀɢᴇ Gᴀᴛᴇꜱ\n━━━━━━━━━━━━━━━━━\n"
            "/chk ➺ Stripe  /pp ➺ PayPal\n/sh ➺ Shopify  /pyu ➺ PayU",
            kb_charge_gates())
    elif data == "mmass":
        await edit(
            "[ 𖥷iТ ] ➺ Pʀᴇᴍɪᴜᴍ Gᴀᴛᴇꜱ\n━━━━━━━━━━━━━━━━━\n"
            "/au   ➺ Sᴛʀɪᴘᴇ Aᴜᴛʜ\n"
            "/mss  ➺ Sᴛʀɪᴘᴇ Mᴀss\n"
            "/mpp2 ➺ PᴀʏPᴀʟ Mᴀss\n\n"
            "Supports file upload + reply-to-file.",
            kb_premium_gates())
    elif data == "mprice":
        await edit(
            "[ 𖥷iТ ] ➺ Pʀᴇᴍɪᴜᴍ Pʟᴀɴꜱ\n━━━━━━━━━━━━━━━━━\n"
            "Cᴏʀᴇ  ➺ $10 / 30 days\n"
            "Eʟɪᴛᴇ ➺ $15 / 30 days\n"
            "Rᴏᴏᴛ  ➺ $30 / 30 days\n━━━━━━━━━━━━━━━━━\n"
            "Contact support to purchase.",
            kb_price())
    elif data == "mrefer":
        link = get_referral_link(user.id)
        ud   = get_user_data(user.id, context)
        await edit(
            f"[ 𖥷iТ ] ➺ Rᴇꜰᴇʀ & Eᴀʀɴ\n━━━━━━━━━━━━━━━━━\n"
            f"Yᴏᴜʀ Lɪɴᴋ ➺ {link}\n"
            f"Rᴇꜰᴇʀʀᴀʟꜱ ➺ {ud.get('total_refs', 0)}\n━━━━━━━━━━━━━━━━━",
            kb_back("bmain"))
    elif data == "check_sub":
        not_joined = await check_force_sub(user.id, context)
        if not_joined:
            await query.answer("Please join all channels first!", show_alert=True)
        else:
            await edit(
                "[ 𖥷iТ ] ➺ Vᴇʀɪꜰɪᴇᴅ ✅\nYou are now subscribed. Use /start.",
                kb_main(user.id))
    elif data in ("ib3", "ichk", "ipp", "ish", "ipyu", "iau", "imss", "impp2"):
        gate_map = {
            "ib3":   ("b3",   "Braintree Auth"),
            "ichk":  ("chk",  "Stripe Charge"),
            "ipp":   ("pp",   "PayPal Charge"),
            "ish":   ("sh",   "Shopify Charge"),
            "ipyu":  ("pyu",  "PayU Charge"),
            "iau":   ("au",   "Sᴛʀɪᴘᴇ Aᴜᴛʜ"),
            "imss":  ("mss",  "Sᴛʀɪᴘᴇ Mᴀss"),
            "impp2": ("mpp2", "PᴀʏPᴀʟ Mᴀss"),
        }
        cmd, name = gate_map[data]
        cost      = 0 if cmd in ("au", "mss", "mpp2", "b3") else 1
        await edit(gate_info_text(name, cmd, cost), kb_back("mgates"))
    # payment callbacks (owner flow)
    elif data.startswith("pay"):
        plan_map = {"pay10": ("CORE", 30), "pay15": ("ELITE", 30), "pay30": ("ROOT", 30)}
        plan, days = plan_map.get(data, ("CORE", 30))
        await edit(
            f"[ 𖥷iТ ] ➺ Pᴜʀᴄʜᴀꜱᴇ {get_styled_plan(plan)}\n━━━━━━━━━━━━━━━━━\n"
            f"Contact support with your user ID:\n<code>{user.id}</code>\n━━━━━━━━━━━━━━━━━",
            kb_payment())

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# APPLICATION SETUP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def build_application() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()

    # ── User commands ────────────────────────────────────
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("help",    cmd_help))
    app.add_handler(CommandHandler("profile", cmd_profile))
    app.add_handler(CommandHandler("plan",    cmd_plan))
    app.add_handler(CommandHandler("refer",   cmd_refer))

    # ── Free single-card gates ───────────────────────────
    app.add_handler(CommandHandler("chk",  cmd_chk))
    app.add_handler(CommandHandler("pp",   cmd_pp))
    app.add_handler(CommandHandler("sh",   cmd_sh))
    app.add_handler(CommandHandler("pyu",  cmd_pyu))
    app.add_handler(CommandHandler("b3",   cmd_b3))

    # ── Premium mass gates (/au /mss /mpp2) + result buttons
    for handler in get_mass_handlers():
        app.add_handler(handler)

    # ── Owner commands ────────────────────────────────────
    app.add_handler(CommandHandler("add",         cmd_add))
    app.add_handler(CommandHandler("remove",      cmd_remove))
    app.add_handler(CommandHandler("seturl",      cmd_seturl))
    app.add_handler(CommandHandler("broadcast",   cmd_broadcast))
    app.add_handler(CommandHandler("maintenance", cmd_maintenance))
    app.add_handler(CommandHandler("gate",        cmd_gate_toggle))
    app.add_handler(CommandHandler("stats",       cmd_stats))

    # ── Inline button callbacks ───────────────────────────
    # result_ callbacks are already registered by get_mass_handlers()
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

    loop = asyncio.get_running_loop()
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
        logger.info("Bot started. Waiting for updates...")
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
