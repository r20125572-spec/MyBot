import json
import os
import re
import random
import string
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, ContextTypes
from config import OWNER_ID, SUPPORT_LINK

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 DATABASE FILES 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DB_FILE = "plans_db.json"
CODES_FILE = "codes_db.json"

def load_db(file):
    if not os.path.exists(file):
        return {}
    with open(file, 'r') as f:
        return json.load(f)

def save_db(file, data):
    with open(file, 'w') as f:
        json.dump(data, f, indent=4)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 CORE LOGIC FUNCTIONS 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_user(user_id: int) -> dict:
    """Get user data. Creates new user with 150 Trial credits if not exists."""
    db = load_db(DB_FILE)
    uid = str(user_id)
    if uid not in db:
        db[uid] = {
            "plan": "Trial",
            "credits": 150,  # ✅ UPDATED TO 150
            "expires_at": None,
            "activated_at": None,
            "receipt_id": None
        }
        save_db(DB_FILE, db)
    return db[uid]

def is_premium(user_id: int) -> bool:
    """Check if user has active premium. Auto-reverts to Trial with 0 credits if expired."""
    db = load_db(DB_FILE)
    uid = str(user_id)
    if uid not in db: return False
    
    user = db[uid]
    if user['plan'] == "Trial": return False
    
    # Check expiration
    if user.get('expires_at'):
        exp_time = datetime.strptime(user['expires_at'], "%Y-%m-%d %H:%M:%S")
        if datetime.now() > exp_time:
            # Premium Expired -> Revert to Trial with 0 credits
            user['plan'] = "Trial"
            user['credits'] = 0 
            user['expires_at'] = None
            db[uid] = user
            save_db(DB_FILE, db)
            return False
    return True

def deduct_credit(user_id: int) -> bool:
    """Deducts 1 credit. Returns False if out of credits (and not premium)."""
    if is_premium(user_id): return True
    
    db = load_db(DB_FILE)
    uid = str(user_id)
    user = db[uid]
    
    if user['credits'] > 0:
        user['credits'] -= 1
        db[uid] = user
        save_db(DB_FILE, db)
        return True
    return False

