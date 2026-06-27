import logging
import time
import string
import random
import asyncio
import signal
import os
from typing import Optional
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ApplicationHandlerStop,
)
from telegram.error import Conflict, BadRequest, NetworkError
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

BATMAN_PHOTO_PATH = "attached_assets/photo_5906503312989687726_w_(1)_1782576635191.jpg"

FORCE_CHANNELS = [
    ("Batcardchk",      CHANNEL_LINK),
    ("batcardchkGroup", GROUP_LINK),
]

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
    "t.me/a_toolsx", "t.me/a-toolsx", "@a_toolsx", "@atoolsx",
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

MAX_MSG = 4000


def B(text: str) -> str:
    bold_map = {
        'A': '\U0001d5d4', 'B': '\U0001d5d5', 'C': '\U0001d5d6', 'D': '\U0001d5d7',
        'E': '\U0001d5d8', 'F': '\U0001d5d9', 'G': '\U0001d5da', 'H': '\U0001d5db',
        'I': '\U0001d5dc', 'J': '\U0001d5dd', 'K': '\U0001d5de', 'L': '\U0001d5df',
        'M': '\U0001d5e0', 'N': '\U0001d5e1', 'O': '\U0001d5e2', 'P': '\U0001d5e3',
        'Q': '\U0001d5e4', 'R': '\U0001d5e5', 'S': '\U0001d5e6', 'T': '\U0001d5e7',
        'U': '\U0001d5e8', 'V': '\U0001d5e9', 'W': '\U0001d5ea', 'X': '\U0001d5eb',
        'Y': '\U0001d5ec', 'Z': '\U0001d5ed',
        'a': '\U0001d5ee', 'b': '\U0001d5ef', 'c': '\U0001d5f0', 'd': '\U0001d5f1',
        'e': '\U0001d5f2', 'f': '\U0001d5f3', 'g': '\U0001d5f4', 'h': '\U0001d5f5',
        'i': '\U0001d5f6', 'j': '\U0001d5f7', 'k': '\U0001d5f8', 'l': '\U0001d5f9',
        'm': '\U0001d5fa', 'n': '\U0001d5fb', 'o': '\U0001d5fc', 'p': '\U0001d5fd',
        'q': '\U0001d5fe', 'r': '\U0001d5ff', 's': '\U0001d600', 't': '\U0001d601',
        'u': '\U0001d602', 'v': '\U0001d603', 'w': '\U0001d604', 'x': '\U0001d605',
        'y': '\U0001d606', 'z': '\U0001d607',
        '0': '\U0001d7ec', '1': '\U0001d7ed', '2': '\U0001d7ee', '3': '\U0001d7ef',
        '4': '\U0001d7f0', '5': '\U0001d7f1', '6': '\U0001d7f2', '7': '\U0001d7f3',
        '8': '\U0001d7f4', '9': '\U0001d7f5',
    }
    return "".join(bold_map.get(ch, ch) for ch in text)


CHECKER_STATUS_TEXT = (
    "CHECKER STATUS:\n"
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
    "A\u1d1c\u1d1b\u029c G\u1d00\u1d1b\u1d07   \u279a 2\n"
    "M\u1d00\u1d1c\u1d1c G\u1d00\u1d1b\u1d07  \u279a 2\n"
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
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
    "G\u1d00\u1d1b\u1d07    \u279a S\u1d1b\u0280\u026a\u1d18\u1d07 0$\n"
    "C\u1d0f\u1d0d\u1d0d\u1d00\u0274\u1d05 \u279a /chk\n"
    "S\u026a\u1d1b\u1d07   \u279a 16\n"
    "H\u1d07\u1d00\u029f\u1d1b\u029c  \u279a 100%\n"
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
)

BRAINTREE_TEXT = (
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
    "G\u1d00\u1d1b\u1d07    \u279a B\u0280\u1d00\u026a\u0274\u1d1b\u0280\u1d07\u1d07 0$\n"
    "C\u1d0f\u1d0d\u1d0d\u1d00\u0274\u1d05 \u279a /b3\n"
    "S\u026a\u1d1b\u1d07   \u279a 2\n"
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
    "S\u1d07\u029f\u1d07\u1d04\u1d1b M\u1d00\u1d1c\u1d1c G\u1d00\u1d1b\u1d07 \u279a\n"
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
)

PLAN_TEXT = (
    "\u2501" * 20 + "\n"
    "Batman Premium Plans\n"
    + "\u2501" * 20 + "\n\n"
    "A\u1d04\u1d04\u1d07\u1d1c\u1d1c \u279a C\u1d0f\u0280\u1d07 \U0001F380\n"
    "S\u1d18\u1d00\u0274   \u279a [7 D\u1d00y\u1d1c]\n"
    "C\u0280\u1d07\u1d05\u026a\u1d1b\u1d1c \u279a \u221e Unlimited\n"
    "P\u0280\u026a\u1d04\u1d07  \u279a 10$\n"
    + "\u2501" * 16 + "\n"
    "A\u1d04\u1d04\u1d07\u1d1c\u1d1c \u279a E\u029f\u026a\u1d1b\u1d07 \u2b50\ufe0f\n"
    "S\u1d18\u1d00\u0274   \u279a [15 D\u1d00y\u1d1c]\n"
    "C\u0280\u1d07\u1d05\u026a\u1d1b\u1d1c \u279a \u221e Unlimited\n"
    "P\u0280\u026a\u1d04\u1d07  \u279a 15$\n"
    + "\u2501" * 16 + "\n"
    "A\u1d04\u1d04\u1d07\u1d1c\u1d1c \u279a R\u1d0f\u1d0f\u1d1b \U0001F451\n"
    "S\u1d18\u1d00\u0274   \u279a [30 D\u1d00y\u1d1c]\n"
    "C\u0280\u1d07\u1d05\u026a\u1d1b\u1d1c \u279a \u221e Unlimited\n"
    "P\u0280\u026a\u1d04\u1d07  \u279a 30$\n"
    + "\u2501" * 20
)

