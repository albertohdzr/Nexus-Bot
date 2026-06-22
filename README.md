# Nexus-Chatbot

API FastAPI para el chatbot de admisiones y la integracion con WhatsApp Cloud API. En produccion este servicio se hostea en Render.

## Responsabilidad del servicio

- Recibir el webhook de Meta en `/whatsapp/webhook`.
- Validar el `WHATSAPP_VERIFY_TOKEN` en el handshake de Meta.
- Validar la firma `X-Hub-Signature-256` con `WHATSAPP_APP_SECRET`.
- Guardar mensajes, chats, leads y sesiones en Supabase.
- Disparar la Edge Function `process-whatsapp-queue`.
- Procesar la cola en `/api/whatsapp/process` con `CRON_SECRET`.
- Enviar respuestas, media y documentos por WhatsApp Cloud API.
- Exponer endpoints internos protegidos por `API_SECRET` para la app de Vercel.

## Requisitos

- Python 3.9 o superior.
- pip.
- Proyecto Supabase compartido con `Nexus-App`.
- Token de WhatsApp Cloud API.
- App Secret de Meta.
- API key de OpenAI compatible con `OPEN_AI_KEY`.
- Render para el despliegue productivo.

## Variables de entorno

Variables requeridas:

```env
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
SUPABASE_STORAGE_BUCKET=media
OPEN_AI_KEY=<openai-api-key>
WHATSAPP_ACCESS_TOKEN=<meta-whatsapp-token>
WHATSAPP_VERIFY_TOKEN=<same-token-configured-in-meta>
WHATSAPP_APP_SECRET=<meta-app-secret>
API_SECRET=<same-api-secret-used-in-nexus-app>
CRON_SECRET=<same-cron-secret-used-in-supabase-edge-function>
```

Variables opcionales soportadas:

```env
XAI_API_KEY=<xai-api-key>
XAI_BASE_URL=https://api.x.ai/v1
WHATSAPP_DRY_RUN=false
```

Notas:

- `API_SECRET` debe ser identico al valor configurado en Vercel para `Nexus-App`.
- `CRON_SECRET` debe ser identico al valor configurado en Supabase Secrets para `process-whatsapp-queue`.
- `WHATSAPP_DRY_RUN=true` evita envios reales por WhatsApp y sirve para pruebas.
- No uses llaves anonimas de Supabase en `SUPABASE_SERVICE_ROLE_KEY`.

## Desarrollo local

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Crea `.env` en la raiz del repo con las variables anteriores. Para desarrollo local normalmente:

```env
WHATSAPP_DRY_RUN=true
```

Levanta la API:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

URLs utiles:

- API: `http://127.0.0.1:8000`
- Swagger: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

Verificacion:

```bash
curl http://127.0.0.1:8000/
```

Respuesta esperada:

```json
{"mensaje":"Backend funcionando correctamente"}
```

## Supabase

Este repo incluye migraciones y la Edge Function `process-whatsapp-queue`, pero el proyecto Supabase debe ser el mismo que usa `Nexus-App`.

La funcion de cola vive en:

```text
supabase/functions/process-whatsapp-queue/index.ts
```

Secretos requeridos para esa Edge Function:

```env
APP_BASE_URL=https://<render-chatbot>.onrender.com
CRON_SECRET=<same-cron-secret-as-render>
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
```

`APP_BASE_URL` debe apuntar al servicio de Render, porque la funcion llama:

```text
POST /api/whatsapp/process
Authorization: Bearer <CRON_SECRET>
```

Despliegue de la funcion:

```bash
supabase link --project-ref <project-ref>
supabase functions deploy process-whatsapp-queue --no-verify-jwt
supabase secrets set \
  APP_BASE_URL="https://<render-chatbot>.onrender.com" \
  CRON_SECRET="<cron-secret>" \
  SUPABASE_URL="https://<project-ref>.supabase.co" \
  SUPABASE_SERVICE_ROLE_KEY="<service-role-key>"
```

## Despliegue en Render

`render.yaml` ya define la configuracion principal:

```yaml
buildCommand: pip install -r requirements.txt
startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Configura el Web Service en Render con:

- Runtime: Python.
- Build command: `pip install -r requirements.txt`.
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
- Health check path: `/`.
- Variables de entorno: las listadas en este README.

Despues del deploy:

```bash
curl https://<render-chatbot>.onrender.com/
```

## Configuracion en Meta WhatsApp

En Meta for Developers, configura el webhook directamente contra Render:

```text
Callback URL: https://<render-chatbot>.onrender.com/whatsapp/webhook
Verify token: <WHATSAPP_VERIFY_TOKEN>
```

Suscribe los campos de WhatsApp que necesites, incluyendo mensajes. Si usas sincronizacion de plantillas, incluye tambien los eventos de templates.

La organizacion en Supabase debe tener:

- `phone_number_id`: Phone Number ID de WhatsApp.
- `whatsapp_business_account_id`: WABA ID, necesario para templates.

## Conexion con Nexus-App

`Nexus-App` debe tener:

```env
CHAT_API_URL=https://<render-chatbot>.onrender.com
API_SECRET=<same-api-secret-as-render>
```

La app llama endpoints del chatbot con header:

```text
X-Api-Key: <API_SECRET>
```

## Pruebas

Compilar Python:

```bash
python -m compileall app
```

Ejecutar escenarios con envios simulados:

```bash
WHATSAPP_DRY_RUN=true python scripts/run_e2e_scenarios.py
```

Opcionalmente puedes pasar escenarios especificos o ajustar el timeout:

```bash
WHATSAPP_DRY_RUN=true python scripts/run_e2e_scenarios.py full_journey two_siblings --timeout 240
```

## Estructura

```text
Nexus-Chatbot/
  app/
    chat/              # endpoints de chat protegidos por API_SECRET
    core/              # config, auth y cliente Supabase
    whatsapp/          # webhook, procesamiento, cola, media y outbound
  scripts/             # pruebas y escenarios E2E
  supabase/
    functions/         # Edge Function process-whatsapp-queue
    migrations/        # schema compartido
  render.yaml
  requirements.txt
```
