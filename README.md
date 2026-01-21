# Nexus-Bot

## 🚀 Ejecutar el proyecto localmente

### Prerrequisitos

- Python 3.9 o superior
- pip (gestor de paquetes de Python)
- Supabase CLI (opcional, si quieres correr Supabase localmente)

### Pasos para ejecutar

1. **Clonar el repositorio** (si aún no lo has hecho)
   ```bash
   git clone <url-del-repositorio>
   cd Nexus-Chatbot
   ```

2. **Crear y activar un entorno virtual**
   ```bash
   # Crear entorno virtual
   python3 -m venv venv

   # Activar entorno virtual
   # En macOS/Linux:
   source venv/bin/activate
   # En Windows:
   # venv\Scripts\activate
   ```

3. **Instalar dependencias**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configurar variables de entorno**

   Crea un archivo `.env` en la raíz del proyecto con las siguientes variables:

   ```env
   # Supabase Configuration
   SUPABASE_URL=https://your-project.supabase.co
   SUPABASE_KEY=your-anon-key
   SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
   SUPABASE_STORAGE_BUCKET=media

   # XAI (OpenAI-compatible) Configuration
   XAI_API_KEY=your-xai-api-key
   XAI_BASE_URL=https://api.x.ai/v1

   # WhatsApp Configuration
   WHATSAPP_ACCESS_TOKEN=your-whatsapp-access-token
   WHATSAPP_VERIFY_TOKEN=my_secure_token

   # Cron Secret (for scheduled tasks)
   CRON_SECRET=your-cron-secret
   ```

   **Nota:** Reemplaza los valores con tus credenciales reales.

5. **Ejecutar el servidor de desarrollo**
   ```bash
   uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

   El servidor estará disponible en: `http://localhost:8000`

   - Documentación interactiva (Swagger): `http://localhost:8000/docs`
   - Documentación alternativa (ReDoc): `http://localhost:8000/redoc`

### Opciones de ejecución

**Modo desarrollo (con recarga automática):**

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Modo producción:**

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Supabase Local (Opcional)

Si quieres correr Supabase localmente:

1. **Instalar Supabase CLI**
   ```bash
   npm install -g supabase
   ```

2. **Iniciar Supabase localmente**
   ```bash
   supabase start
   ```

3. **Configurar variables de entorno para Supabase local**
   ```env
   SUPABASE_URL=http://127.0.0.1:54321
   SUPABASE_KEY=<key-from-supabase-status>
   SUPABASE_SERVICE_ROLE_KEY=<service-key-from-supabase-status>
   ```

### Verificar que funciona

Una vez que el servidor esté corriendo, puedes verificar que funciona visitando:

- `http://localhost:8000/` - Debería mostrar:
  `{"mensaje": "Backend funcionando correctamente"}`

### Estructura del proyecto

```
Nexus-Chatbot/
├── app/
│   ├── chat/          # Endpoints de chat
│   ├── core/          # Configuración y Supabase
│   ├── whatsapp/      # Integración con WhatsApp
│   └── main.py        # Aplicación FastAPI principal
├── supabase/          # Configuración y migraciones de Supabase
├── requirements.txt   # Dependencias de Python
└── main.py           # Punto de entrada alternativo
```
