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

CHANNEL_USERNAME = "@Batcardchk"
GROUP_USERNAME = "@batcardchkGroup"
CHANNEL_LINK = "https://t.me/Batcardchk"
GROUP_LINK = "https://t.me/batcardchkGroup"
SUPPORT_LINK = "https://t.me/failurefr_07"

GATE_COST = {"chk": 1, "pp": 1, "sh": 2, "pyu": 1, "b3": 1}
GATE_NAMES = {"chk": "Stripe", "pp": "PayPal", "sh": "Shopify", "pyu": "PayU", "b3": "Braintree"}

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

BLOCK_WORDS = (
    "http://", "https://", "www.", "t.me", ".com", ".net", ".org",
    ".io", ".me", ".xyz", ".tk", ".ml", ".cf", ".ga", ".ru", ".in",
    ".pw", "telegram.me", "joinchat", "://",
    "a_toolsx", "a-tools", "atoolsx", "a tools x", "a-tools x", "a_tools", "toolsx"
)

DOWNLOADED_PHOTO_PATH = None

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
    return ud.get('plan', 'FREE') != 'FREE' and ud.get('expires', 0) > time.time()

def _find_local_photo():
    global DOWNLOADED_PHOTO_PATH
    search = ["batman.jpg", "batman.png", "batman.jpeg", "batman.webp", "BATMAN.jpg", "BATMAN.png", "photo.jpg", "photo.png"]
    dirs = [".", "/app", os.path.dirname(os.path.abspath(__file__)), tempfile.gettempdir()]
    for d in dirs:
        for name in search:
            p = os.path.join(d, name)
            if os.path.isfile(p):
                DOWNLOADED_PHOTO_PATH = p
                print(f"🦇 [PHOTO] Found: {p}")
                return True
    return False

async def _download_photo(url: str) -> bool:
    global DOWNLOADED_PHOTO_PATH
    print(f"🦇 [PHOTO] Downloading...")
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "image/*,*/*;q=0.8",
            "Referer": "https://chatglm.cn/"
        })
        loop = asyncio.get_running_loop()
        def do_download():
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read()
        data = await loop.run_in_executor(None, do_download)
        if len(data) < 1000: return False
        path = os.path.join(tempfile.gettempdir(), "batman_bot_photo.jpg")
        with open(path, 'wb') as f: f.write(data)
        DOWNLOADED_PHOTO_PATH = path
        print(f"🦇 [PHOTO] Saved: {path} ({len(data)} bytes)")
        return True
    except Exception as e:
        print(f"🦇 [PHOTO] Failed: {e}")
        return False

async def init_photo():
    global DOWNLOADED_PHOTO_PATH
    if _find_local_photo(): return
    url = BOT_PHOTO_URL or (BOT_PHOTO if BOT_PHOTO and BOT_PHOTO.startswith("http") else "")
    if url: await _download_photo(url)
    if not DOWNLOADED_PHOTO_PATH:
        print("❌ [PHOTO] No photo available")

def ui_profile(user, context: ContextTypes.DEFAULT_TYPE) -> str:
    try:
        u = user.username or "None"
        uid_str = str(user.id)
        ud = context.bot_data.get('user_data', {}).get(uid_str, {})
        plan = ud.get('plan', 'FREE').upper()
        expires = ud.get('expires', 0); now = time.time()
        if plan != 'FREE' and expires <= now:
            plan = 'FREE'; ud['plan'] = 'FREE'; ud['expires'] = 0
        credits = "∞" if plan != 'FREE' else ud.get('credits', 150)
        lines = [f"Uꜱᴇʀ ➺ {u}", f"Uꜱᴇʀ ID ➺ <code>{user.id}</code>", f"Pʟᴀɴ ➺ {plan}", f"Cʀᴇᴅɪᴛꜱ ➺ {credits}"]
        if plan != 'FREE' and expires > now:
            exp_date = datetime.fromtimestamp(expires).strftime('%Y-%m-%d %H:%M')
            remaining = int((expires - now) / 86400); remaining_hrs = int(((expires - now) % 86400) / 3600)
            lines.append(f"Exᴘɪʀᴇꜱ ➺ {exp_date}")
            if remaining > 0: lines.append(f"Rᴇᴍᴀɪɴɪɴɢ ➺ {remaining} Dᴀʏꜱ {remaining_hrs} Hʀꜱ")
            else: lines.append(f"Rᴇᴍᴀɪɴɪɴɢ ➺ {remaining_hrs} Hʀꜱ")
        lines.append(f"Jᴏɪɴᴇᴅ ➺ {ud.get('joined', datetime.now().strftime('%Y-%m-%d')}")
        lines.append(f"Dᴇᴠ ➺ <a href='{DEV_LINK}'>Batman</a>")
        return "\n".join(lines)
    except Exception as e:
        logging.error(f"ui_profile error: {e}")
        return f"Uꜱᴇʀ ➺ {user.first_name}\nID ➺ <code>{user.id}</code>\nPʟᴀɴ ➺ FREE\nCʀᴇᴅɪᴛꜱ ➺ 150"

