from decimal import Decimal

from app.modules.tax.service import TaxService


class TestCalculateGst:
    def test_intra_state_splits_cgst_sgst(self):
        result = TaxService.calculate_gst(Decimal("1000.00"), "Maharashtra")
        assert result.is_interstate is False
        assert result.cgst_amount == Decimal("15.00")
        assert result.sgst_amount == Decimal("15.00")
        assert result.igst_amount == Decimal("0.00")
        assert result.total_tax == Decimal("30.00")

    def test_inter_state_charges_igst(self):
        result = TaxService.calculate_gst(Decimal("1000.00"), "Karnataka")
        assert result.is_interstate is True
        assert result.cgst_amount == Decimal("0.00")
        assert result.sgst_amount == Decimal("0.00")
        assert result.igst_amount == Decimal("30.00")
        assert result.total_tax == Decimal("30.00")

    def test_state_match_is_case_and_whitespace_insensitive(self):
        result = TaxService.calculate_gst(Decimal("100"), "  maharashtra ")
        assert result.is_interstate is False

    def test_missing_state_treated_as_interstate(self):
        result = TaxService.calculate_gst(Decimal("100"), None)
        assert result.is_interstate is True

    def test_zero_amount(self):
        result = TaxService.calculate_gst(Decimal("0"), "Maharashtra")
        assert result.total_tax == Decimal("0.00")

    def test_rounding_half_up_to_paise(self):
        # 333.33 * 1.5% = 4.99995 → 5.00 per component
        result = TaxService.calculate_gst(Decimal("333.33"), "Maharashtra")
        assert result.cgst_amount == Decimal("5.00")
        assert result.sgst_amount == Decimal("5.00")

    def test_custom_rate_override(self):
        result = TaxService.calculate_gst(Decimal("100"), "Delhi", gst_rate=5.0)
        assert result.igst_amount == Decimal("5.00")


class TestSplitTotalTax:
    def test_intra_state_halves_sum_exactly(self):
        # 26.95 / 2 = 13.475 → rounding must not lose a paisa
        result = TaxService.split_total_tax(Decimal("26.95"), "Maharashtra")
        assert result.cgst_amount + result.sgst_amount == Decimal("26.95")

    def test_inter_state_keeps_full_amount_as_igst(self):
        result = TaxService.split_total_tax(Decimal("26.95"), "Tamil Nadu")
        assert result.igst_amount == Decimal("26.95")
        assert result.cgst_amount == Decimal("0.00")
