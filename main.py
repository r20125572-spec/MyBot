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
from bin import get_bin_handler

CHANNEL_LINK  = "https://t.me/Batcardchk"
GROUP_LINK    = "https://t.me/batcardchkGroup"
SUPPORT_LINK  = "https://t.me/cardchkSupport"
BOT_LINK      = "https://t.me/Batmancardchk_bot"

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

MAX_MSG = 4000  # safe buffer below Telegram's 4096 limit


# ── Bold unicode font ─────────────────────────────────────────────────────────

def B(text: str) -> str:
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


# ── Static text blocks ────────────────────────────────────────────────────────

CHECKER_STATUS_TEXT = (
    "\U0001d402\U0001d41a\U0001d42d\U0001d41e\U0001d42c \U0001d412\U0001d42d\U0001d41a\U0001d42d\U0001d42e\U0001d42c:\n"
    "A\u1d1c\u1d1b\u029c G\u1d00\u1d1b\u1d07   \u279a 2\n"
    "M\u1d00\u1d1b\u1d1c G\u1d00\u1d1b\u1d07  \u279a 2\n"
    "C\u029c\u1d00\u0280\u0262\u1d07 G\u1d00\u1d1b\u1d07 \u279a 4\n"
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
    "S\u1d07\u029f\u1d07\u1d04\u1d1b \u1d00 G\u1d00\u1d1b\u1d07 \u279a C\u1d00\u1d1b\u1d07\u0262\u1d0f\u0280y"
)

AUTH_MENU_TEXT = (
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
    "S\u1d07\u029f\u1d07\u1d04\u1d1b A\u1d1c\u1d1b\u029c G\u1d00\u1d1b\u1d07 \u279a\n"
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
)

STRIPE_AUTH_TEXT = (
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
    "G\u1d00\u1d1b\u1d07    \u279a S\u1d1b\u0280\u026a\u1d18\u1d07 0$\n"
    "C\u1d0f\u1d0d\u1d0d\u1d00\u0274\u1d05 \u279a /chk\n"
    "S\u026a\u1d1b\u1d07\u1d04   \u279a 16\n"
    "H\u1d07\u1d00\u029f\u1d1b\u029c  \u279a 100%\n"
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
)

BRAINTREE_TEXT = (
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
    "G\u1d00\u1d1b\u1d07    \u279a B\u0280\u1d00\u026a\u0274\u1d1b\u0280\u1d07\u1d07 0$\n"
    "C\u1d0f\u1d0d\u1d0d\u1d00\u0274\u1d05 \u279a /b3\n"
    "S\u026a\u1d1b\u1d07\u1d04   \u279a 2\n"
    "H\u1d07\u1d00\u029f\u1d1b\u029c  \u279a 100%\n"
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
)

CHARGE_MENU_TEXT = (
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
    "S\u1d07\u029f\u1d07\u1d04\u1d1b C\u029c\u1d00\u0280\u0262\u1d07 G\u1d00\u1d1b\u1d07 \u279a\n"
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
)

MASS_MENU_TEXT = (
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
    "S\u1d07\u029f\u1d07\u1d04\u1d1b M\u1d00\u1d1b\u1d00 G\u1d00\u1d1b\u1d07 \u279a\n"
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
)

PLAN_TEXT = (
    "\u2501" * 20 + "\n"
    "B\u1d00\u1d1b\u1d0d\u1d00\u0274 P\u0280\u1d07\u1d0d\u026a\u1d1c\u1d0d P\u029f\u1d00\u0274\u1d04\n"
    "\u2501" * 20 + "\n\n"
    "A\u1d04\u1d04\u1d07\u1d1b\u1d04 \u279a C\u1d0f\u0280\u1d07 \U0001F380\n"
    "S\u1d18\u1d00\u0274   \u279a [7 D\u1d00y\u1d1c]\n"
    "C\u0280\u1d07\u1d05\u026a\u1d1b\u1d04 \u279a \u221e U\u0274\u029f\u026a\u1d0d\u026a\u1d1b\u1d07\u1d05\n"
    "P\u0280\u026a\u1d04\u1d07  \u279a 10$\n"
    "\u2501" * 16 + "\n"
    "A\u1d04\u1d04\u1d07\u1d1b\u1d04 \u279a E\u029f\u026a\u1d1b\u1d07 \u2b50\ufe0f\n"
    "S\u1d18\u1d00\u0274   \u279a [15 D\u1d00y\u1d1c]\n"
    "C\u0280\u1d07\u1d05\u026a\u1d1b\u1d04 \u279a \u221e U\u0274\u029f\u026a\u1d0d\u026a\u1d1b\u1d07\u1d05\n"
    "P\u0280\u026a\u1d04\u1d07  \u279a 15$\n"
    "\u2501" * 16 + "\n"
    "A\u1d04\u1d04\u1d07\u1d1b\u1d04 \u279a R\u1d0f\u1d0f\u1d1b \U0001F451\n"
    "S\u1d18\u1d00\u0274   \u279a [30 D\u1d00y\u1d1c]\n"
    "C\u0280\u1d07\u1d05\u026a\u1d1b\u1d04 \u279a \u221e U\u0274\u029f\u026a\u1d0d\u026a\u1d1b\u1d07\u1d05\n"
    "P\u0280\u026a\u1d04\u1d07  \u279a 30$\n"
    "\u2501" * 20
)

