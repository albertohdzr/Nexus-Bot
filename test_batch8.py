#!/usr/bin/env python3
"""
Batch 8 v2: Long conversations with fresh Supabase client per scenario.
Forces httpx connection pool refresh to avoid stale keep-alive.
"""
import os, sys, time, gc
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

from test_chat import (
    create_test_chat, simulate_message, _h, _user, _bot, _info, _err,
)
from app.core.supabase import get_supabase_client

TEST_ORG_ID = os.getenv("TEST_ORG_ID", "726f0ce2-edd0-4319-a7fd-7d0bfc4161aa")
LOG_DIR = os.path.join(os.path.dirname(__file__), "test_logs")
DELAY_MSG = 2.0
DELAY_SCENARIO = 8


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


def fresh_client():
    """Force a brand new Supabase client with fresh HTTP connections."""
    get_supabase_client.cache_clear()
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
                # Force fresh connections on retry
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


# ═══════════════════════════════════════════════════════════
# A: The Indecisive Parent (~25 msgs, 3 sessions)
# ═══════════════════════════════════════════════════════════
def sc_indecisive():
    _h("LARGO A: Padre indeciso (~25 msgs, 3 sesiones)")
    fresh_client()
    c = create_test_chat(TEST_ORG_ID, label="indeciso_v2")
    cid = c["id"]

    print("\n  ╔══ SESSION 1: Discovery + indecision ══╗")
    send(cid, "Hola buenas tardes")
    send(cid, "Quiero información, estoy viendo opciones de colegio para mi hija")
    send(cid, "Tiene 11 años, nació el 20 de marzo de 2015. Está en 5to de primaria")
    send(cid, "No, espera, está en 6to, no en 5to. Perdón me confundí")
    send(cid, "Bueno la verdad no sé si meterla ahora a 6to o esperar a agosto "
         "para que entre a 1ro de secundaria. ¿Qué me recomiendan?")
    send(cid, "Se llama Fernanda Moreno Castillo, viene del Cervantes. "
         "Yo soy Gabriela Castillo, tel 871-222-5566, gabriela.castillo@test.com")
    send(cid, "¿Qué actividades tienen en secundaria? A mi hija le gusta mucho "
         "el arte y la pintura")
    send(cid, "¿Y deportes? Porque también le gusta la natación")
    send(cid, "Ay me quedé pensando... ¿qué pasa si la meto ahorita a 6to? "
         "¿Pierde la opción de entrar a 1ro de secundaria en agosto?")
    send(cid, "Ya platiqué con mi esposo y dice que mejor esperemos a agosto. "
         "Cierra la conversación por favor")
    send(cid, "Sí")

    time.sleep(3)
    fresh_client()

    print("\n  ╔══ SESSION 2: Cambia de opinión, quiere visita ══╗")
    send(cid, "Hola, soy Gabriela otra vez. Ya cambiamos de opinión, sí queremos "
         "meterla para agosto en secundaria")
    send(cid, "Pero quisiera antes ir a conocer. ¿Qué horarios tienen?")
    send(cid, "Mmm, ¿tienen algo en la tarde? Yo trabajo en la mañana")
    send(cid, "Ah no, mejor en la mañana, puedo pedir permiso. ¿El jueves?")
    send(cid, "Hmm, ¿pero no tienen algo más tempranito? Como a las 7?")
    send(cid, "Ok la primera opción de la mañana que tengan")
    send(cid, "Cierra por favor")
    send(cid, "Sí")

    time.sleep(3)
    fresh_client()

    print("\n  ╔══ SESSION 3: Día de la visita + preguntas ══╗")
    send(cid, "Hola, ya vamos para allá pero no encuentro la entrada. "
         "¿Es por el estacionamiento grande o por la otra calle?")
    send(cid, "Gracias, ya llegamos. Otra pregunta: ¿los uniformes los venden aquí mismo?")
    send(cid, "¿Y los libros? ¿Usan tablets o cuadernos?")
    send(cid, "Una última cosa, ¿cuándo son las inscripciones formales para agosto?")
    send(cid, "Perfecto, muchas gracias por toda la paciencia. Cierra la conversación")
    send(cid, "Sí")

    _info(f"Chat ID: {cid}")
    return cid