PAYMENT_PENDING_TEXT = (
    "\u2501" * 20 + "\n"
    "Payment Address\n"
    + "\u2501" * 20 + "\n\n"
    "Payment address will be added shortly.\n\n"
    "For payment contact through support.\n\n"
    + "\u2501" * 20
)

FORCE_JOIN_TEXT = (
    "\u2501" * 20 + "\n"
    "\U0001F987 Welcome to Batman Card Checker!\n"
    + "\u2501" * 20 + "\n\n"
    "To use this bot you must join our\n"
    "channel and group first.\n\n"
    "\U0001F447 Click the buttons below to join:\n\n"
    + "\u2501" * 20
)


def get_styled_plan(raw_plan: str) -> str:
    p = raw_plan.upper()
    if p == "CORE":  return "C\u1d0f\u0280\u1d07 \U0001F380"
    if p == "ELITE": return "E\u029f\u026a\u1d1b\u1d07 \u2b50\ufe0f"
    if p == "ROOT":  return "R\u1d0f\u1d0f\u1d1b \U0001F451"
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
    return "BATCARD-{}-CHK".format(random.randint(100000, 999999))


def ui_profile(user, context: ContextTypes.DEFAULT_TYPE) -> str:
    ud       = get_user_data(user.id, context)
    raw_plan = ud.get("plan", "TRIAL").upper()
    expires  = ud.get("expires", 0)
    now      = time.time()
    if raw_plan != "TRIAL" and expires <= now:
        raw_plan = "TRIAL"
        ud["plan"] = "TRIAL"
        ud["expires"] = 0
        expires = 0
    is_premium = raw_plan != "TRIAL"
    credits    = "\u221e Unlimited" if is_premium else "{}/150".format(ud.get("credits", 150))
    uname      = "@{}".format(user.username) if user.username else "None"
    lines = [
        "User    \u279a {}".format(uname),
        "User ID \u279a <code>{}</code>".format(user.id),
        "Access  \u279a {}".format(get_styled_plan(raw_plan)),
        "Credits \u279a {}".format(credits),
    ]
    if is_premium and expires > now:
        exp_date    = datetime.fromtimestamp(expires).strftime("%Y-%m-%d %H:%M")
        remaining_d = int((expires - now) / 86400)
        remaining_h = int(((expires - now) % 86400) / 3600)
        lines.append("Expires  \u279a {}".format(exp_date))
        if remaining_d > 0:
            lines.append("Remaining \u279a {}d {}h".format(remaining_d, remaining_h))
        else:
            lines.append("Remaining \u279a {}h".format(remaining_h))
    lines.append("Joined  \u279a {}".format(ud.get("joined", datetime.now().strftime("%Y-%m-%d"))))
    lines.append("Dev    \u279a <a href='{}'>Batman</a>".format(DEV_LINK))
    lines.append("Version \u279a {}".format(VERSION))
    return "\n".join(lines)


async def is_member(bot, user_id: int, chat_username: str) -> bool:
    try:
        member = await bot.get_chat_member("@{}".format(chat_username), user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception:
        return False


async def check_force_join(user_id: int, bot) -> bool:
    if user_id == OWNER_ID:
        return True
    results = await asyncio.gather(
        *[is_member(bot, user_id, uname) for uname, _ in FORCE_CHANNELS],
        return_exceptions=True,
    )
    return all(r is True for r in results)


def kb_force_join() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("JOIN CHANNEL") + " \u2197", url=CHANNEL_LINK)],
        [InlineKeyboardButton(B("JOIN GROUP") + " \u2197",   url=GROUP_LINK)],
        [InlineKeyboardButton("\u2705 " + B("VERIFY"),        callback_data="verify_join")],
    ])


async def send_force_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        with open(BATMAN_PHOTO_PATH, "rb") as photo_file:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=photo_file,
                caption=FORCE_JOIN_TEXT,
                reply_markup=kb_force_join(),
                parse_mode="HTML",
            )
    except Exception:
        await update.effective_message.reply_text(
            FORCE_JOIN_TEXT,
            reply_markup=kb_force_join(),
            parse_mode="HTML",
        )


def kb_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(B("CHECKER"),         callback_data="mgates"),
            InlineKeyboardButton(B("BUY NOW"),          callback_data="mprice"),
        ],
        [
            InlineKeyboardButton(B("UPDATES") + " \u2197", url=CHANNEL_LINK),
            InlineKeyboardButton(B("GROUP") + " \u2197",   url=GROUP_LINK),
        ],
        [
            InlineKeyboardButton(B("SUPPORT") + " \u2197", url=SUPPORT_LINK),
        ],
    ])


def kb_back(cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("\U0001f519 " + B("BACK"), callback_data=cb)]])


def kb_bin_result() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(B("Batcardchk") + " \u2197", url=BOT_LINK)]])


