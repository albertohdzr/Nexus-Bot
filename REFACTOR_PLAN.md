# Refactoring Plan: process_router.py → Modular Architecture

## ✅ Completed Steps

### Step 1-4: Module Extraction (DONE)

- `chat_state.py` — State management, lead lookups, session helpers
- `prompt.py` — System prompt builder
- `sanitizer.py` — Response sanitization & WhatsApp formatting
- `tools/__init__.py` — Pydantic schemas + tool registry

### Step 5: Responses API Migration (DONE)

Migrated from Chat Completions API to the new Responses API:

- `client.chat.completions.create()` → `client.responses.create()`
- System messages → `instructions` parameter (single string)
- `messages` array → `input` parameter
- `response.choices[0].message.content` → `response.output_text`
- Tool calls extracted from `response.output` (type="function_call")
- Tool results: `{type: "function_call_output", call_id, output}`
- Followup calls use `response.output + tool_outputs` as input
- Tools use flat format: `{type: "function", name, description, parameters}`

## Current Architecture

```
app/whatsapp/
├── process_router.py      # API endpoints + orchestration (~2,600 lines)
├── prompt.py              # System prompt builder (~275 lines)
├── chat_state.py          # Chat state helpers (~286 lines)
├── sanitizer.py           # Response sanitization & validation (~191 lines)
├── tools/
│   └── __init__.py        # Tool schemas + Responses API registry (~190 lines)
├── outbound.py            # WhatsApp message sending
├── processing.py          # Incoming message handling
├── webhook.py             # Webhook handler
└── ...
```

## Remaining Steps (Future)

### Step 6: Extract tool handlers

Move tool handler functions into `tools/` submodules:

- `tools/leads.py` — create_admissions_lead, update_admissions_lead,
  add_lead_note
- `tools/booking.py` — search_availability_slots, book_appointment,
  cancel_appointment
- `tools/events.py` — get_next_event, register_event
- `tools/requirements.py` — send_requirements

### Step 7: Extract booking flow

Create `booking_flow.py`:

- `maybe_book_from_selection` (pre-LLM)
- `maybe_book_pending_selection` (post-tool)
- `maybe_auto_cancel` (pre-LLM)

### Step 8: Create orchestrator.py

Extract the main LLM loop from `process_router.py` into `orchestrator.py`:

- Load chat, org, session
- Pre-LLM hooks (booking flow)
- Build instructions + input
- Call Responses API
- Execute tool calls
- Post-response validation
- Send final message

### Step 9: Slim process_router.py

Reduce to API endpoints only (~100 lines):

- `process_queue` endpoint → calls orchestrator
- `get_chat_history_endpoint`
- `close_chat_session_endpoint`
