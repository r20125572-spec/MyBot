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
    txt += "\n━━━━━━━━━━━━━━━━━━━━"
    try: await status.edit_text(txt, parse_mode="HTML", disable_web_page_preview=True)
    except: pass

async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(PLAN_TEXT, parse_mode="HTML", reply_markup=kb_price())

async def cmd_allcm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    await update.message.reply_text(f"BATMAN BOT - ALL COMMANDS\n━━━━━━━━━━━━━━━━━━\nVersion: {VERSION}\n━━━━━━━━━━━━━━━━━━\n\nUSER COMMANDS\n━━━━━━━━━━━━━━━━━━\n/start /plan /bin\n/chk /pp /sh /pyu /b3 /rm\n\nOWNER COMMANDS\n━━━━━━━━━━━━━━━━━━\n/info /allcm /gen\n/key10 /key20 /key30\n/sub /resub /allplans\n/oneday /threeday\n/seturl /geturl\n/onchk /offchk /onpp /offpp\n/onsh /offsh /onpyu /offpyu\n/killbot\n━━━━━━━━━━━━━━━━━━", parse_mode="HTML")

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
    udata = context.bot_data.get('user_data', {}).get(str(uid), {})
    raw_plan = udata.get('plan', 'TRIAL').upper(); expires = udata.get('expires', 0); now = time.time()
    if raw_plan != 'TRIAL' and expires <= now: raw_plan = 'TRIAL'
    
    plan_str = get_styled_plan(raw_plan)
    credits = "∞" if raw_plan != 'TRIAL' else f"{udata.get('credits', 150)}/150"
    txt = (f"━━━━━━━━━━━━━━━━━━━━\n🦇 USER INFO\n━━━━━━━━━━━━━━━━━━━━\n\nName ➺ {name}\nUsername ➺ @{username}\nUser ID ➺ <code>{uid}</code>\nJoined Bot ➺ {udata.get('joined', 'N/A')}\nPlan ➺ {plan_str}\nCredits ➺ {credits}\n")
    if raw_plan != 'TRIAL' and expires > now:
        txt += f"Expires ➺ {datetime.fromtimestamp(expires).strftime('%Y-%m-%d %H:%M')}\nRemaining ➺ {int((expires - now) / 86400)} Days {int(((expires - now) % 86400) / 3600)} Hrs\n"
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
    ud = context.bot_data.setdefault('user_data', {}); uid_str = str(uid)
    if uid_str not in ud: ud[uid_str] = {"name": "User", "joined": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "credits": 150, "plan": "TRIAL", "expires": 0}
    ud[uid_str]["plan"] = plan; ud[uid_str]["expires"] = time.time() + (days * 86400)
    receipt = await send_activation_msg(uid, plan, days, context)
    await update.message.reply_text(f"✅ Granted {days} Days ({get_styled_plan(plan)}) to <code>{uid}</code>\nRᴇᴄᴇɪᴘᴛ ➺ <code>{receipt}</code>", parse_mode="HTML")

async def cmd_oneday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args: await update.message.reply_text("❌ Usage: /oneday <user_id>", parse_mode="HTML"); return
    uid = await resolve_user(context.args[0], context)
    if not uid: await update.message.reply_text("❌ User not found.", parse_mode="HTML"); return
    await _grant_premium(uid, "core", 1, update, context)

async def cmd_threeday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args: await update.message.reply_text("❌ Usage: /threeday <user_id>", parse_mode="HTML"); return
    uid = await resolve_user(context.args[0], context)
    if not uid: await update.message.reply_text("❌ User not found.", parse_mode="HTML"); return
    await _grant_premium(uid, "core", 3, update, context)

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
    ud = context.bot_data.setdefault('user_data', {}); uid_str = str(uid)
    if uid_str in ud: ud[uid_str]["plan"] = "TRIAL"; ud[uid_str]["expires"] = 0; await update.message.reply_text(f"✅ Removed premium from <code>{uid}</code>", parse_mode="HTML")
    else: await update.message.reply_text("❌ User not found.", parse_mode="HTML")

