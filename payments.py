"""Secure OxaPay invoices and webhook processing for the Telegram bot."""
# Python 3.10+ supports the annotations used in this module directly.

import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from decimal import Decimal, InvalidOperation
from typing import Awaitable, Callable

import aiohttp
from aiohttp import web

import database as db

logger = logging.getLogger(__name__)


class OxaPayTemporaryResponseError(RuntimeError):
    """OxaPay/proxy returned no usable API document; retry may succeed."""


OXAPAY_API_BASE = "https://api.oxapay.com/v1"
SUCCESS_STATUSES = frozenset({
    "paid",
    "manual_accept",
    "completed",
    "complete",
    "confirmed",
})
_ACTIVATION_LOCKS: dict[int, asyncio.Lock] = {}
WHITE_LABEL_MAX_ATTEMPTS = 4
RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})

PLANS = {
    "pay1d": {"name": "Core", "plan": "CORE", "days": 1, "price": Decimal("1.50")},
    "pay10": {"name": "Core", "plan": "CORE", "days": 7, "price": Decimal("8.00")},
    "pay15": {"name": "Elite", "plan": "ELITE", "days": 15, "price": Decimal("12.00")},
    "pay30": {"name": "Root", "plan": "ROOT", "days": 30, "price": Decimal("25.00")},
}

PAYMENT_METHODS = {
    "bep20": {
        "label": "BEP20", "pay_currency": "USDT", "network": "BSC",
        "network_name": "Binance Smart Chain",
    },
    "trx": {
        "label": "TRX", "pay_currency": "TRX", "network": "Tron",
        "network_name": "Tron Network",
    },
    "pol": {
        "label": "POL", "pay_currency": "POL", "network": "Polygon",
        "network_name": "Polygon Network",
    },
    "ton": {
        "label": "TON", "pay_currency": "GRAM", "network": "The Open Network",
        "network_name": "TON Network",
    },
    "ltc": {
        "label": "LTC", "pay_currency": "LTC", "network": "Litecoin",
        "network_name": "Litecoin Network",
    },
    "btc": {
        "label": "BTC", "pay_currency": "BTC", "network": "Bitcoin",
        "network_name": "Bitcoin Network",
    },
    "sol": {
        "label": "SOL", "pay_currency": "SOL", "network": "Solana",
        "network_name": "Solana Network",
    },
    "eth": {
        "label": "ETH", "pay_currency": "ETH", "network": "Ethereum",
        "network_name": "Ethereum Network",
    },
}

_accepted_cache: tuple[float, frozenset[str]] | None = None
ACCEPTED_CACHE_TTL = 30
ACCEPTED_STALE_TTL = 15 * 60


def _api_key() -> str:
    return os.environ.get("OXAPAY_MERCHANT_API_KEY", "").strip()


def _callback_url() -> str:
    return os.environ.get("OXAPAY_CALLBACK_URL", "").strip()


def _sandbox_enabled() -> bool:
    return os.environ["OXAPAY_SANDBOX"].strip().lower() == "true"


def configuration_error() -> str | None:
    if not _api_key():
        return "OXAPAY_MERCHANT_API_KEY is not configured."
    callback = _callback_url()
    if not callback:
        return "OXAPAY_CALLBACK_URL is not configured."
    if not callback.startswith("https://"):
        return "OXAPAY_CALLBACK_URL must use https://."
    sandbox = os.environ.get("OXAPAY_SANDBOX", "").strip().lower()
    if sandbox not in {"true", "false"}:
        return "OXAPAY_SANDBOX must be set explicitly to true or false."
    if sandbox == "true":
        return (
            "Direct OxaPay crypto addresses require live mode. "
            "Set OXAPAY_SANDBOX=false."
        )
    if not db.is_connected():
        return "PostgreSQL is unavailable; secure payment orders cannot be created."
    return None


async def _read_oxapay_json(
    response: aiohttp.ClientResponse,
    operation: str,
) -> dict:
    """Decode an OxaPay response without exposing raw proxy/HTML errors."""
    body = await response.text()
    if not body.strip():
        raise OxaPayTemporaryResponseError(
            f"OxaPay returned an empty response while {operation}. "
            "Please try again in a moment."
        )
    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        logger.warning(
            "[OXAPAY] Non-JSON response while %s: status=%s content_type=%s bytes=%s",
            operation,
            response.status,
            response.headers.get("Content-Type", ""),
            len(body.encode("utf-8", errors="replace")),
        )
        raise OxaPayTemporaryResponseError(
            f"OxaPay returned an invalid response while {operation}. "
            "Please try again in a moment."
        ) from exc
    if not isinstance(result, dict):
        raise OxaPayTemporaryResponseError(
            f"OxaPay returned an unexpected response while {operation}. "
            "Please try again in a moment."
        )
    return result


def _api_status(result: dict) -> int:
    """Return OxaPay's API status without allowing malformed values to crash."""
    try:
        return int(result.get("status", 0))
    except (TypeError, ValueError):
        return 0


async def _retry_temporary(
    operation: Callable[[], Awaitable[dict]],
    *,
    name: str,
    attempts: int = WHITE_LABEL_MAX_ATTEMPTS,
) -> dict:
    """Retry temporary provider/transport failures with bounded backoff."""
    last_error: BaseException | None = None
    total_attempts = max(1, int(attempts))
    for attempt in range(1, total_attempts + 1):
        try:
            return await operation()
        except (
            OxaPayTemporaryResponseError,
            aiohttp.ClientError,
            asyncio.TimeoutError,
        ) as exc:
            last_error = exc
            if attempt >= total_attempts:
                break
            delay = min(4.0, 0.65 * (2 ** (attempt - 1)))
            delay += secrets.randbelow(250) / 1000
            logger.warning(
                "[OXAPAY] Temporary failure while %s; retrying attempt %s/%s "
                "in %.2fs (%s)",
                name,
                attempt + 1,
                total_attempts,
                delay,
                type(exc).__name__,
            )
            await asyncio.sleep(delay)
    raise OxaPayTemporaryResponseError(
        "OxaPay is temporarily unavailable after several automatic retries. "
        "Please press Retry Payment."
    ) from last_error


async def get_accepted_method_keys(force: bool = False) -> list[str]:
    """Return only payment methods enabled for this OxaPay merchant."""
    global _accepted_cache
    error = configuration_error()
    if error:
        raise RuntimeError(error)
    now = time.monotonic()
    if (
        not force
        and _accepted_cache
        and now - _accepted_cache[0] < ACCEPTED_CACHE_TTL
    ):
        accepted = _accepted_cache[1]
    else:
        headers = {
            "merchant_api_key": _api_key(),
            "Content-Type": "application/json",
        }
        timeout = aiohttp.ClientTimeout(
            total=10,
            connect=5,
            sock_connect=5,
            sock_read=7,
        )
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"{OXAPAY_API_BASE}/payment/accepted-currencies",
                    headers=headers,
                ) as response:
                    result = await _read_oxapay_json(
                        response,
                        "loading payment methods",
                    )
                    response_status = response.status
            if response_status != 200 or _api_status(result) != 200:
                raise RuntimeError(
                    _oxapay_error(
                        result,
                        "Could not load accepted OxaPay currencies.",
                    )
                )
            values = (result.get("data") or {}).get("list") or []
            accepted = frozenset(str(value).upper() for value in values)
            if not accepted:
                raise RuntimeError("OxaPay returned no accepted currencies.")
            _accepted_cache = (now, accepted)
        except (
            OxaPayTemporaryResponseError,
            aiohttp.ClientError,
            asyncio.TimeoutError,
        ):
            if (
                _accepted_cache
                and now - _accepted_cache[0] < ACCEPTED_STALE_TTL
            ):
                accepted = _accepted_cache[1]
                logger.warning(
                    "[OXAPAY] Using cached accepted currencies after a "
                    "temporary API response failure."
                )
            else:
                # Currency discovery is optional. Address creation remains
                # authoritative and rejects any disabled merchant currency.
                accepted = frozenset(
                    method["pay_currency"].upper()
                    for method in PAYMENT_METHODS.values()
                )
                logger.warning(
                    "[OXAPAY] Accepted-currencies API unavailable; showing "
                    "configured methods and deferring validation to payment "
                    "address creation."
                )

    return [
        key
        for key, method in PAYMENT_METHODS.items()
        if method["pay_currency"].upper() in accepted
    ]


async def create_white_label_payment(
    user_id: int,
    plan_selection: str,
    method_selection: str,
) -> dict:
    error = configuration_error()
    if error:
        raise RuntimeError(error)
    plan = PLANS.get(plan_selection)
    if not plan:
        raise ValueError("Unknown payment plan.")
    method = PAYMENT_METHODS.get(method_selection)
    if not method:
        raise ValueError("Unknown payment method.")
    accepted_methods = await get_accepted_method_keys(force=True)
    if method_selection not in accepted_methods:
        raise RuntimeError(
            f"{method['label']} is not enabled in your OxaPay Merchant Service."
        )

    order_id = f"tg-{user_id}-{secrets.token_hex(12)}"
    created = await db.create_payment_order(
        order_id=order_id,
        user_id=user_id,
        plan=plan["plan"],
        days=plan["days"],
        expected_amount=plan["price"],
        currency="USD",
    )
    if not created:
        raise RuntimeError("Could not store the payment order.")

    payload = {
        "amount": float(plan["price"]),
        "currency": "USD",
        "pay_currency": method["pay_currency"],
        "network": method["network"],
        "lifetime": 120,
        "fee_paid_by_payer": 1,
        "under_paid_coverage": 0,
        "callback_url": _callback_url(),
        "order_id": order_id,
        "description": f"{plan['name']} plan for Telegram user {user_id}",
    }
    headers = {
        "merchant_api_key": _api_key(),
        "Content-Type": "application/json",
    }

    try:
        timeout = aiohttp.ClientTimeout(
            total=20,
            connect=7,
            sock_connect=7,
            sock_read=12,
        )
        connector = aiohttp.TCPConnector(
            ttl_dns_cache=300,
            enable_cleanup_closed=True,
        )
        async with aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            headers={"Accept": "application/json"},
        ) as session:
            async def request_payment() -> dict:
                async with session.post(
                    f"{OXAPAY_API_BASE}/payment/white-label",
                    headers=headers,
                    json=payload,
                ) as response:
                    result = await _read_oxapay_json(
                        response,
                        "creating the payment address",
                    )
                    if response.status in RETRYABLE_HTTP_STATUSES:
                        raise OxaPayTemporaryResponseError(
                            "OxaPay temporarily could not create the payment address."
                        )
                    api_status = _api_status(result)
                    if api_status in RETRYABLE_HTTP_STATUSES:
                        raise OxaPayTemporaryResponseError(
                            "OxaPay temporarily could not create the payment address."
                        )
                    if response.status != 200 or api_status != 200:
                        # Parsed merchant/authentication/currency errors are
                        # authoritative and must not be hidden by retries.
                        raise RuntimeError(
                            _oxapay_error(
                                result,
                                "OxaPay rejected the payment request.",
                            )
                        )
                    response_data = result.get("data")
                    if not isinstance(response_data, dict):
                        raise OxaPayTemporaryResponseError(
                            "OxaPay returned incomplete payment information."
                        )
                    required = (
                        response_data.get("track_id"),
                        response_data.get("address"),
                        response_data.get("pay_amount"),
                        response_data.get("expired_at"),
                    )
                    if any(value in (None, "", 0, "0") for value in required):
                        raise OxaPayTemporaryResponseError(
                            "OxaPay returned incomplete payment information."
                        )
                    return result

            result = await _retry_temporary(
                request_payment,
                name="creating the payment address",
            )

        data = result.get("data") or {}
        track_id = str(data.get("track_id") or "").strip()
        address = str(data.get("address") or "").strip()
        pay_amount = str(data.get("pay_amount") or "").strip()
        pay_currency = str(data.get("pay_currency") or method["pay_currency"]).upper()
        network_name = method["network_name"]
        memo = str(data.get("memo") or "").strip()
        expired_at = int(data.get("expired_at") or 0)
        if not track_id or not address or not pay_amount or expired_at <= 0:
            raise RuntimeError("OxaPay returned incomplete payment information.")

        saved = await db.attach_payment_invoice(order_id, track_id, "")
        if not saved:
            raise RuntimeError("Could not save the OxaPay payment.")

        return {
            "order_id": order_id,
            "track_id": track_id,
            "address": address,
            "pay_amount": pay_amount,
            "pay_currency": pay_currency,
            "network_name": network_name,
            "memo": memo,
            "expired_at": expired_at,
            "lifetime": int(data.get("lifetime") or 120),
            **plan,
            "method": method,
        }
    except Exception as exc:
        await db.fail_payment_order(order_id, str(exc))
        raise


async def _fetch_payment(track_id: str) -> dict:
    headers = {
        "merchant_api_key": _api_key(),
        "Content-Type": "application/json",
    }
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(
            f"{OXAPAY_API_BASE}/payment/{track_id}",
            headers=headers,
        ) as response:
            result = await _read_oxapay_json(
                response,
                "verifying the payment",
            )
    if response.status != 200 or _api_status(result) != 200:
        raise RuntimeError(_oxapay_error(result, "Payment verification failed."))
    return result.get("data") or {}


def _decimal(value) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("-1")


def _oxapay_error(result: dict, fallback: str) -> str:
    error = result.get("error")
    if isinstance(error, dict):
        detail = str(error.get("message") or "").strip()
        key = str(error.get("key") or "").strip()
        if detail:
            return f"{key}: {detail}" if key else detail
    return str(result.get("message") or fallback)


def _payment_field(data: dict, snake_case: str, camel_case: str = ""):
    value = data.get(snake_case)
    if value in (None, "") and camel_case:
        value = data.get(camel_case)
    return value


async def _deliver_activation(
    app,
    order_id: str,
    activate: Callable[[object, dict], Awaitable[None]],
) -> None:
    claim_token = secrets.token_hex(16)
    entitlement = await db.claim_payment_activation(order_id, claim_token)
    if not entitlement:
        return
    user_id = int(entitlement["user_id"])
    lock = _ACTIVATION_LOCKS.setdefault(user_id, asyncio.Lock())
    try:
        async with lock:
            # Another order for this user may have finalized while this older
            # delivery was waiting. Always activate the canonical latest row.
            current = await db.get_current_payment_entitlement(user_id)
            if not current:
                raise RuntimeError("Canonical paid entitlement is unavailable.")
            await activate(app, current)
            if not await db.mark_payment_activated(order_id, claim_token):
                raise RuntimeError("Could not mark payment activation delivered.")
    except Exception:
        await db.release_payment_activation(order_id, claim_token)
        raise


async def _process_callback(
    app,
    callback_data: dict,
    activate: Callable[[object, dict], Awaitable[None]],
    trusted_callback: bool = False,
) -> None:
    data = callback_data.get("data") if isinstance(callback_data.get("data"), dict) else callback_data
    track_id = str(_payment_field(data, "track_id", "trackId") or "").strip()
    order_id = str(_payment_field(data, "order_id", "orderId") or "").strip()
    if not track_id or not order_id:
        return

    callback_status = str(data.get("status") or "").strip().lower()
    if trusted_callback and callback_status not in SUCCESS_STATUSES:
        return

    # A callback reaching this trusted path has already passed OxaPay's
    # raw-body HMAC verification. Use it immediately when it contains all
    # fields required to bind the payment to the stored order. Reconciliation
    # uses OxaPay's read API when a callback was missed.
    verified = data if trusted_callback else {}
    required_callback_fields = (
        _payment_field(data, "track_id", "trackId"),
        _payment_field(data, "order_id", "orderId"),
        data.get("status"),
        data.get("currency"),
        data.get("amount"),
    )
    if not trusted_callback or any(value in (None, "") for value in required_callback_fields):
        verified = await _fetch_payment(track_id)

    verified_status = str(verified.get("status") or "").strip().lower()
    if verified_status not in SUCCESS_STATUSES:
        return
    if str(_payment_field(verified, "track_id", "trackId") or "").strip() != track_id:
        raise RuntimeError("OxaPay track ID verification failed.")
    if str(_payment_field(verified, "order_id", "orderId") or "").strip() != order_id:
        raise RuntimeError("OxaPay order ID verification failed.")

    order = await db.get_payment_order(order_id)
    if not order:
        raise RuntimeError("Unknown OxaPay order.")
    if order["status"] == "paid":
        await _deliver_activation(app, order_id, activate)
        return
    if str(order.get("track_id") or "") != track_id:
        raise RuntimeError("Stored OxaPay track ID does not match.")
    if str(verified.get("currency") or "").upper() != str(order["currency"]).upper():
        raise RuntimeError("OxaPay payment currency does not match the order.")
    verified_amount = _decimal(verified.get("amount"))
    expected_amount = _decimal(order["expected_amount"])
    if (
        not verified_amount.is_finite()
        or not expected_amount.is_finite()
        or expected_amount <= 0
        or verified_amount < expected_amount
    ):
        raise RuntimeError("OxaPay payment amount is below the order amount.")

    entitlement = await db.finalize_paid_order(order_id, track_id)
    if not entitlement:
        return
    await _deliver_activation(app, order_id, activate)


async def _reconcile_pending(
    telegram_app,
    activate: Callable[[object, dict], Awaitable[None]],
) -> None:
    """Recover paid orders when a webhook is delayed, lost, or raced."""
    delay = 3
    while True:
        try:
            await asyncio.sleep(delay)
            delay = 2
            pending = await db.list_pending_payment_orders(limit=100)
            for order in pending:
                try:
                    await _process_callback(
                        telegram_app,
                        {
                            "track_id": order["track_id"],
                            "order_id": order["order_id"],
                        },
                        activate,
                        trusted_callback=False,
                    )
                except Exception as exc:
                    logger.warning(
                        "[OXAPAY] Pending order %s reconciliation deferred: %s",
                        order["order_id"],
                        exc,
                    )
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("[OXAPAY] Pending-payment reconciliation failed.")
            await asyncio.sleep(2)


async def _webhook(request: web.Request) -> web.Response:
    raw_body = await request.read()
    received = request.headers.get("HMAC", "").strip().lower()
    expected = hmac.new(
        _api_key().encode("utf-8"),
        raw_body,
        hashlib.sha512,
    ).hexdigest()
    if not received or not hmac.compare_digest(received, expected):
        return web.Response(text="Invalid HMAC", status=401)
    try:
        payload = json.loads(raw_body.decode("utf-8"))
        await _process_callback(
            request.app["telegram_app"],
            payload,
            request.app["activate_payment"],
            trusted_callback=True,
        )
    except (UnicodeDecodeError, json.JSONDecodeError):
        return web.Response(text="Invalid JSON", status=400)
    except Exception:
        logger.exception("[OXAPAY] Callback processing failed.")
        return web.Response(text="Temporary failure", status=500)
    return web.Response(text="OK", status=200)


async def _health(_request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "service": "oxapay-webhook"})


