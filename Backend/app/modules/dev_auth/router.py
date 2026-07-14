from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, ok
from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundError
from app.middleware.rate_limit import rate_limit_dev_login
from app.modules.dev_auth.schemas import (
    DevLoginRequest,
    DevLoginResponse,
    DevMeResponse,
)
from app.modules.dev_auth.service import DevAuthService
from app.modules.profiles.models import Profile

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/dev", tags=["dev-auth"])

_svc = DevAuthService()

_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "customer": [
        "read:own_profile",
        "read:products",
        "write:own_orders",
        "write:own_cart",
    ],
    "admin": [
        "read:own_profile",
        "read:products",
        "write:own_orders",
        "write:own_cart",
        "admin:read_all",
        "admin:write_products",
        "admin:write_orders",
        "admin:write_users",
        "admin:write_cms",
    ],
    "super_admin": [
        "read:own_profile",
        "read:products",
        "write:own_orders",
        "write:own_cart",
        "admin:read_all",
        "admin:write_products",
        "admin:write_orders",
        "admin:write_users",
        "admin:write_cms",
        "super_admin:manage_roles",
        "super_admin:force_logout",
        "super_admin:manage_settings",
    ],
}


def _check_dev_enabled() -> None:
    """Raise 404 if this endpoint is not enabled in the current environment."""
    enabled = settings.is_development or settings.ENABLE_DEV_AUTH
    if not enabled:
        raise NotFoundError("Not found")


@router.post(
    "/login",
    response_model=BaseSuccessResponse[DevLoginResponse],
    summary="[DEV ONLY] Authenticate with email/password and receive a Supabase JWT",
    description=(
        "**Development and QA use only.** Disabled in production. "
        "Authenticates against Supabase and verifies the user is an active admin "
        "in the application database. Returns the full session payload suitable "
        "for use with Postman collection variables."
    ),
    dependencies=[Depends(rate_limit_dev_login)],
)
async def dev_login(
    body: DevLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> BaseSuccessResponse[DevLoginResponse]:
    _check_dev_enabled()
    log.info("dev_auth_login_attempt", email=body.email)
    result = await _svc.login(db, body.email, body.password)
    return ok(result, ResponseCode.DEV_AUTH_LOGIN, "Authentication successful")


@router.get(
    "/me",
    response_model=BaseSuccessResponse[DevMeResponse],
    summary="[DEV ONLY] Inspect the current Bearer token",
    description=(
        "**Development and QA use only.** Decodes the Bearer token and returns "
        "the resolved user profile, role, and permissions. Useful for verifying "
        "that the correct token is being used in Postman."
    ),
)
async def dev_me(
    current_user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BaseSuccessResponse[DevMeResponse]:
    _check_dev_enabled()

    # Derive session expiry from the profile's updated_at as a best-effort proxy;
    # the JWT exp is not stored locally — callers can inspect it via jwt.io.
    permissions = _ROLE_PERMISSIONS.get(current_user.role, [])

    me = DevMeResponse(
        user_id=str(current_user.id),
        supabase_uid=str(current_user.id),
        email=current_user.email,
        role=current_user.role,
        is_active=current_user.is_active,
        session_expires_at=None,
        permissions=permissions,
    )
    return ok(me, ResponseCode.DEV_AUTH_ME, "Token is valid")
