import os
import signal
import logging
import time
import string
import random
import urllib.request
import urllib.error
import json
import asyncio
import tempfile
from typing import Optional
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ApplicationHandlerStop
from telegram.error import Conflict
import aiohttp

from config import (
    BOT_TOKEN, OWNER_ID, VERSION, DEV_LINK, BOT_PHOTO, BOT_PHOTO_URL,
    GATE_URLS, GATE_SITES, API_TIMEOUT, get_bin_info, kb_result
)

CHANNEL_USERNAME = "@Batcardchk"
GROUP_USERNAME = "@batcardchkGroup"
CHANNEL_LINK = "https://t.me/Batcardchk"
GROUP_LINK = "https://t.me/batcardchkGroup"
SUPPORT_LINK = "https://t.me/cardchkSupport"

WELCOME_IMAGE_URL = "https://example.com/batman.jpg"

GATE_COST = {"chk": 1, "pp": 1, "sh": 2, "pyu": 1, "b3": 1, "au": 1, "mss": 2, "mpp2": 2}
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

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

BLOCK_WORDS = (
    "http://", "https://", "www.", "t.me", ".com", ".net", ".org",
    ".io", ".me", ".xyz", ".tk", ".ml", ".cf", ".ga", ".ru", ".in",
    ".pw", "telegram.me", "joinchat", "://",
    "a_toolsx", "a-tools", "atoolsx", "a tools x", "a-tools x", "a_tools",
    "toolsx"
)

PLAN_TEXT = (
    "━━━━━━━━━━━━━━━━━━━━\n"
    "Bᴀᴛᴍᴀɴ Pʀᴇᴍɪᴜᴍ Pʟᴀɴs\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "Aᴄᴄᴇꜱꜱ ➺ Cᴏʀᴇ 🎀\n"
    "Sᴘᴀɴ ➺ [7 Dᴀʏꜱ]\n"
    "Cʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ\n"
    "Pʀɪᴄᴇ ➺ 10$\n"
    "━━━━━━━━━━━━━━━━\n"
    "Aᴄᴄᴇꜱꜱ ➺ Eʟɪᴛᴇ ⭐️\n"
    "Sᴘᴀɴ ➺ [15 Dᴀʏꜱ]\n"
    "Cʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ\n"
    "Pʀɪᴄᴇ ➺ 15$\n"
    "━━━━━━━━━━━━━━━━\n"
    "Aᴄᴄᴇꜱꜱ ➺ Rᴏᴏᴛ 👑\n"
    "Sᴘᴀɴ ➺ [30 Dᴀʏꜱ]\n"
    "Cʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ\n"
    "Pʀɪᴄᴇ ➺ 30$\n"
    "━━━━━━━━━━━━━━━━━━━━"
)

PAYMENT_PENDING_TEXT = (
    "━━━━━━━━━━━━━━━━━━━━\n"
    "Pᴀʏᴍᴇɴᴛ Aᴅᴅʀᴇꜱꜱ\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "Pᴀʏᴍᴇɴᴛ ᴀᴅᴅʀᴇꜱꜱ ᴡɪʟʟ ʙᴇ ᴀᴅᴅᴇᴅ ꜱᴏᴏɴ.\n\n"
    "Fᴏʀ ᴘᴀʏᴍᴇɴᴛ ᴀɴᴅ ᴀᴄᴛɪᴠᴀᴛɪᴏɴ, ᴄᴏɴᴛᴀᴄᴛ ꜱᴜᴘᴘᴏʀᴛ.\n\n"
    "━━━━━━━━━━━━━━━━━━━━"
)

CHECKER_STATUS_TEXT = (
    "Gᴀᴛᴇꜱ Sᴛᴀᴛᴜꜱ:\n"
    "Aᴜᴛʜ Gᴀᴛᴇꜱ ➺ 2\n"
    "Mᴀss Gᴀᴛᴇꜱ ➺ 2\n"
    "Cʜᴀʀɢᴇ Gᴀᴛᴇꜱ ➺ 4\n"
    "━━━━━━━━━━━━━━━━\n"
    "Sᴇʟᴇᴄᴛ ᴀ Gᴀᴛᴇ ➺ Cᴀᴛᴇɢᴏʀʏ"
)


def get_styled_plan(raw_plan: str) -> str:
    plan_upper = raw_plan.upper()
    if plan_upper == "CORE":
        return "Cᴏʀᴇ"
    elif plan_upper == "ELITE":
        return "Eʟɪᴛᴇ"
    elif plan_upper == "ROOT":
        return "Rᴏᴏᴛ"
    return "Tʀɪᴀʟ"


