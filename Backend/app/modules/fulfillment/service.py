import uuid
from datetime import datetime
from io import BytesIO

import qrcode
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.fulfillment.models import FulfillmentTimeline
from app.modules.fulfillment.repository import FulfillmentTimelineRepository
from app.modules.fulfillment.schemas import DispatchOrderRequest
from app.modules.orders.models import Order
from app.modules.orders.repository import OrderRepository
from app.modules.shipping.models import Shipment
from app.modules.shipping.repository import ShipmentRepository


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

    async def mark_label_generated(
        self,
        db: AsyncSession,
        order_id: uuid.UUID,
        admin_id: uuid.UUID,
        admin_name: str,
    ) -> None:
        """Record that a shipping label was generated (on-demand; no file stored)."""
        order = await self.order_repo.get_by_id(db, order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

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
            details={"method": "on_demand"},
        )

    async def get_shipping_label_html(
        self, db: AsyncSession, order_id: uuid.UUID
    ) -> str:
        order = await self.order_repo.get_by_id(db, order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        return await ShippingLabelService().render_html(db, order)

    async def get_shipping_label_pdf(
        self, db: AsyncSession, order_id: uuid.UUID
    ) -> bytes:
        order = await self.order_repo.get_by_id(db, order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        return await ShippingLabelService().render_pdf(db, order)

    async def get_packing_slip_html(self, db: AsyncSession, order_id: uuid.UUID) -> str:
        order = await self.order_repo.get_by_id(db, order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        return await PackingSlipService().render_html(db, order)

    async def get_packing_slip_pdf(
        self, db: AsyncSession, order_id: uuid.UUID
    ) -> bytes:
        order = await self.order_repo.get_by_id(db, order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        return await PackingSlipService().render_pdf(db, order)

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


def _register_unicode_font() -> bool:
    """Register a Telugu/Unicode-capable font with ReportLab (once per process).

    Returns True if a suitable font was registered as 'HadhaUni'.
    """
    import pathlib

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if "HadhaUni" in pdfmetrics.getRegisteredFontNames():
        return True
    candidates = [
        r"C:\Windows\Fonts\Gautami.ttf",
        r"C:\Windows\Fonts\gautamib.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansTelugu-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    ]
    for path in candidates:
        if pathlib.Path(path).exists():
            try:
                pdfmetrics.registerFont(TTFont("HadhaUni", path))
                return True
            except Exception:
                continue
    return False


def _logo_data_uri() -> str | None:
    import base64
    import pathlib

    logo = pathlib.Path(__file__).parent.parent.parent / "templates" / "hadha-logo.png"
    try:
        data = base64.b64encode(logo.read_bytes()).decode()
        return f"data:image/png;base64,{data}"
    except Exception:
        return None


class ShippingLabelService:
    """On-demand shipping label renderer — no file storage.

    Fetches order + company config from DB, generates barcode/QR as base64,
    renders the Jinja2 HTML template, and optionally converts to PDF via
    xhtml2pdf. Nothing is written to disk or uploaded to R2.
    """

    _TEMPLATE_PATH = (
        __import__("pathlib").Path(__file__).parent.parent.parent
        / "templates"
        / "shipping_label.html"
    )

    def _get_template(self) -> str:
        return self._TEMPLATE_PATH.read_text(encoding="utf-8")

    @staticmethod
    def _barcode_b64(value: str) -> str | None:
        import base64

        try:
            from barcode import get as bc_get
            from barcode.writer import ImageWriter

            buf = BytesIO()
            bc_get("code128", value, writer=ImageWriter()).write(
                buf, options={"module_width": 0.4, "module_height": 8, "quiet_zone": 1}
            )
            return base64.b64encode(buf.getvalue()).decode()
        except Exception:
            return None

    @staticmethod
    def _qr_b64(value: str) -> str:
        import base64

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=4,
            border=1,
        )
        qr.add_data(value)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()

    async def _build_context(self, db: AsyncSession, order: Order) -> dict:

        from app.modules.company.repository import CompanyConfigRepository

        company = await CompanyConfigRepository().get(db)

        company_data = {
            "name": company.name if company else "Hadha Jewellery",
            "tagline": (
                company.tagline if company else "Timeless Beauty, Trusted Quality"
            ),
            "address_line1": company.address_line1 if company else None,
            "address_line2": company.address_line2 if company else None,
            "city": company.city if company else None,
            "state": company.state if company else None,
            "postal_code": company.postal_code if company else None,
            "country": company.country if company else "IN",
            "phone": company.phone if company else None,
            "support_email": company.support_email if company else None,
            "website": company.website if company else None,
            "logo_url": company.logo_url if company else None,
        }

        order_data = {
            "order_number": order.order_number,
            "created_at": order.created_at.strftime("%Y-%m-%d"),
            "dispatched_at": (
                order.dispatched_at.strftime("%Y-%m-%d")
                if order.dispatched_at
                else None
            ),
            "shipping_full_name": order.shipping_full_name,
            "shipping_phone": order.shipping_phone,
            "shipping_alternate_phone": order.shipping_alternate_phone,
            "shipping_line1": order.shipping_line1,
            "shipping_line2": order.shipping_line2,
            "shipping_landmark": order.shipping_landmark,
            "shipping_city": order.shipping_city,
            "shipping_state": order.shipping_state,
            "shipping_postal": order.shipping_postal,
            "shipping_provider": order.shipping_provider,
            "tracking_number": order.tracking_number,
            "shipping_charge": float(order.shipping_charge),
            "discount": float(order.discount),
            "total": float(order.total),
            "item_count": sum(i.quantity for i in order.items),
        }

        items_data = [
            {
                "product_name": item.product_name,
                "product_sku": item.product_sku,
                "variant_name": item.variant_name,
                "quantity": item.quantity,
                "line_total": float(item.line_total),
            }
            for item in order.items
        ]

        barcode_b64 = (
            self._barcode_b64(order.tracking_number) if order.tracking_number else None
        )
        qr_data = f"{order.order_number}:{order.tracking_number or ''}"
        qr_b64 = self._qr_b64(qr_data)

        return {
            "company": company_data,
            "order": order_data,
            "items": items_data,
            "logo_data_uri": _logo_data_uri(),
            "barcode_b64": barcode_b64,
            "qr_b64": qr_b64,
        }

    def _render_html(self, context: dict) -> str:
        from jinja2 import BaseLoader, Environment

        env = Environment(loader=BaseLoader(), autoescape=True)
        tmpl = env.from_string(self._get_template())
        return tmpl.render(**context)

    def _html_to_pdf(self, html: str) -> bytes:
        from xhtml2pdf import pisa

        _register_unicode_font()
        buf = BytesIO()
        result = pisa.CreatePDF(html.encode("utf-8"), dest=buf)
        if result.err:
            raise RuntimeError("PDF generation failed")
        return buf.getvalue()

    async def render_html(self, db: AsyncSession, order: Order) -> str:
        context = await self._build_context(db, order)
        return self._render_html(context)

    async def render_pdf(self, db: AsyncSession, order: Order) -> bytes:
        context = await self._build_context(db, order)
        return self._html_to_pdf(self._render_html(context))


class PackingSlipService:
    """On-demand packing slip renderer — no file storage.

    Fetches order + company config from DB, renders the Jinja2 HTML template,
    and optionally converts it to PDF bytes via xhtml2pdf. Nothing is written
    to disk or uploaded to R2.
    """

    _TEMPLATE_PATH = (
        __import__("pathlib").Path(__file__).parent.parent.parent
        / "templates"
        / "packing_slip.html"
    )

    def _get_template(self) -> str:
        return self._TEMPLATE_PATH.read_text(encoding="utf-8")

    async def _build_context(self, db: AsyncSession, order: Order) -> dict:
        from app.modules.company.repository import CompanyConfigRepository

        company = await CompanyConfigRepository().get(db)

        company_data = {
            "name": company.name if company else "Hadha Jewellery",
            "tagline": (
                company.tagline if company else "Timeless Beauty, Trusted Quality"
            ),
            "address_line1": company.address_line1 if company else None,
            "address_line2": company.address_line2 if company else None,
            "city": company.city if company else None,
            "state": company.state if company else None,
            "postal_code": company.postal_code if company else None,
            "country": company.country if company else "IN",
            "phone": company.phone if company else None,
            "support_email": company.support_email if company else None,
            "website": company.website if company else None,
            "logo_url": company.logo_url if company else None,
        }

        order_data = {
            "order_number": order.order_number,
            "created_at": order.created_at.strftime("%Y-%m-%d"),
            "shipping_full_name": order.shipping_full_name,
            "shipping_phone": order.shipping_phone,
            "shipping_alternate_phone": order.shipping_alternate_phone,
            "shipping_line1": order.shipping_line1,
            "shipping_line2": order.shipping_line2,
            "shipping_landmark": order.shipping_landmark,
            "shipping_city": order.shipping_city,
            "shipping_state": order.shipping_state,
            "shipping_postal": order.shipping_postal,
            "shipping_provider": order.shipping_provider,
            "tracking_number": order.tracking_number,
            "subtotal": float(order.subtotal),
            "tax_amount": float(order.tax_amount),
            "shipping_charge": float(order.shipping_charge),
            "discount": float(order.discount),
            "total": float(order.total),
        }

        items_data = [
            {
                "product_name": item.product_name,
                "product_sku": item.product_sku,
                "variant_name": item.variant_name,
                "quantity": item.quantity,
                "line_total": float(item.line_total),
            }
            for item in order.items
        ]

        return {
            "company": company_data,
            "order": order_data,
            "items": items_data,
            "logo_data_uri": _logo_data_uri(),
        }

    def _render_html(self, context: dict) -> str:
        from jinja2 import BaseLoader, Environment

        template_str = self._get_template()
        env = Environment(loader=BaseLoader(), autoescape=True)
        tmpl = env.from_string(template_str)
        return tmpl.render(**context)

    def _html_to_pdf(self, html: str) -> bytes:
        from io import BytesIO

        from xhtml2pdf import pisa

        buf = BytesIO()
        result = pisa.CreatePDF(html.encode("utf-8"), dest=buf)
        if result.err:
            raise RuntimeError("PDF generation failed")
        return buf.getvalue()

    async def render_html(self, db: AsyncSession, order: Order) -> str:
        context = await self._build_context(db, order)
        return self._render_html(context)

    async def render_pdf(self, db: AsyncSession, order: Order) -> bytes:
        context = await self._build_context(db, order)
        html = self._render_html(context)
        return self._html_to_pdf(html)