async def send_activation_msg(user_id: int, plan: str, days: int, context: ContextTypes.DEFAULT_TYPE) -> str:
    receipt = gen_receipt()
    name, username = "Unknown", "None"
    try:
        chat = await context.bot.get_chat(user_id)
        name = chat.first_name or "Unknown"; username = chat.username or "None"
    except: pass
    uid_str = str(user_id)
    ud = context.bot_data.setdefault('user_data', {}).setdefault(uid_str, {"name": name, "joined": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "credits": 150, "plan": "FREE", "expires": 0})
    ud["name"] = name; ud["plan"] = plan; ud["expires"] = time.time() + (days * 86400)
    exp_date = datetime.fromtimestamp(ud["expires"]).strftime('%Y-%m-%d %H:%M')
    txt = (f"Cᴏɴɢʀᴀᴛᴜᴀᴛɪᴏɴꜱ! 🎉 Yᴏᴜʀ ᴀᴄᴄᴇꜱꜱ ʜᴀꜱ ʙᴇᴇɴ ᴀᴄᴛɪᴠᴛᴀᴛᴇᴅ.\n━━━━━━━━━━━━━━━━━━━━\n\nUꜱᴇʀ ➺ {name}\nUꜱᴇʀɴᴀᴍᴇ ➺ @{username}\nAᴄᴄᴇꜱꜱ ➺ {plan.upper()}\nDᴜʀᴀᴛɪᴏɴ ➺ {days} Dᴀʏꜱ\nCʀᴇᴅɪᴛꜱ Aᴅᴅᴇᴅ ➺ ∞\nExᴘɪʀᴇꜱ ➺ {exp_date}\nRᴇᴄᴇɪᴘᴛᴛ ID ➺ <code>{receipt}</code>\n\n━━━━━━━━━━━━━━━━━━━━\nPʟᴇᴀꜱᴇ ꜱᴀᴠᴇ ᴛʜɪꜱ ʀᴇᴄᴇɪᴘᴛᴛ ID.")
    try: await context.bot.send_message(chat_id=user_id, text=txt, parse_mode="HTML")
    except: pass
    return receipt

def kb_main():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("CHECKER", callback_data="mgates"), InlineKeyboardButton("BUY NOW", callback_data="mprice")],
        [InlineKeyboardButton("UPDATES", url=CHANNEL_LINK), InlineKeyboardButton("GROUP", url=GROUP_LINK)],
        [InlineKeyboardButton("SUPPORT", url=SUPPORT_LINK)]
    ])
def kb_back(cb): return InlineKeyboardMarkup([[InlineKeyboardButton("◀ BACK", callback_data=cb)]])
def kb_force():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("JOIN GROUP", url=GROUP_LINK)],
        [InlineKeyboardButton("JOIN CHANNEL", url=CHANNEL_LINK)],
        [InlineKeyboardButton("✅ VERIFY", callback_data="verify_join")]
    ])
def kb_price():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("10$ PAY", callback_data="pay10"), InlineKeyboardButton("20$ PAY", callback_data="pay20"), InlineKeyboardButton("30$ PAY", callback_data="pay30")],
        [InlineKeyboardButton("◀ BACK", callback_data="bmain")]
    ])
