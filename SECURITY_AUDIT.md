# 🔒 Auditoría de Seguridad — Nexus-Chatbot

**Fecha:** 2026-02-24\
**Versión del Código:** Actual (main)\
**Auditor:** Auditoría automatizada

---

## 📊 Resumen Ejecutivo

| Métrica                          | Valor       |
| -------------------------------- | ----------- |
| **Total de Endpoints**           | 16          |
| **Protegidos**                   | 4           |
| **Sin Protección (🔴 CRÍTICO)**  | 10          |
| **Parcialmente Protegidos (🟡)** | 2           |
| **Severidad General**            | 🔴 **ALTA** |

---

## 🗺️ Inventario Completo de Endpoints

### 1. `app/main.py` — Endpoints Raíz

| # | Método | Ruta        | Auth       | Severidad      | Notas                                                             |
| - | ------ | ----------- | ---------- | -------------- | ----------------------------------------------------------------- |
| 1 | `GET`  | `/`         | ❌ Ninguna | 🟢 Bajo        | Health check. Aceptable sin auth.                                 |
| 2 | `GET`  | `/usuarios` | ❌ Ninguna | 🔴 **CRÍTICO** | Expone **TODOS** los registros de la tabla `usuarios` sin filtro. |
| 3 | `POST` | `/usuarios` | ❌ Ninguna | 🔴 **CRÍTICO** | Permite crear usuarios arbitrarios sin autenticación.             |

### 2. `app/chat/router.py` — Chat/AI (prefijo: `/chat`)

| # | Método | Ruta           | Auth       | Severidad      | Notas                                                                                 |
| - | ------ | -------------- | ---------- | -------------- | ------------------------------------------------------------------------------------- |
| 4 | `POST` | `/chat`        | ❌ Ninguna | 🔴 **CRÍTICO** | Proxy abierto a OpenAI. Cualquier persona puede consumir tu API key y generar costos. |
| 5 | `POST` | `/chat/stream` | ❌ Ninguna | 🔴 **CRÍTICO** | Mismo problema que `/chat`, con streaming.                                            |
| 6 | `POST` | `/chat/tools`  | ❌ Ninguna | 🔴 **CRÍTICO** | Permite ejecución de tools (crear tickets, analizar imágenes) sin autenticación.      |

### 3. `app/whatsapp/webhook.py` — Webhook de WhatsApp (prefijo: `/whatsapp`)

| # | Método | Ruta                | Auth            | Severidad | Notas                                                                                                                         |
| - | ------ | ------------------- | --------------- | --------- | ----------------------------------------------------------------------------------------------------------------------------- |
| 7 | `GET`  | `/whatsapp/webhook` | ✅ Verify Token | 🟢 Bajo   | Verificación estándar de Meta. Token compartido.                                                                              |
| 8 | `POST` | `/whatsapp/webhook` | 🟡 Parcial      | 🟡 Medio  | Valida `object == "whatsapp_business_account"` pero **no verifica** la firma HMAC del payload (header `X-Hub-Signature-256`). |

### 4. `app/whatsapp/outbound_router.py` — Envío de Mensajes (prefijo: `/whatsapp`)

| #  | Método | Ruta                      | Auth       | Severidad      | Notas                                                                         |
| -- | ------ | ------------------------- | ---------- | -------------- | ----------------------------------------------------------------------------- |
| 9  | `POST` | `/whatsapp/send/text`     | ❌ Ninguna | 🔴 **CRÍTICO** | Cualquiera puede enviar mensajes WhatsApp a cualquier número usando tu token. |
| 10 | `POST` | `/whatsapp/send/read`     | ❌ Ninguna | 🔴 **ALTO**    | Permite marcar mensajes como leídos.                                          |
| 11 | `POST` | `/whatsapp/send/media`    | ❌ Ninguna | 🔴 **ALTO**    | Permite subir media a WhatsApp (potencial abuso).                             |
| 12 | `POST` | `/whatsapp/send/image`    | ❌ Ninguna | 🔴 **CRÍTICO** | Permite enviar imágenes a cualquier número.                                   |
| 13 | `POST` | `/whatsapp/send/audio`    | ❌ Ninguna | 🔴 **CRÍTICO** | Permite enviar audio a cualquier número.                                      |
| 14 | `POST` | `/whatsapp/send/document` | ❌ Ninguna | 🔴 **CRÍTICO** | Permite enviar documentos a cualquier número.                                 |

### 5. `app/whatsapp/process_router.py` — Backend de Procesamiento (prefijo: `/api/whatsapp`)