def kb_price() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(B("10$ PAY"), callback_data="pay10"),
            InlineKeyboardButton(B("15$ PAY"), callback_data="pay15"),
            InlineKeyboardButton(B("30$ PAY"), callback_data="pay30"),
        ],
        [InlineKeyboardButton(B("SUPPORT") + " \u2197", url=SUPPORT_LINK)],
        [InlineKeyboardButton("\U0001f519 " + B("BACK"),  callback_data="bmain")],
    ])


def kb_payment() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("SUPPORT") + " \u2197", url=SUPPORT_LINK)],
        [InlineKeyboardButton("\U0001f519 " + B("BACK"), callback_data="mprice")],
    ])


def kb_gate_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(B("AUTH"),   callback_data="mauth"),
            InlineKeyboardButton(B("CHARGE"), callback_data="mcharge"),
            InlineKeyboardButton(B("MASS"),   callback_data="mmass"),
        ],
        [InlineKeyboardButton("\U0001f519 " + B("BACK"), callback_data="bmain")],
    ])


def kb_auth_gates() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(B("STRIPE"),    callback_data="iau"),
            InlineKeyboardButton(B("BRAINTREE"), callback_data="ib3"),
        ],
        [InlineKeyboardButton("\U0001f519 " + B("BACK"), callback_data="mgates")],
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
        [InlineKeyboardButton("\U0001f519 " + B("BACK"), callback_data="mgates")],
    ])


def kb_mass_gates() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("STRIPE MASS"), callback_data="imss")],
        [InlineKeyboardButton(B("PAYPAL MASS"), callback_data="impp2")],
        [InlineKeyboardButton("\U0001f519 " + B("BACK"), callback_data="mgates")],
    ])


def gate_info_text(gate_name: str, cmd: str, cost: int) -> str:
    line = "\u2501" * 20
    return (
        "{}\n{}\n{}\n\n"
        "Cost    \u279a {} Credit(s) per check\n\n"
        "Usage:\n<code>/{} cc|mm|yy|cvv</code>\n\n"
        "Example:\n<code>/{} 4111111111111111|12|2026|123</code>\n\n"
        "{}"
    ).format(line, gate_name, line, cost, cmd, cmd, line)


async def maintenance_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    if context.bot_data.get("maintenance", False) and update.effective_user.id != OWNER_ID:
        try:
            if update.message:
                await update.message.reply_text("Bot is currently under maintenance.")
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
    if not await check_force_join(update.effective_user.id, context.bot):
        await send_force_join(update, context)
        return

    if not context.bot_data.get("{}_on".format(gate_key), True):
        await update.message.reply_text("Gate is currently OFF.")
        return

    card = (
        context.args[0] if context.args
        else (
            update.message.reply_to_message.text.strip()
            if update.message.reply_to_message and update.message.reply_to_message.text
            else None
        )
    )
    if not card:
        await update.message.reply_text(
            "Usage: <code>/{} cc|mm|yy|cvv</code>".format(gate_key),
            parse_mode="HTML"
        )
        return

    ud         = get_user_data(update.effective_user.id, context)
    raw_plan   = ud.get("plan", "TRIAL").upper()
    is_premium = raw_plan != "TRIAL" and ud.get("expires", 0) > time.time()

    if not is_premium:
        credits = ud.get("credits", 150)
        if credits <= 0:
            await update.message.reply_text(
                "Your trial credits are empty. Purchase a plan with /plan."
            )
            return

    api_url  = context.bot_data.get("gate_url_{}".format(gate_key)) or GATE_URLS.get(gate_key, "")
    site_url = GATE_SITES.get(gate_key, "example.com")
    bin_num  = card[:6]

    if not api_url:
        await update.message.reply_text(
            "Gate API URL not set. Owner: /seturl {} &lt;url&gt;".format(gate_key),
            parse_mode="HTML"
        )
        return

    if not is_premium:
        ud["credits"] = credits - 1

    msg        = await update.message.reply_text("\u26a1 Processing...")
    start_time = time.time()

    try:
        timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)
        connector = aiohttp.TCPConnector(limit=20, ttl_dns_cache=300)
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
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
        is_approved = any(w in raw_response.lower() for w in ["approved", "captured", "success"])
        status_ui   = "APPROVED \u2705" if is_approved else "DECLINED \u274c"

        bin_txt = "N/A"
        if not bin_data.get("error"):
            s       = str(bin_data.get("scheme", "N/A")).upper()
            b       = bin_data.get("bank", "N/A")
            country = str(bin_data.get("country", "N/A")).upper()
            flag    = bin_data.get("country_emoji", "")
            bin_txt = "{} - {} - {} {}".format(s, b, flag, country)

        if raw_plan != "TRIAL" and ud.get("expires", 0) <= time.time():
            raw_plan = "TRIAL"

        plan_ui    = get_styled_plan(raw_plan)
        first_name = update.effective_user.first_name or "User"
        time_taken = "{:.2f}".format(time.time() - start_time)

        text = (
            "[ STATUS ] \u279a {}\n"
            "Card \u279a <code>{}</code>\n"
            "Gate \u279a {}\n"
            "Raw  \u279a {}\n"
            "Info \u279a {}\n"
            "User \u279a {} ({})\n"
            "Bot  \u279a Batman\n"
            "Time \u279a {}s"
        ).format(status_ui, card, gate_name, raw_response, bin_txt, first_name, plan_ui, time_taken)

        await msg.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=kb_result(),
            disable_web_page_preview=True,
        )

    except aiohttp.ServerTimeoutError:
        if not is_premium:
            ud["credits"] = ud.get("credits", 0) + 1
        await msg.edit_text("Timeout - Gate did not respond. Credit refunded.")
    except Exception as e:
        if not is_premium:
            ud["credits"] = ud.get("credits", 0) + 1
        logger.error("process_gate [{}]: {}".format(gate_key, e))
        await msg.edit_text(
            "Error: <code>{}</code>".format(str(e)[:120]),
            parse_mode="HTML"
        )


