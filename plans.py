import logging
import asyncio
import re
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from datetime import datetime

from config import BOT_TOKEN, OWNER_ID, VERSION, DEV_LINK, CHANNEL_USERNAME, GROUP_USERNAME, CHANNEL_LINK, GROUP_LINK
from chk import get_chk_handler
from pp import get_pp_handler
from sh import get_sh_handler
from pyu import get_pyu_handler
from plans import get_plans_handler, get_user_ui_text

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

BOT_PHOTO = "https://z-cdn-media.chatglm.cn/files/e82a6a24-028b-47b0-b909-003812e3ad83.jpg?auth_key=1882226135-b1b80190e4204674b0398d13564d82fe-0-874f5e21b888b225a795c7f0f75b970a"
SUPPORT_LINK = "https://t.me/cardchkSupport"

async def anti_ad_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    text = update.message.text.lower()
    if update.effective_user.id == OWNER_ID: return
    banned_words = ["t.me", "http://", "https://", "www.", "join our channel", "join channel", "subscribe", "telegram.me"]
    for word in banned_words:
        if word in text:
            try: await update.message.delete()
            except Exception: pass
            return

async def is_joined(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    async def check(chat_id):
        try:
            m = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            return m.status not in ['left', 'kicked']
        except Exception: return False
    results = await asyncio.gather(check(CHANNEL_USERNAME), check(GROUP_USERNAME))
    return all(results)

def ui_profile(user):
    d = datetime.now().strftime("%Y-%m-%d")
    u = user.username or "None"
    plan_credits_txt = get_user_ui_text(user.id)
    return f"Uꜱᴇʀ ➺ {u}\nUꜱᴇʀ ID ➺ <code>{user.id}</code>\n{plan_credits_txt}\nJᴏɪɴᴇᴅ ➺ {d}\nDᴇᴠ ➺ <a href='{DEV_LINK}'>Batman</a>"

def kb_main():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("CHECKER", callback_data="mgates"), InlineKeyboardButton("BUY NOW", callback_data="mprice")],
        [InlineKeyboardButton("UPDATES", url=CHANNEL_LINK), InlineKeyboardButton("GROUP", url=GROUP_LINK)],
        [InlineKeyboardButton("SUPPORT", url=SUPPORT_LINK)]
    ])

def kb_back(cb): return InlineKeyboardMarkup([[InlineKeyboardButton("◀ BACK", callback_data=cb)]])

