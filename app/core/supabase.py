import time
from typing import Any, Optional

from fastapi import HTTPException
from supabase import Client, create_client

from app.core.config import settings

from httpx import Timeout

# ── Manual singleton with resettable client ─────────────────────────
_supabase_client: Optional[Client] = None


def _create_fresh_client() -> Client:
    """Create a new Supabase client with proper timeouts."""
    if not settings.supabase_url:
        raise HTTPException(status_code=500, detail="SUPABASE_URL is not configured")
    if not settings.supabase_service_key:
        raise HTTPException(
            status_code=500, detail="SUPABASE_SERVICE_ROLE_KEY is not configured"
        )

    from supabase.lib.client_options import SyncClientOptions

    opts = SyncClientOptions(
        postgrest_client_timeout=30,
    )
    client = create_client(
        settings.supabase_url, settings.supabase_service_key, options=opts
    )

    # Set explicit timeouts on the underlying httpx client to avoid
    # hanging on stale keep-alive connections (common with local Kong proxy).
    timeout = Timeout(10.0, connect=5.0, read=30.0, write=10.0)
    if hasattr(client, "postgrest") and hasattr(client.postgrest, "session"):
        client.postgrest.session.timeout = timeout

    return client


def get_supabase_client() -> Client:
    """Return the singleton Supabase client, creating it on first call."""
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = _create_fresh_client()
    return _supabase_client


def reset_supabase_client() -> None:
    """Discard the current client so the next call creates a fresh one.

    Use after catching httpx connection pool errors (Errno 11, ReadError, etc.)
    """
    global _supabase_client
    old = _supabase_client
    _supabase_client = None
    # Try to close the old httpx transport cleanly
    if old is not None:
        try:
            if hasattr(old, "postgrest") and hasattr(old.postgrest, "session"):
                old.postgrest.session.aclose  # noqa – just checking existence
        except Exception:
            pass
    print("[supabase] client reset — next call will create a fresh connection")


def supabase_retry(fn, *args, max_retries: int = 2, **kwargs):
    """Run *fn* with automatic Supabase client recreation on connection errors.

    Catches httpx ReadError / ConnectionError that signal a dead pool and
    retries after resetting the client.
    """
    import httpx
    import httpcore

    retryable = (
        httpx.ReadError,
        httpx.ConnectError,
        httpx.RemoteProtocolError,
        httpcore.ReadError,
        httpcore.ConnectError,
        OSError,
    )

    for attempt in range(1, max_retries + 2):
        try:
            return fn(*args, **kwargs)
        except retryable as exc:
            if attempt > max_retries:
                raise
            print(
                f"[supabase] connection error (attempt {attempt}/{max_retries + 1}): {exc}"
            )
            reset_supabase_client()
            time.sleep(0.3 * attempt)  # brief back-off


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
