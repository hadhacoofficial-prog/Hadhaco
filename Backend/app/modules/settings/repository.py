from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_value, encrypt_value
from app.modules.settings.models import FeatureFlag, NotificationProviderSetting


class SettingsRepository:
    async def get_flag(self, db: AsyncSession, key: str) -> FeatureFlag | None:
        result = await db.execute(select(FeatureFlag).where(FeatureFlag.key == key))
        return result.scalar_one_or_none()

    async def list_flags(self, db: AsyncSession) -> list[FeatureFlag]:
        result = await db.execute(select(FeatureFlag).order_by(FeatureFlag.key))
        return list(result.scalars().all())

    async def upsert_flag(
        self,
        db: AsyncSession,
        *,
        key: str,
        value: bool,
        description: str | None,
        updated_by: uuid.UUID | None,
    ) -> FeatureFlag:
        stmt = (
            insert(FeatureFlag)
            .values(
                key=key,
                value=value,
                description=description,
                updated_by=updated_by,
                updated_at=datetime.now(UTC),
            )
            .on_conflict_do_update(
                index_elements=["key"],
                set_={
                    "value": value,
                    "description": description,
                    "updated_by": updated_by,
                    "updated_at": datetime.now(UTC),
                },
            )
            .returning(FeatureFlag)
        )
        result = await db.execute(stmt)
        await db.flush()
        return result.scalar_one()

    # ── Notification provider settings ──────────────────────────────────────

    async def list_provider_settings(
        self, db: AsyncSession, *, provider: str
    ) -> list[NotificationProviderSetting]:
        result = await db.execute(
            select(NotificationProviderSetting).where(
                NotificationProviderSetting.provider == provider
            )
        )
        return list(result.scalars().all())

    async def get_provider_config(
        self, db: AsyncSession, *, provider: str
    ) -> dict[str, str]:
        """Return decrypted key -> value for internal provider use only.

        Never expose this dict's values directly in an API response.
        """
        rows = await self.list_provider_settings(db, provider=provider)
        config: dict[str, str] = {}
        for row in rows:
            if row.is_secret:
                if row.value_encrypted:
                    config[row.key] = decrypt_value(row.value_encrypted)
            elif row.value_plain is not None:
                config[row.key] = row.value_plain
        return config

    async def upsert_provider_setting(
        self,
        db: AsyncSession,
        *,
        provider: str,
        key: str,
        value: str,
        is_secret: bool,
        updated_by: uuid.UUID | None,
    ) -> NotificationProviderSetting:
        values = {
            "provider": provider,
            "key": key,
            "value_encrypted": encrypt_value(value) if is_secret else None,
            "value_plain": None if is_secret else value,
            "is_secret": is_secret,
            "updated_by": updated_by,
            "updated_at": datetime.now(UTC),
        }
        stmt = (
            insert(NotificationProviderSetting)
            .values(**values)
            .on_conflict_do_update(
                constraint="uq_provider_setting",
                set_={k: v for k, v in values.items() if k not in ("provider", "key")},
            )
            .returning(NotificationProviderSetting)
        )
        result = await db.execute(stmt)
        await db.flush()
        return result.scalar_one()
