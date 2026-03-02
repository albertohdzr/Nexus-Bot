#!/usr/bin/env python3
"""
Batch 6: More edge cases - stress tests.
Focus on tricky interactions, error recovery, boundary conditions.
"""
import os, sys, time
from datetime import datetime
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

def sc_wrong_dates():
    """User gives impossible dates, contradictory ages, tests correction."""
    _h("Fechas imposibles y contradictorias")
    chat = create_test_chat(TEST_ORG_ID, label="wrong_dates")
    cid = chat["id"]

    send(cid, "Hola, mi hijo tiene 8 años y nació el 30 de febrero de 2017")
    send(cid, "Perdón, quise decir 28 de febrero de 2017")
    send(cid, "Bueno en realidad tiene 9 años, ¿a qué grado le toca?")
    send(cid, "Se llama Luis González Pérez. Va en el IEST en 3ro de primaria. "
         "Yo soy Patricia Pérez, 871-222-3344, patricia.perez@test.com")
    send(cid, "¿Puedo ir a visitarlos el domingo?")
    send(cid, "Ok, ¿y el sábado?")
    send(cid, "Ya, el lunes entonces. Por la mañana")
    send(cid, "La 1")

    _info(f"Chat ID: {cid}")
    return cid


def sc_competitor_comparison():
    """Parent keeps comparing to competitors, asks about differentiators."""
    _h("Compara con competencia")
    chat = create_test_chat(TEST_ORG_ID, label="competitor")
    cid = chat["id"]

    send(cid, "Hola. Estoy comparando entre el CAT, el Cervantes y el TEC. "
         "¿Qué hace diferente al CAT?")
    send(cid, "El Cervantes me ofrece beca del 30% y el TEC tiene mejor laboratorio. "
         "¿Ustedes qué ofrecen?")
    send(cid, "¿Cuántos idiomas enseñan? El TEC tiene francés y mandarín")
    send(cid, "Mi hija se llama Sofía Herrera Ortiz, nació 5 de enero de 2012, "
         "va en 1ro de secundaria en el Cervantes. "
         "Yo soy Roberto Herrera, 871-111-5555, roberto.herrera@test.com")
    send(cid, "¿Pueden igualar la beca del Cervantes?")
    send(cid, "Bueno, quiero agendar una visita para comparar en persona")
    send(cid, "Cualquiera de la próxima semana en la mañana")
    send(cid, "La 2")

    _info(f"Chat ID: {cid}")
    return cid


def sc_whatsapp_media():
    """User says they sent a photo/audio but we only see text."""
    _h("Menciona media (foto/audio)")
    chat = create_test_chat(TEST_ORG_ID, label="media_mention")
    cid = chat["id"]

    send(cid, "Hola, le mando la foto del acta de nacimiento de mi hijo")
    send(cid, "¿Ya la vieron? ¿Está bien?")
    send(cid, "Ahh ok. Bueno, mi hijo se llama Carlos Medina Soto, "
         "nació 12 de enero de 2015, va en 4to en el Montessori. "
         "Yo soy Ana Soto, 871-666-7700, ana.soto@test.com")
    send(cid, "¿Me agendan visita? Lo que sea de esta semana")
    send(cid, "La primera")

    _info(f"Chat ID: {cid}")
    return cid


def sc_enrolled_parent_returns():
    """Lead marked enrolled comes back thanking and asking admin questions."""
    _h("Lead enrolled regresa a agradecer")
    chat = create_test_chat(TEST_ORG_ID, label="enrolled_thanks")
    cid = chat["id"]

    # Quick reg
    send(cid, "Hola, quiero inscribir a mi hija. Ana Torres Vega, nació 7 de junio 2016, "
         "está en 3ro primaria en el IEST. Yo soy Luis Torres, 871-444-8899, luis.torres@test.com")
    send(cid, "Cierra la conversación")
    send(cid, "ok")

    time.sleep(2)
    set_lead_status(cid, "enrolled")

    time.sleep(3)
    # Session 2: comes back
    send(cid, "¡Hola! Ya nos aceptaron, ¡muchas gracias por toda la ayuda! 🎉")
    send(cid, "¿Cuándo empiezan las clases en agosto?")
    send(cid, "¿Necesitamos comprar uniforme antes? ¿Dónde lo venden?")

    _info(f"Chat ID: {cid}")
    return cid


def sc_very_young_child():
    """Parent with a 1-year-old baby asking about preschool for the future."""
    _h("Bebé de 1 año - pregunta a futuro")
    chat = create_test_chat(TEST_ORG_ID, label="baby_future")
    cid = chat["id"]

    send(cid, "Hola, mi bebé tiene 1 año y medio. ¿A qué edad pueden entrar?")
    send(cid, "Se llama Emiliano Rivas López, nació 7 de septiembre de 2024")
    send(cid, "Yo soy Daniela López, 871-333-0011, daniela.lopez@test.com")
    send(cid, "¿Tienen lista de espera para cuando le toque?")
    send(cid, "¿Cuáles son los requisitos para Maternal?")

    _info(f"Chat ID: {cid}")
    return cid


