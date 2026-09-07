"""
database.py  —  Railway PostgreSQL persistence for premium + user stats.
════════════════════════════════════════════════════════════════════════════

main.py needs only THREE lines:

    import database as db                  # top of file
    await db.attach(app)                   # end of _post_init
    await db.close_db(app.bot_data)        # inside _post_shutdown

After every plan grant/remove:
    await db.save_premium_now(context.bot_data.get("user_data", {}))

After every CHARGED card (in sh.py, both places where total_charged increments):
    await db.save_user_stats_now(user_id, ud)

Three tables:
  • premium_users  — plan / expires / receipt (unchanged)
  • user_stats     — total_charged, name, username, joined, last_active
                     for EVERY user (not just premium)
  • bot_bans       — durable bot-wide access bans with audit metadata
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time

logger = logging.getLogger(__name__)

# ── Connection pool ───────────────────────────────────────────────────────────
_pool = None   # asyncpg.Pool | None


def _find_db_url() -> str:
    """
    Return the database URL from protected hosting environment variables.
    Railway can provide DATABASE_URL via a Postgres variable reference, while
    DATABASE_PRIVATE_URL is accepted as a direct fallback.
    """
    return (
        os.environ.get("DATABASE_URL", "").strip()
        or os.environ.get("DATABASE_PRIVATE_URL", "").strip()
    )


DATABASE_URL: str = _find_db_url()
PREMIUM_FILE: str = os.environ.get("PREMIUM_FILE", "premium_users.json")

# ── Schema ────────────────────────────────────────────────────────────────────
_CREATE_PREMIUM_TABLE = """
CREATE TABLE IF NOT EXISTS premium_users (
    user_id      BIGINT           PRIMARY KEY,
    plan         TEXT             NOT NULL DEFAULT 'TRIAL',
    expires      DOUBLE PRECISION NOT NULL DEFAULT 0,
    name         TEXT             NOT NULL DEFAULT '',
    username     TEXT             NOT NULL DEFAULT '',
    last_receipt TEXT             NOT NULL DEFAULT '',
    granted_at   DOUBLE PRECISION NOT NULL DEFAULT 0
);
"""

# NEW: stores total_charged and all user stats — persists across redeploys
_CREATE_STATS_TABLE = """
CREATE TABLE IF NOT EXISTS user_stats (
    user_id       BIGINT           PRIMARY KEY,
    total_charged BIGINT           NOT NULL DEFAULT 0,
    name          TEXT             NOT NULL DEFAULT '',
    first_name    TEXT             NOT NULL DEFAULT '',
    username      TEXT             NOT NULL DEFAULT '',
    joined        TEXT             NOT NULL DEFAULT '',
    last_active   TEXT             NOT NULL DEFAULT '',
    total_checks  BIGINT           NOT NULL DEFAULT 0,
    approved_checks BIGINT         NOT NULL DEFAULT 0,
    declined_checks BIGINT         NOT NULL DEFAULT 0,
    total_refs    BIGINT           NOT NULL DEFAULT 0,
    hide_identity BOOLEAN          NOT NULL DEFAULT FALSE,
    daily_check_date TEXT           NOT NULL DEFAULT '',
    daily_checks    BIGINT          NOT NULL DEFAULT 0,
    updated_at    DOUBLE PRECISION NOT NULL DEFAULT 0
);
"""

_STATS_MIGRATIONS = (
    "ALTER TABLE user_stats ADD COLUMN IF NOT EXISTS hide_identity "
    "BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE user_stats ADD COLUMN IF NOT EXISTS daily_check_date "
    "TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE user_stats ADD COLUMN IF NOT EXISTS daily_checks "
    "BIGINT NOT NULL DEFAULT 0",
)

_CREATE_BANS_TABLE = """
CREATE TABLE IF NOT EXISTS bot_bans (
    user_id      BIGINT           PRIMARY KEY,
    active       BOOLEAN          NOT NULL DEFAULT TRUE,
    reason       TEXT             NOT NULL DEFAULT '',
    moderator_id BIGINT,
    banned_at    DOUBLE PRECISION NOT NULL DEFAULT 0,
    updated_at   DOUBLE PRECISION NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS bot_bans_active_idx ON bot_bans (active);
"""

_CREATE_PAYMENT_ORDERS_TABLE = """
CREATE TABLE IF NOT EXISTS payment_orders (
    order_id        TEXT             PRIMARY KEY,
    user_id         BIGINT           NOT NULL,
    plan            TEXT             NOT NULL,
    days            INTEGER          NOT NULL CHECK (days > 0),
    expected_amount NUMERIC(12, 2)   NOT NULL CHECK (expected_amount > 0),
    currency        TEXT             NOT NULL DEFAULT 'USD',
    status          TEXT             NOT NULL DEFAULT 'pending',
    track_id        TEXT,
    payment_url     TEXT             NOT NULL DEFAULT '',
    error           TEXT             NOT NULL DEFAULT '',
    created_at      DOUBLE PRECISION NOT NULL,
    updated_at      DOUBLE PRECISION NOT NULL,
    paid_at         DOUBLE PRECISION,
    activated_at    DOUBLE PRECISION,
    activation_claimed_at DOUBLE PRECISION,
    activation_claim_token TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS payment_orders_track_id_idx
    ON payment_orders (track_id) WHERE track_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS payment_orders_user_idx
    ON payment_orders (user_id, created_at DESC);
"""

_PAYMENT_MIGRATIONS = (
    "ALTER TABLE payment_orders ADD COLUMN IF NOT EXISTS activated_at DOUBLE PRECISION",
    "ALTER TABLE payment_orders ADD COLUMN IF NOT EXISTS activation_claimed_at DOUBLE PRECISION",
    "ALTER TABLE payment_orders ADD COLUMN IF NOT EXISTS activation_claim_token TEXT",
)


def _strip_sslmode(url: str) -> str:
    url = re.sub(r'[?&]sslmode=[^&]*', '', url)
    url = re.sub(r'\?$', '', url)
    return url


# ── Connection ────────────────────────────────────────────────────────────────
async def _connect() -> bool:
    global _pool
    if not DATABASE_URL:
        logger.warning("[DB] ⚠️  No DATABASE_URL found — "
                       "user stats will NOT persist across redeploys!")
        return False

    import asyncpg, ssl as _ssl

    _unverified = _ssl.create_default_context()
    _unverified.check_hostname = False
    _unverified.verify_mode    = _ssl.CERT_NONE

    clean_url = _strip_sslmode(DATABASE_URL)

    if "railway.internal" in clean_url:
        ssl_candidates = [False]
    else:
        ssl_candidates = [False, _unverified, True]

    last_exc = None
    for ssl_opt in ssl_candidates:
        pool = None
        try:
            pool = await asyncpg.create_pool(
                clean_url,
                ssl=ssl_opt,
                min_size=1,
                max_size=5,
                command_timeout=30,
            )
            async with pool.acquire() as conn:
                await conn.execute(_CREATE_PREMIUM_TABLE)
                await conn.execute(_CREATE_STATS_TABLE)
                for migration in _STATS_MIGRATIONS:
                    await conn.execute(migration)
                await conn.execute(_CREATE_BANS_TABLE)
                await conn.execute(_CREATE_PAYMENT_ORDERS_TABLE)
                for migration in _PAYMENT_MIGRATIONS:
                    await conn.execute(migration)
            _pool = pool
            label = "none" if ssl_opt is False else (
                "unverified" if ssl_opt is _unverified else "verified"
            )
            logger.info(f"[DB] ✅ PostgreSQL connected (ssl={label}) — "
                        "premium_users + user_stats + bot_bans + payment_orders tables ready.")
            return True
        except Exception as exc:
            label = "none" if ssl_opt is False else (
                "unverified" if ssl_opt is _unverified else "verified"
            )
            logger.warning(f"[DB] ssl={label} attempt failed: {exc}")
            last_exc = exc
            if pool:
                try: await pool.close()
                except Exception: pass

    logger.error(f"[DB] ❌ All SSL attempts failed. Last: {last_exc}")
    _pool = None
    return False


# ══════════════════════════════════════════════════════════════════════════════
#  PREMIUM USERS  (plan / expires — unchanged logic)
# ══════════════════════════════════════════════════════════════════════════════

async def _load_premium_from_db(bot_data: dict) -> int:
    if not _pool:
        return 0
    now = time.time()
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM premium_users WHERE expires > $1", now
            )
    except Exception as exc:
        logger.warning(f"[DB] load premium error: {exc}")
        return 0

    user_data = bot_data.setdefault("user_data", {})
    for row in rows:
        uid_str = str(row["user_id"])
        ud      = user_data.setdefault(uid_str, {})
        ud["plan"]    = row["plan"]
        ud["expires"] = row["expires"]
        if row["name"]:         ud["name"]         = row["name"]
        if row["username"]:     ud["username"]     = row["username"]
        if row["last_receipt"]: ud["last_receipt"] = row["last_receipt"]
        if row["granted_at"]:   ud.setdefault("granted_at", row["granted_at"])

    logger.info(f"[DB] ✅ Restored {len(rows)} premium user(s) from PostgreSQL.")
    return len(rows)


_PREMIUM_UPSERT = """
    INSERT INTO premium_users
        (user_id, plan, expires, name, username, last_receipt, granted_at)
    VALUES ($1,$2,$3,$4,$5,$6,$7)
    ON CONFLICT (user_id) DO UPDATE SET
        plan = CASE
            WHEN EXCLUDED.granted_at >= premium_users.granted_at
            THEN EXCLUDED.plan ELSE premium_users.plan
        END,
        expires = GREATEST(premium_users.expires, EXCLUDED.expires),
        name = CASE
            WHEN EXCLUDED.name <> '' THEN EXCLUDED.name ELSE premium_users.name
        END,
        username = CASE
            WHEN EXCLUDED.username <> '' THEN EXCLUDED.username ELSE premium_users.username
        END,
        last_receipt = CASE
            WHEN EXCLUDED.granted_at >= premium_users.granted_at
            THEN EXCLUDED.last_receipt ELSE premium_users.last_receipt
        END,
        granted_at = GREATEST(premium_users.granted_at, EXCLUDED.granted_at)
"""

async def _upsert_premium_records(records: list) -> int:
    if not _pool or not records:
        return 0
    for attempt in (1, 2):
        try:
            async with _pool.acquire() as conn:
                await conn.executemany(_PREMIUM_UPSERT, records)
            return len(records)
        except Exception as exc:
            logger.warning(f"[DB] premium upsert attempt {attempt}/2 failed: {exc}")
            if attempt == 1:
                await asyncio.sleep(1)
    reconnected = await _connect()
    if reconnected:
        try:
            async with _pool.acquire() as conn:
                await conn.executemany(_PREMIUM_UPSERT, records)
            return len(records)
        except Exception as exc:
            logger.error(f"[DB] ❌ Premium upsert failed after reconnect: {exc}")
    return 0


async def save_premium_now(user_data: dict) -> int:
    """
    Immediately upsert ALL active premium users.
    Call after every plan grant or removal.
    (Was: save_all_now — old name still works via alias below.)
    """
    if not _pool:
        return 0
    now     = time.time()
    records = []
    for uid_str, ud in user_data.items():
        plan    = ud.get("plan", "TRIAL").upper()
        expires = ud.get("expires", 0)
        if plan == "TRIAL" or expires <= now:
            continue
        try:
            uid = int(uid_str)
        except ValueError:
            continue
        records.append((
            uid, plan, expires,
            ud.get("name", ""),
            ud.get("username", ""),
            ud.get("last_receipt", ""),
            ud.get("granted_at", 0),
        ))
    saved = await _upsert_premium_records(records)
    if saved:
        logger.info(f"[DB] ✅ Instant save: {saved} premium user(s) written.")
    return saved


# Keep old name for backward compatibility with existing main.py calls
save_all_now = save_premium_now


async def save_user_now(user_id: int, ud: dict) -> bool:
    """Immediately upsert ONE user's premium record."""
    if not _pool:
        return False
    now     = time.time()
    plan    = ud.get("plan", "TRIAL").upper()
    expires = ud.get("expires", 0)
    if plan == "TRIAL" or expires <= now:
        try:
            async with _pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM premium_users WHERE user_id = $1", user_id
                )
            logger.info(f"[DB] Removed user {user_id} from premium_users.")
            return True
        except Exception as exc:
            logger.warning(f"[DB] delete error uid={user_id}: {exc}")
            return False

    saved = await _upsert_premium_records([(
        user_id, plan, expires,
        ud.get("name", ""),
        ud.get("username", ""),
        ud.get("last_receipt", ""),
        ud.get("granted_at", 0),
    )])
    return saved > 0


# ══════════════════════════════════════════════════════════════════════════════
#  OXAPAY PAYMENT ORDERS
# ══════════════════════════════════════════════════════════════════════════════

async def create_payment_order(order_id: str, user_id: int, plan: str, days: int,
                               expected_amount, currency: str = "USD") -> bool:
    if not _pool:
        return False
    now = time.time()
    try:
        async with _pool.acquire() as conn:
            result = await conn.execute(
                """
                INSERT INTO payment_orders
                    (order_id, user_id, plan, days, expected_amount, currency,
                     status, created_at, updated_at)
                VALUES ($1,$2,$3,$4,$5,$6,'pending',$7,$7)
                ON CONFLICT (order_id) DO NOTHING
                """,
                order_id, int(user_id), plan.upper(), int(days),
                expected_amount, currency.upper(), now,
            )
        return result == "INSERT 0 1"
    except Exception as exc:
        logger.error("[DB] create payment order failed: %s", exc)
        return False


async def attach_payment_invoice(order_id: str, track_id: str,
                                 payment_url: str) -> bool:
    if not _pool:
        return False
    try:
        async with _pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE payment_orders
                SET track_id=$2, payment_url=$3, updated_at=$4
                WHERE order_id=$1 AND status='pending'
                """,
                order_id, track_id, payment_url, time.time(),
            )
        return result == "UPDATE 1"
    except Exception as exc:
        logger.error("[DB] attach payment invoice failed: %s", exc)
        return False


async def fail_payment_order(order_id: str, error: str) -> None:
    if not _pool:
        return
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE payment_orders
                SET status='failed', error=$2, updated_at=$3
                WHERE order_id=$1 AND status='pending'
                """,
                order_id, str(error)[:500], time.time(),
            )
    except Exception as exc:
        logger.warning("[DB] mark payment failed error: %s", exc)


