import time
from typing import Any, Optional

from fastapi import HTTPException
from supabase import Client, create_client

from app.core.config import settings

import httpx
import httpcore

from httpx import Timeout

# ── Connection-error types that indicate a dead pool ────────────────
CONN_ERRORS = (
    httpx.ReadError,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
    httpcore.ReadError,
    httpcore.ConnectError,
    OSError,
)

# ── Manual singleton with TTL + reset ───────────────────────────────
_supabase_client: Optional[Client] = None
_client_created_at: float = 0.0
_CLIENT_TTL_SECONDS: float = 300.0  # 5-minute auto-refresh


def _create_fresh_client() -> Client:
    """Create a new Supabase client with HTTP/1.1, tight pool limits, and timeouts."""
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

    # Replace the postgrest session's transport with one that:
    #  - Forces HTTP/1.1 (avoids HTTP/2 stale multiplexed connections)
    #  - Limits the connection pool to prevent resource exhaustion
    #  - Sets keepalive_expiry so idle connections are recycled
    timeout = Timeout(10.0, connect=5.0, read=30.0, write=10.0)
    if hasattr(client, "postgrest") and hasattr(client.postgrest, "session"):
        session = client.postgrest.session
        session.timeout = timeout

        # Build a transport that disables HTTP/2 and limits pool size
        transport = httpx.HTTPTransport(
            http2=False,  # Force HTTP/1.1 — avoids stale H2 streams
            retries=1,
            limits=httpx.Limits(
                max_connections=10,
                max_keepalive_connections=5,
                keepalive_expiry=30,  # seconds — recycle idle conns quickly
            ),
        )
        # Replace the default transport
        session._transport = transport

    print("[supabase] fresh client created (HTTP/1.1, pool limits enforced)")
    return client


def get_supabase_client() -> Client:
    """Return the singleton Supabase client, creating/refreshing as needed."""
    global _supabase_client, _client_created_at

    now = time.monotonic()
    if _supabase_client is not None and (now - _client_created_at) > _CLIENT_TTL_SECONDS:
        print("[supabase] client TTL expired, refreshing")
        _close_client(_supabase_client)
        _supabase_client = None

    if _supabase_client is None:
        _supabase_client = _create_fresh_client()
        _client_created_at = now

    return _supabase_client


def reset_supabase_client() -> None:
    """Discard the current client so the next call creates a fresh one.

    Use after catching httpx connection pool errors (Errno 11, ReadError, etc.)
    """
    global _supabase_client
    old = _supabase_client
    _supabase_client = None
    _close_client(old)
    print("[supabase] client reset — next call will create a fresh connection")


def _close_client(client: Optional[Client]) -> None:
    """Best-effort close of the old httpx transport."""
    if client is None:
        return
    try:
        if hasattr(client, "postgrest") and hasattr(client.postgrest, "session"):
            client.postgrest.session.close()
    except Exception:
        pass


def supabase_retry(fn, *args, max_retries: int = 1, **kwargs):
    """Run *fn* with automatic Supabase client recreation on connection errors.

    Catches httpx ReadError / ConnectionError that signal a dead pool and
    retries after resetting the client.
    """
    for attempt in range(1, max_retries + 2):
        try:
            return fn(*args, **kwargs)
        except CONN_ERRORS as exc:
            if attempt > max_retries:
                raise
            print(
                f"[supabase] connection error (attempt {attempt}/{max_retries + 1}): {exc}"
            )
            reset_supabase_client()
            time.sleep(0.5 * attempt)


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
