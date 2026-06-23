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

BOT_TOKEN = "8813507423:AAFWkdkk8Je4kB93AB5fu6qQ0-8eo-jlRKE"
CHANNEL_1_USERNAME = "@Batcardchk" 
GROUP_1_USERNAME = "@batcardchkGroup" 
CHANNEL_1_LINK = "https://t.me/Batcardchk" 
GROUP_1_LINK = "https://t.me/batcardchkGroup" 
BOT_PHOTO_URL = "https://z-cdn-media.chatglm.cn/files/cd1a58d5-1a85-4246-8dac-dae333b02023.jpg"

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

async def check_user_joined(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        m1 = await context.bot.get_chat_member(chat_id=CHANNEL_1_USERNAME, user_id=user_id)
        if m1.status in ['left', 'kicked']: return False
        m2 = await context.bot.get_chat_member(chat_id=GROUP_1_USERNAME, user_id=user_id)
        if m2.status in ['left', 'kicked']: return False
    except Exception: return False
    return True

def get_professional_caption(user):
    now = datetime.now().strftime("%d/%m/%y %H:%M:%S")
    username = f"@{user.username}" if user.username else "None"
    return f"<pre>⋪ 𝑺𝒕𝒂𝒕𝒖𝒔: 𝐀𝐜𝐭𝐢𝐯𝐞 ✅</pre>\n⋪ 𝐈𝐃 ↬ {user.id}\n⋪ 𝐔𝒔𝒆𝒓 ↬ {username}\n⊲ 𝐌𝐚𝐧𝐞 ↬ Batman\n⊲ 𝐂𝐫𝐞𝐝𝐢𝐭𝐬 ↬ Infinite😎\n⊲ 𝐉𝐨𝐧𝐞𝐝 ↬ {now}\n⌬ 𝐃𝐞𝐯 ↬ Batman"

def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("𝗚𝗮𝘁𝗲𝘀", callback_data="menu_gates"), InlineKeyboardButton("𝗣𝗿𝗶𝗰𝗶𝗻𝗴", callback_data="menu_pricing")],
        [InlineKeyboardButton("𝗨𝗽𝗱𝗮𝘁𝗲𝘀", url=CHANNEL_1_LINK), InlineKeyboardButton("𝗚𝗿𝗼𝘂𝗽", url=GROUP_1_LINK)],
        [InlineKeyboardButton("𝗦𝘂𝗽𝗽𝗼𝗿𝘁", url="https://t.me/failurefr_07")]
    ])

def get_back_keyboard(target):
    return InlineKeyboardMarkup([[InlineKeyboardButton("𝗕𝗮𝗰𝗸", callback_data=target)]])

