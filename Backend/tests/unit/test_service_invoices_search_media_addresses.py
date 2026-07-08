"""Tests for InvoiceService, SearchService, and AddressService."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.payments.repository import PaymentRepository

# ─── InvoiceService ──────────────────────────────────────────────────────────


class TestInvoiceService:
    def setup_method(self):
        from app.modules.invoices.service import InvoiceService

        self.svc = InvoiceService()

    async def test_generate_returns_existing_when_already_generated(self):
        db = AsyncMock()
        mock_invoice = MagicMock()
        mock_invoice.invoice_number = "INV-0001"
        mock_invoice.pdf_url = "https://cdn.example.com/invoices/INV-0001.pdf"
        mock_order = MagicMock()
        mock_order.id = uuid.uuid4()

        with patch.object(
            PaymentRepository,
            "get_invoice_for_order",
            AsyncMock(return_value=mock_invoice),
        ):
            result = await self.svc.generate_and_store(db, mock_order)

        assert result["invoice_number"] == "INV-0001"
        assert result["pdf_url"] == "https://cdn.example.com/invoices/INV-0001.pdf"

    async def test_generate_builds_pdf_and_uploads_to_r2(self):
        db = AsyncMock()
        mock_order = MagicMock()
        mock_order.id = uuid.uuid4()
        mock_order.order_number = "ORD-0001"
        mock_order.payment_method = "razorpay"
        mock_order.shipping_full_name = "Alice"
        mock_order.shipping_line1 = "123 Main St"
        mock_order.shipping_line2 = None
        mock_order.shipping_city = "Mumbai"
        mock_order.shipping_state = "MH"
        mock_order.shipping_postal = "400001"
        mock_order.shipping_country = "India"
        mock_order.items = []
        mock_order.tax_amount = 0
        mock_order.shipping_state = "MH"
        mock_order.subtotal = 1000
        mock_order.shipping_charge = 0
        mock_order.discount = 0
        mock_order.total = 1000

        mock_created_invoice = MagicMock()
        mock_created_invoice.invoice_number = "INV-0002"
        mock_created_invoice.pdf_url = "https://cdn.example.com/invoices/INV-0002.pdf"

        mock_r2 = MagicMock()

        with (
            patch.object(
                PaymentRepository, "get_invoice_for_order", AsyncMock(return_value=None)
            ),
            patch.object(
                PaymentRepository,
                "generate_invoice_number",
                AsyncMock(return_value="INV-0002"),
            ),
            patch("app.modules.invoices.service._build_pdf", return_value=b"%PDF fake"),
            patch("app.modules.invoices.service._r2_client", return_value=mock_r2),
            patch.object(
                PaymentRepository,
                "create_invoice",
                AsyncMock(return_value=mock_created_invoice),
            ),
        ):
            result = await self.svc.generate_and_store(db, mock_order)

        assert result["invoice_number"] == "INV-0002"
        mock_r2.put_object.assert_called_once()

    async def test_get_download_url_raises_404_when_order_missing(self):
        from app.core.exceptions import NotFoundError
        from app.modules.orders.repository import OrderRepository

        db = AsyncMock()
        with patch.object(OrderRepository, "get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.get_download_url(db, uuid.uuid4(), uuid.uuid4())

    async def test_get_download_url_raises_404_for_wrong_user(self):
        from app.core.exceptions import NotFoundError
        from app.modules.orders.repository import OrderRepository

        db = AsyncMock()
        mock_order = MagicMock()
        mock_order.user_id = uuid.uuid4()  # different from caller
        with patch.object(
            OrderRepository, "get_by_id", AsyncMock(return_value=mock_order)
        ):
            with pytest.raises(NotFoundError):
                await self.svc.get_download_url(db, uuid.uuid4(), uuid.uuid4())

    async def test_get_download_url_raises_404_when_no_invoice(self):
        from app.core.exceptions import NotFoundError
        from app.modules.orders.repository import OrderRepository

        db = AsyncMock()
        user_id = uuid.uuid4()
        mock_order = MagicMock()
        mock_order.user_id = user_id
        with (
            patch.object(
                OrderRepository, "get_by_id", AsyncMock(return_value=mock_order)
            ),
            patch.object(
                PaymentRepository, "get_invoice_for_order", AsyncMock(return_value=None)
            ),
        ):
            with pytest.raises(NotFoundError):
                await self.svc.get_download_url(db, uuid.uuid4(), user_id)

    async def test_get_download_url_raises_404_when_invoice_has_no_r2_key(self):
        from app.core.exceptions import NotFoundError
        from app.modules.orders.repository import OrderRepository

        db = AsyncMock()
        user_id = uuid.uuid4()
        mock_order = MagicMock()
        mock_order.user_id = user_id
        mock_invoice = MagicMock()
        mock_invoice.pdf_r2_key = None
        with (
            patch.object(
                OrderRepository, "get_by_id", AsyncMock(return_value=mock_order)
            ),
            patch.object(
                PaymentRepository,
                "get_invoice_for_order",
                AsyncMock(return_value=mock_invoice),
            ),
        ):
            with pytest.raises(NotFoundError):
                await self.svc.get_download_url(db, uuid.uuid4(), user_id)

    async def test_get_download_url_returns_presigned_url(self):
        from app.modules.orders.repository import OrderRepository

        db = AsyncMock()
        user_id = uuid.uuid4()
        mock_order = MagicMock()
        mock_order.user_id = user_id
        mock_invoice = MagicMock()
        mock_invoice.pdf_r2_key = "invoices/order-id/INV-0001.pdf"
        mock_r2 = MagicMock()
        mock_r2.generate_presigned_url.return_value = (
            "https://presigned.example.com/invoice.pdf"
        )

        with (
            patch.object(
                OrderRepository, "get_by_id", AsyncMock(return_value=mock_order)
            ),
            patch.object(
                PaymentRepository,
                "get_invoice_for_order",
                AsyncMock(return_value=mock_invoice),
            ),
            patch("app.modules.invoices.service._r2_client", return_value=mock_r2),
        ):
            result = await self.svc.get_download_url(db, uuid.uuid4(), user_id)

        assert result == "https://presigned.example.com/invoice.pdf"
        mock_r2.generate_presigned_url.assert_called_once()


# ─── SearchService ────────────────────────────────────────────────────────────


class TestSearchService:
    def setup_method(self):
        from app.modules.search.service import SearchService

        self.svc = SearchService()

    async def test_full_text_search_empty_query_returns_early(self):
        db = AsyncMock()
        result = await self.svc.full_text_search(db, "")
        assert result["items"] == []
        assert result["total"] == 0
        db.execute.assert_not_awaited()

    async def test_full_text_search_whitespace_only_returns_early(self):
        db = AsyncMock()
        result = await self.svc.full_text_search(db, "   ")
        assert result["total"] == 0

    async def test_full_text_search_returns_fts_results(self):
        db = AsyncMock()
        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 2

        mock_row = MagicMock()
        mock_row._mapping = {
            "id": uuid.uuid4(),
            "name": "Silver Ring",
            "slug": "silver-ring",
            "base_price": 999.0,
            "compare_at_price": None,
            "stock_quantity": 10,
            "metal_type": "silver",
            "is_featured": False,
            "rank": 0.8,
        }
        mock_items_result = MagicMock()
        mock_items_result.fetchall.return_value = [mock_row, mock_row]

        db.execute = AsyncMock(side_effect=[mock_count_result, mock_items_result])
        result = await self.svc.full_text_search(db, "silver ring")

        assert result["total"] == 2
        assert len(result["items"]) == 2
        assert result["page"] == 1

    async def test_full_text_search_falls_back_to_ilike_when_no_fts_results(self):
        db = AsyncMock()
        mock_fts_count = MagicMock()
        mock_fts_count.scalar_one.return_value = 0  # no FTS results

        mock_ilike_count = MagicMock()
        mock_ilike_count.scalar_one.return_value = 1  # 1 ILIKE result

        mock_row = MagicMock()
        mock_row._mapping = {
            "id": uuid.uuid4(),
            "name": "Silver Bangle",
            "slug": "silver-bangle",
            "base_price": 500.0,
            "compare_at_price": None,
            "stock_quantity": 5,
            "metal_type": "silver",
            "is_featured": False,
        }
        mock_items_result = MagicMock()
        mock_items_result.fetchall.return_value = [mock_row]

        db.execute = AsyncMock(
            side_effect=[mock_fts_count, mock_ilike_count, mock_items_result]
        )
        result = await self.svc.full_text_search(db, "bangle")

        assert result["total"] == 1
        assert len(result["items"]) == 1

    async def test_full_text_search_with_category_filter(self):
        db = AsyncMock()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 0
        mock_ilike_count = MagicMock()
        mock_ilike_count.scalar_one.return_value = 0
        mock_items = MagicMock()
        mock_items.fetchall.return_value = []

        db.execute = AsyncMock(side_effect=[mock_count, mock_ilike_count, mock_items])
        result = await self.svc.full_text_search(
            db, "ring", category_id=uuid.uuid4(), min_price=100.0, max_price=5000.0
        )
        assert result["total"] == 0

    async def test_full_text_search_pagination_params(self):
        db = AsyncMock()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 45
        mock_items = MagicMock()
        mock_items.fetchall.return_value = []

        db.execute = AsyncMock(side_effect=[mock_count, mock_items])
        result = await self.svc.full_text_search(db, "ring", page=3, page_size=10)

        assert result["page"] == 3
        assert result["page_size"] == 10
        assert result["total"] == 45
        assert result["total_pages"] == 5

    async def test_autocomplete_returns_empty_for_short_query(self):
        db = AsyncMock()
        result = await self.svc.autocomplete(db, "s")
        assert result == []
        db.execute.assert_not_awaited()

    async def test_autocomplete_returns_empty_for_empty_query(self):
        db = AsyncMock()
        result = await self.svc.autocomplete(db, "")
        assert result == []

    async def test_autocomplete_returns_name_list(self):
        db = AsyncMock()
        mock_row1 = MagicMock()
        mock_row1.__getitem__ = lambda self, i: "Silver Ring"
        mock_row2 = MagicMock()
        mock_row2.__getitem__ = lambda self, i: "Silver Bangle"
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row1, mock_row2]
        db.execute = AsyncMock(return_value=mock_result)

        result = await self.svc.autocomplete(db, "silver")
        assert result == ["Silver Ring", "Silver Bangle"]

    async def test_record_search_skips_empty_query(self):
        db = AsyncMock()
        await self.svc.record_search(db, "", user_id=None, result_count=0)
        db.execute.assert_not_awaited()

    async def test_record_search_executes_insert(self):
        db = AsyncMock()
        await self.svc.record_search(
            db, "silver ring", user_id="user-123", result_count=5
        )
        db.execute.assert_awaited_once()

    async def test_trending_searches_returns_list(self):
        db = AsyncMock()
        mock_row1 = MagicMock()
        mock_row1.__getitem__ = lambda self, i: "silver ring" if i == 0 else 42
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row1]
        db.execute = AsyncMock(return_value=mock_result)

        result = await self.svc.trending_searches(db, limit=5)
        assert len(result) == 1
        assert result[0]["query"] == "silver ring"
        assert result[0]["count"] == 42


# MediaService was deleted in the Phase 3 cutover — replaced entirely by
# app.modules.media.universal_service.UniversalImageService. See
# tests/unit/test_media_universal_service.py and
# tests/unit/test_media_crop_engine.py for equivalent coverage of the new
# pipeline.


# ─── AddressService ───────────────────────────────────────────────────────────


class TestAddressService:
    def setup_method(self):
        from app.modules.addresses.service import AddressService

        self.svc = AddressService()

    async def test_list_returns_empty_when_no_addresses(self):
        db = AsyncMock()
        with patch(
            "app.modules.addresses.service._repo.list_for_user",
            AsyncMock(return_value=[]),
        ):
            result = await self.svc.list(db, uuid.uuid4())
        assert result == []

    async def test_create_raises_conflict_when_at_max(self):
        from app.core.exceptions import ConflictError
        from app.modules.addresses.repository import _MAX_ADDRESSES
        from app.modules.addresses.schemas import AddressCreateRequest

        db = AsyncMock()
        with patch(
            "app.modules.addresses.service._repo.count_for_user",
            AsyncMock(return_value=_MAX_ADDRESSES),
        ):
            with pytest.raises(ConflictError):
                await self.svc.create(
                    db,
                    uuid.uuid4(),
                    AddressCreateRequest(
                        type="shipping",
                        full_name="Alice",
                        line1="123 Main St",
                        city="Mumbai",
                        state="Maharashtra",
                        postal_code="400001",
                        country="IN",
                        phone="9999999999",
                    ),
                )

    async def test_create_clears_default_when_is_default_true(self):
        from app.modules.addresses.schemas import AddressCreateRequest

        db = AsyncMock()
        mock_addr = MagicMock()

        with (
            patch(
                "app.modules.addresses.service._repo.count_for_user",
                AsyncMock(return_value=0),
            ),
            patch(
                "app.modules.addresses.service._repo.clear_default", AsyncMock()
            ) as mock_clear,
            patch(
                "app.modules.addresses.service._repo.create",
                AsyncMock(return_value=mock_addr),
            ),
            patch(
                "app.modules.addresses.schemas.AddressResponse.model_validate",
                return_value=MagicMock(),
            ),
        ):
            await self.svc.create(
                db,
                uuid.uuid4(),
                AddressCreateRequest(
                    type="shipping",
                    full_name="Alice",
                    line1="123 Main St",
                    city="Mumbai",
                    state="Maharashtra",
                    postal_code="400001",
                    country="IN",
                    phone="9999999999",
                    is_default=True,
                ),
            )
        mock_clear.assert_awaited_once()

    async def test_update_raises_404_when_address_not_found(self):
        from app.core.exceptions import NotFoundError
        from app.modules.addresses.schemas import AddressUpdateRequest

        db = AsyncMock()
        with patch(
            "app.modules.addresses.service._repo.get", AsyncMock(return_value=None)
        ):
            with pytest.raises(NotFoundError):
                await self.svc.update(
                    db, uuid.uuid4(), uuid.uuid4(), AddressUpdateRequest()
                )

    async def test_update_success_without_default_change(self):
        from app.modules.addresses.schemas import AddressUpdateRequest

        db = AsyncMock()
        mock_existing = MagicMock()
        mock_updated = MagicMock()
        with (
            patch(
                "app.modules.addresses.service._repo.get",
                AsyncMock(return_value=mock_existing),
            ),
            patch(
                "app.modules.addresses.service._repo.update",
                AsyncMock(return_value=mock_updated),
            ),
            patch(
                "app.modules.addresses.schemas.AddressResponse.model_validate",
                return_value=MagicMock(),
            ),
        ):
            await self.svc.update(
                db, uuid.uuid4(), uuid.uuid4(), AddressUpdateRequest(full_name="Bob")
            )

    async def test_set_default_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        with patch(
            "app.modules.addresses.service._repo.get", AsyncMock(return_value=None)
        ):
            with pytest.raises(NotFoundError):
                await self.svc.set_default(db, uuid.uuid4(), uuid.uuid4())

    async def test_set_default_clears_existing_default(self):
        db = AsyncMock()
        mock_existing = MagicMock()
        mock_existing.type = "shipping"
        mock_updated = MagicMock()
        with (
            patch(
                "app.modules.addresses.service._repo.get",
                AsyncMock(return_value=mock_existing),
            ),
            patch(
                "app.modules.addresses.service._repo.clear_default", AsyncMock()
            ) as mock_clear,
            patch(
                "app.modules.addresses.service._repo.update",
                AsyncMock(return_value=mock_updated),
            ),
            patch(
                "app.modules.addresses.schemas.AddressResponse.model_validate",
                return_value=MagicMock(),
            ),
        ):
            await self.svc.set_default(db, uuid.uuid4(), uuid.uuid4())
        mock_clear.assert_awaited_once()

    async def test_delete_raises_404_when_address_not_found(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        with patch(
            "app.modules.addresses.service._repo.get", AsyncMock(return_value=None)
        ):
            with pytest.raises(NotFoundError):
                await self.svc.delete(db, uuid.uuid4(), uuid.uuid4())

    async def test_delete_calls_soft_delete(self):
        db = AsyncMock()
        mock_existing = MagicMock()
        with (
            patch(
                "app.modules.addresses.service._repo.get",
                AsyncMock(return_value=mock_existing),
            ),
            patch(
                "app.modules.addresses.service._repo.soft_delete", AsyncMock()
            ) as mock_del,
        ):
            await self.svc.delete(db, uuid.uuid4(), uuid.uuid4())
        mock_del.assert_awaited_once()
