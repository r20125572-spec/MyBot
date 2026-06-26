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

CHANNEL_LINK       = "https://t.me/Batcardchk"
GROUP_LINK         = "https://t.me/batcardchkGroup"
SUPPORT_LINK       = "https://t.me/cardchkSupport"
BOT_LINK           = "https://t.me/Batmancardchk_bot"

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


# ── Bold Unicode helper for button text ──────────────────────────────────────

def B(text: str) -> str:
    """Convert ASCII text to Unicode bold dark characters for buttons."""
    bold_map = {
        'A': '𝗔', 'B': '𝗕', 'C': '𝗖', 'D': '𝗗', 'E': '𝗘', 'F': '𝗙',
        'G': '𝗚', 'H': '𝗛', 'I': '𝗜', 'J': '𝗝', 'K': '𝗞', 'L': '𝗟',
        'M': '𝗠', 'N': '𝗡', 'O': '𝗢', 'P': '𝗣', 'Q': '𝗤', 'R': '𝗥',
        'S': '𝗦', 'T': '𝗧', 'U': '𝗨', 'V': '𝗩', 'W': '𝗪', 'X': '𝗫',
        'Y': '𝗬', 'Z': '𝗭',
        'a': '𝗮', 'b': '𝗯', 'c': '𝗰', 'd': '𝗱', 'e': '𝗲', 'f': '𝗳',
        'g': '𝗴', 'h': '𝗵', 'i': '𝗶', 'j': '𝗷', 'k': '𝗸', 'l': '𝗹',
        'm': '𝗺', 'n': '𝗻', 'o': '𝗼', 'p': '𝗽', 'q': '𝗾', 'r': '𝗿',
        's': '𝘀', 't': '𝘁', 'u': '𝘂', 'v': '𝘃', 'w': '𝘄', 'x': '𝘅',
        'y': '𝘆', 'z': '𝘇',
        '0': '𝟬', '1': '𝟭', '2': '𝟮', '3': '𝟯', '4': '𝟰',
        '5': '𝟱', '6': '𝟲', '7': '𝟳', '8': '𝟴', '9': '𝟵',
    }
    return "".join(bold_map.get(ch, ch) for ch in text)


# ── Unicode small-caps text blocks ──────────────────────────────────────────

CHECKER_STATUS_TEXT = (
    "\U0001d402\U0001d41a\U0001d42d\U0001d41e\U0001d42c \U0001d412\U0001d42d\U0001d41a\U0001d42d\U0001d42e\U0001d42c:\n"
    "A\u1d1c\u1d1b\u029c G\u1d00\u1d1b\u1d07   \u279a 2\n"
    "M\u1d00\u1d1b\u1d1c G\u1d00\u1d1b\u1d07  \u279a 2\n"
    "C\u029c\u1d00\u0280\u0262\u1d07 G\u1d00\u1d1b\u1d07 \u279a 4\n"
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
    "S\u026a\u1d1b\u1d07\u1d04   \u279a 16\n"
    "H\u1d07\u1d00\u029f\u1d1b\u029c  \u279a 100%\n"
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
)

BRAINTREE_TEXT = (
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
    "G\u1d00\u1d1b\u1d07    \u279a B\u0280\u1d00\u026a\u0274\u1d1b\u0280\u1d07\u1d07 0$\n"
    "C\u1d0f\u1d0d\u1d0d\u1d00\u0274\u1d05 \u279a /b3\n"
    "S\u026a\u1d1b\u1d07\u1d04   \u279a 2\n"
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
    "S\u1d07\u029f\u1d07\u1d04\u1d1b M\u1d00\u1d1b\u1d00 G\u1d00\u1d1b\u1d07 \u279a\n"
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
)

PLAN_TEXT = (
    "\u2501" * 20 + "\n"
    "B\u1d00\u1d1b\u1d0d\u1d00\u0274 P\u0280\u1d07\u1d0d\u026a\u1d1c\u1d0d P\u029f\u1d00\u0274\u1d04\n"
    "\u2501" * 20 + "\n\n"
    "A\u1d04\u1d04\u1d07\u1d1b\u1d04 \u279a C\u1d0f\u0280\u1d07 \U0001F380\n"
    "S\u1d18\u1d00\u0274   \u279a [7 D\u1d00y\u1d1c]\n"
    "C\u0280\u1d07\u1d05\u026a\u1d1b\u1d04 \u279a \u221e U\u0274\u029f\u026a\u1d0d\u026a\u1d1b\u026a\u1d1b\u1d07\u1d05\n"
    "P\u0280\u026a\u1d04\u1d07  \u279a 10$\n"
    "\u2501" * 16 + "\n"
    "A\u1d04\u1d04\u1d07\u1d1b\u1d04 \u279a E\u029f\u026a\u1d1b\u1d07 \u2b50\ufe0f\n"
    "S\u1d18\u1d00\u0274   \u279a [15 D\u1d00y\u1d1c]\n"
    "C\u0280\u1d07\u1d05\u026a\u1d1b\u1d04 \u279a \u221e U\u0274\u029f\u026a\u1d0d\u026a\u1d1b\u026a\u1d1b\u1d07\u1d05\n"
    "P\u0280\u026a\u1d04\u1d07  \u279a 15$\n"
    "\u2501" * 16 + "\n"
    "A\u1d04\u1d04\u1d07\u1d1b\u1d04 \u279a R\u1d0f\u1d0f\u1d1b \U0001F451\n"
    "S\u1d18\u1d00\u0274   \u279a [30 D\u1d00y\u1d1c]\n"
    "C\u0280\u1d07\u1d05\u026a\u1d1b\u1d04 \u279a \u221e U\u0274\u029f\u026a\u1d0d\u026a\u1d1b\u026a\u1d1b\u1d07\u1d05\n"
    "P\u0280\u026a\u1d04\u1d07  \u279a 30$\n"
    "\u2501" * 20
)

