import base64
import io
import re
import time
import uuid
from datetime import UTC, datetime, timedelta

import pyotp
import qrcode
import redis.asyncio as aioredis
from sqlalchemy import cast, delete, or_, select, update
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AuthenticationError, AuthorizationError, NotFoundError
from app.core.redis import safe_redis_delete, safe_redis_get, safe_redis_setex
from app.core.security import (
    decrypt_value,
    encrypt_value,
    generate_backup_codes,
    hash_backup_code,
    verify_backup_code,
)
from app.modules.profiles.models import Admin2FA, AdminSession, Profile

# How long a completed TOTP challenge stays valid for a given admin session
# before the 2FA gate in app.core.dependencies demands it again.
ADMIN_2FA_SESSION_TTL = timedelta(hours=12)

# Account-level brute-force lockout (independent of the per-IP rate limiter —
# an attacker holding a stolen JWT can rotate source IPs, but not accounts).
ADMIN_2FA_LOCKOUT_THRESHOLD = 5
ADMIN_2FA_LOCKOUT_WINDOW_SECONDS = 15 * 60

# Don't write last_activity_at/ip/user_agent on every single request —
# only once this long has passed since the last write for that session.
ADMIN_SESSION_ACTIVITY_THROTTLE = timedelta(minutes=5)

# Sessions past expires_at aren't rejected any earlier than the moment they
# expire, but the hourly cleanup worker waits this much longer before
# deleting the row — gives a small grace window for any in-flight request
# and a debugging trail ("this just expired" vs "long gone").
ADMIN_SESSION_CLEANUP_GRACE = timedelta(hours=1)

_TOTP_STEP_SECONDS = 30

# Real User-Agent strings top out around 200-300 chars; a client sending
# anything wildly longer than that is either malformed or hostile (e.g. a
# probe for a stored-value overflow). Cap it before it ever reaches a regex
# or a database write — the Text/INET columns would happily accept an
# unbounded string, so this is enforced here, not relied on at the schema
# level.
MAX_USER_AGENT_LENGTH = 512


def _sanitize_user_agent(ua: str | None) -> str | None:
    if not ua:
        return ua
    return ua[:MAX_USER_AGENT_LENGTH]


# Minimal, dependency-free user-agent parsing — good enough for a security
# dashboard's "Chrome on Windows" display, not meant to be exhaustive.
_OS_PATTERNS: list[tuple[str, str]] = [
    (r"Windows NT 10\.0", "Windows 10/11"),
    (r"Windows NT", "Windows"),
    (r"Mac OS X", "macOS"),
    (r"iPhone|iPad|iPod", "iOS"),
    (r"Android", "Android"),
    (r"Linux", "Linux"),
]
_BROWSER_PATTERNS: list[tuple[str, str]] = [
    (r"Edg/", "Edge"),
    (r"OPR/|Opera", "Opera"),
    (r"Chrome/", "Chrome"),
    (r"CriOS/", "Chrome (iOS)"),
    (r"Firefox/", "Firefox"),
    (r"Version/.*Safari/", "Safari"),
]


def _parse_user_agent(ua: str | None) -> tuple[str | None, str | None]:
    """Return (browser_name, os_name) from a raw User-Agent header. Best-effort."""
    ua = _sanitize_user_agent(ua)
    if not ua:
        return None, None
    browser = next(
        (name for pattern, name in _BROWSER_PATTERNS if re.search(pattern, ua)), None
    )
    os_name = next(
        (name for pattern, name in _OS_PATTERNS if re.search(pattern, ua)), None
    )
    return browser, os_name