async def start_webhook(
    telegram_app,
    activate: Callable[[object, dict], Awaitable[None]],
) -> None:
    if not _api_key():
        logger.warning("[OXAPAY] Disabled: OXAPAY_MERCHANT_API_KEY is missing.")
        return

    web_app = web.Application(client_max_size=64 * 1024)
    web_app["telegram_app"] = telegram_app
    web_app["activate_payment"] = activate
    web_app.router.add_post("/oxapay/webhook", _webhook)
    web_app.router.add_get("/health", _health)

    runner = web.AppRunner(web_app, access_log=None)
    await runner.setup()
    port = int(os.environ.get("PORT", "8080"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    telegram_app.bot_data["_oxapay_runner"] = runner
    telegram_app.bot_data["_oxapay_reconcile_task"] = asyncio.create_task(
        _reconcile_pending(telegram_app, activate),
        name="oxapay-payment-reconciliation",
    )
    logger.info("[OXAPAY] Webhook listening on port %s.", port)


async def stop_webhook(telegram_app) -> None:
    task = telegram_app.bot_data.pop("_oxapay_reconcile_task", None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    runner = telegram_app.bot_data.pop("_oxapay_runner", None)
    if runner:
        await runner.cleanup()
"""Secure payment invoices and webhook processing for the Telegram bot."""
# Duplicate copy retained as inert-compatible Python; no future import here.

import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from decimal import Decimal, InvalidOperation
from typing import Awaitable, Callable

import aiohttp
from aiohttp import web

import database as db

logger = logging.getLogger(__name__)


class OxaPayTemporaryResponseError(RuntimeError):
    """OxaPay/proxy returned no usable API document; retry may succeed."""


OXAPAY_API_BASE = "https://api.oxapay.com/v1"
SUCCESS_STATUSES = frozenset({
    "paid",
    "manual_accept",
    "completed",
    "complete",
    "confirmed",
})
_ACTIVATION_LOCKS: dict[int, asyncio.Lock] = {}
WHITE_LABEL_MAX_ATTEMPTS = 4
RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})

PLANS = {
    "pay1d": {"name": "Core", "plan": "CORE", "days": 1, "price": Decimal("1.50")},
    "pay10": {"name": "Core", "plan": "CORE", "days": 7, "price": Decimal("8.00")},
    "pay15": {"name": "Elite", "plan": "ELITE", "days": 15, "price": Decimal("12.00")},
    "pay30": {"name": "Root", "plan": "ROOT", "days": 30, "price": Decimal("25.00")},
}

PAYMENT_METHODS = {
    "bep20": {
        "label": "BEP20", "pay_currency": "USDT", "network": "BSC",
        "network_name": "Binance Smart Chain",
    },
    "trx": {
        "label": "TRX", "pay_currency": "TRX", "network": "Tron",
        "network_name": "Tron Network",
    },
    "pol": {
        "label": "POL", "pay_currency": "POL", "network": "Polygon",
        "network_name": "Polygon Network",
    },
    "ton": {
        "label": "TON", "pay_currency": "GRAM", "network": "The Open Network",
        "network_name": "TON Network",
    },
    "ltc": {
        "label": "LTC", "pay_currency": "LTC", "network": "Litecoin",
        "network_name": "Litecoin Network",
    },
    "btc": {
        "label": "BTC", "pay_currency": "BTC", "network": "Bitcoin",
        "network_name": "Bitcoin Network",
    },
    "sol": {
        "label": "SOL", "pay_currency": "SOL", "network": "Solana",
        "network_name": "Solana Network",
    },
    "eth": {
        "label": "ETH", "pay_currency": "ETH", "network": "Ethereum",
        "network_name": "Ethereum Network",
    },
}

_accepted_cache: tuple[float, frozenset[str]] | None = None
ACCEPTED_CACHE_TTL = 30
ACCEPTED_STALE_TTL = 15 * 60


def _api_key() -> str:
    return os.environ.get("OXAPAY_MERCHANT_API_KEY", "").strip()


def _callback_url() -> str:
    return os.environ.get("OXAPAY_CALLBACK_URL", "").strip()


def _sandbox_enabled() -> bool:
    return os.environ["OXAPAY_SANDBOX"].strip().lower() == "true"


def configuration_error() -> str | None:
    if not _api_key():
        return "OXAPAY_MERCHANT_API_KEY is not configured."
    callback = _callback_url()
    if not callback:
        return "OXAPAY_CALLBACK_URL is not configured."
    if not callback.startswith("https://"):
        return "OXAPAY_CALLBACK_URL must use https://."
    sandbox = os.environ.get("OXAPAY_SANDBOX", "").strip().lower()
    if sandbox not in {"true", "false"}:
        return "OXAPAY_SANDBOX must be set explicitly to true or false."
    if sandbox == "true":
        return (
            "Direct OxaPay crypto addresses require live mode. "
            "Set OXAPAY_SANDBOX=false."
        )
    if not db.is_connected():
        return "PostgreSQL is unavailable; secure payment orders cannot be created."
    return None


async def _read_oxapay_json(
    response: aiohttp.ClientResponse,
    operation: str,
) -> dict:
    """Decode an OxaPay response without exposing raw proxy/HTML errors."""
    body = await response.text()
    if not body.strip():
        raise OxaPayTemporaryResponseError(
            f"OxaPay returned an empty response while {operation}. "
            "Please try again in a moment."
        )
    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        logger.warning(
            "[OXAPAY] Non-JSON response while %s: status=%s content_type=%s bytes=%s",
            operation,
            response.status,
            response.headers.get("Content-Type", ""),
            len(body.encode("utf-8", errors="replace")),
        )
        raise OxaPayTemporaryResponseError(
            f"OxaPay returned an invalid response while {operation}. "
            "Please try again in a moment."
        ) from exc
    if not isinstance(result, dict):
        raise OxaPayTemporaryResponseError(
            f"OxaPay returned an unexpected response while {operation}. "
            "Please try again in a moment."
        )
    return result


def _api_status(result: dict) -> int:
    """Return OxaPay's API status without allowing malformed values to crash."""
    try:
        return int(result.get("status", 0))
    except (TypeError, ValueError):
        return 0


async def _retry_temporary(
    operation: Callable[[], Awaitable[dict]],
    *,
    name: str,
    attempts: int = WHITE_LABEL_MAX_ATTEMPTS,
) -> dict:
    """Retry temporary provider/transport failures with bounded backoff."""
    last_error: BaseException | None = None
    total_attempts = max(1, int(attempts))
    for attempt in range(1, total_attempts + 1):
        try:
            return await operation()
        except (
            OxaPayTemporaryResponseError,
            aiohttp.ClientError,
            asyncio.TimeoutError,
        ) as exc:
            last_error = exc
            if attempt >= total_attempts:
                break
            delay = min(4.0, 0.65 * (2 ** (attempt - 1)))
            delay += secrets.randbelow(250) / 1000
            logger.warning(
                "[OXAPAY] Temporary failure while %s; retrying attempt %s/%s "
                "in %.2fs (%s)",
                name,
                attempt + 1,
                total_attempts,
                delay,
                type(exc).__name__,
            )
            await asyncio.sleep(delay)
    raise OxaPayTemporaryResponseError(
        "OxaPay is temporarily unavailable after several automatic retries. "
        "Please press Retry Payment."
    ) from last_error


async def get_accepted_method_keys(force: bool = False) -> list[str]:
    """Return only payment methods enabled for this OxaPay merchant."""
    global _accepted_cache
    error = configuration_error()
    if error:
        raise RuntimeError(error)
    now = time.monotonic()
    if (
        not force
        and _accepted_cache
        and now - _accepted_cache[0] < ACCEPTED_CACHE_TTL
    ):
        accepted = _accepted_cache[1]
    else:
        headers = {
            "merchant_api_key": _api_key(),
            "Content-Type": "application/json",
        }
        timeout = aiohttp.ClientTimeout(
            total=10,
            connect=5,
            sock_connect=5,
            sock_read=7,
        )
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"{OXAPAY_API_BASE}/payment/accepted-currencies",
                    headers=headers,
                ) as response:
                    result = await _read_oxapay_json(
                        response,
                        "loading payment methods",
                    )
                    response_status = response.status
            if response_status != 200 or _api_status(result) != 200:
                raise RuntimeError(
                    _oxapay_error(
                        result,
                        "Could not load accepted OxaPay currencies.",
                    )
                )
            values = (result.get("data") or {}).get("list") or []
            accepted = frozenset(str(value).upper() for value in values)
            if not accepted:
                raise RuntimeError("OxaPay returned no accepted currencies.")
            _accepted_cache = (now, accepted)
        except (
            OxaPayTemporaryResponseError,
            aiohttp.ClientError,
            asyncio.TimeoutError,
        ):
            if (
                _accepted_cache
                and now - _accepted_cache[0] < ACCEPTED_STALE_TTL
            ):
                accepted = _accepted_cache[1]
                logger.warning(
                    "[OXAPAY] Using cached accepted currencies after a "
                    "temporary API response failure."
                )
            else:
                # Currency discovery is optional. Address creation remains
                # authoritative and rejects any disabled merchant currency.
                accepted = frozenset(
                    method["pay_currency"].upper()
                    for method in PAYMENT_METHODS.values()
                )
                logger.warning(
                    "[OXAPAY] Accepted-currencies API unavailable; showing "
                    "configured methods and deferring validation to payment "
                    "address creation."
                )

    return [
        key
        for key, method in PAYMENT_METHODS.items()
        if method["pay_currency"].upper() in accepted
    ]


async def create_white_label_payment(
    user_id: int,
    plan_selection: str,
    method_selection: str,
) -> dict:
    error = configuration_error()
    if error:
        raise RuntimeError(error)
    plan = PLANS.get(plan_selection)
    if not plan:
        raise ValueError("Unknown payment plan.")
    method = PAYMENT_METHODS.get(method_selection)
    if not method:
        raise ValueError("Unknown payment method.")
    accepted_methods = await get_accepted_method_keys(force=True)
    if method_selection not in accepted_methods:
        raise RuntimeError(
            f"{method['label']} is not enabled in your OxaPay Merchant Service."
        )

    order_id = f"tg-{user_id}-{secrets.token_hex(12)}"
    created = await db.create_payment_order(
        order_id=order_id,
        user_id=user_id,
        plan=plan["plan"],
        days=plan["days"],
        expected_amount=plan["price"],
        currency="USD",
    )
    if not created:
        raise RuntimeError("Could not store the payment order.")

    payload = {
        "amount": float(plan["price"]),
        "currency": "USD",
        "pay_currency": method["pay_currency"],
        "network": method["network"],
        "lifetime": 120,
        "fee_paid_by_payer": 1,
        "under_paid_coverage": 0,
        "callback_url": _callback_url(),
        "order_id": order_id,
        "description": f"{plan['name']} plan for Telegram user {user_id}",
    }
    headers = {
        "merchant_api_key": _api_key(),
        "Content-Type": "application/json",
    }

    try:
        timeout = aiohttp.ClientTimeout(
            total=20,
            connect=7,
            sock_connect=7,
            sock_read=12,
        )
        connector = aiohttp.TCPConnector(
            ttl_dns_cache=300,
            enable_cleanup_closed=True,
        )
        async with aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            headers={"Accept": "application/json"},
        ) as session:
            async def request_payment() -> dict:
                async with session.post(
                    f"{OXAPAY_API_BASE}/payment/white-label",
                    headers=headers,
                    json=payload,
                ) as response:
                    result = await _read_oxapay_json(
                        response,
                        "creating the payment address",
                    )
                    if response.status in RETRYABLE_HTTP_STATUSES:
                        raise OxaPayTemporaryResponseError(
                            "OxaPay temporarily could not create the payment address."
                        )
                    api_status = _api_status(result)
                    if api_status in RETRYABLE_HTTP_STATUSES:
                        raise OxaPayTemporaryResponseError(
                            "OxaPay temporarily could not create the payment address."
                        )
                    if response.status != 200 or api_status != 200:
                        # Parsed merchant/authentication/currency errors are
                        # authoritative and must not be hidden by retries.
                        raise RuntimeError(
                            _oxapay_error(
                                result,
                                "OxaPay rejected the payment request.",
                            )
                        )
                    response_data = result.get("data")
                    if not isinstance(response_data, dict):
                        raise OxaPayTemporaryResponseError(
                            "OxaPay returned incomplete payment information."
                        )
                    required = (
                        response_data.get("track_id"),
                        response_data.get("address"),
                        response_data.get("pay_amount"),
                        response_data.get("expired_at"),
                    )
                    if any(value in (None, "", 0, "0") for value in required):
                        raise OxaPayTemporaryResponseError(
                            "OxaPay returned incomplete payment information."
                        )
                    return result

            result = await _retry_temporary(
                request_payment,
                name="creating the payment address",
            )

        data = result.get("data") or {}
        track_id = str(data.get("track_id") or "").strip()
        address = str(data.get("address") or "").strip()
        pay_amount = str(data.get("pay_amount") or "").strip()
        pay_currency = str(data.get("pay_currency") or method["pay_currency"]).upper()
        network_name = method["network_name"]
        memo = str(data.get("memo") or "").strip()
        expired_at = int(data.get("expired_at") or 0)
        if not track_id or not address or not pay_amount or expired_at <= 0:
            raise RuntimeError("OxaPay returned incomplete payment information.")

        saved = await db.attach_payment_invoice(order_id, track_id, "")
        if not saved:
            raise RuntimeError("Could not save the OxaPay payment.")

        return {
            "order_id": order_id,
            "track_id": track_id,
            "address": address,
            "pay_amount": pay_amount,
            "pay_currency": pay_currency,
            "network_name": network_name,
            "memo": memo,
            "expired_at": expired_at,
            "lifetime": int(data.get("lifetime") or 120),
            **plan,
            "method": method,
        }
    except Exception as exc:
        await db.fail_payment_order(order_id, str(exc))
        raise


async def _fetch_payment(track_id: str) -> dict:
    headers = {
        "merchant_api_key": _api_key(),
        "Content-Type": "application/json",
    }
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(
            f"{OXAPAY_API_BASE}/payment/{track_id}",
            headers=headers,
        ) as response:
            result = await _read_oxapay_json(
                response,
                "verifying the payment",
            )
    if response.status != 200 or _api_status(result) != 200:
        raise RuntimeError(_oxapay_error(result, "Payment verification failed."))
    return result.get("data") or {}


def _decimal(value) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("-1")


def _oxapay_error(result: dict, fallback: str) -> str:
    error = result.get("error")
    if isinstance(error, dict):
        detail = str(error.get("message") or "").strip()
        key = str(error.get("key") or "").strip()
        if detail:
            return f"{key}: {detail}" if key else detail
    return str(result.get("message") or fallback)


def _payment_field(data: dict, snake_case: str, camel_case: str = ""):
    value = data.get(snake_case)
    if value in (None, "") and camel_case:
        value = data.get(camel_case)
    return value


async def _deliver_activation(
    app,
    order_id: str,
    activate: Callable[[object, dict], Awaitable[None]],
) -> None:
    claim_token = secrets.token_hex(16)
    entitlement = await db.claim_payment_activation(order_id, claim_token)
    if not entitlement:
        return
    user_id = int(entitlement["user_id"])
    lock = _ACTIVATION_LOCKS.setdefault(user_id, asyncio.Lock())
    try:
        async with lock:
            # Another order for this user may have finalized while this older
            # delivery was waiting. Always activate the canonical latest row.
            current = await db.get_current_payment_entitlement(user_id)
            if not current:
                raise RuntimeError("Canonical paid entitlement is unavailable.")
            await activate(app, current)
            if not await db.mark_payment_activated(order_id, claim_token):
                raise RuntimeError("Could not mark payment activation delivered.")
    except Exception:
        await db.release_payment_activation(order_id, claim_token)
        raise


async def _process_callback(
    app,
    callback_data: dict,
    activate: Callable[[object, dict], Awaitable[None]],
    trusted_callback: bool = False,
) -> None:
    data = callback_data.get("data") if isinstance(callback_data.get("data"), dict) else callback_data
    track_id = str(_payment_field(data, "track_id", "trackId") or "").strip()
    order_id = str(_payment_field(data, "order_id", "orderId") or "").strip()
    if not track_id or not order_id:
        return

    callback_status = str(data.get("status") or "").strip().lower()
    if trusted_callback and callback_status not in SUCCESS_STATUSES:
        return

    # A callback reaching this trusted path has already passed OxaPay's
    # raw-body HMAC verification. Use it immediately when it contains all
    # fields required to bind the payment to the stored order. Reconciliation
    # uses OxaPay's read API when a callback was missed.
    verified = data if trusted_callback else {}
    required_callback_fields = (
        _payment_field(data, "track_id", "trackId"),
        _payment_field(data, "order_id", "orderId"),
        data.get("status"),
        data.get("currency"),
        data.get("amount"),
    )
    if not trusted_callback or any(value in (None, "") for value in required_callback_fields):
        verified = await _fetch_payment(track_id)

    verified_status = str(verified.get("status") or "").strip().lower()
    if verified_status not in SUCCESS_STATUSES:
        return
    if str(_payment_field(verified, "track_id", "trackId") or "").strip() != track_id:
        raise RuntimeError("OxaPay track ID verification failed.")
    if str(_payment_field(verified, "order_id", "orderId") or "").strip() != order_id:
        raise RuntimeError("OxaPay order ID verification failed.")

    order = await db.get_payment_order(order_id)
    if not order:
        raise RuntimeError("Unknown OxaPay order.")
    if order["status"] == "paid":
        await _deliver_activation(app, order_id, activate)
        return
    if str(order.get("track_id") or "") != track_id:
        raise RuntimeError("Stored OxaPay track ID does not match.")
    if str(verified.get("currency") or "").upper() != str(order["currency"]).upper():
        raise RuntimeError("OxaPay payment currency does not match the order.")
    verified_amount = _decimal(verified.get("amount"))
    expected_amount = _decimal(order["expected_amount"])
    if (
        not verified_amount.is_finite()
        or not expected_amount.is_finite()
        or expected_amount <= 0
        or verified_amount < expected_amount
    ):
        raise RuntimeError("OxaPay payment amount is below the order amount.")

    entitlement = await db.finalize_paid_order(order_id, track_id)
    if not entitlement:
        return
    await _deliver_activation(app, order_id, activate)


async def _reconcile_pending(
    telegram_app,
    activate: Callable[[object, dict], Awaitable[None]],
) -> None:
    """Recover paid orders when a webhook is delayed, lost, or raced."""
    delay = 3
    while True:
        try:
            await asyncio.sleep(delay)
            delay = 2
            pending = await db.list_pending_payment_orders(limit=100)
            for order in pending:
                try:
                    await _process_callback(
                        telegram_app,
                        {
                            "track_id": order["track_id"],
                            "order_id": order["order_id"],
                        },
                        activate,
                        trusted_callback=False,
                    )
                except Exception as exc:
                    logger.warning(
                        "[OXAPAY] Pending order %s reconciliation deferred: %s",
                        order["order_id"],
                        exc,
                    )
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("[OXAPAY] Pending-payment reconciliation failed.")
            await asyncio.sleep(2)


async def _webhook(request: web.Request) -> web.Response:
    raw_body = await request.read()
    received = request.headers.get("HMAC", "").strip().lower()
    expected = hmac.new(
        _api_key().encode("utf-8"),
        raw_body,
        hashlib.sha512,
    ).hexdigest()
    if not received or not hmac.compare_digest(received, expected):
        return web.Response(text="Invalid HMAC", status=401)
    try:
        payload = json.loads(raw_body.decode("utf-8"))
        await _process_callback(
            request.app["telegram_app"],
            payload,
            request.app["activate_payment"],
            trusted_callback=True,
        )
    except (UnicodeDecodeError, json.JSONDecodeError):
        return web.Response(text="Invalid JSON", status=400)
    except Exception:
        logger.exception("[OXAPAY] Callback processing failed.")
        return web.Response(text="Temporary failure", status=500)
    return web.Response(text="OK", status=200)


async def _health(_request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "service": "oxapay-webhook"})


