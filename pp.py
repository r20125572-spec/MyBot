import aiohttp
import asyncio
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from config import PP_API, PP_SITE, API_TIMEOUT, get_bin_info, ui_result, kb_result

GATE_NAME = "PAYPAL | 0.10$"

async def cmd_pp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.bot_data.get('pp_on', True):
        await update.message.reply_text("🦇 <b>GATE OFF</b>", parse_mode="HTML")
        return
    if not context.args:
        await update.message.reply_text("❌ <code>/pp cc|mm|yy|cvv</code>", parse_mode="HTML")
        return
    
    card = context.args[0]
    bin_num = card[:6]
    msg = await update.message.reply_text("🦇 <i>Processing...</i>", parse_mode="HTML")
    
    try:
        timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            tasks = [session.get(PP_API, params={"cc": card, "site": PP_SITE}), get_bin_info(bin_num)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        
        api_resp = results[0]
        bin_data = results[1] if not isinstance(results[1], Exception) else {"error": True}
        
        if isinstance(api_resp, Exception): raise api_resp
        
        data = await api_resp.json()
        raw = data.get("response", "ERROR")
        approved = "approved" in raw.lower()
        
        bin_txt, country, flag = "N/A", "N/A", ""
        if not bin_data.get("error"):
            s = str(bin_data.get("scheme", "N/A")).upper()
            t = str(bin_data.get("type", "N/A")).upper()
            b = bin_data.get("bank", "N/A")
            country = str(bin_data.get("country", "N/A")).upper()
            flag = bin_data.get("country_emoji", "")
            bin_txt = f"{s} - {t} - {b}"
        
        await msg.edit_text(ui_result(card, GATE_NAME, bin_txt, country, flag, raw, update.effective_user, approved), parse_mode="HTML", reply_markup=kb_result(), disable_web_page_preview=True)
        
    except aiohttp.ClientTimeout:
        await msg.edit_text("🦇 <b>TIMEOUT</b>", parse_mode="HTML")
    except Exception as e:
        await msg.edit_text(f"🦇 <b>ERROR</b> ➤ <code>{str(e)[:100]}</code>", parse_mode="HTML")

def get_pp_handler():
    return CommandHandler("pp", cmd_pp)
