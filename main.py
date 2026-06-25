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
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.error import Conflict

from config import (
    BOT_TOKEN, OWNER_ID, VERSION, DEV_LINK, BOT_PHOTO, BOT_PHOTO_URL,
    GATE_URLS, GATE_SITES, API_TIMEOUT
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 HARDCODED LINKS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CHANNEL_USERNAME = "@Batcardchk"
GROUP_USERNAME = "@batcardchkGroup"
CHANNEL_LINK = "https://t.me/Batcardchk"
GROUP_LINK = "https://t.me/batcardchkGroup"
SUPPORT_LINK = "https://t.me/cardchkSupport"

GATE_COST = {"chk": 1, "pp": 1, "sh": 2, "pyu": 1, "b3": 1}
GATE_NAMES = {"chk": "Stripe", "pp": "PayPal", "sh": "Shopify", "pyu": "PayU", "b3": "Braintree"}

# Silence httpx and telegram spam logs
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

DOWNLOADED_PHOTO_PATH = None

PLAN_TEXT = """Aᴄᴄᴇꜱꜱ ➺ Cᴏʀᴇ 🎀
Sᴘᴀɴ ➺ [7 Dᴀʏꜱ]
Cʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ
Pʀɪᴄᴇ ➺ 10$ ━━━━━━━━━━━━━━━━
Aᴄᴄᴇꜱꜱ ➺ Eʟɪᴛᴇ ⭐️
Sᴘᴀɴ ➺ [15 Dᴀʏꜱ]
Cʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ
Pʀɪᴄᴇ ➺ 15$ ━━━━━━━━━━━━━━━━
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

async def anti_ad_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or msg.from_user.id == OWNER_ID: return
    text = (msg.text or msg.caption or "").lower()
    if not text: return
    if any(w in text for w in BLOCK_WORDS):
        try: await msg.delete()
        except: pass

async def is_joined(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    async def check(chat_id):
        try: return (await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)).status not in ('left', 'kicked')
        except: return False
    return await check(CHANNEL_USERNAME) and await check(GROUP_USERNAME)

def gen_code(length=10): return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))
def gen_receipt(): return f"BATCARD-{random.randint(100000, 999999)}-CHK"

def is_premium_active(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    ud = context.bot_data.get('user_data', {}).get(str(user_id), {})
    return ud.get('plan', 'TRIAL') != 'TRIAL' and ud.get('expires', 0) > time.time()

def download_photo():
    global DOWNLOADED_PHOTO_PATH
    for name in ["batman.jpg", "batman.png", "batman.jpeg", "batman.webp", "BATMAN.jpg", "BATMAN.png", "photo.jpg", "photo.png"]:
        if os.path.isfile(name):
            DOWNLOADED_PHOTO_PATH = name
            print(f"🦇 Found local photo: {name}")
            return
    if BOT_PHOTO and os.path.isfile(BOT_PHOTO):
        DOWNLOADED_PHOTO_PATH = BOT_PHOTO
        print(f"🦇 Found BOT_PHOTO file: {BOT_PHOTO}")
        return
    url_to_try = BOT_PHOTO_URL or (BOT_PHOTO if BOT_PHOTO and BOT_PHOTO.startswith("http") else "")
    if url_to_try:
        print(f"🦇 Downloading photo from: {url_to_try[:80]}...")
        try:
            req = urllib.request.Request(url_to_try, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            save_path = os.path.join(tempfile.gettempdir(), "batman_bot_photo.jpg")
            with open(save_path, 'wb') as f:
                f.write(data)
            DOWNLOADED_PHOTO_PATH = save_path
            print(f"🦇 Photo downloaded! Saved to: {save_path} ({len(data)} bytes)")
            return
        except Exception as e:
            print(f"❌ Photo download failed: {e}")
    print("❌ NO PHOTO FOUND — join page will be text only")

def ui_profile(user, context: ContextTypes.DEFAULT_TYPE):
    u = user.username or "None"
    uid_str = str(user.id)
    ud = context.bot_data.get('user_data', {}).get(uid_str, {})
    raw_plan = ud.get('plan', 'TRIAL').upper()
    expires = ud.get('expires', 0)
    now = time.time()
    
    if raw_plan != 'TRIAL' and expires <= now:
        raw_plan = 'TRIAL'; ud['plan'] = 'TRIAL'; ud['expires'] = 0
        
    plan_str = get_styled_plan(raw_plan)
    is_premium = raw_plan != 'TRIAL'
    
    # Format credits like 148/150 for trial, ∞ for premium
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
    uid_str = str(user_id)
    ud = context.bot_data.setdefault('user_data', {}).setdefault(uid_str, {"name": name, "joined": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "credits": 150, "plan": "TRIAL", "expires": 0})
    ud["name"] = name; ud["plan"] = plan; ud["expires"] = time.time() + (days * 86400)
    exp_date = datetime.fromtimestamp(ud["expires"]).strftime('%Y-%m-%d %H:%M')
    styled_plan = get_styled_plan(plan)
    txt = (f"Cᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴꜱ! 🎉 Yᴏᴜʀ ᴀᴄᴄᴇꜱꜱ ʜᴀꜱ ʙᴇᴇɴ ᴀᴄᴛɪᴠᴀᴛᴇᴅ.\n━━━━━━━━━━━━━━━━━━━━\n\nUꜱᴇʀ ➺ {name}\nUꜱᴇʀɴᴀᴍᴇ ➺ @{username}\nAᴄᴄᴇꜱꜱ ➺ {styled_plan}\nDᴜʀᴀᴛɪᴏɴ ➺ {days} Dᴀʏꜱ\nCʀᴇᴅɪᴛꜱ Aᴅᴅᴇᴅ ➺ ∞\nExᴘɪʀᴇꜱ ➺ {exp_date}\nRᴇᴄᴇɪᴘᴛ ID ➺ <code>{receipt}</code>\n\n━━━━━━━━━━━━━━━━━━━━\nPʟᴇᴀꜱᴇ ꜱᴀᴠᴇ ᴛʜɪꜱ ʀᴇᴄᴇɪᴘᴛ ID.")
    try: await context.bot.send_message(chat_id=user_id, text=txt, parse_mode="HTML")
    except: pass
    return receipt

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 CLASSIC CLEAN KEYBOARDS (EXACTLY LIKE PHOTO)
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
        [InlineKeyboardButton("10$ PAY", callback_data="pay10"), InlineKeyboardButton("15$ PAY", callback_data="pay15"), InlineKeyboardButton("30$ PAY", callback_data="pay30")],
        [InlineKeyboardButton("« BACK", callback_data="bmain")]
    ])

def kb_gate_info(cmd, back_cb):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ USE GATE", callback_data=f"use_{cmd}")],
        [InlineKeyboardButton("« BACK", callback_data=back_cb)]
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
# 🦇 /start
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ud = context.bot_data.setdefault('user_data', {}); uid = str(user.id)
    if uid not in ud: ud[uid] = {"name": user.first_name, "joined": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "credits": 150, "plan": "TRIAL", "expires": 0}

    if await is_joined(user.id, context):
        await update.message.reply_text(
            text=ui_profile(user, context), parse_mode="HTML",
            reply_markup=kb_main(), disable_web_page_preview=True
        )
    else:
        caption = (
            "🦇 BATMAN CARD CHECKER 🦇\n\n"
            "Access Required\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Join both channels to\n"
            "unlock the bot.\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        photo_sent = False
        if DOWNLOADED_PHOTO_PATH and os.path.isfile(DOWNLOADED_PHOTO_PATH):
            try:
                with open(DOWNLOADED_PHOTO_PATH, 'rb') as f:
                    await update.message.reply_photo(photo=f, caption=caption, parse_mode="HTML", reply_markup=kb_force())
                photo_sent = True
            except Exception as e:
                print(f"⚠️ Send downloaded photo failed: {e}")
        if not photo_sent:
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
    txt += "\n━━━━━━━━━━━━━━
