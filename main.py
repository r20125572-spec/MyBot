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
# 🦇 BATMAN CARD CHECKER CONFIGURATION 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BOT_TOKEN = "8813507423:AAFWkdkk8Je4kB93AB5fu6qQ0-8eo-jlRKE"
VERSION = "V4.1"
DEV_USERNAME = "Batmancardchk"
DEV_LINK = "https://t.me/Batmancardchk"

CHANNEL_1_USERNAME = "@Batcardchk" 
GROUP_1_USERNAME = "@batcardchkGroup" 
CHANNEL_1_LINK = "https://t.me/Batcardchk" 
GROUP_1_LINK = "https://t.me/batcardchkGroup" 
SUPPORT_LINK = "https://t.me/failurefr_07"

BOT_PHOTO_URL = "https://z-cdn-media.chatglm.cn/files/cd1a58d5-1a85-4246-8dac-dae333b02023.jpg"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 FORCE JOIN SYSTEM 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def check_user_joined(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        m1 = await context.bot.get_chat_member(chat_id=CHANNEL_1_USERNAME, user_id=user_id)
        if m1.status in ['left', 'kicked']:
            return False
        m2 = await context.bot.get_chat_member(chat_id=GROUP_1_USERNAME, user_id=user_id)
        if m2.status in ['left', 'kicked']:
            return False
    except Exception:
        return False
    return True

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 PREMIUM BATMAN UI HELPERS 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_premium_caption(user):
    now = datetime.now().strftime("%Y - %m - %d")
    username = user.username if user.username else "None"
    
    return (
        f"╔══════════════════════════════╗\n"
        f"║     🦇 𝐁𝐀𝐓𝐌𝐀𝐍 𝐂𝐇𝐊 🦇      ║\n"
        f"╚══════════════════════════════╝\n"
        f"\n"
        f"┌──────────────────────────┐\n"
        f"│ 𝗨𝗦𝗘𝗥𝗡𝗔𝗠𝗘  ➤ {username}\n"
        f"├──────────────────────────┤\n"
        f"│ 𝗨𝗦𝗘𝗥 𝗜𝗗    ➤ <code>{user.id}</code>\n"
        f"├──────────────────────────┤\n"
        f"│ 𝗔𝗖𝗖𝗘𝗦𝗦    ➤ ⚡ 𝗘𝗟𝗜𝗧𝗘\n"
        f"├──────────────────────────┤\n"
        f"│ 𝗖𝗥𝗘𝗗𝗜𝗧𝗦   ➤ ∞\n"
        f"├──────────────────────────┤\n"
        f"│ 𝗝𝗢𝗜𝗡𝗘𝗗     ➤ {now}\n"
        f"├──────────────────────────┤\n"
        f"│ 𝗗𝗘𝗩       ➤ <a href='{DEV_LINK}'>Batman</a> 🦇\n"
        f"├──────────────────────────┤\n"
        f"│ 𝗩𝗘𝗥𝗦𝗜𝗢𝗡   ➤ {VERSION}\n"
        f"└──────────────────────────┘"
    )

def get_main_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🗡️ 𝗖𝗛𝗘𝗖𝗞𝗘𝗥", callback_data="menu_gates"),
            InlineKeyboardButton("💰 𝗕𝗨𝗬 𝗡𝗢𝗪", callback_data="menu_pricing")
        ],
        [
            InlineKeyboardButton("📢 𝗨𝗣𝗗𝗔𝗧𝗘𝗦", url=CHANNEL_1_LINK),
            InlineKeyboardButton("👥 𝗚𝗥𝗢𝗨𝗣", url=GROUP_1_LINK)
        ],
        [
            InlineKeyboardButton("🛡️ 𝗦𝗨𝗣𝗣𝗢𝗥𝗧", url=SUPPORT_LINK)
        ]
    ])

def get_back_keyboard(target):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ 𝗕𝗔𝗖𝗞", callback_data=target)]
    ])

