from typing import Any, Optional

from fastapi import HTTPException
from supabase import Client, create_client

from app.core.config import settings


def get_supabase_client() -> Client:
    if not settings.supabase_url:
        raise HTTPException(status_code=500, detail="Supabase is not configured")
    key = settings.supabase_service_key or settings.supabase_key
    if not key:
        raise HTTPException(status_code=500, detail="Supabase key is not configured")
    return create_client(settings.supabase_url, key)


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
