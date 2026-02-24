#!/usr/bin/env python3
"""
Batch 3: Exhaustive interactive edge-case scenarios.
Runs sequentially with delays to avoid rate limiting.
"""
import os, sys, time
from dotenv import load_dotenv
load_dotenv()

from test_chat import create_test_chat, simulate_message, _h, _user, _bot, _info, _err, _step

TEST_ORG_ID = os.getenv("TEST_ORG_ID", "726f0ce2-edd0-4319-a7fd-7d0bfc4161aa")

SCENARIOS = [
    # ── F: Changes mind 3 times about grade ──
    {
        "name": "F: Cambia de opinión 3 veces",
        "label": "cambio_opinion",
        "msgs": [
            "Hola buenas tardes",
            "Quiero información sobre preparatoria para mi hija",
            "Bueno pensándolo bien, creo que le toca secundaria, tiene 13 años",
            "No espera, me confundí. Ella tiene 11 años y nació el 15 de enero de 2015. ¿A qué grado le toca?",
            "Ah ok, entonces sí es primaria. Se llama Regina Castañeda López. Está en el Cervantes en 5to.",
            "Yo soy su papá, Manuel Castañeda. Mi cel es 8711001122 y correo manuel.castaneda@test.com",
            "¿Me ayudan a agendar una visita por favor? El miércoles si se puede",
            "La opción 1",
        ],
    },
    # ── G: Custodia compartida ──
    {
        "name": "G: Custodia compartida y coordinación",
        "label": "custodia",
        "msgs": [
            "Hola, necesito información para inscribir a mi hijo",
            "Mire, la situación es que estoy divorciada y tenemos custodia compartida. "
            "Mi ex esposo ya había preguntado en otro colegio pero queremos evaluar el CAT también.",
            "Mi hijo se llama Sebastián Ortega Ramírez, nació 3 de abril de 2014. Está en 5to en el IEST.",
            "Yo soy Claudia Ramírez Mora. Tel 871-222-3344, correo claudia.ramirez@test.com. "
            "Pero OJO: mi ex esposo, Miguel Ortega, también puede comunicarse. Su tel es 871-555-6677.",
            "Los dos necesitamos estar en la visita. ¿Podemos ir los dos juntos?",
            "El viernes por la tarde si hay espacio",
            "La primera opción está bien",
        ],
    },
    # ── H: Pide beca/descuento insistente ──
    {
        "name": "H: Quiere beca o descuento por hermanos",
        "label": "beca_descuento",
        "msgs": [
            "Buenas, ¿tienen algún programa de becas?",
            "¿Y descuento por hermanos? Tengo 3 hijos",
            "En serio no hay ningún tipo de descuento? En otros colegios sí dan",
            "Bueno, entonces ¿cómo me entero de los costos?",
            "Mi hijo mayor se llama Diego, tiene 14 años, nació el 5 de mayo de 2011. Va en 2do de secundaria en el IEST.",
            "Yo soy Gabriela Herrera, 871-888-9900, gabriela.herrera@test.com",
        ],
    },
    # ── I: Pregunta por tema NO de admisiones ──
    {
        "name": "I: Tema fuera de scope (pagos, calificaciones)",
        "label": "fuera_scope",
        "msgs": [
            "Hola, mi hijo ya está inscrito en el CAT y quiero preguntar por sus calificaciones",
            "¿Entonces con quién me comunico?",
            "Ah ok, otra cosa: ¿cómo pago la colegiatura atrasada?",
            "Bueno ya que estamos, también tengo otro hijo más chico que quiero inscribir",
            "Se llama Emilio Gutiérrez Reyes, 5 años, nació 20 de diciembre 2020. Está en kínder en el Lancaster.",
            "Yo soy Ricardo Gutiérrez, 871-444-5566, ricardo.gutierrez@test.com",
        ],
    },
    # ── J: Gemelos ──
    {
        "name": "J: Gemelos, mismo grado",
        "label": "gemelos",
        "msgs": [
            "Hola, tengo gemelos que quiero inscribir",
            "Se llaman Matías y Valentina Herrera Solís. Nacieron el 22 de marzo de 2017. "
            "Están en 2do de primaria en el Instituto Irlandés.",
            "Yo soy Adriana Solís. 871-333-2211, adriana.solis@test.com",
            "¿Los pueden poner en el mismo salón o los separan?",
            "Quiero agendar visita para que los conozcan. ¿Qué tienen para el jueves?",
            "La opción 1",
        ],
    },
    # ── K: Alumno reprobado / situación académica difícil ──
    {
        "name": "K: Alumno reprobado, caso sensible",
        "label": "reprobado",
        "msgs": [
            "Buenas tardes, quiero ver si mi hijo puede entrar al CAT",
            "La verdad es que le ha costado la escuela. Reprobó un año y lo tuvieron que repetir. "
            "Ahorita tiene 14 pero apenas va en 1ro de secundaria.",
            "Se llama Kevin Salazar Morales, nació 12 de agosto de 2011. Está en la Secundaria Federal #5.",
            "Yo soy Laura Morales, 871-111-0099, laura.morales@test.com. En serio queremos un cambio de ambiente para él.",
        ],
    },
    # ── L: Solo quiere ubicación y horarios generales ──
    {
        "name": "L: Solo ubicación, sin intención de inscripción",
        "label": "solo_ubicacion",
        "msgs": [
            "Hola, ¿dónde queda el colegio?",
            "¿A qué hora entran los de primaria?",
            "¿Tienen estacionamiento para visitas?",
            "Gracias eso es todo",
        ],
    },
    # ── M: Persona que manda audios/stickers (simula con texto describe) ──
    {
        "name": "M: Mensajes ambiguos y muy cortos",
        "label": "msgs_cortos",
        "msgs": [
            "Hola",
            "si",
            "ok",
            "mmm",
            "ya",
            "quiero info",
            "primaria",
            "cuanto cuesta",
            "a ya, bueno luego les llamo",
        ],
    },
    # ── N: Múltiples grados - familia que se muda de otra ciudad ──
    {
        "name": "N: Familia de 4 hijos, se mudan de Monterrey",
        "label": "4_hijos_mudanza",
        "msgs": [
            "Buenas tardes, nos vamos a mudar a Torreón desde Monterrey en julio y necesitamos "
            "colegio para nuestros 4 hijos",
            "Son:\n"
            "- Emilia 16 años, 8 sept 2009, 1ro prepa en el San Roberto\n"
            "- Tomás 13 años, 15 enero 2013, 1ro secundaria San Roberto\n"
            "- Isabella 9 años, 30 junio 2016, 4to primaria San Roberto\n"
            "- Nicolás 5 años, 2 agosto 2020, kínder San Roberto",
            "Yo soy Ana Paula Delgado. Tel 811-987-6543, correo anapaula.delgado@test.com. "
            "Mi esposo es Andrés Ochoa, tel 811-123-4567.",
            "¿Tienen espacio para los 4? Es muy importante que entren al mismo colegio",
            "Necesitamos los requisitos para todos los niveles por favor",
        ],
    },
    # ── O: Persona impaciente que quiere todo rápido ──
    {
        "name": "O: Impaciente, quiere todo en 1 minuto",
        "label": "impaciente",
        "msgs": [
            "Hola necesito inscribir a mi hijo ya, se llama Pablo Ríos Méndez, 7 años, "
            "nació 4 de marzo 2019, va en 2do primaria en el Tec de Monterrey, "
            "yo soy Alejandro Ríos, 871-999-0011, alejandro.rios@test.com, "
            "quiero visita mañana temprano si hay y los requisitos de primaria por favor",
            "Rápido, ¿hay espacio o no?",
            "La opción 1",
        ],
    },
]


