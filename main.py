import logging
import asyncio
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from datetime import datetime

from config import BOT_TOKEN, OWNER_ID, VERSION, DEV_LINK, CHANNEL_USERNAME, GROUP_USERNAME, CHANNEL_LINK, GROUP_LINK
from chk import get_chk_handler
from pp import get_pp_handler
from sh import get_sh_handler
from pyu import get_pyu_handler

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 LINKS & MEDIA 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BOT_PHOTO = "https://z-cdn-media.chatglm.cn/files/e82a6a24-028b-47b0-b909-003812e3ad83.jpg?auth_key=1882226135-b1b80190e4204674b0398d13564d82fe-0-874f5e21b888b225a795c7f0f75b970a"
SUPPORT_LINK = "https://t.me/cardchkSupport"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 ANTI-ADVERTISEMENT SYSTEM 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def anti_ad_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Instantly deletes messages containing external links to keep bot clean."""
    if not update.message or not update.message.text:
        return
    
    text = update.message.text
    user_id = update.effective_user.id
    
    # Allow owner to send links
    if user_id == OWNER_ID:
        return
    
    # Block any t.me or http links sent by users
    if "t.me/" in text or "http://" in text or "https://" in text:
        try:
            await update.message.delete()
        except Exception:
            pass

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 ULTRA FAST FORCE JOIN CHECK 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def is_joined(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    async def check(chat_id):
        try:
            m = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            return m.status not in ['left', 'kicked']
        except Exception:
            return False
            
    results = await asyncio.gather(check(CHANNEL_USERNAME), check(GROUP_USERNAME))
    return all(results)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 CLEAN UI GENERATORS 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def ui_profile(user):
    d = datetime.now().strftime("%Y-%m-%d")
    u = user.username or "None"
    return (
        f"Uꜱᴇʀ ➺ {u}\n"
        f"Uꜱᴇʀ ID ➺ <code>{user.id}</code>\n"
        f"Aᴄᴄᴇꜱꜱ ➺ Tʀɪᴀʟ\n"
        f"Cʀᴇᴅɪᴛꜱ ➺ 150\n"
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
        [InlineKeyboardButton("JOIN GROUP", url="https://t.me/batcardchkGroup")],
        [InlineKeyboardButton("JOIN CHANNEL", url="https://t.me/Batcardchk")],
        [InlineKeyboardButton("VERIFY", callback_data="verify_join")]
    ])

def kb_price():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("10$ PAY", callback_data="pay10"), InlineKeyboardButton("20$ PAY", callback_data="pay20"), InlineKeyboardButton("30$ PAY", callback_data="pay30")],
        [InlineKeyboardButton("◀ BACK", callback_data="bmain")]
    ])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 HELPER: RESOLVE USERNAME TO USER ID 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def resolve_user(target: str, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    target = target.lstrip('@')
    if target.lstrip('-').isdigit():
        return int(target)
    try:
        chat = await context.bot.get_chat(f"@{target}")
        return chat.id
    except Exception:
        return None

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 COMMAND HANDLERS 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if 'user_data' not in context.bot_data:
        context.bot_data['user_data'] = {}
    if str(user.id) not in context.bot_data['user_data']:
        context.bot_data['user_data'][str(user.id)] = {
            "name": user.first_name,
            "joined": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    if await is_joined(user.id, context):
        await update.message.reply_text(text=ui_profile(user), parse_mode="HTML", reply_markup=kb_main(), disable_web_page_preview=True)
    else:
        cap = (
            "BATMAN CARD CHECKER\n\n"
            "Access Required\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Join both channels to\n"
            "unlock the bot.\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        try:
            await update.message.reply_photo(photo=BOT_PHOTO, caption=cap, parse_mode="HTML", reply_markup=kb_force())
        except Exception:
            await update.message.reply_text(text=cap, parse_mode="HTML", reply_markup=kb_force())

async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    
    target_id = None
    target_input = None
    
    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
        target_input = str(target_id)
    elif context.args:
        target_input = context.args[0]
        target_id = await resolve_user(target_input, context)
    else:
        await update.message.reply_text("❌ INVALID USAGE\n\n━━━━━━━━━━━━━━━━━━━━\nUsage Methods:\n\n1. Reply to user's message:\n   /info (reply to msg)\n\n2. By Username:\n   /info @username\n   /info username\n\n3. By User ID:\n   /info 123456789\n━━━━━━━━━━━━━━━━━━━━", parse_mode="HTML")
        return

    if target_id is None:
        await update.message.reply_text(f"❌ USER NOT FOUND\n\n━━━━━━━━━━━━━━━━━━━━\nCould not resolve: <code>{target_input}</code>\n━━━━━━━━━━━━━━━━━━━━", parse_mode="HTML")
        return

    try:
        chat = await context.bot.get_chat(target_id)
        first_name = chat.first_name or "N/A"
        last_name = chat.last_name or "N/A"
        full_name = f"{first_name} {last_name}".strip() if last_name != "N/A" else first_name
        username = f"@{chat.username}" if chat.username else "None"
        user_id = chat.id
        
        all_users = context.bot_data.get('user_data', {})
        user_info = all_users.get(str(target_id))
        join_date = user_info.get('joined', 'N/A') if user_info else "Never interacted"
        stored_name = user_info.get('name', 'N/A') if user_info else "N/A"
        
        try:
            if hasattr(chat, 'date') and chat.date:
                account_created = chat.date.strftime("%Y-%m-%d %H:%M:%S")
                days_old = (datetime.now() - chat.date).days
                account_age = f"{days_old} days"
            else:
                account_created = "N/A"
                account_age = "N/A"
        except Exception:
            account_created = "N/A"
            account_age = "N/A"
        
        is_bot = "Yes" if hasattr(chat, 'is_bot') and chat.is_bot else "No"
        is_premium = "Yes" if hasattr(chat, 'is_premium') and chat.is_premium else "No"
        
        info_text = (
            "USER INFORMATION\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Name: {full_name}\nUsername: {username}\nUser ID: <code>{user_id}</code>\nIs Bot: {is_bot}\nPremium: {is_premium}\n\n"
            "━━━━━━━━━━━━━━━━━━━━\nACCOUNT DETAILS\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Account Created: {account_created}\nAccount Age: {account_age}\n\n"
            "━━━━━━━━━━━━━━━━━━━━\nBOT DATA\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"First Interacted: {join_date}\nStored Name: {stored_name}\nAccess Level: Trial\nCredits: 150\nPurchased On: N/A\nEnding On: N/A\n\n━━━━━━━━━━━━━━━━━━━━"
        )
        await update.message.reply_text(info_text, parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ ERROR\n\n━━━━━━━━━━━━━━━━━━━━\n<code>{str(e)}</code>\n━━━━━━━━━━━━━━━━━━━━", parse_mode="HTML")

async def cmd_allcommand(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    commands_list = (
        "BATMAN BOT - ALL COMMANDS\n━━━━━━━━━━━━━━━━━━━━\nVersion: {ver}\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "USER COMMANDS\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "▸ /start - Start the bot\n▸ /chk - Stripe charge check\n▸ /pp - PayPal check\n▸ /sh - Shopify check\n▸ /pyu - PayU check\n\n"
        "OWNER COMMANDS\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "▸ /info - Get user info\n▸ /allcommand - Show this\n▸ /onchk /offchk - Stripe Gate\n▸ /onpp /offpp - PayPal Gate\n▸ /onsh /offsh - Shopify Gate\n▸ /onpyu /offpyu - PayU Gate\n\n━━━━━━━━━━━━━━━━━━━━".format(ver=VERSION)
    )
    await update.message.reply_text(commands_list, parse_mode="HTML")

# Gate Controls
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

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 CALLBACK HANDLER 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data
    
    if d == "verify_join":
        if await is_joined(q.from_user.id, context):
            try:
                if q.message.photo:
                    await q.message.delete()
                    await context.bot.send_message(chat_id=q.message.chat_id, text=ui_profile(q.from_user), parse_mode="HTML", reply_markup=kb_main(), disable_web_page_preview=True)
                else:
                    await q.edit_message_text(text=ui_profile(q.from_user), parse_mode="HTML", reply_markup=kb_main(), disable_web_page_preview=True)
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
        t = ("Aᴄᴄᴇꜱꜱ ➺ Cᴏʀᴇ 🎀\nSᴘᴀɴ ➺ [7 Dᴀʏꜱ]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛᴇᴅ\nPʀɪᴄᴇ ➺ 10$\n━━━━━━━━━━━━━━━━\nAᴄᴄᴇꜱꜱ ➺ Eʟɪᴛᴇ ⭐️\nSᴘᴀɴ ➺ [15 Dᴀʏꜱ]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛᴇᴅ\nPʀɪᴄᴇ ➺ 15$\n━━━━━━━━━━━━━━━━\nAᴄᴄᴇꜱꜱ ➺ Rᴏᴏᴛ 👑\nSᴘᴀɴ ➺ [30 Dᴀʏꜱ]\nCʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛᴇᴅ\nPʀɪᴄᴇ ➺ 30$")
        await edit(t, kb_price())
    elif d == "pay10":
        await edit(f"PAYMENT - 10$\n━━━━━━━━━━━━━━━━━━━━\n\nBase Amount: 10$\nTaxes: Included\nTotal: 10$\n\n━━━━━━━━━━━━━━━━━━━━\n⏳ Soon the payment\naddress will be added\nwith taxes included.\n━━━━━━━━━━━━━━━━━━━━\n\nContact <a href='{DEV_LINK}'>Batman</a> for manual payment.".format(DEV_LINK=DEV_LINK), kb_back("mprice"))
    elif d == "pay20":
        await edit(f"PAYMENT - 20$\n━━━━━━━━━━━━━━━━━━━━\n\nBase Amount: 20$\nTaxes: Included\nTotal: 20$\n\n━━━━━━━━━━━━━━━━━━━━\n⏳ Soon the payment\naddress will be added\nwith taxes included.\n━━━━━━━━━━━━━━━━━━━━\n\nContact <a href='{DEV_LINK}'>Batman</a> for manual payment.".format(DEV_LINK=DEV_LINK), kb_back("mprice"))
    elif d == "pay30":
        await edit(f"PAYMENT - 30$\n━━━━━━━━━━━━━━━━━━━━\n\nBase Amount: 30$\nTaxes: Included\nTotal: 30$\n\n━━━━━━━━━━━━━━━━━━━━\n⏳ Soon the payment\naddress will be added\nwith taxes included.\n━━━━━━━━━━━━━━━━━━━━\n\nContact <a href='{DEV_LINK}'>Batman</a> for manual payment.".format(DEV_LINK=DEV_LINK), kb_back("mprice"))
    elif d == "mgates":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("AUTH", callback_data="mauth"), InlineKeyboardButton("CHARGE", callback_data="mcharge")],[InlineKeyboardButton("◀ BACK", callback_data="bmain")]])
        await edit("SELECT GATE", kb)
    elif d == "mauth":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Stripe", callback_data="iau"), InlineKeyboardButton("Braintree", callback_data="ib3")],[InlineKeyboardButton("◀ BACK", callback_data="mgates")]])
        await edit("AUTH GATES", kb)
    elif d == "iau":
        await edit("━━━━━━━━━━━━━━━━━━━━\nGATE: Stripe Auth\nCMD: /au\nSITES: 16\nHEALTH: 100%\n━━━━━━━━━━━━━━━━━━━━", kb_back("mauth"))
    elif d == "ib3":
        await edit("━━━━━━━━━━━━━━━━━━━━\nGATE: Braintree Auth\nCMD: /b3\nSITES: 2\nHEALTH: 100%\n━━━━━━━━━━━━━━━━━━━━", kb_back("mauth"))
    elif d == "mcharge":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Stripe", callback_data="ichk"), InlineKeyboardButton("PayPal", callback_data="ipp")],[InlineKeyboardButton("Shopify", callback_data="ish"), InlineKeyboardButton("PayU", callback_data="ipyu")],[InlineKeyboardButton("◀ BACK", callback_data="mgates")]])
        await edit("CHARGE GATES", kb)
    elif d == "ichk":
        await edit("━━━━━━━━━━━━━━━━━━━━\nGATE: Stripe\nPRICE: $0.50\nCMD: /chk\nSITES: 4\nHEALTH: 100%\n━━━━━━━━━━━━━━━━━━━━", kb_back("mcharge"))
    elif d == "ipp":
        await edit("━━━━━━━━━━━━━━━━━━━━\nGATE: PayPal\nPRICE: $0.10\nCMD: /pp\nSITES: 7\nHEALTH: 100%\n━━━━━━━━━━━━━━━━━━━━", kb_back("mcharge"))
    elif d == "ish":
        await edit("━━━━━━━━━━━━━━━━━━━━\nGATE: Shopify\nPRICE: $1.00\nCMD: /sh\nSITES: 10\nHEALTH: 100%\n━━━━━━━━━━━━━━━━━━━━", kb_back("mcharge"))
    elif d == "ipyu":
        await edit("━━━━━━━━━━━━━━━━━━━━\nGATE: PayU\nPRICE: $0.30\nCMD: /pyu\nSITES: 1\nHEALTH: 100%\n━━━━━━━━━━━━━━━━━━━━", kb_back("mcharge"))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 STARTUP 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def on_start(app):
    print("Batman Starting...")
    await app.bot.delete_webhook(drop_pending_updates=True)

def main():
    app = Application.builder().token(BOT_TOKEN).post_init(on_start).build()
    
    # Anti-Ad System (Deletes user messages with links)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, anti_ad_filter))
    
    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("info", cmd_info))
    app.add_handler(CommandHandler("allcommand", cmd_allcommand))
    
    # Gates
    app.add_handler(get_chk_handler())
    app.add_handler(get_pp_handler())
    app.add_handler(get_sh_handler())
    app.add_handler(get_pyu_handler())
    
    for cmd in [("onchk", cmd_onchk), ("offchk", cmd_offchk), ("onpp", cmd_onpp), ("offpp", cmd_offpp), ("onsh", cmd_onsh), ("offsh", cmd_offsh), ("onpyu", cmd_onpyu), ("offpyu", cmd_offpyu)]:
        app.add_handler(CommandHandler(cmd[0], cmd[1]))
        
    app.add_handler(CallbackQueryHandler(on_callback))
    
    print("Online!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
