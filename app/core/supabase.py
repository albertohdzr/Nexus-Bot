from functools import lru_cache
from typing import Any, Optional

from fastapi import HTTPException
from supabase import Client, create_client

from app.core.config import settings


from httpx import Timeout

@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """Singleton — creates the Supabase client once and reuses it."""
    if not settings.supabase_url:
        raise HTTPException(status_code=500, detail="SUPABASE_URL is not configured")
    if not settings.supabase_service_key:
        raise HTTPException(status_code=500, detail="SUPABASE_SERVICE_ROLE_KEY is not configured")

    from supabase.lib.client_options import SyncClientOptions
    from postgrest import SyncPostgrestClient

    opts = SyncClientOptions(
        postgrest_client_timeout=30,
    )
    client = create_client(settings.supabase_url, settings.supabase_service_key, options=opts)

    # Set explicit timeouts on the underlying httpx client to avoid
    # hanging on stale keep-alive connections (common with local Kong proxy).
    timeout = Timeout(10.0, connect=5.0, read=30.0, write=10.0)
    if hasattr(client, 'postgrest') and hasattr(client.postgrest, 'session'):
        client.postgrest.session.timeout = timeout

    return client


def get_supabase_error(response: Any) -> Optional[object]:
    if isinstance(response, dict):
        return response.get("error")
    if hasattr(response, "error"):
        return response.error
    return None


def get_supabase_data(response: Any) -> Any:
    if isinstance(response, dict):
        return response.get("data")
    if hasattr(response, "data"):
        return response.data
    return None
