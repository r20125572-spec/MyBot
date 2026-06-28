
import os
import urllib.request
import urllib.error
import json
import asyncio
import aiohttp
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BOT CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BOT_TOKEN  = os.environ.get("BOT_TOKEN", "")
OWNER_ID   = int(os.environ.get("OWNER_ID", "0"))
_ch_env    = os.environ.get("CHANNEL_ID", "").strip()
CHANNEL_ID = int(_ch_env) if _ch_env.lstrip("-").isdigit() else (_ch_env or "@Batcardchk")
VERSION    = "V4.2"
DEV_LINK   = "https://t.me/Batmancardchk"
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OWNER_ID  = int(os.environ.get("OWNER_ID", "0"))
# CHANNEL_ID: set as numeric "-100xxxxxxxxx" or "@Batcardchk" in env
_ch_raw  = os.environ.get("CHANNEL_ID", "@Batcardchk").strip()
CHANNEL_ID: int | str = int(_ch_raw) if _ch_raw.lstrip("-").isdigit() else _ch_raw
VERSION          = "V4.2"
DEV_LINK         = "https://t.me/Batmancardchk"
CHANNEL_USERNAME = "@Batcardchk"
GROUP_USERNAME   = "@batcardchkGroup"
CHANNEL_LINK     = "https://t.me/Batcardchk"
-3
+2
SUPPORT_LINK     = "https://t.me/cardchkSupport"
BOT_USERNAME     = "Batmancardchk_bot"
BOT_LINK         = "https://t.me/Batmancardchk_bot"
BOT_PHOTO_URL = "https://z-cdn-media.chatglm.cn/files/cd1a58d5-1a85-4246-8dac-dae333b02023.jpg"
BOT_PHOTO     = "batman.jpg"
BOT_PHOTO_URL    = "https://z-cdn-media.chatglm.cn/files/cd1a58d5-1a85-4246-8dac-dae333b02023.jpg"
BOT_PHOTO        = "batman.jpg"
API_TIMEOUT      = 120
REFERRAL_CREDITS = 150
-33
+27
]
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BIN LOOKUP
# BIN LOOKUP  (async via aiohttp)
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
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=8)
        ) as s:
            async with s.get(
                f"https://lookup.binlist.net/{bin_num}",
                headers={"Accept-Version": "3", "User-Agent": "Mozilla/5.0"},
            ) as r:
                if r.status != 200:
                    return {"error": True}
                data    = await r.json(content_type=None)
                country = data.get("country") or {}
                bank    = data.get("bank")    or {}
                alpha2  = (country.get("alpha2") or "").upper()
                emoji   = (
                    "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in alpha2)
                    if len(alpha2) == 2 else ""
                )
                return {
                    "scheme":        data.get("scheme", "N/A"),
                    "type":          data.get("type",   "N/A"),
                    "bank":          bank.get("name",   "N/A"),
                    "country":       country.get("name","N/A"),
                    "country_emoji": emoji,
                    "error":         False,
                }
    except Exception:
        pass
    return {"error": True}
        return {"error": True}
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SHARED KEYBOARD
