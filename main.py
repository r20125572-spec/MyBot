import logging
import time
import string
import random
import urllib.request
import json
import asyncio
from typing import Optional
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ApplicationHandlerStop,
)
from telegram.error import Conflict
import aiohttp

from config import (
    BOT_TOKEN, OWNER_ID, VERSION, DEV_LINK, BOT_PHOTO, BOT_PHOTO_URL,
    GATE_URLS, GATE_SITES, API_TIMEOUT, get_bin_info, kb_result,
)

CHANNEL_USERNAME   = "@Batcardchk"
GROUP_USERNAME     = "@batcardchkGroup"
CHANNEL_LINK       = "https://t.me/Batcardchk"
GROUP_LINK         = "https://t.me/batcardchkGroup"
SUPPORT_LINK       = "https://t.me/cardchkSupport"
BOT_LINK           = "https://t.me/Batmancardchk_bot"
WELCOME_IMAGE_PATH = "/app/batman.jpg"

GATE_NAMES = {
    "chk":  "Stripe Charge",
    "pp":   "PayPal Charge",
    "sh":   "Shopify Charge",
    "pyu":  "PayU Charge",
    "b3":   "Braintree Auth",
    "au":   "Stripe Auth",
    "mss":  "Stripe Mass",
    "mpp2": "PayPal Mass",
}

COUNTRY_CURRENCY = {
    "US": "USD", "GB": "GBP", "EU": "EUR", "FR": "EUR", "DE": "EUR",
    "IT": "EUR", "ES": "EUR", "NL": "EUR", "BE": "EUR", "AT": "EUR",
    "PT": "EUR", "GR": "EUR", "IE": "EUR", "FI": "EUR", "SK": "EUR",
    "SI": "EUR", "LT": "EUR", "LV": "EUR", "EE": "EUR", "CY": "EUR",
    "MT": "EUR", "LU": "EUR", "CA": "CAD", "AU": "AUD", "JP": "JPY",
    "CN": "CNY", "IN": "INR", "BR": "BRL", "MX": "MXN", "KR": "KRW",
    "RU": "RUB", "CH": "CHF", "SE": "SEK", "NO": "NOK", "DK": "DKK",
    "PL": "PLN", "CZ": "CZK", "HU": "HUF", "TR": "TRY", "ZA": "ZAR",
    "SG": "SGD", "HK": "HKD", "NZ": "NZD", "SA": "SAR", "AE": "AED",
    "AR": "ARS", "CL": "CLP", "CO": "COP", "PH": "PHP", "MY": "MYR",
    "TH": "THB", "ID": "IDR", "PK": "PKR", "NG": "NGN", "EG": "EGP",
    "UA": "UAH", "RO": "RON", "BG": "BGN", "HR": "HRK", "RS": "RSD",
    "IL": "ILS", "VN": "VND", "BD": "BDT", "LK": "LKR", "KE": "KES",
}

