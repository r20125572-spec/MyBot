import aiohttp
import asyncio
import time
import re
from html import escape
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, ContextTypes
from config import get_bin_info, kb_result, OWNER_ID, FORCE_CHANNELS, SUPPORT_LINK, API_TIMEOUT

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BRAINTREE GATE CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
B3_API_URL = "https://chk.rcvan.indevs.in/b3"
GATE_NAME  = "Bʀᴀɪɴᴛʀᴇᴇ 0$ 💳 🟢"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOCAL USER DATA HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_user_data(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> dict:
    uid = str(user_id)
    if "user_data" not in context.bot_data: context.bot_data["user_data"] = {}
    if uid not in context.bot_data["user_data"]:
        context.bot_data["user_data"][uid] = {
            "name": "User", "credits": 150, "plan": "TRIAL", "expires": 0, "pre_premium_credits": 0
        }
    return context.bot_data["user_data"][uid]

def is_user_premium(ud: dict) -> bool:
    raw_plan = ud.get("plan", "TRIAL").upper()
    if raw_plan == "TRIAL": return False
    if ud.get("expires", 0) <= time.time():
        ud["plan"] = "TRIAL"
        ud["credits"] = ud.get("pre_premium_credits", 150)
        ud["expires"] = 0
        return False
    return True

def get_styled_plan(raw_plan: str) -> str:
    plan_upper = raw_plan.upper()
    if plan_upper == "CORE": return "✨ Cᴏʀᴇ ✨"
    elif plan_upper == "ELITE": return "⭐ Eʟɪᴛᴇ ⭐"
    elif plan_upper == "ROOT": return "👑 Rᴏᴏᴛ 👑"
    else: return "Tʀɪᴀʟ"

async def _check_force_sub(user_id: int, context) -> list:
    if user_id == OWNER_ID: return []
    not_joined = []
    for name, link in FORCE_CHANNELS:
        try:
            member = await context.bot.get_chat_member(f"@{name}", user_id)
            if member.status in ("left", "kicked"): not_joined.append((name, link))
        except Exception:
            pass
    return not_joined

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /b3 COMMAND HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_b3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # ── Maintenance check ──
    if context.bot_data.get("maintenance") and user.id != OWNER_ID:
        await update.message.reply_text("⚠️ Bot is under maintenance. Try again later.")
        return

    # ── Gate toggle check ──
    if not context.bot_data.get("b3_on", True):
        await update.message.reply_text("⚠️ Bʀᴀɪɴᴛʀᴇᴇ gate is currently <b>OFF</b>.", parse_mode="HTML")
        return

    # ── Force subscribe check ──
    not_joined = await _check_force_sub(user.id, context)
    if not_joined:
        rows = [[InlineKeyboardButton(f"➺ Join @{n}", url=l)] for n, l in not_joined]
        rows.append([InlineKeyboardButton("✅ I Joined — Verify Now", callback_data="check_sub")])
        await update.message.reply_text(
            "<b>[ 𖥷iТ ] ➺ Jᴏɪɴ Rᴇǫᴜɪʀᴇᴅ</b>\n━━━━━━━━━━━━━━━━━\n"
            "Join our channel & group to use this bot.\n━━━━━━━━━━━━━━━━━",
            reply_markup=InlineKeyboardMarkup(rows), parse_mode="HTML"
        )
        return

    # ── Parse card (FIXED EXTRACTION) ──
    card = None
    if context.args:
        card = context.args[0].strip()
    elif update.message.reply_to_message:
        replied_msg = update.message.reply_to_message
        # Get the text or caption from the replied message
        replied_text = replied_msg.text or replied_msg.caption or ""
        
        # Use Regex to find the actual card number inside the text (ignores the "[ 𖥷iТ ]" part)
        match = re.search(r'(\d{13,19})\s*[|,;\s]\s*(\d{1,2})\s*[|,;\s]\s*(\d{2,4})\s*[|,;\s]\s*(\d{3,4})', replied_text)
        if match:
            card = f"{match.group(1)}|{match.group(2)}|{match.group(3)}|{match.group(4)}"
        else:
            # Fallback: look for just a 13-19 digit number if there's no expiry/cvv
            match = re.search(r'\b(\d{13,19})\b', replied_text)
            if match:
                card = match.group(1)

    if not card:
        await update.message.reply_text(
            "⚠️ <b>Uꜱᴀɢᴇ:</b>\n"
            "<code>/b3 cc|mm|yy|cvv</code>\n\n"
            "<b>Example:</b>\n"
            "<code>/b3 4111111111111111|12|26|123</code>",
            parse_mode="HTML"
        )
        return

    # ── Credit check & deduction ──
    ud = get_user_data(user.id, context)
    premium = is_user_premium(ud)

    if not premium:
        if ud.get("credits", 0) <= 0:
            await update.message.reply_text(
                "<b>[ 𖥷iТ ] ➺ Nᴏ Cʀᴇᴅɪᴛꜱ ❌</b>\n━━━━━━━━━━━━━━━━━\n"
                "You have no credits left.\n"
                "Redeem a code with /rm or buy a plan.\n━━━━━━━━━━━━━━━━━",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💎 BUY PREMIUM", callback_data="mprice")],
                    [InlineKeyboardButton("📞 Support", url=SUPPORT_LINK)],
                ])
            )
            return
        ud["credits"] -= 1

    msg        = await update.message.reply_text("⏳ <b>[ 𖥷iТ ] ➺ Pʀᴏᴄᴇꜱꜱɪɴɢ...</b>", parse_mode="HTML")
    start_time = time.time()
    bin_num    = card[:6]

    try:
        url = f"{B3_API_URL}?cc={card}"
        timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)

        # Run API + BIN lookup in parallel
        async with aiohttp.ClientSession(timeout=timeout) as session:
            api_task = session.get(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
            bin_task = get_bin_info(bin_num)
            
            resp, bin_data = await asyncio.gather(api_task, bin_task, return_exceptions=True)

            if isinstance(bin_data, Exception): bin_data = {"error": True}
            if isinstance(resp, Exception): raise resp
            
            api_data = await resp.json(content_type=None)

        # Safely extract message and status from various API response formats
        message   = str(api_data.get("message") or api_data.get("response") or api_data.get("msg") or "").strip()
        status    = str(api_data.get("status") or api_data.get("result") or "").lower()
        msg_lower = message.lower()

        # ── STRICT STATUS DETECTION ──
        is_approved = (
            "approved" in status or
            "success" in status or
            status == "true" or
            "processed" in status or
            "nice! new payment method added" in msg_lower or
            "approved" in msg_lower or
            "success" in msg_lower
        )
        
        if is_approved:
            status_ui = "Aᴘᴘʀᴏᴠᴇᴅ ✅"
        else:
            status_ui = "Dᴇᴄʟɪɴᴇᴅ ❌"

        # BIN info formatting
        bin_txt = "N/A"
        if not bin_data.get("error"):
            scheme  = str(bin_data.get("scheme",  "N/A")).upper()
            bank    = bin_data.get("bank",    "N/A")
            country = str(bin_data.get("country", "N/A")).upper()
            flag    = bin_data.get("country_emoji", "")
            bin_txt = f"{scheme} - {bank} - {flag} {country}".strip("- ")

        # User display
        ud_name    = user.first_name or "User"
        raw_plan   = ud.get('plan', 'TRIAL').upper()
        plan_ui    = get_styled_plan(raw_plan)
        elapsed    = f"{time.time() - start_time:.2f}"

        # Escape message to prevent HTML parsing errors
        safe_message = escape(message) if message else "No response"

        text = (
            f"<b>[ 𖥷iТ ] ➺ {status_ui}</b>\n"
            f"🔍 ➺ <code>{card}</code>\n"
            f"Gᴀᴛᴇ ➺ {GATE_NAME}\n"
            f"Rᴀᴡ  ➺ {safe_message}\n"
            f"Iɴꜰᴏ ➺ {bin_txt}\n"
            f"Uꜱᴇʀ ➺ {ud_name} ({plan_ui})\n"
            f"Tɪᴍᴇ ➺ {elapsed}s\n"
            f"Pʀᴏ  ➺ Batman⚡\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"📢 @Batcardchk"
        )

        await msg.edit_text(
            text, parse_mode="HTML",
            reply_markup=kb_result(premium),
            disable_web_page_preview=True
        )

    except asyncio.TimeoutError:
        if not premium: ud["credits"] = ud.get("credits", 0) + 1
        await msg.edit_text(
            "<b>[ 𖥷iТ ] ➺ Tɪᴍᴇᴏᴜᴛ ❌</b>\n━━━━━━━━━━━━━━━━━\n"
            "API took too long. Try again.\n━━━━━━━━━━━━━━━━━",
            parse_mode="HTML"
        )
    except Exception as e:
        if not premium: ud["credits"] = ud.get("credits", 0) + 1
        await msg.edit_text(
            f"<b>[ 𖥷iТ ] ➺ Eʀʀᴏʀ ❌</b>\n━━━━━━━━━━━━━━━━━\n"
            f"<code>{escape(str(e)[:120])}</code>\n━━━━━━━━━━━━━━━━━",
            parse_mode="HTML"
        )

def get_b3_handler():
    return CommandHandler("b3", cmd_b3)
