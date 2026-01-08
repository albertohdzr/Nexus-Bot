from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.chat.service import get_grok_client
from app.core.config import settings
from app.core.supabase import (
    get_supabase_client,
    get_supabase_data,
    get_supabase_error,
)
from app.whatsapp.outbound import SendWhatsAppTextParams, send_whatsapp_text

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])


class ProcessQueueRequest(BaseModel):
    chat_id: str
    final_message: Optional[str] = None


def _require_cron_secret(authorization: Optional[str]) -> None:
    if not settings.cron_secret:
        raise HTTPException(status_code=500, detail="CRON_SECRET is not set")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization.split("Bearer ", 1)[1].strip()
    if token != settings.cron_secret:
        raise HTTPException(status_code=403, detail="Forbidden")


def _build_prompt(org: Dict[str, Any]) -> str:
    bot_name = org.get("bot_name") or "Asistente"
    instructions = org.get("bot_instructions") or ""
    tone = org.get("bot_tone") or "amable"
    language = org.get("bot_language") or "es"

    base_prompt = (
        f"Eres {bot_name}, un asistente de soporte al cliente por WhatsApp. "
        f"Responde en {language} con un tono {tone}. "
        "Mantente en el contexto del negocio y ofrece ayuda clara y breve."
    )
    if instructions:
        base_prompt = f"{base_prompt}\nInstrucciones adicionales: {instructions}"
    return base_prompt


def _ensure_active_session(chat: Dict[str, Any], org_id: str) -> str:
    supabase = get_supabase_client()
    session_id = chat.get("active_session_id")

    if session_id:
        session_response = (
            supabase.from_("chat_sessions")
            .select("id, status, closed_at, last_response_at")
            .eq("id", session_id)
            .maybe_single()
            .execute()
        )
        session_data = get_supabase_data(session_response)
        if session_data and session_data.get("status") == "active" and not session_data.get(
            "closed_at"
        ):
            return session_id

    session_insert = (
        supabase.from_("chat_sessions")
        .insert(
            {
                "organization_id": org_id,
                "chat_id": chat.get("id"),
                "status": "active",
                "ai_enabled": True,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }
        )
        .execute()
    )
    session_error = get_supabase_error(session_insert)
    if session_error:
        raise HTTPException(status_code=500, detail="Failed to create chat session")

    session_fetch = (
        supabase.from_("chat_sessions")
        .select("id")
        .eq("chat_id", chat.get("id"))
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    session_fetch_error = get_supabase_error(session_fetch)
    session_rows = get_supabase_data(session_fetch) or []
    session_data = session_rows[0] if session_rows else None
    if session_fetch_error or not session_data:
        raise HTTPException(status_code=500, detail="Failed to load chat session")

    new_session_id = session_data.get("id")
    supabase.from_("chats").update(
        {
            "active_session_id": new_session_id,
            "last_session_closed_at": None,
            "updated_at": datetime.utcnow().isoformat(),
        }
    ).eq("id", chat.get("id")).execute()

    return new_session_id


def _load_session_messages(
    session_id: str,
) -> List[Dict[str, Any]]:
    supabase = get_supabase_client()
    response = (
        supabase.from_("messages")
        .select("role, body, created_at")
        .eq("chat_session_id", session_id)
        .order("created_at", desc=False)
        .execute()
    )
    data = get_supabase_data(response) or []
    return [
        item
        for item in data
        if item.get("role") in {"user", "assistant"} and item.get("body")
    ]


def _load_session_state(session_id: str) -> Dict[str, Any]:
    supabase = get_supabase_client()
    response = (
        supabase.from_("chat_sessions")
        .select("last_response_at")
        .eq("id", session_id)
        .single()
        .execute()
    )
    return get_supabase_data(response) or {}


@router.post("/process")
def process_queue(
    payload: ProcessQueueRequest,
    authorization: Optional[str] = Header(default=None),
):
    _require_cron_secret(authorization)

    supabase = get_supabase_client()
    chat_response = (
        supabase.from_("chats")
        .select("id, wa_id, organization_id, active_session_id")
        .eq("id", payload.chat_id)
        .single()
        .execute()
    )
    chat_error = get_supabase_error(chat_response)
    chat = get_supabase_data(chat_response)

    if chat_error or not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    org_response = (
        supabase.from_("organizations")
        .select("id, bot_name, bot_instructions, bot_tone, bot_language, bot_model, phone_number_id")
        .eq("id", chat.get("organization_id"))
        .single()
        .execute()
    )
    org_error = get_supabase_error(org_response)
    org = get_supabase_data(org_response)

    if org_error or not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    if not org.get("phone_number_id"):
        raise HTTPException(
            status_code=500, detail="Organization missing phone_number_id"
        )

    if not chat.get("wa_id"):
        raise HTTPException(status_code=500, detail="Chat missing wa_id")

    session_id = _ensure_active_session(chat, org.get("id"))

    supabase.from_("messages").update({"chat_session_id": session_id}).eq(
        "chat_id", chat.get("id")
    ).is_("chat_session_id", None).execute()

    session_state = _load_session_state(session_id)
    last_response_at = session_state.get("last_response_at")
    last_response_dt = None
    if last_response_at:
        try:
            last_response_dt = datetime.fromisoformat(last_response_at)
        except ValueError:
            last_response_dt = None

    all_messages = _load_session_messages(session_id)

    history: List[Dict[str, str]] = []
    pending_user_texts: List[str] = []

    for message in all_messages:
        role = message.get("role")
        body = message.get("body")
        created_at = message.get("created_at")
        created_dt = None
        if created_at:
            try:
                created_dt = datetime.fromisoformat(created_at)
            except ValueError:
                created_dt = None
        if not body or not role:
            continue
        if last_response_dt and created_dt and created_dt <= last_response_dt:
            history.append({"role": role, "content": body})
        elif role == "user":
            pending_user_texts.append(body)

    combined_user = payload.final_message or " ".join(pending_user_texts)
    if not combined_user:
        return {"status": "skipped", "reason": "no_user_message"}

    messages_payload = [
        {"role": "system", "content": _build_prompt(org)},
        *history,
        {"role": "user", "content": combined_user},
    ]

    model = org.get("bot_model")
    if not isinstance(model, str) or not model.startswith("grok"):
        model = "grok-4"
    grok_client = get_grok_client()
    completion = grok_client.chat.completions.create(
        model=model,
        messages=messages_payload,
    )
    assistant_text = completion.choices[0].message.content or ""

    send_result = send_whatsapp_text(
        SendWhatsAppTextParams(
            phone_number_id=org.get("phone_number_id"),
            to=chat.get("wa_id"),
            body=assistant_text,
        )
    )

    message_payload = {
        "chat_id": chat.get("id"),
        "chat_session_id": session_id,
        "wa_message_id": send_result.message_id,
        "body": assistant_text,
        "type": "text",
        "status": "sent" if not send_result.error else "failed",
        "direction": "outbound",
        "role": "assistant",
        "payload": {
            "source": "grok",
            "error": send_result.error,
        },
        "sender_name": org.get("bot_name"),
        "created_at": datetime.utcnow().isoformat(),
    }

    supabase.from_("messages").insert(message_payload).execute()

    supabase.from_("chat_sessions").update(
        {
            "last_response_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
    ).eq("id", session_id).execute()

    return {
        "status": "sent" if not send_result.error else "error",
        "message_id": send_result.message_id,
        "error": send_result.error,
    }
