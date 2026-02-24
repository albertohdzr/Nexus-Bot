"""
Response sanitization and validation.

Cleans up LLM output for WhatsApp formatting and detects
invented/hallucinated content that wasn't backed by tool calls.
"""

import re
from typing import Any, Dict, List, Optional


# ── WhatsApp formatting & artifact removal ─────────────────────────


def sanitize_response(text: str) -> str:
    """Clean LLM output for WhatsApp delivery.

    Handles:
    - ``Human:`` / ``Assistant:`` prefix leaks
    - ``<thinking>`` tags
    - Leaked JSON / system content
    - Markdown **bold** → WhatsApp *bold*
    - Markdown headings → bold text
    - Excessive newlines
    """
    if not text:
        return ""

    sanitized = text.strip()

    # Remove "Human:" / "User:" prefixes
    if re.match(r"^(?:Human|User|Usuario):\s*", sanitized, re.IGNORECASE):
        print(
            f"[admissions] WARNING: Response started with Human/User prefix: "
            f"{sanitized[:100]}"
        )
        lines = sanitized.split("\n")
        filtered_lines: List[str] = []
        skip_human_block = False
        for line in lines:
            if re.match(r"^(?:Human|User|Usuario):\s*", line, re.IGNORECASE):
                skip_human_block = True
                continue
            if re.match(r"^(?:Assistant|Asistente|Bot):\s*", line, re.IGNORECASE):
                skip_human_block = False
                line = re.sub(
                    r"^(?:Assistant|Asistente|Bot):\s*", "", line, flags=re.IGNORECASE
                )
            if not skip_human_block:
                filtered_lines.append(line)
        sanitized = "\n".join(filtered_lines).strip()

    # Remove "Assistant:" prefix
    sanitized = re.sub(
        r"^(?:Assistant|Asistente|Bot):\s*", "", sanitized, flags=re.IGNORECASE
    )

    # Remove thinking tags
    sanitized = re.sub(
        r"<thinking>.*?</thinking>", "", sanitized, flags=re.DOTALL | re.IGNORECASE
    )
    sanitized = re.sub(
        r"\[thinking\].*?\[/thinking\]", "", sanitized, flags=re.DOTALL | re.IGNORECASE
    )

    # Remove leaked JSON blocks
    sanitized = re.sub(
        r"```(?:json|tool_call|system)?\s*\{.*?\}\s*```", "", sanitized, flags=re.DOTALL
    )

    # WhatsApp formatting: **bold** → *bold*
    sanitized = re.sub(r"\*\*(.+?)\*\*", r"*\1*", sanitized)

    # Markdown headings → bold text
    sanitized = re.sub(r"^#{1,6}\s+(.+)$", r"*\1*", sanitized, flags=re.MULTILINE)

    # Collapse excessive newlines
    sanitized = re.sub(r"\n{3,}", "\n\n", sanitized)

    return sanitized.strip()


# ── Invented-content detection ─────────────────────────────────────


def validate_and_fix_response(
    assistant_text: str,
    combined_user: str,
    tool_calls: list,
    lead: Optional[Dict[str, Any]],
    chat: Dict[str, Any],
) -> str:
    """Replace hallucinated content that wasn't backed by tool calls.

    Conservative — only catches clear violations:
    1. Claiming cancellation without ``cancel_appointment``
    2. Inventing a schedule list without ``search_availability_slots``
    """
    lowered_text = assistant_text.lower()
    lowered_user = combined_user.lower()

    called_tools = {getattr(tc, 'name', None) or getattr(getattr(tc, 'function', None), 'name', '') for tc in tool_calls} if tool_calls else set()

    # ── Check 1: fake cancellation ──
    user_wants_cancel = any(
        phrase in lowered_user
        for phrase in [
            "cancelar",
            "cancela mi cita",
            "cambiar la cita",
            "no se me acomoda la hora",
        ]
    )
    if user_wants_cancel:
        cancel_claimed = any(
            phrase in lowered_text
            for phrase in [
                "cita ha sido cancelada",
                "cita fue cancelada",
                "cita cancelada exitosamente",
                "he cancelado tu cita",
                "queda cancelada",
            ]
        )
        if cancel_claimed and "cancel_appointment" not in called_tools:
            print("[admissions] WARNING: Model claimed cancellation without calling tool")
            return (
                "Entiendo que quieres cambiar tu cita. Para hacerlo, "
                "necesito saber la razón del cambio. ¿Podrías decirme por qué "
                "ya no te funciona el horario? (ej: trabajo, agenda familiar, etc.)"
            )

    # ── Check 2: fake note claim (log only) ──
    note_claimed = any(
        phrase in lowered_text
        for phrase in [
            "he actualizado la nota",
            "he anotado",
            "he registrado",
            "he guardado",
            "actualicé la nota",
            "anoté",
            "registré",
            "guardé",
            "lo registro",
            "lo anoto",
        ]
    )
    if (
        note_claimed
        and "add_lead_note" not in called_tools
        and "update_admissions_lead" not in called_tools
    ):
        print("[admissions] WARNING: Model claimed to add note without calling tool")

    # ── Check 3: invented schedule list ──
    if "search_availability_slots" not in called_tools:
        option_count = len(
            re.findall(r"(?:opción|opcion)\s*\d+", lowered_text, re.IGNORECASE)
        )

        time_list_pattern = (
            r"\d+[.):]+\s+[^\n]*(?:\d{1,2}:\d{2}|\d{1,2}\s*(?:am|pm|AM|PM))"
        )
        time_matches = len(re.findall(time_list_pattern, assistant_text))

        time_range_pattern = r"\d{1,2}:\d{2}\s*[-–]\s*\d{1,2}:\d{2}"
        time_range_matches = len(re.findall(time_range_pattern, assistant_text))

        has_invented_list = (
            option_count >= 3 or time_matches >= 3 or time_range_matches >= 3
        )

        if has_invented_list:
            # Import here to avoid circular deps
            from app.whatsapp.chat_state import get_slot_options

            slot_options = get_slot_options(lead, chat)
            if not slot_options:
                print(
                    f"[admissions] WARNING: Model invented schedule list "
                    f"(options={option_count}, times={time_matches}, "
                    f"ranges={time_range_matches}) without tool call"
                )
                return (
                    "Déjame buscar los horarios disponibles en el sistema. "
                    "¿Qué días y horarios te convendrían mejor? "
                    "(ej: 'jueves o viernes por la mañana')"
                )

    return assistant_text
