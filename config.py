import os
import json
import random
import aiohttp

# ╔══════════════════════════════════════════════════════╗
# ║              BATMAN BOT — CONFIG FILE                ║
# ║   Edit the values below, then restart your bot.     ║
# ╚══════════════════════════════════════════════════════╝

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔑  BOT CREDENTIALS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8848759446:AAERdNnYp0cTZ6stj5yMSfVHqnDyGO61w_k")
OWNER_ID  = int(os.environ.get("OWNER_ID", "8283904645"))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🤖  BOT IDENTITY
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VERSION  = "V4.3"
DEV_LINK = "https://t.me/Batmancardchk"

BOT_USERNAME  = "Goutam29_bot"
BOT_LINK      = f"https://t.me/{BOT_USERNAME}"

BOT_PHOTO_URL = "https://z-cdn-media.chatglm.cn/files/baac90d1-06d0-478f-8989-5bef9cbfc9fb.jpg"
BOT_PHOTO     = "batman.jpg"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📢  CHANNEL & GROUP LINKS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CHANNEL_USERNAME = "@Batcardchk"
GROUP_USERNAME   = "@batcardchkGroup"

CHANNEL_LINK  = "https://t.me/Batcardchk"
GROUP_LINK    = "https://t.me/batcardchkGroup"
SUPPORT_LINK  = "https://t.me/cardchkSupport"

