import logging
import time
import string
import random
import asyncio
import signal
import os
import fcntl
from typing import Optional
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes,
)
from telegram.error import Conflict, BadRequest, NetworkError
import aiohttp as _aiohttp

from config import (
    BOT_TOKEN, OWNER_ID, CHANNEL_ID, VERSION, DEV_LINK,
    CHANNEL_USERNAME, CHANNEL_LINK, GROUP_LINK, SUPPORT_LINK,
    BOT_LINK, BOT_USERNAME, BOT_PHOTO_URL, BOT_PHOTO,
    API_TIMEOUT, REFERRAL_CREDITS, LOCK_FILE,
    GATE_URLS, GATE_SITES, PREMIUM_GATES, FORCE_CHANNELS,
    get_bin_info, kb_result,
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
MAX_MSG = 4000

# All special chars built from codepoints - ASCII safe source, no copy-paste corruption
ARROW = chr(0x27BA)
SEP   = chr(0x2501) * 17
TAG   = "[ " + chr(0x16977) + "i" + chr(0x0422) + " ]"


def SC(text: str) -> str:
    MAP = {
        'a': chr(0x1D00), 'b': chr(0x0299), 'c': chr(0x1D04), 'd': chr(0x1D05),
        'e': chr(0x1D07), 'f': chr(0xA730), 'g': chr(0x0262), 'h': chr(0x029C),
        'i': chr(0x026A), 'j': chr(0x1D0A), 'k': chr(0x1D0B), 'l': chr(0x029F),
        'm': chr(0x1D0D), 'n': chr(0x0274), 'o': chr(0x1D0F), 'p': chr(0x1D18),
        'q': 'q',         'r': chr(0x0280), 's': chr(0xA731), 't': chr(0x1D1B),
        'u': chr(0x1D1C), 'v': chr(0x1D20), 'w': chr(0x1D21), 'x': 'x',
        'y': chr(0x028F), 'z': chr(0x1D22),
    }
    return ''.join(MAP.get(c.lower(), c) for c in text)


def B(text: str) -> str:
    result = []
    for c in text:
        if 'A' <= c <= 'Z':
            result.append(chr(0x1D5D4 + ord(c) - ord('A')))
        elif 'a' <= c <= 'z':
            result.append(chr(0x1D5EE + ord(c) - ord('a')))
        elif '0' <= c <= '9':
            result.append(chr(0x1D7EC + ord(c) - ord('0')))
        else:
            result.append(c)
    return ''.join(result)


_lock_file_handle = None

def acquire_instance_lock() -> bool:
    global _lock_file_handle
    try:
        _lock_file_handle = open(LOCK_FILE, "w")
        fcntl.flock(_lock_file_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_file_handle.write(str(os.getpid()))
        _lock_file_handle.flush()
        return True
    except (IOError, OSError):
        return False

def release_instance_lock():
    global _lock_file_handle
    if _lock_file_handle:
        try:
            fcntl.flock(_lock_file_handle, fcntl.LOCK_UN)
            _lock_file_handle.close()
            os.unlink(LOCK_FILE)
        except Exception:
            pass
        _lock_file_handle = None


def get_styled_plan(raw_plan: str) -> str:
    p = raw_plan.upper()
    if p == "CORE":  return SC("Core")
    if p == "ELITE": return SC("Elite")
    if p == "ROOT":  return SC("Root")
    return SC("Trial")

def get_plan_icon(raw_plan: str) -> str:
    return "\U0001F451" if raw_plan.upper() in ("CORE", "ELITE", "ROOT") else ""

def get_user_data(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> dict:
    uid = str(user_id)
    if "user_data" not in context.bot_data:
        context.bot_data["user_data"] = {}
    if uid not in context.bot_data["user_data"]:
        context.bot_data["user_data"][uid] = {
            "name": "User", "first_name": "User", "last_name": "",
            "username": "", "language_code": "en",
            "joined":      datetime.now().strftime("%Y-%m-%d %H:%M"),
            "last_active": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "credits": 150, "plan": "TRIAL", "expires": 0,
            "total_refs": 0, "total_checks": 0,
            "approved_checks": 0, "declined_checks": 0,
            "last_gate": "N/A", "last_card": "N/A",
            "codes_redeemed": 0, "keys_redeemed": 0,
        }
    return context.bot_data["user_data"][uid]

def _update_user_meta(ud: dict, user) -> None:
    ud["first_name"]   = user.first_name or "User"
    ud["last_name"]    = user.last_name  or ""
    ud["name"]         = user.full_name  or user.first_name or "User"
    ud["last_active"]  = datetime.now().strftime("%Y-%m-%d %H:%M")
    if user.username:       ud["username"]      = user.username
    if user.language_code:  ud["language_code"] = user.language_code

def gen_code(length: int = 10) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))

def gen_receipt() -> str:
    return "Batman" + str(random.randint(100000, 999999)) + "-CHK"

def is_user_premium(ud: dict) -> bool:
    return ud.get("plan", "TRIAL").upper() != "TRIAL" and ud.get("expires", 0) > time.time()

def get_referral_link(user_id: int) -> str:
    return "https://t.me/" + BOT_USERNAME + "?start=ref_" + str(user_id)

def owner_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user and update.effective_user.id == OWNER_ID:
            return await func(update, context)
    wrapper.__name__ = func.__name__
    return wrapper

def _row(label: str, value: str) -> str:
    return label + " " + ARROW + " " + value

def ui_profile(user, context: ContextTypes.DEFAULT_TYPE) -> str:
    ud       = get_user_data(user.id, context)
    raw_plan = ud.get("plan", "TRIAL").upper()
    expires  = ud.get("expires", 0)
    now      = time.time()
    if raw_plan != "TRIAL" and expires <= now:
        raw_plan = "TRIAL"; ud["plan"] = "TRIAL"; ud["expires"] = 0; expires = 0
    premium    = raw_plan != "TRIAL"
    credits    = "Unlimited" if premium else str(ud.get("credits", 150))
    uname      = ("@" + user.username) if user.username else (user.first_name or "User")
    total_refs = ud.get("total_refs", 0)
    plan_icon  = get_plan_icon(raw_plan)
    lines = [
        TAG + " Batman Card Checker",
        SEP,
        _row(SC("User")    + "    ", uname + (" " + plan_icon if plan_icon else "")),
        _row("ID       ",            "<code>" + str(user.id) + "</code>"),
        _row(SC("Access")  + "  ",   get_styled_plan(raw_plan)),
        _row(SC("Credits") + " ",    credits),
    ]
    if premium and expires > now:
        rem_d = int((expires - now) / 86400)
        rem_h = int(((expires - now) % 86400) / 3600)
        lines.append(_row(SC("Expires") + " ", datetime.fromtimestamp(expires).strftime("%Y-%m-%d %H:%M")))
        lines.append(_row(SC("Left")    + "    ", str(rem_d) + "d " + str(rem_h) + "h"))
        if ud.get("last_receipt"):
            lines.append(_row(SC("Receipt") + " ", "<code>" + ud["last_receipt"] + "</code>"))
    lines.append(_row(SC("Referrals") + " ", str(total_refs) + " (+" + str(total_refs * REFERRAL_CREDITS) + " credits)"))
    lines.append(_row(SC("Joined")  + "  ",  ud.get("joined", "N/A")))
    lines.append(_row(SC("Dev")     + "     ", "<a href='" + DEV_LINK + "'>Batman</a>"))
    lines.append(SEP)
    return "\n".join(lines)

def gate_info_text(gate_name: str, cmd: str, cost: int) -> str:
    return (
        SEP + "\n" + gate_name + "\n" + SEP + "\n\n"
        + _row(SC("Cost"), str(cost) + " Credit(s) per check") + "\n\n"
        + SC("Usage") + ":\n<code>/" + cmd + " cc|mm|yy|cvv</code>\n\n"
        + SC("Example") + ":\n<code>/" + cmd + " 4111111111111111|12|2026|123</code>\n\n"
        + SEP
    )


async def check_force_sub(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> list:
    not_joined = []
    for name, link in FORCE_CHANNELS:
        try:
            m = await context.bot.get_chat_member("@" + name, user_id)
            if m.status in ("left", "kicked"):
                not_joined.append((name, link))
        except Exception:
            not_joined.append((name, link))
    return not_joined

def kb_force_sub(not_joined: list) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(ARROW + " Join @" + n, url=l)] for n, l in not_joined]
    rows.append([InlineKeyboardButton("\u2705 I Joined \u2014 Check Again", callback_data="check_sub")])
    return InlineKeyboardMarkup(rows)


