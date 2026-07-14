"""Tests for provider-settings encryption/masking in the Settings module."""

from unittest.mock import AsyncMock, MagicMock, patch

from app.core.security import decrypt_value, encrypt_value
from app.modules.settings.repository import SettingsRepository
from app.modules.settings.service import SettingsService


class TestEncryptionRoundTrip:
    def test_encrypt_decrypt_round_trip(self):
        with patch("app.core.security.settings") as mock_settings:
            from cryptography.fernet import Fernet

            mock_settings.ENCRYPTION_KEY = Fernet.generate_key().decode()
            import app.core.security as security_module

            security_module._fernet = None  # reset cached instance for this key
            ciphertext = encrypt_value("re_super_secret_key")
            assert ciphertext != "re_super_secret_key"
            assert decrypt_value(ciphertext) == "re_super_secret_key"
            security_module._fernet = None


class TestSettingsServiceMasking:
    async def test_secret_value_is_masked_not_returned_plain(self):
        svc = SettingsService()
        row = MagicMock()
        row.key = "api_key"
        row.is_secret = True
        row.value_encrypted = "ciphertext"
        row.value_plain = None

        with (
            patch.object(
                SettingsRepository,
                "list_provider_settings",
                AsyncMock(return_value=[row]),
            ),
            patch(
                "app.modules.settings.service._decrypt",
                return_value="re_1234567890abcdef",
            ),
        ):
            result = await svc.get_provider_settings(AsyncMock(), provider="email")

        assert result["api_key"] != "re_1234567890abcdef"
        assert result["api_key"].endswith("cdef")
        assert result["api_key"].startswith("••••")

    async def test_non_secret_value_returned_as_is(self):
        svc = SettingsService()
        row = MagicMock()
        row.key = "from_email"
        row.is_secret = False
        row.value_encrypted = None
        row.value_plain = "orders@hadha.co"

        with patch.object(
            SettingsRepository,
            "list_provider_settings",
            AsyncMock(return_value=[row]),
        ):
            result = await svc.get_provider_settings(AsyncMock(), provider="email")

        assert result["from_email"] == "orders@hadha.co"

    async def test_missing_secret_value_returns_none(self):
        svc = SettingsService()
        row = MagicMock()
        row.key = "access_token"
        row.is_secret = True
        row.value_encrypted = None
        row.value_plain = None

        with patch.object(
            SettingsRepository,
            "list_provider_settings",
            AsyncMock(return_value=[row]),
        ):
            result = await svc.get_provider_settings(AsyncMock(), provider="whatsapp")

        assert result["access_token"] is None

    async def test_update_encrypts_secret_keys_only(self):
        svc = SettingsService()
        with (
            patch.object(
                SettingsRepository, "upsert_provider_setting", AsyncMock()
            ) as mock_upsert,
            patch.object(svc, "get_provider_settings", AsyncMock(return_value={})),
        ):
            db = AsyncMock()
            await svc.update_provider_settings(
                db,
                provider="email",
                data={"api_key": "re_secret", "from_email": "a@b.com"},
                updated_by=None,
            )

        calls = {
            c.kwargs["key"]: c.kwargs["is_secret"] for c in mock_upsert.await_args_list
        }
        assert calls["api_key"] is True
        assert calls["from_email"] is False