async def get_payment_order(order_id: str):
    if not _pool:
        return None
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM payment_orders WHERE order_id=$1",
                order_id,
            )
        return dict(row) if row else None
    except Exception as exc:
        logger.error("[DB] get payment order failed: %s", exc)
        return None


async def list_pending_payment_orders(limit: int = 100) -> list[dict]:
    """Return recent orders needing payment or activation reconciliation."""
    if not _pool:
        return []
    safe_limit = max(1, min(int(limit), 500))
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM payment_orders
                WHERE track_id IS NOT NULL
                  AND (
                      (status='pending' AND created_at >= $1)
                      OR (status='paid' AND activated_at IS NULL)
                  )
                ORDER BY created_at ASC
                LIMIT $2
                """,
                time.time() - (3 * 86400),
                safe_limit,
            )
        return [dict(row) for row in rows]
    except Exception as exc:
        logger.warning("[DB] list pending payment orders failed: %s", exc)
        return []


async def claim_payment_activation(order_id: str, claim_token: str,
                                   lease_seconds: int = 120):
    """Lease one paid activation to exactly one delivery worker."""
    if not _pool:
        return None
    now = time.time()
    stale_before = now - max(30, int(lease_seconds))
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                WITH claimed AS (
                    UPDATE payment_orders
                    SET activation_claimed_at=$3,
                        activation_claim_token=$2,
                        updated_at=$3
                    WHERE order_id=$1
                      AND status='paid'
                      AND activated_at IS NULL
                      AND (
                          activation_claimed_at IS NULL
                          OR activation_claimed_at < $4
                      )
                    RETURNING *
                )
                SELECT claimed.*, pu.expires
                FROM claimed
                JOIN premium_users pu ON pu.user_id = claimed.user_id
                """,
                order_id, claim_token, now, stale_before,
            )
        return dict(row) if row else None
    except Exception as exc:
        logger.warning("[DB] claim payment activation failed: %s", exc)
        return None