def _current_totp_counter() -> int:
    return int(time.time() // _TOTP_STEP_SECONDS)


def _2fa_lockout_key(user_id: str) -> str:
    return f"admin:2fa_lockout:{user_id}"


class AuthService:
    async def verify_token_and_get_profile(
        self, db: AsyncSession, user_id: str
    ) -> Profile:
        from app.modules.profiles.repository import ProfileRepository

        repo = ProfileRepository()
        profile = await repo.get_by_id(db, user_id)
        if not profile:
            raise NotFoundError("User not found")
        if not profile.is_active:
            raise AuthorizationError("Account is inactive", code="ACCOUNT_INACTIVE")
        return profile

    async def has_active_2fa(self, db: AsyncSession, user_id: str) -> bool:
        result = await db.execute(
            select(Admin2FA).where(
                Admin2FA.user_id == user_id,
                Admin2FA.is_enabled.is_(True),
            )
        )
        return result.scalar_one_or_none() is not None

    async def setup_2fa(self, db: AsyncSession, user_id: str, email: str) -> dict:
        """
        Generate a TOTP secret, store it encrypted, return QR URI and data URL.
        Overwrites any existing (disabled) setup.
        """
        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret)
        uri = totp.provisioning_uri(name=email, issuer_name=settings.APP_NAME)

        # Generate QR code as base64 data URL
        img = qrcode.make(uri)
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        qr_data_url = (
            "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
        )

        encrypted_secret = encrypt_value(secret)

        # Upsert
        existing = await db.execute(select(Admin2FA).where(Admin2FA.user_id == user_id))
        record = existing.scalar_one_or_none()

        if record:
            await db.execute(
                update(Admin2FA)
                .where(Admin2FA.user_id == user_id)
                .values(totp_secret=encrypted_secret, is_enabled=False, backup_codes=[])
            )
        else:
            db.add(
                Admin2FA(
                    id=uuid.uuid4(),
                    user_id=uuid.UUID(user_id),
                    totp_secret=encrypted_secret,
                    is_enabled=False,
                    backup_codes=[],
                )
            )

        return {
            "totp_uri": uri,
            "secret": secret,
            "qr_code_data_url": qr_data_url,
        }

    async def verify_and_activate_2fa(
        self, db: AsyncSession, user_id: str, totp_code: str
    ) -> list[str]:
        """
        Verify the TOTP code against the stored secret and activate 2FA.
        Returns plain backup codes (caller must present to user once).
        """
        record = await self._get_2fa_record(db, user_id)
        secret = decrypt_value(record.totp_secret)
        totp = pyotp.TOTP(secret)

        if not totp.verify(totp_code, valid_window=1):
            raise AuthenticationError("Invalid TOTP code")

        plain_codes = generate_backup_codes()
        hashed_codes = [hash_backup_code(c) for c in plain_codes]

        # Record the step this enrollment code verified at — otherwise an
        # attacker who intercepted this exact request could immediately
        # replay the same code against /admin/2fa/validate.
        await db.execute(
            update(Admin2FA)
            .where(Admin2FA.user_id == user_id)
            .values(
                is_enabled=True,
                backup_codes=hashed_codes,
                enabled_at=datetime.now(UTC),
                last_used_counter=_current_totp_counter(),
            )
        )
        return plain_codes

    async def validate_2fa(
        self, db: AsyncSession, user_id: str, totp_code: str
    ) -> bool:
        """Validate TOTP code on every admin login. Also accepts backup codes."""
        valid, _method = await self.validate_2fa_detailed(db, user_id, totp_code)
        return valid

    async def validate_2fa_detailed(
        self, db: AsyncSession, user_id: str, totp_code: str
    ) -> tuple[bool, str | None]:
        """
        Same check as validate_2fa, but also reports which method matched
        on success ("totp" / "backup_code"), or why it failed on failure
        ("replay" / None for a plain wrong/unrecognized code) — so the
        caller can audit-log backup code usage and replay attempts
        distinctly from ordinary wrong-code failures. A cryptographically
        valid but replayed code is a materially different signal (a
        captured/intercepted code) than a random guess. Consumes backup
        code if matched (removes it from the list).
        """
        record = await self._get_2fa_record(db, user_id)
        secret = decrypt_value(record.totp_secret)
        totp = pyotp.TOTP(secret)

        if totp.verify(totp_code, valid_window=1):
            current_counter = _current_totp_counter()
            # Atomic "check-then-set" via a single conditional UPDATE, not a
            # Python if/else around a separate read — two concurrent requests
            # racing the same code would otherwise both pass a Python-side
            # check before either commits. Postgres serializes concurrent
            # UPDATEs on the same row, so only one of two racing transactions
            # can ever satisfy this WHERE clause; the loser sees rowcount=0
            # and is correctly treated as a replay.
            result = await db.execute(
                update(Admin2FA)
                .where(
                    Admin2FA.user_id == user_id,
                    or_(
                        Admin2FA.last_used_counter.is_(None),
                        Admin2FA.last_used_counter < current_counter,
                    ),
                )
                .values(last_used_counter=current_counter)
            )
            if result.rowcount == 0:
                return False, "replay"
            return True, "totp"

        # Try backup codes
        hashed_codes: list[str] = list(record.backup_codes or [])
        for i, hashed in enumerate(hashed_codes):
            if verify_backup_code(totp_code, hashed):
                # Consume the code
                hashed_codes.pop(i)
                await db.execute(
                    update(Admin2FA)
                    .where(Admin2FA.user_id == user_id)
                    .values(backup_codes=hashed_codes)
                )
                return True, "backup_code"

        return False, None

    async def logout(self, db: AsyncSession, user_id: str) -> None:
        """
        Revoke Supabase session via service role API. Best-effort: if
        Supabase's admin API is unreachable (outage, timeout), this must not
        prevent the caller from clearing local AdminSession state — routers
        call this *before* clear_admin_session_2fa/clear_all_admin_sessions_2fa,
        so letting a network error propagate here would leave the local
        2FA-verified row in place even though the user asked to log out.
        """
        import httpx
        import structlog

        log = structlog.get_logger(__name__)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{settings.SUPABASE_URL}/auth/v1/admin/users/{user_id}/logout",
                    headers={
                        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
                        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
                    },
                )
                response.raise_for_status()
        except Exception:
            log.warning(
                "supabase_logout_revocation_failed",
                user_id=user_id,
                exc_info=True,
            )

    async def force_logout(self, db: AsyncSession, target_user_id: str) -> None:
        """Force logout any user (super_admin only)."""
        await self.logout(db, target_user_id)

    async def clear_admin_session_2fa(
        self, db: AsyncSession, user_id: str, session_id: str | None
    ) -> None:
        """
        Drop the 2FA-verified state for this one login session on logout, so a
        stale AdminSession row can't be reused if the same session_id ever
        reappears (e.g. a leaked/replayed token).
        """
        if not session_id:
            return
        await db.execute(
            delete(AdminSession).where(
                AdminSession.user_id == user_id,
                AdminSession.supabase_session_id == session_id,
            )
        )

    async def clear_all_admin_sessions_2fa(self, db: AsyncSession, user_id: str) -> int:
        """Drop 2FA-verified state for every session of this user (force-logout)."""
        result = await db.execute(
            delete(AdminSession).where(AdminSession.user_id == user_id)
        )
        return result.rowcount

    async def is_admin_session_2fa_verified(
        self, db: AsyncSession, user_id: str, session_id: str
    ) -> bool:
        """
        True only if this exact Supabase login session has already completed
        the TOTP challenge and that verification hasn't expired. This is the
        real security boundary — never trust a client-side "verified" flag.
        """
        result = await db.execute(
            select(AdminSession).where(
                AdminSession.user_id == user_id,
                AdminSession.supabase_session_id == session_id,
            )
        )
        record = result.scalar_one_or_none()
        if not record or not record.is_2fa_verified:
            return False
        if record.expires_at and record.expires_at < datetime.now(UTC):
            return False
        return True

    async def ensure_admin_session_tracked(
        self,
        db: AsyncSession,
        user_id: str,
        session_id: str,
        ip_address: str,
        user_agent: str | None = None,
    ) -> None:
        """
        Create (or touch) a lightweight AdminSession row for every admin
        login — 2FA-enabled or not — so the security dashboard can show
        "you're logged in here" universally, not only for 2FA-tracked
        sessions. Called once per session lifetime via
        track_admin_login_if_new_session, alongside the admin_login audit
        dedup.

        Deliberately never touches is_2fa_verified/verified_at on an
        existing row — only mark_admin_session_2fa_verified may set those —
        so this presence-only touch can never regress an already-verified
        session back to unverified, regardless of call order.

        For accounts without 2FA enabled, this row is informational: the
        require_admin gate does not consult AdminSession at all when the
        account has no 2FA enabled, so deleting this row (via the single-
        session or "others" revoke endpoints) removes it from the list but
        does not end the underlying access — only "Log Out All Sessions"
        does, since that calls Supabase's real session-revocation API
        directly, independent of 2FA status. The frontend must say this
        plainly rather than imply a single-session revoke works the same
        way for both cases.
        """
        user_agent = _sanitize_user_agent(user_agent)
        browser_name, os_name = _parse_user_agent(user_agent)
        now = datetime.now(UTC)
        stmt = pg_insert(AdminSession).values(
            id=uuid.uuid4(),
            user_id=uuid.UUID(user_id),
            supabase_session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
            browser_name=browser_name,
            os_name=os_name,
            is_2fa_verified=False,
            last_seen_at=now,
            expires_at=now + ADMIN_2FA_SESSION_TTL,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[AdminSession.user_id, AdminSession.supabase_session_id],
            set_={
                "last_seen_at": now,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "browser_name": browser_name,
                "os_name": os_name,
            },
        )
        await db.execute(stmt)

    async def track_admin_login_if_new_session(
        self,
        db: AsyncSession,
        redis: aioredis.Redis,
        *,
        user_id: str,
        user_email: str,
        user_role: str,
        session_id: str | None,
        ip_address: str,
        user_agent: str | None,
    ) -> None:
        """
        Call from any endpoint that fires once per page load for an
        authenticated admin — currently GET /me, the actual per-load call
        this frontend makes (an earlier version of this wiring lived in
        /auth/verify-token, which turned out to never be called by the
        frontend at all — dead code that silently never fired).

        Creates/touches this session's AdminSession row and logs exactly
        one "admin_login" audit event per session lifetime, deduped via
        Redis so routine reloads don't repeat either side effect. Two
        independent dedup keys, not one shared key — tying a *new* side
        effect to an *existing* dedup key means any session that already
        set that key before the new effect existed silently never gets it,
        for up to the key's full TTL.
        """
        if not session_id:
            return

        ttl = int(ADMIN_2FA_SESSION_TTL.total_seconds())

        session_tracked_key = f"admin:session_tracked:{session_id}"
        if not await safe_redis_get(redis, session_tracked_key):
            await safe_redis_setex(redis, session_tracked_key, ttl, "1")
            await self.ensure_admin_session_tracked(
                db, user_id, session_id, ip_address, user_agent
            )

        login_key = f"admin:login_logged:{session_id}"
        if not await safe_redis_get(redis, login_key):
            await safe_redis_setex(redis, login_key, ttl, "1")
            from app.modules.audit.service import AuditService

            await AuditService().log(
                db,
                actor_id=user_id,
                actor_email=user_email,
                actor_role=user_role,
                action="admin_login",
                resource_type="profile",
                resource_id=user_id,
                ip_address=ip_address,
                user_agent=user_agent,
            )

    async def mark_admin_session_2fa_verified(
        self,
        db: AsyncSession,
        user_id: str,
        session_id: str,
        ip_address: str,
        user_agent: str | None = None,
    ) -> None:
        """Called after a successful POST /auth/admin/2fa/validate."""
        user_agent = _sanitize_user_agent(user_agent)
        now = datetime.now(UTC)
        expires_at = now + ADMIN_2FA_SESSION_TTL

        # A plain SELECT-then-INSERT/UPDATE has a real race window: two
        # concurrent successful validations for the same session can both
        # see "no row yet" and both attempt to INSERT, and the second one
        # would raise an unhandled IntegrityError against the unique index
        # on (user_id, supabase_session_id). A single upsert makes the
        # decision atomic at the database level regardless of concurrency.
        stmt = pg_insert(AdminSession).values(
            id=uuid.uuid4(),
            user_id=uuid.UUID(user_id),
            supabase_session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
            is_2fa_verified=True,
            verified_at=now,
            expires_at=expires_at,
            last_seen_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[AdminSession.user_id, AdminSession.supabase_session_id],
            set_={
                "is_2fa_verified": True,
                "verified_at": now,
                "expires_at": expires_at,
                "last_seen_at": now,
                "ip_address": ip_address,
                "user_agent": user_agent,
            },
        )
        await db.execute(stmt)

    async def touch_admin_session_activity(
        self,
        db: AsyncSession,
        user_id: str,
        session_id: str,
        ip_address: str,
        user_agent: str | None,
    ) -> None:
        """
        Record last-seen activity for the security dashboard. Throttled to
        once every ADMIN_SESSION_ACTIVITY_THROTTLE — called from an already
        2FA-verified request, never from every request, so this stays cheap.
        """
        user_agent = _sanitize_user_agent(user_agent)
        result = await db.execute(
            select(AdminSession).where(
                AdminSession.user_id == user_id,
                AdminSession.supabase_session_id == session_id,
            )
        )
        record = result.scalar_one_or_none()
        if not record:
            return

        now = datetime.now(UTC)
        if (
            record.last_activity_at is not None
            and now - record.last_activity_at < ADMIN_SESSION_ACTIVITY_THROTTLE
        ):
            return

        browser_name, os_name = _parse_user_agent(user_agent)
        await db.execute(
            update(AdminSession)
            .where(AdminSession.id == record.id)
            .values(
                last_activity_at=now,
                last_seen_ip=ip_address,
                last_seen_user_agent=user_agent,
                browser_name=browser_name,
                os_name=os_name,
            )
        )

    async def is_new_device(
        self,
        db: AsyncSession,
        user_id: str,
        ip_address: str,
        user_agent: str | None,
    ) -> bool:
        """
        Best-effort "have we seen this device/location before" check for the
        login-notification feature — true if no existing session row for this
        user matches this IP or this browser+OS combination. Limited to
        currently-existing rows (cleaned up on logout/expiry), so it's a
        heuristic, not an exhaustive history.
        """
        # New IP and new device are independent signals — checked separately
        # so that, say, a familiar browser from a brand-new IP still counts
        # as "new" (a single OR'd query would only fire when *both* the IP
        # and the device are unrecognized, under-notifying new-location
        # logins from an already-seen browser).
        # Explicit cast: comparing an INET column against a plain Python str
        # bind parameter, SQLAlchemy/asyncpg compiled the parameter as
        # ::VARCHAR rather than inferring ::INET from the column, and
        # Postgres has no inet = varchar operator — a real 500 in
        # production, not merely a style nit. Casting the literal side
        # explicitly removes any ambiguity regardless of inference quirks.
        ip_cast = cast(ip_address, INET)
        ip_seen = await db.execute(
            select(AdminSession.id)
            .where(
                AdminSession.user_id == user_id,
                or_(
                    AdminSession.last_seen_ip == ip_cast,
                    AdminSession.ip_address == ip_cast,
                ),
            )
            .limit(1)
        )
        if ip_seen.scalar_one_or_none() is None:
            return True

        browser_name, os_name = _parse_user_agent(user_agent)
        if not browser_name or not os_name:
            return False

        device_seen = await db.execute(
            select(AdminSession.id)
            .where(
                AdminSession.user_id == user_id,
                AdminSession.browser_name == browser_name,
                AdminSession.os_name == os_name,
            )
            .limit(1)
        )
        return device_seen.scalar_one_or_none() is None

    async def list_admin_sessions(
        self, db: AsyncSession, user_id: str
    ) -> list[AdminSession]:
        """All sessions for the security dashboard, most recently active first."""
        result = await db.execute(
            select(AdminSession)
            .where(AdminSession.user_id == user_id)
            .order_by(AdminSession.last_activity_at.desc().nullslast())
        )
        return list(result.scalars().all())

    async def revoke_admin_session(
        self,
        db: AsyncSession,
        user_id: str,
        session_row_id: str,
        *,
        current_session_id: str | None = None,
    ) -> tuple[bool, bool]:
        """
        Delete one session row by its own id (not by supabase_session_id).
        Returns (deleted, was_current_session).

        Refuses to delete the caller's *own current* session through this
        generic endpoint — that must go through /revoke-all or /logout
        instead, so a session can't be torn down by accident via what looks
        like "log out one other device". The SELECT is scoped to user_id
        before any decision is made, so probing another user's session id
        always looks identical to a session that doesn't exist (no IDOR,
        no existence leak either way).

        Note on scope: Supabase's admin API can only revoke *every* session
        for a user at once (used by force_logout/logout/revoke-all), not one
        specific session. Deleting the row here immediately revokes that
        session's access to the admin panel (the next request re-hits the
        2FA gate and gets 403 2FA_REQUIRED) even though the underlying
        Supabase JWT stays technically valid until it naturally expires.
        """
        result = await db.execute(
            select(AdminSession).where(
                AdminSession.id == session_row_id,
                AdminSession.user_id == user_id,
            )
        )
        record = result.scalar_one_or_none()
        if not record:
            return False, False

        was_current = (
            current_session_id is not None
            and record.supabase_session_id == current_session_id
        )
        if was_current:
            return False, True

        await db.execute(delete(AdminSession).where(AdminSession.id == record.id))
        return True, False

    async def revoke_other_admin_sessions(
        self, db: AsyncSession, user_id: str, current_session_id: str | None
    ) -> int:
        """Delete every session row for this user except the caller's own."""
        conditions = [AdminSession.user_id == user_id]
        if current_session_id:
            conditions.append(AdminSession.supabase_session_id != current_session_id)
        result = await db.execute(delete(AdminSession).where(*conditions))
        return result.rowcount

    async def cleanup_expired_admin_sessions(self, db: AsyncSession) -> int:
        """
        Batch-delete sessions whose 2FA verification expired more than
        ADMIN_SESSION_CLEANUP_GRACE ago. Called hourly by the
        admin_session_cleanup worker — a single DELETE, no row locking beyond
        what Postgres does for the statement itself, safe to run concurrently
        with normal request traffic since it only ever removes rows that can
        no longer pass is_admin_session_2fa_verified anyway.
        """
        cutoff = datetime.now(UTC) - ADMIN_SESSION_CLEANUP_GRACE
        result = await db.execute(
            delete(AdminSession).where(
                AdminSession.expires_at.is_not(None),
                AdminSession.expires_at < cutoff,
            )
        )
        return result.rowcount

    async def is_2fa_locked_out(self, redis: aioredis.Redis, user_id: str) -> bool:
        """Account-level lockout, independent of the per-IP rate limiter."""
        raw = await safe_redis_get(redis, _2fa_lockout_key(user_id))
        return raw is not None and int(raw) >= ADMIN_2FA_LOCKOUT_THRESHOLD

    async def record_2fa_failure(self, redis: aioredis.Redis, user_id: str) -> int:
        key = _2fa_lockout_key(user_id)
        raw = await safe_redis_get(redis, key)
        count = (int(raw) if raw else 0) + 1
        await safe_redis_setex(redis, key, ADMIN_2FA_LOCKOUT_WINDOW_SECONDS, str(count))
        return count

    async def clear_2fa_failures(self, redis: aioredis.Redis, user_id: str) -> None:
        await safe_redis_delete(redis, _2fa_lockout_key(user_id))

    async def get_2fa_status(self, db: AsyncSession, user_id: str) -> dict:
        """Return 2FA status for the current user."""
        result = await db.execute(select(Admin2FA).where(Admin2FA.user_id == user_id))
        record = result.scalar_one_or_none()
        if not record or not record.is_enabled:
            return {
                "is_enabled": False,
                "enabled_at": None,
                "backup_codes_remaining": 0,
                "total_backup_codes": 0,
            }
        hashed_codes: list[str] = list(record.backup_codes or [])
        return {
            "is_enabled": True,
            "enabled_at": record.enabled_at.isoformat() if record.enabled_at else None,
            "backup_codes_remaining": len(hashed_codes),
            "total_backup_codes": 10,
        }

    async def disable_2fa(self, db: AsyncSession, user_id: str, totp_code: str) -> None:
        """Validate TOTP code then disable 2FA for the user."""
        valid = await self.validate_2fa(db, user_id, totp_code)
        if not valid:
            raise AuthenticationError("Invalid TOTP code")
        await db.execute(
            update(Admin2FA)
            .where(Admin2FA.user_id == user_id)
            .values(is_enabled=False, backup_codes=[])
        )
        # Otherwise a stale "verified" session row would silently satisfy the
        # 2FA gate again the moment this user re-enables 2FA, without ever
        # completing a fresh TOTP challenge.
        await self.clear_all_admin_sessions_2fa(db, user_id)

    async def regenerate_backup_codes(
        self, db: AsyncSession, user_id: str, totp_code: str
    ) -> list[str]:
        """Validate TOTP code then generate and store new backup codes."""
        valid = await self.validate_2fa(db, user_id, totp_code)
        if not valid:
            raise AuthenticationError("Invalid TOTP code")
        plain_codes = generate_backup_codes()
        hashed_codes = [hash_backup_code(c) for c in plain_codes]
        await db.execute(
            update(Admin2FA)
            .where(Admin2FA.user_id == user_id)
            .values(backup_codes=hashed_codes)
        )
        return plain_codes

    async def force_reset_2fa(self, db: AsyncSession, target_user_id: str) -> None:
        """Delete the 2FA record for a user (super_admin only)."""
        result = await db.execute(
            select(Admin2FA).where(Admin2FA.user_id == target_user_id)
        )
        record = result.scalar_one_or_none()
        if record:
            await db.execute(delete(Admin2FA).where(Admin2FA.user_id == target_user_id))
        await self.clear_all_admin_sessions_2fa(db, target_user_id)

    async def _get_2fa_record(self, db: AsyncSession, user_id: str) -> Admin2FA:
        result = await db.execute(select(Admin2FA).where(Admin2FA.user_id == user_id))
        record = result.scalar_one_or_none()
        if not record:
            raise NotFoundError("2FA not configured for this account")
        return record
