#!/usr/bin/env python3
"""
Batch 4: Multi-session lifecycle simulations.
Tests full lead lifecycle across multiple sessions + edge cases.
"""
import os, sys, time, json
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv()

from test_chat import (
    create_test_chat, simulate_message, _h, _user, _bot, _info, _err,
    get_supabase_client
)

TEST_ORG_ID = os.getenv("TEST_ORG_ID", "726f0ce2-edd0-4319-a7fd-7d0bfc4161aa")
DELAY_MSG = 1.5    # delay between messages
DELAY_SCENARIO = 5  # delay between scenarios


def send(cid, msg, step_label=""):
    """Send a message and print the exchange with error handling."""
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


def set_lead_status(chat_id: str, status: str):
    """Manually set all leads on a chat to a specific status (for testing)."""
    sb = get_supabase_client()
    leads = sb.from_("leads").select("id").eq("wa_chat_id", chat_id).execute()
    data = leads.data if hasattr(leads, 'data') else []
    for lead in data:
        sb.from_("leads").update({
            "status": status,
            "updated_at": datetime.utcnow().isoformat()
        }).eq("id", lead["id"]).execute()
        print(f"  [test] Set lead {lead['id'][:8]}… → {status}")


# ══════════════════════════════════════════════════════════
# SCENARIO 1: Full lifecycle across 3 sessions
# ══════════════════════════════════════════════════════════
def scenario_full_lifecycle():
    _h("SCENARIO 1: Full Lifecycle (3 sessions)")
    chat = create_test_chat(TEST_ORG_ID, label="lifecycle")
    cid = chat["id"]

    # ── Session 1: Registration & Visit Booking ──
    print("\n  ╔══ SESSION 1: Registration & Visit Booking ══╗")

    send(cid, "Hola buenas tardes")

    send(cid, "Quiero inscribir a mi hija en primaria. Se llama Sofía Delgado Ruiz, "
         "nació el 10 de mayo de 2017. Está en 2do de kínder en el Montessori.")

    send(cid, "Yo soy Andrea Ruiz Sánchez, tel 871-100-2233, correo andrea.ruiz@test.com")

    send(cid, "Si, vi que tienen robótica y eso me parece increíble. "
         "¿Qué más actividades tienen para primaria?")

    send(cid, "¿Me puedes mandar los requisitos de primaria?")

    send(cid, "Perfecto, quiero agendar visita. ¿Qué tienen para el jueves?")

    send(cid, "La opción 1 por favor")

    send(cid, "Gracias, ¿puedes cerrar esta conversación?")
    send(cid, "Si")

    # ── Session 2: Returns, asks about appointment, reschedules ──
    time.sleep(3)
    print("\n  ╔══ SESSION 2: Reschedule Appointment ══╗")

    send(cid, "Hola, soy Andrea de nuevo. Tenía una cita agendada.")

    send(cid, "¿Me pueden recordar cuándo es mi cita?")

    send(cid, "Ay, ese día no voy a poder. ¿La podemos cambiar para el viernes?")

    send(cid, "La que sea más tempranito")

    send(cid, "Listo, gracias. Cierra la conversación por favor.")
    send(cid, "Sí adelante")

    # ── Session 3: Day of visit — asks directions, what to bring ──
    time.sleep(3)
    print("\n  ╔══ SESSION 3: Day-of Visit ══╗")

    send(cid, "¡Hola! Ya vamos para allá 🚗")

    send(cid, "¿Cómo llego? ¿Por dónde entro?")

    send(cid, "¿Tenemos que llevar algún documento o algo?")

    send(cid, "Perfecto, ya vamos llegando. Gracias por todo.")

    send(cid, "Ya puedes cerrar la conversación, muchas gracias.")
    send(cid, "Si")

    _info(f"Chat ID: {cid}")
    return cid, "lifecycle"


