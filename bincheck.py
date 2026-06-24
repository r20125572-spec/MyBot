import urllib.request
import urllib.error
import urllib.parse
import json
import asyncio
import logging
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

logger = logging.getLogger(__name__)

# BIN Lookup API
BIN_API_URL = "https://lookup.binlist.net/{bin}"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


async def fetch_url(url: str, timeout: int = 15) -> tuple:
    """
    Fetch URL using urllib (built-in, no requests needed)
    Returns (status_code, json_data or error_message)
    """
    try:
        req = urllib.request.Request(
            url,
            headers={
                "Accept-Version": "3",
                "User-Agent": USER_AGENT,
                "Accept": "application/json"
            }
        )
        
        loop = asyncio.get_event_loop()
        
        def do_request():
            with urllib.request.urlopen(req, timeout=timeout) as response:
                data = response.read().decode('utf-8')
                return response.status, json.loads(data)
        
        status_code, data = await loop.run_in_executor(None, do_request)
        return status_code, data
        
    except urllib.error.HTTPError as e:
        try:
            error_body = e.read().decode('utf-8')
            return e.code, json.loads(error_body)
        except:
            return e.code, {"error": f"HTTP {e.code}"}
            
    except urllib.error.URLError as e:
        return 0, {"error": f"Connection failed: {str(e.reason)[:50]}"}
        
    except TimeoutError:
        return 0, {"error": "Request timeout!"}
        
    except json.JSONDecodeError:
        return 0, {"error": "Invalid JSON response"}
        
    except Exception as e:
        logger.error(f"Fetch error: {e}")
        return 0, {"error": f"Error: {str(e)[:50]}"}


async def lookup_bin(bin_number: str) -> dict:
    """
    Lookup BIN information from API
    Returns dict with success status and data
    """
    try:
        # Clean BIN - extract only digits, max 8 chars
        bin_clean = ''.join(filter(str.isdigit, str(bin_number)))[:8]
        
        if len(bin_clean) < 6:
            return {
                "success": False,
                "error": "Invalid BIN! Must be at least 6 digits."
            }
        
        # Use first 6 digits for standard BIN lookup
        bin_lookup = bin_clean[:6]
        
        logger.info(f"Looking up BIN: {bin_lookup}")
        
        # Fetch data
        url = BIN_API_URL.format(bin=bin_lookup)
        status_code, data = await fetch_url(url)
        
        if status_code == 200:
            # Extract data safely with defaults
            scheme = data.get("scheme", "N/A")
            scheme = scheme.upper() if scheme else "N/A"
            
            card_type = data.get("type", "N/A")
            card_type = card_type.upper() if card_type else "N/A"
            
            brand = data.get("brand", "N/A")
            brand = brand.upper() if brand else "N/A"
            
            country_data = data.get("country") or {}
            country_name = country_data.get("name", "N/A")
            country_emoji = country_data.get("emoji", "🌍")
            country_code = country_data.get("alpha2", "??")
            
            bank_data = data.get("bank") or {}
            bank_name = bank_data.get("name", "N/A")
            bank_url = bank_data.get("url", "N/A")
            bank_phone = bank_data.get("phone", "N/A")
            
            return {
                "success": True,
                "bin": bin_lookup,
                "scheme": scheme,
                "type": card_type,
                "brand": brand,
                "country": country_name,
                "country_flag": country_emoji,
                "country_code": country_code,
                "bank": bank_name,
                "bank_url": bank_url,
                "bank_phone": bank_phone,
                "prepaid": data.get("prepaid", False)
            }
            
        elif status_code == 404:
            return {
                "success": False,
                "error": "BIN not found in database."
            }
        elif status_code == 429:
            return {
                "success": False,
                "error": "Rate limited! Try again in a few seconds."
            }
        else:
            error_msg = data.get("error", f"API Error: {status_code}") if isinstance(data, dict) else f"API Error: {status_code}"
            return {
                "success": False,
                "error": error_msg
            }
            
    except Exception as e:
        logger.error(f"BIN lookup error: {e}")
        return {
            "success": False,
            "error": "Internal error occurred."
        }


def format_bin_response(result: dict) -> str:
    """Format BIN lookup result into nice message"""
    if not result["success"]:
        return (
            "❌ BIN LOOKUP FAILED\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"⚠️ {result['error']}\n\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
    
    # Card type emoji
    type_emojis = {
        "CREDIT": "💳",
        "DEBIT": "🏦",
        "PREPAID": "💰",
        "CHARGE CARD": "⚡",
        "N/A": "❓"
    }
    type_emoji = type_emojis.get(result["type"], "💳")
    
    # Brand logos
    brand_emojis = {
        "VISA": "🔵",
        "MASTERCARD": "🔴",
        "AMEX": "🟡",
        "DISCOVER": "🟠",
        "JCB": "🟢",
        "DINERS CLUB": "🟣",
        "UNIONPAY": "🔴",
        "N/A": "⚪"
    }
    brand_emoji = brand_emojis.get(result["brand"], "⚪")
    
    # Prepaid status
    prepaid_status = "✅ YES" if result.get("prepaid") else "❌ NO"
    
    response = (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🦇 BIN LOOKUP RESULT\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"BIN ➺ <code>{result['bin']}</code>\n"
        f"SCHEME ➺ {result['scheme']}\n"
        f"TYPE ➺ {type_emoji} {result['type']}\n"
        f"BRAND ➺ {brand_emoji} {result['brand']}\n"
        f"PREPAID ➺ {prepaid_status}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🌍 COUNTRY INFO\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"NAME ➺ {result['country_flag']} {result['country']}\n"
        f"CODE ➺ {result['country_code']}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🏦 BANK INFO\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"BANK ➺ {result['bank']}\n"
    )
    
    if result.get("bank_url") and result["bank_url"] != "N/A":
        response += f"URL ➺ {result['bank_url']}\n"
    
    if result.get("bank_phone") and result["bank_phone"] != "N/A":
        response += f"PHONE ➺ <code>{result['bank_phone']}</code>\n"
    
    response += "\n━━━━━━━━━━━━━━━━━━━━"
    
    return response


async def cmd_bin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /bin command
    Usage: /bin 453201
    """
    # Check if BIN provided
    if not context.args:
        await update.message.reply_text(
            "❌ INVALID USAGE\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "📌 Usage: /bin &lt;BIN&gt;\n"
            "📌 Example: /bin 453201\n"
            "📌 BIN = First 6-8 digits of card\n\n"
            "━━━━━━━━━━━━━━━━━━━━",
            parse_mode="HTML"
        )
        return
    
    bin_input = context.args[0]
    
    # Send processing message
    status_msg = await update.message.reply_text(
        f"🔍 Looking up BIN: <code>{bin_input[:6]}</code>\n\n"
        f"⏳ Please wait...",
        parse_mode="HTML"
    )
    
    # Perform lookup
    result = await lookup_bin(bin_input)
    
    # Format and send response
    response_text = format_bin_response(result)
    
    try:
        await status_msg.edit_text(
            text=response_text,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Failed to edit BIN message: {e}")
        try:
            await status_msg.delete()
            await update.message.reply_text(
                text=response_text,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        except Exception:
            pass


def get_bin_handler():
    """
    Return the bin command handler for registration
    """
    return CommandHandler("bin", cmd_bin)
