import os
import aiohttp
import urllib.request
import urllib.error
import json
import asyncio
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
BOT_TOKEN    = os.environ["BOT_TOKEN"]
OWNER_ID     = int(os.environ["OWNER_ID"])
CHANNEL_ID   = os.environ["CHANNEL_ID"]   # e.g. "@Batcardchk" or "-100xxxxxxxxx"
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BOT CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VERSION      = "2.0.0"
DEV_LINK     = "https://t.me/BatmanDev"
CHANNEL_LINK = "https://t.me/Batcardchk"
GROUP_LINK   = "https://t.me/batcardchkGroup"
SUPPORT_LINK = "https://t.me/BatmanSupport"
BOT_LINK     = "https://t.me/BatcardBot"
BOT_USERNAME = "BatcardBot"
BOT_PHOTO_URL = ""
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OWNER_ID  = int(os.environ.get("OWNER_ID", "0"))
VERSION   = "V4.2"
DEV_LINK  = "https://t.me/Batmancardchk"
API_TIMEOUT      = 25
REFERRAL_CREDITS = 10
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
    "chk":  "",
    "pp":   "",
    "sh":   "",
    "pyu":  "",
    "chk":  "https://stripe-auth-test-production.up.railway.app/st0",
    "pp":   "https://pp-auth-test-production.up.railway.app/pp",
    "sh":   "https://shopify-auth-test-production.up.railway.app/sh",
    "pyu":  "https://payu-auth-test-production.up.railway.app/pyu",
    "b3":   "",
    "au":   "",
    "mss":  "",
    "mpp2": "",
    "au":   "https://stripe-auth-test-production.up.railway.app/st0",
    "mss":  "https://stripe-auth-test-production.up.railway.app/st0",
    "mpp2": "https://pp-auth-test-production.up.railway.app/pp",
}
GATE_SITES = {
    "chk":  "example.com",
    "chk":  "fashionspicex.com",
    "pp":   "example.com",
    "sh":   "example.com",
    "pyu":  "example.com",
    "b3":   "example.com",
    "au":   "example.com",
    "mss":  "example.com",
    "au":   "fashionspicex.com",
    "mss":  "fashionspicex.com",
    "mpp2": "example.com",
}
PREMIUM_GATES = {"au", "mss", "mpp2"}
FORCE_CHANNELS = [
    ("Batcardchk",      CHANNEL_LINK),
    ("batcardchkGroup", GROUP_LINK),
]
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BIN LOOKUP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def get_bin_info(bin_num: str) -> dict:
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            async with s.get(f"https://lookup.binlist.net/{bin_num}",
                             headers={"Accept-Version": "3"}) as r:
                if r.status != 200:
                    return {"error": True}
                data = await r.json(content_type=None)
                country = (data.get("country") or {})
                bank    = (data.get("bank") or {})
                scheme  = data.get("scheme", "N/A")
                ctype   = data.get("type", "N/A")
                alpha2  = (country.get("alpha2") or "").upper()
                emoji   = (
                    "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in alpha2)
                    if len(alpha2) == 2 else ""
                )
                return {
                    "scheme":        scheme,
                    "type":          ctype,
                    "bank":          bank.get("name", "N/A"),
                    "country":       country.get("name", "N/A"),
                    "country_emoji": emoji,
                }
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
        return {"error": True}
        pass
    return {"error": True}
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
def kb_result():
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SHARED KEYBOARD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def kb_result() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Channel", url=CHANNEL_LINK),
         InlineKeyboardButton("💬 Support", url=SUPPORT_LINK)],
        [InlineKeyboardButton("🦇 CARD X CHK ➺", url=CHANNEL_LINK)],
        [InlineKeyboardButton("🗡️ DEV ➺ Batman ➺", url=DEV_LINK)],
    ])