PAYMENT_PENDING_TEXT = (
    "\u2501" * 20 + "\n"
    "P\u1d00y\u1d0d\u1d07\u0274\u1d1b A\u1d05\u1d05\u0280\u1d07\u1d1b\u1d04\n"
    "\u2501" * 20 + "\n\n"
    "P\u1d00y\u1d0d\u1d07\u0274\u1d1b \u1d00\u1d05\u1d05\u0280\u1d07\u1d1b\u1d04 \u1d21\u026a\u029f\u029f \u0299\u1d07 \u1d00\u1d05\u1d05\u1d07\u1d05 \u1d1c\u029f\u1d0f\u0280\u1d1b\u029f\u029f\u029f y.\n\n"
    "F\u1d0f\u0280 \u1d18\u1d00y\u1d0d\u1d07\u0274\u1d1b \u1d04\u1d0f\u0274\u1d1b\u1d00\u1d04\u1d1b \u1d1b\u0280\u1d0f\u1d1c\u0262\u029c \u1d04\u1d1c\u1d18\u1d18\u1d0f\u0280\u1d1b.\n\n"
    "\u2501" * 20
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def get_styled_plan(raw_plan: str) -> str:
    p = raw_plan.upper()
    if p == "CORE":
        return "C\u1d0f\u0280\u1d07"
    if p == "ELITE":
        return "E\u029f\u026a\u1d1b\u1d07"
    if p == "ROOT":
        return "R\u1d0f\u1d0f\u1d1b"
    return "T\u0280\u026a\u1d00\u029f"


def get_user_data(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> dict:
    uid = str(user_id)
    if "user_data" not in context.bot_data:
        context.bot_data["user_data"] = {}
    if uid not in context.bot_data["user_data"]:
        context.bot_data["user_data"][uid] = {
            "name":    "User",
            "joined":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "credits": 150,
            "plan":    "TRIAL",
            "expires": 0,
        }
    return context.bot_data["user_data"][uid]


def gen_code(length: int = 10) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


def gen_receipt() -> str:
    return f"BATCARD-{random.randint(100000, 999999)}-CHK"


def ui_profile(user, context: ContextTypes.DEFAULT_TYPE) -> str:
    ud       = get_user_data(user.id, context)
    raw_plan = ud.get("plan", "TRIAL").upper()
    expires  = ud.get("expires", 0)
    now      = time.time()
    if raw_plan != "TRIAL" and expires <= now:
        raw_plan      = "TRIAL"
        ud["plan"]    = "TRIAL"
        ud["expires"] = 0
        expires       = 0
    is_premium = raw_plan != "TRIAL"
    credits    = "\u221e U\u0274\u029f\u026a\u1d0d\u026a\u1d1b\u1d07\u1d05" if is_premium else f"{ud.get('credits', 150)}/150"
    uname_raw  = user.username
    uname      = f"@{uname_raw}" if uname_raw else "None"
    lines = [
        f"U\u1d1b\u026a\u029f    \u279a {uname}",
        f"U\u1d1b\u026a\u029f ID \u279a <code>{user.id}</code>",
        f"P\u029f\u1d00\u0274    \u279a {get_styled_plan(raw_plan)}",
        f"C\u0280\u1d07\u1d05\u026a\u1d1b\u1d04 \u279a {credits}",
    ]
    if is_premium and expires > now:
        exp_date    = datetime.fromtimestamp(expires).strftime("%Y-%m-%d %H:%M")
        remaining_d = int((expires - now) / 86400)
        remaining_h = int(((expires - now) % 86400) / 3600)
        lines.append(f"E\u02e3\u1d18\u026a\u0280\u1d07\u1d04  \u279a {exp_date}")
        if remaining_d > 0:
            lines.append(f"R\u1d07\u1d0d\u1d00\u026a\u0274\u026a\u0274\u0262 \u279a {remaining_d}d {remaining_h}h")
        else:
            lines.append(f"R\u1d07\u1d0d\u1d00\u026a\u0274\u026a\u0274\u0262 \u279a {remaining_h}h")
    lines.append(f"J\u1d0f\u026a\u0274\u1d07\u1d05  \u279a {ud.get('joined', datetime.now().strftime('%Y-%m-%d'))}")
    lines.append(f"D\u1d07\u1d20    \u279a <a href='{DEV_LINK}'>Batman</a>")
    return "\n".join(lines)


async def send_activation_msg(
    user_id: int, plan: str, days: int, context: ContextTypes.DEFAULT_TYPE
) -> str:
    receipt  = gen_receipt()
    name     = "Unknown"
    username = None
    try:
        chat     = await context.bot.get_chat(user_id)
        name     = chat.first_name or "Unknown"
        username = chat.username or None
    except Exception:
        pass
    ud = get_user_data(user_id, context)
    ud["name"]    = name
    ud["plan"]    = plan
    ud["expires"] = time.time() + (days * 86400)
    exp_date      = datetime.fromtimestamp(ud["expires"]).strftime("%Y-%m-%d %H:%M")
    uname_display = f"@{username}" if username else "None"
    txt = (
        "C\u1d0f\u0274\u0262\u0280\u1d00\u1d1b\u1d1c\u029f\u1d00\u1d1b\u026a\u1d0f\u0274\u1d1b! Y\u1d0f\u1d1c\u0280 \u1d00\u1d04\u1d04\u1d07\u1d1c\u1d04 \u029c\u1d00\u1d1b \u0299\u1d07\u1d07\u0274 \u1d00\u1d04\u1d1b\u026a\u1d20\u1d00\u1d1b\u1d07\u1d05.\n"
        + "\u2501" * 20 + "\n\n"
        f"U\u1d1b\u026a\u029f     \u279a {name}\n"
        f"U\u1d1b\u026a\u029f\u0274\u1d00\u1d0d\u1d07 \u279a {uname_display}\n"
        f"A\u1d04\u1d04\u1d07\u1d1b\u1d04   \u279a {get_styled_plan(plan)}\n"
        f"D\u1d1c\u0280\u1d00\u1d1b\u026a\u1d0f\u0274  \u279a {days} D\u1d00y\u1d1c\n"
        "C\u0280\u1d07\u1d05\u026a\u1d1b\u1d04   \u279a \u221e U\u0274\u029f\u026a\u1d0d\u026a\u1d1b\u1d07\u1d05\n"
        f"E\u02e3\u1d18\u026a\u0280\u1d07\u1d04   \u279a {exp_date}\n"
        f"R\u1d07\u1d04\u1d07\u026a\u1d18\u1d1b  \u279a <code>{receipt}</code>\n\n"
        + "\u2501" * 20 + "\n"
        "P\u029f\u1d07\u1d00\u1d1b\u1d07 \u1d1c\u1d00\u1d20\u1d07 \u1d1b\u029c\u026a\u1d1c \u0280\u1d07\u1d04\u1d07\u026a\u1d18\u1d1b ID."
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
            chat = await context.bot.get_chat(attempt)
            return chat.id
        except Exception:
            continue
    return None


# ── Keyboard helpers (all bold dark) ─────────────────────────────────────────

def kb_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(B("CHECKER"), callback_data="mgates"),
            InlineKeyboardButton(B("BUY NOW"), callback_data="mprice"),
        ],
        [
            InlineKeyboardButton(B("UPDATES"), url=CHANNEL_LINK),
            InlineKeyboardButton(B("GROUP"),   url=GROUP_LINK),
        ],
        [InlineKeyboardButton(B("SUPPORT"), url=SUPPORT_LINK)],
    ])


