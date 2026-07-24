import os
import json
import random
import aiohttp
from telegram import TelegramObject

# ╔══════════════════════════════════════════════════════╗
# ║              BATMAN BOT — CONFIG FILE                ║
# ║   Edit the values below, then restart your bot.     ║
# ╚══════════════════════════════════════════════════════╝

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔑  BOT CREDENTIALS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8653105443:AAHi9rpt9kSiF9vj_YdvxcmnYXrDCCzilbI")
OWNER_ID  = int(os.environ.get("OWNER_ID", "5502877086"))  # @lucifer2600

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🤖  BOT IDENTITY
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VERSION  = "V4.3"
BOT_NAME = "Batmancardchk"
DEV_LINK = "https://t.me/Batxchk_bot"

BOT_USERNAME  = "Batxchk_bot"
BOT_LINK      = f"https://t.me/{BOT_USERNAME}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📢  CHANNEL & GROUP LINKS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CHANNEL_USERNAME = "@Batcardchk"
GROUP_USERNAME   = "@batcardchkGroup"

CHANNEL_LINK  = "https://t.me/Batcardchk"
GROUP_LINK    = "https://t.me/batcardchkGroup"
SUPPORT_LINK  = "https://t.me/+Gjwke5Yc1ddhYmZk"

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
API_TIMEOUT      = 240
REFERRAL_CREDITS = 150
LOCK_FILE        = "/tmp/batman_bot.lock"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔗  GATE API URLS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GATE_URLS: dict[str, str] = {
    "chk":  "https://stripe-auth-test-production.up.railway.app/st0",
    "pp":   "https://pp-auth-test-production.up.railway.app/pp",
    "sh":   "https://goshopi.up.railway.app/shopii",
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
    "sh":   "aloracosmetics.myshopify.com",
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
PROG_LIVE_EMOJI_ID     = "6267225207560214192"   # ← fixed (was same as CHARGED)
PROG_DEAD_EMOJI_ID     = "4958526153955476488"
PROG_ERRORS_EMOJI_ID   = "4956611513369494230"
PROG_CHARGED_EMOJI_ID  = "5427168083074628963"   # 💎 charged

BTN_ALL_EMOJI_ID       = "4956324463525233747"
BTN_STOP_EMOJI_ID      = "6179444193518162239"
BTN_CHARGED_EMOJI_ID   = "5465465194056525619"   # 💎 charged button (reference)
BTN_LIVE_EMOJI_ID      = "5039793437776282663"   # ✅ live button (fixed)

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
    """Returns a <tg-emoji> HTML tag for Telegram Premium custom emoji.
    Animates for Premium users; shows the fallback glyph for non-Premium users.
    Always use parse_mode='HTML' when sending messages that contain these tags."""
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
E_CHARGED  = tg_emoji(PROG_CHARGED_EMOJI_ID,  "💎")
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

class RawMarkup(TelegramObject):
    """Coloured inline keyboard — passes style/icon_custom_emoji_id through PTB's encoder."""
    __slots__ = ("_data",)

    def __init__(self, inline_keyboard: list):
        super().__init__()
        self._data = {"inline_keyboard": inline_keyboard}

    def to_dict(self, api_kwargs=None) -> dict:
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
# 🔍  BIN LOOKUP  — 5-API waterfall + in-memory cache
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_BIN_CACHE: dict = {}   # bin6 → result dict (populated on first successful hit)

def _flag(alpha2: str) -> str:
    """Convert ISO 2-letter country code to flag emoji."""
    a = (alpha2 or "").strip().upper()
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in a) if len(a) == 2 else ""

def _bin_has_data(r: dict) -> bool:
    """Accept a BIN result if at least one meaningful field is non-N/A."""
    if not r:
        return False
    for k in ("scheme", "bank", "country"):
        v = r.get(k, "N/A")
        if v and str(v).strip().upper() not in ("", "N/A", "NONE", "NULL", "UNKNOWN"):
            return True
    return False


async def _bin_binlist(session: aiohttp.ClientSession, bin6: str) -> dict:
    """Primary: lookup.binlist.net"""
    async with session.get(
        f"https://lookup.binlist.net/{bin6}",
        headers={"Accept-Version": "3", "User-Agent": "Mozilla/5.0"},
        timeout=aiohttp.ClientTimeout(total=6),
    ) as r:
        if r.status != 200:
            return {}
        d       = await r.json(content_type=None)
        country = d.get("country") or {}
        bank    = d.get("bank")    or {}
        alpha2  = (country.get("alpha2") or "").upper()
        name    = country.get("name", "")
        return {
            "scheme":        (d.get("scheme") or "N/A").upper(),
            "type":          (d.get("type")   or "N/A").upper(),
            "bank":          bank.get("name", "N/A") or "N/A",
            "country":       name or "N/A",
            "country_emoji": _flag(alpha2),
        }


