"""Tests for PaymentService, WebhookService, and pure payment functions."""

import hashlib
import hmac
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.orders.repository import OrderRepository

# ─── Payment Signature Pure Functions ─────────────────────────────────────────


class TestPaymentSignatureVerification:
    """Test HMAC signature helpers (pure functions, no DB)."""

    def test_verify_signature_returns_true_for_valid_sig(self):
        from app.core.config import settings
        from app.modules.payments.service import _verify_signature

        rzp_order_id = "order_abc123"
        rzp_payment_id = "pay_xyz789"
        msg = f"{rzp_order_id}|{rzp_payment_id}"
        valid_sig = hmac.new(
            settings.RAZORPAY_KEY_SECRET.encode(),
            msg.encode(),
            hashlib.sha256,
        ).hexdigest()
        assert _verify_signature(rzp_order_id, rzp_payment_id, valid_sig) is True

    def test_verify_signature_returns_false_for_invalid_sig(self):
        from app.modules.payments.service import _verify_signature

        assert _verify_signature("order_abc", "pay_xyz", "wrong_signature") is False

    def test_verify_signature_different_order_id_fails(self):
        from app.core.config import settings
        from app.modules.payments.service import _verify_signature

        valid_sig = hmac.new(
            settings.RAZORPAY_KEY_SECRET.encode(),
            b"order_A|pay_B",
            hashlib.sha256,
        ).hexdigest()
        assert _verify_signature("order_DIFFERENT", "pay_B", valid_sig) is False


# ─── PaymentService error paths ───────────────────────────────────────────────