PAYMENT_PENDING_TEXT = (
    "\u2501" * 20 + "\n"
    "P\u1d00y\u1d0d\u1d07\u0274\u1d1b A\u1d05\u1d05\u0280\u1d07\u1d1b\u1d04\n"
    "\u2501" * 20 + "\n\n"
    "P\u1d00y\u1d0d\u1d07\u0274\u1d1b \u1d00\u1d05\u1d05\u0280\u1d07\u1d1c\u1d1c \u1d21\u026a\u029f\u029f \u0299\u1d07 \u1d00\u1d05\u1d05\u1d07\u1d05 \u1d1c\u029c\u1d0f\u0280\u1d1b\u029f\u029f\u029f y.\n\n"
    "F\u1d0f\u0280 \u1d18\u1d00y\u1d0d\u1d07\u0274\u1d1b \u1d04\u1d0f\u0274\u1d1b\u1d00\u1d04\u1d1b \u1d1b\u029c\u0280\u1d0f\u1d1c\u0262\u029c \u1d04\u1d1c\u1d18\u1d18\u1d0f\u0280\u1d1b.\n\n"
    "\u2501" * 20
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_styled_plan(raw_plan: str) -> str:
    p = raw_plan.upper()
    if p == "CORE":  return "C\u1d0f\u0280\u1d07"
    if p == "ELITE": return "E\u029f\u026a\u1d1b\u1d07"
    if p == "ROOT":  return "R\u1d0f\u1d0f\u1d1b"
    return "T\u0280\u026a\u1d00\u029f"


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
    ud       = get_user_data(user.id, context)
    raw_plan = ud.get("plan", "TRIAL").upper()
    expires  = ud.get("expires", 0)
    now      = time.time()
    if raw_plan != "TRIAL" and expires <= now:
        raw_plan = "TRIAL"; ud["plan"] = "TRIAL"; ud["expires"] = 0; expires = 0
    is_premium = raw_plan != "TRIAL"
    credits    = "\u221e U\u0274\u029f\u026a\u1d0d\u026a\u1d1b\u1d07\u1d05" if is_premium else f"{ud.get('credits', 150)}/150"
    uname      = f"@{user.username}" if user.username else "None"
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
        lines.append(
            f"R\u1d07\u1d0d\u1d00\u026a\u0274\u026a\u0274\u0262 \u279a {remaining_d}d {remaining_h}h"
            if remaining_d > 0 else
            f"R\u1d07\u1d0d\u1d00\u026a\u0274\u026a\u0274\u0262 \u279a {remaining_h}h"
        )
    lines.append(f"J\u1d0f\u026a\u0274\u1d07\u1d05  \u279a {ud.get('joined', datetime.now().strftime('%Y-%m-%d'))}")
    lines.append(f"D\u1d07\u1d20    \u279a <a href='{DEV_LINK}'>Batman</a>")
    return "\n".join(lines)


async def send_activation_msg(
    user_id: int, plan: str, days: int, context: ContextTypes.DEFAULT_TYPE
) -> str:
    receipt = gen_receipt()
    name, username = "Unknown", None
    try:
        chat = await context.bot.get_chat(user_id)
        name = chat.first_name or "Unknown"
        username = chat.username or None
    except Exception:
        pass
    ud = get_user_data(user_id, context)
    ud["name"] = name; ud["plan"] = plan; ud["expires"] = time.time() + (days * 86400)
    exp_date      = datetime.fromtimestamp(ud["expires"]).strftime("%Y-%m-%d %H:%M")
    uname_display = f"@{username}" if username else "None"
    txt = (
        "C\u1d0f\u0274\u0262\u0280\u1d00\u1d1b\u1d1c\u029f\u1d00\u1d1b\u026a\u1d0f\u0274\u1d1b! Y\u1d0f\u1d1c\u0280 \u1d00\u1d04\u1d04\u1d07\u1d1c\u1d04 \u029c\u1d00\u1d1b \u0299\u1d07\u1d07\u0274 \u1d00\u1d04\u1d1b\u026a\u1d20\u1d00\u1d1b\u1d07\u1d05.\n"
        + "\u2501" * 20 + "\n\n"
        + f"U\u1d1b\u026a\u029f     \u279a {name}\n"
        + f"U\u1d1b\u026a\u029f\u0274\u1d00\u1d0d\u1d07 \u279a {uname_display}\n"
        + f"A\u1d04\u1d04\u1d07\u1d1b\u1d04   \u279a {get_styled_plan(plan)}\n"
        + f"D\u1d1c\u0280\u1d00\u1d1b\u026a\u1d0f\u0274  \u279a {days} D\u1d00y\u1d1c\n"
        + "C\u0280\u1d07\u1d05\u026a\u1d1b\u1d04   \u279a \u221e U\u0274\u029f\u026a\u1d0d\u026a\u1d1b\u1d07\u1d05\n"
        + f"E\u02e3\u1d18\u026a\u0280\u1d07\u1d04   \u279a {exp_date}\n"
        + f"R\u1d07\u1d04\u1d07\u026a\u1d18\u1d1b  \u279a <code>{receipt}</code>\n\n"
        + "\u2501" * 20 + "\n"
        + "P\u029f\u1d07\u1d00\u1d1b\u1d07 \u1d1c\u1d00\u1d20\u1d07 \u1d1b\u029c\u026a\u1d1c \u0280\u1d07\u1d04\u1d07\u026a\u1d18\u1d1b ID."
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
    return None


# ── Keyboards ─────────────────────────────────────────────────────────────────

def kb_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("CHECKER"), callback_data="mgates"),
         InlineKeyboardButton(B("BUY NOW"), callback_data="mprice")],
        [InlineKeyboardButton(B("UPDATES"), url=CHANNEL_LINK),
         InlineKeyboardButton(B("GROUP"),   url=GROUP_LINK)],
        [InlineKeyboardButton(B("SUPPORT"), url=SUPPORT_LINK)],
    ])

