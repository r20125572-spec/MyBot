import aiohttp
import asyncio
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, ContextTypes
from config import get_bin_info, kb_result, OWNER_ID, FORCE_CHANNELS, SUPPORT_LINK, API_TIMEOUT

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BRAINTREE GATE CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
B3_API_URL = "https://avs.blaze.indevs.in/api/b3"
GATE_NAME  = "Bʀᴀɪɴᴛʀᴇᴇ 0$"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOCAL USER DATA HELPERS (Matches main.py logic)
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

    # ── Parse card ──
    card = None
    if context.args:
        card = context.args[0].strip()
    elif update.message.reply_to_message and update.message.reply_to_message.text:
        card = update.message.reply_to_message.text.strip().split()[0]

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

        message   = str(api_data.get("message", "")).strip()
        status    = str(api_data.get("status", "")).lower()
        msg_lower = message.lower()

        is_approved = (
            status == "processed"
            or "nice! new payment method added" in msg_lower
            or "approved" in msg_lower
            or "success" in msg_lower
            or status == "true"
        )

        status_ui = "Aᴘᴘʀᴏᴠᴇᴅ ✅" if is_approved else "Dᴇᴄʟɪɴᴇᴅ ❌"

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
        plan_label = "Pʀᴇᴍɪᴜᴍ 👑" if premium else "Tʀɪᴀʟ"
        elapsed    = f"{time.time() - start_time:.2f}"

        text = (
            f"<b>[ 𖥷iТ ] ➺ {status_ui}</b>\n"
            f"🔍 ➺ <code>{card}</code>\n"
            f"<b>Gᴀᴛᴇ</b> ➺ {GATE_NAME} 💳\n"
            f"<b>Rᴀᴡ</b>  ➺ {message if message else 'No response'}\n"
            f"<b>Iɴꜰᴏ</b> ➺ {bin_txt}\n"
            f"<b>Uꜱᴇʀ</b> ➺ {ud_name} ({plan_label})\n"
            f"<b>Tɪᴍᴇ</b> ➺ {elapsed}s\n"
            f"<b>Pʀᴏ</b>  ➺ Batman ⚡\n"
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
            f"<code>{str(e)[:120]}</code>\n━━━━━━━━━━━━━━━━━",
            parse_mode="HTML"
        )

def get_b3_handler():
    return CommandHandler("b3", cmd_b3)