# ══════════════════════════════════════════════════════════
# SCENARIO 2: Lost/Disqualified lead
# ══════════════════════════════════════════════════════════
def scenario_lost_lead():
    _h("SCENARIO 2: Lost (Disqualified) Lead")
    chat = create_test_chat(TEST_ORG_ID, label="lost_lead")
    cid = chat["id"]

    # First, create a lead normally
    print("\n  ╔══ SESSION 1: Create lead then mark as lost ══╗")

    send(cid, "Hola, quiero información para secundaria")

    send(cid, "Mi hijo se llama Adrián Reyes Luna, nació 20 de febrero de 2012. "
         "Está en 6to de primaria en el IEST.")

    send(cid, "Yo soy Carolina Luna, 871-555-1234, carolina.luna@test.com")

    send(cid, "Gracias, cierra la conversación.")
    send(cid, "ok")

    # Now manually set lead to 'lost'
    time.sleep(2)
    print("\n  [test] Setting lead to 'lost'...")
    set_lead_status(cid, "lost")

    # Session 2: User comes back — should NOT be able to book
    time.sleep(3)
    print("\n  ╔══ SESSION 2: Returns after being marked lost ══╗")

    send(cid, "Hola, quiero agendar una visita al campus para mi hijo Adrián")

    send(cid, "¿No me pueden dar cita? ¿Por qué no?")

    send(cid, "Bueno, entonces ¿quién me puede ayudar?")

    _info(f"Chat ID: {cid}")
    return cid, "lost_lead"


# ══════════════════════════════════════════════════════════
# SCENARIO 3: Inscription status inquiry
# ══════════════════════════════════════════════════════════
def scenario_status_inquiry():
    _h("SCENARIO 3: Status Inquiry")
    chat = create_test_chat(TEST_ORG_ID, label="status_query")
    cid = chat["id"]

    # Create a lead with visit_scheduled status
    print("\n  ╔══ SESSION 1: Create lead + Schedule ══╗")

    send(cid, "Hola quiero inscribir a mi hija Valentina Torres Méndez, "
         "nació 15 marzo 2016, está en 3ro de primaria en el Cervantes. "
         "Yo soy Mariana Méndez, 871-444-5577, mariana.mendez@test.com")

    send(cid, "¿Qué horarios tienen para visita? El viernes me queda bien")

    send(cid, "La opción 1")

    send(cid, "Gracias, cierra por favor")
    send(cid, "si")

    # Session 2: Ask about process status
    time.sleep(3)
    print("\n  ╔══ SESSION 2: Ask about process status ══╗")

    send(cid, "Hola, soy Mariana otra vez. Quiero saber cómo va el proceso de inscripción de mi hija Valentina.")

    send(cid, "¿Cuándo es nuestra visita?")

    send(cid, "¿Y después de la visita qué sigue?")

    send(cid, "¿Hay algo que deba preparar antes de ir?")

    _info(f"Chat ID: {cid}")
    return cid, "status_inquiry"


# ══════════════════════════════════════════════════════════
# SCENARIO 4: Kindergarten section (Preescolar)
# ══════════════════════════════════════════════════════════
def scenario_preescolar():
    _h("SCENARIO 4: Preescolar - Maternal a Kinder")
    chat = create_test_chat(TEST_ORG_ID, label="preescolar")
    cid = chat["id"]

    send(cid, "Hola, mi bebé tiene 2 años y medio. ¿Tienen programa para niños tan chiquitos?")

    send(cid, "Ah qué bueno. Se llama Mateo García Vega, nació el 1 de diciembre de 2023. "
         "Ahorita no va a ninguna escuela.")

    send(cid, "Soy Diana Vega, 871-333-4455, diana.vega@test.com")

    send(cid, "¿Qué actividades tienen para los más chiquitos? ¿Hay deportes o arte?")

    send(cid, "¿Cómo es el horario de maternal?")

    send(cid, "¿Me pueden mandar los requisitos?")

    _info(f"Chat ID: {cid}")
    return cid, "preescolar"