def run_one(scenario, idx, total):
    name = scenario["name"]
    label = scenario["label"]
    msgs = scenario["msgs"]
    
    _h(f"[{idx}/{total}] {name}")
    chat = create_test_chat(TEST_ORG_ID, label=label)
    cid = chat["id"]
    
    for i, m in enumerate(msgs, 1):
        _step(i, len(msgs), name)
        _user(m)
        try:
            r = simulate_message(cid, m)
            _bot(r)
        except Exception as exc:
            _err(f"Error: {exc}")
        print()
        time.sleep(1)  # Small delay between messages
    
    _info(f"Chat ID: {cid} (kept for analysis)")
    print()
    return cid


if __name__ == "__main__":
    results = []
    total = len(SCENARIOS)
    
    for idx, sc in enumerate(SCENARIOS, 1):
        try:
            cid = run_one(sc, idx, total)
            results.append((sc["name"], cid, "✅"))
        except Exception as exc:
            _err(f"Scenario {sc['name']} FAILED: {exc}")
            results.append((sc["name"], "N/A", f"❌ {exc}"))
        
        # Delay between scenarios to avoid rate limits
        if idx < total:
            print(f"\n{'─'*40}")
            print(f"  ⏳ Pausing 3s before next scenario...")
            print(f"{'─'*40}\n")
            time.sleep(3)
    
    # Summary
    _h("RESUMEN BATCH 3")
    for name, cid, status in results:
        short_id = cid[:8] if cid != "N/A" else "N/A"
        print(f"  {status} {name} → {short_id}")
    print()