def build_check_result(card_raw, gate_name, raw_response, bin_data,
                        username, plan, time_taken, is_approved,
                        is_timeout=False, is_error=False) -> str:
    if is_timeout:    status = SC("Timeout")
    elif is_error:    status = SC("Error")
    elif is_approved: status = SC("Approved")
    else:             status = SC("Declined")

    bin_txt = "N/A"
    if bin_data and not bin_data.get("error"):
        scheme  = str(bin_data.get("scheme", "N/A")).upper()
        bank    = bin_data.get("bank", "N/A")
        country = str(bin_data.get("country", "N/A")).upper()
        flag    = bin_data.get("country_emoji", "")
        bin_txt = (scheme + " - " + bank + " - " + flag + " " + country).strip()

    return "\n".join([
        TAG + " " + ARROW + " " + status,
        "\U0001F50D " + ARROW + " <code>" + card_raw + "</code>",
        _row(SC("Gate"), gate_name + " \U0001F4B3"),
        _row(SC("Raw"),  raw_response),
        _row(SC("Info"), bin_txt),
        _row(SC("User"), username + " " + get_plan_icon(plan) + " (" + get_styled_plan(plan) + ")"),
        _row(SC("Pro"),  "Batman | " + time_taken + "s"),
    ])


def kb_main(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("CHECKER"),  callback_data="mgates"),
         InlineKeyboardButton(B("BUY NOW"), callback_data="mprice")],
        [InlineKeyboardButton(B("UPDATES") + " " + ARROW, url=CHANNEL_LINK),
         InlineKeyboardButton(B("GROUP")   + " " + ARROW, url=GROUP_LINK)],
        [InlineKeyboardButton("\U0001F517 " + B("REFER & EARN"), callback_data="mrefer")],
        [InlineKeyboardButton(B("SUPPORT") + " " + ARROW, url=SUPPORT_LINK)],
    ])

