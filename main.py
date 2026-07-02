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

import re
import aiohttp as _aiohttp

from config import (
    BOT_TOKEN, OWNER_ID, VERSION, DEV_LINK,
    CHANNEL_USERNAME, CHANNEL_LINK, GROUP_LINK, SUPPORT_LINK,
    BOT_LINK, BOT_USERNAME, BOT_PHOTO_URL, BOT_PHOTO,
    API_TIMEOUT, REFERRAL_CREDITS, LOCK_FILE,
    GATE_URLS, GATE_SITES, PREMIUM_GATES, FORCE_CHANNELS,
    get_bin_info,
)
from mass import get_mass_handlers

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
# BOLD UNICODE FONT  (used for buttons only)
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
    if p == "CORE":  return "Core"
    if p == "ELITE": return "Elite"
    if p == "ROOT":  return "Root"
    return "Trial"

def get_plan_icon(raw_plan: str) -> str:
    p = raw_plan.upper()
    if p in ("CORE", "ELITE", "ROOT"): return "★"
    return ""

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
            "name":               "User",
            "first_name":         "User",
            "last_name":          "",
            "username":           "",
            "language_code":      "en",
            "joined":             datetime.now().strftime("%Y-%m-%d %H:%M"),
            "last_active":        datetime.now().strftime("%Y-%m-%d %H:%M"),
            "credits":            DEFAULT_CREDITS,
            "plan":               "TRIAL",
            "expires":            0,
            "credits_before_prem": DEFAULT_CREDITS,
            "total_refs":         0,
            "total_checks":       0,
            "approved_checks":    0,
            "declined_checks":    0,
            "last_gate":          "N/A",
            "last_card":          "N/A",
            "codes_redeemed":     0,
            "keys_redeemed":      0,
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

def is_user_premium(ud: dict) -> bool:
    return (
        ud.get("plan", "TRIAL").upper() != "TRIAL"
        and ud.get("expires", 0) > time.time()
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AUTO-EXPIRE PREMIUM
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def check_and_expire_premium(
    ud: dict, user_id: int, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    raw_plan = ud.get("plan", "TRIAL").upper()
    if raw_plan == "TRIAL":
        return False
    if ud.get("expires", 0) > time.time():
        return False
    restored      = ud.get("credits_before_prem", DEFAULT_CREDITS)
    ud["plan"]    = "TRIAL"
    ud["expires"] = 0
    ud["credits"] = restored
    try:
        await context.bot.send_message(
            chat_id=user_id, parse_mode="HTML",
            text=(
                "BatmanCardXChk\n"
                "━━━━━━━━━━━━━━━━━\n"
                "<b>Premium Expired</b>\n\n"
                f"Your premium plan has ended.\n"
                f"Credits Restored → <b>{restored}</b>\n\n"
                "Renew with /plan\n"
                "━━━━━━━━━━━━━━━━━"
            ),
        )
    except Exception:
        pass
    return True

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MISC HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_referral_link(user_id: int) -> str:
    return f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"

def gen_receipt() -> str:
    return f"BATMAN-{random.randint(100000, 999999)}"

def gen_code(length: int = 12) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# KEYBOARDS  (clean, no sticker emojis in buttons)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def kb_main(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("CHECKER"),      callback_data="mgates"),
         InlineKeyboardButton(B("BUY NOW"),      callback_data="mprice")],
        [InlineKeyboardButton(B("UPDATES") + " ↗", url=CHANNEL_LINK),
         InlineKeyboardButton(B("GROUP")   + " ↗", url=GROUP_LINK)],
        [InlineKeyboardButton(B("SUPPORT") + " ↗", url=SUPPORT_LINK)],
    ])

def kb_back(cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("← " + B("BACK"), callback_data=cb)
    ]])

def kb_price() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("$10 — CORE"),  callback_data="pay10"),
         InlineKeyboardButton(B("$15 — ELITE"), callback_data="pay15"),
         InlineKeyboardButton(B("$30 — ROOT"),  callback_data="pay30")],
        [InlineKeyboardButton(B("SUPPORT") + " ↗", url=SUPPORT_LINK)],
        [InlineKeyboardButton("← " + B("BACK"), callback_data="bmain")],
    ])

def kb_payment() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("SUPPORT") + " ↗", url=SUPPORT_LINK)],
        [InlineKeyboardButton("← " + B("BACK"), callback_data="mprice")],
    ])

def kb_gate_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("AUTH"),    callback_data="mauth"),
         InlineKeyboardButton(B("CHARGE"),  callback_data="mcharge"),
         InlineKeyboardButton(B("PREMIUM"), callback_data="mmass")],
        [InlineKeyboardButton("← " + B("BACK"), callback_data="bmain")],
    ])

def kb_auth_gates() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("BRAINTREE"), callback_data="ib3")],
        [InlineKeyboardButton("← " + B("BACK"), callback_data="mgates")],
    ])

def kb_charge_gates() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("STRIPE"),  callback_data="ichk"),
         InlineKeyboardButton(B("PAYPAL"),  callback_data="ipp")],
        [InlineKeyboardButton(B("SHOPIFY"), callback_data="ish"),
         InlineKeyboardButton(B("PAYU"),    callback_data="ipyu")],
        [InlineKeyboardButton("← " + B("BACK"), callback_data="mgates")],
    ])

def kb_premium_gates() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("STRIPE AUTH"), callback_data="iau")],
        [InlineKeyboardButton(B("STRIPE MASS"), callback_data="imss")],
        [InlineKeyboardButton(B("PAYPAL MASS"), callback_data="impp2")],
        [InlineKeyboardButton("← " + B("BACK"), callback_data="mgates")],
    ])

def kb_upgrade() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("BUY PREMIUM"), callback_data="mprice")],
        [InlineKeyboardButton(B("SUPPORT") + " ↗", url=SUPPORT_LINK)],
    ])

# Card result buttons: trial → BUY NOW, premium → channel link
def kb_card_result(plan: str) -> InlineKeyboardMarkup:
    p = plan.upper()
    if p in ("CORE", "ELITE", "ROOT"):
        return InlineKeyboardMarkup([[
            InlineKeyboardButton(B("BATMANCARDXCHK") + " ↗", url=CHANNEL_LINK)
        ]])
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(B("BUY NOW"), callback_data="mprice")
    ]])

