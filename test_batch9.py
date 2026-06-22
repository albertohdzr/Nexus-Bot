#!/usr/bin/env python3
"""
Batch 9: Comprehensive automated tests with assertions.

Covers: language handling, scholarships, grade calculation, status inquiry,
long conversations, multi-session, edge cases, all tools, and bombardment.
"""
import os, sys, time, gc, re
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

from test_chat import (
    create_test_chat, simulate_message, _h, _user, _bot, _info, _err,
)
from app.core.supabase import get_supabase_client, get_supabase_data, reset_supabase_client

TEST_ORG_ID = os.getenv("TEST_ORG_ID", "726f0ce2-edd0-4319-a7fd-7d0bfc4161aa")
LOG_DIR = os.path.join(os.path.dirname(__file__), "test_logs")
DELAY_MSG = 2.0
DELAY_SCENARIO = 8


# ── Logging ─────────────────────────────────────────────────
class Tee:
    def __init__(self, f):
        self.file = f
        self.stdout = sys.stdout
    def write(self, d):
        self.stdout.write(d)
        self.file.write(d)
    def flush(self):
        self.stdout.flush()
        if not self.file.closed:
            self.file.flush()


# ── Helpers ─────────────────────────────────────────────────
def fresh_client():
    reset_supabase_client()
    gc.collect()
    return get_supabase_client()


def send(cid, msg, retries=3):
    _user(msg)
    result = None
    for attempt in range(retries + 1):
        try:
            r = simulate_message(cid, msg)
            _bot(r)
            result = r
            break
        except Exception as exc:
            if attempt < retries:
                wait = 3 * (attempt + 1)
                _err(f"Retry {attempt+1}/{retries}: {exc}")
                fresh_client()
                time.sleep(wait)
            else:
                _err(f"FAILED after {retries} retries: {exc}")
    time.sleep(DELAY_MSG)
    return result


