# 🏗️ Nexus-Chatbot — Auditoría de Producción

**Fecha:** 2026-02-24\
**Alcance:** Análisis completo de la arquitectura, identificación de problemas y
propuesta de mejoras priorizadas.

---

## 📋 Resumen Ejecutivo

El chatbot funciona correctamente en su estado actual, pero tiene **varios
riesgos significativos** que podrían causar problemas bajo carga real o en
escenarios de error. Los problemas principales son:

1. **Sin manejo de errores de la API de OpenAI** — si OpenAI falla, el chatbot
   crashea silenciosamente
2. **Cliente de Supabase se recrea en cada request** — desperdicia recursos y
   conexiones
3. **Archivo monolítico de 3,200 líneas** (`process_router.py`) — difícil de
   mantener y debuggear
4. **Sin logging estructurado** — solo `print()`, imposible de monitorear en
   producción
5. **Sin timeouts ni reintentos** en llamadas a OpenAI
6. **Endpoints síncronos procesando I/O** — bloquean el event loop

---

## 🔍 Análisis Detallado por Componente

### 1. `app/core/config.py` — Configuración

**Estado actual:** Funcional pero básico.

| Problema                     | Severidad | Descripción                                                  |
| ---------------------------- | --------- | ------------------------------------------------------------ |
| Sin validación               | 🟡 Media  | No valida que las variables obligatorias existan al arranque |
| Sin tipado estricto          | 🟢 Baja   | Todos los valores son `Optional[str]` implícitos             |
| `render.yaml` desactualizado | 🔴 Alta   | No incluye `OPEN_AI_KEY` en las env vars de Render           |

**Mejora propuesta:**

```python
# Usar Pydantic Settings para validación automática al arranque
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    supabase_url: str
    supabase_key: str
    supabase_service_key: str | None = None
    openai_api_key: str  # Falla inmediatamente si no existe
    whatsapp_access_token: str
    whatsapp_verify_token: str = "my_secure_token"
    cron_secret: str | None = None
    supabase_storage_bucket: str = "media"
    default_model: str = "gpt-5.2-2025-12-11"
    
    class Config:
        env_file = ".env"
        # Mapeo de nombres de env vars a campos
        fields = {
            "openai_api_key": {"env": "OPEN_AI_KEY"},
            "supabase_service_key": {"env": "SUPABASE_SERVICE_ROLE_KEY"},
        }
```

---

### 2. `app/core/supabase.py` — Cliente de Base de Datos

**Estado actual:** ⚠️ Problema crítico de rendimiento.

| Problema                           | Severidad | Descripción                                                                                                                                                                                   |
| ---------------------------------- | --------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Crea cliente nuevo en cada llamada | 🔴 Alta   | `get_supabase_client()` llama `create_client()` cada vez que se invoca. Esto crea una nueva conexión HTTP por cada operación de BD. En `process_router.py` se llama ~15-20 veces por request. |
| Sin connection pooling             | 🔴 Alta   | No hay reutilización de conexiones                                                                                                                                                            |

**Mejora propuesta:**

```python
from functools import lru_cache

@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """Singleton: crea el cliente una sola vez y lo reutiliza."""
    if not settings.supabase_url:
        raise RuntimeError("Supabase is not configured")
    key = settings.supabase_service_key or settings.supabase_key
    if not key:
        raise RuntimeError("Supabase key is not configured")
    return create_client(settings.supabase_url, key)
```

---

### 3. `app/chat/service.py` — Cliente de OpenAI

**Estado actual:** Funcional tras la migración, pero sin protecciones.

| Problema                  | Severidad | Descripción                                              |
| ------------------------- | --------- | -------------------------------------------------------- |
| Sin singleton del cliente | 🟡 Media  | Crea un nuevo `OpenAI()` en cada llamada                 |
| Sin timeout configurado   | 🔴 Alta   | Si OpenAI tarda 60+ segundos, el request queda colgado   |
| Sin retry automático      | 🔴 Alta   | Errores transitorios (429, 500, 503) crashean la request |

**Mejora propuesta:**

```python
from functools import lru_cache

DEFAULT_MODEL = "gpt-5.2-2025-12-11"

@lru_cache(maxsize=1)
def get_openai_client() -> OpenAI:
    """Singleton con timeout y reintentos configurados."""
    if not settings.openai_api_key:
        raise RuntimeError("OPEN_AI_KEY is not set")
    return OpenAI(
        api_key=settings.openai_api_key,
        timeout=30.0,        # Timeout de 30 segundos
        max_retries=3,        # Reintenta hasta 3 veces con backoff exponencial
    )
```