def kb_fb_owner(key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Approve", callback_data=f"fb_ok_{key}"),
        InlineKeyboardButton("Decline", callback_data=f"fb_no_{key}"),
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
        raw_plan      = "TRIAL"
        ud["plan"]    = "TRIAL"
        ud["expires"] = 0
        ud["credits"] = ud.get("credits_before_prem", DEFAULT_CREDITS)
        expires = 0
    premium    = raw_plan != "TRIAL"
    credits    = "Unlimited" if premium else str(ud.get("credits", DEFAULT_CREDITS))
    uname      = f"@{user.username}" if user.username else user.first_name or "User"
    total_refs = ud.get("total_refs", 0)

    lines = [
        "BatmanCardXChk",
        "━━━━━━━━━━━━━━━━━",
        f"User     → {uname} {get_plan_icon(raw_plan)}".rstrip(),
        f"ID       → <code>{user.id}</code>",
        f"Access   → {get_styled_plan(raw_plan)}",
        f"Credits  → {credits}",
    ]
    if premium and expires > now:
        exp_date = datetime.fromtimestamp(expires).strftime("%Y-%m-%d %H:%M")
        rem_d    = int((expires - now) / 86400)
        rem_h    = int(((expires - now) % 86400) / 3600)
        lines.append(f"Expires  → {exp_date}")
        lines.append(f"Left     → {rem_d}d {rem_h}h")
        receipt = ud.get("last_receipt")
        if receipt:
            lines.append(f"Receipt  → <code>{receipt}</code>")
    lines.append(f"Referrals → {total_refs} (+{total_refs * REFERRAL_CREDITS} credits)")
    lines.append(f"Joined    → {ud.get('joined', datetime.now().strftime('%Y-%m-%d'))}")
    lines.append(f"Dev       → <a href='{DEV_LINK}'>Batman</a>")
    lines.append(f"Version   → {VERSION}")
    lines.append("━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)

def gate_info_text(gate_name: str, cmd: str, cost: int) -> str:
    return (
        f"━━━━━━━━━━━━━━━━━\n"
        f"{gate_name}\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"Cost   → {cost} Credit(s) per check\n\n"
        f"Usage:\n<code>/{cmd} cc|mm|yy|cvv</code>\n\n"
        f"Example:\n<code>/{cmd} 4111111111111111|12|2026|123</code>\n\n"
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
        label = "Join Channel" if "group" not in name.lower() else "Join Group"
        rows.append([InlineKeyboardButton(f"{label} — @{name} ↗", url=link)])
    rows.append([InlineKeyboardButton("Verify Membership", callback_data="check_sub")])
    return InlineKeyboardMarkup(rows)

FORCE_SUB_TEXT = (
    "BatmanCardXChk\n"
    "━━━━━━━━━━━━━━━━━\n"
    "<b>Join Required</b>\n\n"
    "You must join our channels to use this bot.\n"
    "Join then press Verify Membership below.\n"
    "━━━━━━━━━━━━━━━━━"
)

async def require_membership(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id    = update.effective_user.id
    not_joined = await check_force_sub(user_id, context)
    if not_joined:
        await update.message.reply_text(
            FORCE_SUB_TEXT, reply_markup=kb_force_sub(not_joined), parse_mode="HTML"
        )
        return False
    return True

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SEND START PHOTO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _send_start_photo(
    message, caption: str, reply_markup, parse_mode: str = "HTML"
):
    """Send batman.jpg above the welcome caption (like CXC layout).
    Falls back to plain text if the photo can't be sent."""
    # Try local file first
    script_dir   = os.path.dirname(os.path.abspath(__file__))
    local_photo  = os.path.join(script_dir, BOT_PHOTO) if BOT_PHOTO else None

    if local_photo and os.path.isfile(local_photo):
        try:
            with open(local_photo, "rb") as f:
                await message.reply_photo(
                    photo=f, caption=caption,
                    parse_mode=parse_mode, reply_markup=reply_markup,
                    disable_notification=False,
                )
            return
        except Exception:
            pass

    # Try file_id / URL string
    if BOT_PHOTO and not os.path.isfile(str(BOT_PHOTO)):
        try:
            await message.reply_photo(
                photo=BOT_PHOTO, caption=caption,
                parse_mode=parse_mode, reply_markup=reply_markup,
            )
            return
        except Exception:
            pass

    # Fallback: text only
    await message.reply_text(
        caption, parse_mode=parse_mode, reply_markup=reply_markup,
        disable_web_page_preview=True,
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CARD CHECK RESULT TEXT
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
        status_line = "Timeout"
    elif is_error:
        status_line = "Error"
    elif is_approved:
        status_line = "Approved"
    else:
        status_line = "Declined"

    bin_txt = "N/A"
    if bin_data and not bin_data.get("error"):
        scheme  = str(bin_data.get("scheme",  "N/A")).upper()
        bank    = bin_data.get("bank",    "N/A")
        country = str(bin_data.get("country", "N/A")).upper()
        flag    = bin_data.get("country_emoji", "")
        bin_txt = f"{scheme} — {bank} — {flag} {country}".strip(" —")

    plan_label    = get_styled_plan(plan)
    plan_icon     = get_plan_icon(plan)
    uname_display = f"{username} ({plan_label} {plan_icon})".rstrip()

    lines = [
        f"BatmanCardXChk — {status_line}",
        f"━━━━━━━━━━━━━━━━━",
        f"Card → <code>{card_raw}</code>",
        f"Gate → {gate_name}",
        f"Raw  → {raw_response}",
        f"Info → {bin_txt}",
        f"User → {uname_display}",
        f"Pro  → Batman | {time_taken}s",
        f"━━━━━━━━━━━━━━━━━",
    ]
    return "\n".join(lines)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# REFERRAL SYSTEM
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def process_referral(
    new_user_id: int, referrer_id: int, context: ContextTypes.DEFAULT_TYPE
) -> bool:
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
            chat_id=referrer_id, parse_mode="HTML",
            text=(
                "BatmanCardXChk\n"
                "━━━━━━━━━━━━━━━━━\n"
                "<b>Referral Bonus!</b>\n\n"
                "Someone joined using your link.\n"
                f"Credits Added     → <b>+{REFERRAL_CREDITS}</b>\n"
                f"Total Referrals   → <b>{referrer_ud['total_refs']}</b>\n"
                "━━━━━━━━━━━━━━━━━"
            ),
        )
    except Exception:
        pass
    return True

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GATE PROCESSING  (single-card)
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

async def process_gate(
    update: Update, context: ContextTypes.DEFAULT_TYPE,
    gate_key: str, gate_name: str,
):
    user = update.effective_user

    if context.bot_data.get("maintenance") and user.id != OWNER_ID:
        await update.message.reply_text(
            "Bot is under maintenance. Try again later.", parse_mode="HTML"
        )
        return

    if not context.bot_data.get(f"{gate_key}_on", True):
        await update.message.reply_text(
            f"Gate [{gate_name}] is currently OFF.", parse_mode="HTML"
        )
        return

    if not await require_membership(update, context):
        return

    ud = get_user_data(user.id, context)
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
            f"Usage: <code>/{gate_key} cc|mm|yy|cvv</code>", parse_mode="HTML"
        )
        return

    if not premium:
        credits = ud.get("credits", 0)
        if credits <= 0:
            await update.message.reply_text(
                "BatmanCardXChk\n"
                "━━━━━━━━━━━━━━━━━\n"
                "<b>No Credits</b>\n\n"
                "Buy a plan: /plan\n"
                "Earn free credits: /refer\n"
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
            f"Gate API URL not set.\nOwner: <code>/seturl {gate_key} &lt;url&gt;</code>",
            parse_mode="HTML",
        )
        return

    msg        = await update.message.reply_text("Scanning...", parse_mode="HTML")
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
        if isinstance(results[0], Exception):
            raise results[0]

        raw_response = str(
            data.get("value") or data.get("message") or
            data.get("Response") or data.get("category") or "ERROR"
        ).strip()

        is_approved = any(
            w in raw_response.lower()
            for w in ["approved", "captured", "success", "charged", "true"]
        )
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
        if not premium:
            ud["credits"] = ud.get("credits", 0) + 1
        time_taken = f"{time.time() - start_time:.2f}"
        text = build_check_result(
            card_raw=card_raw, gate_name=gate_name,
            raw_response="Request Timeout", bin_data={},
            username=uname, plan=plan, time_taken=time_taken,
            is_approved=False, is_timeout=True,
        )
        await msg.edit_text(
            text, parse_mode="HTML",
            reply_markup=kb_card_result(plan),
            disable_web_page_preview=True,
        )
    except Exception as e:
        if not premium:
            ud["credits"] = ud.get("credits", 0) + 1
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

# Single-card gate wrappers
async def cmd_chk(update, context):  await process_gate(update, context, "chk",  "Stripe Charge")
async def cmd_pp(update, context):   await process_gate(update, context, "pp",   "PayPal Charge")
async def cmd_sh(update, context):   await process_gate(update, context, "sh",   "Shopify Charge")
async def cmd_pyu(update, context):  await process_gate(update, context, "pyu",  "PayU Charge")
async def cmd_b3(update, context):   await process_gate(update, context, "b3",   "Braintree Auth")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PREMIUM KEY STORE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_key_store(context: ContextTypes.DEFAULT_TYPE) -> dict:
    return context.bot_data.setdefault("keys", {})

def create_key(context: ContextTypes.DEFAULT_TYPE, plan: str, days: int) -> str:
    code  = gen_code(14)
    store = get_key_store(context)
    store[code] = {"plan": plan.upper(), "days": days, "used": False}
    return code

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PREMIUM ACTIVATION HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def send_activation_msg(
    user_id: int, plan: str, days: int,
    context: ContextTypes.DEFAULT_TYPE,
) -> str:
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

    txt = (
        "BatmanCardXChk\n"
        "━━━━━━━━━━━━━━━━━\n"
        "<b>Access Activated</b>\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"User     → {display_name}\n"
        f"Access   → <b>{get_styled_plan(plan)}</b>\n"
        f"Days     → <b>{days}</b>\n"
        f"Credits  → <b>Unlimited</b>\n"
        f"Expires  → {exp_date}\n"
        f"Receipt  → <code>{receipt}</code>\n"
        "━━━━━━━━━━━━━━━━━\n"
        "Save your receipt ID.\n"
        "Pro → Batman"
    )
    try:
        await context.bot.send_message(chat_id=user_id, text=txt, parse_mode="HTML")
    except Exception:
        pass
    return receipt

async def resolve_user(
    target: str, context: ContextTypes.DEFAULT_TYPE
) -> Optional[int]:
    target = target.strip().lstrip("@")
    if target.lstrip("-").isdigit():
        return int(target)
    for attempt in (f"@{target}", target):
        try:
            return (await context.bot.get_chat(attempt)).id
        except Exception:
            continue
    target_lower = target.lower()
    for uid_str, ud in context.bot_data.get("user_data", {}).items():
        stored = ud.get("username", "").lower().lstrip("@")
        if stored and stored == target_lower:
            return int(uid_str)
    return None

async def _grant(
    uid: int, plan: str, days: int,
    update: Update, context: ContextTypes.DEFAULT_TYPE,
):
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
    exp_date   = datetime.fromtimestamp(ud["expires"]).strftime("%Y-%m-%d %H:%M")

    await update.message.reply_text(
        "BatmanCardXChk\n"
        "━━━━━━━━━━━━━━━━━\n"
        "<b>Granted</b>\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"User    → {uname_line}\n"
        f"ID      → <code>{uid}</code>\n"
        f"Plan    → <b>{get_styled_plan(plan)}</b>\n"
        f"Days    → <b>{days}</b>\n"
        f"Expires → {exp_date}\n"
        f"Receipt → <code>{receipt}</code>\n"
        "━━━━━━━━━━━━━━━━━",
        parse_mode="HTML",
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# USER COMMANDS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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
    premium  = is_user_premium(ud)
    credits  = "Unlimited" if premium else str(ud.get("credits", DEFAULT_CREDITS))
    uname    = f"@{user.username}" if user.username else user.first_name or "User"

    caption = (
        "BatmanCardXChk\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"User     → {uname} {get_plan_icon(raw_plan)}".rstrip() + "\n"
        f"User ID  → <code>{user.id}</code>\n"
        f"Access   → {get_styled_plan(raw_plan)}\n"
        f"Credits  → {credits}\n"
        f"Joined   → {ud.get('joined', datetime.now().strftime('%Y-%m-%d'))}\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"Dev      → <a href='{DEV_LINK}'>Batman</a>\n"
        f"Version  → {VERSION}"
    )
    await _send_start_photo(update.message, caption, kb_main(user.id))

async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ud   = get_user_data(user.id, context)
    _update_user_meta(ud, user)
    await check_and_expire_premium(ud, user.id, context)
    await update.message.reply_text(
        ui_profile(user, context), parse_mode="HTML",
        reply_markup=kb_back("bmain"), disable_web_page_preview=True,
    )

async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "BatmanCardXChk\n"
        "━━━━━━━━━━━━━━━━━\n"
        "<b>Premium Plans</b>\n"
        "━━━━━━━━━━━━━━━━━\n"
        "Core  → $10 / 30 days\n"
        "Elite → $15 / 30 days\n"
        "Root  → $30 / 30 days\n"
        "━━━━━━━━━━━━━━━━━\n"
        "All plans include unlimited credits.\n"
        "Contact support to purchase.",
        parse_mode="HTML",
        reply_markup=kb_price(),
    )

async def cmd_refer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ud   = get_user_data(user.id, context)
    link = get_referral_link(user.id)
    await update.message.reply_text(
        "BatmanCardXChk\n"
        "━━━━━━━━━━━━━━━━━\n"
        "<b>Refer & Earn</b>\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"Your Link  → {link}\n"
        f"Referrals  → <b>{ud.get('total_refs', 0)}</b>\n"
        f"Earned     → <b>{ud.get('total_refs', 0) * REFERRAL_CREDITS}</b> credits\n"
        "━━━━━━━━━━━━━━━━━",
        parse_mode="HTML",
    )

async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    start = time.time()
    msg   = await update.message.reply_text("Pinging...")
    delta = (time.time() - start) * 1000
    await msg.edit_text(
        f"BatmanCardXChk\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"Latency → <b>{delta:.0f}ms</b>\n"
        f"Status  → Online\n"
        f"━━━━━━━━━━━━━━━━━",
        parse_mode="HTML",
    )

async def cmd_bin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Usage: <code>/bin 411111</code>", parse_mode="HTML"
        )
        return
    bin_num = re.sub(r"\D", "", context.args[0])[:6] if context.args else ""
    if len(bin_num) < 6:
        await update.message.reply_text("Please provide a 6-digit BIN number.")
        return

    msg  = await update.message.reply_text("Looking up BIN...")
    data = await get_bin_info(bin_num)

    if data.get("error"):
        await msg.edit_text(
            f"BatmanCardXChk\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"BIN {bin_num} not found.\n"
            f"━━━━━━━━━━━━━━━━━",
            parse_mode="HTML",
        )
        return

    scheme  = data.get("scheme",  "N/A").upper()
    btype   = data.get("type",    "N/A").upper()
    brand   = data.get("brand",   "N/A")
    bank    = data.get("bank",    "N/A")
    country = data.get("country", "N/A")
    flag    = data.get("country_emoji", "")

    await msg.edit_text(
        f"BatmanCardXChk\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"<b>BIN Lookup</b>\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"BIN     → <code>{bin_num}</code>\n"
        f"Scheme  → {scheme}\n"
        f"Type    → {btype}\n"
        f"Brand   → {brand}\n"
        f"Bank    → {bank}\n"
        f"Country → {flag} {country}\n"
        f"━━━━━━━━━━━━━━━━━",
        parse_mode="HTML",
    )

async def cmd_rm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Redeem a premium key."""
    user = update.effective_user
    if not context.args:
        await update.message.reply_text(
            "Usage: <code>/rm YOUR-KEY-HERE</code>", parse_mode="HTML"
        )
        return
    code  = context.args[0].strip().upper()
    store = get_key_store(context)
    entry = store.get(code)

    if not entry:
        await update.message.reply_text("Invalid key.")
        return
    if entry.get("used"):
        await update.message.reply_text("This key has already been used.")
        return

    ud = get_user_data(user.id, context)
    _update_user_meta(ud, user)

    if ud.get("plan", "TRIAL").upper() == "TRIAL":
        ud["credits_before_prem"] = ud.get("credits", DEFAULT_CREDITS)

    plan       = entry["plan"]
    days       = entry["days"]
    expires_ts = time.time() + days * 86400
    ud["plan"]         = plan
    ud["expires"]      = expires_ts
    ud["last_receipt"] = code
    ud["keys_redeemed"] = ud.get("keys_redeemed", 0) + 1
    entry["used"]      = True

    exp_date = datetime.fromtimestamp(expires_ts).strftime("%Y-%m-%d %H:%M")
    await update.message.reply_text(
        "BatmanCardXChk\n"
        "━━━━━━━━━━━━━━━━━\n"
        "<b>Key Redeemed!</b>\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"Plan     → <b>{get_styled_plan(plan)}</b>\n"
        f"Days     → <b>{days}</b>\n"
        f"Credits  → <b>Unlimited</b>\n"
        f"Expires  → {exp_date}\n"
        "━━━━━━━━━━━━━━━━━",
        parse_mode="HTML",
    )

async def cmd_fb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Submit feedback — text, photo, or video forwarded to owner."""
    user = update.effective_user
    msg  = update.message

    uname = f"@{user.username}" if user.username else user.first_name or "User"
    header = (
        f"Feedback from {uname} (<code>{user.id}</code>)\n"
        f"━━━━━━━━━━━━━━━━━\n"
    )

    fb_key = f"fb_{user.id}_{int(time.time())}"

    if msg.photo:
        caption = (msg.caption or "(no caption)").strip()
        await context.bot.send_photo(
            chat_id=OWNER_ID,
            photo=msg.photo[-1].file_id,
            caption=header + caption,
            parse_mode="HTML",
            reply_markup=kb_fb_owner(fb_key),
        )
    elif msg.video:
        caption = (msg.caption or "(no caption)").strip()
        await context.bot.send_video(
            chat_id=OWNER_ID,
            video=msg.video.file_id,
            caption=header + caption,
            parse_mode="HTML",
            reply_markup=kb_fb_owner(fb_key),
        )
    else:
        text_body = " ".join(context.args) if context.args else (msg.text or "").strip()
        if not text_body or text_body.startswith("/fb"):
            await update.message.reply_text(
                "Usage: /fb Your feedback message\n"
                "You can also send a photo or video with /fb as caption.",
                parse_mode="HTML",
            )
            return
        await context.bot.send_message(
            chat_id=OWNER_ID,
            text=header + text_body,
            parse_mode="HTML",
            reply_markup=kb_fb_owner(fb_key),
        )

    await update.message.reply_text(
        "Feedback submitted. Thank you.",
        parse_mode="HTML",
    )

async def cmd_allcm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_owner = update.effective_user.id == OWNER_ID
    owner_section = ""
    if is_owner:
        owner_section = (
            "\nOwner:\n"
            "/info     — Full user info\n"
            "/find     — Search user by username\n"
            "/allcm    — This menu\n"
            "/gen      — Generate credits\n"
            "/key10    — Generate Core key (30d)\n"
            "/key20    — Generate Elite key (30d)\n"
            "/key30    — Generate Root key (30d)\n"
            "/oneday   — Generate 1-day key\n"
            "/threeday — Generate 3-day key\n"
            "/sub      — Grant premium\n"
            "/resub    — Remove premium\n"
            "/addcredits — Add credits to user\n"
            "/allplans — List all premium users\n"
            "/seturl   — Set gate API URL\n"
            "/geturl   — View gate URLs\n"
            "/broadcast — Message all users\n"
            "/killbot  — Enable maintenance mode\n"
            "/onbot    — Disable maintenance mode\n"
        )

    text = (
        "━━━━━━━━━━━━━━━━━\n"
        "BatmanCardXChk — All Commands\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        "User:\n"
        "/start   — Start the bot\n"
        "/plan    — View plans & pricing\n"
        "/bin     — BIN lookup\n"
        "/rm      — Redeem a premium key\n"
        "/ping    — Bot speed check\n"
        "/refer   — Your referral link\n"
        "/fb      — Submit feedback\n"
        "/profile — Your profile\n\n"
        "Free Checker:\n"
        "/chk  — Stripe Charge\n"
        "/pp   — PayPal Charge\n"
        "/sh   — Shopify Charge\n"
        "/pyu  — PayU Charge\n"
        "/b3   — Braintree Auth\n\n"
        "Premium Only:\n"
        "/au   — Stripe Auth\n"
        "/mss  — Stripe Mass\n"
        "/mpp2 — PayPal Mass\n"
        f"{owner_section}"
        "━━━━━━━━━━━━━━━━━"
    )
    await update.message.reply_text(text, parse_mode="HTML")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# OWNER COMMANDS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _owner_only(fn):
    """Decorator — silently ignores non-owner calls."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != OWNER_ID:
            return
        return await fn(update, context)
    wrapper.__name__ = fn.__name__
    return wrapper

@_owner_only
async def cmd_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/sub <user> <plan> <days>  — Grant premium."""
    args = context.args
    if len(args) < 3:
        await update.message.reply_text(
            "Usage: <code>/sub &lt;user_id|@username&gt; &lt;core|elite|root&gt; &lt;days&gt;</code>",
            parse_mode="HTML",
        )
        return
    uid = await resolve_user(args[0], context)
    if not uid:
        await update.message.reply_text(f"User not found: {args[0]}")
        return
    plan = args[1].upper()
    if plan not in ("CORE", "ELITE", "ROOT"):
        await update.message.reply_text("Invalid plan. Use: core  elite  root")
        return
    try:
        days = int(args[2])
    except ValueError:
        await update.message.reply_text("Days must be a number.")
        return
    await _grant(uid, plan, days, update, context)

@_owner_only
async def cmd_resub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/resub <user>  — Remove premium."""
    if not context.args:
        await update.message.reply_text(
            "Usage: <code>/resub &lt;user_id|@username&gt;</code>", parse_mode="HTML"
        )
        return
    uid = await resolve_user(context.args[0], context)
    if not uid:
        await update.message.reply_text(f"User not found: {context.args[0]}")
        return
    ud       = get_user_data(uid, context)
    restored = ud.get("credits_before_prem", DEFAULT_CREDITS)
    ud["plan"]    = "TRIAL"
    ud["expires"] = 0
    ud["credits"] = restored
    try:
        name = ud.get("name", str(uid))
        await context.bot.send_message(
            chat_id=uid, parse_mode="HTML",
            text=(
                "BatmanCardXChk\n"
                "━━━━━━━━━━━━━━━━━\n"
                "<b>Premium Removed</b>\n\n"
                "Your premium access has been revoked.\n"
                f"Credits Restored → <b>{restored}</b>\n"
                "━━━━━━━━━━━━━━━━━"
            ),
        )
    except Exception:
        pass
    await update.message.reply_text(
        f"Premium removed from <code>{uid}</code>.\n"
        f"Credits restored: <b>{restored}</b>",
        parse_mode="HTML",
    )

@_owner_only
async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/info <user>  — Full user details."""
    if not context.args:
        await update.message.reply_text(
            "Usage: <code>/info &lt;user_id|@username&gt;</code>", parse_mode="HTML"
        )
        return
    uid = await resolve_user(context.args[0], context)
    if not uid:
        await update.message.reply_text(f"User not found: {context.args[0]}")
        return

    ud       = context.bot_data.get("user_data", {}).get(str(uid), {})
    raw_plan = ud.get("plan", "TRIAL").upper()
    now      = time.time()
    expires  = ud.get("expires", 0)
    if raw_plan != "TRIAL" and expires <= now:
        raw_plan = "TRIAL"
    premium  = raw_plan != "TRIAL" and expires > now
    credits  = "Unlimited" if premium else str(ud.get("credits", DEFAULT_CREDITS))
    uname    = f"@{ud.get('username','')}" if ud.get("username") else ud.get("name", str(uid))
    exp_str  = datetime.fromtimestamp(expires).strftime("%Y-%m-%d %H:%M") if expires > 0 else "N/A"
    rem_str  = ""
    if premium:
        rem_d = int((expires - now) / 86400)
        rem_h = int(((expires - now) % 86400) / 3600)
        rem_str = f"\nTime Left    → <b>{rem_d}d {rem_h}h</b>"

    await update.message.reply_text(
        "BatmanCardXChk — User Info\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"Name         → {uname}\n"
        f"ID           → <code>{uid}</code>\n"
        f"Plan         → <b>{get_styled_plan(raw_plan)}</b> {get_plan_icon(raw_plan)}\n"
        f"Credits      → <b>{credits}</b>\n"
        f"Expires      → {exp_str}"
        f"{rem_str}\n"
        f"Total Checks → {ud.get('total_checks', 0)}\n"
        f"Approved     → {ud.get('approved_checks', 0)}\n"
        f"Declined     → {ud.get('declined_checks', 0)}\n"
        f"Last Gate    → {ud.get('last_gate', 'N/A')}\n"
        f"Last Card    → <code>{ud.get('last_card', 'N/A')}</code>\n"
        f"Referrals    → {ud.get('total_refs', 0)}\n"
        f"Joined       → {ud.get('joined', 'N/A')}\n"
        f"Last Active  → {ud.get('last_active', 'N/A')}\n"
        f"Receipt      → <code>{ud.get('last_receipt', 'N/A')}</code>\n"
        "━━━━━━━━━━━━━━━━━",
        parse_mode="HTML",
    )

@_owner_only
async def cmd_find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/find <@username or partial name>  — Search users."""
    if not context.args:
        await update.message.reply_text(
            "Usage: <code>/find &lt;@username | name | id&gt;</code>", parse_mode="HTML"
        )
        return
    query  = " ".join(context.args).lower().lstrip("@")
    users  = context.bot_data.get("user_data", {})
    found  = []
    for uid_str, ud in users.items():
        uname = ud.get("username", "").lower()
        name  = ud.get("name",     "").lower()
        if query in uname or query in name or query == uid_str:
            found.append((uid_str, ud))

    if not found:
        await update.message.reply_text("No users found.")
        return

    lines = ["BatmanCardXChk — Search Results", "━━━━━━━━━━━━━━━━━"]
    for uid_str, ud in found[:10]:
        plan  = ud.get("plan", "TRIAL").upper()
        uname = f"@{ud.get('username')}" if ud.get("username") else ud.get("name", uid_str)
        lines.append(f"{uname} — ID: <code>{uid_str}</code> — {get_styled_plan(plan)}")
    if len(found) > 10:
        lines.append(f"... and {len(found) - 10} more.")
    lines.append("━━━━━━━━━━━━━━━━━")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

@_owner_only
async def cmd_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/gen <user> <amount>  — Add credits."""
    if len(context.args or []) < 2:
        await update.message.reply_text(
            "Usage: <code>/gen &lt;user_id|@username&gt; &lt;amount&gt;</code>",
            parse_mode="HTML",
        )
        return
    uid = await resolve_user(context.args[0], context)
    if not uid:
        await update.message.reply_text(f"User not found: {context.args[0]}")
        return
    try:
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("Amount must be a number.")
        return
    ud = get_user_data(uid, context)
    ud["credits"] = ud.get("credits", 0) + amount
    await update.message.reply_text(
        f"Added <b>{amount}</b> credits to <code>{uid}</code>.\n"
        f"New balance: <b>{ud['credits']}</b>",
        parse_mode="HTML",
    )
    try:
        await context.bot.send_message(
            chat_id=uid, parse_mode="HTML",
            text=(
                "BatmanCardXChk\n"
                "━━━━━━━━━━━━━━━━━\n"
                "<b>Credits Added!</b>\n"
                f"Credits Added → <b>+{amount}</b>\n"
                f"New Balance   → <b>{ud['credits']}</b>\n"
                "━━━━━━━━━━━━━━━━━"
            ),
        )
    except Exception:
        pass

@_owner_only
async def cmd_addcredits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Alias for /gen."""
    return await cmd_gen.__wrapped__(update, context)

@_owner_only
async def cmd_key10(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/key10  — Generate Core key (30 days)."""
    code = create_key(context, "CORE", 30)
    await update.message.reply_text(
        f"Core key (30d):\n<code>{code}</code>", parse_mode="HTML"
    )

@_owner_only
async def cmd_key20(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/key20  — Generate Elite key (30 days)."""
    code = create_key(context, "ELITE", 30)
    await update.message.reply_text(
        f"Elite key (30d):\n<code>{code}</code>", parse_mode="HTML"
    )

@_owner_only
async def cmd_key30(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/key30  — Generate Root key (30 days)."""
    code = create_key(context, "ROOT", 30)
    await update.message.reply_text(
        f"Root key (30d):\n<code>{code}</code>", parse_mode="HTML"
    )

@_owner_only
async def cmd_oneday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/oneday  — Generate 1-day Core trial key."""
    code = create_key(context, "CORE", 1)
    await update.message.reply_text(
        f"1-day key (Core):\n<code>{code}</code>", parse_mode="HTML"
    )

@_owner_only
async def cmd_threeday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/threeday  — Generate 3-day Core trial key."""
    code = create_key(context, "CORE", 3)
    await update.message.reply_text(
        f"3-day key (Core):\n<code>{code}</code>", parse_mode="HTML"
    )

@_owner_only
async def cmd_allplans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/allplans  — List all premium users."""
    users = context.bot_data.get("user_data", {})
    now   = time.time()
    lines = ["BatmanCardXChk — Premium Users", "━━━━━━━━━━━━━━━━━"]
    count = 0
    for uid_str, ud in users.items():
        plan    = ud.get("plan", "TRIAL").upper()
        expires = ud.get("expires", 0)
        if plan != "TRIAL" and expires > now:
            uname   = f"@{ud.get('username')}" if ud.get("username") else ud.get("name", uid_str)
            rem_d   = int((expires - now) / 86400)
            exp_str = datetime.fromtimestamp(expires).strftime("%Y-%m-%d")
            lines.append(f"{uname} — {get_styled_plan(plan)} — {rem_d}d left ({exp_str})")
            count += 1
    if count == 0:
        lines.append("No active premium users.")
    lines.append(f"━━━━━━━━━━━━━━━━━\nTotal: {count}")
    # Split into chunks if too long
    text = "\n".join(lines)
    if len(text) > MAX_MSG:
        text = text[:MAX_MSG] + "\n... (truncated)"
    await update.message.reply_text(text, parse_mode="HTML")

@_owner_only
async def cmd_seturl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/seturl <gate> <url>"""
    if len(context.args or []) < 2:
        await update.message.reply_text(
            "Usage: <code>/seturl &lt;gate_key&gt; &lt;url&gt;</code>", parse_mode="HTML"
        )
        return
    key = context.args[0].lower()
    url = context.args[1]
    context.bot_data[f"gate_url_{key}"] = url
    await update.message.reply_text(
        f"URL set for gate <code>{key}</code>.", parse_mode="HTML"
    )

@_owner_only
async def cmd_geturl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/geturl  — Show all configured gate URLs."""
    gates = ["chk", "pp", "sh", "pyu", "b3"]
    lines = ["BatmanCardXChk — Gate URLs", "━━━━━━━━━━━━━━━━━"]
    for key in gates:
        url = context.bot_data.get(f"gate_url_{key}") or GATE_URLS.get(key, "Not set")
        lines.append(f"{key}: <code>{url}</code>")
    lines.append("━━━━━━━━━━━━━━━━━")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

@_owner_only
async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/broadcast <message>  — Send HTML message to all users."""
    if not context.args:
        await update.message.reply_text(
            "Usage: <code>/broadcast &lt;message&gt;</code>", parse_mode="HTML"
        )
        return
    text    = " ".join(context.args)
    users   = context.bot_data.get("user_data", {})
    status  = await update.message.reply_text(
        f"Broadcasting to {len(users)} users..."
    )
    sent, failed = 0, 0
    for uid_str in list(users.keys()):
        try:
            await context.bot.send_message(
                chat_id=int(uid_str), text=text, parse_mode="HTML"
            )
            sent += 1
        except Exception:
            failed += 1
    await status.edit_text(
        f"Broadcast complete.\nSent: {sent}  Failed: {failed}", parse_mode="HTML"
    )

@_owner_only
async def cmd_killbot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/killbot  — Enable maintenance mode."""
    context.bot_data["maintenance"] = True
    await update.message.reply_text("Maintenance mode ON. Users cannot use the bot.")

@_owner_only
async def cmd_onbot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/onbot  — Disable maintenance mode."""
    context.bot_data["maintenance"] = False
    await update.message.reply_text("Maintenance mode OFF. Bot is live.")

@_owner_only
async def cmd_gate_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/gate <key> on|off"""
    if len(context.args or []) < 2:
        await update.message.reply_text("Usage: /gate <key> on|off")
        return
    key   = context.args[0].lower()
    state = context.args[1].lower() == "on"
    context.bot_data[f"{key}_on"] = state
    await update.message.reply_text(
        f"Gate <code>{key}</code> is now {'ON' if state else 'OFF'}.", parse_mode="HTML"
    )

@_owner_only
async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users   = context.bot_data.get("user_data", {})
    total   = len(users)
    now     = time.time()
    premium = sum(
        1 for ud in users.values()
        if ud.get("plan", "TRIAL").upper() != "TRIAL" and ud.get("expires", 0) > now
    )
    await update.message.reply_text(
        "BatmanCardXChk — Stats\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"Total Users  → <b>{total}</b>\n"
        f"Premium      → <b>{premium}</b>\n"
        f"Trial        → <b>{total - premium}</b>\n"
        "━━━━━━━━━━━━━━━━━",
        parse_mode="HTML",
    )

# Alias — keep /add and /remove working too
async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await cmd_sub(update, context)

async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await cmd_resub(update, context)

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
                disable_web_page_preview=True, **kw,
            )
        except BadRequest:
            pass

    raw_plan = ud.get("plan", "TRIAL").upper()
    premium  = is_user_premium(ud)
    credits  = "Unlimited" if premium else str(ud.get("credits", DEFAULT_CREDITS))
    uname    = f"@{user.username}" if user.username else user.first_name or "User"

    if data == "bmain":
        await edit(
            "BatmanCardXChk\n"
            "━━━━━━━━━━━━━━━━━\n"
            f"User     → {uname} {get_plan_icon(raw_plan)}".rstrip() + "\n"
            f"User ID  → <code>{user.id}</code>\n"
            f"Access   → {get_styled_plan(raw_plan)}\n"
            f"Credits  → {credits}\n"
            "━━━━━━━━━━━━━━━━━\n"
            f"Dev     → <a href='{DEV_LINK}'>Batman</a>\n"
            f"Version → {VERSION}",
            kb_main(user.id),
        )

    elif data == "mgates":
        await edit(
            "BatmanCardXChk\n"
            "━━━━━━━━━━━━━━━━━\n"
            "Select Gate Category",
            kb_gate_main(),
        )

    elif data == "mauth":
        await edit(
            "BatmanCardXChk\n"
            "━━━━━━━━━━━━━━━━━\n"
            "Auth Gates\n"
            "━━━━━━━━━━━━━━━━━\n"
            "/b3 — Braintree Auth",
            kb_auth_gates(),
        )

    elif data == "mcharge":
        await edit(
            "BatmanCardXChk\n"
            "━━━━━━━━━━━━━━━━━\n"
            "Charge Gates\n"
            "━━━━━━━━━━━━━━━━━\n"
            "/chk — Stripe\n"
            "/pp  — PayPal\n"
            "/sh  — Shopify\n"
            "/pyu — PayU",
            kb_charge_gates(),
        )

    elif data == "mmass":
        await edit(
            "BatmanCardXChk\n"
            "━━━━━━━━━━━━━━━━━\n"
            "Premium Gates\n"
            "━━━━━━━━━━━━━━━━━\n"
            "/au   — Stripe Auth\n"
            "/mss  — Stripe Mass\n"
            "/mpp2 — PayPal Mass\n\n"
            "Supports file upload and reply-to-file.",
            kb_premium_gates(),
        )

    elif data == "mprice":
        await edit(
            "BatmanCardXChk\n"
            "━━━━━━━━━━━━━━━━━\n"
            "<b>Premium Plans</b>\n"
            "━━━━━━━━━━━━━━━━━\n"
            "Core  → $10 / 30 days\n"
            "Elite → $15 / 30 days\n"
            "Root  → $30 / 30 days\n"
            "━━━━━━━━━━━━━━━━━\n"
            "Contact support to purchase.",
            kb_price(),
        )

    elif data == "mrefer":
        link = get_referral_link(user.id)
        await edit(
            "BatmanCardXChk\n"
            "━━━━━━━━━━━━━━━━━\n"
            f"Your Link  → {link}\n"
            f"Referrals  → <b>{ud.get('total_refs', 0)}</b>\n"
            "━━━━━━━━━━━━━━━━━",
            kb_back("bmain"),
        )

    elif data == "check_sub":
        not_joined = await check_force_sub(user.id, context)
        if not_joined:
            await query.answer("Please join all channels first!", show_alert=True)
        else:
            await edit(
                "BatmanCardXChk\n"
                "━━━━━━━━━━━━━━━━━\n"
                "<b>Verified!</b>\n\n"
                "You are now subscribed. Use /start to continue.\n"
                "━━━━━━━━━━━━━━━━━",
                kb_main(user.id),
            )

    elif data in ("ib3", "ichk", "ipp", "ish", "ipyu", "iau", "imss", "impp2"):
        gate_map = {
            "ib3":   ("b3",   "Braintree Auth",  0),
            "ichk":  ("chk",  "Stripe Charge",   1),
            "ipp":   ("pp",   "PayPal Charge",   1),
            "ish":   ("sh",   "Shopify Charge",  1),
            "ipyu":  ("pyu",  "PayU Charge",     1),
            "iau":   ("au",   "Stripe Auth",     0),
            "imss":  ("mss",  "Stripe Mass",     0),
            "impp2": ("mpp2", "PayPal Mass",     0),
        }
        cmd, name, cost = gate_map[data]
        await edit(gate_info_text(name, cmd, cost), kb_back("mgates"))

    elif data.startswith("pay"):
        plan_map = {
            "pay10": ("CORE", 30),
            "pay15": ("ELITE", 30),
            "pay30": ("ROOT", 30),
        }
        plan, days = plan_map.get(data, ("CORE", 30))
        await edit(
            "BatmanCardXChk\n"
            "━━━━━━━━━━━━━━━━━\n"
            f"<b>Purchase {get_styled_plan(plan)}</b>\n"
            "━━━━━━━━━━━━━━━━━\n"
            "Contact support with your User ID:\n"
            f"<code>{user.id}</code>\n"
            "━━━━━━━━━━━━━━━━━",
            kb_payment(),
        )

    elif data.startswith("fb_"):
        if user.id != OWNER_ID:
            return
        parts  = data.split("_", 2)
        action = parts[1]
        try:
            msg_text = query.message.text or query.message.caption or ""
            if action == "ok":
                await query.edit_message_reply_markup(reply_markup=None)
                await query.answer("Feedback approved.")
            else:
                await query.edit_message_reply_markup(reply_markup=None)
                await query.answer("Feedback declined.")
        except Exception:
            pass

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FIX: missing import for BIN cmd
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
import re

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# APPLICATION SETUP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def build_application() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()

    # ── User commands ─────────────────────────────────
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("profile", cmd_profile))
    app.add_handler(CommandHandler("plan",    cmd_plan))
    app.add_handler(CommandHandler("refer",   cmd_refer))
    app.add_handler(CommandHandler("ping",    cmd_ping))
    app.add_handler(CommandHandler("bin",     cmd_bin))
    app.add_handler(CommandHandler("rm",      cmd_rm))
    app.add_handler(CommandHandler("fb",      cmd_fb))
    app.add_handler(CommandHandler("allcm",   cmd_allcm))
    app.add_handler(CommandHandler("help",    cmd_allcm))   # /help = /allcm

    # ── Free single-card gates ────────────────────────
    app.add_handler(CommandHandler("chk",  cmd_chk))
    app.add_handler(CommandHandler("pp",   cmd_pp))
    app.add_handler(CommandHandler("sh",   cmd_sh))
    app.add_handler(CommandHandler("pyu",  cmd_pyu))
    app.add_handler(CommandHandler("b3",   cmd_b3))

    # ── Premium mass gates + download result buttons ──
    # MUST be registered before the catch-all CallbackQueryHandler
    for handler in get_mass_handlers():
        app.add_handler(handler)

    # ── Owner commands ────────────────────────────────
    app.add_handler(CommandHandler("sub",         cmd_sub))
    app.add_handler(CommandHandler("resub",       cmd_resub))
    app.add_handler(CommandHandler("add",         cmd_add))         # alias
    app.add_handler(CommandHandler("remove",      cmd_remove))      # alias
    app.add_handler(CommandHandler("info",        cmd_info))
    app.add_handler(CommandHandler("find",        cmd_find))
    app.add_handler(CommandHandler("gen",         cmd_gen))
    app.add_handler(CommandHandler("addcredits",  cmd_addcredits))
    app.add_handler(CommandHandler("key10",       cmd_key10))
    app.add_handler(CommandHandler("key20",       cmd_key20))
    app.add_handler(CommandHandler("key30",       cmd_key30))
    app.add_handler(CommandHandler("oneday",      cmd_oneday))
    app.add_handler(CommandHandler("threeday",    cmd_threeday))
    app.add_handler(CommandHandler("allplans",    cmd_allplans))
    app.add_handler(CommandHandler("seturl",      cmd_seturl))
    app.add_handler(CommandHandler("geturl",      cmd_geturl))
    app.add_handler(CommandHandler("broadcast",   cmd_broadcast))
    app.add_handler(CommandHandler("killbot",     cmd_killbot))
    app.add_handler(CommandHandler("onbot",       cmd_onbot))
    app.add_handler(CommandHandler("gate",        cmd_gate_toggle))
    app.add_handler(CommandHandler("stats",       cmd_stats))

    # ── Catch-all inline button callbacks ────────────
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
        logger.info("BatmanCardXChk — Bot started.")
        await stop_event.wait()
    except Conflict:
        logger.error("Telegram conflict: another bot instance is already running.")
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
