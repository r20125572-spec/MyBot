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

Two tables:
  • premium_users  — plan / expires / receipt (unchanged)
  • user_stats     — total_charged, name, username, joined, last_active
                     for EVERY user (not just premium)
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
    updated_at    DOUBLE PRECISION NOT NULL DEFAULT 0
);
"""


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
            _pool = pool
            label = "none" if ssl_opt is False else (
                "unverified" if ssl_opt is _unverified else "verified"
            )
            logger.info(f"[DB] ✅ PostgreSQL connected (ssl={label}) — "
                        "premium_users + user_stats tables ready.")
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
        plan         = EXCLUDED.plan,
        expires      = EXCLUDED.expires,
        name         = EXCLUDED.name,
        username     = EXCLUDED.username,
        last_receipt = EXCLUDED.last_receipt,
        granted_at   = EXCLUDED.granted_at
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
            ud.get("granted_at", now),
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
        ud.get("granted_at", now),
    )])
    return saved > 0


# ══════════════════════════════════════════════════════════════════════════════
#  USER STATS  (total_charged + activity — NEW, survives redeploys)
# ══════════════════════════════════════════════════════════════════════════════

_STATS_UPSERT = """
    INSERT INTO user_stats
        (user_id, total_charged, name, first_name, username,
         joined, last_active, total_checks, approved_checks,
         declined_checks, total_refs, updated_at)
    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
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
    Immediately upsert stats for ALL users that have at least one charged card.
    Called by the periodic flush job and on shutdown.
    """
    if not _pool:
        return 0
    records = []
    for uid_str, ud in user_data.items():
        if ud.get("total_charged", 0) <= 0:
            continue
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

        db_checks = row["total_checks"] or 0
        ud["total_checks"] = max(ud.get("total_checks", 0), db_checks)

        db_approved = row["approved_checks"] or 0
        ud["approved_checks"] = max(ud.get("approved_checks", 0), db_approved)

        db_declined = row["declined_checks"] or 0
        ud["declined_checks"] = max(ud.get("declined_checks", 0), db_declined)

        db_refs = row["total_refs"] or 0
        ud["total_refs"] = max(ud.get("total_refs", 0), db_refs)

    logger.info(f"[DB] ✅ Restored stats for {len(rows)} user(s) from PostgreSQL "
                f"(total_charged, checks, etc. safe across redeploys).")
    return len(rows)


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
                    "granted_at":   pdata.get("granted_at", now),
                })
            seeded = await save_premium_now(app.bot_data.get("user_data", {}))
            if seeded:
                logger.info(f"[DB] Seeded {seeded} premium user(s) from JSON → Postgres.")

    # ★ NEW: Restore user stats (total_charged etc.) — critical for /me and /status
    await _load_stats_from_db(app.bot_data)

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
