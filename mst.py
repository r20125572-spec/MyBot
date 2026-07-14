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
    bold_map = {
        'A': '𝗔', 'B': '𝗕', 'C': '𝗖', 'D': '𝗗', 'E': '𝗘', 'F': '𝗙',
        'G': '𝗚', 'H': '𝗛', 'I': '𝗜', 'J': '𝗝', 'K': '𝗞', 'L': '𝗟',
        'M': '𝗠', 'N': '𝗡', 'O': '𝗢', 'P': '𝗣', 'Q': '𝗤', 'R': '𝗥',
        'S': '𝗦', 'T': '𝗧', 'U': '𝗨', 'V': '𝗩', 'W': '𝗪', 'X': '𝗫',
        'Y': '𝗬', 'Z': '𝗭',
        'a': '𝗮', 'b': '𝗯', 'c': '𝗰', 'd': '𝗱', 'e': '𝗲', 'f': '𝗳',
        'g': '𝗴', 'h': '𝗵', 'i': '𝗶', 'j': '𝗷', 'k': '𝗸', 'l': '𝗹',
        'm': '𝗺', 'n': '𝗻', 'o': '𝗼', 'p': '𝗽', 'q': '𝗾', 'r': '𝗿',
        's': '𝘀', 't': '𝘁', 'u': '𝘂', 'v': '𝘃', 'w': '𝘄', 'x': '𝘅',
        'y': '𝘆', 'z': '𝘇',
        '0': '𝟬', '1': '𝟭', '2': '𝟮', '3': '𝟯', '4': '𝟰',
        '5': '𝟱', '6': '𝟲', '7': '𝟳', '8': '𝟴', '9': '𝟵',
    }
    return "".join(bold_map.get(ch, ch) for ch in text)

async def fetch_url(url: str, timeout: int = 15) -> tuple:
    try:
        req = urllib.request.Request(
            url,
            headers={
                "Accept-Version": "3",
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
            },
        )
        loop = asyncio.get_running_loop()
        def do_request():
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        return await loop.run_in_executor(None, do_request)
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception:
        return 0, {}

async def lookup_bin(bin_number: str) -> dict:
    try:
        bin_clean = "".join(filter(str.isdigit, str(bin_number)))[:8]
        if len(bin_clean) < 6:
            return {"success": False, "error": "Invalid BIN! Must be at least 6 digits."}
        status_code, data = await fetch_url(f"https://lookup.binlist.net/{bin_clean[:6]}")
        if status_code == 200:
            country_data = data.get("country") or {}
            bank_data    = data.get("bank") or {}
            return {
                "success":      True,
                "bin":          bin_clean[:6],
                "scheme":       (data.get("scheme") or "N/A").upper(),
                "type":         (data.get("type") or "N/A").upper(),
                "brand":        (data.get("brand") or "N/A").upper(),
                "country":      country_data.get("name", "N/A"),
                "country_flag": country_data.get("emoji", "🌍"),
                "country_code": country_data.get("alpha2", "??"),
                "bank":         bank_data.get("name", "N/A"),
                "bank_url":     bank_data.get("url", "N/A"),
                "prepaid":      data.get("prepaid", False),
            }
        return {"success": False, "error": "BIN not found or rate limited."}
    except Exception:
        return {"success": False, "error": "Internal error occurred."}

def format_bin_response(result: dict, user_name: str = "User", user_plan: str = "Tʀɪᴀʟ") -> str:
    if not result["success"]:
        return (
            f"❌ BIN LOOKUP FAILED\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"⚠️ {result['error']}\n━━━━━━━━━━━━━━━━━━━━"
        )
    currency = COUNTRY_CURRENCY.get(result.get("country_code", ""), "N/A")
    return (
        f"{B('Bin')}      ➛ <code>{result['bin']}</code>\n"
        f"{B('Brand')}    ➛ {result['brand']}\n"
        f"{B('Level')}    ➛ {result['type']}\n"
        f"{B('Bank')}     ➛ {result['bank']}\n"
        f"{B('Country')}  ➛ {result['country_flag']} {result['country']}\n"
        f"{B('Currency')} ➛ {currency}\n"
        f"{B('User')}     ➛ {user_name} ({user_plan})\n"
        f"{B('Dev')}      ➛ Batman"
    )

async def cmd_bin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ <b>INVALID USAGE</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            "📌 Usage: <code>/bin 453201</code>\n"
            "📌 Enter 6–8 digit BIN\n\n"
            "━━━━━━━━━━━━━━━━━━━━",
            parse_mode="HTML",
        )
        return

    status_msg = await update.message.reply_text(
        f"🔍 Looking up BIN: <code>{context.args[0][:6]}</code>...",
        parse_mode="HTML",
    )
    result    = await lookup_bin(context.args[0])
    user_name = update.effective_user.first_name or "User"
    uid       = str(update.effective_user.id)
    ud        = context.bot_data.get("user_data", {}).get(uid, {})
    raw_plan  = ud.get("plan", "TRIAL").upper()
    if raw_plan != "TRIAL" and ud.get("expires", 0) <= time.time():
        raw_plan = "TRIAL"
    styled_plan = {"CORE": "Cᴏʀᴇ", "ELITE": "Eʟɪᴛᴇ", "ROOT": "Rᴏᴏᴛ"}.get(raw_plan, "Tʀɪᴀʟ")

    try:
        await status_msg.edit_text(
            text=format_bin_response(result, user_name, styled_plan),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception:
        pass

def get_bin_handler():
    return CommandHandler("bin", cmd_bin)
