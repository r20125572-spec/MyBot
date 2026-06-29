import logging
import time
import string
import random
import asyncio
import signal
import os
import functools
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
    BOT_TOKEN, OWNER_ID, CHANNEL_ID, VERSION, DEV_LINK,
    CHANNEL_LINK, GROUP_LINK, SUPPORT_LINK,
    BOT_LINK, BOT_USERNAME, BOT_PHOTO_URL,
    API_TIMEOUT, REFERRAL_CREDITS, LOCK_FILE,
    GATE_URLS, GATE_SITES, PREMIUM_GATES, FORCE_CHANNELS,
    get_bin_info, kb_result,
)

# -------------------------------------------------------
# LOGGING
# -------------------------------------------------------
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
MAX_MSG = 4000

# -------------------------------------------------------
# DISPLAY CONSTANTS
# -------------------------------------------------------
ARROW = "➺"
SEP   = "━━━━━━━━━━━━━━━━━"
TAG   = "[ 𖥷iТ ]"

def SC(text: str) -> str:
    MAP = {
        'a': 'ᴀ', 'b': 'ʙ', 'c': 'ᴄ', 'd': 'ᴅ', 'e': 'ᴇ', 'f': 'ꜰ', 'g': 'ɢ', 'h': 'ʜ',
        'i': 'ɪ', 'j': 'ᴊ', 'k': 'ᴋ', 'l': 'ʟ', 'm': 'ᴍ', 'n': 'ɴ', 'o': 'ᴏ', 'p': 'ᴘ',
        'q': 'q', 'r': 'ʀ', 's': 'ꜱ', 't': 'ᴛ', 'u': 'ᴜ', 'v': 'ᴠ', 'w': 'ᴡ', 'x': 'x',
        'y': 'ʏ', 'z': 'ᴢ',
    }
    return ''.join(MAP.get(c.lower(), c) for c in text)

def B(text: str) -> str:
    result = []
    for c in text:
        if 'A' <= c <= 'Z': result.append(chr(0x1D5D4 + ord(c) - ord('A')))
        elif 'a' <= c <= 'z': result.append(chr(0x1D5EE + ord(c) - ord('a')))
        elif '0' <= c <= '9': result.append(chr(0x1D7EC + ord(c) - ord('0')))
        else: result.append(c)
    return ''.join(result)

# -------------------------------------------------------
# INSTANCE LOCK (FOR VPS)
# -------------------------------------------------------
try:
    import fcntl
    _lock_file_handle = None
    def acquire_instance_lock() -> bool:
        global _lock_file_handle
        try:
            _lock_file_handle = open(LOCK_FILE, "w")
            fcntl.flock(_lock_file_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            _lock_file_handle.write(str(os.getpid()))
            _lock_file_handle.flush()
            return True
        except (IOError, OSError): return False

    def release_instance_lock():
        global _lock_file_handle
        if _lock_file_handle:
            try:
                fcntl.flock(_lock_file_handle, fcntl.LOCK_UN)
                _lock_file_handle.close()
                os.unlink(LOCK_FILE)
            except Exception: pass
            _lock_file_handle = None
except ImportError:
    def acquire_instance_lock(): return True
    def release_instance_lock(): pass

# -------------------------------------------------------
# HELPERS
# -------------------------------------------------------
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
        context.bot_data["user_data"][uid] = {
            "name": "User", "username": "", "joined": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "credits": 150, "plan": "TRIAL", "expires": 0, "total_checks": 0, "total_refs": 0
        }
    return context.bot_data["user_data"][uid]

def gen_code(length: int = 10) -> str: return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))
def gen_receipt() -> str: return f"Batman{random.randint(100000, 999999)}-CHK"
def is_user_premium(ud: dict) -> bool: return ud.get("plan", "TRIAL").upper() != "TRIAL" and ud.get("expires", 0) > time.time()
def get_referral_link(user_id: int) -> str: return f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"

def owner_only(func):
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user and update.effective_user.id == OWNER_ID:
            return await func(update, context)
    return wrapper

