"""Shared Pydantic field validators/type aliases."""

from __future__ import annotations

import ipaddress
from typing import Annotated

from pydantic import BeforeValidator


def _coerce_ip_to_str(value: object) -> object:
    """
    asyncpg decodes Postgres INET columns as ipaddress.IPv4Address/
    IPv6Address, not str. A schema field typed plain `str` validates fine
    while the column is NULL (never exercised) and crashes the moment real
    data is queried. Coerce before Pydantic's str check runs.
    """
    if isinstance(value, ipaddress.IPv4Address | ipaddress.IPv6Address):
        return str(value)
    return value


IpAddressStr = Annotated[str, BeforeValidator(_coerce_ip_to_str)]
