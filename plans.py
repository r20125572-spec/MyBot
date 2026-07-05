import json
import os
import re
import random
import string
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, MessageHandler, filters, ContextTypes
from config import OWNER_ID

# 🦇 SUPPORT LINK 🦇
SUPPORT_LINK = "https://t.me/cardchkSupport"

DB_FILE    = "plans_db.json"
CODES_FILE = "codes_db.json"

def load_db(file):
    if not os.path.exists(file): return {}
    try:
        with open(file, 'r') as f: return json.load(f)
    except Exception: return {}

def save_db(file, data):
    with open(file, 'w') as f: json.dump(data, f, indent=4)

def get_user(user_id: int) -> dict:
    db  = load_db(DB_FILE)
    uid = str(user_id)
    if uid not in db:
        db[uid] = {"plan": "Trial", "credits": 150, "expires_at": None, "activated_at": None, "receipt_id": None}
        save_db(DB_FILE, db)
    return db[uid]

def is_premium(user_id: int) -> bool:
    db  = load_db(DB_FILE)
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
    db  = load_db(DB_FILE)
    uid = str(user_id)
    user = db[uid]
    if user['credits'] > 0:
        user['credits'] -= 1
        db[uid] = user
        save_db(DB_FILE, db)
        return True
    return False

def get_user_ui_text(user_id: int) -> str:
    user       = get_user(user_id)
    plan       = user['plan']
    credits_txt = "∞ Uɴʟɪᴍɪᴛᴇᴅ" if is_premium(user_id) else str(user['credits'])
    return f"Aᴄᴄᴇꜱꜱ ➺ {plan}\nCʀᴇᴅɪᴛꜱ ➺ {credits_txt}"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /sub COMMAND
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return

    if not context.args:
        await update.message.reply_text("❌ Usage: /sub <userid> Elite\nExample: /sub 123456789 Elite")
        return

    full_text = "".join(context.args)

    id_match = re.search(r"(\d+)", full_text)
    if not id_match:
        await update.message.reply_text("❌ No User ID found!")
        return

    target_id = id_match.group(1)

    plan_name = None
    if "elite" in full_text.lower():
        plan_name = "Elite"
    elif "root" in full_text.lower():
        plan_name = "Root"
    else:
        await update.message.reply_text("❌ Use /sub <id> Elite or /sub <id> Root")
        return

    days = 15 if plan_name == "Elite" else 30
    now  = datetime.now()
    db   = load_db(DB_FILE)
    db[target_id] = {
        "plan": plan_name,
        "credits": 999999,
        "expires_at":    (now + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S"),
        "activated_at":  now.strftime("%Y-%m-%d %H:%M:%S"),
        "receipt_id":    "PAY-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    }
    save_db(DB_FILE, db)

    kb  = InlineKeyboardMarkup([[InlineKeyboardButton("SUPPORT", url=SUPPORT_LINK)]])
    txt = (
        f"Cᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴꜱ! 🎉 Yᴏᴜʀ ᴀᴄᴄᴇꜱꜱ ʜᴀꜱ ʙᴇᴇɴ ᴀᴄᴛɪᴠᴀᴛᴇᴅ.\n\n"
        f"Uꜱᴇʀ ➺ {target_id}\n"
        f"Aᴄᴄᴇꜱꜱ ➺ {plan_name}\n"
        f"Dᴜʀᴀᴛɪᴏɴ ➺ {days} Dᴀʏꜱ\n"
        f"Cʀᴇᴅɪᴛꜱ Aᴅᴅᴇᴅ ➺ ∞\n"
        f"Rᴇᴄᴇɪᴘᴛ ID ➺ {db[target_id]['receipt_id']}\n\n"
        "Pʟᴇᴀꜱᴇ ꜱᴀᴠᴇ ᴛʜɪꜱ ʀᴇᴄᴇɪᴘᴛ ID."
    )

    try:
        await context.bot.send_message(chat_id=int(target_id), text=txt, parse_mode="HTML", reply_markup=kb)
        await update.message.reply_text(f"✅ {plan_name} activated for {target_id}.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)[:50]}")

async def cmd_resub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("❌ Usage: /resub <userid>"); return
    tid = context.args[0]
    db  = load_db(DB_FILE)
    if tid in db:
        db[tid] = {"plan": "Trial", "credits": 0, "expires_at": None, "activated_at": None, "receipt_id": None}
        save_db(DB_FILE, db)
        await update.message.reply_text(f"✅ Premium cancelled for {tid}.")
    else:
        await update.message.reply_text("❌ User not found.")

async def cmd_allplans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    db     = load_db(DB_FILE)
    active = [uid for uid, d in db.items() if d['plan'] != "Trial"]
    if not active:
        await update.message.reply_text("❌ No active plans."); return
    txt = "Aᴄᴛɪᴠᴇ Pʟᴀɴꜱ\n━━━━━━━━━━━━━━━━━━━━\n"
    for uid in active:
        u    = db[uid]
        txt += (
            f"\nUꜱᴇʀ ID ➺ <code>{uid}</code>\n"
            f"Aᴄᴄᴇꜱꜱ ➺ {u['plan']}\n"
            f"Bᴏᴜɢʜᴛ ➺ {u.get('activated_at', 'N/A')}\n"
            f"Exᴘɪʀᴇꜱ ➺ {u.get('expires_at', 'N/A')}\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
    await update.message.reply_text(txt, parse_mode="HTML")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /gen COMMAND
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("❌ Usage: /gen <amount>\nExample: /gen 100"); return
    amount = context.args[0]
    code   = f"CR-{amount}-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    db     = load_db(CODES_FILE)
    db[code] = {"type": "credits", "value": int(amount)}
    save_db(CODES_FILE, db)
    await update.message.reply_text(f"🔑 Cʀᴇᴅɪᴛ Cᴏᴅᴇ ({amount}):\n\n<code>{code}</code>", parse_mode="HTML")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /key<n> COMMAND
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    match = re.match(r"^/key(\d+)", update.message.text)
    if not match: return
    days   = int(match.group(1))
    code   = f"KEY-{days}D-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    db     = load_db(CODES_FILE)
    db[code] = {"type": "days", "value": days}
    save_db(CODES_FILE, db)
    await update.message.reply_text(f"🔑 {days} Dᴀʏꜱ Pʀᴇᴍɪᴜᴍ Kᴇʏ:\n\n<code>{code}</code>", parse_mode="HTML")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /rm COMMAND
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_rm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Usage: /rm <code>"); return
    code = context.args[0]
    db   = load_db(CODES_FILE)

    if code not in db:
        await update.message.reply_text("❌ Iɴᴠᴀʟɪᴅ ᴏʀ ᴜꜱᴇᴅ ᴄᴏᴅᴇ."); return

    code_data = db[code]
    del db[code]
    save_db(CODES_FILE, db)

    user_db = load_db(DB_FILE)
    uid     = str(update.effective_user.id)

    if code_data["type"] == "credits":
        user = get_user(update.effective_user.id)
        user['credits'] += code_data["value"]
        user_db[uid] = user
        save_db(DB_FILE, user_db)
        await update.message.reply_text(
            f"✅ Cʀᴇᴅɪᴛꜱ Aᴅᴅᴇᴅ!\n\n"
            f"Cʀᴇᴅɪᴛꜱ Aᴅᴅᴇᴅ ➺ {code_data['value']}\n"
            f"Tᴏᴛᴀʟ Cʀᴇᴅɪᴛꜱ ➺ {user['credits']}",
            parse_mode="HTML"
        )
    else:
        days = code_data["value"]
        now  = datetime.now()
        user_db[uid] = {
            "plan":         f"Key ({days}D)",
            "credits":      999999,
            "expires_at":   (now + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S"),
            "activated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "receipt_id":   "KEY-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        }
        save_db(DB_FILE, user_db)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("SUPPORT", url=SUPPORT_LINK)]])
        await update.message.reply_text(
            f"Cᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴꜱ! 🎉 Yᴏᴜʀ ᴀᴄᴄᴇꜱꜱ ʜᴀꜱ ʙᴇᴇɴ ᴀᴄᴛɪᴠᴀᴛᴇᴅ.\n\n"
            f"Uꜱᴇʀ ➺ {uid}\n"
            f"Aᴄᴄᴇꜱꜱ ➺ {days} Dᴀʏꜱ Kᴇʏ\n"
            f"Dᴜʀᴀᴛɪᴏɴ ➺ {days} Dᴀʏꜱ\n"
            f"Cʀᴇᴅɪᴛꜱ Aᴅᴅᴇᴅ ➺ ∞\n"
            f"Rᴇᴄᴇɪᴘᴛ ID ➺ {user_db[uid]['receipt_id']}\n\n"
            "Pʟᴇᴀꜱᴇ ꜱᴀᴠᴇ ᴛʜɪꜱ ʀᴇᴄᴇɪᴘᴛ ID.",
            parse_mode="HTML",
            reply_markup=kb
        )

def get_plans_handler():
    return [
        CommandHandler("sub",     cmd_sub),
        CommandHandler("resub",   cmd_resub),
        CommandHandler("allplans", cmd_allplans),
        CommandHandler("gen",     cmd_gen),
        MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Regex(r"^/key\d+$"), cmd_key),
        CommandHandler("rm",      cmd_rm),
    ]
