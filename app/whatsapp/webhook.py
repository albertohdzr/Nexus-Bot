from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response

from app.core.auth import verify_webhook_signature
from app.core.config import settings
from app.whatsapp.processing import handle_incoming_messages
from app.whatsapp.status import handle_status_updates
from app.whatsapp.templates import handle_template_updates, is_template_change_field

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


@router.get("/webhook")
async def verify_webhook(request: Request):
    """Meta verification handshake — no HMAC needed here (GET)."""
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


def _process_webhook_background(
    value: Optional[Dict[str, Any]],
    template_updates: List[Dict[str, Any]],
) -> None:
    """Runs in background after 200 OK is returned to WhatsApp."""
    for update in template_updates:
        try:
            handle_template_updates(**update)
        except Exception as exc:
            print("[webhook] template update error", {"error": str(exc)})

    if value:
        try:
            handle_incoming_messages(value)
        except Exception as exc:
            print("[webhook] incoming messages error", {"error": str(exc)})
        try:
            handle_status_updates(value)
        except Exception as exc:
            print("[webhook] status update error", {"error": str(exc)})


@router.post("/webhook", dependencies=[Depends(verify_webhook_signature)])
async def receive_webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        body: Dict[str, Any] = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc

    if body.get("object") != "whatsapp_business_account":
        return Response(content="Not a WhatsApp API event", status_code=404)

    entries = body.get("entry") or []
    value: Optional[Dict[str, Any]] = None
    template_updates: List[Dict[str, Any]] = []

    for entry in entries:
        changes = entry.get("changes") or []
        for change in changes:
            if is_template_change_field(change.get("field")):
                template_updates.append({
                    "entry_id": str(entry.get("id")) if entry.get("id") else None,
                    "entry_time": entry.get("time") if isinstance(entry.get("time"), int) else None,
                    "change": change,
                })
                continue

            if not value:
                change_value = change.get("value") if isinstance(change, dict) else None
                if change_value and change_value.get("metadata", {}).get("phone_number_id"):
                    value = change_value

    # Process in background — respond 200 immediately so WhatsApp
    # doesn't retry the webhook due to timeout.
    if value or template_updates:
        background_tasks.add_task(
            _process_webhook_background, value, template_updates
        )

    return Response(content="EVENT_RECEIVED", status_code=200)

