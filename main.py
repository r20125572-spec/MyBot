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
from typing import Optional
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

from config import (
    BOT_TOKEN, OWNER_ID, VERSION, DEV_LINK, 
    CHANNEL_USERNAME, GROUP_USERNAME, CHANNEL_LINK, GROUP_LINK, 
    BOT_PHOTO
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 FIXED SUPPORT LINK 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SUPPORT_LINK = "https://t.me/cardchkSupport"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 FAST SAFE IMPORTS 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
try: from chk import get_chk_handler
except: get_chk_handler = None

try: from pp import get_pp_handler
except: get_pp_handler = None

try: from sh import get_sh_handler
except: get_sh_handler = None

try: from pyu import get_pyu_handler
except: get_pyu_handler = None

try: from plans import get_plans_handler, get_user_ui_text
except: 
    get_plans_handler = lambda: []
    get_user_ui_text = lambda uid: "Pʟᴀɴ ➺ Fʀᴇᴇ\nCʀᴇᴅɪᴛꜱ ➺ 0"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 ULTRA FAST LINK BLOCKER 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BLOCK_WORDS = ("http://", "https://", "www.", "t.me", ".com", ".net", ".org", ".io", ".me", ".xyz", ".tk", ".ml", ".cf", ".ga", ".ru", ".in", ".pw", "telegram.me", "joinchat", "://")

async def anti_ad_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text or msg.from_user.id == OWNER_ID: return
    text = msg.text.lower()
    if any(w in text for w in BLOCK_WORDS):
        try: await msg.delete()
        except: pass

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 FAST HELPERS 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def is_joined(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    async def check(chat_id):
        try:
            return (await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)).status not in ('left', 'kicked')
        except: return False
    return await check(CHANNEL_USERNAME) and await check(GROUP_USERNAME)

def ui_profile(user):
    u = user.username or "None"
    return (
        f"Uꜱᴇʀ ➺ {u}\n"
        f"Uꜱᴇʀ ID ➺ <code>{user.id}</code>\n"
        f"{get_user_ui_text(user.id)}\n"
        f"Jᴏɪɴᴇᴅ ➺ {datetime.now().strftime('%Y-%m-%d')}\n"
        f"Dᴇᴠ ➺ <a href='{DEV_LINK}'>Batman</a>"
    )

def kb_main():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("CHECKER", callback_data="mgates"), InlineKeyboardButton("BUY NOW", callback_data="mprice")],
        [InlineKeyboardButton("UPDATES", url=CHANNEL_LINK), InlineKeyboardButton("GROUP", url=GROUP_LINK)],
        [InlineKeyboardButton("SUPPORT", url=SUPPORT_LINK)] # FIXED SUPPORT LINK
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
# 🦇 FIXED BIN COMMAND (Built-in so it never fails) 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def fetch_bin(url: str) -> dict:
    try:
        req = urllib.request.Request(url, headers={"Accept-Version": "3", "User-Agent": "Mozilla/5.0"})
        loop = asyncio.get_running_loop()
        def do_req():
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read().decode('utf-8'))
        return await loop.run_in_executor(None, do_req)
    except: return {}

