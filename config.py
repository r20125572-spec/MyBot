import os
import aiohttp
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

# ╔══════════════════════════════════════════════════════╗
# ║              BATMAN BOT — CONFIG FILE                ║
# ║   Edit the values below, then restart your bot.     ║
# ╚══════════════════════════════════════════════════════╝

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔑  BOT CREDENTIALS
#     BOT_TOKEN  → get from @BotFather on Telegram
#     OWNER_ID   → your personal Telegram user ID
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8799211002:AAH95tK5_6ovIiz7gRxA0X__xUUF6R3C0ts")
OWNER_ID  = int(os.environ.get("OWNER_ID", "8283904645"))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🤖  BOT IDENTITY
#     VERSION    → shown in /start and profile messages
#     DEV_LINK   → your dev / contact Telegram link
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VERSION  = "V4.3"
DEV_LINK = "https://t.me/Batmancardchk"

BOT_USERNAME  = "Goutam29_bot"
BOT_LINK      = f"https://t.me/{BOT_USERNAME}"

# Bot photo shown in /start (URL fallback — used if photo.jpg is missing)
BOT_PHOTO_URL = "https://z-cdn-media.chatglm.cn/files/baac90d1-06d0-478f-8989-5bef9cbfc9fb.jpg"
BOT_PHOTO     = "batman.jpg"          # local filename (not used directly; bot.py uses photo.jpg)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📢  CHANNEL & GROUP LINKS
#     Used for the CONNECT button, results footer, etc.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CHANNEL_USERNAME = "@Batcardchk"
GROUP_USERNAME   = "@batcardchkGroup"

CHANNEL_LINK  = "https://t.me/Batcardchk"
GROUP_LINK    = "https://t.me/batcardchkGroup"
SUPPORT_LINK  = "https://t.me/cardchkSupport"

# Telegram channel ID (used by force-sub check for private channels)
# Leave as username string if channel is public
_ch_raw    = os.environ.get("CHANNEL_ID", CHANNEL_USERNAME).strip()
CHANNEL_ID = int(_ch_raw) if _ch_raw.lstrip("-").isdigit() else _ch_raw

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔒  FORCE-JOIN CHANNELS & GROUPS
#     Every user must join ALL entries before using the bot.
#     Format: ("username_without_@", "https://t.me/username")
#
#     ⚠️  The bot must be ADMIN in each chat listed here.
#     ⚠️  Add / remove entries freely; bot.py merges this
#         list with its own FORCE_JOIN_LIST automatically.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FORCE_CHANNELS = [
    ("Batcardchk",      CHANNEL_LINK),   # 📢 Main Channel
    ("batcardchkGroup", GROUP_LINK),     # 👥 Main Group
    # ("AnotherChannel", "https://t.me/AnotherChannel"),
    # ("AnotherGroup",   "https://t.me/AnotherGroup"),
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ⚙️  GENERAL SETTINGS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
API_TIMEOUT      = 120    # seconds to wait for a gate API response
REFERRAL_CREDITS = 150    # credits awarded to referrer per successful invite
LOCK_FILE        = "/tmp/batman_bot.lock"   # prevents duplicate bot instances

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔗  GATE API URLS
#     Set the API endpoint for each gate key.
#     You can override these at runtime with /seturl <gate> <url>
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GATE_URLS: dict[str, str] = {
    # ── Single Checkers ───────────────────────────────
    "chk":  "https://stripe-auth-test-production.up.railway.app/st0",   # Stripe Charge
    "pp":   "https://pp-auth-test-production.up.railway.app/pp",         # PayPal Charge
    "sh":   "https://shopify-auth-test-production.up.railway.app/sh",    # Shopify Charge
    "pyu":  "https://payu-auth-test-production.up.railway.app/pyu",      # PayU Charge
    # ── Auth ──────────────────────────────────────────
    "b3":   "https://avs.blaze.indevs.in/api/b3",                        # Braintree Auth
    # ── Mass / Premium ────────────────────────────────
    "au":   "https://stripe-auth-test-production.up.railway.app/st0",    # Stripe Auth Mass
    "mss":  "https://stripe-auth-test-production.up.railway.app/st0",    # Stripe Mass
    "mpp2": "https://pp-auth-test-production.up.railway.app/pp",          # PayPal Mass
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🌐  GATE TARGET SITES
#     The merchant site sent alongside the card to the API.
#     Replace "example.com" with real sites for better results.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GATE_SITES: dict[str, str] = {
    "chk":  "fashionspicex.com",
    "pp":   "example.com",
    "sh":   "example.com",
    "pyu":  "example.com",
    "b3":   "example.com",
    "au":   "fashionspicex.com",
    "mss":  "fashionspicex.com",
    "mpp2": "example.com",
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 👑  PREMIUM-ONLY GATES
#     Users with Trial plan cannot access these gate keys.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PREMIUM_GATES: set[str] = {"au", "mss", "mpp2"}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔍  BIN LOOKUP  (uses binlist.net — no key needed)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def get_bin_info(bin_num: str) -> dict:
    """Fetch card BIN details. Returns dict with keys:
       scheme, type, bank, country, country_emoji, error (bool).
    """
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=8)
        ) as session:
            async with session.get(
                f"https://lookup.binlist.net/{str(bin_num)[:6]}",
                headers={"Accept-Version": "3", "User-Agent": "Mozilla/5.0"},
            ) as resp:
                if resp.status != 200:
                    return {"error": True}
                data    = await resp.json(content_type=None)
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
# ⌨️  SHARED RESULT KEYBOARD
#     Shown under every card-check result.
#     Premium users → link to channel.
#     Trial users   → upgrade button.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def kb_result(is_premium: bool = False) -> InlineKeyboardMarkup:
    if is_premium:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Batcardchk", url=CHANNEL_LINK)],
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 BUY PREMIUM", callback_data="mprice")],
    ])
