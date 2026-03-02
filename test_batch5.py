#!/usr/bin/env python3
"""
Batch 5: Diverse scenarios with full logging to test_logs/ folder.
Each scenario writes a timestamped .log file with the full conversation.
"""
import os, sys, time, io
from datetime import datetime
from contextlib import redirect_stdout
from dotenv import load_dotenv
load_dotenv()

from test_chat import (
    create_test_chat, simulate_message, _h, _user, _bot, _info, _err,
    get_supabase_client,
)

TEST_ORG_ID = os.getenv("TEST_ORG_ID", "726f0ce2-edd0-4319-a7fd-7d0bfc4161aa")
LOG_DIR = os.path.join(os.path.dirname(__file__), "test_logs")
DELAY_MSG = 1.5
DELAY_SCENARIO = 4


class Tee:
    """Write to both stdout and a file."""
    def __init__(self, file):
        self.file = file
        self.stdout = sys.stdout
    def write(self, data):
        self.stdout.write(data)
        self.file.write(data)
    def flush(self):
        self.stdout.flush()
        self.file.flush()


def send(cid, msg):
    _user(msg)
    try:
        r = simulate_message(cid, msg)
        _bot(r)
        return r
    except Exception as exc:
        _err(f"Error: {exc}")
        return None
    finally:
        time.sleep(DELAY_MSG)


