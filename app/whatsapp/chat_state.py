"""
Chat state management, lead lookups, and shared utility functions.

This module contains all stateful helpers that operate on the chat's
`state_context` dict and lead lookups from Supabase.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.supabase import (
    get_supabase_client,
    get_supabase_data,
    get_supabase_error,
)


# ── Naming helpers ────────────────────────────────────────────────


def compose_full_name(parts: List[Optional[str]]) -> Optional[str]:
    cleaned = [part.strip() for part in parts if part and part.strip()]
    return " ".join(cleaned) if cleaned else None


# ── Chat state accessors ──────────────────────────────────────────


def get_chat_state(chat: Dict[str, Any]) -> Dict[str, Any]:
    return chat.get("state_context") or {}


def set_chat_state_value(
    supabase: Any,
    chat: Dict[str, Any],
    key: str,
    value: Any,
) -> None:
    state = get_chat_state(chat)
    state[key] = value
    supabase.from_("chats").update(
        {"state_context": state, "updated_at": datetime.utcnow().isoformat()}
    ).eq("id", chat.get("id")).execute()
    chat["state_context"] = state


def pop_chat_state_value(
    supabase: Any,
    chat: Dict[str, Any],
    key: str,
) -> Optional[Any]:
    state = get_chat_state(chat)
    if key not in state:
        return None
    value = state.pop(key)
    supabase.from_("chats").update(
        {"state_context": state, "updated_at": datetime.utcnow().isoformat()}
    ).eq("id", chat.get("id")).execute()
    chat["state_context"] = state
    return value


# ── Lead lookups ──────────────────────────────────────────────────

_LEAD_SELECT_FIELDS = (
    "id, lead_number, metadata, notes, contact_id, "
    "student_first_name, student_last_name_paternal"
)


def get_leads_by_chat(
    supabase: Any,
    org_id: str,
    chat_id: str,
    wa_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return all leads associated with a chat, newest first."""
    response = (
        supabase.from_("leads")
        .select(_LEAD_SELECT_FIELDS)
        .eq("organization_id", org_id)
        .eq("wa_chat_id", chat_id)
        .order("created_at", desc=True)
        .execute()
    )
    if not get_supabase_error(response):
        leads = get_supabase_data(response)
        if leads:
            return leads

    # Fallback: look up by WhatsApp ID
    if wa_id:
        fallback = (
            supabase.from_("leads")
            .select(_LEAD_SELECT_FIELDS)
            .eq("organization_id", org_id)
            .eq("wa_id", wa_id)
            .order("created_at", desc=True)
            .execute()
        )
        if not get_supabase_error(fallback):
            leads = get_supabase_data(fallback)
            if leads:
                return leads

    return []


def get_lead_by_chat(
    supabase: Any,
    org_id: str,
    chat_id: str,
    wa_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Return the most recent (primary) lead for a chat."""
    leads = get_leads_by_chat(supabase, org_id, chat_id, wa_id)
    return leads[0] if leads else None


# ── Lead notes ────────────────────────────────────────────────────


def append_lead_note(
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


def append_pending_note(
    supabase: Any,
    chat: Dict[str, Any],
    note: str,
) -> None:
    note = note.strip()
    if not note:
        return
    state = get_chat_state(chat)
    pending = state.get("pending_notes") or []
    if note in pending:
        return
    pending.append(note)
    set_chat_state_value(supabase, chat, "pending_notes", pending)


def drain_pending_notes(
    supabase: Any,
    chat: Dict[str, Any],
) -> List[str]:
    notes = get_chat_state(chat).get("pending_notes") or []
    pop_chat_state_value(supabase, chat, "pending_notes")
    return [note for note in notes if note]


# ── Slot options (appointment scheduling) ─────────────────────────


def get_slot_options(
    lead: Optional[Dict[str, Any]],
    chat: Dict[str, Any],
) -> List[Dict[str, Any]]:
    if lead:
        metadata = lead.get("metadata") or {}
        options = (metadata.get("slot_options") or {}).get("options") or []
        if options:
            return options
    state = get_chat_state(chat)
    return (state.get("slot_options") or {}).get("options") or []


def clear_slot_options(
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
    pop_chat_state_value(supabase, chat, "slot_options")


def slot_id_from_selection(
    options: List[Dict[str, Any]],
    selection: int,
) -> Optional[Dict[str, Any]]:
    return next(
        (option for option in options if option.get("option") == selection),
        None,
    )


def slot_id_allowed(
    slot_id: str,
    lead: Optional[Dict[str, Any]],
    chat: Dict[str, Any],
) -> bool:
    options = get_slot_options(lead, chat)
    if not options:
        return True
    return any(option.get("slot_id") == slot_id for option in options)


# ── Pending event ─────────────────────────────────────────────────


def get_pending_event(chat: Dict[str, Any]) -> Dict[str, Any]:
    return get_chat_state(chat).get("pending_event") or {}


# ── Session management ────────────────────────────────────────────


def ensure_active_session(chat: Dict[str, Any], org_id: str) -> str:
    """Ensure the chat has an active session, creating one if needed."""
    supabase = get_supabase_client()
    session_id = chat.get("active_session_id")

    if session_id:
        session_response = (
            supabase.from_("chat_sessions")
            .select("id, status")
            .eq("id", session_id)
            .maybe_single()
            .execute()
        )
        session = get_supabase_data(session_response)
        if session and session.get("status") == "active":
            return session_id

    # Create new session
    new_session = (
        supabase.from_("chat_sessions")
        .insert(
            {
                "chat_id": chat.get("id"),
                "organization_id": org_id,
                "status": "active",
                "started_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }
        )
        .execute()
    )
    new_session_data = get_supabase_data(new_session)
    if not new_session_data:
        raise HTTPException(status_code=500, detail="Failed to create session")

    new_id = new_session_data[0]["id"]
    supabase.from_("chats").update(
        {"active_session_id": new_id, "updated_at": datetime.utcnow().isoformat()}
    ).eq("id", chat.get("id")).execute()
    chat["active_session_id"] = new_id
    return new_id


# Avoid circular — only needed for ensure_active_session error
from fastapi import HTTPException  # noqa: E402
