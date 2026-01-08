from typing import Optional, Tuple

from app.core.config import settings
from app.core.supabase import get_supabase_client


def upload_to_storage(
    file_bytes: bytes,
    path: str,
    content_type: Optional[str],
) -> Tuple[Optional[str], Optional[object]]:
    supabase = get_supabase_client()
    bucket = settings.supabase_storage_bucket
    response = supabase.storage.from_(bucket).upload(
        path,
        file_bytes,
        {
            "content-type": content_type or "application/octet-stream",
            "upsert": False,
        },
    )
    error = None
    if isinstance(response, dict):
        error = response.get("error")
    elif hasattr(response, "error"):
        error = response.error
    if error:
        return None, error
    return path, None
