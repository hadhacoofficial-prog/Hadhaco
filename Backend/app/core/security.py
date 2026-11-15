import asyncio
import functools
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import bcrypt
import jwt
import structlog
from cryptography.fernet import Fernet, MultiFernet
from fastapi import HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.config import settings

if TYPE_CHECKING:
    import razorpay

log = structlog.get_logger(__name__)

# auto_error=False: the token may arrive in a cookie instead of the Bearer
# header; `get_access_token` (dependencies.py) decides and raises the 401.
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_PREFIX}/auth/login", auto_error=False
)

_fernet: MultiFernet | None = None


def _get_fernet() -> MultiFernet:
    """
    MultiFernet encrypts with the first (primary) key and can decrypt with
    any key in the list — the mechanism for safe key rotation: add the new
    key as ENCRYPTION_KEY, move the old one to ENCRYPTION_KEY_LEGACY, and
    every existing encrypted value (e.g. Admin2FA.totp_secret) keeps
    decrypting correctly with no migration required at deploy time.
    """
    global _fernet
    if _fernet is None:
        _fernet = MultiFernet(
            [Fernet(key.encode()) for key in settings.encryption_keys_list]
        )
    return _fernet


# ── Access token (first-party, HS256) ──────────────────────────────────────────

ACCESS_TOKEN_ISSUER = "hadha-auth"
ACCESS_TOKEN_AUDIENCE = "hadha-api"


def _derived_key(purpose: bytes) -> bytes:
    """Per-purpose 32-byte key derived from SECRET_KEY (domain separation, so a
    value signed for one purpose can never be replayed as another)."""
    return hmac.new(settings.SECRET_KEY.encode(), purpose, hashlib.sha256).digest()


@dataclass(frozen=True, slots=True)
class JWTPayload:
    """Strongly typed, immutable access-token payload returned after verification."""

    sub: str
    email: str | None
    role: str | None
    aud: str | list[str]
    exp: int
    iat: int
    # The AuthSession id (`sid` claim). Persists across access-token refreshes
    # within the same login, so it correlates an AdminSession row to "this
    # browser login" for admin 2FA session-verification gating.
    session_id: str | None


def create_access_token(
    *, user_id: str, email: str | None, role: str, session_id: str
) -> tuple[str, int]:
    """Sign a short-lived access token. Returns (token, expires_in_seconds)."""
    now = int(time.time())
    ttl = settings.AUTH_ACCESS_TTL_SECONDS
    token = jwt.encode(
        {
            "iss": ACCESS_TOKEN_ISSUER,
            "aud": ACCESS_TOKEN_AUDIENCE,
            "sub": user_id,
            "email": email,
            "role": role,
            "sid": session_id,
            "iat": now,
            "exp": now + ttl,
        },
        _derived_key(b"hadha:auth:access:v1"),
        algorithm="HS256",
    )
    return token, ttl


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def verify_access_token(token: str) -> JWTPayload:
    """
    Verify an access token minted by `create_access_token`.

    Validates algorithm (HS256 only — `alg: none` and key-confusion are
    rejected), signature, issuer, audience, expiration, issued-at and the
    presence of `sub` and `sid`. Raises HTTP 401 on any failure.

    Revocation (logout / password change) is checked separately against the
    Redis deny-list by the request dependency — see `is_session_revoked`.
    """
    # Never log the raw token — only the failure reason.
    try:
        payload = jwt.decode(
            token,
            _derived_key(b"hadha:auth:access:v1"),
            algorithms=["HS256"],
            audience=ACCESS_TOKEN_AUDIENCE,
            issuer=ACCESS_TOKEN_ISSUER,
            options={"require": ["exp", "iat", "sub", "sid"]},
            leeway=10,
        )
    except jwt.ExpiredSignatureError as exc:
        log.info("jwt_verify_failed", reason="expired")
        raise _unauthorized("Token expired") from exc
    except jwt.InvalidTokenError as exc:
        log.warning("jwt_verify_failed", reason="invalid")
        raise _unauthorized("Invalid token") from exc

    return JWTPayload(
        sub=payload["sub"],
        email=payload.get("email"),
        role=payload.get("role"),
        aud=payload.get("aud", ""),
        exp=payload.get("exp", 0),
        iat=payload.get("iat", 0),
        session_id=payload.get("sid"),
    )


_REVOKED_KEY = "auth:revoked:{session_id}"


async def mark_sessions_revoked(session_ids: list[str]) -> None:
    """Deny-list sessions for the access-token lifetime so logout takes effect
    immediately instead of when the access token expires. Best-effort: if Redis
    is down the session row is still revoked, so no refresh can succeed."""
    if not session_ids:
        return
    from app.core.redis import get_redis_pool, safe_redis_setex

    redis = get_redis_pool()
    ttl = settings.AUTH_ACCESS_TTL_SECONDS + 60
    for sid in session_ids:
        await safe_redis_setex(redis, _REVOKED_KEY.format(session_id=sid), ttl, "1")


async def is_session_revoked(session_id: str | None) -> bool:
    if not session_id:
        return False
    from app.core.redis import get_redis_pool, safe_redis_get

    raw = await safe_redis_get(
        get_redis_pool(), _REVOKED_KEY.format(session_id=session_id)
    )
    return raw is not None


