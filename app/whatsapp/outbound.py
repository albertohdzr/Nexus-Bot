import base64
import time
from typing import Optional

import httpx
from fastapi import HTTPException
from pydantic import BaseModel

from app.core.config import settings

API_VERSION = "v21.0"


def _normalize_recipient(to: str) -> str:
    if to.startswith("521"):
        return "52" + to[3:]
    return to


def _get_access_token(access_token: Optional[str]) -> str:
    token = access_token or settings.whatsapp_access_token
    if not token:
        raise HTTPException(
            status_code=500, detail="WHATSAPP_ACCESS_TOKEN is not set"
        )
    return token


class SendWhatsAppTextParams(BaseModel):
    phone_number_id: str
    to: str
    body: str
    access_token: Optional[str] = None


class SendWhatsAppReadParams(BaseModel):
    phone_number_id: str
    message_id: str
    typing_type: str = "text"
    access_token: Optional[str] = None


class UploadWhatsAppMediaParams(BaseModel):
    phone_number_id: str
    media_base64: str
    mime_type: str
    file_name: Optional[str] = None
    access_token: Optional[str] = None


class SendWhatsAppImageParams(BaseModel):
    phone_number_id: str
    to: str
    media_id: str
    caption: Optional[str] = None
    access_token: Optional[str] = None


class SendWhatsAppAudioParams(BaseModel):
    phone_number_id: str
    to: str
    media_id: str
    voice: Optional[bool] = False
    access_token: Optional[str] = None


class SendWhatsAppDocumentParams(BaseModel):
    phone_number_id: str
    to: str
    media_id: str
    file_name: Optional[str] = None
    caption: Optional[str] = None
    access_token: Optional[str] = None


class WhatsAppResponse(BaseModel):
    message_id: Optional[str] = None
    media_id: Optional[str] = None
    error: Optional[str] = None


def send_whatsapp_text(
    params: SendWhatsAppTextParams,
) -> WhatsAppResponse:
    recipient = _normalize_recipient(params.to)
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "text",
        "text": {"preview_url": False, "body": params.body},
    }

    token = _get_access_token(params.access_token)
    response = httpx.post(
        f"https://graph.facebook.com/{API_VERSION}/{params.phone_number_id}/messages",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        json=payload,
        timeout=30,
    )

    try:
        data = response.json()
    except ValueError:
        data = {}
    if not response.is_success:
        error_message = data.get("error", {}).get("message") or "Unknown WhatsApp API error"
        return WhatsAppResponse(error=error_message)

    message_id = data.get("messages", [{}])[0].get("id")
    return WhatsAppResponse(message_id=message_id)


def send_whatsapp_read(
    params: SendWhatsAppReadParams,
) -> WhatsAppResponse:
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": params.message_id,
        "typing_indicator": {"type": params.typing_type},
    }

    token = _get_access_token(params.access_token)
    response = httpx.post(
        f"https://graph.facebook.com/{API_VERSION}/{params.phone_number_id}/messages",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        json=payload,
        timeout=30,
    )

    try:
        data = response.json()
    except ValueError:
        data = {}
    if not response.is_success:
        error_message = data.get("error", {}).get("message") or "Unknown WhatsApp API error"
        return WhatsAppResponse(error=error_message)

    return WhatsAppResponse()


def upload_whatsapp_media(
    params: UploadWhatsAppMediaParams,
) -> WhatsAppResponse:
    token = _get_access_token(params.access_token)
    file_name = params.file_name or f"media-{int(time.time())}"

    try:
        file_bytes = base64.b64decode(params.media_base64)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid base64 media") from exc

    files = {
        "file": (file_name, file_bytes, params.mime_type),
    }
    data = {
        "messaging_product": "whatsapp",
    }

    response = httpx.post(
        f"https://graph.facebook.com/{API_VERSION}/{params.phone_number_id}/media",
        headers={"Authorization": f"Bearer {token}"},
        data=data,
        files=files,
        timeout=60,
    )

    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if not response.is_success:
        error_message = payload.get("error", {}).get("message") or "Unknown WhatsApp API error"
        return WhatsAppResponse(error=error_message)

    return WhatsAppResponse(media_id=payload.get("id"))


def send_whatsapp_image(
    params: SendWhatsAppImageParams,
) -> WhatsAppResponse:
    recipient = _normalize_recipient(params.to)
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "image",
        "image": {
            "id": params.media_id,
            "caption": params.caption,
        },
    }

    token = _get_access_token(params.access_token)
    response = httpx.post(
        f"https://graph.facebook.com/{API_VERSION}/{params.phone_number_id}/messages",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        json=payload,
        timeout=30,
    )

    try:
        data = response.json()
    except ValueError:
        data = {}
    if not response.is_success:
        error_message = data.get("error", {}).get("message") or "Unknown WhatsApp API error"
        return WhatsAppResponse(error=error_message)

    message_id = data.get("messages", [{}])[0].get("id")
    return WhatsAppResponse(message_id=message_id)


def send_whatsapp_audio(
    params: SendWhatsAppAudioParams,
) -> WhatsAppResponse:
    recipient = _normalize_recipient(params.to)
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "audio",
        "audio": {
            "id": params.media_id,
            "voice": bool(params.voice),
        },
    }

    token = _get_access_token(params.access_token)
    response = httpx.post(
        f"https://graph.facebook.com/{API_VERSION}/{params.phone_number_id}/messages",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        json=payload,
        timeout=30,
    )

    try:
        data = response.json()
    except ValueError:
        data = {}
    if not response.is_success:
        error_message = data.get("error", {}).get("message") or "Unknown WhatsApp API error"
        return WhatsAppResponse(error=error_message)

    message_id = data.get("messages", [{}])[0].get("id")
    return WhatsAppResponse(message_id=message_id)


def send_whatsapp_document(
    params: SendWhatsAppDocumentParams,
) -> WhatsAppResponse:
    recipient = _normalize_recipient(params.to)
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "document",
        "document": {
            "id": params.media_id,
            "caption": params.caption,
            "filename": params.file_name,
        },
    }

    token = _get_access_token(params.access_token)
    response = httpx.post(
        f"https://graph.facebook.com/{API_VERSION}/{params.phone_number_id}/messages",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        json=payload,
        timeout=30,
    )

    try:
        data = response.json()
    except ValueError:
        data = {}
    if not response.is_success:
        error_message = data.get("error", {}).get("message") or "Unknown WhatsApp API error"
        return WhatsAppResponse(error=error_message)

    message_id = data.get("messages", [{}])[0].get("id")
    return WhatsAppResponse(message_id=message_id)
