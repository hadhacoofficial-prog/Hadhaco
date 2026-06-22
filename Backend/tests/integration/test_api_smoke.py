"""In-process API smoke tests — no DB/Redis required.

These verify the app factory wires every router, exception handler, and
middleware correctly, and that auth guards reject anonymous requests.
"""


class TestAppWiring:
    async def test_liveness(self, client):
        resp = await client.get("/health/live")
        assert resp.status_code == 200
        assert resp.json() == {"status": "alive"}

    async def test_root(self, client):
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "version" in resp.json()

    async def test_openapi_lists_all_modules(self, app):
        schema = app.openapi()
        paths = schema["paths"].keys()
        # webhooks are include_in_schema=False by design — covered by request test below
        expected_fragments = [
            "/api/v1/products",
            "/api/v1/cart",
            "/api/v1/orders",
            "/api/v1/payments",
            "/api/v1/admin/dashboard",
            "/api/v1/admin/audit-logs",
        ]
        joined = " ".join(paths)
        for fragment in expected_fragments:
            assert fragment in joined, f"missing route: {fragment}"


class TestAuthGuards:
    async def test_me_requires_token(self, client):
        resp = await client.get("/api/v1/me")
        assert resp.status_code == 401

    async def test_admin_dashboard_requires_token(self, client):
        resp = await client.get("/api/v1/admin/dashboard")
        assert resp.status_code == 401

    async def test_invalid_bearer_rejected(self, client):
        resp = await client.get(
            "/api/v1/me", headers={"Authorization": "Bearer not-a-real-token"}
        )
        assert resp.status_code == 401

    async def test_webhook_missing_signature_rejected(self, client):
        resp = await client.post("/api/v1/webhooks/razorpay", json={"event": "x"})
        assert resp.status_code == 400


class TestSecurityHeaders:
    async def test_security_headers_present(self, client):
        resp = await client.get("/health/live")
        assert "x-request-id" in {k.lower() for k in resp.headers.keys()}
