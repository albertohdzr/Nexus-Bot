from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.chat.service import get_openai_client, DEFAULT_MODEL
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
    SendWhatsAppReadParams,
    send_whatsapp_read,
)

# ── New modular imports ──────────────────────────────────────────
from app.whatsapp.prompt import build_prompt
from app.whatsapp.sanitizer import (
    sanitize_response,
    validate_and_fix_response,
)
from app.whatsapp.chat_state import (
    compose_full_name,
    get_chat_state,
    set_chat_state_value,
    pop_chat_state_value,
    get_leads_by_chat,
    get_lead_by_chat,
    append_lead_note,
    append_pending_note,
    drain_pending_notes,
    get_slot_options,
    clear_slot_options,
    slot_id_from_selection,
    slot_id_allowed,
    get_pending_event,
    ensure_active_session,
)
from app.whatsapp.tools import (
    CreateAdmissionsLeadRequest,
    UpdateAdmissionsLeadRequest,
    AddLeadNoteRequest,
    CloseChatSessionRequest,
    SearchSlotsRequest,
    BookAppointmentRequest,
    CancelAppointmentRequest,
    GetNextEventRequest,
    RegisterEventRequest,
    GetRequirementsRequest,
    build_tools_list,
)

# ── Backward-compatible aliases (used throughout this file) ──────
# These allow the existing code (with underscore prefixes) to keep
# working while we progressively migrate.  Remove once all internal
# callers have been updated.

_build_prompt = build_prompt
_sanitize_assistant_response = sanitize_response
_validate_and_fix_response = validate_and_fix_response
_compose_full_name = compose_full_name
_get_chat_state = get_chat_state
_set_chat_state_value = set_chat_state_value
_pop_chat_state_value = pop_chat_state_value
_get_leads_by_chat = get_leads_by_chat
_get_lead_by_chat = get_lead_by_chat
_append_lead_note = append_lead_note
_append_pending_note = append_pending_note
_drain_pending_notes = drain_pending_notes
_get_slot_options = get_slot_options
_clear_slot_options = clear_slot_options
_slot_id_from_selection = slot_id_from_selection
_slot_id_allowed = slot_id_allowed
_get_pending_event = get_pending_event
_ensure_active_session = ensure_active_session

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])


class ProcessQueueRequest(BaseModel):
    chat_id: str
    final_message: Optional[str] = None


class CloseChatSessionEndpointRequest(BaseModel):
    chat_id: str
    org_id: str
    model: str = DEFAULT_MODEL


def _require_cron_secret(authorization: Optional[str]) -> None:
    if not settings.cron_secret:
        raise HTTPException(status_code=500, detail="CRON_SECRET is not set")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization.split("Bearer ", 1)[1].strip()
    if token != settings.cron_secret:
        raise HTTPException(status_code=403, detail="Forbidden")


# ── Remaining inline helpers (not yet modularised) ───────────────

# (prompt logic moved to app.whatsapp.prompt)
# (continued prompt removal — see prompt.py)


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
    return [
        item
        for item in ordered
        if item.get("role") in {"user", "assistant"} and item.get("body")
    ]



def _extract_interest_note(text: str) -> Optional[str]:
    lowered = text.lower()
    if "robotica" in lowered or "robótica" in lowered:
        return "Interes en robotica"
    return None


def _extract_scholarship_note(text: str) -> Optional[str]:
    lowered = text.lower()
    if any(term in lowered for term in ["beca", "becas", "descuento", "descuentos", "herman"]):
        return "Solicita beca/descuento"
    return None


def _parse_slot_selection(text: str, allow_bare: bool) -> Optional[int]:
    import re

    lowered = text.strip().lower()
    
    # Pattern 1: Exact match for bare numbers or with prefix ("1", "la 1", "el 1")
    if allow_bare:
        bare_match = re.match(
            r"^(?:la|el|opcion|opción)?\s*(\d{1,2})\s*$", lowered
        )
        if bare_match:
            value = int(bare_match.group(1))
            return value if 1 <= value <= 10 else None
    
    # Pattern 2: "opción X" anywhere in the text ("opción 1 funciona para mi")
    option_match = re.search(r"\b(?:opcion|opción)\s*(\d{1,2})\b", lowered)
    if option_match:
        value = int(option_match.group(1))
        return value if 1 <= value <= 10 else None
    
    # Pattern 3: "la X" or "el X" at the start ("la 1", "el 2")
    prefix_match = re.match(r"^(?:la|el)\s+(\d{1,2})\b", lowered)
    if prefix_match:
        value = int(prefix_match.group(1))
        return value if 1 <= value <= 10 else None
    
    # Pattern 4: Just a number with optional text after ("1", "1 por favor")
    if allow_bare:
        starts_with_num = re.match(r"^(\d{1,2})(?:\s|$|\.|,)", lowered)
        if starts_with_num:
            value = int(starts_with_num.group(1))
            return value if 1 <= value <= 10 else None
    
    return None


def _match_slot_by_date_text(
    text: str,
    options: List[Dict[str, Any]],
) -> Optional[int]:
    """Try to match user text against formatted slot dates."""
    if not options:
        return None
    
    lowered = text.strip().lower()
    
    for option in options:
        starts_at = option.get("starts_at")
        ends_at = option.get("ends_at")
        if not starts_at or not ends_at:
            continue
        
        formatted = _format_slot_window_local(starts_at, ends_at)
        if not formatted:
            continue
        
        # Check if the user's text contains key parts of the formatted date
        formatted_lower = formatted.lower()
        
        # Exact or near-exact match
        if formatted_lower in lowered or lowered in formatted_lower:
            return option.get("option")
        
        # Check for day + date pattern (e.g., "jueves 15")
        import re
        day_pattern = r"(lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo)\s*(\d{1,2})"
        user_match = re.search(day_pattern, lowered)
        formatted_match = re.search(day_pattern, formatted_lower)
        
        if user_match and formatted_match:
            user_day = user_match.group(1).replace("á", "a").replace("é", "e")
            formatted_day = formatted_match.group(1).replace("á", "a").replace("é", "e")
            user_num = user_match.group(2)
            formatted_num = formatted_match.group(2)
            
            if user_day == formatted_day and user_num == formatted_num:
                return option.get("option")
    
    return None


def _extract_preferred_date(text: str) -> Optional[str]:
    import re

    lowered = text.lower()
    months = {
        "enero": 1,
        "febrero": 2,
        "marzo": 3,
        "abril": 4,
        "mayo": 5,
        "junio": 6,
        "julio": 7,
        "agosto": 8,
        "septiembre": 9,
        "setiembre": 9,
        "octubre": 10,
        "noviembre": 11,
        "diciembre": 12,
    }
    match = re.search(
        r"\b(lunes|martes|miercoles|miércoles|jueves|viernes|sabado|sábado|domingo)\s+(\d{1,2})(?:\s+de\s+([a-z]+))?",
        lowered,
    )
    if not match:
        return None
    day_num = int(match.group(2))
    month_name = match.group(3)
    now = datetime.utcnow()
    year = now.year
    if month_name and month_name in months:
        month = months[month_name]
    else:
        month = now.month
        if day_num < now.day:
            if month == 12:
                month = 1
                year += 1
            else:
                month += 1
    try:
        return datetime(year, month, day_num).strftime("%Y-%m-%d")
    except ValueError:
        return None


def _format_slot_window_local(starts_at: str, ends_at: str) -> Optional[str]:
    from datetime import timedelta

    if not starts_at or not ends_at:
        return None
    try:
        start_utc = datetime.fromisoformat(starts_at.replace("+00", "+00:00"))
        end_utc = datetime.fromisoformat(ends_at.replace("+00", "+00:00"))
    except ValueError:
        return None

    utc_offset = timedelta(hours=-6)
    start_local = start_utc + utc_offset
    end_local = end_utc + utc_offset
    days_es = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    months_es = [
        "enero",
        "febrero",
        "marzo",
        "abril",
        "mayo",
        "junio",
        "julio",
        "agosto",
        "septiembre",
        "octubre",
        "noviembre",
        "diciembre",
    ]
    day_name = days_es[start_local.weekday()]
    month_name = months_es[start_local.month - 1]
    date_str = f"{start_local.day} de {month_name} de {start_local.year}"
    start_time = start_local.strftime("%I:%M %p").lstrip("0")
    end_time = end_local.strftime("%I:%M %p").lstrip("0")
    return f"{day_name.capitalize()} {date_str}, {start_time} - {end_time}"


