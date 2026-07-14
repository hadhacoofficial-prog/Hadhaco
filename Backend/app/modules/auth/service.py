import base64
import io
import time
import uuid
from datetime import UTC, datetime, timedelta

import pyotp
import qrcode
import redis.asyncio as aioredis
from sqlalchemy import delete, select, update
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

_TOTP_STEP_SECONDS = 30


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
        """
        Validate TOTP code on every admin login. Also accepts backup codes.
        Consumes backup code if matched (removes from list).
        """
        record = await self._get_2fa_record(db, user_id)
        secret = decrypt_value(record.totp_secret)
        totp = pyotp.TOTP(secret)

        if totp.verify(totp_code, valid_window=1):
            current_counter = _current_totp_counter()
            if (
                record.last_used_counter is not None
                and current_counter <= record.last_used_counter
            ):
                # Same code (or an earlier one) already consumed this step —
                # reject the replay instead of granting access again.
                return False
            await db.execute(
                update(Admin2FA)
                .where(Admin2FA.user_id == user_id)
                .values(last_used_counter=current_counter)
            )
            return True

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
                return True

        return False

    async def logout(self, db: AsyncSession, user_id: str) -> None:
        """Revoke Supabase session via service role API."""
        import httpx

        async with httpx.AsyncClient() as client:
            await client.post(
                f"{settings.SUPABASE_URL}/auth/v1/admin/users/{user_id}/logout",
                headers={
                    "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
                    "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
                },
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

    async def clear_all_admin_sessions_2fa(
        self, db: AsyncSession, user_id: str
    ) -> None:
        """Drop 2FA-verified state for every session of this user (force-logout)."""
        await db.execute(delete(AdminSession).where(AdminSession.user_id == user_id))

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

    async def mark_admin_session_2fa_verified(
        self,
        db: AsyncSession,
        user_id: str,
        session_id: str,
        ip_address: str,
        user_agent: str | None = None,
    ) -> None:
        """Called after a successful POST /auth/admin/2fa/validate."""
        now = datetime.now(UTC)
        expires_at = now + ADMIN_2FA_SESSION_TTL

        result = await db.execute(
            select(AdminSession).where(
                AdminSession.user_id == user_id,
                AdminSession.supabase_session_id == session_id,
            )
        )
        record = result.scalar_one_or_none()
        if record:
            await db.execute(
                update(AdminSession)
                .where(AdminSession.id == record.id)
                .values(
                    is_2fa_verified=True,
                    verified_at=now,
                    expires_at=expires_at,
                    last_seen_at=now,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
            )
        else:
            db.add(
                AdminSession(
                    id=uuid.uuid4(),
                    user_id=uuid.UUID(user_id),
                    supabase_session_id=session_id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    is_2fa_verified=True,
                    verified_at=now,
                    expires_at=expires_at,
                )
            )

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
