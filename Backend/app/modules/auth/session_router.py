"""
Public authentication endpoints: register, login, refresh, session, e-mail
verification, password recovery/change and Google sign-in.

Tokens are only ever delivered as HttpOnly cookies (see app.core.auth_cookies);
JSON bodies carry the user and the CSRF token, never a bearer token.
"""

from __future__ import annotations

import time

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, created, ok
from app.core.auth_cookies import (
    clear_auth_cookies,
    clear_binder_cookie,
    enforce_origin,
    read_binder_cookie,
    read_refresh_cookie,
    set_auth_cookies,
    set_binder_cookie,
    surface_for_request,
)
from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import (
    get_current_user,
    get_jwt_payload,
    profile_cache_key,
)
from app.core.exceptions import AuthenticationError, HadhaException, _error_response
from app.core.redis import get_redis, safe_redis_delete
from app.core.security import (
    JWTPayload,
    generate_opaque_token,
    hash_opaque_token,
    make_csrf_token,
)
from app.middleware.rate_limit import (
    check_rate_limit,
    get_client_ip,
    rate_limit_auth_email,
    rate_limit_auth_token,
    rate_limit_change_password,
    rate_limit_login,
    rate_limit_refresh,
    rate_limit_register,
)
from app.modules.auth import emails
from app.modules.auth import google_oauth as google
from app.modules.auth.identity_service import (
    IdentityService,
    IssuedSession,
    normalize_email,
)
from app.modules.auth.schemas import (
    ChangePasswordRequest,
    EmailRequest,
    LoginRequest,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
    SessionResponse,
    SessionUser,
    VerifyEmailRequest,
)
from app.modules.profiles.models import Profile

router = APIRouter(prefix="/auth", tags=["auth"])
_svc = IdentityService()
_log = structlog.get_logger(__name__)

_LOGIN_PATH = {"store": "/account/login", "admin": "/admin/login"}
_VERIFY_PATH = {"store": "/account/verify-email", "admin": "/admin/verify-email"}
_RESET_PATH = {"store": "/account/reset-password", "admin": "/admin/reset-password"}


_BINDER_VERIFY = "reg"
_BINDER_OAUTH = "oauth"
_VERIFY_BINDER_PATH = f"{settings.API_V1_PREFIX}/auth"
_OAUTH_BINDER_PATH = f"{settings.API_V1_PREFIX}/auth/google"


def _set_verify_binder(response: Response, binder: str) -> None:
    """Tie the e-mailed link to the browser that asked for it (see
    IdentityService.verify_email). Outlives the link itself."""
    set_binder_cookie(
        response,
        _BINDER_VERIFY,
        binder,
        path=_VERIFY_BINDER_PATH,
        max_age=settings.AUTH_VERIFY_TTL_HOURS * 3600,
    )


def _client_meta(request: Request) -> tuple[str, str | None]:
    return get_client_ip(request), request.headers.get("user-agent")


def _user(profile: Profile) -> SessionUser:
    return SessionUser(
        id=profile.id,
        email=profile.email,
        full_name=profile.full_name,
        role=profile.role,
        is_verified=profile.is_verified,
        created_at=profile.created_at,
    )


async def _session_body(db: AsyncSession, issued: IssuedSession) -> SessionResponse:
    return SessionResponse(
        user=_user(issued.profile),
        csrf_token=issued.csrf_token,
        expires_in=issued.access_ttl,
        has_password=await _svc.has_password(db, issued.profile.id),
    )


def _apply_cookies(response: Response, surface: str, issued: IssuedSession) -> None:
    set_auth_cookies(
        response,
        surface,  # type: ignore[arg-type]
        access_token=issued.access_token,
        access_ttl=issued.access_ttl,
        refresh_token=issued.refresh_token,
        refresh_ttl=issued.refresh_ttl,
    )


