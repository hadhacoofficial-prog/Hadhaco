from __future__ import annotations

import time

import redis.asyncio as aioredis
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import UserRole
from app.core.exceptions import AuthorizationError
from app.modules.auth.identity_service import IdentityService
from app.modules.dev_auth.schemas import (
    DevLoginResponse,
    DevSessionPayload,
    DevUserPayload,
)

log = structlog.get_logger(__name__)

_ADMIN_ROLES = {UserRole.ADMIN, UserRole.SUPER_ADMIN}

_identity = IdentityService()


def _split_name(full_name: str | None) -> tuple[str | None, str | None]:
    if not full_name:
        return None, None
    parts = full_name.strip().split(" ", 1)
    return parts[0], parts[1] if len(parts) > 1 else None


class DevAuthService:
    async def login(
        self,
        db: AsyncSession,
        redis: aioredis.Redis,
        email: str,
        password: str,
        *,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> DevLoginResponse:
        """Password login that returns the tokens in the body (for Postman/QA),
        unlike the cookie-only production endpoints."""
        profile = await _identity.authenticate_password(
            db, redis, email=email, password=password, ip=ip
        )
        user_id = str(profile.id)

        if profile.role not in _ADMIN_ROLES:
            log.warning(
                "dev_auth_non_admin", user_id=user_id, role=profile.role, email=email
            )
            raise AuthorizationError(
                f"Dev auth is restricted to admin accounts. Role '{profile.role}' is not permitted.",
                code="DEV_AUTH_ADMIN_ONLY",
            )

        issued = await _identity.issue_session(
            db, profile, surface="admin", ip=ip, user_agent=user_agent
        )
        log.info("dev_auth_success", user_id=user_id, email=email, role=profile.role)

        first_name, last_name = _split_name(profile.full_name)
        return DevLoginResponse(
            user=DevUserPayload(
                id=profile.id,
                email=profile.email,
                role=profile.role,
                full_name=profile.full_name,
                first_name=first_name,
                last_name=last_name,
            ),
            session=DevSessionPayload(
                access_token=issued.access_token,
                refresh_token=issued.refresh_token or "",
                expires_in=issued.access_ttl,
                expires_at=int(time.time()) + issued.access_ttl,
                token_type="bearer",
            ),
        )
