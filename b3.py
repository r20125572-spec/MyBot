import urllib.request
import urllib.error
import json
import asyncio
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, ContextTypes
from config import get_bin_info, kb_result, OWNER_ID, FORCE_CHANNELS, SUPPORT_LINK
from plans import deduct_credit, is_premium

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BRAINTREE GATE CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
B3_API_URL = "https://avs.blaze.indevs.in/api/b3"
GATE_NAME  = "Bʀᴀɪɴᴛʀᴇᴇ 0$"

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

    # ── Credit check & deduction via plans.py ──
    premium = is_premium(user.id)

    if not premium:
        if not deduct_credit(user.id):
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

    msg        = await update.message.reply_text("⏳ <b>[ 𖥷iТ ] ➺ Pʀᴏᴄᴇꜱꜱɪɴɢ...</b>", parse_mode="HTML")
    start_time = time.time()
    bin_num    = card[:6]

    try:
        loop = asyncio.get_running_loop()

        def do_request():
            url = f"{B3_API_URL}?cc={card}"
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))

        # Run API + BIN lookup in parallel
        api_task = loop.run_in_executor(None, do_request)
        bin_task = get_bin_info(bin_num)
        results  = await asyncio.gather(api_task, bin_task, return_exceptions=True)

        api_data = results[0]
        bin_data = results[1] if not isinstance(results[1], Exception) else {"error": True}

        if isinstance(api_data, Exception):
            raise api_data

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

    except urllib.error.HTTPError as e:
        await msg.edit_text(
            f"<b>[ 𖥷iТ ] ➺ Eʀʀᴏʀ ❌</b>\n━━━━━━━━━━━━━━━━━\n"
            f"HTTP {e.code}: {e.reason}\n━━━━━━━━━━━━━━━━━",
            parse_mode="HTML"
        )
    except urllib.error.URLError:
        await msg.edit_text(
            "<b>[ 𖥷iТ ] ➺ Eʀʀᴏʀ ❌</b>\n━━━━━━━━━━━━━━━━━\n"
            "Connection error. Check API URL.\n━━━━━━━━━━━━━━━━━",
            parse_mode="HTML"
        )
    except asyncio.TimeoutError:
        await msg.edit_text(
            "<b>[ 𖥷iТ ] ➺ Tɪᴍᴇᴏᴜᴛ ❌</b>\n━━━━━━━━━━━━━━━━━\n"
            "API took too long. Try again.\n━━━━━━━━━━━━━━━━━",
            parse_mode="HTML"
        )
    except json.JSONDecodeError:
        await msg.edit_text(
            "<b>[ 𖥷iТ ] ➺ Eʀʀᴏʀ ❌</b>\n━━━━━━━━━━━━━━━━━\n"
            "API returned invalid response.\n━━━━━━━━━━━━━━━━━",
            parse_mode="HTML"
        )
    except Exception as e:
        await msg.edit_text(
            f"<b>[ 𖥷iТ ] ➺ Eʀʀᴏʀ ❌</b>\n━━━━━━━━━━━━━━━━━\n"
            f"<code>{str(e)[:120]}</code>\n━━━━━━━━━━━━━━━━━",
            parse_mode="HTML"
        )

def get_b3_handler():
    return CommandHandler("b3", cmd_b3)
