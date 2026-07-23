import uuid

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, ok
from app.core.database import get_db
from app.core.dependencies import (
    get_current_user,
    get_jwt_payload,
    require_admin,
    require_admin_role,
    require_super_admin,
)
from app.core.exceptions import AuthorizationError, NotFoundError
from app.core.redis import get_redis
from app.core.security import JWTPayload
from app.middleware.rate_limit import (
    get_client_ip,
    rate_limit_2fa_setup,
    rate_limit_2fa_validate,
    rate_limit_2fa_verify,
    rate_limit_admin_sessions,
    rate_limit_force_logout,
    rate_limit_logout,
    rate_limit_verify_token,
)
from app.modules.audit.service import AuditService
from app.modules.auth.schemas import (
    AdminSessionListResponse,
    AdminSessionOut,
    Disable2FARequest,
    RegenerateBackupCodesRequest,
    RegenerateBackupCodesResponse,
    RevokeSessionResponse,
    Setup2FAResponse,
    TwoFactorStatusResponse,
    Validate2FARequest,
    Validate2FAResponse,
    Verify2FARequest,
    Verify2FAResponse,
    VerifyTokenResponse,
)
from app.modules.auth.service import AuthService
from app.modules.media.repository import ImageRepository
from app.modules.profiles.models import Profile

router = APIRouter(prefix="/auth", tags=["auth"])
_svc = AuthService()
_image_repo = ImageRepository()
_audit = AuditService()
_log = structlog.get_logger(__name__)

# Single toggle gating every admin security-notification email — off by
# default. Managed the same way as every other flag (Settings > Feature
# Flags), no separate config surface.
ADMIN_LOGIN_NOTIFICATIONS_FLAG = "admin_login_notifications"


def _client_meta(request: Request) -> tuple[str, str | None]:
    # get_client_ip honors X-Real-IP/X-Forwarded-For from the reverse proxy —
    # request.client.host alone would record the proxy's own address for
    # every request in any deployment that sits behind one, silently
    # breaking new-location detection and the audit trail's forensic value.
    return get_client_ip(request), request.headers.get("user-agent")


async def _notify_security_event(
    db: AsyncSession, current_user: Profile, subject: str, message: str
) -> None:
    """
    Best-effort security-alert email via the existing Resend/notification
    dispatcher — gated behind ADMIN_LOGIN_NOTIFICATIONS_FLAG (off by
    default). Never raises: a delivery failure must not block the request
    that triggered it.
    """
    from app.modules.notifications.dispatcher import dispatcher
    from app.modules.notifications.dto import EmailPayload
    from app.modules.settings.service import SettingsService

    try:
        if not await SettingsService.is_feature_enabled(
            db, ADMIN_LOGIN_NOTIFICATIONS_FLAG
        ):
            return
        from app.core.config import settings as _settings

        payload = EmailPayload(
            to=current_user.email,
            subject=subject,
            html=f"<p>{message}</p><p>If this wasn't you, revoke your sessions immediately from Settings &rarr; Security and re-enable 2FA.</p>",
            api_key=_settings.RESEND_API_KEY,
            from_name=_settings.EMAIL_FROM_NAME,
            from_email=_settings.EMAIL_FROM,
            reply_to=_settings.EMAIL_REPLY_TO,
        )
        await dispatcher.send_email(payload)
    except Exception:
        # Best-effort: a delivery failure must never block the request that
        # triggered it, but silently swallowing it entirely would let every
        # notification quietly stop working (e.g. a Resend outage or a typo)
        # with no way to notice. Log it; never re-raise.
        _log.warning(
            "admin_security_notification_failed",
            actor_id=str(current_user.id),
            subject=subject,
            exc_info=True,
        )