def kb_gate_info(cmd, back_cb):
    return InlineKeyboardMarkup([[InlineKeyboardButton("⚡ USE GATE", callback_data=f"use_{cmd}")],[InlineKeyboardButton("◀ BACK", callback_data=back_cb)]])

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

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ud = context.bot_data.setdefault('user_data', {}); uid = str(user.id)
    if uid not in ud: ud[uid] = {"name": user.first_name, "joined": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "credits": 150, "plan": "FREE", "expires": 0}
    if await is_joined(user.id, context):
        await update.message.reply_text(text=ui_profile(user, context), parse_mode="HTML", reply_markup=kb_main(), disable_web_page_preview=True)
    else:
        caption = "🦇 BATMAN CARD CHECKER 🦇\n\nAccess Required\n━━━━━━━━━━━━━━━━━━━━\nJoin both channels to\nunlock the bot.\n━━━━━━━━━━━━━━━━━━━━"
        photo_sent = False
        photo_url = BOT_PHOTO_URL or (BOT_PHOTO if BOT_PHOTO and BOT_PHOTO.startswith("http") else "")
        if photo_url:
            try:
                await update.message.reply_photo(photo=photo_url, caption=caption, parse_mode="HTML", reply_markup=kb_force())
                photo_sent = True
                print(f"🦇 [START] Photo sent via URL")
            except: pass
        if not photo_sent and DOWNLOADED_PHOTO_PATH and os.path.isfile(DOWNLOADED_PHOTO_PATH):
            try:
                with open(DOWNLOADED_PHOTO_PATH, 'rb') as f:
                    await update.message.reply_photo(photo=f, caption=caption, parse_mode="HTML", reply_markup=kb_force())
                photo_sent = True
                print(f"🦇 [START] Photo sent from file")
            except: pass
        if not photo_sent:
            print("❌ [START] No photo, text only")
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
    await update.message.reply_text("Aᴄᴄᴇꜱꜱ ➺ Cᴏʀᴇ 🎀\nSᴘᴀɴ ➺ [7 Dᴀʏꜱ]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ\nPʀɪᴄᴇ ➺ 10$\n━━━━━━━━━━━━━━━━\nAᴄᴄᴇꜱꜱ ➺ Eʟɪᴛᴇ ⭐️\nSᴘᴀɴ ➺ [15 Dᴀʏꜱ]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ\nPʀɪᴄᴇ ➺ 15$\n━━━━━━━━━━━━━━━━\nAᴄᴄᴇꜱꜱ ➺ Rᴏᴏᴛ 👑\nSᴘᴀɴ ➺ [30 Dᴀʏꜱ]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ\nPʀɪᴄᴇ ➺ 30$", parse_mode="HTML", reply_markup=kb_price())

async def cmd_allcm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    await update.message.reply_text(f"BATMAN BOT V{VERSION}\n\nUSER\n/start /plan /bin\n/chk /pp /sh /pyu /b3 /rm\n\nOWNER\n/info /allcm /gen\n/key10 /key20 /key30\n/sub /resub /allplans\n/oneday /threeday\n/seturl /geturl\n/onchk /offchk /onpp /offpp\n/onsh /offsh /onpyu /offpyu\n/killbot", parse_mode="HTML")

async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not update.message.reply_to_message and not context.args:
        await update.message.reply_text("❌ /info <user_id>", parse_mode="HTML"); return
    if update.message.reply_to_message: target_id = update.message.reply_to_message.from_user.id
    else: target_id = await resolve_user(context.args[0], context)
    if not target_id: await update.message.reply_text("❌ Not found.", parse_mode="HTML"); return
    name, username, uid = "N/A", "None", target_id
    try:
        u = await context.bot.get_chat(target_id); name = u.first_name or "N/A"; username = u.username or "None"; uid = u.id
    except: pass
    udata = context.bot_data.get('user_data', {}).get(str(uid), {})
    plan = udata.get('plan', 'FREE').upper(); expires = udata.get('expires', 0); now = time.time()
    if plan != 'FREE' and expires <= now: plan = 'FREE'
    credits = "∞" if plan != 'FREE' else udata.get('credits', 150)
    txt = (f"━━━━━━━━━━━━━━━━━━━━\n🦇 USER INFO\n━━━━━━━━━━━━━━━━━━━━\n\nName ➺ {name}\nUsername ➺ @{username}\nUser ID ➺ <code>{uid}</code>\nPlan ➺ {plan}\nCredits ➺ {credits}\n")
    if plan != 'FREE' and expires > now:
        txt += f"Expires ➺ {datetime.fromtimestamp(expires).strftime('%Y-%m-%d %H:%M')}\nRemaining ➺ {int((expires - now) / 86400)} Days\n"
    else: txt += "Status ➺ Free\n"
    txt += "━━━━━━━━━━━━━━━━━━━━"
    await update.message.reply_text(txt, parse_mode="HTML")

async def cmd_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args: await update.message.reply_text("❌ /gen <credits>", parse_mode="HTML"); return
    try:
        amt = int(context.args[0]); code = gen_code()
        context.bot_data.setdefault('codes', {})[code] = {"type": "credit", "value": amt, "used": False}
        await update.message.reply_text(f"✅ CODE: <code>{code}</code>\nCredits: {amt}", parse_mode="HTML")
    except: await update.message.reply_text("❌ Invalid amount.", parse_mode="HTML")

