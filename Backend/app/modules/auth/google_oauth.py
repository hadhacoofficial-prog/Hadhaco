"""
Google sign-in (OpenID Connect authorization-code flow with PKCE).

  start     -> redirect the browser to Google with state + nonce + PKCE challenge
  callback  -> Google returns ?code&state; the code is exchanged server-side
               (client secret + PKCE verifier), the ID token is validated, and
               the caller signs the user in.

The state record (PKCE verifier, nonce, surface, post-login path) lives in Redis
for 10 minutes and is single-use.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
import jwt
import redis.asyncio as aioredis

from app.core.config import settings
from app.core.exceptions import AuthenticationError, ServiceUnavailableError

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
_ISSUERS = {"https://accounts.google.com", "accounts.google.com"}
STATE_TTL_SECONDS = 600


@dataclass(frozen=True)
class GoogleClaims:
    subject: str
    email: str
    email_verified: bool
    name: str | None


@dataclass(frozen=True)
class GoogleState:
    verifier: str
    nonce: str
    surface: str
    next_path: str


def is_configured() -> bool:
    return bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)


def callback_url() -> str:
    return f"{settings.API_BASE_URL.rstrip('/')}{settings.API_V1_PREFIX}/auth/google/callback"


def safe_next_path(value: str | None) -> str:
    """Post-login destination: a same-site path only (never an open redirect)."""
    if (
        not value
        or not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or any(ord(ch) < 32 for ch in value)
    ):
        return "/"
    return value


def _state_key(state: str) -> str:
    return f"auth:google_state:{hashlib.sha256(state.encode()).hexdigest()}"


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


async def build_authorization_url(
    redis: aioredis.Redis, *, surface: str, next_path: str
) -> tuple[str, str]:
    """Returns (Google URL, browser binder). The binder goes into an HttpOnly
    cookie on the initiating browser; the callback only accepts a state whose
    binder cookie matches, so a callback link cannot be replayed into a
    different browser (login CSRF / session fixation)."""
    if not is_configured():
        raise ServiceUnavailableError(
            "Google sign-in is not configured", code="GOOGLE_NOT_CONFIGURED"
        )
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    nonce = secrets.token_urlsafe(24)
    binder = secrets.token_urlsafe(32)
    record = {
        "binder": hashlib.sha256(binder.encode()).hexdigest(),
        "verifier": verifier,
        "nonce": nonce,
        "surface": surface,
        "next": safe_next_path(next_path),
    }
    # Raw call (not the fail-open helper): without the record the callback can
    # never succeed, so a Redis outage must surface now, not as a dead login.
    try:
        await redis.set(_state_key(state), json.dumps(record), ex=STATE_TTL_SECONDS)
    except Exception as exc:
        raise ServiceUnavailableError(
            "Sign-in is temporarily unavailable", code="AUTH_STATE_UNAVAILABLE"
        ) from exc
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": callback_url(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "code_challenge": _b64url(hashlib.sha256(verifier.encode()).digest()),
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    return f"{AUTH_URL}?{urlencode(params)}", binder


async def pop_state(
    redis: aioredis.Redis, state: str, binder: str | None
) -> GoogleState:
    """Atomically fetch-and-delete the state record (single use) and check it
    belongs to this browser."""
    try:
        raw = await redis.getdel(_state_key(state))
    except Exception as exc:
        raise ServiceUnavailableError(
            "Sign-in is temporarily unavailable", code="AUTH_STATE_UNAVAILABLE"
        ) from exc
    if raw is None:
        raise AuthenticationError(
            "Sign-in session expired. Please try again.", code="GOOGLE_STATE_INVALID"
        )
    data = json.loads(raw)
    expected = str(data.get("binder", ""))
    if not binder or not secrets.compare_digest(
        expected, hashlib.sha256(binder.encode()).hexdigest()
    ):
        raise AuthenticationError(
            "Sign-in session expired. Please try again.", code="GOOGLE_STATE_INVALID"
        )
    return GoogleState(
        verifier=data["verifier"],
        nonce=data["nonce"],
        surface=data["surface"],
        next_path=data["next"],
    )


async def exchange_code(code: str, state: GoogleState) -> GoogleClaims:
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": callback_url(),
                "grant_type": "authorization_code",
                "code_verifier": state.verifier,
            },
        )
    if resp.status_code != 200:
        raise AuthenticationError(
            "Google sign-in failed", code="GOOGLE_EXCHANGE_FAILED"
        )
    id_token = resp.json().get("id_token")
    if not id_token:
        raise AuthenticationError(
            "Google sign-in failed", code="GOOGLE_EXCHANGE_FAILED"
        )
    return validate_id_token(id_token, nonce=state.nonce)


def validate_id_token(id_token: str, *, nonce: str) -> GoogleClaims:
    """Validate the claims of an ID token received straight from Google's token
    endpoint. OIDC Core §3.1.3.7 permits relying on the TLS-authenticated
    channel instead of re-checking the signature for such a token; every claim
    that binds it to *this* login is still verified."""
    try:
        claims = jwt.decode(
            id_token,
            options={"verify_signature": False},
            algorithms=["RS256"],
        )
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError(
            "Google sign-in failed", code="GOOGLE_TOKEN_INVALID"
        ) from exc

    audience = claims.get("aud")
    aud_ok = audience == settings.GOOGLE_CLIENT_ID or (
        isinstance(audience, list) and settings.GOOGLE_CLIENT_ID in audience
    )
    if (
        claims.get("iss") not in _ISSUERS
        or not aud_ok
        or not isinstance(claims.get("exp"), int | float)
        or claims["exp"] <= time.time() - 10
        or not secrets.compare_digest(str(claims.get("nonce", "")), nonce)
        or not claims.get("sub")
        or not claims.get("email")
    ):
        raise AuthenticationError("Google sign-in failed", code="GOOGLE_TOKEN_INVALID")

    return GoogleClaims(
        subject=str(claims["sub"]),
        email=str(claims["email"]),
        # Google emits this as a bool; tolerate the string form some SDKs echo.
        email_verified=claims.get("email_verified") in (True, "true"),
        name=claims.get("name"),
    )