@router.post(
    "/verify-token",
    response_model=BaseSuccessResponse[VerifyTokenResponse],
    summary="Validate a Supabase JWT and return the profile",
    dependencies=[Depends(rate_limit_verify_token)],
)
async def verify_token(
    request: Request,
    current_user: Profile = Depends(get_current_user),
    payload: JWTPayload = Depends(get_jwt_payload),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> BaseSuccessResponse[VerifyTokenResponse]:
    # NOTE: the admin frontend never actually calls /auth/verify-token — the
    # real per-page-load call is GET /me (see profiles/router.py), which is
    # where track_admin_login_if_new_session is wired in. Kept here too
    # (harmless, correct, just currently unreached by this frontend) in case
    # some other client legitimately uses this endpoint per its own docs.
    if current_user.role in ("admin", "super_admin") and payload.session_id:
        ip, ua = _client_meta(request)
        await _svc.track_admin_login_if_new_session(
            db,
            redis,
            user_id=str(current_user.id),
            user_email=current_user.email,
            user_role=current_user.role,
            session_id=payload.session_id,
            ip_address=ip,
            user_agent=ua,
        )
    avatar_url = None
    if current_user.primary_image_id:
        # get_primary_variant_urls looks up by owner_id (the profile's own
        # id), not by primary_image_id (the Image row's own id).
        urls = await _image_repo.get_primary_variant_urls(
            db,
            "user",
            [current_user.id],
            variant_name="avatar",
            breakpoint="all",
        )
        avatar_url = urls.get(current_user.id)
    return ok(
        VerifyTokenResponse(
            id=current_user.id,
            email=current_user.email,
            full_name=current_user.full_name,
            role=current_user.role,
            is_active=current_user.is_active,
            avatar_url=avatar_url,
        ),
        ResponseCode.AUTH_TOKEN_VERIFIED,
        "Token verified successfully",
    )


@router.post(
    "/logout",
    response_model=BaseSuccessResponse[None],
    summary="Revoke the current Supabase session",
    dependencies=[Depends(rate_limit_logout)],
)
async def logout(
    request: Request,
    current_user: Profile = Depends(get_current_user),
    payload: JWTPayload = Depends(get_jwt_payload),
    db: AsyncSession = Depends(get_db),
) -> BaseSuccessResponse[None]:
    await _svc.logout(db, str(current_user.id))
    await _svc.clear_admin_session_2fa(db, str(current_user.id), payload.session_id)
    if current_user.role in ("admin", "super_admin"):
        ip, ua = _client_meta(request)
        await _audit.log(
            db,
            actor_id=str(current_user.id),
            actor_email=current_user.email,
            actor_role=current_user.role,
            action="admin_logout",
            resource_type="profile",
            resource_id=str(current_user.id),
            ip_address=ip,
            user_agent=ua,
        )
    return ok(None, ResponseCode.AUTH_LOGOUT_SUCCESS, "Logged out successfully")


@router.post(
    "/force-logout/{user_id}",
    response_model=BaseSuccessResponse[None],
    summary="Force logout any user (super_admin only)",
    dependencies=[Depends(rate_limit_force_logout)],
)
async def force_logout(
    user_id: uuid.UUID,
    request: Request,
    actor: Profile = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> BaseSuccessResponse[None]:
    user_id_str = str(user_id)
    await _svc.force_logout(db, user_id_str)
    await _svc.clear_all_admin_sessions_2fa(db, user_id_str)
    ip, ua = _client_meta(request)
    await _audit.log(
        db,
        actor_id=str(actor.id),
        actor_email=actor.email,
        actor_role=actor.role,
        action="admin_force_logout",
        resource_type="profile",
        resource_id=user_id_str,
        ip_address=ip,
        user_agent=ua,
    )
    return ok(
        None, ResponseCode.AUTH_FORCE_LOGOUT_SUCCESS, f"User {user_id} logged out"
    )


# ── Admin 2FA endpoints ────────────────────────────────────────────────────────


@router.post(
    "/admin/2fa/setup",
    response_model=BaseSuccessResponse[Setup2FAResponse],
    summary="Generate TOTP secret and QR code for admin 2FA setup",
    dependencies=[Depends(rate_limit_2fa_setup)],
)
async def setup_2fa(
    request: Request,
    current_user: Profile = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
) -> BaseSuccessResponse[Setup2FAResponse]:
    data = await _svc.setup_2fa(db, str(current_user.id), current_user.email)
    ip, ua = _client_meta(request)
    await _audit.log(
        db,
        actor_id=str(current_user.id),
        actor_email=current_user.email,
        actor_role=current_user.role,
        action="2fa_setup_initiated",
        resource_type="admin_2fa",
        resource_id=str(current_user.id),
        ip_address=ip,
        user_agent=ua,
    )
    return ok(
        Setup2FAResponse(**data), ResponseCode.AUTH_2FA_SETUP, "2FA setup initiated"
    )


@router.post(
    "/admin/2fa/verify",
    response_model=BaseSuccessResponse[Verify2FAResponse],
    summary="Verify TOTP code and activate 2FA",
    dependencies=[Depends(rate_limit_2fa_verify)],
)
async def verify_2fa(
    body: Verify2FARequest,
    request: Request,
    current_user: Profile = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
) -> BaseSuccessResponse[Verify2FAResponse]:
    backup_codes = await _svc.verify_and_activate_2fa(
        db, str(current_user.id), body.totp_code
    )
    ip, ua = _client_meta(request)
    await _audit.log(
        db,
        actor_id=str(current_user.id),
        actor_email=current_user.email,
        actor_role=current_user.role,
        action="2fa_enabled",
        resource_type="admin_2fa",
        resource_id=str(current_user.id),
        ip_address=ip,
        user_agent=ua,
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
    dependencies=[Depends(rate_limit_2fa_validate)],
)
async def validate_2fa(
    body: Validate2FARequest,
    request: Request,
    current_user: Profile = Depends(require_admin_role),
    payload: JWTPayload = Depends(get_jwt_payload),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> BaseSuccessResponse[Validate2FAResponse]:
    user_id = str(current_user.id)
    ip, ua = _client_meta(request)

    # Account-level lockout — independent of the per-IP rate limiter, so
    # rotating source IPs can't be used to grind through TOTP/backup codes
    # for one specific stolen-token account.
    if await _svc.is_2fa_locked_out(redis, user_id):
        await _audit.log(
            db,
            actor_id=user_id,
            actor_email=current_user.email,
            actor_role=current_user.role,
            action="2fa_locked_out",
            resource_type="admin_2fa",
            resource_id=user_id,
            ip_address=ip,
            user_agent=ua,
        )
        raise AuthorizationError(
            "Too many failed verification attempts. Try again later.",
            code="2FA_LOCKED",
        )

    valid, method = await _svc.validate_2fa_detailed(db, user_id, body.totp_code)

    if valid:
        await _svc.clear_2fa_failures(redis, user_id)
        # Check against sessions that exist *before* this login's own row is
        # created/updated below, otherwise it would always match itself.
        is_new_device = await _svc.is_new_device(db, user_id, ip, ua)
        if payload.session_id:
            await _svc.mark_admin_session_2fa_verified(
                db, user_id, payload.session_id, ip, ua
            )
        if is_new_device:
            await _notify_security_event(
                db,
                current_user,
                "New sign-in to your Hadha admin account",
                f"A new sign-in to your admin account was just verified from IP {ip}.",
            )
        await _audit.log(
            db,
            actor_id=user_id,
            actor_email=current_user.email,
            actor_role=current_user.role,
            action="2fa_verify_success",
            resource_type="admin_2fa",
            resource_id=user_id,
            metadata={"method": method},
            ip_address=ip,
            user_agent=ua,
        )
        if method == "backup_code":
            await _audit.log(
                db,
                actor_id=user_id,
                actor_email=current_user.email,
                actor_role=current_user.role,
                action="2fa_backup_code_used",
                resource_type="admin_2fa",
                resource_id=user_id,
                ip_address=ip,
                user_agent=ua,
            )
    else:
        failure_count = await _svc.record_2fa_failure(redis, user_id)
        await _audit.log(
            db,
            actor_id=user_id,
            actor_email=current_user.email,
            actor_role=current_user.role,
            action="2fa_verify_failed",
            resource_type="admin_2fa",
            resource_id=user_id,
            # method == "replay" means the code was cryptographically valid
            # but already consumed this time-step — a materially different
            # signal (a captured/intercepted code) than a plain wrong guess.
            metadata={
                "failure_count": failure_count,
                "reason": method or "invalid_code",
            },
            ip_address=ip,
            user_agent=ua,
        )

    return ok(
        Validate2FAResponse(valid=valid),
        ResponseCode.AUTH_2FA_VALID,
        "2FA code validated",
    )


@router.get(
    "/admin/2fa/status",
    response_model=BaseSuccessResponse[TwoFactorStatusResponse],
    summary="Get 2FA status for the current admin",
)
async def get_2fa_status(
    current_user: Profile = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
) -> BaseSuccessResponse[TwoFactorStatusResponse]:
    data = await _svc.get_2fa_status(db, str(current_user.id))
    return ok(
        TwoFactorStatusResponse(**data),
        ResponseCode.AUTH_2FA_SETUP,
        "2FA status fetched",
    )


@router.post(
    "/admin/2fa/disable",
    response_model=BaseSuccessResponse[None],
    summary="Disable 2FA for the current admin",
    dependencies=[Depends(rate_limit_2fa_verify)],
)
async def disable_2fa(
    body: Disable2FARequest,
    request: Request,
    current_user: Profile = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
) -> BaseSuccessResponse[None]:
    await _svc.disable_2fa(db, str(current_user.id), body.totp_code)
    ip, ua = _client_meta(request)
    await _audit.log(
        db,
        actor_id=str(current_user.id),
        actor_email=current_user.email,
        actor_role=current_user.role,
        action="2fa_disabled",
        resource_type="admin_2fa",
        resource_id=str(current_user.id),
        ip_address=ip,
        user_agent=ua,
    )
    await _notify_security_event(
        db,
        current_user,
        "Two-factor authentication disabled",
        "Two-factor authentication was just disabled on your Hadha admin account.",
    )
    return ok(None, ResponseCode.AUTH_2FA_VERIFIED, "2FA disabled successfully")


@router.post(
    "/admin/2fa/backup-codes/regenerate",
    response_model=BaseSuccessResponse[RegenerateBackupCodesResponse],
    summary="Regenerate backup codes for the current admin",
    dependencies=[Depends(rate_limit_2fa_verify)],
)
async def regenerate_backup_codes(
    body: RegenerateBackupCodesRequest,
    request: Request,
    current_user: Profile = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
) -> BaseSuccessResponse[RegenerateBackupCodesResponse]:
    codes = await _svc.regenerate_backup_codes(db, str(current_user.id), body.totp_code)
    ip, ua = _client_meta(request)
    await _audit.log(
        db,
        actor_id=str(current_user.id),
        actor_email=current_user.email,
        actor_role=current_user.role,
        action="2fa_backup_codes_regenerated",
        resource_type="admin_2fa",
        resource_id=str(current_user.id),
        ip_address=ip,
        user_agent=ua,
    )
    await _notify_security_event(
        db,
        current_user,
        "Backup codes regenerated",
        "Your two-factor backup codes were just regenerated — all previous codes are now invalid.",
    )
    return ok(
        RegenerateBackupCodesResponse(
            message="Backup codes regenerated. Save them — they will not be shown again.",
            backup_codes=codes,
        ),
        ResponseCode.AUTH_2FA_VERIFIED,
        "Backup codes regenerated",
    )


# ── Admin session dashboard ───────────────────────────────────────────────────


@router.get(
    "/admin/sessions",
    response_model=BaseSuccessResponse[AdminSessionListResponse],
    summary="List this admin's active sessions",
    dependencies=[Depends(rate_limit_admin_sessions)],
)
async def list_admin_sessions(
    current_user: Profile = Depends(require_admin),
    payload: JWTPayload = Depends(get_jwt_payload),
    db: AsyncSession = Depends(get_db),
) -> BaseSuccessResponse[AdminSessionListResponse]:
    rows = await _svc.list_admin_sessions(db, str(current_user.id))
    sessions = []
    for row in rows:
        item = AdminSessionOut.model_validate(row)
        item.is_current = row.supabase_session_id == payload.session_id
        sessions.append(item)
    return ok(
        AdminSessionListResponse(sessions=sessions),
        ResponseCode.AUTH_SESSIONS_LISTED,
        "Sessions fetched successfully",
    )


@router.delete(
    "/admin/sessions/{session_row_id}",
    response_model=BaseSuccessResponse[RevokeSessionResponse],
    summary="Revoke one admin session",
    dependencies=[Depends(rate_limit_admin_sessions)],
)
async def revoke_admin_session(
    session_row_id: uuid.UUID,
    request: Request,
    current_user: Profile = Depends(require_admin),
    payload: JWTPayload = Depends(get_jwt_payload),
    db: AsyncSession = Depends(get_db),
) -> BaseSuccessResponse[RevokeSessionResponse]:
    deleted, was_current = await _svc.revoke_admin_session(
        db,
        str(current_user.id),
        str(session_row_id),
        current_session_id=payload.session_id,
    )
    if was_current:
        raise AuthorizationError(
            'Can\'t revoke your current session this way — use "Log out" '
            'or "Log out all sessions" instead.',
            code="CANNOT_REVOKE_CURRENT_SESSION",
        )
    if not deleted:
        raise NotFoundError("Session not found")
    ip, ua = _client_meta(request)
    await _audit.log(
        db,
        actor_id=str(current_user.id),
        actor_email=current_user.email,
        actor_role=current_user.role,
        action="admin_session_revoked",
        resource_type="admin_session",
        resource_id=str(session_row_id),
        ip_address=ip,
        user_agent=ua,
    )
    return ok(
        RevokeSessionResponse(revoked_count=1),
        ResponseCode.AUTH_SESSION_REVOKED,
        "Session revoked",
    )


@router.post(
    "/admin/sessions/revoke-others",
    response_model=BaseSuccessResponse[RevokeSessionResponse],
    summary="Revoke every other admin session, keeping the current one",
    dependencies=[Depends(rate_limit_admin_sessions)],
)
async def revoke_other_admin_sessions(
    request: Request,
    current_user: Profile = Depends(require_admin),
    payload: JWTPayload = Depends(get_jwt_payload),
    db: AsyncSession = Depends(get_db),
) -> BaseSuccessResponse[RevokeSessionResponse]:
    count = await _svc.revoke_other_admin_sessions(
        db, str(current_user.id), payload.session_id
    )
    ip, ua = _client_meta(request)
    await _audit.log(
        db,
        actor_id=str(current_user.id),
        actor_email=current_user.email,
        actor_role=current_user.role,
        action="admin_sessions_revoked_others",
        resource_type="admin_session",
        resource_id=str(current_user.id),
        metadata={"revoked_count": count},
        ip_address=ip,
        user_agent=ua,
    )
    if count > 0:
        # Only notify when there was actually something to revoke — the
        # caller who just clicked this button already knows; this is for
        # visibility if the action wasn't something they consciously did in
        # this tab (e.g. triggered from a different device).
        await _notify_security_event(
            db,
            current_user,
            "Other sessions signed out",
            f"{count} other session(s) on your Hadha admin account were just signed out.",
        )
    return ok(
        RevokeSessionResponse(revoked_count=count),
        ResponseCode.AUTH_SESSION_REVOKED,
        f"{count} other session(s) revoked",
    )


@router.post(
    "/admin/sessions/revoke-all",
    response_model=BaseSuccessResponse[RevokeSessionResponse],
    summary="Revoke every admin session, including this one, and sign out of Supabase",
    dependencies=[Depends(rate_limit_admin_sessions)],
)
async def revoke_all_admin_sessions(
    request: Request,
    current_user: Profile = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> BaseSuccessResponse[RevokeSessionResponse]:
    count = await _svc.clear_all_admin_sessions_2fa(db, str(current_user.id))
    # Supabase's admin API only supports revoking every session for a user at
    # once (not one specific session) — this is the strongest option
    # available and matches "logout everywhere".
    await _svc.logout(db, str(current_user.id))
    ip, ua = _client_meta(request)
    await _audit.log(
        db,
        actor_id=str(current_user.id),
        actor_email=current_user.email,
        actor_role=current_user.role,
        action="admin_sessions_revoked_all",
        resource_type="admin_session",
        resource_id=str(current_user.id),
        metadata={"revoked_count": count},
        ip_address=ip,
        user_agent=ua,
    )
    return ok(
        RevokeSessionResponse(revoked_count=count),
        ResponseCode.AUTH_SESSION_REVOKED,
        "All sessions revoked",
    )
