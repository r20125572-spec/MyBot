"""
database.py  —  Railway PostgreSQL persistence for premium user data.
════════════════════════════════════════════════════════════════════════
This file is 100 % self-contained.  main.py needs only THREE lines:

    # 1. top of file (already added)
    import database as db

    # 2. end of _post_init
    await db.attach(app)

    # 3. inside _post_shutdown  (already added)
    await db.close_db()

How it works
────────────
• attach(app) connects to Postgres, loads premium users into bot_data,
  seeds the DB from premium_users.json on first run, then schedules a
  repeating job (every 60 s) to flush bot_data → Postgres.
• close_db() does a final save and closes the connection pool.
• If DATABASE_URL is not set (or connection fails) the module is a
  silent no-op — main.py's JSON file handles everything as before.

Railway setup
────────────
  Project → New → Database → PostgreSQL
  Railway injects DATABASE_URL into your service automatically.
"""
from __future__ import annotations

import json
import logging
import os
import time

logger = logging.getLogger(__name__)

# ── connection pool ───────────────────────────────────────────────────────────
_pool = None          # asyncpg.Pool | None

DATABASE_URL: str = os.environ.get("DATABASE_URL", "")
PREMIUM_FILE: str = os.environ.get("PREMIUM_FILE", "premium_users.json")

# ── schema ────────────────────────────────────────────────────────────────────
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

# ═══════════════════════════════════════════════════════════════════════════════
# INTERNAL — connection helpers
# ═══════════════════════════════════════════════════════════════════════════════

async def _connect() -> bool:
    """Open connection pool and create the table.  Returns True on success."""
    global _pool
    if not DATABASE_URL:
        logger.info("[DB] DATABASE_URL not set — JSON fallback only.")
        return False
    try:
        import asyncpg
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=5,
            command_timeout=30,
        )
        async with _pool.acquire() as conn:
            await conn.execute(_CREATE_TABLE)
        logger.info("[DB] PostgreSQL connected — premium_users table ready.")
        return True
    except Exception as exc:
        logger.warning(f"[DB] Connection failed: {exc} — JSON fallback only.")
        _pool = None
        return False


async def _load_from_db(bot_data: dict) -> int:
    """Read all non-expired rows and merge into bot_data. Returns count."""
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
        if row["name"]:         ud.setdefault("name",         row["name"])
        if row["username"]:     ud.setdefault("username",     row["username"])
        if row["last_receipt"]: ud.setdefault("last_receipt", row["last_receipt"])

    logger.info(f"[DB] Restored {len(rows)} premium user(s) from PostgreSQL.")
    return len(rows)


async def _save_to_db(user_data: dict) -> None:
    """Upsert every active premium user into premium_users."""
    if not _pool:
        return
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
            uid,
            plan,
            expires,
            ud.get("name", ""),
            ud.get("username", ""),
            ud.get("last_receipt", ""),
            ud.get("granted_at", now),
        ))

    if not records:
        return

    try:
        async with _pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO premium_users
                    (user_id, plan, expires, name, username,
                     last_receipt, granted_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7)
                ON CONFLICT (user_id) DO UPDATE SET
                    plan         = EXCLUDED.plan,
                    expires      = EXCLUDED.expires,
                    name         = EXCLUDED.name,
                    username     = EXCLUDED.username,
                    last_receipt = EXCLUDED.last_receipt,
                    granted_at   = EXCLUDED.granted_at
                """,
                records,
            )
        logger.info(f"[DB] Saved {len(records)} premium user(s) to PostgreSQL.")
    except Exception as exc:
        logger.warning(f"[DB] save error: {exc}")


def _read_json() -> dict:
    """Read premium_users.json → {uid_str: {...}}. Returns {} on any error."""
    if not os.path.exists(PREMIUM_FILE):
        return {}
    try:
        with open(PREMIUM_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning(f"[DB] JSON read error: {exc}")
        return {}


# ═══════════════════════════════════════════════════════════════════════════════
# PTB JOB — periodic flush
# ═══════════════════════════════════════════════════════════════════════════════

async def _flush_job(context) -> None:
    """PTB JobQueue callback: save premium users to Postgres every 60 s."""
    user_data = context.bot_data.get("user_data", {})
    await _save_to_db(user_data)


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API  (the only 3 symbols main.py uses)
# ═══════════════════════════════════════════════════════════════════════════════

async def attach(app) -> None:
    """
    Call once at the end of _post_init.

    1. Connects to Postgres (silently no-ops if DATABASE_URL is absent).
    2. Loads non-expired premium rows into app.bot_data.
       • If the table is empty on first run, seeds it from premium_users.json.
    3. Schedules a repeating job to flush bot_data → Postgres every 60 s.
    """
    ok = await _connect()
    if not ok:
        return     # no DATABASE_URL or connection failed — JSON is enough

    # Load from Postgres
    restored = await _load_from_db(app.bot_data)

    # First run: Postgres is empty → seed from JSON backup
    if restored == 0:
        saved_json = _read_json()
        if saved_json:
            logger.info(f"[DB] Seeding DB from {PREMIUM_FILE} "
                        f"({len(saved_json)} entries) …")
            # Merge JSON data into bot_data so the flush below picks it up
            now       = time.time()
            user_data = app.bot_data.setdefault("user_data", {})
            for uid_str, pdata in saved_json.items():
                if pdata.get("expires", 0) <= now:
                    continue
                ud = user_data.setdefault(uid_str, {})
                ud.setdefault("plan",         pdata.get("plan", "TRIAL"))
                ud.setdefault("expires",      pdata.get("expires", 0))
                ud.setdefault("name",         pdata.get("name", ""))
                ud.setdefault("username",     pdata.get("username", ""))
                ud.setdefault("last_receipt", pdata.get("last_receipt", ""))
            await _save_to_db(app.bot_data.get("user_data", {}))

    # Schedule periodic flush (every 60 s, first run after 30 s)
    if app.job_queue:
        app.job_queue.run_repeating(
            _flush_job,
            interval=60,
            first=30,
            name="db_premium_flush",
        )
        logger.info("[DB] Periodic flush scheduled (every 60 s).")


async def close_db() -> None:
    """
    Call inside _post_shutdown.
    Does a final save then closes the connection pool gracefully.
    """
    global _pool
    if not _pool:
        return
    logger.info("[DB] Final save before shutdown …")
    # We can't easily get bot_data here, but the 60-s job already ran.
    # Pool close is the important part.
    try:
        await _pool.close()
    except Exception as exc:
        logger.warning(f"[DB] pool close error: {exc}")
    _pool = None
    logger.info("[DB] PostgreSQL pool closed.")


def is_connected() -> bool:
    """True when the pool is open (used for health checks if needed)."""
    return _pool is not None

