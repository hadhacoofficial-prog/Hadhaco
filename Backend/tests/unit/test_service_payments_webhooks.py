"""Tests for PaymentService and WebhookService."""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ─── PaymentService error paths ───────────────────────────────────────────────


class TestPaymentService:
    def setup_method(self):
        from app.modules.payments.service import PaymentService

        self.svc = PaymentService()

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
            "app.modules.payments.service._repo.get_for_order_with_lock",
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
            "app.modules.payments.service._repo.get_for_order_with_lock",
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
        mock_existing.status = "processed"
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