def kb_back(cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(B("BACK"), callback_data=cb)]])

def kb_bin_result() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(B("Batcardchk"), url=BOT_LINK)]])

def kb_price() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("10$PAY"), callback_data="pay10"),
         InlineKeyboardButton(B("15$PAY"), callback_data="pay15"),
         InlineKeyboardButton(B("30$PAY"), callback_data="pay30")],
        [InlineKeyboardButton(B("BACK"), callback_data="bmain")],
    ])

def kb_payment() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("SUPPORT"), url=SUPPORT_LINK)],
        [InlineKeyboardButton(B("BACK"),    callback_data="mprice")],
    ])

def kb_gate_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("AUTH"),   callback_data="mauth"),
         InlineKeyboardButton(B("CHARGE"), callback_data="mcharge"),
         InlineKeyboardButton(B("MASS"),   callback_data="mmass")],
        [InlineKeyboardButton(B("BACK"), callback_data="bmain")],
    ])

def kb_auth_gates() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("STRIPE"),    callback_data="iau"),
         InlineKeyboardButton(B("BRAINTREE"), callback_data="ib3")],
        [InlineKeyboardButton(B("BACK"), callback_data="mgates")],
    ])

def kb_charge_gates() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("STRIPE"),  callback_data="ichk"),
         InlineKeyboardButton(B("PAYPAL"),  callback_data="ipp")],
        [InlineKeyboardButton(B("SHOPIFY"), callback_data="ish"),
         InlineKeyboardButton(B("PAYU"),    callback_data="ipyu")],
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
        f"{line}\n{gate_name}\n{line}\n\n"
        f"C\u1d0f\u1d1b\u1d1b    \u279a {cost} C\u0280\u1d07\u1d05\u026a\u1d1b(\u1d1c) \u1d18\u1d07\u0280 \u1d04\u029c\u1d07\u1d04\u1d04\n\n"
        f"U\u1d1b\u1d00\u0262\u1d07:\n<code>/{cmd} cc|mm|yy|cvv</code>\n\n"
        f"E\u02e3\u1d00\u1d0d\u1d18\u029f\u1d07:\n<code>/{cmd} 4111111111111111|12|2026|123</code>\n\n"
        f"{line}"
    )