def set_lead_status(chat_id, status):
    sb = get_supabase_client()
    leads = sb.from_("leads").select("id").eq("wa_chat_id", chat_id).execute()
    data = leads.data if hasattr(leads, "data") else []
    for lead in data:
        sb.from_("leads").update({
            "status": status,
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", lead["id"]).execute()
        print(f"  [test] Set lead {lead['id'][:8]}… → {status}")


# ─────────────────────────────────────────────────────────
# SCENARIOS
# ─────────────────────────────────────────────────────────

def sc_kinder_event_and_visit():
    """Kinder parent: asks about events, books visit, asks about transport."""
    _h("Kinder: Evento + Visita + Transporte")
    chat = create_test_chat(TEST_ORG_ID, label="kinder_full")
    cid = chat["id"]

    send(cid, "Buenas tardes, quiero inscribir a mi hija en kínder")
    send(cid, "Se llama Isabella Flores Martínez, nació el 3 de agosto de 2021. "
         "Está en guardería ahorita.")
    send(cid, "Yo soy Mónica Martínez, 871-222-1100, monica.martinez@test.com")
    send(cid, "¿Tienen algún evento próximo para preescolar?")
    send(cid, "¿Tienen transporte escolar?")
    send(cid, "Ok, ¿me pueden agendar una visita? Cualquier día de la próxima semana por la mañana")
    send(cid, "La opción 2")
    send(cid, "¿Qué tengo que llevar a la visita?")
    send(cid, "Cierra por favor")
    send(cid, "Sí")

    _info(f"Chat ID: {cid}")
    return cid


def sc_sibling_followup():
    """Parent already registered one child, comes back for sibling."""
    _h("Hermano adicional en sesión 2")
    chat = create_test_chat(TEST_ORG_ID, label="sibling_add")
    cid = chat["id"]

    # Session 1
    print("\n  ╔══ SESSION 1: First child ══╗")
    send(cid, "Hola, quiero inscribir a mi hijo en secundaria. Se llama Diego Ramírez Torres, "
         "nació 11 de noviembre de 2012, va en 6to de primaria en el Cervantes. "
         "Yo soy Laura Torres, 871-888-3344, laura.torres@test.com")
    send(cid, "¿Tienen horarios para visita el viernes?")
    send(cid, "La primera")
    send(cid, "Cierra la conversación")
    send(cid, "Sí")

    time.sleep(3)
    # Session 2: add sibling
    print("\n  ╔══ SESSION 2: Add sibling ══╗")
    send(cid, "Hola soy Laura de nuevo. Olvidé decirles que también quiero inscribir a mi otra hija")
    send(cid, "Se llama Camila Ramírez Torres, nació 5 de marzo de 2016, "
         "va en 4to de primaria también en el Cervantes")
    send(cid, "¿La visita que ya tenemos agendada sirve para los dos?")
    send(cid, "¿Me puedes mandar los requisitos para primaria y secundaria?")

    _info(f"Chat ID: {cid}")
    return cid


def sc_cancel_and_rebook():
    """Book, cancel with reason, rebook different day."""
    _h("Cancela y reagenda")
    chat = create_test_chat(TEST_ORG_ID, label="cancel_rebook")
    cid = chat["id"]

    # Session 1: book
    print("\n  ╔══ SESSION 1: Book ══╗")
    send(cid, "Hola, quiero agendar visita para primaria. Mi hijo se llama Mateo Herrera Ríos, "
         "nació 15 de enero de 2018, va en 1ro de kínder en el Lancaster. "
         "Yo soy Alejandra Ríos, 871-999-1122, ale.rios@test.com")
    send(cid, "¿Qué có tienen para el jueves?")
    send(cid, "La primera opción")
    send(cid, "Cierra por favor")
    send(cid, "Si")

    time.sleep(3)
    # Session 2: cancel and rebook
    print("\n  ╔══ SESSION 2: Cancel + rebook ══╗")
    send(cid, "Hola, necesito cancelar mi cita. Me surgió un viaje de trabajo.")
    send(cid, "¿Tienen algo para la próxima semana? De preferencia el martes o miércoles por la mañana")
    send(cid, "La opción 1")

    _info(f"Chat ID: {cid}")
    return cid


def sc_franglais_mixed():
    """User switches between Spanish and English mid-conversation."""
    _h("Spanglish / Code-switching")
    chat = create_test_chat(TEST_ORG_ID, label="spanglish")
    cid = chat["id"]

    send(cid, "Hi! Quiero info del colegio for my son")
    send(cid, "Se llama Daniel, tiene eight years old, born on June 15 2017. "
         "Está en third grade en una escuela here in Torreón, el Instituto Francés")
    send(cid, "I'm Carlos García, phone ocho setenta y uno, cuatro cuatro cuatro, once once. "
         "Email carlos.garcia@test.com")
    send(cid, "What sports do you have? A mi hijo le gusta mucho el soccer y el swimming")
    send(cid, "Awesome, do you have robotics too? He loves coding")
    send(cid, "Can we schedule a visit? Any day next week works for me")
    send(cid, "La 3 please")

    _info(f"Chat ID: {cid}")
    return cid


def sc_multiple_questions_one_msg():
    """User dumps 6 questions in a single message."""
    _h("Bombardeo de preguntas en un mensaje")
    chat = create_test_chat(TEST_ORG_ID, label="multi_questions")
    cid = chat["id"]

    send(cid, "Hola buenas tardes, tengo muchas preguntas:\n"
         "1. ¿Cuánto cuesta la inscripción?\n"
         "2. ¿Tienen descuento por hermanos?\n"
         "3. ¿Cuál es el horario de clase para primaria?\n"
         "4. ¿Tienen transporte escolar?\n"
         "5. ¿Cuáles son los requisitos de admisión?\n"
         "6. ¿Dónde queda el colegio?")
    send(cid, "Bueno, mi hija se llama Renata Soto Vega, nació el 22 de abril de 2016, "
         "está en 4to de primaria en el TEC. "
         "Yo soy Miguel Soto, 871-555-6677, miguel.soto@test.com")
    send(cid, "¿Me pueden mandar los requisitos de primaria?")
    send(cid, "¿Qué actividades extracurriculares tienen?")

    _info(f"Chat ID: {cid}")
    return cid


def sc_late_enrollment_current_cycle():
    """Parent explicitly wants current cycle (not August 2026)."""
    _h("Inscripción ciclo actual (late enrollment)")
    chat = create_test_chat(TEST_ORG_ID, label="late_enroll")
    cid = chat["id"]

    send(cid, "Hola, necesitamos meter a mi hijo YA, no puede esperar a agosto. "
         "Nos acabamos de mudar de Guadalajara.")
    send(cid, "Se llama Santiago Méndez Cruz, tiene 11 años, nació 8 de septiembre de 2014. "
         "Iba en 5to de primaria en el Colegio Finlandés de Guadalajara.")
    send(cid, "Yo soy Paola Cruz, 871-777-4455, paola.cruz@test.com. "
         "El papá es Eduardo Méndez, 33-1234-5678")
    send(cid, "¿Hay cupo para este ciclo? Es urgente, no puede perder el año")
    send(cid, "¿Qué documentos necesitan para procesar la entrada inmediata?")
    send(cid, "¿Puedo ir mañana a dejar los papeles?")
    send(cid, "La 1")

    _info(f"Chat ID: {cid}")
    return cid


def sc_application_started_status():
    """Lead already in application_started, user asks about progress."""
    _h("Lead en application_started pregunta progreso")
    chat = create_test_chat(TEST_ORG_ID, label="app_started")
    cid = chat["id"]

    # Session 1: quick registration
    print("\n  ╔══ SESSION 1: Quick registration ══╗")
    send(cid, "Hola quiero inscribir a mi hija María Fernández López, "
         "nació 1 de julio de 2015, va en 4to primaria en el IEST. "
         "Yo soy Roberto Fernández, 871-111-2233, roberto.fz@test.com")
    send(cid, "Cierra por favor")
    send(cid, "sí")

    # Set status to application_started
    time.sleep(2)
    print("\n  [test] Setting lead to 'application_started'...")
    set_lead_status(cid, "application_started")

    # Session 2
    time.sleep(3)
    print("\n  ╔══ SESSION 2: Asks about application status ══╗")
    send(cid, "Hola soy Roberto. ¿Cómo va el proceso de inscripción de mi hija María?")
    send(cid, "¿Ya revisaron sus documentos?")
    send(cid, "¿Nos van a avisar por teléfono o por correo cuando esté lista la resolución?")

    _info(f"Chat ID: {cid}")
    return cid


def sc_only_wants_price():
    """Person only cares about price, won't give data, leaves frustrated."""
    _h("Solo quiere precio, no da datos")
    chat = create_test_chat(TEST_ORG_ID, label="price_only")
    cid = chat["id"]

    send(cid, "Hola, ¿cuánto cuesta primaria?")
    send(cid, "No quiero dar mis datos, solo dime cuánto cuesta")
    send(cid, "En el Cervantes me dieron el precio por WhatsApp sin problema")
    send(cid, "Ok, ¿me pueden llamar entonces? Solo díganme el precio")
    send(cid, "Bueno dame el teléfono para yo llamar")

    _info(f"Chat ID: {cid}")
    return cid


def sc_existing_student_parent():
    """Parent of current student asking non-admissions questions, then asks for younger sibling."""
    _h("Padre de alumno actual + hermano menor")
    chat = create_test_chat(TEST_ORG_ID, label="existing_parent")
    cid = chat["id"]

    send(cid, "Buenas tardes, mi hijo ya está en el CAT en 3ro de secundaria")
    send(cid, "Quería preguntar cuándo son las vacaciones de semana santa")
    send(cid, "Ah ok, bueno otra cosa. Tengo una hija más chica que quiero inscribir")
    send(cid, "Se llama Valeria Ochoa Pérez, nació 14 de agosto de 2019, "
         "está en kínder en el Montessori")
    send(cid, "Yo soy Marcela Pérez, 871-333-9988, marcela.perez@test.com")
    send(cid, "¿Qué horario manejan para los de preescolar?")
    send(cid, "Genial, quiero agendar visita para conocer esa sección. ¿Qué tienen?")
    send(cid, "La opción 1")

    _info(f"Chat ID: {cid}")
    return cid


def sc_location_only_then_interested():
    """Starts asking only about location, then gets interested."""
    _h("Pregunta ubicación y luego se interesa")
    chat = create_test_chat(TEST_ORG_ID, label="ubicacion_interes")
    cid = chat["id"]

    send(cid, "Hola, ¿dónde queda el Colegio Americano?")
    send(cid, "Ah está cerquita de mi casa. ¿Tienen prepa?")
    send(cid, "Mi hija va a entrar a 1ro de prepa el próximo año. "
         "Se llama Daniela Navarro Ruiz, nació 2 de octubre de 2010, "
         "va en 3ro de secundaria en el IEST")
    send(cid, "Yo soy Fernando Navarro, 871-111-5566, fer.navarro@test.com")
    send(cid, "¿Qué promedio necesita? Tiene 8.5")
    send(cid, "¿Tienen club de debate? Daniela está en el equipo de debate de su escuela")
    send(cid, "Quiero visita, ¿qué tienen para el viernes por la tarde?")
    send(cid, "La 1")

    _info(f"Chat ID: {cid}")
    return cid


# ─────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────
SCENARIOS = [
    ("01_kinder_event_visit",       sc_kinder_event_and_visit),
    ("02_sibling_followup",         sc_sibling_followup),
    ("03_cancel_rebook",            sc_cancel_and_rebook),
    ("04_spanglish",                sc_franglais_mixed),
    ("05_multi_questions",          sc_multiple_questions_one_msg),
    ("06_late_enrollment",          sc_late_enrollment_current_cycle),
    ("07_application_started",      sc_application_started_status),
    ("08_price_only",               sc_only_wants_price),
    ("09_existing_parent_sibling",  sc_existing_student_parent),
    ("10_location_then_interested", sc_location_only_then_interested),
]

if __name__ == "__main__":
    os.makedirs(LOG_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    results = []
    total = len(SCENARIOS)

    for idx, (name, fn) in enumerate(SCENARIOS, 1):
        log_path = os.path.join(LOG_DIR, f"{ts}_{name}.log")
        log_file = open(log_path, "w", encoding="utf-8")
        old_stdout = sys.stdout
        sys.stdout = Tee(log_file)

        print(f"\n{'═'*64}")
        print(f"  [{idx}/{total}] {name}")
        print(f"  Log file: {log_path}")
        print(f"{'═'*64}\n")

        try:
            cid = fn()
            results.append((name, cid, "✅"))
        except Exception as exc:
            import traceback
            traceback.print_exc()
            results.append((name, "N/A", f"❌ {exc}"))

        sys.stdout = old_stdout
        log_file.close()
        print(f"  ✅ {name} → logged to {os.path.basename(log_path)}")

        if idx < total:
            print(f"  ⏳ Pausing {DELAY_SCENARIO}s...")
            time.sleep(DELAY_SCENARIO)

    # Summary
    print(f"\n{'═'*64}")
    print(f"  RESUMEN BATCH 5 ({ts})")
    print(f"{'═'*64}")
    for name, cid, status in results:
        short_id = cid[:8] if cid != "N/A" else "N/A"
        print(f"  {status} {name} → {short_id}")
    print(f"\n  Logs saved to: {LOG_DIR}/")
    print()
