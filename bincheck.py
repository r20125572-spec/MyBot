import urllib.request
import urllib.error
import json
import asyncio
import logging
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

logger = logging.getLogger(__name__)

async def fetch_url(url: str, timeout: int = 15) -> tuple:
    try:
        req = urllib.request.Request(url, headers={"Accept-Version": "3", "User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        loop = asyncio.get_running_loop()
        def do_request():
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.status, json.loads(response.read().decode('utf-8'))
        return await loop.run_in_executor(None, do_request)
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception:
        return 0, {}

async def lookup_bin(bin_number: str) -> dict:
    try:
        bin_clean = ''.join(filter(str.isdigit, str(bin_number)))[:8]
        if len(bin_clean) < 6:
            return {"success": False, "error": "Invalid BIN! Must be at least 6 digits."}
        
        status_code, data = await fetch_url(f"https://lookup.binlist.net/{bin_clean[:6]}")
        
        if status_code == 200:
            country_data = data.get("country") or {}
            bank_data = data.get("bank") or {}
            return {
                "success": True, "bin": bin_clean[:6],
                "scheme": (data.get("scheme") or "N/A").upper(),
                "type": (data.get("type") or "N/A").upper(),
                "brand": (data.get("brand") or "N/A").upper(),
                "country": country_data.get("name", "N/A"),
                "country_flag": country_data.get("emoji", "🌍"),
                "country_code": country_data.get("alpha2", "??"),
                "bank": bank_data.get("name", "N/A"),
                "bank_url": bank_data.get("url", "N/A"),
                "prepaid": data.get("prepaid", False)
            }
        return {"success": False, "error": "BIN not found or rate limited."}
    except Exception:
        return {"success": False, "error": "Internal error occurred."}

def format_bin_response(result: dict) -> str:
    if not result["success"]:
        return f"❌ BIN LOOKUP FAILED\n━━━━━━━━━━━━━━━━━━━━\n\n⚠️ {result['error']}\n━━━━━━━━━━━━━━━━━━━━"
    
    type_emoji = {"CREDIT": "💳", "DEBIT": "🏦", "PREPAID": "💰"}.get(result["type"], "💳")
    brand_emoji = {"VISA": "🔵", "MASTERCARD": "🔴", "AMEX": "🟡"}.get(result["brand"], "⚪")
    prepaid_status = "✅ YES" if result.get("prepaid") else "❌ NO"
    
    response = (
        f"━━━━━━━━━━━━━━━━━━━━\n🦇 BIN LOOKUP RESULT\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"BIN ➺ <code>{result['bin']}</code>\nSCHEME ➺ {result['scheme']}\n"
        f"TYPE ➺ {type_emoji} {result['type']}\nBRAND ➺ {brand_emoji} {result['brand']}\n"
        f"PREPAID ➺ {prepaid_status}\n\n━━━━━━━━━━━━━━━━━━━━\n"
        f"🌍 COUNTRY INFO\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"NAME ➺ {result['country_flag']} {result['country']}\nCODE ➺ {result['country_code']}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n🏦 BANK INFO\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"BANK ➺ {result['bank']}\n"
    )
    if result.get("bank_url") and result["bank_url"] != "N/A":
        response += f"URL ➺ {result['bank_url']}\n"
    response += "\n━━━━━━━━━━━━━━━━━━━━"
    return response

async def cmd_bin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ INVALID USAGE\n━━━━━━━━━━━━━━━━━━━━\n\n📌 Usage: /bin <BIN>\n📌 Example: /bin 453201\n\n━━━━━━━━━━━━━━━━━━━━", parse_mode="HTML")
        return
    
    status_msg = await update.message.reply_text(f"🔍 Looking up BIN: <code>{context.args[0][:6]}</code>...", parse_mode="HTML")
    result = await lookup_bin(context.args[0])
    
    try:
        await status_msg.edit_text(text=format_bin_response(result), parse_mode="HTML", disable_web_page_preview=True)
    except Exception:
        pass

def get_bin_handler():
    return CommandHandler("bin", cmd_bin)
