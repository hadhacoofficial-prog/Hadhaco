"""Tests for PaymentService and NotificationService."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ─── PaymentService ───────────────────────────────────────────────────────────


class TestPaymentServiceCreateOrder:
    def setup_method(self):
        from app.modules.payments.service import PaymentService

        self.svc = PaymentService()

    async def test_raises_404_when_order_not_found(self):
        from app.core.exceptions import NotFoundError
        from app.modules.orders.repository import OrderRepository
        from app.modules.payments.schemas import CreatePaymentOrderRequest

        db = AsyncMock()
        with patch.object(OrderRepository, "get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.create_razorpay_order(
                    db, uuid.uuid4(), CreatePaymentOrderRequest(order_id=uuid.uuid4())
                )

    async def test_raises_404_when_wrong_user(self):
        from app.core.exceptions import NotFoundError
        from app.modules.orders.repository import OrderRepository
        from app.modules.payments.schemas import CreatePaymentOrderRequest

        db = AsyncMock()
        mock_order = MagicMock()
        mock_order.user_id = uuid.uuid4()  # different user
        with patch.object(OrderRepository, "get_by_id", AsyncMock(return_value=mock_order)):
            with pytest.raises(NotFoundError):
                await self.svc.create_razorpay_order(
                    db, uuid.uuid4(), CreatePaymentOrderRequest(order_id=uuid.uuid4())
                )

    async def test_raises_validation_error_when_already_paid(self):
        from app.core.exceptions import ValidationError
        from app.modules.orders.repository import OrderRepository
        from app.modules.payments.schemas import CreatePaymentOrderRequest

        db = AsyncMock()
        user_id = uuid.uuid4()
        mock_order = MagicMock()
        mock_order.user_id = user_id
        mock_order.payment_status = "paid"
        with patch.object(OrderRepository, "get_by_id", AsyncMock(return_value=mock_order)):
            with pytest.raises(ValidationError, match="already paid"):
                await self.svc.create_razorpay_order(
                    db, user_id, CreatePaymentOrderRequest(order_id=uuid.uuid4())
                )

    async def test_raises_validation_error_when_order_cancelled(self):
        from app.core.exceptions import ValidationError
        from app.modules.orders.repository import OrderRepository
        from app.modules.payments.schemas import CreatePaymentOrderRequest

        db = AsyncMock()
        user_id = uuid.uuid4()
        mock_order = MagicMock()
        mock_order.user_id = user_id
        mock_order.payment_status = "pending"
        mock_order.status = "cancelled"
        with patch.object(OrderRepository, "get_by_id", AsyncMock(return_value=mock_order)):
            with pytest.raises(ValidationError, match="cancelled"):
                await self.svc.create_razorpay_order(
                    db, user_id, CreatePaymentOrderRequest(order_id=uuid.uuid4())
                )


class TestPaymentServiceVerifyAndCapture:
    def setup_method(self):
        from app.modules.payments.service import PaymentService

        self.svc = PaymentService()

    async def test_raises_404_when_payment_not_found(self):
        from app.core.exceptions import NotFoundError
        from app.modules.payments.schemas import VerifyPaymentRequest

        db = AsyncMock()
        with patch("app.modules.payments.service._repo.get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.verify_and_capture(
                    db,
                    uuid.uuid4(),
                    VerifyPaymentRequest(
                        payment_id=uuid.uuid4(),
                        razorpay_order_id="order_abc",
                        razorpay_payment_id="pay_abc",
                        razorpay_signature="sig_abc",
                    ),
                )

    async def test_raises_404_when_wrong_user(self):
        from app.core.exceptions import NotFoundError
        from app.modules.payments.schemas import VerifyPaymentRequest

        db = AsyncMock()
        mock_payment = MagicMock()
        mock_payment.user_id = uuid.uuid4()
        with patch(
            "app.modules.payments.service._repo.get_by_id", AsyncMock(return_value=mock_payment)
        ):
            with pytest.raises(NotFoundError):
                await self.svc.verify_and_capture(
                    db,
                    uuid.uuid4(),
                    VerifyPaymentRequest(
                        payment_id=uuid.uuid4(),
                        razorpay_order_id="order_abc",
                        razorpay_payment_id="pay_abc",
                        razorpay_signature="sig_abc",
                    ),
                )

    async def test_returns_response_when_already_captured(self):
        from app.modules.payments.schemas import VerifyPaymentRequest

        db = AsyncMock()
        user_id = uuid.uuid4()
        mock_payment = MagicMock()
        mock_payment.user_id = user_id
        mock_payment.status = "captured"
        with (
            patch(
                "app.modules.payments.service._repo.get_by_id", AsyncMock(return_value=mock_payment)
            ),
            patch(
                "app.modules.payments.service.PaymentResponse.model_validate",
                return_value=MagicMock(),
            ),
        ):
            result = await self.svc.verify_and_capture(
                db,
                user_id,
                VerifyPaymentRequest(
                    payment_id=uuid.uuid4(),
                    razorpay_order_id="order_abc",
                    razorpay_payment_id="pay_abc",
                    razorpay_signature="sig_abc",
                ),
            )
        assert result is not None

    async def test_raises_validation_error_when_signature_invalid(self):
        from app.core.events import event_bus
        from app.core.exceptions import ValidationError
        from app.modules.payments.schemas import VerifyPaymentRequest

        db = AsyncMock()
        user_id = uuid.uuid4()
        mock_payment = MagicMock()
        mock_payment.user_id = user_id
        mock_payment.status = "created"
        with (
            patch(
                "app.modules.payments.service._repo.get_by_id", AsyncMock(return_value=mock_payment)
            ),
            patch("app.modules.payments.service._verify_signature", return_value=False),
            patch("app.modules.payments.service._repo.update", AsyncMock()),
            patch.object(event_bus, "publish", AsyncMock()),
        ):
            with pytest.raises(ValidationError, match="signature"):
                await self.svc.verify_and_capture(
                    db,
                    user_id,
                    VerifyPaymentRequest(
                        payment_id=uuid.uuid4(),
                        razorpay_order_id="order_abc",
                        razorpay_payment_id="pay_abc",
                        razorpay_signature="bad_sig",
                    ),
                )


class TestPaymentServiceGetAndRefund:
    def setup_method(self):
        from app.modules.payments.service import PaymentService

        self.svc = PaymentService()

    async def test_get_payment_for_order_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        with patch(
            "app.modules.payments.service._repo.get_for_order", AsyncMock(return_value=None)
        ):
            with pytest.raises(NotFoundError):
                await self.svc.get_payment_for_order(db, uuid.uuid4())

    async def test_get_payment_for_order_raises_404_when_wrong_user(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        mock_payment = MagicMock()
        mock_payment.user_id = uuid.uuid4()
        with patch(
            "app.modules.payments.service._repo.get_for_order", AsyncMock(return_value=mock_payment)
        ):
            with pytest.raises(NotFoundError):
                await self.svc.get_payment_for_order(db, uuid.uuid4(), user_id=uuid.uuid4())

    async def test_get_payment_for_order_success(self):
        db = AsyncMock()
        user_id = uuid.uuid4()
        mock_payment = MagicMock()
        mock_payment.user_id = user_id
        with (
            patch(
                "app.modules.payments.service._repo.get_for_order",
                AsyncMock(return_value=mock_payment),
            ),
            patch(
                "app.modules.payments.service.PaymentResponse.model_validate",
                return_value=MagicMock(),
            ),
        ):
            result = await self.svc.get_payment_for_order(db, uuid.uuid4(), user_id=user_id)
        assert result is not None

    async def test_initiate_refund_raises_404_when_no_payment(self):
        from app.core.exceptions import NotFoundError
        from app.modules.payments.schemas import RefundRequest

        db = AsyncMock()
        with patch(
            "app.modules.payments.service._repo.get_for_order", AsyncMock(return_value=None)
        ):
            with pytest.raises(NotFoundError):
                await self.svc.initiate_refund(db, uuid.uuid4(), RefundRequest(reason="Defective"))

    async def test_initiate_refund_raises_validation_error_when_not_captured(self):
        from app.core.exceptions import ValidationError
        from app.modules.payments.schemas import RefundRequest

        db = AsyncMock()
        mock_payment = MagicMock()
        mock_payment.status = "created"  # not "captured"
        with patch(
            "app.modules.payments.service._repo.get_for_order", AsyncMock(return_value=mock_payment)
        ):
            with pytest.raises(ValidationError, match="Cannot refund"):
                await self.svc.initiate_refund(db, uuid.uuid4(), RefundRequest(reason="Defective"))

    async def test_initiate_refund_raises_validation_error_when_amount_exceeds(self):
        from app.core.exceptions import ValidationError
        from app.modules.payments.schemas import RefundRequest

        db = AsyncMock()
        mock_payment = MagicMock()
        mock_payment.status = "captured"
        mock_payment.amount = 500.0
        with patch(
            "app.modules.payments.service._repo.get_for_order", AsyncMock(return_value=mock_payment)
        ):
            with pytest.raises(ValidationError, match="exceeds"):
                await self.svc.initiate_refund(
                    db, uuid.uuid4(), RefundRequest(reason="Defective", amount=999.0)
                )

    async def test_list_refunds_returns_validated_list(self):
        db = AsyncMock()
        mock_refund = MagicMock()
        with (
            patch(
                "app.modules.payments.service._repo.get_refunds_for_order",
                AsyncMock(return_value=[mock_refund]),
            ),
            patch(
                "app.modules.payments.service.RefundResponse.model_validate",
                return_value=MagicMock(),
            ),
        ):
            result = await self.svc.list_refunds(db, uuid.uuid4())
        assert len(result) == 1


# ─── _verify_signature pure function ─────────────────────────────────────────


class TestVerifySignature:
    def test_returns_false_on_bad_signature(self):
        from app.modules.payments.service import _verify_signature

        result = _verify_signature("order_abc", "pay_abc", "bad_sig")
        assert result is False

    def test_correct_signature_returns_true(self):
        import hashlib
        import hmac as hmac_mod

        from app.core.config import settings
        from app.modules.payments.service import _verify_signature

        msg = "order_abc|pay_abc"
        expected = hmac_mod.new(
            settings.RAZORPAY_KEY_SECRET.encode(),
            msg.encode(),
            hashlib.sha256,
        ).hexdigest()
        assert _verify_signature("order_abc", "pay_abc", expected) is True


# ─── NotificationService ──────────────────────────────────────────────────────


class TestNotificationServiceSendEmail:
    def setup_method(self):
        from app.modules.notifications.repository import NotificationRepository
        from app.modules.notifications.service import NotificationService

        self.svc = NotificationService()
        self.repo_cls = NotificationRepository

    async def test_send_email_returns_early_when_no_template(self):
        db = AsyncMock()
        with patch.object(self.repo_cls, "get_template", AsyncMock(return_value=None)):
            await self.svc.send_email(
                db,
                user_id=uuid.uuid4(),
                event_type="order_created",
                recipient="test@example.com",
                context={"order_number": "ORD-001"},
            )
        # No log should be created since we return early

    async def test_send_email_success_marks_sent(self):
        db = AsyncMock()
        mock_template = MagicMock()
        mock_template.subject = "Order Confirmed"
        mock_template.template_body = "Hello {{ full_name }}"
        mock_log = MagicMock()

        with (
            patch.object(self.repo_cls, "get_template", AsyncMock(return_value=mock_template)),
            patch.object(self.repo_cls, "create_log", AsyncMock(return_value=mock_log)),
            patch.object(self.repo_cls, "mark_sent", AsyncMock()) as mock_sent,
            patch.object(self.svc._email_primary, "send_email", AsyncMock(return_value="msg-123")),
        ):
            await self.svc.send_email(
                db,
                user_id=uuid.uuid4(),
                event_type="order_created",
                recipient="test@example.com",
                context={"full_name": "Alice"},
            )
        mock_sent.assert_awaited_once()

    async def test_send_email_marks_failed_when_primary_fails(self):
        db = AsyncMock()
        mock_template = MagicMock()
        mock_template.subject = "Test"
        mock_template.template_body = "Hello"
        mock_log = MagicMock()

        with (
            patch.object(self.repo_cls, "get_template", AsyncMock(return_value=mock_template)),
            patch.object(self.repo_cls, "create_log", AsyncMock(return_value=mock_log)),
            patch.object(self.repo_cls, "mark_failed", AsyncMock()) as mock_failed,
            patch.object(
                self.svc._email_primary, "send_email", AsyncMock(side_effect=Exception("SMTP down"))
            ),
        ):
            await self.svc.send_email(
                db,
                user_id=None,
                event_type="test",
                recipient="test@example.com",
                context={},
            )
        mock_failed.assert_awaited_once()


class TestNotificationServiceSendSMS:
    def setup_method(self):
        from app.modules.notifications.repository import NotificationRepository
        from app.modules.notifications.service import NotificationService

        self.svc = NotificationService()
        self.repo_cls = NotificationRepository

    async def test_send_sms_returns_early_when_no_template(self):
        db = AsyncMock()
        with patch.object(self.repo_cls, "get_template", AsyncMock(return_value=None)):
            await self.svc.send_sms(
                db,
                user_id=uuid.uuid4(),
                event_type="order_shipped",
                recipient="+919876543210",
                context={},
            )

    async def test_send_sms_success_marks_sent_when_enabled(self):
        db = AsyncMock()
        mock_template = MagicMock()
        mock_template.template_body = "Your order {{ order_number }} shipped"
        mock_log = MagicMock()
        with (
            patch("app.modules.notifications.service.settings") as mock_settings,
            patch.object(self.repo_cls, "get_template", AsyncMock(return_value=mock_template)),
            patch.object(self.repo_cls, "create_log", AsyncMock(return_value=mock_log)),
            patch.object(self.repo_cls, "mark_sent", AsyncMock()) as mock_sent,
            patch.object(self.svc._sms, "send_sms", AsyncMock(return_value="req-123")),
        ):
            mock_settings.SMS_ENABLED = True
            await self.svc.send_sms(
                db,
                user_id=uuid.uuid4(),
                event_type="order_shipped",
                recipient="+919876543210",
                context={"order_number": "ORD-001"},
            )
        mock_sent.assert_awaited_once()

    async def test_send_sms_skipped_when_disabled(self):
        db = AsyncMock()
        with patch("app.modules.notifications.service.settings") as mock_settings:
            mock_settings.SMS_ENABLED = False
            await self.svc.send_sms(
                db,
                user_id=None,
                event_type="order_shipped",
                recipient="+919876543210",
                context={},
            )
        db.commit.assert_not_called()

    async def test_send_sms_marks_failed_on_error(self):
        db = AsyncMock()
        mock_template = MagicMock()
        mock_template.template_body = "SMS body"
        mock_log = MagicMock()
        with (
            patch("app.modules.notifications.service.settings") as mock_settings,
            patch.object(self.repo_cls, "get_template", AsyncMock(return_value=mock_template)),
            patch.object(self.repo_cls, "create_log", AsyncMock(return_value=mock_log)),
            patch.object(self.repo_cls, "mark_failed", AsyncMock()) as mock_failed,
            patch.object(self.svc._sms, "send_sms", AsyncMock(side_effect=Exception("MSG91 down"))),
        ):
            mock_settings.SMS_ENABLED = True
            await self.svc.send_sms(
                db,
                user_id=None,
                event_type="order_shipped",
                recipient="+919876543210",
                context={},
            )
        mock_failed.assert_awaited_once()


class TestNotificationServiceRetry:
    def setup_method(self):
        from app.modules.notifications.repository import NotificationRepository
        from app.modules.notifications.service import NotificationService

        self.svc = NotificationService()
        self.repo_cls = NotificationRepository

    async def test_retry_pending_calls_retry_for_each_log(self):
        db = AsyncMock()
        mock_log1 = MagicMock()
        mock_log2 = MagicMock()
        with (
            patch.object(
                self.repo_cls, "get_pending_retries", AsyncMock(return_value=[mock_log1, mock_log2])
            ),
            patch.object(self.svc, "_retry_log", AsyncMock()) as mock_retry,
        ):
            await self.svc.retry_pending(db)
        assert mock_retry.await_count == 2

    async def test_retry_log_returns_early_when_no_template(self):
        db = AsyncMock()
        mock_log = MagicMock()
        mock_log.event_type = "order_created"
        mock_log.channel = "email"
        with patch.object(self.repo_cls, "get_template", AsyncMock(return_value=None)):
            await self.svc._retry_log(db, mock_log)

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
            patch.object(self.repo_cls, "get_template", AsyncMock(return_value=mock_template)),
            patch.object(self.repo_cls, "mark_sent", AsyncMock()) as mock_sent,
            patch.object(
                self.svc._email_primary, "send_email", AsyncMock(return_value="msg-retry")
            ),
        ):
            await self.svc._retry_log(db, mock_log)
        mock_sent.assert_awaited_once()

    async def test_retry_log_sms_success_when_enabled(self):
        db = AsyncMock()
        mock_log = MagicMock()
        mock_log.event_type = "order_shipped"
        mock_log.channel = "sms"
        mock_log.recipient = "+919876543210"
        mock_template = MagicMock()
        mock_template.subject = None
        mock_template.template_body = "Order shipped"
        with (
            patch("app.modules.notifications.service.settings") as mock_settings,
            patch.object(self.repo_cls, "get_template", AsyncMock(return_value=mock_template)),
            patch.object(self.repo_cls, "mark_sent", AsyncMock()) as mock_sent,
            patch.object(self.svc._sms, "send_sms", AsyncMock(return_value="req-retry")),
        ):
            mock_settings.SMS_ENABLED = True
            await self.svc._retry_log(db, mock_log)
        mock_sent.assert_awaited_once()

    async def test_retry_log_sms_skipped_when_disabled(self):
        db = AsyncMock()
        mock_log = MagicMock()
        mock_log.event_type = "order_shipped"
        mock_log.channel = "sms"
        mock_log.recipient = "+919876543210"
        mock_template = MagicMock()
        mock_template.subject = None
        mock_template.template_body = "Order shipped"
        with (
            patch("app.modules.notifications.service.settings") as mock_settings,
            patch.object(self.repo_cls, "get_template", AsyncMock(return_value=mock_template)),
        ):
            mock_settings.SMS_ENABLED = False
            await self.svc._retry_log(db, mock_log)
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
            patch.object(self.repo_cls, "get_template", AsyncMock(return_value=mock_template)),
            patch.object(self.repo_cls, "mark_failed", AsyncMock()) as mock_failed,
            patch.object(
                self.svc._email_primary,
                "send_email",
                AsyncMock(side_effect=Exception("Send error")),
            ),
        ):
            await self.svc._retry_log(db, mock_log)
        mock_failed.assert_awaited_once()
