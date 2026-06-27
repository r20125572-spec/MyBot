import logging
import time
import string
import random
import asyncio
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
    BOT_TOKEN, OWNER_ID, VERSION, DEV_LINK, BOT_PHOTO, BOT_PHOTO_URL,
    GATE_URLS, GATE_SITES, API_TIMEOUT, get_bin_info, kb_result,
)
from bin import get_bin_handler

# ── Links ─────────────────────────────────────────────────────────────────────
CHANNEL_LINK   = "https://t.me/Batcardchk"
GROUP_LINK     = "https://t.me/batcardchkGroup"
SUPPORT_LINK   = "https://t.me/cardchkSupport"
BOT_LINK       = "https://t.me/Batmancardchk_bot"
WELCOME_PHOTO  = "https://example.com/batman.jpg"

# Channel/Group usernames for membership check (without @)
FORCE_CHANNELS = [
    ("Batcardchk",      CHANNEL_LINK),   # channel
    ("batcardchkGroup", GROUP_LINK),     # group
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
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

MAX_MSG = 4000


# ── Bold unicode font ────────────────────────────────────────────────────────

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


# ── Static text blocks ───────────────────────────────────────────────────────

CHECKER_STATUS_TEXT = (
    "𝗖𝗛𝗘𝗖𝗞𝗘𝗥 𝗦𝗧𝗔𝗧𝗨𝗦:\n"
    "━━━━━━━━━━━━━━━━━\n"
    "Aᴜᴛʜ Gᴀᴛᴇ   ➺ 2\n"
    "Mᴀss Gᴀᴛᴇ  ➺ 2\n"
    "Cʜᴀʀɢᴇ Gᴀᴛᴇ ➺ 4\n"
    "━━━━━━━━━━━━━━━━━\n"
    "Sᴇʟᴇᴄᴛ ᴀ Gᴀᴛᴇ ➺ Cᴀᴛᴇɢᴏʀʏ"
)

AUTH_MENU_TEXT = (
    "━━━━━━━━━━━━━━━━━\n"
    "Sᴇʟᴇᴄᴛ Aᴜᴛʜ Gᴀᴛᴇ ➺\n"
    "━━━━━━━━━━━━━━━━━"
)

STRIPE_AUTH_TEXT = (
    "━━━━━━━━━━━━━━━━━━\n"
    "Gᴀᴛᴇ    ➺ Sᴛʀɪᴘᴇ 0$\n"
    "Cᴏᴍᴍᴀɴᴅ ➺ /chk\n"
    "Sɪᴛᴇ   ➺ 16\n"
    "Hᴇᴀʟᴛʜ  ➺ 100%\n"
    "━━━━━━━━━━━━━━━━━━"
)

BRAINTREE_TEXT = (
    "━━━━━━━━━━━━━━━━━━\n"
    "Gᴀᴛᴇ    ➺ Bʀᴀɪɴᴛʀᴇᴇ 0$\n"
    "Cᴏᴍᴍᴀɴᴅ ➺ /b3\n"
    "Sɪᴛᴇ   ➺ 2\n"
    "Hᴇᴀʟᴛʜ  ➺ 100%\n"
    "━━━━━━━━━━━━━━━━━━"
)

CHARGE_MENU_TEXT = (
    "━━━━━━━━━━━━━━━━━\n"
    "Sᴇʟᴇᴄᴛ Cʜᴀʀɢᴇ Gᴀᴛᴇ ➺\n"
    "━━━━━━━━━━━━━━━━━"
)

MASS_MENU_TEXT = (
    "━━━━━━━━━━━━━━━━━\n"
    "Sᴇʟᴇᴄᴛ Mᴀss Gᴀᴛᴇ ➺\n"
    "━━━━━━━━━━━━━━━━━"
)

PLAN_TEXT = (
    "━━━━━━━━━━━━━━━━━━━━\n"
    "Bᴀᴛᴍᴀɴ Pʀᴇᴍɪᴜᴍ Pʟᴀɴs\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "Aᴄᴄᴇꜱꜱ ➺ Cᴏʀᴇ 🎀\n"
    "Sᴘᴀɴ   ➺ [7 Dᴀʏs]\n"
    "Cʀᴇᴅɪᴛs ➺ ∞ Uɴʟɪᴍɪᴛᴇᴅ\n"
    "Pʀɪᴄᴇ  ➺ 10$\n"
    "━━━━━━━━━━━━━━━━\n"
    "Aᴄᴄᴇꜱꜱ ➺ Eʟɪᴛᴇ ⭐️\n"
    "Sᴘᴀɴ   ➺ [15 Dᴀʏs]\n"
    "Cʀᴇᴅɪᴛs ➺ ∞ Uɴʟɪᴍɪᴛᴇᴅ\n"
    "Pʀɪᴄᴇ  ➺ 15$\n"
    "━━━━━━━━━━━━━━━━\n"
    "Aᴄᴄᴇꜱꜱ ➺ Rᴏᴏᴛ 👑\n"
    "Sᴘᴀɴ   ➺ [30 Dᴀʏs]\n"
    "Cʀᴇᴅɪᴛs ➺ ∞ Uɴʟɪᴍɪᴛᴇᴅ\n"
    "Pʀɪᴄᴇ  ➺ 30$\n"
    "━━━━━━━━━━━━━━━━━━━━"
)

PAYMENT_PENDING_TEXT = (
    "━━━━━━━━━━━━━━━━━━━━\n"
    "Pᴀʏᴍᴇɴᴛ Aᴅᴅʀᴇss\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "Pᴀʏᴍᴇɴᴛ ᴀᴅᴅʀᴇss ᴡɪʟʟ ʙᴇ ᴀᴅᴅᴇᴅ sʜᴏʀᴛʟʏ.\n\n"
    "Fᴏʀ ᴘᴀʏᴍᴇɴᴛ ᴄᴏɴᴛᴀᴄᴛ ᴛʜʀᴏᴜɢʜ sᴜᴘᴘᴏʀᴛ.\n\n"
    "━━━━━━━━━━━━━━━━━━━━"
)

FORCE_JOIN_TEXT = (
    "━━━━━━━━━━━━━━━━━━━━\n"
    "🦇 Wᴇʟᴄᴏᴍᴇ ᴛᴏ Bᴀᴛᴍᴀɴ Cᴀʀᴅ Cʜᴇᴄᴋᴇʀ!\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "Tᴏ ᴜsᴇ ᴛʜɪs ʙᴏᴛ ʏᴏᴜ ᴍᴜsᴛ ᴊᴏɪɴ ᴏᴜʀ\n"
    "ᴄʜᴀɴɴᴇʟ ᴀɴᴅ ɢʀᴏᴜᴘ ꜰɪʀsᴛ.\n\n"
    "👇 Cʟɪᴄᴋ ᴛʜᴇ ʙᴜᴛᴛᴏɴs ʙᴇʟᴏᴡ ᴛᴏ ᴊᴏɪɴ:\n\n"
    "━━━━━━━━━━━━━━━━━━━━"
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def get_styled_plan(raw_plan: str) -> str:
    p = raw_plan.upper()
    if p == "CORE":  return "Cᴏʀᴇ 🎀"
    if p == "ELITE": return "Eʟɪᴛᴇ ⭐️"
    if p == "ROOT":  return "Rᴏᴏᴛ 👑"
    return "Tʀɪᴀʟ"


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
        raw_plan = "TRIAL"; ud["plan"] = "TRIAL"; ud["expires"] = 0; expires = 0
    is_premium = raw_plan != "TRIAL"
    credits    = "∞ Uɴʟɪᴍɪᴛᴇᴅ" if is_premium else f"{ud.get('credits', 150)}/150"
    uname      = f"@{user.username}" if user.username else "None"
    lines = [
        f"Uᴛɪʟ    ➺ {uname}",
        f"Uᴛɪʟ ID ➺ <code>{user.id}</code>",
        f"Pʟᴀɴ    ➺ {get_styled_plan(raw_plan)}",
        f"Cʀᴇᴅɪᴛs ➺ {credits}",
    ]
    if is_premium and expires > now:
        exp_date    = datetime.fromtimestamp(expires).strftime("%Y-%m-%d %H:%M")
        remaining_d = int((expires - now) / 86400)
        remaining_h = int(((expires - now) % 86400) / 3600)
        lines.append(f"Exᴘɪʀᴇs  ➺ {exp_date}")
        lines.append(
            f"Rᴇᴍᴀɪɴɪɴɢ ➺ {remaining_d}d {remaining_h}h"
            if remaining_d > 0 else
            f"Rᴇᴍᴀɪɴɪɴɢ ➺ {remaining_h}h"
        )
    lines.append(f"Jᴏɪɴᴇᴅ  ➺ {ud.get('joined', datetime.now().strftime('%Y-%m-%d'))}")
    lines.append(f"Dᴇᴠ    ➺ <a href='{DEV_LINK}'>Batman</a>")
    return "\n".join(lines)


# ── Force Join check ──────────────────────────────────────────────────────────

async def is_member(bot, user_id: int, chat_username: str) -> bool:
    try:
        member = await bot.get_chat_member(f"@{chat_username}", user_id)
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
        [InlineKeyboardButton("📢 " + B("JOIN CHANNEL"), url=CHANNEL_LINK)],
        [InlineKeyboardButton("👥 " + B("JOIN GROUP"),   url=GROUP_LINK)],
        [InlineKeyboardButton("✅ " + B("VERIFY"),       callback_data="verify_join")],
    ])


