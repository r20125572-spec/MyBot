import aiohttp
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 BOT CONFIGURATION 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BOT_TOKEN = "8813507423:AAFWkdkk8Je4kB93AB5fu6qQ0-8eo-jlRKE"
OWNER_ID = 8283904645
VERSION = "V4.1"
DEV_LINK = "https://t.me/Batmancardchk"

CHANNEL_USERNAME = "@Batcardchk"
GROUP_USERNAME = "@batcardchkGroup"
CHANNEL_LINK = "https://t.me/Batcardchk"
GROUP_LINK = "https://t.me/batcardchkGroup"
SUPPORT_LINK = "https://t.me/failurefr_07"
BOT_PHOTO = "https://z-cdn-media.chatglm.cn/files/cd1a58d5-1a85-4246-8dac-dae333b02023.jpg"

# Gate APIs
STRIPE_API = "https://stripe-auth-test-production.up.railway.app/st0"
STRIPE_SITE = "fashionspicex.com"
PP_API = "https://pp-auth-test-production.up.railway.app/pp"
PP_SITE = "example.com"
SH_API = "https://shopify-auth-test-production.up.railway.app/sh"
SH_SITE = "example.com"
PYU_API = "https://payu-auth-test-production.up.railway.app/pyu"
PYU_SITE = "example.com"

API_TIMEOUT = 120

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 BIN LOOKUP 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def get_bin_info(bin_num: str) -> dict:
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"https://lookup.binlist.net/{bin_num}") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    bank_name = "N/A"
                    if data.get("bank"):
                        bank_name = data["bank"].get("name", "N/A")
                    country_name = "N/A"
                    country_emoji = ""
                    if data.get("country"):
                        country_name = data["country"].get("name", "N/A").upper()
                        country_emoji = data["country"].get("emoji", "")
                    return {
                        "scheme": data.get("scheme", "N/A"),
                        "type": data.get("type", "N/A"),
                        "bank": bank_name,
                        "country": country_name,
                        "country_emoji": country_emoji,
                        "error": False
                    }
    except Exception:
        pass
    return {"error": True}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 SHARED CHECK UI (NEW CLEAN STYLE) 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def ui_result(card, gate, bin_txt, country, flag, raw, user, approved, time_taken="0.00"):
    u = user.username or user.first_name
    status = "Cᴀʀᴅ Cʜᴀʀɢᴇᴅ ✅" if approved else "Cᴀʀᴅ Dᴇᴄʟɪɴᴇᴅ ❌"
    
    # Combine BIN info and Country cleanly
    if bin_txt and bin_txt != "N/A":
        info = f"{bin_txt} - {country}{flag}"
    else:
        info = f"{country}{flag}"
        
    return (
        f"Tᴏᴛᴀʟ Cᴀʀᴅꜱ ➺ 1/1\n"
        f"Tɪᴍᴇ ➺ {time_taken}s\n"
        f"Uꜱᴇʀ ➺ {u}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"<code>{card}</code>\n"
        f"{status}\n"
        f"Iɴꜰᴏ ➺ {info}\n"
        f"━━━━━━━━━━━━━━━━\n\n"
        f"✅ Cʜᴇᴄᴋ Cᴏᴍᴘʟᴇᴛᴇ."
    )

def kb_result():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🦇 CARD X CHK", url="https://t.me/Batcardchk")],
        [InlineKeyboardButton("🗡️ DEV ➺ Batman", url="https://t.me/Batmancardchk")]
    ])