async def start_webhook(
    telegram_app,
    activate: Callable[[object, dict], Awaitable[None]],
) -> None:
    if not _api_key():
        logger.warning("[OXAPAY] Disabled: OXAPAY_MERCHANT_API_KEY is missing.")
        return

    web_app = web.Application(client_max_size=64 * 1024)
    web_app["telegram_app"] = telegram_app
    web_app["activate_payment"] = activate
    web_app.router.add_post("/oxapay/webhook", _webhook)
    web_app.router.add_get("/health", _health)

    runner = web.AppRunner(web_app, access_log=None)
    await runner.setup()
    port = int(os.environ.get("PORT", "8080"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    telegram_app.bot_data["_oxapay_runner"] = runner
    telegram_app.bot_data["_oxapay_reconcile_task"] = asyncio.create_task(
        _reconcile_pending(telegram_app, activate),
        name="oxapay-payment-reconciliation",
    )
    logger.info("[OXAPAY] Webhook listening on port %s.", port)


async def stop_webhook(telegram_app) -> None:
    task = telegram_app.bot_data.pop("_oxapay_reconcile_task", None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    runner = telegram_app.bot_data.pop("_oxapay_runner", None)
    if runner:
        await runner.cleanup()
"""Secure payment invoices and webhook processing for the Telegram bot."""
# Duplicate copy retained as inert-compatible Python; no future import here.

import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from decimal import Decimal, InvalidOperation
from typing import Awaitable, Callable

import aiohttp
from aiohttp import web

import database as db

logger = logging.getLogger(__name__)


class OxaPayTemporaryResponseError(RuntimeError):
    """OxaPay/proxy returned no usable API document; retry may succeed."""


OXAPAY_API_BASE = "https://api.oxapay.com/v1"
SUCCESS_STATUSES = frozenset({
    "paid",
    "manual_accept",
    "completed",
    "complete",
    "confirmed",
})
_ACTIVATION_LOCKS: dict[int, asyncio.Lock] = {}
WHITE_LABEL_MAX_ATTEMPTS = 4
RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})

PLANS = {
    "pay1d": {"name": "Core", "plan": "CORE", "days": 1, "price": Decimal("1.50")},
    "pay10": {"name": "Core", "plan": "CORE", "days": 7, "price": Decimal("8.00")},
    "pay15": {"name": "Elite", "plan": "ELITE", "days": 15, "price": Decimal("12.00")},
    "pay30": {"name": "Root", "plan": "ROOT", "days": 30, "price": Decimal("25.00")},
}

PAYMENT_METHODS = {
    "bep20": {
        "label": "BEP20", "pay_currency": "USDT", "network": "BSC",
        "network_name": "Binance Smart Chain",
    },
    "trx": {
        "label": "TRX", "pay_currency": "TRX", "network": "Tron",
        "network_name": "Tron Network",
    },
    "pol": {
        "label": "POL", "pay_currency": "POL", "network": "Polygon",
        "network_name": "Polygon Network",
    },
    "ton": {
        "label": "TON", "pay_currency": "GRAM", "network": "The Open Network",
        "network_name": "TON Network",
    },
    "ltc": {
        "label": "LTC", "pay_currency": "LTC", "network": "Litecoin",
        "network_name": "Litecoin Network",
    },
    "btc": {
        "label": "BTC", "pay_currency": "BTC", "network": "Bitcoin",
        "network_name": "Bitcoin Network",
    },
    "sol": {
        "label": "SOL", "pay_currency": "SOL", "network": "Solana",
        "network_name": "Solana Network",
    },
    "eth": {
        "label": "ETH", "pay_currency": "ETH", "network": "Ethereum",
        "network_name": "Ethereum Network",
    },
}

_accepted_cache: tuple[float, frozenset[str]] | None = None
ACCEPTED_CACHE_TTL = 30
ACCEPTED_STALE_TTL = 15 * 60


def _api_key() -> str:
    return os.environ.get("OXAPAY_MERCHANT_API_KEY", "").strip()


def _callback_url() -> str:
    return os.environ.get("OXAPAY_CALLBACK_URL", "").strip()


def _sandbox_enabled() -> bool:
    return os.environ["OXAPAY_SANDBOX"].strip().lower() == "true"


def configuration_error() -> str | None:
    if not _api_key():
        return "OXAPAY_MERCHANT_API_KEY is not configured."
    callback = _callback_url()
    if not callback:
        return "OXAPAY_CALLBACK_URL is not configured."
    if not callback.startswith("https://"):
        return "OXAPAY_CALLBACK_URL must use https://."
    sandbox = os.environ.get("OXAPAY_SANDBOX", "").strip().lower()
    if sandbox not in {"true", "false"}:
        return "OXAPAY_SANDBOX must be set explicitly to true or false."
    if sandbox == "true":
        return (
            "Direct OxaPay crypto addresses require live mode. "
            "Set OXAPAY_SANDBOX=false."
        )
    if not db.is_connected():
        return "PostgreSQL is unavailable; secure payment orders cannot be created."
    return None


async def _read_oxapay_json(
    response: aiohttp.ClientResponse,
    operation: str,
) -> dict:
    """Decode an OxaPay response without exposing raw proxy/HTML errors."""
    body = await response.text()
    if not body.strip():
        raise OxaPayTemporaryResponseError(
            f"OxaPay returned an empty response while {operation}. "
            "Please try again in a moment."
        )
    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        logger.warning(
            "[OXAPAY] Non-JSON response while %s: status=%s content_type=%s bytes=%s",
            operation,
            response.status,
            response.headers.get("Content-Type", ""),
            len(body.encode("utf-8", errors="replace")),
        )
        raise OxaPayTemporaryResponseError(
            f"OxaPay returned an invalid response while {operation}. "
            "Please try again in a moment."
        ) from exc
    if not isinstance(result, dict):
        raise OxaPayTemporaryResponseError(
            f"OxaPay returned an unexpected response while {operation}. "
            "Please try again in a moment."
        )
    return result


def _api_status(result: dict) -> int:
    """Return OxaPay's API status without allowing malformed values to crash."""
    try:
        return int(result.get("status", 0))
    except (TypeError, ValueError):
        return 0


async def _retry_temporary(
    operation: Callable[[], Awaitable[dict]],
    *,
    name: str,
    attempts: int = WHITE_LABEL_MAX_ATTEMPTS,
) -> dict:
    """Retry temporary provider/transport failures with bounded backoff."""
    last_error: BaseException | None = None
    total_attempts = max(1, int(attempts))
    for attempt in range(1, total_attempts + 1):
        try:
            return await operation()
        except (
            OxaPayTemporaryResponseError,
            aiohttp.ClientError,
            asyncio.TimeoutError,
        ) as exc:
            last_error = exc
            if attempt >= total_attempts:
                break
            delay = min(4.0, 0.65 * (2 ** (attempt - 1)))
            delay += secrets.randbelow(250) / 1000
            logger.warning(
                "[OXAPAY] Temporary failure while %s; retrying attempt %s/%s "
                "in %.2fs (%s)",
                name,
                attempt + 1,
                total_attempts,
                delay,
                type(exc).__name__,
            )
            await asyncio.sleep(delay)
    raise OxaPayTemporaryResponseError(
        "OxaPay is temporarily unavailable after several automatic retries. "
        "Please press Retry Payment."
    ) from last_error


async def get_accepted_method_keys(force: bool = False) -> list[str]:
    """Return only payment methods enabled for this OxaPay merchant."""
    global _accepted_cache
    error = configuration_error()
    if error:
        raise RuntimeError(error)
    now = time.monotonic()
    if (
        not force
        and _accepted_cache
        and now - _accepted_cache[0] < ACCEPTED_CACHE_TTL
    ):
        accepted = _accepted_cache[1]
    else:
        headers = {
            "merchant_api_key": _api_key(),
            "Content-Type": "application/json",
        }
        timeout = aiohttp.ClientTimeout(
            total=10,
            connect=5,
            sock_connect=5,
            sock_read=7,
        )
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"{OXAPAY_API_BASE}/payment/accepted-currencies",
                    headers=headers,
                ) as response:
                    result = await _read_oxapay_json(
                        response,
                        "loading payment methods",
                    )
                    response_status = response.status
            if response_status != 200 or _api_status(result) != 200:
                raise RuntimeError(
                    _oxapay_error(
                        result,
                        "Could not load accepted OxaPay currencies.",
                    )
                )
            values = (result.get("data") or {}).get("list") or []
            accepted = frozenset(str(value).upper() for value in values)
            if not accepted:
                raise RuntimeError("OxaPay returned no accepted currencies.")
            _accepted_cache = (now, accepted)
        except (
            OxaPayTemporaryResponseError,
            aiohttp.ClientError,
            asyncio.TimeoutError,
        ):
            if (
                _accepted_cache
                and now - _accepted_cache[0] < ACCEPTED_STALE_TTL
            ):
                accepted = _accepted_cache[1]
                logger.warning(
                    "[OXAPAY] Using cached accepted currencies after a "
                    "temporary API response failure."
                )
            else:
                # Currency discovery is optional. Address creation remains
                # authoritative and rejects any disabled merchant currency.
                accepted = frozenset(
                    method["pay_currency"].upper()
                    for method in PAYMENT_METHODS.values()
                )
                logger.warning(
                    "[OXAPAY] Accepted-currencies API unavailable; showing "
                    "configured methods and deferring validation to payment "
                    "address creation."
                )

    return [
        key
        for key, method in PAYMENT_METHODS.items()
        if method["pay_currency"].upper() in accepted
    ]


async def create_white_label_payment(
    user_id: int,
    plan_selection: str,
    method_selection: str,
) -> dict:
    error = configuration_error()
    if error:
        raise RuntimeError(error)
    plan = PLANS.get(plan_selection)
    if not plan:
        raise ValueError("Unknown payment plan.")
    method = PAYMENT_METHODS.get(method_selection)
    if not method:
        raise ValueError("Unknown payment method.")
    accepted_methods = await get_accepted_method_keys(force=True)
    if method_selection not in accepted_methods:
        raise RuntimeError(
            f"{method['label']} is not enabled in your OxaPay Merchant Service."
        )

    order_id = f"tg-{user_id}-{secrets.token_hex(12)}"
    created = await db.create_payment_order(
        order_id=order_id,
        user_id=user_id,
        plan=plan["plan"],
        days=plan["days"],
        expected_amount=plan["price"],
        currency="USD",
    )
    if not created:
        raise RuntimeError("Could not store the payment order.")

    payload = {
        "amount": float(plan["price"]),
        "currency": "USD",
        "pay_currency": method["pay_currency"],
        "network": method["network"],
        "lifetime": 120,
        "fee_paid_by_payer": 1,
        "under_paid_coverage": 0,
        "callback_url": _callback_url(),
        "order_id": order_id,
        "description": f"{plan['name']} plan for Telegram user {user_id}",
    }
    headers = {
        "merchant_api_key": _api_key(),
        "Content-Type": "application/json",
    }

    try:
        timeout = aiohttp.ClientTimeout(
            total=20,
            connect=7,
            sock_connect=7,
            sock_read=12,
        )
        connector = aiohttp.TCPConnector(
            ttl_dns_cache=300,
            enable_cleanup_closed=True,
        )
        async with aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            headers={"Accept": "application/json"},
        ) as session:
            async def request_payment() -> dict:
                async with session.post(
                    f"{OXAPAY_API_BASE}/payment/white-label",
                    headers=headers,
                    json=payload,
                ) as response:
                    result = await _read_oxapay_json(
                        response,
                        "creating the payment address",
                    )
                    if response.status in RETRYABLE_HTTP_STATUSES:
                        raise OxaPayTemporaryResponseError(
                            "OxaPay temporarily could not create the payment address."
                        )
                    api_status = _api_status(result)
                    if api_status in RETRYABLE_HTTP_STATUSES:
                        raise OxaPayTemporaryResponseError(
                            "OxaPay temporarily could not create the payment address."
                        )
                    if response.status != 200 or api_status != 200:
                        # Parsed merchant/authentication/currency errors are
                        # authoritative and must not be hidden by retries.
                        raise RuntimeError(
                            _oxapay_error(
                                result,
                                "OxaPay rejected the payment request.",
                            )
                        )
                    response_data = result.get("data")
                    if not isinstance(response_data, dict):
                        raise OxaPayTemporaryResponseError(
                            "OxaPay returned incomplete payment information."
                        )
                    required = (
                        response_data.get("track_id"),
                        response_data.get("address"),
                        response_data.get("pay_amount"),
                        response_data.get("expired_at"),
                    )
                    if any(value in (None, "", 0, "0") for value in required):
                        raise OxaPayTemporaryResponseError(
                            "OxaPay returned incomplete payment information."
                        )
                    return result

            result = await _retry_temporary(
                request_payment,
                name="creating the payment address",
            )

        data = result.get("data") or {}
        track_id = str(data.get("track_id") or "").strip()
        address = str(data.get("address") or "").strip()
        pay_amount = str(data.get("pay_amount") or "").strip()
        pay_currency = str(data.get("pay_currency") or method["pay_currency"]).upper()
        network_name = method["network_name"]
        memo = str(data.get("memo") or "").strip()
        expired_at = int(data.get("expired_at") or 0)
        if not track_id or not address or not pay_amount or expired_at <= 0:
            raise RuntimeError("OxaPay returned incomplete payment information.")

        saved = await db.attach_payment_invoice(order_id, track_id, "")
        if not saved:
            raise RuntimeError("Could not save the OxaPay payment.")

        return {
            "order_id": order_id,
            "track_id": track_id,
            "address": address,
            "pay_amount": pay_amount,
            "pay_currency": pay_currency,
            "network_name": network_name,
            "memo": memo,
            "expired_at": expired_at,
            "lifetime": int(data.get("lifetime") or 120),
            **plan,
            "method": method,
        }
    except Exception as exc:
        await db.fail_payment_order(order_id, str(exc))
        raise


async def _fetch_payment(track_id: str) -> dict:
    headers = {
        "merchant_api_key": _api_key(),
        "Content-Type": "application/json",
    }
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(
            f"{OXAPAY_API_BASE}/payment/{track_id}",
            headers=headers,
        ) as response:
            result = await _read_oxapay_json(
                response,
                "verifying the payment",
            )
    if response.status != 200 or _api_status(result) != 200:
        raise RuntimeError(_oxapay_error(result, "Payment verification failed."))
    return result.get("data") or {}


def _decimal(value) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("-1")


def _oxapay_error(result: dict, fallback: str) -> str:
    error = result.get("error")
    if isinstance(error, dict):
        detail = str(error.get("message") or "").strip()
        key = str(error.get("key") or "").strip()
        if detail:
            return f"{key}: {detail}" if key else detail
    return str(result.get("message") or fallback)


def _payment_field(data: dict, snake_case: str, camel_case: str = ""):
    value = data.get(snake_case)
    if value in (None, "") and camel_case:
        value = data.get(camel_case)
    return value


async def _deliver_activation(
    app,
    order_id: str,
    activate: Callable[[object, dict], Awaitable[None]],
) -> None:
    claim_token = secrets.token_hex(16)
    entitlement = await db.claim_payment_activation(order_id, claim_token)
    if not entitlement:
        return
    user_id = int(entitlement["user_id"])
    lock = _ACTIVATION_LOCKS.setdefault(user_id, asyncio.Lock())
    try:
        async with lock:
            # Another order for this user may have finalized while this older
            # delivery was waiting. Always activate the canonical latest row.
            current = await db.get_current_payment_entitlement(user_id)
            if not current:
                raise RuntimeError("Canonical paid entitlement is unavailable.")
            await activate(app, current)
            if not await db.mark_payment_activated(order_id, claim_token):
                raise RuntimeError("Could not mark payment activation delivered.")
    except Exception:
        await db.release_payment_activation(order_id, claim_token)
        raise


async def _process_callback(
    app,
    callback_data: dict,
    activate: Callable[[object, dict], Awaitable[None]],
    trusted_callback: bool = False,
) -> None:
    data = callback_data.get("data") if isinstance(callback_data.get("data"), dict) else callback_data
    track_id = str(_payment_field(data, "track_id", "trackId") or "").strip()
    order_id = str(_payment_field(data, "order_id", "orderId") or "").strip()
    if not track_id or not order_id:
        return

    callback_status = str(data.get("status") or "").strip().lower()
    if trusted_callback and callback_status not in SUCCESS_STATUSES:
        return

    # A callback reaching this trusted path has already passed OxaPay's
    # raw-body HMAC verification. Use it immediately when it contains all
    # fields required to bind the payment to the stored order. Reconciliation
    # uses OxaPay's read API when a callback was missed.
    verified = data if trusted_callback else {}
    required_callback_fields = (
        _payment_field(data, "track_id", "trackId"),
        _payment_field(data, "order_id", "orderId"),
        data.get("status"),
        data.get("currency"),
        data.get("amount"),
    )
    if not trusted_callback or any(value in (None, "") for value in required_callback_fields):
        verified = await _fetch_payment(track_id)

    verified_status = str(verified.get("status") or "").strip().lower()
    if verified_status not in SUCCESS_STATUSES:
        return
    if str(_payment_field(verified, "track_id", "trackId") or "").strip() != track_id:
        raise RuntimeError("OxaPay track ID verification failed.")
    if str(_payment_field(verified, "order_id", "orderId") or "").strip() != order_id:
        raise RuntimeError("OxaPay order ID verification failed.")

    order = await db.get_payment_order(order_id)
    if not order:
        raise RuntimeError("Unknown OxaPay order.")
    if order["status"] == "paid":
        await _deliver_activation(app, order_id, activate)
        return
    if str(order.get("track_id") or "") != track_id:
        raise RuntimeError("Stored OxaPay track ID does not match.")
    if str(verified.get("currency") or "").upper() != str(order["currency"]).upper():
        raise RuntimeError("OxaPay payment currency does not match the order.")
    verified_amount = _decimal(verified.get("amount"))
    expected_amount = _decimal(order["expected_amount"])
    if (
        not verified_amount.is_finite()
        or not expected_amount.is_finite()
        or expected_amount <= 0
        or verified_amount < expected_amount
    ):
        raise RuntimeError("OxaPay payment amount is below the order amount.")

    entitlement = await db.finalize_paid_order(order_id, track_id)
    if not entitlement:
        return
    await _deliver_activation(app, order_id, activate)


async def _reconcile_pending(
    telegram_app,
    activate: Callable[[object, dict], Awaitable[None]],
) -> None:
    """Recover paid orders when a webhook is delayed, lost, or raced."""
    delay = 3
    while True:
        try:
            await asyncio.sleep(delay)
            delay = 2
            pending = await db.list_pending_payment_orders(limit=100)
            for order in pending:
                try:
                    await _process_callback(
                        telegram_app,
                        {
                            "track_id": order["track_id"],
                            "order_id": order["order_id"],
                        },
                        activate,
                        trusted_callback=False,
                    )
                except Exception as exc:
                    logger.warning(
                        "[OXAPAY] Pending order %s reconciliation deferred: %s",
                        order["order_id"],
                        exc,
                    )
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("[OXAPAY] Pending-payment reconciliation failed.")
            await asyncio.sleep(2)


async def _webhook(request: web.Request) -> web.Response:
    raw_body = await request.read()
    received = request.headers.get("HMAC", "").strip().lower()
    expected = hmac.new(
        _api_key().encode("utf-8"),
        raw_body,
        hashlib.sha512,
    ).hexdigest()
    if not received or not hmac.compare_digest(received, expected):
        return web.Response(text="Invalid HMAC", status=401)
    try:
        payload = json.loads(raw_body.decode("utf-8"))
        await _process_callback(
            request.app["telegram_app"],
            payload,
            request.app["activate_payment"],
            trusted_callback=True,
        )
    except (UnicodeDecodeError, json.JSONDecodeError):
        return web.Response(text="Invalid JSON", status=400)
    except Exception:
        logger.exception("[OXAPAY] Callback processing failed.")
        return web.Response(text="Temporary failure", status=500)
    return web.Response(text="OK", status=200)


async def _health(_request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "service": "oxapay-webhook"})