_ch_raw    = os.environ.get("CHANNEL_ID", CHANNEL_USERNAME).strip()
CHANNEL_ID = int(_ch_raw) if _ch_raw.lstrip("-").isdigit() else _ch_raw

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔒  FORCE-JOIN CHANNELS & GROUPS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FORCE_CHANNELS = [
    ("Batcardchk",      CHANNEL_LINK),
    ("batcardchkGroup", GROUP_LINK),
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ⚙️  GENERAL SETTINGS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
API_TIMEOUT      = 120
REFERRAL_CREDITS = 150
LOCK_FILE        = "/tmp/batman_bot.lock"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔗  GATE API URLS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GATE_URLS: dict[str, str] = {
    "chk":  "https://stripe-auth-test-production.up.railway.app/st0",
    "pp":   "https://pp-auth-test-production.up.railway.app/pp",
    "sh":   "https://shopify-auth-test-production.up.railway.app/sh",
    "pyu":  "https://payu-auth-test-production.up.railway.app/pyu",
    "b3":   "https://avs.blaze.indevs.in/api/b3",
    "au":   "https://stripe-auth-test-production.up.railway.app/st0",
    "mss":  "https://stripe-auth-test-production.up.railway.app/st0",
    "mpp2": "https://pp-auth-test-production.up.railway.app/pp",
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🌐  GATE TARGET SITES
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
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PREMIUM_GATES: set[str] = {"au", "mss", "mpp2"}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🎨  CUSTOM EMOJI IDS  (mst.py style)
#     Telegram Premium custom emoji stickers.
#     All users see them — even non-Premium accounts.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DECLINED_EMOJI_ID      = "4956612582816351459"
CARD_EMOJI_ID          = "5800709991627232190"
USER_EMOJI_ID          = "4958689671950369798"
TIME_EMOJI_ID          = "5382194935057372936"
DEV_EMOJI_ID           = "6267091732861555879"
PRO_EMOJI_ID           = "6298678524379137990"

HIT_RESP_EMOJI_ID      = "5839116473951328489"

PROG_GATE_EMOJI_ID     = "5341715473882955310"
PROG_PROGRESS_EMOJI_ID = "5258113901106580375"
PROG_LIVE_EMOJI_ID     = "5427168083074628963"
PROG_DEAD_EMOJI_ID     = "4958526153955476488"
PROG_ERRORS_EMOJI_ID   = "4956611513369494230"

BTN_ALL_EMOJI_ID       = "4956324463525233747"
BTN_STOP_EMOJI_ID      = "6179444193518162239"

LIVE_EMOJI_IDS = [
    "5801154993188770160", "4956739572114392015", "5285221724634239278",
    "5287777298894835685", "5285024405246725814", "5287547831677112267",
    "5287658362660474522", "5285186510197381130", "5803233241963959320",
    "5462902520215002477", "5787435351521889877", "5323674506705785412",
    "5801005158959683238", "5436143465211640305", "5800688138833629633",
    "5891044423856296980", "5436068999068662274", "5427168083074628963",
]

PLAN_EMOJIS = {
    "CORE":   "5379869575338812919",
    "ELITE":  "5836898273666798437",
    "ROOT":   "4956420911310832630",
    "CUSTOM": "5445027583588593750",
}

SPECIAL_FONT_MAP = {
    'ᴀ': 'A', 'ʙ': 'B', 'ᴄ': 'C', 'ᴅ': 'D', 'ᴇ': 'E',
    'ꜰ': 'F', 'ɢ': 'G', 'ʜ': 'H', 'ɪ': 'I', 'ᴊ': 'J',
    'ᴋ': 'K', 'ʟ': 'L', 'ᴍ': 'M', 'ɴ': 'N', 'ᴏ': 'O',
    'ᴘ': 'P', 'ǫ': 'Q', 'ʀ': 'R', 'ꜱ': 'S', 'ᴛ': 'T',
    'ᴜ': 'U', 'ᴠ': 'V', 'ᴡ': 'W', 'x': 'X', 'ʏ': 'Y',
    'ᴢ': 'Z', 'Ɪ': 'I',
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🛠  EMOJI HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def tg_emoji(emoji_id: str, fallback: str = "⭐") -> str:
    """Render a Telegram custom emoji tag (HTML parse_mode).
    All users — including non-Premium — see the animated sticker."""
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'

def get_random_live_emoji() -> str:
    """Return a random live-hit emoji ID (string, not rendered tag)."""
    return random.choice(LIVE_EMOJI_IDS)

def get_plan_emoji_id(plan_name: str) -> str:
    """Return the custom emoji ID for a given plan name string."""
    if not plan_name:
        return PRO_EMOJI_ID
    normalized = "".join(SPECIAL_FONT_MAP.get(c, c.upper()) for c in plan_name)
    if normalized in PLAN_EMOJIS:
        return PLAN_EMOJIS[normalized]
    for key, eid in PLAN_EMOJIS.items():
        if key in normalized:
            return eid
    return PRO_EMOJI_ID

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🏷  PRE-RENDERED EMOJI SHORTHANDS
#     Import these in b3.py, chk.py, main.py, etc.
#     Always use parse_mode="HTML" — NOT MarkdownV2.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

E_CARD     = tg_emoji(CARD_EMOJI_ID,          "💳")
E_USER     = tg_emoji(USER_EMOJI_ID,          "👤")
E_TIME     = tg_emoji(TIME_EMOJI_ID,          "⏱")
E_DEV      = tg_emoji(DEV_EMOJI_ID,           "⚡")
E_PRO      = tg_emoji(PRO_EMOJI_ID,           "⭐")
E_LIVE     = tg_emoji(PROG_LIVE_EMOJI_ID,     "✅")
E_DECLINED = tg_emoji(PROG_DEAD_EMOJI_ID,     "❌")
E_ERRORS   = tg_emoji(PROG_ERRORS_EMOJI_ID,   "⚠️")
E_PROGRESS = tg_emoji(PROG_PROGRESS_EMOJI_ID, "🔄")
E_GATE     = tg_emoji(PROG_GATE_EMOJI_ID,     "🛒")
E_HIT_RESP = tg_emoji(HIT_RESP_EMOJI_ID,      "✅")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ⌨️  RAW MARKUP — coloured buttons (mst.py style)
#
#   Telegram Bot API supports:
#     "style": "primary"   → blue button
#     "style": "danger"    → red button
#     "icon_custom_emoji_id" → animated sticker on button
#
#   python-telegram-bot calls .to_dict() on reply_markup,
#   so this thin wrapper passes raw API JSON straight through.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class RawMarkup:
    """Coloured inline keyboard — compatible with python-telegram-bot."""
    def __init__(self, inline_keyboard: list):
        self._data = {"inline_keyboard": inline_keyboard}

    def to_dict(self) -> dict:
        return self._data

    def to_json(self) -> str:
        return json.dumps(self._data)


def _btn(text: str, *, cb: str = None, url: str = None,
         style: str = None, icon: str = None) -> dict:
    """Build one raw Telegram API button dict."""
    d: dict = {"text": text}
    if cb:    d["callback_data"]        = cb
    if url:   d["url"]                  = url
    if style: d["style"]                = style
    if icon:  d["icon_custom_emoji_id"] = icon
    return d

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔍  BIN LOOKUP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def get_bin_info(bin_num: str) -> dict:
    """Fetch card BIN details from binlist.net (no API key needed)."""
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
                    "country":       country.get("name", "N/A"),
                    "country_emoji": emoji,
                    "error":         False,
                }
    except Exception:
        return {"error": True}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ⌨️  SHARED RESULT KEYBOARD  — coloured (mst.py style)
#
#   Used by b3.py, chk.py, and any other checker module.
#   Trial users  → blue "BUY PREMIUM" + grey channel link
#   Premium users → blue "Open Bot" + blue "Channel"
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def kb_result(is_premium: bool = False) -> RawMarkup:
    if is_premium:
        return RawMarkup([
            [
                _btn("🤖 Open Bot", url=BOT_LINK,     style="primary"),
                _btn("📢 Channel",  url=CHANNEL_LINK, style="primary"),
            ],
        ])
    return RawMarkup([
        [_btn("💎 BUY PREMIUM — Unlimited Checks", cb="mprice", style="primary")],
        [_btn("📢 @Batcardchk", url=CHANNEL_LINK)],
    ])
