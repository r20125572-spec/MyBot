import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from datetime import datetime
from chk import get_chk_handler
from pp import get_pp_handler
from sh import get_sh_handler
from pyu import get_pyu_handler
from fb import get_fb_handler, get_fb_callback_handler
from subs import get_subs_handlers

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 GOTHAM CONFIGURATION 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BOT_TOKEN = "8774596040:AAFGArSQUWOu5k_xRLyShiYy2y04uYzlPG4"

CHANNEL_1_USERNAME = "@Batcardchk" 
GROUP_1_USERNAME = "@batcardchkGroup" 
CHANNEL_1_LINK = "https://t.me/Batcardchk" 
GROUP_1_LINK = "https://t.me/batcardchkGroup" 

# Batman Image for Force Join
BOT_PHOTO_URL = "https://z-cdn-media.chatglm.cn/files/cd1a58d5-1a85-4246-8dac-dae333b02023.jpg"

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 FORCE JOIN SYSTEM 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def check_user_joined(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        m1 = await context.bot.get_chat_member(chat_id=CHANNEL_1_USERNAME, user_id=user_id)
        if m1.status in ['left', 'kicked']: return False
        m2 = await context.bot.get_chat_member(chat_id=GROUP_1_USERNAME, user_id=user_id)
        if m2.status in ['left', 'kicked']: return False
    except Exception: return False
    return True

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 BATMAN PREMIUM UI HELPERS 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_professional_caption(user):
    now = datetime.now().strftime("%d/%m/%y %H:%M:%S")
    username = f"@{user.username}" if user.username else "None"
    return (
        f"<pre>╭━━━ 🦇 𝐆𝐎𝐓𝐇𝐀𝐌 𝐒𝐘𝐒𝐓𝐄𝐌 🦇 ━━━╮\n"
        f"┃  𝑺𝒕𝒂𝒕𝒖𝒔: 𝐀𝐜𝐭𝐢𝐯𝐞 ✅  ┃\n"
        f"╰━━━━━━━━━━━━━━━━━━━━━━╯</pre>\n"
        f"◺ 𝐈𝐃 ↬ <code>{user.id}</code>\n"
        f"⋪ 𝐔𝒔𝒆𝒓 ↬ {username}\n"
        f"⊲ 𝐁𝐚𝐭𝐦𝐚𝐧 ↬ 𝐎𝐰𝐧𝐞𝐫 🦇\n"
        f"⊲ 𝐂𝐫𝐞𝐝𝐢𝐭𝐬 ↬ ∞\n"
        f"⊲ 𝐉𝐨𝐢𝐧𝐞𝐝 ↬ {now}\n"
        f"⌬ 𝐃𝐞𝐯 ↬ 𝐁𝐚𝐭𝐦𝐚𝐧 🦇"
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 BATMAN KEYBOARDS 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🦇 𝗚𝗮𝘁𝗲𝘀", callback_data="menu_gates"), InlineKeyboardButton("💰 𝗣𝗿𝗶𝗰𝗶𝗻𝗴", callback_data="menu_pricing")],
        [InlineKeyboardButton("🌃 𝗨𝗽𝗱𝗮𝘁𝗲𝘀", url=CHANNEL_1_LINK), InlineKeyboardButton("🦇 𝗚𝗿𝗼𝘂𝗽", url=GROUP_1_LINK)],
        [InlineKeyboardButton("🛡️ 𝗦𝘂𝗽𝗽𝗼𝗿𝘁", url="https://t.me/failurefr_07")]
    ])

def get_back_keyboard(target):
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸 𝘁𝗼 𝗚𝗼𝘁𝗵𝗮𝗺", callback_data=target)]])

