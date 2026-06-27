import logging
import time
import string
import random
import asyncio
import os
from typing import Optional
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ApplicationHandlerStop,
)
from telegram.error import Conflict, BadRequest
import aiohttp

from config import (
    BOT_TOKEN, OWNER_ID, VERSION, DEV_LINK,
    BOT_PHOTO, BOT_PHOTO_URL,
    GATE_URLS, GATE_SITES, API_TIMEOUT,
    CHANNEL_LINK, GROUP_LINK, SUPPORT_LINK, BOT_LINK,
    get_bin_info, kb_result,
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

MAX_MSG = 4000

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
    "http://", "https://", "www.", ".com", ".net", ".org",
    ".io", ".xyz", ".tk", ".ml", ".cf", ".ga", ".ru", ".in",
    ".pw", "telegram.me", "joinchat", "://",
    "a_toolsx", "a-toolsx", "atoolsx", "a tools x",
    "toolsx", "t.me/a_toolsx", "@a_toolsx", "@atoolsx",
)


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


LINE  = "\u2501" * 18
LINE2 = "\u2501" * 20

CHECKER_STATUS_TEXT = (
    "{}\n"
    "A\u1d1c\u1d1b\u029c G\u1d00\u1d1b\u1d07   \u279a 2\n"
    "M\u1d00\u1d1c\u1d1c G\u1d00\u1d1b\u1d07  \u279a 2\n"
    "C\u029c\u1d00\u0280\u0262\u1d07 G\u1d00\u1d1b\u1d07 \u279a 4\n"
    "{}\n"
    "S\u1d07\u029f\u1d07\u1d04\u1d1b \u1d00 G\u1d00\u1d1b\u1d07 \u279a C\u1d00\u1d1b\u1d07\u0262\u1d0f\u0280y"
).format(LINE, LINE)

AUTH_MENU_TEXT   = "{}\nS\u1d07\u029f\u1d07\u1d04\u1d1b A\u1d1c\u1d1b\u029c G\u1d00\u1d1b\u1d07 \u279a\n{}".format(LINE, LINE)
CHARGE_MENU_TEXT = "{}\nS\u1d07\u029f\u1d07\u1d04\u1d1b C\u029c\u1d00\u0280\u0262\u1d07 G\u1d00\u1d1b\u1d07 \u279a\n{}".format(LINE, LINE)
MASS_MENU_TEXT   = "{}\nS\u1d07\u029f\u1d07\u1d04\u1d1b M\u1d00\u1d1c\u1d1c G\u1d00\u1d1b\u1d07 \u279a\n{}".format(LINE, LINE)

STRIPE_AUTH_TEXT = (
    "{}\nG\u1d00\u1d1b\u1d07    \u279a S\u1d1b\u0280\u026a\u1d18\u1d07 0$\n"
    "C\u1d0f\u1d0d\u1d0d\u1d00\u0274\u1d05 \u279a /chk\nS\u026a\u1d1b\u1d07   \u279a 16\n"
    "H\u1d07\u1d00\u029f\u1d1b\u029c  \u279a 100%\n{}"
).format(LINE, LINE)

BRAINTREE_TEXT = (
    "{}\nG\u1d00\u1d1b\u1d07    \u279a B\u0280\u1d00\u026a\u0274\u1d1b\u0280\u1d07\u1d07 0$\n"
    "C\u1d0f\u1d0d\u1d0d\u1d00\u0274\u1d05 \u279a /b3\nS\u026a\u1d1b\u1d07   \u279a 2\n"
    "H\u1d07\u1d00\u029f\u1d1b\u029c  \u279a 100%\n{}"
).format(LINE, LINE)

PLAN_TEXT = (
    "{}\n\U0001F987 Batman Premium Plans\n{}\n\n"
    "A\u1d04\u1d04\u1d07\u1d1c\u1d1c \u279a C\u1d0f\u0280\u1d07 \U0001F380\n"
    "S\u1d18\u1d00\u0274   \u279a [7 Days]\nC\u0280\u1d07\u1d05\u026a\u1d1b\u1d1c \u279a \u221e Unlimited\nP\u0280\u026a\u1d04\u1d07  \u279a 10$\n"
    "{}\n"
    "A\u1d04\u1d04\u1d07\u1d1c\u1d1c \u279a E\u029f\u026a\u1d1b\u1d07 \u2b50\ufe0f\n"
    "S\u1d18\u1d00\u0274   \u279a [15 Days]\nC\u0280\u1d07\u1d05\u026a\u1d1b\u1d1c \u279a \u221e Unlimited\nP\u0280\u026a\u1d04\u1d07  \u279a 15$\n"
    "{}\n"
    "A\u1d04\u1d04\u1d07\u1d1c\u1d1c \u279a R\u1d0f\u1d0f\u1d1b \U0001F451\n"
    "S\u1d18\u1d00\u0274   \u279a [30 Days]\nC\u0280\u1d07\u1d05\u026a\u1d1b\u1d1c \u279a \u221e Unlimited\nP\u0280\u026a\u1d04\u1d07  \u279a 30$\n"
    "{}"
).format(LINE2, LINE2, LINE, LINE, LINE2)

