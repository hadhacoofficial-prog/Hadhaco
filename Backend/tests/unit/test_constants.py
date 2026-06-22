"""Unit tests for constants, enums, and shared utilities."""

from app.core.constants import (
    AuditAction,
    Gender,
    MetalType,
    NotificationChannel,
    OrderStatus,
    PaymentStatus,
    ProductStatus,
    ReturnStatus,
    ShipmentStatus,
    SupportTicketPriority,
    SupportTicketStatus,
    UserRole,
)


class TestUserRole:
    def test_customer_value(self):
        assert UserRole.CUSTOMER == "customer"

    def test_admin_value(self):
        assert UserRole.ADMIN == "admin"

    def test_super_admin_value(self):
        assert UserRole.SUPER_ADMIN == "super_admin"

    def test_all_three_are_distinct(self):
        assert len({UserRole.CUSTOMER, UserRole.ADMIN, UserRole.SUPER_ADMIN}) == 3

    def test_role_is_string(self):
        assert isinstance(UserRole.CUSTOMER, str)


class TestProductStatus:
    def test_statuses_defined(self):
        assert ProductStatus.DRAFT == "draft"
        assert ProductStatus.ACTIVE == "active"
        assert ProductStatus.ARCHIVED == "archived"


class TestOrderStatus:
    def test_full_lifecycle(self):
        statuses = [
            OrderStatus.PENDING,
            OrderStatus.CONFIRMED,
            OrderStatus.PROCESSING,
            OrderStatus.SHIPPED,
            OrderStatus.DELIVERED,
            OrderStatus.CANCELLED,
            OrderStatus.REFUNDED,
        ]
        assert len(statuses) == 7
        assert all(isinstance(s, str) for s in statuses)


class TestPaymentStatus:
    def test_captured_and_paid_defined(self):
        assert PaymentStatus.CAPTURED == "captured"
        assert PaymentStatus.PAID == "paid"
        assert PaymentStatus.FAILED == "failed"
        assert PaymentStatus.REFUNDED == "refunded"


class TestShipmentStatus:
    def test_in_transit_defined(self):
        assert ShipmentStatus.IN_TRANSIT == "in_transit"
        assert ShipmentStatus.DELIVERED == "delivered"
        assert ShipmentStatus.CANCELLED == "cancelled"


class TestMetalType:
    def test_silver_types_defined(self):
        assert MetalType.SILVER_925 == "925_silver"
        assert MetalType.OXIDIZED_SILVER == "oxidized_silver"
        assert MetalType.GOLD_PLATED_SILVER == "gold_plated_silver"


class TestGender:
    def test_all_genders(self):
        assert Gender.WOMEN == "women"
        assert Gender.MEN == "men"
        assert Gender.KIDS == "kids"
        assert Gender.UNISEX == "unisex"


class TestNotificationChannel:
    def test_channels(self):
        assert NotificationChannel.EMAIL == "email"
        assert NotificationChannel.SMS == "sms"


class TestAuditAction:
    def test_crud_actions(self):
        assert AuditAction.CREATE == "create"
        assert AuditAction.UPDATE == "update"
        assert AuditAction.DELETE == "delete"

    def test_auth_actions(self):
        assert AuditAction.LOGIN == "login"
        assert AuditAction.LOGOUT == "logout"


class TestReturnStatus:
    def test_lifecycle(self):
        assert ReturnStatus.REQUESTED == "requested"
        assert ReturnStatus.APPROVED == "approved"
        assert ReturnStatus.COMPLETED == "completed"


class TestSupportTicket:
    def test_status_values(self):
        assert SupportTicketStatus.OPEN == "open"
        assert SupportTicketStatus.RESOLVED == "resolved"

    def test_priority_values(self):
        assert SupportTicketPriority.HIGH == "high"
        assert SupportTicketPriority.URGENT == "urgent"
