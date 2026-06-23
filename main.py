import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from datetime import datetime

from config import BOT_TOKEN, OWNER_ID, VERSION, DEV_LINK, CHANNEL_USERNAME, GROUP_USERNAME, CHANNEL_LINK, GROUP_LINK, SUPPORT_LINK
from chk import get_chk_handler
from pp import get_pp_handler
from sh import get_sh_handler
from pyu import get_pyu_handler

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

# 🦇 YOUR BATMAN PHOTO (ONLY SHOWS ON WELCOME SCREEN) 🦇
BOT_PHOTO = "https://z-cdn-media.chatglm.cn/files/e82a6a24-028b-47b0-b909-003812e3ad83.jpg?auth_key=1882226135-b1b80190e4204674b0398d13564d82fe-0-874f5e21b888b225a795c7f0f75b970a"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 FORCE JOIN CHECK 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def is_joined(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        c = await context.bot.get_chat_member(CHANNEL_USERNAME, user_id)
        if c.status in ['left', 'kicked']: return False
        g = await context.bot.get_chat_member(GROUP_USERNAME, user_id)
        if g.status in ['left', 'kicked']: return False
        return True
    except Exception:
        return False

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 CLEAN UI GENERATORS (NO PHOTO, EASY COPY ID) 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def ui_profile(user):
    d = datetime.now().strftime("%Y-%m-%d")
    u = user.username or "None"
    # Note: There is a space after {user.id} inside <code> so you only copy the numbers
    return (
        f"Uꜱᴇʀ ➺ {u}\n"
        f"Uꜱᴇʀ ID ➺ <code>{user.id} </code>\n"
        f"Aᴄᴄᴇꜱꜱ ➺ Tʀɪᴀʟ\n"
        f"Cʀᴇᴅɪᴛꜱ ➺ 150\n"
        f"Jᴏɪɴᴇᴅ ➺ {d}\n"
        f"Dᴇᴠ ➺ <a href='{DEV_LINK}'>Batman</a>"
    )

def kb_main():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🖤 𝗖𝗛𝗘𝗖𝗞𝗘𝗥", callback_data="mgates"), InlineKeyboardButton("⬛ 𝗕𝗨𝗬 𝗡𝗢𝗪", callback_data="mprice")],
        [InlineKeyboardButton("•• 𝗨𝗣𝗗𝗔𝗧𝗘𝗦 ••", url=CHANNEL_LINK), InlineKeyboardButton("•• 𝗚𝗥𝗢𝗨𝗣 ••", url=GROUP_LINK)],
        [InlineKeyboardButton("🦇 𝗦𝗨𝗣𝗣𝗢𝗥𝗧", url=SUPPORT_LINK)]
    ])

def kb_back(cb):
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬛ ◀️ 𝗕𝗔𝗖𝗞", callback_data=cb)]])

