"""Unit tests for exception hierarchy and handlers."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    InventoryError,
    NotFoundError,
    PaymentError,
    RateLimitError,
    ServiceUnavailableError,
    ValidationError,
    WebhookVerificationError,
    register_exception_handlers,
)


class TestExceptionHierarchy:
    def test_not_found_error_status(self):
        err = NotFoundError("item not found")
        assert err.status_code == 404
        assert "not found" in err.message.lower()

    def test_authentication_error_status(self):
        err = AuthenticationError("bad token")
        assert err.status_code == 401

    def test_authorization_error_status(self):
        err = AuthorizationError("no access")
        assert err.status_code == 403

    def test_conflict_error_status(self):
        err = ConflictError("already exists")
        assert err.status_code == 409

    def test_validation_error_status(self):
        err = ValidationError("invalid field")
        assert err.status_code == 422

    def test_rate_limit_error_status(self):
        err = RateLimitError("too many requests")
        assert err.status_code == 429

    def test_inventory_error_status(self):
        err = InventoryError("out of stock")
        assert err.status_code == 409

    def test_payment_error_status(self):
        err = PaymentError("payment failed")
        assert err.status_code == 402

    def test_service_unavailable_status(self):
        err = ServiceUnavailableError("service down")
        assert err.status_code == 503

    def test_webhook_verification_status(self):
        err = WebhookVerificationError("bad sig")
        assert err.status_code == 400

    def test_optional_code_stored(self):
        err = NotFoundError("not found", code="ITEM_MISSING")
        assert err.code == "ITEM_MISSING"

    def test_no_code_is_none(self):
        err = NotFoundError("not found")
        assert err.code is None

    def test_exception_inherits_from_base(self):
        from app.core.exceptions import HadhaException
        assert isinstance(NotFoundError("x"), HadhaException)


class TestExceptionHandlers:
    """Verify exception handlers return correct HTTP status codes via ASGI."""

    def setup_method(self):
        app = FastAPI()
        register_exception_handlers(app)

        @app.get("/not-found")
        def not_found():
            raise NotFoundError("Resource not found")

        @app.get("/auth-error")
        def auth_error():
            raise AuthenticationError("Token required")

        @app.get("/forbidden")
        def forbidden():
            raise AuthorizationError("Forbidden")

        @app.get("/conflict")
        def conflict():
            raise ConflictError("Already exists")

        @app.get("/validation")
        def validation():
            raise ValidationError("Bad input")

        @app.get("/rate-limit")
        def rate_limit():
            raise RateLimitError("Slow down")

        @app.get("/payment")
        def payment():
            raise PaymentError("Payment required")

        self.client = TestClient(app, raise_server_exceptions=False)

    def test_not_found_returns_404(self):
        r = self.client.get("/not-found")
        assert r.status_code == 404
        assert "error" in r.json()

    def test_auth_error_returns_401(self):
        r = self.client.get("/auth-error")
        assert r.status_code == 401

    def test_forbidden_returns_403(self):
        r = self.client.get("/forbidden")
        assert r.status_code == 403

    def test_conflict_returns_409(self):
        r = self.client.get("/conflict")
        assert r.status_code == 409

    def test_validation_returns_422(self):
        r = self.client.get("/validation")
        assert r.status_code == 422

    def test_rate_limit_returns_429(self):
        r = self.client.get("/rate-limit")
        assert r.status_code == 429

    def test_payment_returns_402(self):
        r = self.client.get("/payment")
        assert r.status_code == 402

    def test_response_has_error_key(self):
        r = self.client.get("/not-found")
        body = r.json()
        assert "error" in body
        assert body["error"] == "Resource not found"

    def test_unregistered_route_returns_404(self):
        r = self.client.get("/this-does-not-exist")
        assert r.status_code == 404