async def _bin_handyapi(session: aiohttp.ClientSession, bin6: str) -> dict:
    """Fallback 1: data.handyapi.com (free, no key)"""
    async with session.get(
        f"https://data.handyapi.com/bin/{bin6}",
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=aiohttp.ClientTimeout(total=6),
    ) as r:
        if r.status != 200:
            return {}
        d = await r.json(content_type=None)
        if d.get("Status", "").upper() != "SUCCESS":
            return {}
        co = d.get("Country") or {}
        return {
            "scheme":        (d.get("Scheme") or "N/A").upper(),
            "type":          (d.get("Type")   or "N/A").upper(),
            "bank":          d.get("Issuer", "N/A") or "N/A",
            "country":       co.get("Name", "N/A") or "N/A",
            "country_emoji": _flag(co.get("A2", "")),
        }


async def _bin_bincodes(session: aiohttp.ClientSession, bin6: str) -> dict:
    """Fallback 2: api.bincodes.com (free tier, no key needed for basic)"""
    async with session.get(
        f"https://api.bincodes.com/bin/?format=json&api_key=free&bin={bin6}",
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=aiohttp.ClientTimeout(total=6),
    ) as r:
        if r.status != 200:
            return {}
        d = await r.json(content_type=None)
        if str(d.get("valid", "false")).lower() != "true":
            return {}
        return {
            "scheme":        (d.get("brand",   "N/A") or "N/A").upper(),
            "type":          (d.get("type",    "N/A") or "N/A").upper(),
            "bank":          d.get("issuer",   "N/A") or "N/A",
            "country":       d.get("country",  "N/A") or "N/A",
            "country_emoji": _flag(d.get("country_code", "")),
        }


async def _bin_bincheck(session: aiohttp.ClientSession, bin6: str) -> dict:
    """Fallback 3: api.bincheck.io (free, no key)"""
    async with session.get(
        f"https://api.bincheck.io/api/{bin6}",
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=aiohttp.ClientTimeout(total=7),
    ) as r:
        if r.status != 200:
            return {}
        d = await r.json(content_type=None)
        if not d or d.get("valid") is False:
            return {}
        country = d.get("country_name") or d.get("country") or "N/A"
        alpha2  = d.get("country_code", "")
        return {
            "scheme":        (d.get("scheme") or d.get("brand") or "N/A").upper(),
            "type":          (d.get("type")   or "N/A").upper(),
            "bank":          d.get("bank") or d.get("bank_name") or "N/A",
            "country":       country,
            "country_emoji": _flag(alpha2),
        }


async def _bin_antipublic(session: aiohttp.ClientSession, bin6: str) -> dict:
    """Fallback 4: bins.antipublic.one (free, no key)"""
    async with session.get(
        f"https://bins.antipublic.one/bins/{bin6}",
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=aiohttp.ClientTimeout(total=7),
    ) as r:
        if r.status != 200:
            return {}
        d = await r.json(content_type=None)
        if not d:
            return {}
        alpha2 = d.get("country_alpha2") or d.get("country") or ""
        return {
            "scheme":        (d.get("scheme") or d.get("brand") or "N/A").upper(),
            "type":          (d.get("type")   or "N/A").upper(),
            "bank":          d.get("bank") or d.get("bank_name") or "N/A",
            "country":       d.get("country_name") or d.get("country") or "N/A",
            "country_emoji": _flag(alpha2[:2] if alpha2 else ""),
        }


async def get_bin_info(bin_num: str) -> dict:
    """Fetch BIN details — 5-API waterfall with cache. Returns first usable hit."""
    bin6 = str(bin_num).strip()[:6]
    if not bin6.isdigit() or len(bin6) < 6:
        return {"error": True}

    # Return cached result if available
    if bin6 in _BIN_CACHE:
        return _BIN_CACHE[bin6]

    _empty = {"scheme": "N/A", "type": "N/A", "bank": "N/A",
              "country": "N/A", "country_emoji": "", "error": False}

    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        for _fn in (_bin_binlist, _bin_handyapi, _bin_bincodes,
                    _bin_bincheck, _bin_antipublic):
            try:
                result = await _fn(session, bin6)
                if _bin_has_data(result):
                    result["error"] = False
                    _BIN_CACHE[bin6] = result  # cache successful result
                    return result
            except Exception:
                continue

    return _empty

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
                _btn("Open Bot", url=BOT_LINK,     style="primary"),
                _btn("Channel",  url=CHANNEL_LINK, style="primary"),
            ],
        ])
    return RawMarkup([
        [_btn("BUY PREMIUM", cb="mprice", style="primary")],
        [_btn("@Batcardchk", url=CHANNEL_LINK)],
    ])
