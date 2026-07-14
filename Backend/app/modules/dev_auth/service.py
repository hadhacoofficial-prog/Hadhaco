from __future__ import annotations

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import UserRole
from app.core.exceptions import AuthenticationError, AuthorizationError, NotFoundError
from app.modules.dev_auth.schemas import (
    DevLoginResponse,
    DevSessionPayload,
    DevUserPayload,
)
from app.modules.profiles.repository import ProfileRepository

log = structlog.get_logger(__name__)

_ADMIN_ROLES = {UserRole.ADMIN, UserRole.SUPER_ADMIN}

_repo = ProfileRepository()


def _split_name(full_name: str | None) -> tuple[str | None, str | None]:
    if not full_name:
        return None, None
    parts = full_name.strip().split(" ", 1)
    return parts[0], parts[1] if len(parts) > 1 else None


class DevAuthService:
    async def login(
        self, db: AsyncSession, email: str, password: str
    ) -> DevLoginResponse:
        supabase_data = await self._supabase_sign_in(email, password)

        supabase_user = supabase_data.get("user") or {}
        user_id: str = supabase_user.get("id", "")

        profile = await _repo.get_by_id(db, user_id)
        if not profile:
            log.warning("dev_auth_user_not_in_db", user_id=user_id, email=email)
            raise NotFoundError("User not found in application database")

        if not profile.is_active:
            log.warning("dev_auth_inactive", user_id=user_id, email=email)
            raise AuthorizationError("Account is inactive", code="ACCOUNT_INACTIVE")

        if profile.role not in _ADMIN_ROLES:
            log.warning(
                "dev_auth_non_admin", user_id=user_id, role=profile.role, email=email
            )
            raise AuthorizationError(
                f"Dev auth is restricted to admin accounts. Role '{profile.role}' is not permitted.",
                code="DEV_AUTH_ADMIN_ONLY",
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
                access_token=supabase_data["access_token"],
                refresh_token=supabase_data["refresh_token"],
                expires_in=supabase_data["expires_in"],
                expires_at=int(supabase_data["expires_at"]),
                token_type=supabase_data.get("token_type", "bearer"),
            ),
        )

    async def _supabase_sign_in(self, email: str, password: str) -> dict:
        url = f"{settings.SUPABASE_URL}/auth/v1/token?grant_type=password"
        headers = {
            "apikey": settings.supabase_anon_key,
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                url, headers=headers, json={"email": email, "password": password}
            )

        if resp.status_code in (400, 401, 422):
            body = resp.json()
            log.warning(
                "dev_auth_supabase_rejected",
                email=email,
                status=resp.status_code,
                error=body.get("error_description") or body.get("msg"),
            )
            raise AuthenticationError("Invalid email or password")

        if resp.status_code != 200:
            log.error("dev_auth_supabase_error", status=resp.status_code)
            raise AuthenticationError("Authentication service error")

        return resp.json()