def set_lead_status(chat_id, status):
    sb = fresh_client()
    leads = sb.from_("leads").select("id").eq("wa_chat_id", chat_id).execute()
    for lead in (leads.data or []):
        sb.from_("leads").update({
            "status": status,
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", lead["id"]).execute()
        print(f"  [test] Set lead {lead['id'][:8]}… → {status}")


# ── Assertion framework ────────────────────────────────────
_test_results = []


def assert_contains(text, keywords, label):
    """Check response contains at least one keyword."""
    if not text:
        _test_results.append(("FAIL", label, "Empty response"))
        _err(f"ASSERT FAIL [{label}]: Empty response")
        return False
    text_lower = text.lower()
    found = [k for k in keywords if k.lower() in text_lower]
    if found:
        _test_results.append(("PASS", label, f"Found: {found}"))
        _info(f"ASSERT PASS [{label}]: Found {found}")
        return True
    _test_results.append(("FAIL", label, f"None of {keywords} found"))
    _err(f"ASSERT FAIL [{label}]: None of {keywords} found in: {text[:200]}")
    return False


def assert_not_contains(text, keywords, label):
    """Check response does NOT contain any keyword."""
    if not text:
        return True
    text_lower = text.lower()
    found = [k for k in keywords if k.lower() in text_lower]
    if found:
        _test_results.append(("FAIL", label, f"Unwanted: {found}"))
        _err(f"ASSERT FAIL [{label}]: Unwanted {found} in: {text[:200]}")
        return False
    _test_results.append(("PASS", label, "Clean"))
    return True


def assert_english(text, label):
    """Check response is primarily in English (no heavy Spanish)."""
    if not text:
        _test_results.append(("FAIL", label, "Empty response"))
        _err(f"ASSERT FAIL [{label}]: Empty response")
        return False
    spanish_markers = [
        "bienvenido", "buenas tardes", "gusto", "ayudarte",
        "información", "colegio", "alumno", "visita al campus",
        "horario", "agendar", "inscripción", "requisitos",
        "escolar", "colegiatura",
    ]
    text_lower = text.lower()
    spanish_count = sum(1 for m in spanish_markers if m in text_lower)
    if spanish_count >= 3:
        _test_results.append(("FAIL", label, f"{spanish_count} Spanish markers"))
        _err(f"ASSERT FAIL [{label}]: LANGUAGE SWITCH — {spanish_count} Spanish words in: {text[:200]}")
        return False
    _test_results.append(("PASS", label, "English OK"))
    _info(f"ASSERT PASS [{label}]: English maintained")
    return True


def assert_spanish(text, label):
    """Check response is primarily in Spanish."""
    if not text:
        _test_results.append(("FAIL", label, "Empty response"))
        return False
    english_markers = [
        "welcome", "thank you", "would you like", "appointment",
        "enrollment", "schedule", "requirements", "scholarship",
    ]
    text_lower = text.lower()
    english_count = sum(1 for m in english_markers if m in text_lower)
    if english_count >= 3:
        _test_results.append(("FAIL", label, f"{english_count} English markers"))
        _err(f"ASSERT FAIL [{label}]: Should be Spanish but found {english_count} English words")
        return False
    _test_results.append(("PASS", label, "Spanish OK"))
    return True


def print_test_summary():
    passed = sum(1 for r in _test_results if r[0] == "PASS")
    failed = sum(1 for r in _test_results if r[0] == "FAIL")
    total = len(_test_results)
    print(f"\n{'=' * 64}")
    print(f"  TEST SUMMARY: {passed}/{total} passed, {failed} failed")
    print(f"{'=' * 64}")
    for status, label, detail in _test_results:
        icon = "✅" if status == "PASS" else "❌"
        print(f"  {icon} [{label}]: {detail}")
    print(f"{'=' * 64}\n")


# ═══════════════════════════════════════════════════════════
# 1: Full English conversation
# ═══════════════════════════════════════════════════════════
def sc_full_english():
    _h("SCENARIO 1: Full English conversation")
    fresh_client()
    c = create_test_chat(TEST_ORG_ID, label="full_english")
    cid = c["id"]

    r1 = send(cid, "Hi, I'm interested in enrolling my daughter at your school")
    assert_english(r1, "en-1-greeting")

    r2 = send(cid, "She's 6 years old, born on March 15, 2020. "
              "She's currently in first grade at the American School in Monterrey")
    assert_english(r2, "en-2-info")

    r3 = send(cid, "Her name is Emily Johnson, and her father's last name is Johnson, "
              "mother's last name is Davis")
    assert_english(r3, "en-3-names")

    r4 = send(cid, "My name is Sarah Davis, phone 8711234567, email sarah.davis@test.com")
    assert_english(r4, "en-4-contact")

    r5 = send(cid, "What are the admission requirements for elementary school?")
    assert_english(r5, "en-5-requirements")

    r6 = send(cid, "Can I schedule a campus visit for next week in the morning?")
    assert_english(r6, "en-6-visit")

    _info(f"Chat ID: {cid}")
    return cid


# ═══════════════════════════════════════════════════════════
# 2: Language switch (English → Spanish)
# ═══════════════════════════════════════════════════════════
def sc_language_switch():
    _h("SCENARIO 2: Language switch (EN → ES)")
    fresh_client()
    c = create_test_chat(TEST_ORG_ID, label="lang_switch")
    cid = c["id"]

    r1 = send(cid, "Hello, I'd like information about your school for my son")
    assert_english(r1, "lang-1-start-english")

    r2 = send(cid, "He's 10 years old and currently in 4th grade")
    assert_english(r2, "lang-2-continue-english")

    r3 = send(cid, "Ah perdón, mejor hablemos en español. "
              "Quiero inscribir a mi hijo en primaria para el próximo ciclo")
    assert_spanish(r3, "lang-3-switch-to-spanish")

    r4 = send(cid, "Tiene 10 años, nació el 10 de febrero de 2016")
    assert_spanish(r4, "lang-4-continue-spanish")

    _info(f"Chat ID: {cid}")
    return cid


# ═══════════════════════════════════════════════════════════
# 3: Scholarship inquiries
# ═══════════════════════════════════════════════════════════
def sc_scholarships():
    _h("SCENARIO 3: Scholarship & discount inquiries")
    fresh_client()
    c = create_test_chat(TEST_ORG_ID, label="becas")
    cid = c["id"]

    send(cid, "Hola, tengo 3 hijos y quiero inscribirlos a todos")
    r2 = send(cid, "¿Tienen algún descuento por meter a los 3 hermanos?")
    assert_contains(r2, ["10%", "descuento", "tercer"], "beca-3er-hijo")

    r3 = send(cid, "¿Y si inscribo un cuarto hijo también?")
    assert_contains(r3, ["15%", "cuarto"], "beca-4to-hijo")

    r4 = send(cid, "Imagina que fueran 5 hijos, ¿qué pasa con el quinto?")
    assert_contains(r4, ["100%", "beca", "quinto"], "beca-5to-hijo")

    r5 = send(cid, "También escuché que hay una beca si mi hijo entró desde kínder "
              "y sigue hasta secundaria, ¿es cierto?")
    assert_contains(r5, ["20%", "continuidad"], "beca-continuidad")

    r6 = send(cid, "¿Me puedes decir cuánto cuesta la colegiatura exactamente?")
    assert_not_contains(r6, ["$", "pesos", "mensualidad"], "no-share-prices")
    assert_contains(r6, ["asesor", "contactar", "personalizada"], "redirect-pricing")

    _info(f"Chat ID: {cid}")
    return cid


# ═══════════════════════════════════════════════════════════
# 4: Grade calculation from DOB
# ═══════════════════════════════════════════════════════════
def sc_grade_calc():
    _h("SCENARIO 4: Grade calculation from DOB")
    fresh_client()
    c = create_test_chat(TEST_ORG_ID, label="grade_calc")
    cid = c["id"]

    send(cid, "Hola, quiero saber en qué grado le tocaría a mi hijo para agosto 2026")

    # Born Aug 1 2020 → Kindergarten for 2026-2027
    r1 = send(cid, "Nació el 1 de agosto de 2020")
    assert_contains(r1, ["kinder", "kindergarten"], "grade-aug1-2020")

    # Born in 2024 → Prenursery for 2026-2027
    r2 = send(cid, "Tengo otro hijo que nació el 15 de enero de 2024")
    assert_contains(r2, ["prenursery", "maternal"], "grade-jan-2024")

    # DOB mismatch - 6yr old asking for high school
    r3 = send(cid, "¿Y si quiero meterlo a preparatoria? El que nació en 2020")
    assert_contains(r3, ["no", "rango", "asesor", "corresponde", "kinder", "kindergarten"],
                    "grade-mismatch")

    _info(f"Chat ID: {cid}")
    return cid


# ═══════════════════════════════════════════════════════════
# 5: Status inquiry
# ═══════════════════════════════════════════════════════════
def sc_status_inquiry():
    _h("SCENARIO 5: Lead status inquiry")
    fresh_client()
    c = create_test_chat(TEST_ORG_ID, label="status_inq")
    cid = c["id"]

    # First create a lead
    send(cid, "Hola, quiero inscribir a mi hijo Diego Pérez López en secundaria 1. "
         "Nació el 5 de marzo de 2013. Está en 6to en el IEST. "
         "Soy María López, 871-555-0001, maria.lopez@test.com")

    # Ask about status
    r2 = send(cid, "¿Cómo va mi proceso de admisión? ¿Cuál es mi estatus?")
    assert_contains(r2, ["estado", "status", "registro", "new", "nuevo", "recibido"],
                    "status-new")

    # Change status and ask again
    set_lead_status(cid, "visit_scheduled")
    fresh_client()
    r3 = send(cid, "¿Ya me pueden confirmar el estatus de mi inscripción?")
    assert_contains(r3, ["visita", "programada", "scheduled", "cita"],
                    "status-visit-scheduled")

    _info(f"Chat ID: {cid}")
    return cid


# ═══════════════════════════════════════════════════════════
# 6: Long conversation (10+ exchanges)
# ═══════════════════════════════════════════════════════════
def sc_long_conversation():
    _h("SCENARIO 6: Long conversation (12+ exchanges)")
    fresh_client()
    c = create_test_chat(TEST_ORG_ID, label="long_conv")
    cid = c["id"]

    send(cid, "Hola")
    send(cid, "Quiero información sobre el colegio para mi hijo")
    send(cid, "¿Qué niveles manejan?")
    send(cid, "Me interesa primaria")
    send(cid, "¿Qué deportes tienen?")
    send(cid, "¿Tienen robótica?")
    send(cid, "Mi hijo se llama Carlos Hernández Vega, nació el 10 de octubre de 2018. "
         "Está en kínder 3 en el Cervantes")
    send(cid, "Yo soy Pedro Hernández, 871-111-2222, pedro.hernandez@test.com")
    send(cid, "¿Cuándo puedo ir a conocer las instalaciones?")
    send(cid, "Prefiero por la mañana, ¿qué tienen la próxima semana?")

    # This should still work after 10+ messages
    r11 = send(cid, "¿Dónde queda exactamente el campus?")
    assert_contains(r11, ["viñedos", "algodón", "500", "torreón"],
                    "long-conv-location")

    send(cid, "Gracias por todo")

    _info(f"Chat ID: {cid}")
    return cid


# ═══════════════════════════════════════════════════════════
# 7: Multi-session (close and come back)
# ═══════════════════════════════════════════════════════════
def sc_multi_session():
    _h("SCENARIO 7: Multi-session continuity")
    fresh_client()
    c = create_test_chat(TEST_ORG_ID, label="multi_sess")
    cid = c["id"]

    # Session 1: register lead
    print("\n  ╔══ SESSION 1: Registro ══╗")
    send(cid, "Hola, quiero inscribir a mi hija Ana Sofía Ruiz Martínez en primaria 1. "
         "Nació el 2 de diciembre de 2019. Viene del Montessori. "
         "Soy Laura Martínez, 871-444-5555, laura.martinez@test.com")
    send(cid, "Cierra la conversación por favor")
    send(cid, "Sí")

    time.sleep(3)
    fresh_client()

    # Session 2: come back and ask about status
    print("\n  ╔══ SESSION 2: Regresa y pregunta estatus ══╗")
    r = send(cid, "Hola, soy Laura Martínez otra vez. ¿Cómo va el proceso de mi hija?")
    # Should recall the lead context
    assert_contains(r, ["ana", "sofía", "ruiz", "proceso", "estado", "registro"],
                    "multi-session-recall")

    _info(f"Chat ID: {cid}")
    return cid


# ═══════════════════════════════════════════════════════════
# 8: Edge cases (invalid DOB, mismatch, twins)
# ═══════════════════════════════════════════════════════════
def sc_edge_cases():
    _h("SCENARIO 8: Edge cases")
    fresh_client()
    c = create_test_chat(TEST_ORG_ID, label="edge_cases")
    cid = c["id"]

    # DOB that doesn't match requested grade
    r1 = send(cid, "Quiero inscribir a mi hijo en preparatoria, nació en 2020")
    assert_contains(r1, ["no", "corresponde", "rango", "asesor", "kinder", "kindergarten", "edad"],
                    "edge-dob-mismatch")

    # Twins
    r2 = send(cid, "Tengo gemelos nacidos el 5 de mayo de 2018: "
              "Ana García Pérez y Luis García Pérez. Están en 2do primaria en el Montessori. "
              "Soy Carmen Pérez, 871-666-7777, carmen.perez@test.com")
    assert_contains(r2, ["ana", "luis", "gemelos", "hermanos", "registr"],
                    "edge-twins")

    # Very short ambiguous message
    r3 = send(cid, "ok")
    # Should not crash or give nonsensical response
    assert_not_contains(r3, ["error", "exception", "traceback"], "edge-short-msg")

    _info(f"Chat ID: {cid}")
    return cid


# ═══════════════════════════════════════════════════════════
# 9: All tools exercised
# ═══════════════════════════════════════════════════════════
def sc_all_tools():
    _h("SCENARIO 9: Exercise all tools")
    fresh_client()
    c = create_test_chat(TEST_ORG_ID, label="all_tools")
    cid = c["id"]

    # create_admissions_lead
    print("\n  ── Tool: create_admissions_lead ──")
    send(cid, "Quiero inscribir a mi hijo Marco Ruiz Vega en secundaria 1. "
         "Nació el 3 de septiembre de 2013, viene del Lancaster. "
         "Soy Patricia Vega, 871-333-4444, patricia.vega@test.com")

    # update_admissions_lead
    print("\n  ── Tool: update_admissions_lead ──")
    send(cid, "Perdón, el nombre correcto es Marcos, no Marco")

    # add_lead_note
    print("\n  ── Tool: add_lead_note ──")
    send(cid, "Le interesa mucho la robótica y el fútbol, por favor anótalo")

    # get_admission_requirements
    print("\n  ── Tool: get_admission_requirements ──")
    send(cid, "¿Me envían los requisitos de secundaria en PDF?")

    # get_next_event
    print("\n  ── Tool: get_next_event ──")
    send(cid, "¿Tienen algún evento próximo para secundaria?")

    # search_availability_slots
    print("\n  ── Tool: search_availability_slots ──")
    send(cid, "Quiero agendar visita, ¿qué tienen la próxima semana por la mañana?")

    # book_appointment (via slot selection)
    print("\n  ── Tool: book_appointment ──")
    send(cid, "La opción 1 por favor")

    # cancel_appointment
    print("\n  ── Tool: cancel_appointment ──")
    send(cid, "Necesito cancelar la cita, me surgió un compromiso de trabajo")

    # get_lead_status
    print("\n  ── Tool: get_lead_status ──")
    r_status = send(cid, "¿Cuál es mi estatus de admisión?")
    assert_contains(r_status, ["estado", "status", "registro", "proceso"],
                    "all-tools-status")

    # close_chat_session
    print("\n  ── Tool: close_chat_session ──")
    send(cid, "Cierra la conversación por favor")
    send(cid, "Sí, cierra")

    _info(f"Chat ID: {cid}")
    return cid


# ═══════════════════════════════════════════════════════════
# 10: Bombardment (multiple questions in one message)
# ═══════════════════════════════════════════════════════════
def sc_bombardment():
    _h("SCENARIO 10: Question bombardment")
    fresh_client()
    c = create_test_chat(TEST_ORG_ID, label="bombardment")
    cid = c["id"]

    r1 = send(cid, "Hola, tengo muchas preguntas: "
              "¿Qué horarios manejan? ¿Tienen transporte? "
              "¿Cuánto cuesta la inscripción? ¿Hay uniformes? "
              "¿Tienen actividades deportivas? ¿Y artísticas?")

    # Should address multiple topics, not crash
    assert_contains(r1, ["horario", "transporte", "deporte", "arte", "actividad"],
                    "bombardment-multi-topic")
    # Should say no transport
    assert_contains(r1, ["no", "transporte"], "bombardment-no-transport")

    # Follow up with another barrage
    r2 = send(cid, "Mi hijo se llama Andrés Torres Salazar, nació el 8 de julio de 2017, "
              "va en 3ro primaria en el San Roberto, quiero cambiarlo para agosto, "
              "también quiero saber de becas y agendar visita todo en uno")

    # Should handle multiple intents
    assert_not_contains(r2, ["error", "exception"], "bombardment-no-error")

    _info(f"Chat ID: {cid}")
    return cid


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════
SCENARIOS = [
    ("1-full-english",     sc_full_english),
    ("2-language-switch",  sc_language_switch),
    ("3-scholarships",     sc_scholarships),
    ("4-grade-calc",       sc_grade_calc),
    ("5-status-inquiry",   sc_status_inquiry),
    ("6-long-conversation", sc_long_conversation),
    ("7-multi-session",    sc_multi_session),
    ("8-edge-cases",       sc_edge_cases),
    ("9-all-tools",        sc_all_tools),
    ("10-bombardment",     sc_bombardment),
]


if __name__ == "__main__":
    os.makedirs(LOG_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(LOG_DIR, f"batch9_{ts}.log")
    log_file = open(log_path, "w", encoding="utf-8")
    sys.stdout = Tee(log_file)

    print(f"{'=' * 64}")
    print(f"  BATCH 9 — Comprehensive Automated Tests")
    print(f"  Started: {datetime.now().isoformat()}")
    print(f"  Log: {log_path}")
    print(f"{'=' * 64}\n")

    # Parse optional scenario filter
    run_only = None
    if len(sys.argv) > 1:
        run_only = sys.argv[1]
        print(f"  Running only scenario: {run_only}\n")

    for name, fn in SCENARIOS:
        if run_only and run_only not in name:
            continue
        try:
            fn()
        except Exception as exc:
            _err(f"SCENARIO {name} CRASHED: {exc}")
            import traceback
            traceback.print_exc()
        if name != SCENARIOS[-1][0]:
            print(f"\n  ⏳ Cooling down {DELAY_SCENARIO}s …")
            time.sleep(DELAY_SCENARIO)

    print_test_summary()
    log_file.close()
