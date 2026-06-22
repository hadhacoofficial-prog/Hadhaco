"""
JWKS cache — downloads Supabase public keys once per TTL, caches them in
memory, and refreshes automatically on expiry or unknown key ID.

Never hits the network more than once per TTL window, even under concurrent
requests, thanks to a single asyncio.Lock that serialises refreshes.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
from jwt.algorithms import ECAlgorithm

from app.core.config import settings


class JWKSCache:
    """
    Async-safe, in-memory cache for Supabase JWKS EC public keys.

    Lifecycle:
    - First call: fetch JWKS from Supabase and cache all keys.
    - Subsequent calls within TTL: return cached key.
    - After TTL expires: refresh on next call.
    - Unknown kid: refresh once immediately, then raise if still missing
      (handles key rotation where Supabase issues a new signing key).
    """

    def __init__(self, ttl: int | None = None) -> None:
        self._ttl: int = ttl if ttl is not None else settings.JWKS_CACHE_TTL
        self._keys: dict[str, Any] = {}  # kid → ECAlgorithm public key object
        self._fetched_at: float = 0.0
        self._lock: asyncio.Lock = asyncio.Lock()

    async def get_key(self, kid: str) -> Any:
        """Return the EC public key for *kid*, refreshing the cache if needed."""
        async with self._lock:
            if self._is_stale():
                await self._refresh()
            if kid not in self._keys:
                # Key not found — Supabase may have rotated. Refresh once more.
                await self._refresh()

        if kid not in self._keys:
            raise ValueError(f"JWKS: unknown key id '{kid}'")
        return self._keys[kid]

    def _is_stale(self) -> bool:
        return (time.monotonic() - self._fetched_at) >= self._ttl

    async def _refresh(self) -> None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(settings.supabase_jwks_url)
            response.raise_for_status()
            data = response.json()

        keys: dict[str, Any] = {}
        for jwk in data.get("keys", []):
            kid = jwk.get("kid")
            if kid:
                keys[kid] = ECAlgorithm.from_jwk(jwk)

        self._keys = keys
        self._fetched_at = time.monotonic()


# Process-lifetime singleton — one cache per uvicorn worker
_cache = JWKSCache()


async def get_public_key(kid: str) -> Any:
    """Return the EC public key for *kid* from the JWKS cache."""
    return await _cache.get_key(kid)