# ═══════════════════════════════════════════════════════════
# B: Family of 4 children (~20 msgs)
# ═══════════════════════════════════════════════════════════
def sc_four_kids():
    _h("LARGO B: Familia con 4 hijos (~20 msgs)")
    fresh_client()
    c = create_test_chat(TEST_ORG_ID, label="cuatro_hijos_v2")
    cid = c["id"]

    send(cid, "Hola, tenemos 4 hijos y queremos cambiarlos de escuela todos juntos")
    send(cid, "Yo soy Rodrigo Méndez, 871-111-9988, rodrigo.mendez@test.com. "
         "Mi esposa es Ana García, 871-333-7766")
    send(cid, "El mayor se llama Santiago Méndez García, nació 15 de enero de 2010. "
         "Va en 2do de prepa en el TEC")
    send(cid, "La segunda es Isabella Méndez García, nació 3 de mayo de 2013. "
         "Va en 6to de primaria en el TEC también")
    send(cid, "El tercero es Mateo Méndez García, nació 20 de agosto de 2016. "
         "Está en 3ro de primaria en el TEC")
    send(cid, "Y la más chica es Valentina Méndez García, nació 12 de diciembre de 2020. "
         "Está en kínder 2 en el TEC")
    send(cid, "¿Les toca a todos en secciones diferentes verdad?")
    send(cid, "¿Tienen descuento por meter a los 4?")
    send(cid, "¿La visita puede ser para toda la familia? ¿O tenemos que ir a cada sección "
         "por separado?")
    send(cid, "Entendido. Quisiéramos ir el viernes. ¿Qué tienen?")
    send(cid, "La primera que tengan")
    send(cid, "¿Hay estacionamiento suficiente? Vamos a ir mi esposa y yo con los 4 niños")
    send(cid, "¿Nos pueden mandar los requisitos de todas las secciones? "
         "Preescolar, primaria, secundaria y prepa")
    send(cid, "Una duda más: ¿el TEC les puede hacer transferencia directa del expediente "
         "o tenemos que empezar de cero?")
    send(cid, "Ok, ya la última pregunta: ¿cuánto tiempo toma todo el proceso "
         "desde la visita hasta saber si los aceptan?")

    _info(f"Chat ID: {cid}")
    return cid


# ═══════════════════════════════════════════════════════════
# C: Full journey 4 sessions - complete lifecycle
# ═══════════════════════════════════════════════════════════
def sc_full_journey():
    _h("LARGO C: Jornada completa en 4 sesiones (~24 msgs)")
    fresh_client()
    c = create_test_chat(TEST_ORG_ID, label="journey_v2")
    cid = c["id"]

    print("\n  ╔══ SESSION 1: Descubrimiento y registro ══╗")
    send(cid, "Hola, un amigo me recomendó el colegio americano. "
         "¿Me pueden dar información para preescolar?")
    send(cid, "Mi hija se llama Camila Reyes Ortiz, nació 15 de septiembre de 2021. "
         "Actualmente está en una guardería particular")
    send(cid, "Yo soy Diego Reyes, 871-888-4433, diego.reyes@test.com")
    send(cid, "¿Qué horario manejan para preescolar?")
    send(cid, "¿Tienen servicio de estancia extendida o afterschool para los chiquitos?")
    send(cid, "¿Me mandan los requisitos de preescolar?")
    send(cid, "Cierra la conversación, voy a platicarlo con mi esposa")
    send(cid, "Sí")

    time.sleep(3)
    fresh_client()

    print("\n  ╔══ SESSION 2: Regresa y agenda visita ══╗")
    send(cid, "Hola, soy Diego Reyes. Ya platicamos mi esposa y yo y sí queremos visitar")
    send(cid, "¿Qué horarios tienen para la próxima semana?")
    send(cid, "Queremos ir los dos juntos. ¿Puede ser por la mañana temprano?")
    send(cid, "La primera")
    send(cid, "¿Cuánto tarda la visita normalmente?")
    send(cid, "Cierra la conversación por favor")
    send(cid, "Sí")

    time.sleep(2)
    set_lead_status(cid, "visited")
    time.sleep(3)
    fresh_client()

    print("\n  ╔══ SESSION 3: Después de la visita ══╗")
    send(cid, "Hola, fuimos a la visita y nos encantó 😍 Queremos continuar con el proceso")
    send(cid, "¿Cuáles son los siguientes pasos para formalizar la inscripción?")
    send(cid, "¿Los documentos los puedo mandar por correo o tienen que ser presenciales?")
    send(cid, "¿Hay alguna evaluación o examen para preescolar?")
    send(cid, "Cierra por favor")
    send(cid, "Sí")

    time.sleep(2)
    set_lead_status(cid, "enrolled")
    time.sleep(3)
    fresh_client()

    print("\n  ╔══ SESSION 4: ¡Inscrita! Preguntas admin ══╗")
    send(cid, "¡Hola! Ya nos confirmaron la inscripción de Camila 🎉🎉🎉")
    send(cid, "¿Cuándo empieza el ciclo escolar nuevo?")
    send(cid, "¿Hay alguna reunión para padres nuevos antes de agosto?")
    send(cid, "¿Dónde compramos el uniforme?")
    send(cid, "Muchas gracias por todo el proceso, fueron muy amables. "
         "Cierra esta conversación, nos vemos en agosto 😊")
    send(cid, "Sí")

    _info(f"Chat ID: {cid}")
    return cid