def kb_back(cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(B("BACK"), callback_data=cb)]])


def kb_bin_result() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(B("Batcardchk"), url=BOT_LINK)]])


def kb_price() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(B("10$PAY"), callback_data="pay10"),
            InlineKeyboardButton(B("15$PAY"), callback_data="pay15"),
            InlineKeyboardButton(B("30$PAY"), callback_data="pay30"),
        ],
        [InlineKeyboardButton(B("BACK"), callback_data="bmain")],
    ])


def kb_payment() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("SUPPORT"), url=SUPPORT_LINK)],
        [InlineKeyboardButton(B("BACK"),    callback_data="mprice")],
    ])


def kb_gate_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(B("AUTH"),   callback_data="mauth"),
            InlineKeyboardButton(B("CHARGE"), callback_data="mcharge"),
            InlineKeyboardButton(B("MASS"),   callback_data="mmass"),
        ],
        [InlineKeyboardButton(B("BACK"), callback_data="bmain")],
    ])


def kb_auth_gates() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(B("STRIPE"),    callback_data="iau"),
            InlineKeyboardButton(B("BRAINTREE"), callback_data="ib3"),
        ],
        [InlineKeyboardButton(B("BACK"), callback_data="mgates")],
    ])


def kb_charge_gates() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(B("STRIPE"),  callback_data="ichk"),
            InlineKeyboardButton(B("PAYPAL"),  callback_data="ipp"),
        ],
        [
            InlineKeyboardButton(B("SHOPIFY"), callback_data="ish"),
            InlineKeyboardButton(B("PAYU"),    callback_data="ipyu"),
        ],
        [InlineKeyboardButton(B("BACK"), callback_data="mgates")],
    ])


def kb_mass_gates() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("STRIPE MASS"), callback_data="imss")],
        [InlineKeyboardButton(B("PAYPAL MASS"), callback_data="impp2")],
        [InlineKeyboardButton(B("BACK"),        callback_data="mgates")],
    ])


def gate_info_text(gate_name: str, cmd: str, cost: int) -> str:
    line = "\u2501" * 20
    return (
        f"{line}\n"
        f"{gate_name}\n"
        f"{line}\n\n"
        f"C\u1d0f\u1d1b\u1d1b    \u279a {cost} C\u0280\u1d07\u1d05\u026a\u1d1b(\u1d1c) \u1d18\u1d07\u0280 \u1d04\u029c\u1d07\u1d04\u1d04\n\n"
        "U\u1d1b\u1d00\u0262\u1d07:\n"
        f"<code>/{cmd} cc|mm|yy|cvv</code>\n\n"
        "E\u02e3\u1d00\u1d0d\u1d18\u029f\u1d07:\n"
        f"<code>/{cmd} 4111111111111111|12|2026|123</code>\n\n"
        f"{line}"
    )


# ── Middleware ───────────────────────────────────────────────────────────────

async def maintenance_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    if (
        context.bot_data.get("maintenance", False)
        and update.effective_user.id != OWNER_ID
    ):
        try:
            if update.message:
                await update.message.reply_text(
                    "B\u1d0f\u1d1b \u026a\u0274 \u1d1c\u1d1c\u029f\u026a\u1d07\u0274\u1d1b\u029f\u029f y \u1d1c\u0274\u1d05\u1d07\u0280 \u1d0d\u1d00\u026a\u0274\u1d1b\u1d07\u0274\u1d00\u0274\u1d04\u1d07."
                )
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


# ── BIN lookup ───────────────────────────────────────────────────────────────

async def fetch_bin(url: str) -> dict:
    try:
        req  = urllib.request.Request(
            url, headers={"Accept-Version": "3", "User-Agent": "Mozilla/5.0"}
        )
        loop = asyncio.get_running_loop()
        def do_req():
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read().decode("utf-8"))
        return await loop.run_in_executor(None, do_req)
    except Exception:
        return {}


