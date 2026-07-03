import os
import aiohttp
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BOT CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8032773834:AAEWbgMolss5toTzWd5zQe3KTUp3Zy2D5-k")
OWNER_ID  = int(os.environ.get("OWNER_ID", "8283904645"))

_ch_raw    = os.environ.get("CHANNEL_ID", "@Batcardchk").strip()
CHANNEL_ID = int(_ch_raw) if _ch_raw.lstrip("-").isdigit() else _ch_raw

VERSION  = "V4.3"
DEV_LINK = "https://t.me/Batmancardchk"

CHANNEL_USERNAME = "@Batcardchk"
GROUP_USERNAME   = "@batcardchkGroup"
CHANNEL_LINK     = "https://t.me/Batcardchk"
GROUP_LINK       = "https://t.me/batcardchkGroup"
SUPPORT_LINK     = "https://t.me/cardchkSupport"

BOT_USERNAME  = "Batmanchk_bot"
BOT_LINK      = "https://t.me/Batmanchk_bot"
BOT_PHOTO_URL = "https://z-cdn-media.chatglm.cn/files/cd1a58d5-1a85-4246-8dac-dae333b02023.jpg"
BOT_PHOTO     = "batman.jpg" 

API_TIMEOUT      = 120
REFERRAL_CREDITS = 150
LOCK_FILE        = "/tmp/batman_bot.lock"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FORCE JOIN  
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FORCE_CHANNELS = [
    ("Batcardchk",      CHANNEL_LINK),
    ("batcardchkGroup", GROUP_LINK),
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GATE CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BIN LOOKUP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def get_bin_info(bin_num: str) -> dict:
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            async with s.get(
                f"https://lookup.binlist.net/{str(bin_num)[:6]}",
                headers={"Accept-Version": "3", "User-Agent": "Mozilla/5.0"},
            ) as r:
                if r.status != 200:
                    return {"error": True}
                data    = await r.json(content_type=None)
                country = data.get("country") or {}
                bank    = data.get("bank") or {}
                alpha2  = (country.get("alpha2") or "").upper()
                emoji   = (
                    "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in alpha2)
                    if len(alpha2) == 2 else ""
                )
                return {
                    "scheme":        data.get("scheme", "N/A"),
                    "type":          data.get("type",   "N/A"),
                    "bank":          bank.get("name",   "N/A"),
                    "country":       country.get("name", "N/A"),
                    "country_emoji": emoji,
                    "error":         False,
                }
    except Exception:
        return {"error": True}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SHARED RESULT KEYBOARD  (Dynamic based on Premium)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def kb_result(is_premium: bool = False) -> InlineKeyboardMarkup:
    if is_premium:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("Batcardchk", url=CHANNEL_LINK)],
        ])
    else:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("💎 BUY PREMIUM", callback_data="mprice")],
        ])