def ui_profile(user, context: ContextTypes.DEFAULT_TYPE) -> str:
    ud = get_user_data(user.id, context)
    raw_plan = ud.get("plan", "TRIAL").upper()
    expires = ud.get("expires", 0)
    now = time.time()
    if raw_plan != "TRIAL" and expires <= now:
        raw_plan = "TRIAL"; ud["plan"] = "TRIAL"; ud["expires"] = 0; expires = 0
    premium = raw_plan != "TRIAL"
    credits = "∞ Unlimited" if premium else f"{ud.get('credits', 150)}/150"
    uname = f"@{user.username}" if user.username else (user.first_name or "User")
    lines = [
        f"{TAG} Batman Card Checker\n{SEP}",
        f"Uꜱᴇʀ    {ARROW} {uname}",
        f"ID      {ARROW} <code>{user.id}</code>",
        f"Aᴄᴄᴇꜱꜱ  {ARROW} {get_styled_plan(raw_plan)}",
        f"Cʀᴇᴅɪᴛꜱ {ARROW} {credits}",
    ]
    if premium and expires > now:
        rem_d = int((expires - now) / 86400); rem_h = int(((expires - now) % 86400) / 3600)
        lines.append(f"Exᴘɪʀᴇꜱ {ARROW} {datetime.fromtimestamp(expires).strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"Lᴇꜰᴛ    {ARROW} {rem_d}d {rem_h}h")
    lines.append(f"Jᴏɪɴᴇᴅ  {ARROW} {ud.get('joined', 'N/A')}")
    lines.append(f"Dᴇᴠ     {ARROW} <a href='{DEV_LINK}'>Batman</a>")
    lines.append(SEP)
    return "\n".join(lines)

def gate_info_text(gate_name: str, cmd: str, cost: int) -> str:
    return (f"{SEP}\n{gate_name}\n{SEP}\n\n"
            f"Cᴏsᴛ    {ARROW} {cost} Credit(s) per check\n\n"
            f"Uꜱᴀɢᴇ:\n<code>/{cmd} cc|mm|yy|cvv</code>\n\n"
            f"Exᴀᴍᴘʟᴇ:\n<code>/{cmd} 4111111111111111|12|2026|123</code>\n\n{SEP}")

# -------------------------------------------------------
# FORCE SUBSCRIBE
# -------------------------------------------------------
async def check_force_sub(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> list:
    if user_id == OWNER_ID: return []
    not_joined = []
    for name, link in FORCE_CHANNELS:
        try:
            m = await context.bot.get_chat_member(f"@{name}", user_id)
            if m.status in ("left", "kicked"): not_joined.append((name, link))
        except Exception: not_joined.append((name, link))
    return not_joined

def kb_force_sub(not_joined: list) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(f"📢 Join @{n}", url=l)] for n, l in not_joined]
    rows.append([InlineKeyboardButton("✅ I Joined — Verify Access", callback_data="check_sub")])
    return InlineKeyboardMarkup(rows)

# -------------------------------------------------------
# KEYBOARDS
# -------------------------------------------------------
def kb_main(): return InlineKeyboardMarkup([[InlineKeyboardButton(B("CHECKER"), callback_data="mgates"), InlineKeyboardButton(B("BUY NOW"), callback_data="mprice")], [InlineKeyboardButton(B("UPDATES") + " " + ARROW, url=CHANNEL_LINK), InlineKeyboardButton(B("GROUP") + " " + ARROW, url=GROUP_LINK)], [InlineKeyboardButton(B("SUPPORT") + " " + ARROW, url=SUPPORT_LINK)]])
def kb_back(cb): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 " + B("BACK"), callback_data=cb)]])
def kb_price(): return InlineKeyboardMarkup([[InlineKeyboardButton(B("10$ - CORE"), callback_data="pay10"), InlineKeyboardButton(B("15$ - ELITE"), callback_data="pay15"), InlineKeyboardButton(B("30$ - ROOT"), callback_data="pay30")], [InlineKeyboardButton(B("SUPPORT") + " " + ARROW, url=SUPPORT_LINK)], [InlineKeyboardButton("🔙 " + B("BACK"), callback_data="bmain")]])
def kb_payment(): return InlineKeyboardMarkup([[InlineKeyboardButton(B("SUPPORT") + " " + ARROW, url=SUPPORT_LINK)], [InlineKeyboardButton("🔙 " + B("BACK"), callback_data="mprice")]])
def kb_gate_main(): return InlineKeyboardMarkup([[InlineKeyboardButton(B("AUTH"), callback_data="mauth"), InlineKeyboardButton(B("CHARGE"), callback_data="mcharge"), InlineKeyboardButton("👑 " + B("PREMIUM"), callback_data="mmass")], [InlineKeyboardButton("🔙 " + B("BACK"), callback_data="bmain")]])
def kb_auth_gates(): return InlineKeyboardMarkup([[InlineKeyboardButton(B("BRAINTREE"), callback_data="ib3")], [InlineKeyboardButton("🔙 " + B("BACK"), callback_data="mgates")]])
def kb_charge_gates(): return InlineKeyboardMarkup([[InlineKeyboardButton(B("STRIPE"), callback_data="ichk"), InlineKeyboardButton(B("PAYPAL"), callback_data="ipp")], [InlineKeyboardButton(B("SHOPIFY"), callback_data="ish"), InlineKeyboardButton(B("PAYU"), callback_data="ipyu")], [InlineKeyboardButton("🔙 " + B("BACK"), callback_data="mgates")]])
def kb_premium_gates(): return InlineKeyboardMarkup([[InlineKeyboardButton(B("STRIPE AUTH") + " 👑", callback_data="iau")], [InlineKeyboardButton(B("STRIPE MASS") + " 👑", callback_data="imss")], [InlineKeyboardButton(B("PAYPAL MASS") + " 👑", callback_data="impp2")], [InlineKeyboardButton("🔙 " + B("BACK"), callback_data="mgates")]])
def kb_upgrade(): return InlineKeyboardMarkup([[InlineKeyboardButton("💎 " + B("BUY PREMIUM"), callback_data="mprice")], [InlineKeyboardButton(B("SUPPORT") + " " + ARROW, url=SUPPORT_LINK)]])