def kb_back(cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("\U0001F519 " + B("BACK"), callback_data=cb)]])

def kb_price() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("10$ - CORE"),  callback_data="pay10"),
         InlineKeyboardButton(B("15$ - ELITE"), callback_data="pay15"),
         InlineKeyboardButton(B("30$ - ROOT"),  callback_data="pay30")],
        [InlineKeyboardButton(B("SUPPORT") + " " + ARROW, url=SUPPORT_LINK)],
        [InlineKeyboardButton("\U0001F519 " + B("BACK"), callback_data="bmain")],
    ])

def kb_payment() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("SUPPORT") + " " + ARROW, url=SUPPORT_LINK)],
        [InlineKeyboardButton("\U0001F519 " + B("BACK"), callback_data="mprice")],
    ])

def kb_gate_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("AUTH"),   callback_data="mauth"),
         InlineKeyboardButton(B("CHARGE"), callback_data="mcharge"),
         InlineKeyboardButton("\U0001F451 " + B("PREMIUM"), callback_data="mmass")],
        [InlineKeyboardButton("\U0001F519 " + B("BACK"), callback_data="bmain")],
    ])

def kb_auth_gates() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("BRAINTREE"), callback_data="ib3")],
        [InlineKeyboardButton("\U0001F519 " + B("BACK"), callback_data="mgates")],
    ])

def kb_charge_gates() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("STRIPE"),  callback_data="ichk"),
         InlineKeyboardButton(B("PAYPAL"),  callback_data="ipp")],
        [InlineKeyboardButton(B("SHOPIFY"), callback_data="ish"),
         InlineKeyboardButton(B("PAYU"),    callback_data="ipyu")],
        [InlineKeyboardButton("\U0001F519 " + B("BACK"), callback_data="mgates")],
    ])

def kb_premium_gates() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(B("STRIPE AUTH") + " \U0001F451", callback_data="iau")],
        [InlineKeyboardButton(B("STRIPE MASS") + " \U0001F451", callback_data="imss")],
        [InlineKeyboardButton(B("PAYPAL MASS") + " \U0001F451", callback_data="impp2")],
        [InlineKeyboardButton("\U0001F519 " + B("BACK"), callback_data="mgates")],
    ])

def kb_upgrade() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("\U0001F48E " + B("BUY PREMIUM"), callback_data="mprice")],
        [InlineKeyboardButton(B("SUPPORT") + " " + ARROW, url=SUPPORT_LINK)],
    ])

def kb_fb_owner(key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("\u2705 Approve", callback_data="fb_ok_" + key),
        InlineKeyboardButton("\u274C Decline", callback_data="fb_no_" + key),
    ]])


async def process_referral(new_uid: int, referrer_id: int,
                            context: ContextTypes.DEFAULT_TYPE) -> bool:
    if new_uid == referrer_id: return False
    referred_set = context.bot_data.setdefault("referred_users", set())
    if new_uid in referred_set: return False
    ref_ud = context.bot_data.get("user_data", {}).get(str(referrer_id))
    if ref_ud is None: return False
    referred_set.add(new_uid)
    ref_ud["credits"]    = ref_ud.get("credits", 0) + REFERRAL_CREDITS
    ref_ud["total_refs"] = ref_ud.get("total_refs", 0) + 1
    try:
        await context.bot.send_message(
            chat_id=referrer_id,
            text=(TAG + " " + SC("Referral Bonus") + "\n" + SEP + "\n"
                  "Someone joined via your link!\n"
                  + _row(SC("Credits Added"),   "+" + str(REFERRAL_CREDITS)) + "\n"
                  + _row(SC("Total Referrals"), str(ref_ud["total_refs"])) + "\n"
                  + SEP),
        )
    except Exception:
        pass
    return True


