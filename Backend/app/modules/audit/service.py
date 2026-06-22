import json
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditLog


class AuditService:
    async def log(
        self,
        db: AsyncSession,
        *,
        actor_id: str | None,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            id=uuid.uuid4(),
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            meta=json.dumps(metadata) if metadata else None,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.add(entry)
        await db.flush()
        return entry