BLOCK_WORDS = (
    "http://", "https://", "www.", "t.me", ".com", ".net", ".org",
    ".io", ".me", ".xyz", ".tk", ".ml", ".cf", ".ga", ".ru", ".in",
    ".pw", "telegram.me", "joinchat", "://",
    "a_toolsx", "a-toolsx", "atoolsx", "a tools x", "a_tools",
    "toolsx", "must join our channel", "to use this bot",
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

CHECKER_STATUS_TEXT = (
    "Gᴀᴛᴇꜱ Sᴛᴀᴛᴜꜱ:\n"
    "Aᴜᴛʜ Gᴀᴛᴇꜱ   \u279a 2\n"
    "Mᴀss Gᴀᴛᴇꜱ   \u279a 2\n"
    "C\u029c\u1d00\u0280\u0262\u1d07 G\u1d00\u1d1b\u1d07s \u279a 4\n"
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
    "S\u1d07\u029f\u1d07\u1d04\u1d1b \u1d00 G\u1d00\u1d1b\u1d07 \u279a C\u1d00\u1d1b\u1d07\u0262\u1d0f\u0280y"
)

AUTH_MENU_TEXT = (
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
    "S\u1d07\u029f\u1d07\u1d04\u1d1b A\u1d1c\u1d1b\u029c G\u1d00\u1d1b\u1d07 \u279a\n"
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
)

STRIPE_AUTH_TEXT = (
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
    "G\u1d00\u1d1b\u1d07    \u279a S\u1d1b\u0280\u026a\u1d18\u1d07 0$\n"
    "C\u1d0f\u1d0d\u1d0d\u1d00\u0274\u1d05 \u279a /chk\n"
    "S\u026a\u1d1b\u1d07s   \u279a 16\n"
    "H\u1d07\u1d00\u029f\u1d1b\u029c  \u279a 100%\n"
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
)

BRAINTREE_TEXT = (
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
    "G\u1d00\u1d1b\u1d07    \u279a B\u0280\u1d00\u026a\u0274\u1d1b\u0280\u1d07\u1d07 0$\n"
    "C\u1d0f\u1d0d\u1d0d\u1d00\u0274\u1d05 \u279a /b3\n"
    "S\u026a\u1d1b\u1d07s   \u279a 2\n"
    "H\u1d07\u1d00\u029f\u1d1b\u029c  \u279a 100%\n"
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
)

CHARGE_MENU_TEXT = (
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
    "S\u1d07\u029f\u1d07\u1d04\u1d1b C\u029c\u1d00\u0280\u0262\u1d07 G\u1d00\u1d1b\u1d07 \u279a\n"
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
)

MASS_MENU_TEXT = (
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
    "S\u1d07\u029f\u1d07\u1d04\u1d1b M\u1d00ss G\u1d00\u1d1b\u1d07 \u279a\n"
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
)

PLAN_TEXT = (
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
    "B\u1d00\u1d1b\u1d0d\u1d00\u0274 P\u0280\u1d07\u1d0d\u026a\u1d1c\u1d0d P\u029f\u1d00\u0274s\n"
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
    "A\u1d04\u1d04\u1d07ss \u279a C\u1d0f\u0280\u1d07 \U0001F380\n"
    "S\u1d18\u1d00\u0274   \u279a [7 D\u1d00ys]\n"
    "C\u0280\u1d07\u1d05\u026a\u1d1b\u1d04s \u279a \u221e U\u0274\u029f\u026a\u1d0d\u026a\u1d1b\u026a\u1d1b\u1d07\u1d05\n"
    "P\u0280\u026a\u1d04\u1d07  \u279a 10$\n"
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
    "A\u1d04\u1d04\u1d07ss \u279a E\u029f\u026a\u1d1b\u1d07 \u2b50\ufe0f\n"
    "S\u1d18\u1d00\u0274   \u279a [15 D\u1d00ys]\n"
    "C\u0280\u1d07\u1d05\u026a\u1d1b\u1d04s \u279a \u221e U\u0274\u029f\u026a\u1d0d\u026a\u1d1b\u026a\u1d1b\u1d07\u1d05\n"
    "P\u0280\u026a\u1d04\u1d07  \u279a 15$\n"
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
    "A\u1d04\u1d04\u1d07ss \u279a R\u1d0f\u1d0f\u1d1b \U0001F451\n"
    "S\u1d18\u1d00\u0274   \u279a [30 D\u1d00ys]\n"
    "C\u0280\u1d07\u1d05\u026a\u1d1b\u1d04s \u279a \u221e U\u0274\u029f\u026a\u1d0d\u026a\u1d1b\u026a\u1d1b\u1d07\u1d05\n"
    "P\u0280\u026a\u1d04\u1d07  \u279a 30$\n"
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
)

PAYMENT_PENDING_TEXT = (
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
    "Payment Address\n"
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
    "Payment address will be added soon.\n\n"
    "For payment and activation contact support.\n\n"
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
)

FORCED_JOIN_CAPTION = (
    "BATMAN CARD CHECKER\n\n"
    "Access Required\n"
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
    "Join our channel and group to unlock the bot.\n"
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
)


def get_styled_plan(raw_plan: str) -> str:
    p = raw_plan.upper()
    if p == "CORE":
        return "Core"
    if p == "ELITE":
        return "Elite"
    if p == "ROOT":
        return "Root"
    return "Trial"


def get_user_data(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> dict:
    uid = str(user_id)
    if "user_data" not in context.bot_data:
        context.bot_data["user_data"] = {}
    if uid not in context.bot_data["user_data"]:
        context.bot_data["user_data"][uid] = {
            "name": "User",
            "joined": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "credits": 150,
            "plan": "TRIAL",
            "expires": 0,
        }
    return context.bot_data["user_data"][uid]


def gen_code(length: int = 10) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


def gen_receipt() -> str:
    return f"BATCARD-{random.randint(100000, 999999)}-CHK"


def ui_profile(user, context: ContextTypes.DEFAULT_TYPE) -> str:
    uname = user.username or "None"
    ud = get_user_data(user.id, context)
    raw_plan = ud.get("plan", "TRIAL").upper()
    expires = ud.get("expires", 0)
    now = time.time()
    if raw_plan != "TRIAL" and expires <= now:
        raw_plan = "TRIAL"
        ud["plan"] = "TRIAL"
        ud["expires"] = 0
    is_premium = raw_plan != "TRIAL"
    credits = "\u221e Unlimited" if is_premium else f"{ud.get('credits', 150)}/150"
    lines = [
        f"User    : {uname}",
        f"User ID : <code>{user.id}</code>",
        f"Plan    : {get_styled_plan(raw_plan)}",
        f"Credits : {credits}",
    ]
    if is_premium and expires > now:
        exp_date = datetime.fromtimestamp(expires).strftime("%Y-%m-%d %H:%M")
        remaining = int((expires - now) / 86400)
        remaining_hrs = int(((expires - now) % 86400) / 3600)
        lines.append(f"Expires  : {exp_date}")
        if remaining > 0:
            lines.append(f"Remaining: {remaining}d {remaining_hrs}h")
        else:
            lines.append(f"Remaining: {remaining_hrs}h")
    lines.append(f"Joined  : {ud.get('joined', datetime.now().strftime('%Y-%m-%d'))}")
    lines.append(f"Dev     : <a href='{DEV_LINK}'>Batman</a>")
    return "\n".join(lines)


async def send_activation_msg(
    user_id: int, plan: str, days: int, context: ContextTypes.DEFAULT_TYPE
) -> str:
    receipt = gen_receipt()
    name, username = "Unknown", "None"
    try:
        chat = await context.bot.get_chat(user_id)
        name = chat.first_name or "Unknown"
        username = chat.username or "None"
    except Exception:
        pass
    ud = get_user_data(user_id, context)
    ud["name"] = name
    ud["plan"] = plan
    ud["expires"] = time.time() + (days * 86400)
    exp_date = datetime.fromtimestamp(ud["expires"]).strftime("%Y-%m-%d %H:%M")
    txt = (
        "Congratulations! Your access has been activated.\n"
        "\u2501" * 20 + "\n\n"
        f"User    : {name}\n"
        f"Username: @{username}\n"
        f"Access  : {get_styled_plan(plan)}\n"
        f"Duration: {days} Days\n"
        "Credits : \u221e Unlimited\n"
        f"Expires : {exp_date}\n"
        f"Receipt : <code>{receipt}</code>\n\n"
        "\u2501" * 20 + "\n"
        "Please save this receipt ID."
    )
    try:
        await context.bot.send_message(chat_id=user_id, text=txt, parse_mode="HTML")
    except Exception:
        pass
    return receipt


async def is_joined(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    async def check(chat_id: str) -> bool:
        try:
            status = (
                await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            ).status
            return status not in ("left", "kicked")
        except Exception:
            return False
    return await check(CHANNEL_USERNAME) and await check(GROUP_USERNAME)


async def resolve_user(target: str, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    target = target.lstrip("@")
    if target.lstrip("-").isdigit():
        return int(target)
    try:
        return (await context.bot.get_chat(f"@{target}")).id
    except Exception:
        return None


async def send_welcome_photo(
    update: Update, caption: str, markup: InlineKeyboardMarkup
) -> None:
    try:
        with open(WELCOME_IMAGE_PATH, "rb") as img:
            await update.message.reply_photo(
                photo=img,
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup,
            )
    except Exception:
        await update.message.reply_text(
            caption,
            parse_mode="HTML",
            reply_markup=markup,
            disable_web_page_preview=True,
        )


def kb_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("CHECKER", callback_data="mgates"),
            InlineKeyboardButton("BUY NOW", callback_data="mprice"),
        ],
        [
            InlineKeyboardButton("UPDATES", url=CHANNEL_LINK),
            InlineKeyboardButton("GROUP",   url=GROUP_LINK),
        ],
        [InlineKeyboardButton("SUPPORT", url=SUPPORT_LINK)],
    ])


def kb_force() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("JOIN CHANNEL", url=CHANNEL_LINK)],
        [InlineKeyboardButton("JOIN GROUP",   url=GROUP_LINK)],
        [InlineKeyboardButton("VERIFY",       callback_data="verify_join")],
    ])