PAYMENT_PENDING_TEXT = (
    "{}\nPayment Address\n{}\n\nPayment address will be added shortly.\n\n"
    "For payment contact through support.\n\n{}"
).format(LINE2, LINE2, LINE2)

FORCE_JOIN_TEXT = (
    "{}\n\U0001F987 Welcome to Batman Card Checker!\n{}\n\n"
    "To use this bot you must join our\nchannel and group first.\n\n"
    "\U0001F447 Click the buttons below to join:\n\n{}"
).format(LINE2, LINE2, LINE2)


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
            "name": "User", "joined": datetime.now().strftime("%Y-%m-%d"),
            "credits": 150, "plan": "TRIAL", "expires": 0,
        }
    return context.bot_data["user_data"][uid]


def gen_code(length: int = 10) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))

def gen_receipt() -> str:
    return "BATCARD-{}-CHK".format(random.randint(100000, 999999))


def ui_profile(user, context: ContextTypes.DEFAULT_TYPE) -> str:
    ud = get_user_data(user.id, context)
    raw_plan = ud.get("plan", "TRIAL").upper()
    expires  = ud.get("expires", 0)
    now      = time.time()
    if raw_plan != "TRIAL" and expires <= now:
        raw_plan = "TRIAL"; ud["plan"] = "TRIAL"; ud["expires"] = 0; expires = 0
    is_premium = raw_plan != "TRIAL"
    credits    = "\u221e Unlimited" if is_premium else "{}/150".format(ud.get("credits", 150))
    uname      = "@{}".format(user.username) if user.username else user.first_name or "User"
    lines = [
        "{}\n\U0001F987 Batman Card Checker\n{}".format(LINE2, LINE2),
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
        lines.append("Remaining \u279a {}d {}h".format(remaining_d, remaining_h) if remaining_d > 0
                     else "Remaining \u279a {}h".format(remaining_h))
    lines.append("Joined  \u279a {}".format(ud.get("joined", datetime.now().strftime("%Y-%m-%d"))))
    lines.append("Dev    \u279a <a href='{}'>Batman</a>".format(DEV_LINK))
    lines.append("Version \u279a {}".format(VERSION))
    lines.append(LINE2)
    return "\n".join(lines)


def gate_info_text(gate_name: str, cmd: str, cost: int) -> str:
    return (
        "{}\n{}\n{}\n\nCost    \u279a {} Credit(s) per check\n\n"
        "Usage:\n<code>/{} cc|mm|yy|cvv</code>\n\n"
        "Example:\n<code>/{} 4111111111111111|12|2026|123</code>\n\n{}"
    ).format(LINE, gate_name, LINE, cost, cmd, cmd, LINE)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# KEYBOARDS — matches the photo exactly
# Row 1: CHECKER | BUY NOW
# Row 2: UPDATES ↗ | GROUP ↗
# Row 3: SUPPORT ↗
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def kb_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("CHECKER"), callback_data="mgates"),
         InlineKeyboardButton(B("BUY NOW"), callback_data="mprice")],
        [InlineKeyboardButton(B("UPDATES") + " \u2197", url=CHANNEL_LINK),
         InlineKeyboardButton(B("GROUP")   + " \u2197", url=GROUP_LINK)],
        [InlineKeyboardButton(B("SUPPORT") + " \u2197", url=SUPPORT_LINK)],
    ])

def kb_force_join() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("\U0001f4e2 " + B("JOIN CHANNEL") + " \u2197", url=CHANNEL_LINK)],
        [InlineKeyboardButton("\U0001f465 " + B("JOIN GROUP")   + " \u2197", url=GROUP_LINK)],
        [InlineKeyboardButton("\u2705 " + B("I JOINED - VERIFY"), callback_data="verify_join")],
    ])

