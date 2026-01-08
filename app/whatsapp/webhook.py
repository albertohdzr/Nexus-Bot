from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request, Response

from app.core.config import settings
from app.whatsapp.processing import handle_incoming_messages
from app.whatsapp.status import handle_status_updates
from app.whatsapp.templates import handle_template_updates, is_template_change_field

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


@router.get("/webhook")
async def verify_webhook(request: Request):
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode and token:
        if mode == "subscribe" and token == settings.whatsapp_verify_token:
            print("WEBHOOK_VERIFIED")
            return Response(content=challenge or "", status_code=200)
        return Response(content="Forbidden", status_code=403)

    return Response(content="Bad Request", status_code=400)


@router.post("/webhook")
async def receive_webhook(request: Request):
    try:
        body: Dict[str, Any] = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc

    if body.get("object") != "whatsapp_business_account":
        return Response(content="Not a WhatsApp API event", status_code=404)

    entries = body.get("entry") or []
    value: Optional[Dict[str, Any]] = None

    for entry in entries:
        changes = entry.get("changes") or []
        for change in changes:
            if is_template_change_field(change.get("field")):
                handle_template_updates(
                    entry_id=str(entry.get("id")) if entry.get("id") else None,
                    entry_time=entry.get("time") if isinstance(entry.get("time"), int) else None,
                    change=change,
                )
                continue

            if not value:
                change_value = change.get("value") if isinstance(change, dict) else None
                if change_value and change_value.get("metadata", {}).get("phone_number_id"):
                    value = change_value

    if value:
        handle_incoming_messages(value)
        handle_status_updates(value)

    return Response(content="EVENT_RECEIVED", status_code=200)
