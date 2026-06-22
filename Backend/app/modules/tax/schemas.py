from decimal import Decimal

from pydantic import BaseModel, Field


class TaxBreakdown(BaseModel):
    """GST breakdown for one taxable amount.

    Intra-state (buyer state == seller state): CGST + SGST, each at half rate.
    Inter-state: IGST at the full rate.
    """

    taxable_amount: Decimal = Field(..., ge=0)
    gst_rate: Decimal = Field(..., ge=0, description="Total GST rate percent")
    is_interstate: bool

    cgst_rate: Decimal
    sgst_rate: Decimal
    igst_rate: Decimal

    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    total_tax: Decimal


class TaxCalculationRequest(BaseModel):
    taxable_amount: Decimal = Field(..., ge=0)
    buyer_state: str = Field(..., min_length=1, max_length=100)
