from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, ok
from app.core.database import get_db
from app.core.dependencies import (
    get_current_user,
    require_admin,
    require_super_admin,
)
from app.middleware.rate_limit import rate_limit_auth
from app.modules.auth.schemas import (
    AdminSessionResponse,
    Setup2FAResponse,
    Validate2FARequest,
    Validate2FAResponse,
    Verify2FARequest,
    Verify2FAResponse,
    VerifyTokenResponse,
)
from app.modules.auth.service import AuthService
from app.modules.profiles.models import Profile

router = APIRouter(prefix="/auth", tags=["auth"])
_svc = AuthService()


@router.post(
    "/verify-token",
    response_model=BaseSuccessResponse[VerifyTokenResponse],
    summary="Validate a Supabase JWT and return the profile",
)
async def verify_token(
    current_user: Profile = Depends(get_current_user),
) -> BaseSuccessResponse[VerifyTokenResponse]:
    return ok(
        VerifyTokenResponse(
            id=current_user.id,
            email=current_user.email,
            full_name=current_user.full_name,
            role=current_user.role,
            is_active=current_user.is_active,
            avatar_url=current_user.avatar_url,
        ),
        ResponseCode.AUTH_TOKEN_VERIFIED,
        "Token verified successfully",
    )


@router.post(
    "/logout",
    response_model=BaseSuccessResponse[None],
    summary="Revoke the current Supabase session",
)
async def logout(
    current_user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BaseSuccessResponse[None]:
    await _svc.logout(db, str(current_user.id))
    return ok(None, ResponseCode.AUTH_LOGOUT_SUCCESS, "Logged out successfully")


@router.post(
    "/force-logout/{user_id}",
    response_model=BaseSuccessResponse[None],
    summary="Force logout any user (super_admin only)",
)
async def force_logout(
    user_id: str,
    _: Profile = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> BaseSuccessResponse[None]:
    await _svc.force_logout(db, user_id)
    return ok(None, ResponseCode.AUTH_FORCE_LOGOUT_SUCCESS, f"User {user_id} logged out")


# ── Admin 2FA endpoints ────────────────────────────────────────────────────────

@router.post(
    "/admin/2fa/setup",
    response_model=BaseSuccessResponse[Setup2FAResponse],
    summary="Generate TOTP secret and QR code for admin 2FA setup",
)
async def setup_2fa(
    current_user: Profile = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> BaseSuccessResponse[Setup2FAResponse]:
    data = await _svc.setup_2fa(db, str(current_user.id), current_user.email)
    return ok(Setup2FAResponse(**data), ResponseCode.AUTH_2FA_SETUP, "2FA setup initiated")


@router.post(
    "/admin/2fa/verify",
    response_model=BaseSuccessResponse[Verify2FAResponse],
    summary="Verify TOTP code and activate 2FA",
)
async def verify_2fa(
    body: Verify2FARequest,
    current_user: Profile = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> BaseSuccessResponse[Verify2FAResponse]:
    backup_codes = await _svc.verify_and_activate_2fa(
        db, str(current_user.id), body.totp_code
    )
    return ok(
        Verify2FAResponse(
            message="2FA activated successfully. Save your backup codes — they will not be shown again.",
            backup_codes=backup_codes,
        ),
        ResponseCode.AUTH_2FA_VERIFIED,
        "2FA activated successfully",
    )


@router.post(
    "/admin/2fa/validate",
    response_model=BaseSuccessResponse[Validate2FAResponse],
    summary="Validate TOTP code on admin login",
)
async def validate_2fa(
    body: Validate2FARequest,
    current_user: Profile = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> BaseSuccessResponse[Validate2FAResponse]:
    valid = await _svc.validate_2fa(db, str(current_user.id), body.totp_code)
    return ok(Validate2FAResponse(valid=valid), ResponseCode.AUTH_2FA_VALID, "2FA code validated")
