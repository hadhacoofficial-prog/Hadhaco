"""
Shared FastAPI dependencies.

Provides:
  - get_db         → AsyncSession
  - get_redis      → aioredis.Redis
  - get_current_user          → Profile (any authenticated user)
  - get_current_user_optional → Profile | None (public endpoints that enrich authed users)
  - require_customer          → Profile (role: customer | admin | super_admin)
  - require_admin             → Profile (role: admin | super_admin; gated by admin 2FA
                                 session verification when the account has 2FA enabled)
  - require_super_admin       → Profile (role: super_admin only; same 2FA gating)
  - require_2fa_verified      → Profile (role: admin | super_admin; 2FA MUST be enabled
                                 and this session MUST have passed the TOTP challenge —
                                 used for extra-sensitive admin mutations)
  - require_admin_role        → Profile (role: admin | super_admin, NO 2FA gate — only
                                 for the 2FA bootstrap endpoints themselves, which must
                                 stay reachable before/while completing the challenge)

2FA session verification is backed by the `admin_sessions` table (see
app.modules.profiles.models.AdminSession), correlated to the caller via the
Supabase JWT's `session_id` claim. There is no separate session store —
this reuses the existing AdminSession architecture end to end.
"""

import json
import types
import uuid
from datetime import datetime

import redis.asyncio as aioredis
import structlog
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import UserRole
from app.core.database import get_db
from app.core.exceptions import AuthorizationError
from app.core.redis import get_redis, safe_redis_get, safe_redis_setex
from app.core.security import JWTPayload, oauth2_scheme, verify_supabase_jwt

# Forward declaration — resolved at runtime to avoid circular imports
_profile_repository = None

# Cached profiles expire after 60 s. Short enough that role/status changes
# propagate quickly; long enough to absorb repeated auth DB hits.
_PROFILE_CACHE_TTL = 60


def _get_profile_repository():
    global _profile_repository
    if _profile_repository is None:
        from app.modules.profiles.repository import ProfileRepository

        _profile_repository = ProfileRepository()
    return _profile_repository


def profile_cache_key(user_id: str) -> str:
    return f"profile:v1:{user_id}"


def _parse_profile_from_cache(data: dict):
    """Reconstruct a Profile-compatible namespace from cached JSON data."""
    return types.SimpleNamespace(
        id=uuid.UUID(data["id"]),
        email=data["email"],
        full_name=data.get("full_name"),
        phone=data.get("phone"),
        primary_image_id=(
            uuid.UUID(data["primary_image_id"])
            if data.get("primary_image_id")
            else None
        ),
        role=data["role"],
        is_active=data["is_active"],
        is_verified=data["is_verified"],
        deleted_at=(
            datetime.fromisoformat(data["deleted_at"])
            if data.get("deleted_at")
            else None
        ),
        created_at=(
            datetime.fromisoformat(data["created_at"])
            if data.get("created_at")
            else None
        ),
        updated_at=(
            datetime.fromisoformat(data["updated_at"])
            if data.get("updated_at")
            else None
        ),
    )


async def _cache_profile(redis: aioredis.Redis, profile) -> None:
    """Write profile fields to Redis via the circuit-breaker helper."""
    data = {
        "id": str(profile.id),
        "email": profile.email,
        "full_name": profile.full_name,
        "phone": profile.phone,
        "primary_image_id": (
            str(profile.primary_image_id) if profile.primary_image_id else None
        ),
        "role": profile.role,
        "is_active": profile.is_active,
        "is_verified": profile.is_verified,
        "deleted_at": profile.deleted_at.isoformat() if profile.deleted_at else None,
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }
    await safe_redis_setex(
        redis, profile_cache_key(str(profile.id)), _PROFILE_CACHE_TTL, json.dumps(data)
    )


async def _load_profile(user_id: str, db: AsyncSession, redis: aioredis.Redis):
    """
    Return the profile for *user_id*, checking Redis first.

    Cache hit  → returns a SimpleNamespace with all Profile fields (no DB hit).
    Cache miss → hits the DB, populates the cache, returns the ORM Profile.
    Redis down → circuit breaker skips Redis entirely after the first failure.
    """
    raw = await safe_redis_get(redis, profile_cache_key(user_id))
    if raw:
        return _parse_profile_from_cache(json.loads(raw))

    repo = _get_profile_repository()
    profile = await repo.get_by_id(db, user_id)
    if profile:
        await _cache_profile(redis, profile)
    return profile


