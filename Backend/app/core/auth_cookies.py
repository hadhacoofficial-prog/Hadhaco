"""
Session cookies, client "surface" detection and CSRF enforcement.

The API sets HttpOnly cookies on its own host (host-only, so they are sent only
to the API). Storefront and admin are separate sites that call the API with
``credentials: "include"``; each gets its own cookie pair so signing in to one
never replaces the other's session.

  access   short-lived JWT        SameSite=Lax    Path=/
  refresh  opaque rotating token  SameSite=Strict Path=<api>/auth

In production the names carry the ``__Host-`` / ``__Secure-`` prefixes, which
make browsers refuse the cookie unless it is Secure (and, for ``__Host-``,
host-only with Path=/). They are dropped in development (plain http).
"""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

from fastapi import HTTPException, Request, Response, status

from app.core.config import settings
from app.core.security import verify_csrf_token

Surface = Literal["store", "admin"]

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
CSRF_HEADER = "X-CSRF-Token"


def _origin_of(url: str) -> str | None:
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}".lower()


def request_origin(request: Request) -> str | None:
    """Origin of the calling page: the Origin header, else the Referer's origin."""
    origin = request.headers.get("origin")
    if origin and origin != "null":
        return origin.lower().rstrip("/")
    referer = request.headers.get("referer")
    return _origin_of(referer) if referer else None


def surface_for_request(request: Request) -> Surface:
    """ "admin" when the call comes from the admin site, otherwise "store"."""
    if request_origin(request) == _origin_of(settings.ADMIN_URL):
        return "admin"
    return "store"


def _use_host_prefix() -> bool:
    return settings.is_production and not settings.AUTH_COOKIE_DOMAIN


def access_cookie_name(surface: Surface) -> str:
    base = "hadha_at" if surface == "store" else "hadha_admin_at"
    if _use_host_prefix():
        return f"__Host-{base}"
    return f"__Secure-{base}" if settings.is_production else base


def refresh_cookie_name(surface: Surface) -> str:
    base = "hadha_rt" if surface == "store" else "hadha_admin_rt"
    return f"__Secure-{base}" if settings.is_production else base


def _refresh_path() -> str:
    return f"{settings.API_V1_PREFIX}/auth"


def set_auth_cookies(
    response: Response,
    surface: Surface,
    *,
    access_token: str,
    access_ttl: int,
    refresh_token: str | None,
    refresh_ttl: int,
) -> None:
    """Set the access cookie and, when a new one was minted, the refresh cookie."""
    secure = settings.is_production
    domain = settings.AUTH_COOKIE_DOMAIN or None
    response.set_cookie(
        access_cookie_name(surface),
        access_token,
        max_age=access_ttl,
        path="/",
        domain=domain,
        secure=secure,
        httponly=True,
        samesite="lax",
    )
    if refresh_token is not None:
        response.set_cookie(
            refresh_cookie_name(surface),
            refresh_token,
            max_age=refresh_ttl,
            path=_refresh_path(),
            domain=domain,
            secure=secure,
            httponly=True,
            samesite="strict",
        )


def clear_auth_cookies(response: Response, surface: Surface) -> None:
    secure = settings.is_production
    domain = settings.AUTH_COOKIE_DOMAIN or None
    response.delete_cookie(
        access_cookie_name(surface),
        path="/",
        domain=domain,
        secure=secure,
        httponly=True,
        samesite="lax",
    )
    response.delete_cookie(
        refresh_cookie_name(surface),
        path=_refresh_path(),
        domain=domain,
        secure=secure,
        httponly=True,
        samesite="strict",
    )


def binder_cookie_name(kind: str) -> str:
    base = f"hadha_{kind}"
    return f"__Secure-{base}" if settings.is_production else base


def set_binder_cookie(
    response: Response, kind: str, value: str, *, path: str, max_age: int
) -> None:
    """Short-lived HttpOnly cookie tying a one-time flow (Google sign-in,
    e-mail verification) to the browser that started it. Lax so it survives the
    top-level redirect back from Google / a click in a mail client."""
    response.set_cookie(
        binder_cookie_name(kind),
        value,
        max_age=max_age,
        path=path,
        domain=settings.AUTH_COOKIE_DOMAIN or None,
        secure=settings.is_production,
        httponly=True,
        samesite="lax",
    )


def read_binder_cookie(request: Request, kind: str) -> str | None:
    return request.cookies.get(binder_cookie_name(kind))


def clear_binder_cookie(response: Response, kind: str, *, path: str) -> None:
    response.delete_cookie(
        binder_cookie_name(kind),
        path=path,
        domain=settings.AUTH_COOKIE_DOMAIN or None,
        secure=settings.is_production,
        httponly=True,
        samesite="lax",
    )


def read_access_cookie(request: Request) -> str | None:
    return request.cookies.get(access_cookie_name(surface_for_request(request)))


def read_refresh_cookie(request: Request) -> str | None:
    return request.cookies.get(refresh_cookie_name(surface_for_request(request)))


def _csrf_error(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=detail,
        headers={"X-Error-Code": "CSRF_FAILED"},
    )


def enforce_origin(request: Request) -> None:
    """Unsafe cookie-authenticated requests must come from an allowed site.

    Browsers always send Origin on cross-origin and on same-origin non-GET
    requests, so a missing Origin on a cookie request is rejected.
    """
    origin = request_origin(request)
    if origin is None or origin not in {
        o.lower().rstrip("/") for o in settings.allowed_origins_list
    }:
        raise _csrf_error("Origin not allowed")


def enforce_csrf(request: Request, session_id: str) -> None:
    """Origin allow-list + per-session token for cookie-authenticated writes.
    Requests authenticated by an Authorization header are not cookie-borne and
    skip this (a cross-site attacker cannot set that header)."""
    if request.method in SAFE_METHODS:
        return
    enforce_origin(request)
    if not verify_csrf_token(session_id, request.headers.get(CSRF_HEADER)):
        raise _csrf_error("Missing or invalid CSRF token")
