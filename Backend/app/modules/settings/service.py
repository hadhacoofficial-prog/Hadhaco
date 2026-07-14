from __future__ import annotations

import uuid
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings as app_settings
from app.modules.settings.models import FeatureFlag
from app.modules.settings.repository import SettingsRepository
from app.modules.settings.schemas import FeatureFlagUpdate

_repo = SettingsRepository()

# Which keys are secret per provider — controls encryption + response masking.
_SECRET_KEYS: dict[str, set[str]] = {
    "email": {"api_key"},
    "whatsapp": {"access_token", "webhook_secret"},
}


class SettingsService:
    async def list_flags(self, db: AsyncSession) -> list[FeatureFlag]:
        return await _repo.list_flags(db)

    async def set_flag(
        self,
        db: AsyncSession,
        *,
        key: str,
        data: FeatureFlagUpdate,
        updated_by: uuid.UUID,
    ) -> FeatureFlag:
        flag = await _repo.upsert_flag(
            db,
            key=key,
            value=data.value,
            description=data.description,
            updated_by=updated_by,
        )
        await db.commit()
        return flag

    @staticmethod
    async def is_feature_enabled(db: AsyncSession, key: str) -> bool:
        flag = await _repo.get_flag(db, key)
        return flag.value if flag else False

    async def get_flag(self, db: AsyncSession, *, key: str) -> FeatureFlag | None:
        return await _repo.get_flag(db, key)

    # ── Notification provider settings ──────────────────────────────────────

    @staticmethod
    def _mask(value: str) -> str:
        if len(value) <= 4:
            return "••••"
        return f"••••{value[-4:]}"

    async def get_provider_settings(
        self, db: AsyncSession, *, provider: str
    ) -> dict[str, str | None]:
        """Return settings for admin display — secret values are masked, never
        returned decrypted."""
        rows = await _repo.list_provider_settings(db, provider=provider)
        result: dict[str, str | None] = {}
        for row in rows:
            if row.is_secret:
                result[row.key] = (
                    self._mask(_decrypt(row.value_encrypted))
                    if row.value_encrypted
                    else None
                )
            else:
                result[row.key] = row.value_plain
        return result

    async def update_provider_settings(
        self,
        db: AsyncSession,
        *,
        provider: str,
        data: dict[str, str],
        updated_by: uuid.UUID,
    ) -> dict[str, str | None]:
        secret_keys = _SECRET_KEYS.get(provider, set())
        for key, value in data.items():
            if value is None or value == "":
                continue
            await _repo.upsert_provider_setting(
                db,
                provider=provider,
                key=key,
                value=value,
                is_secret=key in secret_keys,
                updated_by=updated_by,
            )
        await db.commit()
        return await self.get_provider_settings(db, provider=provider)

    # ── Provider health ──────────────────────────────────────────────────────

    async def get_provider_health(
        self, db: AsyncSession, *, provider: str
    ) -> dict[str, Any]:
        from app.modules.notifications.repository import NotificationRepository

        stats = await NotificationRepository().get_provider_health_stats(
            db, channel=provider
        )
        connection_status, connection_detail = await self._probe_connection(
            db, provider=provider
        )
        webhook_url: str | None = None
        webhook_verification_configured = False
        if provider == "whatsapp":
            webhook_url = f"{app_settings.API_BASE_URL}{app_settings.API_V1_PREFIX}/notifications/webhooks/whatsapp"
            config = await _repo.get_provider_config(db, provider="whatsapp")
            verify_token = (
                config.get("verify_token") or app_settings.WHATSAPP_VERIFY_TOKEN
            )
            webhook_verification_configured = bool(verify_token)
        return {
            "provider": provider,
            "connection_status": connection_status,
            "connection_detail": connection_detail,
            "webhook_url": webhook_url,
            "webhook_verification_configured": webhook_verification_configured,
            **stats,
        }

    # ── WhatsApp template sync ───────────────────────────────────────────────

    async def list_whatsapp_templates(self, db: AsyncSession) -> list[dict[str, Any]]:
        """Read-only passthrough to Meta's approved WhatsApp message templates."""
        config = await _repo.get_provider_config(db, provider="whatsapp")
        access_token = config.get("access_token") or app_settings.WHATSAPP_ACCESS_TOKEN
        waba_id = config.get("waba_id") or app_settings.WHATSAPP_BUSINESS_ACCOUNT_ID
        api_version = config.get("api_version") or app_settings.WHATSAPP_API_VERSION
        if not access_token or not waba_id:
            return []

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"https://graph.facebook.com/{api_version}/{waba_id}/message_templates",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        return [
            {
                "name": t.get("name", ""),
                "language": t.get("language", ""),
                "status": t.get("status", "UNKNOWN"),
                "category": t.get("category", ""),
            }
            for t in data
        ]

    async def _probe_connection(
        self, db: AsyncSession, *, provider: str
    ) -> tuple[str, str | None]:
        config = await _repo.get_provider_config(db, provider=provider)
        try:
            if provider == "email":
                api_key = config.get("api_key") or app_settings.RESEND_API_KEY
                if not api_key:
                    return "not_configured", "No Resend API key configured"
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(
                        "https://api.resend.com/domains",
                        headers={"Authorization": f"Bearer {api_key}"},
                    )
                if resp.status_code == 200:
                    return "connected", None
                return "error", f"Resend returned {resp.status_code}"

            if provider == "whatsapp":
                access_token = (
                    config.get("access_token") or app_settings.WHATSAPP_ACCESS_TOKEN
                )
                phone_number_id = (
                    config.get("phone_number_id")
                    or app_settings.WHATSAPP_PHONE_NUMBER_ID
                )
                api_version = (
                    config.get("api_version") or app_settings.WHATSAPP_API_VERSION
                )
                if not access_token or not phone_number_id:
                    return "not_configured", "WhatsApp credentials not configured"
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(
                        f"https://graph.facebook.com/{api_version}/{phone_number_id}",
                        headers={"Authorization": f"Bearer {access_token}"},
                    )
                if resp.status_code == 200:
                    return "connected", None
                return "error", f"Meta Graph API returned {resp.status_code}"

            return "not_configured", f"Unknown provider: {provider}"
        except Exception as exc:
            return "error", str(exc)


def _decrypt(ciphertext: str) -> str:
    from app.core.security import decrypt_value

    return decrypt_value(ciphertext)
