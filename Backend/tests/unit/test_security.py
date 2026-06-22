"""
Unit tests for app/core/security.py and app/core/jwks.py.

JWT tests use a real EC P-256 key pair generated in-process.
The JWKS network call is replaced by a mock so tests run offline.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ec import SECP256R1, generate_private_key
from fastapi import HTTPException

from app.core.config import settings
from app.core.security import (
    JWTPayload,
    decrypt_value,
    encrypt_value,
    generate_backup_codes,
    hash_backup_code,
    verify_backup_code,
    verify_razorpay_webhook_signature,
    verify_supabase_jwt,
)

# ── Shared test key pair ──────────────────────────────────────────────────────

_PRIVATE_KEY = generate_private_key(SECP256R1())
_PUBLIC_KEY = _PRIVATE_KEY.public_key()
_TEST_KID = "test-kid-001"


def _make_token(
    exp_delta: timedelta,
    *,
    kid: str = _TEST_KID,
    alg: str = "ES256",
    aud: str = "authenticated",
    issuer: str | None = None,
    private_key=None,
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": "11111111-1111-1111-1111-111111111111",
        "email": "user@test.com",
        "role": "authenticated",
        "aud": aud,
        "iss": issuer or settings.supabase_issuer,
        "exp": now + exp_delta,
        "iat": now,
    }
    return jwt.encode(
        payload,
        private_key or _PRIVATE_KEY,
        algorithm=alg,
        headers={"kid": kid, "alg": alg},
    )


# ── JWT / JWKS tests ──────────────────────────────────────────────────────────


class TestSupabaseJwt:
    """ES256 verification via mocked JWKS public key."""

    @pytest.fixture(autouse=True)
    def mock_public_key(self):
        """Replace JWKS network calls with our in-process test key."""
        with patch(
            "app.core.security.get_public_key",
            new=AsyncMock(return_value=_PUBLIC_KEY),
        ):
            yield

    async def test_valid_token_returns_typed_payload(self):
        token = _make_token(timedelta(minutes=5))
        payload = await verify_supabase_jwt(token)
        assert isinstance(payload, JWTPayload)
        assert payload.sub == "11111111-1111-1111-1111-111111111111"
        assert payload.email == "user@test.com"

    async def test_expired_token_raises_401_with_expired_message(self):
        token = _make_token(timedelta(minutes=-5))
        with pytest.raises(HTTPException) as exc:
            await verify_supabase_jwt(token)
        assert exc.value.status_code == 401
        assert "expired" in exc.value.detail.lower()

    async def test_wrong_audience_raises_401(self):
        token = _make_token(timedelta(minutes=5), aud="anon")
        with pytest.raises(HTTPException) as exc:
            await verify_supabase_jwt(token)
        assert exc.value.status_code == 401

    async def test_wrong_issuer_raises_401(self):
        token = _make_token(
            timedelta(minutes=5),
            issuer="https://evil.supabase.co/auth/v1",
        )
        with pytest.raises(HTTPException) as exc:
            await verify_supabase_jwt(token)
        assert exc.value.status_code == 401

    async def test_non_es256_algorithm_raises_401(self):
        # HS256 token — should be rejected at the header check (alg != "ES256")
        now = datetime.now(UTC)
        hs_token = jwt.encode(
            {
                "sub": "x",
                "aud": "authenticated",
                "iss": settings.supabase_issuer,
                "exp": now + timedelta(minutes=5),
                "iat": now,
            },
            "some-secret",
            algorithm="HS256",
            headers={"kid": _TEST_KID, "alg": "HS256"},
        )
        with pytest.raises(HTTPException) as exc:
            await verify_supabase_jwt(hs_token)
        assert exc.value.status_code == 401

    async def test_malformed_token_raises_401(self):
        with pytest.raises(HTTPException) as exc:
            await verify_supabase_jwt("not.a.jwt")
        assert exc.value.status_code == 401

    async def test_token_missing_kid_raises_401(self):
        now = datetime.now(UTC)
        token = jwt.encode(
            {
                "sub": "x",
                "aud": "authenticated",
                "iss": settings.supabase_issuer,
                "exp": now + timedelta(minutes=5),
                "iat": now,
            },
            _PRIVATE_KEY,
            algorithm="ES256",
            # No kid in headers
        )
        with pytest.raises(HTTPException) as exc:
            await verify_supabase_jwt(token)
        assert exc.value.status_code == 401

    async def test_unknown_kid_raises_401(self):
        with patch(
            "app.core.security.get_public_key",
            new=AsyncMock(side_effect=ValueError("JWKS: unknown key id 'bad-kid'")),
        ):
            token = _make_token(timedelta(minutes=5))
            with pytest.raises(HTTPException) as exc:
                await verify_supabase_jwt(token)
            assert exc.value.status_code == 401

    async def test_wrong_signing_key_raises_401(self):
        other_private_key = generate_private_key(SECP256R1())
        token = _make_token(timedelta(minutes=5), private_key=other_private_key)
        with pytest.raises(HTTPException) as exc:
            await verify_supabase_jwt(token)
        assert exc.value.status_code == 401


# ── Encryption tests ──────────────────────────────────────────────────────────


class TestEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        secret = "JBSWY3DPEHPK3PXP"
        assert decrypt_value(encrypt_value(secret)) == secret

    def test_ciphertext_differs_from_plaintext(self):
        assert encrypt_value("abc") != "abc"


# ── Webhook signature tests ───────────────────────────────────────────────────


class TestWebhookSignature:
    def test_valid_signature_accepted(self):
        import hashlib
        import hmac

        body = b'{"event":"payment.captured"}'
        sig = hmac.new(
            settings.RAZORPAY_WEBHOOK_SECRET.encode(), body, hashlib.sha256
        ).hexdigest()
        assert verify_razorpay_webhook_signature(body, sig) is True

    def test_tampered_body_rejected(self):
        import hashlib
        import hmac

        sig = hmac.new(
            settings.RAZORPAY_WEBHOOK_SECRET.encode(), b"original", hashlib.sha256
        ).hexdigest()
        assert verify_razorpay_webhook_signature(b"tampered", sig) is False


# ── Backup code tests ─────────────────────────────────────────────────────────


class TestBackupCodes:
    def test_generates_requested_count_unique(self):
        codes = generate_backup_codes(10)
        assert len(codes) == 10
        assert len(set(codes)) == 10

    def test_hash_verify_roundtrip(self):
        code = "ABCDEF1234"
        hashed = hash_backup_code(code)
        assert verify_backup_code(code, hashed) is True
        assert verify_backup_code("WRONG12345", hashed) is False