def get_user_data(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> dict:
    uid_str = str(user_id)
    if "user_data" not in context.bot_data:
        context.bot_data["user_data"] = {}
    if uid_str not in context.bot_data["user_data"]:
        context.bot_data["user_data"][uid_str] = {
            "name": "User",
            "joined": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "credits": 150,
            "plan": "TRIAL",
            "expires": 0,
        }
    return context.bot_data["user_data"][uid_str]


async def anti_ad_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.from_user:
        return
    if msg.from_user.id == OWNER_ID:
        return
    text = (msg.text or msg.caption or "").lower()
    if not text:
        return
    if any(w in text for w in BLOCK_WORDS):
        try:
            await msg.delete()
        except Exception:
            pass


async def maintenance_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    if context.bot_data.get("maintenance", False) and update.effective_user.id != OWNER_ID:
        try:
            if update.message:
                await update.message.reply_text("Bot is currently under maintenance.", parse_mode="HTML")
        except Exception:
            pass
        raise ApplicationHandlerStop


async def is_joined(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    async def check(chat_id):
        try:
            status = (await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)).status
            return status not in ("left", "kicked")
        except Exception:
            return False
    return await check(CHANNEL_USERNAME) and await check(GROUP_USERNAME)


def gen_code(length=10):
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


def gen_receipt():
    return f"BATCARD-{random.randint(100000, 999999)}-CHK"


def ui_profile(user, context: ContextTypes.DEFAULT_TYPE) -> str:
    u = user.username or "None"
    ud = get_user_data(user.id, context)
    raw_plan = ud.get("plan", "TRIAL").upper()
    expires = ud.get("expires", 0)
    now = time.time()
    if raw_plan != "TRIAL" and expires <= now:
        raw_plan = "TRIAL"
        ud["plan"] = "TRIAL"
        ud["expires"] = 0
    plan_str = get_styled_plan(raw_plan)
    is_premium = raw_plan != "TRIAL"
    credits = "∞" if is_premium else f"{ud.get('credits', 150)}/150"
    lines = [
        f"Uꜱᴇʀ ➺ {u}",
        f"Uꜱᴇʀ ID ➺ <code>{user.id}</code>",
        f"Pʟᴀɴ ➺ {plan_str}",
        f"Cʀᴇᴅɪᴛꜱ ➺ {credits}",
    ]
    if is_premium and expires > now:
        exp_date = datetime.fromtimestamp(expires).strftime("%Y-%m-%d %H:%M")
        remaining = int((expires - now) / 86400)
        remaining_hrs = int(((expires - now) % 86400) / 3600)
        lines.append(f"Exᴘɪʀᴇꜱ ➺ {exp_date}")
        if remaining > 0:
            lines.append(f"Rᴇᴍᴀɪɴɪɴɢ ➺ {remaining} Dᴀʏꜱ {remaining_hrs} Hʀꜱ")
        else:
            lines.append(f"Rᴇᴍᴀɪɴɪɴɢ ➺ {remaining_hrs} Hʀꜱ")
    lines.append(f"Jᴏɪɴᴇᴅ ➺ {ud.get('joined', datetime.now().strftime('%Y-%m-%d'))}")
    lines.append(f"Dᴇᴠ ➺ <a href='{DEV_LINK}'>Batman</a>")
    return "\n".join(lines)


async def send_activation_msg(user_id: int, plan: str, days: int, context: ContextTypes.DEFAULT_TYPE) -> str:
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
    styled_plan = get_styled_plan(plan)
    txt = (
        f"Cᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴꜱ! Yᴏᴜʀ ᴀᴄᴄᴇꜱꜱ ʜᴀꜱ ʙᴇᴇɴ ᴀᴄᴛɪᴠᴀᴛᴇᴅ.\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Uꜱᴇʀ ➺ {name}\n"
        f"Uꜱᴇʀɴᴀᴍᴇ ➺ @{username}\n"
        f"Aᴄᴄᴇꜱꜱ ➺ {styled_plan}\n"
        f"Dᴜʀᴀᴛɪᴏɴ ➺ {days} Dᴀʏꜱ\n"
        f"Cʀᴇᴅɪᴛꜱ Aᴅᴅᴇᴅ ➺ ∞\n"
        f"Exᴘɪʀᴇꜱ ➺ {exp_date}\n"
        f"Rᴇᴄᴇɪᴘᴛ ID ➺ <code>{receipt}</code>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Pʟᴇᴀꜱᴇ ꜱᴀᴠᴇ ᴛʜɪꜱ ʀᴇᴄᴇɪᴘᴛ ID."
    )
    try:
        await context.bot.send_message(chat_id=user_id, text=txt, parse_mode="HTML")
    except Exception:
        pass
    return receipt


# ── KEYBOARDS ──

def kb_main():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("CHECKER", callback_data="mgates"),
            InlineKeyboardButton("BUY NOW", callback_data="mprice"),
        ],
        [
            InlineKeyboardButton("UPDATES", url=CHANNEL_LINK),
            InlineKeyboardButton("GROUP", url=GROUP_LINK),
        ],
        [InlineKeyboardButton("SUPPORT", url=SUPPORT_LINK)],
    ])


