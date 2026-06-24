import os
import signal
import logging
import asyncio
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from datetime import datetime

from config import (
    BOT_TOKEN, OWNER_ID, VERSION, DEV_LINK, 
    CHANNEL_USERNAME, GROUP_USERNAME, CHANNEL_LINK, GROUP_LINK, 
    SUPPORT_LINK, BOT_PHOTO
)
from chk import get_chk_handler
from pp import get_pp_handler
from sh import get_sh_handler
from pyu import get_pyu_handler
from plans import get_plans_handler, get_user_ui_text
from bincheck import get_bin_handler

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 STRICT LINK BLOCKER 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def anti_ad_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    if update.effective_user.id == OWNER_ID: return
    
    text = update.message.text.lower()
    link_patterns = [
        "http://", "https://", "www.", "t.me", ".com", ".net", ".org", 
        ".io", ".me", ".xyz", ".tk", ".ml", ".cf", ".ga", ".ru", ".in", ".pw",
        "telegram.me", "joinchat", "://"
    ]
    
    for pattern in link_patterns:
        if pattern in text:
            try: 
                await update.message.delete()
            except Exception: 
                pass
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
    return (
        f"Uꜱᴇʀ ➺ {u}\n"
        f"Uꜱᴇʀ ID ➺ <code>{user.id}</code>\n"
        f"{plan_credits_txt}\n"
        f"Jᴏɪɴᴇᴅ ➺ {d}\n"
        f"Dᴇᴠ ➺ <a href='{DEV_LINK}'>Batman</a>"
    )

def kb_main():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("CHECKER", callback_data="mgates"), InlineKeyboardButton("BUY NOW", callback_data="mprice")],
        [InlineKeyboardButton("UPDATES", url=CHANNEL_LINK), InlineKeyboardButton("GROUP", url=GROUP_LINK)],
        [InlineKeyboardButton("SUPPORT", url=SUPPORT_LINK)]
    ])

def kb_back(cb): 
    return InlineKeyboardMarkup([[InlineKeyboardButton("◀ BACK", callback_data=cb)]])

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
        try: 
            await update.message.reply_photo(photo=BOT_PHOTO, caption=cap, parse_mode="HTML", reply_markup=kb_force())
        except Exception: 
            await update.message.reply_text(text=cap, parse_mode="HTML", reply_markup=kb_force())

