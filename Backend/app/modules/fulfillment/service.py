import uuid
from datetime import datetime
from io import BytesIO

import barcode
import boto3
import qrcode
from botocore.config import Config
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, A6
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.fulfillment.models import FulfillmentTimeline
from app.modules.fulfillment.repository import FulfillmentTimelineRepository
from app.modules.fulfillment.schemas import (
    DispatchOrderRequest,
    PackingSlipResponse,
    ShippingLabelResponse,
)
from app.modules.orders.models import Order
from app.modules.orders.repository import OrderRepository
from app.modules.shipping.models import Shipment
from app.modules.shipping.repository import ShipmentRepository


def _r2_client():
    """Create and return an R2 client."""
    return boto3.client(
        "s3",
        endpoint_url=settings.R2_ENDPOINT_URL,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


class FulfillmentService:
    """Service for managing order fulfillment workflow."""

    def __init__(self):
        self.timeline_repo = FulfillmentTimelineRepository()
        self.order_repo = OrderRepository()
        self.shipment_repo = ShipmentRepository()

    async def confirm_payment(
        self,
        db: AsyncSession,
        order_id: uuid.UUID,
        admin_id: uuid.UUID,
        admin_name: str,
    ) -> Order:
        """Confirm payment and update order status.

        Args:
            db: Database session
            order_id: Order to confirm
            admin_id: Admin user ID
            admin_name: Admin user name

        Returns:
            Updated Order
        """
        order = await self.order_repo.get_by_id(db, order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        order.payment_status = "paid"
        order.status = "confirmed"
        order.fulfilled_by = admin_id
        order.last_fulfillment_action = "confirm_payment"

        await self.timeline_repo.add_entry(
            db,
            order_id,
            "confirm_payment",
            actor_id=admin_id,
            admin_name=admin_name,
            details={"payment_status": "paid", "status": "confirmed"},
        )

        return order

    async def mark_packing(
        self,
        db: AsyncSession,
        order_id: uuid.UUID,
        admin_id: uuid.UUID,
        admin_name: str,
    ) -> Order:
        """Mark order as being packed.

        Args:
            db: Database session
            order_id: Order to pack
            admin_id: Admin user ID
            admin_name: Admin user name

        Returns:
            Updated Order
        """
        order = await self.order_repo.get_by_id(db, order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        order.fulfillment_status = "packing"
        order.packed_at = datetime.utcnow()
        order.fulfilled_by = admin_id
        order.last_fulfillment_action = "mark_packing"

        await self.timeline_repo.add_entry(
            db,
            order_id,
            "mark_packing",
            actor_id=admin_id,
            admin_name=admin_name,
            details={"fulfillment_status": "packing"},
        )

        return order

    async def generate_shipping_label(
        self,
        db: AsyncSession,
        order_id: uuid.UUID,
        admin_id: uuid.UUID,
        admin_name: str,
    ) -> ShippingLabelResponse:
        """Generate and store shipping label PDF.

        Args:
            db: Database session
            order_id: Order for which to generate label
            admin_id: Admin user ID
            admin_name: Admin user name

        Returns:
            ShippingLabelResponse with URL and R2 key
        """
        order = await self.order_repo.get_by_id(db, order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        label_service = ShippingLabelService()
        label_url, r2_key = await label_service.generate_label(
            db, order, admin_id, admin_name
        )

        order.fulfillment_status = "label_generated"
        order.shipping_label_generated_at = datetime.utcnow()
        order.fulfilled_by = admin_id
        order.last_fulfillment_action = "generate_label"

        await self.timeline_repo.add_entry(
            db,
            order_id,
            "generate_label",
            actor_id=admin_id,
            admin_name=admin_name,
            details={"label_url": label_url},
        )

        return ShippingLabelResponse(label_url=label_url, pdf_r2_key=r2_key)

    async def generate_packing_slip(
        self,
        db: AsyncSession,
        order_id: uuid.UUID,
    ) -> PackingSlipResponse:
        """Generate and store packing slip PDF.

        Args:
            db: Database session
            order_id: Order for which to generate slip

        Returns:
            PackingSlipResponse with URL and R2 key
        """
        order = await self.order_repo.get_by_id(db, order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        slip_service = PackingSlipService()
        slip_url, r2_key = await slip_service.generate_slip(db, order)

        return PackingSlipResponse(slip_url=slip_url, pdf_r2_key=r2_key)

    async def dispatch_order(
        self,
        db: AsyncSession,
        order_id: uuid.UUID,
        request: DispatchOrderRequest,
        admin_id: uuid.UUID,
        admin_name: str,
    ) -> Order:
        """Mark order as dispatched with shipping provider and tracking info.

        Args:
            db: Database session
            order_id: Order to dispatch
            request: Dispatch details
            admin_id: Admin user ID
            admin_name: Admin user name

        Returns:
            Updated Order
        """
        order = await self.order_repo.get_by_id(db, order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        # Update order fields
        order.fulfillment_status = "dispatched"
        order.shipping_provider = request.shipping_provider.value
        order.tracking_number = request.tracking_number
        order.dispatched_at = request.dispatch_date or datetime.utcnow()
        order.shipment_notes = request.dispatch_notes
        order.fulfilled_by = admin_id
        order.last_fulfillment_action = "dispatch"

        # Update shipment if exists, otherwise create one
        shipment = await self.shipment_repo.get_for_order(db, order_id)
        if not shipment:
            shipment = Shipment(
                order_id=order_id,
                provider=request.shipping_provider.value,
                awb_number=request.tracking_number,
            )
            db.add(shipment)
        else:
            shipment.provider = request.shipping_provider.value
            shipment.awb_number = request.tracking_number

        shipment.dispatch_date = request.dispatch_date or datetime.utcnow()
        shipment.expected_delivery_date = request.expected_delivery_date
        shipment.dispatch_notes = request.dispatch_notes
        shipment.fulfilled_by = admin_id

        await self.timeline_repo.add_entry(
            db,
            order_id,
            "dispatch",
            actor_id=admin_id,
            admin_name=admin_name,
            details={
                "shipping_provider": request.shipping_provider.value,
                "tracking_number": request.tracking_number,
                "dispatch_date": (
                    request.dispatch_date or datetime.utcnow()
                ).isoformat(),
            },
        )

        return order

    async def mark_in_transit(
        self,
        db: AsyncSession,
        order_id: uuid.UUID,
        admin_id: uuid.UUID,
        admin_name: str,
    ) -> Order:
        """Mark order as in transit.

        Args:
            db: Database session
            order_id: Order in transit
            admin_id: Admin user ID
            admin_name: Admin user name

        Returns:
            Updated Order
        """
        order = await self.order_repo.get_by_id(db, order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        order.fulfillment_status = "in_transit"
        order.fulfilled_by = admin_id
        order.last_fulfillment_action = "mark_in_transit"

        await self.timeline_repo.add_entry(
            db,
            order_id,
            "mark_in_transit",
            actor_id=admin_id,
            admin_name=admin_name,
            details={"fulfillment_status": "in_transit"},
        )

        return order

    async def mark_delivered(
        self,
        db: AsyncSession,
        order_id: uuid.UUID,
        admin_id: uuid.UUID,
        admin_name: str,
    ) -> Order:
        """Mark order as delivered.

        Args:
            db: Database session
            order_id: Order delivered
            admin_id: Admin user ID
            admin_name: Admin user name

        Returns:
            Updated Order
        """
        order = await self.order_repo.get_by_id(db, order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        order.fulfillment_status = "delivered"
        order.delivered_at = datetime.utcnow()
        order.fulfilled_by = admin_id
        order.last_fulfillment_action = "mark_delivered"

        await self.timeline_repo.add_entry(
            db,
            order_id,
            "mark_delivered",
            actor_id=admin_id,
            admin_name=admin_name,
            details={"fulfillment_status": "delivered"},
        )

        return order

    async def get_fulfillment_timeline(
        self,
        db: AsyncSession,
        order_id: uuid.UUID,
    ) -> list[FulfillmentTimeline]:
        """Get fulfillment timeline for an order.

        Args:
            db: Database session
            order_id: Order ID

        Returns:
            List of timeline entries (newest first)
        """
        return await self.timeline_repo.get_for_order(db, order_id)

    def validate_status_transition(self, current_status: str, new_status: str) -> bool:
        """Validate that a status transition is allowed.

        Args:
            current_status: Current fulfillment status
            new_status: Desired fulfillment status

        Returns:
            True if transition is valid

        Raises:
            ValueError: If transition is invalid
        """
        valid_transitions = {
            "pending": ["packing", "cancelled"],
            "packing": ["label_generated", "cancelled"],
            "label_generated": ["dispatched", "cancelled"],
            "dispatched": ["in_transit", "cancelled"],
            "in_transit": ["delivered", "cancelled"],
            "delivered": ["returned", "cancelled"],
            "cancelled": [],
            "returned": ["refunded"],
            "refunded": [],
        }

        if current_status not in valid_transitions:
            raise ValueError(f"Unknown current status: {current_status}")

        if new_status not in valid_transitions.get(current_status, []):
            raise ValueError(f"Cannot transition from {current_status} to {new_status}")

        return True


class ShippingLabelService:
    """Service for generating shipping label PDFs."""

    COMPANY_NAME = "Hadha Jewellery"
    COMPANY_ADDRESS = "Your Company Address\nYour City, State ZIP\nIndia"
    COMPANY_PHONE = "+91 XXXXX XXXXX"
    COMPANY_GST = "Your GST Number"

    async def generate_label(
        self,
        db: AsyncSession,
        order: Order,
        admin_id: uuid.UUID,
        admin_name: str,
    ) -> tuple[str, str]:
        """Generate A6 shipping label PDF.

        Args:
            db: Database session
            order: Order to generate label for
            admin_id: Admin user ID
            admin_name: Admin user name

        Returns:
            Tuple of (label_url, r2_key)
        """
        # Create PDF in memory
        pdf_buffer = BytesIO()
        doc = SimpleDocTemplate(
            pdf_buffer,
            pagesize=A6,
            leftMargin=5 * mm,
            rightMargin=5 * mm,
            topMargin=5 * mm,
            bottomMargin=5 * mm,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "CustomTitle",
            parent=styles["Normal"],
            fontSize=10,
            fontName="Helvetica-Bold",
            spaceAfter=6,
        )
        normal_style = ParagraphStyle(
            "CustomNormal",
            parent=styles["Normal"],
            fontSize=8,
            spaceAfter=2,
        )

        # Build content
        elements = []

        # FROM Address Section
        elements.append(Paragraph("<b>FROM:</b>", title_style))
        from_text = (
            f"{self.COMPANY_NAME}<br/>{self.COMPANY_ADDRESS}<br/>{self.COMPANY_PHONE}"
        )
        elements.append(Paragraph(from_text, normal_style))
        elements.append(Spacer(1, 3 * mm))

        # TO Address Section
        elements.append(Paragraph("<b>TO:</b>", title_style))
        to_text = f"{order.shipping_full_name}<br/>{order.shipping_line1}"
        if order.shipping_line2:
            to_text += f"<br/>{order.shipping_line2}"
        to_text += f"<br/>{order.shipping_city}, {order.shipping_state} {order.shipping_postal}"
        if order.shipping_phone:
            to_text += f"<br/>Phone: {order.shipping_phone}"
        elements.append(Paragraph(to_text, normal_style))
        elements.append(Spacer(1, 3 * mm))

        # Order Details Section
        elements.append(Paragraph("<b>ORDER DETAILS:</b>", title_style))
        details_text = f"Order #: {order.order_number}<br/>Date: {order.created_at.strftime('%Y-%m-%d')}"
        if order.tracking_number:
            details_text += f"<br/>AWB: {order.tracking_number}"
        elements.append(Paragraph(details_text, normal_style))
        elements.append(Spacer(1, 3 * mm))

        # Generate barcode if tracking number exists
        if order.tracking_number:
            barcode_buffer = BytesIO()
            try:
                barcode_obj = barcode.get(
                    "code128",
                    order.tracking_number,
                    writer_options={"module_width": 0.5},
                )
                barcode_obj.write(barcode_buffer)
                barcode_buffer.seek(0)
            except Exception:
                pass

        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=5,
            border=1,
        )
        qr.add_data(f"{order.order_number}:{order.tracking_number or ''}")
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white")
        qr_buffer = BytesIO()
        qr_img.save(qr_buffer, format="PNG")
        qr_buffer.seek(0)

        # Additional Info
        elements.append(Spacer(1, 2 * mm))
        additional_text = f"Provider: {order.shipping_provider or 'TBD'}<br/>Payment: {('PREPAID' if order.payment_status == 'paid' else 'COD')}"
        elements.append(Paragraph(additional_text, normal_style))

        # Build PDF
        doc.build(elements)

        # Upload to R2
        pdf_buffer.seek(0)
        filename = f"shipping-labels/{order.id}/{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"

        client = _r2_client()
        client.put_object(
            Bucket=settings.R2_BUCKET_NAME,
            Key=filename,
            Body=pdf_buffer.getvalue(),
            ContentType="application/pdf",
        )

        # Generate URL
        label_url = f"{settings.R2_PUBLIC_URL.rstrip('/')}/{filename}"

        return label_url, filename


class PackingSlipService:
    """Service for generating packing slip PDFs."""

    async def generate_slip(
        self,
        db: AsyncSession,
        order: Order,
    ) -> tuple[str, str]:
        """Generate A4 packing slip PDF.

        Args:
            db: Database session
            order: Order to generate slip for

        Returns:
            Tuple of (slip_url, r2_key)
        """
        # Create PDF in memory
        pdf_buffer = BytesIO()
        doc = SimpleDocTemplate(
            pdf_buffer,
            pagesize=A4,
            leftMargin=15 * mm,
            rightMargin=15 * mm,
            topMargin=15 * mm,
            bottomMargin=15 * mm,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "CustomTitle",
            parent=styles["Normal"],
            fontSize=14,
            fontName="Helvetica-Bold",
            spaceAfter=12,
        )
        heading_style = ParagraphStyle(
            "CustomHeading",
            parent=styles["Normal"],
            fontSize=10,
            fontName="Helvetica-Bold",
            spaceAfter=6,
        )
        normal_style = ParagraphStyle(
            "CustomNormal",
            parent=styles["Normal"],
            fontSize=9,
            spaceAfter=3,
        )

        elements = []

        # Title
        elements.append(Paragraph("PACKING SLIP", title_style))

        # Order and Customer Info
        elements.append(
            Paragraph(f"<b>Order Number:</b> {order.order_number}", normal_style)
        )
        elements.append(
            Paragraph(f"<b>Customer:</b> {order.shipping_full_name}", normal_style)
        )
        if order.shipping_phone:
            elements.append(
                Paragraph(f"<b>Phone:</b> {order.shipping_phone}", normal_style)
            )
        elements.append(Spacer(1, 6 * mm))

        # Items Table
        elements.append(Paragraph("<b>ITEMS TO PACK:</b>", heading_style))

        table_data = [["Product", "SKU", "Variant", "Qty"]]
        for item in order.items:
            table_data.append(
                [
                    item.product_name,
                    item.product_sku,
                    item.variant_name or "-",
                    str(item.quantity),
                ]
            )

        table = Table(table_data, colWidths=[150 * mm, 30 * mm, 50 * mm, 20 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 9),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                    ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ]
            )
        )
        elements.append(table)
        elements.append(Spacer(1, 8 * mm))

        # Packing Notes Section
        elements.append(Paragraph("<b>PACKING NOTES:</b>", heading_style))
        elements.append(Paragraph("_" * 100, normal_style))
        elements.append(Spacer(1, 20 * mm))
        elements.append(Paragraph("_" * 100, normal_style))
        elements.append(Spacer(1, 6 * mm))

        # Warehouse Notes Section
        elements.append(Paragraph("<b>WAREHOUSE NOTES:</b>", heading_style))
        elements.append(Paragraph("_" * 100, normal_style))

        # Build PDF
        doc.build(elements)

        # Upload to R2
        pdf_buffer.seek(0)
        filename = f"packing-slips/{order.id}/{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"

        client = _r2_client()
        client.put_object(
            Bucket=settings.R2_BUCKET_NAME,
            Key=filename,
            Body=pdf_buffer.getvalue(),
            ContentType="application/pdf",
        )

        # Generate URL
        slip_url = f"{settings.R2_PUBLIC_URL.rstrip('/')}/{filename}"

        return slip_url, filename
