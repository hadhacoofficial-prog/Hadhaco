import secrets
from dataclasses import dataclass

import jwt
from cryptography.fernet import Fernet
from fastapi import HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.config import settings
from app.core.jwks import get_public_key

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/token")

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(settings.ENCRYPTION_KEY.encode())
    return _fernet


# ── JWT payload ────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class JWTPayload:
    """Strongly typed, immutable Supabase JWT payload returned after verification."""

    sub: str
    email: str | None
    role: str | None
    aud: str | list[str]
    exp: int
    iat: int
    # Supabase's stable per-login session identifier (`session_id` claim).
    # Persists across access-token refreshes within the same login session,
    # so it's used to correlate an AdminSession row to "this browser login"
    # for admin 2FA session-verification gating.
    session_id: str | None


# ── Supabase JWT — ES256 + JWKS ───────────────────────────────────────────────


async def verify_supabase_jwt(token: str) -> JWTPayload:
    """
    Verify a Supabase-issued JWT using ES256 and cached JWKS public keys.

    Validates: algorithm (ES256), kid presence, JWKS signature, issuer,
    audience, expiration, issued-at, and not-before (if present).
    Returns a typed JWTPayload; raises HTTP 401 on any failure.

    Never calls the Supabase JWKS endpoint more than once per TTL window.
    On an unknown kid it refreshes once (handles key rotation), then fails.
    """
    try:
        header = jwt.get_unverified_header(token)
    except jwt.DecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    kid: str | None = header.get("kid")
    alg: str = header.get("alg", "")
    if not kid or alg != "ES256":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        public_key = await get_public_key(kid)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    try:
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["ES256"],
            audience="authenticated",
            issuer=settings.supabase_issuer,
            options={"require": ["exp", "iat", "sub"]},
            leeway=60,  # tolerate up to 60 s of clock skew between server and Supabase
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return JWTPayload(
        sub=payload["sub"],
        email=payload.get("email"),
        role=payload.get("role"),
        aud=payload.get("aud", ""),
        exp=payload.get("exp", 0),
        iat=payload.get("iat", 0),
        session_id=payload.get("session_id"),
    )


# ── Encryption (TOTP secrets, sensitive fields) ────────────────────────────────


def encrypt_value(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    return _get_fernet().decrypt(ciphertext.encode()).decode()


# ── Webhook signature verification ────────────────────────────────────────────


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

    prefix = "sha256="
    if not signature_header.startswith(prefix):
        return False
    provided = signature_header[len(prefix) :]
    expected = hmac.new(
        settings.WHATSAPP_WEBHOOK_SECRET.encode(),
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
