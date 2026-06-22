import pytest

from app.core.config import Settings, settings, validate_required_settings


class TestConfigValidation:
    def test_current_test_settings_pass(self):
        validate_required_settings(settings)

    def test_missing_values_raise_system_exit_listing_all(self):
        broken = settings.model_copy(update={"SECRET_KEY": "", "RAZORPAY_KEY_ID": ""})
        with pytest.raises(SystemExit) as exc:
            validate_required_settings(broken)
        message = str(exc.value)
        assert "SECRET_KEY" in message
        assert "RAZORPAY_KEY_ID" in message

    def test_invalid_app_env_rejected(self):
        with pytest.raises(Exception):
            Settings(APP_ENV="not-an-env")

    def test_r2_aliases_resolve(self):
        assert settings.R2_BUCKET_NAME == settings.CLOUDFLARE_R2_BUCKET
        assert settings.R2_ENDPOINT_URL == settings.CLOUDFLARE_R2_ENDPOINT
