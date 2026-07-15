"""Comprehensive API integration tests — no DB/Redis required.

Strategy: Only test endpoints that respond before hitting the DB layer:
  - Auth-guarded endpoints → 401 without a token (dependency rejects immediately)
  - Pydantic/FastAPI validation → 422 for malformed params (before handlers run)
  - Health/status endpoints → no DB needed
  - Webhook signature checks → rejected before DB
"""


class TestAuthRequiredEndpoints:
    """All protected endpoints must return 401 when no token is provided."""

    async def test_me_requires_auth(self, client):
        assert (await client.get("/api/v1/me")).status_code == 401

    async def test_me_avatar_requires_auth(self, client):
        assert (await client.patch("/api/v1/me/avatar")).status_code in (401, 422)

    async def test_wishlist_get_requires_auth(self, client):
        assert (await client.get("/api/v1/me/wishlist")).status_code == 401

    async def test_wishlist_add_requires_auth(self, client):
        r = await client.post("/api/v1/me/wishlist", json={})
        assert r.status_code == 401

    async def test_wishlist_toggle_requires_auth(self, client):
        r = await client.post("/api/v1/me/wishlist/toggle", json={})
        assert r.status_code == 401

    async def test_orders_list_requires_auth(self, client):
        assert (await client.get("/api/v1/orders")).status_code == 401

    async def test_order_create_requires_auth(self, client):
        assert (
            await client.post("/api/v1/orders/create-payment", json={})
        ).status_code == 401

    async def test_coupon_validate_requires_auth(self, client):
        r = await client.post(
            "/api/v1/coupons/validate", json={"code": "X", "order_subtotal": 500}
        )
        assert r.status_code == 401

    async def test_get_order_payment_requires_auth(self, client):
        r = await client.get(
            "/api/v1/orders/00000000-0000-0000-0000-000000000000/payment"
        )
        assert r.status_code == 401

    async def test_initiate_refund_requires_auth(self, client):
        r = await client.post(
            "/api/v1/admin/orders/00000000-0000-0000-0000-000000000000/refund",
            json={},
        )
        assert r.status_code == 401

    async def test_submit_review_requires_auth(self, client):
        r = await client.post("/api/v1/reviews", json={})
        assert r.status_code == 401

    async def test_support_ticket_requires_auth(self, client):
        r = await client.post("/api/v1/support/tickets", json={})
        assert r.status_code == 401

    async def test_returns_requires_auth(self, client):
        r = await client.post("/api/v1/returns", json={})
        assert r.status_code == 401

    async def test_logout_requires_auth(self, client):
        r = await client.post("/api/v1/auth/logout")
        assert r.status_code == 401

    async def test_verify_token_requires_auth(self, client):
        r = await client.post("/api/v1/auth/verify-token")
        assert r.status_code == 401

    async def test_cart_merge_requires_auth(self, client):
        r = await client.post("/api/v1/cart/merge")
        assert r.status_code == 401

    async def test_addresses_requires_auth(self, client):
        r = await client.get("/api/v1/me/addresses")
        assert r.status_code == 401


class TestAdminRequiredEndpoints:
    """Admin endpoints must return 401 without a token."""

    async def test_admin_dashboard_requires_auth(self, client):
        assert (await client.get("/api/v1/admin/dashboard")).status_code == 401

    async def test_admin_products_requires_auth(self, client):
        assert (await client.get("/api/v1/admin/products")).status_code == 401

    async def test_admin_product_create_requires_auth(self, client):
        assert (await client.post("/api/v1/admin/products", json={})).status_code == 401

    async def test_admin_orders_requires_auth(self, client):
        assert (await client.get("/api/v1/admin/orders")).status_code == 401

    async def test_admin_users_requires_auth(self, client):
        assert (await client.get("/api/v1/admin/users")).status_code == 401

    async def test_admin_coupons_list_requires_auth(self, client):
        assert (await client.get("/api/v1/admin/coupons")).status_code == 401

    async def test_admin_coupons_create_requires_auth(self, client):
        assert (await client.post("/api/v1/admin/coupons", json={})).status_code == 401

    async def test_admin_inventory_low_stock_requires_auth(self, client):
        assert (
            await client.get("/api/v1/admin/inventory/low-stock")
        ).status_code == 401

    async def test_admin_reviews_pending_requires_auth(self, client):
        assert (await client.get("/api/v1/reviews/admin/pending")).status_code == 401

    async def test_admin_cms_banners_requires_auth(self, client):
        assert (await client.get("/api/v1/cms/admin/banners")).status_code == 401

    async def test_admin_cms_banners_create_requires_auth(self, client):
        assert (
            await client.post("/api/v1/cms/admin/banners", json={})
        ).status_code == 401

    async def test_admin_analytics_dashboard_requires_auth(self, client):
        assert (
            await client.get("/api/v1/analytics/admin/dashboard")
        ).status_code == 401

    async def test_admin_audit_logs_requires_auth(self, client):
        assert (await client.get("/api/v1/admin/audit-logs")).status_code == 401

    async def test_admin_categories_create_requires_auth(self, client):
        assert (
            await client.post("/api/v1/admin/categories", json={})
        ).status_code == 401

    async def test_admin_support_tickets_requires_auth(self, client):
        assert (await client.get("/api/v1/support/admin/tickets")).status_code == 401

    async def test_admin_returns_requires_auth(self, client):
        assert (await client.get("/api/v1/returns/admin/returns")).status_code == 401

    async def test_admin_notifications_logs_requires_auth(self, client):
        assert (await client.get("/api/v1/notifications/admin/logs")).status_code == 401

    async def test_setup_2fa_requires_admin(self, client):
        assert (await client.post("/api/v1/auth/admin/2fa/setup")).status_code == 401

    async def test_validate_2fa_requires_admin(self, client):
        assert (
            await client.post("/api/v1/auth/admin/2fa/validate", json={})
        ).status_code == 401