def get_user_ui_text(user_id: int) -> str:
    """Returns the specific Access and Credits text for profile UI."""
    user = get_user(user_id)
    plan = user['plan']
    
    if is_premium(user_id):
        credits_txt = "∞ Uɴʟɪᴍɪᴛᴇᴅ"
    else:
        credits_txt = str(user['credits'])
        
    return f"Aᴄᴄᴇꜱꜱ ➺ {plan}\nCʀᴇᴅɪᴛꜱ ➺ {credits_txt}"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 OWNER COMMANDS 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def cmd_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args:
        await update.message.reply_text("❌ Usage: /sub<userid>Elite\nExample: /sub123456789Root", parse_mode="HTML")
        return

    raw = context.args[0]
    match = re.match(r"(\d+)(Elite|Root)", raw)
    if not match:
        await update.message.reply_text("❌ Invalid format. Use /sub<userid>Elite or /sub<userid>Root", parse_mode="HTML")
        return

    target_id = match.group(1)
    plan_name = match.group(2)
    days = 15 if plan_name == "Elite" else 30
    
    db = load_db(DB_FILE)
    now = datetime.now()
    expire = now + timedelta(days=days)
    receipt = "PAY-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    
    db[target_id] = {
        "plan": plan_name,
        "credits": 999999, # Represents unlimited
        "expires_at": expire.strftime("%Y-%m-%d %H:%M:%S"),
        "activated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "receipt_id": receipt
    }
    save_db(DB_FILE, db)

    # Send Congrats Message to User
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("SUPPORT", url=SUPPORT_LINK)]])
    congrats = (
        "Cᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴꜱ! 🎉 Yᴏᴜʀ ᴀᴄᴄᴇꜱꜱ ʜᴀꜱ ʙᴇᴇɴ ᴀᴄᴛɪᴠᴀᴛᴇᴅ.\n\n"
        f"Uꜱᴇʀ ➺ {target_id}\n"
        f"Aᴄᴄᴇꜱꜱ ➺ {plan_name}\n"
        f"Dᴜʀᴀᴛɪᴏɴ ➺ {days} Dᴀʏꜱ\n"
        f"Cʀᴇᴅɪᴛꜱ Aᴅᴅᴇᴅ ➺ ∞\n"
        f"Rᴇᴄᴇɪᴘᴛ ID ➺ {receipt}\n\n"
        "Pʟᴇᴀꜱᴇ ꜱᴀᴠᴇ ᴛʜɪꜱ ʀᴇᴄᴇɪᴘᴛ ID."
    )
    try:
        await context.bot.send_message(chat_id=int(target_id), text=congrats, parse_mode="HTML", reply_markup=kb)
        await update.message.reply_text(f"✅ {plan_name} activated for {target_id}.", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to message user. Error: {str(e)[:50]}", parse_mode="HTML")

async def cmd_resub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("❌ Usage: /resub<userid>", parse_mode="HTML")
        return

    target_id = context.args[0]
    db = load_db(DB_FILE)
    if target_id in db:
        db[target_id] = {"plan": "Trial", "credits": 0, "expires_at": None, "activated_at": None, "receipt_id": None}
        save_db(DB_FILE, db)
        await update.message.reply_text(f"✅ Premium cancelled for {target_id}. Reverted to Trial.", parse_mode="HTML")
    else:
        await update.message.reply_text("❌ User not found in database.", parse_mode="HTML")

async def cmd_allplans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    db = load_db(DB_FILE)
    active_plans = [uid for uid, data in db.items() if data['plan'] != "Trial"]
    
    if not active_plans:
        await update.message.reply_text("❌ No active plans running.", parse_mode="HTML")
        return

    text = "Aᴄᴛɪᴠᴇ Pʟᴀɴꜱ\n━━━━━━━━━━━━━━━━━━━━\n"
    for uid in active_plans:
        u = db[uid]
        text += (
            f"\nUꜱᴇʀ ID ➺ <code>{uid}</code>\n"
            f"Aᴄᴄᴇꜱꜱ ➺ {u['plan']}\n"
            f"Bᴏᴜɢʜᴛ ➺ {u.get('activated_at', 'N/A')}\n"
            f"Exᴘɪʀᴇꜱ ➺ {u.get('expires_at', 'N/A')}\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
    await update.message.reply_text(text, parse_mode="HTML")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 ACCESS CODE GENERATOR 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def cmd_oneday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    code = "1D-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    db = load_db(CODES_FILE)
    db[code] = {"days": 1}
    save_db(CODES_FILE, db)
    await update.message.reply_text(f"🔑 1 Dᴀʏ Aᴄᴄᴇꜱꜱ Cᴏᴅᴇ:\n\n<code>{code}</code>", parse_mode="HTML")

async def cmd_threeday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    code = "3D-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    db = load_db(CODES_FILE)
    db[code] = {"days": 3}
    save_db(CODES_FILE, db)
    await update.message.reply_text(f"🔑 3 Dᴀʏꜱ Aᴄᴄᴇꜱꜱ Cᴏᴅᴇ:\n\n<code>{code}</code>", parse_mode="HTML")

async def cmd_rm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Usage: /rm <code>", parse_mode="HTML")
        return

    code = context.args[0]
    db = load_db(CODES_FILE)
    
    if code not in db:
        await update.message.reply_text("❌ Iɴᴠᴀʟɪᴅ ᴏʀ ᴜꜱᴇᴅ ᴄᴏᴅᴇ.", parse_mode="HTML")
        return

    days = db[code]['days']
    del db[code]  # Delete code so it can't be reused
    save_db(CODES_FILE, db)

    # Activate Code Plan
    user_db = load_db(DB_FILE)
    uid = str(update.effective_user.id)
    now = datetime.now()
    expire = now + timedelta(days=days)
    receipt = "CODE-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    
    user_db[uid] = {
        "plan": f"Code ({days}D)",
        "credits": 999999,
        "expires_at": expire.strftime("%Y-%m-%d %H:%M:%S"),
        "activated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "receipt_id": receipt
    }
    save_db(DB_FILE, user_db)

    kb = InlineKeyboardMarkup([[InlineKeyboardButton("SUPPORT", url=SUPPORT_LINK)]])
    congrats = (
        "Cᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴꜱ! 🎉 Yᴏᴜʀ ᴀᴄᴄᴇꜱꜱ ʜᴀꜱ ʙᴇᴇɴ ᴀᴄᴛɪᴠᴀᴛᴇᴅ.\n\n"
        f"Uꜱᴇʀ ➺ {uid}\n"
        f"Aᴄᴄᴇꜱꜱ ➺ {days} Dᴀʏꜱ Cᴏᴅᴇ\n"
        f"Dᴜʀᴀᴛɪᴏɴ ➺ {days} Dᴀʏꜱ\n"
        f"Cʀᴇᴅɪᴛꜱ Aᴅᴅᴇᴅ ➺ ∞\n"
        f"Rᴇᴄᴇɪᴘᴛ ID ➺ {receipt}\n\n"
        "Pʟᴇᴀꜱᴇ ꜱᴀᴠᴇ ᴛʜɪꜱ ʀᴇᴄᴇɪᴘᴛ ID."
    )
    await update.message.reply_text(congrats, parse_mode="HTML", reply_markup=kb)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 REGISTER HANDLERS 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_plans_handler():
    return [
        CommandHandler("sub", cmd_sub),      # /sub123456789Elite
        CommandHandler("resub", cmd_resub),  # /resub123456789
        CommandHandler("allplans", cmd_allplans),
        CommandHandler("oneday", cmd_oneday),
        CommandHandler("threeday", cmd_threeday),
        CommandHandler("rm", cmd_rm)         # /rm <code>
    ]
