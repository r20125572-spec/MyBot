"""
database.py  —  Railway PostgreSQL persistence for premium user data.
════════════════════════════════════════════════════════════════════════
main.py needs only THREE lines:

    import database as db                  # top of file
    await db.attach(app)                   # end of _post_init
    await db.close_db(app.bot_data)        # inside _post_shutdown

IMPORTANT: Every time a plan is granted/removed, call:
    await db.save_all_now(context.bot_data.get("user_data", {}))
This saves instantly instead of waiting for the 60-second flush.

How it works
────────────
• attach()      → connect, load saved users into bot_data, schedule 60s flush
• save_all_now()→ immediate upsert — call after every plan grant/remove
• close_db()    → FINAL SAVE then close pool — no data lost on redeploy
• If DATABASE_URL absent/fails → silent no-op, JSON fallback only
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time

logger = logging.getLogger(__name__)

# ── Connection pool ───────────────────────────────────────────────────────────
_pool = None   # asyncpg.Pool | None

# Try all Railway variable names in order
def _find_db_url() -> str:
    for key in ("DATABASE_URL", "DATABASE_PRIVATE_URL",
                "PGURL", "POSTGRES_URL", "POSTGRESQL_URL"):
        val = os.environ.get(key, "").strip()
        if val:
            logger.info(f"[DB] Using database URL from env var: {key}")
            return val
    return ""

DATABASE_URL: str = _find_db_url()
PREMIUM_FILE: str = os.environ.get("PREMIUM_FILE", "premium_users.json")

# ── Schema ────────────────────────────────────────────────────────────────────
_CREATE_TABLE = """
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

# ── SSL helper ────────────────────────────────────────────────────────────────
def _ssl_for_url(url: str):
    """Internal Railway URLs don't need SSL. External ones do."""
    if "railway.internal" in url:
        return False
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode    = ssl.CERT_NONE
    return ctx


# ── Connection ────────────────────────────────────────────────────────────────
async def _connect() -> bool:
    global _pool
    if not DATABASE_URL:
        logger.warning("[DB] ⚠️  No DATABASE_URL found in environment — "
                       "premium users will NOT persist across redeploys! "
                       "Add PostgreSQL to your Railway project and link DATABASE_URL.")
        return False
    try:
        import asyncpg
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            ssl=_ssl_for_url(DATABASE_URL),
            min_size=1,
            max_size=5,
            command_timeout=30,
        )
        async with _pool.acquire() as conn:
            await conn.execute(_CREATE_TABLE)
        logger.info("[DB] ✅ PostgreSQL connected — premium_users table ready.")
        return True
    except Exception as exc:
        logger.error(f"[DB] ❌ Connection failed: {exc}")
        _pool = None
        return False


# ── Read ──────────────────────────────────────────────────────────────────────
async def _load_from_db(bot_data: dict) -> int:
    if not _pool:
        return 0
    now = time.time()
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM premium_users WHERE expires > $1", now
            )
    except Exception as exc:
        logger.warning(f"[DB] load error: {exc}")
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


# ── Write (shared logic) ──────────────────────────────────────────────────────
_UPSERT_SQL = """
    INSERT INTO premium_users
        (user_id, plan, expires, name, username, last_receipt, granted_at)
    VALUES ($1,$2,$3,$4,$5,$6,$7)
    ON CONFLICT (user_id) DO UPDATE SET
        plan         = EXCLUDED.plan,
        expires      = EXCLUDED.expires,
        name         = EXCLUDED.name,
        username     = EXCLUDED.username,
        last_receipt = EXCLUDED.last_receipt,
        granted_at   = EXCLUDED.granted_at
"""

async def _upsert_records(records: list) -> int:
    """Upsert a list of tuples into premium_users. Retries once on failure."""
    if not _pool or not records:
        return 0
    for attempt in (1, 2):
        try:
            async with _pool.acquire() as conn:
                await conn.executemany(_UPSERT_SQL, records)
            logger.debug(f"[DB] upsert OK: {len(records)} record(s).")
            return len(records)
        except Exception as exc:
            logger.warning(f"[DB] upsert attempt {attempt}/2 failed: {exc}")
            if attempt == 1:
                await asyncio.sleep(1)   # brief pause before retry
    # Both attempts failed — try to reconnect and do one final attempt
    logger.error("[DB] ❌ Both upsert attempts failed — trying reconnect...")
    reconnected = await _connect()
    if reconnected:
        try:
            async with _pool.acquire() as conn:
                await conn.executemany(_UPSERT_SQL, records)
            logger.info(f"[DB] ✅ Upsert succeeded after reconnect: {len(records)} record(s).")
            return len(records)
        except Exception as exc:
            logger.error(f"[DB] ❌ Upsert failed even after reconnect: {exc}")
    return 0


# ── Public write helpers ──────────────────────────────────────────────────────

async def save_all_now(user_data: dict) -> int:
    """
    Immediately upsert ALL active premium users to Postgres.
    Call this right after every plan grant or removal — don't wait for the
    60-second flush job.
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
            ud.get("granted_at", now),
        ))
    saved = await _upsert_records(records)
    if saved:
        logger.info(f"[DB] ✅ Instant save: {saved} premium user(s) written to Postgres.")
    return saved


async def save_user_now(user_id: int, ud: dict) -> bool:
    """
    Immediately upsert ONE user to Postgres.
    Use when you know exactly which user changed.
    """
    if not _pool:
        return False
    now     = time.time()
    plan    = ud.get("plan", "TRIAL").upper()
    expires = ud.get("expires", 0)
    if plan == "TRIAL" or expires <= now:
        # Plan removed — delete from DB
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

    saved = await _upsert_records([(
        user_id, plan, expires,
        ud.get("name", ""),
        ud.get("username", ""),
        ud.get("last_receipt", ""),
        ud.get("granted_at", now),
    )])
    if saved:
        logger.info(f"[DB] ✅ Instant save: user {user_id} plan={plan}.")
    return saved > 0


def _read_json() -> dict:
    if not os.path.exists(PREMIUM_FILE):
        return {}
    try:
        with open(PREMIUM_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning(f"[DB] JSON read error: {exc}")
        return {}


# ── PTB periodic flush ────────────────────────────────────────────────────────
async def _flush_job(context) -> None:
    user_data = context.bot_data.get("user_data", {})
    await save_all_now(user_data)


# ── Public API ────────────────────────────────────────────────────────────────

async def attach(app) -> None:
    """Call once at the end of _post_init."""
    ok = await _connect()
    if not ok:
        return

    restored = await _load_from_db(app.bot_data)

    if restored == 0:
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
                    "granted_at":   pdata.get("granted_at", now),
                })
            seeded = await save_all_now(app.bot_data.get("user_data", {}))
            if seeded:
                logger.info(f"[DB] Seeded {seeded} user(s) from JSON → Postgres.")

    # Schedule 60-second periodic flush
    if app.job_queue:
        app.job_queue.run_repeating(
            _flush_job, interval=60, first=30, name="db_premium_flush"
        )
        logger.info("[DB] Periodic flush scheduled (every 60 s).")


async def close_db(bot_data: dict | None = None) -> None:
    """
    Call inside _post_shutdown — ALWAYS pass app.bot_data.
    Does a FINAL SAVE before closing so no data is lost on redeploy.
    """
    global _pool
    if not _pool:
        return
    if bot_data:
        saved = await save_all_now(bot_data.get("user_data", {}))
        logger.info(f"[DB] 🔒 Final save on shutdown: {saved} premium user(s) saved.")
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
    return "✅ PostgreSQL connected — premium users are safe."