async def start_webhook(
    telegram_app,
    activate: Callable[[object, dict], Awaitable[None]],
) -> None:
    if not _api_key():
        logger.warning("[OXAPAY] Disabled: OXAPAY_MERCHANT_API_KEY is missing.")
        return

    web_app = web.Application(client_max_size=64 * 1024)
    web_app["telegram_app"] = telegram_app
    web_app["activate_payment"] = activate
    web_app.router.add_post("/oxapay/webhook", _webhook)
    web_app.router.add_get("/health", _health)

    runner = web.AppRunner(web_app, access_log=None)
    await runner.setup()
    port = int(os.environ.get("PORT", "8080"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    telegram_app.bot_data["_oxapay_runner"] = runner
    telegram_app.bot_data["_oxapay_reconcile_task"] = asyncio.create_task(
        _reconcile_pending(telegram_app, activate),
        name="oxapay-payment-reconciliation",
    )
    logger.info("[OXAPAY] Webhook listening on port %s.", port)


async def stop_webhook(telegram_app) -> None:
    task = telegram_app.bot_data.pop("_oxapay_reconcile_task", None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    runner = telegram_app.bot_data.pop("_oxapay_runner", None)
    if runner:
        await runner.cleanup()
"""Secure payment invoices and webhook processing for the Telegram bot."""
# Duplicate copy retained as inert-compatible Python; no future import here.

import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from decimal import Decimal, InvalidOperation
from typing import Awaitable, Callable

import aiohttp
from aiohttp import web

import database as db

logger = logging.getLogger(__name__)


class OxaPayTemporaryResponseError(RuntimeError):
    """OxaPay/proxy returned no usable API document; retry may succeed."""


OXAPAY_API_BASE = "https://api.oxapay.com/v1"
SUCCESS_STATUSES = frozenset({
    "paid",
    "manual_accept",
    "completed",
    "complete",
    "confirmed",
})
_ACTIVATION_LOCKS: dict[int, asyncio.Lock] = {}
WHITE_LABEL_MAX_ATTEMPTS = 4
RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})

PLANS = {
    "pay1d": {"name": "Core", "plan": "CORE", "days": 1, "price": Decimal("1.50")},
    "pay10": {"name": "Core", "plan": "CORE", "days": 7, "price": Decimal("8.00")},
    "pay15": {"name": "Elite", "plan": "ELITE", "days": 15, "price": Decimal("12.00")},
    "pay30": {"name": "Root", "plan": "ROOT", "days": 30, "price": Decimal("25.00")},
}

PAYMENT_METHODS = {
    "bep20": {
        "label": "BEP20", "pay_currency": "USDT", "network": "BSC",
        "network_name": "Binance Smart Chain",
    },
    "trx": {
        "label": "TRX", "pay_currency": "TRX", "network": "Tron",
        "network_name": "Tron Network",
    },
    "pol": {
        "label": "POL", "pay_currency": "POL", "network": "Polygon",
        "network_name": "Polygon Network",
    },
    "ton": {
        "label": "TON", "pay_currency": "GRAM", "network": "The Open Network",
        "network_name": "TON Network",
    },
    "ltc": {
        "label": "LTC", "pay_currency": "LTC", "network": "Litecoin",
        "network_name": "Litecoin Network",
    },
    "btc": {
        "label": "BTC", "pay_currency": "BTC", "network": "Bitcoin",
        "network_name": "Bitcoin Network",
    },
    "sol": {
        "label": "SOL", "pay_currency": "SOL", "network": "Solana",
        "network_name": "Solana Network",
    },
    "eth": {
        "label": "ETH", "pay_currency": "ETH", "network": "Ethereum",
        "network_name": "Ethereum Network",
    },
}

_accepted_cache: tuple[float, frozenset[str]] | None = None
ACCEPTED_CACHE_TTL = 30
ACCEPTED_STALE_TTL = 15 * 60


def _api_key() -> str:
    return os.environ.get("OXAPAY_MERCHANT_API_KEY", "").strip()


def _callback_url() -> str:
    return os.environ.get("OXAPAY_CALLBACK_URL", "").strip()


def _sandbox_enabled() -> bool:
    return os.environ["OXAPAY_SANDBOX"].strip().lower() == "true"


def configuration_error() -> str | None:
    if not _api_key():
        return "OXAPAY_MERCHANT_API_KEY is not configured."
    callback = _callback_url()
    if not callback:
        return "OXAPAY_CALLBACK_URL is not configured."
    if not callback.startswith("https://"):
        return "OXAPAY_CALLBACK_URL must use https://."
    sandbox = os.environ.get("OXAPAY_SANDBOX", "").strip().lower()
    if sandbox not in {"true", "false"}:
        return "OXAPAY_SANDBOX must be set explicitly to true or false."
    if sandbox == "true":
        return (
            "Direct OxaPay crypto addresses require live mode. "
            "Set OXAPAY_SANDBOX=false."
        )
    if not db.is_connected():
        return "PostgreSQL is unavailable; secure payment orders cannot be created."
    return None


async def _read_oxapay_json(
    response: aiohttp.ClientResponse,
    operation: str,
) -> dict:
    """Decode an OxaPay response without exposing raw proxy/HTML errors."""
    body = await response.text()
    if not body.strip():
        raise OxaPayTemporaryResponseError(
            f"OxaPay returned an empty response while {operation}. "
            "Please try again in a moment."
        )
    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        logger.warning(
            "[OXAPAY] Non-JSON response while %s: status=%s content_type=%s bytes=%s",
            operation,
            response.status,
            response.headers.get("Content-Type", ""),
            len(body.encode("utf-8", errors="replace")),
        )
        raise OxaPayTemporaryResponseError(
            f"OxaPay returned an invalid response while {operation}. "
            "Please try again in a moment."
        ) from exc
    if not isinstance(result, dict):
        raise OxaPayTemporaryResponseError(
            f"OxaPay returned an unexpected response while {operation}. "
            "Please try again in a moment."
        )
    return result


def _api_status(result: dict) -> int:
    """Return OxaPay's API status without allowing malformed values to crash."""
    try:
        return int(result.get("status", 0))
    except (TypeError, ValueError):
        return 0


async def _retry_temporary(
    operation: Callable[[], Awaitable[dict]],
    *,
    name: str,
    attempts: int = WHITE_LABEL_MAX_ATTEMPTS,
) -> dict:
    """Retry temporary provider/transport failures with bounded backoff."""
    last_error: BaseException | None = None
    total_attempts = max(1, int(attempts))
    for attempt in range(1, total_attempts + 1):
        try:
            return await operation()
        except (
            OxaPayTemporaryResponseError,
            aiohttp.ClientError,
            asyncio.TimeoutError,
        ) as exc:
            last_error = exc
            if attempt >= total_attempts:
                break
            delay = min(4.0, 0.65 * (2 ** (attempt - 1)))
            delay += secrets.randbelow(250) / 1000
            logger.warning(
                "[OXAPAY] Temporary failure while %s; retrying attempt %s/%s "
                "in %.2fs (%s)",
                name,
                attempt + 1,
                total_attempts,
                delay,
                type(exc).__name__,
            )
            await asyncio.sleep(delay)
    raise OxaPayTemporaryResponseError(
        "OxaPay is temporarily unavailable after several automatic retries. "
        "Please press Retry Payment."
    ) from last_error


async def get_accepted_method_keys(force: bool = False) -> list[str]:
    """Return only payment methods enabled for this OxaPay merchant."""
    global _accepted_cache
    error = configuration_error()
    if error:
        raise RuntimeError(error)
    now = time.monotonic()
    if (
        not force
        and _accepted_cache
        and now - _accepted_cache[0] < ACCEPTED_CACHE_TTL
    ):
        accepted = _accepted_cache[1]
    else:
        headers = {
            "merchant_api_key": _api_key(),
            "Content-Type": "application/json",
        }
        timeout = aiohttp.ClientTimeout(
            total=10,
            connect=5,
            sock_connect=5,
            sock_read=7,
        )
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"{OXAPAY_API_BASE}/payment/accepted-currencies",
                    headers=headers,
                ) as response:
                    result = await _read_oxapay_json(
                        response,
                        "loading payment methods",
                    )
                    response_status = response.status
            if response_status != 200 or _api_status(result) != 200:
                raise RuntimeError(
                    _oxapay_error(
                        result,
                        "Could not load accepted OxaPay currencies.",
                    )
                )
            values = (result.get("data") or {}).get("list") or []
            accepted = frozenset(str(value).upper() for value in values)
            if not accepted:
                raise RuntimeError("OxaPay returned no accepted currencies.")
            _accepted_cache = (now, accepted)
        except (
            OxaPayTemporaryResponseError,
            aiohttp.ClientError,
            asyncio.TimeoutError,
        ):
            if (
                _accepted_cache
                and now - _accepted_cache[0] < ACCEPTED_STALE_TTL
            ):
                accepted = _accepted_cache[1]
                logger.warning(
                    "[OXAPAY] Using cached accepted currencies after a "
                    "temporary API response failure."
                )
            else:
                # Currency discovery is optional. Address creation remains
                # authoritative and rejects any disabled merchant currency.
                accepted = frozenset(
                    method["pay_currency"].upper()
                    for method in PAYMENT_METHODS.values()
                )
                logger.warning(
                    "[OXAPAY] Accepted-currencies API unavailable; showing "
                    "configured methods and deferring validation to payment "
                    "address creation."
                )

    return [
        key
        for key, method in PAYMENT_METHODS.items()
        if method["pay_currency"].upper() in accepted
    ]


async def create_white_label_payment(
    user_id: int,
    plan_selection: str,
    method_selection: str,
) -> dict:
    error = configuration_error()
    if error:
        raise RuntimeError(error)
    plan = PLANS.get(plan_selection)
    if not plan:
        raise ValueError("Unknown payment plan.")
    method = PAYMENT_METHODS.get(method_selection)
    if not method:
        raise ValueError("Unknown payment method.")
    accepted_methods = await get_accepted_method_keys(force=True)
    if method_selection not in accepted_methods:
        raise RuntimeError(
            f"{method['label']} is not enabled in your OxaPay Merchant Service."
        )

    order_id = f"tg-{user_id}-{secrets.token_hex(12)}"
    created = await db.create_payment_order(
        order_id=order_id,
        user_id=user_id,
        plan=plan["plan"],
        days=plan["days"],
        expected_amount=plan["price"],
        currency="USD",
    )
    if not created:
        raise RuntimeError("Could not store the payment order.")

    payload = {
        "amount": float(plan["price"]),
        "currency": "USD",
        "pay_currency": method["pay_currency"],
        "network": method["network"],
        "lifetime": 120,
        "fee_paid_by_payer": 1,
        "under_paid_coverage": 0,
        "callback_url": _callback_url(),
        "order_id": order_id,
        "description": f"{plan['name']} plan for Telegram user {user_id}",
    }
    headers = {
        "merchant_api_key": _api_key(),
        "Content-Type": "application/json",
    }

    try:
        timeout = aiohttp.ClientTimeout(
            total=20,
            connect=7,
            sock_connect=7,
            sock_read=12,
        )
        connector = aiohttp.TCPConnector(
            ttl_dns_cache=300,
            enable_cleanup_closed=True,
        )
        async with aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            headers={"Accept": "application/json"},
        ) as session:
            async def request_payment() -> dict:
                async with session.post(
                    f"{OXAPAY_API_BASE}/payment/white-label",
                    headers=headers,
                    json=payload,
                ) as response:
                    result = await _read_oxapay_json(
                        response,
                        "creating the payment address",
                    )
                    if response.status in RETRYABLE_HTTP_STATUSES:
                        raise OxaPayTemporaryResponseError(
                            "OxaPay temporarily could not create the payment address."
                        )
                    api_status = _api_status(result)
                    if api_status in RETRYABLE_HTTP_STATUSES:
                        raise OxaPayTemporaryResponseError(
                            "OxaPay temporarily could not create the payment address."
                        )
                    if response.status != 200 or api_status != 200:
                        # Parsed merchant/authentication/currency errors are
                        # authoritative and must not be hidden by retries.
                        raise RuntimeError(
                            _oxapay_error(
                                result,
                                "OxaPay rejected the payment request.",
                            )
                        )
                    response_data = result.get("data")
                    if not isinstance(response_data, dict):
                        raise OxaPayTemporaryResponseError(
                            "OxaPay returned incomplete payment information."
                        )
                    required = (
                        response_data.get("track_id"),
                        response_data.get("address"),
                        response_data.get("pay_amount"),
                        response_data.get("expired_at"),
                    )
                    if any(value in (None, "", 0, "0") for value in required):
                        raise OxaPayTemporaryResponseError(
                            "OxaPay returned incomplete payment information."
                        )
                    return result

            result = await _retry_temporary(
                request_payment,
                name="creating the payment address",
            )

        data = result.get("data") or {}
        track_id = str(data.get("track_id") or "").strip()
        address = str(data.get("address") or "").strip()
        pay_amount = str(data.get("pay_amount") or "").strip()
        pay_currency = str(data.get("pay_currency") or method["pay_currency"]).upper()
        network_name = method["network_name"]
        memo = str(data.get("memo") or "").strip()
        expired_at = int(data.get("expired_at") or 0)
        if not track_id or not address or not pay_amount or expired_at <= 0:
            raise RuntimeError("OxaPay returned incomplete payment information.")

        saved = await db.attach_payment_invoice(order_id, track_id, "")
        if not saved:
            raise RuntimeError("Could not save the OxaPay payment.")

        return {
            "order_id": order_id,
            "track_id": track_id,
            "address": address,
            "pay_amount": pay_amount,
            "pay_currency": pay_currency,
            "network_name": network_name,
            "memo": memo,
            "expired_at": expired_at,
            "lifetime": int(data.get("lifetime") or 120),
            **plan,
            "method": method,
        }
    except Exception as exc:
        await db.fail_payment_order(order_id, str(exc))
        raise


async def _fetch_payment(track_id: str) -> dict:
    headers = {
        "merchant_api_key": _api_key(),
        "Content-Type": "application/json",
    }
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(
            f"{OXAPAY_API_BASE}/payment/{track_id}",
            headers=headers,
        ) as response:
            result = await _read_oxapay_json(
                response,
                "verifying the payment",
            )
    if response.status != 200 or _api_status(result) != 200:
        raise RuntimeError(_oxapay_error(result, "Payment verification failed."))
    return result.get("data") or {}


def _decimal(value) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("-1")


def _oxapay_error(result: dict, fallback: str) -> str:
    error = result.get("error")
    if isinstance(error, dict):
        detail = str(error.get("message") or "").strip()
        key = str(error.get("key") or "").strip()
        if detail:
            return f"{key}: {detail}" if key else detail
    return str(result.get("message") or fallback)


def _payment_field(data: dict, snake_case: str, camel_case: str = ""):
    value = data.get(snake_case)
    if value in (None, "") and camel_case:
        value = data.get(camel_case)
    return value


async def _deliver_activation(
    app,
    order_id: str,
    activate: Callable[[object, dict], Awaitable[None]],
) -> None:
    claim_token = secrets.token_hex(16)
    entitlement = await db.claim_payment_activation(order_id, claim_token)
    if not entitlement:
        return
    user_id = int(entitlement["user_id"])
    lock = _ACTIVATION_LOCKS.setdefault(user_id, asyncio.Lock())
    try:
        async with lock:
            # Another order for this user may have finalized while this older
            # delivery was waiting. Always activate the canonical latest row.
            current = await db.get_current_payment_entitlement(user_id)
            if not current:
                raise RuntimeError("Canonical paid entitlement is unavailable.")
            await activate(app, current)
            if not await db.mark_payment_activated(order_id, claim_token):
                raise RuntimeError("Could not mark payment activation delivered.")
    except Exception:
        await db.release_payment_activation(order_id, claim_token)
        raise


async def _process_callback(
    app,
    callback_data: dict,
    activate: Callable[[object, dict], Awaitable[None]],
    trusted_callback: bool = False,
) -> None:
    data = callback_data.get("data") if isinstance(callback_data.get("data"), dict) else callback_data
    track_id = str(_payment_field(data, "track_id", "trackId") or "").strip()
    order_id = str(_payment_field(data, "order_id", "orderId") or "").strip()
    if not track_id or not order_id:
        return

    callback_status = str(data.get("status") or "").strip().lower()
    if trusted_callback and callback_status not in SUCCESS_STATUSES:
        return

    # A callback reaching this trusted path has already passed OxaPay's
    # raw-body HMAC verification. Use it immediately when it contains all
    # fields required to bind the payment to the stored order. Reconciliation
    # uses OxaPay's read API when a callback was missed.
    verified = data if trusted_callback else {}
    required_callback_fields = (
        _payment_field(data, "track_id", "trackId"),
        _payment_field(data, "order_id", "orderId"),
        data.get("status"),
        data.get("currency"),
        data.get("amount"),
    )
    if not trusted_callback or any(value in (None, "") for value in required_callback_fields):
        verified = await _fetch_payment(track_id)

    verified_status = str(verified.get("status") or "").strip().lower()
    if verified_status not in SUCCESS_STATUSES:
        return
    if str(_payment_field(verified, "track_id", "trackId") or "").strip() != track_id:
        raise RuntimeError("OxaPay track ID verification failed.")
    if str(_payment_field(verified, "order_id", "orderId") or "").strip() != order_id:
        raise RuntimeError("OxaPay order ID verification failed.")

    order = await db.get_payment_order(order_id)
    if not order:
        raise RuntimeError("Unknown OxaPay order.")
    if order["status"] == "paid":
        await _deliver_activation(app, order_id, activate)
        return
    if str(order.get("track_id") or "") != track_id:
        raise RuntimeError("Stored OxaPay track ID does not match.")
    if str(verified.get("currency") or "").upper() != str(order["currency"]).upper():
        raise RuntimeError("OxaPay payment currency does not match the order.")
    verified_amount = _decimal(verified.get("amount"))
    expected_amount = _decimal(order["expected_amount"])
    if (
        not verified_amount.is_finite()
        or not expected_amount.is_finite()
        or expected_amount <= 0
        or verified_amount < expected_amount
    ):
        raise RuntimeError("OxaPay payment amount is below the order amount.")

    entitlement = await db.finalize_paid_order(order_id, track_id)
    if not entitlement:
        return
    await _deliver_activation(app, order_id, activate)


async def _reconcile_pending(
    telegram_app,
    activate: Callable[[object, dict], Awaitable[None]],
) -> None:
    """Recover paid orders when a webhook is delayed, lost, or raced."""
    delay = 3
    while True:
        try:
            await asyncio.sleep(delay)
            delay = 2
            pending = await db.list_pending_payment_orders(limit=100)
            for order in pending:
                try:
                    await _process_callback(
                        telegram_app,
                        {
                            "track_id": order["track_id"],
                            "order_id": order["order_id"],
                        },
                        activate,
                        trusted_callback=False,
                    )
                except Exception as exc:
                    logger.warning(
                        "[OXAPAY] Pending order %s reconciliation deferred: %s",
                        order["order_id"],
                        exc,
                    )
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("[OXAPAY] Pending-payment reconciliation failed.")
            await asyncio.sleep(2)


async def _webhook(request: web.Request) -> web.Response:
    raw_body = await request.read()
    received = request.headers.get("HMAC", "").strip().lower()
    expected = hmac.new(
        _api_key().encode("utf-8"),
        raw_body,
        hashlib.sha512,
    ).hexdigest()
    if not received or not hmac.compare_digest(received, expected):
        return web.Response(text="Invalid HMAC", status=401)
    try:
        payload = json.loads(raw_body.decode("utf-8"))
        await _process_callback(
            request.app["telegram_app"],
            payload,
            request.app["activate_payment"],
            trusted_callback=True,
        )
    except (UnicodeDecodeError, json.JSONDecodeError):
        return web.Response(text="Invalid JSON", status=400)
    except Exception:
        logger.exception("[OXAPAY] Callback processing failed.")
        return web.Response(text="Temporary failure", status=500)
    return web.Response(text="OK", status=200)


async def _health(_request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "service": "oxapay-webhook"})