# ── CSRF (cookie-authenticated unsafe requests) ───────────────────────────────


def make_csrf_token(session_id: str) -> str:
    """Stateless CSRF token bound to a session. The JS app receives it in the
    JSON body of login/refresh/session (cookies are host-only on the API host,
    so a double-submit cookie is unreadable from the site's origin) and echoes
    it in `X-CSRF-Token`."""
    return hmac.new(
        _derived_key(b"hadha:auth:csrf:v1"), session_id.encode(), hashlib.sha256
    ).hexdigest()


def verify_csrf_token(session_id: str, provided: str | None) -> bool:
    if not provided:
        return False
    return secrets.compare_digest(make_csrf_token(session_id), provided)


# ── Opaque one-time / refresh tokens ──────────────────────────────────────────


def generate_opaque_token() -> str:
    """256-bit URL-safe random token (refresh tokens, email links)."""
    return secrets.token_urlsafe(32)


def hash_opaque_token(token: str) -> str:
    """SHA-256 hex. Sufficient (no salt/stretching) because the input is 256
    bits of CSPRNG output, not a human-chosen secret."""
    return hashlib.sha256(token.encode()).hexdigest()


# ── User passwords (bcrypt — compatible with imported Supabase `$2a$` hashes) ──

# bcrypt only reads the first 72 bytes; longer input is rejected up front
# instead of being silently truncated.
PASSWORD_MAX_BYTES = 72
_BCRYPT_ROUNDS = 12
# Verified against when the account does not exist, so "unknown email" and
# "wrong password" cost the same time (no account-enumeration timing signal).
_DUMMY_HASH = bcrypt.hashpw(
    b"not-a-real-password", bcrypt.gensalt(_BCRYPT_ROUNDS)
).decode()


def _bcrypt_hash(password: str) -> str:
    return bcrypt.hashpw(
        password.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    ).decode()


def _bcrypt_verify(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        # Malformed stored hash — treat as a non-match, never a 500.
        return False


async def hash_password(password: str) -> str:
    return await asyncio.to_thread(_bcrypt_hash, password)


async def verify_password(password: str, hashed: str | None) -> bool:
    """Constant-ish time: always performs one bcrypt comparison, even when
    there is no stored hash."""
    if len(password.encode()) > PASSWORD_MAX_BYTES:
        return False
    ok = await asyncio.to_thread(_bcrypt_verify, password, hashed or _DUMMY_HASH)
    return ok and hashed is not None


# ── Encryption (TOTP secrets, sensitive fields) ────────────────────────────────


def encrypt_value(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    return _get_fernet().decrypt(ciphertext.encode()).decode()


# ── Razorpay ─────────────────────────────────────────────────────────────────


# (connect, read) seconds. The Razorpay SDK passes no timeout to requests, so
# a stalled Razorpay API would otherwise hang the calling thread indefinitely.
RAZORPAY_HTTP_TIMEOUT = (5, 15)


@functools.lru_cache(maxsize=1)
def get_razorpay_client() -> "razorpay.Client":
    """Process-wide Razorpay client.

    Reusing one client keeps its requests.Session (and the pooled TLS
    connection to api.razorpay.com) alive across checkouts instead of paying
    a fresh TCP + TLS handshake on every order/refund call. requests.Session
    is safe to share across the executor threads these calls run on: the SDK
    sends no cookies and urllib3's connection pool is thread-safe.
    """
    import razorpay
    import requests

    class _TimeoutSession(requests.Session):
        def request(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            kwargs.setdefault("timeout", RAZORPAY_HTTP_TIMEOUT)
            return super().request(*args, **kwargs)

    return razorpay.Client(
        session=_TimeoutSession(),
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET),
    )


def verify_razorpay_webhook_signature(body: bytes, signature: str) -> bool:
    import hashlib
    import hmac

    expected = hmac.new(
        settings.RAZORPAY_WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    return secrets.compare_digest(expected, signature)


def verify_whatsapp_webhook_signature(body: bytes, signature_header: str) -> bool:
    """Validate Meta's `X-Hub-Signature-256: sha256=<hex>` header against
    WHATSAPP_WEBHOOK_SECRET (the app secret configured for the webhook)."""
    import hashlib
    import hmac

    secret = settings.WHATSAPP_WEBHOOK_SECRET
    if not secret:
        # Fail closed: HMAC with an empty key is computable by anyone, so an
        # unconfigured secret must reject every callback instead of accepting
        # forged ones.
        return False
    prefix = "sha256="
    if not signature_header.startswith(prefix):
        return False
    provided = signature_header[len(prefix) :]
    expected = hmac.new(
        secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    return secrets.compare_digest(expected, provided)


# ── Secure token generation ────────────────────────────────────────────────────


def generate_secure_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def generate_backup_codes(count: int = 10) -> list[str]:
    """Generate one-time backup codes (plain). Caller must hash before storing."""
    return [secrets.token_hex(5).upper() for _ in range(count)]


# ── Backup code hashing (NOT for user passwords) ──────────────────────────────


def hash_backup_code(code: str) -> str:
    import bcrypt

    return bcrypt.hashpw(code.encode(), bcrypt.gensalt()).decode()


def verify_backup_code(code: str, hashed: str) -> bool:
    import bcrypt

    return bcrypt.checkpw(code.encode(), hashed.encode())