async def cmd_allplans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    users = context.bot_data.get('user_data', {}); txt = "🦇 ACTIVE PLANS\n━━━━━━━━━━━━━━━━━━━━\n\n"; found = False; now = time.time()
    for uid, data in users.items():
        exp = data.get('expires', 0)
        if data.get('plan', 'TRIAL') != 'TRIAL' and exp > now:
            found = True; remaining = int((exp - now) / 86400)
            txt += f"ID: <code>{uid}</code>\nPlan: {get_styled_plan(data.get('plan', 'TRIAL'))}\nCredits: ∞\nRemaining: {remaining} Days\nExp: {datetime.fromtimestamp(exp).strftime('%Y-%m-%d %H:%M')}\n━━━━━━━━━━━━━━━━━━━━\n"
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
    code = context.args[0].upper(); codes, keys = context.bot_data.get('codes', {}), context.bot_data.get('keys', {}); uid = str(update.effective_user.id)
    ud = context.bot_data.setdefault('user_data', {})
    if uid not in ud: ud[uid] = {"name": "User", "credits": 150, "plan": "TRIAL", "expires": 0}
    if code in codes and not codes[code]['used']:
        codes[code]['used'] = True; ud[uid]["credits"] += codes[code]['value']
        await update.message.reply_text(f"✅ Redeemed! Added {codes[code]['value']} credits.\nNew Balance: {ud[uid]['credits']}/150", parse_mode="HTML")
    elif code in keys and not keys[code]['used']:
        keys[code]['used'] = True; p, d = keys[code]['plan'], keys[code]['days']
        ud[uid]["plan"] = p; ud[uid]["expires"] = time.time() + (d * 86400)
        receipt = await send_activation_msg(int(uid), p, d, context)
        await update.message.reply_text(f"✅ Activated {get_styled_plan(p)} for {d} days.\nRᴇᴄᴇɪᴘᴛ ➺ <code>{receipt}</code>", parse_mode="HTML")
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

async def cmd_seturl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if len(context.args) < 2:
        await update.message.reply_text("❌ Usage: /seturl <gate> <url>\n/seturl chk remove", parse_mode="HTML"); return
    gate = context.args[0].lower(); url = " ".join(context.args[1:])
    if gate not in GATE_NAMES:
        await update.message.reply_text(f"❌ Unknown gate. Valid: chk, pp, sh, pyu, b3", parse_mode="HTML"); return
    if url.lower() == "remove":
        context.bot_data.pop(f'gate_url_{gate}', None)
        await update.message.reply_text(f"✅ Removed {GATE_NAMES[gate]} override.", parse_mode="HTML"); return
    context.bot_data[f'gate_url_{gate}'] = url
    await update.message.reply_text(f"✅ {GATE_NAMES[gate]} override set.\n<code>{url}</code>", parse_mode="HTML")

async def cmd_geturl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    txt = "🦇 GATE API URLs\n━━━━━━━━━━━━━━━━━━━━\n\n"
    for gate, name in GATE_NAMES.items():
        override = context.bot_data.get(f'gate_url_{gate}', '')
        config_url = GATE_URLS.get(gate, '')
        active = override if override else config_url
        source = "⚡ Override" if override else "📝 Config"
        status = "🟢 ON" if context.bot_data.get(f'{gate}_on', True) else "🔴 OFF"
        txt += f"{name} [{status}] [{source}]\n<code>{active or '❌ Not set'}</code>\n\n"
    txt += "━━━━━━━━━━━━━━━━━━━━"
    await update.message.reply_text(txt, parse_mode="HTML")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇🦇🦇 GATE COMMANDS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def parse_card(text: str) -> Optional[dict]:
    text = text.strip()
    for sep in ['|', '/', ' ']:
        if sep in text:
            parts = [p.strip() for p in text.split(sep)]
            if len(parts) >= 4:
                cc = parts[0].replace(' ', ''); mm = parts[1].zfill(2)
                yy = parts[2][-2:].zfill(2); cvv = parts[3]
                if cc.isdigit() and 13 <= len(cc) <= 19 and mm.isdigit() and yy.isdigit() and cvv.isdigit():
                    return {"cc": cc, "mm": mm, "yy": yy, "cvv": cvv}
    return None

