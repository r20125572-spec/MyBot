"""Secure OxaPay invoices and webhook processing for the Telegram bot."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
from decimal import Decimal, InvalidOperation
from typing import Awaitable, Callable

import aiohttp
from aiohttp import web

import database as db

logger = logging.getLogger(__name__)

OXAPAY_API_BASE = "https://api.oxapay.com/v1"
SUCCESS_STATUSES = frozenset({"paid", "completed", "complete", "confirmed"})

PLANS = {
    "pay1d": {"name": "Core", "plan": "CORE", "days": 1, "price": Decimal("1.50")},
    "pay10": {"name": "Core", "plan": "CORE", "days": 7, "price": Decimal("8.00")},
    "pay15": {"name": "Elite", "plan": "ELITE", "days": 15, "price": Decimal("12.00")},
    "pay30": {"name": "Root", "plan": "ROOT", "days": 30, "price": Decimal("25.00")},
}


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
    if os.environ.get("OXAPAY_SANDBOX", "").strip().lower() not in {"true", "false"}:
        return "OXAPAY_SANDBOX must be set explicitly to true or false."
    if not db.is_connected():
        return "PostgreSQL is unavailable; secure payment orders cannot be created."
    return None


async def create_invoice(user_id: int, selection: str) -> dict:
    error = configuration_error()
    if error:
        raise RuntimeError(error)
    plan = PLANS.get(selection)
    if not plan:
        raise ValueError("Unknown payment plan.")

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
        "amount": str(plan["price"]),
        "currency": "USD",
        "lifetime": 60,
        "fee_paid_by_payer": 1,
        "under_paid_coverage": 0,
        "mixed_payment": False,
        "callback_url": _callback_url(),
        "order_id": order_id,
        "description": f"{plan['name']} plan for Telegram user {user_id}",
        "thanks_message": "Payment received. Your plan will activate automatically.",
        "sandbox": _sandbox_enabled(),
    }
    headers = {
        "merchant_api_key": _api_key(),
        "Content-Type": "application/json",
    }

    try:
        timeout = aiohttp.ClientTimeout(
            total=15,
            connect=5,
            sock_connect=5,
            sock_read=10,
        )
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{OXAPAY_API_BASE}/payment/invoice",
                headers=headers,
                json=payload,
            ) as response:
                result = await response.json(content_type=None)
                if response.status != 200 or int(result.get("status", 0)) != 200:
                    message = result.get("message") or "OxaPay rejected the invoice."
                    raise RuntimeError(str(message))

        data = result.get("data") or {}
        track_id = str(data.get("track_id") or "").strip()
        payment_url = str(data.get("payment_url") or "").strip()
        if not track_id or not payment_url.startswith("https://"):
            raise RuntimeError("OxaPay returned incomplete invoice information.")

        saved = await db.attach_payment_invoice(order_id, track_id, payment_url)
        if not saved:
            raise RuntimeError("Could not save the OxaPay invoice.")

        return {
            "order_id": order_id,
            "track_id": track_id,
            "payment_url": payment_url,
            **plan,
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
            result = await response.json(content_type=None)
    if response.status != 200 or int(result.get("status", 0)) != 200:
        raise RuntimeError(result.get("message") or "Payment verification failed.")
    return result.get("data") or {}


def _decimal(value) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("-1")


async def _process_callback(
    app,
    callback_data: dict,
    activate: Callable[[object, dict], Awaitable[None]],
) -> None:
    data = callback_data.get("data") if isinstance(callback_data.get("data"), dict) else callback_data
    track_id = str(data.get("track_id") or "").strip()
    order_id = str(data.get("order_id") or "").strip()
    if not track_id or not order_id:
        return

    # Never grant from callback fields alone. Re-query OxaPay over its API.
    verified = await _fetch_payment(track_id)
    if str(verified.get("status") or "").strip().lower() not in SUCCESS_STATUSES:
        return
    if str(verified.get("track_id") or "").strip() != track_id:
        raise RuntimeError("OxaPay track ID verification failed.")
    if str(verified.get("order_id") or "").strip() != order_id:
        raise RuntimeError("OxaPay order ID verification failed.")

    order = await db.get_payment_order(order_id)
    if not order:
        raise RuntimeError("Unknown OxaPay order.")
    if order["status"] == "paid":
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
    await activate(app, entitlement)


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
    logger.info("[OXAPAY] Webhook listening on port %s.", port)


async def stop_webhook(telegram_app) -> None:
    runner = telegram_app.bot_data.pop("_oxapay_runner", None)
    if runner:
        await runner.cleanup()
