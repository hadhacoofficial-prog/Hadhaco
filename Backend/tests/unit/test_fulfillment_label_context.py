"""Unit tests for ShippingLabelService._build_context and PackingSlipService._build_context.

No real DB, file I/O, or network calls. Company repo and _logo_data_uri are
patched for every test.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

# ─── Mock helpers ─────────────────────────────────────────────────────────────


def _make_company(**overrides):
    c = MagicMock()
    c.name = "Hadha Jewellery"
    c.tagline = "Quality First"
    c.address_line1 = "Plot 42"
    c.address_line2 = None
    c.city = "Hyderabad"
    c.state = "Telangana"
    c.postal_code = "500033"
    c.country = "IN"
    c.phone = "+91 98765 43210"
    c.support_email = "info@hadha.com"
    c.website = "www.hadha.com"
    c.logo_url = None
    for k, v in overrides.items():
        setattr(c, k, v)
    return c


def _make_order(**overrides):
    o = MagicMock()
    o.order_number = "HDH-202606-000009"
    o.created_at = MagicMock()
    o.created_at.strftime.return_value = "2026-06-26"
    o.dispatched_at = None
    o.shipping_full_name = "Sai Thrinadh"
    o.shipping_phone = "+91 98494 61585"
    o.shipping_alternate_phone = None
    o.shipping_line1 = "D.No 6-64"
    o.shipping_line2 = None
    o.shipping_landmark = None
    o.shipping_city = "Razole"
    o.shipping_state = "Andhra Pradesh"
    o.shipping_postal = "533242"
    o.shipping_provider = "India Post"
    o.tracking_number = "IP123456789IN"
    o.shipping_charge = Decimal("99.00")
    o.discount = Decimal("0.00")
    o.total = Decimal("1109.00")
    o.subtotal = Decimal("1010.00")
    o.tax_amount = Decimal("0.00")
    o.items = []
    for k, v in overrides.items():
        setattr(o, k, v)
    return o


def _make_item(
    name="Ring", sku="SKU-001", variant="Gold", qty=2, total=Decimal("500.00")
):
    item = MagicMock()
    item.product_name = name
    item.product_sku = sku
    item.variant_name = variant
    item.quantity = qty
    item.line_total = total
    return item


# ─── ShippingLabelService._build_context ─────────────────────────────────────


class TestShippingLabelServiceBuildContext:
    def setup_method(self):
        from app.modules.fulfillment.service import ShippingLabelService

        self.svc = ShippingLabelService()

    async def _ctx(self, company, order):
        db = AsyncMock()
        with (
            patch(
                "app.modules.company.repository.CompanyConfigRepository.get",
                new=AsyncMock(return_value=company),
            ),
            patch(
                "app.modules.fulfillment.service._logo_data_uri",
                return_value=None,
            ),
        ):
            return await self.svc._build_context(db, order)

    async def test_company_name_from_config(self):
        company = _make_company(name="My Brand")
        ctx = await self._ctx(company, _make_order())
        assert ctx["company"]["name"] == "My Brand"

    async def test_company_defaults_when_none(self):
        ctx = await self._ctx(None, _make_order())
        assert ctx["company"]["name"] == "Hadha Jewellery"

    async def test_order_dict_contains_key_fields(self):
        order = _make_order()
        ctx = await self._ctx(_make_company(), order)
        od = ctx["order"]
        assert od["order_number"] == "HDH-202606-000009"
        assert od["item_count"] == 0
        assert od["shipping_charge"] == 99.0
        assert od["discount"] == 0.0
        assert od["total"] == 1109.0

    async def test_items_empty_when_no_order_items(self):
        ctx = await self._ctx(_make_company(), _make_order(items=[]))
        assert ctx["items"] == []

    async def test_items_populated_when_order_has_items(self):
        items = [_make_item("Ring", qty=1), _make_item("Necklace", qty=2)]
        order = _make_order(items=items)
        ctx = await self._ctx(_make_company(), order)
        assert len(ctx["items"]) == 2
        assert ctx["items"][0]["product_name"] == "Ring"
        assert ctx["items"][1]["product_name"] == "Necklace"

    async def test_logo_data_uri_key_present(self):
        ctx = await self._ctx(_make_company(), _make_order())
        assert "logo_data_uri" in ctx  # value may be None if file missing

    async def test_barcode_b64_none_when_no_tracking_number(self):
        order = _make_order(tracking_number=None)
        ctx = await self._ctx(_make_company(), order)
        assert ctx["barcode_b64"] is None

    async def test_barcode_b64_non_none_when_tracking_set(self):
        order = _make_order(tracking_number="IP123456789IN")
        fake_b64 = "AAABBBCCC"
        with (
            patch(
                "app.modules.company.repository.CompanyConfigRepository.get",
                new=AsyncMock(return_value=_make_company()),
            ),
            patch(
                "app.modules.fulfillment.service._logo_data_uri",
                return_value=None,
            ),
            patch.object(
                type(self.svc),
                "_barcode_b64",
                staticmethod(lambda v: fake_b64),
            ),
        ):
            ctx = await self.svc._build_context(AsyncMock(), order)
        assert ctx["barcode_b64"] == fake_b64

    async def test_qr_b64_always_non_empty(self):
        ctx = await self._ctx(_make_company(), _make_order())
        assert ctx["qr_b64"]
        assert len(ctx["qr_b64"]) > 0

    async def test_item_count_sums_quantities(self):
        items = [_make_item(qty=3), _make_item(qty=2)]
        order = _make_order(items=items)
        ctx = await self._ctx(_make_company(), order)
        assert ctx["order"]["item_count"] == 5

    async def test_items_have_product_name_and_quantity(self):
        items = [_make_item("Bangle", qty=4)]
        order = _make_order(items=items)
        ctx = await self._ctx(_make_company(), order)
        assert ctx["items"][0]["product_name"] == "Bangle"
        assert ctx["items"][0]["quantity"] == 4


# ─── PackingSlipService._build_context ───────────────────────────────────────


class TestPackingSlipServiceBuildContext:
    def setup_method(self):
        from app.modules.fulfillment.service import PackingSlipService

        self.svc = PackingSlipService()

    async def _ctx(self, company, order):
        db = AsyncMock()
        with (
            patch(
                "app.modules.company.repository.CompanyConfigRepository.get",
                new=AsyncMock(return_value=company),
            ),
            patch(
                "app.modules.fulfillment.service._logo_data_uri",
                return_value=None,
            ),
        ):
            return await self.svc._build_context(db, order)

    async def test_context_has_required_top_level_keys(self):
        ctx = await self._ctx(_make_company(), _make_order())
        for key in ("company", "order", "items", "logo_data_uri"):
            assert key in ctx

    async def test_order_dict_has_subtotal_and_tax_amount(self):
        order = _make_order(subtotal=Decimal("1010.00"), tax_amount=Decimal("18.00"))
        ctx = await self._ctx(_make_company(), order)
        assert ctx["order"]["subtotal"] == 1010.0
        assert ctx["order"]["tax_amount"] == 18.0

    async def test_defaults_when_company_is_none(self):
        ctx = await self._ctx(None, _make_order())
        assert ctx["company"]["name"] == "Hadha Jewellery"
        assert ctx["company"]["tagline"] == "Timeless Beauty, Trusted Quality"
        assert ctx["company"]["country"] == "IN"

    async def test_items_have_expected_fields(self):
        items = [_make_item("Ring", sku="SKU-001", variant="22K Gold", qty=1)]
        order = _make_order(items=items)
        ctx = await self._ctx(_make_company(), order)
        item = ctx["items"][0]
        assert item["product_name"] == "Ring"
        assert item["product_sku"] == "SKU-001"
        assert item["variant_name"] == "22K Gold"
        assert item["quantity"] == 1
        assert "line_total" in item


# ─── ShippingLabelService._barcode_b64 static method ─────────────────────────


class TestShippingLabelServiceBarcode:
    def setup_method(self):
        from app.modules.fulfillment.service import ShippingLabelService

        self.svc = ShippingLabelService()

    def test_barcode_b64_returns_none_on_import_error(self):
        import sys
        import unittest.mock

        # Remove barcode from sys.modules so import inside the method fails
        barcode_mod = sys.modules.pop("barcode", None)
        barcode_writer_mod = sys.modules.pop("barcode.writer", None)
        # Force ImportError by inserting a fake that raises
        sys.modules["barcode"] = unittest.mock.MagicMock(
            **{"get.side_effect": ImportError("no barcode")}
        )
        try:
            result = self.svc._barcode_b64("IP123456789IN")
        finally:
            # Restore original modules
            if barcode_mod is not None:
                sys.modules["barcode"] = barcode_mod
            else:
                sys.modules.pop("barcode", None)
            if barcode_writer_mod is not None:
                sys.modules["barcode.writer"] = barcode_writer_mod
            else:
                sys.modules.pop("barcode.writer", None)
        assert result is None

    def test_barcode_b64_returns_none_on_generic_exception(self):
        import sys
        import unittest.mock

        mock_barcode = unittest.mock.MagicMock()
        mock_barcode.get.side_effect = RuntimeError("barcode failed")
        barcode_mod = sys.modules.pop("barcode", None)
        sys.modules["barcode"] = mock_barcode
        try:
            result = self.svc._barcode_b64("IP123456789IN")
        finally:
            if barcode_mod is not None:
                sys.modules["barcode"] = barcode_mod
            else:
                sys.modules.pop("barcode", None)
        assert result is None

    def test_barcode_b64_returns_base64_string_when_library_works(self):
        import base64
        from unittest.mock import MagicMock, patch

        fake_bytes = b"PNG_IMAGE_DATA"

        mock_bc_obj = MagicMock()

        def fake_write(buf, options=None):
            buf.write(fake_bytes)

        mock_bc_obj.write.side_effect = fake_write
        mock_bc_get = MagicMock(return_value=mock_bc_obj)
        mock_writer = MagicMock()

        with (
            patch.dict(
                "sys.modules",
                {
                    "barcode": MagicMock(get=mock_bc_get),
                    "barcode.writer": MagicMock(ImageWriter=mock_writer),
                },
            ),
        ):
            result = self.svc._barcode_b64("IP123456789IN")

        assert result is not None
        assert isinstance(result, str)
        # Verify it's valid base64
        decoded = base64.b64decode(result)
        assert decoded == fake_bytes