async def cmd_bin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ INVALID USAGE\n━━━━━━━━━━━━━━━━━━━━\n\n📌 Usage: /bin <BIN>\n📌 Example: /bin 453201\n\n━━━━━━━━━━━━━━━━━━━━", parse_mode="HTML")
        return
    
    bin_num = ''.join(filter(str.isdigit, context.args[0]))[:6]
    if len(bin_num) < 6:
        await update.message.reply_text("❌ Invalid BIN! Must be 6 digits.", parse_mode="HTML")
        return
        
    status = await update.message.reply_text(f"🔍 Looking up BIN: <code>{bin_num}</code>...", parse_mode="HTML")
    data = await fetch_bin(f"https://lookup.binlist.net/{bin_num}")
    
    if not data or "scheme" not in data:
        try: await status.edit_text("❌ BIN not found in database.", parse_mode="HTML")
        except: pass
        return

    c_data = data.get("country") or {}
    b_data = data.get("bank") or {}
    brand = (data.get("brand") or "N/A").upper()
    
    brand_emoji = {"VISA": "🔵", "MASTERCARD": "🔴", "AMEX": "🟡", "DISCOVER": "🟠"}.get(brand, "⚪")
    type_emoji = {"CREDIT": "💳", "DEBIT": "🏦", "PREPAID": "💰"}.get((data.get("type") or "").upper(), "💳")
    
    txt = (
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🦇 BIN LOOKUP RESULT\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"BIN ➺ <code>{bin_num}</code>\n"
        f"SCHEME ➺ {(data.get('scheme') or 'N/A').upper()}\n"
        f"TYPE ➺ {type_emoji} {(data.get('type') or 'N/A').upper()}\n"
        f"BRAND ➺ {brand_emoji} {brand}\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🌍 COUNTRY INFO\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"NAME ➺ {c_data.get('emoji', '🌍')} {c_data.get('name', 'N/A')}\n"
        f"CODE ➺ {c_data.get('alpha2', '??')}\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🏦 BANK INFO\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"BANK ➺ {b_data.get('name', 'N/A')}\n"
    )
    if b_data.get("url"): txt += f"URL ➺ {b_data.get('url')}\n"
    txt += "\n━━━━━━━━━━━━━━━━━━━━"
    
    try: await status.edit_text(txt, parse_mode="HTML", disable_web_page_preview=True)
    except: pass

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 USER COMMANDS 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ud = context.bot_data.setdefault('user_data', {})
    if str(user.id) not in ud:
        ud[str(user.id)] = {"name": user.first_name, "joined": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    
    if await is_joined(user.id, context):
        await update.message.reply_text(text=ui_profile(user), parse_mode="HTML", reply_markup=kb_main(), disable_web_page_preview=True)
    else:
        cap = "BATMAN CARD CHECKER\n\nAccess Required\n━━━━━━━━━━━━━━━━━━━━\nJoin both channels to\nunlock the bot.\n━━━━━━━━━━━━━━━━━━━━"
        try: await update.message.reply_photo(photo=BOT_PHOTO, caption=cap, parse_mode="HTML", reply_markup=kb_force())
        except: await update.message.reply_text(text=cap, parse_mode="HTML", reply_markup=kb_force())

async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Aᴄᴄᴇꜱꜱ ➺ Cᴏʀᴇ 🎀\nSᴘᴀɴ ➺ [7 Dᴀʏꜱ]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ\nPʀɪᴄᴇ ➺ 10$\n"
        "━━━━━━━━━━━━━━━━\n"
        "Aᴄᴄᴇꜱꜱ ➺ Eʟɪᴛᴇ ⭐️\nSᴘᴀɴ ➺ [15 Dᴀʏꜱ]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ\nPʀɪᴄᴇ ➺ 15$\n"
        "━━━━━━━━━━━━━━━━\n"
        "Aᴄᴄᴇꜱꜱ ➺ Rᴏᴏᴛ 👑\nSᴘᴀɴ ➺ [30 Dᴀʏꜱ]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ\nPʀɪᴄᴇ ➺ 30$", 
        parse_mode="HTML", reply_markup=kb_price()
    )