def get_force_join_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 𝗝𝗢𝗜𝗡 𝗖𝗛𝗔𝗡𝗡𝗘𝗟", url=CHANNEL_1_LINK)],
        [InlineKeyboardButton("👥 𝗝𝗢𝗜𝗡 𝗚𝗥𝗢𝗨𝗣", url=GROUP_1_LINK)],
        [InlineKeyboardButton("✅ 𝗩𝗘𝗥𝗜𝗙𝗬 𝗔𝗖𝗖𝗘𝗦𝗦", callback_data="verify_join")]
    ])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 HANDLERS 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if await check_user_joined(user.id, context):
        await update.message.reply_text(
            text=get_premium_caption(user), 
            parse_mode="HTML", 
            reply_markup=get_main_keyboard(),
            disable_web_page_preview=True
        )
    else:
        cap = (
            "🦇 <b>BATMAN CARD CHECKER</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "🔒 Access Required\n\n"
            "1️⃣ Join <b>CHANNEL</b>\n"
            "2️⃣ Join <b>GROUP</b>\n"
            "3️⃣ Click <b>✅ VERIFY</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        )
        try:
            await update.message.reply_photo(
                photo=BOT_PHOTO_URL, 
                caption=cap, 
                parse_mode="HTML", 
                reply_markup=get_force_join_keyboard()
            )
        except Exception:
            await update.message.reply_text(
                text=cap, 
                parse_mode="HTML", 
                reply_markup=get_force_join_keyboard()
            )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "verify_join":
        if await check_user_joined(query.from_user.id, context):
            await query.answer("🦇 Access Granted!", show_alert=True)
            try:
                await query.edit_message_caption(
                    caption=get_premium_caption(query.from_user), 
                    parse_mode="HTML", 
                    reply_markup=get_main_keyboard(),
                    disable_web_page_preview=True
                )
            except Exception:
                await query.edit_message_text(
                    text=get_premium_caption(query.from_user), 
                    parse_mode="HTML", 
                    reply_markup=get_main_keyboard(),
                    disable_web_page_preview=True
                )
        else:
            await query.answer("❌ Join channels first!", show_alert=True)
        return

    async def update_text(text, kb):
        try:
            if query.message.photo:
                await query.edit_message_caption(
                    caption=text, 
                    parse_mode="HTML", 
                    reply_markup=kb,
                    disable_web_page_preview=True
                )
            else:
                await query.edit_message_text(
                    text=text, 
                    parse_mode="HTML", 
                    reply_markup=kb,
                    disable_web_page_preview=True
                )
        except Exception as e:
            logging.error(f"UI Error: {e}")

    if data == "back_main":
        await update_text(get_premium_caption(query.from_user), get_main_keyboard())
        
    elif data == "menu_pricing":
        text = (
            "╔══════════════════════════════╗\n"
            f"║     🦇 𝐏𝐑𝐈𝐂𝐈𝐍𝐆 🦇          ║\n"
            "╚══════════════════════════════╝\n"
            "\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "💰 <b>PLANS COMING SOON</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "\n"
            "⚡ Trial - <b>FREE</b>\n"
            "💎 Elite - <b>$5</b>\n"
            "🔥 VIP - <b>$10</b>\n"
            "\n"
            f"Contact <a href='{DEV_LINK}'>Batman</a> to buy"
        )
        await update_text(text, get_back_keyboard("back_main"))
        
    elif data == "menu_gates":
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⚡ 𝗔𝗨𝗧𝗛", callback_data="menu_auth"), 
                InlineKeyboardButton("💀 𝗖𝗛𝗔𝗥𝗚𝗘", callback_data="menu_charge")
            ], 
            [InlineKeyboardButton("◀️ 𝗕𝗔𝗖𝗞", callback_data="back_main")]
        ])
        text = (
            "╔══════════════════════════════╗\n"
            "║     🦇 𝗦𝗘𝗟𝗘𝗖𝗧 𝗚𝗔𝗧𝗘 🦇      ║\n"
            "╚══════════════════════════════╝"
        )
        await update_text(text, kb)
        
    elif data == "menu_auth":
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⚡ Stripe", callback_data="info_auth_stripe"), 
                InlineKeyboardButton("🦇 Braintree", callback_data="info_auth_braintree")
            ], 
            [InlineKeyboardButton("◀️ 𝗕𝗔𝗖𝗞", callback_data="menu_gates")]
        ])
        text = (
            "╔══════════════════════════════╗\n"
            "║     ⚡ 𝗔𝗨𝗧𝗛 𝗚𝗔𝗧𝗘𝗦 ⚡       ║\n"
            "╚══════════════════════════════╝"
        )
        await update_text(text, kb)
        
    elif data == "info_auth_stripe":
        text = (
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚡ <b>GATE</b> ➤ Stripe Auth\n"
            "📋 <b>CMD</b> ➤ /au\n"
            "🌐 <b>SITES</b> ➤ 16\n"
            "💚 <b>HEALTH</b> ➤ 100%\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        )
        await update_text(text, get_back_keyboard("menu_auth"))
        
    elif data == "info_auth_braintree":
        text = (
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "🦇 <b>GATE</b> ➤ Braintree Auth\n"
            "📋 <b>CMD</b> ➤ /b3\n"
            "🌐 <b>SITES</b> ➤ 2\n"
            "💚 <b>HEALTH</b> ➤ 100%\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        )
        await update_text(text, get_back_keyboard("menu_auth"))
        
    elif data == "menu_charge":
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⚡ Stripe", callback_data="info_charge_stripe"), 
                InlineKeyboardButton("💰 PayPal", callback_data="info_charge_paypal")
            ],
            [
                InlineKeyboardButton("🛒 Shopify", callback_data="info_charge_shopify"), 
                InlineKeyboardButton("💸 PayU", callback_data="info_charge_payu")
            ],
            [InlineKeyboardButton("🏦 PayFast", callback_data="info_charge_payfast")],
            [InlineKeyboardButton("◀️ 𝗕𝗔𝗖𝗞", callback_data="menu_gates")]
        ])
        text = (
            "╔══════════════════════════════╗\n"
            "║     💀 𝗖𝗛𝗔𝗥𝗚𝗘 𝗚𝗔𝗧𝗘𝗦 💀     ║\n"
            "╚══════════════════════════════╝"
        )
        await update_text(text, kb)
        
    elif data == "info_charge_stripe":
        text = (
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚡ <b>GATE</b> ➤ Stripe\n"
            "💵 <b>PRICE</b> ➤ $0.50\n"
            "📋 <b>CMD</b> ➤ /chk\n"
            "🌐 <b>SITES</b> ➤ 4\n"
            "💚 <b>HEALTH</b> ➤ 100%\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        )
        await update_text(text, get_back_keyboard("menu_charge"))
        
    elif data == "info_charge_paypal":
        text = (
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "💰 <b>GATE</b> ➤ PayPal\n"
            "💵 <b>PRICE</b> ➤ $0.10\n"
            "📋 <b>CMD</b> ➤ /pp\n"
            "🌐 <b>SITES</b> ➤ 7\n"
            "💚 <b>HEALTH</b> ➤ 100%\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        )
        await update_text(text, get_back_keyboard("menu_charge"))
        
    elif data == "info_charge_shopify":
        text = (
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "🛒 <b>GATE</b> ➤ Shopify\n"
            "💵 <b>PRICE</b> ➤ $1.00\n"
            "📋 <b>CMD</b> ➤ /sh\n"
            "🌐 <b>SITES</b> ➤ 10\n"
            "💚 <b>HEALTH</b> ➤ 100%\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        )
        await update_text(text, get_back_keyboard("menu_charge"))
        
    elif data == "info_charge_payu":
        text = (
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "💸 <b>GATE</b> ➤ PayU\n"
            "💵 <b>PRICE</b> ➤ $0.30\n"
            "📋 <b>CMD</b> ➤ /pyu\n"
            "🌐 <b>SITES</b> ➤ 1\n"
            "💚 <b>HEALTH</b> ➤ 100%\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        )
        await update_text(text, get_back_keyboard("menu_charge"))
        
    elif data == "info_charge_payfast":
        text = (
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "🏦 <b>GATE</b> ➤ PayFast\n"
            "💵 <b>PRICE</b> ➤ $0.30\n"
            "📋 <b>CMD</b> ➤ /pf\n"
            "🌐 <b>SITES</b> ➤ 1\n"
            "💚 <b>HEALTH</b> ➤ 100%\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        )
        await update_text(text, get_back_keyboard("menu_charge"))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 ANTI-CONFLICT SYSTEM 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def post_init(app):
    print("🦇 Batman Card Checker Initializing...")
    await app.bot.delete_webhook(drop_pending_updates=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 MAIN EXECUTION 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(get_fb_handler())
    app.add_handler(get_chk_handler())
    app.add_handler(get_pp_handler())
    app.add_handler(get_sh_handler())
    app.add_handler(get_pyu_handler())
    for h in get_subs_handlers():
        app.add_handler(h)
    app.add_handler(get_fb_callback_handler())
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🦇 Batman Card Checker Online!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
