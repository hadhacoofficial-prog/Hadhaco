"""Unit tests for MSG91SMSProvider and related helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.modules.notifications.providers.msg91_sms import (
    MSG91SMSProvider,
    _normalize_mobile,
)

# ─── _normalize_mobile ────────────────────────────────────────────────────────


class TestNormalizeMobile:
    def test_strips_plus_and_dashes(self):
        assert _normalize_mobile("+91-98765-43210") == "919876543210"

    def test_prepends_91_for_10_digit_number(self):
        assert _normalize_mobile("9876543210") == "919876543210"

    def test_already_has_country_code(self):
        assert _normalize_mobile("919876543210") == "919876543210"

    def test_strips_spaces(self):
        assert _normalize_mobile("+91 98765 43210") == "919876543210"

    def test_e164_format(self):
        assert _normalize_mobile("+919876543210") == "919876543210"


# ─── MSG91SMSProvider ─────────────────────────────────────────────────────────


class TestMSG91SMSProvider:
    def setup_method(self):
        self.provider = MSG91SMSProvider()

    async def test_send_email_raises_not_implemented(self):
        with pytest.raises(NotImplementedError):
            await self.provider.send_email(to="a@b.com", subject="S", html="<p>H</p>")

    async def test_send_sms_success_returns_request_id(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "type": "success",
            "request_id": "req-abc123",
        }
        mock_response.raise_for_status = MagicMock()

        with (
            patch(
                "app.modules.notifications.providers.msg91_sms.settings"
            ) as mock_settings,
            patch(
                "httpx.AsyncClient.post",
                new_callable=AsyncMock,
                return_value=mock_response,
            ),
        ):
            mock_settings.MSG91_API_KEY = "test-api-key"
            mock_settings.MSG91_SENDER_ID = "HADHA"
            mock_settings.MSG91_TEMPLATE_ID = "tpl-001"

            result = await self.provider.send_sms(
                to="+919876543210", body="Your order is placed"
            )

        assert result == "req-abc123"

    async def test_send_sms_raises_on_http_error(self):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "401", request=MagicMock(), response=mock_response
        )

        with (
            patch(
                "app.modules.notifications.providers.msg91_sms.settings"
            ) as mock_settings,
            patch(
                "httpx.AsyncClient.post",
                new_callable=AsyncMock,
                return_value=mock_response,
            ),
        ):
            mock_settings.MSG91_API_KEY = "bad-key"
            mock_settings.MSG91_SENDER_ID = "HADHA"
            mock_settings.MSG91_TEMPLATE_ID = "tpl-001"

            with pytest.raises(httpx.HTTPStatusError):
                await self.provider.send_sms(to="+919876543210", body="Test")

    async def test_send_sms_raises_on_api_rejection(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "type": "error",
            "message": "Invalid template",
        }
        mock_response.raise_for_status = MagicMock()

        with (
            patch(
                "app.modules.notifications.providers.msg91_sms.settings"
            ) as mock_settings,
            patch(
                "httpx.AsyncClient.post",
                new_callable=AsyncMock,
                return_value=mock_response,
            ),
        ):
            mock_settings.MSG91_API_KEY = "test-key"
            mock_settings.MSG91_SENDER_ID = "HADHA"
            mock_settings.MSG91_TEMPLATE_ID = "tpl-bad"

            with pytest.raises(RuntimeError, match="MSG91 rejected"):
                await self.provider.send_sms(to="+919876543210", body="Test")

    async def test_send_sms_normalizes_phone_number(self):
        captured: list[dict] = []

        async def _fake_post(url, *, headers, json, timeout):
            captured.append(json)
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"type": "success", "request_id": "req-1"}
            mock_resp.raise_for_status = MagicMock()
            return mock_resp

        with (
            patch(
                "app.modules.notifications.providers.msg91_sms.settings"
            ) as mock_settings,
            patch(
                "httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=_fake_post
            ),
        ):
            mock_settings.MSG91_API_KEY = "key"
            mock_settings.MSG91_SENDER_ID = "HADHA"
            mock_settings.MSG91_TEMPLATE_ID = "tpl-1"

            await self.provider.send_sms(to="9876543210", body="Hello")

        assert captured[0]["mobiles"] == "919876543210"


# ─── Configuration validation ─────────────────────────────────────────────────


class TestConfigValidation:
    def test_validate_fails_fast_when_sms_enabled_without_credentials(self):
        from app.core.config import Settings, validate_required_settings

        with pytest.raises(SystemExit, match="MSG91"):
            s = Settings(
                SECRET_KEY="x" * 32,
                ENCRYPTION_KEY="x" * 32,
                SUPABASE_URL="https://x.supabase.co",
                SUPABASE_SERVICE_ROLE_KEY="key",
                DATABASE_URL="postgresql+asyncpg://localhost/db",
                REDIS_URL="redis://localhost",
                CLOUDFLARE_ACCOUNT_ID="acc",
                CLOUDFLARE_R2_BUCKET="bucket",
                CLOUDFLARE_R2_ACCESS_KEY="ak",
                CLOUDFLARE_R2_SECRET_KEY="sk",
                CLOUDFLARE_R2_PUBLIC_URL="https://cdn.example.com",
                CLOUDFLARE_R2_ENDPOINT="https://endpoint.example.com",
                RESEND_API_KEY="re_xxx",
                EMAIL_FROM="noreply@hadha.co",
                EMAIL_REPLY_TO="support@hadha.co",
                RAZORPAY_KEY_ID="rzp_key",
                RAZORPAY_KEY_SECRET="rzp_secret",
                RAZORPAY_WEBHOOK_SECRET="rzp_webhook",
                DELIVERY_ONE_BASE_URL="https://api.deliveryone.in",
                DELIVERY_ONE_API_KEY="d1key",
                DELIVERY_ONE_WEBHOOK_SECRET="d1secret",
                FRONTEND_URL="http://localhost:3000",
                ADMIN_URL="http://localhost:3001",
                SMS_ENABLED=True,
                MSG91_API_KEY="",  # missing
                MSG91_SENDER_ID="",  # missing
                MSG91_TEMPLATE_ID="",  # missing
            )
            validate_required_settings(s)

    def test_validate_passes_when_sms_disabled(self):
        from app.core.config import Settings, validate_required_settings

        s = Settings(
            SECRET_KEY="x" * 32,
            ENCRYPTION_KEY="x" * 32,
            SUPABASE_URL="https://x.supabase.co",
            SUPABASE_SERVICE_ROLE_KEY="key",
            SUPABASE_JWT_SECRET="secret",
            DATABASE_URL="postgresql+asyncpg://localhost/db",
            REDIS_URL="redis://localhost",
            CLOUDFLARE_ACCOUNT_ID="acc",
            CLOUDFLARE_R2_BUCKET="bucket",
            CLOUDFLARE_R2_ACCESS_KEY="ak",
            CLOUDFLARE_R2_SECRET_KEY="sk",
            CLOUDFLARE_R2_PUBLIC_URL="https://cdn.example.com",
            CLOUDFLARE_R2_ENDPOINT="https://endpoint.example.com",
            RESEND_API_KEY="re_xxx",
            EMAIL_FROM="noreply@hadha.co",
            EMAIL_REPLY_TO="support@hadha.co",
            RAZORPAY_KEY_ID="rzp_key",
            RAZORPAY_KEY_SECRET="rzp_secret",
            RAZORPAY_WEBHOOK_SECRET="rzp_webhook",
            DELIVERY_ONE_BASE_URL="https://api.deliveryone.in",
            DELIVERY_ONE_API_KEY="d1key",
            DELIVERY_ONE_WEBHOOK_SECRET="d1secret",
            FRONTEND_URL="http://localhost:3000",
            ADMIN_URL="http://localhost:3001",
            SMS_ENABLED=False,
            MSG91_API_KEY="",
            MSG91_SENDER_ID="",
            MSG91_TEMPLATE_ID="",
        )
        validate_required_settings(s)  # must not raise