# ═══════════════════════════════════════════════════════════
# D: Emotional divorce situation (~18 msgs, 2 sessions)
# ═══════════════════════════════════════════════════════════
def sc_divorce():
    _h("LARGO D: Papá recién divorciado (~18 msgs, 2 sesiones)")
    fresh_client()
    c = create_test_chat(TEST_ORG_ID, label="divorcio_v2")
    cid = c["id"]

    print("\n  ╔══ SESSION 1: Primera interacción emotiva ══╗")
    send(cid, "Hola, disculpe que le moleste. Estoy pasando por un momento difícil "
         "y necesito cambiar a mis hijos de escuela lo antes posible")
    send(cid, "Nos estamos separando mi esposa y yo, y los niños van a la escuela "
         "cerca de donde vivía ella. Yo me mudé a la zona de Viñedos y necesito "
         "algo más cercano para cuando me toque tenerlos")
    send(cid, "Son dos: Diego tiene 9 años, nació 4 de abril de 2016, va en 3ro "
         "en el Lancaster. Y Sofía tiene 7, nació 22 de agosto de 2018, "
         "va en 1ro en el mismo Lancaster")
    send(cid, "Perdón, estoy un poco abrumado con todo esto. Solo quiero lo mejor "
         "para ellos")
    send(cid, "¿El colegio americano queda cerca de Viñedos verdad?")
    send(cid, "Yo soy Ricardo Fuentes, 871-999-4455, ricardo.fuentes@test.com")
    send(cid, "¿Ambos pueden ir al mismo campus?")
    send(cid, "¿Tienen servicio de psicología? Creo que les vendría bien algo de "
         "apoyo emocional con todo el cambio")
    send(cid, "Cierra la conversación, necesito procesar todo esto")
    send(cid, "Sí")

    time.sleep(3)
    fresh_client()

    print("\n  ╔══ SESSION 2: Más tranquilo, listo para avanzar ══╗")
    send(cid, "Hola, soy Ricardo otra vez. Ya me siento mejor y quiero avanzar")
    send(cid, "¿Ya quedaron registrados mis dos hijos?")
    send(cid, "Quiero agendar visita. ¿Puede ser esta semana?")
    send(cid, "La más temprana que tengan")
    send(cid, "Una cosa: ¿necesito traer algo firmado por su mamá? "
         "Tenemos custodia compartida")
    send(cid, "Ok gracias, eso me deja más tranquilo. Cierra la conversación por favor")
    send(cid, "Sí")

    _info(f"Chat ID: {cid}")
    return cid


# ─────────────────────────────────────────────────────────
SCENARIOS = [
    ("31_indeciso_largo",       sc_indecisive),
    ("32_cuatro_hijos",         sc_four_kids),
    ("33_journey_4_sessions",   sc_full_journey),
    ("34_divorcio_emotivo",     sc_divorce),
]

if __name__ == "__main__":
    os.makedirs(LOG_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    results = []
    total = len(SCENARIOS)

    for idx, (name, fn) in enumerate(SCENARIOS, 1):
        fresh_client()

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
    print(f"  RESUMEN BATCH 8 v2 ({ts})")
    print(f"{'═'*64}")
    for name, cid, status in results:
        short_id = cid[:8] if cid != "N/A" else "N/A"
        print(f"  {status} {name} → {short_id}")
    print(f"\n  Logs saved to: {LOG_DIR}/")
    print()