async def _api_request(session, url: str, card: str, site: str) -> dict:
    if "{card}" in url:
        url = url.replace("{card}", card)
        async with session.get(url) as r:
            try:    data = await r.json(content_type=None)
            except: data = {"value": await r.text()}
    else:
        async with session.get(url, params={"cc": card, "site": site}) as r:
            try:    data = await r.json(content_type=None)
            except: data = {"value": await r.text()}
    return data if isinstance(data, dict) else {"value": str(data)}

async def process_gate(update: Update, context: ContextTypes.DEFAULT_TYPE,
                       gate_key: str, gate_name: str):
    user = update.effective_user
    if context.bot_data.get("maintenance") and user.id != OWNER_ID:
        await update.message.reply_text("\u2699\uFE0F Bot is under maintenance. Try again later.")
        return
    if not context.bot_data.get(gate_key + "_on", True):
        await update.message.reply_text("Gate [" + gate_name + "] is currently OFF.")
        return

    ud      = get_user_data(user.id, context)
    premium = is_user_premium(ud)
    _update_user_meta(ud, user)

    not_joined = await check_force_sub(user.id, context)
    if not_joined:
        await update.message.reply_text(
            TAG + " " + ARROW + " " + SC("Join Required") + "\n" + SEP + "\n"
            "Join our channels first:\n" + SEP,
            reply_markup=kb_force_sub(not_joined))
        return

    if gate_key in PREMIUM_GATES and not premium:
        await update.message.reply_text(
            TAG + " " + ARROW + " " + SC("Premium Only") + "\n" + SEP + "\n"
            + _row(SC("Gate"), gate_name) + "\n\n"
            "Free: /chk /pp /sh /pyu /b3\nPremium: /au /mss /mpp2\n\nUpgrade: /plan",
            parse_mode="HTML", reply_markup=kb_upgrade())
        return

    card_raw = None
    if context.args:
        card_raw = context.args[0].strip()
    elif update.message.reply_to_message and update.message.reply_to_message.text:
        card_raw = update.message.reply_to_message.text.strip().split()[0]

    if not card_raw:
        await update.message.reply_text(
            SC("Usage") + ": <code>/" + gate_key + " cc|mm|yy|cvv</code>", parse_mode="HTML")
        return

    if not premium:
        credits = ud.get("credits", 0)
        if credits <= 0:
            await update.message.reply_text(
                TAG + " " + ARROW + " No Credits\n" + SEP + "\n"
                "Buy a plan: /plan\nEarn free: /refer",
                reply_markup=kb_upgrade())
            return
        ud["credits"] = credits - 1

    api_url  = context.bot_data.get("gate_url_" + gate_key) or GATE_URLS.get(gate_key, "")
    site_url = GATE_SITES.get(gate_key, "example.com")
    if not api_url:
        await update.message.reply_text(
            "Gate API not set. Use: /seturl " + gate_key + " &lt;url&gt;", parse_mode="HTML")
        return

    msg        = await update.message.reply_text(TAG + " " + ARROW + " " + SC("Scanning") + "...")
    start_time = time.time()
    uname      = ("@" + user.username) if user.username else (user.first_name or "User")
    plan       = ud.get("plan", "TRIAL")

    try:
        timeout = _aiohttp.ClientTimeout(total=API_TIMEOUT)
        async with _aiohttp.ClientSession(timeout=timeout) as session:
            results = await asyncio.gather(
                _api_request(session, api_url, card_raw, site_url),
                get_bin_info(card_raw[:6]),
                return_exceptions=True,
            )
        data     = results[0] if not isinstance(results[0], Exception) else {}
        bin_data = results[1] if not isinstance(results[1], Exception) else {"error": True}
        if isinstance(results[0], Exception): raise results[0]

        raw_response = str(
            data.get("value") or data.get("message") or
            data.get("Response") or data.get("category") or "ERROR"
        ).strip()
        is_approved = any(w in raw_response.lower() for w in
                          ["approved", "captured", "success", "charged", "true"])

        ud["total_checks"] = ud.get("total_checks", 0) + 1
        ud["last_gate"]    = gate_name
        ud["last_card"]    = card_raw[:6] + "xxxxxxxxxx"
        ud["last_active"]  = datetime.now().strftime("%Y-%m-%d %H:%M")
        if is_approved: ud["approved_checks"] = ud.get("approved_checks", 0) + 1
        else:           ud["declined_checks"] = ud.get("declined_checks", 0) + 1

        elapsed = "{:.2f}".format(time.time() - start_time)
        text    = build_check_result(card_raw, gate_name, raw_response, bin_data,
                                     uname, plan, elapsed, is_approved)
        await msg.edit_text(text, parse_mode="HTML",
                            reply_markup=kb_result(), disable_web_page_preview=True)

    except asyncio.TimeoutError:
        if not premium: ud["credits"] = ud.get("credits", 0) + 1
        elapsed = "{:.2f}".format(time.time() - start_time)
        text    = build_check_result(card_raw, gate_name, "Request Timeout", {},
                                     uname, plan, elapsed, False, is_timeout=True)
        await msg.edit_text(text, parse_mode="HTML",
                            reply_markup=kb_result(), disable_web_page_preview=True)
    except Exception as e:
        if not premium: ud["credits"] = ud.get("credits", 0) + 1
        logger.error("Gate [" + gate_key + "] error: " + str(e))
        elapsed = "{:.2f}".format(time.time() - start_time)
        text    = build_check_result(card_raw, gate_name, str(e)[:120], {},
                                     uname, plan, elapsed, False, is_error=True)
        await msg.edit_text(text, parse_mode="HTML",
                            reply_markup=kb_result(), disable_web_page_preview=True)


