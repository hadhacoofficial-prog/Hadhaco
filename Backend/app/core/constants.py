from enum import StrEnum


class UserRole(StrEnum):
    CUSTOMER = "customer"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


class ProductStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class MetalType(StrEnum):
    SILVER_925 = "925_silver"
    OXIDIZED_SILVER = "oxidized_silver"
    GOLD_PLATED_SILVER = "gold_plated_silver"
    RHODIUM_PLATED_SILVER = "rhodium_plated_silver"
    OTHER = "other"


class Gender(StrEnum):
    WOMEN = "women"
    MEN = "men"
    KIDS = "kids"
    UNISEX = "unisex"


class OrderStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUND_INITIATED = "refund_initiated"
    REFUNDED = "refunded"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"


class PaymentMethod(StrEnum):
    RAZORPAY = "razorpay"
    COD = "cod"
    UPI = "upi"


class ShipmentStatus(StrEnum):
    PENDING = "pending"
    BOOKED = "booked"
    PICKUP_SCHEDULED = "pickup_scheduled"
    PICKED_UP = "picked_up"
    IN_TRANSIT = "in_transit"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    DELIVERY_FAILED = "delivery_failed"
    RETURNED = "returned"
    CANCELLED = "cancelled"


class NotificationChannel(StrEnum):
    EMAIL = "email"
    WHATSAPP = "whatsapp"


class NotificationStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


class ReturnStatus(StrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    PICKED_UP = "picked_up"
    RECEIVED = "received"
    REFUND_INITIATED = "refund_initiated"
    COMPLETED = "completed"


class SupportTicketStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class SupportTicketPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class AddressType(StrEnum):
    SHIPPING = "shipping"
    BILLING = "billing"
    BOTH = "both"


class CouponType(StrEnum):
    PERCENT = "percent"
    FLAT = "flat"
    FREE_SHIPPING = "free_shipping"


class InventoryMovementType(StrEnum):
    PURCHASE = "purchase"
    SALE = "sale"
    RETURN = "return"
    ADJUSTMENT = "adjustment"
    RESERVATION = "reservation"
    RELEASE = "release"


class AuditAction(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGOUT = "logout"
    ROLE_CHANGE = "role_change"
    STATUS_CHANGE = "status_change"
    PRICE_CHANGE = "price_change"
    REFUND = "refund"
    CANCEL = "cancel"


class WebhookProvider(StrEnum):
    RAZORPAY = "razorpay"
    DELIVERY_ONE = "delivery_one"


class WebhookStatus(StrEnum):
    RECEIVED = "received"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    SKIPPED = "skipped"


class SEOEntityType(StrEnum):
    PRODUCT = "product"
    CATEGORY = "category"
    COLLECTION = "collection"
    CMS_PAGE = "cms_page"


# HTTP status helpers used in error responses
HTTP_400 = 400
HTTP_401 = 401
HTTP_403 = 403
HTTP_404 = 404
HTTP_409 = 409
HTTP_422 = 422
HTTP_429 = 429
HTTP_500 = 500
