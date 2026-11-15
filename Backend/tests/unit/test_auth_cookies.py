"""Cookie naming, surface detection and CSRF enforcement (app/core/auth_cookies.py)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, Response
from starlette.datastructures import Headers

from app.core import auth_cookies as ac
from app.core.config import settings
from app.core.security import make_csrf_token

_SESSION = "22222222-2222-2222-2222-222222222222"


def _request(headers: dict[str, str], method: str = "POST", cookies=None) -> MagicMock:
    request = MagicMock()
    request.headers = Headers(headers)
    request.method = method
    request.cookies = cookies or {}
    return request


class TestSurface:
    def test_admin_origin_is_admin_surface(self):
        origin = settings.ADMIN_URL.rstrip("/")
        assert ac.surface_for_request(_request({"Origin": origin})) == "admin"

    def test_storefront_origin_is_store_surface(self):
        origin = settings.FRONTEND_URL.rstrip("/")
        assert ac.surface_for_request(_request({"Origin": origin})) == "store"

    def test_no_origin_defaults_to_store(self):
        assert ac.surface_for_request(_request({})) == "store"

    def test_referer_is_used_when_origin_absent(self):
        referer = settings.ADMIN_URL.rstrip("/") + "/admin/login"
        assert ac.surface_for_request(_request({"Referer": referer})) == "admin"

    def test_null_origin_is_ignored(self):
        assert ac.request_origin(_request({"Origin": "null"})) is None


class TestCookieNames:
    def test_development_names_are_unprefixed(self):
        assert ac.access_cookie_name("store") == "hadha_at"
        assert ac.refresh_cookie_name("admin") == "hadha_admin_rt"

    def test_surfaces_never_share_cookie_names(self):
        assert ac.access_cookie_name("store") != ac.access_cookie_name("admin")
        assert ac.refresh_cookie_name("store") != ac.refresh_cookie_name("admin")

    def test_production_uses_host_and_secure_prefixes(self):
        with patch.object(settings, "APP_ENV", "production"):
            assert ac.access_cookie_name("store") == "__Host-hadha_at"
            assert ac.refresh_cookie_name("store") == "__Secure-hadha_rt"

    def test_cookie_domain_disables_host_prefix(self):
        with (
            patch.object(settings, "APP_ENV", "production"),
            patch.object(settings, "AUTH_COOKIE_DOMAIN", ".hadha.co"),
        ):
            assert ac.access_cookie_name("store") == "__Secure-hadha_at"


class TestSetAndClear:
    def _cookies(self, response: Response) -> list[str]:
        return response.headers.getlist("set-cookie")

    def test_cookies_are_httponly_with_expected_scope(self):
        response = Response()
        ac.set_auth_cookies(
            response,
            "store",
            access_token="AT",
            access_ttl=900,
            refresh_token="RT",
            refresh_ttl=3600,
        )
        access, refresh = self._cookies(response)
        assert access.startswith("hadha_at=AT") and "HttpOnly" in access
        assert "Path=/;" in access + ";" and "SameSite=lax" in access
        assert "Max-Age=900" in access
        assert refresh.startswith("hadha_rt=RT") and "HttpOnly" in refresh
        assert "Path=/api/v1/auth" in refresh and "SameSite=strict" in refresh

    def test_secure_flag_set_in_production(self):
        response = Response()
        with patch.object(settings, "APP_ENV", "production"):
            ac.set_auth_cookies(
                response,
                "store",
                access_token="AT",
                access_ttl=1,
                refresh_token=None,
                refresh_ttl=1,
            )
        (access,) = self._cookies(response)
        assert "Secure" in access and access.startswith("__Host-hadha_at=")

    def test_refresh_cookie_untouched_when_no_new_token(self):
        response = Response()
        ac.set_auth_cookies(
            response,
            "store",
            access_token="AT",
            access_ttl=900,
            refresh_token=None,
            refresh_ttl=0,
        )
        assert len(self._cookies(response)) == 1

    def test_clear_expires_both_cookies(self):
        response = Response()
        ac.clear_auth_cookies(response, "admin")
        cleared = self._cookies(response)
        assert len(cleared) == 2
        assert all("Max-Age=0" in c for c in cleared)


class TestCsrf:
    ORIGIN = "http://localhost:3000"

    def test_safe_methods_skip_checks(self):
        ac.enforce_csrf(_request({}, method="GET"), _SESSION)

    def test_valid_origin_and_token_pass(self):
        request = _request(
            {"Origin": self.ORIGIN, "X-CSRF-Token": make_csrf_token(_SESSION)}
        )
        ac.enforce_csrf(request, _SESSION)

    def test_missing_origin_rejected(self):
        request = _request({"X-CSRF-Token": make_csrf_token(_SESSION)})
        with pytest.raises(HTTPException) as exc:
            ac.enforce_csrf(request, _SESSION)
        assert exc.value.status_code == 403
        assert exc.value.headers["X-Error-Code"] == "CSRF_FAILED"

    def test_foreign_origin_rejected(self):
        request = _request(
            {
                "Origin": "https://evil.example",
                "X-CSRF-Token": make_csrf_token(_SESSION),
            }
        )
        with pytest.raises(HTTPException) as exc:
            ac.enforce_csrf(request, _SESSION)
        assert exc.value.status_code == 403

    @pytest.mark.parametrize("token", [None, "", "wrong"])
    def test_missing_or_wrong_token_rejected(self, token):
        headers = {"Origin": self.ORIGIN}
        if token is not None:
            headers["X-CSRF-Token"] = token
        with pytest.raises(HTTPException) as exc:
            ac.enforce_csrf(_request(headers), _SESSION)
        assert exc.value.status_code == 403

    def test_token_from_another_session_rejected(self):
        request = _request(
            {"Origin": self.ORIGIN, "X-CSRF-Token": make_csrf_token("someone-else")}
        )
        with pytest.raises(HTTPException):
            ac.enforce_csrf(request, _SESSION)
