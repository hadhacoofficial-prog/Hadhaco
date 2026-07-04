import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditLog


def _as_uuid(value: uuid.UUID | str | None) -> uuid.UUID | None:
    if value is None or isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(value)


class AuditService:
    async def log(
        self,
        db: AsyncSession,
        *,
        actor_id: uuid.UUID | str | None,
        action: str,
        resource_type: str,
        resource_id: uuid.UUID | str | None = None,
        metadata: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        actor_email: str | None = None,
        actor_role: str | None = None,
        old_value: dict[str, Any] | None = None,
        new_value: dict[str, Any] | None = None,
        request_id: str | None = None,
        source: str = "api",
    ) -> AuditLog:
        entry = AuditLog(
            id=uuid.uuid4(),
            actor_id=_as_uuid(actor_id),
            actor_email=actor_email,
            actor_role=actor_role,
            action=action,
            resource_type=resource_type,
            resource_id=_as_uuid(resource_id),
            old_value=old_value,
            new_value=new_value,
            meta=metadata,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            source=source,
        )
        db.add(entry)
        await db.flush()
        return entry
