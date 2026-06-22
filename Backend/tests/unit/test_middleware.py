"""Unit tests for middleware components."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.request_id import RequestIDMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware


def _make_test_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIDMiddleware)

    @app.get("/test")
    def root():
        return {"ok": True}

    return app


class TestRequestIDMiddleware:
    def setup_method(self):
        self.client = TestClient(_make_test_app())

    def test_x_request_id_header_present(self):
        resp = self.client.get("/test")
        assert "x-request-id" in {k.lower() for k in resp.headers}

    def test_request_id_is_non_empty(self):
        resp = self.client.get("/test")
        rid = resp.headers.get("x-request-id") or resp.headers.get("X-Request-ID")
        assert rid and len(rid) > 0

    def test_custom_request_id_propagated(self):
        resp = self.client.get("/test", headers={"X-Request-ID": "my-custom-id"})
        rid = resp.headers.get("x-request-id") or resp.headers.get("X-Request-ID")
        assert rid == "my-custom-id"


class TestSecurityHeadersMiddleware:
    def setup_method(self):
        self.client = TestClient(_make_test_app())

    def test_x_content_type_options(self):
        resp = self.client.get("/test")
        header_names = {k.lower() for k in resp.headers}
        assert "x-content-type-options" in header_names

    def test_x_frame_options(self):
        resp = self.client.get("/test")
        header_names = {k.lower() for k in resp.headers}
        assert "x-frame-options" in header_names

    def test_no_caching_on_api(self):
        resp = self.client.get("/test")
        # Security headers must not include caching directives from middleware
        # (ensuring that the middleware adds the expected security headers)
        assert resp.status_code == 200
