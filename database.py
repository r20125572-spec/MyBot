"""
database.py  —  Railway PostgreSQL persistence for premium user data.
════════════════════════════════════════════════════════════════════════
main.py needs only THREE lines:

    import database as db          # top of file
    await db.attach(app)           # end of _post_init
    await db.close_db(app.bot_data) # inside _post_shutdown  ← pass bot_data!

How it works
────────────
• attach(app)        → connect, load all saved users into bot_data,
                       seed DB from JSON on first run,
                       schedule 60-second periodic flush.
• close_db(bot_data) → FINAL SAVE to Postgres, then close pool.
                       Called on every redeploy/restart — no data lost.
• Flush job          → saves every 60 seconds as extra safety net.
• If DATABASE_URL missing / connection fails → silent no-op, JSON takes over.

Railway SSL note
────────────────
Internal URL  (postgres.railway.internal) → SSL disabled (already secure)
External URL  (*.railway.app / other)     → SSL enabled automatically
"""
from __future__ import annotations

import json
import logging
import os
import time

logger = logging.getLogger(__name__)

# ── Connection pool ───────────────────────────────────────────────────────────
_pool = None   # asyncpg.Pool | None

DATABASE_URL: str = os.environ.get("DATABASE_URL", "").strip()
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

# ── Internal helpers ──────────────────────────────────────────────────────────

def _ssl_for_url(url: str):
    """
    Railway internal connections (postgres.railway.internal) don't need SSL.
    All other connections use SSL with verification disabled so self-signed
    Railway certs are accepted.
    """
    if "railway.internal" in url:
        return False           # internal private network — no SSL needed
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode    = ssl.CERT_NONE
    return ctx


async def _connect() -> bool:
    """Open asyncpg pool and create the table. Returns True on success."""
    global _pool
    if not DATABASE_URL:
        logger.info("[DB] DATABASE_URL not set — JSON fallback only.")
        return False
    try:
        import asyncpg
        ssl_arg = _ssl_for_url(DATABASE_URL)
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            ssl=ssl_arg,
            min_size=1,
            max_size=5,
            command_timeout=30,
        )
        async with _pool.acquire() as conn:
            await conn.execute(_CREATE_TABLE)
        logger.info("[DB] ✅ PostgreSQL connected — premium_users table ready.")
        return True
    except Exception as exc:
        logger.error(f"[DB] ❌ Connection failed: {exc} — JSON fallback only.")
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
        if row["name"]:         ud["name"]         = row["name"]
        if row["username"]:     ud["username"]     = row["username"]
        if row["last_receipt"]: ud["last_receipt"] = row["last_receipt"]
        if row["granted_at"]:   ud.setdefault("granted_at", row["granted_at"])

    logger.info(f"[DB] ✅ Restored {len(rows)} premium user(s) from PostgreSQL.")
    return len(rows)


async def _save_to_db(user_data: dict) -> int:
    """Upsert every active premium user. Returns number of rows saved."""
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
            uid,
            plan,
            expires,
            ud.get("name", ""),
            ud.get("username", ""),
            ud.get("last_receipt", ""),
            ud.get("granted_at", now),
        ))

    if not records:
        return 0

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
        logger.info(f"[DB] ✅ Saved {len(records)} premium user(s) to PostgreSQL.")
        return len(records)
    except Exception as exc:
        logger.warning(f"[DB] save error: {exc}")
        return 0


def _read_json() -> dict:
    """Read premium_users.json → dict. Returns {} on any error."""
    if not os.path.exists(PREMIUM_FILE):
        return {}
    try:
        with open(PREMIUM_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning(f"[DB] JSON read error: {exc}")
        return {}


# ── PTB periodic flush job ────────────────────────────────────────────────────

async def _flush_job(context) -> None:
    """PTB JobQueue callback — flush bot_data → Postgres every 60 s."""
    user_data = context.bot_data.get("user_data", {})
    saved = await _save_to_db(user_data)
    if saved:
        logger.info(f"[DB] Periodic flush: {saved} user(s) saved.")


# ── Public API ────────────────────────────────────────────────────────────────

async def attach(app) -> None:
    """
    Call once at the end of _post_init.

    1. Connect to Postgres (no-op if DATABASE_URL absent).
    2. Load all saved premium users into app.bot_data.
       • First run: seeds DB from premium_users.json if table is empty.
    3. Immediately flush in-memory data → DB (catches any JSON users).
    4. Schedule 60-second repeating flush job.
    """
    ok = await _connect()
    if not ok:
        return

    # Load existing DB rows → bot_data
    restored = await _load_from_db(app.bot_data)

    if restored == 0:
        # First run or empty DB — seed from JSON backup
        saved_json = _read_json()
        if saved_json:
            now       = time.time()
            user_data = app.bot_data.setdefault("user_data", {})
            seeded    = 0
            for uid_str, pdata in saved_json.items():
                expires = pdata.get("expires", 0)
                plan    = pdata.get("plan", "TRIAL").upper()
                if plan == "TRIAL" or expires <= now:
                    continue
                ud = user_data.setdefault(uid_str, {})
                ud["plan"]         = plan
                ud["expires"]      = expires
                ud["name"]         = pdata.get("name", "")
                ud["username"]     = pdata.get("username", "")
                ud["last_receipt"] = pdata.get("last_receipt", "")
                ud["granted_at"]   = pdata.get("granted_at", now)
                seeded += 1
            if seeded:
                logger.info(f"[DB] Seeding {seeded} user(s) from {PREMIUM_FILE} → Postgres …")
                await _save_to_db(app.bot_data.get("user_data", {}))

    # Immediate flush — write any JSON-loaded users to DB right now
    await _save_to_db(app.bot_data.get("user_data", {}))

    # Schedule periodic flush (every 60 s)
    if app.job_queue:
        app.job_queue.run_repeating(
            _flush_job,
            interval=60,
            first=30,
            name="db_premium_flush",
        )
        logger.info("[DB] Periodic flush job scheduled (every 60 s).")


async def close_db(bot_data: dict | None = None) -> None:
    """
    Call inside _post_shutdown — pass app.bot_data so we do a FINAL SAVE
    before closing the pool. This ensures no data is lost on redeploy.

    Usage in _post_shutdown:
        await db.close_db(app.bot_data)
    """
    global _pool
    if not _pool:
        return

    # ── CRITICAL: final save before shutting down ─────────────────────────
    if bot_data:
        user_data = bot_data.get("user_data", {})
        saved = await _save_to_db(user_data)
        logger.info(f"[DB] Final save on shutdown: {saved} premium user(s) saved.")
    else:
        logger.warning("[DB] close_db called without bot_data — skipping final save.")

    try:
        await _pool.close()
    except Exception as exc:
        logger.warning(f"[DB] Pool close error: {exc}")
    _pool = None
    logger.info("[DB] PostgreSQL pool closed cleanly.")


def is_connected() -> bool:
    """True when the asyncpg pool is open."""
    return _pool is not None
