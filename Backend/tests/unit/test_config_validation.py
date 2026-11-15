import pytest
from pydantic import ValidationError

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
        with pytest.raises(ValidationError):
            Settings(APP_ENV="not-an-env")

    def test_r2_aliases_resolve(self):
        assert settings.R2_BUCKET_NAME == settings.CLOUDFLARE_R2_BUCKET
        assert settings.R2_ENDPOINT_URL == settings.CLOUDFLARE_R2_ENDPOINT


class TestGoogleApiBaseUrl:
    def _prod(self, **overrides) -> Settings:
        return settings.model_copy(
            update={
                "APP_ENV": "production",
                "APP_DEBUG": False,
                "LOG_SQL": False,
                "ALLOWED_ORIGINS": "https://hadha.co",
                "ALLOWED_HOSTS": "api.hadha.co",
                **overrides,
            }
        )

    def test_localhost_api_base_url_rejected_when_google_configured(self):
        from app.core.config import validate_production_safety

        broken = self._prod(
            GOOGLE_CLIENT_ID="cid.apps.googleusercontent.com",
            API_BASE_URL="http://localhost:8000",
        )
        with pytest.raises(SystemExit) as exc:
            validate_production_safety(broken)
        assert "API_BASE_URL" in str(exc.value)

    def test_https_api_base_url_accepted(self):
        from app.core.config import validate_production_safety

        ok = self._prod(
            GOOGLE_CLIENT_ID="cid.apps.googleusercontent.com",
            API_BASE_URL="https://api.hadha.co",
        )
        try:
            validate_production_safety(ok)
        except SystemExit as exc:  # other unrelated production rules may fire
            assert "API_BASE_URL" not in str(exc)