async def send_force_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=WELCOME_PHOTO,
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
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 " + B("BACK"), callback_data=cb)]])


def kb_bin_result() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(B("Batcardchk"), url=BOT_LINK)]])


def kb_price() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(B("10$PAY"), callback_data="pay10"),
            InlineKeyboardButton(B("15$PAY"), callback_data="pay15"),
            InlineKeyboardButton(B("30$PAY"), callback_data="pay30"),
        ],
        [InlineKeyboardButton(B("SUPPORT"), url=SUPPORT_LINK)],
        [InlineKeyboardButton("🔙 " + B("BACK"), callback_data="bmain")],
    ])


def kb_payment() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("SUPPORT"), url=SUPPORT_LINK)],
        [InlineKeyboardButton("🔙 " + B("BACK"), callback_data="mprice")],
    ])


def kb_gate_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(B("AUTH"),   callback_data="mauth"),
            InlineKeyboardButton(B("CHARGE"), callback_data="mcharge"),
            InlineKeyboardButton(B("MASS"),   callback_data="mmass"),
        ],
        [InlineKeyboardButton("🔙 " + B("BACK"), callback_data="bmain")],
    ])


def kb_auth_gates() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(B("STRIPE"),    callback_data="iau"),
            InlineKeyboardButton(B("BRAINTREE"), callback_data="ib3"),
        ],
        [InlineKeyboardButton("🔙 " + B("BACK"), callback_data="mgates")],
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
        [InlineKeyboardButton("🔙 " + B("BACK"), callback_data="mgates")],
    ])


