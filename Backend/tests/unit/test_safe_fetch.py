import pytest

from app.core import safe_fetch
from app.core.safe_fetch import UnsafeUrlError, validate_public_https_url


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/logo.png",
        "https://localhost/logo.png",
        "https://127.0.0.1/logo.png",
        "https://169.254.169.254/latest/meta-data/",
        "https://10.0.0.5/logo.png",
        "https://[::1]/logo.png",
        "https://[::ffff:127.0.0.1]/logo.png",
        "https://user:pw@example.com/logo.png",
        "https://example.com:8443/logo.png",
        "https://metadata.internal/logo.png",
        "file:///etc/passwd",
        "https:///nohost",
    ],
)
def test_validate_rejects_unsafe_urls(url):
    with pytest.raises(UnsafeUrlError):
        validate_public_https_url(url)


def test_validate_accepts_public_https():
    assert (
        validate_public_https_url(" https://cdn.example.com/logo.png ")
        == "https://cdn.example.com/logo.png"
    )


def test_fetch_rejects_host_resolving_to_private_address(monkeypatch):
    monkeypatch.setattr(
        safe_fetch.socket,
        "getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("10.1.2.3", 443))],
    )
    with pytest.raises(UnsafeUrlError):
        safe_fetch.fetch_public_image("https://evil.example.com/logo.png")


def test_fetch_rejects_if_any_resolved_address_is_private(monkeypatch):
    monkeypatch.setattr(
        safe_fetch.socket,
        "getaddrinfo",
        lambda *a, **k: [
            (2, 1, 6, "", ("93.184.216.34", 443)),
            (2, 1, 6, "", ("127.0.0.1", 443)),
        ],
    )
    with pytest.raises(UnsafeUrlError):
        safe_fetch.fetch_public_image("https://rebind.example.com/logo.png")


def test_company_update_rejects_internal_logo_url():
    from pydantic import ValidationError

    from app.modules.company.schemas import CompanyConfigUpdate

    with pytest.raises(ValidationError):
        CompanyConfigUpdate(shipping_label_logo_url="https://169.254.169.254/x")
    CompanyConfigUpdate(packing_slip_logo_url="https://cdn.example.com/x.png")
    CompanyConfigUpdate(logo_url="/relative/logo.png")
