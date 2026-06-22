"""Tests for app/common/responses.py and app/common/response_codes.py."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.common.response_codes import ResponseCode
from app.common.responses import (
    BaseErrorResponse,
    BaseSuccessResponse,
    accepted,
    created,
    deleted,
    ok,
)

# ── Unit tests for helpers ────────────────────────────────────────────────────


class TestOkHelper:
    def test_returns_base_success_response(self):
        result = ok({"key": "value"}, ResponseCode.PRODUCT_FETCHED, "Fetched")
        assert isinstance(result, BaseSuccessResponse)

    def test_success_is_true(self):
        result = ok(None, ResponseCode.PRODUCT_LISTED, "Listed")
        assert result.success is True

    def test_code_is_string_value(self):
        result = ok(None, ResponseCode.AUTH_TOKEN_VERIFIED, "ok")
        assert result.code == "AUTH_TOKEN_VERIFIED"

    def test_message_is_preserved(self):
        result = ok(None, ResponseCode.USER_PROFILE_FETCHED, "Profile loaded")
        assert result.message == "Profile loaded"

    def test_data_is_preserved(self):
        payload = {"id": 1, "name": "Ring"}
        result = ok(payload, ResponseCode.PRODUCT_FETCHED, "ok")
        assert result.data == payload

    def test_data_none(self):
        result = ok(None, ResponseCode.PRODUCT_FETCHED, "ok")
        assert result.data is None

    def test_data_list(self):
        result = ok([1, 2, 3], ResponseCode.PRODUCT_LISTED, "ok")
        assert result.data == [1, 2, 3]


class TestCreatedHelper:
    def test_returns_base_success_response(self):
        result = created({"id": "abc"}, ResponseCode.ORDER_CREATED, "Created")
        assert isinstance(result, BaseSuccessResponse)

    def test_success_is_true(self):
        result = created({}, ResponseCode.ORDER_CREATED, "Created")
        assert result.success is True

    def test_code_matches(self):
        result = created({}, ResponseCode.PRODUCT_CREATED, "Created")
        assert result.code == "PRODUCT_CREATED"

    def test_message_matches(self):
        result = created({}, ResponseCode.ORDER_CREATED, "Order placed")
        assert result.message == "Order placed"

    def test_data_is_preserved(self):
        data = {"order_id": "xyz"}
        result = created(data, ResponseCode.ORDER_CREATED, "ok")
        assert result.data == data


class TestDeletedHelper:
    def test_returns_base_success_response(self):
        result = deleted(ResponseCode.ADDRESS_DELETED, "Deleted")
        assert isinstance(result, BaseSuccessResponse)

    def test_success_is_true(self):
        result = deleted(ResponseCode.ADDRESS_DELETED, "Deleted")
        assert result.success is True

    def test_data_is_none(self):
        result = deleted(ResponseCode.ADDRESS_DELETED, "Deleted")
        assert result.data is None

    def test_code_matches(self):
        result = deleted(ResponseCode.CATEGORY_DELETED, "Removed")
        assert result.code == "CATEGORY_DELETED"

    def test_message_matches(self):
        result = deleted(ResponseCode.PRODUCT_DELETED, "Product removed")
        assert result.message == "Product removed"


class TestAcceptedHelper:
    def test_returns_base_success_response(self):
        result = accepted(None, ResponseCode.ANALYTICS_EVENT_TRACKED, "Accepted")
        assert isinstance(result, BaseSuccessResponse)

    def test_success_is_true(self):
        result = accepted(None, ResponseCode.ANALYTICS_EVENT_TRACKED, "ok")
        assert result.success is True

    def test_code_matches(self):
        result = accepted(None, ResponseCode.ANALYTICS_EVENT_TRACKED, "ok")
        assert result.code == "ANALYTICS_EVENT_TRACKED"

    def test_data_preserved(self):
        result = accepted(
            {"status": "queued"}, ResponseCode.ANALYTICS_EVENT_TRACKED, "ok"
        )
        assert result.data == {"status": "queued"}


# ── BaseErrorResponse ─────────────────────────────────────────────────────────


class TestBaseErrorResponse:
    def test_success_is_false(self):
        err = BaseErrorResponse(code="NOT_FOUND", message="Not found")
        assert err.success is False

    def test_code_preserved(self):
        err = BaseErrorResponse(code="AUTH_FAILED", message="Unauthorized")
        assert err.code == "AUTH_FAILED"

    def test_message_preserved(self):
        err = BaseErrorResponse(code="ERROR", message="Something went wrong")
        assert err.message == "Something went wrong"

    def test_data_defaults_none(self):
        err = BaseErrorResponse(code="ERROR", message="Oops")
        assert err.data is None

    def test_data_can_be_list(self):
        err = BaseErrorResponse(
            code="VALIDATION_ERROR", message="Invalid", data=[{"field": "email"}]
        )
        assert err.data == [{"field": "email"}]


# ── ResponseCode enum ─────────────────────────────────────────────────────────


class TestResponseCode:
    def test_is_string(self):
        assert isinstance(ResponseCode.AUTH_TOKEN_VERIFIED, str)

    def test_value_equals_name(self):
        for code in ResponseCode:
            assert code.value == code.name

    def test_auth_codes_present(self):
        assert ResponseCode.AUTH_TOKEN_VERIFIED == "AUTH_TOKEN_VERIFIED"
        assert ResponseCode.AUTH_LOGOUT_SUCCESS == "AUTH_LOGOUT_SUCCESS"
        assert ResponseCode.AUTH_2FA_SETUP == "AUTH_2FA_SETUP"

    def test_product_codes_present(self):
        assert ResponseCode.PRODUCT_LISTED == "PRODUCT_LISTED"
        assert ResponseCode.PRODUCT_CREATED == "PRODUCT_CREATED"
        assert ResponseCode.PRODUCT_DELETED == "PRODUCT_DELETED"

    def test_order_codes_present(self):
        assert ResponseCode.ORDER_CREATED == "ORDER_CREATED"
        assert ResponseCode.ORDER_CANCELLED == "ORDER_CANCELLED"

    def test_webhook_code_present(self):
        assert ResponseCode.WEBHOOK_PROCESSED == "WEBHOOK_PROCESSED"

    def test_total_code_count(self):
        # ensure we have a healthy number of codes
        assert len(ResponseCode) >= 100


# ── FastAPI integration: envelope in real HTTP response ───────────────────────


def _make_app() -> FastAPI:
    from pydantic import BaseModel

    app = FastAPI()

    class ItemOut(BaseModel):
        name: str

    @app.get("/items/{name}", response_model=BaseSuccessResponse[ItemOut])
    def get_item(name: str):
        return ok(ItemOut(name=name), ResponseCode.PRODUCT_FETCHED, "Item fetched")

    @app.post("/items", response_model=BaseSuccessResponse[ItemOut], status_code=201)
    def create_item(name: str):
        return created(ItemOut(name=name), ResponseCode.PRODUCT_CREATED, "Item created")

    @app.delete("/items/{name}", response_model=BaseSuccessResponse[None])
    def delete_item(name: str):
        return deleted(ResponseCode.PRODUCT_DELETED, "Item deleted")

    return app


class TestEnvelopeIntegration:
    def setup_method(self):
        self.client = TestClient(_make_app())

    def test_get_returns_envelope(self):
        resp = self.client.get("/items/ring")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["code"] == "PRODUCT_FETCHED"
        assert body["message"] == "Item fetched"
        assert body["data"] == {"name": "ring"}

    def test_create_returns_201_envelope(self):
        resp = self.client.post("/items?name=bracelet")
        assert resp.status_code == 201
        body = resp.json()
        assert body["success"] is True
        assert body["code"] == "PRODUCT_CREATED"
        assert body["data"] == {"name": "bracelet"}

    def test_delete_returns_200_with_null_data(self):
        resp = self.client.delete("/items/ring")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["code"] == "PRODUCT_DELETED"
        assert body["data"] is None


# ── Exception handler envelope ────────────────────────────────────────────────


class TestExceptionHandlerEnvelope:
    def setup_method(self):
        from fastapi import FastAPI

        from app.core.exceptions import NotFoundError, register_exception_handlers

        app = FastAPI()
        register_exception_handlers(app)

        @app.get("/missing")
        def missing():
            raise NotFoundError("Item not found", code="ITEM_NOT_FOUND")

        self.client = TestClient(app, raise_server_exceptions=False)

    def test_error_response_has_success_false(self):
        resp = self.client.get("/missing")
        assert resp.status_code == 404
        body = resp.json()
        assert body["success"] is False

    def test_error_response_has_code(self):
        resp = self.client.get("/missing")
        body = resp.json()
        assert body["code"] == "ITEM_NOT_FOUND"

    def test_error_response_has_message(self):
        resp = self.client.get("/missing")
        body = resp.json()
        assert body["message"] == "Item not found"

    def test_error_response_has_data_key(self):
        resp = self.client.get("/missing")
        body = resp.json()
        assert "data" in body