def kb_force():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬛ 𝗝𝗢𝗜𝗡 𝗚𝗥𝗢𝗨𝗣", url="https://t.me/batcardchkGroup")],
        [InlineKeyboardButton("🖤 𝗝𝗢𝗜𝗡 𝗖𝗛𝗔𝗡𝗡𝗘𝗟", url="https://t.me/Batcardchk")],
        [InlineKeyboardButton("🔐 𝗩𝗔𝗥𝗜𝗙𝗬", callback_data="verify_join")]
    ])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 COMMAND HANDLERS 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # Save user join date for /info
    if 'user_data' not in context.bot_data:
        context.bot_data['user_data'] = {}
    if str(user.id) not in context.bot_data['user_data']:
        context.bot_data['user_data'][str(user.id)] = {
            "name": user.first_name,
            "joined": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    if await is_joined(user.id, context):
        # ALREADY JOINED: Send ONLY text, NO photo
        await update.message.reply_text(
            text=ui_profile(user), 
            parse_mode="HTML", 
            reply_markup=kb_main(), 
            disable_web_page_preview=True
        )
    else:
        # NOT JOINED: Send photo + buttons
        cap = (
            "🦇 ⚫ 𝐁𝐀𝐓𝐌𝐀𝐍 𝐂𝐀𝐑𝐃 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 ⚫ 🦇\n\n"
            "🔐 𝐀𝐜𝐜𝐞𝐬𝐬 𝐑𝐞𝐪𝐮𝐢𝐫𝐞𝐝\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "⏳ Join both channels to unlock\n"
            "the Batcomputer.\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        )
        try:
            await update.message.reply_photo(
                photo=BOT_PHOTO, 
                caption=cap, 
                parse_mode="HTML", 
                reply_markup=kb_force()
            )
        except Exception:
            await update.message.reply_text(text=cap, parse_mode="HTML", reply_markup=kb_force())

# 🦇 OWNER /info COMMAND (STRICTLY OWNER, SHOWS USERNAME) 🦇
async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # RESTRICTED: If not owner, completely ignore the command (no error shown to user)
    if update.effective_user.id != OWNER_ID:
        return
    
    target_id = None
    
    # Check if owner replied to a user's message
    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
    # Check if owner provided a user ID manually
    elif context.args and context.args[0].lstrip('-').isdigit():
        target_id = int(context.args[0])
    else:
        # Only show error text to the OWNER if they typed it wrong
        await update.message.reply_text("❌ Usage: <code>/info [UserID]</code>\n_or reply to a user's message_", parse_mode="HTML")
        return

    try:
        # Get fresh user data from Telegram
        chat = await context.bot.get_chat(target_id)
        name = chat.first_name
        username = f"@{chat.username}" if chat.username else "None"
        
        # Get join date from bot memory
        all_users = context.bot_data.get('user_data', {})
        user_info = all_users.get(str(target_id))
        
        if user_info and 'joined' in user_info:
            join_date = user_info['joined'].split(" ")[0]
        else:
            join_date = "N/A"
            
        # Exact UI with Name and Username included
        info_text = (
            f"Uꜱᴇʀ ➺ {name}\n"
            f"Uꜱᴇʀɴᴀᴍᴇ ➺ {username}\n"
            f"Uꜱᴇʀ ID ➺ <code>{target_id} </code>\n"
            f"Aᴄᴄᴇꜱꜱ ➺ Tʀɪᴀʟ\n"
            f"Pᴜʀᴄʜᴀꜱᴇᴅ Oɴ ➺ N/A\n"
            f"Eɴᴅɪɴɢ Oɴ ➺ N/A\n"
            f"Cʀᴇᴅɪᴛꜱ ➺ 150\n"
            f"Jᴏɪɴᴇᴅ ➺ {join_date}"
        )
        await update.message.reply_text(info_text, parse_mode="HTML")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error fetching user: <code>{str(e)}</code>", parse_mode="HTML")

# Owner Gate Controls
async def cmd_onchk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data['chk_on'] = True
    await update.message.reply_text("⬛ <b>STRIPE → ON</b>", parse_mode="HTML")

async def cmd_offchk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data['chk_on'] = False
    await update.message.reply_text("⬛ <b>STRIPE → OFF</b>", parse_mode="HTML")

async def cmd_onpp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data['pp_on'] = True
    await update.message.reply_text("⬛ <b>PAYPAL → ON</b>", parse_mode="HTML")

async def cmd_offpp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data['pp_on'] = False
    await update.message.reply_text("⬛ <b>PAYPAL → OFF</b>", parse_mode="HTML")

async def cmd_onsh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data['sh_on'] = True
    await update.message.reply_text("⬛ <b>SHOPIFY → ON</b>", parse_mode="HTML")

async def cmd_offsh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data['sh_on'] = False
    await update.message.reply_text("⬛ <b>SHOPIFY → OFF</b>", parse_mode="HTML")

async def cmd_onpyu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data['pyu_on'] = True
    await update.message.reply_text("⬛ <b>PAYU → ON</b>", parse_mode="HTML")

async def cmd_offpyu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data['pyu_on'] = False
    await update.message.reply_text("⬛ <b>PAYU → OFF</b>", parse_mode="HTML")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 CALLBACK HANDLER 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data
    
    # Using edit_message_text automatically removes the photo when they verify!
    async def edit(t, kb):
        try:
            await q.edit_message_text(text=t, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
        except Exception:
            pass
    
    if d == "verify_join":
        if await is_joined(q.from_user.id, context):
            await q.answer("✅ Access Granted!", show_alert=True)
            # This changes the photo message into pure text
            await edit(ui_profile(q.from_user), kb_main())
        else:
            await q.answer("❌ Error: Join Group & Channel first!", show_alert=True)
        return
    
    if d == "bmain":
        await edit(ui_profile(q.from_user), kb_main())
    elif d == "mprice":
        t = "🦇 ⚫ 𝐏𝐑𝐈𝐂𝐈𝐍𝐆 ⚫ 🦇\n\n━━━━━━━━━━━━━━━━━━━━━━\n⚡ Trial → <b>FREE</b>\n🖤 Elite → <b>$5</b>\n⬛ VIP → <b>$10</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n" + f"Contact <a href='{DEV_LINK}'>Batman</a> 🦇"
        await edit(t, kb_back("bmain"))
    elif d == "mgates":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⚡ 𝗔𝗨𝗧𝗛", callback_data="mauth"), InlineKeyboardButton("💀 𝗖𝗛𝗔𝗥𝗚𝗘", callback_data="mcharge")],[InlineKeyboardButton("⬛ ◀️ 𝗕𝗔𝗖𝗞", callback_data="bmain")]])
        await edit("🦇 ⚫ 𝐒𝐄𝐋𝐄𝐂𝐓 𝐆𝐀𝐓𝐄 ⚫ 🦇", kb)
    elif d == "mauth":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⚡ Stripe", callback_data="iau"), InlineKeyboardButton("🖤 Braintree", callback_data="ib3")],[InlineKeyboardButton("⬛ ◀️ 𝗕𝗔𝗖𝗞", callback_data="mgates")]])
        await edit("⚡ ⚫ 𝗔𝗨𝗧𝗛 𝗚𝗔𝗧𝗘𝗦 ⚫ ⚡", kb)
    elif d == "iau":
        await edit("━━━━━━━━━━━━━━━━━━━━━━\n⚡ <b>GATE</b> ➤ Stripe Auth\n📋 <b>CMD</b> ➤ /au\n🌐 <b>SITES</b> ➤ 16\n🖤 <b>HEALTH</b> ➤ 100%\n━━━━━━━━━━━━━━━━━━━━━━", kb_back("mauth"))
    elif d == "ib3":
        await edit("━━━━━━━━━━━━━━━━━━━━━━\n🖤 <b>GATE</b> ➤ Braintree Auth\n📋 <b>CMD</b> ➤ /b3\n🌐 <b>SITES</b> ➤ 2\n🖤 <b>HEALTH</b> ➤ 100%\n━━━━━━━━━━━━━━━━━━━━━━", kb_back("mauth"))
    elif d == "mcharge":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⚡ Stripe", callback_data="ichk"), InlineKeyboardButton("💰 PayPal", callback_data="ipp")],[InlineKeyboardButton("🛒 Shopify", callback_data="ish"), InlineKeyboardButton("💸 PayU", callback_data="ipyu")],[InlineKeyboardButton("⬛ ◀️ 𝗕𝗔𝗖𝗞", callback_data="mgates")]])
        await edit("💀 ⚫ 𝗖𝗛𝗔𝗥𝗚𝗘 𝗚𝗔𝗧𝗘𝗦 ⚫ 💀", kb)
    elif d == "ichk":
        await edit("━━━━━━━━━━━━━━━━━━━━━━\n⚡ <b>GATE</b> ➤ Stripe\n💵 <b>PRICE</b> ➤ $0.50\n📋 <b>CMD</b> ➤ /chk\n🌐 <b>SITES</b> ➤ 4\n🖤 <b>HEALTH</b> ➤ 100%\n━━━━━━━━━━━━━━━━━━━━━━", kb_back("mcharge"))
    elif d == "ipp":
        await edit("━━━━━━━━━━━━━━━━━━━━━━\n💰 <b>GATE</b> ➤ PayPal\n💵 <b>PRICE</b> ➤ $0.10\n📋 <b>CMD</b> ➤ /pp\n🌐 <b>SITES</b> ➤ 7\n🖤 <b>HEALTH</b> ➤ 100%\n━━━━━━━━━━━━━━━━━━━━━━", kb_back("mcharge"))
    elif d == "ish":
        await edit("━━━━━━━━━━━━━━━━━━━━━━\n🛒 <b>GATE</b> ➤ Shopify\n💵 <b>PRICE</b> ➤ $1.00\n📋 <b>CMD</b> ➤ /sh\n🌐 <b>SITES</b> ➤ 10\n🖤 <b>HEALTH</b> ➤ 100%\n━━━━━━━━━━━━━━━━━━━━━━", kb_back("mcharge"))
    elif d == "ipyu":
        await edit("━━━━━━━━━━━━━━━━━━━━━━\n💸 <b>GATE</b> ➤ PayU\n💵 <b>PRICE</b> ➤ $0.30\n📋 <b>CMD</b> ➤ /pyu\n🌐 <b>SITES</b> ➤ 1\n🖤 <b>HEALTH</b> ➤ 100%\n━━━━━━━━━━━━━━━━━━━━━━", kb_back("mcharge"))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 STARTUP 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def on_start(app):
    print("🦇 Batman Card Checker Starting...")
    await app.bot.delete_webhook(drop_pending_updates=True)
    print("⬛ Webhooks Cleared - Ready!")

def main():
    app = Application.builder().token(BOT_TOKEN).post_init(on_start).build()
    
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("info", cmd_info))
    
    # Gate Handlers
    app.add_handler(get_chk_handler())
    app.add_handler(get_pp_handler())
    app.add_handler(get_sh_handler())
    app.add_handler(get_pyu_handler())
    
    # Owner Controls
    for cmd in [("onchk", cmd_onchk), ("offchk", cmd_offchk), ("onpp", cmd_onpp), ("offpp", cmd_offpp), ("onsh", cmd_onsh), ("offsh", cmd_offsh), ("onpyu", cmd_onpyu), ("offpyu", cmd_offpyu)]:
        app.add_handler(CommandHandler(cmd[0], cmd[1]))
        
    app.add_handler(CallbackQueryHandler(on_callback))
    
    print("🦇 Batman Card Checker Online!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