El SDK de OpenAI v2.x ya incluye **reintentos automáticos con backoff
exponencial** para errores 429 (rate limit), 500, y 503. Solo hay que configurar
`max_retries`.

---

### 4. `app/whatsapp/webhook.py` — Recepción de Webhooks

**Estado actual:** Funcional, pero con un problema arquitectónico importante.

| Problema                | Severidad | Descripción                                                                                                                                                                 |
| ----------------------- | --------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Procesamiento síncrono  | 🔴 Alta   | `handle_incoming_messages()` es síncrono y se ejecuta DENTRO del handler del webhook. Si OpenAI tarda 10 seg, WhatsApp no recibe el `200 OK` a tiempo y reenvía el webhook. |
| Sin respuesta inmediata | 🔴 Alta   | WhatsApp espera `200 OK` en max 20 seg. El procesamiento completo puede tardar más.                                                                                         |

**Mejora propuesta:**

```python
from fastapi import BackgroundTasks

@router.post("/webhook")
async def receive_webhook(request: Request, background_tasks: BackgroundTasks):
    body = await request.json()
    
    if body.get("object") != "whatsapp_business_account":
        return Response(content="Not a WhatsApp API event", status_code=404)
    
    # Procesar entries para extraer el value
    value = _extract_webhook_value(body)  # función auxiliar
    
    if value:
        # Ejecutar en background - responder 200 inmediatamente
        background_tasks.add_task(handle_incoming_messages, value)
        background_tasks.add_task(handle_status_updates, value)
    
    return Response(content="EVENT_RECEIVED", status_code=200)
```

> **Nota:** `processing.py` ya invoca `process-whatsapp-queue` como edge
> function, lo cual ayuda. Pero el `handle_incoming_messages` mismo hace ~8
> queries a Supabase antes de llegar ahí, lo cual puede tardar.

---

### 5. `app/whatsapp/process_router.py` — Cerebro del Chatbot (3,198 líneas)

**Este es el archivo más crítico y el que más problemas tiene.**

#### 5.1 Problemas Estructurales

| Problema                        | Severidad | Descripción                                                                                                                                       |
| ------------------------------- | --------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| Archivo monolítico              | 🟡 Media  | 3,198 líneas en un solo archivo. Mezcla routing, lógica de negocio, tools, prompts, y utilidades.                                                 |
| Prompt hardcodeado              | 🟡 Media  | El prompt del sistema está en el código Python (líneas 99-292). Debería estar en la BD o en un archivo separado.                                  |
| `import re` dentro de funciones | 🟢 Baja   | `_sanitize_assistant_response`, `_validate_and_fix_response`, `_extract_preferred_date` importan `re` localmente en vez de al inicio del archivo. |

#### 5.2 Problemas de Resiliencia

| Problema                           | Severidad      | Descripción                                                                                                                                                                         |
| ---------------------------------- | -------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Sin try/except en llamada a OpenAI | 🔴 **Crítica** | La llamada principal (línea 2067) y el followup (línea 2275) NO tienen manejo de excepciones. Si OpenAI devuelve error, **el chatbot crashea y el usuario nunca recibe respuesta.** |
| Sin fallback ante fallas           | 🔴 Alta        | No hay mensaje de "lo siento, hubo un error" si algo falla                                                                                                                          |
| Sin rate limiting interno          | 🟡 Media       | Un usuario podría enviar 100 mensajes seguidos y generar 100 llamadas a OpenAI                                                                                                      |

**Mejora propuesta para la llamada principal:**

```python
try:
    completion = client.chat.completions.create(
        model=model,
        messages=messages_payload,
        tools=tools,
    )
    assistant_message = completion.choices[0].message
    assistant_text = assistant_message.content or ""
    tool_calls = assistant_message.tool_calls or []
except Exception as exc:
    print(f"[admissions] OpenAI API error: {exc}")
    # Enviar mensaje de fallback al usuario
    return _send_assistant_message(
        "Disculpa, estoy teniendo dificultades técnicas en este momento. "
        "Por favor intenta de nuevo en unos minutos, o si prefieres, "
        "puedes llamarnos al 8711123687.",
        org, chat, session_id,
    )
```