| #  | Método | Ruta                                    | Auth                    | Severidad      | Notas                                                                                                                                |
| -- | ------ | --------------------------------------- | ----------------------- | -------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| 15 | `POST` | `/api/whatsapp/process`                 | ✅ Bearer + CRON_SECRET | 🟢 Bajo        | Protegido correctamente con `_require_cron_secret()`.                                                                                |
| 16 | `GET`  | `/api/whatsapp/chats/{chat_id}/history` | ❌ Ninguna              | 🔴 **CRÍTICO** | Expone historial completo de conversaciones. IDOR: cualquiera con un `chat_id` (UUID adivinable) puede leer mensajes privados.       |
| 17 | `POST` | `/api/whatsapp/chats/close-session`     | 🟡 Parcial              | 🟡 Medio       | Valida que `org_id` coincida con el chat, pero **no autentica** al caller. Solo impide acceso cruzado entre orgs, no acceso anónimo. |

---

## 🚨 Hallazgos Críticos

### HALLAZGO 1: Secretos Expuestos en `.env` del Repositorio

**Severidad: 🔴 CRÍTICA**

Aunque `.env` está en `.gitignore`, el archivo contiene secretos con valores
reales localmente:

- `SUPABASE_KEY` / `SUPABASE_SERVICE_ROLE_KEY`
- `XAI_API_KEY`
- `WHATSAPP_ACCESS_TOKEN`
- `CRON_SECRET`
- `OPEN_ROUTER_API_KEY`
- `OPEN_AI_KEY`

**⚠️ Si alguna vez se comiteó este archivo al repositorio**, todos los secretos
están comprometidos y deben rotarse inmediatamente.

**Verificación recomendada:**

```bash
git log --all --diff-filter=A -- .env
```

---

### HALLAZGO 2: Supabase Service Role Key como Cliente Único

**Severidad: 🔴 CRÍTICA**

```python
# app/core/supabase.py:15
key = settings.supabase_service_key or settings.supabase_key
```

El backend usa la **Service Role Key** como cliente Supabase predeterminado.
Esta clave **bypasea todas las políticas RLS**. Esto significa que:

- Incluso si tienes RLS bien configurada, el backend la ignora completamente.
- Cualquier endpoint sin auth puede leer/escribir cualquier dato de cualquier
  organización.

---

### HALLAZGO 3: Proxy Abierto a OpenAI (`/chat/*`)

**Severidad: 🔴 CRÍTICA**

Los 3 endpoints de chat son proxies completamente abiertos a la API de OpenAI:

- No hay autenticación
- No hay rate limiting
- El usuario puede especificar el modelo (`request.model`)
- El usuario controla el `system_prompt`

**Impacto:**

- Cualquier persona puede generar costos ilimitados en tu cuenta OpenAI
- Se puede usar para generar contenido malicioso a tu nombre
- Posible prompt injection via `system_prompt`

---

### HALLAZGO 4: Endpoints de WhatsApp Outbound Sin Auth

**Severidad: 🔴 CRÍTICA**

Los 6 endpoints en `/whatsapp/send/*` permiten a **cualquier persona**:

1. Enviar mensajes de texto a cualquier número de WhatsApp
2. Enviar imágenes, audio y documentos
3. Marcar mensajes como leídos
4. Subir media

**Impacto:** Spam masivo, suplantación de identidad, abuso de la cuenta de
WhatsApp Business, posible bloqueo de la cuenta por Meta.

---

### HALLAZGO 5: IDOR en Historial de Chat

**Severidad: 🔴 CRÍTICA**

```python
# process_router.py:2516-2578
@router.get("/chats/{chat_id}/history")
def get_chat_history_endpoint(chat_id: str):
    # No authentication, no authorization
    # Anyone with a UUID can read private WhatsApp conversations
```

Un atacante puede enumerar UUIDs o adivinar `chat_id`s para acceder a
conversaciones privadas de WhatsApp.

---

### HALLAZGO 6: Webhook de WhatsApp Sin Verificación HMAC

**Severidad: 🟡 MEDIA**

El endpoint `POST /whatsapp/webhook` no verifica el header `X-Hub-Signature-256`
de Meta. Esto permite que un atacante envíe webhooks falsos para:

- Inyectar mensajes falsos en la base de datos
- Triggear procesamiento de AI con contenido arbitrario
- Potencialmente manipular el estado de los chats

---

### HALLAZGO 7: Endpoints "/usuarios" Expuestos

**Severidad: 🔴 CRÍTICA**

```python
# app/main.py:22-27
@app.get("/usuarios")
def get_users():
    supabase = get_supabase_client()
    response = supabase.table("usuarios").select("*").execute()
```

Devuelve `SELECT *` sin filtro ni autenticación. Dependiendo de qué hay en la
tabla `usuarios`, esto podría exponer PII (emails, nombres, etc.).

---

### HALLAZGO 8: Sin CORS Configurado

**Severidad: 🟡 MEDIA**

No hay middleware CORS configurado en `app/main.py`. Dependiendo del despliegue:

- Si se accede desde un frontend web, CORS abierto permite que cualquier dominio
  haga requests.
- Si es solo backend-to-backend, el riesgo es menor.

