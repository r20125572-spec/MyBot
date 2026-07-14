import aiohttp
import asyncio
import time
import re
import random
from html import escape
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, ContextTypes
from config import (
    get_bin_info, kb_result, OWNER_ID, FORCE_CHANNELS, SUPPORT_LINK, API_TIMEOUT,
    CHANNEL_LINK,
    E_CARD, E_USER, E_TIME, E_DEV, E_PRO, E_LIVE, E_DECLINED, E_ERRORS, E_PROGRESS,
    get_plan_emoji_id, get_random_live_emoji, tg_emoji,
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BRAINTREE GATE CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
B3_API_URL = "https://chk.rcvan.indevs.in/b3"
GATE_NAME  = "Bʀᴀɪɴᴛʀᴇᴇ 0$"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOCAL USER DATA HELPERS
# (Mirrors bot.py helpers — no Bot(token) usage here)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _get_user_data(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> dict:
    uid = str(user_id)
    if "user_data" not in context.bot_data:
        context.bot_data["user_data"] = {}
    if uid not in context.bot_data["user_data"]:
        context.bot_data["user_data"][uid] = {
            "name": "User", "credits": 150, "plan": "TRIAL",
            "expires": 0, "pre_premium_credits": 0,
        }
    return context.bot_data["user_data"][uid]

def _is_premium(ud: dict) -> bool:
    raw_plan = ud.get("plan", "TRIAL").upper()
    if raw_plan == "TRIAL":
        return False
    if ud.get("expires", 0) <= time.time():
        ud["plan"]    = "TRIAL"
        ud["credits"] = ud.get("pre_premium_credits", 150)
        ud["expires"] = 0
        return False
    return True

def _styled_plan(raw_plan: str) -> str:
    p = raw_plan.upper()
    if p == "CORE":  return "Cᴏʀᴇ"
    if p == "ELITE": return "Eʟɪᴛᴇ"
    if p == "ROOT":  return "Rᴏᴏᴛ"
    return "Tʀɪᴀʟ"

async def _check_force_sub(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> list:
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
# /b3  COMMAND HANDLER
# Uses context.bot — never creates its own Bot(token) instance.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_b3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # ── Maintenance check ──
    if context.bot_data.get("maintenance") and user.id != OWNER_ID:
        await update.message.reply_text(
            f"<b>{E_ERRORS} Mᴀɪɴᴛᴇɴᴀɴᴄᴇ</b>\n━━━━━━━━━━━━━━━━━\n"
            "Bot is under maintenance. Try again later.\n━━━━━━━━━━━━━━━━━",
            parse_mode="HTML"
        )
        return

    # ── Gate toggle check ──
    if not context.bot_data.get("b3_on", True):
        await update.message.reply_text(
            f"<b>{E_DECLINED} Gᴀᴛᴇ OFF</b>\n━━━━━━━━━━━━━━━━━\n"
            "Bʀᴀɪɴᴛʀᴇᴇ gate is currently <b>OFF</b>.\n━━━━━━━━━━━━━━━━━",
            parse_mode="HTML"
        )
        return

    # ── Force subscribe check ──
    not_joined = await _check_force_sub(user.id, context)
    if not_joined:
        rows = [[InlineKeyboardButton(f"➺ Join @{n}", url=l)] for n, l in not_joined]
        rows.append([InlineKeyboardButton(f"✅ I Joined — Verify Now", callback_data="check_sub")])
        await update.message.reply_text(
            f"<b>{E_ERRORS} Jᴏɪɴ Rᴇǫᴜɪʀᴇᴅ</b>\n━━━━━━━━━━━━━━━━━\n"
            "Join our channel & group to use this bot.\n━━━━━━━━━━━━━━━━━",
            reply_markup=InlineKeyboardMarkup(rows),
            parse_mode="HTML"
        )
        return

    # ── Parse card ──
    card = None
    if context.args:
        card = context.args[0].strip()
    elif update.message.reply_to_message:
        replied_text = (
            update.message.reply_to_message.text or
            update.message.reply_to_message.caption or ""
        )
        match = re.search(
            r'(\d{13,19})\s*[|,;\s]\s*(\d{1,2})\s*[|,;\s]\s*(\d{2,4})\s*[|,;\s]\s*(\d{3,4})',
            replied_text
        )
        if match:
            card = f"{match.group(1)}|{match.group(2)}|{match.group(3)}|{match.group(4)}"
        else:
            m2 = re.search(r'\b(\d{13,19})\b', replied_text)
            if m2:
                card = m2.group(1)

    if not card:
        await update.message.reply_text(
            f"<b>{E_ERRORS} Uꜱᴀɢᴇ</b>\n━━━━━━━━━━━━━━━━━\n"
            f"<code>/b3 cc|mm|yy|cvv</code>\n\n"
            f"<b>Example:</b>\n"
            f"<code>/b3 4111111111111111|12|26|123</code>\n"
            f"━━━━━━━━━━━━━━━━━",
            parse_mode="HTML"
        )
        return

    # ── User data & credit / cooldown check ──
    ud      = _get_user_data(user.id, context)
    premium = _is_premium(ud)

    if not premium:
        if ud.get("credits", 0) <= 0:
            await update.message.reply_text(
                f"<b>{E_DECLINED} Nᴏ Cʀᴇᴅɪᴛꜱ</b>\n━━━━━━━━━━━━━━━━━\n"
                "You have <b>0 credits</b> remaining.\n\n"
                f"{E_PRO} Upgrade to <b>Premium</b> for unlimited checks.\n"
                "━━━━━━━━━━━━━━━━━",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💎 BUY PREMIUM — Unlimited Checks", callback_data="mprice")],
                    [InlineKeyboardButton("📢 @Batcardchk", url=CHANNEL_LINK)],
                ])
            )
            return

        # ── 25s cooldown for trial/free users ──
        B3_COOLDOWN = 25
        cooldown_store = context.bot_data.setdefault("cooldown_store", {})
        last_check     = cooldown_store.get(user.id, 0)
        remaining      = B3_COOLDOWN - (time.time() - last_check)
        if remaining > 0:
            await update.message.reply_text(
                f"<b>{E_ERRORS} Cᴏᴏʟᴅᴏᴡɴ</b>\n━━━━━━━━━━━━━━━━━\n"
                f"Please wait <b>{remaining:.1f}s</b> before your next check.\n\n"
                f"{E_PRO} <b>Premium users have no cooldown.</b>\n"
                "━━━━━━━━━━━━━━━━━",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💎 BUY PREMIUM — No Cooldown", callback_data="mprice")],
                ])
            )
            return

        cooldown_store[user.id] = time.time()
        ud["credits"] -= 1

    # ── Processing ──
    msg        = await update.message.reply_text(
        f"{E_PROGRESS} <b>Pʀᴏᴄᴇꜱꜱɪɴɢ...</b>", parse_mode="HTML"
    )
    start_time = time.time()
    bin_num    = card[:6]

    try:
        url     = f"{B3_API_URL}?cc={card}"
        timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            resp, bin_data = await asyncio.gather(
                session.get(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}),
                get_bin_info(bin_num),
                return_exceptions=True,
            )
            if isinstance(bin_data, Exception):
                bin_data = {"error": True}
            if isinstance(resp, Exception):
                raise resp
            api_data = await resp.json(content_type=None)

        message   = str(
            api_data.get("message") or api_data.get("response") or
            api_data.get("msg") or ""
        ).strip()
        status    = str(api_data.get("status") or api_data.get("result") or "").lower()
        msg_lower = message.lower()

        is_approved = (
            "approved"   in status or "success"   in status or
            status == "true" or "processed" in status or
            "nice! new payment method added" in msg_lower or
            "approved" in msg_lower or "success" in msg_lower
        )

        if is_approved:
            live_eid    = get_random_live_emoji()
            status_line = f"Lɪᴠᴇ {tg_emoji(live_eid, '✅')}"
        else:
            status_line = f"Dᴇᴄʟɪɴᴇᴅ {E_DECLINED}"

        # BIN info
        bin_txt = "N/A"
        if not bin_data.get("error"):
            scheme  = str(bin_data.get("scheme",  "N/A")).upper()
            bank    = bin_data.get("bank",    "N/A")
            country = str(bin_data.get("country", "N/A")).upper()
            flag    = bin_data.get("country_emoji", "")
            bin_txt = f"{scheme} - {bank} - {flag} {country}".strip("- ")

        # Plan emoji
        raw_plan      = ud.get("plan", "TRIAL").upper()
        plan_emoji_id = get_plan_emoji_id(raw_plan)
        plan_emoji    = tg_emoji(plan_emoji_id, "⭐")
        plan_ui       = _styled_plan(raw_plan)
        ud_name       = user.first_name or "User"
        elapsed       = f"{time.time() - start_time:.2f}"
        safe_msg      = escape(message) if message else "No response"

        # ── Result message ──
        text = (
            f"<b>{E_CARD} {status_line}</b>\n"
            f"<b>━━━━━━━━━━━━━━━━━</b>\n"
            f"{E_CARD} <code>{card}</code>\n"
            f"<b>Gᴀᴛᴇ</b> ➺ {GATE_NAME}\n"
            f"<b>Rᴀᴡ</b>  ➺ {safe_msg}\n"
            f"<b>Iɴꜰᴏ</b> ➺ {bin_txt}\n"
            f"<b>━━━━━━━━━━━━━━━━━</b>\n"
            f"{E_TIME} <b>{elapsed}s</b>\n"
            f"{E_USER} <b>{escape(ud_name)}</b> {plan_emoji} <b>({plan_ui})</b>\n"
            f"{E_DEV} <b>Batman</b> {E_PRO}\n"
            f"<b>━━━━━━━━━━━━━━━━━</b>\n"
            f"📢 <a href='{CHANNEL_LINK}'>@Batcardchk</a>"
        )

        await msg.edit_text(
            text, parse_mode="HTML",
            reply_markup=kb_result(premium),
            disable_web_page_preview=True,
        )

        # Update user stats
        ud["total_checks"]  = ud.get("total_checks", 0) + 1
        ud["last_gate"]     = GATE_NAME
        ud["last_card"]     = card[:6] + "xxxxxxxxxx"
        ud["last_active"]   = time.strftime("%Y-%m-%d %H:%M")
        if is_approved:
            ud["approved_checks"] = ud.get("approved_checks", 0) + 1
        else:
            ud["declined_checks"] = ud.get("declined_checks", 0) + 1

    except asyncio.TimeoutError:
        if not premium:
            ud["credits"] = ud.get("credits", 0) + 1
        await msg.edit_text(
            f"<b>{E_ERRORS} Tɪᴍᴇᴏᴜᴛ</b>\n━━━━━━━━━━━━━━━━━\n"
            "API took too long. Try again.\n━━━━━━━━━━━━━━━━━",
            parse_mode="HTML"
        )
    except Exception as e:
        if not premium:
            ud["credits"] = ud.get("credits", 0) + 1
        await msg.edit_text(
            f"<b>{E_ERRORS} Eʀʀᴏʀ</b>\n━━━━━━━━━━━━━━━━━\n"
            f"<code>{escape(str(e)[:120])}</code>\n━━━━━━━━━━━━━━━━━",
            parse_mode="HTML"
        )

def get_b3_handler():
    return CommandHandler("b3", cmd_b3)
