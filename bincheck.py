import requests
import asyncio
import logging
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

logger = logging.getLogger(__name__)

# BIN Lookup API
BIN_API_URL = "https://lookup.binlist.net/{bin}"
BIN_API_HEADERS = {"Accept-Version": "3", "User-Agent": "Mozilla/5.0"}


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
        
        # Async HTTP request
        loop = asyncio.get_event_loop()
        
        def fetch():
            return requests.get(
                BIN_API_URL.format(bin=bin_lookup),
                headers=BIN_API_HEADERS,
                timeout=15
            )
        
        response = await loop.run_in_executor(None, fetch)
        
        if response.status_code == 200:
            data = response.json()
            
            # Extract data safely with defaults
            scheme = data.get("scheme", "N/A")
            if scheme:
                scheme = scheme.upper()
            else:
                scheme = "N/A"
                
            card_type = data.get("type", "N/A")
            if card_type:
                card_type = card_type.upper()
            else:
                card_type = "N/A"
                
            brand = data.get("brand", "N/A")
            if brand:
                brand = brand.upper()
            else:
                brand = "N/A"
            
            country_data = data.get("country", {})
            country_name = country_data.get("name", "N/A") if country_data else "N/A"
            country_emoji = country_data.get("emoji", "🌍") if country_data else "🌍"
            country_code = country_data.get("alpha2", "??") if country_data else "??"
            
            bank_data = data.get("bank", {})
            bank_name = bank_data.get("name", "N/A") if bank_data else "N/A"
            bank_url = bank_data.get("url", "N/A") if bank_data else "N/A"
            bank_phone = bank_data.get("phone", "N/A") if bank_data else "N/A"
            
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
                "prepaid": data.get("prepaid", False),
                "number": data.get("number", {})
            }
            
        elif response.status_code == 404:
            return {
                "success": False,
                "error": "BIN not found in database."
            }
        elif response.status_code == 429:
            return {
                "success": False,
                "error": "Rate limited! Try again in a few seconds."
            }
        else:
            return {
                "success": False,
                "error": f"API Error: {response.status_code}"
            }
            
    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": "Request timeout! Please try again."
        }
    except requests.exceptions.Timeout:
        return {
            "success": False,
            "error": "Connection timeout! Please try again."
        }
    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "error": "Connection failed! Check internet."
        }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": f"Network error: {str(e)[:50]}"
        }
    except Exception as e:
        logger.error(f"BIN lookup error: {e}")
        return {
            "success": False,
            "error": f"Internal error occurred."
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
        # If edit fails, send new message
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


# Test function (for local testing only)
if __name__ == "__main__":
    import sys
    
    async def test():
        test_bins = ["453201", "542543", "371449", "601100"]
        
        for test_bin in test_bins:
            print(f"\nTesting BIN: {test_bin}")
            print("-" * 30)
            result = await lookup_bin(test_bin)
            if result["success"]:
                print(f"Scheme: {result['scheme']}")
                print(f"Type: {result['type']}")
                print(f"Brand: {result['brand']}")
                print(f"Country: {result['country_flag']} {result['country']}")
                print(f"Bank: {result['bank']}")
            else:
                print(f"Error: {result['error']}")
    
    asyncio.run(test())