# -------------------------------------------------------
# GATE PROCESSING
# -------------------------------------------------------
async def _api_request(session, url: str, card: str, site: str) -> dict:
    if "{card}" in url:
        url = url.replace("{card}", card)
        async with session.get(url) as r:
            try: data = await r.json(content_type=None)
            except: data = {"value": await r.text()}
    else:
        async with session.get(url, params={"cc": card, "site": site}) as r:
            try: data = await r.json(content_type=None)
            except: data = {"value": await r.text()}
    return data if isinstance(data, dict) else {"value": str(data)}

async def process_gate(update: Update, context: ContextTypes.DEFAULT_TYPE, gate_key: str, gate_name: str):
    user = update.effective_user
    ud = get_user_data(user.id, context)
    premium = is_user_premium(ud)

    not_joined = await check_force_sub(user.id, context)
    if not_joined:
        await update.message.reply_text(f"{TAG} {ARROW} Join Required\n{SEP}\nJoin our channels first:\n{SEP}", reply_markup=kb_force_sub(not_joined))
        return

    if gate_key in PREMIUM_GATES and not premium:
        await update.message.reply_text(f"{TAG} {ARROW} Premium Only\n{SEP}\nMass Gates are restricted to Premium Users.\nBuy premium using /plan to use this gate.", parse_mode="HTML", reply_markup=kb_upgrade())
        return

    if not context.bot_data.get(f"{gate_key}_on", True):
        await update.message.reply_text(f"❌ Gate [{gate_name}] is currently OFF.")
        return

    card_raw = context.args[0].strip() if context.args else (update.message.reply_to_message.text.strip().split()[0] if update.message.reply_to_message and update.message.reply_to_message.text else None)
    if not card_raw:
        await update.message.reply_text(f"Usage: <code>/{gate_key} cc|mm|yy|cvv</code>", parse_mode="HTML")
        return

    if not premium:
        if ud.get("credits", 0) <= 0:
            await update.message.reply_text("❌ No credits left. Buy a plan: /plan")
            return
        ud["credits"] -= 1

    api_url = context.bot_data.get(f"gate_url_{gate_key}") or GATE_URLS.get(gate_key, "")
    if not api_url: await update.message.reply_text("Gate API not set."); return

    msg = await update.message.reply_text(f"{TAG} {ARROW} Scanning Gotham...")
    start_time = time.time()
    uname = f"@{user.username}" if user.username else (user.first_name or "User")

    try:
        timeout = _aiohttp.ClientTimeout(total=API_TIMEOUT)
        async with _aiohttp.ClientSession(timeout=timeout) as session:
            results = await asyncio.gather(_api_request(session, api_url, card_raw, GATE_SITES.get(gate_key, "")), get_bin_info(card_raw[:6]), return_exceptions=True)

        data = results[0] if not isinstance(results[0], Exception) else {}
        bin_data = results[1] if not isinstance(results[1], Exception) else {"error": True}
        if isinstance(results[0], Exception): raise results[0]

        raw_response = str(data.get("value") or data.get("message") or data.get("Response") or data.get("category") or "ERROR").strip()
        is_approved = any(w in raw_response.lower() for w in ["approved", "captured", "success", "charged", "true"])
        status_ui = "Cʜᴀʀɢᴇᴅ ✅" if is_approved else "Dᴇᴄʟɪɴᴇᴅ ❌"

        bin_txt = "N/A"
        if not bin_data.get("error"):
            s = str(bin_data.get("scheme", "N/A")).upper()
            b = bin_data.get("bank", "N/A")
            c = str(bin_data.get("country", "N/A")).upper()
            e = bin_data.get("country_emoji", "")
            bin_txt = f"{s} - {b} - {e} {c}"

        time_taken = f"{time.time() - start_time:.2f}"
        text = (
            f"{TAG} {ARROW} {status_ui}\n"
            f"{SEP}\n"
            f"💳 {ARROW} <code>{card_raw}</code>\n"
            f"🏦 {ARROW} {bin_txt}\n"
            f"{SEP}\n"
            f"🌃 𝐆𝐚𝐭𝐞 {ARROW} {gate_name}\n"
            f"📜 𝐑𝐚𝐰  {ARROW} {raw_response}\n"
            f"⏱️ 𝐓𝐢𝐦𝐞 {ARROW} {time_taken}s\n"
            f"🦇 𝐔ꜱᴇʀ {ARROW} {uname} ({get_styled_plan(ud['plan'])})\n"
            f"{SEP}"
        )
        await msg.edit_text(text, parse_mode="HTML", reply_markup=kb_result(), disable_web_page_preview=True)

    except Exception as e:
        if not premium: ud["credits"] += 1
        await msg.edit_text(f"❌ Error: <code>{str(e)[:150]}</code>", parse_mode="HTML")

