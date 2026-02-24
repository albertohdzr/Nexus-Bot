# 🔬 Análisis Profundo de Conversación — Problemas Detectados

## Conversación Analizada

Chat ID: `74552fdc-6167-41f4-8f31-e03cac80e262`

---

## 🐛 Problema 1: **El bot INVENTA horarios** (CRÍTICO)

### Qué pasó

El usuario pidió horarios para el jueves en la mañana. El bot respondió:

> **Jueves 26 de febrero**
>
> 1. 8:00–9:00 am
> 2. 9:00–10:00 am
> 3. 10:00–11:00 am
> 4. 11:00 am–12:00 pm

**Estos horarios son INVENTADOS.** El bot nunca llamó
`search_availability_slots`. GPT-5.2 generó una lista ficticia de opciones.

### Por qué pasó

La función `_validate_and_fix_response` intenta detectar este caso, pero tiene
un problema:

- Solo se activa si `user_asked_for_times` es true Y hay 3+ "Opción X" en la
  respuesta
- PERO el bot escribió "1)" "2)" "3)" "4)" en vez de "Opción 1", "Opción 2" — el
  regex NO lo detectó

### Impacto

El usuario eligió la "opción 4", pero como no existían slot_options reales en el
state, el bot cayó al fallback:

> "Antes de reservar necesito mostrarte las opciones disponibles."

Esto es confuso y rompe la confianza.

---

## 🐛 Problema 2: **Reservó la fecha INCORRECTA** (CRÍTICO)

### Qué pasó

- El usuario pidió **jueves a las 11**
- El bot agendó **miércoles 25 de febrero, 11:00 AM - 12:00 PM**

### Por qué pasó

Cuando del `_maybe_book_from_selection` no encontró slot_options pero SÍ había
un `preferred_date`, intentó buscar automáticamente. La búsqueda probablemente
devolvió un slot del miércoles (el primer disponible) y lo reservó sin confirmar
con el usuario.

---

## 🐛 Problema 3: **Formato de negritas no funciona en WhatsApp**

### Qué pasó

El bot envía `**Nombre completo de tu hijo**` pero WhatsApp usa `*texto*` (un
solo asterisco) para negritas.

Markdown estándar:

- `**bold**` → NO funciona en WhatsApp
- `*bold*` → SÍ funciona en WhatsApp
- `_italic_` → SÍ funciona en WhatsApp

### Solución

Agregar conversión en `_sanitize_assistant_response`: `**texto**` → `*texto*`

---

## 🐛 Problema 4: **Mensajes de fallback genéricos rompen el flujo**

### Mensajes problemáticos

1. "Antes de reservar necesito mostrarte las opciones disponibles." — Seco, sin
   contexto
2. "¡Listo! He procesado tu solicitud exitosamente." — Genérico, no dice QUÉ
   procesó
3. "¡Listo! He procesado tu solicitud. ¿En qué más puedo apoyarte hoy?" — Igual
   de genérico

### Por qué pasa

Estos mensajes son hardcoded fallbacks que se usan cuando:

1. El bot inventó horarios y `_validate_and_fix_response` los interceptó
2. El followup de OpenAI devolvió un string vacío
3. El try/except de OpenAI capturó una excepción

Ninguno de ellos lleva contexto de la conversación.

---

## 🎯 Correcciones a Implementar

### Fix 1: Convertir `**bold**` a `*bold*` para WhatsApp

En `_sanitize_assistant_response`, agregar conversión de markdown a formato
WhatsApp.

### Fix 2: Mejorar detección de horarios inventados

El regex debe detectar CUALQUIER formato de lista numerada, no solo "Opción X".

### Fix 3: Cuando se detectan horarios inventados, hacer la búsqueda real automáticamente

En vez de responder con un mensaje genérico, el validator debe EJECUTAR
`search_availability_slots` con el contexto disponible y responder con horarios
reales.

### Fix 4: Los fallbacks deben incluir contexto de la conversación

En vez de mensajes genéricos, deben referenciar lo que el usuario pidió.