async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    target_id = target_input = None
    if update.message.reply_to_message: 
        target_id = update.message.reply_to_message.from_user.id
        target_input = str(target_id)
    elif context.args: 
        target_input = context.args[0]
        target_id = await resolve_user(target_input, context)
    else: 
        await update.message.reply_text("❌ Reply to a user or provide ID/Username.\nUsage: /info @username or /info 12345", parse_mode="HTML"); return

    if not target_id: 
        await update.message.reply_text(f"❌ User not found: <code>{target_input}</code>", parse_mode="HTML"); return

    udata = context.bot_data.get('user_data', {}).get(str(target_id))
    plans = context.bot_data.get('plans', {}).get(str(target_id))
    
    txt = (
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"USER INFO\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Name: {udata.get('name', 'N/A') if udata else 'N/A'}\n"
        f"ID: <code>{target_id}</code>\n"
        f"Joined: {udata.get('joined', 'N/A') if udata else 'N/A'}\n\n"
    )
    if plans:
        exp = datetime.fromtimestamp(plans['expires']).strftime('%Y-%m-%d %H:%M')
        txt += f"Plan: {plans['plan'].upper()}\nExpires: {exp}\n"
    else:
        txt += "Plan: FREE\n"
    txt += "━━━━━━━━━━━━━━━━━━━━━━"
    await update.message.reply_text(txt, parse_mode="HTML")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 ALL OWNER COMMANDS (FIXED) 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_allcm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    await update.message.reply_text(
        f"🦇 BATMAN BOT COMMANDS\n━━━━━━━━━━━━━━━━━━━━\nVersion: {VERSION}\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "👤 USER COMMANDS\n━━━━━━━━━━━━━━━━━━━━\n"
        "▸ /start - Start Bot\n"
        "▸ /plan - View Plans\n"
        "▸ /bin - BIN Lookup\n"
        "▸ /chk - Stripe Check\n"
        "▸ /pp - PayPal Check\n"
        "▸ /sh - Shopify Check\n"
        "▸ /pyu - PayU Check\n"
        "▸ /rm - Redeem Code\n\n"
        "👑 OWNER COMMANDS\n━━━━━━━━━━━━━━━━━━━━\n"
        "▸ /info - User Info\n"
        "▸ /allcm - This Menu\n"
        "▸ /gen <amt> - Gen Credit Code\n"
        "▸ /key10 - Gen Core Key (7 Days)\n"
        "▸ /key20 - Gen Elite Key (15 Days)\n"
        "▸ /key30 - Gen Root Key (30 Days)\n"
        "▸ /oneday <user_id> - Give 1 Day Access\n"
        "▸ /sub <user_id> <days> - Grant Premium\n"
        "▸ /resub <user_id> - Remove Premium\n"
        "▸ /allplans - View Active Plans\n"
        "▸ /delcode <code> - Delete Code/Key\n"
        "▸ /onchk /offchk - Stripe Gate\n"
        "▸ /onpp /offpp - PayPal Gate\n"
        "▸ /onsh /offsh - Shopify Gate\n"
        "▸ /onpyu /offpyu - PayU Gate\n"
        "━━━━━━━━━━━━━━━━━━━━", parse_mode="HTML"
    )

async def cmd_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args: 
        await update.message.reply_text("❌ Usage: /gen <credits>\nExample: /gen 10", parse_mode="HTML"); return
    try:
        amt = int(context.args[0])
        code = gen_code()
        context.bot_data.setdefault('codes', {})[code] = {"type": "credit", "value": amt, "used": False}
        await update.message.reply_text(f"✅ CREDIT CODE GENERATED\n━━━━━━━━━━━━━━━━━━━━\n\nCode: <code>{code}</code>\nCredits: {amt}\n━━━━━━━━━━━━━━━━━━━━", parse_mode="HTML")
    except: await update.message.reply_text("❌ Invalid amount.", parse_mode="HTML")

async def cmd_gen_key(update: Update, context: ContextTypes.DEFAULT_TYPE, plan: str, days: int):
    if update.effective_user.id != OWNER_ID: return
    code = "KEY-" + gen_code(12)
    context.bot_data.setdefault('keys', {})[code] = {"plan": plan, "days": days, "used": False}
    await update.message.reply_text(
        f"✅ PREMIUM KEY GENERATED\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Key: <code>{code}</code>\nPlan: {plan.upper()}\nDays: {days}\n"
        f"━━━━━━━━━━━━━━━━━━━━", parse_mode="HTML"
    )