class TestQueryParamValidation:
    """FastAPI/Pydantic rejects invalid query params before the handler runs."""

    async def test_search_requires_q_param(self, client):
        resp = await client.get("/api/v1/search")
        assert resp.status_code == 422

    async def test_search_empty_q_rejected(self, client):
        resp = await client.get("/api/v1/search?q=")
        assert resp.status_code == 422

    async def test_search_autocomplete_min_length_two(self, client):
        resp = await client.get("/api/v1/search/autocomplete?q=r")
        assert resp.status_code == 422

    async def test_products_page_zero_rejected(self, client):
        resp = await client.get("/api/v1/products?page=0")
        assert resp.status_code == 422

    async def test_products_page_size_over_max(self, client):
        resp = await client.get("/api/v1/products?page_size=101")
        assert resp.status_code == 422

    async def test_shipping_rates_short_pincode(self, client):
        resp = await client.get("/api/v1/shipping/rates?pincode=12345")
        assert resp.status_code == 422

    async def test_shipping_rates_missing_pincode(self, client):
        resp = await client.get("/api/v1/shipping/rates")
        assert resp.status_code == 422

    async def test_shipping_rates_zero_weight(self, client):
        resp = await client.get("/api/v1/shipping/rates?weight_grams=0&pincode=400001")
        assert resp.status_code == 422

    async def test_orders_page_size_over_limit(self, client):
        # Protected, but FastAPI may still validate before auth in some versions
        # This tests that the endpoint exists (not 404)
        resp = await client.get("/api/v1/orders?page_size=51")
        # May be 401 (auth first) or 422 — either is fine, never 404
        assert resp.status_code != 404

    async def test_sort_dir_invalid_value(self, client):
        resp = await client.get("/api/v1/products?sort_dir=sideways")
        assert resp.status_code == 422


class TestWebhookEndpoints:
    """Webhook endpoints reject missing/invalid signatures before processing."""

    async def test_razorpay_webhook_missing_signature_returns_400(self, client):
        resp = await client.post(
            "/api/v1/payments/webhook/razorpay", json={"event": "payment.captured"}
        )
        assert resp.status_code == 400


class TestHealthEndpoints:
    async def test_liveness_returns_200(self, client):
        resp = await client.get("/health/live")
        assert resp.status_code == 200
        assert resp.json() == {"status": "alive"}

    async def test_root_returns_app_info(self, client):
        resp = await client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert "name" in data or "version" in data

    async def test_readiness_returns_valid_json(self, client):
        resp = await client.get("/health/ready")
        assert resp.status_code in (200, 503)
        body = resp.json()
        assert "status" in body
        assert "checks" in body

    async def test_readiness_reports_db_check(self, client):
        resp = await client.get("/health/ready")
        body = resp.json()
        assert "db" in body["checks"]

    async def test_readiness_reports_redis_check(self, client):
        resp = await client.get("/health/ready")
        body = resp.json()
        assert "redis" in body["checks"]


class TestOpenAPISchema:
    async def test_schema_includes_core_routes(self, app):
        schema = app.openapi()
        paths = " ".join(schema["paths"].keys())
        for fragment in [
            "/api/v1/products",
            "/api/v1/cart",
            "/api/v1/orders",
            "/api/v1/admin/orders/{order_id}/refund",
            "/api/v1/admin/dashboard",
        ]:
            assert fragment in paths, f"missing route: {fragment}"

    async def test_schema_has_auth_security_scheme(self, app):
        schema = app.openapi()
        components = schema.get("components", {})
        security_schemes = components.get("securitySchemes", {})
        # FastAPI's OAuth2PasswordBearer registers a security scheme
        assert len(security_schemes) > 0

    async def test_schema_includes_review_routes(self, app):
        schema = app.openapi()
        paths = " ".join(schema["paths"].keys())
        assert "/api/v1/reviews" in paths

    async def test_schema_includes_cms_routes(self, app):
        schema = app.openapi()
        paths = " ".join(schema["paths"].keys())
        assert "/api/v1/cms" in paths

    async def test_schema_includes_analytics_routes(self, app):
        schema = app.openapi()
        paths = " ".join(schema["paths"].keys())
        assert "/api/v1/analytics" in paths
