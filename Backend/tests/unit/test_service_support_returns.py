"""SupportService and ReturnService mock-based tests."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.modules.returns.repository import ReturnRepository
from app.modules.returns.schemas import AdminReturnStatusUpdate, ReturnCreate, ReturnItemCreate
from app.modules.support.repository import SupportRepository
from app.modules.support.schemas import AdminTicketUpdate, MessageCreate


class TestSupportServiceReply:
    def setup_method(self):
        from app.modules.support.service import SupportService

        self.svc = SupportService()

    async def test_reply_raises_404_when_ticket_missing(self):
        db = AsyncMock()
        with patch.object(SupportRepository, "get_ticket", AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc:
                await self.svc.reply(
                    db,
                    ticket_id=uuid.uuid4(),
                    sender_id=uuid.uuid4(),
                    data=MessageCreate(body="hi"),
                )
        assert exc.value.status_code == 404

    async def test_reply_raises_403_when_not_customers_ticket(self):
        db = AsyncMock()
        mock_ticket = MagicMock()
        mock_ticket.customer_id = uuid.uuid4()  # ticket owner
        mock_ticket.status = "open"
        caller_id = uuid.uuid4()  # different user
        with patch.object(SupportRepository, "get_ticket", AsyncMock(return_value=mock_ticket)):
            with pytest.raises(HTTPException) as exc:
                await self.svc.reply(
                    db,
                    ticket_id=uuid.uuid4(),
                    sender_id=caller_id,
                    data=MessageCreate(body="hi"),
                    is_admin=False,
                )
        assert exc.value.status_code == 403

    async def test_reply_customer_reopens_resolved_ticket(self):
        db = AsyncMock()
        ticket_id = uuid.uuid4()
        customer_id = uuid.uuid4()
        mock_ticket = MagicMock()
        mock_ticket.id = ticket_id
        mock_ticket.customer_id = customer_id
        mock_ticket.status = "resolved"
        mock_msg = MagicMock()

        with (
            patch.object(SupportRepository, "get_ticket", AsyncMock(return_value=mock_ticket)),
            patch.object(SupportRepository, "add_message", AsyncMock(return_value=mock_msg)),
            patch.object(SupportRepository, "update_ticket", AsyncMock(return_value=mock_ticket)),
        ):
            db.commit = AsyncMock()
            db.refresh = AsyncMock()
            result = await self.svc.reply(
                db,
                ticket_id=ticket_id,
                sender_id=customer_id,
                data=MessageCreate(body="Still broken"),
            )

        assert result is mock_msg

    async def test_admin_reply_bypasses_customer_check(self):
        db = AsyncMock()
        ticket_id = uuid.uuid4()
        admin_id = uuid.uuid4()
        customer_id = uuid.uuid4()
        mock_ticket = MagicMock()
        mock_ticket.id = ticket_id
        mock_ticket.customer_id = customer_id
        mock_ticket.status = "open"
        mock_msg = MagicMock()

        with (
            patch.object(SupportRepository, "get_ticket", AsyncMock(return_value=mock_ticket)),
            patch.object(SupportRepository, "add_message", AsyncMock(return_value=mock_msg)),
        ):
            db.commit = AsyncMock()
            db.refresh = AsyncMock()
            result = await self.svc.reply(
                db,
                ticket_id=ticket_id,
                sender_id=admin_id,
                data=MessageCreate(body="Noted"),
                is_admin=True,
            )

        assert result is mock_msg


class TestSupportServiceGetTicket:
    def setup_method(self):
        from app.modules.support.service import SupportService

        self.svc = SupportService()

    async def test_get_ticket_raises_404_when_not_found(self):
        db = AsyncMock()
        with patch.object(SupportRepository, "get_ticket", AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc:
                await self.svc.get_ticket(db, uuid.uuid4(), viewer_id=uuid.uuid4(), is_admin=False)
        assert exc.value.status_code == 404

    async def test_get_ticket_raises_403_when_not_customers_ticket(self):
        db = AsyncMock()
        mock_ticket = MagicMock()
        mock_ticket.customer_id = uuid.uuid4()
        with patch.object(SupportRepository, "get_ticket", AsyncMock(return_value=mock_ticket)):
            with pytest.raises(HTTPException) as exc:
                await self.svc.get_ticket(db, uuid.uuid4(), viewer_id=uuid.uuid4(), is_admin=False)
        assert exc.value.status_code == 403

    async def test_get_ticket_admin_can_view_any_ticket(self):
        db = AsyncMock()
        mock_ticket = MagicMock()
        mock_ticket.customer_id = uuid.uuid4()
        with patch.object(SupportRepository, "get_ticket", AsyncMock(return_value=mock_ticket)):
            result = await self.svc.get_ticket(
                db, uuid.uuid4(), viewer_id=uuid.uuid4(), is_admin=True
            )
        assert result is mock_ticket

    async def test_admin_update_raises_404_when_not_found(self):
        db = AsyncMock()
        with patch.object(SupportRepository, "get_ticket", AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc:
                await self.svc.admin_update(
                    db, ticket_id=uuid.uuid4(), data=AdminTicketUpdate(status="closed")
                )
        assert exc.value.status_code == 404

    async def test_list_customer_tickets_delegates_to_repo(self):
        db = AsyncMock()
        with patch.object(SupportRepository, "list_for_customer", AsyncMock(return_value=[])):
            result = await self.svc.list_customer_tickets(db, uuid.uuid4())
        assert result == []


class TestReturnService:
    def setup_method(self):
        from app.modules.returns.service import ReturnService

        self.svc = ReturnService()

    async def test_create_return_raises_400_when_outside_window(self):
        db = AsyncMock()
        with patch.object(
            ReturnRepository, "is_within_return_window", AsyncMock(return_value=False)
        ):
            with pytest.raises(HTTPException) as exc:
                await self.svc.create_return(
                    db,
                    customer_id=uuid.uuid4(),
                    data=ReturnCreate(
                        order_id=uuid.uuid4(),
                        reason="defective",
                        items=[
                            ReturnItemCreate(
                                order_item_id=uuid.uuid4(), quantity=1, reason="defective"
                            )
                        ],
                    ),
                )
        assert exc.value.status_code == 400

    async def test_create_return_success(self):
        db = AsyncMock()
        mock_ret = MagicMock()
        mock_ret.id = uuid.uuid4()
        with (
            patch.object(ReturnRepository, "is_within_return_window", AsyncMock(return_value=True)),
            patch.object(ReturnRepository, "create", AsyncMock(return_value=mock_ret)),
            patch.object(ReturnRepository, "add_item", AsyncMock()),
        ):
            db.commit = AsyncMock()
            db.refresh = AsyncMock()
            result = await self.svc.create_return(
                db,
                customer_id=uuid.uuid4(),
                data=ReturnCreate(
                    order_id=uuid.uuid4(),
                    reason="defective",
                    items=[
                        ReturnItemCreate(order_item_id=uuid.uuid4(), quantity=1, reason="defective")
                    ],
                ),
            )
        assert result is mock_ret

    async def test_admin_update_status_raises_404_when_not_found(self):
        db = AsyncMock()
        with patch.object(ReturnRepository, "get", AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc:
                await self.svc.admin_update_status(
                    db,
                    return_id=uuid.uuid4(),
                    admin_id=uuid.uuid4(),
                    data=AdminReturnStatusUpdate(status="approved"),
                )
        assert exc.value.status_code == 404

    async def test_admin_update_status_success(self):
        db = AsyncMock()
        mock_ret = MagicMock()
        mock_updated = MagicMock()
        with (
            patch.object(ReturnRepository, "get", AsyncMock(return_value=mock_ret)),
            patch.object(ReturnRepository, "update_status", AsyncMock(return_value=mock_updated)),
        ):
            db.commit = AsyncMock()
            db.refresh = AsyncMock()
            result = await self.svc.admin_update_status(
                db,
                return_id=uuid.uuid4(),
                admin_id=uuid.uuid4(),
                data=AdminReturnStatusUpdate(status="approved", admin_notes="OK"),
            )
        assert result is mock_updated

    async def test_list_customer_returns_delegates_to_repo(self):
        db = AsyncMock()
        with patch.object(ReturnRepository, "list_for_customer", AsyncMock(return_value=[])):
            result = await self.svc.list_customer_returns(db, uuid.uuid4())
        assert result == []

    async def test_list_all_delegates_to_repo(self):
        db = AsyncMock()
        with patch.object(ReturnRepository, "list_all", AsyncMock(return_value=[])):
            result = await self.svc.list_all(db)
        assert result == []