# ── Gate processing ──────────────────────────────────────────────────────────

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
        await update.message.reply_text("G\u1d00\u1d1b\u1d07 \u026a\u1d1c \u1d04\u1d1c\u0280\u0280\u1d07\u0274\u1d1b\u029f\u029f OFF.")
        return
    card = None
    if context.args:
        card = context.args[0]
    elif update.message.reply_to_message and update.message.reply_to_message.text:
        card = update.message.reply_to_message.text.strip()
    if not card:
        await update.message.reply_text(
            f"U\u1d1b\u1d00\u0262\u1d07: <code>/{gate_key} cc|mm|yy|cvv</code>",
            parse_mode="HTML",
        )
        return
    ud         = get_user_data(update.effective_user.id, context)
    raw_plan   = ud.get("plan", "TRIAL").upper()
    is_premium = raw_plan != "TRIAL" and ud.get("expires", 0) > time.time()
    if not is_premium:
        credits = ud.get("credits", 150)
        if credits <= 0:
            await update.message.reply_text(
                "Y\u1d0f\u1d1c\u0280 \u1d1b\u0280\u026a\u1d00\u029f \u1d04\u0280\u1d07\u1d05\u026a\u1d1b\u1d04 \u1d00\u0280\u1d07 \u1d07\u1d0d\u1d18\u1d1b\u029f. \u1d18\u1d1c\u0280\u1d04\u029c\u1d00\u1d1b\u1d07 \u1d00 \u1d18\u029f\u1d00\u0274 \u1d21\u026a\u1d1b\u029c /plan."
            )
            return
        ud["credits"] = credits - 1
    bin_num    = card[:6]
    msg        = await update.message.reply_text("P\u0280\u1d0f\u1d04\u1d07\u1d1c\u1d1c\u026a\u0274\u0262...")
    start_time = time.time()
    api_url    = context.bot_data.get(f"gate_url_{gate_key}") or GATE_URLS.get(gate_key, "")
    site_url   = GATE_SITES.get(gate_key, "example.com")
    if not api_url:
        await msg.edit_text(
            f"G\u1d00\u1d1b\u1d07 API URL \u0274\u1d0f\u1d1c \u1d1c\u1d07\u1d1b. O\u1d21\u0274\u1d07\u0280: /seturl {gate_key} &lt;url&gt;",
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
        data     = results[0] if not isinstance(results[0], Exception) else {}
        bin_data = results[1] if not isinstance(results[1], Exception) else {"error": True}
        if isinstance(results[0], Exception):
            raise results[0]
        raw_response = str(
            data.get("value") or data.get("message") or data.get("category") or "ERROR"
        ).strip()
        is_approved = any(
            w in raw_response.lower() for w in ["approved", "captured", "success"]
        )
        status_ui = "APPROVED \u2705" if is_approved else "DECLINED \u274c"
        bin_txt   = "N/A"
        if not bin_data.get("error"):
            s       = str(bin_data.get("scheme", "N/A")).upper()
            b       = bin_data.get("bank", "N/A")
            country = str(bin_data.get("country", "N/A")).upper()
            flag    = bin_data.get("country_emoji", "")
            bin_txt = f"{s} - {b} - {flag} {country}"
        if raw_plan != "TRIAL" and ud.get("expires", 0) <= time.time():
            raw_plan = "TRIAL"
        plan_ui    = get_styled_plan(raw_plan)
        first_name = update.effective_user.first_name or "User"
        time_taken = f"{time.time() - start_time:.2f}"
        text = (
            f"[ STATUS ] \u279a {status_ui}\n"
            f"C\u1d00\u0280\u1d05 \u279a <code>{card}</code>\n"
            f"G\u1d00\u1d1b\u1d07 \u279a {gate_name}\n"
            f"R\u1d00\u1d21  \u279a {raw_response}\n"
            f"I\u0274\u1d0f\u279a {bin_txt}\n"
            f"U\u1d1b\u026a\u029f \u279a {first_name} ({plan_ui})\n"
            f"B\u1d0f\u1d1b  \u279a Batman\n"
            f"T\u026a\u1d0d\u1d07 \u279a {time_taken}s"
        )
        await msg.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=kb_result(),
            disable_web_page_preview=True,
        )
    except aiohttp.ServerTimeoutError:
        await msg.edit_text("T\u026a\u1d0d\u1d07\u1d0f\u1d1c\u1d1b \u2014 G\u1d00\u1d1b\u1d07 \u1d05\u026a\u1d05 \u0274\u1d0f\u1d1c \u0280\u1d07\u1d04\u1d18\u1d0f\u1d05.")
    except Exception as e:
        logger.error(f"process_gate [{gate_key}]: {e}")
        await msg.edit_text(f"E\u0280\u0280\u1d0f\u0280: <code>{str(e)[:120]}</code>", parse_mode="HTML")


async def cmd_chk(u, c):  await process_gate(u, c, "chk",  "Stripe Charge")
async def cmd_pp(u, c):   await process_gate(u, c, "pp",   "PayPal Charge")
async def cmd_sh(u, c):   await process_gate(u, c, "sh",   "Shopify Charge")
async def cmd_pyu(u, c):  await process_gate(u, c, "pyu",  "PayU Charge")
async def cmd_b3(u, c):   await process_gate(u, c, "b3",   "Braintree Auth")
async def cmd_au(u, c):   await process_gate(u, c, "au",   "Stripe Auth")
async def cmd_mss(u, c):  await process_gate(u, c, "mss",  "Stripe Mass")
async def cmd_mpp2(u, c): await process_gate(u, c, "mpp2", "PayPal Mass")


# ── /start (no image, no force join) ─────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ud   = get_user_data(user.id, context)
    ud.setdefault("joined", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    ud.setdefault("name",   user.first_name or "User")
    await update.message.reply_text(
        ui_profile(user, context),
        parse_mode="HTML",
        reply_markup=kb_main(),
        disable_web_page_preview=True,
    )


# ── /ping ────────────────────────────────────────────────────────────────────

async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Pong! Bot is online.")


# ── /bin ─────────────────────────────────────────────────────────────────────

async def cmd_bin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "U\u1d1b\u1d00\u0262\u1d07: /bin &lt;BIN&gt;\nE\u02e3\u1d00\u1d0d\u1d18\u029f\u1d07: /bin 453201",
            parse_mode="HTML",
        )
        return
    bin_num = "".join(filter(str.isdigit, context.args[0]))[:6]
    if len(bin_num) < 6:
        await update.message.reply_text("I\u0274\u1d20\u1d00\u029f\u026a\u1d05 BIN!")
        return
    status = await update.message.reply_text(
        f"L\u1d0f\u1d0f\u1d04\u026a\u0274\u0262 \u1d1c\u1d18 BIN: <code>{bin_num}</code>...",
        parse_mode="HTML",
    )
    data = await fetch_bin(f"https://lookup.binlist.net/{bin_num}")
    if not data or "scheme" not in data:
        try:
            await status.edit_text("BIN \u0274\u1d0f\u1d1c \u1d00\u1d20\u1d00\u026a\u029f\u1d00\u0299\u029f\u1d07.")
        except Exception:
            pass
        return
    c_data       = data.get("country") or {}
    b_data       = data.get("bank")    or {}
    user         = update.effective_user
    ud           = get_user_data(user.id, context)
    raw_plan     = ud.get("plan", "TRIAL").upper()
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
        f"\U0001D401\U0001D422\U0001D427 \u279b <code>{bin_num}</code>\n"
        f"\U0001D401\U0001D42B\U0001D41A\U0001D427\U0001D41D \u279b {brand}\n"
        f"\U0001D40B\U0001D41E\U0001D42F\U0001D41E\U0001D425 \u279b {level}\n"
        f"\U0001D401\U0001D41A\U0001D427\U0001D424 \u279b {bank}\n"
        f"\U0001D402\U0001D428\U0001D42E\U0001D427\U0001D42D\U0001D42B\U0001D432 \u279b {country_flag} {country_name}\n"
        f"\U0001D413\U0001D432\U0001D429\U0001D41E \u279b {card_type}\n"
        f"\U0001D402\U0001D432\U0001D42B\U0001D42B\U0001D41E\U0001D427\U0001D41C\U0001D432 \u279b {currency}\n"
        f"\U0001D41C\U0001D41E\U0001D42B \u279b {user.first_name or 'User'} ({get_styled_plan(raw_plan)})\n"
        f"\U0001D403\U0001D41E\U0001D42F \u279b Batman"
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