async def cmd_key10(update: Update, context: ContextTypes.DEFAULT_TYPE): await cmd_gen_key(update, context, "core", 7)
async def cmd_key20(update: Update, context: ContextTypes.DEFAULT_TYPE): await cmd_gen_key(update, context, "elite", 15)
async def cmd_key30(update: Update, context: ContextTypes.DEFAULT_TYPE): await cmd_gen_key(update, context, "root", 30)

async def cmd_oneday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args: 
        await update.message.reply_text("❌ Usage: /oneday <user_id>\nExample: /oneday 123456789", parse_mode="HTML"); return
    uid = await resolve_user(context.args[0], context)
    if not uid: await update.message.reply_text("❌ User not found.", parse_mode="HTML"); return
    
    plans = context.bot_data.setdefault('plans', {})
    plans[str(uid)] = {"plan": "core", "expires": time.time() + 86400}
    await update.message.reply_text(f"✅ Granted 1 Day Access to <code>{uid}</code>", parse_mode="HTML")

async def cmd_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if len(context.args) < 2: 
        await update.message.reply_text("❌ Usage: /sub <user_id> <days>\nExample: /sub 123456789 30", parse_mode="HTML"); return
    uid = await resolve_user(context.args[0], context)
    if not uid: await update.message.reply_text("❌ User not found.", parse_mode="HTML"); return
    try:
        days = int(context.args[1])
        plan = "root" if days >= 30 else "elite" if days >= 15 else "core"
        plans = context.bot_data.setdefault('plans', {})
        plans[str(uid)] = {"plan": plan, "expires": time.time() + (days * 86400)}
        await update.message.reply_text(f"✅ Granted {days} Days ({plan.upper()}) to <code>{uid}</code>", parse_mode="HTML")
    except: await update.message.reply_text("❌ Invalid days.", parse_mode="HTML")

async def cmd_resub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args: 
        await update.message.reply_text("❌ Usage: /resub <user_id>", parse_mode="HTML"); return
    uid = await resolve_user(context.args[0], context)
    if not uid: await update.message.reply_text("❌ User not found.", parse_mode="HTML"); return
    
    plans = context.bot_data.get('plans', {})
    if str(uid) in plans:
        del plans[str(uid)]
        await update.message.reply_text(f"✅ Removed premium from <code>{uid}</code>", parse_mode="HTML")
    else:
        await update.message.reply_text("❌ User doesn't have premium.", parse_mode="HTML")

async def cmd_allplans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    plans = context.bot_data.get('plans', {})
    if not plans: 
        await update.message.reply_text("❌ No active plans found.", parse_mode="HTML"); return
    
    txt = "🦇 ACTIVE PLANS\n━━━━━━━━━━━━━━━━━━━━\n\n"
    for uid, data in plans.items():
        if data['expires'] > time.time():
            exp = datetime.fromtimestamp(data['expires']).strftime('%Y-%m-%d')
            txt += f"ID: <code>{uid}</code>\nPlan: {data['plan'].upper()}\nExpires: {exp}\n━━━━━━━━━━━━━━━━━━━━\n"
    await update.message.reply_text(txt, parse_mode="HTML")

async def cmd_delcode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args: 
        await update.message.reply_text("❌ Usage: /delcode <code>", parse_mode="HTML"); return
    code = context.args[0]
    codes = context.bot_data.get('codes', {})
    keys = context.bot_data.get('keys', {})
    
    if code in codes: del codes[code]; await update.message.reply_text(f"✅ Credit code deleted.", parse_mode="HTML")
    elif code in keys: del keys[code]; await update.message.reply_text(f"✅ Premium key deleted.", parse_mode="HTML")
    else: await update.message.reply_text("❌ Code not found.", parse_mode="HTML")