def get_force_join_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 JOIN CHANNEL", url=CHANNEL_1_LINK)],
        [InlineKeyboardButton("👥 JOIN GROUP", url=GROUP_1_LINK)],
        [InlineKeyboardButton("✅ Verify Joined", callback_data="verify_join")]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if await check_user_joined(user.id, context):
        await update.message.reply_text(text=get_professional_caption(user), parse_mode="HTML", reply_markup=get_main_keyboard())
    else:
        cap = "🚫 <b>Access Denied!</b>\n\n1️⃣ Click <b>JOIN CHANNEL</b>\n2️⃣ Click <b>JOIN GROUP</b>\n3️⃣ Click <b>✅ Verify Joined</b>"
        try: await update.message.reply_photo(photo=BOT_PHOTO_URL, caption=cap, parse_mode="HTML", reply_markup=get_force_join_keyboard())
        except: await update.message.reply_text(text=cap, parse_mode="HTML", reply_markup=get_force_join_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "verify_join":
        if await check_user_joined(query.from_user.id, context):
            await query.answer("✅ Verified!", show_alert=True)
            try: await query.edit_message_caption(caption=get_professional_caption(query.from_user), parse_mode="HTML", reply_markup=get_main_keyboard())
            except: await query.edit_message_text(text=get_professional_caption(query.from_user), parse_mode="HTML", reply_markup=get_main_keyboard())
        else: await query.answer("❌ Join Channel & Group first!", show_alert=True)
        return

    async def update_text(text, kb):
        if query.message.photo: await query.edit_message_caption(caption=text, parse_mode="HTML", reply_markup=kb)
        else: await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=kb)

    if data == "back_main": await update_text(get_professional_caption(query.from_user), get_main_keyboard())
    elif data == "menu_pricing": await update_text("<b><i>UPDATING SOON</i></b>", get_back_keyboard("back_main"))
    elif data == "menu_gates": await update_text("<b><i>Select a Gate Category</i></b>", InlineKeyboardMarkup([[InlineKeyboardButton("𝗔𝘂𝘁𝗵", callback_data="menu_auth"), InlineKeyboardButton("𝗖𝗵𝗮𝗿𝗴𝗲", callback_data="menu_charge")], [InlineKeyboardButton("𝗕𝗮𝗰𝗸", callback_data="back_main")]]))
    elif data == "menu_auth": await update_text("<b><i>Select Auth Method</i></b>", InlineKeyboardMarkup([[InlineKeyboardButton("𝗔𝘂𝘁𝗼𝘀𝘁𝗿𝗶𝗽𝗲", callback_data="info_auth_stripe"), InlineKeyboardButton("𝗕𝗿𝗮𝗶𝗻𝘁𝗿𝗲𝗲", callback_data="info_auth_braintree")], [InlineKeyboardButton("𝗕𝗮𝗰𝗸", callback_data="menu_gates")]]))
    elif data == "info_auth_stripe": await update_text("━━━━━━━━━━━━━━━━\n<b><i>Gate ↬ Stripe Auth</i></b>\n<b><i>Command ↬ /au</i></b>\n━━━━━━━━━━━━━━━━", get_back_keyboard("menu_auth"))
    elif data == "info_auth_braintree": await update_text("━━━━━━━━━━━━━━━━\n<b><i>Gate ↬ Braintree Auth</i></b>\n<b><i>Command ↬ /b3</i></b>\n━━━━━━━━━━━━━━━━", get_back_keyboard("menu_auth"))
    elif data == "menu_charge": await update_text("<b><i>Select Charge Method</i></b>", InlineKeyboardMarkup([[InlineKeyboardButton("𝗦𝘁𝗿𝗶𝗽𝗲", callback_data="info_charge_stripe"), InlineKeyboardButton("𝗣𝗮𝘆𝗽𝗮𝗹", callback_data="info_charge_paypal")], [InlineKeyboardButton("𝗦𝗵𝗼𝗽𝗶𝗳𝘆", callback_data="info_charge_shopify"), InlineKeyboardButton("𝗣𝗮𝘆𝗨", callback_data="info_charge_payu")], [InlineKeyboardButton("𝗣𝗮𝘆𝗙𝗮𝘀𝘁", callback_data="info_charge_payfast")], [InlineKeyboardButton("𝗕𝗮𝗰𝗸", callback_data="menu_gates")]]))
    elif data == "info_charge_stripe": await update_text("━━━━━━━━━━━━━━━━\n<b><i>Gate ↬ Stripe 0.50$</i></b>\n<b><i>Command ↬ /chk</i></b>\n━━━━━━━━━━━━━━━━", get_back_keyboard("menu_charge"))
    elif data == "info_charge_paypal": await update_text("━━━━━━━━━━━━━━━━\n<b><i>Gate ↬ Paypal 0.10$</i></b>\n<b><i>Command ↬ /pp</i></b>\n━━━━━━━━━━━━━━━━", get_back_keyboard("menu_charge"))
    elif data == "info_charge_shopify": await update_text("━━━━━━━━━━━━━━━━\n<b><i>Gate ↬ Shopify 1$</i></b>\n<b><i>Command ↬ /sh</i></b>\n━━━━━━━━━━━━━━━━", get_back_keyboard("menu_charge"))
    elif data == "info_charge_payu": await update_text("━━━━━━━━━━━━━━━━\n<b><i>Gate ↬ PayU</i></b>\n<b><i>Command ↬ /pyu</i></b>\n━━━━━━━━━━━━━━━━", get_back_keyboard("menu_charge"))
    elif data == "info_charge_payfast": await update_text("━━━━━━━━━━━━━━━━\n<b><i>Gate ↬ PayFast 0.30$</i></b>\n<b><i>Command ↬ /pf</i></b>\n━━━━━━━━━━━━━━━━", get_back_keyboard("menu_charge"))

async def post_init(app):
    print("🧹 Cleaning webhooks...")
    await app.bot.delete_webhook(drop_pending_updates=True)

def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(get_fb_handler())
    app.add_handler(get_chk_handler())
    app.add_handler(get_pp_handler())
    app.add_handler(get_sh_handler())
    app.add_handler(get_pyu_handler())
    for h in get_subs_handlers(): app.add_handler(h)
    app.add_handler(get_fb_callback_handler())
    app.add_handler(CallbackQueryHandler(button_handler))
    print("🚀 Bot starting...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__": main()