# ── /plan ────────────────────────────────────────────────────────────────────

async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        PLAN_TEXT,
        parse_mode="HTML",
        reply_markup=kb_price(),
        disable_web_page_preview=True,
    )


# ── /rm ─────────────────────────────────────────────────────────────────────

async def cmd_rm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("U\u1d1b\u1d00\u0262\u1d07: /rm &lt;code&gt;", parse_mode="HTML")
        return
    code  = context.args[0].upper()
    uid   = update.effective_user.id
    ud    = get_user_data(uid, context)
    codes = context.bot_data.get("codes", {})
    keys  = context.bot_data.get("keys",  {})
    if code in codes and not codes[code]["used"]:
        codes[code]["used"] = True
        ud["credits"] = ud.get("credits", 0) + codes[code]["value"]
        await update.message.reply_text(
            f"R\u1d07\u1d05\u1d07\u1d07\u1d0d\u1d07\u1d05! A\u1d05\u1d05\u1d07\u1d05 {codes[code]['value']} \u1d04\u0280\u1d07\u1d05\u026a\u1d1b\u1d04. Balance: {ud['credits']}/150"
        )
    elif code in keys and not keys[code]["used"]:
        keys[code]["used"] = True
        p, d = keys[code]["plan"], keys[code]["days"]
        ud["plan"]    = p
        ud["expires"] = time.time() + (d * 86400)
        receipt = await send_activation_msg(uid, p, d, context)
        await update.message.reply_text(
            f"A\u1d04\u1d1b\u026a\u1d20\u1d00\u1d1b\u1d07\u1d05 {get_styled_plan(p)} \u1d0a\u1d0f\u0280 {d} \u1d05\u1d00y\u1d1c.\nR\u1d07\u1d04\u1d07\u026a\u1d18\u1d1b \u279a <code>{receipt}</code>",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text("I\u0274\u1d20\u1d00\u029f\u026a\u1d05 \u1d0f\u0280 \u1d00\u029f\u0280\u1d07\u1d00\u1d05y \u1d1c\u1d1c\u1d07\u1d05 \u1d04\u1d0f\u1d05\u1d07.")


# ── /info — OWNER ONLY ────────────────────────────────────────────────────────

async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    target_id       = None
    target_name     = "N/A"
    target_username = None
    target_lastname = ""

    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        ru              = update.message.reply_to_message.from_user
        target_id       = ru.id
        target_name     = ru.first_name or "N/A"
        target_username = ru.username or None
        target_lastname = ru.last_name or ""
    elif context.args:
        raw = context.args[0].strip().lstrip("@")
        if raw.lstrip("-").isdigit():
            target_id = int(raw)
        else:
            for attempt in (f"@{raw}", raw):
                try:
                    chat            = await context.bot.get_chat(attempt)
                    target_id       = chat.id
                    target_name     = chat.first_name or "N/A"
                    target_username = chat.username or None
                    target_lastname = getattr(chat, "last_name", "") or ""
                    break
                except Exception:
                    continue

    if not target_id:
        await update.message.reply_text(
            "Usage:\n/info &lt;user_id&gt;\n/info @username\nOr reply to any user message.",
            parse_mode="HTML",
        )
        return

    if target_name == "N/A":
        try:
            chat            = await context.bot.get_chat(target_id)
            target_name     = chat.first_name or "N/A"
            target_username = chat.username or None
            target_lastname = getattr(chat, "last_name", "") or ""
        except Exception:
            pass

    if target_lastname:
        target_name = f"{target_name} {target_lastname}"

    username_display = f"@{target_username}" if target_username else "None"

    all_users = context.bot_data.get("user_data", {})
    uid_str   = str(target_id)
    has_data  = uid_str in all_users
    now       = time.time()

    if has_data:
        udata       = all_users[uid_str]
        raw_plan    = udata.get("plan", "TRIAL").upper()
        expires     = udata.get("expires", 0)
        joined      = udata.get("joined", "N/A")
        credits_val = udata.get("credits", 150)
        if raw_plan != "TRIAL" and expires <= now:
            raw_plan         = "TRIAL"
            udata["plan"]    = "TRIAL"
            udata["expires"] = 0
            expires          = 0
    else:
        raw_plan    = "TRIAL"
        expires     = 0
        joined      = "Never used the bot"
        credits_val = 150

    is_premium = raw_plan != "TRIAL" and expires > now
    credits    = "\u221e Unlimited" if is_premium else f"{credits_val}/150"
    line       = "\u2501" * 20

    txt = (
        f"{line}\n"
        "\U0001F464 USER INFO\n"
        f"{line}\n\n"
        f"Name       \u279a {target_name}\n"
        f"Username   \u279a {username_display}\n"
        f"User ID    \u279a <code>{target_id}</code>\n"
        f"Plan       \u279a {get_styled_plan(raw_plan)}\n"
        f"Credits    \u279a {credits}\n"
        f"Joined     \u279a {joined}\n"
    )

    if is_premium:
        exp_str        = datetime.fromtimestamp(expires).strftime("%Y-%m-%d %H:%M")
        remaining_secs = expires - now
        remaining_days = int(remaining_secs / 86400)
        remaining_hrs  = int((remaining_secs % 86400) / 3600)
        remaining_mins = int((remaining_secs % 3600) / 60)
        if remaining_days > 0:
            remaining_str = f"{remaining_days}d {remaining_hrs}h"
        elif remaining_hrs > 0:
            remaining_str = f"{remaining_hrs}h {remaining_mins}m"
        else:
            remaining_str = f"{remaining_mins}m"
        txt += (
            f"Plan End   \u279a {exp_str}\n"
            f"Remaining  \u279a {remaining_str}\n"
            f"Status     \u279a \u2705 Active\n"
        )
    else:
        txt += (
            "Plan End   \u279a No Active Plan\n"
            "Remaining  \u279a N/A\n"
            "Status     \u279a \u274c Inactive / Trial\n"
        )

    txt += f"\n{line}"
    await update.message.reply_text(txt, parse_mode="HTML")


# ── /allcm ───────────────────────────────────────────────────────────────────

async def cmd_allcm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    line = "\u2501" * 18
    await update.message.reply_text(
        f"BATMAN BOT \u2014 ALL COMMANDS\n{line}\nVersion: {VERSION}\n{line}\n\n"
        f"USER COMMANDS\n{line}\n"
        "/start  /plan  /bin  /rm  /ping\n"
        "/chk  /pp  /sh  /pyu  /b3  /au  /mss  /mpp2\n\n"
        f"OWNER COMMANDS\n{line}\n"
        "/info  /allcm  /gen\n"
        "/key10  /key20  /key30\n"
        "/sub  /resub  /allplans\n"
        "/oneday  /threeday\n"
        "/seturl  /geturl\n"
        "/onchk  /offchk  /onpp  /offpp\n"
        "/onsh  /offsh  /onpyu  /offpyu\n"
        "/onb3  /offb3  /onau  /offau\n"
        "/onmss  /offmss  /onmpp2  /offmpp2\n"
        "/killbot  /onbot\n"
        f"{line}",
        parse_mode="HTML",
    )


# ── /gen ─────────────────────────────────────────────────────────────────────

async def cmd_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("U\u1d1b\u1d00\u0262\u1d07: /gen &lt;credits&gt;", parse_mode="HTML")
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
        await update.message.reply_text("I\u0274\u1d20\u1d00\u029f\u026a\u1d05 \u1d00\u1d0d\u1d0f\u1d1c\u0274\u1d1b.")


# ── Key generation ───────────────────────────────────────────────────────────

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


# ── Grant helper ─────────────────────────────────────────────────────────────

async def _grant(
    uid: int, plan: str, days: int,
    update: Update, context: ContextTypes.DEFAULT_TYPE,
):
    ud = get_user_data(uid, context)
    ud["plan"]    = plan
    ud["expires"] = time.time() + (days * 86400)
    receipt = await send_activation_msg(uid, plan, days, context)
    await update.message.reply_text(
        f"G\u0280\u1d00\u0274\u1d1b\u1d07\u1d05 {days} D\u1d00y\u1d1c ({get_styled_plan(plan)}) \u1d1b\u1d0f <code>{uid}</code>\nR\u1d07\u1d04\u1d07\u026a\u1d18\u1d1b \u279a <code>{receipt}</code>",
        parse_mode="HTML",
    )


# ── /oneday / /threeday ──────────────────────────────────────────────────────

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


# ── /sub / /resub ────────────────────────────────────────────────────────────

async def cmd_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if len(context.args) < 2:
        await update.message.reply_text(
            "U\u1d1b\u1d00\u0262\u1d07: /sub &lt;user_id&gt; &lt;days&gt;", parse_mode="HTML"
        )
        return
    uid = await resolve_user(context.args[0], context)
    if not uid:
        await update.message.reply_text("U\u1d1b\u026a\u029f \u0274\u1d0f\u1d1c \u1d0a\u1d0f\u1d1c\u0274\u1d05.")
        return
    try:
        days = int(context.args[1])
        plan = "root" if days >= 30 else "elite" if days >= 15 else "core"
        await _grant(uid, plan, days, update, context)
    except ValueError:
        await update.message.reply_text("I\u0274\u1d20\u1d00\u029f\u026a\u1d05 \u1d05\u1d00y\u1d1c.")


async def cmd_resub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("U\u1d1b\u1d00\u0262\u1d07: /resub &lt;user_id&gt;", parse_mode="HTML")
        return
    uid = await resolve_user(context.args[0], context)
    if not uid:
        await update.message.reply_text("U\u1d1b\u026a\u029f \u0274\u1d0f\u1d1c \u1d0a\u1d0f\u1d1c\u0274\u1d05.")
        return
    ud = get_user_data(uid, context)
    raw_plan = ud.get("plan", "TRIAL").upper()
    expires  = ud.get("expires", 0)
    now      = time.time()
    if raw_plan != "TRIAL" and expires > now:
        remaining = int((expires - now) / 86400)
        days = remaining
        plan = raw_plan.lower()
    else:
        await update.message.reply_text("U\u1d1b\u026a\u029f \u0262\u1d00\u1d1b \u0274\u1d0f \u1d00\u1d04\u1d1b\u026a\u1d20\u1d07 \u1d18\u029f\u1d00\u0274.")
        return
    await _grant(uid, plan, days, update, context)


# ── /allplans ────────────────────────────────────────────────────────────────

async def cmd_allplans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    all_users = context.bot_data.get("user_data", {})
    now       = time.time()
    line      = "\u2501" * 18
    if not all_users:
        await update.message.reply_text("N\u1d0f \u1d1c\u1d1b\u1d07\u0280\u1d05 \u0262\u1d07\u1d07\u0274.")
        return
    txt = f"ALL USER PLANS\n{line}\nTotal: {len(all_users)}\n{line}\n\n"
    for uid_str, ud in all_users.items():
        raw_plan = ud.get("plan", "TRIAL").upper()
        expires  = ud.get("expires", 0)
        name     = ud.get("name", "Unknown")
        if raw_plan != "TRIAL" and expires > now:
            remaining = int((expires - now) / 86400)
            txt += f"[{uid_str}] {name} \u279a {get_styled_plan(raw_plan)} ({remaining}d left)\n"
        else:
            txt += f"[{uid_str}] {name} \u279a TRIAL\n"
    txt += f"\n{line}"
    await update.message.reply_text(txt, parse_mode="HTML")


# ── /seturl / /geturl ────────────────────────────────────────────────────────

async def cmd_seturl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if len(context.args) < 2:
        await update.message.reply_text(
            "U\u1d1b\u1d00\u0262\u1d07: /seturl &lt;gate&gt; &lt;url&gt;\nGates: chk, pp, sh, pyu, b3, au, mss, mpp2",
            parse_mode="HTML",
        )
        return
    gate = context.args[0].lower().strip()
    url  = context.args[1].strip()
    if gate not in GATE_NAMES:
        await update.message.reply_text(f"I\u0274\u1d20\u1d00\u029f\u026a\u1d05 \u0262\u1d00\u1d1b\u1d07: {gate}")
        return
    context.bot_data[f"gate_url_{gate}"] = url
    await update.message.reply_text(f"G\u1d00\u1d1b\u1d07 [{GATE_NAMES[gate]}] URL \u1d1c\u1d05\u1d05\u1d00\u1d1b\u1d07\u1d05:\n<code>{url}</code>", parse_mode="HTML")


async def cmd_geturl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    line = "\u2501" * 18
    txt  = f"GATE URLs\n{line}\n\n"
    for gate, name in GATE_NAMES.items():
        url = context.bot_data.get(f"gate_url_{gate}") or GATE_URLS.get(gate, "NOT SET")
        status = "ON" if context.bot_data.get(f"{gate}_on", True) else "OFF"
        txt += f"{name} [{gate}]:\n  URL: <code>{url}</code>\n  Status: {status}\n\n"
    txt += line
    await update.message.reply_text(txt, parse_mode="HTML")


# ── Gate toggle commands ─────────────────────────────────────────────────────

async def _gate_toggle(
    update: Update, context: ContextTypes.DEFAULT_TYPE, gate: str, state: bool
):
    if update.effective_user.id != OWNER_ID:
        return
    context.bot_data[f"{gate}_on"] = state
    s = "ON" if state else "OFF"
    await update.message.reply_text(f"G\u1d00\u1d1b\u1d07 [{GATE_NAMES[gate]}] \u1d1b\u1d1c\u0280\u0274\u1d07\u1d05 {s}.")


async def cmd_onchk(u, c):  await _gate_toggle(u, c, "chk",  True)
async def cmd_offchk(u, c): await _gate_toggle(u, c, "chk",  False)
async def cmd_onpp(u, c):   await _gate_toggle(u, c, "pp",   True)
async def cmd_offpp(u, c):  await _gate_toggle(u, c, "pp",   False)
async def cmd_onsh(u, c):   await _gate_toggle(u, c, "sh",   True)
async def cmd_offsh(u, c):  await _gate_toggle(u, c, "sh",   False)
async def cmd_onpyu(u, c):  await _gate_toggle(u, c, "pyu",  True)
async def cmd_offpyu(u, c): await _gate_toggle(u, c, "pyu",  False)
async def cmd_onb3(u, c):   await _gate_toggle(u, c, "b3",   True)
async def cmd_offb3(u, c):  await _gate_toggle(u, c, "b3",   False)
async def cmd_onau(u, c):   await _gate_toggle(u, c, "au",   True)
async def cmd_offau(u, c):  await _gate_toggle(u, c, "au",   False)
async def cmd_onmss(u, c):  await _gate_toggle(u, c, "mss",  True)
async def cmd_offmss(u, c): await _gate_toggle(u, c, "mss",  False)
async def cmd_onmpp2(u, c): await _gate_toggle(u, c, "mpp2", True)
async def cmd_offmpp2(u, c):await _gate_toggle(u, c, "mpp2", False)


# ── /killbot / /onbot ────────────────────────────────────────────────────────

async def cmd_killbot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    context.bot_data["maintenance"] = True
    await update.message.reply_text("B\u1d0f\u1d1b \u1d1b\u1d1c\u0280\u0274\u1d07\u1d05 OFF \u2014 M\u1d00\u026a\u0274\u1d1b\u1d07\u0274\u1d00\u0274\u1d04\u1d07 \u1d0d\u1d0f\u1d05\u1d07.")


async def cmd_onbot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    context.bot_data["maintenance"] = False
    await update.message.reply_text("B\u1d0f\u1d1b \u1d1b\u1d1c\u0280\u0274\u1d07\u1d05 ON \u2014 B\u1d0f\u1d1b \u026a\u1d1c \u0274\u1d0f\u1d21 \u1d00\u1d20\u1d00\u026a\u029f\u1d00\u0299\u029f\u1d07.")


# ── Callback query handler ───────────────────────────────────────────────────

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data  = query.data
    user  = query.from_user

    # ── Main menu ──
    if data == "bmain":
        await query.edit_message_text(
            ui_profile(user, context),
            parse_mode="HTML",
            reply_markup=kb_main(),
            disable_web_page_preview=True,
        )

    # ── Price / plan ──
    elif data == "mprice":
        await query.edit_message_text(
            PLAN_TEXT,
            parse_mode="HTML",
            reply_markup=kb_price(),
            disable_web_page_preview=True,
        )
    elif data == "pay10":
        await query.edit_message_text(
            PAYMENT_PENDING_TEXT,
            parse_mode="HTML",
            reply_markup=kb_payment(),
            disable_web_page_preview=True,
        )
    elif data == "pay15":
        await query.edit_message_text(
            PAYMENT_PENDING_TEXT,
            parse_mode="HTML",
            reply_markup=kb_payment(),
            disable_web_page_preview=True,
        )
    elif data == "pay30":
        await query.edit_message_text(
            PAYMENT_PENDING_TEXT,
            parse_mode="HTML",
            reply_markup=kb_payment(),
            disable_web_page_preview=True,
        )

    # ── Gate menu ──
    elif data == "mgates":
        await query.edit_message_text(
            CHECKER_STATUS_TEXT,
            parse_mode="HTML",
            reply_markup=kb_gate_main(),
            disable_web_page_preview=True,
        )

    # ── Auth gates ──
    elif data == "mauth":
        await query.edit_message_text(
            AUTH_MENU_TEXT,
            parse_mode="HTML",
            reply_markup=kb_auth_gates(),
            disable_web_page_preview=True,
        )
    elif data == "iau":
        await query.edit_message_text(
            STRIPE_AUTH_TEXT,
            parse_mode="HTML",
            reply_markup=kb_back("mauth"),
            disable_web_page_preview=True,
        )
    elif data == "ib3":
        await query.edit_message_text(
            BRAINTREE_TEXT,
            parse_mode="HTML",
            reply_markup=kb_back("mauth"),
            disable_web_page_preview=True,
        )

    # ── Charge gates ──
    elif data == "mcharge":
        await query.edit_message_text(
            CHARGE_MENU_TEXT,
            parse_mode="HTML",
            reply_markup=kb_charge_gates(),
            disable_web_page_preview=True,
        )
    elif data == "ichk":
        await query.edit_message_text(
            gate_info_text("STRIPE CHARGE", "chk", 1),
            parse_mode="HTML",
            reply_markup=kb_back("mcharge"),
            disable_web_page_preview=True,
        )
    elif data == "ipp":
        await query.edit_message_text(
            gate_info_text("PAYPAL CHARGE", "pp", 1),
            parse_mode="HTML",
            reply_markup=kb_back("mcharge"),
            disable_web_page_preview=True,
        )
    elif data == "ish":
        await query.edit_message_text(
            gate_info_text("SHOPIFY CHARGE", "sh", 1),
            parse_mode="HTML",
            reply_markup=kb_back("mcharge"),
            disable_web_page_preview=True,
        )
    elif data == "ipyu":
        await query.edit_message_text(
            gate_info_text("PAYU CHARGE", "pyu", 1),
            parse_mode="HTML",
            reply_markup=kb_back("mcharge"),
            disable_web_page_preview=True,
        )

    # ── Mass gates ──
    elif data == "mmass":
        await query.edit_message_text(
            MASS_MENU_TEXT,
            parse_mode="HTML",
            reply_markup=kb_mass_gates(),
            disable_web_page_preview=True,
        )
    elif data == "imss":
        await query.edit_message_text(
            gate_info_text("STRIPE MASS", "mss", 1),
            parse_mode="HTML",
            reply_markup=kb_back("mmass"),
            disable_web_page_preview=True,
        )
    elif data == "impp2":
        await query.edit_message_text(
            gate_info_text("PAYPAL MASS", "mpp2", 1),
            parse_mode="HTML",
            reply_markup=kb_back("mmass"),
            disable_web_page_preview=True,
        )


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Middleware
    app.add_handler(MessageHandler(
        filters.ALL & ~filters.COMMAND, maintenance_check, block=False
    ))
    app.add_handler(MessageHandler(
        filters.ALL & ~filters.COMMAND, anti_ad_filter, block=False
    ))

    # User commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("ping",  cmd_ping))
    app.add_handler(CommandHandler("bin",   cmd_bin))
    app.add_handler(CommandHandler("plan",  cmd_plan))
    app.add_handler(CommandHandler("rm",    cmd_rm))

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
    app.add_handler(CommandHandler("info",      cmd_info))
    app.add_handler(CommandHandler("allcm",     cmd_allcm))
    app.add_handler(CommandHandler("gen",       cmd_gen))
    app.add_handler(CommandHandler("key10",     cmd_key10))
    app.add_handler(CommandHandler("key20",     cmd_key20))
    app.add_handler(CommandHandler("key30",     cmd_key30))
    app.add_handler(CommandHandler("sub",       cmd_sub))
    app.add_handler(CommandHandler("resub",     cmd_resub))
    app.add_handler(CommandHandler("allplans",  cmd_allplans))
    app.add_handler(CommandHandler("oneday",    cmd_oneday))
    app.add_handler(CommandHandler("threeday",  cmd_threeday))
    app.add_handler(CommandHandler("seturl",    cmd_seturl))
    app.add_handler(CommandHandler("geturl",    cmd_geturl))
    app.add_handler(CommandHandler("onchk",     cmd_onchk))
    app.add_handler(CommandHandler("offchk",    cmd_offchk))
    app.add_handler(CommandHandler("onpp",      cmd_onpp))
    app.add_handler(CommandHandler("offpp",     cmd_offpp))
    app.add_handler(CommandHandler("onsh",      cmd_onsh))
    app.add_handler(CommandHandler("offsh",     cmd_offsh))
    app.add_handler(CommandHandler("onpyu",     cmd_onpyu))
    app.add_handler(CommandHandler("offpyu",    cmd_offpyu))
    app.add_handler(CommandHandler("onb3",      cmd_onb3))
    app.add_handler(CommandHandler("offb3",     cmd_offb3))
    app.add_handler(CommandHandler("onau",      cmd_onau))
    app.add_handler(CommandHandler("offau",     cmd_offau))
    app.add_handler(CommandHandler("onmss",     cmd_onmss))
    app.add_handler(CommandHandler("offmss",    cmd_offmss))
    app.add_handler(CommandHandler("onmpp2",    cmd_onmpp2))
    app.add_handler(CommandHandler("offmpp2",   cmd_offmpp2))
    app.add_handler(CommandHandler("killbot",   cmd_killbot))
    app.add_handler(CommandHandler("onbot",     cmd_onbot))

    # Callback queries
    app.add_handler(CallbackQueryHandler(callback_handler))

    # Start bot
    logger.info("Batman Card Checker Bot starting...")
    try:
        app.run_polling(drop_pending_updates=True)
    except Conflict:
        logger.error("Bot token conflict — another instance is running.")


if __name__ == "__main__":
    main()