async def cmd_rm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: 
        await update.message.reply_text("❌ Usage: /rm <code>", parse_mode="HTML"); return
    code = context.args[0].upper()
    codes = context.bot_data.get('codes', {})
    keys = context.bot_data.get('keys', {})
    uid = str(update.effective_user.id)
    
    if code in codes and not codes[code]['used']:
        codes[code]['used'] = True
        await update.message.reply_text(f"✅ Redeemed! Added {codes[code]['value']} credits.", parse_mode="HTML")
    elif code in keys and not keys[code]['used']:
        keys[code]['used'] = True
        plan = keys[code]['plan']
        days = keys[code]['days']
        context.bot_data.setdefault('plans', {})[uid] = {"plan": plan, "expires": time.time() + (days * 86400)}
        await update.message.reply_text(f"✅ Redeemed! Activated {plan.upper()} for {days} days.", parse_mode="HTML")
    else:
        await update.message.reply_text("❌ Invalid or already used code.", parse_mode="HTML")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 GATE TOGGLES 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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
# 🦇 CALLBACKS 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); d = q.data
    if d == "verify_join":
        if await is_joined(q.from_user.id, context):
            try:
                if q.message.photo: 
                    await q.message.delete()
                    await context.bot.send_message(chat_id=q.message.chat_id, text=ui_profile(q.from_user), parse_mode="HTML", reply_markup=kb_main(), disable_web_page_preview=True)
                else: 
                    await q.edit_message_text(text=ui_profile(q.from_user), parse_mode="HTML", reply_markup=kb_main(), disable_web_page_preview=True)
            except: pass
        else: await q.answer("❌ Join Group & Channel first!", show_alert=True)
        return
        
    async def edit(t, kb):
        try: await q.edit_message_text(text=t, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
        except: pass
        
    if d == "bmain": await edit(ui_profile(q.from_user), kb_main())
    elif d == "mprice": await edit("Aᴄᴄᴇꜱꜱ ➺ Cᴏʀᴇ 🎀\nSᴘᴀɴ ➺ [7 Dᴀʏꜱ]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ\nPʀɪᴄᴇ ➺ 10$\n━━━━━━━━━━━━━━━━\nAᴄᴄᴇꜱꜱ ➺ Eʟɪᴛᴇ ⭐️\nSᴘᴀɴ ➺ [15 Dᴀʏꜱ]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ\nPʀɪᴄᴇ ➺ 15$\n━━━━━━━━━━━━━━━━\nAᴄᴄᴇꜱꜱ ➺ Rᴏᴏᴛ 👑\nSᴘᴀɴ ➺ [30 Dᴀʏꜱ]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ\nPʀɪᴄᴇ ➺ 30$", kb_price())
    elif d in ("pay10", "pay20", "pay30"): 
        amt = d.replace("pay", "$")
        await edit(f"PAYMENT - {amt}\n━━━━━━━━━━━━━━━━━━━━\n\nBase Amount: {amt}\nTaxes: Included\nTotal: {amt}\n\n━━━━━━━━━━━━━━━━━━━━\n⏳ Soon the payment\naddress will be added.\n━━━━━━━━━━━━━━━━━━━━\n\nContact <a href='{DEV_LINK}'>Batman</a> for manual payment.", kb_back("mprice"))
    elif d == "mgates": await edit("SELECT GATE", InlineKeyboardMarkup([[InlineKeyboardButton("AUTH", callback_data="mauth"), InlineKeyboardButton("CHARGE", callback_data="mcharge")],[InlineKeyboardButton("◀ BACK", callback_data="bmain")]]))
    elif d == "mauth": await edit("AUTH GATES", InlineKeyboardMarkup([[InlineKeyboardButton("Stripe", callback_data="iau"), InlineKeyboardButton("Braintree", callback_data="ib3")],[InlineKeyboardButton("◀ BACK", callback_data="mgates")]]))
    elif d == "iau": await edit("━━━━━━━━━━━━━━━━━━━━\nGATE: Stripe Auth\nCMD: /au\nSITES: 16\nHEALTH: 100%\n━━━━━━━━━━━━━━━━━━━━", kb_back("mauth"))
    elif d == "ib3": await edit("━━━━━━━━━━━━━━━━━━━━\nGATE: Braintree Auth\nCMD: /b3\nSITES: 2\nHEALTH: 100%\n━━━━━━━━━━━━━━━━━━━━", kb_back("mauth"))
    elif d == "mcharge": await edit("CHARGE GATES", InlineKeyboardMarkup([[InlineKeyboardButton("Stripe", callback_data="ichk"), InlineKeyboardButton("PayPal", callback_data="ipp")],[InlineKeyboardButton("Shopify", callback_data="ish"), InlineKeyboardButton("PayU", callback_data="ipyu")],[InlineKeyboardButton("◀ BACK", callback_data="mgates")]]))
    elif d == "ichk": await edit("━━━━━━━━━━━━━━━━━━━━\nGATE: Stripe\nPRICE: $0.50\nCMD: /chk\nSITES: 4\nHEALTH: 100%\n━━━━━━━━━━━━━━━━━━━━", kb_back("mcharge"))
    elif d == "ipp": await edit("━━━━━━━━━━━━━━━━━━━━\nGATE: PayPal\nPRICE: $0.10\nCMD: /pp\nSITES: 7\nHEALTH: 100%\n━━━━━━━━━━━━━━━━━━━━", kb_back("mcharge"))
    elif d == "ish": await edit("━━━━━━━━━━━━━━━━━━━━\nGATE: Shopify\nPRICE: $1.00\nCMD: /sh\nSITES: 10\nHEALTH: 100%\n━━━━━━━━━━━━━━━━━━━━", kb_back("mcharge"))
    elif d == "ipyu": await edit("━━━━━━━━━━━━━━━━━━━━\nGATE: PayU\nPRICE: $0.30\nCMD: /pyu\nSITES: 1\nHEALTH: 100%\n━━━━━━━━━━━━━━━━━━━━", kb_back("mcharge"))

async def on_start(app):
    print("🦇 Batman Bot Starting...")
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
    
    # 1. ALL Built-in Commands (Fastest Priority)
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("plan", cmd_plan))
    app.add_handler(CommandHandler("bin", cmd_bin)) # FIXED: Built-in BIN
    app.add_handler(CommandHandler("info", cmd_info))
    app.add_handler(CommandHandler("allcm", cmd_allcm))
    app.add_handler(CommandHandler("gen", cmd_gen))
    app.add_handler(CommandHandler("key10", cmd_key10))
    app.add_handler(CommandHandler("key20", cmd_key20))
    app.add_handler(CommandHandler("key30", cmd_key30))
    app.add_handler(CommandHandler("oneday", cmd_oneday))
    app.add_handler(CommandHandler("sub", cmd_sub))
    app.add_handler(CommandHandler("resub", cmd_resub))
    app.add_handler(CommandHandler("allplans", cmd_allplans))
    app.add_handler(CommandHandler("delcode", cmd_delcode))
    app.add_handler(CommandHandler("rm", cmd_rm))
    app.add_handler(CommandHandler("killbot", cmd_killbot))
    
    for cmd, func in [("onchk", cmd_onchk), ("offchk", cmd_offchk), ("onpp", cmd_onpp), ("offpp", cmd_offpp), ("onsh", cmd_onsh), ("offsh", cmd_offsh), ("onpyu", cmd_onpyu), ("offpyu", cmd_offpyu)]:
        app.add_handler(CommandHandler(cmd, func))
    
    # 2. External Gate Handlers
    if get_chk_handler: app.add_handler(get_chk_handler())
    if get_pp_handler: app.add_handler(get_pp_handler())
    if get_sh_handler: app.add_handler(get_sh_handler())
    if get_pyu_handler: app.add_handler(get_pyu_handler())
    
    # 3. Safe Plans Handler
    try:
        for h in get_plans_handler(): app.add_handler(h)
    except: pass
    
    # 4. Callbacks & Filter Last
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, anti_ad_filter))
    
    print("🦇 Online! All Commands Active.")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
