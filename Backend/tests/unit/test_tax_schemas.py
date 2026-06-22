"""Tests for tax schemas and serialization."""

from decimal import Decimal

from app.modules.tax.service import TaxService


class TestTaxBreakdown:
    def test_intrastate_breakdown_structure(self):
        bd = TaxService.calculate_gst(Decimal("1000"), "Maharashtra")
        assert hasattr(bd, "cgst_amount")
        assert hasattr(bd, "sgst_amount")
        assert hasattr(bd, "igst_amount")
        assert hasattr(bd, "total_tax")
        assert hasattr(bd, "is_interstate")

    def test_intrastate_igst_is_zero(self):
        bd = TaxService.calculate_gst(Decimal("1000"), "Maharashtra")
        assert bd.igst_amount == Decimal("0.00")

    def test_interstate_cgst_sgst_are_zero(self):
        bd = TaxService.calculate_gst(Decimal("1000"), "Karnataka")
        assert bd.cgst_amount == Decimal("0.00")
        assert bd.sgst_amount == Decimal("0.00")

    def test_total_equals_sum_intrastate(self):
        bd = TaxService.calculate_gst(Decimal("500"), "Maharashtra")
        assert bd.total_tax == bd.cgst_amount + bd.sgst_amount

    def test_total_equals_igst_interstate(self):
        bd = TaxService.calculate_gst(Decimal("500"), "Delhi")
        assert bd.total_tax == bd.igst_amount

    def test_split_intrastate_preserves_total(self):
        for amount in [Decimal("1.00"), Decimal("99.99"), Decimal("1500.50"), Decimal("26.95")]:
            bd = TaxService.split_total_tax(amount, "Maharashtra")
            assert bd.cgst_amount + bd.sgst_amount == amount

    def test_split_interstate_full_igst(self):
        bd = TaxService.split_total_tax(Decimal("50.00"), "Rajasthan")
        assert bd.igst_amount == Decimal("50.00")

    def test_custom_rate_3_percent_intrastate(self):
        bd = TaxService.calculate_gst(Decimal("1000"), "Maharashtra", gst_rate=3.0)
        assert bd.total_tax == Decimal("30.00")
        assert bd.cgst_amount == Decimal("15.00")
        assert bd.sgst_amount == Decimal("15.00")

    def test_custom_rate_18_percent_interstate(self):
        bd = TaxService.calculate_gst(Decimal("100"), "Delhi", gst_rate=18.0)
        assert bd.total_tax == Decimal("18.00")
        assert bd.igst_amount == Decimal("18.00")

    def test_large_amount_rounding(self):
        bd = TaxService.calculate_gst(Decimal("99999.99"), "Maharashtra")
        assert bd.cgst_amount + bd.sgst_amount == bd.total_tax
