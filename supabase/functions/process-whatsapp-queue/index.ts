import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "@supabase/supabase-js";

const WAIT_TIME_MS = 5000;

// Usa SERVICE_ROLE_KEY para tener permisos de borrado/update
const supabaseUrl = Deno.env.get("SUPABASE_URL") ?? "";
const supabaseServiceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";

Deno.serve(async (req) => {
  const { chat_id } = await req.json();
  const supabase = createClient(supabaseUrl, supabaseServiceKey);

  console.log(
    `[Timer iniciado] Chat: ${chat_id}. Esperando ${WAIT_TIME_MS}ms...`,
  );

  // 1. ESPERA LA VENTANA
  await new Promise((resolve) => setTimeout(resolve, WAIT_TIME_MS));

  // 2. CONSULTA EL ESTADO ACTUAL
  const { data: queue } = await supabase
    .from("message_queue")
    .select("*")
    .eq("chat_id", chat_id)
    .maybeSingle();

  if (!queue) {
    return new Response("La cola ya fue procesada o eliminada", {
      status: 200,
    });
  }

  // 3. VALIDACIÓN DE DEBOUNCE (REINICIO DEL CRONÓMETRO)
  const lastAdded = new Date(queue.last_added_at).getTime();
  const now = Date.now();
  const diff = now - lastAdded;

  if (diff < WAIT_TIME_MS) {
    console.log(
      `[Debounce] Llegó un mensaje hace ${diff}ms. Esta instancia se cancela.`,
    );
    return new Response("Skipped", { status: 200 });
  }

  // 4. BLOQUEO ATÓMICO (Evita que dos funciones manden lo mismo)
  const { data: lockedQueue } = await supabase
    .from("message_queue")
    .update({ is_processing: true })
    .eq("chat_id", chat_id)
    .eq("is_processing", false) // Solo si nadie más lo está procesando
    .select()
    .maybeSingle();

  if (!lockedQueue) {
    console.log(
      `[Bloqueo] Otra instancia ya está procesando el chat ${chat_id}`,
    );
    return new Response("Already processing", { status: 200 });
  }

  // 5. "ENVÍO" A LA API
  const finalMessage = lockedQueue.combined_text;
  console.log("-----------------------------------------");
  console.log(`🚀 ENVIANDO A API FINAL: "${finalMessage}"`);
  console.log("-----------------------------------------");

  const appBaseUrl = "http://host.docker.internal:8000";
  const cronSecret = "m1LIdlqcxZl0JY5btW9FQO+VB4Cm1L9h/egJXzc2gkE=";

  if (!appBaseUrl) {
    console.error("Missing APP_BASE_URL for API call.");
    return new Response("Missing app base url", { status: 500 });
  }

  if (!cronSecret) {
    console.error("Missing CRON_SECRET for API call.");
    return new Response("Missing cron secret", { status: 500 });
  }

  const response = await fetch(`${appBaseUrl}/api/whatsapp/process`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${cronSecret}`,
    },
    body: JSON.stringify({
      chat_id,
      final_message: finalMessage,
    }),
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => "");
    console.error("API process error:", response.status, errorText);
    return new Response("API process error", { status: 502 });
  }

  // 6. LIMPIEZA TOTAL (Esto garantiza que el 4to mensaje sea "nuevo")
  await supabase.from("message_queue").delete().eq("chat_id", chat_id);

  console.log(
    `[Limpieza] Cola eliminada para ${chat_id}. Próximo mensaje empezará de cero.`,
  );

  return new Response("Processed", { status: 200 });
});
