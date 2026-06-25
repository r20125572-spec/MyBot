import urllib.request
import urllib.error
import json
import asyncio
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 BOT CONFIGURATION 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BOT_TOKEN = "8813507423:AAFWkdkk8Je4kB93AB5fu6qQ0-8eo-jlRKE"
OWNER_ID = 8283904645
VERSION = "V4.2"
DEV_LINK = "https://t.me/Batmancardchk"

CHANNEL_USERNAME = "@Batcardchk"
GROUP_USERNAME = "@batcardchkGroup"
CHANNEL_LINK = "https://t.me/Batcardchk"
GROUP_LINK = "https://t.me/batcardchkGroup"
SUPPORT_LINK = "https://t.me/failurefr_07"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 BATMAN PHOTO — Bot downloads this URL itself
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BOT_PHOTO_URL = "https://z-cdn-media.chatglm.cn/files/cd1a58d5-1a85-4246-8dac-dae333b02023.jpg"
BOT_PHOTO = "batman.jpg"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 GATE API URLs
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GATE_URLS = {
    "chk": "https://stripe-auth-test-production.up.railway.app/st0",
    "pp":  "https://pp-auth-test-production.up.railway.app/pp",
    "sh":  "https://shopify-auth-test-production.up.railway.app/sh",
    "pyu": "https://payu-auth-test-production.up.railway.app/pyu",
    "b3":  "",
}

GATE_SITES = {
    "chk": "fashionspicex.com",
    "pp":  "example.com",
    "sh":  "example.com",
    "pyu": "example.com",
    "b3":  "example.com",
}

API_TIMEOUT = 120

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 DIRECT GATE VARIABLES (Fixes Import Errors for gates)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CHK_API = GATE_URLS.get("chk", "")
CHK_SITE = GATE_SITES.get("chk", "example.com")

PP_API = GATE_URLS.get("pp", "")
PP_SITE = GATE_SITES.get("pp", "example.com")

SH_API = GATE_URLS.get("sh", "")
SH_SITE = GATE_SITES.get("sh", "example.com")

PYU_API = GATE_URLS.get("pyu", "")
PYU_SITE = GATE_SITES.get("pyu", "example.com")

B3_API = GATE_URLS.get("b3", "")
B3_SITE = GATE_SITES.get("b3", "example.com")

async def get_bin_info(bin_num: str) -> dict:
    try:
        url = f"https://lookup.binlist.net/{bin_num}"
        req = urllib.request.Request(url, headers={"Accept-Version": "3", "User-Agent": "Mozilla/5.0"})
        def fetch():
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode('utf-8'))
        data = await asyncio.get_running_loop().run_in_executor(None, fetch)
        bank_name = "N/A"
        if data.get("bank"): bank_name = data["bank"].get("name", "N/A")
        country_name = "N/A"; country_emoji = ""
        if data.get("country"):
            country_name = data["country"].get("name", "N/A").upper()
            country_emoji = data["country"].get("emoji", "")
        return {"scheme": data.get("scheme", "N/A"), "type": data.get("type", "N/A"), "bank": bank_name, "country": country_name, "country_emoji": country_emoji, "error": False}
    except Exception: pass
    return {"error": True}

def ui_result(card, gate, bin_txt, country, flag, raw, user, approved, time_taken="0.00"):
    u = user.username or user.first_name
    status = "Cᴀʀᴅ Cʜᴀʀɢᴇᴅ ✅" if approved else "Cᴀʀᴅ Dᴇᴄʟɪɴᴇᴅ ❌"
    info = f"{bin_txt} - {country}{flag}" if bin_txt and bin_txt != "N/A" else f"{country}{flag}"
    return (f"Tᴏᴛᴀʟ Cᴀʀᴅꜱ ➺ 1/1\nTɪᴍᴇ ➺ {time_taken}s\nUꜱᴇʀ ➺ {u}\n━━━━━━━━━━━━━━━━\n━━━━━━━━━━━━━━━━\n<code>{card}</code>\n{status}\nIɴꜰᴏ ➺ {info}\n━━━━━━━━━━━━━━━━\n\n✅ Cʜᴇᴄᴋ Cᴏᴍᴘʟᴇᴛᴇ.")

def kb_result():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🦇 CARD X CHK", url="https://t.me/Batcardchk")],
        [InlineKeyboardButton("🗡️ DEV ➺ Batman", url="https://t.me/Batmancardchk")]
    ])