async def cmd_chk(u, c):  await process_gate(u, c, "chk",  "Stripe Charge")
async def cmd_pp(u, c):   await process_gate(u, c, "pp",   "PayPal Charge")
async def cmd_sh(u, c):   await process_gate(u, c, "sh",   "Shopify Charge")
async def cmd_pyu(u, c):  await process_gate(u, c, "pyu",  "PayU Charge")
async def cmd_b3(u, c):   await process_gate(u, c, "b3",   "Braintree Auth")
async def cmd_au(u, c):   await process_gate(u, c, "au",   "Stripe Auth")
async def cmd_mss(u, c):  await process_gate(u, c, "mss",  "Stripe Mass")
async def cmd_mpp2(u, c): await process_gate(u, c, "mpp2", "PayPal Mass")


async def send_activation_msg(user_id: int, plan: str, days: int,
                               context: ContextTypes.DEFAULT_TYPE) -> str:
    receipt    = gen_receipt()
    expires_ts = time.time() + days * 86400
    ud         = get_user_data(user_id, context)
    ud["plan"]         = plan.upper()
    ud["expires"]      = expires_ts
    ud["last_receipt"] = receipt

    name  = ud.get("name", "Unknown")
    uname = ud.get("username", "")
    try:
        chat  = await context.bot.get_chat(user_id)
        name  = chat.first_name or name
        uname = chat.username or uname
        ud["name"] = name
        if uname: ud["username"] = uname
    except Exception:
        pass

    display = ("@" + uname) if uname else name
    txt = (
        TAG + " " + ARROW + " " + SC("Access Activated") + "\n" + SEP + "\n"
        + _row(SC("User"),    display)    + "\n"
        + _row(SC("Access"),  get_styled_plan(plan) + " \U0001F451") + "\n"
        + _row(SC("Days"),    str(days))  + "\n"
        + _row(SC("Credits"), "Unlimited") + "\n"
        + _row(SC("Expires"), datetime.fromtimestamp(expires_ts).strftime("%Y-%m-%d %H:%M")) + "\n"
        + _row(SC("Receipt"), "<code>" + receipt + "</code>") + "\n"
        + SEP + "\nSave this receipt ID.\n" + SC("Pro") + " " + ARROW + " Batman"
    )
    try:
        await context.bot.send_message(chat_id=user_id, text=txt, parse_mode="HTML")
    except Exception:
        pass
    return receipt

