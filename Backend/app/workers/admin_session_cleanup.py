"""
Admin session cleanup worker — runs hourly.

Batch-deletes AdminSession rows whose 2FA verification expired more than an
hour ago. Expired sessions are already rejected at request time by
AuthService.is_admin_session_2fa_verified (expires_at check) — this worker
is pure operational hygiene, keeping the table from growing unbounded.

A single DELETE by indexed expires_at, no per-row locking beyond what
Postgres does for the statement itself, safe to run concurrently with
request traffic, and idempotent — running it twice with nothing new expired
just deletes zero rows the second time.
"""

import structlog

from app.workers.base import run_with_session

log = structlog.get_logger(__name__)


async def run() -> None:
    await run_with_session(_cleanup_expired_sessions)


async def _cleanup_expired_sessions(db) -> None:
    from app.modules.auth.service import AuthService

    deleted = await AuthService().cleanup_expired_admin_sessions(db)
    if deleted:
        log.info("admin_sessions_cleaned_up", count=deleted)
    else:
        log.debug("admin_session_cleanup_run_no_expired")
