#!/usr/bin/env python3
"""
Smoke test for chatbot appointment handlers against a local Supabase instance.

It bypasses OpenAI and WhatsApp transport on purpose. The goal is to verify the
bot's appointment handlers, chat state, and atomic Postgres RPCs together.
"""

import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

load_dotenv()

from app.core.supabase import get_supabase_client, get_supabase_data, reset_supabase_client
from app.whatsapp.chat_state import set_chat_state_value
from app.whatsapp.process_router import (
    _book_appointment,
    _cancel_appointment,
    _maybe_book_from_selection,
)
from app.whatsapp.tools import BookAppointmentRequest, CancelAppointmentRequest


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def insert_one(supabase, table, payload):
    response = supabase.from_(table).insert(payload).execute()
    data = get_supabase_data(response) or []
    if not data:
        raise RuntimeError(f"Insert failed for {table}: {response}")
    return data[0]


def reload_slot(supabase, slot_id):
    response = (
        supabase.from_("availability_slots")
        .select("appointments_count")
        .eq("id", slot_id)
        .single()
        .execute()
    )
    return get_supabase_data(response)


def main():
    reset_supabase_client()
    supabase = get_supabase_client()
    suffix = uuid.uuid4().hex
    now = datetime.now(timezone.utc)

    org = insert_one(
        supabase,
        "organizations",
        {
            "name": "Chatbot Smoke Org",
            "slug": f"chatbot-smoke-{suffix}",
            "phone_number_id": f"chatbot-smoke-{suffix}",
            "bot_name": "Vale",
            "bot_tone": "amable",
        },
    )
    chat = insert_one(
        supabase,
        "chats",
        {
            "organization_id": org["id"],
            "wa_id": f"521-smoke-{suffix[:12]}",
            "phone_number": f"521-smoke-{suffix[:12]}",
            "name": "Smoke Chat",
            "state_context": {},
        },
    )
    contact = insert_one(
        supabase,
        "crm_contacts",
        {
            "organization_id": org["id"],
            "first_name": "Tutor",
            "last_name_paternal": "Smoke",
            "phone": f"5200{suffix[:11]}",
            "source": "whatsapp",
        },
    )
    insert_one(
        supabase,
        "leads",
        {
            "organization_id": org["id"],
            "source": "whatsapp",
            "student_first_name": "Alumno",
            "student_last_name_paternal": "Smoke",
            "grade_interest": "Kinder",
            "current_school": "Escuela de prueba",
            "contact_id": contact["id"],
            "contact_name": "Tutor Smoke",
            "contact_phone": contact["phone"],
            "wa_chat_id": chat["id"],
            "wa_id": chat["wa_id"],
        },
    )
    slot_1 = insert_one(
        supabase,
        "availability_slots",
        {
            "organization_id": org["id"],
            "starts_at": (now + timedelta(days=7)).isoformat(),
            "ends_at": (now + timedelta(days=7, hours=1)).isoformat(),
            "max_appointments": 1,
            "appointments_count": 0,
            "is_active": True,
            "is_blocked": False,
        },
    )
    slot_2 = insert_one(
        supabase,
        "availability_slots",
        {
            "organization_id": org["id"],
            "starts_at": (now + timedelta(days=8)).isoformat(),
            "ends_at": (now + timedelta(days=8, hours=1)).isoformat(),
            "max_appointments": 1,
            "appointments_count": 0,
            "is_active": True,
            "is_blocked": False,
        },
    )

    set_chat_state_value(
        supabase,
        chat,
        "slot_options",
        {
            "generated_at": now.isoformat(),
            "options": [
                {
                    "option": 1,
                    "slot_id": slot_1["id"],
                    "starts_at": slot_1["starts_at"],
                    "ends_at": slot_1["ends_at"],
                }
            ],
        },
    )
    book_result = _book_appointment(
        BookAppointmentRequest(slot_id=slot_1["id"]),
        org=org,
        chat=chat,
    )
    assert_true(
        book_result.lower().startswith("cita agendada exitosamente"),
        f"Expected booking success, got: {book_result}",
    )

    duplicate_result = _book_appointment(
        BookAppointmentRequest(slot_id=slot_1["id"]),
        org=org,
        chat=chat,
    )
    assert_true(
        "ya tiene una cita" in duplicate_result.lower(),
        f"Expected duplicate booking rejection, got: {duplicate_result}",
    )

    set_chat_state_value(
        supabase,
        chat,
        "appointment_flow",
        "reschedule",
    )
    set_chat_state_value(
        supabase,
        chat,
        "slot_options",
        {
            "generated_at": now.isoformat(),
            "options": [
                {
                    "option": 1,
                    "slot_id": slot_2["id"],
                    "starts_at": slot_2["starts_at"],
                    "ends_at": slot_2["ends_at"],
                }
            ],
        },
    )
    selection_result = _maybe_book_from_selection("la 1", org=org, chat=chat)
    assert_true(
        selection_result and "reagendada" in selection_result.lower(),
        f"Expected reschedule confirmation, got: {selection_result}",
    )
    assert_true(
        reload_slot(supabase, slot_1["id"])["appointments_count"] == 0,
        "Expected old slot count to be 0 after reschedule",
    )
    assert_true(
        reload_slot(supabase, slot_2["id"])["appointments_count"] == 1,
        "Expected new slot count to be 1 after reschedule",
    )

    cancel_result = _cancel_appointment(
        CancelAppointmentRequest(cancellation_reason="Smoke cleanup"),
        org=org,
        chat=chat,
    )
    assert_true(
        cancel_result.lower().startswith("cita cancelada exitosamente"),
        f"Expected cancellation success, got: {cancel_result}",
    )
    assert_true(
        reload_slot(supabase, slot_2["id"])["appointments_count"] == 0,
        "Expected new slot count to be 0 after cancellation",
    )

    print(
        json.dumps(
            {
                "booking": "passed",
                "duplicate_rejection": "passed",
                "reschedule_selection": "passed",
                "cancellation": "passed",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