# ══════════════════════════════════════════════════════════
# SCENARIO 5: Preparatoria section
# ══════════════════════════════════════════════════════════
def scenario_preparatoria():
    _h("SCENARIO 5: Preparatoria - English Speaker")
    chat = create_test_chat(TEST_ORG_ID, label="prepa_english")
    cid = chat["id"]

    send(cid, "Hi, I'm looking for a high school for my daughter. "
         "She's 15, born March 3rd 2011. Currently in 9th grade at a school in Dallas, Texas.")

    send(cid, "Her name is Emily Johnson. I'm Sarah Johnson, phone 871-777-8811, "
         "email sarah.johnson@test.com. We just moved to Torreon.")

    send(cid, "What's the minimum GPA requirement? She has a 3.8 GPA")

    send(cid, "Does she need to take any admission test?")

    send(cid, "Can you send me the requirements document for high school?")

    send(cid, "Can I schedule a visit for Thursday morning?")

    send(cid, "Option 1 please")

    _info(f"Chat ID: {cid}")
    return cid, "preparatoria"


# ══════════════════════════════════════════════════════════
# SCENARIO 6: Secundaria section with status check
# ══════════════════════════════════════════════════════════
def scenario_secundaria():
    _h("SCENARIO 6: Secundaria - Visit, comes back, visited status")
    chat = create_test_chat(TEST_ORG_ID, label="secundaria")
    cid = chat["id"]

    # Session 1: Create lead + book visit
    print("\n  ╔══ SESSION 1: Register + Book Visit ══╗")

    send(cid, "Hola, quiero inscribir a mi hijo en secundaria. Se llama Andrés Morales Díaz, "
         "nació 7 julio 2013, va en 6to de primaria en el Cervantes. "
         "Yo soy Jorge Morales, 871-666-7788, jorge.morales@test.com")

    send(cid, "¿Qué horarios tienen para una visita? El jueves o viernes me queda bien")

    send(cid, "La primera opción")

    send(cid, "Cierra la conversación por favor")
    send(cid, "si")

    # Set to 'visited' to simulate the visit already happened
    time.sleep(2)
    print("\n  [test] Setting lead to 'visited'...")
    set_lead_status(cid, "visited")

    # Session 2: Come back asking about next steps after visit
    time.sleep(3)
    print("\n  ╔══ SESSION 2: After visit — ask about next steps ══╗")

    send(cid, "Hola, ya fuimos a la visita hace unos días. ¿Cuál es el siguiente paso?")

    send(cid, "¿Cuánto tardan en darnos respuesta sobre si lo aceptan?")

    send(cid, "¿Necesitamos mandar algún documento adicional?")

    _info(f"Chat ID: {cid}")
    return cid, "secundaria"


# ══════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════
if __name__ == "__main__":
    scenarios = [
        scenario_full_lifecycle,
        scenario_lost_lead,
        scenario_status_inquiry,
        scenario_preescolar,
        scenario_preparatoria,
        scenario_secundaria,
    ]

    results = []
    total = len(scenarios)

    for idx, fn in enumerate(scenarios, 1):
        print(f"\n{'═'*64}")
        print(f"  Starting scenario {idx}/{total}")
        print(f"{'═'*64}")

        try:
            cid, name = fn()
            results.append((name, cid, "✅"))
        except Exception as exc:
            import traceback
            traceback.print_exc()
            results.append((fn.__name__, "N/A", f"❌ {exc}"))

        if idx < total:
            print(f"\n{'─'*40}")
            print(f"  ⏳ Pausing {DELAY_SCENARIO}s before next scenario...")
            print(f"{'─'*40}")
            time.sleep(DELAY_SCENARIO)

    # Final summary
    _h("RESUMEN BATCH 4")
    for name, cid, status in results:
        short_id = cid[:8] if cid != "N/A" else "N/A"
        print(f"  {status} {name} → {short_id}")
    print()
