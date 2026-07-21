import asyncio
import random
import re
import logging
import aiohttp
import time
import string
import os
import psycopg2.extras
from datetime import datetime
from typing import Optional, Tuple, List
from io import BytesIO
from html import escape as html_escape

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AIOGRAM IMPORTS
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
# CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

HIT_LOG_GROUP_ID               = -1004398328329
EXTRA_CHARGED_GROUP_ID         = -1003991915326
CHANNEL_LINK                   = "https://t.me/Batcardchk"
BUTTON_LOCK_SECONDS            = 30

PROGRESS_UPDATE_INTERVAL       = 5.0
CARDS_PER_PROGRESS_UPDATE      = 10
SESSION_CLEANUP_SECONDS        = 1800
COMPLETED_SESSION_KEEP_SECONDS = 86400

MAX_CONCURRENT_CARDS           = 10
CARD_TIMEOUT_SECONDS           = 180

STRIPE_GATE_API_URL = "https://cardx.up.railway.app/stripe/cc={card}"

MST_SESSIONS           = {}
MST_COMPLETED_SESSIONS = {}
MST_SESSION_LOCKS      = {}
MST_TASKS              = {}

router = Router()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EMOJI IDS  — msh.py style
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DECLINED_EMOJI_ID = "4956612582816351459"
CARD_EMOJI_ID     = "5800709991627232190"
USER_EMOJI_ID     = "4958689671950369798"
TIME_EMOJI_ID     = "5382194935057372936"
DEV_EMOJI_ID      = "6267091732861555879"
PRO_EMOJI_ID      = "6298678524379137990"

# Hit-log emojis
HIT_RESP_EMOJI_ID = "5839116473951328489"

# Progress-message emojis
PROG_GATE_EMOJI_ID     = "5341715473882955310"
PROG_PROGRESS_EMOJI_ID = "5258113901106580375"
PROG_LIVE_EMOJI_ID     = "5427168083074628963"
PROG_DEAD_EMOJI_ID     = "4958526153955476488"
PROG_ERRORS_EMOJI_ID   = "4956611513369494230"

# Button emoji IDs
BTN_ALL_EMOJI_ID  = "4956324463525233747"
BTN_STOP_EMOJI_ID = "6179444193518162239"

# Pool of live emoji IDs (random one shown per live hit)
LIVE_EMOJI_IDS = [
    "5801154993188770160", "4956739572114392015", "5285221724634239278",
    "5287777298894835685", "5285024405246725814", "5287547831677112267",
    "5287658362660474522", "5285186510197381130", "5803233241963959320",
    "5462902520215002477", "5787435351521889877", "5323674506705785412",
    "5801005158959683238", "5436143465211640305", "5800688138833629633",
    "5891044423856296980", "5436068999068662274", "5427168083074628963",
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PLAN EMOJIS
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
# STATUS MAPPINGS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STATUS_APPROVED = "approved"   # API value — do not change
STATUS_DECLINED = "declined"
STATUS_ERROR    = "error"
STATUS_TIMEOUT  = "timeout"

STATUS_DISPLAY_MAP = {
    STATUS_APPROVED: "Live ✅",
    STATUS_DECLINED: "Declined ❌",
    STATUS_ERROR:    "Error ⚠️",
    STATUS_TIMEOUT:  "Timeout ⏱️",
}

ERROR_STATUSES    = {STATUS_ERROR, STATUS_TIMEOUT}
HIT_STATUSES      = {STATUS_APPROVED}
DECLINED_STATUSES = {STATUS_DECLINED}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CALLBACK DATA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class MstResultCallback(CallbackData, prefix="mstr"):
    session_id:  str
    result_type: str

class MstStopCallback(CallbackData, prefix="msts"):
    session_id: str

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
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def safe_html(text: str) -> str:
    if not text:
        return "N/A"
    return html_escape(str(text))

def get_random_live_emoji() -> str:
    return random.choice(LIVE_EMOJI_IDS)

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

def get_status_display(status: str) -> str:
    return STATUS_DISPLAY_MAP.get(status.lower(), "Unknown ❓")

def build_user_link(user_obj) -> str:
    name = safe_html(user_obj.first_name or "User")
    if user_obj.username:
        return f'<a href="https://t.me/{user_obj.username}">{name}</a>'
    return f'<a href="tg://user?id={user_obj.id}">{name}</a>'

def log_hit_to_mst(user_id, username, first_name):
    try:
        with open("mst.txt", "a", encoding="utf-8") as f:
            u_name = username if username else "None"
            f_name = first_name if first_name else "Unknown"
            f.write(f"{user_id}|{u_name}|{f_name}\n")
    except Exception as e:
        logging.error(f"Error writing to mst.txt: {e}")

def is_session_stopped(session_id: str) -> bool:
    session = MST_SESSIONS.get(session_id)
    if not session: return True
    return session.get('status') == "STOPPED"

def is_buttons_locked(session_id: str) -> bool:
    session = MST_SESSIONS.get(session_id)
    if not session:
        completed = MST_COMPLETED_SESSIONS.get(session_id)
        if not completed: return False
        return False
    elapsed = time.time() - session.get('start_time', 0)
    return elapsed < BUTTON_LOCK_SECONDS

def get_remaining_lock(session_id: str) -> int:
    session = MST_SESSIONS.get(session_id)
    if not session: return 0
    elapsed   = time.time() - session.get('start_time', 0)
    remaining = BUTTON_LOCK_SECONDS - elapsed
    return max(0, int(remaining) + 1)

def get_session_data(session_id: str) -> Optional[dict]:
    session = MST_SESSIONS.get(session_id)
    if session: return session
    return MST_COMPLETED_SESSIONS.get(session_id)

def luhn_check(card_number: str) -> bool:
    card_number = str(card_number).strip()
    if not card_number.isdigit(): return False
    total = 0
    reverse_digits = card_number[::-1]
    for i, char in enumerate(reverse_digits):
        digit = int(char)
        if i % 2 == 1:
            digit *= 2
            if digit > 9: digit -= 9
        total += digit
    return total % 10 == 0

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CARD EXTRACTION
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
        matches = re.findall(pattern, text)
        for match in matches:
            if len(match) == 4:
                card_number, month, year, cvv = match
                month = month.zfill(2)
                if len(year) == 4: year = year[2:]
                card_string = f"{card_number}|{month}|{year}|{cvv}"
                if card_string not in cards:
                    cards.append(card_string)
    return cards

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PLAN FETCHING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def get_user_plan_info(user_id):
    """Returns (plan_name, plan_emoji_id)."""
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
        return plan_name, plan_emoji_id
    return "TRIAL", PRO_EMOJI_ID

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STRIPE GATE API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def check_stripe_gate(card: str) -> dict:
    url = STRIPE_GATE_API_URL.format(card=card)
    try:
        timeout = aiohttp.ClientTimeout(total=CARD_TIMEOUT_SECONDS)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "status":   data.get("status", "error").lower(),
                        "response": data.get("response", "Unknown Error")
                    }
                else:
                    logging.error(f"[MST] API returned HTTP {response.status}")
                    return {"status": "error", "response": f"API Error (HTTP {response.status})"}
    except asyncio.TimeoutError:
        logging.error(f"[MST] API Request Timed Out for {card[:6]}****")
        return {"status": "error", "response": "Connection Timed Out"}
    except aiohttp.ClientError as e:
        logging.error(f"[MST] API Connection Error: {e}")
        return {"status": "error", "response": f"Connection Failed: {str(e)[:50]}"}
    except Exception as e:
        logging.error(f"[MST] Unexpected API Error: {e}")
        return {"status": "error", "response": "Unexpected Error"}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SESSION CLEANUP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_cleanup_task_started = False