def kb_mass_gates() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("STRIPE MASS"), callback_data="imss")],
        [InlineKeyboardButton(B("PAYPAL MASS"), callback_data="impp2")],
        [InlineKeyboardButton("🔙 " + B("BACK"), callback_data="mgates")],
    ])


def gate_info_text(gate_name: str, cmd: str, cost: int) -> str:
    line = "━" * 20
    return (
        f"{line}\n{gate_name}\n{line}\n\n"
        f"Cᴏsᴛ    ➺ {cost} Cʀᴇᴅɪᴛ(s) ᴘᴇʀ ᴄʜᴇᴄᴋ\n\n"
        f"Usᴀɢᴇ:\n<code>/{cmd} cc|mm|yy|cvv</code>\n\n"
        f"Exᴀᴍᴘʟᴇ:\n<code>/{cmd} 4111111111111111|12|2026|123</code>\n\n"
        f"{line}"
    )


# ── Middleware ────────────────────────────────────────────────────────────────

async def maintenance_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    if context.bot_data.get("maintenance", False) and update.effective_user.id != OWNER_ID:
        try:
            if update.message:
                await update.message.reply_text("Bᴏᴛ ɪs ᴄᴜʀʀᴇɴᴛʟʏ ᴜɴᴅᴇʀ ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ.")
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
    if not await check_force_join(update.effective_user.id, context.bot):
        await send_force_join(update, context)
        return

    if not context.bot_data.get(f"{gate_key}_on", True):
        await update.message.reply_text("Gᴀᴛᴇ ɪs ᴄᴜʀʀᴇɴᴛʟʏ OFF.")
        return

    card = (
        context.args[0] if context.args
        else (update.message.reply_to_message.text.strip()
              if update.message.reply_to_message and update.message.reply_to_message.text
              else None)
    )
    if not card:
        await update.message.reply_text(
            f"Usᴀɢᴇ: <code>/{gate_key} cc|mm|yy|cvv</code>", parse_mode="HTML"
        )
        return

    ud         = get_user_data(update.effective_user.id, context)
    raw_plan   = ud.get("plan", "TRIAL").upper()
    is_premium = raw_plan != "TRIAL" and ud.get("expires", 0) > time.time()

    if not is_premium:
        credits = ud.get("credits", 150)
        if credits <= 0:
            await update.message.reply_text(
                "Yᴏᴜʀ ᴛʀɪᴀʟ ᴄʀᴇᴅɪᴛs ᴀʀᴇ ᴇᴍᴘᴛʏ. Pᴜʀᴄʜᴀsᴇ ᴀ ᴘʟᴀɴ ᴡɪᴛʜ /plan."
            )
            return

    # Validate URL before deducting credits
    api_url  = context.bot_data.get(f"gate_url_{gate_key}") or GATE_URLS.get(gate_key, "")
    site_url = GATE_SITES.get(gate_key, "example.com")
    bin_num  = card[:6]
    if not api_url:
        await update.message.reply_text(
            f"Gᴀᴛᴇ API URL ɴᴏᴛ sᴇᴛ. Oᴡɴᴇʀ: /seturl {gate_key} &lt;url&gt;",
            parse_mode="HTML"
        )
        return

    if not is_premium:
        ud["credits"] = credits - 1

    msg        = await update.message.reply_text("Pʀᴏᴄᴇssɪɴɢ...")
    start_time = time.time()
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
        status_ui    = "APPROVED ✅" if is_approved else "DECLINED ❌"
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
            f"[ STATUS ] ➺ {status_ui}\n"
            f"Cᴀʀᴅ ➺ <code>{card}</code>\n"
            f"Gᴀᴛᴇ ➺ {gate_name}\n"
            f"Rᴀᴡ  ➺ {raw_response}\n"
            f"Iɴᴏ➺ {bin_txt}\n"
            f"Usᴇʀ ➺ {first_name} ({plan_ui})\n"
            f"Bᴏᴛ  ➺ Batman\n"
            f"Tɪᴍᴇ ➺ {time_taken}s"
        )
        await msg.edit_text(text, parse_mode="HTML", reply_markup=kb_result(), disable_web_page_preview=True)
    except aiohttp.ServerTimeoutError:
        if not is_premium:
            ud["credits"] = ud.get("credits", 0) + 1
        await msg.edit_text("Tɪᴍᴇᴏᴜᴛ — Gᴀᴛᴇ ᴅɪᴅ ɴᴏᴛ ʀᴇsᴘᴏɴᴅ. Cʀᴇᴅɪᴛ ʀᴇꜰᴜɴᴅᴇᴅ.")
    except Exception as e:
        if not is_premium:
            ud["credits"] = ud.get("credits", 0) + 1
        logger.error(f"process_gate [{gate_key}]: {e}")
        await msg.edit_text(f"Eʀʀᴏʀ: <code>{str(e)[:120]}</code>", parse_mode="HTML")