async def cmd_chk(u, c): await process_gate(u, c, "chk", "Stripe Charge")
async def cmd_pp(u, c): await process_gate(u, c, "pp", "PayPal Charge")
async def cmd_sh(u, c): await process_gate(u, c, "sh", "Shopify Charge")
async def cmd_pyu(u, c): await process_gate(u, c, "pyu", "PayU Charge")
async def cmd_b3(u, c): await process_gate(u, c, "b3", "Braintree Auth")
async def cmd_au(u, c): await process_gate(u, c, "au", "Stripe Auth")
async def cmd_mss(u, c): await process_gate(u, c, "mss", "Stripe Mass")
async def cmd_mpp2(u, c): await process_gate(u, c, "mpp2", "PayPal Mass")

# -------------------------------------------------------
# PREMIUM GRANT (TEXT EXACTLY AS REQUESTED)
# -------------------------------------------------------
async def send_activation_msg(user_id: int, plan: str, days: int, context: ContextTypes.DEFAULT_TYPE) -> str:
    receipt = gen_receipt()
    ud = get_user_data(user_id, context)
    ud["plan"] = plan.upper()
    ud["expires"] = time.time() + days * 86400
    name = ud.get("name", "User")
    try:
        chat = await context.bot.get_chat(user_id)
        name = chat.first_name or name
    except Exception: pass

    txt = (
        "Cᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴꜱ! 🎉 Yᴏᴜʀ ᴀᴄᴄᴇꜱꜱ ʜᴀꜱ ʙᴇᴇɴ ᴀᴄᴛɪᴠᴀᴛᴇᴅ.\n"
        f"Uꜱᴇʀ ➺ {name}\n"
        f"Aᴄᴄᴇꜱꜱ ➺ {get_styled_plan(plan)}\n"
        f"Dᴜʀᴀᴛɪᴏɴ ➺ {days} Dᴀʏꜱ\n"
        "Cʀᴇᴅɪᴛꜱ Aᴅᴅᴇᴅ ➺ ∞\n"
        f"Rᴇᴄᴇɪᴘᴘᴛ ID ➺ {receipt}\n"
        "Pʟᴇᴀꜱᴇ ꜱᴀᴠᴇ ᴛʜɪꜱ ʀᴇᴄᴇɪᴘᴘᴛ ID."
    )
    try: await context.bot.send_message(chat_id=user_id, text=txt)
    except Exception: pass
    return receipt

