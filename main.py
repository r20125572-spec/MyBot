import os
import signal
import logging
import time
import string
import random
import urllib.request
import json
import asyncio
from typing import Optional
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes, ApplicationHandlerStop
)
from telegram.error import Conflict

from config import (
    BOT_TOKEN, OWNER_ID, VERSION, DEV_LINK, 
    CHANNEL_USERNAME, GROUP_USERNAME, CHANNEL_LINK, GROUP_LINK, 
    BOT_PHOTO
)

SUPPORT_LINK = "https://t.me/cardchkSupport"
DB_FILE = "db.json"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 SAFE IMPORTS (Won't crash if files are missing) 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
try: from chk import get_chk_handler
except: get_chk_handler = None
try: from pp import get_pp_handler
except: get_pp_handler = None
try: from sh import get_sh_handler
except: get_sh_handler = None
try: from pyu import get_pyu_handler
except: get_pyu_handler = None

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 PERMANENT DATABASE SYSTEM 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def load_db():
    try:
        with open(DB_FILE, 'r') as f: return json.load(f)
    except: return {"users": {}, "codes": {}, "keys": {}}

def save_db(data):
    try:
        with open(DB_FILE, 'w') as f: json.dump(data, f, indent=2)
    except Exception as e:
        logging.error(f"DB Save Error: {e}")

def get_user(user_id):
    db = load_db()
    return db.get("users", {}).get(str(user_id), {"credits": 0, "plan": "FREE", "expires": 0})

def update_user(user_id, updates):
    db = load_db()
    uid = str(user_id)
    if uid not in db["users"]:
        db["users"][uid] = {"name": "", "joined": "", "credits": 0, "plan": "FREE", "expires": 0}
    db["users"][uid].update(updates)
    save_db(db)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 HELPERS & FILTERS 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BLOCK_WORDS = ("http://", "https://", "www.", "t.me", ".com", ".net", ".org", ".io", ".me", ".xyz", ".tk", ".ml", ".cf", ".ga", ".ru", ".in", ".pw", "telegram.me", "joinchat", "://")

async def anti_ad_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text or msg.from_user.id == OWNER_ID: return
    if any(w in msg.text.lower() for w in BLOCK_WORDS):
        try: await msg.delete()
        except: pass

async def is_joined(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    async def check(chat_id):
        try: return (await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)).status not in ('left', 'kicked')
        except: return False
    return await check(CHANNEL_USERNAME) and await check(GROUP_USERNAME)

def ui_profile(user):
    udata = get_user(user.id)
    plan = udata.get("plan", "FREE").upper()
    credits = udata.get("credits", 0)
    expires = udata.get("expires", 0)
    
    status = f"Pʟᴀɴ ➺ {plan}\nCʀᴇᴅɪᴛꜱ ➺ {credits}"
    if expires > time.time():
        status += f"\nExᴘɪʀᴇꜱ ➺ {datetime.fromtimestamp(expires).strftime('%Y-%m-%d')}"
        
    return (
        f"Uꜱᴇʀ ➺ {user.username or 'None'}\n"
        f"Uꜱᴇʀ ID ➺ <code>{user.id}</code>\n"
        f"{status}\n"
        f"Jᴏɪɴᴇᴅ ➺ {datetime.now().strftime('%Y-%m-%d')}\n"
        f"Dᴇᴠ ➺ <a href='{DEV_LINK}'>Batman</a>"
    )

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

async def resolve_user(target: str, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    target = target.lstrip('@')
    if target.lstrip('-').isdigit(): return int(target)
    try: return (await context.bot.get_chat(f"@{target}")).id
    except: return None

def gen_code(length=10): return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 CREDIT DEDUCTION SYSTEM (1 Check = 1 Credit) 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def gate_credit_guard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    cmd = update.message.text.split()[0].lower()
    
    # Only intercept gate commands
    if cmd in ['/chk', '/pp', '/sh', '/pyu']:
        if update.effective_user.id == OWNER_ID: return # Owner has unlimited checks
        
        user_id = str(update.effective_user.id)
        db = load_db()
        user = db.get("users", {}).get(user_id, {})
        
        has_premium = user.get('expires', 0) > time.time()
        has_credits = user.get('credits', 0) > 0
        
        if not has_premium and not has_credits:
            await update.message.reply_text(
                "❌ INSUFFICIENT BALANCE\n━━━━━━━━━━━━━━━━━━━━\n\n"
                "You have 0 credits.\n\n"
                "📌 Use /rm <code> to add credits\n"
                "📌 Or buy premium /plan\n"
                "━━━━━━━━━━━━━━━━━━━━", parse_mode="HTML"
            )
            raise ApplicationHandlerStop # BLOCKS THE CHECK COMMAND FROM RUNNING
            
        if not has_premium and has_credits:
            db["users"][user_id]["credits"] -= 1
            save_db(db)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 BIN COMMAND 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def fetch_bin(url: str) -> dict:
    try:
        req = urllib.request.Request(url, headers={"Accept-Version": "3", "User-Agent": "Mozilla/5.0"})
        loop = asyncio.get_running_loop()
        def do_req():
            with urllib.request.urlopen(req, timeout=10) as r: return json.loads(r.read().decode('utf-8'))
        return await loop.run_in_executor(None, do_req)
    except: return {}

async def cmd_bin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: await update.message.reply_text("❌ Usage: /bin <BIN>", parse_mode="HTML"); return
    bin_num = ''.join(filter(str.isdigit, context.args[0]))[:6]
    if len(bin_num) < 6: await update.message.reply_text("❌ Invalid BIN!", parse_mode="HTML"); return
    status = await update.message.reply_text(f"🔍 Looking up BIN: <code>{bin_num}</code>...", parse_mode="HTML")
    data = await fetch_bin(f"https://lookup.binlist.net/{bin_num}")
    if not data or "scheme" not in data:
        try: await status.edit_text("❌ BIN not found.", parse_mode="HTML")
        except: pass
        return
    c_data, b_data = data.get("country") or {}, data.get("bank") or {}
    brand = (data.get("brand") or "N/A").upper()
    txt = (
        "━━━━━━━━━━━━━━━━━━━━\n🦇 BIN LOOKUP RESULT\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"BIN ➺ <code>{bin_num}</code>\nSCHEME ➺ {(data.get('scheme') or 'N/A').upper()}\n"
        f"TYPE ➺ {(data.get('type') or 'N/A').upper()}\nBRAND ➺ {brand}\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n🌍 COUNTRY INFO\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"NAME ➺ {c_data.get('emoji', '🌍')} {c_data.get('name', 'N/A')}\nCODE ➺ {c_data.get('alpha2', '??')}\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n🏦 BANK INFO\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"BANK ➺ {b_data.get('name', 'N/A')}\n"
    )
    if b_data.get("url"): txt += f"URL ➺ {b_data.get('url')}\n"
    try: await status.edit_text(txt + "\n━━━━━━━━━━━━━━━━━━━━", parse_mode="HTML", disable_web_page_preview=True)
    except: pass

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 USER COMMANDS 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db = load_db()
    uid = str(user.id)
    if uid not in db["users"]:
        db["users"][uid] = {"name": user.first_name, "joined": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "credits": 0, "plan": "FREE", "expires": 0}
        save_db(db)
        
    if await is_joined(user.id, context):
        await update.message.reply_text(text=ui_profile(user), parse_mode="HTML", reply_markup=kb_main(), disable_web_page_preview=True)
    else:
        cap = "BATMAN CARD CHECKER\n\nAccess Required\n━━━━━━━━━━━━━━━━━━━━\nJoin both channels to\nunlock the bot.\n━━━━━━━━━━━━━━━━━━━━"
        try: await update.message.reply_photo(photo=BOT_PHOTO, caption=cap, parse_mode="HTML", reply_markup=kb_force())
        except: await update.message.reply_text(text=cap, parse_mode="HTML", reply_markup=kb_force())

async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Aᴄᴄᴇꜱꜱ ➺ Cᴏʀᴇ 🎀\nSᴘᴀɴ ➺ [7 Dᴀʏꜱ]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ\nPʀɪᴄᴇ ➺ 10$\n━━━━━━━━━━━━━━━━\nAᴄᴄᴇꜱꜱ ➺ Eʟɪᴛᴇ ⭐️\nSᴘᴀɴ ➺ [15 Dᴀʏꜱ]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ\nPʀɪᴄᴇ ➺ 15$\n━━━━━━━━━━━━━━━━\nAᴄᴄᴇꜱꜱ ➺ Rᴏᴏᴛ 👑\nSᴘᴀɴ ➺ [30 Dᴀʏꜱ]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ\nPʀɪᴄᴇ ➺ 30$", parse_mode="HTML", reply_markup=kb_price())

async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    target_id = target_input = None
    if update.message.reply_to_message: target_id = update.message.reply_to_message.from_user.id; target_input = str(target_id)
    elif context.args: target_input = context.args[0]; target_id = await resolve_user(target_input, context)
    else: await update.message.reply_text("❌ Reply to user or provide ID.", parse_mode="HTML"); return
    if not target_id: await update.message.reply_text(f"❌ User not found.", parse_mode="HTML"); return
    
    udata = get_user(target_id)
    txt = (
        f"━━━━━━━━━━━━━━━━━━━━━━\nUSER INFO\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Name: {udata.get('name', 'N/A')}\n"
        f"ID: <code>{target_id}</code>\n"
        f"Joined: {udata.get('joined', 'N/A')}\n\n"
        f"Plan: {udata.get('plan', 'FREE').upper()}\n"
        f"Credits: {udata.get('credits', 0)}\n"
    )
    if udata.get('expires', 0) > time.time():
        txt += f"Expires: {datetime.fromtimestamp(udata['expires']).strftime('%Y-%m-%d %H:%M')}\n"
    await update.message.reply_text(txt + "━━━━━━━━━━━━━━━━━━━━━━", parse_mode="HTML")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 OWNER COMMANDS (ALL FIXED) 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_allcm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    await update.message.reply_text(
        f"🦇 BATMAN BOT COMMANDS\n━━━━━━━━━━━━━━━━━━━━\nVersion: {VERSION}\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "👤 USER COMMANDS\n━━━━━━━━━━━━━━━━━━━━\n"
        "▸ /start - Start Bot\n▸ /plan - View Plans\n▸ /bin - BIN Lookup\n"
        "▸ /chk - Stripe Check (-1 Credit)\n▸ /pp - PayPal Check (-1 Credit)\n"
        "▸ /sh - Shopify Check (-1 Credit)\n▸ /pyu - PayU Check (-1 Credit)\n"
        "▸ /rm - Redeem Code\n\n"
        "👑 OWNER COMMANDS\n━━━━━━━━━━━━━━━━━━━━\n"
        "▸ /info - User Info\n▸ /allcm - This Menu\n"
        "▸ /gen <amt> - Gen Credit Code\n"
        "▸ /key10 - Gen Core Key\n▸ /key20 - Gen Elite Key\n▸ /key30 - Gen Root Key\n"
        "▸ /oneday <id> - Give 1 Day Access\n"
        "▸ /threeday <id> - Give 3 Days Access\n"
        "▸ /sub <id> <days> - Grant Premium\n"
        "▸ /resub <id> - Remove Premium\n"
        "▸ /allplans - View Active Plans\n"
        "▸ /delcode <code> - Delete Code/Key\n"
        "━━━━━━━━━━━━━━━━━━━━", parse_mode="HTML"
    )

async def cmd_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args: await update.message.reply_text("❌ Usage: /gen <credits>", parse_mode="HTML"); return
    try:
        amt = int(context.args[0])
        code = gen_code()
        db = load_db()
        db["codes"][code] = {"type": "credit", "value": amt, "used": False}
        save_db(db)
        await update.message.reply_text(f"✅ CREDIT CODE GENERATED\n━━━━━━━━━━━━━━━━━━━━\n\nCode: <code>{code}</code>\nCredits: {amt}\n━━━━━━━━━━━━━━━━━━━━", parse_mode="HTML")
    except: await update.message.reply_text("❌ Invalid amount.", parse_mode="HTML")

async def cmd_gen_key(update: Update, context: ContextTypes.DEFAULT_TYPE, plan: str, days: int):
    if update.effective_user.id != OWNER_ID: return
    code = "KEY-" + gen_code(12)
    db = load_db()
    db["keys"][code] = {"plan": plan, "days": days, "used": False}
    save_db(db)
    await update.message.reply_text(f"✅ PREMIUM KEY GENERATED\n━━━━━━━━━━━━━━━━━━━━\n\nKey: <code>{code}</code>\nPlan: {plan.upper()}\nDays: {days}\n━━━━━━━━━━━━━━━━━━━━", parse_mode="HTML")

async def cmd_key10(update: Update, context: ContextTypes.DEFAULT_TYPE): await cmd_gen_key(update, context, "core", 7)
async def cmd_key20(update: Update, context: ContextTypes.DEFAULT_TYPE): await cmd_gen_key(update, context, "elite", 15)
async def cmd_key30(update: Update, context: ContextTypes.DEFAULT_TYPE): await cmd_gen_key(update, context, "root", 30)

async def cmd_oneday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args: await update.message.reply_text("❌ Usage: /oneday <user_id>", parse_mode="HTML"); return
    uid = await resolve_user(context.args[0], context)
    if not uid: await update.message.reply_text("❌ User not found.", parse_mode="HTML"); return
    update_user(uid, {"plan": "core", "expires": time.time() + 86400})
    await update.message.reply_text(f"✅ Granted 1 Day Access to <code>{uid}</code>", parse_mode="HTML")

async def cmd_threeday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args: await update.message.reply_text("❌ Usage: /threeday <user_id>", parse_mode="HTML"); return
    uid = await resolve_user(context.args[0], context)
    if not uid: await update.message.reply_text("❌ User not found.", parse_mode="HTML"); return
    update_user(uid, {"plan": "core", "expires": time.time() + (3 * 86400)})
    await update.message.reply_text(f"✅ Granted 3 Days Access to <code>{uid}</code>", parse_mode="HTML")

async def cmd_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if len(context.args) < 2: await update.message.reply_text("❌ Usage: /sub <user_id> <days>", parse_mode="HTML"); return
    uid = await resolve_user(context.args[0], context)
    if not uid: await update.message.reply_text("❌ User not found.", parse_mode="HTML"); return
    try:
        days = int(context.args[1])
        plan = "root" if days >= 30 else "elite" if days >= 15 else "core"
        update_user(uid, {"plan": plan, "expires": time.time() + (days * 86400)})
        await update.message.reply_text(f"✅ Granted {days} Days ({plan.upper()}) to <code>{uid}</code>", parse_mode="HTML")
    except: await update.message.reply_text("❌ Invalid days.", parse_mode="HTML")

async def cmd_resub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args: await update.message.reply_text("❌ Usage: /resub <user_id>", parse_mode="HTML"); return
    uid = await resolve_user(context.args[0], context)
    if not uid: await update.message.reply_text("❌ User not found.", parse_mode="HTML"); return
    update_user(uid, {"plan": "FREE", "expires": 0})
    await update.message.reply_text(f"✅ Removed premium from <code>{uid}</code>", parse_mode="HTML")

async def cmd_allplans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    db = load_db()
    users = db.get("users", {})
    txt = "🦇 ACTIVE PLANS\n━━━━━━━━━━━━━━━━━━━━\n\n"
    found = False
    for uid, data in users.items():
        if data.get('expires', 0) > time.time():
            found = True
            txt += f"ID: <code>{uid}</code>\nPlan: {data.get('plan', 'FREE').upper()}\nExp: {datetime.fromtimestamp(data['expires']).strftime('%Y-%m-%d')}\n━━━━━━━━━━━━━━━━━━━━\n"
    if not found: txt += "❌ No active premium plans."
    await update.message.reply_text(txt, parse_mode="HTML")

async def cmd_delcode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args: await update.message.reply_text("❌ Usage: /delcode <code>", parse_mode="HTML"); return
    code = context.args[0]
    db = load_db()
    if code in db.get("codes", {}): del db["codes"][code]; save_db(db); await update.message.reply_text("✅ Code deleted.", parse_mode="HTML")
    elif code in db.get("keys", {}): del db["keys"][code]; save_db(db); await update.message.reply_text("✅ Key deleted.", parse_mode="HTML")
    else: await update.message.reply_text("❌ Not found.", parse_mode="HTML")

async def cmd_rm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: await update.message.reply_text("❌ Usage: /rm <code>", parse_mode="HTML"); return
    code = context.args[0].upper()
    db = load_db()
    uid = str(update.effective_user.id)
    
    if code in db.get("codes", {}) and not db["codes"][code]["used"]:
        db["codes"][code]["used"] = True
        val = db["codes"][code]["value"]
        user = db.get("users", {}).get(uid, {"credits": 0})
        user["credits"] = user.get("credits", 0) + val
        db["users"][uid] = user
        save_db(db)
        await update.message.reply_text(f"✅ Redeemed! Added {val} credits to your balance.", parse_mode="HTML")
        
    elif code in db.get("keys", {}) and not db["keys"][code]["used"]:
        db["keys"][code]["used"] = True
        plan, days = db["keys"][code]["plan"], db["keys"][code]["days"]
        update_user(uid, {"plan": plan, "expires": time.time() + (days * 86400)})
        await update.message.reply_text(f"✅ Redeemed! Activated {plan.upper()} for {days} days.", parse_mode="HTML")
    else:
        await update.message.reply_text("❌ Invalid or already used code.", parse_mode="HTML")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 GATE TOGGLES 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_onchk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    db = load_db(); db.setdefault("settings", {})['chk_on'] = True; save_db(db)
    await update.message.reply_text("STRIPE → ON ✅", parse_mode="HTML")
async def cmd_offchk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    db = load_db(); db.setdefault("settings", {})['chk_on'] = False; save_db(db)
    await update.message.reply_text("STRIPE → OFF ❌", parse_mode="HTML")
async def cmd_onpp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    db = load_db(); db.setdefault("settings", {})['pp_on'] = True; save_db(db)
    await update.message.reply_text("PAYPAL → ON ✅", parse_mode="HTML")
async def cmd_offpp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    db = load_db(); db.setdefault("settings", {})['pp_on'] = False; save_db(db)
    await update.message.reply_text("PAYPAL → OFF ❌", parse_mode="HTML")
async def cmd_onsh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    db = load_db(); db.setdefault("settings", {})['sh_on'] = True; save_db(db)
    await update.message.reply_text("SHOPIFY → ON ✅", parse_mode="HTML")
async def cmd_offsh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    db = load_db(); db.setdefault("settings", {})['sh_on'] = False; save_db(db)
    await update.message.reply_text("SHOPIFY → OFF ❌", parse_mode="HTML")
async def cmd_onpyu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    db = load_db(); db.setdefault("settings", {})['pyu_on'] = True; save_db(db)
    await update.message.reply_text("PAYU → ON ✅", parse_mode="HTML")
async def cmd_offpyu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    db = load_db(); db.setdefault("settings", {})['pyu_on'] = False; save_db(db)
    await update.message.reply_text("PAYU → OFF ❌", parse_mode="HTML")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 CALLBACKS 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); d = q.data
    if d == "verify_join":
        if await is_joined(q.from_user.id, context):
            try:
                if q.message.photo: await q.message.delete(); await context.bot.send_message(chat_id=q.message.chat_id, text=ui_profile(q.from_user), parse_mode="HTML", reply_markup=kb_main(), disable_web_page_preview=True)
                else: await q.edit_message_text(text=ui_profile(q.from_user), parse_mode="HTML", reply_markup=kb_main(), disable_web_page_preview=True)
            except: pass
        else: await q.answer("❌ Join Group & Channel first!", show_alert=True)
        return
    async def edit(t, kb):
        try: await q.edit_message_text(text=t, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
        except: pass
    if d == "bmain": await edit(ui_profile(q.from_user), kb_main())
    elif d == "mprice": await edit("Aᴄᴄᴇꜱꜱ ➺ Cᴏʀᴇ 🎀\nSᴘᴀɴ ➺ [7 Dᴀʏꜱ]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ\nPʀɪᴄᴇ ➺ 10$\n━━━━━━━━━━━━━━━━\nAᴄᴄᴇꜱꜱ ➺ Eʟɪᴛᴇ ⭐️\nSᴘᴀɴ ➺ [15 Dᴀʏꜱ]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ\nPʀɪᴄᴇ ➺ 15$\n━━━━━━━━━━━━━━━━\nAᴄᴄᴇꜱꜱ ➺ Rᴏᴏᴛ 👑\nSᴘᴀɴ ➺ [30 Dᴀʏꜱ]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ\nPʀɪᴄᴇ ➺ 30$", kb_price())
    elif d in ("pay10", "pay20", "pay30"): await edit(f"PAYMENT - {d.replace('pay','$')}\n━━━━━━━━━━━━━━━━━━━━\n\nBase Amount: {d.replace('pay','$')}\nTotal: {d.replace('pay','$')}\n\n━━━━━━━━━━━━━━━━━━━━\nContact <a href='{DEV_LINK}'>Batman</a> for manual payment.", kb_back("mprice"))
    elif d == "mgates": await edit("SELECT GATE", InlineKeyboardMarkup([[InlineKeyboardButton("AUTH", callback_data="mauth"), InlineKeyboardButton("CHARGE", callback_data="mcharge")],[InlineKeyboardButton("◀ BACK", callback_data="bmain")]]))
    elif d == "mauth": await edit("AUTH GATES", InlineKeyboardMarkup([[InlineKeyboardButton("Stripe", callback_data="iau"), InlineKeyboardButton("Braintree", callback_data="ib3")],[InlineKeyboardButton("◀ BACK", callback_data="mgates")]]))
    elif d == "iau": await edit("━━━━━━━━━━━━━━━━━━━━\nGATE: Stripe Auth\nCMD: /au\nSITES: 16\nHEALTH: 100%\n━━━━━━━━━━━━━━━━━━━━", kb_back("mauth"))
    elif d == "ib3": await edit("━━━━━━━━━━━━━━━━━━━━\nGATE: Braintree Auth\nCMD: /b3\nSITES: 2\nHEALTH: 100%\n━━━━━━━━━━━━━━━━━━━━", kb_back("mauth"))
    elif d == "mcharge": await edit("CHARGE GATES", InlineKeyboardMarkup([[InlineKeyboardButton("Stripe", callback_data="ichk"), InlineKeyboardButton("PayPal", callback_data="ipp")],[InlineKeyboardButton("Shopify", callback_data="ish"), InlineKeyboardButton("PayU", callback_data="ipyu")],[InlineKeyboardButton("◀ BACK", callback_data="mgates")]]))
    elif d == "ichk": await edit("━━━━━━━━━━━━━━━━━━━━\nGATE: Stripe\nPRICE: 1 Credit\nCMD: /chk\nSITES: 4\nHEALTH: 100%\n━━━━━━━━━━━━━━━━━━━━", kb_back("mcharge"))
    elif d == "ipp": await edit("━━━━━━━━━━━━━━━━━━━━\nGATE: PayPal\nPRICE: 1 Credit\nCMD: /pp\nSITES: 7\nHEALTH: 100%\n━━━━━━━━━━━━━━━━━━━━", kb_back("mcharge"))
    elif d == "ish": await edit("━━━━━━━━━━━━━━━━━━━━\nGATE: Shopify\nPRICE: 1 Credit\nCMD: /sh\nSITES: 10\nHEALTH: 100%\n━━━━━━━━━━━━━━━━━━━━", kb_back("mcharge"))
    elif d == "ipyu": await edit("━━━━━━━━━━━━━━━━━━━━\nGATE: PayU\nPRICE: 1 Credit\nCMD: /pyu\nSITES: 1\nHEALTH: 100%\n━━━━━━━━━━━━━━━━━━━━", kb_back("mcharge"))

async def on_start(app):
    print("🦇 Batman Bot Initializing...")
    await app.bot.delete_webhook(drop_pending_updates=True)

async def cmd_killbot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    await update.message.reply_text("🛑 Killing bot...", parse_mode="HTML")
    os.kill(os.getpid(), signal.SIGTERM)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 MAIN STARTUP 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def main():
    app = Application.builder().token(BOT_TOKEN).post_init(on_start).build()
    
    # 1. CREDIT INTERCEPTOR (Runs FIRST in Group -1 to block checks if 0 credits)
    app.add_handler(MessageHandler(filters.Regex(r'^/(chk|pp|sh|pyu)(@\w+)?\s'), gate_credit_guard), group=-1)
    
    # 2. ALL COMMANDS
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("plan", cmd_plan))
    app.add_handler(CommandHandler("bin", cmd_bin))
    app.add_handler(CommandHandler("info", cmd_info))
    app.add_handler(CommandHandler("allcm", cmd_allcm))
    app.add_handler(CommandHandler("gen", cmd_gen))
    app.add_handler(CommandHandler("key10", cmd_key10))
    app.add_handler(CommandHandler("key20", cmd_key20))
    app.add_handler(CommandHandler("key30", cmd_key30))
    app.add_handler(CommandHandler("oneday", cmd_oneday))
    app.add_handler(CommandHandler("threeday", cmd_threeday)) # NEW
    app.add_handler(CommandHandler("sub", cmd_sub))
    app.add_handler(CommandHandler("resub", cmd_resub))
    app.add_handler(CommandHandler("allplans", cmd_allplans))
    app.add_handler(CommandHandler("delcode", cmd_delcode))
    app.add_handler(CommandHandler("rm", cmd_rm))
    app.add_handler(CommandHandler("killbot", cmd_killbot))
    
    for cmd, func in [("onchk", cmd_onchk), ("offchk", cmd_offchk), ("onpp", cmd_onpp), ("offpp", cmd_offpp), ("onsh", cmd_onsh), ("offsh", cmd_offsh), ("onpyu", cmd_onpyu), ("offpyu", cmd_offpyu)]:
        app.add_handler(CommandHandler(cmd, func))
    
    # 3. EXTERNAL GATES
    if get_chk_handler: app.add_handler(get_chk_handler())
    if get_pp_handler: app.add_handler(get_pp_handler())
    if get_sh_handler: app.add_handler(get_sh_handler())
    if get_pyu_handler: app.add_handler(get_pyu_handler())
    
    # 4. CALLBACKS & FILTERS
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, anti_ad_filter))
    
    print("🦇 Online! Database & Credits Active.")
    
    while True:
        try:
            app.run_polling(drop_pending_updates=True)
            break
        except Conflict:
            print("⚠️ Conflict detected! Waiting 15s...")
            time.sleep(15)
        except Exception as e:
            print(f"⚠️ Stopped: {e}")
            break

if __name__ == "__main__":
    main()
