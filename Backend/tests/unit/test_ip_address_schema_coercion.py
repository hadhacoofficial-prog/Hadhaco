"""
asyncpg decodes Postgres INET columns as ipaddress.IPv4Address/IPv6Address,
not str. A Pydantic schema field typed plain `str` validates fine while the
column is NULL (never exercised in a quick smoke test) and crashes with a
validation error the moment a row with real IP data is actually read back —
this happened in production on GET /admin/audit-logs. IpAddressStr coerces
before the str check runs.
"""

import ipaddress

from pydantic import BaseModel

from app.common.validators import IpAddressStr
from app.modules.audit.schemas import AuditLogEntry


class _Model(BaseModel):
    ip: IpAddressStr | None


def test_ipv4_address_object_coerced_to_str():
    result = _Model(ip=ipaddress.IPv4Address("172.20.0.1"))
    assert result.ip == "172.20.0.1"
    assert isinstance(result.ip, str)


def test_ipv6_address_object_coerced_to_str():
    result = _Model(ip=ipaddress.IPv6Address("::1"))
    assert result.ip == "::1"


def test_plain_string_passes_through_unchanged():
    result = _Model(ip="10.0.0.5")
    assert result.ip == "10.0.0.5"


def test_none_passes_through():
    result = _Model(ip=None)
    assert result.ip is None


def test_audit_log_entry_survives_ipv4address_from_db():
    """Reproduces the exact production crash: AuditLogEntry.model_validate
    against an ORM-like object whose ip_address is an IPv4Address, as
    asyncpg actually returns for an INET column."""

    class _FakeRow:
        id = "00000000-0000-0000-0000-000000000000"
        actor_id = None
        actor_email = None
        actor_role = None
        action = "admin_login"
        resource_type = "profile"
        resource_id = None
        old_value = None
        new_value = None
        meta = None
        ip_address = ipaddress.IPv4Address("172.20.0.1")
        user_agent = "Mozilla/5.0"
        request_id = None
        source = "api"
        created_at = "2026-07-15T00:00:00Z"

    entry = AuditLogEntry.model_validate(_FakeRow())
    assert entry.ip_address == "172.20.0.1"
