from fastapi import APIRouter

from app.whatsapp.outbound import (
    SendWhatsAppAudioParams,
    SendWhatsAppDocumentParams,
    SendWhatsAppImageParams,
    SendWhatsAppReadParams,
    SendWhatsAppTextParams,
    UploadWhatsAppMediaParams,
    WhatsAppResponse,
    send_whatsapp_audio,
    send_whatsapp_document,
    send_whatsapp_image,
    send_whatsapp_read,
    send_whatsapp_text,
    upload_whatsapp_media,
)

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


@router.post("/send/text", response_model=WhatsAppResponse)
def send_text(params: SendWhatsAppTextParams):
    return send_whatsapp_text(params)


@router.post("/send/read", response_model=WhatsAppResponse)
def send_read(params: SendWhatsAppReadParams):
    return send_whatsapp_read(params)


@router.post("/send/media", response_model=WhatsAppResponse)
def upload_media(params: UploadWhatsAppMediaParams):
    return upload_whatsapp_media(params)


@router.post("/send/image", response_model=WhatsAppResponse)
def send_image(params: SendWhatsAppImageParams):
    return send_whatsapp_image(params)


@router.post("/send/audio", response_model=WhatsAppResponse)
def send_audio(params: SendWhatsAppAudioParams):
    return send_whatsapp_audio(params)


@router.post("/send/document", response_model=WhatsAppResponse)
def send_document(params: SendWhatsAppDocumentParams):
    return send_whatsapp_document(params)