async def cmd_chk(u, c):  await process_gate(u, c, "chk",  "Stripe Charge")
async def cmd_pp(u, c):   await process_gate(u, c, "pp",   "PayPal Charge")
async def cmd_sh(u, c):   await process_gate(u, c, "sh",   "Shopify Charge")
async def cmd_pyu(u, c):  await process_gate(u, c, "pyu",  "PayU Charge")
async def cmd_b3(u, c):   await process_gate(u, c, "b3",   "Braintree Auth")
async def cmd_au(u, c):   await process_gate(u, c, "au",   "Stripe Auth")
async def cmd_mss(u, c):  await process_gate(u, c, "mss",  "Stripe Mass")
async def cmd_mpp2(u, c): await process_gate(u, c, "mpp2", "PayPal Mass")


async def send_activation_msg(
    user_id: int, plan: str, days: int, context: ContextTypes.DEFAULT_TYPE
) -> str:
    receipt = gen_receipt()
    name, username = "Unknown", None
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
    if username:
        ud["username"] = username
    exp_date      = datetime.fromtimestamp(ud["expires"]).strftime("%Y-%m-%d %H:%M")
    uname_display = "@{}".format(username) if username else "None"
    txt = (
        "Congratulations! Your access has been activated.\n"
        + "\u2501" * 20 + "\n\n"
        + "User     \u279a {}\n".format(name)
        + "Username \u279a {}\n".format(uname_display)
        + "Access   \u279a {}\n".format(get_styled_plan(plan))
        + "Duration  \u279a {} Days\n".format(days)
        + "Credits   \u279a \u221e Unlimited\n"
        + "Expires   \u279a {}\n".format(exp_date)
        + "Receipt  \u279a <code>{}</code>\n\n".format(receipt)
        + "\u2501" * 20 + "\n"
        + "Please save this receipt ID."
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
    for attempt in ("@{}".format(target), target):
        try:
            return (await context.bot.get_chat(attempt)).id
        except Exception:
            continue
    return None


async def send_chunks(send_fn, text: str, **kwargs):
    if len(text) <= MAX_MSG:
        await send_fn(text, **kwargs)
        return
    lines = text.split("\n")
    chunk = ""
    for line in lines:
        if len(chunk) + len(line) + 1 > MAX_MSG:
            await send_fn(chunk, **kwargs)
            chunk = line + "\n"
        else:
            chunk += line + "\n"
    if chunk.strip():
        await send_fn(chunk, **kwargs)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ud   = get_user_data(user.id, context)
    ud.setdefault("joined", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    ud.setdefault("name",   user.first_name or "User")
    if user.username:
        ud["username"] = user.username

    if not await check_force_join(user.id, context.bot):
        await send_force_join(update, context)
        return

    is_new = not context.bot_data.get("user_data", {}).get(str(user.id), {}).get("_welcomed", False)
    ud["_welcomed"] = True

    if is_new:
        try:
            with open(BATMAN_PHOTO_PATH, "rb") as photo_file:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=photo_file,
                    caption=(
                        "\U0001F987 <b>Welcome to Batman Card Checker!</b>\n\n"
                        "Join our community:\n"
                        "\U0001F4E2 Channel: {}\n"
                        "\U0001F465 Group: {}"
                    ).format(CHANNEL_LINK, GROUP_LINK),
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
        except Exception:
            pass

    await update.message.reply_text(
        ui_profile(user, context),
        parse_mode="HTML",
        reply_markup=kb_main(),
        disable_web_page_preview=True,
    )


async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    start = time.time()
    msg = await update.message.reply_text("Pinging...")
    elapsed = (time.time() - start) * 1000
    await msg.edit_text("\u26a1 Pong! Speed: {:.0f}ms".format(elapsed))


async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_force_join(update.effective_user.id, context.bot):
        await send_force_join(update, context)
        return
    await update.message.reply_text(
        PLAN_TEXT,
        parse_mode="HTML",
        reply_markup=kb_price(),
        disable_web_page_preview=True,
    )


async def cmd_rm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_force_join(update.effective_user.id, context.bot):
        await send_force_join(update, context)
        return
    if not context.args:
        await update.message.reply_text("Usage: /rm &lt;code&gt;", parse_mode="HTML")
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
            "Redeemed! Added {} credits. Balance: {}/150".format(
                codes[code]["value"], ud["credits"]
            )
        )
    elif code in keys and not keys[code]["used"]:
        keys[code]["used"] = True
        p, d = keys[code]["plan"], keys[code]["days"]
        ud["plan"]    = p
        ud["expires"] = time.time() + (d * 86400)
        receipt = await send_activation_msg(uid, p, d, context)
        await update.message.reply_text(
            "Activated {} for {} days.\nReceipt \u279a <code>{}</code>".format(
                get_styled_plan(p), d, receipt
            ),
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text("Invalid or already used code.")


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
            for attempt in ("@{}".format(raw), raw):
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
        target_name = "{} {}".format(target_name, target_lastname)

    username_display = "@{}".format(target_username) if target_username else "None"

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
            raw_plan = "TRIAL"
            udata["plan"]    = "TRIAL"
            udata["expires"] = 0
            expires = 0
    else:
        raw_plan    = "TRIAL"
        expires     = 0
        joined      = "Never used the bot"
        credits_val = 150

    is_premium = raw_plan != "TRIAL" and expires > now
    credits    = "\u221e Unlimited" if is_premium else "{}/150".format(credits_val)
    line       = "\u2501" * 20

    txt = (
        "{}\n"
        "\U0001F464 User Info\n"
        "{}\n\n"
        "Name      \u279a {}\n"
        "Username  \u279a {}\n"
        "User ID  \u279a <code>{}</code>\n"
        "Plan      \u279a {}\n"
        "Credits  \u279a {}\n"
        "Joined   \u279a {}\n"
    ).format(
        line, line,
        target_name, username_display, target_id,
        get_styled_plan(raw_plan), credits, joined,
    )

    if is_premium:
        exp_str        = datetime.fromtimestamp(expires).strftime("%Y-%m-%d %H:%M")
        remaining_secs = expires - now
        remaining_days = int(remaining_secs / 86400)
        remaining_hrs  = int((remaining_secs % 86400) / 3600)
        remaining_mins = int((remaining_secs % 3600) / 60)
        if remaining_days > 0:
            remaining_str = "{}d {}h".format(remaining_days, remaining_hrs)
        elif remaining_hrs > 0:
            remaining_str = "{}h {}m".format(remaining_hrs, remaining_mins)
        else:
            remaining_str = "{}m".format(remaining_mins)
        txt += (
            "Plan End  \u279a {}\n"
            "Remaining \u279a {}\n"
            "Status  \u279a \u2705 Active\n"
        ).format(exp_str, remaining_str)
    else:
        txt += (
            "Plan End  \u279a No Active Plan\n"
            "Remaining \u279a N/A\n"
            "Status  \u279a \u274c Inactive / Trial\n"
        )

    txt += "\n{}".format(line)
    await update.message.reply_text(txt, parse_mode="HTML")


async def cmd_allcm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    line = "\u2501" * 18
    await update.message.reply_text(
        "BATMAN BOT - ALL COMMANDS\n{}\nVersion: {}\n{}\n\n"
        "USER COMMANDS\n{}\n"
        "/start  /plan  /bin  /rm  /ping\n"
        "/chk  /pp  /sh  /pyu  /b3  /au  /mss  /mpp2\n\n"
        "OWNER COMMANDS\n{}\n"
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
        "{}".format(line, VERSION, line, line, line, line),
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
        context.bot_data.setdefault("codes", {})[code] = {"type": "credit", "value": amt, "used": False}
        await update.message.reply_text(
            "CODE GENERATED\n\nCode: <code>{}</code>\nCredits: {}".format(code, amt),
            parse_mode="HTML"
        )
    except ValueError:
        await update.message.reply_text("Invalid amount.")


async def _gen_key(update: Update, context: ContextTypes.DEFAULT_TYPE, plan: str, days: int):
    if update.effective_user.id != OWNER_ID:
        return
    code = "KEY-" + gen_code(12)
    context.bot_data.setdefault("keys", {})[code] = {"plan": plan, "days": days, "used": False}
    await update.message.reply_text(
        "KEY GENERATED\n\nKey : <code>{}</code>\nPlan: {}\nDays: {}".format(
            code, get_styled_plan(plan), days
        ),
        parse_mode="HTML",
    )

async def cmd_key10(u, c): await _gen_key(u, c, "CORE",  7)
async def cmd_key20(u, c): await _gen_key(u, c, "ELITE", 15)
async def cmd_key30(u, c): await _gen_key(u, c, "ROOT",  30)


async def _grant(uid: int, plan: str, days: int, update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud = get_user_data(uid, context)
    ud["plan"]    = plan
    ud["expires"] = time.time() + (days * 86400)
    receipt = await send_activation_msg(uid, plan, days, context)
    await update.message.reply_text(
        "Granted {} Days ({}) to <code>{}</code>\nReceipt \u279a <code>{}</code>".format(
            days, get_styled_plan(plan), uid, receipt
        ),
        parse_mode="HTML",
    )


async def cmd_oneday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    code = "KEY-" + gen_code(12)
    context.bot_data.setdefault("keys", {})[code] = {"plan": "CORE", "days": 1, "used": False}
    await update.message.reply_text(
        "1 DAY CODE\n\nCode: <code>{}</code>\nRedeem: /rm {}".format(code, code),
        parse_mode="HTML"
    )

async def cmd_threeday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    code = "KEY-" + gen_code(12)
    context.bot_data.setdefault("keys", {})[code] = {"plan": "CORE", "days": 3, "used": False}
    await update.message.reply_text(
        "3 DAYS CODE\n\nCode: <code>{}</code>\nRedeem: /rm {}".format(code, code),
        parse_mode="HTML"
    )


async def cmd_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /sub &lt;user_id or @username&gt; &lt;days&gt;\n"
            "Example: /sub @username 30",
            parse_mode="HTML"
        )
        return
    uid = await resolve_user(context.args[0], context)
    if not uid:
        await update.message.reply_text("User not found.")
        return
    try:
        days = int(context.args[1])
        plan = "ROOT" if days >= 30 else "ELITE" if days >= 15 else "CORE"
        await _grant(uid, plan, days, update, context)
    except ValueError:
        await update.message.reply_text("Invalid days. Usage: /sub @username 30")


async def cmd_resub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text(
            "Usage: /resub &lt;user_id or @username&gt;\n"
            "This will REMOVE the user's premium and reset to TRIAL.",
            parse_mode="HTML"
        )
        return
    uid = await resolve_user(context.args[0], context)
    if not uid:
        await update.message.reply_text("User not found.")
        return

    uid_str  = str(uid)
    all_data = context.bot_data.get("user_data", {})

    if uid_str not in all_data:
        await update.message.reply_text(
            "User <code>{}</code> has no data in bot.".format(uid),
            parse_mode="HTML"
        )
        return

    ud       = all_data[uid_str]
    raw_plan = ud.get("plan", "TRIAL").upper()
    expires  = ud.get("expires", 0)
    now      = time.time()

    if raw_plan == "TRIAL" or expires <= now:
        await update.message.reply_text(
            "User <code>{}</code> has no active premium to remove.".format(uid),
            parse_mode="HTML"
        )
        return

    old_plan    = get_styled_plan(raw_plan)
    old_expires = datetime.fromtimestamp(expires).strftime("%Y-%m-%d %H:%M")

    ud["plan"]    = "TRIAL"
    ud["expires"] = 0
    ud["credits"] = 0

    try:
        await context.bot.send_message(
            chat_id=uid,
            text=(
                "\u2501" * 18 + "\n"
                "\u274c Premium Removed\n"
                "\u2501" * 18 + "\n\n"
                "Your premium access has been removed by the owner.\n"
                "Your account has been reset to Trial.\n\n"
                "Contact support if you think this is a mistake.\n"
                "\u2501" * 18
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass

    line = "\u2501" * 18
    await update.message.reply_text(
        "{}\n"
        "\u2705 Premium Removed\n"
        "{}\n\n"
        "User ID   \u279a <code>{}</code>\n"
        "Old Plan  \u279a {}\n"
        "Old Expiry \u279a {}\n"
        "New Plan  \u279a Trial\n"
        "Status   \u279a \u274c Reset to Trial\n"
        "{}".format(line, line, uid, old_plan, old_expires, line),
        parse_mode="HTML",
    )


async def cmd_allplans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    all_users     = context.bot_data.get("user_data", {})
    now           = time.time()
    line          = "\u2501" * 20
    premium_users = []

    for uid_str, ud in all_users.items():
        raw_plan = ud.get("plan", "TRIAL").upper()
        expires  = ud.get("expires", 0)
        if raw_plan != "TRIAL" and expires > now:
            premium_users.append((uid_str, ud, raw_plan, expires))

    if not premium_users:
        await update.message.reply_text(
            "{}\n\U0001F464 Live Premium Users\n{}\n\nNo active plans found.\n\n{}".format(
                line, line, line
            ),
            parse_mode="HTML",
        )
        return

    header  = "{}\n\U0001F464 Live Premium Users\n{}\nTotal \u279a {} Users\n{}\n\n".format(
        line, line, len(premium_users), line
    )
    current = header

    for uid_str, ud, raw_plan, expires in premium_users:
        name          = ud.get("name", "Unknown")
        stored_uname  = ud.get("username", None)
        uname_display = "@{}".format(stored_uname) if stored_uname else "None"
        joined        = ud.get("joined", "N/A")

        remaining_secs = expires - now
        remaining_days = int(remaining_secs / 86400)
        remaining_hrs  = int((remaining_secs % 86400) / 3600)
        remaining_mins = int((remaining_secs % 3600) / 60)
        if remaining_days > 0:
            remaining_str = "{}d {}h".format(remaining_days, remaining_hrs)
        elif remaining_hrs > 0:
            remaining_str = "{}h {}m".format(remaining_hrs, remaining_mins)
        else:
            remaining_str = "{}m".format(remaining_mins)

        exp_str = datetime.fromtimestamp(expires).strftime("%Y-%m-%d %H:%M")

        block = (
            "Name     \u279a {}\n"
            "Username \u279a {}\n"
            "User ID \u279a <code>{}</code>\n"
            "Plan     \u279a {}\n"
            "Joined  \u279a {}\n"
            "Expires  \u279a {}\n"
            "Remaining \u279a {}\n"
            "Status  \u279a \u2705 Active\n"
            "{}\n\n"
        ).format(
            name, uname_display, uid_str,
            get_styled_plan(raw_plan), joined, exp_str, remaining_str, line
        )

        if len(current) + len(block) > MAX_MSG:
            await update.message.reply_text(current, parse_mode="HTML")
            current = block
        else:
            current += block

    if current.strip():
        await update.message.reply_text(current, parse_mode="HTML")


async def cmd_seturl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /seturl &lt;gate&gt; &lt;url&gt;\nGates: chk, pp, sh, pyu, b3, au, mss, mpp2",
            parse_mode="HTML",
        )
        return
    gate = context.args[0].lower().strip()
    url  = context.args[1].strip()
    if gate not in GATE_NAMES:
        await update.message.reply_text("Invalid gate: {}".format(gate))
        return
    context.bot_data["gate_url_{}".format(gate)] = url
    await update.message.reply_text(
        "Gate [{}] URL set:\n<code>{}</code>".format(GATE_NAMES[gate], url),
        parse_mode="HTML",
    )


async def cmd_geturl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    line = "\u2501" * 18
    txt  = "GATE URLs\n{}\n\n".format(line)
    for gate, name in GATE_NAMES.items():
        url    = context.bot_data.get("gate_url_{}".format(gate)) or GATE_URLS.get(gate, "NOT SET")
        status = "ON" if context.bot_data.get("{}_on".format(gate), True) else "OFF"
        txt   += "{}  [{}]:\n  URL: <code>{}</code>\n  Status: {}\n\n".format(name, gate, url, status)
    txt += line
    await update.message.reply_text(txt, parse_mode="HTML")


async def cmd_killbot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    context.bot_data["maintenance"] = True
    await update.message.reply_text("Bot turned OFF - Maintenance mode.")


async def cmd_onbot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    context.bot_data["maintenance"] = False
    await update.message.reply_text("Bot turned ON - Bot is now available.")


async def _gate_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE, gate: str, state: bool):
    if update.effective_user.id != OWNER_ID:
        return
    context.bot_data["{}_on".format(gate)] = state
    await update.message.reply_text(
        "Gate [{}] turned {}.".format(GATE_NAMES[gate], "ON" if state else "OFF")
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


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data  = query.data
    user  = query.from_user

    try:
        await query.answer()
    except Exception:
        pass

    if context.bot_data.get("maintenance", False) and user.id != OWNER_ID:
        try:
            await query.answer("Bot is under maintenance.", show_alert=True)
        except Exception:
            pass
        return

    if data == "verify_join":
        joined = await check_force_join(user.id, context.bot)
        if joined:
            try:
                await query.message.delete()
            except Exception:
                pass
            ud = get_user_data(user.id, context)
            ud.setdefault("joined", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            ud.setdefault("name",   user.first_name or "User")
            if user.username:
                ud["username"] = user.username
            try:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=ui_profile(user, context),
                    parse_mode="HTML",
                    reply_markup=kb_main(),
                    disable_web_page_preview=True,
                )
            except Exception as ex:
                logger.error("verify send: {}".format(ex))
        else:
            try:
                await query.answer(
                    "You have not joined yet!\n\nPlease join both the channel and group first, then press VERIFY.",
                    show_alert=True,
                )
            except Exception:
                pass
        return

    if not await check_force_join(user.id, context.bot):
        try:
            await query.answer("You must join our channel & group first!", show_alert=True)
        except Exception:
            pass
        return

    async def edit(text: str, markup: InlineKeyboardMarkup):
        try:
            await query.message.edit_text(
                text=text,
                parse_mode="HTML",
                reply_markup=markup,
                disable_web_page_preview=True,
            )
        except BadRequest as e:
            err = str(e).lower()
            if "message is not modified" in err:
                return
            if "there is no text" in err or "message can't be edited" in err or "caption" in err:
                try:
                    await query.message.edit_caption(
                        caption=text,
                        parse_mode="HTML",
                        reply_markup=markup,
                    )
                    return
                except BadRequest as e2:
                    if "message is not modified" in str(e2).lower():
                        return
                except Exception:
                    pass
            try:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=markup,
                    disable_web_page_preview=True,
                )
            except Exception:
                pass

    if data == "bmain":
        await edit(ui_profile(user, context), kb_main())
    elif data == "mgates":
        await edit(CHECKER_STATUS_TEXT, kb_gate_main())
    elif data == "mprice":
        await edit(PLAN_TEXT, kb_price())
    elif data == "mauth":
        await edit(AUTH_MENU_TEXT, kb_auth_gates())
    elif data == "mcharge":
        await edit(CHARGE_MENU_TEXT, kb_charge_gates())
    elif data == "mmass":
        await edit(MASS_MENU_TEXT, kb_mass_gates())
    elif data == "iau":
        await edit(STRIPE_AUTH_TEXT, kb_back("mauth"))
    elif data == "ib3":
        await edit(BRAINTREE_TEXT, kb_back("mauth"))
    elif data in ("ichk", "ipp", "ish", "ipyu"):
        gate_map = {
            "ichk": ("chk", "Stripe Charge", 1),
            "ipp":  ("pp",  "PayPal Charge", 1),
            "ish":  ("sh",  "Shopify Charge", 1),
            "ipyu": ("pyu", "PayU Charge", 1),
        }
        gk, gn, gc = gate_map[data]
        await edit(gate_info_text(gn, gk, gc), kb_back("mcharge"))
    elif data in ("imss", "impp2"):
        gate_map = {
            "imss":  ("mss",  "Stripe Mass",  2),
            "impp2": ("mpp2", "PayPal Mass",  2),
        }
        gk, gn, gc = gate_map[data]
        await edit(gate_info_text(gn, gk, gc), kb_back("mmass"))
    elif data in ("pay10", "pay15", "pay30"):
        await edit(PAYMENT_PENDING_TEXT, kb_payment())


# ============================================================
# ERROR HANDLER - catches ALL errors including Conflict
# ============================================================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global error handler that prevents unhandled exceptions from crashing the bot."""
    error = context.error

    if isinstance(error, Conflict):
        logger.warning(
            "CONFLICT detected: Another bot instance is running with the same token. "
            "This instance will keep retrying. Kill other instances to resolve."
        )
        return

    if isinstance(error, NetworkError):
        logger.warning("Network error (will auto-retry): %s", error)
        return

    if isinstance(error, BadRequest):
        # BadRequests are usually non-fatal (deleted message, etc.)
        logger.debug("BadRequest (non-fatal): %s", error)
        return

    # Log all other unexpected errors
    logger.error("Unhandled exception: %s", error, exc_info=context.error)

    # Optionally notify owner about critical errors
    if update and hasattr(update, "effective_chat") and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=OWNER_ID,
                text="\u26a0\ufe0f Bot Error:\n<code>{}</code>".format(str(error)[:500]),
                parse_mode="HTML",
            )
        except Exception:
            pass


# ============================================================
# POST-INIT: safely drop pending updates on startup
# ============================================================
async def post_init(application: Application) -> None:
    """Called after Application is initialized. Drops any queued updates."""
    logger.info("Bot initialized. Dropping any pending updates...")
    try:
        await application.bot.delete_webhook(drop_pending_updates=True)
        logger.info("Pending updates dropped successfully.")
    except Conflict:
        logger.warning(
            "Conflict on startup: Another instance is still polling. "
            "Waiting for it to release..."
        )
        await asyncio.sleep(3)
        try:
            await application.bot.delete_webhook(drop_pending_updates=True)
            logger.info("Pending updates dropped after retry.")
        except Exception as e:
            logger.error("Failed to drop updates after retry: %s", e)
    except Exception as e:
        logger.error("Error dropping pending updates: %s", e)


# ============================================================
# POST-SHUTDOWN: clean logout
# ============================================================
async def post_shutdown(application: Application) -> None:
    """Called when the bot is shutting down."""
    logger.info("Bot shutting down. Releasing webhook/getUpdates lock...")
    try:
        await application.bot.delete_webhook(drop_pending_updates=False)
    except Exception:
        pass
    logger.info("Bot stopped cleanly.")


# ============================================================
# BUILD AND RUN
# ============================================================
def build_application() -> Application:
    """Build the Application with all handlers and error handling."""

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .concurrent_updates(True)
        .build()
    )

    # ---- Global error handler (MUST be registered) ----
    app.add_error_handler(error_handler)

    # ---- Pre-check filters ----
    app.add_handler(MessageHandler(
        filters.ALL & ~filters.COMMAND,
        maintenance_check,
        block=False,
    ))

    # ---- Anti-ad filter (runs before other handlers) ----
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        anti_ad_filter,
        block=False,
    ))

    # ---- Command handlers ----
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("ping",   cmd_ping))
    app.add_handler(CommandHandler("plan",   cmd_plan))
    app.add_handler(CommandHandler("rm",     cmd_rm))

    # Gate commands
    app.add_handler(CommandHandler("chk",  cmd_chk))
    app.add_handler(CommandHandler("pp",   cmd_pp))
    app.add_handler(CommandHandler("sh",   cmd_sh))
    app.add_handler(CommandHandler("pyu",  cmd_pyu))
    app.add_handler(CommandHandler("b3",   cmd_b3))
    app.add_handler(CommandHandler("au",   cmd_au))
    app.add_handler(CommandHandler("mss",  cmd_mss))
    app.add_handler(CommandHandler("mpp2", cmd_mpp2))

    # Bin lookup
    app.add_handler(CommandHandler("bin", get_bin_handler))

    # ---- Owner commands ----
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
    app.add_handler(CommandHandler("killbot",   cmd_killbot))
    app.add_handler(CommandHandler("onbot",     cmd_onbot))

    # Gate toggles
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

    # ---- Callback query handler (MUST be last) ----
    app.add_handler(CallbackQueryHandler(callback_handler))

    return app