async def run_gate_api(gate: str, card: dict, context: ContextTypes.DEFAULT_TYPE) -> dict:
    api_url = context.bot_data.get(f'gate_url_{gate}', '')
    if not api_url: api_url = GATE_URLS.get(gate, '')
    if not api_url:
        return {"status": "error", "message": f"{GATE_NAMES[gate]} gate is not configured."}
    if not context.bot_data.get(f'{gate}_on', True):
        return {"status": "error", "message": f"{GATE_NAMES[gate]} gate is temporarily disabled."}
    site = GATE_SITES.get(gate, "")
    payload = json.dumps({"cc": card["cc"], "mm": card["mm"], "yy": card["yy"], "cvv": card["cvv"], "gate": gate, "site": site}).encode('utf-8')
    req = urllib.request.Request(api_url, data=payload, headers={"Content-Type": "application/json", "User-Agent": "BatCardChk/4.1", "Accept": "application/json"})
    try:
        loop = asyncio.get_running_loop()
        def do_req():
            with urllib.request.urlopen(req, timeout=API_TIMEOUT) as r:
                raw = r.read().decode('utf-8', errors='ignore')
                try: return json.loads(raw)
                except: return {"status": "unknown", "message": raw[:500]}
        result = await loop.run_in_executor(None, do_req)
        if isinstance(result, dict): return result
        return {"status": "unknown", "message": str(result)[:500]}
    except urllib.error.HTTPError as e:
        body = ""
        try: body = e.read().decode('utf-8', errors='ignore')[:500]
        except: pass
        try:
            err_json = json.loads(body)
            return {"status": "error", "message": err_json.get("message", err_json.get("msg", body))}
        except: return {"status": "error", "message": f"API Error {e.code}"}
    except urllib.error.URLError as e:
        return {"status": "error", "message": f"Cannot reach server — {str(e.reason)[:150]}"}
    except TimeoutError:
        return {"status": "error", "message": "Server took too long to respond."}
    except Exception as e:
        return {"status": "error", "message": f"Connection failed — {str(e)[:150]}"}

def format_gate_result(gate: str, data: dict, card: dict) -> str:
    status = str(data.get("status", "")).lower()
    if not status: status = str(data.get("result", "")).lower()
    if not status: status = str(data.get("response", "")).lower()
    if not status: status = str(data.get("code", "")).lower()
    msg = data.get("message", "") or data.get("msg", "") or data.get("info", "") or data.get("description", "") or ""
    if isinstance(msg, (dict, list)): msg = json.dumps(msg, ensure_ascii=False)
    if any(w == status for w in ("approved", "live", "charged", "success", "1", "true", "approved_charged", "valid", "alive")) or status.startswith("approv"):
        icon, result = "✅", "APPROVED ✅"
    elif any(w == status for w in ("declined", "dead", "rejected", "fail", "0", "false", "declined_dead", "invalid", "die")) or status.startswith("declin") or status.startswith("reject"):
        icon, result = "❌", "DECLINED ❌"
    elif "cvv" in status and "mismatch" in status:
        icon, result = "⚠️", "CVV MISMATCH ⚠️"
    elif status == "error":
        masked = f"{card['cc'][:6]}******{card['cc'][-4:]}"
        return (f"❌ {GATE_NAMES[gate].upper()} GATE\n━━━━━━━━━━━━━━━━━━━━\n\nCard ➺ <code>{masked}</code>\nResult ➺ FAILED ❌\nReason ➺ {msg if msg else 'Unknown error'}\n\n━━━━━━━━━━━━━━━━━━━━")
    else:
        icon, result = "⚠️", f"RESPONSE: {(status or 'UNKNOWN').upper()}"
    masked = f"{card['cc'][:6]}******{card['cc'][-4:]}"
    txt = (f"{icon} {GATE_NAMES[gate].upper()} GATE\n━━━━━━━━━━━━━━━━━━━━\n\nCard ➺ <code>{masked}</code>\nResult ➺ {result}\n")
    if msg and msg.lower() not in ("none", "", "null"): txt += f"Info ➺ {msg[:300]}\n"
    for key in ["bin_info", "charge_id", "transaction_id", "bank", "country", "type", "brand", "funding", "site"]:
        val = data.get(key)
        if val and str(val).lower() not in ("none", "null", ""): txt += f"{key.title()} ➺ {val}\n"
    txt += "\n━━━━━━━━━━━━━━━━━━━━"
    return txt