# ── Middleware ────────────────────────────────────────────────────────────────

async def maintenance_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    if context.bot_data.get("maintenance", False) and update.effective_user.id != OWNER_ID:
        try:
            if update.message:
                await update.message.reply_text(
                    "B\u1d0f\u1d1b \u026a\u1d1c \u1d1c\u1d1c\u029f\u026a\u1d07\u0274\u1d1b\u029f\u029f y \u1d1c\u0274\u1d05\u1d07\u0280 \u1d0d\u1d00\u026a\u0274\u1d1b\u1d07\u0274\u1d00\u0274\u1d04\u1d07."
                )
        except Exception:
            pass
        raise ApplicationHandlerStop


async def anti_ad_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.from_user or msg.from_user.id == OWNER_ID:
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


# ── Gate processing ───────────────────────────────────────────────────────────

async def _api_request(session: aiohttp.ClientSession, url: str, card: str, site: str) -> dict:
    async with session.get(url, params={"cc": card, "site": site}) as resp:
        try:
            data = await resp.json(content_type=None)
        except Exception:
            data = {"value": await resp.text()}
        if not isinstance(data, dict):
            data = {"value": str(data)}
        return data


async def process_gate(
    update: Update, context: ContextTypes.DEFAULT_TYPE, gate_key: str, gate_name: str
):
    if not context.bot_data.get(f"{gate_key}_on", True):
        await update.message.reply_text("G\u1d00\u1d1b\u1d07 \u026a\u1d1c \u1d04\u1d1c\u0280\u0280\u1d07\u0274\u1d1b\u029f\u029f OFF.")
        return
    card = (
        context.args[0] if context.args
        else (update.message.reply_to_message.text.strip()
              if update.message.reply_to_message and update.message.reply_to_message.text
              else None)
    )
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
        raw_response = str(data.get("value") or data.get("message") or data.get("category") or "ERROR").strip()
        is_approved  = any(w in raw_response.lower() for w in ["approved", "captured", "success"])
        status_ui    = "APPROVED \u2705" if is_approved else "DECLINED \u274c"
        bin_txt      = "N/A"
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
        await msg.edit_text(text, parse_mode="HTML", reply_markup=kb_result(), disable_web_page_preview=True)
    except aiohttp.ServerTimeoutError:
        await msg.edit_text("T\u026a\u1d0d\u1d07\u1d0f\u1d1c\u1d1b \u2014 G\u1d00\u1d1b\u1d07 \u1d05\u026a\u1d05 \u0274\u1d0f\u1d1c \u0280\u1d07\u1d1c\u1d18\u1d0f\u0274\u1d05.")
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


# ── /start ────────────────────────────────────────────────────────────────────

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


# ── /ping ─────────────────────────────────────────────────────────────────────

async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Pong! Bot is online.")


# ── /plan ─────────────────────────────────────────────────────────────────────

async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        PLAN_TEXT, parse_mode="HTML", reply_markup=kb_price(), disable_web_page_preview=True
    )


# ── /rm ───────────────────────────────────────────────────────────────────────

