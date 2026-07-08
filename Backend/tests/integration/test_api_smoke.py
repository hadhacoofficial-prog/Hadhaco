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

    async def test_openapi_lists_universal_media_routes(self, app):
        """The Universal Image System is now the only image pipeline for
        products/collections/categories/avatars/reviews — the Phase 3
        cutover deleted MediaService and every legacy per-module image
        endpoint. See docs/architecture/
        Universal_Responsive_Image_System_Design.md §17."""
        schema = app.openapi()
        paths = schema["paths"].keys()
        expected_fragments = [
            "/api/v1/admin/media/presets",
            "/api/v1/admin/media/{preset_id}/upload",
            "/api/v1/admin/media/{image_id}/crop",
            "/api/v1/admin/media/{image_id}/replace",
            "/api/v1/admin/media/{image_id}/attach",
            "/api/v1/admin/media/reorder",
            "/api/v1/admin/media/{image_id}/regenerate",
        ]
        joined = " ".join(paths)
        for fragment in expected_fragments:
            assert fragment in joined, f"missing route: {fragment}"

        # Legacy per-module endpoints are gone, not just deprecated.
        removed_fragments = [
            "/api/v1/admin/products/{product_id}/images",
            "/api/v1/admin/collections/{col_id}/image",
            "/api/v1/admin/categories/{cat_id}/image",
        ]
        for fragment in removed_fragments:
            assert fragment not in joined, f"legacy route should be removed: {fragment}"


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

    async def test_universal_media_presets_requires_token(self, client):
        resp = await client.get("/api/v1/admin/media/presets")
        assert resp.status_code == 401

    async def test_universal_media_reorder_requires_token(self, client):
        resp = await client.patch(
            "/api/v1/admin/media/reorder",
            json={
                "owner_type": "product",
                "owner_id": "00000000-0000-0000-0000-000000000000",
                "items": [],
            },
        )
        assert resp.status_code == 401

    async def test_webhook_missing_signature_rejected(self, client):
        resp = await client.post(
            "/api/v1/payments/webhook/razorpay", json={"event": "x"}
        )
        assert resp.status_code == 400


class TestSecurityHeaders:
    async def test_security_headers_present(self, client):
        resp = await client.get("/health/live")
        assert "x-request-id" in {k.lower() for k in resp.headers.keys()}
