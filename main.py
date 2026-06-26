import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from datetime import datetime
from chk import get_chk_handler  # CONNECTS CHK.PY
from pp import get_pp_handler    # CONNECTS PP.PY
from sh import get_sh_handler    # CONNECTS SH.PY
from pyu import get_pyu_handler  # CONNECTS PYU.PY

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BOT_TOKEN = "8813507423:AAFWkdkk8Je4kB93AB5fu6qQ0-8eo-jlRKE"

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_professional_caption(user):
    now = datetime.now().strftime("%d/%m/%y %H:%M:%S")
    username = f"@{user.username}" if user.username else "None"
    status_part = "<pre>⋪ 𝑺𝒕𝒂𝒕𝒖𝒔: 𝐀𝐜𝐭𝐢𝐯𝐞 ✅</pre>"
    details_part = (
        f"\n⋪ 𝐈𝐃 ↬ {user.id}\n"
        f"⋪ 𝐔𝒔𝒆𝒓 ↬ {username}\n"
        f"⊲ 𝐌𝐚𝐧𝐞 ↬ Batman\n"
        f"⊲ 𝐂𝐫𝐞𝐝𝐢𝐭𝐬 ↬ Infinite😎\n"
        f"⊲ 𝐉𝐨𝐧𝐞𝐝 ↬ {now}\n"
        f"⌬ 𝐃𝐞𝐯 ↬ Batman"
    )
    return status_part + details_part

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# KEYBOARDS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_main_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("𝗚𝗮𝘁𝗲𝘀", callback_data="menu_gates"),
            InlineKeyboardButton("𝗣𝗿𝗶𝗰𝗶𝗻𝗴", callback_data="menu_pricing")
        ],
        [
            InlineKeyboardButton("𝗨𝗽𝗱𝗮𝘁𝗲𝘀", url="https://t.me/+E6zoRhIFhtNmM2E5"),
            InlineKeyboardButton("𝗚𝗿𝗼𝘂𝗽", url="https://t.me/+zQIEseDYxtdhZTQ1")
        ],
        [InlineKeyboardButton("𝗦𝘂𝗽𝗽𝗼𝗿𝘁", url="https://t.me/failurefr_07")]
    ])