async def _invalidate_profile(redis: aioredis.Redis, user_id: object) -> None:
    await safe_redis_delete(redis, profile_cache_key(str(user_id)))


# ── Registration / login ──────────────────────────────────────────────────────


@router.post(
    "/register",
    response_model=BaseSuccessResponse[RegisterResponse],
    status_code=201,
    summary="Create an account; a verification link is e-mailed",
    dependencies=[Depends(rate_limit_register)],
)
async def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> BaseSuccessResponse[RegisterResponse]:
    surface = surface_for_request(request)
    binder = generate_opaque_token()
    profile, token = await _svc.register(
        db,
        email=body.email,
        password=body.password,
        full_name=body.full_name,
        binder=binder,
    )
    _set_verify_binder(response, binder)
    background.add_task(
        emails.send_verification_email,
        to=profile.email,
        full_name=profile.full_name,
        action_url=emails.build_action_url(surface, _VERIFY_PATH[surface], token),
    )
    return created(
        RegisterResponse(email=profile.email),
        ResponseCode.AUTH_REGISTERED,
        "Account created. Check your email to verify your address.",
    )


@router.post(
    "/login",
    response_model=BaseSuccessResponse[SessionResponse],
    summary="Sign in with email and password (sets session cookies)",
    dependencies=[Depends(rate_limit_login)],
)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> BaseSuccessResponse[SessionResponse]:
    surface = surface_for_request(request)
    ip, ua = _client_meta(request)
    profile = await _svc.authenticate_password(
        db, redis, email=body.email, password=body.password, ip=ip
    )
    issued = await _svc.issue_session(
        db, profile, surface=surface, ip=ip, user_agent=ua
    )
    _apply_cookies(response, surface, issued)
    return ok(
        await _session_body(db, issued), ResponseCode.AUTH_LOGIN_SUCCESS, "Signed in"
    )


@router.post(
    "/refresh",
    response_model=None,
    summary="Rotate the refresh cookie and mint a new access cookie",
    dependencies=[Depends(rate_limit_refresh)],
)
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> BaseSuccessResponse[SessionResponse] | JSONResponse:
    surface = surface_for_request(request)
    # The refresh cookie is cookie-borne authority: only our own sites may use it.
    enforce_origin(request)
    token = read_refresh_cookie(request)
    if not token:
        raise AuthenticationError("Not authenticated", code="SESSION_INVALID")
    try:
        issued = await _svc.refresh_session(db, refresh_token=token)
    except HadhaException as exc:
        # Dead/revoked session: drop the cookies so the client stops retrying.
        # Returned (not raised) because an exception response would discard
        # the Set-Cookie headers.
        failure = _error_response(
            exc.status_code,  # type: ignore[attr-defined]
            exc.message,
            exc.code,
        )
        # SESSION_UNKNOWN = a token this server has no record of; with racing
        # tabs it can be a stale copy while the jar already holds the newer
        # one, so the cookies are left alone.
        if exc.code != "SESSION_UNKNOWN":
            clear_auth_cookies(failure, surface)  # type: ignore[arg-type]
        return failure
    _apply_cookies(response, surface, issued)
    return ok(
        await _session_body(db, issued),
        ResponseCode.AUTH_SESSION_REFRESHED,
        "Session refreshed",
    )


