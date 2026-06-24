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
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.error import Conflict

from config import BOT_TOKEN, OWNER_ID, VERSION, DEV_LINK, BOT_PHOTO

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 HARDCODED LINKS (NO A_ToolsX LEAK)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CHANNEL_USERNAME = "@Batcardchk"
GROUP_USERNAME = "@batcardchkGroup"
CHANNEL_LINK = "https://t.me/Batcardchk"
GROUP_LINK = "https://t.me/batcardchkGroup"
SUPPORT_LINK = "https://t.me/cardchkSupport"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 FAST SAFE IMPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
try: from chk import get_chk_handler
except: get_chk_handler = None
try: from pp import get_pp_handler
except: get_pp_handler = None
try: from sh import get_sh_handler
except: get_sh_handler = None
try: from pyu import get_pyu_handler
except: get_pyu_handler = None
try: from b3 import get_b3_handler
except: get_b3_handler = None
get_plans_handler = lambda: []

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 BLOCKED WORDS (A_ToolsX FULLY BLOCKED)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BLOCK_WORDS = (
    "http://", "https://", "www.", "t.me", ".com", ".net", ".org",
    ".io", ".me", ".xyz", ".tk", ".ml", ".cf", ".ga", ".ru", ".in",
    ".pw", "telegram.me", "joinchat", "://",
    "a_toolsx", "a-tools", "atoolsx", "a tools x", "a-tools x"
)

async def anti_ad_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or msg.from_user.id == OWNER_ID: return
    # Check both text and caption (photo messages with text)
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

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 PREMIUM ACTIVATION MESSAGE TO USER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def send_activation_msg(user_id: int, plan: str, days: int, context: ContextTypes.DEFAULT_TYPE) -> str:
    receipt = gen_receipt()
    name = "Unknown"
    try:
        chat = await context.bot.get_chat(user_id)
        name = chat.first_name or "Unknown"
    except: pass
    txt = (
        "Cᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴꜱ! 🎉 Yᴏᴜʀ ᴀᴄᴄᴇꜱꜱ ʜᴀꜱ ʙᴇᴇɴ ᴀᴄᴛɪᴠᴀᴛᴇᴅ.\n\n"
        f"Uꜱᴇʀ ➺ {name}\n"
        f"Aᴄᴄᴇꜱꜱ ➺ {plan.upper()}\n"
        f"Dᴜʀᴀᴛɪᴏɴ ➺ {days} Dᴀʏꜱ\n"
        f"Cʀᴇᴅɪᴛꜱ Aᴅᴅᴇᴅ ➺ ∞\n"
        f"Rᴇᴄᴇɪᴘᴘᴛ ID ➺ <code>{receipt}</code>\n\n"
        "Pʟᴇᴀꜱᴇ ꜱᴀᴠᴇ ᴛʜɪꜱ ʀᴇᴄᴇɪᴘᴘᴛ ID."
    )
    try:
        await context.bot.send_message(chat_id=user_id, text=txt, parse_mode="HTML")
    except: pass
    return receipt

