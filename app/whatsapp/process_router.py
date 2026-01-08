from datetime import datetime, timezone
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
from app.whatsapp.outbound import (
    SendWhatsAppTextParams,
    send_whatsapp_text,
    SendWhatsAppDocumentParams,
    send_whatsapp_document,
    UploadWhatsAppMediaParams,
    upload_whatsapp_media,
)

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])


class ProcessQueueRequest(BaseModel):
    chat_id: str
    final_message: Optional[str] = None


class CreateAdmissionsLeadRequest(BaseModel):
    student_first_name: str
    student_middle_name: Optional[str] = None
    student_last_name_paternal: str
    student_last_name_maternal: Optional[str] = None
    grade_interest: str
    school_year: Optional[str] = None
    current_school: str
    contact_first_name: Optional[str] = None
    contact_middle_name: Optional[str] = None
    contact_last_name_paternal: Optional[str] = None
    contact_last_name_maternal: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    relationship: Optional[str] = None
    notes: Optional[str] = None


class UpdateAdmissionsLeadRequest(BaseModel):
    student_first_name: Optional[str] = None
    student_middle_name: Optional[str] = None
    student_last_name_paternal: Optional[str] = None
    student_last_name_maternal: Optional[str] = None
    grade_interest: Optional[str] = None
    school_year: Optional[str] = None
    current_school: Optional[str] = None
    contact_first_name: Optional[str] = None
    contact_middle_name: Optional[str] = None
    contact_last_name_paternal: Optional[str] = None
    contact_last_name_maternal: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    relationship: Optional[str] = None
    notes: Optional[str] = None


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
    school_name = org.get("name") or "el colegio"

    base_prompt = (
        f"Eres {bot_name}, un asistente virtual de admisiones de {school_name}. "
        f"Responde en {language} con un tono {tone}. "
        "Tu objetivo es orientar a familias interesadas de forma natural y servicial. "
        "No pidas datos personales (como nombre, correo o teléfono) de inmediato en el saludo. "
        "Primero responde a las dudas del usuario o inicia la conversación de manera amigable. "
        "Recaba los datos necesarios poco a poco y de forma integrada en la charla, no como un interrogatorio. "
        "No inventes datos. "
        "Nunca compartas costos, colegiaturas, cuotas ni descuentos. "
        "Si preguntan por precios, explica amablemente que no puedes compartirlos por este medio y ofrece "
        "que un asesor de admisiones los contactará para darles información personalizada. "
        "Generalmente conversas con madres, padres o tutores. Usa un saludo neutro si no conoces su nombre. "
        "No saludes de nuevo si ya la conversación está iniciada. "
        "Solo di que actualizaste o guardaste datos cuando hayas ejecutado exitosamente una herramienta. "
        "Datos objetivo a recolectar durante la charla: Nombre completo del alumno, Grado de interés (kinder, primaria, secundaria, prepa), Escuela actual, Nombre del tutor, Correo y Teléfono. "
        "Valora la fluidez y la empatía por encima de capturar los datos rápido. "
        "SÍ tienes acceso a información de requisitos. Si preguntan, responde con la información clave y OFRECE enviar el documento PDF oficial usando la herramienta 'get_admission_requirements'. "
        
        "RESUMEN DE REQUISITOS (ten esto en contexto para dudas): "
        "1. PRENURSERY (MATERNAL): 4 fotos, Acta nacimiento, Carta desempeño (si aplica), Curp, Carta solvencia (nuevos), Certificado salud, Cartilla vacunación, Formatos CAT. "
        "2. EARLY CHILDHOOD (PREESCOLAR/KINDER): Similar a maternal + Reporte evaluación SEP y Carta conducta escuela anterior. "
        "3. ELEMENTARY (PRIMARIA): Fotos, Acta, Calificaciones SEP (año en curso y 2 anteriores), Certificado Preescolar (para 1ro), Carta conducta, Curp, Solvencia, Cartas recomendación. "
        "4. MIDDLE SCHOOL (SECUNDARIA): Similar primaria + Certificado Primaria. "
        "5. HIGH SCHOOL (PREPARATORIA): Promedio mínimo 8.0, Conducta condicionante. Certificado Secundaria + Papelería estándar. "

        "Para enviar el PDF usa 'get_admission_requirements' con la división correcta: "
        "'prenursery', 'early_child' (para kinder/preescolar), 'elementary' (primaria), 'middle_school' (secundaria), 'high_school' (prepa). "
        "Si no sabes la división, pregúntala antes de intentar enviar."
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
    print("[admissions] loading session messages", {"session_id": session_id})
    response = (
        supabase.from_("messages")
        .select("role, body, created_at, wa_timestamp")
        .eq("chat_session_id", session_id)
        .order("created_at", desc=True)
        .execute()
    )
    data = get_supabase_data(response) or []
    # print("[admissions] session messages data", data)
    # print(
    #     "[admissions] session messages fetched",
    #     {"session_id": session_id, "count": len(data)},
    # )

    def _normalize_dt(value: str) -> str:
        import re

        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized.replace("Z", "+00:00")
        if len(normalized) >= 3 and normalized[-3] in {"+", "-"}:
            normalized = f"{normalized}:00"
        if len(normalized) >= 5 and normalized[-5] in {"+", "-"}:
            normalized = f"{normalized[:-2]}:{normalized[-2:]}"

        # Fix microseconds to be 3 or 6 digits for Python < 3.11 compatibility
        match = re.search(r"\.(\d+)(?:([+-]\d{2}:\d{2})|$)", normalized)
        if match:
            us = match.group(1)
            tz = match.group(2) or ""
            if len(us) != 3 and len(us) != 6:
                if len(us) < 6:
                    new_us = us.ljust(6, "0")
                else:
                    new_us = us[:6]
                normalized = normalized.replace(f".{us}{tz}", f".{new_us}{tz}")

        return normalized

    def _parse_dt(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(_normalize_dt(value))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            try:
                parsed = datetime.fromisoformat(_normalize_dt(value.replace(" ", "T")))
                if parsed.tzinfo is None:
                    return parsed.replace(tzinfo=timezone.utc)
                return parsed
            except ValueError:
                return None

    def _sort_key(item: Dict[str, Any]) -> float:
        role = item.get("role")
        created_dt = _parse_dt(item.get("created_at"))
        wa_dt = _parse_dt(item.get("wa_timestamp"))
        if role == "user" and wa_dt:
            dt = wa_dt
        else:
            dt = created_dt or wa_dt
        return dt.timestamp() if dt else 0.0

    ordered = sorted(data, key=_sort_key)
    debug_order = [
        {
            "role": item.get("role"),
            "created_at": item.get("created_at"),
            "wa_timestamp": item.get("wa_timestamp"),
            "key": _sort_key(item),
            "body": (item.get("body") or "")[:60],
        }
        for item in ordered[:20]
    ]
    # print("[admissions] session messages ordered", debug_order)
    return [
        item
        for item in ordered
        if item.get("role") in {"user", "assistant"} and item.get("body")
    ]


def _compose_full_name(parts: List[Optional[str]]) -> Optional[str]:
    cleaned = [part.strip() for part in parts if part and part.strip()]
    return " ".join(cleaned) if cleaned else None


def _find_or_create_contact(
    org_id: str,
    wa_id: Optional[str],
    request: CreateAdmissionsLeadRequest,
) -> str:
    supabase = get_supabase_client()
    contact_phone = request.contact_phone or wa_id
    print(
        "[admissions] contact lookup",
        {"org_id": org_id, "wa_id": wa_id, "contact_phone": contact_phone},
    )

    contact_response = (
        supabase.from_("crm_contacts")
        .select("id")
        .eq("organization_id", org_id)
        .eq("whatsapp_wa_id", wa_id)
        .maybe_single()
        .execute()
    )
    contact_error = get_supabase_error(contact_response)
    contact_data = get_supabase_data(contact_response)
    if contact_error:
        raise HTTPException(status_code=500, detail="Failed to lookup contact")

    if not contact_data and contact_phone:
        contact_response = (
            supabase.from_("crm_contacts")
            .select("id")
            .eq("organization_id", org_id)
            .eq("phone", contact_phone)
            .maybe_single()
            .execute()
        )
        contact_error = get_supabase_error(contact_response)
        contact_data = get_supabase_data(contact_response)
        if contact_error:
            raise HTTPException(status_code=500, detail="Failed to lookup contact")

    if contact_data and contact_data.get("id"):
        print("[admissions] contact found", {"contact_id": contact_data.get("id")})
        return contact_data["id"]

    if not contact_phone:
        raise HTTPException(status_code=400, detail="Missing contact phone")

    contact_insert = (
        supabase.from_("crm_contacts")
        .insert(
            {
                "organization_id": org_id,
                "first_name": request.contact_first_name,
                "middle_name": request.contact_middle_name,
                "last_name_paternal": request.contact_last_name_paternal,
                "last_name_maternal": request.contact_last_name_maternal,
                "phone": contact_phone,
                "email": request.contact_email,
                "whatsapp_wa_id": wa_id,
                "source": "whatsapp",
            }
        )
        .execute()
    )
    contact_error = get_supabase_error(contact_insert)
    contact_rows = get_supabase_data(contact_insert) or []
    contact_row = contact_rows[0] if contact_rows else None
    if contact_error or not contact_row or not contact_row.get("id"):
        raise HTTPException(status_code=500, detail="Failed to create contact")

    print("[admissions] contact created", {"contact_id": contact_row.get("id")})
    return contact_row["id"]


def _create_admissions_lead(
    request: CreateAdmissionsLeadRequest,
    org: Dict[str, Any],
    chat: Dict[str, Any],
) -> str:
    supabase = get_supabase_client()
    print(
        "[admissions] create lead payload",
        {
            "student_first_name": request.student_first_name,
            "student_last_name_paternal": request.student_last_name_paternal,
            "grade_interest": request.grade_interest,
            "current_school": request.current_school,
            "contact_email": request.contact_email,
            "contact_phone": request.contact_phone,
        },
    )
    if (
        not request.student_first_name.strip()
        or not request.student_last_name_paternal.strip()
        or not request.grade_interest.strip()
        or not request.current_school.strip()
    ):
        return (
            "No se pudo crear el lead porque faltan datos obligatorios del alumno, "
            "el colegio de procedencia o el grado de interes."
        )

    org_id = org.get("id")
    chat_id = chat.get("id")
    wa_id = chat.get("wa_id")
    if not org_id or not chat_id:
        raise HTTPException(status_code=400, detail="Missing org or chat id")

    existing_response = (
        supabase.from_("leads")
        .select("id, lead_number")
        .eq("organization_id", org_id)
        .eq("wa_chat_id", chat_id)
        .maybe_single()
        .execute()
    )
    existing_error = get_supabase_error(existing_response)
    existing_data = get_supabase_data(existing_response)
    if existing_error:
        raise HTTPException(status_code=500, detail="Failed to lookup lead")
    if existing_data and existing_data.get("id"):
        lead_number = existing_data.get("lead_number")
        print(
            "[admissions] lead exists",
            {"lead_id": existing_data.get("id"), "lead_number": lead_number},
        )
        return (
            f"Lead ya existente con folio L-{lead_number}."
            if lead_number
            else "Lead ya existente."
        )

    contact_id = _find_or_create_contact(org_id, wa_id, request)
    contact_phone = request.contact_phone or wa_id
    if not contact_phone:
        raise HTTPException(status_code=400, detail="Missing contact phone")

    contact_name = _compose_full_name(
        [
            request.contact_first_name,
            request.contact_middle_name,
            request.contact_last_name_paternal,
            request.contact_last_name_maternal,
        ]
    ) or chat.get("name")

    metadata: Dict[str, Any] = {}
    if request.relationship:
        metadata["relationship"] = request.relationship

    lead_insert = (
        supabase.from_("leads")
        .insert(
            {
                "organization_id": org_id,
                "source": "whatsapp",
                "student_first_name": request.student_first_name,
                "student_middle_name": request.student_middle_name,
                "student_last_name_paternal": request.student_last_name_paternal,
                "student_last_name_maternal": request.student_last_name_maternal,
                "student_grade_interest": request.grade_interest,
                "grade_interest": request.grade_interest,
                "school_year": request.school_year,
                "current_school": request.current_school,
                "contact_id": contact_id,
                "contact_name": contact_name,
                "contact_first_name": request.contact_first_name,
                "contact_middle_name": request.contact_middle_name,
                "contact_last_name_paternal": request.contact_last_name_paternal,
                "contact_last_name_maternal": request.contact_last_name_maternal,
                "contact_email": request.contact_email,
                "contact_phone": contact_phone,
                "notes": request.notes,
                "wa_chat_id": chat_id,
                "wa_id": wa_id,
                "metadata": metadata,
            }
        )
        .execute()
    )
    lead_error = get_supabase_error(lead_insert)
    lead_rows = get_supabase_data(lead_insert) or []
    lead_row = lead_rows[0] if lead_rows else None
    if lead_error or not lead_row:
        raise HTTPException(status_code=500, detail="Failed to create lead")

    lead_number = lead_row.get("lead_number")
    print(
        "[admissions] lead created",
        {"lead_id": lead_row.get("id"), "lead_number": lead_number},
    )
    return (
        f"Lead creado con folio L-{lead_number}."
        if lead_number
        else "Lead creado."
    )


def _update_admissions_lead(
    request: UpdateAdmissionsLeadRequest,
    org: Dict[str, Any],
    chat: Dict[str, Any],
) -> str:
    supabase = get_supabase_client()
    print("[admissions] update lead payload", request.model_dump(exclude_none=True))
    org_id = org.get("id")
    chat_id = chat.get("id")
    wa_id = chat.get("wa_id")
    if not org_id or not chat_id:
        raise HTTPException(status_code=400, detail="Missing org or chat id")

    lead_response = (
        supabase.from_("leads")
        .select("id, lead_number, contact_id, metadata")
        .eq("organization_id", org_id)
        .eq("wa_chat_id", chat_id)
        .maybe_single()
        .execute()
    )
    lead_error = get_supabase_error(lead_response)
    lead_data = get_supabase_data(lead_response)
    if lead_error:
        raise HTTPException(status_code=500, detail="Failed to lookup lead")
    if not lead_data or not lead_data.get("id"):
        print("[admissions] lead not found for update", {"chat_id": chat_id})
        return "No encontre un lead activo para actualizar."

    lead_updates: Dict[str, Any] = {}
    if request.student_first_name:
        lead_updates["student_first_name"] = request.student_first_name
    if request.student_middle_name:
        lead_updates["student_middle_name"] = request.student_middle_name
    if request.student_last_name_paternal:
        lead_updates["student_last_name_paternal"] = request.student_last_name_paternal
    if request.student_last_name_maternal:
        lead_updates["student_last_name_maternal"] = request.student_last_name_maternal
    if request.grade_interest:
        lead_updates["grade_interest"] = request.grade_interest
        lead_updates["student_grade_interest"] = request.grade_interest
    if request.school_year:
        lead_updates["school_year"] = request.school_year
    if request.current_school:
        lead_updates["current_school"] = request.current_school
    if request.notes:
        lead_updates["notes"] = request.notes
    if request.contact_email:
        lead_updates["contact_email"] = request.contact_email
    if request.contact_phone:
        lead_updates["contact_phone"] = request.contact_phone
    if request.contact_first_name:
        lead_updates["contact_first_name"] = request.contact_first_name
    if request.contact_middle_name:
        lead_updates["contact_middle_name"] = request.contact_middle_name
    if request.contact_last_name_paternal:
        lead_updates["contact_last_name_paternal"] = request.contact_last_name_paternal
    if request.contact_last_name_maternal:
        lead_updates["contact_last_name_maternal"] = request.contact_last_name_maternal

    contact_name = _compose_full_name(
        [
            request.contact_first_name,
            request.contact_middle_name,
            request.contact_last_name_paternal,
            request.contact_last_name_maternal,
        ]
    )
    if contact_name:
        lead_updates["contact_name"] = contact_name

    metadata = lead_data.get("metadata") or {}
    if request.relationship:
        metadata = {**metadata, "relationship": request.relationship}
        lead_updates["metadata"] = metadata

    if lead_updates:
        update_response = (
            supabase.from_("leads")
            .update(lead_updates)
            .eq("id", lead_data.get("id"))
            .execute()
        )
        update_error = get_supabase_error(update_response)
        if update_error:
            raise HTTPException(status_code=500, detail="Failed to update lead")
        print(
            "[admissions] lead updated",
            {"lead_id": lead_data.get("id"), "updates": lead_updates},
        )

    contact_id = lead_data.get("contact_id")
    contact_updates: Dict[str, Any] = {}
    if request.contact_first_name:
        contact_updates["first_name"] = request.contact_first_name
    if request.contact_middle_name:
        contact_updates["middle_name"] = request.contact_middle_name
    if request.contact_last_name_paternal:
        contact_updates["last_name_paternal"] = request.contact_last_name_paternal
    if request.contact_last_name_maternal:
        contact_updates["last_name_maternal"] = request.contact_last_name_maternal
    if request.contact_email:
        contact_updates["email"] = request.contact_email
    if request.contact_phone:
        contact_updates["phone"] = request.contact_phone
    if wa_id:
        contact_updates["whatsapp_wa_id"] = wa_id

    if contact_updates and contact_id:
        contact_response = (
            supabase.from_("crm_contacts")
            .update(contact_updates)
            .eq("id", contact_id)
            .execute()
        )
        contact_error = get_supabase_error(contact_response)
        if contact_error:
            raise HTTPException(status_code=500, detail="Failed to update contact")
        print(
            "[admissions] contact updated",
            {"contact_id": contact_id, "updates": contact_updates},
        )

    lead_number = lead_data.get("lead_number")
    return (
        f"Lead L-{lead_number} actualizado."
        if lead_number
        else "Lead actualizado."
    )


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


def _load_lead_context(org_id: str, chat_id: str) -> Optional[str]:
    supabase = get_supabase_client()
    response = (
        supabase.from_("leads")
        .select(
            "id, lead_number, student_first_name, student_middle_name, "
            "student_last_name_paternal, student_last_name_maternal, "
            "grade_interest, current_school, contact_name, contact_email, contact_phone"
        )
        .eq("organization_id", org_id)
        .eq("wa_chat_id", chat_id)
        .maybe_single()
        .execute()
    )
    lead_error = get_supabase_error(response)
    lead_data = get_supabase_data(response)
    if lead_error or not lead_data:
        return None

    lead_number = lead_data.get("lead_number")
    student_name = _compose_full_name(
        [
            lead_data.get("student_first_name"),
            lead_data.get("student_middle_name"),
            lead_data.get("student_last_name_paternal"),
            lead_data.get("student_last_name_maternal"),
        ]
    )
    missing = []
    if not lead_data.get("current_school"):
        missing.append("colegio de procedencia")
    if not lead_data.get("grade_interest"):
        missing.append("grado de interes")
    if not lead_data.get("contact_name"):
        missing.append("nombre del tutor")
    if not lead_data.get("contact_email"):
        missing.append("correo del tutor")
    if not lead_data.get("contact_phone"):
        missing.append("telefono del tutor")

    missing_text = ", ".join(missing) if missing else "ninguno"
    lead_label = f"L-{lead_number}" if lead_number else "sin folio"
    return (
        "Lead existente: "
        f"folio {lead_label}. "
        f"Alumno: {student_name or 'sin nombre'}. "
        f"Grado: {lead_data.get('grade_interest') or 'sin dato'}. "
        f"Escuela actual: {lead_data.get('current_school') or 'sin dato'}. "
        f"Tutor: {lead_data.get('contact_name') or 'sin dato'}. "
        f"Correo: {lead_data.get('contact_email') or 'sin dato'}. "
        f"Telefono: {lead_data.get('contact_phone') or 'sin dato'}. "
        f"Faltantes: {missing_text}."
    )


@router.post("/process")
def process_queue(
    payload: ProcessQueueRequest,
    authorization: Optional[str] = Header(default=None),
):
    _require_cron_secret(authorization)
    print("[admissions] process_queue", {"chat_id": payload.chat_id})

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
    print("[admissions] chat loaded", {"chat_id": chat.get("id")})

    org_response = (
        supabase.from_("organizations")
        .select(
            "id, name, bot_name, bot_instructions, bot_tone, bot_language, bot_model, phone_number_id"
        )
        .eq("id", chat.get("organization_id"))
        .single()
        .execute()
    )
    org_error = get_supabase_error(org_response)
    org = get_supabase_data(org_response)

    if org_error or not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    print("[admissions] org loaded", {"org_id": org.get("id")})

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

    all_messages = _load_session_messages(session_id)

    history: List[Dict[str, str]] = []
    pending_user_texts: List[str] = []

    last_assistant_index = -1
    for index, message in enumerate(all_messages):
        if message.get("role") == "assistant":
            last_assistant_index = index

    for message in all_messages[: last_assistant_index + 1]:
        role = message.get("role")
        body = message.get("body")
        if not body or not role:
            continue
        history.append({"role": role, "content": body})

    for message in all_messages[last_assistant_index + 1 :]:
        role = message.get("role")
        body = message.get("body")
        if role == "user" and body:
            pending_user_texts.append(body)

    combined_user = payload.final_message or " ".join(pending_user_texts)
    if not combined_user:
        return {"status": "skipped", "reason": "no_user_message"}
    print("[admissions] combined user", {"text": combined_user})
    # print(
    #     "[admissions] history",
    #     {"count": len(history), "messages": history},
    # )
    # print("----------- HISTORY LINES -----------")
    # for i, msg in enumerate(history):
    #     print(f"[{i}] {msg.get('role')}: {msg.get('content')}")
    # print("-------------------------------------")

    has_assistant_history = any(
        message.get("role") == "assistant" for message in history
    )

    lead_context = _load_lead_context(org.get("id"), chat.get("id"))
    messages_payload = [
        {"role": "system", "content": _build_prompt(org)},
        *(
            [
                {
                    "role": "system",
                    "content": "El usuario ya fue saludado en esta conversacion.",
                }
            ]
            if has_assistant_history
            else []
        ),
        *(
            [{"role": "system", "content": lead_context}]
            if lead_context
            else []
        ),
        *history,
        {"role": "user", "content": combined_user},
    ]

    tools = [
        {
            "type": "function",
            "function": {
                "name": "create_admissions_lead",
                "description": "Create an admissions lead once the required data is collected",
                "parameters": CreateAdmissionsLeadRequest.model_json_schema(),
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_admissions_lead",
                "description": "Update an admissions lead with additional details",
                "parameters": UpdateAdmissionsLeadRequest.model_json_schema(),
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_admission_requirements",
                "description": "Get and send the admission requirements document (PDF) for a specific school division. Use this when the user asks for requirements.",
                "parameters": GetRequirementsRequest.model_json_schema(),
            },
        },
    ]

    model = org.get("bot_model")
    if not isinstance(model, str) or not model.startswith("grok"):
        model = "grok-4"
    grok_client = get_grok_client()
    completion = grok_client.chat.completions.create(
        model=model,
        messages=messages_payload,
        tools=tools,
    )
    assistant_message = completion.choices[0].message
    assistant_text = assistant_message.content or ""
    tool_calls = assistant_message.tool_calls or []
    print(
        "[admissions] grok response",
        {"assistant_text": assistant_text, "tool_calls": len(tool_calls)},
    )

    if tool_calls:
        messages_payload.append(
            {
                "role": "assistant",
                "content": assistant_text,
                "tool_calls": [
                    tool_call.model_dump() for tool_call in tool_calls
                ],
            }
        )
        for tool_call in tool_calls:
            tool_name = tool_call.function.name
            tool_args_json = tool_call.function.arguments
            tool_result = "No se pudo ejecutar la accion solicitada."
            print(
                "[admissions] tool call received",
                {"tool_name": tool_name, "args": tool_args_json},
            )
            if tool_name == "create_admissions_lead":
                try:
                    tool_args = CreateAdmissionsLeadRequest.model_validate_json(
                        tool_args_json
                    )
                    tool_result = _create_admissions_lead(
                        tool_args, org=org, chat=chat
                    )
                except HTTPException as exc:
                    tool_result = f"No se pudo crear el lead: {exc.detail}"
                except Exception:
                    tool_result = (
                        "No se pudo crear el lead: datos incompletos o invalidos."
                    )
            elif tool_name == "update_admissions_lead":
                try:
                    tool_args = UpdateAdmissionsLeadRequest.model_validate_json(
                        tool_args_json
                    )
                    tool_result = _update_admissions_lead(
                        tool_args, org=org, chat=chat
                    )
                except HTTPException as exc:
                    tool_result = f"No se pudo actualizar el lead: {exc.detail}"
                except Exception:
                    tool_result = (
                        "No se pudo actualizar el lead: datos invalidos."
                    )
            elif tool_name == "get_admission_requirements":
                try:
                    tool_args = GetRequirementsRequest.model_validate_json(
                        tool_args_json
                    )
                    tool_result = _send_requirements(
                        tool_args, org=org, chat=chat, session_id=session_id
                    )
                except Exception as exc:
                    tool_result = f"Error al enviar requisitos: {str(exc)}"

            print(
                "[admissions] tool result",
                {"tool_name": tool_name, "result": tool_result},
            )
            messages_payload.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result,
                }
            )
        followup = grok_client.chat.completions.create(
            model=model,
            messages=messages_payload,
            tools=tools,
        )
        assistant_text = followup.choices[0].message.content or ""

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


