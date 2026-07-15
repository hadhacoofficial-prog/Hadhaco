"""Tests for the reverse-proxy-aware client IP extraction.

Covers the specific gap this was written to close: forwarding headers
(X-Real-IP / X-Forwarded-For) must only be trusted when the request's
direct TCP peer is itself a recognized reverse proxy. Otherwise an
attacker who can reach the API directly can spoof their own rate-limit
key, audit-log IP, and new-device/location detection.
"""

from unittest.mock import MagicMock, patch

from app.middleware.rate_limit import _is_trusted_proxy_peer, get_client_ip


def _mock_request(peer_ip: str | None, headers: dict[str, str]) -> MagicMock:
    request = MagicMock()
    request.client = MagicMock(host=peer_ip) if peer_ip is not None else None
    request.headers = headers
    return request


class TestIsTrustedProxyPeer:
    def test_private_range_is_trusted(self):
        assert _is_trusted_proxy_peer("172.20.0.1") is True  # Docker bridge

    def test_loopback_is_trusted(self):
        assert _is_trusted_proxy_peer("127.0.0.1") is True

    def test_public_ip_is_not_trusted_by_default(self):
        assert _is_trusted_proxy_peer("8.8.8.8") is False

    def test_explicitly_configured_ip_is_trusted(self):
        with patch("app.middleware.rate_limit.settings.TRUSTED_PROXY_IPS", "8.8.8.8"):
            assert _is_trusted_proxy_peer("8.8.8.8") is True

    def test_malformed_ip_is_not_trusted(self):
        assert _is_trusted_proxy_peer("not-an-ip") is False


class TestGetClientIp:
    def test_untrusted_peer_headers_are_ignored(self):
        """An attacker connecting directly (not via the reverse proxy) who
        sets X-Real-IP themselves must not have it trusted — otherwise they
        can spoof their own rate-limit key and audit-log IP."""
        request = _mock_request("8.8.8.8", {"X-Real-IP": "1.1.1.1"})
        assert get_client_ip(request) == "8.8.8.8"

    def test_trusted_peer_x_real_ip_is_honored(self):
        request = _mock_request("172.20.0.1", {"X-Real-IP": "8.8.8.8"})
        assert get_client_ip(request) == "8.8.8.8"

    def test_trusted_peer_x_forwarded_for_takes_last_entry(self):
        request = _mock_request(
            "172.20.0.1", {"X-Forwarded-For": "8.8.8.8, 172.20.0.5"}
        )
        assert get_client_ip(request) == "172.20.0.5"

    def test_no_headers_falls_back_to_peer(self):
        request = _mock_request("172.20.0.1", {})
        assert get_client_ip(request) == "172.20.0.1"

    def test_no_client_returns_unknown(self):
        request = _mock_request(None, {})
        assert get_client_ip(request) == "unknown"
