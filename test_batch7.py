#!/usr/bin/env python3
"""
Batch 7: Creative & extreme edge cases.
Wild, realistic scenarios that stress-test the bot's boundaries.
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
    def __init__(self, f):
        self.file = f
        self.stdout = sys.stdout
    def write(self, d):
        self.stdout.write(d)
        self.file.write(d)
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
    for lead in (leads.data or []):
        sb.from_("leads").update({
            "status": status,
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", lead["id"]).execute()
        print(f"  [test] Set lead {lead['id'][:8]}… → {status}")


# ─────────────────────────────────────────────────────────

def sc_grandma_tech_challenged():
    """Elderly grandma barely knows WhatsApp, types slowly, makes typos."""
    _h("Abuelita que apenas sabe usar WhatsApp")
    c = create_test_chat(TEST_ORG_ID, label="abuelita")
    cid = c["id"]

    send(cid, "hola buenod dias")
    send(cid, "disculpe como le hago para inscribie a mi nieto")
    send(cid, "si es para mi nieto el hijo de mi hija que vive en estados unidls")
    send(cid, "se yama marco antonio y tiene 6 anios creo que nasio en 2019 "
         "no se exactamente que dia pero fue en noviembre")
    send(cid, "es que mi hija se va a regresar a mexico y quiere meterlo al colegio "
         "americano. ella se llama maria lopez garcia. su telefono es 871 222 3344 "
         "y su correo no se cual es")
    send(cid, "aaa ya me dijo dice que es maria.lopez@gmail.com")
    send(cid, "cuando pueden venir a verlos? ella llega la proxima semana")

    _info(f"Chat ID: {cid}")
    return cid


def sc_embassy_diplomat():
    """Diplomat family, child has attended schools in 4 countries."""
    _h("Familia diplomática - hijo en 4 países")
    c = create_test_chat(TEST_ORG_ID, label="diplomat")
    cid = c["id"]

    send(cid, "Good morning. My husband works at the US Consulate in Monterrey and we're "
         "being reassigned to Torreón. We need a bilingual school for our daughter.")
    send(cid, "She's attended schools in Germany, Japan, and Brazil before this. "
         "Her name is Sophia Chen-Williams, born April 22 2013. She speaks English, "
         "Mandarin, and some Portuguese. She was in 6th grade at the American School of Monterrey.")
    send(cid, "I'm Catherine Williams, phone +1-555-234-5678, email c.williams@state.gov. "
         "We'd need to start mid-March if possible, not August.")
    send(cid, "Is the IB program available? We need something internationally recognized "
         "for when we transfer again in 2-3 years")
    send(cid, "What about college counseling? She'll likely apply to universities in the US and UK")

    _info(f"Chat ID: {cid}")
    return cid


def sc_angry_review_threat():
    """Person threatens to leave bad Google/FB review if not helped immediately."""
    _h("Amenaza con reseña negativa")
    c = create_test_chat(TEST_ORG_ID, label="angry_review")
    cid = c["id"]

    send(cid, "He mandado 3 mensajes y NADIE me contesta. Pésimo servicio.")
    send(cid, "Si no me dan información AHORA les pongo una reseña de 1 estrella en Google")
    send(cid, "Quiero saber CUÁNTO CUESTA y si hay lugar para secundaria")
    send(cid, "Me dicen o no?? ya me voy al TEC mejor")
    send(cid, "Ok ya, mi hijo se llama Fernando Cruz Ávila, 13 años, nació 9 de marzo 2013. "
         "Va en 1ro de secundaria en una escuela pública. "
         "Yo soy Alejandra Ávila, 871-999-0033, alejandra.avila@test.com")
    send(cid, "¿Hay cupo o no? Contéstenme rápido")

    _info(f"Chat ID: {cid}")
    return cid


def sc_twin_different_grades():
    """Twins born in different years (Dec 31 / Jan 1) - different grade placement."""
    _h("Mellizos nacidos en años distintos (dic/ene)")
    c = create_test_chat(TEST_ORG_ID, label="twins_diff_year")
    cid = c["id"]

    send(cid, "Hola tengo una situación peculiar. Tengo mellizos pero nacieron en "
         "años diferentes: uno el 31 de diciembre de 2016 y la otra el 1 de enero de 2017")
    send(cid, "¿Les tocan grados diferentes? ¿Los pueden poner juntos?")
    send(cid, "El niño se llama Emilio y la niña Renata. Apellidos Garza Mendoza. "
         "Ambos están en 3ro de primaria en el Cervantes ahorita. "
         "Yo soy Lorena Mendoza, 871-333-7788, lorena.mendoza@test.com")
    send(cid, "Es que en el Cervantes están juntos y les va muy bien así. "
         "No queremos que los separen de grado")

    _info(f"Chat ID: {cid}")
    return cid


def sc_homeschooled_child():
    """Child has been homeschooled, no previous school records."""
    _h("Niño homeschool sin historial escolar")
    c = create_test_chat(TEST_ORG_ID, label="homeschool")
    cid = c["id"]

    send(cid, "Hola, mi hijo ha sido educado en casa (homeschool) desde siempre "
         "y queremos que entre al colegio por primera vez")
    send(cid, "Tiene 10 años, nació 14 de febrero de 2016. Se llama Sebastián Mora Torres. "
         "No tiene boletas ni calificaciones oficiales, ¿es un problema?")
    send(cid, "Yo soy Verónica Torres, 871-444-6677, veronica.torres@test.com")
    send(cid, "¿Le harían algún examen de colocación para ver en qué grado va?")
    send(cid, "¿Cuál sería el proceso diferente para un niño homeschool?")

    _info(f"Chat ID: {cid}")
    return cid


def sc_custody_battle():
    """One parent wants to enroll, the other calls to say NO - contradictory."""
    _h("Pleito de custodia - padres contradictorios")
    c = create_test_chat(TEST_ORG_ID, label="custody_fight")
    cid = c["id"]

    # Session 1: Dad enrolls
    print("\n  ╔══ SESSION 1: Papá quiere inscribir ══╗")
    send(cid, "Hola, quiero inscribir a mi hijo Rodrigo Salinas Pérez, "
         "nació 5 de mayo de 2014, va en 5to de primaria en el Lancaster. "
         "Yo soy Pedro Salinas, 871-555-1234, pedro.salinas@test.com")
    send(cid, "Cierra por favor")
    send(cid, "Sí")

    time.sleep(3)
    # Session 2: Mom contradicts
    print("\n  ╔══ SESSION 2: Mamá dice que NO lo inscriban ══╗")
    send(cid, "Buenas tardes, soy la mamá de Rodrigo Salinas. "
         "NO autorizo que lo inscriban. Su papá no tiene la custodia legal.")
    send(cid, "¿Quién autorizó esto? Voy a tomar acciones legales")
    send(cid, "Mi nombre es Sofía Pérez, 871-666-4321, sofia.perez@test.com")

    _info(f"Chat ID: {cid}")
    return cid


def sc_gifted_child():
    """Parent wants to skip a grade because child is gifted."""
    _h("Niño adelantado quiere saltar grado")
    c = create_test_chat(TEST_ORG_ID, label="gifted")
    cid = c["id"]

    send(cid, "Hola, mi hija es superdotada y queremos saber si pueden adelantarla de grado")
    send(cid, "Tiene 8 años pero ya está en nivel de 5to de primaria según sus evaluaciones. "
         "Nació el 12 de julio de 2017. Su psicóloga dice que tiene un CI de 145")
    send(cid, "Se llama Valentina Rojas Contreras, actualmente está en 2do en el Montessori "
         "pero se aburre mucho. Yo soy Diana Contreras, 871-888-1122, diana.contreras@test.com")
    send(cid, "¿Han tenido casos así antes? ¿Qué opciones me dan?")
    send(cid, "¿Tienen programa para niños con altas capacidades?")

    _info(f"Chat ID: {cid}")
    return cid


def sc_teacher_wants_to_work():
    """Someone thinks this is HR and wants to apply for a teaching job."""
    _h("Quiere trabajar como maestro (confusión)")
    c = create_test_chat(TEST_ORG_ID, label="job_seeker")
    cid = c["id"]

    send(cid, "Hola buenas tardes, estoy buscando trabajo como maestro de inglés. "
         "¿Tienen vacantes?")
    send(cid, "Tengo 5 años de experiencia y certificación CELTA. "
         "¿A quién le mando mi CV?")
    send(cid, "Ah ok, entonces este no es el contacto de recursos humanos? "
         "Bueno ya que estoy aquí, mi sobrina quiere entrar al colegio jaja")
    send(cid, "Se llama Ana Lucía Vega Ramos, nació 3 de septiembre de 2018, "
         "va en 1ro de primaria en el IEST. "
         "Su mamá es mi hermana Patricia Vega, 871-111-3344, patricia.vega@test.com")

    _info(f"Chat ID: {cid}")
    return cid


def sc_allergies_medical():
    """Parent very worried about severe allergies and medical emergencies."""
    _h("Alergias severas y emergencias médicas")
    c = create_test_chat(TEST_ORG_ID, label="allergies")
    cid = c["id"]

    send(cid, "Hola, antes de inscribir a mi hijo necesito saber si pueden manejar "
         "alergias severas. Mi hijo es alérgico al cacahuate (anafilaxia) y siempre "
         "tiene que traer su EpiPen")
    send(cid, "¿Tienen enfermería? ¿El personal sabe usar un autoinyector de epinefrina?")
    send(cid, "También es alérgico al látex y a los mariscos. ¿La cafetería puede "
         "garantizar que no haya contaminación cruzada?")
    send(cid, "Se llama Miguel Ángel Fuentes Rivas, nació 8 de abril de 2015, "
         "va en 4to de primaria en el Cervantes. "
         "Yo soy Sandra Rivas, 871-777-9988, sandra.rivas@test.com")
    send(cid, "¿Podemos agendar una visita? Necesito ver la enfermería y hablar con "
         "la nutrióloga de la cafetería")
    send(cid, "La primera que tengan")

    _info(f"Chat ID: {cid}")
    return cid


def sc_three_gen_family():
    """Three generations: grandma enrolling grandchild talks about when SHE went to CAT."""
    _h("3 generaciones - abuela exalumna del CAT")
    c = create_test_chat(TEST_ORG_ID, label="three_gen")
    cid = c["id"]

    send(cid, "¡Hola! Yo fui alumna del CAT hace 40 años, mi hija también fue al CAT, "
         "y ahora quiero inscribir a mi nieta. ¡Somos familia CAT! 💚")
    send(cid, "Mi nieta se llama Ximena Ochoa Delgado, nació 22 de junio de 2020, "
         "está en kínder en el Lancaster. "
         "Yo soy la abuelita pero la mamá es mi hija Paulina Delgado, "
         "871-555-8899, paulina.delgado@test.com")
    send(cid, "¿Siguen teniendo el festival de primavera? Me acuerdo mucho de eso 😊")
    send(cid, "¿Cuánto ha cambiado el colegio? ¿Ya tienen tecnología en los salones?")
    send(cid, "Quiero llevar a mi nieta a conocer. ¿Cuándo puedo ir?")
    send(cid, "La primera de la mañana")

    _info(f"Chat ID: {cid}")
    return cid


# ─────────────────────────────────────────────────────────
SCENARIOS = [
    ("21_abuelita_tech",         sc_grandma_tech_challenged),
    ("22_diplomat_family",       sc_embassy_diplomat),
    ("23_angry_review_threat",   sc_angry_review_threat),
    ("24_twins_diff_year",       sc_twin_different_grades),
    ("25_homeschool",            sc_homeschooled_child),
    ("26_custody_fight",         sc_custody_battle),
    ("27_gifted_child",          sc_gifted_child),
    ("28_job_seeker_confusion",  sc_teacher_wants_to_work),
    ("29_allergies_medical",     sc_allergies_medical),
    ("30_three_generations",     sc_three_gen_family),
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

    print(f"\n{'═'*64}")
    print(f"  RESUMEN BATCH 7 ({ts})")
    print(f"{'═'*64}")
    for name, cid, status in results:
        short_id = cid[:8] if cid != "N/A" else "N/A"
        print(f"  {status} {name} → {short_id}")
    print(f"\n  Logs saved to: {LOG_DIR}/")
    print()
