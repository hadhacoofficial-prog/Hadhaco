import base64
import io
import json
import uuid

import pyotp
import qrcode
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AuthenticationError, AuthorizationError, NotFoundError
from app.core.security import (
    decrypt_value,
    encrypt_value,
    generate_backup_codes,
    hash_backup_code,
    verify_backup_code,
)
from app.modules.profiles.models import Admin2FA, AdminSession, Profile


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
                .values(
                    totp_secret=encrypted_secret, is_enabled=False, backup_codes="[]"
                )
            )
        else:
            db.add(
                Admin2FA(
                    id=uuid.uuid4(),
                    user_id=uuid.UUID(user_id),
                    totp_secret=encrypted_secret,
                    is_enabled=False,
                    backup_codes="[]",
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
        hashed_codes = json.dumps([hash_backup_code(c) for c in plain_codes])

        from datetime import UTC, datetime

        await db.execute(
            update(Admin2FA)
            .where(Admin2FA.user_id == user_id)
            .values(
                is_enabled=True,
                backup_codes=hashed_codes,
                enabled_at=datetime.now(UTC),
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
            return True

        # Try backup codes
        hashed_codes: list[str] = json.loads(record.backup_codes or "[]")
        for i, hashed in enumerate(hashed_codes):
            if verify_backup_code(totp_code, hashed):
                # Consume the code
                hashed_codes.pop(i)
                await db.execute(
                    update(Admin2FA)
                    .where(Admin2FA.user_id == user_id)
                    .values(backup_codes=json.dumps(hashed_codes))
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

    async def record_admin_session(
        self,
        db: AsyncSession,
        user_id: str,
        ip_address: str,
        user_agent: str | None = None,
    ) -> None:
        db.add(
            AdminSession(
                id=uuid.uuid4(),
                user_id=uuid.UUID(user_id),
                ip_address=ip_address,
                user_agent=user_agent,
            )
        )

    async def _get_2fa_record(self, db: AsyncSession, user_id: str) -> Admin2FA:
        result = await db.execute(select(Admin2FA).where(Admin2FA.user_id == user_id))
        record = result.scalar_one_or_none()
        if not record:
            raise NotFoundError("2FA not configured for this account")
        return record
