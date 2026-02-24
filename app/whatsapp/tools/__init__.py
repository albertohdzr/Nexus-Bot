"""
Tool definitions (schemas + OpenAI function-calling descriptors).

Centralises all Pydantic request models and the ``TOOLS`` list
that is passed to the OpenAI chat completion call.
"""

from typing import Optional
from pydantic import BaseModel


# ── Lead tools ───────────────────────────────────────────────────


class CreateAdmissionsLeadRequest(BaseModel):
    student_first_name: str
    student_middle_name: Optional[str] = None
    student_last_name_paternal: str
    student_last_name_maternal: Optional[str] = None
    student_dob: Optional[str] = None
    grade_interest: str
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
    qualification_status: Optional[str] = None


class AddLeadNoteRequest(BaseModel):
    notes: str
    subject: Optional[str] = None


# ── Session tools ────────────────────────────────────────────────


class CloseChatSessionRequest(BaseModel):
    summary: str
    reason: Optional[str] = None


# ── Booking tools ────────────────────────────────────────────────


class SearchSlotsRequest(BaseModel):
    start_date: str   # YYYY-MM-DD
    end_date: str     # YYYY-MM-DD
    preferred_time: Optional[str] = None  # "morning" | "afternoon"


class BookAppointmentRequest(BaseModel):
    slot_id: str
    notes: Optional[str] = None


class CancelAppointmentRequest(BaseModel):
    cancellation_reason: str


# ── Event tools ──────────────────────────────────────────────────


class GetNextEventRequest(BaseModel):
    division: str


class RegisterEventRequest(BaseModel):
    event_id: Optional[str] = None


# ── Requirements tools ───────────────────────────────────────────


class GetRequirementsRequest(BaseModel):
    division: str


# ── OpenAI Responses API function-calling descriptors ────────────
# Format: flat FunctionToolParam (not nested under "function" key)


def build_tools_list():
    """Return the ``tools`` list for the OpenAI Responses API."""
    return [
        {
            "type": "function",
            "name": "create_admissions_lead",
            "description": "Create an admissions lead once the required data is collected",
            "parameters": CreateAdmissionsLeadRequest.model_json_schema(),
        },
        {
            "type": "function",
            "name": "update_admissions_lead",
            "description": "Update an admissions lead with additional details",
            "parameters": UpdateAdmissionsLeadRequest.model_json_schema(),
        },
        {
            "type": "function",
            "name": "add_lead_note",
            "description": "Add a note to the lead activities for the current chat",
            "parameters": AddLeadNoteRequest.model_json_schema(),
        },
        {
            "type": "function",
            "name": "get_next_event",
            "description": "Get the next upcoming event for a specific division.",
            "parameters": GetNextEventRequest.model_json_schema(),
        },
        {
            "type": "function",
            "name": "register_event",
            "description": "Register the current lead for the selected event.",
            "parameters": RegisterEventRequest.model_json_schema(),
        },
        {
            "type": "function",
            "name": "get_admission_requirements",
            "description": (
                "Get and send the admission requirements document (PDF) "
                "for a specific school division. Use this when the user asks for requirements."
            ),
            "parameters": GetRequirementsRequest.model_json_schema(),
        },
        {
            "type": "function",
            "name": "search_availability_slots",
            "description": (
                "Search for available appointment slots within a date range. "
                "MUST be called before offering any schedule options to the user. "
                "Business hours are 8am-3pm Monday-Friday (Torreón time). "
                "Use 'preferred_time' to filter: 'morning' (8am-12pm) or 'afternoon' (12pm-3pm)."
            ),
            "parameters": SearchSlotsRequest.model_json_schema(),
        },
        {
            "type": "function",
            "name": "book_appointment",
            "description": (
                "Book an appointment slot for the current lead. "
                "The slot_id MUST come from a previous 'search_availability_slots' result. "
                "NEVER invent or guess a slot_id."
            ),
            "parameters": BookAppointmentRequest.model_json_schema(),
        },
        {
            "type": "function",
            "name": "cancel_appointment",
            "description": (
                "Cancel an existing scheduled appointment. "
                "Requires a cancellation reason from the user."
            ),
            "parameters": CancelAppointmentRequest.model_json_schema(),
        },
        {
            "type": "function",
            "name": "close_chat_session",
            "description": (
                "Close the current chat session with a summary. "
                "Only use when the user explicitly wants to end the conversation."
            ),
            "parameters": CloseChatSessionRequest.model_json_schema(),
        },
    ]