def kb_back(cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("BACK", callback_data=cb)]])


def kb_bin_result() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Batcardchk", url=BOT_LINK)]])


def kb_price() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("10$PAY", callback_data="pay10"),
            InlineKeyboardButton("15$PAY", callback_data="pay15"),
            InlineKeyboardButton("30$PAY", callback_data="pay30"),
        ],
        [InlineKeyboardButton("BACK", callback_data="bmain")],
    ])


def kb_payment() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("SUPPORT", url=SUPPORT_LINK)],
        [InlineKeyboardButton("BACK",    callback_data="mprice")],
    ])


def kb_gate_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("AUTH",   callback_data="mauth"),
            InlineKeyboardButton("CHARGE", callback_data="mcharge"),
            InlineKeyboardButton("MASS",   callback_data="mmass"),
        ],
        [InlineKeyboardButton("BACK", callback_data="bmain")],
    ])


def kb_auth_gates() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("STRIPE",    callback_data="iau"),
            InlineKeyboardButton("BRAINTREE", callback_data="ib3"),
        ],
        [InlineKeyboardButton("BACK", callback_data="mgates")],
    ])


def kb_charge_gates() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("STRIPE",  callback_data="ichk"),
            InlineKeyboardButton("PAYPAL",  callback_data="ipp"),
        ],
        [
            InlineKeyboardButton("SHOPIFY", callback_data="ish"),
            InlineKeyboardButton("PAYU",    callback_data="ipyu"),
        ],
        [InlineKeyboardButton("BACK", callback_data="mgates")],
    ])


def kb_mass_gates() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("STRIPE MASS", callback_data="imss")],
        [InlineKeyboardButton("PAYPAL MASS", callback_data="impp2")],
        [InlineKeyboardButton("BACK",        callback_data="mgates")],
    ])


def gate_info_text(gate_name: str, cmd: str, cost: int) -> str:
    return (
        "\u2501" * 20 + "\n"
        f"{gate_name}\n"
        "\u2501" * 20 + "\n\n"
        f"Cost    : {cost} Credit(s) per check\n\n"
        "Usage:\n"
        f"<code>/{cmd} cc|mm|yy|cvv</code>\n\n"
        "Example:\n"
        f"<code>/{cmd} 4111111111111111|12|2026|123</code>\n\n"
        "\u2501" * 20
    )


async def maintenance_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    if (
        context.bot_data.get("maintenance", False)
        and update.effective_user.id != OWNER_ID
    ):
        try:
            if update.message:
                await update.message.reply_text("Bot is currently under maintenance.")
        except Exception:
            pass
        raise ApplicationHandlerStop