async def cmd_chk(u, c):  await process_gate(u, c, "chk",  "Stripe Charge")
async def cmd_pp(u, c):   await process_gate(u, c, "pp",   "PayPal Charge")
async def cmd_sh(u, c):   await process_gate(u, c, "sh",   "Shopify Charge")
async def cmd_pyu(u, c):  await process_gate(u, c, "pyu",  "PayU Charge")
async def cmd_b3(u, c):   await process_gate(u, c, "b3",   "Braintree Auth")
async def cmd_au(u, c):   await process_gate(u, c, "au",   "Stripe Auth")
async def cmd_mss(u, c):  await process_gate(u, c, "mss",  "Stripe Mass")
async def cmd_mpp2(u, c): await process_gate(u, c, "mpp2", "PayPal Mass")


# ── Activation helper ─────────────────────────────────────────────────────────

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
    ud["name"] = name
    ud["plan"] = plan
    ud["expires"] = time.time() + (days * 86400)
    if username:
        ud["username"] = username
    exp_date      = datetime.fromtimestamp(ud["expires"]).strftime("%Y-%m-%d %H:%M")
    uname_display = f"@{username}" if username else "None"
    txt = (
        "Cᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴs! Yᴏᴜʀ ᴀᴄᴄᴇss ʜᴀs ʙᴇᴇɴ ᴀᴄᴛɪᴠᴀᴛᴇᴅ.\n"
        + "━" * 20 + "\n\n"
        + f"Usᴇʀ     ➺ {name}\n"
        + f"Usᴇʀɴᴀᴍᴇ ➺ {uname_display}\n"
        + f"Aᴄᴄᴇss   ➺ {get_styled_plan(plan)}\n"
        + f"Dᴜʀᴀᴛɪᴏɴ  ➺ {days} Dᴀʏs\n"
        + "Cʀᴇᴅɪᴛs   ➺ ∞ Uɴʟɪᴍɪᴛᴇᴅ\n"
        + f"Exᴘɪʀᴇs   ➺ {exp_date}\n"
        + f"Rᴇᴄᴇɪᴘᴛ  ➺ <code>{receipt}</code>\n\n"
        + "━" * 20 + "\n"
        + "Pʟᴇᴀsᴇ sᴀᴠᴇ ᴛʜɪs ʀᴇᴄᴇɪᴘᴛ ID."
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


# ── /start ────────────────────────────────────────────────────────────────────

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
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=WELCOME_PHOTO,
                caption=(
                    "🦇 Wᴇʟᴄᴏᴍᴇ ᴛᴏ Bᴀᴛᴍᴀɴ Cᴀʀᴅ Cʜᴇᴄᴋᴇʀ!\n\n"
                    "Jᴏɪɴ ᴏᴜʀ ᴄᴏᴍᴍᴜɴɪᴛʏ:\n"
                    f"📢 Cʜᴀɴɴᴇʟ: {CHANNEL_LINK}\n"
                    f"👥 Gʀᴏᴜᴘ: {GROUP_LINK}"
                ),
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


# ── /ping ─────────────────────────────────────────────────────────────────────

async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Pong! Bot is online.")


# ── /plan ─────────────────────────────────────────────────────────────────────

async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_force_join(update.effective_user.id, context.bot):
        await send_force_join(update, context)
        return
    await update.message.reply_text(
        PLAN_TEXT, parse_mode="HTML", reply_markup=kb_price(), disable_web_page_preview=True,
    )


# ── /rm ──────────────────────────────────────────────────────────────────────

async def cmd_rm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_force_join(update.effective_user.id, context.bot):
        await send_force_join(update, context)
        return
    if not context.args:
        await update.message.reply_text("Usᴀɢᴇ: /rm &lt;code&gt;", parse_mode="HTML")
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
            f"Rᴇᴅᴇᴇᴍᴇᴅ! Aᴅᴅᴇᴅ {codes[code]['value']} ᴄʀᴇᴅɪᴛs. Balance: {ud['credits']}/150"
        )
    elif code in keys and not keys[code]["used"]:
        keys[code]["used"] = True
        p, d = keys[code]["plan"], keys[code]["days"]
        ud["plan"] = p; ud["expires"] = time.time() + (d * 86400)
        receipt = await send_activation_msg(uid, p, d, context)
        await update.message.reply_text(
            f"Aᴄᴛɪᴠᴀᴛᴇᴅ {get_styled_plan(p)} ꜰᴏʀ {d} ᴅᴀʏs.\nRᴇᴄᴇɪᴘᴛ ➺ <code>{receipt}</code>",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text("Iɴᴠᴀʟɪᴅ ᴏʀ ᴀʟʀᴇᴀᴅʏ ᴜsᴇᴅ ᴄᴏᴅᴇ.")


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
            "Usᴀɢᴇ:\n/info &lt;user_id&gt;\n/info @username\nOʀ ʀᴇᴘʟʏ ᴛᴏ ᴀɴʏ ᴜsᴇʀ ᴍᴇssᴀɢᴇ.",
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
            raw_plan = "TRIAL"; udata["plan"] = "TRIAL"; udata["expires"] = 0; expires = 0
    else:
        raw_plan = "TRIAL"; expires = 0; joined = "Nᴇᴠᴇʀ ᴜsᴇᴅ ᴛʜᴇ ʙᴏᴛ"; credits_val = 150
    is_premium = raw_plan != "TRIAL" and expires > now
    credits    = "∞ Uɴʟɪᴍɪᴛᴇᴅ" if is_premium else f"{credits_val}/150"
    line       = "━" * 20
    txt = (
        f"{line}\n👤 Usᴇʀ Iɴꜰᴏ\n{line}\n\n"
        f"Nᴀᴍᴇ      ➺ {target_name}\n"
        f"Usᴇʀɴᴀᴍᴇ  ➺ {username_display}\n"
        f"Usᴇʀ ID  ➺ <code>{target_id}</code>\n"
        f"Pʟᴀɴ      ➺ {get_styled_plan(raw_plan)}\n"
        f"Cʀᴇᴅɪᴛs  ➺ {credits}\n"
        f"Jᴏɪɴᴇᴅ   ➺ {joined}\n"
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
            f"Pʟᴀɴ Eɴᴅ  ➺ {exp_str}\n"
            f"Rᴇᴍᴀɪɴɪɴɢ ➺ {remaining_str}\n"
            "Sᴛᴀᴛᴜs  ➺ ✅ Aᴄᴛɪᴠᴇ\n"
        )
    else:
        txt += (
            "Pʟᴀɴ Eɴᴅ  ➺ Nᴏ Aᴄᴛɪᴠᴇ Pʟᴀɴ\n"
            "Rᴇᴍᴀɪɴɪɴɢ ➺ N/A\n"
            "Sᴛᴀᴛᴜs  ➺ ❌ Iɴᴀᴄᴛɪᴠᴇ / Tʀɪᴀʟ\n"
        )
    txt += f"\n{line}"
    await update.message.reply_text(txt, parse_mode="HTML")


# ── /allcm ────────────────────────────────────────────────────────────────────

async def cmd_allcm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    line = "━" * 18
    await update.message.reply_text(
        f"BATMAN BOT — ALL COMMANDS\n{line}\nVersion: {VERSION}\n{line}\n\n"
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
        await update.message.reply_text("Usᴀɢᴇ: /gen &lt;credits&gt;", parse_mode="HTML")
        return
    try:
        amt  = int(context.args[0])
        code = gen_code()
        context.bot_data.setdefault("codes", {})[code] = {"type": "credit", "value": amt, "used": False}
        await update.message.reply_text(
            f"CODE GENERATED\n\nCode: <code>{code}</code>\nCredits: {amt}", parse_mode="HTML"
        )
    except ValueError:
        await update.message.reply_text("Iɴᴠᴀʟɪᴅ ᴀᴍᴏᴜɴᴛ.")


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

async def cmd_key10(u, c): await _gen_key(u, c, "CORE",  7)
async def cmd_key20(u, c): await _gen_key(u, c, "ELITE", 15)
async def cmd_key30(u, c): await _gen_key(u, c, "ROOT",  30)


# ── Grant helper ──────────────────────────────────────────────────────────────

async def _grant(uid: int, plan: str, days: int, update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud = get_user_data(uid, context)
    ud["plan"] = plan; ud["expires"] = time.time() + (days * 86400)
    receipt = await send_activation_msg(uid, plan, days, context)
    await update.message.reply_text(
        f"Gʀᴀɴᴛᴇᴅ {days} Dᴀʏs ({get_styled_plan(plan)}) ᴛᴏ <code>{uid}</code>\n"
        f"Rᴇᴄᴇɪᴘᴛ ➺ <code>{receipt}</code>",
        parse_mode="HTML",
    )


# ── /oneday / /threeday ───────────────────────────────────────────────────────

async def cmd_oneday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    code = "KEY-" + gen_code(12)
    context.bot_data.setdefault("keys", {})[code] = {"plan": "CORE", "days": 1, "used": False}
    await update.message.reply_text(
        f"1 DAY CODE\n\nCode: <code>{code}</code>\nRedeem: /rm {code}", parse_mode="HTML"
    )

async def cmd_threeday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    code = "KEY-" + gen_code(12)
    context.bot_data.setdefault("keys", {})[code] = {"plan": "CORE", "days": 3, "used": False}
    await update.message.reply_text(
        f"3 DAYS CODE\n\nCode: <code>{code}</code>\nRedeem: /rm {code}", parse_mode="HTML"
    )


# ── /sub / /resub ─────────────────────────────────────────────────────────────

async def cmd_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if len(context.args) < 2:
        await update.message.reply_text(
            "Usᴀɢᴇ: /sub &lt;user_id&gt; &lt;days&gt;", parse_mode="HTML"
        )
        return
    uid = await resolve_user(context.args[0], context)
    if not uid:
        await update.message.reply_text("Usᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ.")
        return
    try:
        days = int(context.args[1])
        plan = "ROOT" if days >= 30 else "ELITE" if days >= 15 else "CORE"
        await _grant(uid, plan, days, update, context)
    except ValueError:
        await update.message.reply_text("Iɴᴠᴀʟɪᴅ ᴅᴀʏs.")


async def cmd_resub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("Usᴀɢᴇ: /resub &lt;user_id&gt;", parse_mode="HTML")
        return
    uid = await resolve_user(context.args[0], context)
    if not uid:
        await update.message.reply_text("Usᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ.")
        return
    ud       = get_user_data(uid, context)
    raw_plan = ud.get("plan", "TRIAL").upper()
    expires  = ud.get("expires", 0)
    now      = time.time()
    if raw_plan != "TRIAL" and expires > now:
        remaining = int((expires - now) / 86400)
        await _grant(uid, raw_plan, remaining, update, context)
    else:
        await update.message.reply_text("Usᴇʀ ʜᴀs ɴᴏ ᴀᴄᴛɪᴠᴇ ᴘʟᴀɴ.")


# ── /allplans ─────────────────────────────────────────────────────────────────

async def cmd_allplans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    all_users = context.bot_data.get("user_data", {})
    now       = time.time()
    line      = "━" * 20
    premium_users = []
    for uid_str, ud in all_users.items():
        raw_plan = ud.get("plan", "TRIAL").upper()
        expires  = ud.get("expires", 0)
        if raw_plan != "TRIAL" and expires > now:
            premium_users.append((uid_str, ud, raw_plan, expires))
    if not premium_users:
        await update.message.reply_text(
            f"{line}\n👤 Lɪᴠᴇ Pʀᴇᴍɪᴜᴍ Usᴇʀs\n{line}\n\nNᴏ ᴀᴄᴛɪᴠᴇ ᴘʟᴀɴs ꜰᴏᴜɴᴅ.\n\n{line}",
            parse_mode="HTML",
        )
        return
    header  = f"{line}\n👤 Lɪᴠᴇ Pʀᴇᴍɪᴜᴍ Usᴇʀs\n{line}\nTᴏᴛᴀʟ ➺ {len(premium_users)} Usᴇʀs\n{line}\n\n"
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
            f"Nᴀᴍᴇ     ➺ {name}\n"
            f"Usᴇʀɴᴀᴍᴇ ➺ {uname_display}\n"
            f"Usᴇʀ ID ➺ <code>{uid_str}</code>\n"
            f"Pʟᴀɴ     ➺ {get_styled_plan(raw_plan)}\n"
            f"Jᴏɪɴᴇᴅ  ➺ {joined}\n"
            f"Exᴘɪʀᴇs  ➺ {exp_str}\n"
            f"Rᴇᴍᴀɪɴɪɴɢ ➺ {remaining_str}\n"
            f"Sᴛᴀᴛᴜs  ➺ ✅ Aᴄᴛɪᴠᴇ\n"
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
            "Usᴀɢᴇ: /seturl &lt;gate&gt; &lt;url&gt;\nGᴀᴛᴇs: chk, pp, sh, pyu, b3, au, mss, mpp2",
            parse_mode="HTML",
        )
        return
    gate = context.args[0].lower().strip()
    url  = context.args[1].strip()
    if gate not in GATE_NAMES:
        await update.message.reply_text(f"Iɴᴠᴀʟɪᴅ ɢᴀᴛᴇ: {gate}")
        return
    context.bot_data[f"gate_url_{gate}"] = url
    await update.message.reply_text(
        f"Gᴀᴛᴇ [{GATE_NAMES[gate]}] URL sᴇᴛ:\n<code>{url}</code>", parse_mode="HTML",
    )


async def cmd_geturl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    line = "━" * 18
    txt  = f"GATE URLs\n{line}\n\n"
    for gate, name in GATE_NAMES.items():
        url    = context.bot_data.get(f"gate_url_{gate}") or GATE_URLS.get(gate, "NOT SET")
        status = "ON" if context.bot_data.get(f"{gate}_on", True) else "OFF"
        txt   += f"{name} [{gate}]:\n  URL: <code>{url}</code>\n  Status: {status}\n\n"
    txt += line
    await update.message.reply_text(txt, parse_mode="HTML")


# ── /killbot / /onbot ─────────────────────────────────────────────────────────

async def cmd_killbot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    context.bot_data["maintenance"] = True
    await update.message.reply_text("Bᴏᴛ ᴛᴜʀɴᴇᴅ OFF — Mᴀɪɴᴛᴇɴᴀɴᴄᴇ ᴍᴏᴅᴇ.")


async def cmd_onbot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    context.bot_data["maintenance"] = False
    await update.message.reply_text("Bᴏᴛ ᴛᴜʀɴᴇᴅ ON — Bᴏᴛ ɪs ɴᴏᴡ ᴀᴠᴀɪʟᴀʙʟᴇ.")


# ── Gate toggles ──────────────────────────────────────────────────────────────

async def _gate_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE, gate: str, state: bool):
    if update.effective_user.id != OWNER_ID:
        return
    context.bot_data[f"{gate}_on"] = state
    await update.message.reply_text(f"Gᴀᴛᴇ [{GATE_NAMES[gate]}] ᴛᴜʀɴᴇᴅ {'ON' if state else 'OFF'}.")

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


# ── Callback handler ──────────────────────────────────────────────────────────

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

    # ── Verify join ───────────────────────────────────────────────────────────
    if data == "verify_join":
        joined = await check_force_join **…**

_This response is too long to display in full._