async def resolve_user(target: str, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    target = target.strip().lstrip("@")
    if target.lstrip("-").isdigit():
        return int(target)
    for attempt in ("@" + target, target):
        try:
            return (await context.bot.get_chat(attempt)).id
        except Exception:
            continue
    tl = target.lower()
    for uid_str, ud in context.bot_data.get("user_data", {}).items():
        stored = ud.get("username", "").lower().lstrip("@")
        if stored and stored == tl:
            return int(uid_str)
    return None

async def _grant(uid: int, plan: str, days: int,
                 update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud = get_user_data(uid, context)
    ud["plan"]    = plan
    ud["expires"] = time.time() + days * 86400
    dn  = ud.get("name", "Unknown")
    dun = ud.get("username", "")
    try:
        chat = await context.bot.get_chat(uid)
        dn   = chat.first_name or dn
        if chat.last_name: dn = dn + " " + chat.last_name
        dun  = chat.username or dun
        ud["name"] = dn
        if dun: ud["username"] = dun
    except Exception:
        pass
    receipt    = await send_activation_msg(uid, plan, days, context)
    uname_line = ("@" + dun) if dun else dn
    exp_date   = datetime.fromtimestamp(ud["expires"]).strftime("%Y-%m-%d %H:%M")
    await update.message.reply_text(
        SEP + "\n\u2705 " + SC("Premium Granted") + "\n" + SEP + "\n"
        + _row(SC("User"),    uname_line) + "\n"
        + _row("ID",          "<code>" + str(uid) + "</code>") + "\n"
        + _row(SC("Plan"),    get_styled_plan(plan) + " \U0001F451") + "\n"
        + _row(SC("Days"),    str(days))   + "\n"
        + _row(SC("Expires"), exp_date)    + "\n"
        + _row(SC("Receipt"), "<code>" + receipt + "</code>") + "\n"
        + SEP,
        parse_mode="HTML")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ud   = get_user_data(user.id, context)
    ud.setdefault("joined", datetime.now().strftime("%Y-%m-%d %H:%M"))
    ud.setdefault("name",   user.full_name or user.first_name or "User")
    ud.setdefault("total_refs", 0)
    _update_user_meta(ud, user)
    if context.args and context.args[0].startswith("ref_"):
        try:
            await process_referral(user.id, int(context.args[0][4:]), context)
        except Exception:
            pass
    not_joined = await check_force_sub(user.id, context)
    if not_joined:
        await update.message.reply_text(
            TAG + " " + ARROW + " " + SC("Join Required") + "\n" + SEP + "\n"
            "Join our channels to use the bot:\n" + SEP,
            reply_markup=kb_force_sub(not_joined))
        return
    await update.message.reply_text(
        ui_profile(user, context), parse_mode="HTML",
        reply_markup=kb_main(user.id), disable_web_page_preview=True)

async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t   = time.time()
    msg = await update.message.reply_text(TAG + " " + ARROW + " Pinging...")
    await msg.edit_text(TAG + " " + ARROW + " Pong | " + str(int((time.time() - t) * 1000)) + "ms")

async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        TAG + " Batman Premium Plans\n" + SEP + "\n\n"
        + _row(SC("Access"),  SC("Core"))  + "\n"
        + _row(SC("Days"),    "7")         + "\n"
        + _row(SC("Credits"), "Unlimited") + "\n"
        + _row(SC("Price"),   "10$")       + "\n"
        + SEP + "\n"
        + _row(SC("Access"),  SC("Elite")) + "\n"
        + _row(SC("Days"),    "15")        + "\n"
        + _row(SC("Credits"), "Unlimited") + "\n"
        + _row(SC("Price"),   "15$")       + "\n"
        + SEP + "\n"
        + _row(SC("Access"),  SC("Root"))  + "\n"
        + _row(SC("Days"),    "30")        + "\n"
        + _row(SC("Credits"), "Unlimited") + "\n"
        + _row(SC("Price"),   "30$")       + "\n"
        + SEP,
        reply_markup=kb_price())

async def cmd_refer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user       = update.effective_user
    ud         = get_user_data(user.id, context)
    total_refs = ud.get("total_refs", 0)
    link       = get_referral_link(user.id)
    await update.message.reply_text(
        TAG + " " + SC("Referral") + "\n" + SEP + "\n"
        + _row(SC("Link"),      "<code>" + link + "</code>") + "\n"
        + SEP + "\n"
        + _row(SC("Referrals"), str(total_refs)) + "\n"
        + _row(SC("Earned"),    str(total_refs * REFERRAL_CREDITS) + " credits") + "\n"
        + _row(SC("Per Ref"),   "+" + str(REFERRAL_CREDITS) + " credits") + "\n"
        + SEP + "\nShare your link to earn free credits!",
        parse_mode="HTML", reply_markup=kb_back("bmain"), disable_web_page_preview=True)

async def cmd_rm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            SC("Usage") + ": /rm <code>CODE</code>", parse_mode="HTML")
        return
    code  = context.args[0].upper()
    uid   = update.effective_user.id
    ud    = get_user_data(uid, context)
    codes = context.bot_data.setdefault("codes", {})
    keys  = context.bot_data.setdefault("keys",  {})
    if code in codes and not codes[code]["used"]:
        codes[code]["used"] = True
        ud["credits"] = ud.get("credits", 0) + codes[code]["value"]
        ud["codes_redeemed"] = ud.get("codes_redeemed", 0) + 1
        await update.message.reply_text(
            "\u2705 Redeemed +" + str(codes[code]["value"]) + " credits\n"
            + _row(SC("Credits"), str(ud["credits"])))
    elif code in keys and not keys[code]["used"]:
        keys[code]["used"] = True
        p, d = keys[code]["plan"], keys[code]["days"]
        ud["keys_redeemed"] = ud.get("keys_redeemed", 0) + 1
        receipt = await send_activation_msg(uid, p, d, context)
        await update.message.reply_text(
            "\u2705 Activated " + get_styled_plan(p) + " for " + str(d) + " days!\n"
            + _row(SC("Receipt"), "<code>" + receipt + "</code>"), parse_mode="HTML")
    else:
        await update.message.reply_text("\u274C Invalid or already used code.")

