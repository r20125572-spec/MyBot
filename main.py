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

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 HARDCODED LINKS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CHANNEL_USERNAME = "@Batcardchk"
GROUP_USERNAME = "@batcardchkGroup"
CHANNEL_LINK = "https://t.me/Batcardchk"
GROUP_LINK = "https://t.me/batcardchkGroup"
SUPPORT_LINK = "https://t.me/cardchkSupport"

WELCOME_IMAGE_URL = "https://example.com/batman.jpg"

GATE_COST = {"chk": 1, "pp": 1, "sh": 2, "pyu": 1, "b3": 1}
GATE_NAMES = {"chk": "Stripe", "pp": "PayPal", "sh": "Shopify", "pyu": "PayU", "b3": "Braintree"}

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

BLOCK_WORDS = (
    "http://", "https://", "www.", "t.me", ".com", ".net", ".org",
    ".io", ".me", ".xyz", ".tk", ".ml", ".cf", ".ga", ".ru", ".in",
    ".pw", "telegram.me", "joinchat", "://",
    "a_toolsx", "a-tools", "atoolsx", "a tools x", "a-tools x", "a_tools",
    "toolsx"
)

PLAN_TEXT = """Aᴄᴄᴇꜱꜱ ➺ Cᴏʀᴇ 🎀
Sᴘᴀɴ ➺ [7 Dᴀʏꜱ]
Cʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ
Pʀɪᴄᴇ ➺ 10$ 
━━━━━━━━━━━━━━━━
Aᴄᴄᴇꜱꜱ ➺ Eʟɪᴛᴇ ⭐️
Sᴘᴀɴ ➺ [15 Dᴀʏꜱ]
Cʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ
Pʀɪᴄᴇ ➺ 15$ 
━━━━━━━━━━━━━━━━
Aᴄᴄᴇꜱꜱ ➺ Rᴏᴏᴛ 👑
Sᴘᴀɴ ➺ [30 Dᴀʏꜱ]
Cʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ
Pʀɪᴄᴇ ➺ 30$"""

def get_styled_plan(raw_plan: str) -> str:
    plan_upper = raw_plan.upper()
    if plan_upper == "CORE": return "✨ Cᴏʀᴇ ✨"
    elif plan_upper == "ELITE": return "⭐ Eʟɪᴛᴇ ⭐"
    elif plan_upper == "ROOT": return "👑 Rᴏᴏᴛ 👑"
    else: return "Tʀɪᴀʟ"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 SAFE USER DATA GETTER (FIXES '8283904645' ERROR)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_user_data(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> dict:
    uid_str = str(user_id)
    if 'user_data' not in context.bot_data:
        context.bot_data['user_data'] = {}
    if uid_str not in context.bot_data['user_data']:
        context.bot_data['user_data'][uid_str] = {"name": "User", "joined": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "credits": 150, "plan": "TRIAL", "expires": 0}
    return context.bot_data['user_data'][uid_str]

async def anti_ad_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or msg.from_user.id == OWNER_ID: return
    text = (msg.text or msg.caption or "").lower()
    if not text: return
    if any(w in text for w in BLOCK_WORDS):
        try: await msg.delete()
        except: pass

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 MAINTENANCE MODE CHECKER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def maintenance_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot_data.get('maintenance', False) and update.effective_user.id != OWNER_ID:
        try:
            await update.message.reply_text("🛑 Bot is currently under maintenance.", parse_mode="HTML")
        except: pass
        raise ApplicationHandlerStop

async def is_joined(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    async def check(chat_id):
        try: return (await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)).status not in ('left', 'kicked')
        except: return False
    return await check(CHANNEL_USERNAME) and await check(GROUP_USERNAME)

def gen_code(length=10): return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))
def gen_receipt(): return f"BATCARD-{random.randint(100000, 999999)}-CHK"

