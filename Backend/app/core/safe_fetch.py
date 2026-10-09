"""SSRF-safe outbound fetch for admin/customer-influenced URLs.

Any URL a user can influence (logo URLs, remote images, ...) must go through
``fetch_public_image`` / ``validate_public_https_url`` instead of calling
httpx directly. Guarantees:

* https only, no embedded credentials, default port only;
* every address the host resolves to must be globally routable (rejects
  loopback, RFC1918, link-local/cloud-metadata, CGNAT, multicast, reserved);
* the connection is pinned to the validated IP (TLS SNI/Host keep the
  original hostname) so DNS cannot change between check and use;
* redirects are never followed;
* the response must be a raster image and is size-capped while streaming.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

import httpx

ALLOWED_IMAGE_TYPES = frozenset({"image/png", "image/jpeg", "image/webp", "image/gif"})
MAX_IMAGE_BYTES = 2 * 1024 * 1024
_TIMEOUT = httpx.Timeout(5.0, connect=3.0)


class UnsafeUrlError(ValueError):
    """The URL is not allowed to be fetched server-side."""


def _is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def validate_public_https_url(url: str) -> str:
    """Static (no DNS) validation, suitable for write-time schema checks."""
    parts = urlsplit(url.strip())
    if parts.scheme != "https":
        raise UnsafeUrlError("URL must use https")
    if not parts.hostname:
        raise UnsafeUrlError("URL must include a host")
    if parts.username or parts.password:
        raise UnsafeUrlError("URL must not contain credentials")
    if parts.port not in (None, 443):
        raise UnsafeUrlError("URL must use the default https port")
    try:
        literal = ipaddress.ip_address(parts.hostname)
    except ValueError:
        host = parts.hostname.lower()
        if host in {"localhost"} or host.endswith(
            (".localhost", ".local", ".internal", ".lan", ".home.arpa")
        ):
            raise UnsafeUrlError("URL host is not publicly routable") from None
    else:
        if not _is_public(literal):
            raise UnsafeUrlError("URL host is not publicly routable")
    return url.strip()


def _resolve_public_ip(host: str) -> str:
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeUrlError("URL host could not be resolved") from exc
    addrs = [ipaddress.ip_address(info[4][0]) for info in infos]
    if not addrs or not all(_is_public(a) for a in addrs):
        raise UnsafeUrlError("URL host resolves to a non-public address")
    return str(addrs[0])


def fetch_public_image(url: str) -> tuple[bytes, str]:
    """Fetch a public https image; returns (body, content_type) or raises."""
    validate_public_https_url(url)
    parts = urlsplit(url.strip())
    host = parts.hostname or ""
    ip = _resolve_public_ip(host)
    ip_host = f"[{ip}]" if ":" in ip else ip
    target = parts._replace(netloc=ip_host).geturl()
    with httpx.Client(timeout=_TIMEOUT, follow_redirects=False) as client:
        with client.stream(
            "GET",
            target,
            headers={"Host": host, "Accept": "image/png,image/jpeg,image/webp"},
            extensions={"sni_hostname": host},
        ) as resp:
            if resp.status_code != 200:
                raise UnsafeUrlError("unexpected response status")
            ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
            if ctype not in ALLOWED_IMAGE_TYPES:
                raise UnsafeUrlError("response is not a supported raster image")
            declared = resp.headers.get("content-length")
            if declared and declared.isdigit() and int(declared) > MAX_IMAGE_BYTES:
                raise UnsafeUrlError("image too large")
            body = bytearray()
            for chunk in resp.iter_bytes():
                body.extend(chunk)
                if len(body) > MAX_IMAGE_BYTES:
                    raise UnsafeUrlError("image too large")
    return bytes(body), ctype