async def get_jwt_payload(token: str = Depends(oauth2_scheme)) -> JWTPayload:
    """Verify the Supabase JWT once per request (FastAPI caches by dependable)."""
    return await verify_supabase_jwt(token)


async def get_current_user(
    payload: JWTPayload = Depends(get_jwt_payload),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """
    Verify the Supabase JWT, load the profile from Redis/DB, and return it.
    Raises 401 if the token is invalid or the profile does not exist/is inactive.
    """
    user_id: str = payload.sub

    profile = await _load_profile(user_id, db, redis)

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not profile.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
            headers={"X-Error-Code": "ACCOUNT_INACTIVE"},
        )

    structlog.contextvars.bind_contextvars(
        user_id=str(profile.id),
        user_email=profile.email or "",
    )

    return profile


async def get_current_user_optional(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """
    Attempt to load the current user from the Authorization header.
    Returns None instead of raising if the token is missing or invalid.
    Used by public endpoints that optionally enrich responses for logged-in users.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header.removeprefix("Bearer ").strip()
    try:
        payload: JWTPayload = await verify_supabase_jwt(token)
        user_id = payload.sub
        if not user_id:
            return None
        profile = await _load_profile(user_id, db, redis)
        if profile and profile.is_active:
            return profile
        return None
    except HTTPException:
        return None


def require_role(*roles: str):
    """
    Returns a dependency that enforces one of the given roles.
    Automatically includes all roles above in the hierarchy.
    """

    async def dependency(current_user=Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
                headers={"X-Required-Roles": ",".join(roles)},
            )
        return current_user

    return dependency


# Convenience role dependencies
require_customer = require_role(UserRole.CUSTOMER, UserRole.ADMIN, UserRole.SUPER_ADMIN)

# Role-only checks, with NO 2FA session gate. Only the 2FA bootstrap endpoints
# themselves (setup/verify/validate/status/disable/regenerate) may depend on
# these directly — every other admin route must use require_admin /
# require_super_admin / require_2fa_verified below so the 2FA gate applies.
require_admin_role = require_role(UserRole.ADMIN, UserRole.SUPER_ADMIN)
_require_super_admin_role = require_role(UserRole.SUPER_ADMIN)


async def _ensure_2fa_session(
    current_user,
    payload: JWTPayload,
    db: AsyncSession,
    *,
    required: bool,
):
    """
    Backend-enforced 2FA gate, backed by the `admin_sessions` table.

    If the account has 2FA enabled, this request's Supabase session must have
    already completed the TOTP challenge (POST /auth/admin/2fa/validate) —
    frontend routing/sessionStorage is never the source of truth. If the
    account has 2FA disabled, `required=False` callers (require_admin /
    require_super_admin) let it through unchanged; `required=True` callers
    (require_2fa_verified) instead mandate that 2FA be enabled at all.
    """
    from app.modules.auth.service import AuthService

    svc = AuthService()
    has_2fa = await svc.has_active_2fa(db, str(current_user.id))
    if not has_2fa:
        if required:
            raise AuthorizationError(
                "Two-factor authentication is required for this action",
                code="2FA_REQUIRED",
                data={"setup_required": True, "setup_url": "/admin/settings/security"},
            )
        return current_user

    verified = (
        payload.session_id is not None
        and await svc.is_admin_session_2fa_verified(
            db, str(current_user.id), payload.session_id
        )
    )
    if not verified:
        raise AuthorizationError(
            "Two-factor verification is required for this session",
            code="2FA_REQUIRED",
            data={"setup_required": False, "setup_url": "/admin/2fa"},
        )
    return current_user


async def require_admin(
    current_user=Depends(require_admin_role),
    payload: JWTPayload = Depends(get_jwt_payload),
    db: AsyncSession = Depends(get_db),
):
    return await _ensure_2fa_session(current_user, payload, db, required=False)


async def require_super_admin(
    current_user=Depends(_require_super_admin_role),
    payload: JWTPayload = Depends(get_jwt_payload),
    db: AsyncSession = Depends(get_db),
):
    return await _ensure_2fa_session(current_user, payload, db, required=False)


async def require_2fa_verified(
    current_user=Depends(require_admin_role),
    payload: JWTPayload = Depends(get_jwt_payload),
    db: AsyncSession = Depends(get_db),
):
    """
    Stricter than require_admin: 2FA MUST be enabled (not just optionally
    verified) and this session MUST have passed the TOTP challenge. Used for
    admin mutations that mandate 2FA regardless of the account's own choice.
    """
    return await _ensure_2fa_session(current_user, payload, db, required=True)
