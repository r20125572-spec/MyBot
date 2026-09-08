import urllib.request
import urllib.error
import json
import asyncio
import logging
import time
from datetime import datetime
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

logger = logging.getLogger(__name__)

COUNTRY_CURRENCY = {
    "US": "USD", "GB": "GBP", "EU": "EUR", "FR": "EUR", "DE": "EUR",
    "IT": "EUR", "ES": "EUR", "NL": "EUR", "BE": "EUR", "AT": "EUR",
    "PT": "EUR", "GR": "EUR", "IE": "EUR", "FI": "EUR", "SK": "EUR",
    "SI": "EUR", "LT": "EUR", "LV": "EUR", "EE": "EUR", "CY": "EUR",
    "MT": "EUR", "LU": "EUR", "CA": "CAD", "AU": "AUD", "JP": "JPY",
    "CN": "CNY", "IN": "INR", "BR": "BRL", "MX": "MXN", "KR": "KRW",
    "RU": "RUB", "CH": "CHF", "SE": "SEK", "NO": "NOK", "DK": "DKK",
    "PL": "PLN", "CZ": "CZK", "HU": "HUF", "TR": "TRY", "ZA": "ZAR",
    "SG": "SGD", "HK": "HKD", "NZ": "NZD", "SA": "SAR", "AE": "AED",
    "AR": "ARS", "CL": "CLP", "CO": "COP", "PH": "PHP", "MY": "MYR",
    "TH": "THB", "ID": "IDR", "PK": "PKR", "NG": "NGN", "EG": "EGP",
    "UA": "UAH", "RO": "RON", "BG": "BGN", "HR": "HRK", "RS": "RSD",
    "IL": "ILS", "VN": "VND", "BD": "BDT", "LK": "LKR", "KE": "KES",
}

def B(text: str) -> str:
    """Convert ASCII labels to Serif Bold Italic Unicode."""
    styled = []
    for char in str(text):
        if "A" <= char <= "Z":
            styled.append(chr(0x1D468 + ord(char) - ord("A")))
        elif "a" <= char <= "z":
            styled.append(chr(0x1D482 + ord(char) - ord("a")))
        elif "0" <= char <= "9":
            styled.append(chr(0x1D7CE + ord(char) - ord("0")))
        else:
            styled.append(char)
    return "".join(styled)

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
            bank_data    = data.get("bank") or {}
            alpha2       = (country_data.get("alpha2") or "").upper()
            # binlist.net has no emoji field — build flag from alpha2 e.g. "US" -> 🇺🇸
            flag = "".join(chr(ord(c) + 127397) for c in alpha2) if len(alpha2) == 2 else "🌍"
            return {
                "success":      True,
                "bin":          bin_clean[:6],
                "scheme":       (data.get("scheme") or "N/A").upper(),
                "type":         (data.get("type")   or "N/A").upper(),
                "brand":        (data.get("brand")  or "N/A").upper(),
                "country":      country_data.get("name", "N/A"),
                "country_flag": flag,
                "country_code": alpha2 or "??",
                "bank":         bank_data.get("name", "N/A"),
                "bank_url":     bank_data.get("url",  "N/A"),
                "prepaid":      data.get("prepaid", False),
            }
        return {"success": False, "error": "BIN not found or rate limited."}
    except Exception:
        return {"success": False, "error": "Internal error occurred."}

def format_bin_response(result: dict, user_name: str = "User", user_plan: str = "Tʀɪᴀʟ") -> str:
    if not result["success"]:
        return f"❌ BIN LOOKUP FAILED\n━━━━━━━━━━━━━━━━━━━━\n\n⚠️ {result['error']}\n━━━━━━━━━━━━━━━━━━━━"
    
    currency = COUNTRY_CURRENCY.get(result.get("country_code", ""), "N/A")
    
    response = (
        f"{B('Bin')} ➛ <code>{result['bin']}</code>\n"
        f"{B('Brand')} ➛ {result['brand']}\n"
        f"{B('Level')} ➛ {result['type']}\n"
        f"{B('Bank')} ➛ {result['bank']}\n"
        f"{B('Country')} ➛ {result['country_flag']} {result['country']}\n"
        f"{B('Currency')} ➛ {currency}\n"
        f"{B('User')} ➛ {user_name} ({user_plan})\n"
        f"{B('Dev')} ➛ Batman"
    )
    return response

async def cmd_bin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ INVALID USAGE\n━━━━━━━━━━━━━━━━━━━━\n\n📌 Usage: /bin <BIN>\n📌 Example: /bin 453201\n\n━━━━━━━━━━━━━━━━━━━━", parse_mode="HTML")
        return
    
    status_msg = await update.message.reply_text(f"🔍 Looking up BIN: <code>{context.args[0][:6]}</code>...", parse_mode="HTML")
    result = await lookup_bin(context.args[0])
    
    # Get User Plan for UI
    user_name = update.effective_user.first_name or "User"
    uid = str(update.effective_user.id)
    ud = context.bot_data.get("user_data", {}).get(uid, {})
    raw_plan = ud.get("plan", "TRIAL").upper()
    expires = ud.get("expires", 0)
    if raw_plan != "TRIAL" and expires <= time.time(): raw_plan = "TRIAL"
    
    styled_plan_map = {"CORE": "Cᴏʀᴇ", "ELITE": "Eʟɪᴛᴇ", "ROOT": "Rᴏᴏᴛ"}
    styled_plan = styled_plan_map.get(raw_plan, "Tʀɪᴀʟ")
    
    text = format_bin_response(result, user_name, styled_plan)
    try:
        await status_msg.edit_text(text, parse_mode="HTML", disable_web_page_preview=True)
    except Exception:
        try:
            await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)
        except Exception:
            pass

def get_bin_handler():
    return CommandHandler("bin", cmd_bin)
