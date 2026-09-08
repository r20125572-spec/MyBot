import asyncio
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch


BOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT_DIR))

import payments


class InMemoryPaymentDatabase:
    """Small transactional model of the payment database contract."""

    def __init__(self, orders):
        self.orders = {
            order["order_id"]: {
                "status": "pending",
                "activated_at": None,
                "activation_claimed_at": None,
                "activation_claim_token": None,
                **order,
            }
            for order in orders
        }
        self.entitlements = {}
        self.now = 1_000_000.0
        self.finalize_lock = asyncio.Lock()
        self.finalization_grants = 0

    async def get_payment_order(self, order_id):
        return dict(self.orders[order_id])

    async def finalize_paid_order(self, order_id, track_id):
        async with self.finalize_lock:
            await asyncio.sleep(0)
            order = self.orders[order_id]
            if order["track_id"] != track_id:
                raise RuntimeError("track mismatch")
            if order["status"] == "paid":
                return None

            current = self.entitlements.get(order["user_id"])
            expiry = max(self.now, current["expires"] if current else 0)
            expiry += order["days"] * 86_400

            # Purchase creation time, not callback arrival time, determines the
            # canonical plan when purchases complete out of order.
            is_latest = current is None or order["created_at"] >= current["created_at"]
            canonical = {
                "user_id": order["user_id"],
                "plan": order["plan"] if is_latest else current["plan"],
                "expires": expiry,
                "order_id": order_id if is_latest else current["order_id"],
                "days": order["days"] if is_latest else current["days"],
                "created_at": max(
                    order["created_at"],
                    current["created_at"] if current else order["created_at"],
                ),
            }
            self.entitlements[order["user_id"]] = canonical
            order["status"] = "paid"
            self.finalization_grants += 1
            return {**order, "expires": expiry}

    async def claim_payment_activation(self, order_id, claim_token, lease_seconds=120):
        order = self.orders[order_id]
        stale_before = self.now - max(30, lease_seconds)
        claim_is_available = (
            order["activation_claimed_at"] is None
            or order["activation_claimed_at"] < stale_before
        )
        if (
            order["status"] != "paid"
            or order["activated_at"] is not None
            or not claim_is_available
        ):
            return None
        order["activation_claimed_at"] = self.now
        order["activation_claim_token"] = claim_token
        return {**order, "expires": self.entitlements[order["user_id"]]["expires"]}

    async def get_current_payment_entitlement(self, user_id):
        entitlement = self.entitlements.get(user_id)
        return dict(entitlement) if entitlement else None

    async def mark_payment_activated(self, order_id, claim_token):
        order = self.orders[order_id]
        if (
            order["activated_at"] is not None
            or order["activation_claim_token"] != claim_token
        ):
            return False
        order["activated_at"] = self.now
        order["activation_claimed_at"] = None
        order["activation_claim_token"] = None
        return True

    async def release_payment_activation(self, order_id, claim_token):
        order = self.orders[order_id]
        if (
            order["activated_at"] is None
            and order["activation_claim_token"] == claim_token
        ):
            order["activation_claimed_at"] = None
            order["activation_claim_token"] = None


def order(order_id, track_id, plan, days, created_at, user_id=42):
    return {
        "order_id": order_id,
        "track_id": track_id,
        "user_id": user_id,
        "plan": plan,
        "days": days,
        "created_at": created_at,
        "currency": "USD",
        "expected_amount": "10.00",
    }


def paid_callback(order_id, track_id):
    return {
        "order_id": order_id,
        "track_id": track_id,
        "status": "paid",
        "currency": "USD",
        "amount": "10.00",
    }


class PaymentReliabilityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        payments._ACTIVATION_LOCKS.clear()

    @contextmanager
    def use_database(self, database):
        with patch.object(payments, "db", database):
            yield

    async def test_webhook_and_reconciliation_race_grants_entitlement_once(self):
        database = InMemoryPaymentDatabase(
            [order("order-1", "track-1", "ELITE", 15, created_at=10)]
        )
        activations = []

        async def activate(_app, entitlement):
            activations.append(entitlement)

        with self.use_database(database):
            await asyncio.gather(
                payments._process_callback(
                    object(),
                    paid_callback("order-1", "track-1"),
                    activate,
                    trusted_callback=True,
                ),
                payments._process_callback(
                    object(),
                    paid_callback("order-1", "track-1"),
                    activate,
                    trusted_callback=True,
                ),
            )

        self.assertEqual(database.finalization_grants, 1)
        self.assertEqual(database.entitlements[42]["expires"], 1_000_000 + 15 * 86_400)
        self.assertEqual(len(activations), 1)

    async def test_stale_activation_claim_can_be_recovered(self):
        database = InMemoryPaymentDatabase(
            [order("order-1", "track-1", "ELITE", 15, created_at=10)]
        )
        await database.finalize_paid_order("order-1", "track-1")
        database.orders["order-1"]["activation_claimed_at"] = database.now - 121
        database.orders["order-1"]["activation_claim_token"] = "dead-worker"
        activations = []

        with self.use_database(database):
            await payments._deliver_activation(
                object(), "order-1", lambda _app, item: _append(activations, item)
            )

        self.assertEqual(len(activations), 1)
        self.assertIsNotNone(database.orders["order-1"]["activated_at"])

    async def test_activation_failure_releases_claim_and_retry_succeeds(self):
        database = InMemoryPaymentDatabase(
            [order("order-1", "track-1", "ROOT", 30, created_at=10)]
        )
        attempts = 0

        async def activate(_app, _entitlement):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("temporary Telegram failure")

        with self.use_database(database):
            with self.assertRaisesRegex(RuntimeError, "temporary Telegram failure"):
                await payments._process_callback(
                    object(),
                    paid_callback("order-1", "track-1"),
                    activate,
                    trusted_callback=True,
                )
            self.assertIsNone(database.orders["order-1"]["activation_claim_token"])

            await payments._process_callback(
                object(),
                paid_callback("order-1", "track-1"),
                activate,
                trusted_callback=True,
            )

        self.assertEqual(attempts, 2)
        self.assertEqual(database.finalization_grants, 1)
        self.assertIsNotNone(database.orders["order-1"]["activated_at"])

    async def test_temporary_oxapay_response_retries_until_success(self):
        attempts = 0

        async def operation():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise payments.OxaPayTemporaryResponseError("temporary HTML")
            return {"status": 200, "data": {"track_id": "track-1"}}

        with patch.object(payments.asyncio, "sleep", return_value=None):
            result = await payments._retry_temporary(
                operation,
                name="test payment creation",
                attempts=4,
            )

        self.assertEqual(attempts, 3)
        self.assertEqual(result["data"]["track_id"], "track-1")

    async def test_parsed_merchant_error_is_not_retried(self):
        attempts = 0

        async def operation():
            nonlocal attempts
            attempts += 1
            raise RuntimeError("merchant_api_key: invalid")

        with self.assertRaisesRegex(RuntimeError, "merchant_api_key"):
            await payments._retry_temporary(
                operation,
                name="test payment creation",
                attempts=4,
            )

        self.assertEqual(attempts, 1)

    async def test_out_of_order_purchases_add_time_once_and_keep_newest_plan(self):
        database = InMemoryPaymentDatabase(
            [
                order("older", "track-old", "CORE", 7, created_at=10),
                order("newer", "track-new", "ROOT", 30, created_at=20),
            ]
        )
        activations = []

        async def activate(_app, entitlement):
            activations.append(entitlement)

        with self.use_database(database):
            await payments._process_callback(
                object(),
                paid_callback("newer", "track-new"),
                activate,
                trusted_callback=True,
            )
            await payments._process_callback(
                object(),
                paid_callback("older", "track-old"),
                activate,
                trusted_callback=True,
            )
            # Duplicate delivery of each paid callback must be a no-op.
            await payments._process_callback(
                object(),
                paid_callback("older", "track-old"),
                activate,
                trusted_callback=True,
            )
            await payments._process_callback(
                object(),
                paid_callback("newer", "track-new"),
                activate,
                trusted_callback=True,
            )

        entitlement = database.entitlements[42]
        self.assertEqual(database.finalization_grants, 2)
        self.assertEqual(entitlement["expires"], 1_000_000 + 37 * 86_400)
        self.assertEqual(entitlement["plan"], "ROOT")
        self.assertEqual(entitlement["order_id"], "newer")
        self.assertTrue(all(item["plan"] == "ROOT" for item in activations))


async def _append(items, item):
    items.append(item)
