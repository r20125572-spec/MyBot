import urllib.request
import urllib.error
import json
import asyncio
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BOT CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BOT_TOKEN = "8815716763:AAHUMJqQcCwN9TILIyGT6eTLRt4DMio93tA"
OWNER_ID  = 8283904645
VERSION   = "V4.2"
DEV_LINK  = "https://t.me/Batmancardchk"

CHANNEL_USERNAME = "@Batcardchk"
GROUP_USERNAME   = "@batcardchkGroup"
CHANNEL_LINK     = "https://t.me/Batcardchk"
GROUP_LINK       = "https://t.me/batcardchkGroup"
SUPPORT_LINK     = "https://t.me/cardchkSupport"
BOT_USERNAME     = "Batmancardchk_bot"
BOT_LINK         = "https://t.me/Batmancardchk_bot"

BOT_PHOTO_URL = "https://z-cdn-media.chatglm.cn/files/cd1a58d5-1a85-4246-8dac-dae333b02023.jpg"
BOT_PHOTO     = "batman.jpg"

API_TIMEOUT      = 120
REFERRAL_CREDITS = 150
LOCK_FILE        = "/tmp/batman_bot.lock"

GATE_URLS = {
    "chk":  "https://stripe-auth-test-production.up.railway.app/st0",
    "pp":   "https://pp-auth-test-production.up.railway.app/pp",
    "sh":   "https://shopify-auth-test-production.up.railway.app/sh",
    "pyu":  "https://payu-auth-test-production.up.railway.app/pyu",
    "b3":   "",
    "au":   "https://stripe-auth-test-production.up.railway.app/st0",
    "mss":  "https://stripe-auth-test-production.up.railway.app/st0",
    "mpp2": "https://pp-auth-test-production.up.railway.app/pp",
}

GATE_SITES = {
    "chk":  "fashionspicex.com",
    "pp":   "example.com",
    "sh":   "example.com",
    "pyu":  "example.com",
    "b3":   "example.com",
    "au":   "fashionspicex.com",
    "mss":  "fashionspicex.com",
    "mpp2": "example.com",
}

PREMIUM_GATES = {"au", "mss", "mpp2"}

FORCE_CHANNELS = [
    ("Batcardchk",     CHANNEL_LINK),
    ("batcardchkGroup", GROUP_LINK),
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BIN LOOKUP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def get_bin_info(bin_num: str) -> dict:
    try:
        url = f"https://lookup.binlist.net/{bin_num}"
        req = urllib.request.Request(
            url,
            headers={"Accept-Version": "3", "User-Agent": "Mozilla/5.0"},
        )

        def fetch():
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))

        data = await asyncio.get_running_loop().run_in_executor(None, fetch)

        bank_name = "N/A"
        if data.get("bank"):
            bank_name = data["bank"].get("name", "N/A")

        country_name  = "N/A"
        country_emoji = ""
        if data.get("country"):
            country_name  = data["country"].get("name",  "N/A").upper()
            country_emoji = data["country"].get("emoji", "")

        return {
            "scheme":        data.get("scheme", "N/A"),
            "type":          data.get("type",   "N/A"),
            "bank":          bank_name,
            "country":       country_name,
            "country_emoji": country_emoji,
            "error":         False,
        }
    except Exception:
        pass
    return {"error": True}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SHARED KEYBOARD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def kb_result() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🦇 CARD X CHK ➺", url=CHANNEL_LINK)],
        [InlineKeyboardButton("🗡️ DEV ➺ Batman ➺", url=DEV_LINK)],
    ])