def sc_teacher_referral():
    """Someone referred by a teacher at the school."""
    _h("Referido por maestro del colegio")
    chat = create_test_chat(TEST_ORG_ID, label="teacher_ref")
    cid = chat["id"]

    send(cid, "Hola, la maestra Jessica de preescolar me recomendó el colegio. "
         "Somos vecinas y me habló muy bien del programa.")
    send(cid, "Mi hija se llama Ximena Vargas Coronado, nació 14 de mayo de 2021, "
         "está en un maternal particular aquí en Viñedos")
    send(cid, "Yo soy Alejandra Coronado, 871-555-9911, ale.coronado@test.com")
    send(cid, "¿Qué me recomienda la maestra Jessica? ¿Preescolar o maternal?")
    send(cid, "Quiero agendar visita, de preferencia tempranito")
    send(cid, "La primera")

    _info(f"Chat ID: {cid}")
    return cid


def sc_financial_concern():
    """Parent mentions economic difficulty - sensitive case."""
    _h("Preocupación económica - caso sensible")
    chat = create_test_chat(TEST_ORG_ID, label="financial")
    cid = chat["id"]

    send(cid, "Buenas tardes, me interesa mucho el colegio para mi hijo pero la verdad "
         "nuestra situación económica no es la mejor ahorita")
    send(cid, "¿Tienen algún tipo de apoyo o plan de pagos?")
    send(cid, "Mi hijo es muy bueno en la escuela, tiene promedio de 9.8 y le encanta "
         "la robótica. Se llama Emiliano Rojas Fuentes, nació 3 de marzo de 2013, "
         "va en 6to de primaria en la Escuela Pública #12")
    send(cid, "Yo soy Martha Fuentes, 871-444-0022, martha.fuentes@test.com")

    _info(f"Chat ID: {cid}")
    return cid


def sc_returning_after_months():
    """Simulates someone who inquired months ago returning."""
    _h("Regresa después de meses")
    chat = create_test_chat(TEST_ORG_ID, label="returning_old")
    cid = chat["id"]

    # Session 1
    send(cid, "Hola, quiero info sobre preescolar. Mi hija Valentina Ochoa Ríos, "
         "nació 20 de agosto de 2022, va en guardería. "
         "Yo soy Sandra Ríos, 871-999-8877, sandra.rios@test.com")
    send(cid, "Cierra por favor")
    send(cid, "ok")

    time.sleep(3)
    # Session 2: months later
    send(cid, "Hola, yo había preguntado hace meses por mi hija Valentina. "
         "¿Todavía tienen espacio para agosto?")
    send(cid, "¿Me recuerdan qué documentos necesito?")
    send(cid, "¿Puedo agendar visita? El miércoles o jueves")
    send(cid, "La 1")

    _info(f"Chat ID: {cid}")
    return cid


def sc_accessibility_question():
    """Parent asks about accessibility/special needs."""
    _h("Accesibilidad y necesidades especiales")
    chat = create_test_chat(TEST_ORG_ID, label="accessibility")
    cid = chat["id"]

    send(cid, "Buenas tardes, mi hijo usa silla de ruedas. "
         "¿El campus es accesible para él?")
    send(cid, "¿Tienen rampas y elevadores? ¿Qué tipo de apoyo le pueden dar?")
    send(cid, "Se llama Rodrigo Salinas Mora, nació 8 de octubre de 2013, "
         "va en 5to de primaria en el Cervantes. "
         "Yo soy Carmen Mora, 871-777-1122, carmen.mora@test.com")
    send(cid, "¿Podemos ir a una visita para ver si las instalaciones funcionan para él?")
    send(cid, "La primera opción que tengan por la mañana")

    _info(f"Chat ID: {cid}")
    return cid


def sc_rapid_successive_msgs():
    """User sends all info in one massive mega-message."""
    _h("Todo en un solo mensaje masivo")
    chat = create_test_chat(TEST_ORG_ID, label="mega_message")
    cid = chat["id"]

    send(cid,
        "Hola buenas tardes soy Fernanda Castillo mi tel es 871-888-5544 "
        "y mi correo es fer.castillo@test.com. Quiero inscribir a mis dos hijos "
        "el primero se llama Santiago Mejía Castillo nació el 2 de abril de 2014 "
        "va en 5to de primaria en el IEST y la segunda se llama Luciana Mejía Castillo "
        "nació el 15 de noviembre de 2017 va en kínder 3 en el IEST también. "
        "Quiero agendarles visita para el jueves o viernes de la próxima semana "
        "por la mañana y también quiero que me manden los requisitos de primaria "
        "y de preescolar por favor. Ah y una cosa más mi esposo se llama Eduardo "
        "Mejía su tel es 871-777-2233 por si necesitan contactarlo también. Gracias!")
    send(cid, "¿Hay lugar para los dos?")
    send(cid, "La primera opción que den")

    _info(f"Chat ID: {cid}")
    return cid


# ─────────────────────────────────────────────────────────
SCENARIOS = [
    ("11_wrong_dates",              sc_wrong_dates),
    ("12_competitor_comparison",    sc_competitor_comparison),
    ("13_media_mention",            sc_whatsapp_media),
    ("14_enrolled_returns",         sc_enrolled_parent_returns),
    ("15_baby_future",              sc_very_young_child),
    ("16_teacher_referral",         sc_teacher_referral),
    ("17_financial_concern",        sc_financial_concern),
    ("18_returning_months",         sc_returning_after_months),
    ("19_accessibility",            sc_accessibility_question),
    ("20_mega_message",             sc_rapid_successive_msgs),
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
    print(f"  RESUMEN BATCH 6 ({ts})")
    print(f"{'═'*64}")
    for name, cid, status in results:
        short_id = cid[:8] if cid != "N/A" else "N/A"
        print(f"  {status} {name} → {short_id}")
    print(f"\n  Logs saved to: {LOG_DIR}/")
    print()