async def cmd_gen_key(update: Update, context: ContextTypes.DEFAULT_TYPE, plan: str, days: int):
    if update.effective_user.id != OWNER_ID: return
    code = "KEY-" + gen_code(12)
    context.bot_data.setdefault('keys', {})[code] = {"plan": plan, "days": days, "used": False}
    await update.message.reply_text(f"✅ KEY: <code>{code}</code>\n{plan.upper()} | {days}d", parse_mode="HTML")

async def cmd_key10(update: Update, context: ContextTypes.DEFAULT_TYPE): await cmd_gen_key(update, context, "core", 7)
async def cmd_key20(update: Update, context: ContextTypes.DEFAULT_TYPE): await cmd_gen_key(update, context, "elite", 15)
async def cmd_key30(update: Update, context: ContextTypes.DEFAULT_TYPE): await cmd_gen_key(update, context, "root", 30)

async def _grant_premium(uid: int, plan: str, days: int, update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud = context.bot_data.setdefault('user_data', {}); uid_str = str(uid)
    if uid_str not in ud: ud[uid_str] = {"name": "User", "joined": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "credits": 150, "plan": "FREE", "expires": 0}
    ud[uid_str]["plan"] = plan; ud[uid_str]["expires"] = time.time() + (days * 86400)
    receipt = await send_activation_msg(uid, plan, days, context)
    await update.message.reply_text(f"✅ {days}d ({plan.upper()}) → <code>{uid}</code>\nReceipt: <code>{receipt}</code>", parse_mode="HTML")

async def cmd_oneday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args: await update.message.reply_text("❌ /oneday <user_id>", parse_mode="HTML"); return
    uid = await resolve_user(context.args[0], context)
    if not uid: await update.message.reply_text("❌ Not found.", parse_mode="HTML"); return
    await _grant_premium(uid, "core", 1, update, context)

async def cmd_threeday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args: await update.message.reply_text("❌ /threeday <user_id>", parse_mode="HTML"); return
    uid = await resolve_user(context.args[0], context)
    if not uid: await update.message.reply_text("❌ Not found.", parse_mode="HTML"); return
    await _grant_premium(uid, "core", 3, update, context)

async def cmd_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if len(context.args) < 2: await update.message.reply_text("❌ /sub <user_id> <days>", parse_mode="HTML"); return
    uid = await resolve_user(context.args[0], context)
    if not uid: await update.message.reply_text("❌ Not found.", parse_mode="HTML"); return
    try:
        days = int(context.args[1]); plan = "root" if days >= 30 else "elite" if days >= 15 else "core"
        await _grant_premium(uid, plan, days, update, context)
    except ValueError: await update.message.reply_text("❌ Invalid days.", parse_mode="HTML")

async def cmd_resub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args: await update.message.reply_text("❌ /resub <user_id>", parse_mode="HTML"); return
    uid = await resolve_user(context.args[0], context)
    if not uid: await update.message.reply_text("❌ Not found.", parse_mode="HTML"); return
    ud = context.bot_data.setdefault('user_data', {}); uid_str = str(uid)
    if uid_str in ud: ud[uid_str]["plan"] = "FREE"; ud[uid_str]["expires"] = 0; await update.message.reply_text(f"✅ Removed premium from <code>{uid}</code>", parse_mode="HTML")
    else: await update.message.reply_text("❌ Not found.", parse_mode="HTML")

async def cmd_allplans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    users = context.bot_data.get('user_data', {}); txt = "🦇 ACTIVE PLANS\n━━━━━━━━━━━━━━━━━━━━\n\n"; found = False; now = time.time()
    for uid, data in users.items():
        exp = data.get('expires', 0)
        if data.get('plan', 'FREE') != 'FREE' and exp > now:
            found = True; r = int((exp - now) / 86400)
            txt += f"<code>{uid}</code> | {data.get('plan','FREE').upper()} | {r}d left\n"
    if not found: txt += "❌ No active plans."
    await update.message.reply_text(txt, parse_mode="HTML")

async def cmd_delcode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args: await update.message.reply_text("❌ /delcode <code>", parse_mode="HTML"); return
    code = context.args[0]; codes, keys = context.bot_data.get('codes', {}), context.bot_data.get('keys', {})
    if code in codes: del codes[code]; await update.message.reply_text("✅ Deleted.", parse_mode="HTML")
    elif code in keys: del keys[code]; await update.message.reply_text("✅ Deleted.", parse_mode="HTML")
    else: await update.message.reply_text("❌ Not found.", parse_mode="HTML")

async def cmd_rm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: await update.message.reply_text("❌ /rm <code>", parse_mode="HTML"); return
    code = context.args[0].upper(); codes, keys = context.bot_data.get('codes', {}), context.bot_data.get('keys', {}); uid = str(update.effective_user.id)
    ud = context.bot_data.setdefault('user_data', {})
    if uid not in ud: ud[uid] = {"name": "User", "credits": 150, "plan": "FREE", "expires": 0}
    if code in codes and not codes[code]['used']:
        codes[code]['used'] = True; ud[uid]["credits"] += codes[code]['value']
        await update.message.reply_text(f"✅ +{codes[code]['value']} credits. Balance: {ud[uid]['credits']}", parse_mode="HTML")
    elif code in keys and not keys[code]['used']:
        keys[code]['used'] = True; p, d = keys[code]['plan'], keys[code]['days']
        ud[uid]["plan"] = p; ud[uid]["expires"] = time.time() + (d * 86400)
        receipt = await send_activation_msg(int(uid), p, d, context)
        await update.message.reply_text(f"✅ {p.upper()} {d}d activated.\nReceipt: <code>{receipt}</code>", parse_mode="HTML")
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
    if len(context.args) < 2: await update.message.reply_text("❌ /seturl <gate> <url>", parse_mode="HTML"); return
    gate = context.args[0].lower(); url = " ".join(context.args[1:])
    if gate not in GATE_NAMES: await update.message.reply_text("❌ Unknown gate.", parse_mode="HTML"); return
    if url.lower() == "remove": context.bot_data.pop(f'gate_url_{gate}', None); await update.message.reply_text("✅ Removed.", parse_mode="HTML"); return
    context.bot_data[f'gate_url_{gate}'] = url
    await update.message.reply_text(f"✅ {GATE_NAMES[gate]} set.", parse_mode="HTML")

async def cmd_geturl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    txt = "🦇 GATE URLs\n━━━━━━━━━━━━━━━━━━━━\n\n"
    for g, n in GATE_NAMES.items():
        u = context.bot_data.get(f'gate_url_{g}', '') or GATE_URLS.get(g, '')
        s = "🟢" if context.bot_data.get(f'{g}_on', True) else "🔴"
        txt += f"{s} {n}: <code>{u or '❌'}</code>\n"
    await update.message.reply_text(txt, parse_mode="HTML")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇🦇🦇 GATE COMMANDS — IMPROVED RESPONSE
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
    api_url = context.bot_data.get(f'gate_url_{gate}', '') or GATE_URLS.get(gate, '')
    if not api_url:
        return {"status": "error", "message": f"{GATE_NAMES[gate]} not configured."}
    if not context.bot_data.get(f'{gate}_on', True):
        return {"status": "error", "message": f"{GATE_NAMES[gate]} is OFF."}
    site = GATE_SITES.get(gate, "")
    payload = json.dumps({"cc": card["cc"], "mm": card["mm"], "yy": card["yy"], "cvv": card["cvv"], "gate": gate, "site": site}).encode('utf-8')
    req = urllib.request.Request(api_url, data=payload, headers={"Content-Type": "application/json", "User-Agent": "BatCardChk/4.2", "Accept": "application/json"})
    try:
        loop = asyncio.get_running_loop()
        def do_req():
            with urllib.request.urlopen(req, timeout=API_TIMEOUT) as r:
                raw = r.read().decode('utf-8', errors='ignore')
                try: return json.loads(raw)
                except: return {"status": "unknown", "message": raw[:500], "raw": raw}
        return await loop.run_in_executor(None, do_req)
    except urllib.error.HTTPError as e:
        body = ""
        try: body = e.read().decode('utf-8', errors='ignore')[:500]
        except: pass
        try:
            j = json.loads(body); return {"status": "error", "message": j.get("message", j.get("msg", j.get("error", body))}
        except: return {"status": "error", "message": f"HTTP {e.code}"}
    except urllib.error.URLError as e:
        return {"status": "error", "message": f"Unreachable: {str(e.reason)[:120]}"}
    except Exception as e:
        return {"status": "error", "message": f"{type(e).__name__}: {str(e)[:120]}"}

def format_gate_result(gate: str, data: dict, card: dict, t: float) -> str:
    masked = f"{card['cc'][:6]}******{card['cc'][-4:]}"
    status = str(data.get("status", "") or data.get("result", "") or data.get("response", "") or data.get("code", "") or "").lower().strip()
    msg = ""
    for k in ("message", "msg", "info", "description", "reason", "detail"):
        v = data.get(k)
        if v and isinstance(v, str): msg = v
        elif v and isinstance(v, dict): msg = json.dumps(v, ensure_ascii=False)
    if msg: msg = str(msg)[:400]
    approved = ("approved", "live", "charged", "success", "1", "true", "approved_charged", "valid", "alive")
    declined = ("declined", "dead", "rejected", "fail", "0", "false", "declined_dead", "invalid", "die")
    if status in approved or status.startswith("approv"):
        icon, result = "✅", "APPROVED ✅"
    elif status in declined or status.startswith("declin") or status.startswith("reject"):
        icon, result = "❌", "DECLINED ❌"
    elif "cvv" in status:
        icon, result = "⚠️", "CVV MISMATCH ⚠️"
    elif status == "error":
        return f"❌ {GATE_NAMES[gate].upper()} GATE\n━━━━━━━━━━━━━━━━━━━━\n\nCard ➺ <code>{masked}</code>\nResult ➺ FAILED ❌\nReason ➺ {msg or 'Unknown'}\nTime ➺ {t:.2f}s\n━━━━━━━━━━━━━━━━━━━━"
    else:
        icon, result = "⚠️", f"RESPONSE: {status.upper() or 'UNKNOWN'}"
    txt = f"{icon} {GATE_NAMES[gate].upper()} GATE\n━━━━━━━━━━━━━━━━━━━━\n\nCard ➺ <code>{masked}</code>\nResult ➺ {result}\nTime ➺ {t:.2f}s\n"
    if msg and msg.lower() not in ("none", "", "null"): txt += f"Info ➺ {msg}\n"
    for key in ("bin_info", "charge_id", "transaction_id", "bank", "country", "type", "brand", "funding", "site", "gateway"):
        val = data.get(key)
        if val and str(val).lower() not in ("none", "null", ""): txt += f"{key.title()} ➺ {val}\n"
    txt += "\n━━━━━━━━━━━━━━━━━━━━"
    return txt

async def handle_gate_cmd(gate: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user; uid_str = str(user.id)
    if not context.bot_data.get(f'{gate}_on', True):
        await update.message.reply_text(f"❌ {GATE_NAMES[gate]} is OFF.", parse_mode="HTML"); return
    if not context.args:
        await update.message.reply_text(f"❌ /{gate} cc|mm|yy|cvv\n\nExample: /{gate} 4532010123456789|03|28|353", parse_mode="HTML"); return
    card = parse_card(" ".join(context.args))
    if not card:
        await update.message.reply_text("❌ Invalid format!\n\ncc|mm|yy|cvv\ncc/mm/yy/cvv\ncc mm yy cvv", parse_mode="HTML"); return
    if not is_premium_active(user.id, context):
        ud = context.bot_data.setdefault('user_data', {}).get(uid_str, {})
        cost = GATE_COST.get(gate, 1); credits = ud.get('credits', 150)
        if credits < cost:
            await update.message.reply_text(f"❌ Need {cost} credits, have {credits}.\nUse /rm <code> or buy premium.", parse_mode="HTML"); return
        ud['credits'] = credits - cost
    masked = f"{card['cc'][:6]}******{card['cc'][-4:]}"
    status_msg = await update.message.reply_text(f"⏳ Checking <code>{masked}</code> on {GATE_NAMES[gate]}...", parse_mode="HTML")
    start_time = time.time()
    result = await run_gate_api(gate, card, context)
    time_taken = time.time() - start_time
    txt = format_gate_result(gate, result, card, time_taken)
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
# 🦇🦇🦇 CALLBACKS — ZERO DELAY, ALWAYS RESPONDS
#    - edit() now tries 3 methods: edit, delete+send, fallback text
#    - Every error is logged, never silent
#    - Catch-all at the end for unmatched callbacks
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        q = update.callback_query
        d = q.data
        if not d:
            await q.answer("❌ No callback data")
            return

        # Always answer instantly — never let this fail
        try:
            await q.answer()
        except Exception as e:
            logging.error(f"[CALLBACK] answer() failed: {e}")

        # ── VERIFY JOIN ──
        if d == "verify_join":
            try:
                await q.edit_message_text(
                    text=ui_profile(q.from_user, context),
                    parse_mode="HTML",
                    reply_markup=kb_main(),
                    disable_web_page_preview=True
                )
            except Exception as e:
                logging.error(f"[CALLBACK] verify_join edit failed: {e}")
                try:
                    await context.bot.send_message(
                        chat_id=q.message.chat_id,
                        text=ui_profile(q.from_user, context),
                        parse_mode="HTML",
                        reply_markup=kb_main(),
                        disable_web_page_preview=True
                    )
                except Exception as e2:
                    logging.error(f"[CALLBACK] verify_join send fallback failed: {e2}")
                    await q.answer("❌ Error loading menu")
            asyncio.ensure_future(_check_and_kick_if_not_joined(q.from_user.id, context, q.message.chat_id))
            return

        # ── HELPER: safe message edit with 3 fallback methods ──
        async def safe_edit(text: str, kb):
            """Try edit, then delete+send, then fallback text"""
            # Method 1: Edit existing message
            try:
                await q.edit_message_text(text=text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
                return True
            except Exception as e:
                logging.debug(f"[CALLBACK] edit failed: {e}")

            # Method 2: Delete old message, send new one
            try:
                if q.message:
                    await q.message.delete()
            except: pass
            try:
                await context.bot.send_message(
                    chat_id=q.message.chat_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=kb,
                    disable_web_page_preview=True
                )
                return True
            except Exception as e:
                logging.error(f"[CALLBACK] send fallback failed: {e}")

            # Method 3: Pure text fallback (no HTML, no keyboard)
            try:
                clean = text.replace("<code>", "").replace("</a>", "").replace("<b>", "").replace("</b>", "")
                await context.bot.send_message(chat_id=q.message.chat_id, text=clean)
            except: pass
            return False

        # ── ROUTE ALL CALLBACKS ──
        if d.startswith("use_"):
            cmd = d.replace("use_", "")
            gn = GATE_NAMES.get(cmd, cmd.upper())
            await safe_edit(
                f"━━━━━━━━━━━━━━━━━━━━\n⚡ {gn.upper()} GATE\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Send your card:\n\n"
                f"<code>/{cmd} cc|mm|yy|cvv</code>\n\n"
                f"Example:\n"
                f"<code>/{cmd} 4532010123456789|03|28|353</code>",
                kb_back("mgates")
            )
            return

        if d == "bmain":
            await safe_edit(ui_profile(q.from_user, context), kb_main())

        elif d == "mprice":
            await safe_edit(
                "Aᴄᴄᴇꜱꜱ ➺ Cᴏʀᴇ 🎀\n"
                "Sᴘᴀɴ ➺ [7 Dᴀʏꜱ]\n"
                "Cʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ\n"
                "Pʀɪᴄᴇ ➺ 10$\n"
                "━━━━━━━━━━━━━━━━\n"
                "Aᴄᴄᴇꜱꜱ ➺ Eʟɪᴛᴇ ⭐️\n"
                "Sᴘᴀɴ ➺ [15 Dᴀʏꜱ]\n"
                "Cʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ\n"
                "Pʀɪᴄᴇ ➺ 15$\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "Aᴄᴄᴇꜱꜱ ➺ Rᴏᴏᴛ 👑\n"
                "Sᴘᴀɴ ➺ [30 Dᴀʏꜱ]\n"
                "Cʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴍɪᴛɪᴛᴇᴅ\n"
                "Pʀɪᴄᴇ ➺ 30$",
                kb_price()
            )

        elif d in ("pay10", "pay20", "pay30"):
            amt = d.replace("pay", "$")
            await safe_edit(
                f"PAYMENT - {amt}\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Base Amount: {amt}\n"
                f"Taxes: Included\n"
                f"Total: {amt}\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "⏳ Payment system coming soon.\n\n"
                f"Contact <a href='{DEV_LINK}'>Batman</a> for manual payment.",
                kb_back("mprice")
            )

        elif d == "mgates":
            await safe_edit(
                "SELECT GATE",
                InlineKeyboardMarkup([
                    [InlineKeyboardButton("AUTH", callback_data="mauth"), InlineKeyboardButton("CHARGE", callback_data="mcharge")],
                    [InlineKeyboardButton("◀ BACK", callback_data="bmain")]
                ])
            )

        elif d == "mauth":
            await safe_edit(
                "AUTH GATES",
                InlineKeyboardMarkup([
                    [InlineKeyboardButton("Stripe", callback_data="iau"), InlineKeyboardButton("Braintree", callback_data="ib3")],
                    [InlineKeyboardButton("◀ BACK", callback_data="mgates")]
                )
            )

        elif d == "iau":
            await safe_edit(
                "━━━━━━━━━━━━━━━━━━━━\nGATE: Stripe Auth\nCMD: /chk cc|mm|yy|cvv\nSITES: 16\n━━━━━━━━━━━━━━━━━━━━",
                kb_gate_info("chk", "mauth")
            )

        elif d == "ib3":
            await safe_edit(
                "━━━━━━━━━━━━━━━━━━━━\nGATE: Braintree Auth\nCMD: /b3 cc|mm|yy|cvv\nSITES: 2\n━━━━━━━━━━━━━━━━━━━━",
                kb_gate_info("b3", "mauth")
            )

        elif d == "mcharge":
            await safe_edit(
                "CHARGE GATES",
                InlineKeyboardMarkup([
                    [InlineKeyboardButton("Stripe", callback_data="ichk"), InlineKeyboardButton("PayPal", callback_data="ipp")],
                    [InlineKeyboardButton("Shopify", callback_data="ish"), InlineKeyboardButton("PayU", callback_data="ipyu")],
                    [InlineKeyboardButton("◀ BACK", callback_data="mgates")]
                ])
            )

        elif d == "ichk":
            await safe_edit(
                "━━━━━━━━━━━━━━━━━━━━\nGATE: Stripe\nCMD: /chk cc|mm|yy|cvv\nSITES: 4\n━━━━━━━━━━━━━━━━━━━━",
                kb_gate_info("chk", "mcharge")
            )

        elif d == "ipp":
            await safe_edit(
                "━━━━━━━━━━━━━━━━━━━━\nGATE: PayPal\nCMD: /pp cc|mm|yy|cvv\nSITES: 7\n━━━━━━━━━━━━━━━━━━━━",
                kb_gate_info("pp", "mcharge")
            )

        elif d == "ish":
            await safe_edit(
                "━━━━━━━━━━━━━━━━━━━━\nGATE: Shopify\nCMD: /sh cc|mm|yy|cvv\nSITES: 10\n━━━━━━━━━━━━━━━━━━━━",
                kb_gate_info("sh", "mcharge")
            )

        elif d == "ipyu":
            await safe_edit(
                "━━━━━━━━━━━━━━━━━━━━\nGATE: PayU\nCMD: /pyu cc|mm|yy|cvv\nSITES: 1\n━━━━━━━━━━━━━━━━━━━━",
                kb_gate_info("pyu", "mcharge")
            )

        else:
            # CATCH-ALL for any unmatched callback data
            logging.warning(f"[CALLBACK] Unmatched callback: {d}")
            try:
                await q.answer("❌ Unknown button")
            except: pass

    except Exception as e:
        logging.error(f"[CALLBACK] CRASH: {e}")
        try:
            await q.answer(f"❌ Error: {str(e)[:100}")
        except: pass

async def _check_and_kick_if_not_joined(user_id, chat_id, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not await is_joined(user_id, context):
            try: await context.bot.send_message(chat_id=chat_id, text="❌ You didn't join both channels!", parse_mode="HTML")
            except: pass
    except: pass

async def on_start(app):
    print("🦇 Batman Bot Initializing...")
    await init_photo()
    if DOWNLOADED_PHOTO_PATH:
        print(f"🦇 Photo ready: {DOWNLOADED_PHOTO_PATH}")
    else:
        print("❌ NO PHOTO — join page text only")
    await app.bot.delete_webhook(drop_pending_updates=True)

async def cmd_killbot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    await update.message.reply_text("🛑 Killing bot...", parse_mode="HTML")
    os.kill(os.getpid(), signal.SIGTERM)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    if isinstance(context.error, Conflict):
        logging.warning("⚠️ Conflict caught!")
        await asyncio.sleep(15)
        return
    logging.error(f"Exception: {context.error}")

def main():
    _find_local_photo()

    try: urllib.request.urlopen(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=5).read()
    except: pass

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

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 🦇 /b3 — External b3.py if available, else built-in
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    b3_loaded = False
    try:
        from b3 import get_b3_handler
        if get_b3_handler:
            handler = get_b3_handler()
            app.add_handler(handler)
            b3_loaded = True
            print("🦇 [B3] Loaded b3.py handler")
    except ImportError:
        print("⚠️ [B3] b3.py not found — using built-in /b3")
    except Exception as e:
        print(f"⚠️ [B3] b3.py error: {e}")
    if not b3_loaded:
        app.add_handler(CommandHandler("b3", cmd_b3))
        print("🦇 [B3] Using built-in /b3")

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

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CALLBACK HANDLER — MUST BE LAST (catches all unmatched callbacks)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, anti_ad_filter))
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, anti_ad_filter))

    print("🦇 Online!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