async def cmd_bin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bin_num = context.args[0].strip()[:6] if context.args else ""
    if not bin_num or not bin_num.isdigit() or len(bin_num) < 6:
        await update.message.reply_text(
            SC("Usage") + ": <code>/bin 411111</code>", parse_mode="HTML")
        return
    msg = await update.message.reply_text(TAG + " " + ARROW + " Looking up...")
    bd  = await get_bin_info(bin_num)
    if bd.get("error"):
        await msg.edit_text("\u274C BIN not found.")
        return
    await msg.edit_text(
        TAG + " " + ARROW + " BIN Lookup\n" + SEP + "\n"
        + _row("BIN",     "<code>" + bin_num + "</code>") + "\n"
        + _row("Scheme",  str(bd.get("scheme", "N/A")).upper()) + "\n"
        + _row("Type",    str(bd.get("type",   "N/A")).upper()) + "\n"
        + _row("Bank",    bd.get("bank", "N/A")) + "\n"
        + _row("Country", bd.get("country_emoji", "") + " " + str(bd.get("country", "N/A")).upper()) + "\n"
        + SEP,
        parse_mode="HTML")


def _fb_key(user_id: int) -> str:
    return str(user_id) + "_" + str(int(time.time())) + "_" + str(random.randint(1000, 9999))

async def cmd_fb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.photo or msg.video:
        await handle_fb_media(update, context)
        return
    await msg.reply_text(
        SEP + "\n\U0001F4F8 " + SC("Feedback") + "\n" + SEP + "\n\n"
        "Send a photo or video WITH caption /fb\n\n"
        "Optionally add a note:\n<code>/fb Great service!</code>\n" + SEP,
        parse_mode="HTML")

async def handle_fb_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg  = update.message
    user = update.effective_user
    if msg.photo:
        file_id, file_type = msg.photo[-1].file_id, "photo"
    elif msg.video:
        file_id, file_type = msg.video.file_id, "video"
    else:
        return

    raw_cap   = (msg.caption or "").strip()
    user_note = raw_cap
    bot_un    = context.bot.username or ""
    for prefix in ("/fb@" + bot_un, "/fb"):
        if user_note.lower().startswith(prefix.lower()):
            user_note = user_note[len(prefix):].strip()
            break

    key       = _fb_key(user.id)
    uname     = ("@" + user.username) if user.username else (user.first_name or "User")
    submitted = datetime.now().strftime("%Y-%m-%d %H:%M")

    context.bot_data.setdefault("fb_pending", {})[key] = {
        "file_id": file_id, "file_type": file_type,
        "user_id": user.id, "username": uname,
        "name": user.full_name or user.first_name or "User",
        "note": user_note, "date": submitted,
    }
    await msg.reply_text(
        SEP + "\n" + SC("Feedback Submitted") + " \u2705\n" + SEP + "\n"
        "Under review \u2014 you'll be notified once approved.\n" + SEP)

    cap = (TAG + " " + ARROW + " New Feedback\n" + SEP + "\n"
           + _row(SC("User"), uname) + "\n"
           + _row("ID",  str(user.id)) + "\n"
           + _row(SC("Date"), submitted) + "\n"
           + _row(SC("Type"), file_type.capitalize()) + "\n")
    if user_note:
        cap += _row(SC("Note"), user_note[:200]) + "\n"
    cap += SEP + "\nApprove to post to channel?"
    try:
        send  = context.bot.send_photo if file_type == "photo" else context.bot.send_video
        kwarg = {"photo": file_id} if file_type == "photo" else {"video": file_id}
        await send(chat_id=OWNER_ID, caption=cap, reply_markup=kb_fb_owner(key), **kwarg)
    except Exception as e:
        logger.error("Feedback notify owner failed: " + str(e))