async def get_current_payment_entitlement(user_id: int):
    """Load the canonical latest paid entitlement for live activation."""
    if not _pool:
        return None
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT pu.user_id, pu.plan, pu.expires, pu.granted_at,
                       pu.last_receipt AS order_id,
                       COALESCE(po.days, 0) AS days
                FROM premium_users pu
                LEFT JOIN payment_orders po
                  ON po.order_id = pu.last_receipt
                 AND po.status = 'paid'
                WHERE pu.user_id=$1
                """,
                int(user_id),
            )
        return dict(row) if row else None
    except Exception as exc:
        logger.warning("[DB] get current payment entitlement failed: %s", exc)
        return None


async def mark_payment_activated(order_id: str, claim_token: str) -> bool:
    if not _pool:
        return False
    try:
        async with _pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE payment_orders
                SET activated_at=$3, updated_at=$3,
                    activation_claimed_at=NULL,
                    activation_claim_token=NULL
                WHERE order_id=$1
                  AND status='paid'
                  AND activated_at IS NULL
                  AND activation_claim_token=$2
                """,
                order_id, claim_token, time.time(),
            )
        return result == "UPDATE 1"
    except Exception as exc:
        logger.warning("[DB] mark payment activated failed: %s", exc)
        return False


async def release_payment_activation(order_id: str, claim_token: str) -> None:
    if not _pool:
        return
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE payment_orders
                SET activation_claimed_at=NULL,
                    activation_claim_token=NULL,
                    updated_at=$3
                WHERE order_id=$1
                  AND activated_at IS NULL
                  AND activation_claim_token=$2
                """,
                order_id, claim_token, time.time(),
            )
    except Exception as exc:
        logger.warning("[DB] release payment activation failed: %s", exc)


async def finalize_paid_order(order_id: str, track_id: str):
    """Atomically mark an order paid and persist its premium entitlement."""
    if not _pool:
        raise RuntimeError("PostgreSQL is unavailable.")
    try:
        async with _pool.acquire() as conn:
            async with conn.transaction():
                order = await conn.fetchrow(
                    """
                    SELECT * FROM payment_orders
                    WHERE order_id=$1 AND track_id=$2
                    FOR UPDATE
                    """,
                    order_id, track_id,
                )
                if not order:
                    raise RuntimeError("Payment order was not found.")
                if order["status"] == "paid":
                    return None
                if order["status"] != "pending":
                    raise RuntimeError("Payment order is not available for finalization.")

                # Serializes all grants for this user, including the first grant
                # where no premium_users row exists yet.
                await conn.execute(
                    "SELECT pg_advisory_xact_lock($1)",
                    order["user_id"],
                )
                # Capture the version timestamp after serialization so the
                # last finalized purchase also owns the final plan/receipt.
                now = time.time()
                current = await conn.fetchrow(
                    "SELECT * FROM premium_users WHERE user_id=$1 FOR UPDATE",
                    order["user_id"],
                )
                current_expiry = float(current["expires"]) if current else 0.0
                expires = max(now, current_expiry) + int(order["days"]) * 86400
                name = str(current["name"]) if current else ""
                username = str(current["username"]) if current else ""
                canonical_plan = order["plan"]
                canonical_receipt = order_id
                if current and current["last_receipt"]:
                    current_purchase = await conn.fetchrow(
                        """
                        SELECT created_at
                        FROM payment_orders
                        WHERE order_id=$1 AND status='paid'
                        """,
                        current["last_receipt"],
                    )
                    if (
                        current_purchase
                        and float(current_purchase["created_at"])
                        > float(order["created_at"])
                    ):
                        canonical_plan = current["plan"]
                        canonical_receipt = current["last_receipt"]

                await conn.execute(
                    _PREMIUM_UPSERT,
                    order["user_id"], canonical_plan, expires, name, username,
                    canonical_receipt, now,
                )
                updated = await conn.fetchrow(
                    """
                    UPDATE payment_orders
                    SET status='paid', paid_at=$3, updated_at=$3, error=''
                    WHERE order_id=$1 AND track_id=$2 AND status='pending'
                    RETURNING *
                    """,
                    order_id, track_id, now,
                )
                if not updated:
                    raise RuntimeError("Payment order finalization failed.")

        entitlement = dict(updated)
        entitlement["expires"] = expires
        return entitlement
    except Exception:
        logger.exception("[DB] atomic payment finalization failed.")
        raise


# ══════════════════════════════════════════════════════════════════════════════
#  USER STATS  (total_charged + activity — NEW, survives redeploys)
# ══════════════════════════════════════════════════════════════════════════════

_STATS_UPSERT = """
    INSERT INTO user_stats
        (user_id, total_charged, name, first_name, username,
         joined, last_active, total_checks, approved_checks,
         declined_checks, total_refs, hide_identity, daily_check_date,
         daily_checks, updated_at)
    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
    ON CONFLICT (user_id) DO UPDATE SET
        total_charged   = GREATEST(user_stats.total_charged, EXCLUDED.total_charged),
        name            = EXCLUDED.name,
        first_name      = EXCLUDED.first_name,
        username        = EXCLUDED.username,
        last_active     = EXCLUDED.last_active,
        total_checks    = GREATEST(user_stats.total_checks,   EXCLUDED.total_checks),
        approved_checks = GREATEST(user_stats.approved_checks,EXCLUDED.approved_checks),
        declined_checks = GREATEST(user_stats.declined_checks,EXCLUDED.declined_checks),
        total_refs      = GREATEST(user_stats.total_refs,     EXCLUDED.total_refs),
        hide_identity   = EXCLUDED.hide_identity,
        daily_check_date = EXCLUDED.daily_check_date,
        daily_checks    = CASE
            WHEN user_stats.daily_check_date = EXCLUDED.daily_check_date
            THEN GREATEST(user_stats.daily_checks, EXCLUDED.daily_checks)
            ELSE EXCLUDED.daily_checks
        END,
        updated_at      = EXCLUDED.updated_at