@router.get(
    "/session",
    response_model=BaseSuccessResponse[SessionResponse],
    summary="Current user + CSRF token (401 when signed out or expired)",
)
async def get_session(
    request: Request,
    payload: JWTPayload = Depends(get_jwt_payload),
    current_user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BaseSuccessResponse[SessionResponse]:
    assert payload.session_id is not None  # `sid` is a required claim
    body = SessionResponse(
        user=_user(current_user),
        csrf_token=make_csrf_token(payload.session_id),
        expires_in=max(0, payload.exp - int(time.time())),
        has_password=await _svc.has_password(db, current_user.id),
    )
    return ok(body, ResponseCode.AUTH_SESSION_FETCHED, "Session active")


# ── E-mail verification ───────────────────────────────────────────────────────


@router.post(
    "/verify-email",
    response_model=BaseSuccessResponse[SessionResponse],
    summary="Confirm the e-mail link and sign the user in",
    dependencies=[Depends(rate_limit_auth_token)],
)
async def verify_email(
    body: VerifyEmailRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> BaseSuccessResponse[SessionResponse]:
    surface = surface_for_request(request)
    profile = await _svc.verify_email(
        db, body.token, read_binder_cookie(request, _BINDER_VERIFY)
    )
    clear_binder_cookie(response, _BINDER_VERIFY, path=_VERIFY_BINDER_PATH)
    await _invalidate_profile(redis, profile.id)
    ip, ua = _client_meta(request)
    issued = await _svc.issue_session(
        db, profile, surface=surface, ip=ip, user_agent=ua
    )
    _apply_cookies(response, surface, issued)
    return ok(
        await _session_body(db, issued),
        ResponseCode.AUTH_EMAIL_VERIFIED,
        "Email verified",
    )


async def _limit_per_address(
    request: Request, redis: aioredis.Redis, email: str
) -> None:
    """Hourly cap per target mailbox, so the endpoint cannot be used to flood
    someone's inbox even from many IPs."""
    await check_rate_limit(
        request,
        redis,
        limit=5,
        window=3600,
        key_prefix="rl:auth:email-target",
        identity=hash_opaque_token(normalize_email(email))[:32],
    )


@router.post(
    "/resend-verification",
    response_model=BaseSuccessResponse[None],
    summary="Send a new verification link (always answers 200)",
    dependencies=[Depends(rate_limit_auth_email)],
)
async def resend_verification(
    body: EmailRequest,
    request: Request,
    response: Response,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> BaseSuccessResponse[None]:
    surface = surface_for_request(request)
    await _limit_per_address(request, redis, body.email)
    binder = generate_opaque_token()
    issued = await _svc.issue_verification_token(db, body.email, binder)
    if issued is not None:
        _set_verify_binder(response, binder)
        profile, token = issued
        background.add_task(
            emails.send_verification_email,
            to=profile.email,
            full_name=profile.full_name,
            action_url=emails.build_action_url(surface, _VERIFY_PATH[surface], token),
        )
    return ok(
        None,
        ResponseCode.AUTH_VERIFICATION_SENT,
        "If that account needs verification, a new link is on its way.",
    )


# ── Password recovery / change ────────────────────────────────────────────────


@router.post(
    "/forgot-password",
    response_model=BaseSuccessResponse[None],
    summary="E-mail a password-reset link (always answers 200)",
    dependencies=[Depends(rate_limit_auth_email)],
)
async def forgot_password(
    body: EmailRequest,
    request: Request,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> BaseSuccessResponse[None]:
    surface = surface_for_request(request)
    await _limit_per_address(request, redis, body.email)
    issued = await _svc.issue_reset_token(db, body.email)
    if issued is not None:
        profile, token = issued
        background.add_task(
            emails.send_password_reset_email,
            to=profile.email,
            action_url=emails.build_action_url(surface, _RESET_PATH[surface], token),
        )
    return ok(
        None,
        ResponseCode.AUTH_PASSWORD_RESET_SENT,
        "If an account exists for that address, a reset link is on its way.",
    )


@router.post(
    "/reset-password",
    response_model=BaseSuccessResponse[None],
    summary="Set a new password using the e-mailed token; signs out every device",
    dependencies=[Depends(rate_limit_auth_token)],
)
async def reset_password(
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> BaseSuccessResponse[None]:
    profile = await _svc.reset_password(db, body.token, body.new_password)
    await _invalidate_profile(redis, profile.id)
    return ok(
        None, ResponseCode.AUTH_PASSWORD_RESET, "Password updated. Please sign in."
    )


@router.post(
    "/change-password",
    response_model=BaseSuccessResponse[None],
    summary="Change the password; every other device is signed out",
    dependencies=[Depends(rate_limit_change_password)],
)
async def change_password(
    body: ChangePasswordRequest,
    current_user: Profile = Depends(get_current_user),
    payload: JWTPayload = Depends(get_jwt_payload),
    db: AsyncSession = Depends(get_db),
) -> BaseSuccessResponse[None]:
    await _svc.change_password(
        db,
        current_user,
        current_password=body.current_password,
        new_password=body.new_password,
        keep_session_id=payload.session_id,
    )
    return ok(None, ResponseCode.AUTH_PASSWORD_CHANGED, "Password updated")


# ── Google ────────────────────────────────────────────────────────────────────


def _origin_for(surface: str) -> str:
    return (settings.ADMIN_URL if surface == "admin" else settings.FRONTEND_URL).rstrip(
        "/"
    )


def _error_redirect(surface: str, code: str) -> RedirectResponse:
    return RedirectResponse(
        f"{_origin_for(surface)}{_LOGIN_PATH[surface]}?auth_error={code}",
        status_code=303,
    )


@router.get(
    "/google/start",
    summary="Begin Google sign-in (redirects to Google)",
    dependencies=[Depends(rate_limit_login)],
    response_class=RedirectResponse,
    status_code=302,
)
async def google_start(
    surface: str = Query("store", pattern="^(store|admin)$"),
    next: str = Query("/", max_length=512),
    redis: aioredis.Redis = Depends(get_redis),
) -> RedirectResponse:
    url, binder = await google.build_authorization_url(
        redis, surface=surface, next_path=next
    )
    redirect = RedirectResponse(url, status_code=302)
    set_binder_cookie(
        redirect,
        _BINDER_OAUTH,
        binder,
        path=_OAUTH_BINDER_PATH,
        max_age=google.STATE_TTL_SECONDS,
    )
    return redirect


@router.get(
    "/google/callback",
    summary="Google redirect target: finish sign-in and set session cookies",
    response_class=RedirectResponse,
    status_code=303,
    dependencies=[Depends(rate_limit_login)],
)
async def google_callback(
    request: Request,
    code: str | None = Query(None, max_length=2048),
    state: str | None = Query(None, max_length=512),
    error: str | None = Query(None, max_length=128),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> RedirectResponse:
    def finish(redirect: RedirectResponse) -> RedirectResponse:
        # The binder is single-use whatever the outcome.
        clear_binder_cookie(redirect, _BINDER_OAUTH, path=_OAUTH_BINDER_PATH)
        return redirect

    if not state:
        return finish(_error_redirect("store", "google_failed"))
    try:
        saved = await google.pop_state(
            redis, state, read_binder_cookie(request, _BINDER_OAUTH)
        )
    except HadhaException as exc:
        _log.info("google_state_rejected", code=exc.code)
        return finish(_error_redirect("store", "google_expired"))

    if error or not code:
        return finish(_error_redirect(saved.surface, "google_cancelled"))

    try:
        claims = await google.exchange_code(code, saved)
        profile = await _svc.login_with_google(
            db,
            subject=claims.subject,
            email=claims.email,
            email_verified=claims.email_verified,
            full_name=claims.name,
        )
    except HadhaException as exc:
        _log.warning("google_login_failed", code=exc.code)
        return finish(
            _error_redirect(saved.surface, (exc.code or "google_failed").lower())
        )

    await _invalidate_profile(redis, profile.id)
    ip, ua = _client_meta(request)
    issued = await _svc.issue_session(
        db, profile, surface=saved.surface, ip=ip, user_agent=ua
    )
    redirect = RedirectResponse(
        f"{_origin_for(saved.surface)}{saved.next_path}", status_code=303
    )
    _apply_cookies(redirect, saved.surface, issued)
    return finish(redirect)