async def anti_ad_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.from_user:
        return
    if msg.from_user.id == OWNER_ID:
        return
    text = (msg.text or msg.caption or "").lower()
    if not text:
        return
    for w in BLOCK_WORDS:
        if w.lower() in text:
            try:
                await msg.delete()
            except Exception:
                pass
            return


async def fetch_bin(url: str) -> dict:
    try:
        req = urllib.request.Request(
            url, headers={"Accept-Version": "3", "User-Agent": "Mozilla/5.0"}
        )
        loop = asyncio.get_running_loop()
        def do_req():
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read().decode("utf-8"))
        return await loop.run_in_executor(None, do_req)
    except Exception:
        return {}


async def _api_request(
    session: aiohttp.ClientSession, url: str, card: str, site: str
) -> dict:
    async with session.get(url, params={"cc": card, "site": site}) as resp:
        try:
            data = await resp.json(content_type=None)
        except Exception:
            data = {"value": await resp.text()}
        if not isinstance(data, dict):
            data = {"value": str(data)}
        return data


async def process_gate(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    gate_key: str,
    gate_name: str,
):
    if not context.bot_data.get(f"{gate_key}_on", True):
        await update.message.reply_text("Gate is currently OFF.")
        return
    card = None
    if context.args:
        card = context.args[0]
    elif (
        update.message.reply_to_message
        and update.message.reply_to_message.text
    ):
        card = update.message.reply_to_message.text.strip()
    if not card:
        await update.message.reply_text(
            f"Usage: <code>/{gate_key} cc|mm|yy|cvv</code>", parse_mode="HTML"
        )
        return
    ud = get_user_data(update.effective_user.id, context)
    raw_plan = ud.get("plan", "TRIAL").upper()
    is_premium = raw_plan != "TRIAL" and ud.get("expires", 0) > time.time()
    if not is_premium:
        credits = ud.get("credits", 150)
        if credits <= 0:
            await update.message.reply_text(
                "Your trial credits are empty. Purchase a plan with /plan to continue."
            )
            return
        ud["credits"] = credits - 1
    bin_num = card[:6]
    msg = await update.message.reply_text("Processing...")
    start_time = time.time()
    api_url = context.bot_data.get(f"gate_url_{gate_key}") or GATE_URLS.get(gate_key, "")
    site_url = GATE_SITES.get(gate_key, "example.com")
    if not api_url:
        await msg.edit_text(
            f"Gate API URL not set. Owner: /seturl {gate_key} &lt;url&gt;",
            parse_mode="HTML",
        )
        return
    try:
        timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            results = await asyncio.gather(
                _api_request(session, api_url, card, site_url),
                get_bin_info(bin_num),
                return_exceptions=True,
            )
        data = results[0] if not isinstance(results[0], Exception) else {}
        bin_data = (
            results[1] if not isinstance(results[1], Exception) else {"error": True}
        )
        if isinstance(results[0], Exception):
            raise results[0]
        raw_response = str(
            data.get("value") or data.get("message") or data.get("category") or "ERROR"
        ).strip()
        is_approved = any(
            w in raw_response.lower() for w in ["approved", "captured", "success"]
        )
        status_ui = "APPROVED" if is_approved else "DECLINED"
        bin_txt = "N/A"
        if not bin_data.get("error"):
            s = str(bin_data.get("scheme", "N/A")).upper()
            b = bin_data.get("bank", "N/A")
            country = str(bin_data.get("country", "N/A")).upper()
            flag = bin_data.get("country_emoji", "")
            bin_txt = f"{s} - {b} - {flag} {country}"
        if raw_plan != "TRIAL" and ud.get("expires", 0) <= time.time():
            raw_plan = "TRIAL"
        plan_ui = get_styled_plan(raw_plan)
        first_name = update.effective_user.first_name or "User"
        time_taken = f"{time.time() - start_time:.2f}"
        text = (
            f"[ STATUS ] : {status_ui}\n"
            f"Card : {card}\n"
            f"Gate : {gate_name}\n"
            f"Raw  : {raw_response}\n"
            f"Info : {bin_txt}\n"
            f"User : {first_name} ({plan_ui})\n"
            f"Bot  : Batman\n"
            f"Time : {time_taken}s"
        )
        await msg.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=kb_result(),
            disable_web_page_preview=True,
        )
    except aiohttp.ServerTimeoutError:
        await msg.edit_text("Timeout - Gate did not respond in time.")
    except Exception as e:
        logger.error(f"process_gate [{gate_key}]: {e}")
        await msg.edit_text(f"Error: <code>{str(e)[:120]}</code>", parse_mode="HTML")