async def start_webhook(
    telegram_app,
    activate: Callable[[object, dict], Awaitable[None]],
) -> None:
    if not _api_key():
        logger.warning("[OXAPAY] Disabled: OXAPAY_MERCHANT_API_KEY is missing.")
        return

    web_app = web.Application(client_max_size=64 * 1024)
    web_app["telegram_app"] = telegram_app
    web_app["activate_payment"] = activate
    web_app.router.add_post("/oxapay/webhook", _webhook)
    web_app.router.add_get("/health", _health)

    runner = web.AppRunner(web_app, access_log=None)
    await runner.setup()
    port = int(os.environ.get("PORT", "8080"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    telegram_app.bot_data["_oxapay_runner"] = runner
    telegram_app.bot_data["_oxapay_reconcile_task"] = asyncio.create_task(
        _reconcile_pending(telegram_app, activate),
        name="oxapay-payment-reconciliation",
    )
    logger.info("[OXAPAY] Webhook listening on port %s.", port)


async def stop_webhook(telegram_app) -> None:
    task = telegram_app.bot_data.pop("_oxapay_reconcile_task", None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    runner = telegram_app.bot_data.pop("_oxapay_runner", None)
    if runner:
        await runner.cleanup()
"""Secure payment invoices and webhook processing for the Telegram bot."""
# Duplicate copy retained as inert-compatible Python; no future import here.

import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from decimal import Decimal, InvalidOperation
from typing import Awaitable, Callable

import aiohttp
from aiohttp import web

import database as db

logger = logging.getLogger(__name__)


class OxaPayTemporaryResponseError(RuntimeError):
    """OxaPay/proxy returned no usable API document; retry may succeed."""


OXAPAY_API_BASE = "https://api.oxapay.com/v1"
SUCCESS_STATUSES = frozenset({
    "paid",
    "manual_accept",
    "completed",
    "complete",
    "confirmed",
})
_ACTIVATION_LOCKS: dict[int, asyncio.Lock] = {}
WHITE_LABEL_MAX_ATTEMPTS = 4
RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})

PLANS = {
    "pay1d": {"name": "Core", "plan": "CORE", "days": 1, "price": Decimal("1.50")},
    "pay10": {"name": "Core", "plan": "CORE", "days": 7, "price": Decimal("8.00")},
    "pay15": {"name": "Elite", "plan": "ELITE", "days": 15, "price": Decimal("12.00")},
    "pay30": {"name": "Root", "plan": "ROOT", "days": 30, "price": Decimal("25.00")},
}

PAYMENT_METHODS = {
    "bep20": {
        "label": "BEP20", "pay_currency": "USDT", "network": "BSC",
        "network_name": "Binance Smart Chain",
    },
    "trx": {
        "label": "TRX", "pay_currency": "TRX", "network": "Tron",
        "network_name": "Tron Network",
    },
    "pol": {
        "label": "POL", "pay_currency": "POL", "network": "Polygon",
        "network_name": "Polygon Network",
    },
    "ton": {
        "label": "TON", "pay_currency": "GRAM", "network": "The Open Network",
        "network_name": "TON Network",
    },
    "ltc": {
        "label": "LTC", "pay_currency": "LTC", "network": "Litecoin",
        "network_name": "Litecoin Network",
    },
    "btc": {
        "label": "BTC", "pay_currency": "BTC", "network": "Bitcoin",
        "network_name": "Bitcoin Network",
    },
    "sol": {
        "label": "SOL", "pay_currency": "SOL", "network": "Solana",
        "network_name": "Solana Network",
    },
    "eth": {
        "label": "ETH", "pay_currency": "ETH", "network": "Ethereum",
        "network_name": "Ethereum Network",
    },
}

_accepted_cache: tuple[float, frozenset[str]] | None = None
ACCEPTED_CACHE_TTL = 30
ACCEPTED_STALE_TTL = 15 * 60


def _api_key() -> str:
    return os.environ.get("OXAPAY_MERCHANT_API_KEY", "").strip()


def _callback_url() -> str:
    return os.environ.get("OXAPAY_CALLBACK_URL", "").strip()


def _sandbox_enabled() -> bool:
    return os.environ["OXAPAY_SANDBOX"].strip().lower() == "true"


def configuration_error() -> str | None:
    if not _api_key():
        return "OXAPAY_MERCHANT_API_KEY is not configured."
    callback = _callback_url()
    if not callback:
        return "OXAPAY_CALLBACK_URL is not configured."
    if not callback.startswith("https://"):
        return "OXAPAY_CALLBACK_URL must use https://."
    sandbox = os.environ.get("OXAPAY_SANDBOX", "").strip().lower()
    if sandbox not in {"true", "false"}:
        return "OXAPAY_SANDBOX must be set explicitly to true or false."
    if sandbox == "true":
        return (
            "Direct OxaPay crypto addresses require live mode. "
            "Set OXAPAY_SANDBOX=false."
        )
    if not db.is_connected():
        return "PostgreSQL is unavailable; secure payment orders cannot be created."
    return None


async def _read_oxapay_json(
    response: aiohttp.ClientResponse,
    operation: str,
) -> dict:
    """Decode an OxaPay response without exposing raw proxy/HTML errors."""
    body = await response.text()
    if not body.strip():
        raise OxaPayTemporaryResponseError(
            f"OxaPay returned an empty response while {operation}. "
            "Please try again in a moment."
        )
    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        logger.warning(
            "[OXAPAY] Non-JSON response while %s: status=%s content_type=%s bytes=%s",
            operation,
            response.status,
            response.headers.get("Content-Type", ""),
            len(body.encode("utf-8", errors="replace")),
        )
        raise OxaPayTemporaryResponseError(
            f"OxaPay returned an invalid response while {operation}. "
            "Please try again in a moment."
        ) from exc
    if not isinstance(result, dict):
        raise OxaPayTemporaryResponseError(
            f"OxaPay returned an unexpected response while {operation}. "
            "Please try again in a moment."
        )
    return result


def _api_status(result: dict) -> int:
    """Return OxaPay's API status without allowing malformed values to crash."""
    try:
        return int(result.get("status", 0))
    except (TypeError, ValueError):
        return 0


async def _retry_temporary(
    operation: Callable[[], Awaitable[dict]],
    *,
    name: str,
    attempts: int = WHITE_LABEL_MAX_ATTEMPTS,
) -> dict:
    """Retry temporary provider/transport failures with bounded backoff."""
    last_error: BaseException | None = None
    total_attempts = max(1, int(attempts))
    for attempt in range(1, total_attempts + 1):
        try:
            return await operation()
        except (
            OxaPayTemporaryResponseError,
            aiohttp.ClientError,
            asyncio.TimeoutError,
        ) as exc:
            last_error = exc
            if attempt >= total_attempts:
                break
            delay = min(4.0, 0.65 * (2 ** (attempt - 1)))
            delay += secrets.randbelow(250) / 1000
            logger.warning(
                "[OXAPAY] Temporary failure while %s; retrying attempt %s/%s "
                "in %.2fs (%s)",
                name,
                attempt + 1,
                total_attempts,
                delay,
                type(exc).__name__,
            )
            await asyncio.sleep(delay)
    raise OxaPayTemporaryResponseError(
        "OxaPay is temporarily unavailable after several automatic retries. "
        "Please press Retry Payment."
    ) from last_error


async def get_accepted_method_keys(force: bool = False) -> list[str]:
    """Return only payment methods enabled for this OxaPay merchant."""
    global _accepted_cache
    error = configuration_error()
    if error:
        raise RuntimeError(error)
    now = time.monotonic()
    if (
        not force
        and _accepted_cache
        and now - _accepted_cache[0] < ACCEPTED_CACHE_TTL
    ):
        accepted = _accepted_cache[1]
    else:
        headers = {
            "merchant_api_key": _api_key(),
            "Content-Type": "application/json",
        }
        timeout = aiohttp.ClientTimeout(
            total=10,
            connect=5,
            sock_connect=5,
            sock_read=7,
        )
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"{OXAPAY_API_BASE}/payment/accepted-currencies",
                    headers=headers,
                ) as response:
                    result = await _read_oxapay_json(
                        response,
                        "loading payment methods",
                    )
                    response_status = response.status
            if response_status != 200 or _api_status(result) != 200:
                raise RuntimeError(
                    _oxapay_error(
                        result,
                        "Could not load accepted OxaPay currencies.",
                    )
                )
            values = (result.get("data") or {}).get("list") or []
            accepted = frozenset(str(value).upper() for value in values)
            if not accepted:
                raise RuntimeError("OxaPay returned no accepted currencies.")
            _accepted_cache = (now, accepted)
        except (
            OxaPayTemporaryResponseError,
            aiohttp.ClientError,
            asyncio.TimeoutError,
        ):
            if (
                _accepted_cache
                and now - _accepted_cache[0] < ACCEPTED_STALE_TTL
            ):
                accepted = _accepted_cache[1]
                logger.warning(
                    "[OXAPAY] Using cached accepted currencies after a "
                    "temporary API response failure."
                )
            else:
                # Currency discovery is optional. Address creation remains
                # authoritative and rejects any disabled merchant currency.
                accepted = frozenset(
                    method["pay_currency"].upper()
                    for method in PAYMENT_METHODS.values()
                )
                logger.warning(
                    "[OXAPAY] Accepted-currencies API unavailable; showing "
                    "configured methods and deferring validation to payment "
                    "address creation."
                )

    return [
        key
        for key, method in PAYMENT_METHODS.items()
        if method["pay_currency"].upper() in accepted
    ]


async def create_white_label_payment(
    user_id: int,
    plan_selection: str,
    method_selection: str,
) -> dict:
    error = configuration_error()
    if error:
        raise RuntimeError(error)
    plan = PLANS.get(plan_selection)
    if not plan:
        raise ValueError("Unknown payment plan.")
    method = PAYMENT_METHODS.get(method_selection)
    if not method:
        raise ValueError("Unknown payment method.")
    accepted_methods = await get_accepted_method_keys(force=True)
    if method_selection not in accepted_methods:
        raise RuntimeError(
            f"{method['label']} is not enabled in your OxaPay Merchant Service."
        )

    order_id = f"tg-{user_id}-{secrets.token_hex(12)}"
    created = await db.create_payment_order(
        order_id=order_id,
        user_id=user_id,
        plan=plan["plan"],
        days=plan["days"],
        expected_amount=plan["price"],
        currency="USD",
    )
    if not created:
        raise RuntimeError("Could not store the payment order.")

    payload = {
        "amount": float(plan["price"]),
        "currency": "USD",
        "pay_currency": method["pay_currency"],
        "network": method["network"],
        "lifetime": 120,
        "fee_paid_by_payer": 1,
        "under_paid_coverage": 0,
        "callback_url": _callback_url(),
        "order_id": order_id,
        "description": f"{plan['name']} plan for Telegram user {user_id}",
    }
    headers = {
        "merchant_api_key": _api_key(),
        "Content-Type": "application/json",
    }

    try:
        timeout = aiohttp.ClientTimeout(
            total=20,
            connect=7,
            sock_connect=7,
            sock_read=12,
        )
        connector = aiohttp.TCPConnector(
            ttl_dns_cache=300,
            enable_cleanup_closed=True,
        )
        async with aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            headers={"Accept": "application/json"},
        ) as session:
            async def request_payment() -> dict:
                async with session.post(
                    f"{OXAPAY_API_BASE}/payment/white-label",
                    headers=headers,
                    json=payload,
                ) as response:
                    result = await _read_oxapay_json(
                        response,
                        "creating the payment address",
                    )
                    if response.status in RETRYABLE_HTTP_STATUSES:
                        raise OxaPayTemporaryResponseError(
                            "OxaPay temporarily could not create the payment address."
                        )
                    api_status = _api_status(result)
                    if api_status in RETRYABLE_HTTP_STATUSES:
                        raise OxaPayTemporaryResponseError(
                            "OxaPay temporarily could not create the payment address."
                        )
                    if response.status != 200 or api_status != 200:
                        # Parsed merchant/authentication/currency errors are
                        # authoritative and must not be hidden by retries.
                        raise RuntimeError(
                            _oxapay_error(
                                result,
                                "OxaPay rejected the payment request.",
                            )
                        )
                    response_data = result.get("data")
                    if not isinstance(response_data, dict):
                        raise OxaPayTemporaryResponseError(
                            "OxaPay returned incomplete payment information."
                        )
                    required = (
                        response_data.get("track_id"),
                        response_data.get("address"),
                        response_data.get("pay_amount"),
                        response_data.get("expired_at"),
                    )
                    if any(value in (None, "", 0, "0") for value in required):
                        raise OxaPayTemporaryResponseError(
                            "OxaPay returned incomplete payment information."
                        )
                    return result

            result = await _retry_temporary(
                request_payment,
                name="creating the payment address",
            )

        data = result.get("data") or {}
        track_id = str(data.get("track_id") or "").strip()
        address = str(data.get("address") or "").strip()
        pay_amount = str(data.get("pay_amount") or "").strip()
        pay_currency = str(data.get("pay_currency") or method["pay_currency"]).upper()
        network_name = method["network_name"]
        memo = str(data.get("memo") or "").strip()
        expired_at = int(data.get("expired_at") or 0)
        if not track_id or not address or not pay_amount or expired_at <= 0:
            raise RuntimeError("OxaPay returned incomplete payment information.")

        saved = await db.attach_payment_invoice(order_id, track_id, "")
        if not saved:
            raise RuntimeError("Could not save the OxaPay payment.")

        return {
            "order_id": order_id,
            "track_id": track_id,
            "address": address,
            "pay_amount": pay_amount,
            "pay_currency": pay_currency,
            "network_name": network_name,
            "memo": memo,
            "expired_at": expired_at,
            "lifetime": int(data.get("lifetime") or 120),
            **plan,
            "method": method,
        }
    except Exception as exc:
        await db.fail_payment_order(order_id, str(exc))
        raise


async def _fetch_payment(track_id: str) -> dict:
    headers = {
        "merchant_api_key": _api_key(),
        "Content-Type": "application/json",
    }
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(
            f"{OXAPAY_API_BASE}/payment/{track_id}",
            headers=headers,
        ) as response:
            result = await _read_oxapay_json(
                response,
                "verifying the payment",
            )
    if response.status != 200 or _api_status(result) != 200:
        raise RuntimeError(_oxapay_error(result, "Payment verification failed."))
    return result.get("data") or {}


def _decimal(value) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("-1")


def _oxapay_error(result: dict, fallback: str) -> str:
    error = result.get("error")
    if isinstance(error, dict):
        detail = str(error.get("message") or "").strip()
        key = str(error.get("key") or "").strip()
        if detail:
            return f"{key}: {detail}" if key else detail
    return str(result.get("message") or fallback)


def _payment_field(data: dict, snake_case: str, camel_case: str = ""):
    value = data.get(snake_case)
    if value in (None, "") and camel_case:
        value = data.get(camel_case)
    return value


async def _deliver_activation(
    app,
    order_id: str,
    activate: Callable[[object, dict], Awaitable[None]],
) -> None:
    claim_token = secrets.token_hex(16)
    entitlement = await db.claim_payment_activation(order_id, claim_token)
    if not entitlement:
        return
    user_id = int(entitlement["user_id"])
    lock = _ACTIVATION_LOCKS.setdefault(user_id, asyncio.Lock())
    try:
        async with lock:
            # Another order for this user may have finalized while this older
            # delivery was waiting. Always activate the canonical latest row.
            current = await db.get_current_payment_entitlement(user_id)
            if not current:
                raise RuntimeError("Canonical paid entitlement is unavailable.")
            await activate(app, current)
            if not await db.mark_payment_activated(order_id, claim_token):
                raise RuntimeError("Could not mark payment activation delivered.")
    except Exception:
        await db.release_payment_activation(order_id, claim_token)
        raise


async def _process_callback(
    app,
    callback_data: dict,
    activate: Callable[[object, dict], Awaitable[None]],
    trusted_callback: bool = False,
) -> None:
    data = callback_data.get("data") if isinstance(callback_data.get("data"), dict) else callback_data
    track_id = str(_payment_field(data, "track_id", "trackId") or "").strip()
    order_id = str(_payment_field(data, "order_id", "orderId") or "").strip()
    if not track_id or not order_id:
        return

    callback_status = str(data.get("status") or "").strip().lower()
    if trusted_callback and callback_status not in SUCCESS_STATUSES:
        return

    # A callback reaching this trusted path has already passed OxaPay's
    # raw-body HMAC verification. Use it immediately when it contains all
    # fields required to bind the payment to the stored order. Reconciliation
    # uses OxaPay's read API when a callback was missed.
    verified = data if trusted_callback else {}
    required_callback_fields = (
        _payment_field(data, "track_id", "trackId"),
        _payment_field(data, "order_id", "orderId"),
        data.get("status"),
        data.get("currency"),
        data.get("amount"),
    )
    if not trusted_callback or any(value in (None, "") for value in required_callback_fields):
        verified = await _fetch_payment(track_id)

    verified_status = str(verified.get("status") or "").strip().lower()
    if verified_status not in SUCCESS_STATUSES:
        return
    if str(_payment_field(verified, "track_id", "trackId") or "").strip() != track_id:
        raise RuntimeError("OxaPay track ID verification failed.")
    if str(_payment_field(verified, "order_id", "orderId") or "").strip() != order_id:
        raise RuntimeError("OxaPay order ID verification failed.")

    order = await db.get_payment_order(order_id)
    if not order:
        raise RuntimeError("Unknown OxaPay order.")
    if order["status"] == "paid":
        await _deliver_activation(app, order_id, activate)
        return
    if str(order.get("track_id") or "") != track_id:
        raise RuntimeError("Stored OxaPay track ID does not match.")
    if str(verified.get("currency") or "").upper() != str(order["currency"]).upper():
        raise RuntimeError("OxaPay payment currency does not match the order.")
    verified_amount = _decimal(verified.get("amount"))
    expected_amount = _decimal(order["expected_amount"])
    if (
        not verified_amount.is_finite()
        or not expected_amount.is_finite()
        or expected_amount <= 0
        or verified_amount < expected_amount
    ):
        raise RuntimeError("OxaPay payment amount is below the order amount.")

    entitlement = await db.finalize_paid_order(order_id, track_id)
    if not entitlement:
        return
    await _deliver_activation(app, order_id, activate)


async def _reconcile_pending(
    telegram_app,
    activate: Callable[[object, dict], Awaitable[None]],
) -> None:
    """Recover paid orders when a webhook is delayed, lost, or raced."""
    delay = 3
    while True:
        try:
            await asyncio.sleep(delay)
            delay = 2
            pending = await db.list_pending_payment_orders(limit=100)
            for order in pending:
                try:
                    await _process_callback(
                        telegram_app,
                        {
                            "track_id": order["track_id"],
                            "order_id": order["order_id"],
                        },
                        activate,
                        trusted_callback=False,
                    )
                except Exception as exc:
                    logger.warning(
                        "[OXAPAY] Pending order %s reconciliation deferred: %s",
                        order["order_id"],
                        exc,
                    )
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("[OXAPAY] Pending-payment reconciliation failed.")
            await asyncio.sleep(2)


async def _webhook(request: web.Request) -> web.Response:
    raw_body = await request.read()
    received = request.headers.get("HMAC", "").strip().lower()
    expected = hmac.new(
        _api_key().encode("utf-8"),
        raw_body,
        hashlib.sha512,
    ).hexdigest()
    if not received or not hmac.compare_digest(received, expected):
        return web.Response(text="Invalid HMAC", status=401)
    try:
        payload = json.loads(raw_body.decode("utf-8"))
        await _process_callback(
            request.app["telegram_app"],
            payload,
            request.app["activate_payment"],
            trusted_callback=True,
        )
    except (UnicodeDecodeError, json.JSONDecodeError):
        return web.Response(text="Invalid JSON", status=400)
    except Exception:
        logger.exception("[OXAPAY] Callback processing failed.")
        return web.Response(text="Temporary failure", status=500)
    return web.Response(text="OK", status=200)


async def _health(_request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "service": "oxapay-webhook"})


