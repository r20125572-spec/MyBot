import json
import os
import re
import random
import string
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, ContextTypes
from config import OWNER_ID

# Fallback in case SUPPORT_LINK is missing in config
try:
    from config import SUPPORT_LINK
except ImportError:
    SUPPORT_LINK = "https://t.me/cardchkSupport"

DB_FILE = "plans_db.json"
CODES_FILE = "codes_db.json"

def load_db(file):
    if not os.path.exists(file): return {}
    try:
        with open(file, 'r') as f: return json.load(f)
    except Exception: return {}

def save_db(file, data):
    with open(file, 'w') as f: json.dump(data, f, indent=4)

def get_user(user_id: int) -> dict:
    db = load_db(DB_FILE)
    uid = str(user_id)
    if uid not in db:
        db[uid] = {"plan": "Trial", "credits": 150, "expires_at": None, "activated_at": None, "receipt_id": None}
        save_db(DB_FILE, db)
    return db[uid]

def is_premium(user_id: int) -> bool:
    db = load_db(DB_FILE)
    uid = str(user_id)
    if uid not in db: return False
    user = db[uid]
    if user['plan'] == "Trial": return False
    if user.get('expires_at'):
        try:
            if datetime.now() > datetime.strptime(user['expires_at'], "%Y-%m-%d %H:%M:%S"):
                db[uid] = {"plan": "Trial", "credits": 0, "expires_at": None, "activated_at": None, "receipt_id": None}
                save_db(DB_FILE, db)
                return False
        except ValueError: pass
    return True

def deduct_credit(user_id: int) -> bool:
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
    user = get_user(user_id)
    plan = user['plan']
    credits_txt = "∞ Uɴʟɪᴍɪᴛᴇᴅ" if is_premium(user_id) else str(user['credits'])
    return f"Aᴄᴄᴇꜱꜱ ➺ {plan}\nCʀᴇᴅɪᴛꜱ ➺ {credits_txt}"

async def cmd_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args: await update.message.reply_text("❌ Usage: /sub<userid>Elite"); return
    match = re.match(r"(\d+)(Elite|Root)", context.args[0])
    if not match: await update.message.reply_text("❌ Use /sub<id>Elite or /sub<id>Root"); return
    target_id, plan_name = match.group(1), match.group(2)
    days = 15 if plan_name == "Elite" else 30
    now = datetime.now()
    db = load_db(DB_FILE)
    db[target_id] = {"plan": plan_name, "credits": 999999, "expires_at": (now + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S"), "activated_at": now.strftime("%Y-%m-%d %H:%M:%S"), "receipt_id": "PAY-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))}
    save_db(DB_FILE, db)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("SUPPORT", url=SUPPORT_LINK)]])
    txt = f"Cᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴꜱ! 🎉 Yᴏᴜʀ ᴀᴄᴄᴇꜱꜱ ʜᴀꜱ ʙᴇᴇɴ ᴀᴄᴛɪᴠᴀᴛᴇᴅ.\n\nUꜱᴇʀ ➺ {target_id}\nAᴄᴄᴇꜱꜱ ➺ {plan_name}\nDᴜʀᴀᴛɪᴏɴ ➺ {days} Dᴀʏꜱ\nCʀᴇᴅɪᴛꜱ Aᴅᴅᴇᴅ ➺ ∞\nRᴇᴄᴇɪᴘᴛ ID ➺ {db[target_id]['receipt_id']}\n\nPʟᴇᴀꜱᴇ ꜱᴀᴠᴇ ᴛʜɪꜱ ʀᴇᴄᴇɪᴘᴛ ID."
    try:
        await context.bot.send_message(chat_id=int(target_id), text=txt, parse_mode="HTML", reply_markup=kb)
        await update.message.reply_text(f"✅ {plan_name} activated for {target_id}.")
    except Exception as e: await update.message.reply_text(f"❌ Error: {str(e)[:50]}")

async def cmd_resub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args or not context.args[0].isdigit(): await update.message.reply_text("❌ Usage: /resub<userid>"); return
    tid = context.args[0]
    db = load_db(DB_FILE)
    if tid in db:
        db[tid] = {"plan": "Trial", "credits": 0, "expires_at": None, "activated_at": None, "receipt_id": None}
        save_db(DB_FILE, db)
        await update.message.reply_text(f"✅ Premium cancelled for {tid}.")
    else: await update.message.reply_text("❌ User not found.")