def ui_profile(user, context: ContextTypes.DEFAULT_TYPE):
    u = user.username or "None"
    ud = get_user_data(user.id, context)
    raw_plan = ud.get('plan', 'TRIAL').upper()
    expires = ud.get('expires', 0)
    now = time.time()
    
    if raw_plan != 'TRIAL' and expires <= now:
        raw_plan = 'TRIAL'; ud['plan'] = 'TRIAL'; ud['expires'] = 0
        
    plan_str = get_styled_plan(raw_plan)
    is_premium = raw_plan != 'TRIAL'
    credits = "∞" if is_premium else f"{ud.get('credits', 150)}/150"
    
    lines = [
        f"Uꜱᴇʀ ➺ {u}", 
        f"Uꜱᴇʀ ID ➺ <code>{user.id}</code>", 
        f"Pʟᴀɴ ➺ {plan_str}", 
        f"Cʀᴇᴅɪᴛꜱ ➺ {credits}"
    ]
    
    if is_premium and expires > now:
        exp_date = datetime.fromtimestamp(expires).strftime('%Y-%m-%d %H:%M')
        remaining = int((expires - now) / 86400)
        remaining_hrs = int(((expires - now) % 86400) / 3600)
        lines.append(f"Exᴘɪʀᴇꜱ ➺ {exp_date}")
        if remaining > 0: lines.append(f"Rᴇᴍᴀɪɴɪɴɢ ➺ {remaining} Dᴀʏꜱ {remaining_hrs} Hʀꜱ")
        else: lines.append(f"Rᴇᴍᴀɪɴɪɴɢ ➺ {remaining_hrs} Hʀꜱ")
        
    lines.append(f"Jᴏɪɴᴇᴅ ➺ {ud.get('joined', datetime.now().strftime('%Y-%m-%d'))}")
    lines.append(f"Dᴇᴠ ➺ <a href='{DEV_LINK}'>Batman</a>")
    return "\n".join(lines)

async def send_activation_msg(user_id: int, plan: str, days: int, context: ContextTypes.DEFAULT_TYPE) -> str:
    receipt = gen_receipt()
    name, username = "Unknown", "None"
    try:
        chat = await context.bot.get_chat(user_id)
        name = chat.first_name or "Unknown"; username = chat.username or "None"
    except: pass
    
    ud = get_user_data(user_id, context)
    ud["name"] = name; ud["plan"] = plan; ud["expires"] = time.time() + (days * 86400)
    exp_date = datetime.fromtimestamp(ud["expires"]).strftime('%Y-%m-%d %H:%M')
    styled_plan = get_styled_plan(plan)
    txt = (f"Cᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴꜱ! 🎉 Yᴏᴜʀ ᴀᴄᴄᴇꜱꜱ ʜᴀꜱ ʙᴇᴇɴ ᴀᴄᴛɪᴠᴀᴛᴇᴅ.\n━━━━━━━━━━━━━━━━━━━━\n\nUꜱᴇʀ ➺ {name}\nUꜱᴇʀɴᴀᴍᴇ ➺ @{username}\nAᴄᴄᴇꜱꜱ ➺ {styled_plan}\nDᴜʀᴀᴛɪᴏɴ ➺ {days} Dᴀʏꜱ\nCʀᴇᴅɪᴛꜱ Aᴅᴅᴇᴅ ➺ ∞\nExᴘɪʀᴇꜱ ➺ {exp_date}\nRᴇᴄᴇɪᴘᴘᴛ ID ➺ <code>{receipt}</code>\n\n━━━━━━━━━━━━━━━━━━━━\nPʟᴇᴀꜱᴇ ꜱᴀᴠᴇ ᴛʜɪꜱ ʀᴇᴄᴇɪᴘᴘᴛ ID.")
    try: await context.bot.send_message(chat_id=user_id, text=txt, parse_mode="HTML")
    except: pass
    return receipt

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 KEYBOARDS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def kb_main():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("CHECKER", callback_data="mgates"), InlineKeyboardButton("BUY NOW", callback_data="mprice")],
        [InlineKeyboardButton("UPDATES", url=CHANNEL_LINK), InlineKeyboardButton("GROUP", url=GROUP_LINK)],
        [InlineKeyboardButton("SUPPORT", url=SUPPORT_LINK)]
    ])

def kb_back(cb): return InlineKeyboardMarkup([[InlineKeyboardButton("« BACK", callback_data=cb)]])

def kb_force():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("JOIN GROUP", url=GROUP_LINK)],
        [InlineKeyboardButton("JOIN CHANNEL", url=CHANNEL_LINK)],
        [InlineKeyboardButton("✅ VERIFY", callback_data="verify_join")]
    ])

def kb_price():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("10$PAY", callback_data="pay10"), InlineKeyboardButton("15$PAY", callback_data="pay15"), InlineKeyboardButton("30$PAY", callback_data="pay30")],
        [InlineKeyboardButton("« BACK", callback_data="bmain")]
    ])

def kb_payment():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("SUPPORT", url=SUPPORT_LINK)],
        [InlineKeyboardButton("« BACK", callback_data="mprice")]
    ])

def kb_gate_category():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("AUTH", callback_data="mauth"), InlineKeyboardButton("CHARGE", callback_data="mcharge")],
        [InlineKeyboardButton("« BACK", callback_data="bmain")]
    ])

def kb_auth_gates():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("STRIPE", callback_data="iau")],
        [InlineKeyboardButton("BRAINTREE", callback_data="ib3")],
        [InlineKeyboardButton("« BACK", callback_data="mgates")]
    ])