async def start_webhook(
    telegram_app,
    activate: Callable[[object, dict], Awaitable[None]],
) -> None:
    if not _api_key():
        logger.warning("[OXAPAY] Disabled: OXAPAY_MERCHANT_API_KEY is missing.")
        return

    web_app = web.Application(client_max_size=64 * 1024)
    web_app["telegram_app"] = telegram_app
    web_app["activate_payment"] = activate
    web_app.router.add_post("/oxapay/webhook", _webhook)
    web_app.router.add_get("/health", _health)

    runner = web.AppRunner(web_app, access_log=None)
    await runner.setup()
    port = int(os.environ.get("PORT", "8080"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    telegram_app.bot_data["_oxapay_runner"] = runner
    telegram_app.bot_data["_oxapay_reconcile_task"] = asyncio.create_task(
        _reconcile_pending(telegram_app, activate),
        name="oxapay-payment-reconciliation",
    )
    logger.info("[OXAPAY] Webhook listening on port %s.", port)


async def stop_webhook(telegram_app) -> None:
    task = telegram_app.bot_data.pop("_oxapay_reconcile_task", None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    runner = telegram_app.bot_data.pop("_oxapay_runner", None)
    if runner:
        await runner.cleanup()
"""Secure payment invoices and webhook processing for the Telegram bot."""
# Duplicate copy retained as inert-compatible Python; no future import here.

import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from decimal import Decimal, InvalidOperation
from typing import Awaitable, Callable

import aiohttp
from aiohttp import web

import database as db

logger = logging.getLogger(__name__)


class OxaPayTemporaryResponseError(RuntimeError):
    """OxaPay/proxy returned no usable API document; retry may succeed."""


OXAPAY_API_BASE = "https://api.oxapay.com/v1"
SUCCESS_STATUSES = frozenset({
    "paid",
    "manual_accept",
    "completed",
    "complete",
    "confirmed",
})
_ACTIVATION_LOCKS: dict[int, asyncio.Lock] = {}
WHITE_LABEL_MAX_ATTEMPTS = 4
RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})

PLANS = {
    "pay1d": {"name": "Core", "plan": "CORE", "days": 1, "price": Decimal("1.50")},
    "pay10": {"name": "Core", "plan": "CORE", "days": 7, "price": Decimal("8.00")},
    "pay15": {"name": "Elite", "plan": "ELITE", "days": 15, "price": Decimal("12.00")},
    "pay30": {"name": "Root", "plan": "ROOT", "days": 30, "price": Decimal("25.00")},
}

PAYMENT_METHODS = {
    "bep20": {
        "label": "BEP20", "pay_currency": "USDT", "network": "BSC",
        "network_name": "Binance Smart Chain",
    },
    "trx": {
        "label": "TRX", "pay_currency": "TRX", "network": "Tron",
        "network_name": "Tron Network",
    },
    "pol": {
        "label": "POL", "pay_currency": "POL", "network": "Polygon",
        "network_name": "Polygon Network",
    },
    "ton": {
        "label": "TON", "pay_currency": "GRAM", "network": "The Open Network",
        "network_name": "TON Network",
    },
    "ltc": {
        "label": "LTC", "pay_currency": "LTC", "network": "Litecoin",
        "network_name": "Litecoin Network",
    },
    "btc": {
        "label": "BTC", "pay_currency": "BTC", "network": "Bitcoin",
        "network_name": "Bitcoin Network",
    },
    "sol": {
        "label": "SOL", "pay_currency": "SOL", "network": "Solana",
        "network_name": "Solana Network",
    },
    "eth": {
        "label": "ETH", "pay_currency": "ETH", "network": "Ethereum",
        "network_name": "Ethereum Network",
    },
}

_accepted_cache: tuple[float, frozenset[str]] | None = None
ACCEPTED_CACHE_TTL = 30
ACCEPTED_STALE_TTL = 15 * 60


def _api_key() -> str:
    return os.environ.get("OXAPAY_MERCHANT_API_KEY", "").strip()


def _callback_url() -> str:
    return os.environ.get("OXAPAY_CALLBACK_URL", "").strip()


def _sandbox_enabled() -> bool:
    return os.environ["OXAPAY_SANDBOX"].strip().lower() == "true"


def configuration_error() -> str | None:
    if not _api_key():
        return "OXAPAY_MERCHANT_API_KEY is not configured."
    callback = _callback_url()
    if not callback:
        return "OXAPAY_CALLBACK_URL is not configured."
    if not callback.startswith("https://"):
        return "OXAPAY_CALLBACK_URL must use https://."
    sandbox = os.environ.get("OXAPAY_SANDBOX", "").strip().lower()
    if sandbox not in {"true", "false"}:
        return "OXAPAY_SANDBOX must be set explicitly to true or false."
    if sandbox == "true":
        return (
            "Direct OxaPay crypto addresses require live mode. "
            "Set OXAPAY_SANDBOX=false."
        )
    if not db.is_connected():
        return "PostgreSQL is unavailable; secure payment orders cannot be created."
    return None


async def _read_oxapay_json(
    response: aiohttp.ClientResponse,
    operation: str,
) -> dict:
    """Decode an OxaPay response without exposing raw proxy/HTML errors."""
    body = await response.text()
    if not body.strip():
        raise OxaPayTemporaryResponseError(
            f"OxaPay returned an empty response while {operation}. "
            "Please try again in a moment."
        )
    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        logger.warning(
            "[OXAPAY] Non-JSON response while %s: status=%s content_type=%s bytes=%s",
            operation,
            response.status,
            response.headers.get("Content-Type", ""),
            len(body.encode("utf-8", errors="replace")),
        )
        raise OxaPayTemporaryResponseError(
            f"OxaPay returned an invalid response while {operation}. "
            "Please try again in a moment."
        ) from exc
    if not isinstance(result, dict):
        raise OxaPayTemporaryResponseError(
            f"OxaPay returned an unexpected response while {operation}. "
            "Please try again in a moment."
        )
    return result


def _api_status(result: dict) -> int:
    """Return OxaPay's API status without allowing malformed values to crash."""
    try:
        return int(result.get("status", 0))
    except (TypeError, ValueError):
        return 0


async def _retry_temporary(
    operation: Callable[[], Awaitable[dict]],
    *,
    name: str,
    attempts: int = WHITE_LABEL_MAX_ATTEMPTS,
) -> dict:
    """Retry temporary provider/transport failures with bounded backoff."""
    last_error: BaseException | None = None
    total_attempts = max(1, int(attempts))
    for attempt in range(1, total_attempts + 1):
        try:
            return await operation()
        except (
            OxaPayTemporaryResponseError,
            aiohttp.ClientError,
            asyncio.TimeoutError,
        ) as exc:
            last_error = exc
            if attempt >= total_attempts:
                break
            delay = min(4.0, 0.65 * (2 ** (attempt - 1)))
            delay += secrets.randbelow(250) / 1000
            logger.warning(
                "[OXAPAY] Temporary failure while %s; retrying attempt %s/%s "
                "in %.2fs (%s)",
                name,
                attempt + 1,
                total_attempts,
                delay,
                type(exc).__name__,
            )
            await asyncio.sleep(delay)
    raise OxaPayTemporaryResponseError(
        "OxaPay is temporarily unavailable after several automatic retries. "
        "Please press Retry Payment."
    ) from last_error


async def get_accepted_method_keys(force: bool = False) -> list[str]:
    """Return only payment methods enabled for this OxaPay merchant."""
    global _accepted_cache
    error = configuration_error()
    if error:
        raise RuntimeError(error)
    now = time.monotonic()
    if (
        not force
        and _accepted_cache
        and now - _accepted_cache[0] < ACCEPTED_CACHE_TTL
    ):
        accepted = _accepted_cache[1]
    else:
        headers = {
            "merchant_api_key": _api_key(),
            "Content-Type": "application/json",
        }
        timeout = aiohttp.ClientTimeout(
            total=10,
            connect=5,
            sock_connect=5,
            sock_read=7,
        )
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"{OXAPAY_API_BASE}/payment/accepted-currencies",
                    headers=headers,
                ) as response:
                    result = await _read_oxapay_json(
                        response,
                        "loading payment methods",
                    )
                    response_status = response.status
            if response_status != 200 or _api_status(result) != 200:
                raise RuntimeError(
                    _oxapay_error(
                        result,
                        "Could not load accepted OxaPay currencies.",
                    )
                )
            values = (result.get("data") or {}).get("list") or []
            accepted = frozenset(str(value).upper() for value in values)
            if not accepted:
                raise RuntimeError("OxaPay returned no accepted currencies.")
            _accepted_cache = (now, accepted)
        except (
            OxaPayTemporaryResponseError,
            aiohttp.ClientError,
            asyncio.TimeoutError,
        ):
            if (
                _accepted_cache
                and now - _accepted_cache[0] < ACCEPTED_STALE_TTL
            ):
                accepted = _accepted_cache[1]
                logger.warning(
                    "[OXAPAY] Using cached accepted currencies after a "
                    "temporary API response failure."
                )
            else:
                # Currency discovery is optional. Address creation remains
                # authoritative and rejects any disabled merchant currency.
                accepted = frozenset(
                    method["pay_currency"].upper()
                    for method in PAYMENT_METHODS.values()
                )
                logger.warning(
                    "[OXAPAY] Accepted-currencies API unavailable; showing "
                    "configured methods and deferring validation to payment "
                    "address creation."
                )

    return [
        key
        for key, method in PAYMENT_METHODS.items()
        if method["pay_currency"].upper() in accepted
    ]


async def create_white_label_payment(
    user_id: int,
    plan_selection: str,
    method_selection: str,
) -> dict:
    error = configuration_error()
    if error:
        raise RuntimeError(error)
    plan = PLANS.get(plan_selection)
    if not plan:
        raise ValueError("Unknown payment plan.")
    method = PAYMENT_METHODS.get(method_selection)
    if not method:
        raise ValueError("Unknown payment method.")
    accepted_methods = await get_accepted_method_keys(force=True)
    if method_selection not in accepted_methods:
        raise RuntimeError(
            f"{method['label']} is not enabled in your OxaPay Merchant Service."
        )

    order_id = f"tg-{user_id}-{secrets.token_hex(12)}"
    created = await db.create_payment_order(
        order_id=order_id,
        user_id=user_id,
        plan=plan["plan"],
        days=plan["days"],
        expected_amount=plan["price"],
        currency="USD",
    )
    if not created:
        raise RuntimeError("Could not store the payment order.")

    payload = {
        "amount": float(plan["price"]),
        "currency": "USD",
        "pay_currency": method["pay_currency"],
        "network": method["network"],
        "lifetime": 120,
        "fee_paid_by_payer": 1,
        "under_paid_coverage": 0,
        "callback_url": _callback_url(),
        "order_id": order_id,
        "description": f"{plan['name']} plan for Telegram user {user_id}",
    }
    headers = {
        "merchant_api_key": _api_key(),
        "Content-Type": "application/json",
    }

    try:
        timeout = aiohttp.ClientTimeout(
            total=20,
            connect=7,
            sock_connect=7,
            sock_read=12,
        )
        connector = aiohttp.TCPConnector(
            ttl_dns_cache=300,
            enable_cleanup_closed=True,
        )
        async with aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            headers={"Accept": "application/json"},
        ) as session:
            async def request_payment() -> dict:
                async with session.post(
                    f"{OXAPAY_API_BASE}/payment/white-label",
                    headers=headers,
                    json=payload,
                ) as response:
                    result = await _read_oxapay_json(
                        response,
                        "creating the payment address",
                    )
                    if response.status in RETRYABLE_HTTP_STATUSES:
                        raise OxaPayTemporaryResponseError(
                            "OxaPay temporarily could not create the payment address."
                        )
                    api_status = _api_status(result)
                    if api_status in RETRYABLE_HTTP_STATUSES:
                        raise OxaPayTemporaryResponseError(
                            "OxaPay temporarily could not create the payment address."
                        )
                    if response.status != 200 or api_status != 200:
                        # Parsed merchant/authentication/currency errors are
                        # authoritative and must not be hidden by retries.
                        raise RuntimeError(
                            _oxapay_error(
                                result,
                                "OxaPay rejected the payment request.",
                            )
                        )
                    response_data = result.get("data")
                    if not isinstance(response_data, dict):
                        raise OxaPayTemporaryResponseError(
                            "OxaPay returned incomplete payment information."
                        )
                    required = (
                        response_data.get("track_id"),
                        response_data.get("address"),
                        response_data.get("pay_amount"),
                        response_data.get("expired_at"),
                    )
                    if any(value in (None, "", 0, "0") for value in required):
                        raise OxaPayTemporaryResponseError(
                            "OxaPay returned incomplete payment information."
                        )
                    return result

            result = await _retry_temporary(
                request_payment,
                name="creating the payment address",
            )

        data = result.get("data") or {}
        track_id = str(data.get("track_id") or "").strip()
        address = str(data.get("address") or "").strip()
        pay_amount = str(data.get("pay_amount") or "").strip()
        pay_currency = str(data.get("pay_currency") or method["pay_currency"]).upper()
        network_name = method["network_name"]
        memo = str(data.get("memo") or "").strip()
        expired_at = int(data.get("expired_at") or 0)
        if not track_id or not address or not pay_amount or expired_at <= 0:
            raise RuntimeError("OxaPay returned incomplete payment information.")

        saved = await db.attach_payment_invoice(order_id, track_id, "")
        if not saved:
            raise RuntimeError("Could not save the OxaPay payment.")

        return {
            "order_id": order_id,
            "track_id": track_id,
            "address": address,
            "pay_amount": pay_amount,
            "pay_currency": pay_currency,
            "network_name": network_name,
            "memo": memo,
            "expired_at": expired_at,
            "lifetime": int(data.get("lifetime") or 120),
            **plan,
            "method": method,
        }
    except Exception as exc:
        await db.fail_payment_order(order_id, str(exc))
        raise


async def _fetch_payment(track_id: str) -> dict:
    headers = {
        "merchant_api_key": _api_key(),
        "Content-Type": "application/json",
    }
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(
            f"{OXAPAY_API_BASE}/payment/{track_id}",
            headers=headers,
        ) as response:
            result = await _read_oxapay_json(
                response,
                "verifying the payment",
            )
    if response.status != 200 or _api_status(result) != 200:
        raise RuntimeError(_oxapay_error(result, "Payment verification failed."))
    return result.get("data") or {}


def _decimal(value) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("-1")


def _oxapay_error(result: dict, fallback: str) -> str:
    error = result.get("error")
    if isinstance(error, dict):
        detail = str(error.get("message") or "").strip()
        key = str(error.get("key") or "").strip()
        if detail:
            return f"{key}: {detail}" if key else detail
    return str(result.get("message") or fallback)


def _payment_field(data: dict, snake_case: str, camel_case: str = ""):
    value = data.get(snake_case)
    if value in (None, "") and camel_case:
        value = data.get(camel_case)
    return value


async def _deliver_activation(
    app,
    order_id: str,
    activate: Callable[[object, dict], Awaitable[None]],
) -> None:
    claim_token = secrets.token_hex(16)
    entitlement = await db.claim_payment_activation(order_id, claim_token)
    if not entitlement:
        return
    user_id = int(entitlement["user_id"])
    lock = _ACTIVATION_LOCKS.setdefault(user_id, asyncio.Lock())
    try:
        async with lock:
            # Another order for this user may have finalized while this older
            # delivery was waiting. Always activate the canonical latest row.
            current = await db.get_current_payment_entitlement(user_id)
            if not current:
                raise RuntimeError("Canonical paid entitlement is unavailable.")
            await activate(app, current)
            if not await db.mark_payment_activated(order_id, claim_token):
                raise RuntimeError("Could not mark payment activation delivered.")
    except Exception:
        await db.release_payment_activation(order_id, claim_token)
        raise


async def _process_callback(
    app,
    callback_data: dict,
    activate: Callable[[object, dict], Awaitable[None]],
    trusted_callback: bool = False,
) -> None:
    data = callback_data.get("data") if isinstance(callback_data.get("data"), dict) else callback_data
    track_id = str(_payment_field(data, "track_id", "trackId") or "").strip()
    order_id = str(_payment_field(data, "order_id", "orderId") or "").strip()
    if not track_id or not order_id:
        return

    callback_status = str(data.get("status") or "").strip().lower()
    if trusted_callback and callback_status not in SUCCESS_STATUSES:
        return

    # A callback reaching this trusted path has already passed OxaPay's
    # raw-body HMAC verification. Use it immediately when it contains all
    # fields required to bind the payment to the stored order. Reconciliation
    # uses OxaPay's read API when a callback was missed.
    verified = data if trusted_callback else {}
    required_callback_fields = (
        _payment_field(data, "track_id", "trackId"),
        _payment_field(data, "order_id", "orderId"),
        data.get("status"),
        data.get("currency"),
        data.get("amount"),
    )
    if not trusted_callback or any(value in (None, "") for value in required_callback_fields):
        verified = await _fetch_payment(track_id)

    verified_status = str(verified.get("status") or "").strip().lower()
    if verified_status not in SUCCESS_STATUSES:
        return
    if str(_payment_field(verified, "track_id", "trackId") or "").strip() != track_id:
        raise RuntimeError("OxaPay track ID verification failed.")
    if str(_payment_field(verified, "order_id", "orderId") or "").strip() != order_id:
        raise RuntimeError("OxaPay order ID verification failed.")

    order = await db.get_payment_order(order_id)
    if not order:
        raise RuntimeError("Unknown OxaPay order.")
    if order["status"] == "paid":
        await _deliver_activation(app, order_id, activate)
        return
    if str(order.get("track_id") or "") != track_id:
        raise RuntimeError("Stored OxaPay track ID does not match.")
    if str(verified.get("currency") or "").upper() != str(order["currency"]).upper():
        raise RuntimeError("OxaPay payment currency does not match the order.")
    verified_amount = _decimal(verified.get("amount"))
    expected_amount = _decimal(order["expected_amount"])
    if (
        not verified_amount.is_finite()
        or not expected_amount.is_finite()
        or expected_amount <= 0
        or verified_amount < expected_amount
    ):
        raise RuntimeError("OxaPay payment amount is below the order amount.")

    entitlement = await db.finalize_paid_order(order_id, track_id)
    if not entitlement:
        return
    await _deliver_activation(app, order_id, activate)


async def _reconcile_pending(
    telegram_app,
    activate: Callable[[object, dict], Awaitable[None]],
) -> None:
    """Recover paid orders when a webhook is delayed, lost, or raced."""
    delay = 3
    while True:
        try:
            await asyncio.sleep(delay)
            delay = 2
            pending = await db.list_pending_payment_orders(limit=100)
            for order in pending:
                try:
                    await _process_callback(
                        telegram_app,
                        {
                            "track_id": order["track_id"],
                            "order_id": order["order_id"],
                        },
                        activate,
                        trusted_callback=False,
                    )
                except Exception as exc:
                    logger.warning(
                        "[OXAPAY] Pending order %s reconciliation deferred: %s",
                        order["order_id"],
                        exc,
                    )
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("[OXAPAY] Pending-payment reconciliation failed.")
            await asyncio.sleep(2)


async def _webhook(request: web.Request) -> web.Response:
    raw_body = await request.read()
    received = request.headers.get("HMAC", "").strip().lower()
    expected = hmac.new(
        _api_key().encode("utf-8"),
        raw_body,
        hashlib.sha512,
    ).hexdigest()
    if not received or not hmac.compare_digest(received, expected):
        return web.Response(text="Invalid HMAC", status=401)
    try:
        payload = json.loads(raw_body.decode("utf-8"))
        await _process_callback(
            request.app["telegram_app"],
            payload,
            request.app["activate_payment"],
            trusted_callback=True,
        )
    except (UnicodeDecodeError, json.JSONDecodeError):
        return web.Response(text="Invalid JSON", status=400)
    except Exception:
        logger.exception("[OXAPAY] Callback processing failed.")
        return web.Response(text="Temporary failure", status=500)
    return web.Response(text="OK", status=200)


async def _health(_request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "service": "oxapay-webhook"})


