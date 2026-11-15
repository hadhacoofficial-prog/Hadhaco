"""Google OIDC helpers (app/modules/auth/google_oauth.py)."""

from __future__ import annotations

import hashlib
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest

from app.core.config import settings
from app.core.exceptions import AuthenticationError, ServiceUnavailableError
from app.modules.auth import google_oauth as g

CLIENT_ID = "client-123.apps.googleusercontent.com"


@pytest.fixture(autouse=True)
def configured():
    with (
        patch.object(settings, "GOOGLE_CLIENT_ID", CLIENT_ID),
        patch.object(settings, "GOOGLE_CLIENT_SECRET", "secret"),
    ):
        yield


def _id_token(**overrides) -> str:
    claims = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "sub": "1098765",
        "email": "User@Example.com",
        "email_verified": True,
        "name": "Test User",
        "nonce": "nonce-1",
        "exp": int(time.time()) + 300,
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, "irrelevant-signature-not-checked", algorithm="HS256")


class TestSafeNextPath:
    @pytest.mark.parametrize("value", ["/", "/account", "/account/orders?tab=1"])
    def test_same_site_paths_allowed(self, value):
        assert g.safe_next_path(value) == value

    @pytest.mark.parametrize(
        "value",
        [
            None,
            "",
            "account",
            "//evil.example",
            "https://evil.example",
            "/\\evil.example",
            "/ok\nSet-Cookie: x=1",
        ],
    )
    def test_everything_else_falls_back_to_root(self, value):
        assert g.safe_next_path(value) == "/"


class TestAuthorizationUrl:
    async def test_url_carries_pkce_state_and_nonce_and_stores_record(self):
        redis = AsyncMock()
        url, binder = await g.build_authorization_url(
            redis, surface="admin", next_path="/admin/orders"
        )
        parts = urlsplit(url)
        q = {k: v[0] for k, v in parse_qs(parts.query).items()}
        assert f"{parts.scheme}://{parts.netloc}{parts.path}" == g.AUTH_URL
        assert q["client_id"] == CLIENT_ID
        assert q["code_challenge_method"] == "S256"
        assert q["response_type"] == "code" and "openid" in q["scope"]
        assert q["redirect_uri"].endswith("/auth/google/callback")
        key, payload = redis.set.await_args.args
        saved = json.loads(payload)
        assert key == g._state_key(q["state"])
        assert saved["nonce"] == q["nonce"]
        assert saved["surface"] == "admin" and saved["next"] == "/admin/orders"
        assert redis.set.await_args.kwargs["ex"] == g.STATE_TTL_SECONDS
        # The verifier itself is never sent to Google, only its challenge.
        assert saved["verifier"] not in url
        # The browser binder is never in the URL; only its hash is stored.
        assert binder not in url and binder not in payload
        assert saved["binder"] == hashlib.sha256(binder.encode()).hexdigest()

    async def test_open_redirect_target_is_neutralised(self):
        redis = AsyncMock()
        await g.build_authorization_url(
            redis, surface="store", next_path="//evil.example"
        )
        assert json.loads(redis.set.await_args.args[1])["next"] == "/"

    async def test_unconfigured_raises(self):
        with patch.object(settings, "GOOGLE_CLIENT_SECRET", ""):
            with pytest.raises(ServiceUnavailableError):
                await g.build_authorization_url(
                    AsyncMock(), surface="store", next_path="/"
                )

    async def test_redis_outage_surfaces_as_unavailable(self):
        redis = AsyncMock()
        redis.set.side_effect = ConnectionError("down")
        with pytest.raises(ServiceUnavailableError):
            await g.build_authorization_url(redis, surface="store", next_path="/")


class TestPopState:
    BINDER = "browser-binder"

    def _record(self, binder: str = BINDER) -> dict:
        return {
            "verifier": "v",
            "nonce": "n",
            "surface": "store",
            "next": "/x",
            "binder": hashlib.sha256(binder.encode()).hexdigest(),
        }

    async def test_returns_saved_state_for_the_same_browser(self):
        redis = AsyncMock()
        redis.getdel.return_value = json.dumps(self._record())
        state = await g.pop_state(redis, "state-token", self.BINDER)
        assert (state.verifier, state.nonce, state.next_path) == ("v", "n", "/x")
        redis.getdel.assert_awaited_once_with(g._state_key("state-token"))

    @pytest.mark.parametrize("binder", [None, "", "another-browser"])
    async def test_callback_from_a_different_browser_rejected(self, binder):
        redis = AsyncMock()
        redis.getdel.return_value = json.dumps(self._record())
        with pytest.raises(AuthenticationError) as exc:
            await g.pop_state(redis, "state-token", binder)
        assert exc.value.code == "GOOGLE_STATE_INVALID"

    async def test_unknown_or_replayed_state_rejected(self):
        redis = AsyncMock()
        redis.getdel.return_value = None
        with pytest.raises(AuthenticationError) as exc:
            await g.pop_state(redis, "replayed", self.BINDER)
        assert exc.value.code == "GOOGLE_STATE_INVALID"


class TestValidateIdToken:
    def test_valid_token_yields_claims(self):
        claims = g.validate_id_token(_id_token(), nonce="nonce-1")
        assert claims.subject == "1098765"
        assert claims.email == "User@Example.com"
        assert claims.email_verified is True and claims.name == "Test User"

    @pytest.mark.parametrize(
        "override",
        [
            {"iss": "https://evil.example"},
            {"aud": "someone-elses-client"},
            {"exp": int(time.time()) - 3600},
            {"nonce": "other"},
            {"nonce": None},
            {"sub": None},
            {"email": None},
        ],
    )
    def test_binding_claims_are_enforced(self, override):
        with pytest.raises(AuthenticationError) as exc:
            g.validate_id_token(_id_token(**override), nonce="nonce-1")
        assert exc.value.code == "GOOGLE_TOKEN_INVALID"

    def test_audience_list_containing_client_accepted(self):
        token = _id_token(aud=["other", CLIENT_ID])
        assert g.validate_id_token(token, nonce="nonce-1").subject == "1098765"

    def test_unverified_email_is_reported_not_hidden(self):
        token = _id_token(email_verified=False)
        assert g.validate_id_token(token, nonce="nonce-1").email_verified is False

    def test_garbage_rejected(self):
        with pytest.raises(AuthenticationError):
            g.validate_id_token("not-a-jwt", nonce="n")


class TestExchangeCode:
    async def test_non_200_from_google_is_an_auth_failure(self):
        resp = MagicMock(status_code=400)
        client = AsyncMock()
        client.__aenter__.return_value.post = AsyncMock(return_value=resp)
        state = g.GoogleState(verifier="v", nonce="n", surface="store", next_path="/")
        with patch(
            "app.modules.auth.google_oauth.httpx.AsyncClient", return_value=client
        ):
            with pytest.raises(AuthenticationError) as exc:
                await g.exchange_code("code", state)
        assert exc.value.code == "GOOGLE_EXCHANGE_FAILED"
