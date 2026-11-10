"""Tests for the notification ProviderRegistry, NotificationDispatcher, and the
WhatsApp webhook signature helper."""

import hashlib
import hmac
from unittest.mock import AsyncMock, patch

import pytest

from app.core.security import verify_whatsapp_webhook_signature
from app.modules.notifications.dispatcher import NotificationDispatcher
from app.modules.notifications.dto import EmailPayload, WhatsAppPayload
from app.modules.notifications.providers.registry import ProviderRegistry
from app.modules.notifications.providers.resend import ResendProvider
from app.modules.notifications.providers.whatsapp import WhatsAppProvider


class TestProviderRegistry:
    def test_get_email_provider_returns_resend(self):
        registry = ProviderRegistry()
        assert isinstance(registry.get_email_provider(), ResendProvider)

    def test_get_whatsapp_provider_returns_meta(self):
        registry = ProviderRegistry()
        assert isinstance(registry.get_whatsapp_provider(), WhatsAppProvider)

    def test_unknown_email_provider_raises(self):
        registry = ProviderRegistry()
        with pytest.raises(ValueError):
            registry.get_email_provider("nonexistent")

    def test_unknown_whatsapp_provider_raises(self):
        registry = ProviderRegistry()
        with pytest.raises(ValueError):
            registry.get_whatsapp_provider("nonexistent")


class TestNotificationDispatcher:
    async def test_send_email_delegates_to_registry_provider(self):
        dispatcher = NotificationDispatcher()
        payload = EmailPayload(
            to="a@b.com",
            subject="Hi",
            html="<p>hi</p>",
            api_key="test_key",
            from_name="Test",
            from_email="test@example.com",
            reply_to="reply@example.com",
        )
        with patch("app.modules.notifications.dispatcher.registry") as mock_registry:
            mock_provider = AsyncMock()
            mock_provider.send_email = AsyncMock(return_value="msg-1")
            mock_registry.get_email_provider.return_value = mock_provider
            result = await dispatcher.send_email(payload)
        assert result == "msg-1"
        mock_provider.send_email.assert_awaited_once_with(payload)

    async def test_send_whatsapp_delegates_to_registry_provider(self):
        dispatcher = NotificationDispatcher()
        payload = WhatsAppPayload(
            to="+919999999999",
            template_name="order_created",
            language="en_US",
            components=[
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": "ORD-1"},
                        {"type": "text", "text": "500"},
                    ],
                }
            ],
            access_token="test_token",
            phone_number_id="123",
            api_version="v18.0",
        )
        with patch("app.modules.notifications.dispatcher.registry") as mock_registry:
            mock_provider = AsyncMock()
            mock_provider.send_whatsapp = AsyncMock(return_value="wa-1")
            mock_registry.get_whatsapp_provider.return_value = mock_provider
            result = await dispatcher.send_whatsapp(payload)
        assert result == "wa-1"
        mock_provider.send_whatsapp.assert_awaited_once_with(payload)

    async def test_send_whatsapp_with_no_components(self):
        dispatcher = NotificationDispatcher()
        payload = WhatsAppPayload(
            to="+919999999999",
            template_name="low_stock",
            language="en_US",
            components=[],
        )
        with patch("app.modules.notifications.dispatcher.registry") as mock_registry:
            mock_provider = AsyncMock()
            mock_provider.send_whatsapp = AsyncMock(return_value="wa-2")
            mock_registry.get_whatsapp_provider.return_value = mock_provider
            await dispatcher.send_whatsapp(payload)
        mock_provider.send_whatsapp.assert_awaited_once_with(payload)


class TestWhatsAppWebhookSignature:
    def test_valid_signature_passes(self):
        with patch("app.core.security.settings") as mock_settings:
            mock_settings.WHATSAPP_WEBHOOK_SECRET = "test-secret"
            body = b'{"entry": []}'
            digest = hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
            assert verify_whatsapp_webhook_signature(body, f"sha256={digest}")

    def test_invalid_signature_fails(self):
        with patch("app.core.security.settings") as mock_settings:
            mock_settings.WHATSAPP_WEBHOOK_SECRET = "test-secret"
            body = b'{"entry": []}'
            assert not verify_whatsapp_webhook_signature(body, "sha256=deadbeef")

    def test_missing_prefix_fails(self):
        with patch("app.core.security.settings") as mock_settings:
            mock_settings.WHATSAPP_WEBHOOK_SECRET = "test-secret"
            assert not verify_whatsapp_webhook_signature(b"body", "not-a-signature")