async def start_webhook(
    telegram_app,
    activate: Callable[[object, dict], Awaitable[None]],
) -> None:
    if not _api_key():
        logger.warning("[OXAPAY] Disabled: OXAPAY_MERCHANT_API_KEY is missing.")
        return

    web_app = web.Application(client_max_size=64 * 1024)
    web_app["telegram_app"] = telegram_app
    web_app["activate_payment"] = activate
    web_app.router.add_post("/oxapay/webhook", _webhook)
    web_app.router.add_get("/health", _health)

    runner = web.AppRunner(web_app, access_log=None)
    await runner.setup()
    port = int(os.environ.get("PORT", "8080"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    telegram_app.bot_data["_oxapay_runner"] = runner
    telegram_app.bot_data["_oxapay_reconcile_task"] = asyncio.create_task(
        _reconcile_pending(telegram_app, activate),
        name="oxapay-payment-reconciliation",
    )
    logger.info("[OXAPAY] Webhook listening on port %s.", port)


async def stop_webhook(telegram_app) -> None:
    task = telegram_app.bot_data.pop("_oxapay_reconcile_task", None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    runner = telegram_app.bot_data.pop("_oxapay_runner", None)
    if runner:
        await runner.cleanup()
"""Secure payment invoices and webhook processing for the Telegram bot."""
# Duplicate copy retained as inert-compatible Python; no future import here.

import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from decimal import Decimal, InvalidOperation
from typing import Awaitable, Callable

import aiohttp
from aiohttp import web

import database as db

logger = logging.getLogger(__name__)


class OxaPayTemporaryResponseError(RuntimeError):
    """OxaPay/proxy returned no usable API document; retry may succeed."""


OXAPAY_API_BASE = "https://api.oxapay.com/v1"
SUCCESS_STATUSES = frozenset({
    "paid",
    "manual_accept",
    "completed",
    "complete",
    "confirmed",
})
_ACTIVATION_LOCKS: dict[int, asyncio.Lock] = {}
WHITE_LABEL_MAX_ATTEMPTS = 4
RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})

PLANS = {
    "pay1d": {"name": "Core", "plan": "CORE", "days": 1, "price": Decimal("1.50")},
    "pay10": {"name": "Core", "plan": "CORE", "days": 7, "price": Decimal("8.00")},
    "pay15": {"name": "Elite", "plan": "ELITE", "days": 15, "price": Decimal("12.00")},
    "pay30": {"name": "Root", "plan": "ROOT", "days": 30, "price": Decimal("25.00")},
}

PAYMENT_METHODS = {
    "bep20": {
        "label": "BEP20", "pay_currency": "USDT", "network": "BSC",
        "network_name": "Binance Smart Chain",
    },
    "trx": {
        "label": "TRX", "pay_currency": "TRX", "network": "Tron",
        "network_name": "Tron Network",
    },
    "pol": {
        "label": "POL", "pay_currency": "POL", "network": "Polygon",
        "network_name": "Polygon Network",
    },
    "ton": {
        "label": "TON", "pay_currency": "GRAM", "network": "The Open Network",
        "network_name": "TON Network",
    },
    "ltc": {
        "label": "LTC", "pay_currency": "LTC", "network": "Litecoin",
        "network_name": "Litecoin Network",
    },
    "btc": {
        "label": "BTC", "pay_currency": "BTC", "network": "Bitcoin",
        "network_name": "Bitcoin Network",
    },
    "sol": {
        "label": "SOL", "pay_currency": "SOL", "network": "Solana",
        "network_name": "Solana Network",
    },
    "eth": {
        "label": "ETH", "pay_currency": "ETH", "network": "Ethereum",
        "network_name": "Ethereum Network",
    },
}

_accepted_cache: tuple[float, frozenset[str]] | None = None
ACCEPTED_CACHE_TTL = 30
ACCEPTED_STALE_TTL = 15 * 60


def _api_key() -> str:
    return os.environ.get("OXAPAY_MERCHANT_API_KEY", "").strip()


def _callback_url() -> str:
    return os.environ.get("OXAPAY_CALLBACK_URL", "").strip()


def _sandbox_enabled() -> bool:
    return os.environ["OXAPAY_SANDBOX"].strip().lower() == "true"


def configuration_error() -> str | None:
    if not _api_key():
        return "OXAPAY_MERCHANT_API_KEY is not configured."
    callback = _callback_url()
    if not callback:
        return "OXAPAY_CALLBACK_URL is not configured."
    if not callback.startswith("https://"):
        return "OXAPAY_CALLBACK_URL must use https://."
    sandbox = os.environ.get("OXAPAY_SANDBOX", "").strip().lower()
    if sandbox not in {"true", "false"}:
        return "OXAPAY_SANDBOX must be set explicitly to true or false."
    if sandbox == "true":
        return (
            "Direct OxaPay crypto addresses require live mode. "
            "Set OXAPAY_SANDBOX=false."
        )
    if not db.is_connected():
        return "PostgreSQL is unavailable; secure payment orders cannot be created."
    return None


async def _read_oxapay_json(
    response: aiohttp.ClientResponse,
    operation: str,
) -> dict:
    """Decode an OxaPay response without exposing raw proxy/HTML errors."""
    body = await response.text()
    if not body.strip():
        raise OxaPayTemporaryResponseError(
            f"OxaPay returned an empty response while {operation}. "
            "Please try again in a moment."
        )
    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        logger.warning(
            "[OXAPAY] Non-JSON response while %s: status=%s content_type=%s bytes=%s",
            operation,
            response.status,
            response.headers.get("Content-Type", ""),
            len(body.encode("utf-8", errors="replace")),
        )
        raise OxaPayTemporaryResponseError(
            f"OxaPay returned an invalid response while {operation}. "
            "Please try again in a moment."
        ) from exc
    if not isinstance(result, dict):
        raise OxaPayTemporaryResponseError(
            f"OxaPay returned an unexpected response while {operation}. "
            "Please try again in a moment."
        )
    return result


def _api_status(result: dict) -> int:
    """Return OxaPay's API status without allowing malformed values to crash."""
    try:
        return int(result.get("status", 0))
    except (TypeError, ValueError):
        return 0


async def _retry_temporary(
    operation: Callable[[], Awaitable[dict]],
    *,
    name: str,
    attempts: int = WHITE_LABEL_MAX_ATTEMPTS,
) -> dict:
    """Retry temporary provider/transport failures with bounded backoff."""
    last_error: BaseException | None = None
    total_attempts = max(1, int(attempts))
    for attempt in range(1, total_attempts + 1):
        try:
            return await operation()
        except (
            OxaPayTemporaryResponseError,
            aiohttp.ClientError,
            asyncio.TimeoutError,
        ) as exc:
            last_error = exc
            if attempt >= total_attempts:
                break
            delay = min(4.0, 0.65 * (2 ** (attempt - 1)))
            delay += secrets.randbelow(250) / 1000
            logger.warning(
                "[OXAPAY] Temporary failure while %s; retrying attempt %s/%s "
                "in %.2fs (%s)",
                name,
                attempt + 1,
                total_attempts,
                delay,
                type(exc).__name__,
            )
            await asyncio.sleep(delay)
    raise OxaPayTemporaryResponseError(
        "OxaPay is temporarily unavailable after several automatic retries. "
        "Please press Retry Payment."
    ) from last_error


async def get_accepted_method_keys(force: bool = False) -> list[str]:
    """Return only payment methods enabled for this OxaPay merchant."""
    global _accepted_cache
    error = configuration_error()
    if error:
        raise RuntimeError(error)
    now = time.monotonic()
    if (
        not force
        and _accepted_cache
        and now - _accepted_cache[0] < ACCEPTED_CACHE_TTL
    ):
        accepted = _accepted_cache[1]
    else:
        headers = {
            "merchant_api_key": _api_key(),
            "Content-Type": "application/json",
        }
        timeout = aiohttp.ClientTimeout(
            total=10,
            connect=5,
            sock_connect=5,
            sock_read=7,
        )
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"{OXAPAY_API_BASE}/payment/accepted-currencies",
                    headers=headers,
                ) as response:
                    result = await _read_oxapay_json(
                        response,
                        "loading payment methods",
                    )
                    response_status = response.status
            if response_status != 200 or _api_status(result) != 200:
                raise RuntimeError(
                    _oxapay_error(
                        result,
                        "Could not load accepted OxaPay currencies.",
                    )
                )
            values = (result.get("data") or {}).get("list") or []
            accepted = frozenset(str(value).upper() for value in values)
            if not accepted:
                raise RuntimeError("OxaPay returned no accepted currencies.")
            _accepted_cache = (now, accepted)
        except (
            OxaPayTemporaryResponseError,
            aiohttp.ClientError,
            asyncio.TimeoutError,
        ):
            if (
                _accepted_cache
                and now - _accepted_cache[0] < ACCEPTED_STALE_TTL
            ):
                accepted = _accepted_cache[1]
                logger.warning(
                    "[OXAPAY] Using cached accepted currencies after a "
                    "temporary API response failure."
                )
            else:
                # Currency discovery is optional. Address creation remains
                # authoritative and rejects any disabled merchant currency.
                accepted = frozenset(
                    method["pay_currency"].upper()
                    for method in PAYMENT_METHODS.values()
                )
                logger.warning(
                    "[OXAPAY] Accepted-currencies API unavailable; showing "
                    "configured methods and deferring validation to payment "
                    "address creation."
                )

    return [
        key
        for key, method in PAYMENT_METHODS.items()
        if method["pay_currency"].upper() in accepted
    ]


async def create_white_label_payment(
    user_id: int,
    plan_selection: str,
    method_selection: str,
) -> dict:
    error = configuration_error()
    if error:
        raise RuntimeError(error)
    plan = PLANS.get(plan_selection)
    if not plan:
        raise ValueError("Unknown payment plan.")
    method = PAYMENT_METHODS.get(method_selection)
    if not method:
        raise ValueError("Unknown payment method.")
    accepted_methods = await get_accepted_method_keys(force=True)
    if method_selection not in accepted_methods:
        raise RuntimeError(
            f"{method['label']} is not enabled in your OxaPay Merchant Service."
        )

    order_id = f"tg-{user_id}-{secrets.token_hex(12)}"
    created = await db.create_payment_order(
        order_id=order_id,
        user_id=user_id,
        plan=plan["plan"],
        days=plan["days"],
        expected_amount=plan["price"],
        currency="USD",
    )
    if not created:
        raise RuntimeError("Could not store the payment order.")

    payload = {
        "amount": float(plan["price"]),
        "currency": "USD",
        "pay_currency": method["pay_currency"],
        "network": method["network"],
        "lifetime": 120,
        "fee_paid_by_payer": 1,
        "under_paid_coverage": 0,
        "callback_url": _callback_url(),
        "order_id": order_id,
        "description": f"{plan['name']} plan for Telegram user {user_id}",
    }
    headers = {
        "merchant_api_key": _api_key(),
        "Content-Type": "application/json",
    }

    try:
        timeout = aiohttp.ClientTimeout(
            total=20,
            connect=7,
            sock_connect=7,
            sock_read=12,
        )
        connector = aiohttp.TCPConnector(
            ttl_dns_cache=300,
            enable_cleanup_closed=True,
        )
        async with aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            headers={"Accept": "application/json"},
        ) as session:
            async def request_payment() -> dict:
                async with session.post(
                    f"{OXAPAY_API_BASE}/payment/white-label",
                    headers=headers,
                    json=payload,
                ) as response:
                    result = await _read_oxapay_json(
                        response,
                        "creating the payment address",
                    )
                    if response.status in RETRYABLE_HTTP_STATUSES:
                        raise OxaPayTemporaryResponseError(
                            "OxaPay temporarily could not create the payment address."
                        )
                    api_status = _api_status(result)
                    if api_status in RETRYABLE_HTTP_STATUSES:
                        raise OxaPayTemporaryResponseError(
                            "OxaPay temporarily could not create the payment address."
                        )
                    if response.status != 200 or api_status != 200:
                        # Parsed merchant/authentication/currency errors are
                        # authoritative and must not be hidden by retries.
                        raise RuntimeError(
                            _oxapay_error(
                                result,
                                "OxaPay rejected the payment request.",
                            )
                        )
                    response_data = result.get("data")
                    if not isinstance(response_data, dict):
                        raise OxaPayTemporaryResponseError(
                            "OxaPay returned incomplete payment information."
                        )
                    required = (
                        response_data.get("track_id"),
                        response_data.get("address"),
                        response_data.get("pay_amount"),
                        response_data.get("expired_at"),
                    )
                    if any(value in (None, "", 0, "0") for value in required):
                        raise OxaPayTemporaryResponseError(
                            "OxaPay returned incomplete payment information."
                        )
                    return result

            result = await _retry_temporary(
                request_payment,
                name="creating the payment address",
            )

        data = result.get("data") or {}
        track_id = str(data.get("track_id") or "").strip()
        address = str(data.get("address") or "").strip()
        pay_amount = str(data.get("pay_amount") or "").strip()
        pay_currency = str(data.get("pay_currency") or method["pay_currency"]).upper()
        network_name = method["network_name"]
        memo = str(data.get("memo") or "").strip()
        expired_at = int(data.get("expired_at") or 0)
        if not track_id or not address or not pay_amount or expired_at <= 0:
            raise RuntimeError("OxaPay returned incomplete payment information.")

        saved = await db.attach_payment_invoice(order_id, track_id, "")
        if not saved:
            raise RuntimeError("Could not save the OxaPay payment.")

        return {
            "order_id": order_id,
            "track_id": track_id,
            "address": address,
            "pay_amount": pay_amount,
            "pay_currency": pay_currency,
            "network_name": network_name,
            "memo": memo,
            "expired_at": expired_at,
            "lifetime": int(data.get("lifetime") or 120),
            **plan,
            "method": method,
        }
    except Exception as exc:
        await db.fail_payment_order(order_id, str(exc))
        raise


async def _fetch_payment(track_id: str) -> dict:
    headers = {
        "merchant_api_key": _api_key(),
        "Content-Type": "application/json",
    }
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(
            f"{OXAPAY_API_BASE}/payment/{track_id}",
            headers=headers,
        ) as response:
            result = await _read_oxapay_json(
                response,
                "verifying the payment",
            )
    if response.status != 200 or _api_status(result) != 200:
        raise RuntimeError(_oxapay_error(result, "Payment verification failed."))
    return result.get("data") or {}


def _decimal(value) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("-1")


def _oxapay_error(result: dict, fallback: str) -> str:
    error = result.get("error")
    if isinstance(error, dict):
        detail = str(error.get("message") or "").strip()
        key = str(error.get("key") or "").strip()
        if detail:
            return f"{key}: {detail}" if key else detail
    return str(result.get("message") or fallback)


def _payment_field(data: dict, snake_case: str, camel_case: str = ""):
    value = data.get(snake_case)
    if value in (None, "") and camel_case:
        value = data.get(camel_case)
    return value


async def _deliver_activation(
    app,
    order_id: str,
    activate: Callable[[object, dict], Awaitable[None]],
) -> None:
    claim_token = secrets.token_hex(16)
    entitlement = await db.claim_payment_activation(order_id, claim_token)
    if not entitlement:
        return
    user_id = int(entitlement["user_id"])
    lock = _ACTIVATION_LOCKS.setdefault(user_id, asyncio.Lock())
    try:
        async with lock:
            # Another order for this user may have finalized while this older
            # delivery was waiting. Always activate the canonical latest row.
            current = await db.get_current_payment_entitlement(user_id)
            if not current:
                raise RuntimeError("Canonical paid entitlement is unavailable.")
            await activate(app, current)
            if not await db.mark_payment_activated(order_id, claim_token):
                raise RuntimeError("Could not mark payment activation delivered.")
    except Exception:
        await db.release_payment_activation(order_id, claim_token)
        raise


async def _process_callback(
    app,
    callback_data: dict,
    activate: Callable[[object, dict], Awaitable[None]],
    trusted_callback: bool = False,
) -> None:
    data = callback_data.get("data") if isinstance(callback_data.get("data"), dict) else callback_data
    track_id = str(_payment_field(data, "track_id", "trackId") or "").strip()
    order_id = str(_payment_field(data, "order_id", "orderId") or "").strip()
    if not track_id or not order_id:
        return

    callback_status = str(data.get("status") or "").strip().lower()
    if trusted_callback and callback_status not in SUCCESS_STATUSES:
        return

    # A callback reaching this trusted path has already passed OxaPay's
    # raw-body HMAC verification. Use it immediately when it contains all
    # fields required to bind the payment to the stored order. Reconciliation
    # uses OxaPay's read API when a callback was missed.
    verified = data if trusted_callback else {}
    required_callback_fields = (
        _payment_field(data, "track_id", "trackId"),
        _payment_field(data, "order_id", "orderId"),
        data.get("status"),
        data.get("currency"),
        data.get("amount"),
    )
    if not trusted_callback or any(value in (None, "") for value in required_callback_fields):
        verified = await _fetch_payment(track_id)

    verified_status = str(verified.get("status") or "").strip().lower()
    if verified_status not in SUCCESS_STATUSES:
        return
    if str(_payment_field(verified, "track_id", "trackId") or "").strip() != track_id:
        raise RuntimeError("OxaPay track ID verification failed.")
    if str(_payment_field(verified, "order_id", "orderId") or "").strip() != order_id:
        raise RuntimeError("OxaPay order ID verification failed.")

    order = await db.get_payment_order(order_id)
    if not order:
        raise RuntimeError("Unknown OxaPay order.")
    if order["status"] == "paid":
        await _deliver_activation(app, order_id, activate)
        return
    if str(order.get("track_id") or "") != track_id:
        raise RuntimeError("Stored OxaPay track ID does not match.")
    if str(verified.get("currency") or "").upper() != str(order["currency"]).upper():
        raise RuntimeError("OxaPay payment currency does not match the order.")
    verified_amount = _decimal(verified.get("amount"))
    expected_amount = _decimal(order["expected_amount"])
    if (
        not verified_amount.is_finite()
        or not expected_amount.is_finite()
        or expected_amount <= 0
        or verified_amount < expected_amount
    ):
        raise RuntimeError("OxaPay payment amount is below the order amount.")

    entitlement = await db.finalize_paid_order(order_id, track_id)
    if not entitlement:
        return
    await _deliver_activation(app, order_id, activate)


async def _reconcile_pending(
    telegram_app,
    activate: Callable[[object, dict], Awaitable[None]],
) -> None:
    """Recover paid orders when a webhook is delayed, lost, or raced."""
    delay = 3
    while True:
        try:
            await asyncio.sleep(delay)
            delay = 2
            pending = await db.list_pending_payment_orders(limit=100)
            for order in pending:
                try:
                    await _process_callback(
                        telegram_app,
                        {
                            "track_id": order["track_id"],
                            "order_id": order["order_id"],
                        },
                        activate,
                        trusted_callback=False,
                    )
                except Exception as exc:
                    logger.warning(
                        "[OXAPAY] Pending order %s reconciliation deferred: %s",
                        order["order_id"],
                        exc,
                    )
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("[OXAPAY] Pending-payment reconciliation failed.")
            await asyncio.sleep(2)


async def _webhook(request: web.Request) -> web.Response:
    raw_body = await request.read()
    received = request.headers.get("HMAC", "").strip().lower()
    expected = hmac.new(
        _api_key().encode("utf-8"),
        raw_body,
        hashlib.sha512,
    ).hexdigest()
    if not received or not hmac.compare_digest(received, expected):
        return web.Response(text="Invalid HMAC", status=401)
    try:
        payload = json.loads(raw_body.decode("utf-8"))
        await _process_callback(
            request.app["telegram_app"],
            payload,
            request.app["activate_payment"],
            trusted_callback=True,
        )
    except (UnicodeDecodeError, json.JSONDecodeError):
        return web.Response(text="Invalid JSON", status=400)
    except Exception:
        logger.exception("[OXAPAY] Callback processing failed.")
        return web.Response(text="Temporary failure", status=500)
    return web.Response(text="OK", status=200)


async def _health(_request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "service": "oxapay-webhook"})