def get_back_keyboard(target):
    return InlineKeyboardMarkup([[InlineKeyboardButton("𝗕𝗮𝗰𝗸", callback_data=target)]])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HANDLERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    caption = get_professional_caption(user)
    await update.message.reply_text(text=caption, parse_mode="HTML", reply_markup=get_main_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    async def update_text(text, keyboard):
        await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=keyboard)

    if data == "back_main":
        caption = get_professional_caption(query.from_user)
        await update_text(caption, get_main_keyboard())
    elif data == "menu_pricing":
        await update_text("<b><i>UPDATING SOON</i></b>", get_back_keyboard("back_main"))
    elif data == "menu_gates":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("𝗔𝘂𝘁𝗵", callback_data="menu_auth"), InlineKeyboardButton("𝗖𝗵𝗮𝗿𝗴𝗲", callback_data="menu_charge")],
            [InlineKeyboardButton("𝗕𝗮𝗰𝗸", callback_data="back_main")]
        ])
        await update_text("<b><i>Select a Gate Category</i></b>", keyboard)
    elif data == "menu_auth":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("𝗔𝘂𝘁𝗼𝘀𝘁𝗿𝗶𝗽𝗲", callback_data="info_auth_stripe"), InlineKeyboardButton("𝗕𝗿𝗮𝗶𝗻𝘁𝗿𝗲𝗲", callback_data="info_auth_braintree")],
            [InlineKeyboardButton("𝗕𝗮𝗰𝗸", callback_data="menu_gates")]
        ])
        await update_text("<b><i>Select Auth Method</i></b>", keyboard)
    elif data == "info_auth_stripe":
        text = "━━━━━━━━━━━━━━━━\n<b><i>Gate ↬ Stripe Auth</i></b>\n<b><i>Command ↬ /au</i></b>\n<b><i>Sites loaded ↬ 16</i></b>\n<b><i>Gate Health ↬ 100%</i></b>\n━━━━━━━━━━━━━━━━"
        await update_text(text, get_back_keyboard("menu_auth"))
    elif data == "info_auth_braintree":
        text = "━━━━━━━━━━━━━━━━\n<b><i>Gate ↬ Braintree Auth</i></b>\n<b><i>Command ↬ /b3</i></b>\n<b><i>Sites loaded ↬ 2</i></b>\n<b><i>Gate Health ↬ 100%</i></b>\n━━━━━━━━━━━━━━━━"
        await update_text(text, get_back_keyboard("menu_auth"))
        
    elif data == "menu_charge":
        # ADDED PAYU BUTTON HERE
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("𝗦𝘁𝗿𝗶𝗽𝗲", callback_data="info_charge_stripe"), InlineKeyboardButton("𝗣𝗮𝘆𝗽𝗮𝗹", callback_data="info_charge_paypal")],
            [InlineKeyboardButton("𝗦𝗵𝗼𝗽𝗶𝗳𝘆", callback_data="info_charge_shopify"), InlineKeyboardButton("𝗣𝗮𝘆𝗨", callback_data="info_charge_payu")],
            [InlineKeyboardButton("𝗣𝗮𝘆𝗙𝗮𝘀𝘁", callback_data="info_charge_payfast")],
            [InlineKeyboardButton("𝗕𝗮𝗰𝗸", callback_data="menu_gates")]
        ])
        await update_text("<b><i>Select Charge Method</i></b>", keyboard)
        
    elif data == "info_charge_stripe":
        text = "━━━━━━━━━━━━━━━━\n<b><i>Gate ↬ Stripe 0.50$</i></b>\n<b><i>Command ↬ /chk</i></b>\n<b><i>Sites loaded ↬ 4</i></b>\n<b><i>Gate Health ↬ 100%</i></b>\n━━━━━━━━━━━━━━━━"
        await update_text(text, get_back_keyboard("menu_charge"))
    elif data == "info_charge_paypal":
        text = "━━━━━━━━━━━━━━━━\n<b><i>Gate ↬ Paypal 0.10$</i></b>\n<b><i>Command ↬ /pp</i></b>\n<b><i>Sites loaded ↬ 7</i></b>\n<b><i>Gate Health ↬ 100%</i></b>\n━━━━━━━━━━━━━━━━"
        await update_text(text, get_back_keyboard("menu_charge"))
    elif data == "info_charge_shopify":
        text = "━━━━━━━━━━━━━━━━\n<b><i>Gate ↬ Shopify 1$</i></b>\n<b><i>Command ↬ /sh</i></b>\n<b><i>Sites loaded ↬ 10</i></b>\n<b><i>Gate Health ↬ 100%</i></b>\n━━━━━━━━━━━━━━━━"
        await update_text(text, get_back_keyboard("menu_charge"))
        
    # ADDED PAYU INFO PAGE HERE
    elif data == "info_charge_payu":
        text = "━━━━━━━━━━━━━━━━\n<b><i>Gate ↬ PayU</i></b>\n<b><i>Command ↬ /pyu</i></b>\n<b><i>Sites loaded ↬ 1</i></b>\n<b><i>Gate Health ↬ 100%</i></b>\n━━━━━━━━━━━━━━━━"
        await update_text(text, get_back_keyboard("menu_charge"))
        
    elif data == "info_charge_payfast":
        text = "━━━━━━━━━━━━━━━━\n<b><i>Gate ↬ PayFast 0.30$</i></b>\n<b><i>Command ↬ /pf</i></b>\n<b><i>Sites loaded ↬ 1</i></b>\n<b><i>Gate Health ↬ 100%</i></b>\n━━━━━━━━━━━━━━━━"
        await update_text(text, get_back_keyboard("menu_charge"))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN EXECUTION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(get_chk_handler())  # LOADS /chk COMMAND
    app.add_handler(get_pp_handler())   # LOADS /pp COMMAND
    app.add_handler(get_sh_handler())   # LOADS /sh COMMAND
    app.add_handler(get_pyu_handler())  # LOADS /pyu COMMAND
    print("🚀 Bot is starting via Polling...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