class TestPaymentService:
    def setup_method(self):
        from app.modules.payments.service import PaymentService

        self.svc = PaymentService()

    async def test_create_raises_404_when_order_not_found(self):
        from app.core.exceptions import NotFoundError
        from app.modules.payments.schemas import CreatePaymentOrderRequest

        db = AsyncMock()
        with patch.object(OrderRepository, "get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.create_razorpay_order(
                    db,
                    user_id=uuid.uuid4(),
                    payload=CreatePaymentOrderRequest(
                        order_id=uuid.uuid4(), payment_method="razorpay"
                    ),
                )

    async def test_create_raises_404_for_wrong_user(self):
        from app.core.exceptions import NotFoundError
        from app.modules.payments.schemas import CreatePaymentOrderRequest

        db = AsyncMock()
        mock_order = MagicMock()
        mock_order.user_id = uuid.uuid4()  # different from caller
        with patch.object(
            OrderRepository, "get_by_id", AsyncMock(return_value=mock_order)
        ):
            with pytest.raises(NotFoundError):
                await self.svc.create_razorpay_order(
                    db,
                    user_id=uuid.uuid4(),
                    payload=CreatePaymentOrderRequest(
                        order_id=uuid.uuid4(), payment_method="razorpay"
                    ),
                )

    async def test_create_raises_validation_when_already_paid(self):
        from app.core.exceptions import ValidationError
        from app.modules.payments.schemas import CreatePaymentOrderRequest

        db = AsyncMock()
        user_id = uuid.uuid4()
        mock_order = MagicMock()
        mock_order.user_id = user_id
        mock_order.payment_status = "paid"
        with patch.object(
            OrderRepository, "get_by_id", AsyncMock(return_value=mock_order)
        ):
            with pytest.raises(ValidationError):
                await self.svc.create_razorpay_order(
                    db,
                    user_id=user_id,
                    payload=CreatePaymentOrderRequest(
                        order_id=uuid.uuid4(), payment_method="razorpay"
                    ),
                )

    async def test_create_raises_validation_when_cancelled(self):
        from app.core.exceptions import ValidationError
        from app.modules.payments.schemas import CreatePaymentOrderRequest

        db = AsyncMock()
        user_id = uuid.uuid4()
        mock_order = MagicMock()
        mock_order.user_id = user_id
        mock_order.payment_status = "pending"
        mock_order.status = "cancelled"
        with patch.object(
            OrderRepository, "get_by_id", AsyncMock(return_value=mock_order)
        ):
            with pytest.raises(ValidationError):
                await self.svc.create_razorpay_order(
                    db,
                    user_id=user_id,
                    payload=CreatePaymentOrderRequest(
                        order_id=uuid.uuid4(), payment_method="razorpay"
                    ),
                )

    async def test_verify_raises_404_when_payment_not_found(self):
        from app.core.exceptions import NotFoundError
        from app.modules.payments.schemas import VerifyPaymentRequest

        db = AsyncMock()
        with patch(
            "app.modules.payments.service._repo.get_by_id", AsyncMock(return_value=None)
        ):
            with pytest.raises(NotFoundError):
                await self.svc.verify_and_capture(
                    db,
                    user_id=uuid.uuid4(),
                    payload=VerifyPaymentRequest(
                        payment_id=uuid.uuid4(),
                        razorpay_order_id="order_abc",
                        razorpay_payment_id="pay_xyz",
                        razorpay_signature="sig123",
                    ),
                )

    async def test_verify_raises_404_for_wrong_user(self):
        from app.core.exceptions import NotFoundError
        from app.modules.payments.schemas import VerifyPaymentRequest

        db = AsyncMock()
        mock_payment = MagicMock()
        mock_payment.user_id = uuid.uuid4()
        mock_payment.status = "created"
        with patch(
            "app.modules.payments.service._repo.get_by_id",
            AsyncMock(return_value=mock_payment),
        ):
            with pytest.raises(NotFoundError):
                await self.svc.verify_and_capture(
                    db,
                    user_id=uuid.uuid4(),
                    payload=VerifyPaymentRequest(
                        payment_id=uuid.uuid4(),
                        razorpay_order_id="order_abc",
                        razorpay_payment_id="pay_xyz",
                        razorpay_signature="sig123",
                    ),
                )

    async def test_verify_returns_existing_when_already_captured(self):
        from app.modules.payments.schemas import VerifyPaymentRequest

        db = AsyncMock()
        user_id = uuid.uuid4()
        mock_payment = MagicMock()
        mock_payment.user_id = user_id
        mock_payment.status = "captured"
        with (
            patch(
                "app.modules.payments.service._repo.get_by_id",
                AsyncMock(return_value=mock_payment),
            ),
            patch(
                "app.modules.payments.schemas.PaymentResponse.model_validate",
                return_value=MagicMock(),
            ),
        ):
            result = await self.svc.verify_and_capture(
                db,
                user_id=user_id,
                payload=VerifyPaymentRequest(
                    payment_id=uuid.uuid4(),
                    razorpay_order_id="order_abc",
                    razorpay_payment_id="pay_xyz",
                    razorpay_signature="sig123",
                ),
            )
        assert result is not None

    async def test_get_payment_for_order_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        with patch(
            "app.modules.payments.service._repo.get_for_order",
            AsyncMock(return_value=None),
        ):
            with pytest.raises(NotFoundError):
                await self.svc.get_payment_for_order(db, uuid.uuid4())

    async def test_get_payment_for_order_raises_404_for_wrong_user(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        mock_payment = MagicMock()
        mock_payment.user_id = uuid.uuid4()
        with patch(
            "app.modules.payments.service._repo.get_for_order",
            AsyncMock(return_value=mock_payment),
        ):
            with pytest.raises(NotFoundError):
                await self.svc.get_payment_for_order(
                    db, uuid.uuid4(), user_id=uuid.uuid4()
                )

    async def test_initiate_refund_raises_404_when_no_payment(self):
        from app.core.exceptions import NotFoundError
        from app.modules.payments.schemas import RefundRequest

        db = AsyncMock()
        with patch(
            "app.modules.payments.service._repo.get_for_order",
            AsyncMock(return_value=None),
        ):
            with pytest.raises(NotFoundError):
                await self.svc.initiate_refund(
                    db, uuid.uuid4(), RefundRequest(reason="defective")
                )

    async def test_initiate_refund_raises_validation_when_not_captured(self):
        from app.core.exceptions import ValidationError
        from app.modules.payments.schemas import RefundRequest

        db = AsyncMock()
        mock_payment = MagicMock()
        mock_payment.status = "created"  # not "captured"
        with patch(
            "app.modules.payments.service._repo.get_for_order",
            AsyncMock(return_value=mock_payment),
        ):
            with pytest.raises(ValidationError):
                await self.svc.initiate_refund(
                    db, uuid.uuid4(), RefundRequest(reason="defective")
                )

    async def test_list_refunds_returns_empty(self):
        db = AsyncMock()
        with patch(
            "app.modules.payments.service._repo.get_refunds_for_order",
            AsyncMock(return_value=[]),
        ):
            result = await self.svc.list_refunds(db, uuid.uuid4())
        assert result == []


# ─── WebhookService ───────────────────────────────────────────────────────────


class TestWebhookService:
    def setup_method(self):
        from app.modules.webhooks.service import WebhookService

        self.svc = WebhookService()

    async def test_handle_razorpay_invalid_signature_returns_status(self):
        db = AsyncMock()
        with patch(
            "app.modules.webhooks.service.verify_razorpay_webhook_signature",
            return_value=False,
        ):
            result = await self.svc.handle_razorpay(
                db, body=b'{"event":"test"}', signature="bad_sig"
            )
        assert result["status"] == "invalid_signature"

    async def test_handle_razorpay_invalid_json_returns_status(self):
        db = AsyncMock()
        with patch(
            "app.modules.webhooks.service.verify_razorpay_webhook_signature",
            return_value=True,
        ):
            result = await self.svc.handle_razorpay(
                db, body=b"not json", signature="sig"
            )
        assert result["status"] == "invalid_payload"

    async def test_handle_razorpay_already_processed_returns_status(self):
        db = AsyncMock()
        mock_existing = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_existing
        db.execute = AsyncMock(return_value=mock_result)

        payload = json.dumps({"event": "payment.captured", "id": "evt_123"}).encode()
        with patch(
            "app.modules.webhooks.service.verify_razorpay_webhook_signature",
            return_value=True,
        ):
            result = await self.svc.handle_razorpay(db, body=payload, signature="sig")
        assert result["status"] == "already_processed"