class GetRequirementsRequest(BaseModel):
    division: str  # prenursery, early_child, elementary, middle_school, high_school


def _send_requirements(
    request: GetRequirementsRequest,
    org: Dict[str, Any],
    chat: Dict[str, Any],
    session_id: str,
) -> str:
    supabase = get_supabase_client()
    division = request.division.lower().strip()
    valid_divisions = {
        "prenursery",
        "early_child",
        "elementary",
        "middle_school",
        "high_school",
    }
    if division not in valid_divisions:
        return f"Division invalida: {division}. Divisiones validas: {', '.join(valid_divisions)}"

    print(f"[admissions] fetching requirements for {division}")
    
    # 1. Fetch document metadata from DB
    doc_response = (
        supabase.from_("admission_requirement_documents")
        .select("*")
        .eq("organization_id", org.get("id"))
        .eq("division", division)
        .eq("is_active", True)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    docs = get_supabase_data(doc_response)
    if not docs:
        return f"No hay documento de requisitos configurado para la division {division}."
    
    doc = docs[0]
    file_path = doc.get("file_path")
    bucket = doc.get("storage_bucket")
    file_name = doc.get("file_name") or f"Requisitos_{division}.pdf"
    
    if not file_path or not bucket:
        return "Error de configuracion: falta bucket o path del archivo."

    # 2. Download file from Supabase Storage
    try:
        print(f"[admissions] downloading {file_path} from {bucket}")
        file_bytes = supabase.storage.from_(bucket).download(file_path)
    except Exception as exc:
        print(f"[admissions] storage download error: {exc}")
        return "No se pudo descargar el documento de requisitos."
        
    # 3. Upload to WhatsApp
    try:
        import base64
        media_b64 = base64.b64encode(file_bytes).decode("utf-8")
        
        upload_params = UploadWhatsAppMediaParams(
            phone_number_id=org.get("phone_number_id"),
            media_base64=media_b64,
            mime_type="application/pdf",
            file_name=file_name,
        )
        upload_result = upload_whatsapp_media(upload_params)
        
        if upload_result.error or not upload_result.media_id:
            print(f"[admissions] whatsapp upload error: {upload_result.error}")
            return "Error al subir el documento a WhatsApp."
            
        media_id = upload_result.media_id
        
        # 4. Send Document to User
        send_params = SendWhatsAppDocumentParams(
            phone_number_id=org.get("phone_number_id"),
            to=chat.get("wa_id"),
            media_id=media_id,
            file_name=file_name,
            caption=f"Requisitos de admisión para {division.replace('_', ' ').title()}",
        )
        send_result = send_whatsapp_document(send_params)
        
        # 5. Log Outbound Message
        message_payload = {
            "chat_id": chat.get("id"),
            "chat_session_id": session_id,
            "wa_message_id": send_result.message_id,
            "body": f"[Documento enviado: {file_name}]",
            "type": "document",
            "status": "sent" if not send_result.error else "failed",
            "direction": "outbound",
            "role": "assistant",
            "payload": {
                "source": "tool_requirements",
                "division": division,
                "file_path": file_path,
                "error": send_result.error,
            },
            "sender_name": org.get("bot_name"),
            "media_id": media_id,
            "media_path": file_path, # Or storage path
            "media_file_name": file_name,
            "created_at": datetime.utcnow().isoformat(),
        }
        supabase.from_("messages").insert(message_payload).execute()
        
        if send_result.error:
            return f"Error al enviar el documento: {send_result.error}"
            
        return f"Documento de requisitos para {division} enviado exitosamente al usuario."
        
    except Exception as exc:
        print(f"[admissions] send requirements exception: {exc}")
        return "Error inesperado al enviar requisitos."


@router.get("/chats/{chat_id}/history")
def get_chat_history_endpoint(chat_id: str):
    """
    Retrieves the chat history for a given chat_id using the active session or the latest one.
    Useful for debugging and prompt improvement.
    """
    supabase = get_supabase_client()

    # 1. Get Chat to find active session
    chat_response = (
        supabase.from_("chats")
        .select("id, active_session_id")
        .eq("id", chat_id)
        .single()
        .execute()
    )
    # Handle error or missing chat
    chat_data = get_supabase_data(chat_response)
    if not chat_data:
        raise HTTPException(status_code=404, detail="Chat not found")

    session_id = chat_data.get("active_session_id")

    # 2. If no active session, try to find the last created session
    if not session_id:
        session_fetch = (
            supabase.from_("chat_sessions")
            .select("id")
            .eq("chat_id", chat_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = get_supabase_data(session_fetch)
        if rows:
            session_id = rows[0]["id"]

    if not session_id:
        return {
            "chat_id": chat_id,
            "session_id": None,
            "history": [],
            "note": "No session found for this chat",
        }

    # 3. Load messages using existing logic
    messages = _load_session_messages(session_id)

    # 4. Format output
    history = []
    for msg in messages:
        # Sort key used in _load_session_messages ensures order
        role = msg.get("role")
        content = msg.get("body")
        if role and content:
            history.append({"role": role, "content": content})

    return {
        "chat_id": chat_id,
        "session_id": session_id,
        "count": len(history),
        "history": history,
    }