async def resolve_user(target: str, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    target = target.strip().lstrip("@")
    if target.lstrip("-").isdigit(): return int(target)
    for attempt in (f"@{target}", target):
        try: return (await context.bot.get_chat(attempt)).id
        except Exception: continue
    tl = target.lower()
    for uid_str, ud in context.bot_data.get("user_data", {}).items():
        if ud.get("username", "").lower().lstrip("@") == tl: return int(uid_str)
    return None

async def _grant(uid: int, plan: str, days: int, update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud = get_user_data(uid, context)
    ud["plan"] = plan; ud["expires"] = time.time() + days * 86400
    receipt = await send_activation_msg(uid, plan, days, context)
    await update.message.reply_text(f"✅ Granted {get_styled_plan(plan)} ({days} days) to <code>{uid}</code>\nReceipt ➺ <code>{receipt}</code>", parse_mode="HTML")

# -------------------------------------------------------
# USER COMMANDS
# -------------------------------------------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ud = get_user_data(user.id, context)
    ud.setdefault("joined", datetime.now().strftime("%Y-%m-%d %H:%M"))
    ud["name"] = user.full_name or user.first_name or "User"
    if user.username: ud["username"] = user.username

    not_joined = await check_force_sub(user.id, context)
    if not_joined:
        await update.message.reply_text(f"{TAG} {ARROW} Join Required\n{SEP}\nJoin our channels to use the bot:\n{SEP}", reply_markup=kb_force_sub(not_joined))
        return
    await update.message.reply_text(ui_profile(user, context), parse_mode="HTML", reply_markup=kb_main(), disable_web_page_preview=True)

async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (f"{TAG} Batman Premium Plans\n{SEP}\n\n"
           f"Aᴄᴄᴇꜱꜱ {ARROW} Cᴏʀᴇ 🎀\nSᴜʙ   {ARROW} [7 Days]\nCʀᴇᴅɪᴛꜱ {ARROW} ∞ Unlimited\nPʀɪᴄᴇ  {ARROW} 10$\n{SEP}\n"
           f"Aᴄᴄᴇꜱꜱ {ARROW} Eʟɪᴛᴇ ⭐️\nSᴜʙ   {ARROW} [15 Days]\nCʀᴇᴅɪᴛꜱ {ARROW} ∞ Unlimited\nPʀɪᴄᴇ  {ARROW} 15$\n{SEP}\n"
           f"Aᴄᴄᴇꜱꜱ {ARROW} Rᴏᴏᴛ 👑\nSᴜʙ   {ARROW} [30 Days]\nCʀᴇᴅɪᴛꜱ {ARROW} ∞ Unlimited\nPʀɪᴄᴇ  {ARROW} 30$\n{SEP}")
    await update.message.reply_text(txt, parse_mode="HTML", reply_markup=kb_price(), disable_web_page_preview=True)

async def cmd_rm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: await update.message.reply_text("Usage: /rm <code>", parse_mode="HTML"); return
    code = context.args[0].upper(); uid = update.effective_user.id; ud = get_user_data(uid, context)
    codes = context.bot_data.setdefault("codes", {}); keys = context.bot_data.setdefault("keys", {})
    if code in codes and not codes[code]["used"]:
        codes[code]["used"] = True; ud["credits"] = ud.get("credits", 0) + codes[code]["value"]
        await update.message.reply_text(f"✅ Redeemed! +{codes[code]['value']} credits. Balance: {ud['credits']}")
    elif code in keys and not keys[code]["used"]:
        keys[code]["used"] = True; p, d = keys[code]["plan"], keys[code]["days"]
        receipt = await send_activation_msg(uid, p, d, context)
        await update.message.reply_text(f"✅ Activated {get_styled_plan(p)} for {d} days!\nReceipt ➺ <code>{receipt}</code>", parse_mode="HTML")
    else: await update.message.reply_text("❌ Invalid or already used code.")

async def cmd_bin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bin_num = context.args[0].strip()[:6] if context.args else ""
    if not bin_num or not bin_num.isdigit() or len(bin_num) < 6: await update.message.reply_text("Usage: <code>/bin 411111</code>", parse_mode="HTML"); return
    msg = await update.message.reply_text(f"{TAG} {ARROW} Looking up...")
    bd = await get_bin_info(bin_num)
    if bd.get("error"): await msg.edit_text("❌ BIN not found."); return
    txt = (f"{TAG} {ARROW} BIN Lookup\n{SEP}\n"
           f"BIN     {ARROW} <code>{bin_num}</code>\n"
           f"Scheme  {ARROW} {str(bd.get('scheme', 'N/A')).upper()}\n"
           f"Type    {ARROW} {str(bd.get('type', 'N/A')).upper()}\n"
           f"Bank    {ARROW} {bd.get('bank', 'N/A')}\n"
           f"Country {ARROW} {bd.get('country_emoji', '')} {str(bd.get('country', 'N/A')).upper()}\n{SEP}")
    await msg.edit_text(txt, parse_mode="HTML")

# -------------------------------------------------------
# OWNER COMMANDS (FIXED & WORKING)
# -------------------------------------------------------
@owner_only
async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    target_id = None; target_chat = None

    if msg.reply_to_message and msg.reply_to_message.from_user:
        target_id = msg.reply_to_message.from_user.id
        try: target_chat = await context.bot.get_chat(target_id)
        except Exception: pass
    elif context.args:
        raw = " ".join(context.args).strip()
        if raw.lstrip("-").isdigit():
            target_id = int(raw)
            try: target_chat = await context.bot.get_chat(target_id)
            except Exception: pass
        else:
            clean = raw.lstrip("@")
            for attempt in (f"@{clean}", clean):
                try:
                    target_chat = await context.bot.get_chat(attempt)
                    target_id = target_chat.id
                    break
                except Exception: continue
            if not target_id:
                cl = clean.lower()
                for uid_str, ud in context.bot_data.get("user_data", {}).items():
                    if cl in ud.get("username", "").lower().lstrip("@") or cl in ud.get("name", "").lower():
                        target_id = int(uid_str)
                        try: target_chat = await context.bot.get_chat(target_id)
                        except Exception: pass
                        break
    else:
        target_id = update.effective_user.id
        try: target_chat = await context.bot.get_chat(target_id)
        except Exception: pass

    if not target_id: await msg.reply_text("❌ User not found."); return

    udata = get_user_data(target_id, context)
    now = time.time()
    first = getattr(target_chat, "first_name", None) or udata.get("name", "Unknown")
    last = getattr(target_chat, "last_name", None) or ""
    tg_user = getattr(target_chat, "username", None) or udata.get("username", "")
    full = f"{first} {last}".strip()

    raw_plan = udata.get("plan", "TRIAL").upper()
    expires = udata.get("expires", 0)
    if raw_plan != "TRIAL" and expires <= now: raw_plan = "TRIAL"; expires = 0
    premium = raw_plan != "TRIAL" and expires > now
    credits_d = "∞ Unlimited" if premium else f"{udata.get('credits', 150)}/150"

    txt = (f"{TAG} User Info\n{SEP}\n"
           f"Name     {ARROW} {full}\n"
           f"Username {ARROW} @{tg_user if tg_user else 'None'}\n"
           f"ID       {ARROW} <code>{target_id}</code>\n{SEP}\n"
           f"Plan     {ARROW} {get_styled_plan(raw_plan)}\n"
           f"Credits  {ARROW} {credits_d}\n")
    if premium:
        rem = expires - now
        txt += f"Expires  {ARROW} {datetime.fromtimestamp(expires).strftime('%Y-%m-%d %H:%M')}\n"
        txt += f"Remaining {ARROW} {int(rem // 86400)}d {int((rem % 86400) // 3600)}h\n"
    txt += f"{SEP}\nJoined   {ARROW} {udata.get('joined', 'N/A')}\n{SEP}"
    await msg.reply_text(txt, parse_mode="HTML")

@owner_only
async def cmd_allcm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (f"{SEP}\n🦇 ALL COMMANDS\n{SEP}\n\n"
           "🟢 USER:\n/start /plan /bin /rm /ping /fb\n\n"
           "⚡ FREE GATES:\n/chk /pp /sh /pyu /b3\n\n"
           "👑 PREMIUM GATES:\n/au /mss /mpp2\n\n"
           "🛠️ OWNER:\n/info @user|ID|name\n/allcm\n/gen <credits>\n/key10 /key20 /key30\n/oneday /threeday\n/sub @user|ID days\n/resub @user|ID\n/allplans\n/seturl <gate> <url>\n/geturl\n/killbot /onbot\n/on|off + chk|pp|sh|pyu|b3|au|mss|mpp2\n"
           f"{SEP}")
    await update.message.reply_text(txt, parse_mode="HTML")

@owner_only
async def cmd_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: await update.message.reply_text("Usage: /gen <credits>"); return
    try: amt = int(context.args[0])
    except ValueError: await update.message.reply_text("❌ Invalid amount."); return
    code = gen_code()
    context.bot_data.setdefault("codes", {})[code] = {"type": "credit", "value": amt, "used": False}
    await update.message.reply_text(f"✅ Code Generated\n{SEP}\nCode {ARROW} <code>{code}</code>\nCredits {ARROW} {amt}\n{SEP}", parse_mode="HTML")

async def _gen_key(update, context, plan: str, days: int):
    code = "KEY-" + gen_code(12)
    context.bot_data.setdefault("keys", {})[code] = {"plan": plan, "days": days, "used": False}
    await update.message.reply_text(f"✅ Key Generated\n{SEP}\nKey {ARROW} <code>{code}</code>\nPlan {ARROW} {get_styled_plan(plan)}\nDays {ARROW} {days}\n{SEP}", parse_mode="HTML")

@owner_only
async def cmd_key10(u, c): await _gen_key(u, c, "CORE", 7)
@owner_only
async def cmd_key20(u, c): await _gen_key(u, c, "ELITE", 15)
@owner_only
async def cmd_key30(u, c): await _gen_key(u, c, "ROOT", 30)

@owner_only
async def cmd_oneday(update, context): 
    code = "KEY-" + gen_code(12)
    context.bot_data.setdefault("keys", {})[code] = {"plan": "CORE", "days": 1, "used": False}
    await update.message.reply_text(f"✅ 1 Day Key\n{SEP}\n<code>{code}</code>\n{SEP}", parse_mode="HTML")

@owner_only
async def cmd_threeday(update, context): 
    code = "KEY-" + gen_code(12)
    context.bot_data.setdefault("keys", {})[code] = {"plan": "CORE", "days": 3, "used": False}
    await update.message.reply_text(f"✅ 3 Day Key\n{SEP}\n<code>{code}</code>\n{SEP}", parse_mode="HTML")

@owner_only
async def cmd_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2: await update.message.reply_text("Usage: /sub <@username or ID> <days>"); return
    uid = await resolve_user(context.args[0], context)
    if not uid: await update.message.reply_text("❌ User not found."); return
    try:
        days = int(context.args[1])
        plan = "ROOT" if days >= 30 else "ELITE" if days >= 15 else "CORE"
        await _grant(uid, plan, days, update, context)
    except ValueError: await update.message.reply_text("❌ Invalid days number.")

@owner_only
async def cmd_resub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: await update.message.reply_text("Usage: /resub <@username or ID>"); return
    uid = await resolve_user(context.args[0], context)
    if not uid: await update.message.reply_text("❌ User not found."); return
    ud = get_user_data(uid, context)
    ud["plan"] = "TRIAL"; ud["expires"] = 0; ud["credits"] = 0
    await update.message.reply_text(f"✅ Premium Removed for <code>{uid}</code>.")

@owner_only
async def cmd_allplans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = time.time()
    premium_users = [(uid, ud) for uid, ud in context.bot_data.get("user_data", {}).items() if ud.get("plan", "TRIAL").upper() != "TRIAL" and ud.get("expires", 0) > now]
    if not premium_users: await update.message.reply_text("No active premium users."); return
    txt = f"{TAG} Live Premium {ARROW} {len(premium_users)} Users\n{SEP}\n\n"
    for uid_str, ud in premium_users:
        rem = ud["expires"] - now
        un = f"@{ud['username']}" if ud.get("username") else ud.get("name", "Unknown")
        txt += f"Name {ARROW} {ud.get('name', 'Unknown')}\nUser {ARROW} {un}\nID {ARROW} <code>{uid_str}</code>\nPlan {ARROW} {get_styled_plan(ud['plan'])}\nLeft {ARROW} {int(rem // 86400)}d {int((rem % 86400) // 3600)}h\n{SEP}\n"
    for i in range(0, len(txt), MAX_MSG): await update.message.reply_text(txt[i:i+MAX_MSG], parse_mode="HTML")

@owner_only
async def cmd_seturl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2: await update.message.reply_text("Usage: /seturl <gate> <url>"); return
    gate = context.args[0].lower().strip(); url = context.args[1].strip()
    if gate not in GATE_URLS: await update.message.reply_text("❌ Invalid gate."); return
    context.bot_data[f"gate_url_{gate}"] = url
    await update.message.reply_text(f"✅ URL set for gate [{gate.upper()}].")

@owner_only
async def cmd_geturl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = f"{TAG} Gate URLs\n{SEP}\n"
    for gate in GATE_URLS:
        url = context.bot_data.get(f"gate_url_{gate}") or GATE_URLS.get(gate) or "NOT SET"
        txt += f"{gate.upper()} {ARROW} <code>{url}</code>\n"
    txt += SEP
    await update.message.reply_text(txt, parse_mode="HTML")

@owner_only
async def cmd_killbot(update, context): context.bot_data["maintenance"] = True; await update.message.reply_text("🚧 Bot is now in maintenance mode.")

@owner_only
async def cmd_onbot(update, context): context.bot_data["maintenance"] = False; await update.message.reply_text("✅ Bot is back online.")

async def _gate_toggle(update, context, gate: str, state: bool):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data[f"{gate}_on"] = state
    await update.message.reply_text(f"Gate [{gate.upper()}] {ARROW} {'ON ✅' if state else 'OFF ❌'}")

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

# -------------------------------------------------------
# CALLBACK HANDLER
# -------------------------------------------------------
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; data = query.data; user = query.from_user
    try: await query.answer()
    except Exception: pass

    async def edit(text: str, markup):
        try: await query.message.edit_text(text=text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
        except BadRequest as e:
            if "not modified" in str(e).lower(): return
            try: await query.message.edit_caption(caption=text, parse_mode="HTML", reply_markup=markup)
            except Exception: await context.bot.send_message(chat_id=query.message.chat_id, text=text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)

    ud = get_user_data(user.id, context)
    premium = is_user_premium(ud)

    if data == "check_sub":
        not_joined = await check_force_sub(user.id, context)
        if not_joined:
            try: await query.answer("❌ You still haven't joined all channels!", show_alert=True)
            except Exception: pass
        else:
            await edit(ui_profile(user, context), kb_main())
    elif data == "bmain": await edit(ui_profile(user, context), kb_main())
    elif data == "mgates": await edit(f"{TAG} Select Gate Category\n{SEP}\nAuth   {ARROW} 1 gate (Free)\nCharge {ARROW} 4 gates (Free)\nPrem   {ARROW} 3 gates (Premium 👑)\n{SEP}", kb_gate_main())
    elif data == "mprice": await edit(f"{TAG} Batman Premium Plans\n{SEP}\n\nCᴏʀᴇ 🎀 {ARROW} 7 days | 10$\nEʟɪᴛᴇ ⭐️ {ARROW} 15 days | 15$\nRᴏᴏᴛ 👑 {ARROW} 30 days | 30$\n{SEP}", kb_price())
    elif data == "mauth": await edit(f"{TAG} Auth Gates (Free)\n{SEP}\n\nBraintree Auth {ARROW} /b3\n{SEP}", kb_auth_gates())
    elif data == "mcharge": await edit(f"{TAG} Charge Gates (Free)\n{SEP}\n\nStripe  {ARROW} /chk\nPayPal  {ARROW} /pp\nShopify {ARROW} /sh\nPayU    {ARROW} /pyu\n{SEP}", kb_charge_gates())
    elif data == "mmass":
        if not premium:
            try: await query.answer("Premium Gates require a premium plan!", show_alert=True)
            except Exception: pass
            await edit(f"{TAG} Premium Gates 👑\n{SEP}\n\nUpgrade with /plan to unlock:\n/au /mss /mpp2\n{SEP}", kb_upgrade())
            return
        await edit(f"{TAG} Premium Gates 👑\n{SEP}\n\nStripe Auth {ARROW} /au\nStripe Mass {ARROW} /mss\nPayPal Mass {ARROW} /mpp2\n{SEP}", kb_premium_gates())
    elif data == "ib3": await edit(gate_info_text("BRAINTREE AUTH", "b3", 1), kb_back("mauth"))
    elif data == "ichk": await edit(gate_info_text("STRIPE CHARGE", "chk", 1), kb_back("mcharge"))
    elif data == "ipp": await edit(gate_info_text("PAYPAL CHARGE", "pp", 1), kb_back("mcharge"))
    elif data == "ish": await edit(gate_info_text("SHOPIFY CHARGE", "sh", 1), kb_back("mcharge"))
    elif data == "ipyu": await edit(gate_info_text("PAYU CHARGE", "pyu", 1), kb_back("mcharge"))
    elif data == "iau":
        if not premium: return
        await edit(gate_info_text("STRIPE AUTH 👑", "au", 1), kb_back("mmass"))
    elif data == "imss":
        if not premium: return
        await edit(gate_info_text("STRIPE MASS 👑", "mss", 2), kb_back("mmass"))
    elif data == "impp2":
        if not premium: return
        await edit(gate_info_text("PAYPAL MASS 👑", "mpp2", 2), kb_back("mmass"))
    elif data in ("pay10", "pay15", "pay30"):
        await edit(f"{TAG} Payment\n{SEP}\n\nTo purchase, contact support.\n{SEP}", kb_payment())

# -------------------------------------------------------
# MAIN EXECUTION
# -------------------------------------------------------
async def post_init(application: Application):
    try: await application.bot.delete_webhook(drop_pending_updates=True)
    except Exception: pass

def main():
    if not acquire_instance_lock():
        logger.critical("Another instance is running. Exiting."); os._exit(1)

    app = Application.builder().token(BOT_TOKEN).concurrent_updates(True).post_init(post_init).build()

    app.add_handler(CommandHandler("start", cmd_start))
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
    app.add_handler(CommandHandler("oneday", cmd_oneday))
    app.add_handler(CommandHandler("threeday", cmd_threeday))
    app.add_handler(CommandHandler("sub", cmd_sub))
    app.add_handler(CommandHandler("resub", cmd_resub))
    app.add_handler(CommandHandler("allplans", cmd_allplans))
    app.add_handler(CommandHandler("seturl", cmd_seturl))
    app.add_handler(CommandHandler("geturl", cmd_geturl))
    app.add_handler(CommandHandler("killbot", cmd_killbot))
    app.add_handler(CommandHandler("onbot", cmd_onbot))

    for cmd, fn in [("onchk", cmd_onchk), ("offchk", cmd_offchk), ("onpp", cmd_onpp), ("offpp", cmd_offpp), ("onsh", cmd_onsh), ("offsh", cmd_offsh), ("onpyu", cmd_onpyu), ("offpyu", cmd_offpyu), ("onb3", cmd_onb3), ("offb3", cmd_offb3), ("onau", cmd_onau), ("offau", cmd_offau), ("onmss", cmd_onmss), ("offmss", cmd_offmss), ("onmpp2", cmd_onmpp2), ("offmpp2", cmd_offmpp2)]:
        app.add_handler(CommandHandler(cmd, fn))

    app.add_handler(CallbackQueryHandler(callback_handler))

    print("🦇 Batman Bot is starting...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