async def _fb_approve(query, context: ContextTypes.DEFAULT_TYPE, key: str):
    fb = context.bot_data.get("fb_pending", {}).get(key)
    if not fb:
        await query.answer("Already handled or not found.", show_alert=True)
        return
    uname, uid     = fb["username"], fb["user_id"]
    file_id, ftype = fb["file_id"], fb["file_type"]
    user_note      = fb.get("note", "")
    submitted      = fb["date"]

    channel_cap = SEP + "\n"
    if user_note:
        channel_cap += user_note + "\n" + SEP + "\n"
    channel_cap += (
        _row(SC("User"), uname) + "\n"
        + _row("ID",  str(uid)) + "\n"
        + _row(SC("Date"), submitted) + "\n"
        + SEP
    )
    posted = False
    try:
        send  = context.bot.send_photo if ftype == "photo" else context.bot.send_video
        kwarg = {"photo": file_id} if ftype == "photo" else {"video": file_id}
        await send(chat_id=CHANNEL_ID, caption=channel_cap, **kwarg)
        posted = True
    except Exception as e:
        logger.error("Feedback channel post failed: " + str(e))
        try:
            await context.bot.send_message(
                chat_id=OWNER_ID,
                text=("\u26A0\uFE0F Channel post failed!\n"
                      "Error: <code>" + str(e)[:300] + "</code>\n\n"
                      "Make sure bot is admin with Post Messages permission.\n"
                      "CHANNEL_ID used: <code>" + str(CHANNEL_ID) + "</code>"),
                parse_mode="HTML")
        except Exception:
            pass

    context.bot_data["fb_pending"].pop(key, None)
    status_line = "\u2705 Posted to channel!" if posted else "\u26A0\uFE0F Approved but post failed."
    try:
        await query.message.edit_caption(
            caption=(TAG + " " + ARROW + " Feedback Approved\n" + SEP + "\n"
                     + _row(SC("User"),   uname)       + "\n"
                     + _row("ID",         str(uid))    + "\n"
                     + _row(SC("Status"), status_line) + "\n"
                     + SEP),
            reply_markup=None)
    except Exception:
        pass
    try:
        await context.bot.send_message(
            chat_id=uid,
            text=(TAG + " " + ARROW + " Feedback Accepted \u2705\n" + SEP + "\n"
                  "Your feedback was posted to the channel!\n"
                  "\U0001F4E2 " + CHANNEL_LINK + "\n" + SEP))
    except Exception:
        pass

async def _fb_decline(query, context: ContextTypes.DEFAULT_TYPE, key: str):
    fb = context.bot_data.get("fb_pending", {}).get(key)
    if not fb:
        await query.answer("Already handled or not found.", show_alert=True)
        return
    uname, uid = fb["username"], fb["user_id"]
    context.bot_data["fb_pending"].pop(key, None)
    try:
        await query.message.edit_caption(
            caption=(TAG + " " + ARROW + " Feedback Declined\n" + SEP + "\n"
                     + _row(SC("User"),   uname) + "\n"
                     + _row("ID",         str(uid)) + "\n"
                     + _row(SC("Status"), "\u274C Declined") + "\n"
                     + SEP),
            reply_markup=None)
    except Exception:
        pass
    try:
        await context.bot.send_message(
            chat_id=uid,
            text=(TAG + " " + ARROW + " Feedback Declined \u274C\n" + SEP + "\n"
                  "Your feedback was not approved this time.\n" + SEP))
    except Exception:
        pass


@owner_only
async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg         = update.message
    target_id   = None
    target_chat = None

    if msg.reply_to_message and msg.reply_to_message.from_user:
        ru        = msg.reply_to_message.from_user
        target_id = ru.id
        try:   target_chat = await context.bot.get_chat(ru.id)
        except Exception: pass
    elif context.args:
        raw = " ".join(context.args).strip()
        if raw.lstrip("-").isdigit():
            target_id = int(raw)
            try:   target_chat = await context.bot.get_chat(target_id)
            except Exception: pass
        else:
            clean = raw.lstrip("@")
            for attempt in ("@" + clean, clean):
                try:
                    target_chat = await context.bot.get_chat(attempt)
                    target_id   = target_chat.id
                    break
                except Exception:
                    continue
            if not target_id:
                cl = clean.lower()
                for uid_str, ud in context.bot_data.get("user_data", {}).items():
                    stored_un   = ud.get("username", "").lower().lstrip("@")
                    stored_name = ud.get("name", "").lower()
                    if cl in stored_un or cl in stored_name:
                        target_id = int(uid_str)
                        try:   target_chat = await context.bot.get_chat(target_id)
                        except Exception: pass **...**

_This response is too long to display in full._