def get_force_join_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌃 𝗝𝗢𝗜𝗡 𝗖𝗛𝗔𝗡𝗡𝗘𝗟", url=CHANNEL_1_LINK)],
        [InlineKeyboardButton("🦇 𝗝𝗢𝗜𝗡 𝗚𝗥𝗢𝗨𝗣", url=GROUP_1_LINK)],
        [InlineKeyboardButton("✅ 𝗩𝗲𝗿𝗶𝗳𝘆 𝗔𝗰𝗰𝗲𝘀𝘀", callback_data="verify_join")]
    ])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 HANDLERS 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if await check_user_joined(user.id, context):
        await update.message.reply_text(text=get_professional_caption(user), parse_mode="HTML", reply_markup=get_main_keyboard())
    else:
        cap = (
            "🦇 <b>Welcome to Gotham!</b>\n\n"
            "To access the Batcomputer, you must join the League of Shadows.\n\n"
            "1️⃣ Click <b>JOIN CHANNEL</b>\n"
            "2️⃣ Click <b>JOIN GROUP</b>\n"
            "3️⃣ Click <b>✅ Verify Access</b>"
        )
        try: await update.message.reply_photo(photo=BOT_PHOTO_URL, caption=cap, parse_mode="HTML", reply_markup=get_force_join_keyboard())
        except: await update.message.reply_text(text=cap, parse_mode="HTML", reply_markup=get_force_join_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "verify_join":
        if await check_user_joined(query.from_user.id, context):
            await query.answer("🦇 Welcome to the Batcave!", show_alert=True)
            try: await query.edit_message_caption(caption=get_professional_caption(query.from_user), parse_mode="HTML", reply_markup=get_main_keyboard())
            except: await query.edit_message_text(text=get_professional_caption(query.from_user), parse_mode="HTML", reply_markup=get_main_keyboard())
        else: await query.answer("❌ You must join the League first!", show_alert=True)
        return

    async def update_text(text, kb):
        if query.message.photo: await query.edit_message_caption(caption=text, parse_mode="HTML", reply_markup=kb)
        else: await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=kb)

    if data == "back_main": await update_text(get_professional_caption(query.from_user), get_main_keyboard())
    elif data == "menu_pricing": await update_text("<b>💰 𝗣𝗿𝗶𝗰𝗶𝗻𝗴 𝗨𝗽𝗱𝗱𝗮𝘁𝗶𝗻𝗴 𝗦𝗼𝗼𝗻...</b>", get_back_keyboard("back_main"))
    elif data == "menu_gates":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⚡ 𝗔𝘂𝘁𝗵", callback_data="menu_auth"), InlineKeyboardButton("🦇 𝗖𝗵𝗮𝗿𝗴𝗲", callback_data="menu_charge")], [InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸", callback_data="back_main")]])
        await update_text("<b>🦇 𝗦𝗲𝗹𝗲𝗰𝘁 𝗮 𝗚𝗮𝘁𝗲 𝗖𝗮𝘁𝗲𝗴𝗼𝗿𝘆</b>", kb)
    elif data == "menu_auth":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⚡ 𝗔𝘂𝘁𝗼𝘀𝘁𝗿𝗶𝗽𝗲", callback_data="info_auth_stripe"), InlineKeyboardButton("🦇 𝗕𝗿𝗮𝗶𝗻𝘁𝗿𝗲𝗲", callback_data="info_auth_braintree")], [InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸", callback_data="menu_gates")]])
        await update_text("<b>⚡ 𝗦𝗲𝗹𝗲𝗰𝘁 𝗔𝘂𝘁𝗵 𝗠𝗲𝘁𝗵𝗼𝗱</b>", kb)
    elif data == "info_auth_stripe": await update_text("━━━━━━━━━━━━━━━━\n<b>⚡ Gate ↬ Stripe Auth</b>\n<b>Command ↬ /au</b>\n<b>Sites ↬ 16</b>\n<b>Health ↬ 100%</b>\n━━━━━━━━━━━━━━━━", get_back_keyboard("menu_auth"))
    elif data == "info_auth_braintree": await update_text("━━━━━━━━━━━━━━━━\n<b>🦇 Gate ↬ Braintree Auth</b>\n<b>Command ↬ /b3</b>\n<b>Sites ↬ 2</b>\n<b>Health ↬ 100%</b>\n━━━━━━━━━━━━━━━━", get_back_keyboard("menu_auth"))
    elif data == "menu_charge":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⚡ 𝗦𝘁𝗿𝗶𝗽𝗲", callback_data="info_charge_stripe"), InlineKeyboardButton("💰 𝗣𝗮𝘆𝗽𝗮𝗹", callback_data="info_charge_paypal")], [InlineKeyboardButton("🛒 𝗦𝗵𝗼𝗽𝗶𝗳𝘆", callback_data="info_charge_shopify"), InlineKeyboardButton("💸 𝗣𝗮𝘆𝗨", callback_data="info_charge_payu")], [InlineKeyboardButton("🏦 𝗣𝗮𝘆𝗙𝗮𝘀𝘁", callback_data="info_charge_payfast")], [InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸", callback_data="menu_gates")]])
        await update_text("<b>🦇 𝗦𝗲𝗹𝗲𝗰𝘁 𝗖𝗵𝗮𝗿𝗴𝗲 𝗠𝗲𝘁𝗵𝗼𝗱</b>", kb)
    elif data == "info_charge_stripe": await update_text("━━━━━━━━━━━━━━━━\n<b>⚡ Gate ↬ Stripe 0.50$</b>\n<b>Command ↬ /chk</b>\n<b>Sites ↬ 4</b>\n<b>Health ↬ 100%</b>\n━━━━━━━━━━━━━━━━", get_back_keyboard("menu_charge"))
    elif data == "info_charge_paypal": await update_text("━━━━━━━━━━━━━━━━\n<b>💰 Gate ↬ Paypal 0.10$</b>\n<b>Command ↬ /pp</b>\n<b>Sites ↬ 7</b>\n<b>Health ↬ 100%</b>\n━━━━━━━━━━━━━━━━", get_back_keyboard("menu_charge"))
    elif data == "info_charge_shopify": await update_text("━━━━━━━━━━━━━━━━\n<b>🛒 Gate ↬ Shopify 1$</b>\n<b>Command ↬ /sh</b>\n<b>Sites ↬ 10</b>\n<b>Health ↬ 100%</b>\n━━━━━━━━━━━━━━━━", get_back_keyboard("menu_charge"))
    elif data == "info_charge_payu": await update_text("━━━━━━━━━━━━━━━━\n<b>💸 Gate ↬ PayU</b>\n<b>Command ↬ /pyu</b>\n<b>Sites ↬ 1</b>\n<b>Health ↬ 100%</b>\n━━━━━━━━━━━━━━━━", get_back_keyboard("menu_charge"))
    elif data == "info_charge_payfast": await update_text("━━━━━━━━━━━━━━━━\n<b>🏦 Gate ↬ PayFast 0.30$</b>\n<b>Command ↬ /pf</b>\n<b>Sites ↬ 1</b>\n<b>Health ↬ 100%</b>\n━━━━━━━━━━━━━━━━", get_back_keyboard("menu_charge"))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 RAILWAY ANTI-CONFLICT SYSTEM 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def post_init(app):
    """Kills ghost bots and webhooks to stop Railway Conflict Errors"""
    print("🦇 Cleaning Gotham webhooks...")
    await app.bot.delete_webhook(drop_pending_updates=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 MAIN EXECUTION 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    # Build app with post_init to kill ghost bots
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # Register Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(get_fb_handler())
    app.add_handler(get_chk_handler())
    app.add_handler(get_pp_handler())
    app.add_handler(get_sh_handler())
    app.add_handler(get_pyu_handler())
    for h in get_subs_handlers(): app.add_handler(h)
    app.add_handler(get_fb_callback_handler())
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🦇 Batman Bot is starting via Polling...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