#### 5.3 Problemas de Logging

| Problema               | Severidad | Descripción                                                                                             |
| ---------------------- | --------- | ------------------------------------------------------------------------------------------------------- |
| Solo `print()`         | 🟡 Media  | Sin niveles (INFO, WARNING, ERROR), sin formato estructurado                                            |
| Sin tracking de costos | 🟡 Media  | No se registra `completion.usage.total_tokens` para monitorear gasto                                    |
| Sin `ai_logs`          | 🟡 Media  | La tabla `ai_logs` existe en la BD (migración `20251228121000_ai_logs.sql`) pero NO se usa en el código |

**Mejora propuesta:**

```python
import logging

logger = logging.getLogger("nexus.admissions")

# Después de cada llamada a OpenAI:
logger.info(
    "llm_completion",
    extra={
        "chat_id": chat.get("id"),
        "model": model,
        "prompt_tokens": completion.usage.prompt_tokens,
        "completion_tokens": completion.usage.completion_tokens,
        "total_tokens": completion.usage.total_tokens,
        "tool_calls": len(tool_calls),
        "latency_ms": elapsed_ms,
    },
)

# También guardar en la tabla ai_logs para monitoreo
supabase.from_("ai_logs").insert({
    "chat_id": chat.get("id"),
    "model": model,
    "prompt_tokens": completion.usage.prompt_tokens,
    "completion_tokens": completion.usage.completion_tokens,
    "total_tokens": completion.usage.total_tokens,
    "created_at": datetime.utcnow().isoformat(),
}).execute()
```

#### 5.4 Refactorización Sugerida

Dividir `process_router.py` en módulos más pequeños:

```
app/whatsapp/
├── process_router.py          # Solo los endpoints (POST /process, POST /close)
├── llm/
│   ├── __init__.py
│   ├── prompt_builder.py      # _build_prompt()
│   ├── completion.py          # Llamadas a OpenAI con retry/fallback
│   └── response_validator.py  # _validate_and_fix_response(), _sanitize_assistant_response()
├── tools/
│   ├── __init__.py
│   ├── definitions.py         # Lista de tools/schemas
│   ├── leads.py               # create/update lead, add note
│   ├── appointments.py        # search slots, book, cancel
│   ├── events.py              # get_next_event, register_event
│   └── requirements.py        # get_admission_requirements
├── sessions/
│   ├── __init__.py
│   ├── manager.py             # _ensure_active_session, _load_session_messages
│   └── closer.py              # close_chat_session endpoint
└── utils/
    ├── __init__.py
    ├── dates.py               # _extract_preferred_date, _format_slot_window_local
    └── state.py               # _get_chat_state, _set_chat_state_value, etc.
```

---

### 6. `app/whatsapp/outbound.py` — Envío de Mensajes WhatsApp

**Estado actual:** Bien escrito, pero con mejoras menores.

| Problema             | Severidad | Descripción                                                          |
| -------------------- | --------- | -------------------------------------------------------------------- |
| Usa `httpx` síncrono | 🟢 Baja   | Funciona, pero `httpx.AsyncClient` sería más eficiente               |
| Código duplicado     | 🟢 Baja   | Las 6 funciones de envío repiten el mismo patrón de request/response |

---

### 7. `app/whatsapp/processing.py` — Procesamiento de Mensajes Entrantes

**Estado actual:** Sólido, con buen manejo de duplicados.

| Problema                                      | Severidad | Descripción                                                                |
| --------------------------------------------- | --------- | -------------------------------------------------------------------------- |
| `datetime.utcnow()` deprecado                 | 🟢 Baja   | Debería usar `datetime.now(timezone.utc)` (ya importa timezone)            |
| Sin manejo de errores en edge function invoke | 🟡 Media  | Si `process-whatsapp-queue` falla, el error se loguea pero no se reintenta |

---

### 8. `render.yaml` — Configuración de Deploy

| Problema                        | Severidad      | Descripción                                                                                 |
| ------------------------------- | -------------- | ------------------------------------------------------------------------------------------- |
| Falta `OPEN_AI_KEY`             | 🔴 **Crítica** | La variable de OpenAI no está en la lista de env vars de Render. **El deploy va a fallar.** |
| Falta `SUPABASE_STORAGE_BUCKET` | 🟡 Media       | Tiene default "media" en el código, pero el .env tiene "CAT"                                |
| Sin health check                | 🟡 Media       | No hay configuración de health check para Render                                            |
| Un solo worker                  | 🟡 Media       | Sin Gunicorn, solo 1 worker de uvicorn                                                      |