def kb_back(cb):
    return InlineKeyboardMarkup([[InlineKeyboardButton("BACK", callback_data=cb)]])


def kb_force():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("JOIN GROUP", url=GROUP_LINK)],
        [InlineKeyboardButton("JOIN CHANNEL", url=CHANNEL_LINK)],
        [InlineKeyboardButton("VERIFY", callback_data="verify_join")],
    ])


def kb_price():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("10$PAY", callback_data="pay10"),
            InlineKeyboardButton("15$PAY", callback_data="pay15"),
            InlineKeyboardButton("30$PAY", callback_data="pay30"),
        ],
        [InlineKeyboardButton("BACK", callback_data="bmain")],
    ])


def kb_payment():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("SUPPORT", url=SUPPORT_LINK)],
        [InlineKeyboardButton("BACK", callback_data="mprice")],
    ])


def kb_gate_main():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("AUTH", callback_data="mauth"),
            InlineKeyboardButton("CHARGE", callback_data="mcharge"),
            InlineKeyboardButton("MASS", callback_data="mmass"),
        ],
        [InlineKeyboardButton("BACK", callback_data="bmain")],
    ])


def kb_auth_gates():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("STRIPE AUTH", callback_data="iau")],
        [InlineKeyboardButton("BRAINTREE AUTH", callback_data="ib3")],
        [InlineKeyboardButton("BACK", callback_data="mgates")],
    ])


def kb_charge_gates():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("STRIPE", callback_data="ichk"),
            InlineKeyboardButton("PAYPAL", callback_data="ipp"),
        ],
        [
            InlineKeyboardButton("SHOPIFY", callback_data="ish"),
            InlineKeyboardButton("PAYU", callback_data="ipyu"),
        ],
        [InlineKeyboardButton("BACK", callback_data="mgates")],
    ])


def kb_mass_gates():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("STRIPE MASS", callback_data="imss")],
        [InlineKeyboardButton("PAYPAL MASS", callback_data="impp2")],
        [InlineKeyboardButton("BACK", callback_data="mgates")],
    ])


