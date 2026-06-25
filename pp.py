import aiohttp
import asyncio
import time
import re
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from config import API_TIMEOUT, get_bin_info, kb_result
from plans import deduct_credit

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 NEW PAYPAL API CONFIGURATION 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PP_NEW_API = "https://paypal0-1.onrender.com/pp1/cc={card}"
GATE_NAME = "PAYPAL | 0.10 ᴜꜱᴅ"

def get_styled_plan(raw_plan: str) -> str:
    plan_upper = raw_plan.upper()
    if plan_upper == "CORE": return "✨ Cᴏʀᴇ ✨"
    elif plan_upper == "ELITE": return "⭐ Eʟɪᴛᴇ ⭐"
    elif plan_upper == "ROOT": return "👑 Rᴏᴏᴛ 👑"
    else: return "Tʀɪᴀʟ"

async def cmd_pp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.bot_data.get('pp_on', True):
        await update.message.reply_text("⚠️ Gᴀᴛᴇ ➤ OFF", parse_mode="HTML")
        return
    
    card = None
    if context.args: 
        card = context.args[0]
    elif update.message.reply_to_message and update.message.reply_to_message.text: 
        card = update.message.reply_to_message.text.strip()
        
    if not card:
        # Exact requested warning text without "❌ Usage" or "Example"
        await update.message.reply_text(
            "⚠️ Uꜱᴀɢᴇ: Rᴇᴍʟʏ ᴛᴏ ᴀ ᴍᴇꜱꜱᴀɢᴇ ᴡɪᴛʜ ᴄᴀʀᴅꜱ ᴏʀ ꜱᴇɴᴅ\n/pp email|pass", 
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
        timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Format new API URL
            api_url = PP_NEW_API.format(card=card)
            
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
        
        # Extract exact new JSON response fields
        status = data.get("status", "declined")
        code = data.get("code", "")
        message = data.get("message", "ERROR")
        
        # Determine UI status
        if str(status).lower() == "approved":
            status_ui = "APPROVED ✅"
        else:
            status_ui = "Dᴇᴄʟɪɴᴇᴅ ❌"
            
        # Clean raw response
        raw = message or code or "NO RESPONSE"
        raw = re.sub(r'https?://\S+', '', raw).strip()
        
        # Get BIN Info
        bin_txt, country, flag = "N/A", "N/A", ""
        if not bin_data.get("error"):
            s = str(bin_data.get("scheme", "N/A")).upper()
            t = str(bin_data.get("type", "N/A")).upper()
            b = bin_data.get("bank", "N/A")
            country = str(bin_data.get("country", "N/A")).upper()
            flag = bin_data.get("country_emoji", "")
            bin_txt = f"{s} - {b} - {country}"
            
        # Get User's Current Plan (Trial/Elite/Root)
        ud = context.bot_data.get('user_data', {}).get(str(update.effective_user.id), {})
        raw_plan = ud.get('plan', 'TRIAL').upper()
        
        # Check if plan expired
        if raw_plan != 'TRIAL' and ud.get('expires', 0) <= time.time():
            raw_plan = 'TRIAL'
            
        plan_ui = get_styled_plan(raw_plan)
        username = update.effective_user.first_name or "User"
        
        time_taken = f"{time.time() - start_time:.2f}"
        
        # Exact Requested Premium UI Design
        text = (
            f"[ 𖥷iТ ] ➺ {status_ui}\n"
            f"🔍 ➺ \n"
            f"Gᴀᴛᴇ ➺ Pᴀʏᴘᴀʟ 0.10 ᴜꜱᴅ 🛒 🟢\n"
            f"Rᴀᴡ ➺ {raw}\n"
            f"Iɴꜰᴏ ➺ {bin_txt} {flag} {country}\n"
            f"Uꜱᴇʀ ➺ {username} 👑 ({plan_ui})\n"
            f"Pʀᴏ ➺ Batman ⚡"
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

def get_pp_handler():
    return CommandHandler("pp", cmd_pp)