async def cmd_chk(u, c):  await process_gate(u, c, "chk",  "Stripe Charge")
async def cmd_pp(u, c):   await process_gate(u, c, "pp",   "PayPal Charge")
async def cmd_sh(u, c):   await process_gate(u, c, "sh",   "Shopify Charge")
async def cmd_pyu(u, c):  await process_gate(u, c, "pyu",  "PayU Charge")
async def cmd_b3(u, c):   await process_gate(u, c, "b3",   "Braintree Auth")
async def cmd_au(u, c):   await process_gate(u, c, "au",   "Stripe Auth")
async def cmd_mss(u, c):  await process_gate(u, c, "mss",  "Stripe Mass")
async def cmd_mpp2(u, c): await process_gate(u, c, "mpp2", "PayPal Mass")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ud = get_user_data(user.id, context)
    ud.setdefault("joined", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    ud.setdefault("name", user.first_name or "User")
    if await is_joined(user.id, context):
        await send_welcome_photo(update, ui_profile(user, context), kb_main())
    else:
        await send_welcome_photo(update, FORCED_JOIN_CAPTION, kb_force())


async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Pong! Bot is online.")


async def cmd_bin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Usage: /bin &lt;BIN&gt;\nExample: /bin 453201", parse_mode="HTML"
        )
        return
    bin_num = "".join(filter(str.isdigit, context.args[0]))[:6]
    if len(bin_num) < 6:
        await update.message.reply_text("Invalid BIN!")
        return
    status = await update.message.reply_text(
        f"Looking up BIN: <code>{bin_num}</code>...", parse_mode="HTML"
    )
    data = await fetch_bin(f"https://lookup.binlist.net/{bin_num}")
    if not data or "scheme" not in data:
        try:
            await status.edit_text("BIN not found.")
        except Exception:
            pass
        return
    c_data = data.get("country") or {}
    b_data = data.get("bank") or {}
    user = update.effective_user
    ud = get_user_data(user.id, context)
    raw_plan = ud.get("plan", "TRIAL").upper()
    if raw_plan != "TRIAL" and ud.get("expires", 0) <= time.time():
        raw_plan = "TRIAL"
    brand        = (data.get("scheme") or "N/A").upper()
    level        = (data.get("brand")  or "N/A").upper()
    bank         = (b_data.get("name") or "N/A").upper()
    country_code = (c_data.get("alpha2") or "N/A").upper()
    country_flag = c_data.get("emoji", "")
    country_name = (c_data.get("name") or "N/A").upper()
    card_type    = (data.get("type")   or "N/A").upper()
    currency     = COUNTRY_CURRENCY.get(country_code, "N/A")
    txt = (
        f"Bin     : <code>{bin_num}</code>\n"
        f"Brand   : {brand}\n"
        f"Level   : {level}\n"
        f"Bank    : {bank}\n"
        f"Country : {country_flag} {country_name}\n"
        f"Type    : {card_type}\n"
        f"Currency: {currency}\n"
        f"User    : {user.first_name or 'User'} ({get_styled_plan(raw_plan)})\n"
        f"Dev     : Batman"
    )
    try:
        await status.edit_text(
            txt,
            parse_mode="HTML",
            reply_markup=kb_bin_result(),
            disable_web_page_preview=True,
        )
    except Exception:
        pass


async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        PLAN_TEXT,
        parse_mode="HTML",
        reply_markup=kb_price(),
        disable_web_page_preview=True,
    )


