"""
Supabase Python client — thin wrapper around the official `supabase` SDK.

Usage:
    from app.core.supabase_client import get_supabase_client, get_supabase_admin_client

`get_supabase_client()` uses the publishable/anon key (SUPABASE_KEY).
`get_supabase_admin_client()` uses the service-role key (bypasses RLS).

Both return a synchronous Supabase client; for async FastAPI code wrap calls
with `asyncio.to_thread()` or use the underlying httpx session directly.
"""
from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from app.core.config import settings


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """Anon/publishable client — respects RLS policies."""
    return create_client(settings.SUPABASE_URL, settings.supabase_anon_key)


@lru_cache(maxsize=1)
def get_supabase_admin_client() -> Client:
    """Service-role client — bypasses RLS. Use only for server-side admin operations."""
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