def kb_force():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("JOIN GROUP", url="https://t.me/batcardchkGroup")],
        [InlineKeyboardButton("JOIN CHANNEL", url="https://t.me/Batcardchk")],
        [InlineKeyboardButton("VERIFY", callback_data="verify_join")]
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
    except Exception: return None

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if 'user_data' not in context.bot_data: context.bot_data['user_data'] = {}
    if str(user.id) not in context.bot_data['user_data']:
        context.bot_data['user_data'][str(user.id)] = {"name": user.first_name, "joined": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    if await is_joined(user.id, context):
        await update.message.reply_text(text=ui_profile(user), parse_mode="HTML", reply_markup=kb_main(), disable_web_page_preview=True)
    else:
        cap = "BATMAN CARD CHECKER\n\nAccess Required\n━━━━━━━━━━━━━━━━━━━━\nJoin both channels to\nunlock the bot.\n━━━━━━━━━━━━━━━━━━━━"
        try: await update.message.reply_photo(photo=BOT_PHOTO, caption=cap, parse_mode="HTML", reply_markup=kb_force())
        except Exception: await update.message.reply_text(text=cap, parse_mode="HTML", reply_markup=kb_force())

async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = "Aᴄᴄᴇꜱꜱ ➺ Cᴏʀᴇ 🎀\nSᴘᴀɴ ➺ [7 Dᴀʏꜱ]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛᴇᴅ\nPʀɪᴄᴇ ➺ 10$\n━━━━━━━━━━━━━━━━\nAᴄᴄᴇꜱꜱ ➺ Eʟɪᴛᴇ ⭐️\nSᴘᴀɴ ➺ [15 Dᴀʏꜱ]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛᴇᴅ\nPʀɪᴄᴇ ➺ 15$\n━━━━━━━━━━━━━━━━\nAᴄᴄᴇꜱꜱ ➺ Rᴏᴏᴛ 👑\nSᴘᴀɴ ➺ [30 Dᴀʏꜱ]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛᴇᴅ\nPʀɪᴄᴇ ➺ 30$"
    await update.message.reply_text(t, parse_mode="HTML", reply_markup=kb_price())

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 FIXED /info COMMAND (Uses EXACT Bot Database ID) 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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
        await update.message.reply_text("❌ INVALID USAGE\n\n━━━━━━━━━━━━━━━━━━━━\nUsage Methods:\n\n1. Reply to user's message:\n   /info (reply to msg)\n\n2. By Username:\n   /info @username\n\n3. By User ID:\n   /info 123456789\n━━━━━━━━━━━━━━━━━━━━", parse_mode="HTML"); 
        return

    if target_id is None: 
        await update.message.reply_text(f"❌ USER NOT FOUND\n\n━━━━━━━━━━━━━━━━━━━━\nCould not resolve: <code>{target_input}</code>\n━━━━━━━━━━━━━━━━━━━━", parse_mode="HTML"); 
        return

    # Uses bot's internal database strictly to show exact same ID as /start
    all_users = context.bot_data.get('user_data', {})
    user_info = all_users.get(str(target_id))
    
    if user_info:
        join_date = user_info.get('joined', 'N/A')
        stored_name = user_info.get('name', 'N/A')
    else:
        join_date = "Never interacted"
        stored_name = "N/A"
        
    info_text = (
        "USER INFORMATION\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Name: {stored_name}\n"
        f"User ID: <code>{target_id}</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "BOT DATA\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"First Interacted: {join_date}\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    await update.message.reply_text(info_text, parse_mode="HTML")

async def cmd_allcm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    await update.message.reply_text(f"BATMAN BOT - ALL COMMANDS\n━━━━━━━━━━━━━━━━━━━━\nVersion: {VERSION}\n━━━━━━━━━━━━━━━━━━━━\n\nUSER COMMANDS\n━━━━━━━━━━━━━━━━━━━━\n\n▸ /start - Start the bot\n▸ /plan - View pricing plans\n▸ /chk - Stripe check\n▸ /pp - PayPal check\n▸ /sh - Shopify check\n▸ /pyu - PayU check\n▸ /rm - Redeem code\n\nOWNER COMMANDS\n━━━━━━━━━━━━━━━━━━━━\n\n▸ /info - Get user info\n▸ /allcm - Show this\n▸ /gen - Gen credit code\n▸ /key<n> - Gen premium key\n▸ /sub - Grant premium\n▸ /resub - Remove premium\n▸ /allplans - View active plans\n▸ /onchk /offchk - Stripe Gate\n▸ /onpp /offpp - PayPal Gate\n▸ /onsh /offsh - Shopify Gate\n▸ /onpyu /offpyu - PayU Gate\n\n━━━━━━━━━━━━━━━━━━━━", parse_mode="HTML")

async def cmd_onchk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return; context.bot_data['chk_on'] = True; await update.message.reply_text("STRIPE → ON", parse_mode="HTML")
async def cmd_offchk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return; context.bot_data['chk_on'] = False; await update.message.reply_text("STRIPE → OFF", parse_mode="HTML")
async def cmd_onpp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return; context.bot_data['pp_on'] = True; await update.message.reply_text("PAYPAL → ON", parse_mode="HTML")
async def cmd_offpp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return; context.bot_data['pp_on'] = False; await update.message.reply_text("PAYPAL → OFF", parse_mode="HTML")
async def cmd_onsh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return; context.bot_data['sh_on'] = True; await update.message.reply_text("SHOPIFY → ON", parse_mode="HTML")
async def cmd_offsh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return; context.bot_data['sh_on'] = False; await update.message.reply_text("SHOPIFY → OFF", parse_mode="HTML")
async def cmd_onpyu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return; context.bot_data['pyu_on'] = True; await update.message.reply_text("PAYU → ON", parse_mode="HTML")
async def cmd_offpyu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return; context.bot_data['pyu_on'] = False; await update.message.reply_text("PAYU → OFF", parse_mode="HTML")

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); d = q.data
    if d == "verify_join":
        if await is_joined(q.from_user.id, context):
            try:
                if q.message.photo: await q.message.delete(); await context.bot.send_message(chat_id=q.message.chat_id, text=ui_profile(q.from_user), parse_mode="HTML", reply_markup=kb_main(), disable_web_page_preview=True)
                else: await q.edit_message_text(text=ui_profile(q.from_user), parse_mode="HTML", reply_markup=kb_main(), disable_web_page_preview=True)
            except Exception as e: logging.error(f"Verify error: {e}")
        else: await q.answer("❌ Join Group & Channel first!", show_alert=True)
        return
    async def edit(t, kb):
        try: await q.edit_message_text(text=t, parse_mode="HTML