def kb_charge_gates():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("STRIPE", callback_data="ichk"), InlineKeyboardButton("PAYPAL", callback_data="ipp")],
        [InlineKeyboardButton("SHOPIFY", callback_data="ish"), InlineKeyboardButton("PAYU", callback_data="ipyu")],
        [InlineKeyboardButton("« BACK", callback_data="mgates")]
    ])

async def resolve_user(target: str, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    target = target.lstrip('@')
    if target.lstrip('-').isdigit(): return int(target)
    try: return (await context.bot.get_chat(f"@{target}")).id
    except: return None

async def fetch_bin(url: str) -> dict:
    try:
        req = urllib.request.Request(url, headers={"Accept-Version": "3", "User-Agent": "Mozilla/5.0"})
        loop = asyncio.get_running_loop()
        def do_req():
            with urllib.request.urlopen(req, timeout=10) as r: return json.loads(r.read().decode('utf-8'))
        return await loop.run_in_executor(None, do_req)
    except: return {}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 ALL-IN-ONE GATE CHECKER LOGIC
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def process_gate(update: Update, context: ContextTypes.DEFAULT_TYPE, gate_key: str, gate_name: str):
    if not context.bot_data.get(f'{gate_key}_on', True):
        await update.message.reply_text("⚠️ Gᴀᴛᴇ ➤ OFF", parse_mode="HTML")
        return
    
    card = None
    if context.args: 
        card = context.args[0]
    elif update.message.reply_to_message and update.message.reply_to_message.text: 
        card = update.message.reply_to_message.text.strip()
        
    if not card:
        await update.message.reply_text(
            f"⚠️ Uꜱᴀɢᴇ: Rᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇꜱꜱᴀɢᴇ ᴡɪᴛʜ ᴄᴀʀᴅꜱ ᴏʀ ꜱᴇɴᴅ\n/{gate_key} cc|mm|yy|cvv", 
            parse_mode="HTML"
        )
        return
    
    # Safely get user data to prevent KeyError
    ud = get_user_data(update.effective_user.id, context)
    is_premium = ud.get('plan', 'TRIAL').upper() != 'TRIAL' and ud.get('expires', 0) > time.time()

    if not is_premium:
        credits = ud.get('credits', 150)
        if credits <= 0:
            await update.message.reply_text("Buy the PLANS and Start the checking you trils cradits are empty.", parse_mode="HTML")
            return
        ud['credits'] = credits - 1
    
    bin_num = card[:6]
    msg = await update.message.reply_text("⏳ Pʀᴏᴄᴇꜱꜱɪɴɢ...", parse_mode="HTML")
    start_time = time.time()
    
    api_url = context.bot_data.get(f'gate_url_{gate_key}', GATE_URLS.get(gate_key, ""))
    site_url = GATE_SITES.get(gate_key, "example.com")

    if not api_url:
        await msg.edit_text("❌ Eʀʀᴏʀ ➤ Gate API URL not set.", parse_mode="HTML")
        return

    try:
        timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            tasks = [
                session.get(api_url, params={"cc": card, "site": site_url}), 
                get_bin_info(bin_num)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        
        api_resp = results[0]
        bin_data = results[1] if not isinstance(results[1], Exception) else {"error": True}
        
        if isinstance(api_resp, Exception): raise api_resp
        
        data = await api_resp.json()
        
        if not isinstance(data, dict):
            data = {"value": str(data)}
            
        raw_response = data.get("value", "")
        if not raw_response: raw_response = data.get("message", "")
        if not raw_response: raw_response = data.get("category", "ERROR")
        raw_response = str(raw_response).strip()
        
        is_approved = any(word in raw_response.lower() for word in ["approved", "captured", "success"])
        status_ui = "APPROVED ✅" if is_approved else "Dᴇᴄʟɪɴᴇᴅ ❌"
            
        bin_txt, country, flag = "N/A", "N/A", ""
        if not bin_data.get("error"):
            s = str(bin_data.get("scheme", "N/A")).upper()
            b = bin_data.get("bank", "N/A")
            country = str(bin_data.get("country", "N/A")).upper()
            flag = bin_data.get("country_emoji", "")
            bin_txt = f"{s} - {b} - {flag} {country}"
            
        raw_plan = ud.get('plan', 'TRIAL').upper()
        if raw_plan != 'TRIAL' and ud.get('expires', 0) <= time.time(): raw_plan = 'TRIAL'
        plan_ui = get_styled_plan(raw_plan)
        username = update.effective_user.first_name or "User"
        time_taken = f"{time.time() - start_time:.2f}"
        
        text = (
            f"[ 𖥷iТ ] ➺ {status_ui}\n"
            f"🔍 ➺ {card}\n"
            f"Gᴀᴛᴇ ➺ {gate_name} 💳 🟢\n"
            f"Rᴀᴡ ➺ {raw_response}\n"
            f"Iɴꜰᴏ ➺ {bin_txt}\n"
            f"Uꜱᴇʀ ➺ {username} 👑 ({plan_ui})\n"
            f"Pʀᴏ ➺ Batman ⚡\n"
            f"Tɪᴍᴇ ➺ {time_taken}s"
        )
        
        await msg.edit_text(text, parse_mode="HTML", reply_markup=kb_result(), disable_web_page_preview=True)
        
    except aiohttp.ClientTimeout: 
        await msg.edit_text("⏳ Tɪᴍᴇᴏᴜᴛ", parse_mode="HTML")
    except Exception as e: 
        await msg.edit_text(f"❌ Eʀʀᴏʀ ➤ <code>{str(e)[:100]}</code>", parse_mode="HTML")

# Gate Commands
async def cmd_chk(update: Update, context: ContextTypes.DEFAULT_TYPE): await process_gate(update, context, "chk", "Sᴛʀɪᴘᴇ | 1 ᴜꜱᴅ")
async def cmd_pp(update: Update, context: ContextTypes.DEFAULT_TYPE): await process_gate(update, context, "pp", "PᴀʏPᴀʟ | 1 ᴜꜱᴅ")
async def cmd_sh(update: Update, context: ContextTypes.DEFAULT_TYPE): await process_gate(update, context, "sh", "Sʜᴏᴘɪꜰʏ | 2 ᴜꜱᴅ")
async def cmd_pyu(update: Update, context: ContextTypes.DEFAULT_TYPE): await process_gate(update, context, "pyu", "PᴀʏU | 1 ᴜꜱᴅ")
async def cmd_b3(update: Update, context: ContextTypes.DEFAULT_TYPE): await process_gate(update, context, "b3", "Bʀᴀɪɴᴛʀᴇᴇ | 1 ᴜꜱᴅ")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 /start
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ud = get_user_data(user.id, context)
    if "joined" not in ud: ud["joined"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if "name" not in ud: ud["name"] = user.first_name

    if await is_joined(user.id, context):
        await update.message.reply_text(text=ui_profile(user, context), parse_mode="HTML", reply_markup=kb_main(), disable_web_page_preview=True)
    else:
        caption = ("🦇 BATMAN CARD CHECKER 🦇\n\nAccess Required\n━━━━━━━━━━━━━━━━━━━━\nJoin both channels to\nunlock the bot.\n━━━━━━━━━━━━━━━━━━━━")
        try:
            await update.message.reply_photo(photo=WELCOME_IMAGE_URL, caption=caption, parse_mode="HTML", reply_markup=kb_force())
        except Exception:
            await update.message.reply_text(text=caption, parse_mode="HTML", reply_markup=kb_force())

async def cmd_bin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: await update.message.reply_text("❌ Usage: /bin <BIN>\nExample: /bin 453201", parse_mode="HTML"); return
    bin_num = ''.join(filter(str.isdigit, context.args[0]))[:6]
    if len(bin_num) < 6: await update.message.reply_text("❌ Invalid BIN!", parse_mode="HTML"); return
    status = await update.message.reply_text(f"🔍 Looking up BIN: <code>{bin_num}</code>...", parse_mode="HTML")
    data = await fetch_bin(f"https://lookup.binlist.net/{bin_num}")
    if not data or "scheme" not in data:
        try: await status.edit_text("❌ BIN not found.", parse_mode="HTML")
        except: pass
        return
    c_data = data.get("country") or {}; b_data = data.get("bank") or {}
    brand = (data.get("brand") or "N/A").upper()
    brand_emoji = {"VISA": "🔵", "MASTERCARD": "🔴", "AMEX": "🟡"}.get(brand, "⚪")
    type_emoji = {"CREDIT": "💳", "DEBIT": "🏦"}.get((data.get("type") or "").upper(), "💳")
    txt = (f"━━━━━━━━━━━━━━━━━━━━\n🦇 BIN LOOKUP RESULT\n━━━━━━━━━━━━━━━━━━━━\n\nBIN ➺ <code>{bin_num}</code>\nSCHEME ➺ {(data.get('scheme') or 'N/A').upper()}\nTYPE ➺ {type_emoji} {(data.get('type') or 'N/A').upper()}\nBRAND ➺ {brand_emoji} {brand}\n\n━━━━━━━━━━━━━━━━━━━━\n🌍 COUNTRY INFO\n━━━━━━━━━━━━━━━━━━━━\n\nNAME ➺ {c_data.get('emoji', '🌍')} {c_data.get('name', 'N/A')}\nCODE ➺ {c_data.get('alpha2', '??')}\n\n━━━━━━━━━━━━━━━━━━━━\n🏦 BANK INFO\n━━━━━━━━━━━━━━━━━━━━\n\nBANK ➺ {b_data.get('name', 'N/A')}\n")
    if b_data.get("url"): txt += f"URL ➺ {b_data.get('url')}\n"
    txt += "\n━━━━━━━━━━━━━━━━━━━━"
    try: await status.edit_text(txt, parse_mode="HTML", disable_web_page_preview=True)
    except: pass

async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(PLAN_TEXT, parse_mode="HTML", reply_markup=kb_price(), disable_web_page_preview=True)

async def cmd_allcm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    await update.message.reply_text(
        f"BATMAN BOT - ALL COMMANDS\n━━━━━━━━━━━━━━━━━━\nVersion: {VERSION}\n━━━━━━━━━━━━━━━━━━\n\nUSER COMMANDS\n━━━━━━━━━━━━━━━━━━\n/start /plan /bin\n/chk /pp /sh /pyu /b3 /rm\n\nOWNER COMMANDS\n━━━━━━━━━━━━━━━━━━\n/info /allcm /gen\n/key10 /key20 /key30\n/sub /resub /allplans\n/oneday /threeday\n/seturl /geturl\n/onchk /offchk /onpp /offpp\n/onsh /offsh /onpyu /offpyu /onb3 /offb3\n/killbot /onbot\n━━━━━━━━━━━━━━━━━━",
        parse_mode="HTML"
    )

async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not update.message.reply_to_message and not context.args:
        await update.message.reply_text("❌ Usage: /info <user_id>\nOr reply to a message with /info", parse_mode="HTML"); return
    if update.message.reply_to_message: target_id = update.message.reply_to_message.from_user.id
    else: target_id = await resolve_user(context.args[0], context)
    if not target_id: await update.message.reply_text("❌ User not found.", parse_mode="HTML"); return
    name, username, uid = "N/A", "None", target_id
    try:
        u = await context.bot.get_chat(target_id); name = u.first_name or "N/A"; username = u.username or "None"; uid = u.id
    except: pass
    udata = get_user_data(uid, context)
    raw_plan = udata.get('plan', 'TRIAL').upper(); expires = udata.get('expires', 0); now = time.time()
    if raw_plan != 'TRIAL' and expires <= now: raw_plan = 'TRIAL'
    plan_str = get_styled_plan(raw_plan)
    credits = "∞" if raw_plan != 'TRIAL' else f"{udata.get('credits', 150)}/150"
    txt = (f"━━━━━━━━━━━━━━━━━━━━\n🦇 USER INFO\n━━━━━━━━━━━━━━━━━━━━\n\nName ➺ {name}\nUsername ➺ @{username}\nUser ID ➺ <code>{uid}</code>\nPlan ➺ {plan_str}\nCredits ➺ {credits}\n")
    if raw_plan != 'TRIAL' and expires > now:
        txt += f"Expires ➺ {datetime.fromtimestamp(expires).strftime('%Y-%m-%d %H:%M')}\nRemaining ➺ {int((expires - now) / 86400)} Days\n"
    else: txt += "Status ➺ Inactive / Trial\n"
    txt += "━━━━━━━━━━━━━━━━━━━━"
    await update.message.reply_text(txt, parse_mode="HTML")

async def cmd_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args: await update.message.reply_text("❌ Usage: /gen <credits>", parse_mode="HTML"); return
    try:
        amt = int(context.args[0]); code = gen_code()
        context.bot_data.setdefault('codes', {})[code] = {"type": "credit", "value": amt, "used": False}
        await update.message.reply_text(f"✅ CREDIT CODE GENERATED\n━━━━━━━━━━━━━━━━━━━━\n\nCode: <code>{code}</code>\nCredits: {amt}\n━━━━━━━━━━━━━━━━━━━━", parse_mode="HTML")
    except: await update.message.reply_text("❌ Invalid amount.", parse_mode="HTML")

async def cmd_gen_key(update: Update, context: ContextTypes.DEFAULT_TYPE, plan: str, days: int):
    if update.effective_user.id != OWNER_ID: return
    code = "KEY-" + gen_code(12)
    context.bot_data.setdefault('keys', {})[code] = {"plan": plan, "days": days, "used": False}
    await update.message.reply_text(f"✅ PREMIUM KEY GENERATED\n━━━━━━━━━━━━━━━━━━━━\n\nKey: <code>{code}</code>\nPlan: {get_styled_plan(plan)}\nDays: {days}\n━━━━━━━━━━━━━━━━━━━━", parse_mode="HTML")

async def cmd_key10(update: Update, context: ContextTypes.DEFAULT_TYPE): await cmd_gen_key(update, context, "core", 7)
async def cmd_key20(update: Update, context: ContextTypes.DEFAULT_TYPE): await cmd_gen_key(update, context, "elite", 15)
async def cmd_key30(update: Update, context: ContextTypes.DEFAULT_TYPE): await cmd_gen_key(update, context, "root", 30)

async def _grant_premium(uid: int, plan: str, days: int, update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud = get_user_data(uid, context)
    ud["plan"] = plan; ud["expires"] = time.time() + (days * 86400)
    receipt = await send_activation_msg(uid, plan, days, context)
    await update.message.reply_text(f"✅ Granted {days} Days ({get_styled_plan(plan)}) to <code>{uid}</code>\nRᴇᴄᴇɪᴘᴘᴛ ➺ <code>{receipt}</code>", parse_mode="HTML")

async def cmd_oneday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    code = "KEY-" + gen_code(12)
    context.bot_data.setdefault('keys', {})[code] = {"plan": "core", "days": 1, "used": False}
    await update.message.reply_text(f"✅ 1 DAY CODE GENERATED\n━━━━━━━━━━━━━━━━━━━━\n\nCode: <code>{code}</code>\nPlan: {get_styled_plan('core')}\nDays: 1\n\nGive this code to the user!\nUser can redeem via /rm {code}", parse_mode="HTML")

async def cmd_threeday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    code = "KEY-" + gen_code(12)
    context.bot_data.setdefault('keys', {})[code] = {"plan": "core", "days": 3, "used": False}
    await update.message.reply_text(f"✅ 3 DAYS CODE GENERATED\n━━━━━━━━━━━━━━━━━━━━\n\nCode: <code>{code}</code>\nPlan: {get_styled_plan('core')}\nDays: 3\n\nGive this code to the user!\nUser can redeem via /rm {code}", parse_mode="HTML")

async def cmd_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if len(context.args) < 2:
        await update.message.reply_text("❌ Usage: /sub <user_id> <days>", parse_mode="HTML"); return
    uid = await resolve_user(context.args[0], context)
    if not uid: await update.message.reply_text("❌ User not found.", parse_mode="HTML"); return
    try:
        days = int(context.args[1]); plan = "root" if days >= 30 else "elite" if days >= 15 else "core"
        await _grant_premium(uid, plan, days, update, context)
    except ValueError: await update.message.reply_text("❌ Invalid days number.", parse_mode="HTML")

async def cmd_resub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args: await update.message.reply_text("❌ Usage: /resub <user_id>", parse_mode="HTML"); return
    uid = await resolve_user(context.args[0], context)
    if not uid: await update.message.reply_text("❌ User not found.", parse_mode="HTML"); return
    ud = get_user_data(uid, context)
    ud["plan"] = "TRIAL"; ud["expires"] = 0
    await update.message.reply_text(f"✅ Removed premium from <code>{uid}</code>", parse_mode="HTML")

async def cmd_allplans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    users = context.bot_data.get('user_data', {}); txt = "🦇 ACTIVE PLANS\n━━━━━━━━━━━━━━━━━━━━\n\n"; found = False; now = time.time()
    for uid, data in users.items():
        exp = data.get('expires', 0)
        if data.get('plan', 'TRIAL') != 'TRIAL' and exp > now:
            found = True; remaining = int((exp - now) / 86400)
            txt += f"ID: <code>{uid}</code>\nPlan: {get_styled_plan(data.get('plan', 'TRIAL'))}\nCredits: ∞\nRemaining: {remaining} Days\n━━━━━━━━━━━━━━━━━━━━\n"
    if not found: txt += "❌ No active plans."
    await update.message.reply_text(txt, parse_mode="HTML")

async def cmd_delcode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args: await update.message.reply_text("❌ Usage: /delcode <code>", parse_mode="HTML"); return
    code = context.args[0]; codes, keys = context.bot_data.get('codes', {}), context.bot_data.get('keys', {})
    if code in codes: del codes[code]; await update.message.reply_text("✅ Code deleted.", parse_mode="HTML")
    elif code in keys: del keys[code]; await update.message.reply_text("✅ Key deleted.", parse_mode="HTML")
    else: await update.message.reply_text("❌ Not found.", parse_mode="HTML")

async def cmd_rm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: await update.message.reply_text("❌ Usage: /rm <code>", parse_mode="HTML"); return
    code = context.args[0].upper()
    uid = update.effective_user.id
    
    ud = get_user_data(uid, context)
    codes = context.bot_data.get('codes', {})
    keys = context.bot_data.get('keys', {})
    
    if code in codes and not codes[code]['used']:
        codes[code]['used'] = True; ud["credits"] += codes[code]['value']
        await update.message.reply_text(f"✅ Redeemed! Added {codes[code]['value']} credits.\nNew Balance: {ud['credits']}/150", parse_mode="HTML")
    elif code in keys and not keys[code]['used']:
        keys[code]['used'] = True; p, d = keys[code]['plan'], keys[code]['days']
        ud["plan"] = p; ud["expires"] = time.time() + (d * 86400)
        receipt = await send_activation_msg(uid, p, d, context)
        await update.message.reply_text(f"✅ Activated {get_styled_plan(p)} for {d} days.\nRᴇᴄᴇɪᴘᴘᴛ ➺ <code>{receipt}</code>", parse_mode="HTML")
    else: await update.message.reply_text("❌ Invalid or used code.", parse_mode="HTML")

async def cmd_onchk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data['chk_on'] = True; await update.message.reply_text("STRIPE → ON ✅", parse_mode="HTML")
async def cmd_offchk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data['chk_on'] = False; await update.message.reply_text("STRIPE → OFF ❌", parse_mode="HTML")
async def cmd_onpp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data['pp_on'] = True; await update.message.reply_text("PAYPAL → ON ✅", parse_mode="HTML")
async def cmd_offpp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data['pp_on'] = False; await update.message.reply_text("PAYPAL → OFF ❌", parse_mode="HTML")
async def cmd_onsh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data['sh_on'] = True; await update.message.reply_text("SHOPIFY → ON ✅", parse_mode="HTML")
async def cmd_offsh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data['sh_on'] = False; await update.message.reply_text("SHOPIFY → OFF ❌", parse_mode="HTML")
async def cmd_onpyu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data['pyu_on'] = True; await update.message.reply_text("PAYU → ON ✅", parse_mode="HTML")
async def cmd_offpyu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data['pyu_on'] = False; await update.message.reply_text("PAYU → OFF ❌", parse_mode="HTML")
async def cmd_onb3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data['b3_on'] = True; await update.message.reply_text("BRAINTREE → ON ✅", parse_mode="HTML")
async def cmd_offb3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data['b3_on'] = False; await update.message.reply_text("BRAINTREE → OFF ❌", parse_mode="HTML")

async def cmd_seturl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if len(context.args) < 2:
        await update.message.reply_text("❌ Usage: /seturl <gate> <url>\n/seturl chk remove", parse_mode="HTML"); return
    gate = context.args[0].lower(); url = " ".join(context.args[1:])
    if gate not in GATE_NAMES: await update.message.reply_text(f"❌ Unknown gate. Valid: chk, pp, sh, pyu, b3", parse_mode="HTML"); return
    if url.lower() == "remove": context.bot_data.pop(f'gate_url_{gate}', None); await update.message.reply_text(f"✅ Removed {GATE_NAMES[gate]} override.", parse_mode="HTML"); return
    context.bot_data[f'gate_url_{gate}'] = url
    await update.message.reply_text(f"✅ {GATE_NAMES[gate]} override set.\n<code>{url}</code>", parse_mode="HTML")

async def cmd_geturl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    txt = "🦇 GATE API URLs\n━━━━━━━━━━━━━━━━━━━━\n\n"
    for gate, name in GATE_NAMES.items():
        override = context.bot_data.get(f'gate_url_{gate}', ''); config_url = GATE_URLS.get(gate, '')
        active = override if override else config_url; source = "⚡ Override" if override else "📝 Config"
        status = "🟢 ON" if context.bot_data.get(f'{gate}_on', True) else "🔴 OFF"
        txt += f"{name} [{status}] [{source}]\n<code>{active or '❌ Not set'}</code>\n\n"
    txt += "━━━━━━━━━━━━━━━━━━━━"
    await update.message.reply_text(txt, parse_mode="HTML")

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    d = q.data
    try: await q.answer()
    except: pass
    
    if context.bot_data.get('maintenance', False) and q.from_user.id != OWNER_ID:
        await q.answer("🛑 Bot is under maintenance.", show_alert=True)
        return

    async def safe_edit(t, kb):
        if not q.message: return
        success = False
        if not q.message.photo:
            try:
                await q.edit_message_text(text=t, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
                success = True
            except Exception: pass
        if not success:
            try: await context.bot.send_message(chat_id=q.message.chat_id, text=t, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
            except Exception: pass

    if d == "verify_join":
        if await is_joined(q.from_user.id, context):
            await safe_edit(ui_profile(q.from_user, context), kb_main())
        else:
            await q.answer("❌ Join Group & Channel first!", show_alert=True)
        return

    if d == "bmain":
        await safe_edit(ui_profile(q.from_user, context), kb_main())
        
    elif d == "mprice":
        await safe_edit(PLAN_TEXT, kb_price())
        
    elif d in ("pay10", "pay15", "pay30"):
        amt = d.replace("pay", "$")
        await safe_edit(f"━━━━━━━━━━━━━━━━━━━━\nPAYMENT - {amt}\n━━━━━━━━━━━━━━━━━━━━\n\nThe payment method or address is uploaded soon.", kb_payment())
        
    elif d == "mgates":
        await safe_edit("SELECT A GATE → CATEGORY\n━━━━━━━━━━━━━━━━━━━━", kb_gate_category())
        
    elif d == "mauth":
        await safe_edit("SELECT AUTH GATE →", kb_auth_gates())
        
    elif d == "mcharge":
        await safe_edit("SELECT CHARGE GATE →", kb_charge_gates())
        
    elif d == "iau":
        await safe_edit("STRIPE AUTH\n━━━━━━━━━━━━━━━━━━━━\n\nPASTE YOUR TEXT HERE", kb_back("mauth"))
        
    elif d == "ib3":
        await safe_edit("BRAINTREE AUTH\n━━━━━━━━━━━━━━━━━━━━\n\nPASTE YOUR TEXT HERE", kb_back("mauth"))
        
    elif d == "ichk":
        await safe_edit("STRIPE CHARGE\n━━━━━━━━━━━━━━━━━━━━\n\nPASTE YOUR TEXT HERE", kb_back("mcharge"))
        
    elif d == "ipp":
        await safe_edit("PAYPAL CHARGE\n━━━━━━━━━━━━━━━━━━━━\n\nPASTE YOUR TEXT HERE", kb_back("mcharge"))
        
    elif d == "ish":
        await safe_edit("SHOPIFY CHARGE\n━━━━━━━━━━━━━━━━━━━━\n\nPASTE YOUR TEXT HERE", kb_back("mcharge"))
        
    elif d == "ipyu":
        await safe_edit("PAYU CHARGE\n━━━━━━━━━━━━━━━━━━━━\n\nPASTE YOUR TEXT HERE", kb_back("mcharge"))

async def on_start(app):
    print("🦇 Batman Bot Initializing...")
    try:
        await app.bot.delete_webhook(drop_pending_updates=True)
        await asyncio.sleep(1)
    except Exception: pass

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 SAFE KILLBOT & NEW ONBOT COMMAND
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_killbot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data['maintenance'] = True
    await update.message.reply_text("🛑 Maintenance Mode ON.\nBot is now paused for users.\n\nType /onbot to resume.", parse_mode="HTML")

async def cmd_onbot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data['maintenance'] = False
    await update.message.reply_text("✅ Maintenance Mode OFF.\nBot is now online for users!", parse_mode="HTML")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    if isinstance(context.error, Conflict): return
    logging.error(f"Exception: {context.error}")

def main():
    app = Application.builder().token(BOT_TOKEN).post_init(on_start).build()
    app.add_error_handler(error_handler)

    app.add_handler(MessageHandler(filters.ALL, maintenance_check), group=-1)

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("buy", cmd_plan))
    app.add_handler(CommandHandler("plan", cmd_plan))
    app.add_handler(CommandHandler("bin", cmd_bin))
    app.add_handler(CommandHandler("rm", cmd_rm))
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 🦇 ALL 5 GATE COMMANDS FULLY CONNECTED
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    app.add_handler(CommandHandler("chk", cmd_chk))
    app.add_handler(CommandHandler("pp", cmd_pp))
    app.add_handler(CommandHandler("sh", cmd_sh))
    app.add_handler(CommandHandler("pyu", cmd_pyu))
    app.add_handler(CommandHandler("b3", cmd_b3))

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
    app.add_handler(CommandHandler("delcode", cmd_delcode))
    app.add_handler(CommandHandler("seturl", cmd_seturl))
    app.add_handler(CommandHandler("geturl", cmd_geturl))
    
    app.add_handler(CommandHandler("killbot", cmd_killbot))
    app.add_handler(CommandHandler("onbot", cmd_onbot))

    for cmd, func in [("onchk", cmd_onchk), ("offchk", cmd_offchk), ("onpp", cmd_onpp), ("offpp", cmd_offpp), ("onsh", cmd_onsh), ("offsh", cmd_offsh), ("onpyu", cmd_onpyu), ("offpyu", cmd_offpyu), ("onb3", cmd_onb3), ("offb3", cmd_offb3)]:
        app.add_handler(CommandHandler(cmd, func))

    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, anti_ad_filter))
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, anti_ad_filter))

    print("🦇 Online!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
