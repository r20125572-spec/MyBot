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

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION (NO EXTERNAL FILES NEEDED)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BOT_TOKEN = "8813507423:AAFWkdkk8Je4kB93AB5fu6qQ0-8eo-jlRKE"
OWNER_ID = 8283904645
VERSION = "2.0"
DEV_LINK = "https://t.me/Batman"
BOT_PHOTO_URL = "https://z-cdn-media.chatglm.cn/files/cd1a58d5-1a85-4246-8dac-dae333b02023.jpg"
CHANNEL_LINK = "https://t.me/Batcardchk"
GROUP_LINK = "https://t.me/batcardchkGroup"
SUPPORT_LINK = "https://t.me/cardchkSupport"
BOT_LINK = "https://t.me/Batmancardchk_bot"
API_TIMEOUT = 180

GATE_URLS = {
    "chk": "https://stripe-auth-test-production.up.railway.app/st0",
    "pp": "https://paypal0-1.onrender.com/pp1/cc={card}",
    "sh": "https://autosh.up.railway.app/shopii",
    "pyu": "https://stripe-auth-test-production.up.railway.app/st0",
    "b3": "https://stripe-auth-test-production.up.railway.app/st0",
    "au": "https://stripe-auth-test-production.up.railway.app/st0",
    "mss": "https://stripe-auth-test-production.up.railway.app/st0",
    "mpp2": "https://paypal0-1.onrender.com/pp1/cc={card}",
}

GATE_SITES = {
    "chk": "fashionspicex.com",
    "pp": "",
    "sh": "https://powerbuild.store",
    "pyu": "fashionspicex.com",
    "b3": "fashionspicex.com",
    "au": "fashionspicex.com",
    "mss": "fashionspicex.com",
    "mpp2": "",
}

FORCE_CHANNELS = [
    ("Batcardchk", CHANNEL_LINK),
    ("batcardchkGroup", GROUP_LINK),
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOGGING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
MAX_MSG = 4000

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PREMIUM BOLD UNICODE FONT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def B(text: str) -> str:
    bold_map = {
        'A': '𝗔', 'B': '𝗕', 'C': '𝗖', 'D': '𝗗', 'E': '𝗘', 'F': '𝗙', 'G': '𝗚', 'H': '𝗛',
        'I': '𝗜', 'J': '𝗝', 'K': '𝗞', 'L': '𝗟', 'M': '𝗠', 'N': '𝗡', 'O': '𝗢', 'P': '𝗣',
        'Q': '𝗤', 'R': '𝗥', 'S': '𝗦', 'T': '𝗧', 'U': '𝗨', 'V': '𝗩', 'W': '𝗪', 'X': '𝗫',
        'Y': '𝗬', 'Z': '𝗭', 'a': '𝗮', 'b': '𝗯', 'c': '𝗰', 'd': '𝗱', 'e': '𝗲', 'f': '𝗳',
        'g': '𝗴', 'h': '𝗵', 'i': '𝗶', 'j': '𝗷', 'k': '𝗸', 'l': '𝗹', 'm': '𝗺', 'n': '𝗻',
        'o': '𝗼', 'p': '𝗽', 'q': '𝗾', 'r': '𝗿', 's': '𝘀', 't': '𝘁', 'u': '𝘂', 'v': '𝘃',
        'w': '𝘄', 'x': '𝘅', 'y': '𝘆', 'z': '𝘇', '0': '𝟬', '1': '𝟭', '2': '𝟮', '3': '𝟯',
        '4': '𝟰', '5': '𝟱', '6': '𝟲', '7': '𝟳', '8': '𝟴', '9': '𝟵',
    }
    return "".join(bold_map.get(ch, ch) for ch in text)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BIN LOOKUP (INTEGRATED FOR SPEED)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def get_bin_info(bin_num: str) -> dict:
    if not bin_num.isdigit() or len(bin_num) < 6: return {"error": "Invalid"}
    url = f"https://bins.antipublic.cc/bins/{bin_num}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200: return {"error": "Not found"}
                return await resp.json()
    except Exception as e:
        return {"error": str(e)}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_styled_plan(raw_plan: str) -> str:
    p = raw_plan.upper()
    if p == "CORE": return "Cᴏʀᴇ 🎀"
    if p == "ELITE": return "Eʟɪᴛᴇ ⭐️"
    if p == "ROOT": return "Rᴏᴏᴛ 👑"
    return "Tʀɪᴀʟ"

def get_user_data(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> dict:
    uid = str(user_id)
    if "user_data" not in context.bot_data: context.bot_data["user_data"] = {}
    if uid not in context.bot_data["user_data"]:
        context.bot_data["user_data"][uid] = {"name": "User", "joined": datetime.now().strftime("%Y-%m-%d"), "credits": 150, "plan": "TRIAL", "expires": 0}
    return context.bot_data["user_data"][uid]

def gen_code(length: int = 10) -> str: return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))
def gen_receipt() -> str: return f"Batman{random.randint(100000, 999999)}-CHK"