---

### HALLAZGO 9: Sin Rate Limiting

**Severidad: 🟡 MEDIA**

Ningún endpoint tiene rate limiting. Esto permite:

- Ataques de denegación de servicio (DoS)
- Abuso de los proxies OpenAI/WhatsApp
- Fuerza bruta en endpoints sin auth

---

### HALLAZGO 10: Logging de Información Sensible

**Severidad: 🟡 MEDIA**

Múltiples `print()` statements logean datos que podrían ser sensibles:

- Números de WhatsApp (`wa_id`)
- Nombres de contactos
- Contenido de mensajes
- Datos de leads (nombres de alumnos, emails, teléfonos)

En producción, estos logs pueden quedar expuestos en el panel de Render.

---

## ✅ Plan de Remediación

### Prioridad 1 — Inmediato (Bloquear acceso no autorizado)

#### 1A. Crear un middleware de autenticación

```python
# app/core/auth.py
from typing import Optional
from fastapi import Header, HTTPException

from app.core.config import settings


def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    """Simple API key guard for internal/admin endpoints."""
    if not settings.api_secret:
        raise HTTPException(status_code=500, detail="API_SECRET not configured")
    if x_api_key != settings.api_secret:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def require_cron_secret(authorization: Optional[str] = Header(default=None)) -> None:
    """Bearer token guard for cron/queue endpoints."""
    if not settings.cron_secret:
        raise HTTPException(status_code=500, detail="CRON_SECRET not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization.split("Bearer ", 1)[1].strip()
    if token != settings.cron_secret:
        raise HTTPException(status_code=403, detail="Forbidden")
```

#### 1B. Proteger TODOS los endpoints

Agregar `dependencies=[Depends(require_api_key)]` a todos los routers inseguros:

```python
# chat/router.py
from fastapi import Depends
from app.core.auth import require_api_key

router = APIRouter(
    prefix="/chat",
    tags=["chat"],
    dependencies=[Depends(require_api_key)],
)
```

```python
# whatsapp/outbound_router.py
router = APIRouter(
    prefix="/whatsapp",
    tags=["whatsapp"],
    dependencies=[Depends(require_api_key)],
)
```

#### 1C. Proteger `/usuarios` y `/chats/{chat_id}/history`

```python
# main.py
@app.get("/usuarios", dependencies=[Depends(require_api_key)])
def get_users(): ...

@app.post("/usuarios", dependencies=[Depends(require_api_key)])
def create_user(...): ...
```

### Prioridad 2 — Corto Plazo (1-2 semanas)

| Acción                               | Detalle                                                                            |
| ------------------------------------ | ---------------------------------------------------------------------------------- |
| **Verificar firma HMAC del webhook** | Validar `X-Hub-Signature-256` con `APP_SECRET` de Meta en `POST /whatsapp/webhook` |
| **Agregar CORS**                     | `app.add_middleware(CORSMiddleware, allow_origins=[...])` con dominios específicos |
| **Agregar Rate Limiting**            | Usar `slowapi` o middleware custom para limitar requests por IP                    |
| **Rotar todos los secretos**         | Si `.env` fue comiteado alguna vez, rotar TODAS las claves                         |
| **Sanitizar logs**                   | Reemplazar `print()` con `logging` y ofuscar datos PII                             |

### Prioridad 3 — Mediano Plazo

| Acción                           | Detalle                                                              |
| -------------------------------- | -------------------------------------------------------------------- |
| **Implementar JWT auth**         | Para endpoints que usa el frontend (Nexus-App), validar Supabase JWT |
| **Usar Supabase anon key + RLS** | Para queries scoped al usuario, usar anon key y dejar que RLS filtre |
| **Agregar tests de seguridad**   | Tests que validen que endpoints sin auth devuelven 401/403           |
| **Eliminar endpoints muertos**   | Si `/usuarios` no se usa, eliminarlo                                 |

---

## 🎯 Resumen por Endpoint

```
✅ Protegido         | POST /api/whatsapp/process (Bearer CRON_SECRET)
✅ Protegido (Meta)  | GET  /whatsapp/webhook (verify_token)
🟡 Parcial           | POST /whatsapp/webhook (falta HMAC validation)
🟡 Parcial           | POST /api/whatsapp/chats/close-session (valida org pero no auth)
🟢 OK (health)       | GET  / (health check, no necesita auth)

🔴 SIN PROTECCIÓN:
  GET  /usuarios
  POST /usuarios
  POST /chat
  POST /chat/stream
  POST /chat/tools
  POST /whatsapp/send/text
  POST /whatsapp/send/read
  POST /whatsapp/send/media
  POST /whatsapp/send/image
  POST /whatsapp/send/audio
  POST /whatsapp/send/document
  GET  /api/whatsapp/chats/{chat_id}/history
```

---

_Fin del reporte de auditoría._