---

### 9. `app/main.py` — Aplicación Principal

| Problema                          | Severidad | Descripción                                                                    |
| --------------------------------- | --------- | ------------------------------------------------------------------------------ |
| Endpoints de prueba en producción | 🟡 Media  | `/usuarios` GET/POST parecen endpoints de prueba que no deberían estar en prod |
| Sin CORS middleware               | 🟡 Media  | Si el frontend hace requests, necesita CORS                                    |
| Sin middleware de logging         | 🟡 Media  | No hay tracking de requests                                                    |

---

## 🎯 Plan de Acción Priorizado

### 🔴 Prioridad 1 — Críticos (hacer AHORA antes de ir a producción)

| # | Acción                                                               | Esfuerzo | Impacto                                     |
| - | -------------------------------------------------------------------- | -------- | ------------------------------------------- |
| 1 | **Agregar `OPEN_AI_KEY` al `render.yaml`**                           | 2 min    | Sin esto, el deploy falla                   |
| 2 | **Singleton del cliente Supabase** (`lru_cache`)                     | 5 min    | Elimina ~20 conexiones nuevas por request   |
| 3 | **Singleton del cliente OpenAI** con `timeout=30` y `max_retries=3`  | 5 min    | Manejo automático de rate limits y timeouts |
| 4 | **Try/except en llamadas a OpenAI** con mensaje fallback             | 15 min   | Evita que el bot muera silenciosamente      |
| 5 | **Responder 200 inmediatamente en webhook** y procesar en background | 20 min   | Evita que WhatsApp reenvíe mensajes         |

### 🟡 Prioridad 2 — Importantes (primera semana)

| #  | Acción                                                | Esfuerzo | Impacto                                          |
| -- | ----------------------------------------------------- | -------- | ------------------------------------------------ |
| 6  | Implementar logging estructurado con `logging` module | 1 hora   | Monitoreo real en producción                     |
| 7  | Registrar uso de tokens en tabla `ai_logs`            | 30 min   | Control de costos de OpenAI                      |
| 8  | Agregar health check endpoint (`/health`)             | 5 min    | Render puede verificar que el servicio está vivo |
| 9  | Validar config al arranque con Pydantic Settings      | 30 min   | Falla rápido si falta config                     |
| 10 | Quitar endpoints de prueba (`/usuarios`)              | 2 min    | Limpieza de seguridad                            |

### 🟢 Prioridad 3 — Mejoras (siguientes sprints)

| #  | Acción                                      | Esfuerzo  | Impacto                              |
| -- | ------------------------------------------- | --------- | ------------------------------------ |
| 11 | Refactorizar `process_router.py` en módulos | 4-6 horas | Mantenibilidad a largo plazo         |
| 12 | Mover prompt del sistema a tabla de BD      | 1-2 horas | Actualizar comportamiento sin deploy |
| 13 | Agregar Gunicorn con múltiples workers      | 30 min    | Mejor concurrencia                   |
| 14 | Middleware de request logging y CORS        | 30 min    | Observabilidad y seguridad           |
| 15 | Convertir endpoints a `async def`           | 2-3 horas | Mejor rendimiento bajo carga         |

---

## 💰 Estimación de Costos — OpenAI GPT-5.2

**Nota importante:** Monitorea el uso de tokens las primeras semanas. El prompt
del sistema es largo (~2,000+ tokens) y se envía en CADA mensaje. Esto puede ser
costoso a escala.

**Recomendación:** Implementar el logging de tokens (Punto #7) antes de ir a
producción para tener visibilidad de costos desde el día 1.

---

## ✅ Lo que YA está bien hecho

- ✅ Detección de mensajes duplicados (idempotency)
- ✅ Sanitización de respuestas del LLM (thinking tags, JSON leaks)
- ✅ Validación post-respuesta para detectar datos inventados
- ✅ Acumulación de mensajes antes de procesar (batching)
- ✅ Manejo de media (imágenes, documentos, audio)
- ✅ Sesiones de chat con expiración
- ✅ Sistema de tools bien diseñado con schemas Pydantic
- ✅ WhatsApp template sync vía webhook
