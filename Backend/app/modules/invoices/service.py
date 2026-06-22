import io
import uuid
from datetime import UTC, datetime

import boto3
from botocore.config import Config

from app.core.config import settings
from app.modules.payments.repository import PaymentRepository


def _r2_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.R2_ENDPOINT_URL,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def _build_pdf(order, invoice_number: str) -> bytes:
    """Build invoice PDF using reportlab."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
    )
    styles = getSampleStyleSheet()
    elements = []

    # Header
    elements.append(Paragraph(f"<b>{settings.APP_NAME}</b>", styles["Title"]))
    if settings.SELLER_GSTIN:
        elements.append(Paragraph(f"GSTIN: {settings.SELLER_GSTIN}", styles["Normal"]))
    elements.append(Spacer(1, 4 * mm))
    elements.append(Paragraph("<b>TAX INVOICE</b>", styles["Heading2"]))
    elements.append(Spacer(1, 2 * mm))

    # Meta info
    issued = datetime.now(UTC).strftime("%d %b %Y")
    meta = [
        ["Invoice Number:", invoice_number],
        ["Order Number:", order.order_number],
        ["Date:", issued],
        ["Payment Method:", order.payment_method or "—"],
    ]
    meta_table = Table(meta, colWidths=[50 * mm, 100 * mm])
    meta_table.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    elements.append(meta_table)
    elements.append(Spacer(1, 5 * mm))

    # Shipping address
    elements.append(Paragraph("<b>Ship To:</b>", styles["Normal"]))
    addr_lines = filter(
        None,
        [
            order.shipping_full_name,
            order.shipping_line1,
            order.shipping_line2,
            f"{order.shipping_city}, {order.shipping_state} {order.shipping_postal}",
            order.shipping_country,
        ],
    )
    elements.append(Paragraph("<br/>".join(addr_lines), styles["Normal"]))
    elements.append(Spacer(1, 5 * mm))

    # Line items table
    header = [["#", "Product", "SKU", "Qty", "Unit Price", "Tax", "Total"]]
    rows = []
    for i, item in enumerate(order.items, 1):
        rows.append(
            [
                str(i),
                item.product_name,
                item.product_sku,
                str(item.quantity),
                f"₹{float(item.unit_price):,.2f}",
                f"₹{float(item.tax_amount):,.2f} ({float(item.tax_rate):.0f}%)",
                f"₹{float(item.line_total):,.2f}",
            ]
        )

    item_table = Table(
        header + rows,
        colWidths=[8 * mm, 55 * mm, 28 * mm, 12 * mm, 25 * mm, 30 * mm, 25 * mm],
    )
    item_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a1a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#f9f9f9")],
                ),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    elements.append(item_table)
    elements.append(Spacer(1, 5 * mm))

    # Totals — GST split per Indian invoicing rules (CGST+SGST intra-state, IGST inter-state)
    from app.modules.tax.service import tax_service

    gst = tax_service.split_total_tax(order.tax_amount, order.shipping_state)
    totals = [["Subtotal", f"₹{float(order.subtotal):,.2f}"]]
    if gst.is_interstate:
        totals.append(
            [f"IGST ({float(gst.igst_rate):g}%)", f"₹{float(gst.igst_amount):,.2f}"]
        )
    else:
        totals.append(
            [f"CGST ({float(gst.cgst_rate):g}%)", f"₹{float(gst.cgst_amount):,.2f}"]
        )
        totals.append(
            [f"SGST ({float(gst.sgst_rate):g}%)", f"₹{float(gst.sgst_amount):,.2f}"]
        )
    totals.append(["Shipping", f"₹{float(order.shipping_charge):,.2f}"])
    if float(order.discount) > 0:
        totals.append(["Discount", f"-₹{float(order.discount):,.2f}"])
    totals.append(["", ""])
    totals.append(["TOTAL", f"₹{float(order.total):,.2f}"])

    totals_table = Table(totals, colWidths=[130 * mm, 40 * mm])
    totals_table.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.black),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    elements.append(totals_table)

    doc.build(elements)
    return buf.getvalue()


class InvoiceService:
    async def generate_and_store(self, db, order) -> dict:
        """
        Generate PDF, upload to R2, record in DB.
        Returns {"invoice_number": ..., "pdf_url": ...}
        """
        repo = PaymentRepository()
        existing = await repo.get_invoice_for_order(db, order.id)
        if existing:
            return {
                "invoice_number": existing.invoice_number,
                "pdf_url": existing.pdf_url,
            }

        invoice_number = await repo.generate_invoice_number(db)
        pdf_bytes = _build_pdf(order, invoice_number)

        # Upload to R2
        r2_key = f"invoices/{order.id}/{invoice_number}.pdf"
        client = _r2_client()
        client.put_object(
            Bucket=settings.R2_BUCKET_NAME,
            Key=r2_key,
            Body=pdf_bytes,
            ContentType="application/pdf",
        )
        pdf_url = f"{settings.R2_PUBLIC_URL.rstrip('/')}/{r2_key}"

        invoice = await repo.create_invoice(
            db,
            {
                "id": uuid.uuid4(),
                "order_id": order.id,
                "invoice_number": invoice_number,
                "pdf_url": pdf_url,
                "pdf_r2_key": r2_key,
            },
        )

        return {"invoice_number": invoice.invoice_number, "pdf_url": invoice.pdf_url}

    async def get_download_url(
        self, db, order_id: uuid.UUID, user_id: uuid.UUID
    ) -> str:
        """Return a presigned 10-minute download URL for the invoice PDF."""
        from app.core.exceptions import NotFoundError
        from app.modules.orders.repository import OrderRepository

        order = await OrderRepository().get_by_id(db, order_id)
        if not order or order.user_id != user_id:
            raise NotFoundError("Order not found")

        repo = PaymentRepository()
        invoice = await repo.get_invoice_for_order(db, order_id)
        if not invoice or not invoice.pdf_r2_key:
            raise NotFoundError("Invoice not yet generated")

        client = _r2_client()
        url = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.R2_BUCKET_NAME, "Key": invoice.pdf_r2_key},
            ExpiresIn=600,
        )
        return url
