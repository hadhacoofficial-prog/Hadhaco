"""Tests for NotificationService."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.modules.notifications.repository import NotificationRepository
from app.modules.notifications.service import NotificationService


class TestNotificationServiceSendEmail:
    def setup_method(self):
        self.svc = NotificationService()
        self._provider_enabled_patch = patch.object(
            NotificationService, "_provider_enabled", AsyncMock(return_value=True)
        )
        self._provider_enabled_patch.start()

    def teardown_method(self):
        self._provider_enabled_patch.stop()

    async def test_send_email_skips_when_no_template(self):
        db = AsyncMock()
        with patch.object(
            NotificationRepository, "get_template", AsyncMock(return_value=None)
        ):
            await self.svc.send_email(
                db,
                user_id=uuid.uuid4(),
                event_type="nonexistent_event",
                recipient="test@example.com",
                context={},
            )
        db.commit.assert_not_called()

    async def test_send_email_skips_when_no_body(self):
        db = AsyncMock()
        mock_template = MagicMock()
        mock_template.template_body = None
        mock_template.subject = None
        with patch.object(
            NotificationRepository,
            "get_template",
            AsyncMock(return_value=mock_template),
        ):
            await self.svc.send_email(
                db,
                user_id=uuid.uuid4(),
                event_type="order_created",
                recipient="test@example.com",
                context={},
            )
        db.commit.assert_not_called()

    async def test_send_email_creates_log_and_sends(self):
        db = AsyncMock()
        mock_template = MagicMock()
        mock_template.subject = "Hello {{ name }}"
        mock_template.template_body = "<p>Hi {{ name }}</p>"
        mock_log = MagicMock()
        mock_log.id = uuid.uuid4()

        with (
            patch.object(
                NotificationRepository,
                "get_template",
                AsyncMock(return_value=mock_template),
            ),
            patch.object(
                NotificationRepository, "create_log", AsyncMock(return_value=mock_log)
            ),
            patch.object(NotificationRepository, "mark_sent", AsyncMock()),
            patch.object(
                type(self.svc._dispatcher),
                "send_email",
                AsyncMock(return_value="msg-123"),
            ),
        ):
            await self.svc.send_email(
                db,
                user_id=uuid.uuid4(),
                event_type="order_created",
                recipient="test@example.com",
                context={"name": "Alice"},
            )

    async def test_send_email_marks_failed_when_provider_fails(self):
        db = AsyncMock()
        mock_template = MagicMock()
        mock_template.subject = "Test"
        mock_template.template_body = "<p>Test</p>"
        mock_log = MagicMock()

        with (
            patch.object(
                NotificationRepository,
                "get_template",
                AsyncMock(return_value=mock_template),
            ),
            patch.object(
                NotificationRepository, "create_log", AsyncMock(return_value=mock_log)
            ),
            patch.object(NotificationRepository, "mark_failed", AsyncMock()),
            patch.object(
                type(self.svc._dispatcher),
                "send_email",
                AsyncMock(side_effect=Exception("SMTP error")),
            ),
        ):
            await self.svc.send_email(
                db,
                user_id=None,
                event_type="test",
                recipient="test@example.com",
                context={},
            )

    async def test_send_email_marks_permanently_failed_on_auth_error(self):
        from app.modules.notifications.providers.resend import ResendAuthError

        db = AsyncMock()
        mock_template = MagicMock()
        mock_template.subject = "Test"
        mock_template.template_body = "<p>Test</p>"
        mock_log = MagicMock()

        with (
            patch.object(
                NotificationRepository,
                "get_template",
                AsyncMock(return_value=mock_template),
            ),
            patch.object(
                NotificationRepository, "create_log", AsyncMock(return_value=mock_log)
            ),
            patch.object(
                NotificationRepository, "mark_permanently_failed", AsyncMock()
            ) as mock_perm,
            patch.object(
                type(self.svc._dispatcher),
                "send_email",
                AsyncMock(side_effect=ResendAuthError("bad key")),
            ),
        ):
            await self.svc.send_email(
                db,
                user_id=None,
                event_type="test",
                recipient="test@example.com",
                context={},
            )
        mock_perm.assert_awaited_once()


class TestNotificationServiceSendWhatsApp:
    def setup_method(self):
        self.svc = NotificationService()
        self._provider_enabled_patch = patch.object(
            NotificationService, "_provider_enabled", AsyncMock(return_value=True)
        )
        self._provider_enabled_patch.start()

    def teardown_method(self):
        self._provider_enabled_patch.stop()

    async def test_send_whatsapp_skips_when_disabled(self):
        db = AsyncMock()
        with patch("app.modules.notifications.service.settings") as mock_settings:
            mock_settings.WHATSAPP_ENABLED = False
            await self.svc.send_whatsapp(
                db,
                user_id=uuid.uuid4(),
                event_type="order_created",
                recipient="+919999999999",
                context={},
            )
        db.commit.assert_not_called()

    async def test_send_whatsapp_skips_when_no_template(self):
        db = AsyncMock()
        with (
            patch("app.modules.notifications.service.settings") as mock_settings,
            patch.object(
                NotificationRepository, "get_template", AsyncMock(return_value=None)
            ),
        ):
            mock_settings.WHATSAPP_ENABLED = True
            await self.svc.send_whatsapp(
                db,
                user_id=uuid.uuid4(),
                event_type="order_created",
                recipient="+919999999999",
                context={},
            )
        db.commit.assert_not_called()

    async def test_send_whatsapp_skips_when_no_body(self):
        db = AsyncMock()
        mock_template = MagicMock()
        mock_template.template_body = None
        with (
            patch("app.modules.notifications.service.settings") as mock_settings,
            patch.object(
                NotificationRepository,
                "get_template",
                AsyncMock(return_value=mock_template),
            ),
        ):
            mock_settings.WHATSAPP_ENABLED = True
            await self.svc.send_whatsapp(
                db,
                user_id=uuid.uuid4(),
                event_type="order_created",
                recipient="+919999999999",
                context={},
            )
        db.commit.assert_not_called()

    async def test_send_whatsapp_creates_log_and_sends(self):
        db = AsyncMock()
        mock_template = MagicMock()
        mock_template.template_body = "Order {{ order_number }} confirmed"
        mock_template.variables = {
            "whatsapp_template": "order_created",
            "whatsapp_lang": "en_US",
            "params": ["order_number"],
        }
        mock_log = MagicMock()
        mock_log.id = uuid.uuid4()

        with (
            patch("app.modules.notifications.service.settings") as mock_settings,
            patch.object(
                NotificationRepository,
                "get_template",
                AsyncMock(return_value=mock_template),
            ),
            patch.object(
                NotificationRepository, "create_log", AsyncMock(return_value=mock_log)
            ),
            patch.object(NotificationRepository, "mark_sent", AsyncMock()),
            patch.object(
                type(self.svc._dispatcher),
                "send_whatsapp_template",
                AsyncMock(return_value="wa-msg-123"),
            ),
        ):
            mock_settings.WHATSAPP_ENABLED = True
            await self.svc.send_whatsapp(
                db,
                user_id=uuid.uuid4(),
                event_type="order_created",
                recipient="+919999999999",
                context={"order_number": "ORD-001"},
            )

    async def test_send_whatsapp_marks_failed_on_error(self):
        db = AsyncMock()
        mock_template = MagicMock()
        mock_template.template_body = "Hello"
        mock_template.variables = None
        mock_log = MagicMock()

        with (
            patch("app.modules.notifications.service.settings") as mock_settings,
            patch.object(
                NotificationRepository,
                "get_template",
                AsyncMock(return_value=mock_template),
            ),
            patch.object(
                NotificationRepository, "create_log", AsyncMock(return_value=mock_log)
            ),
            patch.object(NotificationRepository, "mark_failed", AsyncMock()),
            patch.object(
                type(self.svc._dispatcher),
                "send_whatsapp_template",
                AsyncMock(side_effect=Exception("WhatsApp API down")),
            ),
        ):
            mock_settings.WHATSAPP_ENABLED = True
            await self.svc.send_whatsapp(
                db,
                user_id=None,
                event_type="test",
                recipient="+919999999999",
                context={},
            )


class TestNotificationServiceRetry:
    def setup_method(self):
        from app.modules.notifications.service import NotificationService

        self.svc = NotificationService()

    async def test_retry_pending_with_no_retries(self):
        db = AsyncMock()
        with patch.object(
            NotificationRepository, "get_pending_retries", AsyncMock(return_value=[])
        ):
            await self.svc.retry_pending(db)

    async def test_retry_log_returns_early_when_no_template(self):
        db = AsyncMock()
        mock_log = MagicMock()
        mock_log.event_type = "order_created"
        mock_log.channel = "email"
        await self.svc._retry_log(db, mock_log, None)

    async def test_retry_log_email_success(self):
        db = AsyncMock()
        mock_log = MagicMock()
        mock_log.event_type = "order_created"
        mock_log.channel = "email"
        mock_log.recipient = "test@example.com"
        mock_template = MagicMock()
        mock_template.subject = "Test"
        mock_template.template_body = "<p>Hello</p>"
        with (
            patch.object(NotificationRepository, "mark_sent", AsyncMock()) as mock_sent,
            patch.object(
                type(self.svc._dispatcher),
                "send_email",
                AsyncMock(return_value="msg-retry"),
            ),
        ):
            await self.svc._retry_log(db, mock_log, mock_template)
        mock_sent.assert_awaited_once()

    async def test_retry_log_whatsapp_success_when_enabled(self):
        db = AsyncMock()
        mock_log = MagicMock()
        mock_log.event_type = "order_shipped"
        mock_log.channel = "whatsapp"
        mock_log.recipient = "+919876543210"
        mock_log.whatsapp_params = None  # legacy log without stored params
        mock_template = MagicMock()
        mock_template.template_body = "Order shipped"
        mock_template.variables = None
        with (
            patch("app.modules.notifications.service.settings") as mock_settings,
            patch.object(NotificationRepository, "mark_sent", AsyncMock()) as mock_sent,
            patch.object(
                type(self.svc._dispatcher),
                "send_whatsapp_template",
                AsyncMock(return_value="wa-retry"),
            ),
        ):
            mock_settings.WHATSAPP_ENABLED = True
            await self.svc._retry_log(db, mock_log, mock_template)
        mock_sent.assert_awaited_once()

    async def test_retry_log_whatsapp_uses_stored_params(self):
        db = AsyncMock()
        mock_log = MagicMock()
        mock_log.event_type = "order_shipped"
        mock_log.channel = "whatsapp"
        mock_log.recipient = "+919876543210"
        mock_log.whatsapp_params = {
            "template_name": "order_shipped",
            "language": "en_US",
            "params": ["#12345"],
        }
        mock_template = MagicMock()
        mock_template.template_body = "Order shipped"
        with (
            patch("app.modules.notifications.service.settings") as mock_settings,
            patch.object(NotificationRepository, "mark_sent", AsyncMock()) as mock_sent,
            patch("app.modules.notifications.service.registry") as mock_registry,
        ):
            mock_settings.WHATSAPP_ENABLED = True
            mock_provider = AsyncMock()
            mock_provider.send_whatsapp = AsyncMock(return_value="wa-stored")
            mock_registry.get_whatsapp_provider.return_value = mock_provider
            await self.svc._retry_log(db, mock_log, mock_template)
        mock_sent.assert_awaited_once()
        mock_provider.send_whatsapp.assert_awaited_once_with(
            db,
            to="+919876543210",
            template_name="order_shipped",
            language="en_US",
            components=[
                {"type": "body", "parameters": [{"type": "text", "text": "#12345"}]}
            ],
        )

    async def test_retry_log_whatsapp_skipped_when_disabled(self):
        db = AsyncMock()
        mock_log = MagicMock()
        mock_log.event_type = "order_shipped"
        mock_log.channel = "whatsapp"
        mock_log.recipient = "+919876543210"
        mock_template = MagicMock()
        mock_template.template_body = "Order shipped"
        with patch("app.modules.notifications.service.settings") as mock_settings:
            mock_settings.WHATSAPP_ENABLED = False
            await self.svc._retry_log(db, mock_log, mock_template)
        db.commit.assert_not_called()

    async def test_retry_log_marks_failed_on_error(self):
        db = AsyncMock()
        mock_log = MagicMock()
        mock_log.event_type = "order_created"
        mock_log.channel = "email"
        mock_log.recipient = "test@example.com"
        mock_template = MagicMock()
        mock_template.subject = "Test"
        mock_template.template_body = "HTML"
        with (
            patch.object(
                NotificationRepository, "mark_failed", AsyncMock()
            ) as mock_failed,
            patch.object(
                type(self.svc._dispatcher),
                "send_email",
                AsyncMock(side_effect=Exception("Send error")),
            ),
        ):
            await self.svc._retry_log(db, mock_log, mock_template)
        mock_failed.assert_awaited_once()


class TestNotificationServiceDispatch:
    def setup_method(self):
        from app.modules.notifications.service import NotificationService

        self.svc = NotificationService()

    async def test_dispatch_sends_email_when_rule_enabled(self):
        db = AsyncMock()
        with (
            patch.object(
                NotificationRepository,
                "should_send",
                AsyncMock(return_value=True),
            ),
            patch.object(
                NotificationRepository,
                "get_preferences_for_channel",
                AsyncMock(return_value=True),
            ),
            patch.object(self.svc, "send_email", AsyncMock()) as mock_email,
            patch.object(self.svc, "send_whatsapp", AsyncMock()),
        ):
            await self.svc.dispatch(
                db,
                user_id=uuid.uuid4(),
                event_type="order_created",
                recipient="test@example.com",
                context={"order_number": "ORD-001"},
            )
        mock_email.assert_awaited_once()

    async def test_dispatch_skips_email_when_rule_disabled(self):
        db = AsyncMock()
        with (
            patch.object(
                NotificationRepository,
                "should_send",
                AsyncMock(return_value=False),
            ),
            patch.object(self.svc, "send_email", AsyncMock()) as mock_email,
            patch.object(self.svc, "send_whatsapp", AsyncMock()),
        ):
            await self.svc.dispatch(
                db,
                user_id=uuid.uuid4(),
                event_type="order_created",
                recipient="test@example.com",
                context={"order_number": "ORD-001"},
            )
        mock_email.assert_not_awaited()

    async def test_dispatch_skips_email_when_user_preference_disabled(self):
        db = AsyncMock()
        with (
            patch.object(
                NotificationRepository,
                "should_send",
                AsyncMock(return_value=True),
            ),
            patch.object(
                NotificationRepository,
                "get_preferences_for_channel",
                AsyncMock(return_value=False),
            ),
            patch.object(self.svc, "send_email", AsyncMock()) as mock_email,
            patch.object(self.svc, "send_whatsapp", AsyncMock()),
        ):
            await self.svc.dispatch(
                db,
                user_id=uuid.uuid4(),
                event_type="order_created",
                recipient="test@example.com",
                context={"order_number": "ORD-001"},
            )
        mock_email.assert_not_awaited()

    async def test_dispatch_sends_whatsapp_when_phone_provided(self):
        db = AsyncMock()
        with (
            patch.object(
                NotificationRepository,
                "should_send",
                AsyncMock(return_value=True),
            ),
            patch.object(
                NotificationRepository,
                "get_preferences_for_channel",
                AsyncMock(return_value=True),
            ),
            patch.object(self.svc, "send_email", AsyncMock()),
            patch.object(self.svc, "send_whatsapp", AsyncMock()) as mock_wa,
        ):
            await self.svc.dispatch(
                db,
                user_id=uuid.uuid4(),
                event_type="order_created",
                recipient="test@example.com",
                recipient_phone="+919999999999",
                context={"order_number": "ORD-001"},
            )
        mock_wa.assert_awaited_once()

    async def test_dispatch_skips_whatsapp_when_no_phone(self):
        db = AsyncMock()
        with (
            patch.object(
                NotificationRepository,
                "should_send",
                AsyncMock(return_value=True),
            ),
            patch.object(
                NotificationRepository,
                "get_preferences_for_channel",
                AsyncMock(return_value=True),
            ),
            patch.object(self.svc, "send_email", AsyncMock()),
            patch.object(self.svc, "send_whatsapp", AsyncMock()) as mock_wa,
        ):
            await self.svc.dispatch(
                db,
                user_id=uuid.uuid4(),
                event_type="order_created",
                recipient="test@example.com",
                context={"order_number": "ORD-001"},
            )
        mock_wa.assert_not_awaited()

    async def test_dispatch_master_switch_blocks_all_channels(self):
        """should_send already encodes the `enabled` master switch (see
        NotificationRepository.should_send) — dispatch relies on it, no
        separate branch needed."""
        db = AsyncMock()
        with (
            patch.object(
                NotificationRepository,
                "should_send",
                AsyncMock(return_value=False),
            ),
            patch.object(self.svc, "send_email", AsyncMock()) as mock_email,
            patch.object(self.svc, "send_whatsapp", AsyncMock()) as mock_wa,
        ):
            await self.svc.dispatch(
                db,
                user_id=uuid.uuid4(),
                event_type="order_created",
                recipient="test@example.com",
                recipient_phone="+919999999999",
                context={"order_number": "ORD-001"},
            )
        mock_email.assert_not_awaited()
        mock_wa.assert_not_awaited()