async def cmd_rm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /rm &lt;code&gt;", parse_mode="HTML")
        return
    code = context.args[0].upper()
    uid  = update.effective_user.id
    ud   = get_user_data(uid, context)
    codes = context.bot_data.get("codes", {})
    keys  = context.bot_data.get("keys",  {})
    if code in codes and not codes[code]["used"]:
        codes[code]["used"] = True
        ud["credits"] = ud.get("credits", 0) + codes[code]["value"]
        await update.message.reply_text(
            f"Redeemed! Added {codes[code]['value']} credits. Balance: {ud['credits']}/150"
        )
    elif code in keys and not keys[code]["used"]:
        keys[code]["used"] = True
        p, d = keys[code]["plan"], keys[code]["days"]
        ud["plan"] = p
        ud["expires"] = time.time() + (d * 86400)
        receipt = await send_activation_msg(uid, p, d, context)
        await update.message.reply_text(
            f"Activated {get_styled_plan(p)} for {d} days.\nReceipt: <code>{receipt}</code>",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text("Invalid or already used code.")


async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not update.message.reply_to_message and not context.args:
        await update.message.reply_text("Usage: /info &lt;user_id&gt;", parse_mode="HTML")
        return
    target_id = (
        update.message.reply_to_message.from_user.id
        if update.message.reply_to_message
        else await resolve_user(context.args[0], context)
    )
    if not target_id:
        await update.message.reply_text("User not found.")
        return
    name, username, uid = "N/A", "None", target_id
    try:
        u = await context.bot.get_chat(target_id)
        name     = u.first_name or "N/A"
        username = u.username   or "None"
        uid      = u.id
    except Exception:
        pass
    udata    = get_user_data(uid, context)
    raw_plan = udata.get("plan", "TRIAL").upper()
    expires  = udata.get("expires", 0)
    now      = time.time()
    if raw_plan != "TRIAL" and expires <= now:
        raw_plan = "TRIAL"
    credits = "\u221e Unlimited" if raw_plan != "TRIAL" else f"{udata.get('credits', 150)}/150"
    txt = (
        "\u2501" * 20 + "\nUSER INFO\n" + "\u2501" * 20 + "\n\n"
        f"Name    : {name}\n"
        f"Username: @{username}\n"
        f"User ID : <code>{uid}</code>\n"
        f"Plan    : {get_styled_plan(raw_plan)}\n"
        f"Credits : {credits}\n"
    )
    if raw_plan != "TRIAL" and expires > now:
        txt += (
            f"Expires : {datetime.fromtimestamp(expires).strftime('%Y-%m-%d %H:%M')}\n"
            f"Remaining: {int((expires - now) / 86400)} Days\n"
        )
    else:
        txt += "Status  : Inactive / Trial\n"
    txt += "\u2501" * 20
    await update.message.reply_text(txt, parse_mode="HTML")


async def cmd_allcm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    await update.message.reply_text(
        f"BATMAN BOT - ALL COMMANDS\n" + "\u2501" * 18 + f"\nVersion: {VERSION}\n" + "\u2501" * 18 + "\n\n"
        "USER COMMANDS\n" + "\u2501" * 18 + "\n"
        "/start  /plan  /bin  /rm  /ping\n"
        "/chk  /pp  /sh  /pyu  /b3  /au  /mss  /mpp2\n\n"
        "OWNER COMMANDS\n" + "\u2501" * 18 + "\n"
        "/info  /allcm  /gen\n"
        "/key10  /key20  /key30\n"
        "/sub  /resub  /allplans\n"
        "/oneday  /threeday\n"
        "/seturl  /geturl\n"
        "/onchk  /offchk  /onpp  /offpp\n"
        "/onsh  /offsh  /onpyu  /offpyu\n"
        "/onb3  /offb3  /onau  /offau\n"
        "/onmss  /offmss  /onmpp2  /offmpp2\n"
        "/killbot  /onbot\n" + "\u2501" * 18,
        parse_mode="HTML",
    )


async def cmd_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /gen &lt;credits&gt;", parse_mode="HTML")
        return
    try:
        amt  = int(context.args[0])
        code = gen_code()
        context.bot_data.setdefault("codes", {})[code] = {
            "type": "credit", "value": amt, "used": False
        }
        await update.message.reply_text(
            f"CODE GENERATED\n\nCode: <code>{code}</code>\nCredits: {amt}",
            parse_mode="HTML",
        )
    except ValueError:
        await update.message.reply_text("Invalid amount.")


async def _gen_key(
    update: Update, context: ContextTypes.DEFAULT_TYPE, plan: str, days: int
):
    if update.effective_user.id != OWNER_ID:
        return
    code = "KEY-" + gen_code(12)
    context.bot_data.setdefault("keys", {})[code] = {
        "plan": plan, "days": days, "used": False
    }
    await update.message.reply_text(
        f"KEY GENERATED\n\nKey : <code>{code}</code>\nPlan: {get_styled_plan(plan)}\nDays: {days}",
        parse_mode="HTML",
    )


async def cmd_key10(u, c): await _gen_key(u, c, "core",  7)
async def cmd_key20(u, c): await _gen_key(u, c, "elite", 15)
async def cmd_key30(u, c): await _gen_key(u, c, "root",  30)


async def _grant(
    uid: int, plan: str, days: int,
    update: Update, context: ContextTypes.DEFAULT_TYPE,
):
    ud = get_user_data(uid, context)
    ud["plan"]    = plan
    ud["expires"] = time.time() + (days * 86400)
    receipt = await send_activation_msg(uid, plan, days, context)
    await update.message.reply_text(
        f"Granted {days} Days ({get_styled_plan(plan)}) to <code>{uid}</code>\nReceipt: <code>{receipt}</code>",
        parse_mode="HTML",
    )


async def cmd_oneday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    code = "KEY-" + gen_code(12)
    context.bot_data.setdefault("keys", {})[code] = {
        "plan": "core", "days": 1, "used": False
    }
    await update.message.reply_text(
        f"1 DAY CODE\n\nCode: <code>{code}</code>\nRedeem: /rm {code}", parse_mode="HTML"
    )


async def cmd_threeday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    code = "KEY-" + gen_code(12)
    context.bot_data.setdefault("keys", {})[code] = {
        "plan": "core", "days": 3, "used": False
    }
    await update.message.reply_text(
        f"3 DAYS CODE\n\nCode: <code>{code}</code>\nRedeem: /rm {code}", parse_mode="HTML"
    )


async def cmd_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /sub &lt;user_id&gt; &lt;days&gt;", parse_mode="HTML"
        )
        return
    uid = await resolve_user(context.args[0], context)
    if not uid:
        await update.message.reply_text("User not found.")
        return
    try:
        days = int(context.args[1])
        plan = "root" if days >= 30 else "elite" if days >= 15 else "core"
        await _grant(uid, plan, days, update, context)
    except ValueError:
        await update.message.reply_text("Invalid days.")


async def cmd_resub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /resub &lt;user_id&gt;", parse_mode="HTML")
        return
    uid = await resolve_user(context.args[0], context)
    if not uid:
        await update.message.reply_text("User not found.")
        return
    ud = get_user_data(uid, context)
    ud["plan"]    = "TRIAL"
    ud["expires"] = 0
    await update.message.reply_text(f"Removed premium from <code>{uid}</code>", parse_mode="HTML")


async def cmd_allplans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    users = context.bot_data.get("user_data", {})
    txt   = "ACTIVE PLANS\n" + "\u2501" * 20 + "\n\n"
    found = False
    now   = time.time()
    for uid, data in users.items():
        exp  = data.get("expires", 0)
        plan = data.get("plan", "TRIAL")
        if plan != "TRIAL" and exp > now:
            found = True
            txt  += (
                f"ID       : <code>{uid}</code>\n"
                f"Plan     : {get_styled_plan(plan)}\n"
                f"Remaining: {int((exp - now) / 86400)} Days\n"
                "\u2501" * 20 + "\n"
            )
    if not found:
        txt += "No active plans."
    await update.message.reply_text(txt, parse_mode="HTML")


