"""
Unit tests for app/core/security.py — access tokens, CSRF tokens, password
hashing and opaque tokens. Everything is in-process; no network, DB or Redis.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.core.security import (
    ACCESS_TOKEN_AUDIENCE,
    ACCESS_TOKEN_ISSUER,
    PASSWORD_MAX_BYTES,
    JWTPayload,
    _derived_key,
    create_access_token,
    decrypt_value,
    encrypt_value,
    generate_backup_codes,
    generate_opaque_token,
    hash_backup_code,
    hash_opaque_token,
    hash_password,
    make_csrf_token,
    verify_access_token,
    verify_backup_code,
    verify_csrf_token,
    verify_password,
    verify_razorpay_webhook_signature,
)

_USER_ID = "11111111-1111-1111-1111-111111111111"
_SESSION_ID = "22222222-2222-2222-2222-222222222222"
_ACCESS_KEY = _derived_key(b"hadha:auth:access:v1")


def _token(**overrides) -> str:
    now = int(time.time())
    claims = {
        "iss": ACCESS_TOKEN_ISSUER,
        "aud": ACCESS_TOKEN_AUDIENCE,
        "sub": _USER_ID,
        "email": "user@test.com",
        "role": "customer",
        "sid": _SESSION_ID,
        "iat": now,
        "exp": now + 300,
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, _ACCESS_KEY, algorithm="HS256")


# ── Access token tests ────────────────────────────────────────────────────────


class TestAccessToken:
    def test_roundtrip_returns_typed_payload(self):
        token, ttl = create_access_token(
            user_id=_USER_ID,
            email="user@test.com",
            role="admin",
            session_id=_SESSION_ID,
        )
        payload = verify_access_token(token)
        assert isinstance(payload, JWTPayload)
        assert payload.sub == _USER_ID
        assert payload.email == "user@test.com"
        assert payload.role == "admin"
        assert payload.session_id == _SESSION_ID
        assert ttl == settings.AUTH_ACCESS_TTL_SECONDS
        assert payload.exp - payload.iat == ttl

    def test_expired_token_raises_401_with_expired_message(self):
        with pytest.raises(HTTPException) as exc:
            verify_access_token(_token(exp=int(time.time()) - 600))
        assert exc.value.status_code == 401
        assert "expired" in exc.value.detail.lower()

    @pytest.mark.parametrize(
        "claim,value",
        [("aud", "anon"), ("iss", "https://evil.example/auth")],
    )
    def test_wrong_audience_or_issuer_raises_401(self, claim, value):
        with pytest.raises(HTTPException) as exc:
            verify_access_token(_token(**{claim: value}))
        assert exc.value.status_code == 401

    @pytest.mark.parametrize("claim", ["sub", "sid", "exp", "iat"])
    def test_missing_required_claim_raises_401(self, claim):
        with pytest.raises(HTTPException) as exc:
            verify_access_token(_token(**{claim: None}))
        assert exc.value.status_code == 401

    def test_wrong_signing_key_raises_401(self):
        now = int(time.time())
        forged = jwt.encode(
            {
                "iss": ACCESS_TOKEN_ISSUER,
                "aud": ACCESS_TOKEN_AUDIENCE,
                "sub": _USER_ID,
                "sid": _SESSION_ID,
                "iat": now,
                "exp": now + 300,
            },
            "x" * 32,
            algorithm="HS256",
        )
        with pytest.raises(HTTPException) as exc:
            verify_access_token(forged)
        assert exc.value.status_code == 401

    def test_alg_none_is_rejected(self):
        now = int(time.time())
        unsigned = jwt.encode(
            {"sub": _USER_ID, "sid": _SESSION_ID, "iat": now, "exp": now + 300},
            key=None,
            algorithm="none",
        )
        with pytest.raises(HTTPException) as exc:
            verify_access_token(unsigned)
        assert exc.value.status_code == 401

    def test_other_hmac_algorithm_is_rejected(self):
        now = int(time.time())
        token = jwt.encode(
            {
                "iss": ACCESS_TOKEN_ISSUER,
                "aud": ACCESS_TOKEN_AUDIENCE,
                "sub": _USER_ID,
                "sid": _SESSION_ID,
                "iat": now,
                "exp": now + 300,
            },
            _ACCESS_KEY,
            algorithm="HS512",
        )
        with pytest.raises(HTTPException) as exc:
            verify_access_token(token)
        assert exc.value.status_code == 401

    def test_malformed_token_raises_401(self):
        with pytest.raises(HTTPException) as exc:
            verify_access_token("not.a.jwt")
        assert exc.value.status_code == 401

    def test_old_supabase_style_token_is_rejected(self):
        now = datetime.now(UTC)
        legacy = jwt.encode(
            {
                "sub": _USER_ID,
                "aud": "authenticated",
                "iss": "https://x.supabase.co/auth/v1",
                "session_id": _SESSION_ID,
                "exp": now + timedelta(minutes=5),
                "iat": now,
            },
            _ACCESS_KEY,
            algorithm="HS256",
        )
        with pytest.raises(HTTPException):
            verify_access_token(legacy)


# ── CSRF token tests ──────────────────────────────────────────────────────────


class TestCsrfToken:
    def test_token_verifies_for_its_session(self):
        assert verify_csrf_token(_SESSION_ID, make_csrf_token(_SESSION_ID)) is True

    def test_token_is_bound_to_the_session(self):
        assert verify_csrf_token("other-session", make_csrf_token(_SESSION_ID)) is False

    @pytest.mark.parametrize("provided", [None, "", "deadbeef"])
    def test_missing_or_wrong_token_rejected(self, provided):
        assert verify_csrf_token(_SESSION_ID, provided) is False

    def test_csrf_key_differs_from_access_key(self):
        assert _derived_key(b"hadha:auth:csrf:v1") != _ACCESS_KEY


# ── Password hashing tests ────────────────────────────────────────────────────


class TestPasswords:
    async def test_hash_and_verify_roundtrip(self):
        hashed = await hash_password("correct horse battery")
        assert hashed.startswith("$2b$")
        assert await verify_password("correct horse battery", hashed) is True
        assert await verify_password("wrong", hashed) is False

    async def test_imported_supabase_2a_hash_verifies(self):
        # Supabase (GoTrue) stores bcrypt with the legacy $2a$ prefix; imported
        # users must be able to sign in with their existing password.
        legacy = bcrypt.hashpw(b"old-password", bcrypt.gensalt(rounds=4, prefix=b"2a"))
        assert legacy.startswith(b"$2a$")
        assert await verify_password("old-password", legacy.decode()) is True

    async def test_missing_hash_never_verifies(self):
        assert await verify_password("anything", None) is False

    async def test_malformed_hash_is_a_mismatch_not_an_error(self):
        assert await verify_password("anything", "not-a-bcrypt-hash") is False

    async def test_over_72_byte_password_rejected_not_truncated(self):
        hashed = await hash_password("a" * PASSWORD_MAX_BYTES)
        assert await verify_password("a" * (PASSWORD_MAX_BYTES + 1), hashed) is False


class TestOpaqueTokens:
    def test_tokens_are_unique_and_long(self):
        a, b = generate_opaque_token(), generate_opaque_token()
        assert a != b
        assert len(a) >= 43

    def test_hash_is_deterministic_sha256_hex(self):
        assert hash_opaque_token("abc") == hash_opaque_token("abc")
        assert len(hash_opaque_token("abc")) == 64
        assert hash_opaque_token("abc") != hash_opaque_token("abd")


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


class TestWhatsappWebhookSignature:
    def test_empty_secret_rejects_even_a_correct_looking_signature(self, monkeypatch):
        import hashlib
        import hmac

        from app.core.config import settings
        from app.core.security import verify_whatsapp_webhook_signature

        monkeypatch.setattr(settings, "WHATSAPP_WEBHOOK_SECRET", "")
        body = b'{"entry": []}'
        forged = "sha256=" + hmac.new(b"", body, hashlib.sha256).hexdigest()
        assert verify_whatsapp_webhook_signature(body, forged) is False

    def test_configured_secret_accepts_valid_and_rejects_invalid(self, monkeypatch):
        import hashlib
        import hmac

        from app.core.config import settings
        from app.core.security import verify_whatsapp_webhook_signature

        monkeypatch.setattr(settings, "WHATSAPP_WEBHOOK_SECRET", "s3cret")
        body = b'{"entry": []}'
        good = "sha256=" + hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
        assert verify_whatsapp_webhook_signature(body, good) is True
        assert verify_whatsapp_webhook_signature(body, "sha256=00") is False
