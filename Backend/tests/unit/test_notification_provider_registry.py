"""Tests for the notification ProviderRegistry, NotificationDispatcher, and the
WhatsApp webhook signature helper."""

import hashlib
import hmac
from unittest.mock import AsyncMock, patch

import pytest

from app.core.security import verify_whatsapp_webhook_signature
from app.modules.notifications.dispatcher import NotificationDispatcher
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
        db = AsyncMock()
        with patch("app.modules.notifications.dispatcher.registry") as mock_registry:
            mock_provider = AsyncMock()
            mock_provider.send_email = AsyncMock(return_value="msg-1")
            mock_registry.get_email_provider.return_value = mock_provider
            result = await dispatcher.send_email(
                db, to="a@b.com", subject="Hi", html="<p>hi</p>"
            )
        assert result == "msg-1"
        mock_provider.send_email.assert_awaited_once_with(
            db, to="a@b.com", subject="Hi", html="<p>hi</p>"
        )

    async def test_send_whatsapp_template_builds_components_from_variables(self):
        dispatcher = NotificationDispatcher()
        db = AsyncMock()
        template = type(
            "T",
            (),
            {
                "name": "order_created_whatsapp",
                "variables": {
                    "whatsapp_template": "order_created",
                    "whatsapp_lang": "en_US",
                    "params": ["order_number", "total"],
                },
            },
        )()
        with patch("app.modules.notifications.dispatcher.registry") as mock_registry:
            mock_provider = AsyncMock()
            mock_provider.send_whatsapp = AsyncMock(return_value="wa-1")
            mock_registry.get_whatsapp_provider.return_value = mock_provider
            result = await dispatcher.send_whatsapp_template(
                db,
                to="+919999999999",
                template=template,
                context={"order_number": "ORD-1", "total": "500"},
            )
        assert result == "wa-1"
        _, kwargs = mock_provider.send_whatsapp.call_args
        assert kwargs["template_name"] == "order_created"
        assert kwargs["language"] == "en_US"
        assert kwargs["components"] == [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": "ORD-1"},
                    {"type": "text", "text": "500"},
                ],
            }
        ]

    async def test_send_whatsapp_template_with_no_params_sends_no_components(self):
        dispatcher = NotificationDispatcher()
        db = AsyncMock()
        template = type("T", (), {"name": "low_stock", "variables": None})()
        with patch("app.modules.notifications.dispatcher.registry") as mock_registry:
            mock_provider = AsyncMock()
            mock_provider.send_whatsapp = AsyncMock(return_value="wa-2")
            mock_registry.get_whatsapp_provider.return_value = mock_provider
            await dispatcher.send_whatsapp_template(
                db, to="+919999999999", template=template, context={}
            )
        _, kwargs = mock_provider.send_whatsapp.call_args
        assert kwargs["components"] == []
        assert kwargs["template_name"] == "low_stock"


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
