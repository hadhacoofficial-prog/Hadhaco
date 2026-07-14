"""Integration tests for the company config API router.

Covers /api/v1/admin/company (GET and PATCH).
No real DB or auth service required — dependency overrides replace both.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest_asyncio

# ─── Mock company helper ──────────────────────────────────────────────────────


def _make_company_mock(**overrides):
    c = MagicMock()
    c.name = "Hadha Jewellery"
    c.tagline = "Timeless Beauty, Trusted Quality"
    c.gstin = None
    c.city = "Hyderabad"
    c.state = "Telangana"
    c.postal_code = "500033"
    c.country = "IN"
    c.phone = "+91 98765 43210"
    c.support_email = "info@hadha.com"
    c.website = "www.hadha.com"
    c.logo_url = None
    c.packing_slip_logo_url = None
    c.shipping_label_logo_url = None
    c.instagram_url = None
    c.facebook_url = None
    for k, v in overrides.items():
        setattr(c, k, v)
    return c


# ─── Dependency overrides ─────────────────────────────────────────────────────


async def _mock_admin():
    return {"sub": str(uuid.uuid4()), "role": "admin"}


async def _mock_db():
    db = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    yield db


# ─── admin_client fixture ─────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def admin_client(app, client):
    """Yield the shared client with admin dependency overrides active."""
    from app.core.database import get_db
    from app.core.dependencies import require_2fa_verified, require_admin

    app.dependency_overrides[require_admin] = _mock_admin
    # PATCH /admin/company sits behind require_2fa_verified, which itself
    # depends on require_admin and calls AuthService().has_active_2fa(db,
    # current_user.id) — real DB call the mocked db/current_user dict can't
    # satisfy. Override it directly so these tests exercise the company
    # config logic, not the 2FA gate (covered separately by auth tests).
    app.dependency_overrides[require_2fa_verified] = _mock_admin
    app.dependency_overrides[get_db] = _mock_db
    yield client
    app.dependency_overrides.clear()


# ─── Auth guard tests ─────────────────────────────────────────────────────────


class TestCompanyConfigAuthGuards:
    async def test_get_without_token_returns_401(self, client):
        resp = await client.get("/api/v1/admin/company")
        assert resp.status_code == 401

    async def test_patch_without_token_returns_401(self, client):
        resp = await client.patch("/api/v1/admin/company", json={"name": "X"})
        assert resp.status_code == 401

    async def test_get_with_invalid_bearer_returns_401(self, client):
        resp = await client.get(
            "/api/v1/admin/company",
            headers={"Authorization": "Bearer invalid"},
        )
        assert resp.status_code == 401


# ─── GET tests ────────────────────────────────────────────────────────────────


class TestCompanyConfigGet:
    async def test_get_returns_200_with_company_data(self, admin_client):
        mock_config = _make_company_mock(name="Hadha Gold")
        with patch(
            "app.modules.company.router._repo.get",
            new=AsyncMock(return_value=mock_config),
        ):
            resp = await admin_client.get("/api/v1/admin/company")

        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["name"] == "Hadha Gold"
        assert data["code"] == "COMPANY_CONFIG_RETRIEVED"

    async def test_get_creates_default_config_when_none_exists(self, admin_client):
        default_config = _make_company_mock()
        with (
            patch(
                "app.modules.company.router._repo.get",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.modules.company.router._repo.update",
                new=AsyncMock(return_value=default_config),
            ) as mock_update,
        ):
            resp = await admin_client.get("/api/v1/admin/company")

        assert resp.status_code == 200
        mock_update.assert_awaited_once()
        call_args = mock_update.call_args
        # second positional arg is the payload dict — must be empty
        assert call_args[0][1] == {}

    async def test_get_response_envelope_structure(self, admin_client):
        mock_config = _make_company_mock()
        with patch(
            "app.modules.company.router._repo.get",
            new=AsyncMock(return_value=mock_config),
        ):
            resp = await admin_client.get("/api/v1/admin/company")

        data = resp.json()
        assert data["success"] is True
        assert "data" in data
        assert "code" in data
        assert "message" in data


# ─── PATCH tests ──────────────────────────────────────────────────────────────


class TestCompanyConfigPatch:
    async def test_patch_with_valid_payload_returns_200(self, admin_client):
        updated = _make_company_mock(name="Updated Name", phone="+91 99999 99999")
        with patch(
            "app.modules.company.router._repo.update",
            new=AsyncMock(return_value=updated),
        ):
            resp = await admin_client.patch(
                "/api/v1/admin/company",
                json={"name": "Updated Name", "phone": "+91 99999 99999"},
            )

        assert resp.status_code == 200
        assert resp.json()["code"] == "COMPANY_CONFIG_UPDATED"

    async def test_patch_with_empty_body_returns_200(self, admin_client):
        unchanged = _make_company_mock()
        with patch(
            "app.modules.company.router._repo.update",
            new=AsyncMock(return_value=unchanged),
        ):
            resp = await admin_client.patch("/api/v1/admin/company", json={})

        assert resp.status_code == 200

    async def test_patch_filters_null_values_from_payload(self, admin_client):
        updated = _make_company_mock(name="Test")
        captured: list = []

        async def _capture_update(db, payload):
            captured.append(payload)
            return updated

        with patch("app.modules.company.router._repo.update", new=_capture_update):
            resp = await admin_client.patch(
                "/api/v1/admin/company",
                json={"name": "Test", "phone": None},
            )

        assert resp.status_code == 200
        assert len(captured) == 1
        assert "phone" not in captured[0], "null values must be filtered out"
        assert captured[0].get("name") == "Test"

    async def test_patch_with_invalid_json_returns_422(self, admin_client):
        resp = await admin_client.patch(
            "/api/v1/admin/company",
            content=b"not-json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422

    async def test_patch_rejects_full_country_name_with_422(self, admin_client):
        """Regression test: a full country name (e.g. "India" instead of the
        2-char ISO code "IN") must be rejected by request validation before
        it ever reaches the DB. The `country` column is varchar(2); letting
        an oversized value through crashed the single UPDATE statement that
        also writes city/state/postal_code, silently discarding those too.
        """
        with patch(
            "app.modules.company.router._repo.update",
            new=AsyncMock(side_effect=AssertionError("must not reach the repository")),
        ):
            resp = await admin_client.patch(
                "/api/v1/admin/company",
                json={"city": "Hyderabad", "state": "Telangana", "country": "India"},
            )

        assert resp.status_code == 422

    async def test_patch_normalizes_lowercase_country_to_uppercase(self, admin_client):
        updated = _make_company_mock(country="IN")
        captured: list = []

        async def _capture_update(db, payload):
            captured.append(payload)
            return updated

        with patch("app.modules.company.router._repo.update", new=_capture_update):
            resp = await admin_client.patch(
                "/api/v1/admin/company",
                json={"country": "in"},
            )

        assert resp.status_code == 200
        assert captured[0]["country"] == "IN"


# ─── OpenAPI schema tests ─────────────────────────────────────────────────────


class TestCompanyConfigInOpenAPI:
    async def test_get_route_exists_in_openapi(self, app):
        schema = app.openapi()
        assert "/api/v1/admin/company" in schema["paths"]

    async def test_patch_route_exists_in_openapi(self, app):
        schema = app.openapi()
        path = schema["paths"].get("/api/v1/admin/company", {})
        assert "patch" in path
