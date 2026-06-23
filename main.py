import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
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
# 🦇 ULTRA FAST FORCE JOIN CHECK 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def is_joined(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    async def check(chat_id):
        try:
            m = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            return m.status not in ['left', 'kicked']
        except Exception:
            return False
            
    # Checks Group AND Channel at the exact same time (2x Faster)
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
    """Resolve a username or user ID to a user ID."""
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
        await update.message.reply_text(
            text=ui_profile(user), 
            parse_mode="HTML", 
            reply_markup=kb_main(), 
            disable_web_page_preview=True
        )
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
            await update.message.reply_photo(
                photo=BOT_PHOTO, 
                caption=cap, 
                parse_mode="HTML", 
                reply_markup=kb_force()
            )
        except Exception:
            await update.message.reply_text(
                text=cap, 
                parse_mode="HTML", 
                reply_markup=kb_force()
            )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 OWNER /info COMMAND (SUPPORTS USERNAME & ID) 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    
    target_id = None
    target_input = None
    
    # Method 1: Reply to message
    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
        target_input = str(target_id)
    # Method 2: Command argument (username or ID)
    elif context.args:
        target_input = context.args[0]
        target_id = await resolve_user(target_input, context)
    else:
        await update.message.reply_text(
            "❌ INVALID USAGE\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Usage Methods:\n\n"
            "1. Reply to user's message:\n"
            "   /info (reply to msg)\n\n"
            "2. By Username:\n"
            "   /info @username\n"
            "   /info username\n\n"
            "3. By User ID:\n"
            "   /info 123456789\n"
            "━━━━━━━━━━━━━━━━━━━━",
            parse_mode="HTML"
        )
        return

    if target_id is None:
        await update.message.reply_text(
            f"❌ USER NOT FOUND\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Could not resolve: <code>{target_input}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━",
            parse_mode="HTML"
        )
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
        
        if user_info:
            join_date = user_info.get('joined', 'N/A')
            stored_name = user_info.get('name', 'N/A')
        else:
            join_date = "Never interacted"
            stored_name = "N/A"
        
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
            "USER INFORMATION\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Name: {full_name}\n"
            f"Username: {username}\n"
            f"User ID: <code>{user_id}</code>\n"
            f"Is Bot: {is_bot}\n"
            f"Premium: {is_premium}\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "ACCOUNT DETAILS\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Account Created: {account_created}\n"
            f"Account Age: {account_age}\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "BOT DATA\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"First Interacted: {join_date}\n"
            f"Stored Name: {stored_name}\n"
            f"Access Level: Trial\n"
            f"Credits: 150\n"
            f"Purchased On: N/A\n"
            f"Ending On: N/A\n\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        await update.message.reply_text(info_text, parse_mode="HTML")
        
    except Exception as e:
        await update.message.reply_text(
            f"❌ ERROR\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<code>{str(e)}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━",
            parse_mode="HTML"
        )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 OWNER /allcommand COMMAND 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def cmd_allcommand(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    
    commands_list = (
        "BATMAN BOT - ALL COMMANDS\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Version: {VERSION}\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        
        "USER COMMANDS\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        
        "▸ /start\n"
        "  Start the bot\n"
        "  Usage: /start\n\n"
        
        "▸ /chk\n"
        "  Stripe charge check\n"
        "  Usage: /chk cc|mm|yy|cvv\n"
        "  Cost: $0.50\n\n"
        
        "▸ /pp\n"
        "  PayPal check\n"
        "  Usage: /pp email|pass\n"
        "  Cost: $0.10\n\n"
        
        "▸ /sh\n"
        "  Shopify check\n"
        "  Usage: /sh cc|mm|yy|cvv\n"
        "  Cost: $1.00\n\n"
        
        "▸ /pyu\n"
        "  PayU check\n"
        "  Usage: /pyu cc|mm|yy|cvv\n"
        "  Cost: $0.30\n\n"
        
        "▸ /au\n"
        "  Stripe Auth check\n"
        "  Usage: /au cc|mm|yy|cvv\n\n"
        
        "▸ /b3\n"
        "  Braintree Auth check\n"
        "  Usage: /b3 cc|mm|yy|cvv\n\n"
        
        "OWNER COMMANDS\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        
        "▸ /info\n"
        "  Get user information\n"
        "  Usage: /info @username\n"
        "  Usage: /info 123456789\n"
        "  Usage: Reply + /info\n"
        "  Owner Only\n\n"
        
        "▸ /allcommand\n"
        "  Show all commands\n"
        "  Usage: /allcommand\n"
        "  Owner Only\n\n"
        
        "▸ /onchk\n"
        "  Enable Stripe gate\n"
        "  Owner Only\n\n"
        
        "▸ /offchk\n"
        "  Disable Stripe gate\n"
        "  Owner Only\n\n"
        
        "▸ /onpp\n"
        "  Enable PayPal gate\n"
        "  Owner Only\n\n"
        
        "▸ /offpp\n"
        "  Disable PayPal gate\n"
        "  Owner Only\n\n"
        
        "▸ /onsh\n"
        "  Enable Shopify gate\n"
        "  Owner Only\n\n"
        
        "▸ /offsh\n"
        "  Disable Shopify gate\n"
        "  Owner Only\n\n"
        
        "▸ /onpyu\n"
        "  Enable PayU gate\n"
        "  Owner Only\n\n"
        
        "▸ /offpyu\n"
        "  Disable PayU gate\n"
        "  Owner Only\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Dev: <a href='{DEV_LINK}'>Batman</a>"
    )
    
    await update.message.reply_text(commands_list, parse_mode="HTML", disable_web_page_preview=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 OWNER GATE CONTROLS 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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
                # Delete photo and send clean text profile
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
        t = (
            "Aᴄᴄᴇꜱꜱ ➺ Cᴏʀᴇ 🎀\n"
            "Sᴘᴀɴ ➺ [7 Dᴀʏꜱ]\n"
            "Cʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛᴇᴅ\n"
            "Pʀɪᴄᴇ ➺ 10$\n"
            "━━━━━━━━━━━━━━━━\n"
            "Aᴄᴄᴇꜱꜱ ➺ Eʟɪᴛᴇ ⭐️\n"
            "Sᴘᴀɴ ➺ [15 Dᴀʏꜱ]\n"
            "Cʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛᴇᴅ\n"
            "Pʀɪᴄᴇ ➺ 15$\n"
            "━━━━━━━━━━━━━━━━\n"
            "Aᴄᴄᴇꜱꜱ ➺ Rᴏᴏᴛ 👑\n"
            "Sᴘᴀɴ ➺ [30 Dᴀʏꜱ]\n"
            "Cʀᴇᴅɪᴛꜱ ➺ ∞ Uɴʟɪᴍɪᴛᴇᴅ\n"
            "Pʀɪᴄᴇ ➺ 30$"
        )
        await edit(t, kb_price())
        
    elif d == "pay10":
        t = (
            "PAYMENT - 10$\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Base Amount: 10$\n"
            "Taxes: Included\n"
            "Total: 10$\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "⏳ Soon the payment\n"
            "address will be added\n"
            "with taxes included.\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Contact <a href='{DEV_LINK}'>Batman</a> for manual payment."
        )
        await edit(t, kb_back("mprice"))
        
    elif d == "pay20":
        t = (
            "PAYMENT - 20$\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Base Amount: 20$\n"
            "Taxes: Included\n"
            "Total: 20$\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "⏳ Soon the payment\n"
            "address will be added\n"
            "with taxes included.\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Contact <a href='{DEV_LINK}'>Batman</a> for manual payment."
        )
        await edit(t, kb_back("mprice"))
        
    elif d == "pay30":
        t = (
            "PAYMENT - 30$\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Base Amount: 30$\n"
            "Taxes: Included\n"
            "Total: 30$\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "⏳ Soon the payment\n"
            "address will be added\n"
            "with taxes included.\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Contact <a href='{DEV_LINK}'>Batman</a> for manual payment."
        )
        await edit(t, kb_back("mprice"))
        
    elif d == "mgates":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("AUTH", callback_data="mauth"), InlineKeyboardButton("CHARGE", callback_data="mcharge")],
            [InlineKeyboardButton("◀ BACK", callback_data="bmain")]
        ])
        await edit("SELECT GATE", kb)
        
    elif d == "mauth":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Stripe", callback_data="iau"), InlineKeyboardButton("Braintree", callback_data="ib3")],
            [InlineKeyboardButton("◀ BACK", callback_data="mgates")]
        ])
        await edit("AUTH GATES", kb)
        
    elif d == "iau":
        await edit(
            "━━━━━━━━━━━━━━━━━━━━\n"
            "GATE: Stripe Auth\n"
            "CMD: /au\n"
            "SITES: 16\n"
            "HEALTH: 100%\n"
            "━━━━━━━━━━━━━━━━━━━━",
            kb_back("mauth")
        )
    elif d == "ib3":
        await edit(
            "━━━━━━━━━━━━━━━━━━━━\n"
            "GATE: Braintree Auth\n"
            "CMD: /b3\n"
            "SITES: 2\n"
            "HEALTH: 100%\n"
            "━━━━━━━━━━━━━━━━━━━━",
            kb_back("mauth")
        )
        
    elif d == "mcharge":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Stripe", callback_data="ichk"), InlineKeyboardButton("PayPal", callback_data="ipp")],
            [InlineKeyboardButton("Shopify", callback_data="ish"), InlineKeyboardButton("PayU", callback_data="ipyu")],
            [InlineKeyboardButton("◀ BACK", callback_data="mgates")]
        ])
        await edit("CHARGE GATES", kb)
        
    elif d == "ichk":
        await edit(
            "━━━━━━━━━━━━━━━━━━━━\n"
            "GATE: Stripe\n"
            "PRICE: $0.50\n"
            "CMD: /chk\n"
            "SITES: 4\n"
            "HEALTH: 100%\n"
            "━━━━━━━━━━━━━━━━━━━━",
            kb_back("mcharge")
        )
    elif d == "ipp":
        await edit(
            "━━━━━━━━━━━━━━━━━━━━\n"
            "GATE: PayPal\n"
            "PRICE: $0.10\n"
            "CMD: /pp\n"
            "SITES: 7\n"
            "HEALTH: 100%\n"
            "━━━━━━━━━━━━━━━━━━━━",
            kb_back("mcharge")
        )
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

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 STARTUP 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def on_start(app):
    print("Batman Starting...")
    await app.bot.delete_webhook(drop_pending_updates=True)

def main():
    app = Application.builder().token(BOT_TOKEN).post_init(on_start).build()
    
    # User commands
    app.add_handler(CommandHandler("start", cmd_start))
    
    # Owner commands
    app.add_handler(CommandHandler("info", cmd_info))
    app.add_handler(CommandHandler("allcommand", cmd_allcommand))
    
    # Gate handlers (Imported from your files)
    app.add_handler(get_chk_handler())
    app.add_handler(get_pp_handler())
    app.add_handler(get_sh_handler())
    app.add_handler(get_pyu_handler())
    
    # Gate toggle commands
    for cmd in [("onchk", cmd_onchk), ("offchk", cmd_offchk), 
                ("onpp", cmd_onpp), ("offpp", cmd_offpp), 
                ("onsh", cmd_onsh), ("offsh", cmd_offsh), 
                ("onpyu", cmd_onpyu), ("offpyu", cmd_offpyu)]:
        app.add_handler(CommandHandler(cmd[0], cmd[1]))
        
    app.add_handler(CallbackQueryHandler(on_callback))
    
    print("Online!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