async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = (
        "Aᴄᴄᴇꜱꜱ ➺ Cᴏʀᴇ 🎀\nSᴘᴀɴ ➺ [7 Dᴀʏꜱ]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ\nPʀɪᴄᴇ ➺ 10$\n"
        "━━━━━━━━━━━━━━━━\n"
        "Aᴄᴄᴇꜱꜱ ➺ Eʟɪᴛᴇ ⭐️\nSᴘᴀɴ ➺ [15 Dᴀʏꜱ]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ\nPʀɪᴄᴇ ➺ 15$\n"
        "━━━━━━━━━━━━━━━━\n"
        "Aᴄᴄᴇꜱꜱ ➺ Rᴏᴏᴛ 👑\nSᴘᴀɴ ➺ [30 Dᴀʏꜱ]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ\nPʀɪᴄᴇ ➺ 30$"
    )
    await update.message.reply_text(t, parse_mode="HTML", reply_markup=kb_price())

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
        await update.message.reply_text(
            "❌ INVALID USAGE\n\n━━━━━━━━━━━━━━━━━━━━\n"
            "Usage Methods:\n\n"
            "1. Reply to user's message:\n   /info (reply to msg)\n\n"
            "2. By Username:\n   /info @username\n"
            "3. By User ID:\n   /info 123456789\n"
            "━━━━━━━━━━━━━━━━━━━━", 
            parse_mode="HTML"
        )
        return

    if target_id is None: 
        await update.message.reply_text(
            f"❌ USER NOT FOUND\n━━━━━━━━━━━━━━━━━━━━\n"
            f"Could not resolve: <code>{target_input}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━", 
            parse_mode="HTML"
        )
        return

    all_users = context.bot_data.get('user_data', {})
    user_info = all_users.get(str(target_id))
    join_date = user_info.get('joined', 'Never interacted') if user_info else "Never interacted"
    stored_name = user_info.get('name', 'N/A') if user_info else "N/A"
        
    info_text = (
        "USER INFORMATION\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Name: {stored_name}\n"
        f"User ID: <code>{target_id}</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "BOT DATA\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"First Interacted: {join_date}\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )
    await update.message.reply_text(info_text, parse_mode="HTML")

async def cmd_allcm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    await update.message.reply_text(
        f"BATMAN BOT - ALL COMMANDS\n━━━━━━━━━━━━━━━━━━━━\nVersion: {VERSION}\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "USER COMMANDS\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "▸ /start - Start the bot\n▸ /plan - View pricing plans\n▸ /bin - Check BIN details\n"
        "▸ /chk - Stripe check\n▸ /pp - PayPal check\n▸ /sh - Shopify check\n"
        "▸ /pyu - PayU check\n▸ /rm - Redeem code\n\n\n"
        "OWNER COMMANDS\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "▸ /info - Get user info\n▸ /allcm - Show this\n▸ /gen - Gen credit code\n"
        "▸ /key<n> - Gen premium key\n▸ /sub - Grant premium\n▸ /resub - Remove premium\n"
        "▸ /allplans - View active plans\n▸ /onchk /offchk - Stripe Gate\n"
        "▸ /onpp /offpp - PayPal Gate\n▸ /onsh /offsh - Shopify Gate\n"
        "▸ /onpyu /offpyu - PayU Gate\n━━━━━━━━━━━━━━━━━━━━", 
        parse_mode="HTML"
    )

async def cmd_onchk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data['chk_on'] = True
    await update.message.reply_text("STRIPE → ON", parse_mode="HTML")

async def cmd_offchk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data['chk_on'] = False
    await update.message.reply_text("STRIPE → OFF", parse_mode="HTML")

async def cmd_onpp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data['pp_on'] = True
    await update.message.reply_text("PAYPAL → ON", parse_mode="HTML")

async def cmd_offpp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data['pp_on'] = False
    await update.message.reply_text("PAYPAL → OFF", parse_mode="HTML")

async def cmd_onsh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data['sh_on'] = True
    await update.message.reply_text("SHOPIFY → ON", parse_mode="HTML")

async def cmd_offsh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data['sh_on'] = False
    await update.message.reply_text("SHOPIFY → OFF", parse_mode="HTML")

async def cmd_onpyu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data['pyu_on'] = True
    await update.message.reply_text("PAYU → ON", parse_mode="HTML")

async def cmd_offpyu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data['pyu_on'] = False
    await update.message.reply_text("PAYU → OFF", parse_mode="HTML")

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data
    
    if d == "verify_join":
        if await is_joined(q.from_user.id, context):
            try:
                if q.message.photo: 
                    await q.message.delete()
                    await context.bot.send_message(
                        chat_id=q.message.chat_id, 
                        text=ui_profile(q.from_user), 
                        parse_mode="HTML", 
                        reply_markup=kb_main(), 
                        disable_web_page_preview=True
                    )
                else: 
                    await q.edit_message_text(
                        text=ui_profile(q.from_user), 
                        parse_mode="HTML", 
                        reply_markup=kb_main(), 
                        disable_web_page_preview=True
                    )
            except Exception as e: 
                logging.error(f"Verify error: {e}")
        else: 
            await q.answer("❌ Join Group & Channel first!", show_alert=True)
        return
        
    async def edit(t, kb):
        try: 
            await q.edit_message_text(text=t, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
        except Exception: 
            pass
            
    if d == "bmain": 
        await edit(ui_profile(q.from_user), kb_main())
        
    elif d == "mprice": 
        await edit(
            "Aᴄᴄᴇꜱꜱ ➺ Cᴏʀᴇ 🎀\nSᴘᴀɴ ➺ [7 Dᴀʏꜱ]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ\nPʀɪᴄᴇ ➺ 10$\n"
            "━━━━━━━━━━━━━━━━\n"
            "Aᴄᴄᴇꜱꜱ ➺ Eʟɪᴛᴇ ⭐️\nSᴘᴀɴ ➺ [15 Dᴀʏꜱ]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ\nPʀɪᴄᴇ ➺ 15$\n"
            "━━━━━━━━━━━━━━━━\n"
            "Aᴄᴄᴇꜱꜱ ➺ Rᴏᴏᴛ 👑\nSᴘᴀɴ ➺ [30 Dᴀʏꜱ]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛɪᴛᴇᴅ\nPʀɪᴄᴇ ➺ 30$", 
            kb_price()
        )
        
    elif d == "pay10": 
        await edit(
            f"PAYMENT - 10$\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Base Amount: 10$\nTaxes: Included\nTotal: 10$\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n⏳ Soon the payment\naddress will be added\nwith taxes included.\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\nContact <a href='{DEV_LINK}'>Batman</a> for manual payment.", 
            kb_back("mprice")
        )
        
    elif d == "pay20": 
        await edit(
            f"PAYMENT - 20$\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Base Amount: 20$\nTaxes: Included\nTotal: 20$\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n⏳ Soon the payment\naddress will be added\nwith taxes included.\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\nContact <a href='{DEV_LINK}'>Batman</a> for manual payment.", 
            kb_back("mprice")
        )
        
    elif d == "pay30": 
        await edit(
            f"PAYMENT - 30$\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Base Amount: 30$\nTaxes: Included\nTotal: 30$\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n⏳ Soon the payment\naddress will be added\nwith taxes included.\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\nContact <a href='{DEV_LINK}'>Batman</a> for manual payment.", 
            kb_back("mprice")
        )
        
    elif d == "mgates": 
        await edit(
            "SELECT GATE", 
            InlineKeyboardMarkup([
                [InlineKeyboardButton("AUTH", callback_data="mauth"), InlineKeyboardButton("CHARGE", callback_data="mcharge")],
                [InlineKeyboardButton("◀ BACK", callback_data="bmain")]
            ])
        )
        
    elif d == "mauth": 
        await edit(
            "AUTH GATES", 
            InlineKeyboardMarkup([
                [InlineKeyboardButton("Stripe", callback_data="iau"), InlineKeyboardButton("Braintree", callback_data="ib3")],
                [InlineKeyboardButton("◀ BACK", callback_data="mgates")]
            ])
        )
        
    elif d == "iau": 
        await edit(
            "━━━━━━━━━━━━━━━━━━━━\nGATE: Stripe Auth\nCMD: /au\nSITES: 16\nHEALTH: 100%\n━━━━━━━━━━━━━━━━━━━━", 
            kb_back("mauth")
        )
        
    elif d == "ib3": 
        await edit(
            "━━━━━━━━━━━━━━━━━━━━\nGATE: Braintree Auth\nCMD: /b3\nSITES: 2\nHEALTH: 100%\n━━━━━━━━━━━━━━━━━━━━", 
            kb_back("mauth")
        )
        
    elif d == "mcharge": 
        await edit(
            "CHARGE GATES", 
            InlineKeyboardMarkup([
                [InlineKeyboardButton("Stripe", callback_data="ichk"), InlineKeyboardButton("PayPal", callback_data="ipp")],
                [InlineKeyboardButton("Shopify", callback_data="ish"), InlineKeyboardButton("PayU", callback_data="ipyu")],
                [InlineKeyboardButton("◀ BACK", callback_data="mgates")]
            ])
        )
        
    elif d == "ichk": 
        await edit(
            "━━━━━━━━━━━━━━━━━━━━\nGATE: Stripe\nPRICE: $0.50\nCMD: /chk\nSITES: 4\nHEALTH: 100%\n━━━━━━━━━━━━━━━━━━━━", 
            kb_back("mcharge")
        )
        
    elif d == "ipp": 
        await edit(
            "━━━━━━━━━━━━━━━━━━━━\nGATE: PayPal\nPRICE: $0.10\nCMD: /pp\nSITES: 7\nHEALTH: 100%\n━━━━━━━━━━━━━━━━━━━━", 
            kb_back("mcharge")
        )
        
    # FIX: Safely split text to prevent "unterminated string literal" error
    elif d == "ish": 
        await edit(
            "━━━━━━━━━━━━━━━━━━━━\n"
            "GATE: Shopify\n"
            "PRICE: $1.00\n"
            "CMD: /sh\n"
            "SITES: 10\n"
            "HEALTH: 100%\n"
            "━━━━━━━━━━━━━━━━━━━━", 
            kb_back("mcharge")
        )
        
    elif d == "ipyu": 
        await edit(
            "━━━━━━━━━━━━━━━━━━━━\n"
            "GATE: PayU\n"
            "PRICE: $0.30\n"
            "CMD: /pyu\n"
            "SITES: 1\n"
            "HEALTH: 100%\n"
            "━━━━━━━━━━━━━━━━━━━━", 
            kb_back("mcharge")
        )

async def on_start(app):
    print("Batman Starting...")
    await app.bot.delete_webhook(drop_pending_updates=True)

async def cmd_killbot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    await update.message.reply_text("🛑 Killing bot process...", parse_mode="HTML")
    os.kill(os.getpid(), signal.SIGTERM)

def main():
    try:
        import psutil
        for proc in psutil.process_iter(['python', 'main.py']):
            if 'main.py' in ' '.join(proc.cmdline()):
                if proc.pid != os.getpid():
                    os.kill(proc.pid, signal.SIGTERM)
    except Exception:
        pass
    
    app = Application.builder().token(BOT_TOKEN).post_init(on_start).build()
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, anti_ad_filter))
    app.add_handler(CommandHandler("killbot", cmd_killbot))
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("plan", cmd_plan))
    app.add_handler(CommandHandler("info", cmd_info))
    app.add_handler(CommandHandler("allcm", cmd_allcm))
    
    app.add_handler(get_chk_handler())
    app.add_handler(get_pp_handler())
    app.add_handler(get_sh_handler())
    app.add_handler(get_pyu_handler())
    app.add_handler(get_bin_handler())
    
    for cmd in [
        ("onchk", cmd_onchk), ("offchk", cmd_offchk), 
        ("onpp", cmd_onpp), ("offpp", cmd_offpp), 
        ("onsh", cmd_onsh), ("offsh", cmd_offsh), 
        ("onpyu", cmd_onpyu), ("offpyu", cmd_offpyu)
    ]:
        app.add_handler(CommandHandler(cmd[0], cmd[1]))
        
    for handler in get_plans_handler(): 
        app.add_handler(handler)
        
    app.add_handler(CallbackQueryHandler(on_callback))
    
    print("Online! Bot is running perfectly.")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