def ui_profile(user, context: ContextTypes.DEFAULT_TYPE):
    u = user.username or "None"
    ud = context.bot_data.get('user_data', {}).get(str(user.id), {})
    plan = ud.get('plan', 'FREE').upper()
    credits = ud.get('credits', 150)
    status = f"Pʟᴀɴ ➺ {plan}\nCʀᴇᴅɪᴛꜱ ➺ {credits}"
    if ud.get('expires', 0) > time.time():
        status += f"\nExᴘɪʀᴇꜱ ➺ {datetime.fromtimestamp(ud['expires']).strftime('%Y-%m-%d')}"
    return (
        f"Uꜱᴇʀ ➺ {u}\n"
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

async def fetch_bin(url: str) -> dict:
    try:
        req = urllib.request.Request(url, headers={"Accept-Version": "3", "User-Agent": "Mozilla/5.0"})
        loop = asyncio.get_running_loop()
        def do_req():
            with urllib.request.urlopen(req, timeout=10) as r: return json.loads(r.read().decode('utf-8'))
        return await loop.run_in_executor(None, do_req)
    except: return {}

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
    c_data = data.get("country") or {}
    b_data = data.get("bank") or {}
    brand = (data.get("brand") or "N/A").upper()
    brand_emoji = {"VISA": "🔵", "MASTERCARD": "🔴", "AMEX": "🟡"}.get(brand, "⚪")
    type_emoji = {"CREDIT": "💳", "DEBIT": "🏦"}.get((data.get("type") or "").upper(), "💳")
    txt = (
        "━━━━━━━━━━━━━━━━━━━━\n🦇 BIN LOOKUP RESULT\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"BIN ➺ <code>{bin_num}</code>\nSCHEME ➺ {(data.get('scheme') or 'N/A').upper()}\n"
        f"TYPE ➺ {type_emoji} {(data.get('type') or 'N/A').upper()}\nBRAND ➺ {brand_emoji} {brand}\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n🌍 COUNTRY INFO\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"NAME ➺ {c_data.get('emoji', '🌍')} {c_data.get('name', 'N/A')}\nCODE ➺ {c_data.get('alpha2', '??')}\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n🏦 BANK INFO\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"BANK ➺ {b_data.get('name', 'N/A')}\n"
    )
    if b_data.get("url"): txt += f"URL ➺ {b_data.get('url')}\n"
    txt += "\n━━━━━━━━━━━━━━━━━━━━"
    try: await status.edit_text(txt, parse_mode="HTML", disable_web_page_preview=True)
    except: pass

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ud = context.bot_data.setdefault('user_data', {})
    uid = str(user.id)
    if uid not in ud:
        ud[uid] = {"name": user.first_name, "joined": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "credits": 150, "plan": "FREE", "expires": 0}
    if await is_joined(user.id, context):
        await update.message.reply_text(text=ui_profile(user, context), parse_mode="HTML", reply_markup=kb_main(), disable_web_page_preview=True)
    else:
        cap = "BATMAN CARD CHECKER\n\nAccess Required\n━━━━━━━━━━━━━━━━━━━━\nJoin both channels to\nunlock the bot.\n━━━━━━━━━━━━━━━━━━━━"
        try: await update.message.reply_photo(photo=BOT_PHOTO, caption=cap, parse_mode="HTML", reply_markup=kb_force())
        except: await update.message.reply_text(text=cap, parse_mode="HTML", reply_markup=kb_force())

async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Aᴄᴄᴇꜱꜱ ➺ Cᴏʀᴇ 🎀\nSᴘᴀɴ ➺ [7 Dᴀʏꜱ]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ\nPʀɪᴄᴇ ➺ 10$\n━━━━━━━━━━━━━━━━\nAᴄᴄᴇꜱꜱ ➺ Eʟɪᴛᴇ ⭐️\nSᴘᴀɴ ➺ [15 Dᴀʏꜱ]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ\nPʀɪᴄᴇ ➺ 15$\n━━━━━━━━━━━━━━━━\nAᴄᴄᴇꜱꜱ ➺ Rᴏᴏᴛ 👑\nSᴘᴀɴ ➺ [30 Dᴀʏꜱ]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ\nPʀɪᴄᴇ ➺ 30$", parse_mode="HTML", reply_markup=kb_price())

async def cmd_allcm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    await update.message.reply_text(
        f"BATMAN BOT - ALL COMMANDS\n━━━━━━━━━━━━━━━━━━\nVersion: {VERSION}\n━━━━━━━━━━━━━━━━━━\n\n"
        "USER COMMANDS\n━━━━━━━━━━━━━━━━━━\n"
        "/start - Start the bot\n"
        "/plan - View pricing plans\n"
        "/bin - Check BIN details\n"
        "/chk - Stripe check\n"
        "/pp - PayPal check\n"
        "/sh - Shopify check\n"
        "/pyu - PayU check\n"
        "/b3 - Braintree Auth\n"
        "/rm - Redeem code\n\n\n"
        "OWNER COMMANDS\n━━━━━━━━━━━━━━━━━━\n"
        "/info - Get user info\n"
        "/allcm - Show this\n"
        "/gen - Gen credit code\n"
        "/key10 - Gen premium key 10$\n"
        "/key20 - Gen premium key 20$\n"
        "/key30 - Gen premium key 30$\n"
        "/sub - Grant premium\n"
        "/resub - Remove premium\n"
        "/allplans - View active plans\n"
        "/oneday - Grant 1 day access\n"
        "/threeday - Grant 3 days access\n"
        "/onchk /offchk - Stripe gate\n"
        "/onpp /offpp - PayPal gate\n"
        "/onsh /offsh - Shopify gate\n"
        "/onpyu /offpyu - PayU gate\n"
        "━━━━━━━━━━━━━━━━━━", parse_mode="HTML"
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 IMPROVED /info — FAST & DETAILED
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not update.message.reply_to_message and not context.args:
        await update.message.reply_text(
            "❌ INVALID USAGE\n\n"
            "How to get User ID:\n"
            "1. Ask user to send /start\n"
            "2. Copy the 'USER ID' from menu\n"
            "3. Then type: /info 123456789\n\n"
            "Or simply reply to their message with /info",
            parse_mode="HTML"
        )
        return

    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
    else:
        target_id = await resolve_user(context.args[0], context)

    if not target_id:
        await update.message.reply_text("❌ User not found.", parse_mode="HTML")
        return

    # Fetch Telegram profile + local data at same time for speed
    async def fetch_tg():
        try:
            u = await context.bot.get_chat(target_id)
            return u.first_name or "N/A", u.username or "None", u.id
        except:
            return "N/A", "None", target_id

    name, username, uid = await fetch_tg()
    udata = context.bot_data.get('user_data', {}).get(str(uid), {})

    plan = udata.get('plan', 'FREE').upper()
    credits = udata.get('credits', 150)
    expires = udata.get('expires', 0)
    joined = udata.get('joined', 'N/A')

    txt = (
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🦇 USER INFO\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Name ➺ {name}\n"
        f"Username ➺ @{username}\n"
        f"User ID ➺ <code>{uid}</code>\n"
        f"Joined Bot ➺ {joined}\n"
        f"Plan ➺ {plan}\n"
        f"Credits ➺ {credits}\n"
    )
    if expires > time.time():
        txt += f"Expires ➺ {datetime.fromtimestamp(expires).strftime('%Y-%m-%d %H:%M')}\n"
        remaining = int((expires - time.time()) / 86400)
        txt += f"Remaining ➺ {remaining} Days\n"
    else:
        txt += "Status ➺ Inactive / Free\n"
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
    await update.message.reply_text(f"✅ PREMIUM KEY GENERATED\n━━━━━━━━━━━━━━━━━━━━\n\nKey: <code>{code}</code>\nPlan: {plan.upper()}\nDays: {days}\n━━━━━━━━━━━━━━━━━━━━", parse_mode="HTML")

async def cmd_key10(update: Update, context: ContextTypes.DEFAULT_TYPE): await cmd_gen_key(update, context, "core", 7)
async def cmd_key20(update: Update, context: ContextTypes.DEFAULT_TYPE): await cmd_gen_key(update, context, "elite", 15)
async def cmd_key30(update: Update, context: ContextTypes.DEFAULT_TYPE): await cmd_gen_key(update, context, "root", 30)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 /oneday /threeday /sub — SENDS ACTIVATION MSG TO USER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_oneday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args: await update.message.reply_text("❌ Usage: /oneday <user_id>", parse_mode="HTML"); return
    uid = await resolve_user(context.args[0], context)
    if not uid: await update.message.reply_text("❌ User not found.", parse_mode="HTML"); return
    ud = context.bot_data.setdefault('user_data', {}); uid_str = str(uid)
    if uid_str not in ud: ud[uid_str] = {"name": "User", "credits": 150, "plan": "FREE", "expires": 0}
    ud[uid_str]["plan"] = "core"; ud[uid_str]["expires"] = time.time() + 86400
    receipt = await send_activation_msg(uid, "core", 1, context)
    await update.message.reply_text(f"✅ Granted 1 Day Access to <code>{uid}</code>\nReceipt: <code>{receipt}</code>", parse_mode="HTML")

async def cmd_threeday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args: await update.message.reply_text("❌ Usage: /threeday <user_id>", parse_mode="HTML"); return
    uid = await resolve_user(context.args[0], context)
    if not uid: await update.message.reply_text("❌ User not found.", parse_mode="HTML"); return
    ud = context.bot_data.setdefault('user_data', {}); uid_str = str(uid)
    if uid_str not in ud: ud[uid_str] = {"name": "User", "credits": 150, "plan": "FREE", "expires": 0}
    ud[uid_str]["plan"] = "core"; ud[uid_str]["expires"] = time.time() + (3 * 86400)
    receipt = await send_activation_msg(uid, "core", 3, context)
    await update.message.reply_text(f"✅ Granted 3 Days Access to <code>{uid}</code>\nReceipt: <code>{receipt}</code>", parse_mode="HTML")

async def cmd_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if len(context.args) < 2: 
        await update.message.reply_text("❌ INVALID USAGE\n\nCorrect Usage:\n/sub 123456789 30\n\nNote: Second parameter MUST be a number (days).", parse_mode="HTML"); return
    uid = await resolve_user(context.args[0], context)
    if not uid: await update.message.reply_text("❌ User not found.", parse_mode="HTML"); return
    try:
        days = int(context.args[1]) 
        plan = "root" if days >= 30 else "elite" if days >= 15 else "core"
        ud = context.bot_data.setdefault('user_data', {}); uid_str = str(uid)
        if uid_str not in ud: ud[uid_str] = {"name": "User", "credits": 150, "plan": "FREE", "expires": 0}
        ud[uid_str]["plan"] = plan; ud[uid_str]["expires"] = time.time() + (days * 86400)
        receipt = await send_activation_msg(uid, plan, days, context)
        await update.message.reply_text(f"✅ Granted {days} Days ({plan.upper()}) to <code>{uid}</code>\nReceipt: <code>{receipt}</code>", parse_mode="HTML")
    except ValueError:
        await update.message.reply_text("❌ INVALID DAYS\nThe second parameter must be a number.\nExample: /sub 123456789 30", parse_mode="HTML")

async def cmd_resub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args: await update.message.reply_text("❌ Usage: /resub <user_id>", parse_mode="HTML"); return
    uid = await resolve_user(context.args[0], context)
    if not uid: await update.message.reply_text("❌ User not found.", parse_mode="HTML"); return
    ud = context.bot_data.setdefault('user_data', {}); uid_str = str(uid)
    if uid_str in ud: ud[uid_str]["plan"] = "FREE"; ud[uid_str]["expires"] = 0; await update.message.reply_text(f"✅ Removed premium from <code>{uid}</code>", parse_mode="HTML")
    else: await update.message.reply_text("❌ User not found.", parse_mode="HTML")

async def cmd_allplans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    users = context.bot_data.get('user_data', {}); txt = "🦇 ACTIVE PLANS\n━━━━━━━━━━━━━━━━━━━━\n\n"; found = False
    for uid, data in users.items():
        if data.get('expires', 0) > time.time(): found = True; txt += f"ID: <code>{uid}</code>\nPlan: {data.get('plan', 'FREE').upper()}\nExp: {datetime.fromtimestamp(data['expires']).strftime('%Y-%m-%d')}\n━━━━━━━━━━━━━━━━━━━━\n"
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
    if uid not in ud: ud[uid] = {"name": "User", "credits": 150, "plan": "FREE", "expires": 0}
    if code in codes and not codes[code]['used']:
        codes[code]['used'] = True; ud[uid]["credits"] += codes[code]['value']
        await update.message.reply_text(f"✅ Redeemed! Added {codes[code]['value']} credits.\nNew Balance: {ud[uid]['credits']}", parse_mode="HTML")
    elif code in keys and not keys[code]['used']:
        keys[code]['used'] = True; p, d = keys[code]['plan'], keys[code]['days']
        ud[uid]["plan"] = p; ud[uid]["expires"] = time.time() + (d * 86400)
        await send_activation_msg(int(uid), p, d, context)
        await update.message.reply_text(f"✅ Activated {p.upper()} for {d} days.", parse_mode="HTML")
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

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 ULTRA FAST CALLBACKS (NO DELAY) 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    d = q.data
    
    try:
        await q.answer()
    except: pass

    if d == "verify_join":
        try:
            await q.edit_message_text(text=ui_profile(q.from_user, context), parse_mode="HTML", reply_markup=kb_main(), disable_web_page_preview=True)
        except:
            try:
                await context.bot.send_message(chat_id=q.message.chat_id, text=ui_profile(q.from_user, context), parse_mode="HTML", reply_markup=kb_main(), disable_web_page_preview=True)
            except:
                pass
        asyncio.ensure_future(_check_and_kick_if_not_joined(q.from_user.id, context, q.message.chat_id))
        return

    async def edit(t, kb):
        try: await q.edit_message_text(text=t, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
        except: pass

    if d == "bmain": await edit(ui_profile(q.from_user, context), kb_main())
    elif d == "mprice": await edit("Aᴄᴄᴇꜱꜱ ➺ Cᴏʀᴇ 🎀\nSᴘᴀɴ ➺ [7 Dᴀʏꜱ]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ\nPʀɪᴄᴇ ➺ 10$\n━━━━━━━━━━━━━━━━\nAᴄᴄᴇꜱꜱ ➺ Eʟɪᴛᴇ ⭐️\nSᴘᴀɴ ➺ [15 Dᴀʏꜱ]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ\nPʀɪᴄᴇ ➺ 15$\n━━━━━━━━━━━━━━━━\nAᴄᴄᴇꜱꜱ ➺ Rᴏᴏᴛ 👑\nSᴘᴀɴ ➺ [30 Dᴀʏꜱ]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ\nPʀɪᴄᴇ ➺ 30$", kb_price())
    elif d in ("pay10", "pay20", "pay30"): 
        amt = d.replace("pay", "$")
        await edit(f"PAYMENT - {amt}\n━━━━━━━━━━━━━━━━━━━━\n\nBase Amount: {amt}\nTaxes: Included\nTotal: {amt}\n\n━━━━━━━━━━━━━━━━━━━━\n⏳ Soon the payment\naddress will be added\nwith taxes included.\n━━━━━━━━━━━━━━━━━━━━\n\nContact <a href='{DEV_LINK}'>Batman</a> for manual payment.", kb_back("mprice"))
    elif d == "mgates": await edit("SELECT GATE", InlineKeyboardMarkup([[InlineKeyboardButton("AUTH", callback_data="mauth"), InlineKeyboardButton("CHARGE", callback_data="mcharge")],[InlineKeyboardButton("◀ BACK", callback_data="bmain")]]))
    elif d == "mauth": await edit("AUTH GATES", InlineKeyboardMarkup([[InlineKeyboardButton("Stripe", callback_data="iau"), InlineKeyboardButton("Braintree", callback_data="ib3")],[InlineKeyboardButton("◀ BACK", callback_data="mgates")]]))
    elif d == "iau": await edit("━━━━━━━━━━━━━━━━━━━━\nGATE: Stripe Auth\nCMD: /au\nSITES: 16\nHEALTH: 100%\n━━━━━━━━━━━━━━━━━━━━", kb_back("mauth"))
    elif d == "ib3": await edit("━━━━━━━━━━━━━━━━━━━━\nGATE: Braintree Auth\nCMD: /b3 cc|mm|yy|cvv\nSITES: 2\nHEALTH: 100%\n━━━━━━━━━━━━━━━━━━━━", kb_back("mauth"))
    elif d == "mcharge": await edit("CHARGE GATES", InlineKeyboardMarkup([[InlineKeyboardButton("Stripe", callback_data="ichk"), InlineKeyboardButton("PayPal", callback_data="ipp")],[InlineKeyboardButton("Shopify", callback_data="ish"), InlineKeyboardButton("PayU", callback_data="ipyu")],[InlineKeyboardButton("◀ BACK", callback_data="mgates")]]))
    elif d == "ichk": await edit("━━━━━━━━━━━━━━━━━━━━\nGATE: Stripe\nPRICE: $0.50\nCMD: /chk cc|mm|yy|cvv\nSITES: 4\nHEALTH: 100%\n━━━━━━━━━━━━━━━━━━━━", kb_back("mcharge"))
    elif d == "ipp": await edit("━━━━━━━━━━━━━━━━━━━━\nGATE: PayPal\nPRICE: $0.10\nCMD: /pp cc|mm|yy|cvv\nSITES: 7\nHEALTH: 100%\n━━━━━━━━━━━━━━━━━━━━", kb_back("mcharge"))
    elif d == "ish": await edit("━━━━━━━━━━━━━━━━━━━━\nGATE: Shopify\nPRICE: $1.00\nCMD: /sh cc|mm|yy|cvv\nSITES: 10\nHEALTH: 100%\n━━━━━━━━━━━━━━━━━━━━", kb_back("mcharge"))
    elif d == "ipyu": await edit("━━━━━━━━━━━━━━━━━━━━\nGATE: PayU\nPRICE: $0.30\nCMD: /pyu cc|mm|yy|cvv\nSITES: 1\nHEALTH: 100%\n━━━━━━━━━━━━━━━━━━━━", kb_back("mcharge"))

async def _check_and_kick_if_not_joined(user_id, chat_id, context: ContextTypes.DEFAULT_TYPE):
    try:
        joined = await is_joined(user_id, context)
        if not joined:
            try:
                await context.bot.send_message(chat_id=chat_id, text="❌ You didn't join both channels! Access Denied.", parse_mode="HTML")
            except: pass
    except Exception:
        pass

async def on_start(app):
    print("🦇 Batman Bot Initializing...")
    await app.bot.delete_webhook(drop_pending_updates=True)

async def cmd_killbot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    await update.message.reply_text("🛑 Killing bot...", parse_mode="HTML")
    os.kill(os.getpid(), signal.SIGTERM)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    if isinstance(context.error, Conflict):
        logging.warning("⚠️ Conflict caught! Ignoring ghost instance...")
        await asyncio.sleep(15) 
        return
    logging.error(f"Exception: {context.error}")

def main():
    try: urllib.request.urlopen(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=5).read()
    except: pass

    app = Application.builder().token(BOT_TOKEN).post_init(on_start).build()
    app.add_error_handler(error_handler)
    
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("buy", cmd_plan))
    app.add_handler(CommandHandler("plan", cmd_plan))
    app.add_handler(CommandHandler("bin", cmd_bin))
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
    app.add_handler(CommandHandler("rm", cmd_rm))
    app.add_handler(CommandHandler("killbot", cmd_killbot))
    
    for cmd, func in [("onchk", cmd_onchk), ("offchk", cmd_offchk), ("onpp", cmd_onpp), ("offpp", cmd_offpp), ("onsh", cmd_onsh), ("offsh", cmd_offsh), ("onpyu", cmd_onpyu), ("offpyu", cmd_offpyu)]:
        app.add_handler(CommandHandler(cmd, func))
    
    # Gate module handlers — wrapped to block A_ToolsX leak
    for get_handler in [get_chk_handler, get_pp_handler, get_sh_handler, get_pyu_handler, get_b3_handler]:
        if get_handler:
            handler = get_handler()
            app.add_handler(handler)
    
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, anti_ad_filter))
    # Also block A_ToolsX in photo captions
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, anti_ad_filter))
    
    print("🦇 Online! All Commands & Buttons Hyper-Fast.")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