def kb_back(cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("\U0001f519 " + B("BACK"), callback_data=cb)]])

def kb_price() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("10$ - CORE"),  callback_data="pay10"),
         InlineKeyboardButton(B("15$ - ELITE"), callback_data="pay15"),
         InlineKeyboardButton(B("30$ - ROOT"),  callback_data="pay30")],
        [InlineKeyboardButton(B("SUPPORT") + " \u2197", url=SUPPORT_LINK)],
        [InlineKeyboardButton("\U0001f519 " + B("BACK"), callback_data="bmain")],
    ])

def kb_payment() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("SUPPORT") + " \u2197", url=SUPPORT_LINK)],
        [InlineKeyboardButton("\U0001f519 " + B("BACK"), callback_data="mprice")],
    ])

def kb_gate_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("AUTH"),   callback_data="mauth"),
         InlineKeyboardButton(B("CHARGE"), callback_data="mcharge"),
         InlineKeyboardButton(B("MASS"),   callback_data="mmass")],
        [InlineKeyboardButton("\U0001f519 " + B("BACK"), callback_data="bmain")],
    ])

def kb_auth_gates() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("STRIPE"),    callback_data="iau"),
         InlineKeyboardButton(B("BRAINTREE"), callback_data="ib3")],
        [InlineKeyboardButton("\U0001f519 " + B("BACK"), callback_data="mgates")],
    ])

def kb_charge_gates() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("STRIPE"),  callback_data="ichk"),
         InlineKeyboardButton(B("PAYPAL"),  callback_data="ipp")],
        [InlineKeyboardButton(B("SHOPIFY"), callback_data="ish"),
         InlineKeyboardButton(B("PAYU"),    callback_data="ipyu")],
        [InlineKeyboardButton("\U0001f519 " + B("BACK"), callback_data="mgates")],
    ])

def kb_mass_gates() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("STRIPE MASS"), callback_data="imss")],
        [InlineKeyboardButton(B("PAYPAL MASS"), callback_data="impp2")],
        [InlineKeyboardButton("\U0001f519 " + B("BACK"), callback_data="mgates")],
    ])


async def send_photo_safe(bot, chat_id: int, caption: str, markup: InlineKeyboardMarkup):
    sent = False
    if os.path.exists(BOT_PHOTO):
        try:
            with open(BOT_PHOTO, "rb") as f:
                await bot.send_photo(chat_id=chat_id, photo=f, caption=caption,
                                     reply_markup=markup, parse_mode="HTML")
            sent = True
        except Exception:
            pass
    if not sent:
        try:
            await bot.send_photo(chat_id=chat_id, photo=BOT_PHOTO_URL, caption=caption,
                                 reply_markup=markup, parse_mode="HTML")
            sent = True
        except Exception:
            pass
    return sent


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

async def send_force_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    sent = await send_photo_safe(context.bot, chat_id, FORCE_JOIN_TEXT, kb_force_join())
    if not sent:
        await update.effective_message.reply_text(FORCE_JOIN_TEXT, reply_markup=kb_force_join(), parse_mode="HTML")


async def maintenance_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    if context.bot_data.get("maintenance", False) and update.effective_user.id != OWNER_ID:
        try:
            if update.message:
                await update.message.reply_text("\U0001f6a7 Bot is under maintenance. Please wait.")
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
        return data if isinstance(data, dict) else {"value": str(data)}


