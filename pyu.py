import aiohttp
import asyncio
import time
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from config import PYU_API, PYU_SITE, API_TIMEOUT, get_bin_info, kb_result

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 PAYU CONFIGURATION & HELPERS 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GATE_NAME = "PᴀʏU | 1 ᴜꜱᴅ"

def get_styled_plan(raw_plan: str) -> str:
    plan_upper = raw_plan.upper()
    if plan_upper == "CORE": return "✨ Cᴏʀᴇ ✨"
    elif plan_upper == "ELITE": return "⭐ Eʟɪᴛᴇ ⭐"
    elif plan_upper == "ROOT": return "👑 Rᴏᴏᴛ 👑"
    else: return "Tʀɪᴀʟ"

def deduct_credit(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    # Built-in credit deduction so it doesn't crash looking for plans.py
    uid_str = str(user_id)
    ud = context.bot_data.get('user_data', {}).get(uid_str, {})
    
    # Premium users bypass credit check
    raw_plan = ud.get('plan', 'TRIAL').upper()
    if raw_plan != 'TRIAL' and ud.get('expires', 0) > time.time():
        return True
        
    # Trial users use credits
    credits = ud.get('credits', 150)
    if credits > 0:
        if 'user_data' not in context.bot_data:
            context.bot_data['user_data'] = {}
        if uid_str not in context.bot_data['user_data']:
            context.bot_data['user_data'][uid_str] = {"credits": 150}
        context.bot_data['user_data'][uid_str]['credits'] = credits - 1
        return True
        
    return False

async def cmd_pyu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.bot_data.get('pyu_on', True):
        await update.message.reply_text("⚠️ Gᴀᴛᴇ ➤ OFF", parse_mode="HTML")
        return
    
    card = None
    if context.args: 
        card = context.args[0]
    elif update.message.reply_to_message and update.message.reply_to_message.text: 
        card = update.message.reply_to_message.text.strip()
        
    if not card:
        await update.message.reply_text(
            "⚠️ Uꜱᴀɢᴇ: Rᴇᴍʟʏ ᴛᴏ ᴀ ᴍᴇꜱꜱᴀɢᴇ ᴡɪᴛʜ ᴄᴀʀᴅꜱ ᴏʀ ꜱᴇɴᴅ\n/pyu cc|mm|yy|cvv", 
            parse_mode="HTML"
        )
        return
    
    if not deduct_credit(update.effective_user.id, context):
        await update.message.reply_text("Buy the PLANS and Start the checking you trils cradits are empty.", parse_mode="HTML")
        return
    
    bin_num = card[:6]
    msg = await update.message.reply_text("⏳ Pʀᴏᴄᴇꜱꜱɪɴɢ...", parse_mode="HTML")
    start_time = time.time()
    
    try:
        timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Fast parallel execution of API and BIN lookup
            tasks = [
                session.get(PYU_API, params={"cc": card, "site": PYU_SITE}), 
                get_bin_info(bin_num)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        
        api_resp = results[0]
        bin_data = results[1] if not isinstance(results[1], Exception) else {"error": True}
        
        if isinstance(api_resp, Exception): raise api_resp
        
        data = await api_resp.json()
        
        # Extract exact new JSON response fields ("value" is the main response message)
        raw_response = data.get("value", "")
        if not raw_response:
            raw_response = data.get("message", "")
        if not raw_response:
            raw_response = data.get("category", "ERROR")
            
        # Clean URLs from raw response for safety
        raw_response = str(raw_response).strip()
        
        # Status logic: Approved if word "approved" or "captured" is found, else Declined
        is_approved = any(word in raw_response.lower() for word in ["approved", "captured", "success"])
        
        if is_approved:
            status_ui = "APPROVED ✅"
        else:
            status_ui = "Dᴇᴄʟɪɴᴇᴅ ❌"
            
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
        
        time_taken = f"{time.time() - start_time:.2f}"
        
        # Exact Requested Premium UI Design
        text = (
            f"[ 𖥷iТ ] ➺ {status_ui}\n"
            f"🔍 ➺ {card}\n"
            f"Gᴀᴛᴇ ➺ {GATE_NAME} 💳 🟢\n"
            f"Rᴀᴡ ➺ {raw_response}\n"
            f"Iɴꜰᴏ ➺ {bin_txt}\n"
            f"Uꜱᴇʀ ➺ {username} 👑 ({plan_ui})\n"
            f"Pʀᴏ ➺ Batman ⚡\n"
            f"Tɪᴍᴇ ➺ {time_taken}s"
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

def get_pyu_handler():
    return CommandHandler("pyu", cmd_pyu)