def ui_profile(user, context: ContextTypes.DEFAULT_TYPE) -> str:
    ud = get_user_data(user.id, context)
    raw_plan = ud.get("plan", "TRIAL").upper()
    expires = ud.get("expires", 0)
    now = time.time()
    if raw_plan != "TRIAL" and expires <= now:
        raw_plan = "TRIAL"; ud["plan"] = "TRIAL"; ud["expires"] = 0; expires = 0
    is_premium = raw_plan != "TRIAL"
    credits = "∞ Unlimited" if is_premium else f"{ud.get('credits', 150)}/150"
    uname = f"@{user.username}" if user.username else user.first_name or "User"
    lines = [
        f"🦇 𝗕𝗮𝘁𝗺𝗮𝗻 𝗖𝗮𝗿𝗱 𝗖𝗵𝗲𝗰𝗸𝗲𝗿\n━━━━━━━━━━━━━━━━━",
        f"Uꜱᴇʀ    ➺ {uname}",
        f"Uꜱᴇʀ ID ➺ <code>{user.id}</code>",
        f"Aᴄᴄᴇꜱꜱ  ➺ {get_styled_plan(raw_plan)}",
        f"Cʀᴇᴅɪᴛꜱ ➺ {credits}",
    ]
    if is_premium and expires > now:
        exp_date = datetime.fromtimestamp(expires).strftime("%Y-%m-%d %H:%M")
        rem_d = int((expires - now) / 86400); rem_h = int(((expires - now) % 86400) / 3600)
        lines.append(f"Exᴘɪʀᴇꜱ ➺ {exp_date}")
        lines.append(f"Lᴇꜰᴛ    ➺ {rem_d}d {rem_h}h")
    lines.append(f"Jᴏɪɴᴇᴅ  ➺ {ud.get('joined', datetime.now().strftime('%Y-%m-%d'))}")
    lines.append(f"Dᴇᴠ     ➺ <a href='{DEV_LINK}'>Batman</a>")
    lines.append("━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)

def gate_info_text(gate_name: str, cmd: str, cost: int) -> str:
    return f"━━━━━━━━━━━━━━━━━\n{gate_name}\n━━━━━━━━━━━━━━━━━\n\nCᴏsᴛ    ➺ {cost} Credit(s) per check\n\nUꜱᴀɢᴇ:\n<code>/{cmd} cc|mm|yy|cvv</code>\n\nExᴀᴍᴘʟᴇ:\n<code>/{cmd} 4111111111111111|12|2026|123</code>\n\n━━━━━━━━━━━━━━━━━"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# KEYBOARDS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def kb_main(): return InlineKeyboardMarkup([[InlineKeyboardButton(B("CHECKER"), callback_data="mgates"), InlineKeyboardButton(B("BUY NOW"), callback_data="mprice")], [InlineKeyboardButton(B("UPDATES") + " ➺", url=CHANNEL_LINK), InlineKeyboardButton(B("GROUP") + " ➺", url=GROUP_LINK)], [InlineKeyboardButton(B("SUPPORT") + " ➺", url=SUPPORT_LINK)]])
def kb_back(cb): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 " + B("BACK"), callback_data=cb)]])
def kb_result(): return InlineKeyboardMarkup([[InlineKeyboardButton(B("Batcardchk"), url=BOT_LINK)]])
def kb_force_join(): return InlineKeyboardMarkup([[InlineKeyboardButton("📢 " + B("JOIN CHANNEL") + " ➺", url=CHANNEL_LINK)], [InlineKeyboardButton("👥 " + B("JOIN GROUP") + " ➺", url=GROUP_LINK)], [InlineKeyboardButton("✅ " + B("I JOINED - VERIFY"), callback_data="verify_join")]])
def kb_price(): return InlineKeyboardMarkup([[InlineKeyboardButton(B("10$ - CORE"), callback_data="pay10"), InlineKeyboardButton(B("15$ - ELITE"), callback_data="pay15"), InlineKeyboardButton(B("30$ - ROOT"), callback_data="pay30")], [InlineKeyboardButton(B("SUPPORT") + " ➺", url=SUPPORT_LINK)], [InlineKeyboardButton("🔙 " + B("BACK"), callback_data="bmain")]])
def kb_payment(): return InlineKeyboardMarkup([[InlineKeyboardButton(B("SUPPORT") + " ➺", url=SUPPORT_LINK)], [InlineKeyboardButton("🔙 " + B("BACK"), callback_data="mprice")]])
def kb_gate_main(): return InlineKeyboardMarkup([[InlineKeyboardButton(B("AUTH"), callback_data="mauth"), InlineKeyboardButton(B("CHARGE"), callback_data="mcharge"), InlineKeyboardButton(B("MASS"), callback_data="mmass")], [InlineKeyboardButton("🔙 " + B("BACK"), callback_data="bmain")]])
def kb_auth_gates(): return InlineKeyboardMarkup([[InlineKeyboardButton(B("STRIPE"), callback_data="iau"), InlineKeyboardButton(B("BRAINTREE"), callback_data="ib3")], [InlineKeyboardButton("🔙 " + B("BACK"), callback_data="mgates")]])
def kb_charge_gates(): return InlineKeyboardMarkup([[InlineKeyboardButton(B("STRIPE"), callback_data="ichk"), InlineKeyboardButton(B("PAYPAL"), callback_data="ipp")], [InlineKeyboardButton(B("SHOPIFY"), callback_data="ish"), InlineKeyboardButton(B("PAYU"), callback_data="ipyu")], [InlineKeyboardButton("🔙 " + B("BACK"), callback_data="mgates")]])
def kb_mass_gates(): return InlineKeyboardMarkup([[InlineKeyboardButton(B("STRIPE MASS"), callback_data="imss")], [InlineKeyboardButton(B("PAYPAL MASS"), callback_data="impp2")], [InlineKeyboardButton("🔙 " + B("BACK"), callback_data="mgates")]])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FORCE JOIN SYSTEM (SECURE)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_MEMBER_CACHE = {}
_CACHE_TTL = 300

async def is_member(bot, user_id: int, chat_username: str) -> bool:
    try:
        member = await bot.get_chat_member(chat_username, user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception:
        return False

async def check_force_join(user_id: int, bot) -> bool:
    if user_id == OWNER_ID: return True
    cached = _MEMBER_CACHE.get(user_id)
    if cached and time.time() < cached[1]: return cached[0]
    results = await asyncio.gather(*[is_member(bot, user_id, uname) for uname, _ in FORCE_CHANNELS], return_exceptions=True)
    ok = all(r is True for r in results)
    _MEMBER_CACHE[user_id] = (ok, time.time() + _CACHE_TTL)
    return ok

def _clear_member_cache(user_id: int): _MEMBER_CACHE.pop(user_id, None)

async def send_force_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    _clear_member_cache(update.effective_user.id)
    cap = "🦇 <b>Welcome to Gotham!</b>\n\nTo access the Batcomputer, you must join the League of Shadows.\n\n1️⃣ Click <b>JOIN CHANNEL</b>\n2️⃣ Click <b>JOIN GROUP</b>\n3️⃣ Click <b>✅ VERIFY ACCESS</b>"
    try:
        await context.bot.send_photo(chat_id=chat_id, photo=BOT_PHOTO_URL, caption=cap, parse_mode="HTML", reply_markup=kb_force_join())
    except Exception:
        await context.bot.send_message(chat_id=chat_id, text=cap, parse_mode="HTML", reply_markup=kb_force_join())

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GATE PROCESSING (FAST & SECURE)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _api_request(session: aiohttp.ClientSession, url: str, card: str, site: str) -> dict:
    if "{card}" in url:
        url = url.replace("{card}", card)
        async with session.get(url) as resp:
            try: data = await resp.json(content_type=None)
            except: data = {"value": await resp.text()}
    else:
        async with session.get(url, params={"cc": card, "site": site}) as resp:
            try: data = await resp.json(content_type=None)
            except: data = {"value": await resp.text()}
    return data if isinstance(data, dict) else {"value": str(data)}

async def process_gate(update: Update, context: ContextTypes.DEFAULT_TYPE, gate_key: str, gate_name: str):
    user = update.effective_user
    if not await check_force_join(user.id, context.bot):
        await send_force_join(update, context); return

    if not context.bot_data.get(f"{gate_key}_on", True):
        await update.message.reply_text(f"❌ Gate [{gate_name}] is currently OFF."); return

    ud = get_user_data(user.id, context)
    raw_plan = ud.get("plan", "TRIAL").upper()
    is_premium = raw_plan != "TRIAL" and ud.get("expires", 0) > time.time()

    # MASS GATE RESTRICTION
    if gate_key in ["mss", "mpp2"] and not is_premium:
        await update.message.reply_text("🚫 <b>Mass Gates are for Premium Users only.</b>\nPlease buy a plan using /plan to use mass checks."); return

    card = context.args[0].strip() if context.args else (update.message.reply_to_message.text.strip() if update.message.reply_to_message and update.message.reply_to_message.text else None)
    if not card:
        await update.message.reply_text(f"Usage: <code>/{gate_key} cc|mm|yy|cvv</code>", parse_mode="HTML"); return

    if not is_premium:
        credits = ud.get("credits", 150)
        if credits <= 0: await update.message.reply_text("❌ No credits left. Buy a plan: /plan"); return
        ud["credits"] = credits - 1

    api_url = context.bot_data.get(f"gate_url_{gate_key}") or GATE_URLS.get(gate_key, "")
    site_url = GATE_SITES.get(gate_key, "example.com")
    bin_num = card[:6]

    if not api_url: await update.message.reply_text(f"Gate API not set. Owner must use: /seturl {gate_key} <url>", parse_mode="HTML"); return

    msg = await update.message.reply_text("⚡ Scanning Gotham...")
    start_time = time.time()

    try:
        timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            results = await asyncio.gather(_api_request(session, api_url, card, site_url), get_bin_info(bin_num), return_exceptions=True)

        data = results[0] if not isinstance(results[0], Exception) else {}
        bin_data = results[1] if not isinstance(results[1], Exception) else {"error": True}
        if isinstance(results[0], Exception): raise results[0]

        raw_response = str(data.get("value") or data.get("message") or data.get("Response") or data.get("category") or "ERROR").strip()
        is_approved = any(w in raw_response.lower() for w in ["approved", "captured", "success", "charged", "true"])
        status_ui = "Cʜᴀʀɢᴇᴅ ✅" if is_approved else "Dᴇᴄʟɪɴᴇᴅ ❌"

        bin_txt = "N/A"
        if not bin_data.get("error"):
            s = str(bin_data.get("brand", bin_data.get("scheme", "N/A"))).upper()
            b = bin_data.get("bank", "N/A")
            country = str(bin_data.get("country_name", bin_data.get("country", "N/A"))).upper()
            flag = bin_data.get("country_flag", bin_data.get("country_emoji", ""))
            bin_txt = f"{s} - {b} - {flag} {country}"

        plan_ui = get_styled_plan(raw_plan)
        uname = user.username or user.first_name or "User"
        time_taken = f"{time.time() - start_time:.2f}"

        text = (
            f"🦇 𝐁𝐀𝐓𝐌𝐀𝐍 ➺ {status_ui}\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"💳 ➺ <code>{card}</code>\n"
            f"🏦 ➺ {bin_txt}\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"🌃 𝐆𝐚𝐭𝐞 ➺ {gate_name}\n"
            f"📜 𝐑𝐚𝐰  ➺ {raw_response}\n"
            f"⏱️ 𝐓𝐢𝐦𝐞 ➺ {time_taken}s\n"
            f"🦇 𝐔ꜱᴇʀ ➺ {uname} ({plan_ui})\n"
            f"━━━━━━━━━━━━━━━━━"
        )
        await msg.edit_text(text, parse_mode="HTML", reply_markup=kb_result(), disable_web_page_preview=True)

    except asyncio.TimeoutError:
        if not is_premium: ud["credits"] = ud.get("credits", 0) + 1
        await msg.edit_text("⏰ Timeout — gate did not respond. Credit refunded.")
    except Exception as e:
        if not is_premium: ud["credits"] = ud.get("credits", 0) + 1
        logger.error(f"Gate [{gate_key}] error: {e}")
        await msg.edit_text(f"❌ Error: <code>{str(e)[:150]}</code>", parse_mode="HTML")

async def cmd_chk(u, c): await process_gate(u, c, "chk", "Stripe Charge")
async def cmd_pp(u, c): await process_gate(u, c, "pp", "PayPal Charge")
async def cmd_sh(u, c): await process_gate(u, c, "sh", "Shopify Charge")
async def cmd_pyu(u, c): await process_gate(u, c, "pyu", "PayU Charge")
async def cmd_b3(u, c): await process_gate(u, c, "b3", "Braintree Auth")
async def cmd_au(u, c): await process_gate(u, c, "au", "Stripe Auth")
async def cmd_mss(u, c): await process_gate(u, c, "mss", "Stripe Mass")
async def cmd_mpp2(u, c): await process_gate(u, c, "mpp2", "PayPal Mass")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ACTIVATION MESSAGES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def send_activation_msg(user_id: int, plan: str, days: int, context: ContextTypes.DEFAULT_TYPE) -> str:
    receipt = gen_receipt()
    name, username = "Unknown", None
    try:
        chat = await context.bot.get_chat(user_id)
        name = chat.first_name or "Unknown"
        username = chat.username
    except Exception: pass
    ud = get_user_data(user_id, context)
    ud.update({"name": name, "plan": plan, "expires": time.time() + days * 86400})
    if username: ud["username"] = username

    txt = (
        "Cᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴꜱ! 🎉 Yᴏᴜʀ ᴀᴄᴄᴇꜱꜱ ʜᴀꜱ ʙᴇᴇɴ ᴀᴄᴛɪᴠᴀᴛᴇᴅ.\n"
        f"Uꜱᴇʀ ➺ {name}\n"
        f"Aᴄᴄᴇꜱꜱ ➺ {get_styled_plan(plan)}\n"
        f"Dᴜʀᴀᴛɪᴏɴ ➺ {days} Dᴀʏꜱ\n"
        "Cʀᴇᴅɪᴛꜱ Aᴅᴅᴇᴅ ➺ ∞\n"
        f"Rᴇᴄᴇɪᴘᴘᴛ ID ➺ {receipt}\n"
        "Pʟᴇᴀꜱᴇ ꜱᴀᴠᴇ ᴛʜɪꜱ ʀᴇᴄᴇɪᴘᴘᴛ ID."
    )
    try: await context.bot.send_message(chat_id=user_id, text=txt, parse_mode="HTML")
    except Exception: pass
    return receipt

async def resolve_user(target: str, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    target = target.strip().lstrip("@")
    if target.lstrip("-").isdigit(): return int(target)
    for attempt in (f"@{target}", target):
        try: return (await context.bot.get_chat(attempt)).id
        except Exception: continue
    return None

async def _grant(uid: int, plan: str, days: int, update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud = get_user_data(uid, context)
    ud["plan"] = plan; ud["expires"] = time.time() + days * 86400
    receipt = await send_activation_msg(uid, plan, days, context)
    await update.message.reply_text(f"✅ Granted {get_styled_plan(plan)} ({days} days) to <code>{uid}</code>\nReceipt ➺ <code>{receipt}</code>", parse_mode="HTML")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# USER COMMANDS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ud = get_user_data(user.id, context)
    ud.setdefault("joined", datetime.now().strftime("%Y-%m-%d"))
    ud.setdefault("name", user.first_name or "User")
    if user.username: ud["username"] = user.username

    if not await check_force_join(user.id, context.bot):
        await send_force_join(update, context); return

    await update.message.reply_text(ui_profile(user, context), parse_mode="HTML", reply_markup=kb_main(), disable_web_page_preview=True)

async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = time.time(); msg = await update.message.reply_text("⚡ Pinging...")
    await msg.edit_text(f"⚡ Pong! Speed: {int((time.time() - t) * 1000)}ms")

async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_force_join(update.effective_user.id, context.bot):
        await send_force_join(update, context); return
    txt = ("━━━━━━━━━━━━━━━━━\n🦇 Batman Premium Plans\n━━━━━━━━━━━━━━━━━\n\n"
           "Aᴄᴄᴇꜱꜱ ➺ Cᴏʀᴇ 🎀\nSᴜʙ   ➺ [7 Days]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Unlimited\nPʀɪᴄᴇ  ➺ 10$\n━━━━━━━━━━━━━━━━━\n"
           "Aᴄᴄᴇꜱꜱ ➺ Eʟɪᴛᴇ ⭐️\nSᴜʙ   ➺ [15 Days]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Unlimited\nPʀɪᴄᴇ  ➺ 15$\n━━━━━━━━━━━━━━━━━\n"
           "Aᴄᴄᴇꜱꜱ ➺ Rᴏᴏᴛ 👑\nSᴜʙ   ➺ [30 Days]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Unlimited\nPʀɪᴄᴇ  ➺ 30$\n━━━━━━━━━━━━━━━━━")
    await update.message.reply_text(txt, parse_mode="HTML", reply_markup=kb_price(), disable_web_page_preview=True)

async def cmd_rm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_force_join(update.effective_user.id, context.bot): await send_force_join(update, context); return
    if not context.args: await update.message.reply_text("Usage: /rm <code>", parse_mode="HTML"); return
    code = context.args[0].upper(); uid = update.effective_user.id; ud = get_user_data(uid, context)
    codes = context.bot_data.get("codes", {}); keys = context.bot_data.get("keys", {})
    if code in codes and not codes[code]["used"]:
        codes[code]["used"] = True; ud["credits"] = ud.get("credits", 0) + codes[code]["value"]
        await update.message.reply_text(f"✅ Redeemed! +{codes[code]['value']} credits. Balance: {ud['credits']}")
    elif code in keys and not keys[code]["used"]:
        keys[code]["used"] = True; p, d = keys[code]["plan"], keys[code]["days"]
        receipt = await send_activation_msg(uid, p, d, context)
        await update.message.reply_text(f"✅ Activated {get_styled_plan(p)} for {d} days!\nReceipt ➺ <code>{receipt}</code>", parse_mode="HTML")
    else: await update.message.reply_text("❌ Invalid or already used code.")

async def cmd_bin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_force_join(update.effective_user.id, context.bot): await send_force_join(update, context); return
    bin_num = context.args[0].strip()[:6] if context.args else None
    if not bin_num or not bin_num.isdigit() or len(bin_num) < 6: await update.message.reply_text("Usage: <code>/bin 411111</code>", parse_mode="HTML"); return
    msg = await update.message.reply_text("🔍 Looking up BIN...")
    try:
        bd = await get_bin_info(bin_num)
        if bd.get("error"): await msg.edit_text("❌ BIN not found."); return
        txt = (f"━━━━━━━━━━━━━━━━━\n💳 BIN Lookup\n━━━━━━━━━━━━━━━━━\n\n"
               f"BIN     ➺ <code>{bin_num}</code>\n"
               f"Scheme  ➺ {str(bd.get('brand', bd.get('scheme', 'N/A'))).upper()}\n"
               f"Type    ➺ {str(bd.get('type', 'N/A')).upper()}\n"
               f"Bank    ➺ {bd.get('bank', 'N/A')}\n"
               f"Country ➺ {bd.get('country_flag', bd.get('country_emoji', ''))} {str(bd.get('country_name', bd.get('country', 'N/A'))).upper()}\n"
               f"━━━━━━━━━━━━━━━━━")
        await msg.edit_text(txt, parse_mode="HTML")
    except Exception as e: await msg.edit_text(f"❌ Error: <code>{str(e)[:100]}</code>", parse_mode="HTML")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# OWNER COMMANDS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    target_id, target_name, target_username = None, "N/A", None

    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        ru = update.message.reply_to_message.from_user
        target_id, target_name, target_username = ru.id, ru.first_name or "N/A", ru.username
    elif context.args:
        raw = context.args[0].strip().lstrip("@")
        if raw.lstrip("-").isdigit(): target_id = int(raw)
        else:
            try:
                chat = await context.bot.get_chat(f"@{raw}")
                target_id, target_name, target_username = chat.id, chat.first_name or "N/A", chat.username
            except Exception: pass

    if not target_id: await update.message.reply_text("Usage: /info <code>@username or ID</code>\nor reply to a message.", parse_mode="HTML"); return
    if target_name == "N/A":
        try: chat = await context.bot.get_chat(target_id); target_name, target_username = chat.first_name or "N/A", chat.username
        except Exception: pass

    all_users = context.bot_data.get("user_data", {})
    uid_str = str(target_id); now = time.time()
    udata = all_users.get(uid_str, {})
    raw_plan = udata.get("plan", "TRIAL").upper(); expires = udata.get("expires", 0)
    if raw_plan != "TRIAL" and expires <= now: raw_plan, expires = "TRIAL", 0

    is_premium = raw_plan != "TRIAL" and expires > now
    credits = "∞ Unlimited" if is_premium else f"{udata.get('credits', 150)}/150"
    uname_d = f"@{target_username}" if target_username else "None"

    txt = (f"━━━━━━━━━━━━━━━━━\n👤 User Info\n━━━━━━━━━━━━━━━━━\n\n"
           f"Name     ➺ {target_name}\n"
           f"Username ➺ {uname_d}\n"
           f"User ID  ➺ <code>{target_id}</code>\n"
           f"Plan     ➺ {get_styled_plan(raw_plan)}\n"
           f"Credits  ➺ {credits}\n"
           f"Joined   ➺ {udata.get('joined', 'N/A')}\n")
    if is_premium:
        rem = expires - now; rstr = f"{int(rem // 86400)}d {int((rem % 86400) // 3600)}h"
        txt += f"Expires  ➺ {datetime.fromtimestamp(expires).strftime('%Y-%m-%d %H:%M')}\nRemaining ➺ {rstr}\nStatus  ➺ ✅ Active\n"
    else: txt += "Status  ➺ ❌ Trial / Inactive\n"
    txt += "━━━━━━━━━━━━━━━━━"
    await update.message.reply_text(txt, parse_mode="HTML")

async def cmd_allcm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    txt = ("━━━━━━━━━━━━━━━━━\n🦇 ALL COMMANDS\n━━━━━━━━━━━━━━━━━\n\n"
           "🟢 USER:\n/start ➺ Start bot\n/plan ➺ View plans\n/bin ➺ Lookup BIN\n/rm ➺ Redeem code\n/ping ➺ Check speed\n\n"
           "⚡ CHECKER:\n/chk ➺ Stripe Charge\n/pp ➺ PayPal Charge\n/sh ➺ Shopify Charge\n/pyu ➺ PayU Charge\n/b3 ➺ Braintree Auth\n/au ➺ Stripe Auth\n/mss ➺ Stripe Mass (Premium)\n/mpp2 ➺ PayPal Mass (Premium)\n\n"
           "👑 OWNER:\n/info ➺ User info (/info @user)\n/allcm ➺ This menu\n/gen ➺ Gen credits (/gen 100)\n/key10 /key20 /key30 ➺ Gen keys\n/sub ➺ Grant prem (/sub @user 30)\n/resub ➺ Remove prem\n/allplans ➺ List premium\n/seturl ➺ Set gate URL\n/geturl ➺ Get gate URLs\n/killbot /onbot ➺ Maintenance\n"
           "━━━━━━━━━━━━━━━━━")
    await update.message.reply_text(txt, parse_mode="HTML")

async def cmd_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args: await update.message.reply_text("Usage: /gen <credits>", parse_mode="HTML"); return
    try:
        amt = int(context.args[0]); code = gen_code()
        context.bot_data.setdefault("codes", {})[code] = {"type": "credit", "value": amt, "used": False}
        await update.message.reply_text(f"🔑 Code: <code>{code}</code>\nCredits: {amt}", parse_mode="HTML")
    except ValueError: await update.message.reply_text("Invalid amount.")

async def _gen_key(update, context, plan: str, days: int):
    if update.effective_user.id != OWNER_ID: return
    code = "KEY-" + gen_code(12)
    context.bot_data.setdefault("keys", {})[code] = {"plan": plan, "days": days, "used": False}
    await update.message.reply_text(f"🔑 Key: <code>{code}</code>\nPlan: {get_styled_plan(plan)} | Days: {days}", parse_mode="HTML")

async def cmd_key10(u, c): await _gen_key(u, c, "CORE", 7)
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
    if len(context.args) < 2: await update.message.reply_text("Usage: /sub <@username or ID> <days>", parse_mode="HTML"); return
    uid = await resolve_user(context.args[0], context)
    if not uid: await update.message.reply_text("❌ User not found."); return
    try:
        days = int(context.args[1]); plan = "ROOT" if days >= 30 else "ELITE" if days >= 15 else "CORE"
        await _grant(uid, plan, days, update, context)
    except ValueError: await update.message.reply_text("Invalid days number.")

async def cmd_resub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args: await update.message.reply_text("Usage: /resub <@username or ID>", parse_mode="HTML"); return
    uid = await resolve_user(context.args[0], context)
    if not uid: await update.message.reply_text("❌ User not found."); return
    uid_str = str(uid); all_data = context.bot_data.get("user_data", {})
    if uid_str not in all_data: await update.message.reply_text("User has no data."); return
    ud = all_data[uid_str]; ud["plan"] = "TRIAL"; ud["expires"] = 0; ud["credits"] = 0
    try: await context.bot.send_message(chat_id=uid, text="❌ Your premium was removed by the owner. Account reset to Trial.")
    except Exception: pass
    await update.message.reply_text(f"✅ Premium Removed for <code>{uid}</code>.")

async def cmd_allplans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    all_users = context.bot_data.get("user_data", {}); now = time.time()
    premium_users = [(uid, ud) for uid, ud in all_users.items() if ud.get("plan", "TRIAL").upper() != "TRIAL" and ud.get("expires", 0) > now]
    if not premium_users: await update.message.reply_text("No active premium users."); return
    txt = f"━━━━━━━━━━━━━━━━━\n🦇 Live Premium — {len(premium_users)} Users\n━━━━━━━━━━━━━━━━━\n\n"
    for uid_str, ud in premium_users:
        rem = ud["expires"] - now; rstr = f"{int(rem // 86400)}d {int((rem % 86400) // 3600)}h"
        txt += f"Name ➺ {ud.get('name', 'Unknown')}\nID ➺ <code>{uid_str}</code>\nPlan ➺ {get_styled_plan(ud['plan'])}\nLeft ➺ {rstr}\n━━━━━━━━━━━━━━━━━\n"
    if len(txt) > MAX_MSG:
        for i in range(0, len(txt), MAX_MSG): await update.message.reply_text(txt[i:i+MAX_MSG], parse_mode="HTML")
    else: await update.message.reply_text(txt, parse_mode="HTML")

async def cmd_seturl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if len(context.args) < 2: await update.message.reply_text("Usage: /seturl <gate> <url>", parse_mode="HTML"); return
    gate = context.args[0].lower().strip(); url = context.args[1].strip()
    if gate not in GATE_URLS: await update.message.reply_text("Invalid gate."); return
    context.bot_data[f"gate_url_{gate}"] = url
    await update.message.reply_text(f"✅ Gate [{gate}] URL set:\n<code>{url}</code>", parse_mode="HTML")

async def cmd_geturl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    txt = "━━━━━━━━━━━━━━━━━\nGATE URLs\n━━━━━━━━━━━━━━━━━\n\n"
    for gate, name in GATE_URLS.items():
        url = context.bot_data.get(f"gate_url_{gate}") or GATE_URLS.get(gate, "NOT SET")
        status = "ON" if context.bot_data.get(f"{gate}_on", True) else "OFF"
        txt += f"{name} [{gate}]:\n<code>{url}</code>\nStatus: {status}\n\n"
    await update.message.reply_text(txt + "━━━━━━━━━━━━━━━━━", parse_mode="HTML")

async def cmd_killbot(update, context):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data["maintenance"] = True; await update.message.reply_text("🚧 Bot is now in maintenance mode.")

async def cmd_onbot(update, context):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data["maintenance"] = False; await update.message.reply_text("✅ Bot is back online.")

async def _gate_toggle(update, context, gate: str, state: bool):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data[f"{gate}_on"] = state
    await update.message.reply_text(f"Gate [{gate}] turned {'ON ✅' if state else 'OFF ❌'}.")

async def cmd_onchk(u, c): await _gate_toggle(u, c, "chk", True)
async def cmd_offchk(u, c): await _gate_toggle(u, c, "chk", False)
async def cmd_onpp(u, c): await _gate_toggle(u, c, "pp", True)
async def cmd_offpp(u, c): await _gate_toggle(u, c, "pp", False)
async def cmd_onsh(u, c): await _gate_toggle(u, c, "sh", True)
async def cmd_offsh(u, c): await _gate_toggle(u, c, "sh", False)
async def cmd_onpyu(u, c): await _gate_toggle(u, c, "pyu", True)
async def cmd_offpyu(u, c): await _gate_toggle(u, c, "pyu", False)
async def cmd_onb3(u, c): await _gate_toggle(u, c, "b3", True)
async def cmd_offb3(u, c): await _gate_toggle(u, c, "b3", False)
async def cmd_onau(u, c): await _gate_toggle(u, c, "au", True)
async def cmd_offau(u, c): await _gate_toggle(u, c, "au", False)
async def cmd_onmss(u, c): await _gate_toggle(u, c, "mss", True)
async def cmd_offmss(u, c): await _gate_toggle(u, c, "mss", False)
async def cmd_onmpp2(u, c): await _gate_toggle(u, c, "mpp2", True)
async def cmd_offmpp2(u, c): await _gate_toggle(u, c, "mpp2", False)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CALLBACK HANDLER (UI MENUS)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; data = query.data; user = query.from_user
    try: await query.answer()
    except Exception: pass

    if data == "verify_join":
        _clear_member_cache(user.id)
        if await check_force_join(user.id, context.bot):
            try: await query.message.delete()
            except Exception: pass
            ud = get_user_data(user.id, context)
            ud.setdefault("joined", datetime.now().strftime("%Y-%m-%d")); ud.setdefault("name", user.first_name or "User")
            if user.username: ud["username"] = user.username
            await context.bot.send_message(chat_id=query.message.chat_id, text=ui_profile(user, context), parse_mode="HTML", reply_markup=kb_main(), disable_web_page_preview=True)
        else: await query.answer("❌ Not joined yet! Join BOTH channel and group, then press VERIFY.", show_alert=True)
        return

    if not await check_force_join(user.id, context.bot):
        try: await query.answer("❌ Join our channel & group first!", show_alert=True)
        except Exception: pass
        return

    async def edit(text: str, markup: InlineKeyboardMarkup):
        try: await query.message.edit_text(text=text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
        except BadRequest as e:
            if "message is not modified" in str(e).lower(): return
            try: await query.message.edit_caption(caption=text, parse_mode="HTML", reply_markup=markup)
            except Exception: await context.bot.send_message(chat_id=query.message.chat_id, text=text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)

    if data == "bmain": await edit(ui_profile(user, context), kb_main())
    elif data == "mgates": await edit("🦇 𝗦𝗘𝗟𝗘𝗖𝗧 𝗔 𝗖𝗔𝗧𝗘𝗚𝗢𝗥𝗬 🦇\n━━━━━━━━━━━━━━━━━\n⚡ 𝗔𝘂𝘁𝗵 𝗚𝗮𝘁𝗲𝘀 ➺ 2\n💰 𝗖𝗵𝗮𝗿𝗴𝗲 𝗚𝗮𝘁𝗲𝘀 ➺ 4\n🚀 𝗠𝗮𝘀𝘀 𝗚𝗮𝘁𝗲𝘀 ➺ 2 (Premium)\n━━━━━━━━━━━━━━━━━", kb_gate_main())
    elif data == "mprice": await edit("━━━━━━━━━━━━━━━━━\n🦇 Batman Premium Plans\n━━━━━━━━━━━━━━━━━\n\nAᴄᴄᴇꜱꜱ ➺ Cᴏʀᴇ 🎀\nSᴜʙ   ➺ [7 Days]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Unlimited\nPʀɪᴄᴇ  ➺ 10$\n━━━━━━━━━━━━━━━━━\nAᴄᴄᴇꜱꜱ ➺ Eʟɪᴛᴇ ⭐️\nSᴜʙ   ➺ [15 Days]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Unlimited\nPʀɪᴄᴇ  ➺ 15$\n━━━━━━━━━━━━━━━━━\nAᴄᴄᴇꜱꜱ ➺ Rᴏᴏᴛ 👑\nSᴜʙ   ➺ [30 Days]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Unlimited\nPʀɪᴄᴇ  ➺ 30$\n━━━━━━━━━━━━━━━━━", kb_price())
    elif data == "mauth": await edit("━━━━━━━━━━━━━━━━━\n⚡ Auth Gates\n━━━━━━━━━━━━━━━━━", kb_auth_gates())
    elif data == "mcharge": await edit("━━━━━━━━━━━━━━━━━\n💰 Charge Gates\n━━━━━━━━━━━━━━━━━", kb_charge_gates())
    elif data == "mmass": await edit("━━━━━━━━━━━━━━━━━\n🚀 Mass Gates (Premium)\n━━━━━━━━━━━━━━━━━", kb_mass_gates())
    elif data == "iau": await edit(gate_info_text("STRIPE AUTH", "au", 1), kb_back("mauth"))
    elif data == "ib3": await edit(gate_info_text("BRAINTREE AUTH", "b3", 1), kb_back("mauth"))
    elif data == "ichk": await edit(gate_info_text("STRIPE CHARGE", "chk", 1), kb_back("mcharge"))
    elif data == "ipp": await edit(gate_info_text("PAYPAL CHARGE", "pp", 1), kb_back("mcharge"))
    elif data == "ish": await edit(gate_info_text("SHOPIFY CHARGE", "sh", 1), kb_back("mcharge"))
    elif data == "ipyu": await edit(gate_info_text("PAYU CHARGE", "pyu", 1), kb_back("mcharge"))
    elif data == "imss": await edit(gate_info_text("STRIPE MASS", "mss", 2), kb_back("mmass"))
    elif data == "impp2": await edit(gate_info_text("PAYPAL MASS", "mpp2", 2), kb_back("mmass"))
    elif data in ("pay10", "pay15", "pay30"): await edit("━━━━━━━━━━━━━━━━━\n💳 Payment Address\n━━━━━━━━━━━━━━━━━\n\nPayment address will be added shortly.\n\nFor payment contact through support.\n\n━━━━━━━━━━━━━━━━━", kb_payment())

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN EXECUTION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def main():
    app = Application.builder().token(BOT_TOKEN).concurrent_updates(True).build()

    async def on_startup(application: Application) -> None:
        try: await application.bot.delete_webhook(drop_pending_updates=True)
        except Exception: pass

    app.post_init = on_startup

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("ping", cmd_ping))
    app.add_handler(CommandHandler("plan", cmd_plan))
    app.add_handler(CommandHandler("rm", cmd_rm))
    app.add_handler(CommandHandler("bin", cmd_bin))

    app.add_handler(CommandHandler("chk", cmd_chk))
    app.add_handler(CommandHandler("pp", cmd_pp))
    app.add_handler(CommandHandler("sh", cmd_sh))
    app.add_handler(CommandHandler("pyu", cmd_pyu))
    app.add_handler(CommandHandler("b3", cmd_b3))
    app.add_handler(CommandHandler("au", cmd_au))
    app.add_handler(CommandHandler("mss", cmd_mss))
    app.add_handler(CommandHandler("mpp2", cmd_mpp2))

    app.add_handler(CommandHandler("info", cmd_info))
    app.add_handler(CommandHandler("allcm", cmd_allcm))
    app.add_handler(CommandHandler("gen", cmd_gen))
    app.add_handler(CommandHandler("key10", cmd_key10))
    app.add_handler(CommandHandler("key20", cmd_key20))
    app.add_handler(CommandHandler("key30", cmd_key30))
    app.add_handler(CommandHandler("sub", cmd_sub))
    app.add_handler(CommandHandler("resub", cmd_resub))
    app.add_handler(CommandHandler("allplans", cmd_allplans))
    app.add_handler(CommandHandler("oneday", cmd_oneday))
    app.add_handler(CommandHandler("threeday", cmd_threeday))
    app.add_handler(CommandHandler("seturl", cmd_seturl))
    app.add_handler(CommandHandler("geturl", cmd_geturl))
    app.add_handler(CommandHandler("killbot", cmd_killbot))
    app.add_handler(CommandHandler("onbot", cmd_onbot))

    for cmd, func in [("onchk", cmd_onchk), ("offchk", cmd_offchk), ("onpp", cmd_onpp), ("offpp", cmd_offpp), ("onsh", cmd_onsh), ("offsh", cmd_offsh), ("onpyu", cmd_onpyu), ("offpyu", cmd_offpyu), ("onb3", cmd_onb3), ("offb3", cmd_offb3), ("onau", cmd_onau), ("offau", cmd_offau), ("onmss", cmd_onmss), ("offmss", cmd_offmss), ("onmpp2", cmd_onmpp2), ("offmpp2", cmd_offmpp2)]:
        app.add_handler(CommandHandler(cmd, func))

    app.add_handler(CallbackQueryHandler(callback_handler))

    print("🦇 Batman Bot is starting...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