async def process_gate(update: Update, context: ContextTypes.DEFAULT_TYPE, gate_key: str, gate_name: str):
    user = update.effective_user
    if not await check_force_join(user.id, context.bot):
        await send_force_join(update, context); return
    if not context.bot_data.get("{}_on".format(gate_key), True):
        await update.message.reply_text("\u274c Gate [{}] is currently OFF.".format(gate_name)); return
    card = None
    if context.args:
        card = context.args[0].strip()
    elif update.message.reply_to_message and update.message.reply_to_message.text:
        card = update.message.reply_to_message.text.strip()
    if not card:
        await update.message.reply_text(
            "Usage: <code>/{} 4111111111111111|12|2026|123</code>".format(gate_key), parse_mode="HTML"); return
    ud         = get_user_data(user.id, context)
    raw_plan   = ud.get("plan", "TRIAL").upper()
    is_premium = raw_plan != "TRIAL" and ud.get("expires", 0) > time.time()
    if not is_premium:
        credits = ud.get("credits", 150)
        if credits <= 0:
            await update.message.reply_text("\u274c No credits left. Buy a plan: /plan"); return
        ud["credits"] = credits - 1
    api_url  = context.bot_data.get("gate_url_{}".format(gate_key)) or GATE_URLS.get(gate_key, "")
    site_url = GATE_SITES.get(gate_key, "example.com")
    bin_num  = card[:6]
    if not api_url:
        await update.message.reply_text(
            "Gate API not set. Use: /seturl {} &lt;url&gt;".format(gate_key), parse_mode="HTML"); return
    msg        = await update.message.reply_text("\u26a1 Checking...")
    start_time = time.time()
    try:
        timeout   = aiohttp.ClientTimeout(total=API_TIMEOUT)
        connector = aiohttp.TCPConnector(limit=30, ttl_dns_cache=300, force_close=False)
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            results = await asyncio.gather(
                _api_request(session, api_url, card, site_url),
                get_bin_info(bin_num), return_exceptions=True,
            )
        data     = results[0] if not isinstance(results[0], Exception) else {}
        bin_data = results[1] if not isinstance(results[1], Exception) else {"error": True}
        if isinstance(results[0], Exception):
            raise results[0]
        raw_response = str(data.get("value") or data.get("message") or data.get("category") or "ERROR").strip()
        is_approved  = any(w in raw_response.lower() for w in ["approved", "captured", "success", "charged"])
        status_ui    = "C\u1d00\u0280\u1d05 C\u029c\u1d00\u0280\u0262\u1d07\u1d05 \u2705" if is_approved else "C\u1d00\u0280\u1d05 D\u1d07\u1d04\u029f\u026a\u0274\u1d07\u1d05 \u274c"
        bin_txt = "N/A"
        if not bin_data.get("error"):
            s       = str(bin_data.get("scheme", "N/A")).upper()
            b       = bin_data.get("bank", "N/A")
            country = str(bin_data.get("country", "N/A")).upper()
            flag    = bin_data.get("country_emoji", "")
            bin_txt = "{} - {} - {} {}".format(s, b, flag, country)
        plan_ui    = get_styled_plan(raw_plan)
        uname      = user.username or user.first_name or "User"
        time_taken = "{:.2f}".format(time.time() - start_time)
        text = (
            "T\u1d0f\u1d1b\u1d00\u029f C\u1d00\u0280\u1d05\u1d1c \u279a 1/1\n"
            "T\u026a\u1d0d\u1d07 \u279a {}s\nU\u1d1c\u1d07\u0280 \u279a {}\n"
            "{}\n<code>{}</code>\n{}\n"
            "I\u0274\u1d0f \u279a {}\nG\u1d00\u1d1b\u1d07 \u279a {}\n"
            "R\u1d00\u1d21 \u279a {}\nP\u029f\u1d00\u0274 \u279a {}\n"
            "{}\n\u2705 C\u029c\u1d07\u1d04\u1d0b C\u1d0f\u1d0d\u1d18\u029f\u1d07\u1d1b\u1d07."
        ).format(time_taken, uname, LINE, card, status_ui, bin_txt, gate_name, raw_response, plan_ui, LINE)
        await msg.edit_text(text, parse_mode="HTML", reply_markup=kb_result(), disable_web_page_preview=True)
    except aiohttp.ServerTimeoutError:
        if not is_premium: ud["credits"] = ud.get("credits", 0) + 1
        await msg.edit_text("\u23f0 Timeout — gate did not respond. Credit refunded.")
    except Exception as e:
        if not is_premium: ud["credits"] = ud.get("credits", 0) + 1
        logger.error("Gate [{}] error: {}".format(gate_key, e))
        await msg.edit_text("\u274c Error: <code>{}</code>".format(str(e)[:150]), parse_mode="HTML")


async def cmd_chk(u, c):  await process_gate(u, c, "chk",  "Stripe Charge")
async def cmd_pp(u, c):   await process_gate(u, c, "pp",   "PayPal Charge")
async def cmd_sh(u, c):   await process_gate(u, c, "sh",   "Shopify Charge")
async def cmd_pyu(u, c):  await process_gate(u, c, "pyu",  "PayU Charge")
async def cmd_b3(u, c):   await process_gate(u, c, "b3",   "Braintree Auth")
async def cmd_au(u, c):   await process_gate(u, c, "au",   "Stripe Auth")
async def cmd_mss(u, c):  await process_gate(u, c, "mss",  "Stripe Mass")
async def cmd_mpp2(u, c): await process_gate(u, c, "mpp2", "PayPal Mass")