async def cmd_rm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "U\u1d1b\u1d00\u0262\u1d07: /rm &lt;code&gt;", parse_mode="HTML"
        )
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
        ud["plan"] = p; ud["expires"] = time.time() + (d * 86400)
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

    target_id, target_name, target_username, target_lastname = None, "N/A", None, ""

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
                    chat = await context.bot.get_chat(attempt)
                    target_id       = chat.id
                    target_name     = chat.first_name or "N/A"
                    target_username = chat.username or None
                    target_lastname = getattr(chat, "last_name", "") or ""
                    break
                except Exception:
                    continue

    if not target_id:
        await update.message.reply_text(
            "U\u1d1b\u1d00\u0262\u1d07:\n"
            "/info &lt;user_id&gt;\n"
            "/info @username\n"
            "O\u0280 \u0280\u1d07\u1d18\u029f\u029f \u1d1b\u1d0f \u1d00\u0274y \u1d1c\u1d07\u0280 \u1d0d\u1d07\u1d1c\u1d1c\u1d00\u0262\u1d07.",
            parse_mode="HTML",
        )
        return

    if target_name == "N/A":
        try:
            chat = await context.bot.get_chat(target_id)
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
            raw_plan = "TRIAL"; udata["plan"] = "TRIAL"; udata["expires"] = 0; expires = 0
    else:
        raw_plan = "TRIAL"; expires = 0
        joined = "N\u1d07\u1d20\u1d07\u0280 \u1d1c\u1d1c\u1d07\u1d05 \u1d1b\u029c\u1d07 \u0299\u1d0f\u1d1c"
        credits_val = 150

    is_premium = raw_plan != "TRIAL" and expires > now
    credits    = "\u221e U\u0274\u029f\u026a\u1d0d\u026a\u1d1b\u1d07\u1d05" if is_premium else f"{credits_val}/150"
    line       = "\u2501" * 20

    txt = (
        f"{line}\n"
        "\U0001F464 U\u1d1c\u1d07\u0280 I\u0274\u1d0a\u1d0f\n"
        f"{line}\n\n"
        f"N\u1d00\u1d0d\u1d07      \u279a {target_name}\n"
        f"U\u1d1b\u026a\u029f\u0274\u1d00\u1d0d\u1d07  \u279a {username_display}\n"
        f"U\u1d1b\u026a\u029f ID  \u279a <code>{target_id}</code>\n"
        f"P\u029f\u1d00\u0274      \u279a {get_styled_plan(raw_plan)}\n"
        f"C\u0280\u1d07\u1d05\u026a\u1d1b\u1d04  \u279a {credits}\n"
        f"J\u1d0f\u026a\u0274\u1d07\u1d05   \u279a {joined}\n"
    )

    if is_premium:
        exp_str        = datetime.fromtimestamp(expires).strftime("%Y-%m-%d %H:%M")
        remaining_secs = expires - now
        remaining_days = int(remaining_secs / 86400)
        remaining_hrs  = int((remaining_secs % 86400) / 3600)
        remaining_mins = int((remaining_secs % 3600) / 60)
        remaining_str  = (
            f"{remaining_days}d {remaining_hrs}h" if remaining_days > 0
            else f"{remaining_hrs}h {remaining_mins}m" if remaining_hrs > 0
            else f"{remaining_mins}m"
        )
        txt += (
            f"P\u029f\u1d00\u0274 E\u0274\u1d05  \u279a {exp_str}\n"
            f"R\u1d07\u1d0d\u1d00\u026a\u0274\u026a\u0274\u0262 \u279a {remaining_str}\n"
            "S\u1d1b\u1d00\u1d1b\u1d1c\u1d1c  \u279a \u2705 A\u1d04\u1d1b\u026a\u1d20\u1d07\n"
        )
    else:
        txt += (
            "P\u029f\u1d00\u0274 E\u0274\u1d05  \u279a N\u1d0f A\u1d04\u1d1b\u026a\u1d20\u1d07 P\u029f\u1d00\u0274\n"
            "R\u1d07\u1d0d\u1d00\u026a\u0274\u026a\u0274\u0262 \u279a N/A\n"
            "S\u1d1b\u1d00\u1d1b\u1d1c\u1d1c  \u279a \u274c I\u0274\u1d00\u1d04\u1d1b\u026a\u1d20\u1d07 / T\u0280\u026a\u1d00\u029f\n"
        )

    txt += f"\n{line}"
    await update.message.reply_text(txt, parse_mode="HTML")


# ── /allcm ────────────────────────────────────────────────────────────────────

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


# ── /gen ──────────────────────────────────────────────────────────────────────

async def cmd_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text(
            "U\u1d1b\u1d00\u0262\u1d07: /gen &lt;credits&gt;", parse_mode="HTML"
        )
        return
    try:
        amt  = int(context.args[0])
        code = gen_code()
        context.bot_data.setdefault("codes", {})[code] = {"type": "credit", "value": amt, "used": False}
        await update.message.reply_text(
            f"CODE GENERATED\n\nCode: <code>{code}</code>\nCredits: {amt}", parse_mode="HTML"
        )
    except ValueError:
        await update.message.reply_text("I\u0274\u1d20\u1d00\u029f\u026a\u1d05 \u1d00\u1d0d\u1d0f\u1d1c\u0274\u1d1b.")


# ── Key generation ────────────────────────────────────────────────────────────