def _normalize_event_division(division: str) -> Optional[str]:
    if not division:
        return None
    value = division.strip().lower()
    valid_divisions = {
        "prenursery",
        "early_child",
        "elementary",
        "middle_school",
        "high_school",
    }
    return value if value in valid_divisions else None


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
            .limit(1)
            .execute()
        )
        contact_error = get_supabase_error(contact_response)
        contact_rows = get_supabase_data(contact_response) or []
        contact_data = contact_rows[0] if contact_rows else None
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

    existing_leads = _get_leads_by_chat(supabase, org_id, chat_id, wa_id)
    
    # Check if a lead exists for THIS student
    normalized_first = request.student_first_name.strip().lower()
    normalized_last = request.student_last_name_paternal.strip().lower()
    
    for lead in existing_leads:
        l_first = (lead.get("student_first_name") or "").strip().lower()
        l_last = (lead.get("student_last_name_paternal") or "").strip().lower()
        if l_first == normalized_first and l_last == normalized_last:
            lead_number = lead.get("lead_number")
            print(
                "[admissions] lead exists for student",
                {"lead_id": lead.get("id"), "lead_number": lead_number},
            )
            return (
                f"Lead ya existente con folio L-{lead_number} para {request.student_first_name}."
                if lead_number
                else f"Lead ya existente para {request.student_first_name}."
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
                "student_dob": request.student_dob,
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

    if request.notes:
        _append_lead_note(
            supabase,
            lead_row,
            org_id,
            request.notes,
            subject="Nota del bot",
        )
    pending_notes = _drain_pending_notes(supabase, chat)
    for note in pending_notes:
        _append_lead_note(supabase, lead_row, org_id, note, subject="Nota")

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
        .select("id, lead_number, contact_id, metadata, notes")
        .eq("organization_id", org_id)
        .eq("wa_chat_id", chat_id)
        .maybe_single()
        .execute()
    )
    lead_error = get_supabase_error(lead_response)
    lead_data = get_supabase_data(lead_response)
    if lead_error:
        raise HTTPException(status_code=500, detail="Failed to lookup lead")
    if (not lead_data or not lead_data.get("id")) and wa_id:
        lead_response = (
            supabase.from_("leads")
            .select("id, lead_number, contact_id, metadata, notes")
            .eq("organization_id", org_id)
            .eq("wa_id", wa_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        lead_error = get_supabase_error(lead_response)
        lead_rows = get_supabase_data(lead_response) or []
        lead_data = lead_rows[0] if lead_rows else None
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
    if request.student_dob:
        lead_updates["student_dob"] = request.student_dob
    if request.grade_interest:
        lead_updates["grade_interest"] = request.grade_interest
        lead_updates["student_grade_interest"] = request.grade_interest
    if request.school_year:
        lead_updates["school_year"] = request.school_year
    if request.current_school:
        lead_updates["current_school"] = request.current_school
    if request.notes:
        _append_lead_note(
            supabase,
            lead_data,
            org_id,
            request.notes,
            subject="Nota del bot",
        )
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

    # Update lead status if qualification is provided (e.g., 'qualified' or 'disqualified')
    if request.qualification_status:
        lead_updates["status"] = request.qualification_status

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


def _add_lead_note(
    request: AddLeadNoteRequest,
    org: Dict[str, Any],
    chat: Dict[str, Any],
) -> str:
    supabase = get_supabase_client()
    org_id = org.get("id")
    chat_id = chat.get("id")
    if not org_id or not chat_id:
        raise HTTPException(status_code=400, detail="Missing org or chat id")

    leads = _get_leads_by_chat(supabase, org_id, chat_id, wa_id=chat.get("wa_id"))
    if not leads:
        # No lead yet — save as pending note so it attaches when lead is created
        _append_pending_note(supabase, chat, request.notes)
        return (
            "Aún no hay un lead registrado, pero guardé la nota pendiente. "
            "Se agregará automáticamente cuando se cree el lead."
        )

    for lead in leads:
        _append_lead_note(
            supabase,
            lead,
            org_id,
            request.notes,
            subject=request.subject,
        )
    
    # Return info about the primary (latest) lead
    lead = leads[0]
    lead_number = lead.get("lead_number")
    return (
        f"Nota agregada al lead L-{lead_number} (y otros asociados si existen)."
        if lead_number
        else "Nota agregada a los leads."
    )


def _maybe_auto_add_interest_note(
    combined_user: str,
    org: Dict[str, Any],
    chat: Dict[str, Any],
) -> Optional[str]:
    note = _extract_interest_note(combined_user)
    if not note:
        return None
    supabase = get_supabase_client()
    leads = _get_leads_by_chat(
        supabase, org.get("id"), chat.get("id"), wa_id=chat.get("wa_id")
    )
    if not leads:
        return None
    for lead in leads:
        _append_lead_note(supabase, lead, org.get("id"), note, subject="Interes")
    return note


def _maybe_auto_add_notes(
    combined_user: str,
    org: Dict[str, Any],
    chat: Dict[str, Any],
) -> bool:
    notes = []
    interest_note = _extract_interest_note(combined_user)
    if interest_note:
        notes.append(interest_note)
    scholarship_note = _extract_scholarship_note(combined_user)
    if scholarship_note:
        notes.append(scholarship_note)
    if not notes:
        return False

    supabase = get_supabase_client()
    leads = _get_leads_by_chat(
        supabase, org.get("id"), chat.get("id"), wa_id=chat.get("wa_id")
    )
    if leads:
        for lead in leads:
            for note in notes:
                _append_lead_note(supabase, lead, org.get("id"), note, subject="Nota")
        return True
    for note in notes:
        _append_pending_note(supabase, chat, note)
    return True


def _maybe_auto_cancel(
    combined_user: str,
    history: List[Dict[str, str]],
    org: Dict[str, Any],
    chat: Dict[str, Any],
) -> Optional[str]:
    """
    Detect when user is providing a cancellation reason after being asked,
    and automatically execute the cancellation.
    """
    import re
    
    lowered = combined_user.lower().strip()
    
    # Common cancellation reason patterns
    reason_patterns = [
        r"(?:por|es por|son)?\s*(?:razones?\s+de\s+)?trabajo",
        r"(?:por|es por)?\s*(?:razones?\s+)?familiar(?:es)?",
        r"(?:por|es por)?\s*(?:la\s+)?agenda",
        r"(?:por|es por)?\s*(?:un\s+)?compromiso",
        r"(?:por|es por)?\s*(?:una\s+)?cita\s+(?:medica|médica)",
        r"(?:tengo\s+)?(?:un\s+)?viaje",
        r"(?:tengo\s+)?(?:una\s+)?junta",
        r"(?:no\s+)?(?:me\s+)?(?:puedo|funciona|acomoda)",
        r"horario\s+(?:de\s+)?trabajo",
        r"cambio\s+de\s+planes",
    ]
    
    is_likely_reason = any(re.search(pattern, lowered) for pattern in reason_patterns)
    if not is_likely_reason:
        return None
    
    # Check if recent history asked for cancellation reason
    asked_for_reason = False
    for msg in reversed(history[-5:]):
        if msg.get("role") == "assistant":
            content = (msg.get("content") or "").lower()
            if any(phrase in content for phrase in [
                "razón del cambio",
                "razon del cambio", 
                "por qué ya no",
                "porque ya no",
                "motivo del cambio",
                "dices la razón",
                "dices la razon",
                "me dices por qué",
                "me dices porque",
            ]):
                asked_for_reason = True
                break
    
    if not asked_for_reason:
        return None
    
    # Check if there's a scheduled appointment to cancel
    supabase = get_supabase_client()
    lead = _get_lead_by_chat(
        supabase, org.get("id"), chat.get("id"), wa_id=chat.get("wa_id")
    )
    if not lead or not lead.get("id"):
        return None
    
    lead_id = lead.get("id")
    appt_response = (
        supabase.from_("appointments")
        .select("id, slot_id, starts_at, ends_at")
        .eq("lead_id", lead_id)
        .eq("status", "scheduled")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    appts = get_supabase_data(appt_response) or []
    if not appts:
        return None
    
    appt = appts[0]
    appt_id = appt.get("id")
    slot_id = appt.get("slot_id")
    
    # Execute cancellation
    print(f"[admissions] auto-canceling appointment {appt_id}, reason: {combined_user}")
    
    supabase.from_("appointments").update({
        "status": "cancelled",
        "notes": f"Cancelado por usuario. Razón: {combined_user}",
        "updated_at": datetime.utcnow().isoformat(),
    }).eq("id", appt_id).execute()
    
    # Free up the slot
    if slot_id:
        slot_response = (
            supabase.from_("availability_slots")
            .select("appointments_count")
            .eq("id", slot_id)
            .single()
            .execute()
        )
        slot = get_supabase_data(slot_response)
        if slot:
            new_count = max(0, slot.get("appointments_count", 1) - 1)
            supabase.from_("availability_slots").update({
                "appointments_count": new_count,
                "updated_at": datetime.utcnow().isoformat(),
            }).eq("id", slot_id).execute()
    
    # Update lead status
    supabase.from_("leads").update({
        "status": "contacted",
        "updated_at": datetime.utcnow().isoformat(),
    }).eq("id", lead_id).execute()
    
    # Clear any stored slot options
    _clear_slot_options(supabase, lead, chat)
    
    # Get formatted cancelled appointment time for context
    formatted = _format_slot_window_local(appt.get("starts_at"), appt.get("ends_at"))
    time_text = f" del {formatted}" if formatted else ""
    
    return (
        f"¡Entendido! Tu cita{time_text} ha sido cancelada. "
        "No te preocupes, podemos reagendar cuando te convenga. 😊\n\n"
        "¿Qué días y horarios de la próxima semana te funcionarían mejor? "
        "(Por ejemplo: 'jueves o viernes por la mañana')"
    )


def _close_chat_session(
    request: CloseChatSessionRequest,
    org: Dict[str, Any],
    chat: Dict[str, Any],
    session_id: str,
) -> str:
    supabase = get_supabase_client()
    print("[admissions] close session payload", request.model_dump(exclude_none=True))

    supabase.from_("chat_sessions").update({
        "status": "closed",
        "closed_at": datetime.utcnow().isoformat(),
        "summary": request.summary,
        "updated_at": datetime.utcnow().isoformat(),
    }).eq("id", session_id).execute()

    return "Sesión cerrada correctamente y resumen guardado."


def _maybe_book_from_selection(
    combined_user: str,
    org: Dict[str, Any],
    chat: Dict[str, Any],
) -> Optional[str]:
    """Attempt to book when the user selects a slot option by number.
    
    CRITICAL DESIGN: This function ONLY books when there are REAL slot_options
    stored from a prior `search_availability_slots` call. It NEVER auto-searches
    or auto-books — doing so caused the wrong-date bug where the bot would
    grab the first available slot instead of what the user requested.
    """
    supabase = get_supabase_client()
    lead = _get_lead_by_chat(
        supabase, org.get("id"), chat.get("id"), wa_id=chat.get("wa_id")
    )
    slot_options = _get_slot_options(lead, chat)
    
    # Only parse selection if there are real slot options to match against
    if not slot_options:
        return None
    
    allow_bare = True
    selection = _parse_slot_selection(combined_user, allow_bare=allow_bare)
    
    # If no numeric selection, try matching by date text
    if not selection:
        selection = _match_slot_by_date_text(combined_user, slot_options)
    
    if not selection:
        return None
    
    # We have slot_options and a selection — try to match
    match = _slot_id_from_selection(slot_options, selection)
    if not match or not match.get("slot_id"):
        return (
            "No encontré esa opción en la lista. "
            "¿Podrías decirme el número de la opción que prefieres?"
        )
    
    # We need a lead to book
    if not lead or not lead.get("id"):
        # Save the pending selection so it can be booked after lead creation
        _set_chat_state_value(supabase, chat, "pending_slot_option", selection)
        formatted = _format_slot_window_local(
            match.get("starts_at"), match.get("ends_at")
        )
        slot_text = formatted or f"la opción {selection}"
        # Tell the LLM what's happening so it can ask for data naturally
        chat["_booking_context"] = (
            f"El usuario eligió {slot_text} para su visita. "
            "Para poder agendar necesito crear el registro de admisiones primero. "
            "Pide de forma natural los datos faltantes para crear el lead: "
            "nombre completo del alumno, nombre del tutor/padre, teléfono y correo electrónico. "
            "NO menciones la palabra 'lead' ni 'registro de admisiones' al usuario. "
            "Di algo como: 'Excelente elección. Para apartar ese horario necesito unos datos...' "
            "Una vez que tengas los datos, usa 'create_admissions_lead' y el sistema "
            "agendará la cita automáticamente."
        )
        return None  # Let the LLM ask for lead data naturally
    
    # Book the selected slot
    result = _book_appointment(
        BookAppointmentRequest(slot_id=match.get("slot_id")),
        org=org,
        chat=chat,
    )
    if not result:
        return None
    if result.lower().startswith("cita agendada exitosamente"):
        formatted = _format_slot_window_local(
            match.get("starts_at"), match.get("ends_at")
        )
        _clear_slot_options(supabase, lead, chat)
        _pop_chat_state_value(supabase, chat, "pending_slot_option")
        slot_text = formatted or "el horario seleccionado"
        # Inject booking context for the LLM to generate a natural response
        chat["_booking_context"] = (
            f"ACCIÓN COMPLETADA: La visita fue agendada exitosamente para {slot_text}. "
            "La entrada es por Puerta 3 (caseta del reloj). "
            "Confirma la cita al usuario de forma cálida y natural, menciona la fecha/hora, "
            "ofrece la ubicación si no se la has dado, y pregunta si necesita algo más. "
            "NO uses tools adicionales."
        )
        return None  # Let the LLM craft a natural response
    return result


def _maybe_book_pending_selection(
    org: Dict[str, Any],
    chat: Dict[str, Any],
) -> Optional[str]:
    """Book a pending slot selection after lead creation.
    
    Returns a string message if something went wrong, None if booking
    was handled (success injected via _booking_context) or nothing to do.
    """
    supabase = get_supabase_client()
    pending = _get_chat_state(chat).get("pending_slot_option")
    if not pending:
        return None
    lead = _get_lead_by_chat(
        supabase, org.get("id"), chat.get("id"), wa_id=chat.get("wa_id")
    )
    if not lead or not lead.get("id"):
        return None
    
    # Get slot options and validate they're not stale
    slot_options = _get_slot_options(lead, chat)
    if not slot_options:
        # No options available — clear stale pending state
        _pop_chat_state_value(supabase, chat, "pending_slot_option")
        return None
    
    # Check if slot_options are stale (older than 30 minutes)
    state = _get_chat_state(chat)
    slot_state = state.get("slot_options") or {}
    generated_at = slot_state.get("generated_at")
    if generated_at:
        try:
            gen_dt = datetime.fromisoformat(generated_at)
            age_seconds = (datetime.utcnow() - gen_dt).total_seconds()
            if age_seconds > 1800:  # 30 minutes
                print(f"[admissions] stale slot_options ({age_seconds:.0f}s old), clearing")
                _clear_slot_options(supabase, lead, chat)
                _pop_chat_state_value(supabase, chat, "pending_slot_option")
                return None
        except ValueError:
            pass
    
    match = _slot_id_from_selection(slot_options, pending)
    if not match or not match.get("slot_id"):
        _pop_chat_state_value(supabase, chat, "pending_slot_option")
        return None
    
    result = _book_appointment(
        BookAppointmentRequest(slot_id=match.get("slot_id")),
        org=org,
        chat=chat,
    )
    if result.lower().startswith("cita agendada exitosamente"):
        formatted = _format_slot_window_local(
            match.get("starts_at"), match.get("ends_at")
        )
        _clear_slot_options(supabase, lead, chat)
        _pop_chat_state_value(supabase, chat, "pending_slot_option")
        slot_text = formatted or "el horario seleccionado"
        # Inject booking context for the LLM to generate a natural response
        chat["_booking_context"] = (
            f"ACCIÓN COMPLETADA: La visita fue agendada exitosamente para {slot_text}. "
            "La entrada es por Puerta 3 (caseta del reloj). "
            "Confirma la cita al usuario de forma cálida y natural, menciona la fecha/hora, "
            "ofrece la ubicación si no se la has dado, y pregunta si necesita algo más. "
            "NO uses tools adicionales."
        )
        return None  # Let the LLM craft a natural response
    
    # Booking failed — clear pending state
    _pop_chat_state_value(supabase, chat, "pending_slot_option")
    return result




def _send_assistant_message(
    assistant_text: str,
    org: Dict[str, Any],
    chat: Dict[str, Any],
    session_id: str,
) -> Dict[str, Any]:
    supabase = get_supabase_client()
    
    # Sanitize the response before sending
    sanitized_text = _sanitize_assistant_response(assistant_text)
    
    # If sanitization resulted in empty text, use a fallback
    if not sanitized_text:
        sanitized_text = "Disculpa, hubo un problema procesando mi respuesta. ¿Podrías repetir tu pregunta?"
        print("[admissions] WARNING: Empty response after sanitization, using fallback")
    
    send_result = send_whatsapp_text(
        SendWhatsAppTextParams(
            phone_number_id=org.get("phone_number_id"),
            to=chat.get("wa_id"),
            body=sanitized_text,
        )
    )

    message_payload = {
        "chat_id": chat.get("id"),
        "chat_session_id": session_id,
        "wa_message_id": send_result.message_id,
        "body": sanitized_text,
        "type": "text",
        "status": "sent" if not send_result.error else "failed",
        "direction": "outbound",
        "role": "assistant",
        "payload": {
            "source": "openai",
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


def _load_lead_context(
    org_id: str, chat_id: str, wa_id: Optional[str] = None
) -> Optional[str]:
    supabase = get_supabase_client()
    
    # 1. Fetch ALL leads for this chat
    response = (
        supabase.from_("leads")
        .select(
            "id, lead_number, student_first_name, student_middle_name, "
            "student_last_name_paternal, student_last_name_maternal, student_dob, "
            "grade_interest, current_school, contact_name, contact_email, contact_phone, notes"
        )
        .eq("organization_id", org_id)
        .eq("wa_chat_id", chat_id)
        .order("created_at", desc=True)
        .execute()
    )
    leads = get_supabase_data(response)
    
    # Fallback to wa_id if no leads found by chat_id
    if not leads and wa_id:
        fallback_response = (
            supabase.from_("leads")
            .select(
                "id, lead_number, student_first_name, student_middle_name, "
                "student_last_name_paternal, student_last_name_maternal, student_dob, "
                "grade_interest, current_school, contact_name, contact_email, contact_phone, notes"
            )
            .eq("organization_id", org_id)
            .eq("wa_id", wa_id)
            .order("created_at", desc=True)
            .execute()
        )
        leads = get_supabase_data(fallback_response) or []

    if not leads:
        return None

    # 2. Build context string for all leads
    context_parts = []
    
    # We will check appointments for ALL lead IDs
    lead_ids = [l["id"] for l in leads]
    
    appt_response = (
        supabase.from_("appointments")
        .select("id, lead_id, starts_at, ends_at, status")
        .in_("lead_id", lead_ids)
        .eq("status", "scheduled")
        .order("created_at", desc=True)
        .execute()
    )
    all_appts = get_supabase_data(appt_response) or []
    appt_map = {a["lead_id"]: a for a in all_appts}

    for i, lead_data in enumerate(leads, 1):
        lead_number = lead_data.get("lead_number")
        lead_id = lead_data.get("id")
        
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
        if not lead_data.get("student_dob"):
            missing.append("fecha de nacimiento")
        
        # Contact info usually shared, but check anyway
        if not lead_data.get("contact_name"):
            missing.append("nombre del tutor")
        if not lead_data.get("contact_email"):
            missing.append("correo del tutor")
        if not lead_data.get("contact_phone"):
            missing.append("telefono del tutor")

        missing_text = ", ".join(missing) if missing else "ninguno"
        lead_label = f"L-{lead_number}" if lead_number else "sin folio"
        
        notes = (lead_data.get("notes") or "").strip()
        if notes and len(notes) > 100:
            notes = f"{notes[:100].rstrip()}..."
        
        # Check appointment for this specific lead
        appointment_text = ""
        if lead_id in appt_map:
            appt = appt_map[lead_id]
            formatted = _format_slot_window_local(appt.get("starts_at"), appt.get("ends_at"))
            if formatted:
                appointment_text = f"Cita programada: {formatted}"
            else:
                appointment_text = "Cita programada (fecha pendiente)"

        # Format block for this lead
        block = (
            f"LEAD {i} ({lead_label}):\n"
            f"  Alumno: {student_name}\n"
            f"  Interés: {lead_data.get('grade_interest') or 'N/A'}\n"
            f"  Datos faltantes: {missing_text}\n"
        )
        if notes:
            block += f"  Notas: {notes}\n"
        if appointment_text:
            block += f"  {appointment_text}\n"
        
        context_parts.append(block)

    full_context = "\n".join(context_parts)
    # Add shared contact info from the first lead (assuming shared)
    first = leads[0]
    contact_name = first.get("contact_name") or "N/A"
    contact_email = first.get("contact_email") or "N/A"
    contact_phone = first.get("contact_phone") or "N/A"
    
    return (
        f"DATOS DE LEADS (Familia):\n"
        f"Tutor: {contact_name} | Email: {contact_email} | Tel: {contact_phone}\n"
        f"----------------------------------------\n"
        f"{full_context}"
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
        .select("id, wa_id, organization_id, active_session_id, state_context")
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

    # Mark last message as read and show typing indicator
    last_msg_response = (
        supabase.from_("messages")
        .select("wa_message_id")
        .eq("chat_id", chat.get("id"))
        .eq("direction", "inbound")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    last_msgs = get_supabase_data(last_msg_response)
    if last_msgs and last_msgs[0].get("wa_message_id"):
        send_whatsapp_read(
            SendWhatsAppReadParams(
                phone_number_id=org.get("phone_number_id"),
                message_id=last_msgs[0].get("wa_message_id"),
                typing_type="text",
            )
        )

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

    preferred_date = _extract_preferred_date(combined_user)
    if preferred_date:
        _set_chat_state_value(supabase, chat, "preferred_date", preferred_date)

    forced_text = _maybe_book_from_selection(
        combined_user=combined_user, org=org, chat=chat
    )
    if forced_text:
        return _send_assistant_message(forced_text, org, chat, session_id)
    
    # Check if user is providing a cancellation reason after being asked
    forced_cancel = _maybe_auto_cancel(
        combined_user=combined_user,
        history=history,
        org=org,
        chat=chat,
    )
    if forced_cancel:
        return _send_assistant_message(forced_cancel, org, chat, session_id)

    has_assistant_history = any(
        message.get("role") == "assistant" for message in history
    )

    lead_context = _load_lead_context(
        org.get("id"), chat.get("id"), wa_id=chat.get("wa_id")
    )

    # ── Build instructions (replaces system messages) ──────────────
    instructions_parts = [_build_prompt(org)]
    if has_assistant_history:
        instructions_parts.append("El usuario ya fue saludado en esta conversacion.")
    if lead_context:
        instructions_parts.append(lead_context)

    # Add slot options context if available
    lead = _get_lead_by_chat(
        supabase, org.get("id"), chat.get("id"), wa_id=chat.get("wa_id")
    )
    slot_options = _get_slot_options(lead, chat)
    if slot_options:
        slot_context_lines = ["OPCIONES DE HORARIOS DISPONIBLES (usa estos IDs exactos para book_appointment):"]
        for opt in slot_options:
            formatted = _format_slot_window_local(opt.get("starts_at"), opt.get("ends_at"))
            if formatted:
                slot_context_lines.append(
                    f"- Opción {opt.get('option')}: {formatted} (slot_id: {opt.get('slot_id')})"
                )
        slot_context_lines.append("Si el usuario elige una opción, usa el slot_id correspondiente en book_appointment.")
        instructions_parts.append("\n".join(slot_context_lines))

    # If a booking was just completed (by _maybe_book_from_selection),
    # inject the context so the LLM generates a natural confirmation
    booking_context = chat.get("_booking_context")
    if booking_context:
        instructions_parts.append(booking_context)
        chat.pop("_booking_context", None)

    full_instructions = "\n\n".join(instructions_parts)

    # ── Build input (history + current user message) ──────────────
    input_messages = []
    input_messages.extend(history)
    input_messages.append({"role": "user", "content": combined_user})

    tools = build_tools_list()

    model = org.get("bot_model")
    if not isinstance(model, str) or not model.strip():
        model = DEFAULT_MODEL
    client = get_openai_client()
    try:
        response = client.responses.create(
            model=model,
            instructions=full_instructions,
            input=input_messages,
            tools=tools,
        )
        assistant_text = response.output_text or ""
        tool_calls = [
            item for item in response.output
            if item.type == "function_call"
        ]
    except Exception as exc:
        print(
            "[admissions] OpenAI API error",
            {"error": str(exc), "chat_id": chat.get("id"), "model": model},
        )
        return _send_assistant_message(
            "Disculpa, estoy teniendo dificultades técnicas en este momento. "
            "Por favor intenta de nuevo en unos minutos, o si prefieres, "
            "puedes llamarnos al 8711123687.",
            org, chat, session_id,
        )
    print(
        "[admissions] llm response",
        {"assistant_text": assistant_text, "tool_calls": len(tool_calls)},
    )


    lead_note_added = False
    booking_done = False
    booking_error_text: Optional[str] = None
    if tool_calls:
        # Collect tool outputs for the Responses API followup
        tool_outputs = []
        for tool_call in tool_calls:
            tool_name = tool_call.name
            tool_args_json = tool_call.arguments
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
                    pending_event_id = _pop_chat_state_value(
                        supabase, chat, "pending_event_registration"
                    )
                    if pending_event_id:
                        register_text = _register_event(
                            RegisterEventRequest(event_id=pending_event_id),
                            org=org,
                            chat=chat,
                            session_id=session_id,
                        )
                        tool_result = f"{tool_result} {register_text}"
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
                    if tool_args.notes:
                        lead_note_added = True
                except HTTPException as exc:
                    tool_result = f"No se pudo actualizar el lead: {exc.detail}"
                except Exception:
                    tool_result = (
                        "No se pudo actualizar el lead: datos invalidos."
                    )
            elif tool_name == "add_lead_note":
                try:
                    tool_args = AddLeadNoteRequest.model_validate_json(
                        tool_args_json
                    )
                    tool_result = _add_lead_note(
                        tool_args, org=org, chat=chat
                    )
                    lead_note_added = True
                except HTTPException as exc:
                    tool_result = f"No se pudo agregar la nota: {exc.detail}"
                except Exception:
                    tool_result = "No se pudo agregar la nota al lead."
            elif tool_name == "get_next_event":
                try:
                    tool_args = GetNextEventRequest.model_validate_json(
                        tool_args_json
                    )
                    tool_result = _get_next_event(
                        tool_args, org=org, chat=chat
                    )
                except Exception as exc:
                    tool_result = f"Error al buscar eventos: {str(exc)}"
            elif tool_name == "register_event":
                try:
                    tool_args = RegisterEventRequest.model_validate_json(
                        tool_args_json
                    )
                    tool_result = _register_event(
                        tool_args, org=org, chat=chat, session_id=session_id
                    )
                except Exception as exc:
                    tool_result = f"Error al registrar evento: {str(exc)}"
            elif tool_name == "get_admission_requirements":
                try:
                    tool_args = GetRequirementsRequest.model_validate_json(
                        tool_args_json
                    )
                    lower_user = combined_user.lower()
                    if not any(
                        term in lower_user
                        for term in [
                            "requisito",
                            "requisitos",
                            "documento",
                            "documentos",
                            "pdf",
                            "lista",
                            "papeleria",
                            "papelería",
                            "papel",
                        ]
                    ):
                        tool_result = (
                            "Solo puedo enviar requisitos si me los solicitan. "
                            "Si los necesitas, dimelo y con gusto te los envio."
                        )
                    else:
                        tool_result = _send_requirements(
                            tool_args, org=org, chat=chat, session_id=session_id
                        )
                except Exception as exc:
                    tool_result = f"Error al enviar requisitos: {str(exc)}"
            elif tool_name == "search_availability_slots":
                try:
                    tool_args = SearchSlotsRequest.model_validate_json(
                        tool_args_json
                    )
                    tool_result = _search_availability_slots(
                        tool_args, org=org, chat=chat
                    )
                except Exception as exc:
                    tool_result = f"Error al buscar horarios: {str(exc)}"
            elif tool_name == "book_appointment":
                try:
                    tool_args = BookAppointmentRequest.model_validate_json(
                        tool_args_json
                    )
                    tool_result = _book_appointment(
                        tool_args, org=org, chat=chat
                    )
                    if tool_result.lower().startswith("cita agendada exitosamente"):
                        booking_done = True
                        assistant_text = "¡Tu visita ha sido agendada exitosamente! Te esperamos con gusto."
                    elif tool_result.lower().startswith("el horario seleccionado"):
                        booking_error_text = (
                            "Para reservar necesito que elijas una opcion "
                            "de la lista enviada. Si no tienes opciones, "
                            "dime que dias te convienen."
                        )
                except Exception as exc:
                    tool_result = f"Error al agendar cita: {str(exc)}"
            elif tool_name == "cancel_appointment":
                try:
                    tool_args = CancelAppointmentRequest.model_validate_json(
                        tool_args_json
                    )
                    tool_result = _cancel_appointment(
                        tool_args, org=org, chat=chat
                    )
                except Exception as exc:
                    tool_result = f"Error al cancelar cita: {str(exc)}"
            elif tool_name == "close_chat_session":
                try:
                    tool_args = CloseChatSessionRequest.model_validate_json(
                        tool_args_json
                    )
                    tool_result = _close_chat_session(
                        tool_args, org=org, chat=chat, session_id=session_id
                    )
                except Exception as exc:
                    tool_result = f"Error al cerrar la sesión: {str(exc)}"

            print(
                "[admissions] tool result",
                {"tool_name": tool_name, "result": tool_result},
            )
            tool_outputs.append({
                "type": "function_call_output",
                "call_id": tool_call.call_id,
                "output": tool_result,
            })
        if booking_error_text and not booking_done:
            assistant_text = booking_error_text
            booking_done = True
        if not booking_done:
            pending_booking_text = _maybe_book_pending_selection(org=org, chat=chat)
            if pending_booking_text:
                assistant_text = pending_booking_text
                booking_done = True
            elif chat.get("_booking_context"):
                # _maybe_book_pending_selection injected booking_context
                # Make a targeted LLM call with booking context so it confirms naturally
                booking_ctx = chat.pop("_booking_context", "")
                followup_instructions = full_instructions + "\n\n" + booking_ctx
                try:
                    followup = client.responses.create(
                        model=model,
                        instructions=followup_instructions,
                        input=input_messages + list(response.output) + tool_outputs,
                    )
                    assistant_text = followup.output_text or ""
                except Exception:
                    # If LLM fails, use a simple confirmation
                    assistant_text = (
                        "¡Excelente! Ya quedaron registrados tus datos y tu visita fue agendada. "
                        "Te esperamos. 😊"
                    )
                booking_done = True
        if not booking_done:
            # ── Agentic loop: keep executing tools until model responds ──
            MAX_TOOL_ROUNDS = 5
            accumulated_input = input_messages + list(response.output) + tool_outputs
            for round_idx in range(MAX_TOOL_ROUNDS):
                try:
                    followup = client.responses.create(
                        model=model,
                        instructions=full_instructions,
                        input=accumulated_input,
                        tools=tools,
                    )
                except Exception as exc:
                    print(
                        "[admissions] OpenAI followup error",
                        {"error": str(exc), "round": round_idx, "chat_id": chat.get("id")},
                    )
                    # Context-aware fallback
                    executed_tools = [t.name for t in tool_calls] if tool_calls else []
                    if "create_admissions_lead" in executed_tools:
                        assistant_text = (
                            "¡Excelente! Ya quedaron registrados tus datos en admisiones. 🎉 "
                            "El siguiente paso es conocer el campus, ¿te gustaría que busque "
                            "horarios disponibles para una visita?"
                        )
                    elif "book_appointment" in executed_tools:
                        assistant_text = "Tu solicitud de cita fue procesada. ¿Necesitas algo más?"
                    else:
                        assistant_text = "Tu solicitud fue procesada correctamente. ¿En qué más puedo ayudarte?"
                    break

                followup_tool_calls = [
                    item for item in followup.output if item.type == "function_call"
                ]

                if not followup_tool_calls:
                    # Model produced text — we're done
                    assistant_text = followup.output_text or ""
                    break

                # Model wants more tools — execute them
                print(
                    "[admissions] followup tool round",
                    {"round": round_idx + 1, "tools": [t.name for t in followup_tool_calls]},
                )
                followup_outputs = []
                for tc in followup_tool_calls:
                    tool_name = tc.name
                    tool_args_json = tc.arguments
                    tool_result = "No se pudo ejecutar la accion solicitada."
                    if tool_name in tool_dispatch:
                        request_cls, handler = tool_dispatch[tool_name]
                        try:
                            parsed_args = request_cls.model_validate_json(tool_args_json)
                            tool_result = handler(parsed_args)
                        except Exception as tool_exc:
                            tool_result = f"Error ejecutando {tool_name}: {tool_exc}"
                    print(
                        f"[admissions] tool call received",
                        {"tool_name": tool_name, "args": tool_args_json[:120]},
                    )
                    print(
                        f"[admissions] tool result",
                        {"tool_name": tool_name, "result": tool_result[:200]},
                    )
                    # Track for note detection
                    tool_calls.append(tc)
                    if tool_name in ("add_lead_note", "update_admissions_lead"):
                        lead_note_added = True

                    followup_outputs.append({
                        "type": "function_call_output",
                        "call_id": tc.call_id,
                        "output": tool_result,
                    })

                # Extend accumulated input for next round
                accumulated_input = accumulated_input + list(followup.output) + followup_outputs
            else:
                # Exhausted all rounds without getting text
                print("[admissions] WARNING: exhausted tool rounds without text response")
                assistant_text = "Tu solicitud fue procesada correctamente. ¿En qué más puedo ayudarte?"

    if not lead_note_added:
        _maybe_auto_add_notes(combined_user, org=org, chat=chat)

    # Post-response validation: detect invented responses
    assistant_text = _validate_and_fix_response(
        assistant_text, combined_user, tool_calls, lead, chat
    )

    return _send_assistant_message(assistant_text, org, chat, session_id)



def _cancel_appointment(
    request: CancelAppointmentRequest,
    org: Dict[str, Any],
    chat: Dict[str, Any],
) -> str:
    supabase = get_supabase_client()
    print(f"[admissions] cancelling appointment, reason: {request.cancellation_reason}")
    
    # 1. Find leads for this chat
    leads = _get_leads_by_chat(supabase, org.get("id"), chat.get("id"))
    if not leads:
        return "No encontré un lead activo para cancelar cita."
    
    lead_ids = [l["id"] for l in leads]
    
    # 2. Find scheduled appointment for ANY of these leads
    appt_response = (
        supabase.from_("appointments")
        .select("id, slot_id")
        .in_("lead_id", lead_ids)
        .eq("status", "scheduled")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    appts = get_supabase_data(appt_response)
    if not appts:
        return "No encontré una cita activa para cancelar."
    
    appt = appts[0]
    appt_id = appt.get("id")
    slot_id = appt.get("slot_id")
    
    # 3. Update appointment to cancelled with reason
    supabase.from_("appointments").update({
        "status": "cancelled",
        "notes": f"Cancelado por usuario. Razón: {request.cancellation_reason}",
        "updated_at": datetime.utcnow().isoformat(),
    }).eq("id", appt_id).execute()
    
    # 4. Free up the slot (decrement count)
    if slot_id:
        slot_response = (
            supabase.from_("availability_slots")
            .select("appointments_count")
            .eq("id", slot_id)
            .single()
            .execute()
        )
        slot = get_supabase_data(slot_response)
        if slot:
            new_count = max(0, slot.get("appointments_count", 1) - 1)
            supabase.from_("availability_slots").update({
                "appointments_count": new_count,
                "updated_at": datetime.utcnow().isoformat(),
            }).eq("id", slot_id).execute()
    
    # 5. Update leads status back to contacted (ALL associated leads)
    supabase.from_("leads").update({
        "status": "contacted",
        "updated_at": datetime.utcnow().isoformat(),
    }).in_("id", lead_ids).execute()
    
    print(f"[admissions] appointment {appt_id} cancelled successfully")
    
    return "Cita cancelada exitosamente. El lead ha sido actualizado. Intenta convencer al usuario de agendar otra visita preguntando qué fechas le convendrían mejor."


def _search_availability_slots(
    request: SearchSlotsRequest,
    org: Dict[str, Any],
    chat: Dict[str, Any],
) -> str:
    from datetime import timedelta

    supabase = get_supabase_client()
    print(
        f"[admissions] searching slots from {request.start_date} to {request.end_date}"
        f" preferred_time={request.preferred_time}"
    )
    
    # Validate dates
    try:
        start_dt = datetime.fromisoformat(request.start_date)
        end_dt = datetime.fromisoformat(request.end_date)
    except ValueError:
        return "Formato de fechas invalido. Usa YYYY-MM-DD."

    # Don't allow past dates
    today = datetime.utcnow().date()
    if end_dt.date() < today:
        return "Las fechas solicitadas ya pasaron. Busca con fechas futuras."
    
    # Don't allow same-day bookings
    if start_dt.date() <= today:
        start_dt = datetime(today.year, today.month, today.day) + timedelta(days=1)
        request_start = start_dt.strftime("%Y-%m-%d")
    else:
        request_start = request.start_date

    # Query all active slots in the date range
    response = (
        supabase.from_("availability_slots")
        .select("id, starts_at, ends_at, max_appointments, appointments_count")
        .eq("organization_id", org.get("id"))
        .eq("is_active", True)
        .eq("is_blocked", False)
        .gte("starts_at", request_start)
        .lte("ends_at", f"{request.end_date} 23:59:59")
        .order("starts_at", desc=False)
        .execute()
    )
    
    slots = get_supabase_data(response) or []
    
    # Torreón timezone offset (UTC-6, no DST in Coahuila)
    utc_offset = timedelta(hours=-6)
    
    # Business hours: 8:00 AM - 3:00 PM local time
    BUSINESS_HOUR_START = 8   # 8:00 AM
    BUSINESS_HOUR_END = 15    # 3:00 PM
    
    # Morning/afternoon split at noon
    MORNING_END = 12   # 12:00 PM
    AFTERNOON_START = 12  # 12:00 PM
    
    available_slots = []
    for slot in slots:
        # Check capacity
        count = slot.get("appointments_count", 0)
        max_app = slot.get("max_appointments", 1)
        if count >= max_app:
            continue
        
        # Parse start time and convert to local
        starts_at = slot.get("starts_at")
        if not starts_at:
            continue
        try:
            start_utc = datetime.fromisoformat(starts_at.replace("+00", "+00:00"))
            start_local = start_utc + utc_offset
        except (ValueError, AttributeError):
            continue
        
        # Exclude weekends (Saturday=5, Sunday=6)
        if start_local.weekday() >= 5:
            continue
        
        # Exclude outside business hours
        if start_local.hour < BUSINESS_HOUR_START or start_local.hour >= BUSINESS_HOUR_END:
            continue
        
        # Apply preferred_time filter
        preferred = (request.preferred_time or "").lower().strip()
        if preferred == "morning" and start_local.hour >= MORNING_END:
            continue
        if preferred == "afternoon" and start_local.hour < AFTERNOON_START:
            continue
        
        available_slots.append(slot)
    
    if not available_slots:
        preferred_label = ""
        if request.preferred_time == "morning":
            preferred_label = " por la mañana"
        elif request.preferred_time == "afternoon":
            preferred_label = " por la tarde"
        return (
            f"No hay horarios disponibles{preferred_label} del {request.start_date} "
            f"al {request.end_date}. Prueba con otras fechas o un horario diferente."
        )

    # Build options (max 8 to keep messages short for WhatsApp)
    options: List[Dict[str, Any]] = []
    for idx, s in enumerate(available_slots[:8], start=1):
        options.append(
            {
                "option": idx,
                "slot_id": s.get("id"),
                "starts_at": s.get("starts_at"),
                "ends_at": s.get("ends_at"),
            }
        )

    # Save slot options to state
    slot_state = {
        "generated_at": datetime.utcnow().isoformat(),
        "options": options,
    }
    _set_chat_state_value(supabase, chat, "slot_options", slot_state)
    _pop_chat_state_value(supabase, chat, "pending_slot_option")

    # Also save to lead metadata if available
    lead = _get_lead_by_chat(
        supabase, org.get("id"), chat.get("id"), wa_id=chat.get("wa_id")
    )
    if lead and lead.get("id"):
        metadata = lead.get("metadata") or {}
        metadata["slot_options"] = slot_state
        supabase.from_("leads").update(
            {"metadata": metadata, "updated_at": datetime.utcnow().isoformat()}
        ).eq("id", lead.get("id")).execute()
    
    # Format results for the LLM to present to the user
    result_text = "Horarios disponibles (hora local Torreón):\n"
    for idx, s in enumerate(available_slots[:8], start=1):
        start_str = s.get("starts_at")
        end_str = s.get("ends_at")
        formatted = _format_slot_window_local(start_str, end_str)
        if formatted:
            result_text += f"- Opción {idx}: {formatted}\n"
        else:
            result_text += f"- Opción {idx}: {start_str} - {end_str}\n"
    
    result_text += "\nPregunta al usuario cuál opción prefiere (por número)."
    return result_text


def _book_appointment(
    request: BookAppointmentRequest,
    org: Dict[str, Any],
    chat: Dict[str, Any],
) -> str:
    supabase = get_supabase_client()
    print(f"[admissions] booking appointment for slot {request.slot_id}")
    try:
        import uuid

        uuid.UUID(request.slot_id)
    except ValueError:
        return "El horario seleccionado no es valido. Indica el numero de la opcion."

    lead = _get_lead_by_chat(
        supabase, org.get("id"), chat.get("id"), wa_id=chat.get("wa_id")
    )
    if not _slot_id_allowed(request.slot_id, lead, chat):
        return "El horario seleccionado no corresponde a las opciones enviadas. Elige una opcion de la lista."
    
    # 1. Verify Slot
    slot_response = (
        supabase.from_("availability_slots")
        .select("*")
        .eq("id", request.slot_id)
        .maybe_single()
        .execute()
    )
    slot = get_supabase_data(slot_response)
    if not slot:
        return "El horario seleccionado no existe."
        
    if slot.get("appointments_count", 0) >= slot.get("max_appointments", 1):
        return "El horario seleccionado ya esta lleno."
        
    # 2. Get Lead ID (Required)
    if not lead:
        lead_response = (
            supabase.from_("leads")
            .select("id")
            .eq("wa_chat_id", chat.get("id"))
            .eq("organization_id", org.get("id"))
            .maybe_single()
            .execute()
        )
        lead = get_supabase_data(lead_response)
    # If multiple leads, we use the primary (first/latest) for the actual appointment record
    # but update status for all.
    leads = _get_leads_by_chat(supabase, org.get("id"), chat.get("id"), wa_id=chat.get("wa_id"))
    
    if not leads:
        return "No encontre un lead activo para agendar. Crea el lead primero."
    
    primary_lead = leads[0]
    lead_id = primary_lead.get("id")

    # 3. Create Appointment (linked to primary lead)
    appt_payload = {
        "organization_id": org.get("id"),
        "lead_id": lead_id,
        "slot_id": request.slot_id,
        "starts_at": slot.get("starts_at"),
        "ends_at": slot.get("ends_at"),
        "status": "scheduled",
        "notes": request.notes or "Agendado via WhatsApp Bot",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    
    appt_insert = supabase.from_("appointments").insert(appt_payload).execute()
    if get_supabase_error(appt_insert):
        return "Error al crear la cita en base de datos."
        
    # 4. Update Slot Count
    new_count = slot.get("appointments_count", 0) + 1
    supabase.from_("availability_slots").update(
        {"appointments_count": new_count}
    ).eq("id", request.slot_id).execute()
    
    # 5. Update Lead Status (For ALL leads sharing this contact)
    for l in leads:
        lid = l.get("id")
        # Update status
        supabase.from_("leads").update(
            {"status": "visit_scheduled", "updated_at": datetime.utcnow().isoformat()}
        ).eq("id", lid).execute()
        
        # Add a note explaining the shared visit if it's not the primary one
        if lid != lead_id:
             _append_lead_note(
                supabase,
                l,
                org.get("id"),
                f"Visita agendada (compartida con lead {primary_lead.get('lead_number')}) para {slot.get('starts_at')}",
                subject="Cita Agendada"
            )

    return "Cita agendada exitosamente. El lead (y hermanos) ha sido actualizado a 'visit_scheduled'."



def _get_next_event(
    request: GetNextEventRequest,
    org: Dict[str, Any],
    chat: Dict[str, Any],
) -> str:
    supabase = get_supabase_client()
    division = _normalize_event_division(request.division)
    if not division:
        return "Division invalida. Usa prenursery, early_child, elementary, middle_school o high_school."

    now_utc = datetime.utcnow().isoformat()
    response = (
        supabase.from_("events")
        .select("id, name, description, starts_at, ends_at, requires_registration")
        .eq("organization_id", org.get("id"))
        .contains("divisions", [division])
        .gte("starts_at", now_utc)
        .order("starts_at", desc=False)
        .limit(1)
        .execute()
    )
    events = get_supabase_data(response) or []
    if not events:
        _pop_chat_state_value(supabase, chat, "pending_event")
        return "No hay eventos proximos para esa division."

    event = events[0]
    event_id = event.get("id")
    _set_chat_state_value(
        supabase,
        chat,
        "pending_event",
        {
            "event_id": event_id,
            "division": division,
            "requires_registration": bool(event.get("requires_registration")),
        },
    )

    lead = _get_lead_by_chat(
        supabase, org.get("id"), chat.get("id"), wa_id=chat.get("wa_id")
    )
    if lead and lead.get("id") and event_id:
        attendance_response = (
            supabase.from_("event_attendance")
            .select("id, status")
            .eq("event_id", event_id)
            .eq("lead_id", lead.get("id"))
            .maybe_single()
            .execute()
        )
        attendance = get_supabase_data(attendance_response)
        if attendance and attendance.get("id"):
            formatted = _format_slot_window_local(
                event.get("starts_at"), event.get("ends_at") or event.get("starts_at")
            )
            event_time = formatted or event.get("starts_at") or "la fecha programada"
            return (
                f"Ya estas registrado en el evento {event.get('name')} "
                f"para {event_time}."
            )

    formatted = _format_slot_window_local(
        event.get("starts_at"), event.get("ends_at") or event.get("starts_at")
    )
    event_time = formatted or event.get("starts_at") or "fecha por confirmar"
    description = (event.get("description") or "").strip()
    description_text = f" Descripcion: {description}." if description else ""
    requires = "Requiere registro." if event.get("requires_registration") else "No requiere registro."
    return (
        f"Proximo evento para {division.replace('_', ' ')}: "
        f"{event.get('name')} el {event_time}. {requires}{description_text}"
    )


def _register_event(
    request: RegisterEventRequest,
    org: Dict[str, Any],
    chat: Dict[str, Any],
    session_id: str,
) -> str:
    supabase = get_supabase_client()
    pending = _get_pending_event(chat)
    event_id = request.event_id or pending.get("event_id")
    if not event_id:
        return "No tengo un evento seleccionado para registrar."

    lead = _get_lead_by_chat(
        supabase, org.get("id"), chat.get("id"), wa_id=chat.get("wa_id")
    )
    if not lead or not lead.get("id"):
        _set_chat_state_value(supabase, chat, "pending_event_registration", event_id)
        return (
            "Para registrarte necesito algunos datos del alumno y tutor. "
            "Primero creo el lead y enseguida hago el registro."
        )

    event_response = (
        supabase.from_("events")
        .select("id, name, starts_at, ends_at, requires_registration")
        .eq("organization_id", org.get("id"))
        .eq("id", event_id)
        .maybe_single()
        .execute()
    )
    event_data = get_supabase_data(event_response)
    if not event_data:
        return "No encontre el evento seleccionado."

    attendance_response = (
        supabase.from_("event_attendance")
        .select("id, status")
        .eq("event_id", event_id)
        .eq("lead_id", lead.get("id"))
        .maybe_single()
        .execute()
    )
    attendance = get_supabase_data(attendance_response)
    if attendance and attendance.get("id"):
        return "Ya estas registrado en ese evento."

    supabase.from_("event_attendance").insert(
        {
            "organization_id": org.get("id"),
            "event_id": event_id,
            "lead_id": lead.get("id"),
            "status": "registered",
            "registered_at": datetime.utcnow().isoformat(),
        }
    ).execute()

    _pop_chat_state_value(supabase, chat, "pending_event_registration")

    doc_result = _send_event_document(
        org=org,
        chat=chat,
        session_id=session_id,
        event_id=event_id,
    )
    if doc_result:
        return f"Registro completado. {doc_result}"
    return "Registro completado. Te esperamos en el evento."


def _send_event_document(
    org: Dict[str, Any],
    chat: Dict[str, Any],
    session_id: str,
    event_id: str,
) -> Optional[str]:
    supabase = get_supabase_client()
    doc_response = (
        supabase.from_("event_documents")
        .select("*")
        .eq("organization_id", org.get("id"))
        .eq("event_id", event_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    docs = get_supabase_data(doc_response) or []
    if not docs:
        return None

    doc = docs[0]
    file_path = doc.get("file_path")
    bucket = doc.get("storage_bucket")
    file_name = doc.get("file_name") or "Documento_evento.pdf"
    mime_type = doc.get("mime_type") or "application/pdf"
    if not file_path or not bucket:
        return "No pude adjuntar el documento del evento por configuracion incompleta."

    try:
        file_bytes = supabase.storage.from_(bucket).download(file_path)
    except Exception:
        return "No pude descargar el documento del evento."

    try:
        import base64

        media_b64 = base64.b64encode(file_bytes).decode("utf-8")
        upload_params = UploadWhatsAppMediaParams(
            phone_number_id=org.get("phone_number_id"),
            media_base64=media_b64,
            mime_type=mime_type,
            file_name=file_name,
        )
        upload_result = upload_whatsapp_media(upload_params)
        if upload_result.error or not upload_result.media_id:
            return "No pude subir el documento del evento a WhatsApp."

        media_id = upload_result.media_id
        send_params = SendWhatsAppDocumentParams(
            phone_number_id=org.get("phone_number_id"),
            to=chat.get("wa_id"),
            media_id=media_id,
            file_name=file_name,
            caption="Documento del evento",
        )
        send_result = send_whatsapp_document(send_params)
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
                "source": "tool_event_document",
                "event_id": event_id,
                "file_path": file_path,
                "error": send_result.error,
            },
            "sender_name": org.get("bot_name"),
            "media_id": media_id,
            "media_path": file_path,
            "media_mime_type": mime_type,
            "created_at": datetime.utcnow().isoformat(),
        }
        supabase.from_("messages").insert(message_payload).execute()

        if send_result.error:
            return "Tu registro quedo listo, pero no pude enviar el documento."
        return "Te comparto el documento del evento."
    except Exception:
        return "Tu registro quedo listo, pero no pude enviar el documento."


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
            "media_path": file_path,
            "media_mime_type": "application/pdf",
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


@router.post("/chats/close-session")
def close_chat_session_endpoint(request: CloseChatSessionEndpointRequest):
    supabase = get_supabase_client()
    chat_response = (
        supabase.from_("chats")
        .select("id, organization_id, active_session_id")
        .eq("id", request.chat_id)
        .single()
        .execute()
    )
    chat_data = get_supabase_data(chat_response)
    if not chat_data:
        raise HTTPException(status_code=404, detail="Chat not found")
    if chat_data.get("organization_id") != request.org_id:
        raise HTTPException(
            status_code=403, detail="Chat does not belong to organization"
        )

    session_id = chat_data.get("active_session_id")
    if not session_id:
        session_fetch = (
            supabase.from_("chat_sessions")
            .select("id")
            .eq("chat_id", request.chat_id)
            .eq("organization_id", request.org_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = get_supabase_data(session_fetch) or []
        if rows:
            session_id = rows[0]["id"]

    if not session_id:
        return {
            "chat_id": request.chat_id,
            "session_id": None,
            "summary": None,
            "note": "No session found for this chat",
        }

    session_response = (
        supabase.from_("chat_sessions")
        .select("id, status, summary")
        .eq("id", session_id)
        .single()
        .execute()
    )
    session_data = get_supabase_data(session_response)
    if not session_data:
        raise HTTPException(status_code=404, detail="Chat session not found")
    if session_data.get("status") == "closed" and session_data.get("summary"):
        return {
            "chat_id": request.chat_id,
            "session_id": session_id,
            "summary": session_data.get("summary"),
            "note": "Session already closed",
        }

    messages = _load_session_messages(session_id)
    if messages:
        summary_instructions = (
            "Resume la conversacion en espanol. Incluye temas, datos clave, "
            "acuerdos y pendientes. Se claro y conciso."
        )
        summary_input = [
            {"role": msg.get("role"), "content": msg.get("body") or ""}
            for msg in messages
        ]
        client = get_openai_client()
        try:
            summary_resp = client.responses.create(
                model=request.model,
                instructions=summary_instructions,
                input=summary_input,
            )
            summary = summary_resp.output_text or ""
        except Exception as exc:
            print(
                "[admissions] OpenAI summary error",
                {"error": str(exc), "chat_id": request.chat_id},
            )
            summary = "Error al generar resumen automático."
    else:
        summary = "No hay mensajes para resumir."

    supabase.from_("chat_sessions").update({
        "status": "closed",
        "closed_at": datetime.utcnow().isoformat(),
        "summary": summary,
        "updated_at": datetime.utcnow().isoformat(),
    }).eq("id", session_id).execute()

    return {
        "chat_id": request.chat_id,
        "session_id": session_id,
        "summary": summary,
        "status": "closed",
    }