async def send_activation_msg(user_id: int, plan: str, days: int, context: ContextTypes.DEFAULT_TYPE) -> str:
    receipt = gen_receipt()
    name, username = "Unknown", None
    try:
        chat = await context.bot.get_chat(user_id)
        name = chat.first_name or "Unknown"; username = chat.username
    except Exception:
        pass
    ud = get_user_data(user_id, context)
    ud.update({"name": name, "plan": plan, "expires": time.time() + days * 86400})
    if username: ud["username"] = username
    exp_date      = datetime.fromtimestamp(ud["expires"]).strftime("%Y-%m-%d %H:%M")
    uname_display = "@{}".format(username) if username else "None"
    txt = (
        "\u2705 Access Activated!\n{}\nUser     \u279a {}\nUsername \u279a {}\n"
        "Access   \u279a {}\nDuration  \u279a {} Days\nCredits   \u279a \u221e Unlimited\n"
        "Expires   \u279a {}\nReceipt  \u279a <code>{}</code>\n{}\nSave your receipt ID."
    ).format(LINE, name, uname_display, get_styled_plan(plan), days, exp_date, receipt, LINE)
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


async def _grant(uid: int, plan: str, days: int, update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud = get_user_data(uid, context)
    ud["plan"] = plan; ud["expires"] = time.time() + days * 86400
    receipt = await send_activation_msg(uid, plan, days, context)
    await update.message.reply_text(
        "\u2705 Granted {} ({} days) to <code>{}</code>\nReceipt \u279a <code>{}</code>".format(
            get_styled_plan(plan), days, uid, receipt), parse_mode="HTML")

async def send_chunks(send_fn, text: str, **kwargs):
    if len(text) <= MAX_MSG:
        await send_fn(text, **kwargs); return
    chunk = ""
    for line in text.split("\n"):
        if len(chunk) + len(line) + 1 > MAX_MSG:
            await send_fn(chunk, **kwargs); chunk = line + "\n"
        else:
            chunk += line + "\n"
    if chunk.strip(): await send_fn(chunk, **kwargs)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ud   = get_user_data(user.id, context)
    ud.setdefault("joined", datetime.now().strftime("%Y-%m-%d"))
    ud.setdefault("name",   user.first_name or "User")
    if user.username: ud["username"] = user.username
    if not await check_force_join(user.id, context.bot):
        await send_force_join(update, context); return
    is_new = not ud.get("_welcomed", False)
    ud["_welcomed"] = True
    if is_new:
        welcome_caption = (
            "\U0001F987 <b>Welcome to Batman Card Checker!</b>\n\n"
            "The fastest card checker bot.\n\n"
            "\U0001F4E2 Channel: {}\n\U0001F465 Group: {}"
        ).format(CHANNEL_LINK, GROUP_LINK)
        await send_photo_safe(context.bot, update.effective_chat.id, welcome_caption, kb_main())
        return
    await update.message.reply_text(ui_profile(user, context), parse_mode="HTML",
                                    reply_markup=kb_main(), disable_web_page_preview=True)


async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = time.time()
    msg = await update.message.reply_text("\u26a1 Pinging...")
    await msg.edit_text("\u26a1 Pong! Speed: {}ms".format(int((time.time() - t) * 1000)))


async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_force_join(update.effective_user.id, context.bot):
        await send_force_join(update, context); return
    await update.message.reply_text(PLAN_TEXT, parse_mode="HTML", reply_markup=kb_price(),
                                    disable_web_page_preview=True)


async def cmd_rm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_force_join(update.effective_user.id, context.bot):
        await send_force_join(update, context); return
    if not context.args:
        await update.message.reply_text("Usage: /rm &lt;code&gt;", parse_mode="HTML"); return
    code  = context.args[0].upper()
    uid   = update.effective_user.id
    ud    = get_user_data(uid, context)
    codes = context.bot_data.get("codes", {})
    keys  = context.bot_data.get("keys",  {})
    if code in codes and not codes[code]["used"]:
        codes[code]["used"] = True; ud["credits"] = ud.get("credits", 0) + codes[code]["value"]
        await update.message.reply_text("\u2705 Redeemed! +{} credits. Balance: {}".format(codes[code]["value"], ud["credits"]))
    elif code in keys and not keys[code]["used"]:
        keys[code]["used"] = True; p, d = keys[code]["plan"], keys[code]["days"]
        receipt = await send_activation_msg(uid, p, d, context)
        await update.message.reply_text(
            "\u2705 Activated {} for {} days!\nReceipt \u279a <code>{}</code>".format(get_styled_plan(p), d, receipt), parse_mode="HTML")
    else:
        await update.message.reply_text("\u274c Invalid or already used code.")


async def cmd_bin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_force_join(update.effective_user.id, context.bot):
        await send_force_join(update, context); return
    bin_num = None
    if context.args: bin_num = context.args[0].strip()[:6]
    elif update.message.reply_to_message and update.message.reply_to_message.text:
        bin_num = update.message.reply_to_message.text.strip()[:6]
    if not bin_num or not bin_num.isdigit() or len(bin_num) < 6:
        await update.message.reply_text("Usage: <code>/bin 411111</code>", parse_mode="HTML"); return
    msg = await update.message.reply_text("\U0001f50d Looking up BIN...")
    try:
        bd = await get_bin_info(bin_num)
        if bd.get("error"):
            await msg.edit_text("\u274c BIN not found."); return
        txt = (
            "{}\n\U0001F4B3 BIN Lookup\n{}\n\nBIN     \u279a <code>{}</code>\n"
            "Scheme  \u279a {}\nType    \u279a {}\nBank    \u279a {}\nCountry \u279a {} {}\n{}"
        ).format(LINE, LINE, bin_num, str(bd.get("scheme","N/A")).upper(), str(bd.get("type","N/A")).upper(),
                 bd.get("bank","N/A"), bd.get("country_emoji",""), str(bd.get("country","N/A")).upper(), LINE)
        await msg.edit_text(txt, parse_mode="HTML")
    except Exception as e:
        await msg.edit_text("\u274c Error: <code>{}</code>".format(str(e)[:100]), parse_mode="HTML")


async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    target_id, target_name, target_username = None, "N/A", None
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        ru = update.message.reply_to_message.from_user
        target_id, target_name, target_username = ru.id, ru.first_name or "N/A", ru.username
    elif context.args:
        raw = context.args[0].strip().lstrip("@")
        if raw.lstrip("-").isdigit():
            target_id = int(raw)
        else:
            try:
                chat = await context.bot.get_chat("@{}".format(raw))
                target_id, target_name, target_username = chat.id, chat.first_name or "N/A", chat.username
            except Exception: pass
    if not target_id:
        await update.message.reply_text("Usage: /info &lt;user_id or @username&gt;\nor reply to a message.", parse_mode="HTML"); return
    if target_name == "N/A":
        try:
            chat = await context.bot.get_chat(target_id)
            target_name, target_username = chat.first_name or "N/A", chat.username
        except Exception: pass
    all_users = context.bot_data.get("user_data", {}); uid_str = str(target_id); now = time.time()
    udata = all_users.get(uid_str, {}); raw_plan = udata.get("plan", "TRIAL").upper(); expires = udata.get("expires", 0)
    if raw_plan != "TRIAL" and expires <= now: raw_plan, expires = "TRIAL", 0
    is_premium = raw_plan != "TRIAL" and expires > now
    credits    = "\u221e Unlimited" if is_premium else "{}/150".format(udata.get("credits", 150))
    uname_d    = "@{}".format(target_username) if target_username else "None"
    txt = (
        "{}\n\U0001F464 User Info\n{}\n\nName     \u279a {}\nUsername \u279a {}\n"
        "User ID  \u279a <code>{}</code>\nPlan     \u279a {}\nCredits  \u279a {}\nJoined   \u279a {}\n"
    ).format(LINE, LINE, target_name, uname_d, target_id, get_styled_plan(raw_plan), credits, udata.get("joined","N/A"))
    if is_premium:
        rem = expires - now; rstr = "{}d {}h".format(int(rem//86400), int((rem%86400)//3600))
        txt += "Expires  \u279a {}\nRemaining \u279a {}\nStatus  \u279a \u2705 Active\n".format(
            datetime.fromtimestamp(expires).strftime("%Y-%m-%d %H:%M"), rstr)
    else:
        txt += "Status  \u279a \u274c Trial / Inactive\n"
    txt += LINE
    await update.message.reply_text(txt, parse_mode="HTML")


async def cmd_allcm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    await update.message.reply_text(
        "{}\nBATMAN BOT — ALL COMMANDS\n{}\n\n"
        "USER:\n/start /plan /bin /rm /ping\n/chk /pp /sh /pyu /b3 /au /mss /mpp2\n\n"
        "OWNER:\n/info /allcm /gen\n/key10 /key20 /key30\n/sub /resub /allplans\n"
        "/oneday /th