async def cmd_delcode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /delcode &lt;code&gt;", parse_mode="HTML")
        return
    code  = context.args[0]
    codes = context.bot_data.get("codes", {})
    keys  = context.bot_data.get("keys",  {})
    if code in codes:
        del codes[code]
        await update.message.reply_text("Code deleted.")
    elif code in keys:
        del keys[code]
        await update.message.reply_text("Key deleted.")
    else:
        await update.message.reply_text("Not found.")


async def cmd_seturl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /seturl &lt;gate&gt; &lt;url&gt;\n"
            "Remove: /seturl chk remove\n"
            "Gates: chk pp sh pyu b3 au mss mpp2",
            parse_mode="HTML",
        )
        return
    gate = context.args[0].lower()
    url  = " ".join(context.args[1:])
    if gate not in GATE_NAMES:
        await update.message.reply_text(
            f"Unknown gate: {gate}\nValid: chk pp sh pyu b3 au mss mpp2"
        )
        return
    if url.lower() == "remove":
        context.bot_data.pop(f"gate_url_{gate}", None)
        await update.message.reply_text(f"Removed {GATE_NAMES[gate]} URL.")
        return
    context.bot_data[f"gate_url_{gate}"] = url
    await update.message.reply_text(
        f"{GATE_NAMES[gate]} URL set.\n<code>{url}</code>", parse_mode="HTML"
    )


async def cmd_geturl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    txt = "GATE API URLs\n" + "\u2501" * 20 + "\n\n"
    for gate, name in GATE_NAMES.items():
        override   = context.bot_data.get(f"gate_url_{gate}", "")
        config_url = GATE_URLS.get(gate, "")
        active     = override if override else config_url
        source     = "Override" if override else "Config"
        status     = "ON" if context.bot_data.get(f"{gate}_on", True) else "OFF"
        txt += f"{name} [{status}] [{source}]\n<code>{active or 'Not set'}</code>\n\n"
    txt += "\u2501" * 20
    await update.message.reply_text(txt, parse_mode="HTML")


async def cmd_killbot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    context.bot_data["maintenance"] = True
    await update.message.reply_text("Maintenance Mode ON. Use /onbot to resume.")


async def cmd_onbot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    context.bot_data["maintenance"] = False
    await update.message.reply_text("Bot is back online!")


def _toggle(gate: str, label: str, state: bool):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != OWNER_ID:
            return
        context.bot_data[f"{gate}_on"] = state
        await update.message.reply_text(f"{label} - {'ON' if state else 'OFF'}")
    return handler


cmd_onchk   = _toggle("chk",  "STRIPE CHARGE",  True)
cmd_offchk  = _toggle("chk",  "STRIPE CHARGE",  False)
cmd_onpp    = _toggle("pp",   "PAYPAL CHARGE",  True)
cmd_offpp   = _toggle("pp",   "PAYPAL CHARGE",  False)
cmd_onsh    = _toggle("sh",   "SHOPIFY CHARGE", True)
cmd_offsh   = _toggle("sh",   "SHOPIFY CHARGE", False)
cmd_onpyu   = _toggle("pyu",  "PAYU CHARGE",    True)
cmd_offpyu  = _toggle("pyu",  "PAYU CHARGE",    False)
cmd_onb3    = _toggle("b3",   "BRAINTREE AUTH", True)
cmd_offb3   = _toggle("b3",   "BRAINTREE AUTH", False)
cmd_onau    = _toggle("au",   "STRIPE AUTH",    True)
cmd_offau   = _toggle("au",   "STRIPE AUTH",    False)
cmd_onmss   = _toggle("mss",  "STRIPE MASS",    True)
cmd_offmss  = _toggle("mss",  "STRIPE MASS",    False)
cmd_onmpp2  = _toggle("mpp2", "PAYPAL MASS",    True)
cmd_offmpp2 = _toggle("mpp2", "PAYPAL MASS",    False)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    d = q.data
    try:
        await q.answer()
    except Exception:
        pass

    if context.bot_data.get("maintenance", False) and q.from_user.id != OWNER_ID:
        try:
            await q.answer("Bot is under maintenance.", show_alert=True)
        except Exception:
            pass
        return

    async def reply(text: str, markup: InlineKeyboardMarkup):
        try:
            await context.bot.send_message(
                chat_id=q.message.chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=markup,
                disable_web_page_preview=True,
            )
        except Exception as ex:
            logger.error(f"reply failed [{d}]: {ex}")
            try:
                await q.answer(f"Error: {str(ex)[:200]}", show_alert=True)
            except Exception:
                pass

    try:
        if d == "verify_join":
            if await is_joined(q.from_user.id, context):
                await reply(ui_profile(q.from_user, context), kb_main())
            else:
                await q.answer("Join channel and group first!", show_alert=True)

        elif d == "bmain":
            await reply(ui_profile(q.from_user, context), kb_main())

        elif d == "mprice":
            await reply(PLAN_TEXT, kb_price())

        elif d == "pay10":
            await reply(
                "PAYMENT - 10$ (Core | 7 Days)\n\n" + PAYMENT_PENDING_TEXT,
                kb_payment(),
            )

        elif d == "pay15":
            await reply(
                "PAYMENT - 15$ (Elite | 15 Days)\n\n" + PAYMENT_PENDING_TEXT,
                kb_payment(),
            )

        elif d == "pay30":
            await reply(
                "PAYMENT - 30$ (Root | 30 Days)\n\n" + PAYMENT_PENDING_TEXT,
                kb_payment(),
            )

        elif d == "mgates":
            await reply(CHECKER_STATUS_TEXT, kb_gate_main())

        elif d == "mauth":
            await reply(AUTH_MENU_TEXT, kb_auth_gates())

        elif d == "iau":
            await reply(STRIPE_AUTH_TEXT, kb_back("mauth"))

        elif d == "ib3":
            await reply(BRAINTREE_TEXT, kb_back("mauth"))

        elif d == "mcharge":
            await reply(CHARGE_MENU_TEXT, kb_charge_gates())

        elif d == "ichk":
            await reply(gate_info_text("Stripe Charge",  "chk", 1), kb_back("mcharge"))

        elif d == "ipp":
            await reply(gate_info_text("PayPal Charge",  "pp",  1), kb_back("mcharge"))

        elif d == "ish":
            await reply(gate_info_text("Shopify Charge", "sh",  2), kb_back("mcharge"))

        elif d == "ipyu":
            await reply(gate_info_text("PayU Charge",    "pyu", 1), kb_back("mcharge"))

        elif d == "mmass":
            await reply(MASS_MENU_TEXT, kb_mass_gates())

        elif d == "imss":
            await reply(gate_info_text("Stripe Mass",  "mss",  2), kb_back("mmass"))

        elif d == "impp2":
            await reply(gate_info_text("PayPal Mass",  "mpp2", 2), kb_back("mmass"))

        else:
            logger.warning(f"Unknown callback: {d}")

    except Exception as ex:
        logger.error(f"on_callback error [{d}]: {ex}")
        try:
            await q.answer(f"Error: {str(ex)[:200]}", show_alert=True)
        except Exception:
            pass


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    if isinstance(context.error, Conflict):
        return
    logger.error(f"Unhandled error: {context.error}", exc_info=context.error)