async def _gen_key(update: Update, context: ContextTypes.DEFAULT_TYPE, plan: str, days: int):
    if update.effective_user.id != OWNER_ID:
        return
    code = "KEY-" + gen_code(12)
    context.bot_data.setdefault("keys", {})[code] = {"plan": plan, "days": days, "used": False}
    await update.message.reply_text(
        f"KEY GENERATED\n\nKey : <code>{code}</code>\nPlan: {get_styled_plan(plan)}\nDays: {days}",
        parse_mode="HTML",
    )

async def cmd_key10(u, c): await _gen_key(u, c, "core",  7)
async def cmd_key20(u, c): await _gen_key(u, c, "elite", 15)
async def cmd_key30(u, c): await _gen_key(u, c, "root",  30)


# ── Grant helper ──────────────────────────────────────────────────────────────

async def _grant(uid: int, plan: str, days: int, update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud = get_user_data(uid, context)
    ud["plan"] = plan; ud["expires"] = time.time() + (days * 86400)
    receipt = await send_activation_msg(uid, plan, days, context)
    await update.message.reply_text(
        f"G\u0280\u1d00\u0274\u1d1b\u1d07\u1d05 {days} D\u1d00y\u1d1c ({get_styled_plan(plan)}) \u1d1b\u1d0f <code>{uid}</code>\n"
        f"R\u1d07\u1d04\u1d07\u026a\u1d18\u1d1b \u279a <code>{receipt}</code>",
        parse_mode="HTML",
    )


# ── /oneday / /threeday ───────────────────────────────────────────────────────

async def cmd_oneday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    code = "KEY-" + gen_code(12)
    context.bot_data.setdefault("keys", {})[code] = {"plan": "core", "days": 1, "used": False}
    await update.message.reply_text(
        f"1 DAY CODE\n\nCode: <code>{code}</code>\nRedeem: /rm {code}", parse_mode="HTML"
    )

async def cmd_threeday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    code = "KEY-" + gen_code(12)
    context.bot_data.setdefault("keys", {})[code] = {"plan": "core", "days": 3, "used": False}
    await update.message.reply_text(
        f"3 DAYS CODE\n\nCode: <code>{code}</code>\nRedeem: /rm {code}", parse_mode="HTML"
    )


# ── /sub / /resub ─────────────────────────────────────────────────────────────

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
        await update.message.reply_text(
            "U\u1d1b\u1d00\u0262\u1d07: /resub &lt;user_id&gt;", parse_mode="HTML"
        )
        return
    uid = await resolve_user(context.args[0], context)
    if not uid:
        await update.message.reply_text("U\u1d1b\u026a\u029f \u0274\u1d0f\u1d1c \u1d0a\u1d0f\u1d1c\u0274\u1d05.")
        return
    ud       = get_user_data(uid, context)
    raw_plan = ud.get("plan", "TRIAL").upper()
    expires  = ud.get("expires", 0)
    now      = time.time()
    if raw_plan != "TRIAL" and expires > now:
        remaining = int((expires - now) / 86400)
        await _grant(uid, raw_plan.lower(), remaining, update, context)
    else:
        await update.message.reply_text("U\u1d1b\u026a\u029f \u029c\u1d00\u1d1c \u0274\u1d0f \u1d00\u1d04\u1d1b\u026a\u1d20\u1d07 \u1d18\u029f\u1d00\u0274.")


# ── /allplans — upgraded, only premium, full info, auto-chunked ───────────────

async def cmd_allplans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    all_users = context.bot_data.get("user_data", {})
    now       = time.time()
    line      = "\u2501" * 20

    premium_users = [
        (uid_str, ud, ud.get("plan", "TRIAL").upper(), ud.get("expires", 0))
        for uid_str, ud in all_users.items()
        if ud.get("plan", "TRIAL").upper() != "TRIAL" and ud.get("expires", 0) > now
    ]

    if not premium_users:
        await update.message.reply_text(
            f"{line}\n"
            "\U0001F464 L\u026a\u1d20\u1d07 P\u0280\u1d07\u1d0d\u026a\u1d1c\u1d0d U\u1d1c\u1d07\u0280\u1d1c\n"
            f"{line}\n\n"
            "N\u1d0f \u1d00\u1d04\u1d1b\u026a\u1d20\u1d07 \u1d18\u029f\u1d00\u0274\u1d1c \u1d0a\u1d0f\u1d1c\u0274\u1d05.\n\n"
            f"{line}",
            parse_mode="HTML",
        )
        return

    header = (
        f"{line}\n"
        f"\U0001F464 L\u026a\u1d20\u1d07 P\u0280\u1d07\u1d0d\u026a\u1d1c\u1d0d U\u1d1c\u1d07\u0280\u1d1c\n"
        f"{line}\n"
        f"T\u1d0f\u1d1b\u1d00\u029f \u279a {len(premium_users)} U\u1d1c\u1d07\u0280\u1d1c\n"
        f"{line}\n\n"
    )
    current = header

    for uid_str, ud, raw_plan, expires in premium_users:
        name          = ud.get("name", "Unknown")
        stored_uname  = ud.get("username", None)
        uname_display = f"@{stored_uname}" if stored_uname else "None"
        joined        = ud.get("joined", "N/A")

        remaining_secs = expires - now
        remaining_days = int(remaining_secs / 86400)
        remaining_hrs  = int((remaining_secs % 86400) / 3600)
        remaining_mins = int((remaining_secs % 3600) / 60)
        remaining_str  = (
            f"{remaining_days}d {remaining_hrs}h" if remaining_days > 0
            else f"{remaining_hrs}h {remaining_mins}m" if remaining_hrs > 0
            else f"{remaining_mins}m"
        )
        exp_str = datetime.fromtimestamp(expires).strftime("%Y-%m-%d %H:%M")

        block = (
            f"N\u1d00\u1d0d\u1d07     \u279a {name}\n"
            f"U\u1d1b\u026a\u029f\u0274\u1d00\u1d0d\u1d07 \u279a {uname_display}\n"
            f"U\u1d1b\u026a\u029f ID \u279a <code>{uid_str}</code>\n"
            f"P\u029f\u1d00\u0274     \u279a {get_styled_plan(raw_plan)}\n"
            f"J\u1d0f\u026a\u0274\u1d07\u1d05  \u279a {joined}\n"
            f"E\u02e3\u1d18\u026a\u0280\u1d07\u1d04  \u279a {exp_str}\n"
            f"R\u1d07\u1d0d\u1d00\u026a\u0274\u026a\u0274\u0262 \u279a {remaining_str}\n"
            "S\u1d1b\u1d00\u1d1b\u1d1c\u1d1c  \u279a \u2705 A\u1d04\u1d1b\u026a\u1d20\u1d07\n"
            f"{line}\n\n"
        )

        if len(current) + len(block) > MAX_MSG:
            await update.message.reply_text(current, parse_mode="HTML")
            current = block
        else:
            current += block

    if current.strip():
        await update.message.reply_text(current, parse_mode="HTML")


# ── /seturl / /geturl ─────────────────────────────────────────────────────────

async def cmd_seturl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if len(context.args) < 2:
        await update.message.reply_text(
            "U\u1d1b\u1d00\u0262\u1d07: /seturl &lt;gate&gt; &lt;url&gt;\n"
            "G\u1d00\u1d1b\u1d07\u1d1c: chk, pp, sh, pyu, b3, au, mss, mpp2",
            parse_mode="HTML",
        )
        return
    gate = context.args[0].lower().strip()
    url  = context.args[1].strip()
    if gate not in GATE_NAMES:
        await update.message.reply_text(f"I\u0274\u1d20\u1d00\u029f\u026a\u1d05 \u0262\u1d00\u1d1b\u1d07: {gate}")
        return
    context.bot_data[f"gate_url_{gate}"] = url
    await update.message.reply_text(
        f"G\u1d00\u1d1b\u1d07 [{GATE_NAMES[gate]}] URL \u1d1c\u1d07\u1d1b:\n<code>{url}</code>",
        parse_mode="HTML",
    )


async def cmd_geturl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    line = "\u2501" * 18
    txt  = f"GATE URLs\n{line}\n\n"
    for gate, name in GATE_NAMES.items():
        url    = context.bot_data.get(f"gate_url_{gate}") or GATE_URLS.get(gate, "NOT SET")
        status = "ON" if context.bot_data.get(f"{gate}_on", True) else "OFF"
        txt   += f"{name} [{gate}]:\n  URL: <code>{url}</code>\n  Status: {status}\n\n"
    txt += line
    await update.message.reply_text(txt, parse_mode="HTML")


# ── /killb **…**

_This response is too long to display in full._