async def _start_cleanup_if_needed():
    global _cleanup_task_started
    if not _cleanup_task_started:
        _cleanup_task_started = True
        asyncio.create_task(session_cleanup_task())

async def session_cleanup_task():
    while True:
        try:
            await asyncio.sleep(60)
            current_time = time.time()

            active_to_remove = []
            for session_id, session in list(MST_SESSIONS.items()):
                if session.get('status') in ["FINISHED", "STOPPED"]:
                    end_time = session.get('end_time') or session.get('start_time') or current_time
                    try:
                        end_time_float = float(end_time)
                    except (TypeError, ValueError):
                        end_time_float = current_time
                    if current_time - end_time_float > SESSION_CLEANUP_SECONDS:
                        active_to_remove.append(session_id)

            for session_id in active_to_remove:
                logging.info(f"[MST] Moving active session to completed: {session_id}")
                session = MST_SESSIONS.get(session_id)
                if session:
                    MST_COMPLETED_SESSIONS[session_id] = {
                        'user_id':     session.get('user_id'),
                        'chat_id':     session.get('chat_id'),
                        'msg_id':      session.get('msg_id'),
                        'user_msg_id': session.get('user_msg_id'),
                        'total':       session.get('total', 0),
                        'checked':     session.get('checked', 0),
                        'live':        session.get('live', 0),
                        'dead':        session.get('dead', 0),
                        'errors':      session.get('errors', 0),
                        'status':      session.get('status'),
                        'end_time':    session.get('end_time') or current_time,
                        'live_cards':  session.get('live_cards', []),
                        'dead_cards':  session.get('dead_cards', []),
                        'error_cards': session.get('error_cards', []),
                        'user_obj':    session.get('user_obj'),
                        'plan_name':   session.get('plan_name', 'TRIAL'),
                        'completed_at': current_time
                    }
                MST_SESSIONS.pop(session_id, None)
                MST_SESSION_LOCKS.pop(session_id, None)
                MST_TASKS.pop(session_id, None)

            completed_to_remove = []
            for session_id, session in list(MST_COMPLETED_SESSIONS.items()):
                completed_at = session.get('completed_at') or current_time
                try:
                    completed_at_float = float(completed_at)
                except (TypeError, ValueError):
                    completed_at_float = current_time
                if current_time - completed_at_float > COMPLETED_SESSION_KEEP_SECONDS:
                    completed_to_remove.append(session_id)

            for session_id in completed_to_remove:
                logging.info(f"[MST] Removing old completed session: {session_id}")
                MST_COMPLETED_SESSIONS.pop(session_id, None)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logging.error(f"[MST] Error in cleanup task: {e}", exc_info=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESULT FILE GENERATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def generate_result_file(session: dict, result_type: str, user_obj, plan_name: str) -> Tuple[BytesIO, str, int]:
    if result_type == "live":
        cards_list, type_label = session.get('live_cards', []), "Live"
    elif result_type == "dead":
        cards_list, type_label = session.get('dead_cards', []),  "Dead"
    else:
        cards_list = (
            session.get('live_cards', []) + session.get('dead_cards', []) +
            session.get('error_cards', [])
        )
        type_label = "All"

    name  = (user_obj.first_name or "User") if user_obj else "User"
    lines = [
        f"Gate ➳ Stripe | 0$",
        f"Result ➳ {type_label}",
        f"Total ➳ {len(cards_list)}",
        "━━━━━━━━━━━━━━",
    ]

    for card_data in cards_list:
        cc            = card_data.get('card', 'N/A')
        response      = card_data.get('response', 'N/A')
        actual_status = card_data.get('status', 'unknown').lower()
        status        = get_status_display(actual_status)
        bin_info      = card_data.get('bin_info', {})
        scheme        = bin_info.get('scheme', 'N/A')
        bank          = bin_info.get('bank', 'N/A')
        country       = bin_info.get('country', 'N/A')
        flag          = bin_info.get('country_emoji', '')
        country_display = f"{flag} {country}" if flag else country

        lines += [
            f"Card ➳ {cc}",
            f"Status ➳ {status}",
            f"Gate ➳ Stripe | 0$",
            f"Resp ➳ {response}",
            f"Brand ➳ {scheme}",
            f"Issuer ➳ {bank}",
            f"Country ➳ {country_display}",
            f"User ➳ {name} ({plan_name})",
            f"Pro ➳ Batamanchk",
            "━━━━━━━━━━━━━━",
        ]

    content     = "\n".join(lines)
    file_buffer = BytesIO(content.encode('utf-8'))
    file_buffer.seek(0)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    type_map  = {"live": "LIVE", "dead": "DEAD", "all": "ALL"}
    filename  = f"BATAMANCHK_STRIPE_{type_map.get(result_type, 'ALL')}_{timestamp}.txt"
    return file_buffer, filename, len(cards_list)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HIT LOG TO GROUP  (msh.py style)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def send_hit_log_to_group(bot: Bot, response_msg: str, user_obj, plan_name: str):
    await HIT_LOG_RATE_LIMITER.wait_if_needed()
    user_link     = build_user_link(user_obj)
    plan_emoji_id = get_plan_emoji_id(plan_name)
    live_emoji_id = get_random_live_emoji()
    safe_resp     = safe_html(response_msg)

    status_line = (
        f'<b><a href="{CHANNEL_LINK}">[❆]</a> LIVE '
        f'<tg-emoji emoji-id="{live_emoji_id}">✅</tg-emoji></b>'
    )
    gate_line = '<b>Stripe • 0$</b>'
    resp_line = (
        f'<b><tg-emoji emoji-id="{HIT_RESP_EMOJI_ID}">✅</tg-emoji> '
        f'{safe_resp}</b>'
    )

    caption = (
        f'{status_line}\n'
        f'<b>────────────</b>\n'
        f'{gate_line}\n'
        f'{resp_line}\n'
        f'<b>────────────</b>\n'
        f'<b>{user_link} '
        f'<tg-emoji emoji-id="{plan_emoji_id}">⭐</tg-emoji></b>'
    )
    try:
        await bot.send_message(
            chat_id=HIT_LOG_GROUP_ID, text=caption,
            parse_mode="HTML", disable_web_page_preview=True
        )
    except Exception as e:
        logging.error(f"[MST] Error sending hit log: {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HIT DM TO USER  (msh.py style, replies to command)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _build_hit_dm(
    cc_formatted: str, response_msg: str, bin_data: dict,
    elapsed_s: float, user_obj, plan_name: str
) -> str:
    bin_scheme    = bin_data.get("scheme", "N/A")
    bin_bank      = bin_data.get("bank", "N/A")
    country_name  = bin_data.get("country", "N/A")
    country_flag  = bin_data.get("country_emoji", "")
    bin_country   = f"{country_flag} {country_name}" if country_flag else country_name
    bin_info_str  = safe_html(f"{bin_scheme} - {bin_bank} - {bin_country}")
    plan_emoji_id = get_plan_emoji_id(plan_name)
    user_link     = build_user_link(user_obj)
    dev_link      = '<a href="https://t.me/Batcardchk">Batamanchk</a>'
    safe_resp     = safe_html(response_msg)
    live_emoji_id = get_random_live_emoji()
    time_str      = f"{int(elapsed_s)}s" if elapsed_s < 60 else f"{int(elapsed_s//60)}m {int(elapsed_s%60)}s"

    status_line = (
        f'<b><a href="{CHANNEL_LINK}">[❆]</a> Live '
        f'<tg-emoji emoji-id="{live_emoji_id}">✅</tg-emoji></b>'
    )

    return (
        f'{status_line}\n'
        f'\n'
        f'<b><tg-emoji emoji-id="{CARD_EMOJI_ID}">💳</tg-emoji></b>\n'
        f'<b>   ⤷ <code>{cc_formatted}</code></b>\n'
        f'<b>Gate ➳ Stripe | 0$</b>\n'
        f'<b>──────────</b>\n'
        f'<b>Resp ➳ {safe_resp}</b>\n'
        f'<b>Bin ➳ <code>{bin_info_str}</code></b>\n'
        f'<b>──────────</b>\n'
        f'<b><tg-emoji emoji-id="{TIME_EMOJI_ID}">⏱</tg-emoji> ➳ {time_str}</b>\n'
        f'<b><tg-emoji emoji-id="{USER_EMOJI_ID}">👤</tg-emoji> ➳ {user_link} '
        f'<tg-emoji emoji-id="{plan_emoji_id}">⭐</tg-emoji></b>\n'
        f'<b><tg-emoji emoji-id="{DEV_EMOJI_ID}">⚡</tg-emoji> ➳ {dev_link} '
        f'<tg-emoji emoji-id="{PRO_EMOJI_ID}">⭐</tg-emoji></b>'
    )


async def send_user_hit_notification(bot: Bot, session_data: dict, cc_formatted: str, cc_num: str,
                                      response_msg: str, user_obj, plan_name: str, elapsed_s: float = 0.0):
    await USER_DM_RATE_LIMITER.wait_if_needed()
    try:
        try:
            bin_data = await asyncio.wait_for(get_bin_info(cc_num[:6]), timeout=10)
        except Exception:
            bin_data = {}

        caption     = _build_hit_dm(cc_formatted, response_msg, bin_data, elapsed_s, user_obj, plan_name)
        user_msg_id = session_data.get('user_msg_id')   # original /mst command message

        try:
            await bot.send_message(
                chat_id=user_obj.id, text=caption,
                parse_mode="HTML", disable_web_page_preview=True,
                reply_to_message_id=user_msg_id,
            )
        except (TelegramForbiddenError, TelegramBadRequest) as e:
            logging.warning(f"[MST] Could not DM hit to user {user_obj.id}: {e}")
            try:
                await bot.send_message(
                    chat_id=session_data['chat_id'], text=caption,
                    parse_mode="HTML", disable_web_page_preview=True,
                    reply_to_message_id=user_msg_id,
                )
            except Exception:
                pass
    except Exception as e:
        logging.error(f"[MST] Error sending user HIT message: {e}")


async def send_live_to_extra_group(bot: Bot, cc_formatted: str, cc_num: str,
                                    response_msg: str, bin_data: dict,
                                    user_obj, plan_name: str, elapsed_s: float = 0.0):
    await asyncio.sleep(0.5)
    await EXTRA_GROUP_RATE_LIMITER.wait_if_needed()
    try:
        plan_emoji_id = get_plan_emoji_id(plan_name)
        user_link     = build_user_link(user_obj)
        live_emoji_id = get_random_live_emoji()
        safe_resp     = safe_html(response_msg)
        bin_scheme    = bin_data.get("scheme", "N/A")
        bin_bank      = bin_data.get("bank", "N/A")
        country_name  = bin_data.get("country", "N/A")
        country_flag  = bin_data.get("country_emoji", "")
        bin_country   = f"{country_flag} {country_name}" if country_flag else country_name
        bin_info_str  = safe_html(f"{bin_scheme} - {bin_bank} - {bin_country}")
        time_str      = f"{int(elapsed_s)}s" if elapsed_s < 60 else f"{int(elapsed_s//60)}m {int(elapsed_s%60)}s"

        caption = (
            f'<b><a href="{CHANNEL_LINK}">[❆]</a> Live '
            f'<tg-emoji emoji-id="{live_emoji_id}">✅</tg-emoji></b>\n'
            f'\n'
            f'<b><tg-emoji emoji-id="{CARD_EMOJI_ID}">💳</tg-emoji></b>\n'
            f'<b>   ⤷ <code>{cc_formatted}</code></b>\n'
            f'<b>Gate ➳ Stripe | 0$</b>\n'
            f'<b>──────────</b>\n'
            f'<b>Resp ➳ {safe_resp}</b>\n'
            f'<b>Bin ➳ <code>{bin_info_str}</code></b>\n'
            f'<b>──────────</b>\n'
            f'<b><tg-emoji emoji-id="{TIME_EMOJI_ID}">⏱</tg-emoji> ➳ {time_str}</b>\n'
            f'<b><tg-emoji emoji-id="{USER_EMOJI_ID}">👤</tg-emoji> ➳ {user_link} '
            f'<tg-emoji emoji-id="{plan_emoji_id}">⭐</tg-emoji></b>'
        )

        await bot.send_message(
            chat_id=EXTRA_CHARGED_GROUP_ID, text=caption,
            parse_mode="HTML", disable_web_page_preview=True
        )
    except Exception as e:
        logging.error(f"[MST] Error sending to extra group: {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BUTTONS  — All + Stop only
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_result_buttons(session_id: str, is_running: bool = True) -> dict:
    session = get_session_data(session_id) or {}
    checked = session.get('checked', 0)

    buttons = [
        [
            {"text": f"All ({checked})", "callback_data": MstResultCallback(session_id=session_id, result_type="all").pack(), "style": "primary", "icon_custom_emoji_id": BTN_ALL_EMOJI_ID},
        ],
    ]
    if is_running:
        buttons.append([
            {"text": "Stop", "callback_data": MstStopCallback(session_id=session_id).pack(), "style": "danger", "icon_custom_emoji_id": BTN_STOP_EMOJI_ID}
        ])
    return {"inline_keyboard": buttons}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROGRESS MESSAGE  (msh.py style)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _build_progress_text(session: dict) -> str:
    elapsed  = time.time() - session['start_time']
    minutes  = int(elapsed // 60)
    seconds  = int(elapsed % 60)
    time_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"

    user_obj      = session.get('user_obj')
    plan_emoji_id = session.get('plan_emoji_id', PRO_EMOJI_ID)
    user_link     = build_user_link(user_obj) if user_obj else "User"
    dev_link      = '<a href="https://t.me/Batcardchk">Batamanchk</a>'

    return (
        f'<b><tg-emoji emoji-id="{PROG_GATE_EMOJI_ID}">🛒</tg-emoji> Gate ➳ Stripe | 0$</b>\n'
        f'<b><tg-emoji emoji-id="{PROG_PROGRESS_EMOJI_ID}">🔄</tg-emoji> Progress ➳ {session["checked"]}/{session["total"]}</b>\n'
        f'<b>Live ➳ {session["live"]} <tg-emoji emoji-id="{PROG_LIVE_EMOJI_ID}">✅</tg-emoji></b>\n'
        f'<b>Dead ➳ {session["dead"]} <tg-emoji emoji-id="{PROG_DEAD_EMOJI_ID}">❌</tg-emoji></b>\n'
        f'<b>Errors ➳ {session["errors"]} <tg-emoji emoji-id="{PROG_ERRORS_EMOJI_ID}">⚠️</tg-emoji></b>\n'
        f'<b>Time ➳ {time_str}</b>\n'
        f'<b><tg-emoji emoji-id="{USER_EMOJI_ID}">👤</tg-emoji> ➳ {user_link} '
        f'<tg-emoji emoji-id="{plan_emoji_id}">⭐</tg-emoji></b>\n'
        f'<b><tg-emoji emoji-id="{DEV_EMOJI_ID}">⚡</tg-emoji> ➳ {dev_link} '
        f'<tg-emoji emoji-id="{PRO_EMOJI_ID}">⭐</tg-emoji></b>'
    )


async def update_progress_message(bot: Bot, session_id: str, force_update: bool = False):
    session = MST_SESSIONS.get(session_id)
    if not session:
        return

    now         = time.time()
    last_update = session.get('last_update_time', 0)
    is_finished = session['status'] in ["FINISHED", "STOPPED"]

    if not force_update and not is_finished:
        if (now - last_update) < PROGRESS_UPDATE_INTERVAL:
            return

    text = _build_progress_text(session)
    if session.get('last_text') == text and not force_update:
        return

    if session_id not in MST_SESSION_LOCKS:
        MST_SESSION_LOCKS[session_id] = asyncio.Lock()

    async with MST_SESSION_LOCKS[session_id]:
        session = MST_SESSIONS.get(session_id)
        if not session:
            return
        if session.get('last_text') == text and not force_update:
            return

        is_running   = session['status'] == "CHECKING"
        reply_markup = get_result_buttons(session_id, is_running=is_running)

        await PROGRESS_UPDATE_LIMITER.wait_if_needed()
        try:
            await bot.edit_message_text(
                chat_id=session['chat_id'],
                message_id=session['msg_id'],
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
            session['last_text']        = text
            session['last_update_time'] = now
            logging.debug(f"[MST] Progress updated: {session['checked']}/{session['total']}")
        except TelegramBadRequest as e:
            err_str = str(e).lower()
            if "message is not modified" not in err_str and "message to edit not found" not in err_str:
                logging.error(f"[MST] Error updating progress: {e}")
        except Exception as e:
            logging.error(f"[MST] Error updating progress: {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CALLBACK HANDLERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.callback_query(MstResultCallback.filter())
async def handle_result_callback(callback: types.CallbackQuery, callback_data: MstResultCallback):
    try:
        session_id  = callback_data.session_id
        result_type = callback_data.result_type

        session = get_session_data(session_id)
        if not session:
            await callback.answer("⚠️ Session not found.", show_alert=True); return
        if callback.from_user.id != session.get('user_id'):
            await callback.answer("❌ No permission", show_alert=True); return

        is_active_session = session_id in MST_SESSIONS
        if is_active_session and is_buttons_locked(session_id):
            remaining = get_remaining_lock(session_id)
            await callback.answer(f"⏳ Please wait {remaining}s before using buttons", show_alert=True); return

        if result_type == "live":
            count = len(session.get('live_cards', []))
        elif result_type == "dead":
            count = len(session.get('dead_cards', []))
        else:
            count = (len(session.get('live_cards', [])) + len(session.get('dead_cards', [])) +
                     len(session.get('error_cards', [])))

        if count == 0:
            type_names = {"live": "Live", "dead": "Dead", "all": ""}
            await callback.answer(f"❌ No {type_names.get(result_type, '')} cards found", show_alert=True); return

        await callback.answer("📦 Generating report...", show_alert=False)

        user_obj    = session.get('user_obj')
        plan_name   = session.get('plan_name', 'TRIAL')
        user_msg_id = session.get('user_msg_id')

        file_buffer, filename, total_count = generate_result_file(session, result_type, user_obj, plan_name)
        file_content = file_buffer.read()
        file_buffer.seek(0)

        type_emojis = {"live": "✅", "dead": "❌", "all": "📁"}
        type_labels = {"live": "Live", "dead": "Dead", "all": "All"}
        caption = (
            f"Result ➳ {type_labels.get(result_type, 'All')} {type_emojis.get(result_type, '📁')}\n"
            f"Total ➳ <b>{total_count}</b>\n"
            f"Gate ➳ Stripe | 0$"
        )

        document = types.BufferedInputFile(file=file_content, filename=filename)
        try:
            await callback.bot.send_document(
                chat_id=callback.message.chat.id, document=document,
                caption=caption, parse_mode="HTML", reply_to_message_id=user_msg_id
            )
        except TelegramBadRequest as e:
            if "message to reply not found" in str(e).lower():
                await callback.message.answer_document(document=document, caption=caption, parse_mode="HTML")
            else:
                raise
    except Exception as e:
        logging.error(f"[MST] Error handling result callback: {e}", exc_info=True)
        try:
            await callback.message.answer(f"❌ Error: <code>{str(e)[:50]}</code>", parse_mode="HTML")
        except Exception:
            pass


@router.callback_query(MstStopCallback.filter())
async def handle_stop_callback(callback: types.CallbackQuery, callback_data: MstStopCallback):
    try:
        session_id = callback_data.session_id

        session           = MST_SESSIONS.get(session_id)
        completed_session = MST_COMPLETED_SESSIONS.get(session_id)

        if not session and completed_session:
            await callback.answer("ℹ️ Session already completed", show_alert=True); return
        if not session:
            await callback.answer("⚠️ Session not found", show_alert=True); return
        if callback.from_user.id != session.get('user_id'):
            await callback.answer("❌ No permission", show_alert=True); return
        if is_buttons_locked(session_id):
            remaining = get_remaining_lock(session_id)
            await callback.answer(f"⏳ Please wait {remaining}s before using buttons", show_alert=True); return
        if session['status'] != "CHECKING":
            await callback.answer("ℹ️ Not running", show_alert=True); return

        session['status'] = "STOPPED"
        logging.info(f"🛑 [MST] Stop signal sent for session {session_id}")

        cancelled_count = 0
        for task in session.get('tasks', []):
            if not task.done():
                task.cancel()
                cancelled_count += 1
        main_task = MST_TASKS.get(session_id)
        if main_task and not main_task.done():
            main_task.cancel()
            cancelled_count += 1

        await callback.answer("🛑 Stopping...", show_alert=False)
        logging.info(f"🛑 [MST] Cancelled {cancelled_count} tasks")

        session['last_text'] = ""
        await update_progress_message(callback.bot, session_id, force_update=True)
    except Exception as e:
        logging.error(f"[MST] Error handling stop callback: {e}", exc_info=True)
        try:
            await callback.answer("❌ Error stopping", show_alert=True)
        except Exception:
            pass

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SINGLE CARD PROCESSING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_single_card(session_id, cc_formatted, cc_num, user_id, bot, user_obj, plan_name):
    sess = MST_SESSIONS.get(session_id)
    if not sess or is_session_stopped(session_id):
        return

    result_status = STATUS_ERROR
    response_msg  = "Unknown Error"
    bin_data      = {}
    card_start    = time.time()

    try:
        bin_data = await asyncio.wait_for(get_bin_info(cc_num[:6]), timeout=10)
    except asyncio.TimeoutError:
        bin_data = {}
        logging.warning(f"[MST] BIN lookup timeout for {cc_num[:6]}")
    except Exception:
        bin_data = {}

    sess = MST_SESSIONS.get(session_id)
    if not sess or is_session_stopped(session_id):
        return

    try:
        api_result    = await check_stripe_gate(cc_formatted)
        result_status = api_result.get("status", STATUS_ERROR).lower()
        response_msg  = api_result.get("response", "Unknown Error")
        logging.info(f"[MST] API returned status={result_status} for {cc_formatted}")
    except asyncio.CancelledError:
        raise
    except Exception as e:
        result_status = STATUS_ERROR
        response_msg  = f"Connection Error: {str(e)[:50]}"
        logging.error(f"[MST] API error {cc_formatted}: {e}")

    sess = MST_SESSIONS.get(session_id)
    if not sess or is_session_stopped(session_id):
        return

    elapsed_s = time.time() - card_start
    logging.info(f"[MST] {cc_formatted} | Status: {result_status} | Response: {response_msg}")

    try:
        sess['checked'] += 1
    except (KeyError, TypeError):
        sess = MST_SESSIONS.get(session_id)
        if not sess: return
        sess['checked'] += 1

    card_result_data = {
        'card':      cc_formatted,
        'response':  response_msg,
        'status':    result_status,
        'bin_info':  bin_data,
        'gateway':   'Stripe 0$',
        'timestamp': datetime.now().isoformat()
    }

    is_hit = False

    sess = MST_SESSIONS.get(session_id)
    if not sess or is_session_stopped(session_id):
        return

    try:
        if result_status in ERROR_STATUSES:
            sess['errors'] += 1
            sess.setdefault('error_cards', []).append(card_result_data)
            await asyncio.to_thread(update_user_stats, user_id, False)

        elif result_status == STATUS_APPROVED:
            sess['live'] += 1
            sess.setdefault('live_cards', []).append(card_result_data)
            is_hit = True
            await _handle_live_hit(session_id, user_id, bot, user_obj, plan_name,
                                    response_msg, cc_formatted, cc_num, bin_data, elapsed_s, sess)

        elif result_status in DECLINED_STATUSES:
            sess['dead'] += 1
            sess.setdefault('dead_cards', []).append(card_result_data)
            await asyncio.to_thread(update_user_stats, user_id, False)
            current_credits = await asyncio.to_thread(get_user_credits, user_id)
            if current_credits >= 1:
                await asyncio.to_thread(update_credits, user_id, current_credits - 1)

        else:
            logging.warning(f"[MST] Unknown status '{result_status}' for {cc_formatted}, treating as declined")
            sess['dead'] += 1
            sess.setdefault('dead_cards', []).append(card_result_data)
            await asyncio.to_thread(update_user_stats, user_id, False)

    except (KeyError, TypeError) as e:
        logging.error(f"[MST] Session dict error for {cc_formatted}: {e}")
        return

    should_update = False
    if is_hit:
        should_update = True
        logging.info(f"[MST] 🎯 Forcing progress update due to HIT: {result_status}")

    checked_count = sess.get('checked', 0)
    if checked_count % CARDS_PER_PROGRESS_UPDATE == 0 and checked_count > 0:
        should_update = True
        logging.debug(f"[MST] 📊 Progress update at {checked_count} cards (every {CARDS_PER_PROGRESS_UPDATE})")
    if checked_count >= sess.get('total', 0):
        should_update = True
        logging.debug(f"[MST] 🏁 Final progress update at {checked_count}/{sess.get('total', 0)}")

    if should_update:
        try:
            await update_progress_message(bot, session_id)
        except Exception as e:
            logging.error(f"[MST] Error updating progress after card: {e}")


async def _handle_live_hit(session_id, user_id, bot, user_obj, plan_name,
                            response_msg, cc_formatted, cc_num, bin_data, elapsed_s, sess):
    try:
        await asyncio.to_thread(update_user_stats, user_id, False, True)
        await asyncio.to_thread(log_hit_to_mst, user_id, user_obj.username, user_obj.first_name)

        current_credits = await asyncio.to_thread(get_user_credits, user_id)
        if current_credits >= 1:
            await asyncio.to_thread(update_credits, user_id, current_credits - 1)

        if is_session_stopped(session_id): return

        await send_hit_log_to_group(bot, response_msg, user_obj, plan_name)

        if is_session_stopped(session_id): return

        await send_live_to_extra_group(bot, cc_formatted, cc_num,
                                        response_msg, bin_data, user_obj, plan_name, elapsed_s)

        if is_session_stopped(session_id): return

        await send_user_hit_notification(bot, sess, cc_formatted, cc_num,
                                          response_msg, user_obj, plan_name, elapsed_s)
        await asyncio.sleep(1.0)

    except Exception as e:
        logging.error(f"[MST] Error handling live hit: {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN COMMAND
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/mst"))
async def mst_command(message: types.Message):
    if not await asyncio.to_thread(is_gate_enabled, "mst"):
        await message.reply("🚧 <b>Mass Stripe under maintenance.</b>", parse_mode="HTML")
        return

    user    = message.from_user
    user_id = user.id
    bot     = message.bot

    is_premium, _ = await asyncio.to_thread(get_premium_status, user_id)
    if not is_premium:
        await message.reply(
            "💎 <b>Please upgrade to use this feature.</b>\n\n👉 Use /buy to upgrade.",
            parse_mode="HTML"
        )
        return

    await _start_cleanup_if_needed()

    for sid, sdata in list(MST_SESSIONS.items()):
        if sdata.get('user_id') == user_id and sdata.get('status') == "CHECKING":
            await message.reply(
                "⚠️ <b>Active Session</b>\n\nUse the <b>Stop</b> button to stop it.",
                parse_mode="HTML"
            )
            return

    raw_text = ""
    if len(message.text.split()) > 1:
        raw_text += " ".join(message.text.split()[1:]) + " "
    if message.reply_to_message:
        replied_msg = message.reply_to_message
        if replied_msg.text:      raw_text += replied_msg.text + " "
        elif replied_msg.caption: raw_text += replied_msg.caption + " "

    document = message.document
    if not document and message.reply_to_message and message.reply_to_message.document:
        document = message.reply_to_message.document
    if document:
        if document.file_size > 2 * 1024 * 1024:
            await message.reply("❌ File too large. Max 2MB."); return
        try:
            file    = await bot.get_file(document.file_id)
            byte_io = await bot.download_file(file.file_path)
            raw_text += byte_io.read().decode('utf-8', errors='ignore')
        except Exception as e:
            await message.reply(f"❌ Error reading file: {e}"); return

    if not raw_text.strip():
        await message.reply("❌ <b>No cards found.</b>", parse_mode="HTML"); return

    extracted_cards = extract_cards_from_text(raw_text)
    if not extracted_cards:
        await message.reply("❌ No valid card formats found."); return

    valid_cards     = []
    MAX_VALID_CARDS = 20000
    for card_string in extracted_cards:
        if len(valid_cards) >= MAX_VALID_CARDS: break
        parts = card_string.split('|')
        if len(parts) != 4: continue
        cc, mm, yy, cvv = parts
        if luhn_check(cc):
            valid_cards.append((card_string, cc))

    total_cards = len(valid_cards)
    if total_cards == 0:
        await message.reply("❌ No valid Luhn checked cards found."); return

    current_credits = await asyncio.to_thread(get_user_credits, user_id)
    if current_credits < total_cards:
        await message.reply(
            f"❌ <b>Insufficient Credits</b>\n\n"
            f"You need <b>{total_cards}</b> credits.\n"
            f"Your balance: <b>{current_credits}</b> credits.",
            parse_mode="HTML"
        )
        return

    asyncio.create_task(process_mass_check_background(message, bot, valid_cards, user))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BACKGROUND PROCESSING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_mass_check_background(message: types.Message, bot: Bot,
                                         valid_cards: list, user_obj):
    user_id     = user_obj.id
    chat_id     = message.chat.id
    total_cards = len(valid_cards)

    session_id               = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    plan_name, plan_emoji_id = await get_user_plan_info(user_id)

    user_link = build_user_link(user_obj)
    dev_link  = '<a href="https://t.me/Batcardchk">Batamanchk</a>'

    initial_text = (
        f'<b><tg-emoji emoji-id="{PROG_GATE_EMOJI_ID}">🛒</tg-emoji> Gate ➳ Stripe | 0$</b>\n'
        f'<b><tg-emoji emoji-id="{PROG_PROGRESS_EMOJI_ID}">🔄</tg-emoji> Progress ➳ 0/{total_cards}</b>\n'
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

    MST_SESSIONS[session_id] = {
        "status":           "CHECKING",
        "chat_id":          chat_id,
        "user_id":          user_id,
        "msg_id":           progress_msg.message_id,
        "user_msg_id":      message.message_id,
        "total":            total_cards,
        "checked":          0,
        "live":             0,
        "dead":             0,
        "errors":           0,
        "start_time":       time.time(),
        "end_time":         None,
        "tasks":            [],
        "last_text":        "",
        "last_update_time": 0,
        "live_cards":       [],
        "dead_cards":       [],
        "error_cards":      [],
        "user_obj":         user_obj,
        "plan_name":        plan_name,
        "plan_emoji_id":    plan_emoji_id,
    }

    logging.info(f"🚀 [MST] Started session {session_id} - {total_cards} cards - User: {user_id}")

    task = asyncio.create_task(run_mass_checker(bot, session_id, valid_cards, user_obj, plan_name))
    MST_TASKS[session_id] = task


async def run_mass_checker(bot: Bot, session_id, cards, user_obj, plan_name):
    sess = MST_SESSIONS.get(session_id)
    if not sess:
        logging.error(f"[MST] Session {session_id} not found at start!")
        return

    sem         = asyncio.Semaphore(MAX_CONCURRENT_CARDS)
    total_cards = len(cards)

    logging.info(f"[MST] Session {session_id}: Processing {total_cards} cards with concurrency={MAX_CONCURRENT_CARDS}")

    async def worker(cc_formatted, cc_num):
        if is_session_stopped(session_id): return
        async with sem:
            if is_session_stopped(session_id): return
            try:
                await process_single_card(
                    session_id, cc_formatted, cc_num,
                    sess.get('user_id', user_obj.id),
                    bot, user_obj, plan_name
                )
            except asyncio.CancelledError:
                logging.info(f"🛑 [MST] Task cancelled: {cc_formatted}")
                raise
            except Exception as e:
                if not is_session_stopped(session_id):
                    logging.error(f"[MST] Worker error for {cc_formatted}: {e}")
                    s = MST_SESSIONS.get(session_id)
                    if s:
                        try:
                            s['checked'] += 1
                            s['errors']  += 1
                            if s['checked'] % CARDS_PER_PROGRESS_UPDATE == 0:
                                await update_progress_message(bot, session_id)
                        except Exception:
                            pass

    tasks = []
    for cc_formatted, cc_num in cards:
        if is_session_stopped(session_id):
            logging.info(f"🛑 [MST] Stopped creating tasks - {len(tasks)} created")
            break
        task = asyncio.create_task(worker(cc_formatted, cc_num))
        tasks.append(task)
        sess['tasks'].append(task)

    logging.info(f"📋 [MST] {len(tasks)} tasks created for session {session_id}")

    if tasks:
        results   = await asyncio.gather(*tasks, return_exceptions=True)
        cancelled = sum(1 for r in results if isinstance(r, asyncio.CancelledError))
        errors    = sum(1 for r in results if isinstance(r, Exception) and not isinstance(r, asyncio.CancelledError))
        if cancelled: logging.info(f"🛑 [MST] {cancelled} tasks cancelled")
        if errors:    logging.error(f"[MST] {errors} tasks failed with exceptions")

    sess = MST_SESSIONS.get(session_id)
    if sess:
        sess['end_time'] = time.time()
        if sess['status'] != "STOPPED":
            sess['status'] = "FINISHED"
        sess['last_text'] = ""
        sess['tasks']     = []

        MST_COMPLETED_SESSIONS[session_id] = {
            'user_id':     sess.get('user_id'),
            'chat_id':     sess.get('chat_id'),
            'msg_id':      sess.get('msg_id'),
            'user_msg_id': sess.get('user_msg_id'),
            'total':       sess.get('total', 0),
            'checked':     sess.get('checked', 0),
            'live':        sess.get('live', 0),
            'dead':        sess.get('dead', 0),
            'errors':      sess.get('errors', 0),
            'status':      sess.get('status'),
            'end_time':    sess.get('end_time', time.time()),
            'live_cards':  sess.get('live_cards', []),
            'dead_cards':  sess.get('dead_cards', []),
            'error_cards': sess.get('error_cards', []),
            'user_obj':    sess.get('user_obj'),
            'plan_name':   sess.get('plan_name', 'TRIAL'),
            'completed_at': time.time()
        }

        try:
            await update_progress_message(bot, session_id, force_update=True)
        except Exception as e:
            logging.error(f"[MST] Error updating final progress: {e}")

        elapsed = sess['end_time'] - sess['start_time']
        logging.info(
            f"🏁 [MST] Session {session_id} {sess['status']} - "
            f"L:{sess['live']} D:{sess['dead']} E:{sess['errors']} "
            f"Checked:{sess['checked']}/{total_cards} Time:{int(elapsed)}s"
        )
    else:
        logging.error(f"[MST] Session {session_id} not found in finally block!")