def main():
    """Main entry point with PID lock file to prevent duplicate instances."""

    # ---- PID lock file to prevent multiple instances ----
    pid_file = "/tmp/batman_bot.pid"
    try:
        if os.path.exists(pid_file):
            with open(pid_file, "r") as f:
                old_pid = f.read().strip()
            if old_pid:
                try:
                    os.kill(int(old_pid), 0)
                    logger.error(
                        "Another bot instance is already running (PID: %s). "
                        "Kill it first with: kill %s",
                        old_pid, old_pid,
                    )
                    return
                except (ProcessLookupError, ValueError, OSError):
                    # Old process is dead, stale lock file
                    logger.info("Stale PID file found (PID: %s). Removing it.", old_pid)
                    os.remove(pid_file)
    except Exception as e:
        logger.warning("Error checking PID file: %s", e)

    # Write our PID
    try:
        with open(pid_file, "w") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        logger.warning("Could not write PID file: %s", e)

    # ---- Build application ----
    app = build_application()

    # ---- Handle SIGINT/SIGTERM for clean shutdown ----
    def signal_handler(sig, frame):
        logger.info("Received signal %s, shutting down...", sig)
        try:
            asyncio.get_event_loop().create_task(app.shutdown())
        except Exception:
            pass
        try:
            os.remove(pid_file)
        except Exception:
            pass

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # ---- Start polling with conflict-safe settings ----
    logger.info("=" * 50)
    logger.info("Batman Card Checker Bot Starting...")
    logger.info("Version: %s", VERSION)
    logger.info("=" * 50)

    try:
        app.run_polling(
            drop_pending_updates=True,
            close_loop=False,
            allowed_updates=Update.ALL_TYPES,
            poll_interval=1.0,
            timeout=10,
            bootstrap_retries=-1,   # infinite retries on startup
            read_timeout=5,
            write_timeout=5,
            connect_timeout=5,
            pool_timeout=3,
        )
    finally:
        # Clean up PID file on exit
        try:
            os.remove(pid_file)
        except Exception:
            pass
        logger.info("Bot process exited.")


if __name__ == "__main__":
    main()