async def cmd_allplans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    db = load_db(DB_FILE)
    active = [uid for uid, d in db.items() if d['plan'] != "Trial"]
    if not active: await update.message.reply_text("❌ No active plans."); return
    txt = "Aᴄᴛɪᴠᴇ Pʟᴀɴꜱ\n━━━━━━━━━━━━━━━━━━━━\n"
    for uid in active:
        u = db[uid]
        txt += f"\nUꜱᴇʀ ID ➺ <code>{uid}</code>\nAᴄᴄᴇꜱꜱ ➺ {u['plan']}\nBᴏᴜɢʜᴛ ➺ {u.get('activated_at', 'N/A')}\nExᴘɪʀᴇꜱ ➺ {u.get('expires_at', 'N/A')}\n━━━━━━━━━━━━━━━━━━━━"
    await update.message.reply_text(txt, parse_mode="HTML")

async def cmd_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args or not context.args[0].isdigit(): await update.message.reply_text("❌ Usage: /gen300"); return
    amount = context.args[0]
    code = f"CR-{amount}-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    db = load_db(CODES_FILE)
    db[code] = {"type": "credits", "value": int(amount)}
    save_db(CODES_FILE, db)
    await update.message.reply_text(f"🔑 Cʀᴇᴅɪᴛ Cᴏᴅᴇ ({amount}):\n\n<code>{code}</code>", parse_mode="HTML")

async def cmd_oneday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    code = "1D-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    db = load_db(CODES_FILE)
    db[code] = {"type": "days", "value": 1}
    save_db(CODES_FILE, db)
    await update.message.reply_text(f"🔑 1 Dᴀʏ Aᴄᴄᴇꜱꜱ Cᴏᴅᴇ:\n\n<code>{code}</code>", parse_mode="HTML")

async def cmd_threeday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    code = "3D-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    db = load_db(CODES_FILE)
    db[code] = {"type": "days", "value": 3}
    save_db(CODES_FILE, db)
    await update.message.reply_text(f"🔑 3 Dᴀʏꜱ Aᴄᴄᴇꜱꜱ Cᴏᴅᴇ:\n\n<code>{code}</code>", parse_mode="HTML")

async def cmd_rm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: await update.message.reply_text("❌ Usage: /rm <code>"); return
    code = context.args[0]
    db = load_db(CODES_FILE)
    if code not in db: await update.message.reply_text("❌ Iɴᴠᴀʟɪᴅ ᴏʀ ᴜꜱᴇᴅ ᴄᴏᴅᴇ."); return
    code_data = db[code]
    del db[code]
    save_db(CODES_FILE, db)
    user_db = load_db(DB_FILE)
    uid = str(update.effective_user.id)
    
    if code_data["type"] == "credits":
        user = get_user(update.effective_user.id)
        user['credits'] += code_data["value"]
        user_db[uid] = user
        save_db(DB_FILE, user_db)
        await update.message.reply_text(f"✅ Cʀᴇᴅɪᴛꜱ Aᴅᴅᴇᴅ!\n\nCʀᴇᴅɪᴛꜱ Aᴅᴅᴇᴅ ➺ {code_data['value']}\nTᴏᴛᴀʟ Cʀᴇᴅɪᴛꜱ ➺ {user['credits']}", parse_mode="HTML")
    else:
        days = code_data["value"]
        now = datetime.now()
        user_db[uid] = {"plan": f"Code ({days}D)", "credits": 999999, "expires_at": (now + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S"), "activated_at": now.strftime("%Y-%m-%d %H:%M:%S"), "receipt_id": "CODE-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))}
        save_db(DB_FILE, user_db)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("SUPPORT", url=SUPPORT_LINK)]])
        await update.message.reply_text(f"Cᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴꜱ! 🎉 Yᴏᴜʀ ᴀᴄᴄᴇꜱꜱ ʜᴀꜱ ʙᴇᴇɴ ᴀᴄᴛɪᴠᴀᴛᴇᴅ.\n\nUꜱᴇʀ ➺ {uid}\nAᴄᴄᴇꜱꜱ ➺ {days} Dᴀʏꜱ Cᴏᴅᴇ\nDᴜʀᴀᴛɪᴏɴ ➺ {days} Dᴀʏꜱ\nCʀᴇᴅɪᴛꜱ Aᴅᴅᴇᴅ ➺ ∞\nRᴇᴄᴇɪᴘᴛ ID ➺ {user_db[uid]['receipt_id']}\n\nPʟᴇᴀꜱᴇ ꜱᴀᴠᴇ ᴛʜɪꜱ ʀᴇᴄᴇɪᴘᴛ ID.", parse_mode="HTML", reply_markup=kb)

def get_plans_handler():
    return [
        CommandHandler("sub", cmd_sub), CommandHandler("resub", cmd_resub),
        CommandHandler("allplans", cmd_allplans), CommandHandler("gen", cmd_gen),
        CommandHandler("oneday", cmd_oneday), CommandHandler("threeday", cmd_threeday),
        CommandHandler("rm", cmd_rm)
    ]
