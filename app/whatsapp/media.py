from typing import Optional, Tuple

import httpx

from app.core.config import settings


class MediaDownloadError(Exception):
    pass


def download_whatsapp_media(
    media_id: str,
) -> Tuple[Optional[bytes], Optional[str]]:
    if not settings.whatsapp_access_token:
        raise MediaDownloadError("WHATSAPP_ACCESS_TOKEN is not set")

    headers = {"Authorization": f"Bearer {settings.whatsapp_access_token}"}

    with httpx.Client(timeout=30) as client:
        meta_response = client.get(
            f"https://graph.facebook.com/v21.0/{media_id}", headers=headers
        )
        if not meta_response.is_success:
            raise MediaDownloadError("Failed to fetch media metadata")

        meta = meta_response.json()
        url = meta.get("url")
        mime_type = meta.get("mime_type")
        if not url:
            raise MediaDownloadError("Missing media URL")

        media_response = client.get(url, headers=headers)
        if not media_response.is_success:
            raise MediaDownloadError("Failed to download media file")

        return media_response.content, mime_type
