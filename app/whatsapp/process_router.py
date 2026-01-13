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
    SendWhatsAppReadParams,
    send_whatsapp_read,
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
    student_dob: Optional[str] = None
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
    student_dob: Optional[str] = None
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


class AddLeadNoteRequest(BaseModel):
    notes: str
    subject: Optional[str] = None


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
    
    now_utc = datetime.utcnow()
    current_date = now_utc.strftime("%Y-%m-%d")
    current_time = now_utc.strftime("%H:%M:%S UTC")
    # Day of week in Spanish
    days_es = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    day_of_week = days_es[now_utc.weekday()]

    base_prompt = (
        f"Eres {bot_name}, un asistente virtual de admisiones de {school_name}. "
        f"Hoy es {day_of_week} {current_date} y la hora actual es {current_time}. "
        f"Responde en {language} con un tono {tone}. "
        "Tu objetivo es orientar a familias interesadas de forma natural y servicial. "
        "En el primer mensaje, usa un saludo breve y claro como: "
        f"'Hola, gracias por comunicarte al area de admisiones de {school_name}. "
        "¿Como puedo ayudarte?' "
        "No pidas datos personales (como nombre, correo o teléfono) de inmediato en el saludo. "
        "Primero responde a las dudas del usuario o inicia la conversación de manera amigable. "
        "Si el usuario solo saluda o no expresa intención, responde con un saludo breve y una pregunta abierta "
        "como '¿Qué te gustaría conocer?' y NO preguntes por grado ni proceso en ese primer turno. "
        "Ejemplos de primer turno cuando solo hay saludo: "
        "1) '¡Hola! Soy Vale, del área de admisiones del Colegio Americano de Torreón. ¿Qué te gustaría conocer?' "
        "2) '¡Hola! Con gusto te ayudo. ¿En qué puedo orientarte hoy?' "
        "3) '¡Hola! Estoy para ayudarte con admisiones. ¿Qué información necesitas?' "
        "Recaba los datos necesarios poco a poco y de forma integrada en la charla, no como un interrogatorio. "
        "No inventes datos. "
        "No inventes nombres de alumnos, padres o tutores. Si no tienes el nombre, usa 'tu hija' o 'tu hijo'. "
        "Nunca compartas costos, colegiaturas, cuotas ni descuentos. "
        "No hay becas ni descuentos por hermanos. Si preguntan por beca o descuentos, "
        "explica amablemente que no hay y registra una nota en el lead: 'Solicita beca/descuento'. "
        "Si preguntan por precios, explica amablemente que no puedes compartirlos por este medio y ofrece "
        "que un asesor de admisiones los contactará para darles información personalizada. "
        "Generalmente conversas con madres, padres o tutores. Usa un saludo neutro si no conoces su nombre. "
        "No saludes de nuevo si ya la conversación está iniciada. "
        "Solo di que actualizaste o guardaste datos cuando hayas ejecutado exitosamente una herramienta. "
        "Valora la fluidez y la empatía por encima de capturar los datos rápido. "
        "Datos objetivo a recolectar durante la charla (solo cuando el usuario ya mostró interés o hizo una pregunta concreta): "
        "Nombre completo del alumno, Fecha de nacimiento, Grado de interés (kinder, primaria, secundaria, prepa), "
        "Escuela actual, Nombre del tutor, Correo y Teléfono. "
        "Si hay interes y aun no tienes la fecha de nacimiento, preguntala. Es obligatoria. "
        "Si el usuario comparte intereses, preferencias o detalles relevantes (motivaciones, dudas, "
        "condiciones, contexto familiar o cualquier informacion util), "
        "guarda una nota breve en el lead usando la herramienta 'add_lead_note'. "
        "Ejemplo: 'Busca jornada extendida', 'Quiere visita con ambos padres', "
        "'Preocupacion por adaptacion', 'Solicita beca/descuento'. "
        "Solo envia el documento de requisitos si el usuario lo pide expresamente. Si no lo pide, solo OFRECE enviarlo. "
        "SÍ tienes acceso a información de requisitos. Si preguntan, responde con la información clave y OFRECE enviar el documento PDF oficial usando la herramienta 'get_admission_requirements'. "
        "Si el usuario no pidio requisitos, NO uses 'get_admission_requirements'. "
        "Si el usuario pide el PDF o la papeleria, envia el documento por WhatsApp con 'get_admission_requirements'. "
        "No digas que lo enviaste por correo ni inventes envios; solo confirma envio si la herramienta se ejecuto. "
        "Los ciclos son de agosto a junio: "
        "si el mes actual es agosto-diciembre, el ciclo actual es anio actual-anio siguiente; "
        "si el mes actual es enero-julio, el ciclo actual es anio anterior-anio actual. "
        "Si la intencion es para el ciclo actual, canaliza a un asesor y no sigas el flujo normal. "
        "Si es para el ciclo siguiente, sigue el flujo normal. "
        "Rangos de fechas de nacimiento para ciclo 2025-2026 (estrictos): "
        "Prenursery: 01-Aug-2022 a 31-Jul-2023; Nursery: 01-Aug-2021 a 31-Jul-2022; "
        "Preschool: 01-Aug-2020 a 31-Jul-2021; Kinder: 01-Aug-2019 a 31-Jul-2020; "
        "Primaria 1: 01-Aug-2018 a 31-Jul-2019; Primaria 2: 01-Aug-2017 a 31-Jul-2018; "
        "Primaria 3: 01-Aug-2016 a 31-Jul-2017; Primaria 4: 01-Aug-2015 a 31-Jul-2016; "
        "Primaria 5: 01-Aug-2014 a 31-Jul-2015; Primaria 6: 01-Aug-2013 a 31-Jul-2014; "
        "Secundaria 1: 01-Aug-2012 a 31-Jul-2013; Secundaria 2: 01-Aug-2011 a 31-Jul-2012; "
        "Secundaria 3: 01-Aug-2010 a 31-Jul-2011; Bachillerato 1: 01-Aug-2009 a 31-Jul-2010; "
        "Bachillerato 2: 01-Aug-2008 a 31-Jul-2009; Bachillerato 3: 01-Aug-2007 a 31-Jul-2008. "
        "Para ciclo 2026-2027, incrementa todos los rangos de fechas un ano. "
        "Se estricto con los rangos: si la fecha de nacimiento no cae en el rango del grado solicitado, explica y ofrece canalizar con un asesor. "
        
        "RESUMEN DE REQUISITOS (ten esto en contexto para dudas): "
        "1. PRENURSERY (MATERNAL): 4 fotos, Acta nacimiento, Carta desempeño (si aplica), Curp, Carta solvencia (nuevos), Certificado salud, Cartilla vacunación, Formatos CAT. "
        "2. EARLY CHILDHOOD (PREESCOLAR/KINDER): Similar a maternal + Reporte evaluación SEP y Carta conducta escuela anterior. "
        "3. ELEMENTARY (PRIMARIA): Fotos, Acta, Calificaciones SEP (año en curso y 2 anteriores), Certificado Preescolar (para 1ro), Carta conducta, Curp, Solvencia, Cartas recomendación. "
        "4. MIDDLE SCHOOL (SECUNDARIA): Similar primaria + Certificado Primaria. "
        "5. HIGH SCHOOL (PREPARATORIA): Promedio mínimo 8.0, Conducta condicionante. Certificado Secundaria + Papelería estándar. "

        "Para enviar el PDF usa 'get_admission_requirements' con la división correcta: "
        "'prenursery', 'early_child' (para kinder/preescolar), 'elementary' (primaria), 'middle_school' (secundaria), 'high_school' (prepa). "
        "Si no sabes la división, pregúntala antes de intentar enviar. "
        
        "OBJETIVO SECUNDARIO (VISITAS): "
        "Una vez creado el lead, tu meta es agendar una visita al campus. "
        "Pregunta qué días y horarios prefieren para visitar. "
        "Usa 'search_availability_slots' con un rango de fechas (YYYY-MM-DD) para buscar espacios. "
        "IMPORTANTE: Cuando presentes los horarios al usuario, NO muestres los IDs técnicos (UUIDs). "
        "En su lugar, presenta una lista numerada amigable (ej: 1. Lunes 13 de enero, 9:00-10:00am). "
        "Guarda internamente la relación entre el número y el ID del slot. "
        "Cuando el usuario elija (ej: 'la opción 2' o 'el de las 10am'), usa 'book_appointment' con el ID correcto. "
        "Confirma cuando la cita esté agendada. "
        "Solo confirma una cita si 'book_appointment' se ejecutó exitosamente. "
        "Nunca inventes un slot_id ni llames 'book_appointment' si no tienes un ID real de 'search_availability_slots'. "
        
        "CANCELACIÓN DE VISITAS: "
        "Si el usuario quiere cancelar su cita, primero pregunta amablemente la razón. "
        "Una vez tengas la razón, usa 'cancel_appointment' con el motivo. "
        "Después de cancelar, intenta convencer al usuario de agendar otra fecha preguntando qué días le convendrían mejor. "
        "Mantén un tono positivo y empático, sin presionar. "
        
        "CAMPUS LIFE (información que SÍ puedes compartir): "
        "🏅 DEPORTES: Alberca con calefacción solar, 5 canchas de fútbol, pista de atletismo, canchas de básquetbol y voleibol, 3 gimnasios. Educación física curricular + programa deportivo vespertino. Participación en torneos ASOMEX (19 escuelas). "
        "🎭 CENTRO DE ARTES (CVPA): Teatro profesional para 450 personas, aulas especializadas. Clases curriculares de arte + talleres vespertinos (pintura, instrumentos de cuerda/viento, teatro, danza clásica/moderna/hip hop, canto, arte digital). Grupos representativos: CATEnsemble, Jazz Band, grupo de teatro. "
        "📚 BIBLIOTECAS: 3 espacios (Early Childhood, Elementary, Middle/High). Luz natural, áreas colaborativas, recursos impresos y electrónicos en inglés y español. Enfoque en formar lectores apasionados. "
        "🚀 CLUBES Y LIDERAZGO: "
        "- Robótica FIRST: FLL Explore (1º-3º primaria), FLL Challenge (4º-6º primaria), FTC (secundaria), FRC (prepa). Competencias nacionales e internacionales. "
        "- Student Council: Representantes electos, eventos tradicionales (Halloween, San Valentín, colectas). "
        "- National Honor Society (NHS): Estudiantes destacados en carácter, estudio, servicio y liderazgo. "
        "- Equipo de Debate. "
        
        "LÍMITES DEL BOT: "
        "Si detectas que la intención del usuario NO es sobre admisiones (ej. quejas, pagos, calificaciones, situación de alumnos actuales, temas administrativos no relacionados), "
        "responde amablemente que este canal es exclusivo para admisiones y ofrece el contacto general: "
        "Teléfono: 8711123687 | Correo: contact@cat.mx"
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


def _get_chat_state(chat: Dict[str, Any]) -> Dict[str, Any]:
    return chat.get("state_context") or {}


def _set_chat_state_value(
    supabase: Any,
    chat: Dict[str, Any],
    key: str,
    value: Any,
) -> None:
    state = _get_chat_state(chat)
    state[key] = value
    supabase.from_("chats").update(
        {"state_context": state, "updated_at": datetime.utcnow().isoformat()}
    ).eq("id", chat.get("id")).execute()
    chat["state_context"] = state


def _pop_chat_state_value(
    supabase: Any,
    chat: Dict[str, Any],
    key: str,
) -> Optional[Any]:
    state = _get_chat_state(chat)
    if key not in state:
        return None
    value = state.pop(key)
    supabase.from_("chats").update(
        {"state_context": state, "updated_at": datetime.utcnow().isoformat()}
    ).eq("id", chat.get("id")).execute()
    chat["state_context"] = state
    return value


def _get_lead_by_chat(
    supabase: Any,
    org_id: str,
    chat_id: str,
) -> Optional[Dict[str, Any]]:
    response = (
        supabase.from_("leads")
        .select("id, lead_number, metadata, notes")
        .eq("organization_id", org_id)
        .eq("wa_chat_id", chat_id)
        .maybe_single()
        .execute()
    )
    if get_supabase_error(response):
        raise HTTPException(status_code=500, detail="Failed to lookup lead")
    return get_supabase_data(response)


def _append_lead_note(
    supabase: Any,
    lead: Dict[str, Any],
    org_id: str,
    note: str,
    subject: Optional[str] = None,
) -> None:
    note = note.strip()
    if not note:
        return
    existing_notes = (lead.get("notes") or "").strip()
    if note in existing_notes:
        return

    supabase.from_("lead_activities").insert(
        {
            "organization_id": org_id,
            "lead_id": lead.get("id"),
            "type": "note",
            "subject": (subject or note)[:120],
            "notes": note,
            "created_at": datetime.utcnow().isoformat(),
        }
    ).execute()

    combined = f"{existing_notes}\n{note}" if existing_notes else note
    supabase.from_("leads").update(
        {"notes": combined, "updated_at": datetime.utcnow().isoformat()}
    ).eq("id", lead.get("id")).execute()


def _append_pending_note(
    supabase: Any,
    chat: Dict[str, Any],
    note: str,
) -> None:
    note = note.strip()
    if not note:
        return
    state = _get_chat_state(chat)
    pending = state.get("pending_notes") or []
    if note in pending:
        return
    pending.append(note)
    _set_chat_state_value(supabase, chat, "pending_notes", pending)


def _drain_pending_notes(
    supabase: Any,
    chat: Dict[str, Any],
) -> List[str]:
    notes = _get_chat_state(chat).get("pending_notes") or []
    _pop_chat_state_value(supabase, chat, "pending_notes")
    return [note for note in notes if note]


def _get_slot_options(
    lead: Optional[Dict[str, Any]],
    chat: Dict[str, Any],
) -> List[Dict[str, Any]]:
    if lead:
        metadata = lead.get("metadata") or {}
        options = (metadata.get("slot_options") or {}).get("options") or []
        if options:
            return options
    state = _get_chat_state(chat)
    return (state.get("slot_options") or {}).get("options") or []


def _clear_slot_options(
    supabase: Any,
    lead: Optional[Dict[str, Any]],
    chat: Dict[str, Any],
) -> None:
    if lead:
        metadata = lead.get("metadata") or {}
        if "slot_options" in metadata:
            metadata.pop("slot_options", None)
            supabase.from_("leads").update(
                {"metadata": metadata, "updated_at": datetime.utcnow().isoformat()}
            ).eq("id", lead.get("id")).execute()
    _pop_chat_state_value(supabase, chat, "slot_options")


def _slot_id_from_selection(
    options: List[Dict[str, Any]],
    selection: int,
) -> Optional[Dict[str, Any]]:
    return next(
        (option for option in options if option.get("option") == selection),
        None,
    )


def _slot_id_allowed(
    slot_id: str,
    lead: Optional[Dict[str, Any]],
    chat: Dict[str, Any],
) -> bool:
    options = _get_slot_options(lead, chat)
    if not options:
        return True
    return any(option.get("slot_id") == slot_id for option in options)


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
    if allow_bare:
        match = re.match(
            r"^(?:la|el|opcion|opción)?\s*(\d{1,2})\s*$", lowered
        )
    else:
        match = re.search(r"\b(?:opcion|opción)\s*(\d{1,2})\b", lowered)
    if not match:
        return None
    value = int(match.group(1))
    return value if 1 <= value <= 10 else None


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

    lead = _get_lead_by_chat(supabase, org_id, chat_id)
    if not lead or not lead.get("id"):
        return "No encontre un lead activo para agregar notas."

    _append_lead_note(
        supabase,
        lead,
        org_id,
        request.notes,
        subject=request.subject,
    )
    lead_number = lead.get("lead_number")
    return (
        f"Nota agregada al lead L-{lead_number}."
        if lead_number
        else "Nota agregada al lead."
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
    lead = _get_lead_by_chat(supabase, org.get("id"), chat.get("id"))
    if not lead or not lead.get("id"):
        return None
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
    lead = _get_lead_by_chat(supabase, org.get("id"), chat.get("id"))
    if lead and lead.get("id"):
        for note in notes:
            _append_lead_note(supabase, lead, org.get("id"), note, subject="Nota")
        return True
    for note in notes:
        _append_pending_note(supabase, chat, note)
    return True


def _maybe_book_from_selection(
    combined_user: str,
    org: Dict[str, Any],
    chat: Dict[str, Any],
) -> Optional[str]:
    supabase = get_supabase_client()
    lead = _get_lead_by_chat(supabase, org.get("id"), chat.get("id"))
    slot_options = _get_slot_options(lead, chat)
    pending_option = _get_chat_state(chat).get("pending_slot_option")
    allow_bare = bool(slot_options or pending_option)
    selection = _parse_slot_selection(combined_user, allow_bare=allow_bare)
    if not selection:
        return None
    if not slot_options and pending_option:
        _pop_chat_state_value(supabase, chat, "pending_slot_option")
        return None
    if not lead or not lead.get("id") or not slot_options:
        _set_chat_state_value(supabase, chat, "pending_slot_option", selection)
        preferred_date = _get_chat_state(chat).get("preferred_date")
        if preferred_date:
            result_text = _search_availability_slots(
                SearchSlotsRequest(
                    start_date=preferred_date, end_date=preferred_date
                ),
                org=org,
                chat=chat,
            )
            lead = _get_lead_by_chat(supabase, org.get("id"), chat.get("id"))
            slot_options = _get_slot_options(lead, chat)
            match = _slot_id_from_selection(slot_options, selection)
            if match and match.get("slot_id"):
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
                    return (
                        f"¡Listo! Tu visita quedó agendada para {slot_text}. "
                        "Si necesitas cambiarla, solo dime."
                    )
            return result_text
        return (
            "Antes de reservar necesito mostrarte las opciones disponibles. "
            "Dime que dias u horarios te convienen y te comparto la lista."
        )
    match = _slot_id_from_selection(slot_options, selection)
    if not match or not match.get("slot_id"):
        return "No pude identificar esa opcion. Dime un numero de la lista."

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
        return (
            f"¡Listo! Tu visita quedó agendada para {slot_text}. "
            "Si necesitas cambiarla, solo dime."
        )
    return result


def _maybe_book_pending_selection(
    org: Dict[str, Any],
    chat: Dict[str, Any],
) -> Optional[str]:
    supabase = get_supabase_client()
    pending = _get_chat_state(chat).get("pending_slot_option")
    if not pending:
        return None
    lead = _get_lead_by_chat(supabase, org.get("id"), chat.get("id"))
    if not lead or not lead.get("id"):
        return None
    slot_options = _get_slot_options(lead, chat)
    if not slot_options:
        return None
    match = _slot_id_from_selection(slot_options, pending)
    if not match or not match.get("slot_id"):
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
        return (
            f"¡Listo! Tu visita quedó agendada para {slot_text}. "
            "Si necesitas cambiarla, solo dime."
        )
    return result


def _send_assistant_message(
    assistant_text: str,
    org: Dict[str, Any],
    chat: Dict[str, Any],
    session_id: str,
) -> Dict[str, Any]:
    supabase = get_supabase_client()
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
            "student_last_name_paternal, student_last_name_maternal, student_dob, "
            "grade_interest, current_school, contact_name, contact_email, contact_phone, notes"
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
    if not lead_data.get("student_dob"):
        missing.append("fecha de nacimiento")
    if not lead_data.get("contact_name"):
        missing.append("nombre del tutor")
    if not lead_data.get("contact_email"):
        missing.append("correo del tutor")
    if not lead_data.get("contact_phone"):
        missing.append("telefono del tutor")

    missing_text = ", ".join(missing) if missing else "ninguno"
    lead_label = f"L-{lead_number}" if lead_number else "sin folio"
    notes = lead_data.get("notes") or ""
    notes = notes.strip()
    if notes and len(notes) > 300:
        notes = f"{notes[:300].rstrip()}..."
    return (
        "Lead existente: "
        f"folio {lead_label}. "
        f"Alumno: {student_name or 'sin nombre'}. "
        f"Grado: {lead_data.get('grade_interest') or 'sin dato'}. "
        f"Fecha nacimiento: {lead_data.get('student_dob') or 'sin dato'}. "
        f"Escuela actual: {lead_data.get('current_school') or 'sin dato'}. "
        f"Tutor: {lead_data.get('contact_name') or 'sin dato'}. "
        f"Correo: {lead_data.get('contact_email') or 'sin dato'}. "
        f"Telefono: {lead_data.get('contact_phone') or 'sin dato'}. "
        f"Notas: {notes or 'sin notas'}. "
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
                "name": "add_lead_note",
                "description": "Add a note to the lead activities for the current chat",
                "parameters": AddLeadNoteRequest.model_json_schema(),
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
        {
            "type": "function",
            "function": {
                "name": "search_availability_slots",
                "description": "Search for available appointment slots within a date range.",
                "parameters": SearchSlotsRequest.model_json_schema(),
            },
        },
        {
            "type": "function",
            "function": {
                "name": "book_appointment",
                "description": "Book an appointment slot for the current lead.",
                "parameters": BookAppointmentRequest.model_json_schema(),
            },
        },
        {
            "type": "function",
            "function": {
                "name": "cancel_appointment",
                "description": "Cancel an existing scheduled appointment. Requires a cancellation reason from the user.",
                "parameters": CancelAppointmentRequest.model_json_schema(),
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

    lead_note_added = False
    booking_done = False
    booking_error_text: Optional[str] = None
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
        if booking_error_text and not booking_done:
            assistant_text = booking_error_text
            booking_done = True
        if not booking_done:
            pending_booking_text = _maybe_book_pending_selection(org=org, chat=chat)
            if pending_booking_text:
                assistant_text = pending_booking_text
                booking_done = True
        if not booking_done:
            followup = grok_client.chat.completions.create(
                model=model,
                messages=messages_payload,
                tools=tools,
            )
            assistant_text = followup.choices[0].message.content or ""

    if not lead_note_added:
        _maybe_auto_add_notes(combined_user, org=org, chat=chat)

    return _send_assistant_message(assistant_text, org, chat, session_id)


class SearchSlotsRequest(BaseModel):
    start_date: str  # YYYY-MM-DD
    end_date: str    # YYYY-MM-DD


class BookAppointmentRequest(BaseModel):
    slot_id: str
    notes: Optional[str] = None


class CancelAppointmentRequest(BaseModel):
    cancellation_reason: str


def _cancel_appointment(
    request: CancelAppointmentRequest,
    org: Dict[str, Any],
    chat: Dict[str, Any],
) -> str:
    supabase = get_supabase_client()
    print(f"[admissions] cancelling appointment, reason: {request.cancellation_reason}")
    
    # 1. Find lead for this chat
    lead_response = (
        supabase.from_("leads")
        .select("id")
        .eq("wa_chat_id", chat.get("id"))
        .eq("organization_id", org.get("id"))
        .maybe_single()
        .execute()
    )
    lead = get_supabase_data(lead_response)
    if not lead:
        return "No encontré un lead activo para cancelar cita."
    
    lead_id = lead.get("id")
    
    # 2. Find scheduled appointment for this lead
    appt_response = (
        supabase.from_("appointments")
        .select("id, slot_id")
        .eq("lead_id", lead_id)
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
    
    # 5. Update lead status back to contacted
    supabase.from_("leads").update({
        "status": "contacted",
        "updated_at": datetime.utcnow().isoformat(),
    }).eq("id", lead_id).execute()
    
    print(f"[admissions] appointment {appt_id} cancelled successfully")
    
    return "Cita cancelada exitosamente. El lead ha sido actualizado. Intenta convencer al usuario de agendar otra visita preguntando qué fechas le convendrían mejor."


def _search_availability_slots(
    request: SearchSlotsRequest,
    org: Dict[str, Any],
    chat: Dict[str, Any],
) -> str:
    supabase = get_supabase_client()
    print(f"[admissions] searching slots from {request.start_date} to {request.end_date}")
    
    # Simple validation
    try:
        start_dt = datetime.fromisoformat(request.start_date).replace(tzinfo=timezone.utc)
        end_dt = datetime.fromisoformat(request.end_date).replace(tzinfo=timezone.utc)
        # Verify range is mostly valid for a query (ends at 23:59:59 usually externally but let's assume raw dates)
    except ValueError:
        return "Formato de fechas invalido. Usa YYYY-MM-DD."

    # Query
    response = (
        supabase.from_("availability_slots")
        .select("id, starts_at, ends_at, max_appointments, appointments_count")
        .eq("organization_id", org.get("id"))
        .eq("is_active", True)
        .eq("is_blocked", False)
        .gte("starts_at", request.start_date)
        .lte("ends_at", f"{request.end_date} 23:59:59")
        .execute()
    )
    
    slots = get_supabase_data(response) or []
    available_slots = []
    
    for slot in slots:
        count = slot.get("appointments_count", 0)
        max_app = slot.get("max_appointments", 1)
        if count < max_app:
            available_slots.append(slot)
            
    if not available_slots:
        return "No hay horarios disponibles en esas fechas."

    options: List[Dict[str, Any]] = []
    for idx, s in enumerate(available_slots[:10], start=1):
        options.append(
            {
                "option": idx,
                "slot_id": s.get("id"),
                "starts_at": s.get("starts_at"),
                "ends_at": s.get("ends_at"),
            }
        )

    slot_state = {
        "generated_at": datetime.utcnow().isoformat(),
        "options": options,
    }
    _set_chat_state_value(supabase, chat, "slot_options", slot_state)
    _pop_chat_state_value(supabase, chat, "pending_slot_option")

    lead = _get_lead_by_chat(supabase, org.get("id"), chat.get("id"))
    if lead and lead.get("id"):
        metadata = lead.get("metadata") or {}
        metadata["slot_options"] = slot_state
        supabase.from_("leads").update(
            {"metadata": metadata, "updated_at": datetime.utcnow().isoformat()}
        ).eq("id", lead.get("id")).execute()
    
    result_text = "Horarios disponibles (hora local Torreón):\n"
    for idx, s in enumerate(available_slots[:10], start=1):
        start_str = s.get("starts_at")
        end_str = s.get("ends_at")
        formatted = _format_slot_window_local(start_str, end_str)
        if formatted:
            result_text += f"- Opción {idx}: {formatted}\n"
        else:
            result_text += f"- Opción {idx}: {start_str} - {end_str}\n"
        
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

    lead = _get_lead_by_chat(supabase, org.get("id"), chat.get("id"))
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
    if not lead:
        return "No encontre un lead activo para agendar. Crea el lead primero."
    
    lead_id = lead.get("id")

    # 3. Create Appointment
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
    
    # 5. Update Lead Status
    supabase.from_("leads").update(
        {"status": "visit_scheduled", "updated_at": datetime.utcnow().isoformat()}
    ).eq("id", lead_id).execute()
    
    return "Cita agendada exitosamente. El lead ha sido actualizado a 'visit_scheduled'."


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