def gate_info_text(gate_name: str, cmd: str, cost: int) -> str:
    return (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{gate_name}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Cᴏsᴛ ➺ {cost} Cʀᴇᴅɪᴛ(s) ᴘᴇʀ ᴄʜᴇᴄᴋ\n\n"
        f"Uꜱᴀɢᴇ:\n"
        f"<code>/{cmd} cc|mm|yy|cvv</code>\n\n"
        f"Exᴀᴍᴘʟᴇ:\n"
        f"<code>/{cmd} 4111111111111111|12|2026|123</code>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )


async def resolve_user(target: str, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    target = target.lstrip("@")
    if target.lstrip("-").isdigit():
        return int(target)
    try:
        return (await context.bot.get_chat(f"@{target}")).id
    except Exception:
        return None


async def fetch_bin(url: str) -> dict:
    try:
        req = urllib.request.Request(url, headers={"Accept-Version": "3", "User-Agent": "Mozilla/5.0"})
        loop = asyncio.get_running_loop()
        def do_req():
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read().decode("utf-8"))
        return await loop.run_in_executor(None, do_req)
    except Exception:
        return {}


async def _do_api_request(session: aiohttp.ClientSession, url: str, card: str, site: str) -> dict:
    async with session.get(url, params={"cc": card, "site": site}) as resp:
        try:
            data = await resp.json(content_type=None)
        except Exception:
            text = await resp.text()
            data = {"value": text}
        if not isinstance(data, dict):
            data = {"value": str(data)}
        return data


async def process_gate(update: Update, context: ContextTypes.DEFAULT_TYPE, gate_key: str, gate_name: str):
    if not context.bot_data.get(f"{gate_key}_on", True):
        await update.message.reply_text("Gate is currently OFF.", parse_mode="HTML")
        return
    card = None
    if context.args:
        card = context.args[0]
    elif update.message.reply_to_message and update.message.reply_to_message.text:
        card = update.message.reply_to_message.text.strip()
    if not card:
        await update.message.reply_text(
            f"Usage: Reply to a message with cards or send\n"
            f"<code>/{gate_key} cc|mm|yy|cvv</code>",
            parse_mode="HTML",
        )
        return
    ud = get_user_data(update.effective_user.id, context)
    raw_plan = ud.get("plan", "TRIAL").upper()
    is_premium = raw_plan != "TRIAL" and ud.get("expires", 0) > time.time()
    if not is_premium:
        credits = ud.get("credits", 150)
        if credits <= 0:
            await update.message.reply_text(
                "Your trial credits are empty.\n"
                "Purchase a plan with /plan to continue.",
                parse_mode="HTML",
            )
            return
        ud["credits"] = credits - 1
    bin_num = card[:6]
    msg = await update.message.reply_text("Processing...", parse_mode="HTML")
    start_time = time.time()
    api_url = context.bot_data.get(f"gate_url_{gate_key}") or GATE_URLS.get(gate_key, "")
    site_url = GATE_SITES.get(gate_key, "example.com")
    if not api_url:
        await msg.edit_text(
            f"Error: Gate API URL not set.\n"
            f"Ask owner to use: /seturl {gate_key} &lt;url&gt;",
            parse_mode="HTML"
        )
        return
    try:
        timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            api_task = _do_api_request(session, api_url, card, site_url)
            bin_task = get_bin_info(bin_num)
            results = await asyncio.gather(api_task, bin_task, return_exceptions=True)
        data = results[0] if not isinstance(results[0], Exception) else {}
        bin_data = results[1] if not isinstance(results[1], Exception) else {"error": True}
        if isinstance(results[0], Exception):
            raise results[0]
        raw_response = (
            data.get("value") or data.get("message") or data.get("category") or "ERROR"
        )
        raw_response = str(raw_response).strip()
        is_approved = any(w in raw_response.lower() for w in ["approved", "captured", "success"])
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
            f"[ STATUS ] ➺ {status_ui}\n"
            f"Card ➺ {card}\n"
            f"Gate ➺ {gate_name}\n"
            f"Raw ➺ {raw_response}\n"
            f"Info ➺ {bin_txt}\n"
            f"User ➺ {first_name} ({plan_ui})\n"
            f"Bot ➺ Batman\n"
            f"Time ➺ {time_taken}s"
        )
        await msg.edit_text(text, parse_mode="HTML", reply_markup=kb_result(), disable_web_page_preview=True)
    except aiohttp.ServerTimeoutError:
        await msg.edit_text("Timeout — Gate did not respond in time.", parse_mode="HTML")
    except Exception as e:
        logger.error(f"process_gate error [{gate_key}]: {e}")
        await msg.edit_text(f"Error: <code>{str(e)[:120]}</code>", parse_mode="HTML")