async def start_webhook(
    telegram_app,
    activate: Callable[[object, dict], Awaitable[None]],
) -> None:
    if not _api_key():
        logger.warning("[OXAPAY] Disabled: OXAPAY_MERCHANT_API_KEY is missing.")
        return

    web_app = web.Application(client_max_size=64 * 1024)
    web_app["telegram_app"] = telegram_app
    web_app["activate_payment"] = activate
    web_app.router.add_post("/oxapay/webhook", _webhook)
    web_app.router.add_get("/health", _health)

    runner = web.AppRunner(web_app, access_log=None)
    await runner.setup()
    port = int(os.environ.get("PORT", "8080"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    telegram_app.bot_data["_oxapay_runner"] = runner
    telegram_app.bot_data["_oxapay_reconcile_task"] = asyncio.create_task(
        _reconcile_pending(telegram_app, activate),
        name="oxapay-payment-reconciliation",
    )
    logger.info("[OXAPAY] Webhook listening on port %s.", port)


async def stop_webhook(telegram_app) -> None:
    task = telegram_app.bot_data.pop("_oxapay_reconcile_task", None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    runner = telegram_app.bot_data.pop("_oxapay_runner", None)
    if runner:
        await runner.cleanup()
"""Secure payment invoices and webhook processing for the Telegram bot."""
# Duplicate copy retained as inert-compatible Python; no future import here.

import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from decimal import Decimal, InvalidOperation
from typing import Awaitable, Callable

import aiohttp
from aiohttp import web

import database as db

logger = logging.getLogger(__name__)


class OxaPayTemporaryResponseError(RuntimeError):
    """OxaPay/proxy returned no usable API document; retry may succeed."""


OXAPAY_API_BASE = "https://api.oxapay.com/v1"
SUCCESS_STATUSES = frozenset({
    "paid",
    "manual_accept",
    "completed",
    "complete",
    "confirmed",
})
_ACTIVATION_LOCKS: dict[int, asyncio.Lock] = {}
WHITE_LABEL_MAX_ATTEMPTS = 4
RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})

PLANS = {
    "pay1d": {"name": "Core", "plan": "CORE", "days": 1, "price": Decimal("1.50")},
    "pay10": {"name": "Core", "plan": "CORE", "days": 7, "price": Decimal("8.00")},
    "pay15": {"name": "Elite", "plan": "ELITE", "days": 15, "price": Decimal("12.00")},
    "pay30": {"name": "Root", "plan": "ROOT", "days": 30, "price": Decimal("25.00")},
}

PAYMENT_METHODS = {
    "bep20": {
        "label": "BEP20", "pay_currency": "USDT", "network": "BSC",
        "network_name": "Binance Smart Chain",
    },
    "trx": {
        "label": "TRX", "pay_currency": "TRX", "network": "Tron",
        "network_name": "Tron Network",
    },
    "pol": {
        "label": "POL", "pay_currency": "POL", "network": "Polygon",
        "network_name": "Polygon Network",
    },
    "ton": {
        "label": "TON", "pay_currency": "GRAM", "network": "The Open Network",
        "network_name": "TON Network",
    },
    "ltc": {
        "label": "LTC", "pay_currency": "LTC", "network": "Litecoin",
        "network_name": "Litecoin Network",
    },
    "btc": {
        "label": "BTC", "pay_currency": "BTC", "network": "Bitcoin",
        "network_name": "Bitcoin Network",
    },
    "sol": {
        "label": "SOL", "pay_currency": "SOL", "network": "Solana",
        "network_name": "Solana Network",
    },
    "eth": {
        "label": "ETH", "pay_currency": "ETH", "network": "Ethereum",
        "network_name": "Ethereum Network",
    },
}

_accepted_cache: tuple[float, frozenset[str]] | None = None
ACCEPTED_CACHE_TTL = 30
ACCEPTED_STALE_TTL = 15 * 60


def _api_key() -> str:
    return os.environ.get("OXAPAY_MERCHANT_API_KEY", "").strip()


def _callback_url() -> str:
    return os.environ.get("OXAPAY_CALLBACK_URL", "").strip()


def _sandbox_enabled() -> bool:
    return os.environ["OXAPAY_SANDBOX"].strip().lower() == "true"


def configuration_error() -> str | None:
    if not _api_key():
        return "OXAPAY_MERCHANT_API_KEY is not configured."
    callback = _callback_url()
    if not callback:
        return "OXAPAY_CALLBACK_URL is not configured."
    if not callback.startswith("https://"):
        return "OXAPAY_CALLBACK_URL must use https://."
    sandbox = os.environ.get("OXAPAY_SANDBOX", "").strip().lower()
    if sandbox not in {"true", "false"}:
        return "OXAPAY_SANDBOX must be set explicitly to true or false."
    if sandbox == "true":
        return (
            "Direct OxaPay crypto addresses require live mode. "
            "Set OXAPAY_SANDBOX=false."
        )
    if not db.is_connected():
        return "PostgreSQL is unavailable; secure payment orders cannot be created."
    return None


async def _read_oxapay_json(
    response: aiohttp.ClientResponse,
    operation: str,
) -> dict:
    """Decode an OxaPay response without exposing raw proxy/HTML errors."""
    body = await response.text()
    if not body.strip():
        raise OxaPayTemporaryResponseError(
            f"OxaPay returned an empty response while {operation}. "
            "Please try again in a moment."
        )
    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        logger.warning(
            "[OXAPAY] Non-JSON response while %s: status=%s content_type=%s bytes=%s",
            operation,
            response.status,
            response.headers.get("Content-Type", ""),
            len(body.encode("utf-8", errors="replace")),
        )
        raise OxaPayTemporaryResponseError(
            f"OxaPay returned an invalid response while {operation}. "
            "Please try again in a moment."
        ) from exc
    if not isinstance(result, dict):
        raise OxaPayTemporaryResponseError(
            f"OxaPay returned an unexpected response while {operation}. "
            "Please try again in a moment."
        )
    return result


def _api_status(result: dict) -> int:
    """Return OxaPay's API status without allowing malformed values to crash."""
    try:
        return int(result.get("status", 0))
    except (TypeError, ValueError):
        return 0


async def _retry_temporary(
    operation: Callable[[], Awaitable[dict]],
    *,
    name: str,
    attempts: int = WHITE_LABEL_MAX_ATTEMPTS,
) -> dict:
    """Retry temporary provider/transport failures with bounded backoff."""
    last_error: BaseException | None = None
    total_attempts = max(1, int(attempts))
    for attempt in range(1, total_attempts + 1):
        try:
            return await operation()
        except (
            OxaPayTemporaryResponseError,
            aiohttp.ClientError,
            asyncio.TimeoutError,
        ) as exc:
            last_error = exc
            if attempt >= total_attempts:
                break
            delay = min(4.0, 0.65 * (2 ** (attempt - 1)))
            delay += secrets.randbelow(250) / 1000
            logger.warning(
                "[OXAPAY] Temporary failure while %s; retrying attempt %s/%s "
                "in %.2fs (%s)",
                name,
                attempt + 1,
                total_attempts,
                delay,
                type(exc).__name__,
            )
            await asyncio.sleep(delay)
    raise OxaPayTemporaryResponseError(
        "OxaPay is temporarily unavailable after several automatic retries. "
        "Please press Retry Payment."
    ) from last_error


async def get_accepted_method_keys(force: bool = False) -> list[str]:
    """Return only payment methods enabled for this OxaPay merchant."""
    global _accepted_cache
    error = configuration_error()
    if error:
        raise RuntimeError(error)
    now = time.monotonic()
    if (
        not force
        and _accepted_cache
        and now - _accepted_cache[0] < ACCEPTED_CACHE_TTL
    ):
        accepted = _accepted_cache[1]
    else:
        headers = {
            "merchant_api_key": _api_key(),
            "Content-Type": "application/json",
        }
        timeout = aiohttp.ClientTimeout(
            total=10,
            connect=5,
            sock_connect=5,
            sock_read=7,
        )
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"{OXAPAY_API_BASE}/payment/accepted-currencies",
                    headers=headers,
                ) as response:
                    result = await _read_oxapay_json(
                        response,
                        "loading payment methods",
                    )
                    response_status = response.status
            if response_status != 200 or _api_status(result) != 200:
                raise RuntimeError(
                    _oxapay_error(
                        result,
                        "Could not load accepted OxaPay currencies.",
                    )
                )
            values = (result.get("data") or {}).get("list") or []
            accepted = frozenset(str(value).upper() for value in values)
            if not accepted:
                raise RuntimeError("OxaPay returned no accepted currencies.")
            _accepted_cache = (now, accepted)
        except (
            OxaPayTemporaryResponseError,
            aiohttp.ClientError,
            asyncio.TimeoutError,
        ):
            if (
                _accepted_cache
                and now - _accepted_cache[0] < ACCEPTED_STALE_TTL
            ):
                accepted = _accepted_cache[1]
                logger.warning(
                    "[OXAPAY] Using cached accepted currencies after a "
                    "temporary API response failure."
                )
            else:
                # Currency discovery is optional. Address creation remains
                # authoritative and rejects any disabled merchant currency.
                accepted = frozenset(
                    method["pay_currency"].upper()
                    for method in PAYMENT_METHODS.values()
                )
                logger.warning(
                    "[OXAPAY] Accepted-currencies API unavailable; showing "
                    "configured methods and deferring validation to payment "
                    "address creation."
                )

    return [
        key
        for key, method in PAYMENT_METHODS.items()
        if method["pay_currency"].upper() in accepted
    ]


async def create_white_label_payment(
    user_id: int,
    plan_selection: str,
    method_selection: str,
) -> dict:
    error = configuration_error()
    if error:
        raise RuntimeError(error)
    plan = PLANS.get(plan_selection)
    if not plan:
        raise ValueError("Unknown payment plan.")
    method = PAYMENT_METHODS.get(method_selection)
    if not method:
        raise ValueError("Unknown payment method.")
    accepted_methods = await get_accepted_method_keys(force=True)
    if method_selection not in accepted_methods:
        raise RuntimeError(
            f"{method['label']} is not enabled in your OxaPay Merchant Service."
        )

    order_id = f"tg-{user_id}-{secrets.token_hex(12)}"
    created = await db.create_payment_order(
        order_id=order_id,
        user_id=user_id,
        plan=plan["plan"],
        days=plan["days"],
        expected_amount=plan["price"],
        currency="USD",
    )
    if not created:
        raise RuntimeError("Could not store the payment order.")

    payload = {
        "amount": float(plan["price"]),
        "currency": "USD",
        "pay_currency": method["pay_currency"],
        "network": method["network"],
        "lifetime": 120,
        "fee_paid_by_payer": 1,
        "under_paid_coverage": 0,
        "callback_url": _callback_url(),
        "order_id": order_id,
        "description": f"{plan['name']} plan for Telegram user {user_id}",
    }
    headers = {
        "merchant_api_key": _api_key(),
        "Content-Type": "application/json",
    }

    try:
        timeout = aiohttp.ClientTimeout(
            total=20,
            connect=7,
            sock_connect=7,
            sock_read=12,
        )
        connector = aiohttp.TCPConnector(
            ttl_dns_cache=300,
            enable_cleanup_closed=True,
        )
        async with aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            headers={"Accept": "application/json"},
        ) as session:
            async def request_payment() -> dict:
                async with session.post(
                    f"{OXAPAY_API_BASE}/payment/white-label",
                    headers=headers,
                    json=payload,
                ) as response:
                    result = await _read_oxapay_json(
                        response,
                        "creating the payment address",
                    )
                    if response.status in RETRYABLE_HTTP_STATUSES:
                        raise OxaPayTemporaryResponseError(
                            "OxaPay temporarily could not create the payment address."
                        )
                    api_status = _api_status(result)
                    if api_status in RETRYABLE_HTTP_STATUSES:
                        raise OxaPayTemporaryResponseError(
                            "OxaPay temporarily could not create the payment address."
                        )
                    if response.status != 200 or api_status != 200:
                        # Parsed merchant/authentication/currency errors are
                        # authoritative and must not be hidden by retries.
                        raise RuntimeError(
                            _oxapay_error(
                                result,
                                "OxaPay rejected the payment request.",
                            )
                        )
                    response_data = result.get("data")
                    if not isinstance(response_data, dict):
                        raise OxaPayTemporaryResponseError(
                            "OxaPay returned incomplete payment information."
                        )
                    required = (
                        response_data.get("track_id"),
                        response_data.get("address"),
                        response_data.get("pay_amount"),
                        response_data.get("expired_at"),
                    )
                    if any(value in (None, "", 0, "0") for value in required):
                        raise OxaPayTemporaryResponseError(
                            "OxaPay returned incomplete payment information."
                        )
                    return result

            result = await _retry_temporary(
                request_payment,
                name="creating the payment address",
            )

        data = result.get("data") or {}
        track_id = str(data.get("track_id") or "").strip()
        address = str(data.get("address") or "").strip()
        pay_amount = str(data.get("pay_amount") or "").strip()
        pay_currency = str(data.get("pay_currency") or method["pay_currency"]).upper()
        network_name = method["network_name"]
        memo = str(data.get("memo") or "").strip()
        expired_at = int(data.get("expired_at") or 0)
        if not track_id or not address or not pay_amount or expired_at <= 0:
            raise RuntimeError("OxaPay returned incomplete payment information.")

        saved = await db.attach_payment_invoice(order_id, track_id, "")
        if not saved:
            raise RuntimeError("Could not save the OxaPay payment.")

        return {
            "order_id": order_id,
            "track_id": track_id,
            "address": address,
            "pay_amount": pay_amount,
            "pay_currency": pay_currency,
            "network_name": network_name,
            "memo": memo,
            "expired_at": expired_at,
            "lifetime": int(data.get("lifetime") or 120),
            **plan,
            "method": method,
        }
    except Exception as exc:
        await db.fail_payment_order(order_id, str(exc))
        raise


async def _fetch_payment(track_id: str) -> dict:
    headers = {
        "merchant_api_key": _api_key(),
        "Content-Type": "application/json",
    }
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(
            f"{OXAPAY_API_BASE}/payment/{track_id}",
            headers=headers,
        ) as response:
            result = await _read_oxapay_json(
                response,
                "verifying the payment",
            )
    if response.status != 200 or _api_status(result) != 200:
        raise RuntimeError(_oxapay_error(result, "Payment verification failed."))
    return result.get("data") or {}


def _decimal(value) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("-1")


def _oxapay_error(result: dict, fallback: str) -> str:
    error = result.get("error")
    if isinstance(error, dict):
        detail = str(error.get("message") or "").strip()
        key = str(error.get("key") or "").strip()
        if detail:
            return f"{key}: {detail}" if key else detail
    return str(result.get("message") or fallback)


def _payment_field(data: dict, snake_case: str, camel_case: str = ""):
    value = data.get(snake_case)
    if value in (None, "") and camel_case:
        value = data.get(camel_case)
    return value


async def _deliver_activation(
    app,
    order_id: str,
    activate: Callable[[object, dict], Awaitable[None]],
) -> None:
    claim_token = secrets.token_hex(16)
    entitlement = await db.claim_payment_activation(order_id, claim_token)
    if not entitlement:
        return
    user_id = int(entitlement["user_id"])
    lock = _ACTIVATION_LOCKS.setdefault(user_id, asyncio.Lock())
    try:
        async with lock:
            # Another order for this user may have finalized while this older
            # delivery was waiting. Always activate the canonical latest row.
            current = await db.get_current_payment_entitlement(user_id)
            if not current:
                raise RuntimeError("Canonical paid entitlement is unavailable.")
            await activate(app, current)
            if not await db.mark_payment_activated(order_id, claim_token):
                raise RuntimeError("Could not mark payment activation delivered.")
    except Exception:
        await db.release_payment_activation(order_id, claim_token)
        raise


async def _process_callback(
    app,
    callback_data: dict,
    activate: Callable[[object, dict], Awaitable[None]],
    trusted_callback: bool = False,
) -> None:
    data = callback_data.get("data") if isinstance(callback_data.get("data"), dict) else callback_data
    track_id = str(_payment_field(data, "track_id", "trackId") or "").strip()
    order_id = str(_payment_field(data, "order_id", "orderId") or "").strip()
    if not track_id or not order_id:
        return

    callback_status = str(data.get("status") or "").strip().lower()
    if trusted_callback and callback_status not in SUCCESS_STATUSES:
        return

    # A callback reaching this trusted path has already passed OxaPay's
    # raw-body HMAC verification. Use it immediately when it contains all
    # fields required to bind the payment to the stored order. Reconciliation
    # uses OxaPay's read API when a callback was missed.
    verified = data if trusted_callback else {}
    required_callback_fields = (
        _payment_field(data, "track_id", "trackId"),
        _payment_field(data, "order_id", "orderId"),
        data.get("status"),
        data.get("currency"),
        data.get("amount"),
    )
    if not trusted_callback or any(value in (None, "") for value in required_callback_fields):
        verified = await _fetch_payment(track_id)

    verified_status = str(verified.get("status") or "").strip().lower()
    if verified_status not in SUCCESS_STATUSES:
        return
    if str(_payment_field(verified, "track_id", "trackId") or "").strip() != track_id:
        raise RuntimeError("OxaPay track ID verification failed.")
    if str(_payment_field(verified, "order_id", "orderId") or "").strip() != order_id:
        raise RuntimeError("OxaPay order ID verification failed.")

    order = await db.get_payment_order(order_id)
    if not order:
        raise RuntimeError("Unknown OxaPay order.")
    if order["status"] == "paid":
        await _deliver_activation(app, order_id, activate)
        return
    if str(order.get("track_id") or "") != track_id:
        raise RuntimeError("Stored OxaPay track ID does not match.")
    if str(verified.get("currency") or "").upper() != str(order["currency"]).upper():
        raise RuntimeError("OxaPay payment currency does not match the order.")
    verified_amount = _decimal(verified.get("amount"))
    expected_amount = _decimal(order["expected_amount"])
    if (
        not verified_amount.is_finite()
        or not expected_amount.is_finite()
        or expected_amount <= 0
        or verified_amount < expected_amount
    ):
        raise RuntimeError("OxaPay payment amount is below the order amount.")

    entitlement = await db.finalize_paid_order(order_id, track_id)
    if not entitlement:
        return
    await _deliver_activation(app, order_id, activate)


async def _reconcile_pending(
    telegram_app,
    activate: Callable[[object, dict], Awaitable[None]],
) -> None:
    """Recover paid orders when a webhook is delayed, lost, or raced."""
    delay = 3
    while True:
        try:
            await asyncio.sleep(delay)
            delay = 2
            pending = await db.list_pending_payment_orders(limit=100)
            for order in pending:
                try:
                    await _process_callback(
                        telegram_app,
                        {
                            "track_id": order["track_id"],
                            "order_id": order["order_id"],
                        },
                        activate,
                        trusted_callback=False,
                    )
                except Exception as exc:
                    logger.warning(
                        "[OXAPAY] Pending order %s reconciliation deferred: %s",
                        order["order_id"],
                        exc,
                    )
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("[OXAPAY] Pending-payment reconciliation failed.")
            await asyncio.sleep(2)


async def _webhook(request: web.Request) -> web.Response:
    raw_body = await request.read()
    received = request.headers.get("HMAC", "").strip().lower()
    expected = hmac.new(
        _api_key().encode("utf-8"),
        raw_body,
        hashlib.sha512,
    ).hexdigest()
    if not received or not hmac.compare_digest(received, expected):
        return web.Response(text="Invalid HMAC", status=401)
    try:
        payload = json.loads(raw_body.decode("utf-8"))
        await _process_callback(
            request.app["telegram_app"],
            payload,
            request.app["activate_payment"],
            trusted_callback=True,
        )
    except (UnicodeDecodeError, json.JSONDecodeError):
        return web.Response(text="Invalid JSON", status=400)
    except Exception:
        logger.exception("[OXAPAY] Callback processing failed.")
        return web.Response(text="Temporary failure", status=500)
    return web.Response(text="OK", status=200)


async def _health(_request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "service": "oxapay-webhook"})


async def start_webhook(
    telegram_app,
    activate: Callable[[object, dict], Awaitable[None]],
) -> None:
    if not _api_key():
        logger.warning("[OXAPAY] Disabled: OXAPAY_MERCHANT_API_KEY is missing.")
        return

    web_app = web.Application(client_max_size=64 * 1024)
    web_app["telegram_app"] = telegram_app
    web_app["activate_payment"] = activate
    web_app.router.add_post("/oxapay/webhook", _webhook)
    web_app.router.add_get("/health", _health)

    runner = web.AppRunner(web_app, access_log=None)
    await runner.setup()
    port = int(os.environ.get("PORT", "8080"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    telegram_app.bot_data["_oxapay_runner"] = runner
    telegram_app.bot_data["_oxapay_reconcile_task"] = asyncio.create_task(
        _reconcile_pending(telegram_app, activate),
        name="oxapay-payment-reconciliation",
    )
    logger.info("[OXAPAY] Webhook listening on port %s.", port)


async def stop_webhook(telegram_app) -> None:
    task = telegram_app.bot_data.pop("_oxapay_reconcile_task", None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    runner = telegram_app.bot_data.pop("_oxapay_runner", None)
    if runner:
        await runner.cleanup()
