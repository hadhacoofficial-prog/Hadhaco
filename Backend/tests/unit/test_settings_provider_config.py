"""Tests for provider-settings encryption/masking in the Settings module."""

from unittest.mock import AsyncMock, MagicMock, patch

from app.core.security import decrypt_value, encrypt_value
from app.modules.settings.repository import SettingsRepository
from app.modules.settings.service import SettingsService


class TestEncryptionRoundTrip:
    def test_encrypt_decrypt_round_trip(self):
        with patch("app.core.security.settings") as mock_settings:
            from cryptography.fernet import Fernet

            key = Fernet.generate_key().decode()
            mock_settings.ENCRYPTION_KEY = key
            mock_settings.ENCRYPTION_KEY_LEGACY = ""
            # _get_fernet reads settings.encryption_keys_list (primary +
            # legacy keys, for MultiFernet key rotation) rather than the
            # single ENCRYPTION_KEY field directly — mock it explicitly
            # since replacing the whole `settings` object bypasses the real
            # Settings.encryption_keys_list property.
            mock_settings.encryption_keys_list = [key]
            import app.core.security as security_module

            security_module._fernet = None  # reset cached instance for this key
            ciphertext = encrypt_value("re_super_secret_key")
            assert ciphertext != "re_super_secret_key"
            assert decrypt_value(ciphertext) == "re_super_secret_key"
            security_module._fernet = None

    def test_decrypts_with_retired_legacy_key_after_rotation(self):
        """Safe key rotation: a value encrypted under an old key must keep
        decrypting once that key is moved to ENCRYPTION_KEY_LEGACY and a new
        key takes over as ENCRYPTION_KEY — no re-encryption migration
        required at deploy time."""
        with patch("app.core.security.settings") as mock_settings:
            from cryptography.fernet import Fernet

            import app.core.security as security_module

            old_key = Fernet.generate_key().decode()
            new_key = Fernet.generate_key().decode()

            # Encrypt under the "old" key, as if this happened before rotation.
            mock_settings.encryption_keys_list = [old_key]
            security_module._fernet = None
            ciphertext = encrypt_value("pre-rotation-secret")

            # Rotate: new key primary, old key demoted to legacy.
            mock_settings.encryption_keys_list = [new_key, old_key]
            security_module._fernet = None
            assert decrypt_value(ciphertext) == "pre-rotation-secret"

            # New values now encrypt under the new primary key.
            new_ciphertext = encrypt_value("post-rotation-secret")
            assert decrypt_value(new_ciphertext) == "post-rotation-secret"

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