# ── GATE COMMANDS ──
async def cmd_chk(update, context):  await process_gate(update, context, "chk",  "Stripe Charge | 1 credit")
async def cmd_pp(update, context):   await process_gate(update, context, "pp",   "PayPal Charge | 1 credit")
async def cmd_sh(update, context):   await process_gate(update, context, "sh",   "Shopify Charge | 2 credits")
async def cmd_pyu(update, context):  await process_gate(update, context, "pyu",  "PayU Charge | 1 credit")
async def cmd_b3(update, context):   await process_gate(update, context, "b3",   "Braintree Auth | 1 credit")
async def cmd_au(update, context):   await process_gate(update, context, "au",   "Stripe Auth | 1 credit")
async def cmd_mss(update, context):  await process_gate(update, context, "mss",  "Stripe Mass | 2 credits")
async def cmd_mpp2(update, context): await process_gate(update, context, "mpp2", "PayPal Mass | 2 credits")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ud = get_user_data(user.id, context)
    if "joined" not in ud:
        ud["joined"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if "name" not in ud:
        ud["name"] = user.first_name or "User"

    if await is_joined(user.id, context):
        caption = ui_profile(user, context)
        try:
            await update.message.reply_photo(
                photo=WELCOME_IMAGE_URL,
                caption=caption,
                parse_mode="HTML",
                reply_markup=kb_main()
            )
        except Exception:
            await update.message.reply_text(
                text=caption,
                parse_mode="HTML",
                reply_markup=kb_main(),
                disable_web_page_preview=True
            )
    else:
        caption = (
            "BATMAN CARD CHECKER\n\n"
            "Access Required\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Join both channels to unlock the bot.\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        try:
            await update.message.reply_photo(
                photo=WELCOME_IMAGE_URL,
                caption=caption,
                parse_mode="HTML",
                reply_markup=kb_force()
            )
        except Exception:
            await update.message.reply_text(
                text=caption,
                parse_mode="HTML",
                reply_markup=kb_force()
            )


async def cmd_bin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /bin <BIN>\nExample: /bin 453201", parse_mode="HTML")
        return
    bin_num = "".join(filter(str.isdigit, context.args[0]))[:6]
    if len(bin_num) < 6:
        await update.message.reply_text("Invalid BIN!", parse_mode="HTML")
        return
    status = await update.message.reply_text(f"Looking up BIN: <code>{bin_num}</code>...", parse_mode="HTML")
    data = await fetch_bin(f"https://lookup.binlist.net/{bin_num}")
    if not data or "scheme" not in data:
        try:
            await status.edit_text("BIN not found.", parse_mode="HTML")
        except Exception:
            pass
        return
    c_data = data.get("country") or {}
    b_data = data.get("bank") or {}
    brand = (data.get("brand") or "N/A").upper()
    type_label = (data.get("type") or "N/A").upper()
    txt = (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"BIN LOOKUP RESULT\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"BIN ➺ <code>{bin_num}</code>\n"
        f"SCHEME ➺ {(data.get('scheme') or 'N/A').upper()}\n"
        f"TYPE ➺ {type_label}\n"
        f"BRAND ➺ {brand}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"COUNTRY INFO\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"NAME ➺ {c_data.get('emoji','')}{c_data.get('name','N/A')}\n"
        f"CODE ➺ {c_data.get('alpha2','N/A')}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"BANK INFO\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"BANK ➺ {b_data.get('name','N/A')}\n"
    )
    if b_data.get("url"):
        txt += f"URL ➺ {b_data.get('url')}\n"
    txt += "\n━━━━━━━━━━━━━━━━━━━━"
    try:
        await status.edit_text(txt, parse_mode="HTML", disable_web_page_preview=True)
    except Exception:
        pass


async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        PLAN_TEXT,
        parse_mode="HTML",
        reply_markup=kb_price(),
        disable_web_page_preview=True
    )


async def cmd_allcm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    await update.message.reply_text(
        f"BATMAN BOT - ALL COMMANDS\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Version: {VERSION}\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"USER COMMANDS\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"/start /plan /bin /rm\n"
        f"/chk /pp /sh /pyu /b3 /au /mss /mpp2\n\n"
        f"OWNER COMMANDS\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"/info /allcm /gen\n"
        f"/key10 /key20 /key30\n"
        f"/sub /resub /allplans\n"
        f"/oneday /threeday\n"
        f"/seturl /geturl\n"
        f"/onchk /offchk /onpp /offpp\n"
        f"/onsh /offsh /onpyu /offpyu\n"
        f"/onb3 /offb3 /onau /offau /onmss /offmss /onmpp2 /offmpp2\n"
        f"/killbot /onbot\n"
        f"━━━━━━━━━━━━━━━━━━",
        parse_mode="HTML"
    )


async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not update.message.reply_to_message and not context.args:
        await update.message.reply_text("Usage: /info <user_id>", parse_mode="HTML")
        return
    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
    else:
        target_id = await resolve_user(context.args[0], context)
    if not target_id:
        await update.message.reply_text("User not found.", parse_mode="HTML")
        return
    name, username, uid = "N/A", "None", target_id
    try:
        u = await context.bot.get_chat(target_id)
        name = u.first_name or "N/A"
        username = u.username or "None"
        uid = u.id
    except Exception:
        pass
    udata = get_user_data(uid, context)
    raw_plan = udata.get("plan", "TRIAL").upper()
    expires = udata.get("expires", 0)
    now = time.time()
    if raw_plan != "TRIAL" and expires <= now:
        raw_plan = "TRIAL"
    plan_str = get_styled_plan(raw_plan)
    credits = "∞" if raw_plan != "TRIAL" else f"{udata.get('credits', 150)}/150"
    txt = (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"USER INFO\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Name ➺ {name}\n"
        f"Username ➺ @{username}\n"
        f"User ID ➺ <code>{uid}</code>\n"
        f"Plan ➺ {plan_str}\n"
        f"Credits ➺ {credits}\n"
    )
    if raw_plan != "TRIAL" and expires > now:
        txt += (
            f"Expires ➺ {datetime.fromtimestamp(expires).strftime('%Y-%m-%d %H:%M')}\n"
            f"Remaining ➺ {int((expires - now) / 86400)} Days\n"
        )
    else:
        txt += "Status ➺ Inactive / Trial\n"
    txt += "━━━━━━━━━━━━━━━━━━━━"
    await update.message.reply_text(txt, parse_mode="HTML")


async def cmd_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /gen <credits>", parse_mode="HTML")
        return
    try:
        amt = int(context.args[0])
        code = gen_code()
        context.bot_data.setdefault("codes", {})[code] = {"type": "credit", "value": amt, "used": False}
        await update.message.reply_text(
            f"CODE GENERATED\n\nCode: <code>{code}</code>\nCredits: {amt}",
            parse_mode="HTML"
        )
    except ValueError:
        await update.message.reply_text("Invalid amount.", parse_mode="HTML")


async def cmd_gen_key(update: Update, context: ContextTypes.DEFAULT_TYPE, plan: str, days: int):
    if update.effective_user.id != OWNER_ID:
        return
    code = "KEY-" + gen_code(12)
    context.bot_data.setdefault("keys", {})[code] = {"plan": plan, "days": days, "used": False}
    await update.message.reply_text(
        f"KEY GENERATED\n\nKey: <code>{code}</code>\nPlan: {get_styled_plan(plan)}\nDays: {days}",
        parse_mode="HTML"
    )


async def cmd_key10(update, context): await cmd_gen_key(update, context, "core", 7)
async def cmd_key20(update, context): await cmd_gen_key(update, context, "elite", 15)
async def cmd_key30(update, context): await cmd_gen_key(update, context, "root", 30)


async def _grant_premium(uid: int, plan: str, days: int, update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud = get_user_data(uid, context)
    ud["plan"] = plan
    ud["expires"] = time.time() + (days * 86400)
    receipt = await send_activation_msg(uid, plan, days, context)
    await update.message.reply_text(
        f"Granted {days} Days ({get_styled_plan(plan)}) to <code>{uid}</code>\n"
        f"Receipt ➺ <code>{receipt}</code>",
        parse_mode="HTML"
    )


async def cmd_oneday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    code = "KEY-" + gen_code(12)
    context.bot_data.setdefault("keys", {})[code] = {"plan": "core", "days": 1, "used": False}
    await update.message.reply_text(
        f"1 DAY CODE\n\nCode: <code>{code}</code>\nUser redeems: /rm {code}",
        parse_mode="HTML"
    )


async def cmd_threeday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    code = "KEY-" + gen_code(12)
    context.bot_data.setdefault("keys", {})[code] = {"plan": "core", "days": 3, "used": False}
    await update.message.reply_text(
        f"3 DAYS CODE\n\nCode: <code>{code}</code>\nUser redeems: /rm {code}",
        parse_mode="HTML"
    )


async def cmd_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /sub <user_id> <days>", parse_mode="HTML")
        return
    uid = await resolve_user(context.args[0], context)
    if not uid:
        await update.message.reply_text("User not found.", parse_mode="HTML")
        return
    try:
        days = int(context.args[1])
        plan = "root" if days >= 30 else "elite" if days >= 15 else "core"
        await _grant_premium(uid, plan, days, update, context)
    except ValueError:
        await update.message.reply_text("Invalid days.", parse_mode="HTML")


async def cmd_resub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /resub <user_id>", parse_mode="HTML")
        return
    uid = await resolve_user(context.args[0], context)
    if not uid:
        await update.message.reply_text("User not found.", parse_mode="HTML")
        return
    ud = get_user_data(uid, context)
    ud["plan"] = "TRIAL"
    ud["expires"] = 0
    await update.message.reply_text(f"Removed premium from <code>{uid}</code>", parse_mode="HTML")


async def cmd_allplans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    users = context.bot_data.get("user_data", {})
    txt = "ACTIVE PLANS\n━━━━━━━━━━━━━━━━━━━━\n\n"
    found = False
    now = time.time()
    for uid, data in users.items():
        exp = data.get("expires", 0)
        if data.get("plan", "TRIAL") != "TRIAL" and exp > now:
            found = True
            remaining = int((exp - now) / 86400)
            txt += (
                f"ID: <code>{uid}</code>\n"
                f"Plan: {get_styled_plan(data.get('plan','TRIAL'))}\n"
                f"Remaining: {remaining} Days\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
            )
    if not found:
        txt += "No active plans."
    await update.message.reply_text(txt, parse_mode="HTML")


async def cmd_delcode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /delcode <code>", parse_mode="HTML")
        return
    code = context.args[0]
    codes = context.bot_data.get("codes", {})
    keys = context.bot_data.get("keys", {})
    if code in codes:
        del codes[code]
        await update.message.reply_text("Code deleted.", parse_mode="HTML")
    elif code in keys:
        del keys[code]
        await update.message.reply_text("Key deleted.", parse_mode="HTML")
    else:
        await update.message.reply_text("Not found.", parse_mode="HTML")


async def cmd_rm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /rm <code>", parse_mode="HTML")
        return
    code = context.args[0].upper()
    uid = update.effective_user.id
    ud = get_user_data(uid, context)
    codes = context.bot_data.get("codes", {})
    keys = context.bot_data.get("keys", {})
    if code in codes and not codes[code]["used"]:
        codes[code]["used"] = True
        ud["credits"] = ud.get("credits", 0) + codes[code]["value"]
        await update.message.reply_text(
            f"Redeemed! Added {codes[code]['value']} credits.\nBalance: {ud['credits']}/150",
            parse_mode="HTML"
        )
    elif code in keys and not keys[code]["used"]:
        keys[code]["used"] = True
        p, d = keys[code]["plan"], keys[code]["days"]
        ud["plan"] = p
        ud["expires"] = time.time() + (d * 86400)
        receipt = await send_activation_msg(uid, p, d, context)
        await update.message.reply_text(
            f"Activated {get_styled_plan(p)} for {d} days.\nReceipt ➺ <code>{receipt}</code>",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text("Invalid or already used code.", parse_mode="HTML")


# ── GATE TOGGLE FACTORY ──
def _make_gate_toggle(gate: str, label: str, state: bool):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != OWNER_ID:
            return
        context.bot_data[f"{gate}_on"] = state
        await update.message.reply_text(
            f"{label} → {'ON' if state else 'OFF'}",
            parse_mode="HTML"
        )
    return handler


cmd_onchk   = _make_gate_toggle("chk",  "STRIPE CHARGE",  True)
cmd_offchk  = _make_gate_toggle("chk",  "STRIPE CHARGE",  False)
cmd_onpp    = _make_gate_toggle("pp",   "PAYPAL CHARGE",  True)
cmd_offpp   = _make_gate_toggle("pp",   "PAYPAL CHARGE",  False)
cmd_onsh    = _make_gate_toggle("sh",   "SHOPIFY CHARGE", True)
cmd_offsh   = _make_gate_toggle("sh",   "SHOPIFY CHARGE", False)
cmd_onpyu   = _make_gate_toggle("pyu",  "PAYU CHARGE",    True)
cmd_offpyu  = _make_gate_toggle("pyu",  "PAYU CHARGE",    False)
cmd_onb3    = _make_gate_toggle("b3",   "BRAINTREE AUTH", True)
cmd_offb3   = _make_gate_toggle("b3",   "BRAINTREE AUTH", False)
cmd_onau    = _make_gate_toggle("au",   "STRIPE AUTH",    True)
cmd_offau   = _make_gate_toggle("au",   "STRIPE AUTH",    False)
cmd_onmss   = _make_gate_toggle("mss",  "STRIPE MASS",    True)
cmd_offmss  = _make_gate_toggle("mss",  "STRIPE MASS",    False)
cmd_onmpp2  = _make_gate_toggle("mpp2", "PAYPAL MASS",    True)
cmd_offmpp2 = _make_gate_toggle("mpp2", "PAYPAL MASS",    False)


async def cmd_seturl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /seturl &lt;gate&gt; &lt;url&gt;\n"
            "To remove: /seturl chk remove\n"
            "Gates: chk pp sh pyu b3 au mss mpp2",
            parse_mode="HTML"
        )
        return
    gate = context.args[0].lower()
    url = " ".join(context.args[1:])
    if gate not in GATE_NAMES:
        await update.message.reply_text(
            f"Unknown gate: {gate}\nValid gates: chk pp sh pyu b3 au mss mpp2",
            parse_mode="HTML"
        )
        return
    if url.lower() == "remove":
        context.bot_data.pop(f"gate_url_{gate}", None)
        await update.message.reply_text(f"Removed {GATE_NAMES[gate]} URL.", parse_mode="HTML")
        return
    context.bot_data[f"gate_url_{gate}"] = url
    await update.message.reply_text(
        f"{GATE_NAMES[gate]} URL set.\n<code>{url}</code>",
        parse_mode="HTML"
    )


async def cmd_geturl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    txt = "GATE API URLs\n━━━━━━━━━━━━━━━━━━━━\n\n"
    for gate, name in GATE_NAMES.items():
        override = context.bot_data.get(f"gate_url_{gate}", "")
        config_url = GATE_URLS.get(gate, "")
        active = override if override else config_url
        source = "Override" if override else "Config"
        status = "ON" if context.bot_data.get(f"{gate}_on", True) else "OFF"
        txt += f"{name} [{status}] [{source}]\n<code>{active or 'Not set'}</code>\n\n"
    txt += "━━━━━━━━━━━━━━━━━━━━"
    await update.message.reply_text(txt, parse_mode="HTML")


# ── CALLBACK HANDLER ──
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    d = q.data
    try:
        await q.answer()
    except Exception:
        pass

    if context.bot_data.get("maintenance", False) and q.from_user.id != OWNER_ID:
        await q.answer("Bot is under maintenance.", show_alert=True)
        return

    async def safe_edit(text: str, markup):
        if not q.message:
            return
        try:
            if q.message.photo:
                await context.bot.send_message(
                    chat_id=q.message.chat_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=markup,
                    disable_web_page_preview=True
                )
            else:
                await q.edit_message_text(
                    text=text,
                    parse_mode="HTML",
                    reply_markup=markup,
                    disable_web_page_preview=True
                )
        except Exception as e:
            logger.warning(f"safe_edit: {e}")
            try:
                await context.bot.send_message(
                    chat_id=q.message.chat_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=markup,
                    disable_web_page_preview=True
                )
            except Exception:
                pass

    if d == "verify_join":
        if await is_joined(q.from_user.id, context):
            await safe_edit(ui_profile(q.from_user, context), kb_main())
        else:
            await q.answer("Join Group & Channel first!", show_alert=True)

    elif d == "bmain":
        await safe_edit(ui_profile(q.from_user, context), kb_main())

    elif d == "mprice":
        await safe_edit(PLAN_TEXT, kb_price())

    elif d == "pay10":
        text = (
            "━━━━━━━━━━━━━━━━━━━━\n"
            "PAYMENT — 10$ (Cᴏʀᴇ | 7 Dᴀʏꜱ)\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            + PAYMENT_PENDING_TEXT
        )
        await safe_edit(text, kb_payment())

    elif d == "pay15":
        text = (
            "━━━━━━━━━━━━━━━━━━━━\n"
            "PAYMENT — 15$ (Eʟɪᴛᴇ | 15 Dᴀʏꜱ)\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            + PAYMENT_PENDING_TEXT
        )
        await safe_edit(text, kb_payment())

    elif d == "pay30":
        text = (
            "━━━━━━━━━━━━━━━━━━━━\n"
            "PAYMENT — 30$ (Rᴏᴏᴛ | 30 Dᴀʏꜱ)\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            + PAYMENT_PENDING_TEXT
        )
        await safe_edit(text, kb_payment())

    elif d == "mgates":
        await safe_edit(CHECKER_STATUS_TEXT, kb_gate_main())

    elif d == "mauth":
        await safe_edit(
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Sᴇʟᴇᴄᴛ ᴀɴ Aᴜᴛʜ Gᴀᴛᴇ\n"
            "━━━━━━━━━━━━━━━━━━━━",
            kb_auth_gates()
        )

    elif d == "mcharge":
        await safe_edit(
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Sᴇʟᴇᴄᴛ ᴀ Cʜᴀʀɢᴇ Gᴀᴛᴇ\n"
            "━━━━━━━━━━━━━━━━━━━━",
            kb_charge_gates()
        )

    elif d == "mmass":
        await safe_edit(
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Sᴇʟᴇᴄᴛ ᴀ Mᴀss Gᴀᴛᴇ\n"
            "━━━━━━━━━━━━━━━━━━━━",
            kb_mass_gates()
        )

    elif d == "iau":
        await safe_edit(gate_info_text("Stripe Auth",    "au",   1), kb_back("mauth"))
    elif d == "ib3":
        await safe_edit(gate_info_text("Braintree Auth", "b3",   1), kb_back("mauth"))
    elif d == "ichk":
        await safe_edit(gate_info_text("Stripe Charge",  "chk",  1), kb_back("mcharge"))
    elif d == "ipp":
        await safe_edit(gate_info_text("PayPal Charge",  "pp",   1), kb_back("mcharge"))
    elif d == "ish":
        await safe_edit(gate_info_text("Shopify Charge", "sh",   2), kb_back("mcharge"))
    elif d == "ipyu":
        await safe_edit(gate_info_text("PayU Charge",    "pyu",  1), kb_back("mcharge"))
    elif d == "imss":
        await safe_edit(gate_info_text("Stripe Mass",    "mss",  2), kb_back("mmass"))
    elif d == "impp2":
        await safe_edit(gate_info_text("PayPal Mass",    "mpp2", 2), kb_back("mmass"))


async def cmd_killbot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    context.bot_data["maintenance"] = True
    await update.message.reply_text("Maintenance Mode ON. Use /onbot to resume.", parse_mode="HTML")


async def cmd_onbot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    context.bot_data["maintenance"] = False
    await update.message.reply_text("Bot is back online!", parse_mode="HTML")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    if isinstance(context.error, Conflict):
        return
    logger.error(f"Unhandled exception: {context.error}", exc_info=context.error)


async def on_start(app):
    print("Batman Bot Initializing...")
    try:
        await app.bot.delete_webhook(drop_pending_updates=True)
        await asyncio.sleep(1)
    except Exception:
        pass


def main():
    app = Application.builder().token(BOT_TOKEN).post_init(on_start).build()
    app.add_error_handler(error_handler)
    app.add_handler(MessageHandler(filters.ALL, maintenance_check), group=-1)

    app.add_handler(CommandHandler("start",    cmd_start))
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
    app.add **...**

_This response is too long to display in full._
