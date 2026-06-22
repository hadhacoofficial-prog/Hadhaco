"""GST calculation for hallmarked silver jewellery (HSN 7113, 3% GST).

Intra-state sales split the rate into CGST + SGST; inter-state sales charge
IGST at the full rate. Making charges are bundled into base_price, so the
single product-level rate applies to the whole taxable amount.

Tax is locked on the order row at creation time and never recalculated.
"""
from decimal import ROUND_HALF_UP, Decimal

from app.core.config import settings
from app.modules.tax.schemas import TaxBreakdown

_TWO_PLACES = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


class TaxService:

    @staticmethod
    def calculate_gst(
        taxable_amount: Decimal | float,
        buyer_state: str | None,
        gst_rate: float | None = None,
    ) -> TaxBreakdown:
        amount = Decimal(str(taxable_amount))
        rate = Decimal(str(gst_rate if gst_rate is not None else settings.TAX_RATE_GST))
        seller_state = settings.SELLER_STATE.strip().lower()
        interstate = (buyer_state or "").strip().lower() != seller_state

        if interstate:
            cgst_rate = sgst_rate = Decimal("0")
            igst_rate = rate
            cgst = sgst = Decimal("0.00")
            igst = _money(amount * rate / 100)
        else:
            cgst_rate = sgst_rate = rate / 2
            igst_rate = Decimal("0")
            cgst = _money(amount * cgst_rate / 100)
            sgst = _money(amount * sgst_rate / 100)
            igst = Decimal("0.00")

        return TaxBreakdown(
            taxable_amount=_money(amount),
            gst_rate=rate,
            is_interstate=interstate,
            cgst_rate=cgst_rate,
            sgst_rate=sgst_rate,
            igst_rate=igst_rate,
            cgst_amount=cgst,
            sgst_amount=sgst,
            igst_amount=igst,
            total_tax=cgst + sgst + igst,
        )

    @staticmethod
    def split_total_tax(total_tax: Decimal | float, buyer_state: str | None) -> TaxBreakdown:
        """Split an already-computed tax total into CGST/SGST or IGST.

        Used by the invoice generator: the order stores the locked tax_amount,
        and the split depends only on the shipping state.
        """
        tax = Decimal(str(total_tax))
        rate = Decimal(str(settings.TAX_RATE_GST))
        seller_state = settings.SELLER_STATE.strip().lower()
        interstate = (buyer_state or "").strip().lower() != seller_state

        if interstate:
            return TaxBreakdown(
                taxable_amount=Decimal("0.00"),
                gst_rate=rate,
                is_interstate=True,
                cgst_rate=Decimal("0"),
                sgst_rate=Decimal("0"),
                igst_rate=rate,
                cgst_amount=Decimal("0.00"),
                sgst_amount=Decimal("0.00"),
                igst_amount=_money(tax),
                total_tax=_money(tax),
            )

        half = _money(tax / 2)
        # keep the two halves summing exactly to the locked total
        other_half = _money(tax) - half
        return TaxBreakdown(
            taxable_amount=Decimal("0.00"),
            gst_rate=rate,
            is_interstate=False,
            cgst_rate=rate / 2,
            sgst_rate=rate / 2,
            igst_rate=Decimal("0"),
            cgst_amount=half,
            sgst_amount=other_half,
            igst_amount=Decimal("0.00"),
            total_tax=_money(tax),
        )


tax_service = TaxService()