async def handle_gate_cmd(gate: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user; uid_str = str(user.id)
    if not context.bot_data.get(f'{gate}_on', True):
        await update.message.reply_text(f"❌ {GATE_NAMES[gate]} gate is currently OFF.", parse_mode="HTML"); return
    if not context.args:
        if gate == "pp":
            usage_msg = "⚠️ Uꜱᴀɢᴇ: Rᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇꜱꜱᴀɢᴇ ᴡɪᴛʜ ᴄᴀʀᴅꜱ ᴏʀ ꜱᴇɴᴅ\n/pp email|pass"
        else:
            usage_msg = f"⚠️ Uꜱᴀɢᴇ: Rᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇꜱꜱᴀɢᴇ ᴡɪᴛʜ ᴄᴀʀᴅꜱ ᴏʀ ꜱᴇɴᴅ\n/{gate} cc|mm|yy|cvv"
        await update.message.reply_text(usage_msg, parse_mode="HTML"); return
    card = parse_card(" ".join(context.args))
    if not card:
        await update.message.reply_text("❌ Invalid card format!\n\ncc|mm|yy|cvv\ncc/mm/yy/cvv\ncc mm yy cvv", parse_mode="HTML"); return
    if not is_premium_active(user.id, context):
        ud = context.bot_data.setdefault('user_data', {}).get(uid_str, {})
        cost = GATE_COST.get(gate, 1); credits = ud.get('credits', 150)
        if credits < cost:
            await update.message.reply_text(f"❌ Not enough credits!\n\nNeeded: {cost}\nBalance: {credits}/150\n\nUse /rm <code> or buy premium.", parse_mode="HTML"); return
        ud['credits'] = credits - cost
    masked = f"{card['cc'][:6]}******{card['cc'][-4:]}"
    status_msg = await update.message.reply_text(f"⏳ Checking <code>{masked}</code> on {GATE_NAMES[gate]}...\n━━━━━━━━━━━━━━━━━━━━", parse_mode="HTML")
    result = await run_gate_api(gate, card, context)
    txt = format_gate_result(gate, result, card)
    try: await status_msg.edit_text(text=txt, parse_mode="HTML")
    except:
        try: await status_msg.delete()
        except: pass
        await update.message.reply_text(text=txt, parse_mode="HTML")

async def cmd_chk(update: Update, context: ContextTypes.DEFAULT_TYPE): await handle_gate_cmd("chk", update, context)
async def cmd_pp(update: Update, context: ContextTypes.DEFAULT_TYPE): await handle_gate_cmd("pp", update, context)
async def cmd_sh(update: Update, context: ContextTypes.DEFAULT_TYPE): await handle_gate_cmd("sh", update, context)
async def cmd_pyu(update: Update, context: ContextTypes.DEFAULT_TYPE): await handle_gate_cmd("pyu", update, context)
async def cmd_b3(update: Update, context: ContextTypes.DEFAULT_TYPE): await handle_gate_cmd("b3", update, context)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 100% BULLETPROOF CALLBACK SYSTEM
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    d = q.data
    try: await q.answer()
    except: pass
    
    async def safe_edit(t, kb):
        try:
            if q.message.photo:
                try: await q.message.delete()
                except: pass
                await context.bot.send_message(chat_id=q.message.chat_id, text=t, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
            else:
                await q.edit_message_text(text=t, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
        except Exception:
            try:
                await context.bot.send_message(chat_id=q.message.chat_id, text=t, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
            except: pass

    if d == "verify_join":
        if await is_joined(q.from_user.id, context):
            await safe_edit(ui_profile(q.from_user, context), kb_main())
            asyncio.ensure_future(_check_and_kick_if_not_joined(q.from_user.id, context, q.message.chat_id))
        else:
            await q.answer("❌ Join Group & Channel first!", show_alert=True)
        return

    if d.startswith("use_"):
        cmd = d.replace("use_", "")
        gate_name = GATE_NAMES.get(cmd, cmd.upper())
        if cmd == "pp":
            usage_text = f"━━━━━━━━━━━━━━━━━━━━\n⚡ {gate_name.upper()} GATE\n━━━━━━━━━━━━━━━━━━━━\n\n⚠️ Uꜱᴀɢᴇ: Rᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇꜱꜱᴀɢᴇ ᴡɪᴛʜ ᴄᴀʀᴅꜱ ᴏʀ ꜱᴇɴᴅ\n<code>/{cmd} email|pass</code>"
        else:
            usage_text = f"━━━━━━━━━━━━━━━━━━━━\n⚡ {gate_name.upper()} GATE\n━━━━━━━━━━━━━━━━━━━━\n\n⚠️ Uꜱᴀɢᴇ: Rᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇꜱꜱᴀɢᴇ ᴡɪᴛʜ ᴄᴀʀᴅꜱ ᴏʀ ꜱᴇɴᴅ\n<code>/{cmd} cc|mm|yy|cvv</code>"
        await safe_edit(usage_text, kb_back("mgates"))
        return

    if d == "bmain":
        await safe_edit(ui_profile(q.from_user, context), kb_main())
        
    elif d == "mprice":
        await safe_edit(PLAN_TEXT, kb_price())
        
    elif d in ("pay10", "pay15", "pay30"):
        if d == "pay10":
            amt, plan_name, days = "10$", "✨ Cᴏʀᴇ ✨", "7"
        elif d == "pay15":
            amt, plan_name, days = "15$", "⭐ Eʟɪᴛᴇ ⭐", "15"
        else:
            amt, plan_name, days = "30$", "👑 Rᴏᴏᴛ 👑", "30"
        await safe_edit(
            f"━━━━━━━━━━━━━━━━━━━━\nPAYMENT - {amt}\n━━━━━━━━━━━━━━━━━━━━\n\nAᴄᴄᴇꜱꜱ ➺ {plan_name}\nDᴜʀᴀᴛɪᴏɴ ➺ {days} Dᴀʏꜱ\nCʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ\nTᴏᴛᴀʟ ➺ {amt}\n\n━━━━━━━━━━━━━━━━━━━━\n⏳ Payment coming soon.\n\nContact <a href='{DEV_LINK}'>Batman</a> for manual payment.",
            kb_back("mprice")
        )
        
    elif d == "mgates":
        await safe_edit(
            "SELECT A GATE → CATEGORY\n━━━━━━━━━━━━━━━━━━━━",
            kb_gate_category()
        )
        
    elif d == "mauth":
        await safe_edit("SELECT AUTH GATE →", kb_auth_gates())
        
    elif d == "mcharge":
        await safe_edit("SELECT CHARGE GATE →", kb_charge_gates())
        
    elif d == "iau":
        await safe_edit(
            "━━━━━━━━━━━━━━━━━━━━\nGATE: STRIPE AUTH\n━━━━━━━━━━━━━━━━━━━━\n\nSITES: 16\nHEALTH: 100%\nSTATUS: 🟢 ONLINE",
            kb_gate_info("chk", "mauth")
        )
    elif d == "ib3":
        await safe_edit(
            "━━━━━━━━━━━━━━━━━━━━\nGATE: BRAINTREE AUTH\n━━━━━━━━━━━━━━━━━━━━\n\nSITES: 2\nHEALTH: 100%\nSTATUS: 🟢 ONLINE",
            kb_gate_info("b3", "mauth")
        )
    elif d == "ichk":
        await safe_edit(
            "━━━━━━━━━━━━━━━━━━━━\nGATE: STRIPE CHARGE\n━━━━━━━━━━━━━━━━━━━━\n\nSITES: 4\nHEALTH: 100%\nSTATUS: 🟢 ONLINE",
            kb_gate_info("chk", "mcharge")
        )
    elif d == "ipp":
        await safe_edit(
            "━━━━━━━━━━━━━━━━━━━━\nGATE: PAYPAL CHARGE\n━━━━━━━━━━━━━━━━━━━━\n\nSITES: 7\nHEALTH: 100%\nSTATUS: 🟢 ONLINE",
            kb_gate_info("pp", "mcharge")
        )
    elif d == "ish":
        await safe_edit(
            "━━━━━━━━━━━━━━━━━━━━\nGATE: SHOPIFY CHARGE\n━━━━━━━━━━━━━━━━━━━━\n\nSITES: 10\nHEALTH: 100%\nSTATUS: 🟢 ONLINE",
            kb_gate_info("sh", "mcharge")
        )
    elif d == "ipyu":
        await safe_edit(
            "━━━━━━━━━━━━━━━━━━━━\nGATE: PAYU CHARGE\n━━━━━━━━━━━━━━━━━━━━\n\nSITES: 1\nHEALTH: 100%\nSTATUS: 🟢 ONLINE",
            kb_gate_info("pyu", "mcharge")
        )

async def _check_and_kick_if_not_joined(user_id, chat_id, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not await is_joined(user_id, context):
            try: await context.bot.send_message(chat_id=chat_id, text="❌ You didn't join both channels! Access Denied.", parse_mode="HTML")
            except: pass
    except: pass

async def on_start(app):
    print("🦇 Batman Bot Initializing...")
    try:
        await app.bot.delete_webhook(drop_pending_updates=True)
        await asyncio.sleep(1) # Prevents 409 conflict on startup
    except Exception as e:
        print(f"Webhook clear skipped: {e}")

async def cmd_killbot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    await update.message.reply_text("🛑 Killing bot...", parse_mode="HTML")
    os.kill(os.getpid(), signal.SIGTERM)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Completely ignore 409 Conflict to stop console spam
    if isinstance(context.error, Conflict):
        return
    logging.error(f"Exception: {context.error}")

def main():
    print("🦇 Downloading photo...")
    download_photo()
    if DOWNLOADED_PHOTO_PATH:
        print(f"🦇 Photo ready: {DOWNLOADED_PHOTO_PATH}")
    else:
        print("❌ NO PHOTO — join page will be text only")

    app = Application.builder().token(BOT_TOKEN).post_init(on_start).build()
    app.add_error_handler(error_handler)

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("buy", cmd_plan))
    app.add_handler(CommandHandler("plan", cmd_plan))
    app.add_handler(CommandHandler("bin", cmd_bin))
    app.add_handler(CommandHandler("rm", cmd_rm))
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

    for cmd, func in [("onchk", cmd_onchk), ("offchk", cmd_offchk), ("onpp", cmd_onpp), ("offpp", cmd_offpp), ("onsh", cmd_onsh), ("offsh", cmd_offsh), ("onpyu", cmd_onpyu), ("offpyu", cmd_offpyu)]:
        app.add_handler(CommandHandler(cmd, func))

    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, anti_ad_filter))
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, anti_ad_filter))

    print("🦇 Online!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