async def on_start(app: Application):
    print("Batman Bot starting...")
    try:
        await app.bot.delete_webhook(drop_pending_updates=True)
        await asyncio.sleep(1)
    except Exception:
        pass


def main():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(on_start)
        .build()
    )

    app.add_error_handler(error_handler)

    app.add_handler(MessageHandler(filters.ALL, maintenance_check), group=-1)

    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("ping",     cmd_ping))
    app.add_handler(CommandHandler("plan",     cmd_plan))
    app.add_handler(CommandHandler("buy",      cmd_plan))
    app.add_handler(CommandHandler("bin",      cmd_bin))
    app.add_handler(CommandHandler("rm",       cmd_rm))
    app.add_handler(CommandHandler("chk",      cmd_chk))
    app.add_handler(CommandHandler("pp",       cmd_pp))
    app.add_handler(CommandHandler("sh",       cmd_sh))
    app.add_handler(CommandHandler("pyu",      cmd_pyu))
    app.add_handler(CommandHandler("b3",       cmd_b3))
    app.add_handler(CommandHandler("au",       cmd_au))
    app.add_handler(CommandHandler("mss",      cmd_mss))
    app.add_handler(CommandHandler("mpp2",     cmd_mpp2))
    app.add_handler(CommandHandler("info",     cmd_info))
    app.add_handler(CommandHandler("allcm",    cmd_allcm))
    app.add_handler(CommandHandler("gen",      cmd_gen))
    app.add_handler(CommandHandler("key10",    cmd_key10))
    app.add_handler(CommandHandler("key20",    cmd_key20))
    app.add_handler(CommandHandler("key30",    cmd_key30))
    app.add_handler(CommandHandler("oneday",   cmd_oneday))
    app.add_handler(CommandHandler("threeday", cmd_threeday))
    app.add_handler(CommandHandler("sub",      cmd_sub))
    app.add_handler(CommandHandler("resub",    cmd_resub))
    app.add_handler(CommandHandler("allplans", cmd_allplans))
    app.add_handler(CommandHandler("delcode",  cmd_delcode))
    app.add_handler(CommandHandler("seturl",   cmd_seturl))
    app.add_handler(CommandHandler("geturl",   cmd_geturl))
    app.add_handler(CommandHandler("killbot",  cmd_killbot))
    app.add_handler(CommandHandler("onbot",    cmd_onbot))

    for cmd, func in [
        ("onchk",   cmd_onchk),  ("offchk",  cmd_offchk),
        ("onpp",    cmd_onpp),   ("offpp",   cmd_offpp),
        ("onsh",    cmd_onsh),   ("offsh",   cmd_offsh),
        ("onpyu",   cmd_onpyu),  ("offpyu",  cmd_offpyu),
        ("onb3",    cmd_onb3),   ("offb3",   cmd_offb3),
        ("onau",    cmd_onau),   ("offau",   cmd_offau),
        ("onmss",   cmd_onmss),  ("offmss",  cmd_offmss),
        ("onmpp2",  cmd_onmpp2), ("offmpp2", cmd_offmpp2),
    ]:
        app.add_handler(CommandHandler(cmd, func))

    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, anti_ad_filter))
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, anti_ad_filter))

    print("Batman Bot Online!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