"""
# Note: GREATEST() ensures we never overwrite a higher value with a lower one —
# protects against race conditions during mass-check sessions.


async def _upsert_stats_records(records: list) -> int:
    if not _pool or not records:
        return 0
    for attempt in (1, 2):
        try:
            async with _pool.acquire() as conn:
                await conn.executemany(_STATS_UPSERT, records)
            return len(records)
        except Exception as exc:
            logger.warning(f"[DB] stats upsert attempt {attempt}/2 failed: {exc}")
            if attempt == 1:
                await asyncio.sleep(1)
    reconnected = await _connect()
    if reconnected:
        try:
            async with _pool.acquire() as conn:
                await conn.executemany(_STATS_UPSERT, records)
            return len(records)
        except Exception as exc:
            logger.error(f"[DB] ❌ Stats upsert failed after reconnect: {exc}")
    return 0


def _make_stats_record(uid_int: int, ud: dict) -> tuple:
    now = time.time()
    return (
        uid_int,
        ud.get("total_charged", 0),
        ud.get("name", "") or ud.get("first_name", ""),
        ud.get("first_name", ""),
        ud.get("username", ""),
        ud.get("joined", ""),
        ud.get("last_active", ""),
        ud.get("total_checks", 0),
        ud.get("approved_checks", 0),
        ud.get("declined_checks", 0),
        ud.get("total_refs", 0),
        bool(ud.get("hide", False)),
        ud.get("daily_check_date", ""),
        ud.get("daily_checks", 0),
        now,
    )


async def save_user_stats_now(user_id: int, ud: dict) -> bool:
    """
    Immediately save ONE user's stats (total_charged, checks, etc.) to Postgres.

    Call this in sh.py right after every CHARGED card:
        await db.save_user_stats_now(user.id, ud)

    Works even for TRIAL users — this table is NOT gated on premium status.
    """
    if not _pool:
        return False
    saved = await _upsert_stats_records([_make_stats_record(user_id, ud)])
    if saved:
        logger.debug(f"[DB] Stats saved: user {user_id} "
                     f"total_charged={ud.get('total_charged', 0)}")
    return saved > 0


async def save_all_stats_now(user_data: dict) -> int:
    """
    Immediately upsert stats for all users with activity.
    Called by the periodic flush job and on shutdown.
    """
    if not _pool:
        return 0
    records = []
    for uid_str, ud in user_data.items():
        try:
            uid = int(uid_str)
        except ValueError:
            continue
        records.append(_make_stats_record(uid, ud))
    saved = await _upsert_stats_records(records)
    if saved:
        logger.info(f"[DB] ✅ Stats flush: {saved} user(s) written.")
    return saved


async def _load_stats_from_db(bot_data: dict) -> int:
    """
    Load user_stats rows into bot_data["user_data"].
    Called on startup — restores total_charged so /me and /status work immediately.
    """
    if not _pool:
        return 0
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM user_stats")
    except Exception as exc:
        logger.warning(f"[DB] load stats error: {exc}")
        return 0

    user_data = bot_data.setdefault("user_data", {})
    for row in rows:
        uid_str = str(row["user_id"])
        ud      = user_data.setdefault(uid_str, {})

        # Use GREATEST so we never downgrade an in-memory value
        # (shouldn't happen on startup, but be safe)
        db_charged = row["total_charged"] or 0
        mem_charged = ud.get("total_charged", 0)
        ud["total_charged"] = max(db_charged, mem_charged)

        # Restore other stats only if not already set in memory
        if not ud.get("name")        and row["name"]:
            ud["name"]        = row["name"]
        if not ud.get("first_name")  and row["first_name"]:
            ud["first_name"]  = row["first_name"]
        if not ud.get("username")    and row["username"]:
            ud["username"]    = row["username"]
        if not ud.get("joined")      and row["joined"]:
            ud["joined"]      = row["joined"]
        if not ud.get("last_active") and row["last_active"]:
            ud["last_active"] = row["last_active"]
        ud["hide"] = bool(row["hide_identity"])

        db_checks = row["total_checks"] or 0
        ud["total_checks"] = max(ud.get("total_checks", 0), db_checks)

        db_approved = row["approved_checks"] or 0
        ud["approved_checks"] = max(ud.get("approved_checks", 0), db_approved)

        db_declined = row["declined_checks"] or 0
        ud["declined_checks"] = max(ud.get("declined_checks", 0), db_declined)

        db_refs = row["total_refs"] or 0
        ud["total_refs"] = max(ud.get("total_refs", 0), db_refs)

        db_daily_date = row["daily_check_date"] or ""
        if db_daily_date >= ud.get("daily_check_date", ""):
            ud["daily_check_date"] = db_daily_date
            ud["daily_checks"] = row["daily_checks"] or 0

    logger.info(f"[DB] ✅ Restored stats for {len(rows)} user(s) from PostgreSQL "
                f"(total_charged, checks, etc. safe across redeploys).")
    return len(rows)


# ══════════════════════════════════════════════════════════════════════════════
#  DURABLE BOT-WIDE BANS
# ══════════════════════════════════════════════════════════════════════════════

async def _load_bans_from_db(bot_data: dict) -> int:
    if not _pool:
        return 0
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT user_id, reason, moderator_id, banned_at "
                "FROM bot_bans WHERE active = TRUE"
            )
    except Exception as exc:
        logger.warning(f"[DB] load bans error: {exc}")
        return 0

    user_data = bot_data.setdefault("user_data", {})
    for row in rows:
        ud = user_data.setdefault(str(row["user_id"]), {})
        ud["banned"] = True
        ud["ban_reason"] = row["reason"] or ""
        ud["banned_by"] = row["moderator_id"]
        ud["banned_at"] = row["banned_at"] or 0
    logger.info(f"[DB] Restored {len(rows)} active bot ban(s).")
    return len(rows)


async def save_ban_now(
    user_id: int,
    *,
    active: bool,
    reason: str = "",
    moderator_id: int | None = None,
) -> bool:
    """Persist or revoke a bot-wide ban immediately."""
    if not _pool:
        return False
    now = time.time()
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO bot_bans
                    (user_id, active, reason, moderator_id, banned_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $5)
                ON CONFLICT (user_id) DO UPDATE SET
                    active = EXCLUDED.active,
                    reason = EXCLUDED.reason,
                    moderator_id = EXCLUDED.moderator_id,
                    banned_at = CASE
                        WHEN EXCLUDED.active THEN EXCLUDED.banned_at
                        ELSE bot_bans.banned_at
                    END,
                    updated_at = EXCLUDED.updated_at
                """,
                int(user_id), bool(active), reason[:500],
                int(moderator_id) if moderator_id is not None else None, now,
            )
        return True
    except Exception as exc:
        logger.warning(f"[DB] save ban error for {user_id}: {exc}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
#  PTB PERIODIC FLUSH  (every 60 s — saves BOTH tables)
# ══════════════════════════════════════════════════════════════════════════════

async def _flush_job(context) -> None:
    user_data = context.bot_data.get("user_data", {})
    # Save premium plans
    await save_premium_now(user_data)
    # Save user stats (total_charged, checks, etc.)
    await save_all_stats_now(user_data)


# ══════════════════════════════════════════════════════════════════════════════
#  JSON FALLBACK (unchanged)
# ══════════════════════════════════════════════════════════════════════════════

def _read_json() -> dict:
    if not os.path.exists(PREMIUM_FILE):
        return {}
    try:
        with open(PREMIUM_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning(f"[DB] JSON read error: {exc}")
        return {}


# ══════════════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════

async def attach(app) -> None:
    """
    Call once at the end of _post_init.
    Connects to Postgres, restores BOTH premium plans AND user stats,
    then schedules the 60-second periodic flush.
    """
    ok = await _connect()
    if not ok:
        return

    # Restore premium plans first
    restored_premium = await _load_premium_from_db(app.bot_data)

    # Seed from JSON if DB was empty (first-ever deploy)
    if restored_premium == 0:
        saved_json = _read_json()
        if saved_json:
            now       = time.time()
            user_data = app.bot_data.setdefault("user_data", {})
            for uid_str, pdata in saved_json.items():
                plan    = pdata.get("plan", "TRIAL").upper()
                expires = pdata.get("expires", 0)
                if plan == "TRIAL" or expires <= now:
                    continue
                ud = user_data.setdefault(uid_str, {})
                ud.update({
                    "plan":         plan,
                    "expires":      expires,
                    "name":         pdata.get("name", ""),
                    "username":     pdata.get("username", ""),
                    "last_receipt": pdata.get("last_receipt", ""),
                    "granted_at":   pdata.get("granted_at", 0),
                })
            seeded = await save_premium_now(app.bot_data.get("user_data", {}))
            if seeded:
                logger.info(f"[DB] Seeded {seeded} premium user(s) from JSON → Postgres.")

    # Restore user stats and access-control state before serving updates.
    await _load_stats_from_db(app.bot_data)
    await _load_bans_from_db(app.bot_data)

    # Schedule 60-second periodic flush for both tables
    if app.job_queue:
        app.job_queue.run_repeating(
            _flush_job, interval=60, first=30, name="db_premium_flush"
        )
        logger.info("[DB] Periodic flush scheduled (every 60 s) — both tables.")


async def close_db(bot_data: dict | None = None) -> None:
    """
    Call inside _post_shutdown.
    Does a FINAL SAVE of both tables before closing — no data lost on redeploy.
    """
    global _pool
    if not _pool:
        return
    if bot_data:
        user_data = bot_data.get("user_data", {})
        saved_p = await save_premium_now(user_data)
        saved_s = await save_all_stats_now(user_data)
        logger.info(f"[DB] 🔒 Final save on shutdown: "
                    f"{saved_p} premium, {saved_s} stats user(s) saved.")
    else:
        logger.warning("[DB] close_db called without bot_data — skipping final save.")
    try:
        await _pool.close()
    except Exception as exc:
        logger.warning(f"[DB] pool close error: {exc}")
    _pool = None
    logger.info("[DB] PostgreSQL pool closed.")


def is_connected() -> bool:
    return _pool is not None


def status_text() -> str:
    """Human-readable one-line status for /dbstatus command."""
    if not DATABASE_URL:
        return "❌ No DATABASE_URL set — data lost on redeploy!"
    if not _pool:
        return "❌ DATABASE_URL set but connection failed — check Railway logs."
    return "✅ PostgreSQL connected — premium plans + user stats are safe across redeploys."
