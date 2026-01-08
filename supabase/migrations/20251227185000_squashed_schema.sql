


SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;


CREATE EXTENSION IF NOT EXISTS "pg_net" WITH SCHEMA "extensions";






COMMENT ON SCHEMA "public" IS 'standard public schema';



CREATE EXTENSION IF NOT EXISTS "pg_graphql" WITH SCHEMA "graphql";






CREATE EXTENSION IF NOT EXISTS "pg_stat_statements" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "pg_trgm" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "pgcrypto" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "supabase_vault" WITH SCHEMA "vault";






CREATE EXTENSION IF NOT EXISTS "unaccent" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA "extensions";






CREATE TYPE "public"."app_status" AS ENUM (
    'draft',
    'submitted',
    'under_review',
    'changes_requested',
    'approved',
    'rejected',
    'paid'
);


ALTER TYPE "public"."app_status" OWNER TO "postgres";


CREATE TYPE "public"."lead_source" AS ENUM (
    'website',
    'whatsapp',
    'facebook',
    'instagram',
    'google_ads',
    'referral',
    'walk_in',
    'other'
);


ALTER TYPE "public"."lead_source" OWNER TO "postgres";


CREATE TYPE "public"."lead_status" AS ENUM (
    'new',
    'contacted',
    'qualified',
    'visit_scheduled',
    'visited',
    'application_started',
    'application_submitted',
    'admitted',
    'enrolled',
    'lost'
);


ALTER TYPE "public"."lead_status" OWNER TO "postgres";


CREATE TYPE "public"."payment_provider" AS ENUM (
    'stripe',
    'mercadopago',
    'transfer',
    'cash'
);


ALTER TYPE "public"."payment_provider" OWNER TO "postgres";


CREATE TYPE "public"."payment_status" AS ENUM (
    'pending',
    'completed',
    'failed',
    'refunded'
);


ALTER TYPE "public"."payment_status" OWNER TO "postgres";


CREATE TYPE "public"."plan_type" AS ENUM (
    'trial',
    'basic',
    'professional',
    'enterprise'
);


ALTER TYPE "public"."plan_type" OWNER TO "postgres";


CREATE TYPE "public"."system_role" AS ENUM (
    'superadmin',
    'org_admin',
    'director',
    'admissions',
    'teacher',
    'finance',
    'staff',
    'parent',
    'student'
);


ALTER TYPE "public"."system_role" OWNER TO "postgres";


CREATE TYPE "public"."task_priority" AS ENUM (
    'low',
    'medium',
    'high',
    'urgent'
);


ALTER TYPE "public"."task_priority" OWNER TO "postgres";


CREATE TYPE "public"."task_status" AS ENUM (
    'pending',
    'in_progress',
    'completed',
    'cancelled'
);


ALTER TYPE "public"."task_status" OWNER TO "postgres";

SET default_tablespace = '';

SET default_table_access_method = "heap";


CREATE TABLE IF NOT EXISTS "public"."message_queue" (
    "chat_id" "uuid" NOT NULL,
    "combined_text" "text" DEFAULT ''::"text" NOT NULL,
    "last_added_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "is_processing" boolean DEFAULT false NOT NULL
);


ALTER TABLE "public"."message_queue" OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."accumulate_whatsapp_message"("p_chat_id" "uuid", "p_new_text" "text") RETURNS SETOF "public"."message_queue"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'extensions'
    AS $$
begin
  return query
  insert into public.message_queue (chat_id, combined_text, last_added_at)
  values (p_chat_id, coalesce(p_new_text, ''), now())
  on conflict (chat_id) do update
  set combined_text = case
        when message_queue.combined_text is null or message_queue.combined_text = '' then excluded.combined_text
        when excluded.combined_text is null or excluded.combined_text = '' then message_queue.combined_text
        else message_queue.combined_text || ' ' || excluded.combined_text
      end,
      last_added_at = now()
  returning *;
end;
$$;


ALTER FUNCTION "public"."accumulate_whatsapp_message"("p_chat_id" "uuid", "p_new_text" "text") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."check_permission"("user_id" "uuid", "req_module" "text", "req_action" "text") RETURNS boolean
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public', 'extensions'
    AS $$
DECLARE
    user_role system_role;
    user_org UUID;
    has_perm BOOLEAN;
BEGIN
    SELECT role, organization_id INTO user_role, user_org FROM user_profiles WHERE id = user_id;
    
    IF user_role IN ('superadmin', 'org_admin') THEN RETURN TRUE; END IF;
    
    SELECT (permissions->>req_action)::BOOLEAN INTO has_perm
    FROM role_permissions
    WHERE organization_id = user_org AND role = user_role AND module = req_module;
    
    RETURN COALESCE(has_perm, FALSE);
END;
$$;


ALTER FUNCTION "public"."check_permission"("user_id" "uuid", "req_module" "text", "req_action" "text") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."concat_names_mx"("first_name" "text", "middle_name" "text", "last_name_paternal" "text", "last_name_maternal" "text") RETURNS "text"
    LANGUAGE "sql" IMMUTABLE
    SET "search_path" TO 'public', 'pg_temp'
    AS $$
select trim(both ' ' from
  (case when coalesce(first_name, '') <> '' then coalesce(first_name, '') || ' ' else '' end) ||
  (case when coalesce(middle_name, '') <> '' then coalesce(middle_name, '') || ' ' else '' end) ||
  (case when coalesce(last_name_paternal, '') <> '' then coalesce(last_name_paternal, '') || ' ' else '' end) ||
  coalesce(last_name_maternal, '')
);
$$;


ALTER FUNCTION "public"."concat_names_mx"("first_name" "text", "middle_name" "text", "last_name_paternal" "text", "last_name_maternal" "text") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_my_org_id"() RETURNS "uuid"
    LANGUAGE "sql" SECURITY DEFINER
    SET "search_path" TO 'public', 'extensions'
    AS $$
    SELECT organization_id FROM user_profiles WHERE id = (select auth.uid());
$$;


ALTER FUNCTION "public"."get_my_org_id"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."is_superadmin"("user_id" "uuid") RETURNS boolean
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public', 'extensions'
    AS $$
BEGIN
    RETURN EXISTS (SELECT 1 FROM user_profiles WHERE id = user_id AND role = 'superadmin');
END;
$$;


ALTER FUNCTION "public"."is_superadmin"("user_id" "uuid") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."notify_lead_created"() RETURNS "trigger"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
declare
  webhook_url text;
  webhook_token text;
  payload jsonb;
begin
  -- Idempotencia: si ya notificaste este lead.created, no vuelvas a disparar
  insert into public.event_outbox (organization_id, event_type, entity_id)
  values (new.organization_id, 'lead.created', new.id)
  on conflict do nothing;

  if not found then
    return new;
  end if;

  -- Leer URL/Token desde Vault
  select decrypted_secret into webhook_url
  from vault.decrypted_secrets
  where name = 'LEAD_WEBHOOK_URL'
  limit 1;

  select decrypted_secret into webhook_token
  from vault.decrypted_secrets
  where name = 'LEAD_WEBHOOK_TOKEN'
  limit 1;

  if webhook_url is null or webhook_url = '' then
    return new;
  end if;

  payload := jsonb_build_object(
    'event_type', 'lead.created',
    'lead_id', new.id,
    'organization_id', new.organization_id,
    'source', new.source,
    'created_at', new.created_at
  );

  perform net.http_post(
    url := webhook_url,
    headers := jsonb_strip_nulls(
      jsonb_build_object(
        'Content-Type', 'application/json',
        'Authorization',
          case
            when coalesce(webhook_token, '') <> '' then 'Bearer ' || webhook_token
            else null
          end
      )
    ),
    body := payload,
    timeout_milliseconds := 2000
  );

  return new;
end;
$$;


ALTER FUNCTION "public"."notify_lead_created"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_updated_at"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public', 'extensions'
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_updated_at"() OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."admission_applications" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "organization_id" "uuid" NOT NULL,
    "cycle_id" "uuid",
    "lead_id" "uuid",
    "user_id" "uuid",
    "status" "public"."app_status" DEFAULT 'draft'::"public"."app_status",
    "step_completed" integer DEFAULT 0,
    "student_data" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "medical_data" "jsonb" DEFAULT '{}'::"jsonb",
    "family_data" "jsonb" DEFAULT '{}'::"jsonb",
    "reviewer_notes" "text",
    "submitted_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."admission_applications" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."admission_cycles" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "organization_id" "uuid" NOT NULL,
    "name" "text" NOT NULL,
    "start_date" "date",
    "end_date" "date",
    "is_active" boolean DEFAULT true,
    "registration_fee" numeric(10,2) DEFAULT 0
);


ALTER TABLE "public"."admission_cycles" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."admission_documents" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "application_id" "uuid" NOT NULL,
    "type" "text" NOT NULL,
    "file_url" "text" NOT NULL,
    "status" "text" DEFAULT 'pending'::"text",
    "rejection_reason" "text",
    "uploaded_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."admission_documents" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."admission_requirement_documents" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "organization_id" "uuid" NOT NULL,
    "division" "text" NOT NULL,
    "title" "text",
    "file_path" "text" NOT NULL,
    "file_name" "text" NOT NULL,
    "mime_type" "text" DEFAULT 'application/pdf'::"text" NOT NULL,
    "storage_bucket" "text" DEFAULT 'whatsapp-media'::"text" NOT NULL,
    "is_active" boolean DEFAULT true NOT NULL,
    "created_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    CONSTRAINT "admission_requirement_documents_division_check" CHECK (("division" = ANY (ARRAY['prenursery'::"text", 'early_child'::"text", 'elementary'::"text", 'middle_school'::"text", 'high_school'::"text"])))
);


ALTER TABLE "public"."admission_requirement_documents" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."announcements" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "organization_id" "uuid" NOT NULL,
    "title" "text" NOT NULL,
    "body" "text" NOT NULL,
    "level" "text",
    "topic" "text",
    "valid_from" "date" NOT NULL,
    "valid_to" "date" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL
);


ALTER TABLE "public"."announcements" OWNER TO "postgres";


COMMENT ON TABLE "public"."announcements" IS 'Avisos y comunicados para la comunidad escolar';



CREATE TABLE IF NOT EXISTS "public"."appointment_blackouts" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "organization_id" "uuid" NOT NULL,
    "date" "date" NOT NULL,
    "start_time" time without time zone DEFAULT '00:00:00'::time without time zone NOT NULL,
    "end_time" time without time zone DEFAULT '23:59:59'::time without time zone NOT NULL,
    "reason" "text",
    "created_by_profile_id" "uuid",
    "created_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL
);


ALTER TABLE "public"."appointment_blackouts" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."appointment_settings" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "organization_id" "uuid" NOT NULL,
    "slot_duration_minutes" integer DEFAULT 60 NOT NULL,
    "days_of_week" smallint[] DEFAULT '{1,2,3,4,5}'::smallint[] NOT NULL,
    "start_time" time without time zone DEFAULT '08:00:00'::time without time zone NOT NULL,
    "end_time" time without time zone DEFAULT '14:00:00'::time without time zone NOT NULL,
    "timezone" "text" DEFAULT 'America/Mexico_City'::"text",
    "buffer_minutes" integer DEFAULT 0 NOT NULL,
    "allow_overbooking" boolean DEFAULT false NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    CONSTRAINT "appointment_settings_days_check" CHECK ((("array_length"("days_of_week", 1) > 0) AND ("days_of_week" <@ ARRAY[(0)::smallint, (1)::smallint, (2)::smallint, (3)::smallint, (4)::smallint, (5)::smallint, (6)::smallint]))),
    CONSTRAINT "appointment_settings_time_check" CHECK (("end_time" > "start_time"))
);


ALTER TABLE "public"."appointment_settings" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."appointments" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "organization_id" "uuid" NOT NULL,
    "lead_id" "uuid" NOT NULL,
    "slot_id" "uuid",
    "starts_at" timestamp with time zone NOT NULL,
    "ends_at" timestamp with time zone,
    "campus" "text",
    "type" "text",
    "status" "text" DEFAULT 'scheduled'::"text" NOT NULL,
    "created_by_profile_id" "uuid",
    "notes" "text",
    "created_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    CONSTRAINT "appointments_time_check" CHECK ((("ends_at" IS NULL) OR ("ends_at" > "starts_at")))
);


ALTER TABLE "public"."appointments" OWNER TO "postgres";


COMMENT ON TABLE "public"."appointments" IS 'Citas de admisión programadas';



CREATE TABLE IF NOT EXISTS "public"."availability_slots" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "organization_id" "uuid" NOT NULL,
    "starts_at" timestamp with time zone NOT NULL,
    "ends_at" timestamp with time zone NOT NULL,
    "campus" "text",
    "max_appointments" integer DEFAULT 1 NOT NULL,
    "appointments_count" integer DEFAULT 0 NOT NULL,
    "is_active" boolean DEFAULT true NOT NULL,
    "created_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    "is_blocked" boolean DEFAULT false NOT NULL,
    "block_reason" "text",
    "blocked_by_profile_id" "uuid",
    CONSTRAINT "availability_slots_time_check" CHECK (("ends_at" > "starts_at"))
);


ALTER TABLE "public"."availability_slots" OWNER TO "postgres";


COMMENT ON TABLE "public"."availability_slots" IS 'Slots de disponibilidad para agendar citas de admisión';



CREATE TABLE IF NOT EXISTS "public"."bot_capabilities" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "organization_id" "uuid" NOT NULL,
    "slug" "text" NOT NULL,
    "title" "text" NOT NULL,
    "description" "text",
    "instructions" "text",
    "response_template" "text",
    "type" "text" DEFAULT 'custom'::"text",
    "enabled" boolean DEFAULT true NOT NULL,
    "priority" integer DEFAULT 0 NOT NULL,
    "metadata" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL
);


ALTER TABLE "public"."bot_capabilities" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."bot_capability_contacts" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "capability_id" "uuid" NOT NULL,
    "organization_id" "uuid" NOT NULL,
    "name" "text" NOT NULL,
    "role" "text",
    "email" "text",
    "phone" "text",
    "notes" "text",
    "priority" integer DEFAULT 0 NOT NULL,
    "is_active" boolean DEFAULT true NOT NULL,
    "created_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL
);


ALTER TABLE "public"."bot_capability_contacts" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."bot_capability_finance" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "capability_id" "uuid" NOT NULL,
    "organization_id" "uuid" NOT NULL,
    "item" "text" NOT NULL,
    "value" "text" NOT NULL,
    "notes" "text",
    "valid_from" "date",
    "valid_to" "date",
    "priority" integer DEFAULT 0 NOT NULL,
    "is_active" boolean DEFAULT true NOT NULL,
    "created_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL
);


ALTER TABLE "public"."bot_capability_finance" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."bot_complaints" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "organization_id" "uuid" NOT NULL,
    "capability_id" "uuid",
    "channel" "text",
    "customer_name" "text",
    "customer_contact" "text",
    "summary" "text" NOT NULL,
    "status" "text" DEFAULT 'open'::"text" NOT NULL,
    "created_by_profile_id" "uuid",
    "created_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL
);


ALTER TABLE "public"."bot_complaints" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."chat_sessions" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "organization_id" "uuid" NOT NULL,
    "social_mapping_id" "uuid",
    "status" "text" DEFAULT 'active'::"text",
    "ai_enabled" boolean DEFAULT true,
    "summary" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "chat_id" "uuid",
    "conversation_id" "text",
    "last_response_at" timestamp with time zone,
    "closed_at" timestamp with time zone
);


ALTER TABLE "public"."chat_sessions" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."chats" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "wa_id" "text" NOT NULL,
    "name" "text",
    "phone_number" "text",
    "organization_id" "uuid" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    "state" "text",
    "state_context" "jsonb",
    "last_message_at" timestamp with time zone,
    "active_session_id" "uuid",
    "last_session_closed_at" timestamp with time zone,
    "requested_handoff" boolean DEFAULT false
);


ALTER TABLE "public"."chats" OWNER TO "postgres";


COMMENT ON TABLE "public"."chats" IS 'Conversaciones de WhatsApp por organización';



CREATE TABLE IF NOT EXISTS "public"."crm_contacts" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "organization_id" "uuid" NOT NULL,
    "first_name" "text",
    "last_name_paternal" "text",
    "phone" "text",
    "email" "text",
    "whatsapp_wa_id" "text",
    "notes" "text",
    "source" "text",
    "created_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    "middle_name" "text",
    "last_name_maternal" "text",
    "full_name" "text" GENERATED ALWAYS AS ("public"."concat_names_mx"("first_name", "middle_name", "last_name_paternal", "last_name_maternal")) STORED
);


ALTER TABLE "public"."crm_contacts" OWNER TO "postgres";


COMMENT ON TABLE "public"."crm_contacts" IS 'Personas/contactos en el CRM (padres, tutores, prospectos)';



CREATE TABLE IF NOT EXISTS "public"."directory_contacts" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "organization_id" "uuid" NOT NULL,
    "role_slug" "text" NOT NULL,
    "display_role" "text" NOT NULL,
    "name" "text" NOT NULL,
    "phone" "text",
    "email" "text",
    "notes" "text",
    "is_active" boolean DEFAULT true NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    "extension" "text",
    "mobile" "text",
    "allow_bot_share" boolean DEFAULT false NOT NULL,
    "share_email" boolean DEFAULT false NOT NULL,
    "share_phone" boolean DEFAULT false NOT NULL,
    "share_extension" boolean DEFAULT false NOT NULL,
    "share_mobile" boolean DEFAULT false NOT NULL
);


ALTER TABLE "public"."directory_contacts" OWNER TO "postgres";


COMMENT ON TABLE "public"."directory_contacts" IS 'Directorio interno de contactos clave para comunicación';



CREATE TABLE IF NOT EXISTS "public"."email_template_bases" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "organization_id" "uuid" NOT NULL,
    "logo_url" "text",
    "header_html" "text",
    "footer_html" "text",
    "created_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL
);


ALTER TABLE "public"."email_template_bases" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."email_template_triggers" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "organization_id" "uuid" NOT NULL,
    "template_id" "uuid" NOT NULL,
    "event_type" "text" NOT NULL,
    "source" "text" DEFAULT 'any'::"text" NOT NULL,
    "rules" "jsonb" DEFAULT '[]'::"jsonb" NOT NULL,
    "is_active" boolean DEFAULT true NOT NULL,
    "created_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL
);


ALTER TABLE "public"."email_template_triggers" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."email_templates" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "organization_id" "uuid" NOT NULL,
    "base_id" "uuid",
    "name" "text" NOT NULL,
    "subject" "text" NOT NULL,
    "category" "text",
    "channel" "text" DEFAULT 'email'::"text" NOT NULL,
    "status" "text" DEFAULT 'active'::"text" NOT NULL,
    "body_html" "text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL
);


ALTER TABLE "public"."email_templates" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."event_outbox" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "organization_id" "uuid" NOT NULL,
    "event_type" "text" NOT NULL,
    "entity_id" "uuid" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."event_outbox" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."faqs" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "organization_id" "uuid" NOT NULL,
    "question" "text" NOT NULL,
    "answer" "text" NOT NULL,
    "tags" "text"[],
    "audience" "text",
    "is_published" boolean DEFAULT true NOT NULL,
    "created_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL
);


ALTER TABLE "public"."faqs" OWNER TO "postgres";


COMMENT ON TABLE "public"."faqs" IS 'Base de conocimiento/FAQs para bots y atención';



CREATE TABLE IF NOT EXISTS "public"."lead_activities" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "organization_id" "uuid" NOT NULL,
    "lead_id" "uuid" NOT NULL,
    "type" "text" NOT NULL,
    "subject" "text",
    "notes" "text",
    "completed_at" timestamp with time zone,
    "created_by" "uuid",
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."lead_activities" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."leads" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "organization_id" "uuid" NOT NULL,
    "lead_number" integer NOT NULL,
    "status" "text" DEFAULT 'new'::"text" NOT NULL,
    "source" "text" NOT NULL,
    "student_first_name" "text" NOT NULL,
    "student_last_name_paternal" "text" NOT NULL,
    "student_dob" "date",
    "student_grade_interest" "text",
    "contact_name" "text",
    "contact_email" "text",
    "contact_phone" "text" NOT NULL,
    "assigned_to" "uuid",
    "score" integer DEFAULT 0,
    "tags" "text"[],
    "notes" "text",
    "converted_at" timestamp with time zone,
    "converted_to_student_id" "uuid",
    "created_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()),
    "updated_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()),
    "contact_id" "uuid" NOT NULL,
    "grade_interest" "text" NOT NULL,
    "school_year" "text",
    "current_school" "text",
    "wa_chat_id" "uuid",
    "wa_id" "text",
    "metadata" "jsonb" DEFAULT '{}'::"jsonb",
    "student_middle_name" "text",
    "student_last_name_maternal" "text",
    "student_name" "text" GENERATED ALWAYS AS ("public"."concat_names_mx"("student_first_name", "student_middle_name", "student_last_name_paternal", "student_last_name_maternal")) STORED,
    "contact_first_name" "text",
    "contact_middle_name" "text",
    "contact_last_name_paternal" "text",
    "contact_last_name_maternal" "text",
    "contact_full_name" "text" GENERATED ALWAYS AS ("public"."concat_names_mx"("contact_first_name", "contact_middle_name", "contact_last_name_paternal", "contact_last_name_maternal")) STORED,
    "ai_summary" "text",
    "ai_metadata" "jsonb" DEFAULT '{}'::"jsonb",
    "cycle_id" "uuid"
);


ALTER TABLE "public"."leads" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."leads_lead_number_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."leads_lead_number_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."leads_lead_number_seq" OWNED BY "public"."leads"."lead_number";



CREATE TABLE IF NOT EXISTS "public"."messages" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "chat_id" "uuid" NOT NULL,
    "wa_message_id" "text",
    "body" "text",
    "type" "text",
    "status" "text" DEFAULT 'received'::"text",
    "payload" "jsonb",
    "created_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL,
    "wa_timestamp" timestamp with time zone,
    "sent_at" timestamp with time zone,
    "delivered_at" timestamp with time zone,
    "read_at" timestamp with time zone,
    "sender_profile_id" "uuid",
    "sender_name" "text",
    "media_id" "text",
    "media_url" "text",
    "media_path" "text",
    "media_mime_type" "text",
    "direction" "text",
    "role" "text",
    "chat_session_id" "uuid",
    "response_id" "text",
    CONSTRAINT "messages_direction_check" CHECK ((("direction" IS NULL) OR ("direction" = ANY (ARRAY['inbound'::"text", 'outbound'::"text"])))),
    CONSTRAINT "messages_role_check" CHECK ((("role" IS NULL) OR ("role" = ANY (ARRAY['user'::"text", 'assistant'::"text", 'agent'::"text"]))))
);


ALTER TABLE "public"."messages" OWNER TO "postgres";


COMMENT ON TABLE "public"."messages" IS 'Mensajes individuales dentro de un chat de WhatsApp';



CREATE TABLE IF NOT EXISTS "public"."organization_knowledge" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "organization_id" "uuid" NOT NULL,
    "title" "text" NOT NULL,
    "category" "text",
    "content" "text",
    "created_by" "uuid",
    "updated_by" "uuid",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."organization_knowledge" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."organizations" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "name" "text" NOT NULL,
    "slug" "text" NOT NULL,
    "logo_url" "text",
    "plan" "public"."plan_type" DEFAULT 'trial'::"public"."plan_type",
    "settings" "jsonb" DEFAULT '{}'::"jsonb",
    "ai_settings" "jsonb" DEFAULT '{"enabled": false, "personality": "formal"}'::"jsonb",
    "is_active" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "deleted_at" timestamp with time zone,
    "display_phone_number" "text",
    "phone_number_id" "text",
    "bot_name" "text" DEFAULT 'Asistente'::"text",
    "bot_instructions" "text",
    "bot_tone" "text",
    "bot_language" "text" DEFAULT 'es'::"text",
    "bot_model" "text" DEFAULT 'gpt-4o-mini'::"text",
    "bot_directory_enabled" boolean DEFAULT false NOT NULL
);


ALTER TABLE "public"."organizations" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."payments" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "organization_id" "uuid" NOT NULL,
    "application_id" "uuid",
    "amount" numeric(10,2) NOT NULL,
    "currency" "text" DEFAULT 'MXN'::"text",
    "status" "public"."payment_status" DEFAULT 'pending'::"public"."payment_status",
    "provider" "public"."payment_provider" NOT NULL,
    "provider_transaction_id" "text",
    "receipt_url" "text",
    "paid_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."payments" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."role_permissions" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "organization_id" "uuid",
    "role" "public"."system_role" NOT NULL,
    "module" "text" NOT NULL,
    "permissions" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL
);


ALTER TABLE "public"."role_permissions" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."school_schedules" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "organization_id" "uuid" NOT NULL,
    "level" "text" NOT NULL,
    "regular_entry_time" time without time zone NOT NULL,
    "regular_exit_time" time without time zone NOT NULL,
    "notes" "text",
    "updated_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL
);


ALTER TABLE "public"."school_schedules" OWNER TO "postgres";


COMMENT ON TABLE "public"."school_schedules" IS 'Horarios regulares por nivel educativo';



CREATE TABLE IF NOT EXISTS "public"."social_mappings" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "organization_id" "uuid" NOT NULL,
    "lead_id" "uuid",
    "user_id" "uuid",
    "platform" "text" NOT NULL,
    "platform_user_id" "text" NOT NULL,
    "profile_data" "jsonb" DEFAULT '{}'::"jsonb",
    "last_interaction_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."social_mappings" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."special_schedules" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "organization_id" "uuid" NOT NULL,
    "level" "text" NOT NULL,
    "date" "date" NOT NULL,
    "entry_time" time without time zone,
    "exit_time" time without time zone,
    "reason" "text",
    "updated_at" timestamp with time zone DEFAULT "timezone"('utc'::"text", "now"()) NOT NULL
);


ALTER TABLE "public"."special_schedules" OWNER TO "postgres";


COMMENT ON TABLE "public"."special_schedules" IS 'Horarios especiales o excepciones por día';



CREATE TABLE IF NOT EXISTS "public"."student_families" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "organization_id" "uuid" NOT NULL,
    "student_id" "uuid",
    "parent_user_id" "uuid",
    "relationship" "text" NOT NULL,
    "is_financial_responsible" boolean DEFAULT false
);


ALTER TABLE "public"."student_families" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."students" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "organization_id" "uuid" NOT NULL,
    "first_name" "text" NOT NULL,
    "last_name_paternal" "text" NOT NULL,
    "student_id_number" "text",
    "current_grade" "text",
    "section" "text",
    "status" "text" DEFAULT 'active'::"text",
    "original_lead_id" "uuid",
    "admission_application_id" "uuid",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "middle_name" "text",
    "last_name_maternal" "text",
    "full_name" "text" GENERATED ALWAYS AS ("public"."concat_names_mx"("first_name", "middle_name", "last_name_paternal", "last_name_maternal")) STORED
);


ALTER TABLE "public"."students" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."tasks" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "organization_id" "uuid" NOT NULL,
    "title" "text" NOT NULL,
    "description" "text",
    "due_date" timestamp with time zone,
    "priority" "public"."task_priority" DEFAULT 'medium'::"public"."task_priority",
    "status" "public"."task_status" DEFAULT 'pending'::"public"."task_status",
    "assigned_to" "uuid",
    "related_lead_id" "uuid",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."tasks" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."user_profiles" (
    "id" "uuid" NOT NULL,
    "organization_id" "uuid",
    "role" "public"."system_role" DEFAULT 'parent'::"public"."system_role" NOT NULL,
    "first_name" "text" NOT NULL,
    "last_name_paternal" "text" NOT NULL,
    "email" "text" NOT NULL,
    "phone" "text",
    "avatar_url" "text",
    "is_active" boolean DEFAULT true,
    "force_password_change" boolean DEFAULT false,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "middle_name" "text",
    "last_name_maternal" "text",
    "full_name" "text" GENERATED ALWAYS AS ("public"."concat_names_mx"("first_name", "middle_name", "last_name_paternal", "last_name_maternal")) STORED
);


ALTER TABLE "public"."user_profiles" OWNER TO "postgres";


ALTER TABLE ONLY "public"."leads" ALTER COLUMN "lead_number" SET DEFAULT "nextval"('"public"."leads_lead_number_seq"'::"regclass");



ALTER TABLE ONLY "public"."admission_applications"
    ADD CONSTRAINT "admission_applications_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."admission_cycles"
    ADD CONSTRAINT "admission_cycles_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."admission_documents"
    ADD CONSTRAINT "admission_documents_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."admission_requirement_documents"
    ADD CONSTRAINT "admission_requirement_documents_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."announcements"
    ADD CONSTRAINT "announcements_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."appointment_blackouts"
    ADD CONSTRAINT "appointment_blackouts_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."appointment_settings"
    ADD CONSTRAINT "appointment_settings_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."appointments"
    ADD CONSTRAINT "appointments_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."availability_slots"
    ADD CONSTRAINT "availability_slots_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."bot_capabilities"
    ADD CONSTRAINT "bot_capabilities_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."bot_capabilities"
    ADD CONSTRAINT "bot_capabilities_slug_unique_per_org" UNIQUE ("organization_id", "slug");



ALTER TABLE ONLY "public"."bot_capability_contacts"
    ADD CONSTRAINT "bot_capability_contacts_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."bot_capability_finance"
    ADD CONSTRAINT "bot_capability_finance_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."bot_complaints"
    ADD CONSTRAINT "bot_complaints_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."chat_sessions"
    ADD CONSTRAINT "chat_sessions_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."chats"
    ADD CONSTRAINT "chats_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."crm_contacts"
    ADD CONSTRAINT "crm_contacts_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."directory_contacts"
    ADD CONSTRAINT "directory_contacts_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."email_template_bases"
    ADD CONSTRAINT "email_template_bases_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."email_template_triggers"
    ADD CONSTRAINT "email_template_triggers_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."email_templates"
    ADD CONSTRAINT "email_templates_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."event_outbox"
    ADD CONSTRAINT "event_outbox_organization_id_event_type_entity_id_key" UNIQUE ("organization_id", "event_type", "entity_id");



ALTER TABLE ONLY "public"."event_outbox"
    ADD CONSTRAINT "event_outbox_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."faqs"
    ADD CONSTRAINT "faqs_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."lead_activities"
    ADD CONSTRAINT "lead_activities_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."leads"
    ADD CONSTRAINT "leads_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."message_queue"
    ADD CONSTRAINT "message_queue_pkey" PRIMARY KEY ("chat_id");



ALTER TABLE ONLY "public"."messages"
    ADD CONSTRAINT "messages_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."messages"
    ADD CONSTRAINT "messages_wa_message_id_key" UNIQUE ("wa_message_id");



ALTER TABLE ONLY "public"."organization_knowledge"
    ADD CONSTRAINT "organization_knowledge_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."organizations"
    ADD CONSTRAINT "organizations_phone_number_id_key" UNIQUE ("phone_number_id");



ALTER TABLE ONLY "public"."organizations"
    ADD CONSTRAINT "organizations_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."payments"
    ADD CONSTRAINT "payments_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."role_permissions"
    ADD CONSTRAINT "role_permissions_organization_id_role_module_key" UNIQUE ("organization_id", "role", "module");



ALTER TABLE ONLY "public"."role_permissions"
    ADD CONSTRAINT "role_permissions_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."school_schedules"
    ADD CONSTRAINT "school_schedules_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."social_mappings"
    ADD CONSTRAINT "social_mappings_organization_id_platform_platform_user_id_key" UNIQUE ("organization_id", "platform", "platform_user_id");



ALTER TABLE ONLY "public"."social_mappings"
    ADD CONSTRAINT "social_mappings_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."special_schedules"
    ADD CONSTRAINT "special_schedules_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."student_families"
    ADD CONSTRAINT "student_families_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."student_families"
    ADD CONSTRAINT "student_families_student_id_parent_user_id_key" UNIQUE ("student_id", "parent_user_id");



ALTER TABLE ONLY "public"."students"
    ADD CONSTRAINT "students_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."tasks"
    ADD CONSTRAINT "tasks_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."user_profiles"
    ADD CONSTRAINT "user_profiles_email_organization_id_key" UNIQUE ("email", "organization_id");



ALTER TABLE ONLY "public"."user_profiles"
    ADD CONSTRAINT "user_profiles_pkey" PRIMARY KEY ("id");



CREATE INDEX "admission_requirement_documents_division_idx" ON "public"."admission_requirement_documents" USING "btree" ("division");



CREATE INDEX "admission_requirement_documents_org_idx" ON "public"."admission_requirement_documents" USING "btree" ("organization_id");



CREATE INDEX "announcements_org_idx" ON "public"."announcements" USING "btree" ("organization_id");



CREATE INDEX "announcements_topic_idx" ON "public"."announcements" USING "btree" ("topic");



CREATE INDEX "announcements_valid_from_idx" ON "public"."announcements" USING "btree" ("valid_from");



CREATE INDEX "announcements_valid_to_idx" ON "public"."announcements" USING "btree" ("valid_to");



CREATE UNIQUE INDEX "appointment_blackouts_org_date_time_idx" ON "public"."appointment_blackouts" USING "btree" ("organization_id", "date", "start_time", "end_time");



CREATE UNIQUE INDEX "appointment_settings_org_idx" ON "public"."appointment_settings" USING "btree" ("organization_id");



CREATE INDEX "appointments_lead_id_idx" ON "public"."appointments" USING "btree" ("lead_id");



CREATE INDEX "appointments_org_idx" ON "public"."appointments" USING "btree" ("organization_id");



CREATE INDEX "appointments_starts_at_idx" ON "public"."appointments" USING "btree" ("starts_at");



CREATE INDEX "appointments_status_idx" ON "public"."appointments" USING "btree" ("status");



CREATE INDEX "availability_slots_is_active_idx" ON "public"."availability_slots" USING "btree" ("is_active");



CREATE INDEX "availability_slots_org_idx" ON "public"."availability_slots" USING "btree" ("organization_id");



CREATE UNIQUE INDEX "availability_slots_org_start_end_key" ON "public"."availability_slots" USING "btree" ("organization_id", "starts_at", "ends_at");



CREATE INDEX "availability_slots_starts_at_idx" ON "public"."availability_slots" USING "btree" ("starts_at");



CREATE INDEX "bot_capabilities_org_priority_idx" ON "public"."bot_capabilities" USING "btree" ("organization_id", "enabled", "priority" DESC);



CREATE INDEX "bot_capability_contacts_capability_idx" ON "public"."bot_capability_contacts" USING "btree" ("capability_id");



CREATE INDEX "bot_capability_contacts_org_role_idx" ON "public"."bot_capability_contacts" USING "btree" ("organization_id", "role", "is_active");



CREATE INDEX "bot_capability_finance_capability_idx" ON "public"."bot_capability_finance" USING "btree" ("capability_id");



CREATE INDEX "bot_capability_finance_org_item_idx" ON "public"."bot_capability_finance" USING "btree" ("organization_id", "item", "is_active");



CREATE INDEX "bot_complaints_capability_idx" ON "public"."bot_complaints" USING "btree" ("capability_id");



CREATE INDEX "bot_complaints_org_status_idx" ON "public"."bot_complaints" USING "btree" ("organization_id", "status");



CREATE INDEX "chat_sessions_chat_id_idx" ON "public"."chat_sessions" USING "btree" ("chat_id");



CREATE INDEX "chat_sessions_conversation_id_idx" ON "public"."chat_sessions" USING "btree" ("conversation_id");



CREATE INDEX "chats_active_session_id_idx" ON "public"."chats" USING "btree" ("active_session_id");



CREATE INDEX "chats_org_id_idx" ON "public"."chats" USING "btree" ("organization_id");



CREATE UNIQUE INDEX "chats_wa_id_org_id_idx" ON "public"."chats" USING "btree" ("wa_id", "organization_id");



CREATE INDEX "crm_contacts_org_idx" ON "public"."crm_contacts" USING "btree" ("organization_id");



CREATE INDEX "crm_contacts_whatsapp_wa_id_idx" ON "public"."crm_contacts" USING "btree" ("whatsapp_wa_id");



CREATE INDEX "directory_contacts_bot_share_idx" ON "public"."directory_contacts" USING "btree" ("organization_id", "allow_bot_share", "is_active");



CREATE INDEX "directory_contacts_org_idx" ON "public"."directory_contacts" USING "btree" ("organization_id");



CREATE UNIQUE INDEX "directory_contacts_org_role_slug_key" ON "public"."directory_contacts" USING "btree" ("organization_id", "role_slug");



CREATE INDEX "email_template_bases_org_idx" ON "public"."email_template_bases" USING "btree" ("organization_id");



CREATE UNIQUE INDEX "email_template_bases_org_unique" ON "public"."email_template_bases" USING "btree" ("organization_id");



CREATE INDEX "email_template_triggers_event_idx" ON "public"."email_template_triggers" USING "btree" ("event_type");



CREATE INDEX "email_template_triggers_org_idx" ON "public"."email_template_triggers" USING "btree" ("organization_id");



CREATE INDEX "email_template_triggers_template_idx" ON "public"."email_template_triggers" USING "btree" ("template_id");



CREATE INDEX "email_templates_org_idx" ON "public"."email_templates" USING "btree" ("organization_id");



CREATE INDEX "email_templates_status_idx" ON "public"."email_templates" USING "btree" ("status");



CREATE INDEX "faqs_is_published_idx" ON "public"."faqs" USING "btree" ("is_published");



CREATE INDEX "faqs_org_idx" ON "public"."faqs" USING "btree" ("organization_id");



CREATE INDEX "faqs_tags_gin_idx" ON "public"."faqs" USING "gin" ("tags");



CREATE INDEX "idx_admission_applications_cycle_id" ON "public"."admission_applications" USING "btree" ("cycle_id");



CREATE INDEX "idx_admission_applications_lead_id" ON "public"."admission_applications" USING "btree" ("lead_id");



CREATE INDEX "idx_admission_applications_organization_id" ON "public"."admission_applications" USING "btree" ("organization_id");



CREATE INDEX "idx_admission_applications_user_id" ON "public"."admission_applications" USING "btree" ("user_id");



CREATE INDEX "idx_admission_cycles_organization_id" ON "public"."admission_cycles" USING "btree" ("organization_id");



CREATE INDEX "idx_admission_documents_application_id" ON "public"."admission_documents" USING "btree" ("application_id");



CREATE INDEX "idx_chat_sessions_organization_id" ON "public"."chat_sessions" USING "btree" ("organization_id");



CREATE INDEX "idx_chat_sessions_social_mapping_id" ON "public"."chat_sessions" USING "btree" ("social_mapping_id");



CREATE INDEX "idx_lead_activities_created_by" ON "public"."lead_activities" USING "btree" ("created_by");



CREATE INDEX "idx_lead_activities_lead_id" ON "public"."lead_activities" USING "btree" ("lead_id");



CREATE INDEX "idx_lead_activities_organization_id" ON "public"."lead_activities" USING "btree" ("organization_id");



CREATE INDEX "idx_leads_assigned_to" ON "public"."leads" USING "btree" ("assigned_to");



CREATE INDEX "idx_leads_organization_id" ON "public"."leads" USING "btree" ("organization_id");



CREATE INDEX "idx_payments_application_id" ON "public"."payments" USING "btree" ("application_id");



CREATE INDEX "idx_payments_organization_id" ON "public"."payments" USING "btree" ("organization_id");



CREATE INDEX "idx_social_mappings_lead_id" ON "public"."social_mappings" USING "btree" ("lead_id");



CREATE INDEX "idx_social_mappings_user_id" ON "public"."social_mappings" USING "btree" ("user_id");



CREATE INDEX "idx_student_families_organization_id" ON "public"."student_families" USING "btree" ("organization_id");



CREATE INDEX "idx_student_families_parent_user_id" ON "public"."student_families" USING "btree" ("parent_user_id");



CREATE INDEX "idx_students_admission_application_id" ON "public"."students" USING "btree" ("admission_application_id");



CREATE INDEX "idx_students_organization_id" ON "public"."students" USING "btree" ("organization_id");



CREATE INDEX "idx_students_original_lead_id" ON "public"."students" USING "btree" ("original_lead_id");



CREATE INDEX "idx_tasks_assigned_to" ON "public"."tasks" USING "btree" ("assigned_to");



CREATE INDEX "idx_tasks_organization_id" ON "public"."tasks" USING "btree" ("organization_id");



CREATE INDEX "idx_tasks_related_lead_id" ON "public"."tasks" USING "btree" ("related_lead_id");



CREATE INDEX "idx_user_profiles_organization_id" ON "public"."user_profiles" USING "btree" ("organization_id");



CREATE INDEX "leads_contact_id_idx" ON "public"."leads" USING "btree" ("contact_id");



CREATE INDEX "leads_cycle_id_idx" ON "public"."leads" USING "btree" ("cycle_id");



CREATE INDEX "leads_status_idx" ON "public"."leads" USING "btree" ("status");



CREATE INDEX "leads_wa_chat_id_idx" ON "public"."leads" USING "btree" ("wa_chat_id");



CREATE INDEX "message_queue_processing_idx" ON "public"."message_queue" USING "btree" ("is_processing", "last_added_at");



CREATE INDEX "messages_chat_id_created_at_idx" ON "public"."messages" USING "btree" ("chat_id", "created_at");



CREATE INDEX "messages_chat_session_id_idx" ON "public"."messages" USING "btree" ("chat_session_id");



CREATE INDEX "messages_response_id_idx" ON "public"."messages" USING "btree" ("response_id");



CREATE INDEX "messages_sender_profile_id_idx" ON "public"."messages" USING "btree" ("sender_profile_id");



CREATE INDEX "organization_knowledge_category_idx" ON "public"."organization_knowledge" USING "btree" ("category");



CREATE INDEX "organization_knowledge_org_id_idx" ON "public"."organization_knowledge" USING "btree" ("organization_id");



CREATE INDEX "school_schedules_org_level_idx" ON "public"."school_schedules" USING "btree" ("organization_id", "level");



CREATE UNIQUE INDEX "special_schedules_org_level_date_key" ON "public"."special_schedules" USING "btree" ("organization_id", "level", "date");



CREATE INDEX "special_schedules_org_level_idx" ON "public"."special_schedules" USING "btree" ("organization_id", "level");



CREATE UNIQUE INDEX "uniq_org_slug" ON "public"."organizations" USING "btree" ("slug") WHERE ("deleted_at" IS NULL);



CREATE OR REPLACE TRIGGER "lead_created_webhook" AFTER INSERT ON "public"."leads" FOR EACH ROW EXECUTE FUNCTION "public"."notify_lead_created"();



CREATE OR REPLACE TRIGGER "update_apps_time" BEFORE UPDATE ON "public"."admission_applications" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at"();



CREATE OR REPLACE TRIGGER "update_leads_time" BEFORE UPDATE ON "public"."leads" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at"();



CREATE OR REPLACE TRIGGER "update_orgs_time" BEFORE UPDATE ON "public"."organizations" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at"();



ALTER TABLE ONLY "public"."admission_applications"
    ADD CONSTRAINT "admission_applications_cycle_id_fkey" FOREIGN KEY ("cycle_id") REFERENCES "public"."admission_cycles"("id");



ALTER TABLE ONLY "public"."admission_applications"
    ADD CONSTRAINT "admission_applications_lead_id_fkey" FOREIGN KEY ("lead_id") REFERENCES "public"."leads"("id");



ALTER TABLE ONLY "public"."admission_applications"
    ADD CONSTRAINT "admission_applications_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."admission_applications"
    ADD CONSTRAINT "admission_applications_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."user_profiles"("id");



ALTER TABLE ONLY "public"."admission_cycles"
    ADD CONSTRAINT "admission_cycles_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."admission_documents"
    ADD CONSTRAINT "admission_documents_application_id_fkey" FOREIGN KEY ("application_id") REFERENCES "public"."admission_applications"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."admission_requirement_documents"
    ADD CONSTRAINT "admission_requirement_documents_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."announcements"
    ADD CONSTRAINT "announcements_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."appointment_blackouts"
    ADD CONSTRAINT "appointment_blackouts_created_by_profile_id_fkey" FOREIGN KEY ("created_by_profile_id") REFERENCES "public"."user_profiles"("id");



ALTER TABLE ONLY "public"."appointment_blackouts"
    ADD CONSTRAINT "appointment_blackouts_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."appointment_settings"
    ADD CONSTRAINT "appointment_settings_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."appointments"
    ADD CONSTRAINT "appointments_created_by_profile_id_fkey" FOREIGN KEY ("created_by_profile_id") REFERENCES "public"."user_profiles"("id");



ALTER TABLE ONLY "public"."appointments"
    ADD CONSTRAINT "appointments_lead_id_fkey" FOREIGN KEY ("lead_id") REFERENCES "public"."leads"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."appointments"
    ADD CONSTRAINT "appointments_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."appointments"
    ADD CONSTRAINT "appointments_slot_id_fkey" FOREIGN KEY ("slot_id") REFERENCES "public"."availability_slots"("id");



ALTER TABLE ONLY "public"."availability_slots"
    ADD CONSTRAINT "availability_slots_blocked_by_profile_id_fkey" FOREIGN KEY ("blocked_by_profile_id") REFERENCES "public"."user_profiles"("id");



ALTER TABLE ONLY "public"."availability_slots"
    ADD CONSTRAINT "availability_slots_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."bot_capabilities"
    ADD CONSTRAINT "bot_capabilities_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."bot_capability_contacts"
    ADD CONSTRAINT "bot_capability_contacts_capability_id_fkey" FOREIGN KEY ("capability_id") REFERENCES "public"."bot_capabilities"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."bot_capability_contacts"
    ADD CONSTRAINT "bot_capability_contacts_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."bot_capability_finance"
    ADD CONSTRAINT "bot_capability_finance_capability_id_fkey" FOREIGN KEY ("capability_id") REFERENCES "public"."bot_capabilities"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."bot_capability_finance"
    ADD CONSTRAINT "bot_capability_finance_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."bot_complaints"
    ADD CONSTRAINT "bot_complaints_capability_id_fkey" FOREIGN KEY ("capability_id") REFERENCES "public"."bot_capabilities"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."bot_complaints"
    ADD CONSTRAINT "bot_complaints_created_by_profile_id_fkey" FOREIGN KEY ("created_by_profile_id") REFERENCES "public"."user_profiles"("id");



ALTER TABLE ONLY "public"."bot_complaints"
    ADD CONSTRAINT "bot_complaints_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."chat_sessions"
    ADD CONSTRAINT "chat_sessions_chat_id_fkey" FOREIGN KEY ("chat_id") REFERENCES "public"."chats"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."chat_sessions"
    ADD CONSTRAINT "chat_sessions_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."chat_sessions"
    ADD CONSTRAINT "chat_sessions_social_mapping_id_fkey" FOREIGN KEY ("social_mapping_id") REFERENCES "public"."social_mappings"("id");



ALTER TABLE ONLY "public"."chats"
    ADD CONSTRAINT "chats_active_session_id_fkey" FOREIGN KEY ("active_session_id") REFERENCES "public"."chat_sessions"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."chats"
    ADD CONSTRAINT "chats_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."crm_contacts"
    ADD CONSTRAINT "crm_contacts_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."directory_contacts"
    ADD CONSTRAINT "directory_contacts_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."email_template_bases"
    ADD CONSTRAINT "email_template_bases_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."email_template_triggers"
    ADD CONSTRAINT "email_template_triggers_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."email_template_triggers"
    ADD CONSTRAINT "email_template_triggers_template_id_fkey" FOREIGN KEY ("template_id") REFERENCES "public"."email_templates"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."email_templates"
    ADD CONSTRAINT "email_templates_base_id_fkey" FOREIGN KEY ("base_id") REFERENCES "public"."email_template_bases"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."email_templates"
    ADD CONSTRAINT "email_templates_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."faqs"
    ADD CONSTRAINT "faqs_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."lead_activities"
    ADD CONSTRAINT "lead_activities_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "public"."user_profiles"("id");



ALTER TABLE ONLY "public"."lead_activities"
    ADD CONSTRAINT "lead_activities_lead_id_fkey" FOREIGN KEY ("lead_id") REFERENCES "public"."leads"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."lead_activities"
    ADD CONSTRAINT "lead_activities_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."leads"
    ADD CONSTRAINT "leads_assigned_to_fkey" FOREIGN KEY ("assigned_to") REFERENCES "public"."user_profiles"("id");



ALTER TABLE ONLY "public"."leads"
    ADD CONSTRAINT "leads_contact_id_fkey" FOREIGN KEY ("contact_id") REFERENCES "public"."crm_contacts"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."leads"
    ADD CONSTRAINT "leads_cycle_id_fkey" FOREIGN KEY ("cycle_id") REFERENCES "public"."admission_cycles"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."leads"
    ADD CONSTRAINT "leads_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."leads"
    ADD CONSTRAINT "leads_wa_chat_id_fkey" FOREIGN KEY ("wa_chat_id") REFERENCES "public"."chats"("id");



ALTER TABLE ONLY "public"."message_queue"
    ADD CONSTRAINT "message_queue_chat_id_fkey" FOREIGN KEY ("chat_id") REFERENCES "public"."chats"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."messages"
    ADD CONSTRAINT "messages_chat_id_fkey" FOREIGN KEY ("chat_id") REFERENCES "public"."chats"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."messages"
    ADD CONSTRAINT "messages_chat_session_id_fkey" FOREIGN KEY ("chat_session_id") REFERENCES "public"."chat_sessions"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."messages"
    ADD CONSTRAINT "messages_sender_profile_id_fkey" FOREIGN KEY ("sender_profile_id") REFERENCES "public"."user_profiles"("id");



ALTER TABLE ONLY "public"."organization_knowledge"
    ADD CONSTRAINT "organization_knowledge_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "public"."user_profiles"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."organization_knowledge"
    ADD CONSTRAINT "organization_knowledge_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."organization_knowledge"
    ADD CONSTRAINT "organization_knowledge_updated_by_fkey" FOREIGN KEY ("updated_by") REFERENCES "public"."user_profiles"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."payments"
    ADD CONSTRAINT "payments_application_id_fkey" FOREIGN KEY ("application_id") REFERENCES "public"."admission_applications"("id");



ALTER TABLE ONLY "public"."payments"
    ADD CONSTRAINT "payments_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."role_permissions"
    ADD CONSTRAINT "role_permissions_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."school_schedules"
    ADD CONSTRAINT "school_schedules_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."social_mappings"
    ADD CONSTRAINT "social_mappings_lead_id_fkey" FOREIGN KEY ("lead_id") REFERENCES "public"."leads"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."social_mappings"
    ADD CONSTRAINT "social_mappings_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."social_mappings"
    ADD CONSTRAINT "social_mappings_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."user_profiles"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."special_schedules"
    ADD CONSTRAINT "special_schedules_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."student_families"
    ADD CONSTRAINT "student_families_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."student_families"
    ADD CONSTRAINT "student_families_parent_user_id_fkey" FOREIGN KEY ("parent_user_id") REFERENCES "public"."user_profiles"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."student_families"
    ADD CONSTRAINT "student_families_student_id_fkey" FOREIGN KEY ("student_id") REFERENCES "public"."students"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."students"
    ADD CONSTRAINT "students_admission_application_id_fkey" FOREIGN KEY ("admission_application_id") REFERENCES "public"."admission_applications"("id");



ALTER TABLE ONLY "public"."students"
    ADD CONSTRAINT "students_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."students"
    ADD CONSTRAINT "students_original_lead_id_fkey" FOREIGN KEY ("original_lead_id") REFERENCES "public"."leads"("id");



ALTER TABLE ONLY "public"."tasks"
    ADD CONSTRAINT "tasks_assigned_to_fkey" FOREIGN KEY ("assigned_to") REFERENCES "public"."user_profiles"("id");



ALTER TABLE ONLY "public"."tasks"
    ADD CONSTRAINT "tasks_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");



ALTER TABLE ONLY "public"."tasks"
    ADD CONSTRAINT "tasks_related_lead_id_fkey" FOREIGN KEY ("related_lead_id") REFERENCES "public"."leads"("id");



ALTER TABLE ONLY "public"."user_profiles"
    ADD CONSTRAINT "user_profiles_id_fkey" FOREIGN KEY ("id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."user_profiles"
    ADD CONSTRAINT "user_profiles_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id") ON DELETE CASCADE;



CREATE POLICY "Access admission applications" ON "public"."admission_applications" TO "authenticated" USING ((("user_id" = ( SELECT "auth"."uid"() AS "uid")) OR (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))) AND (EXISTS ( SELECT 1
   FROM "public"."user_profiles"
  WHERE (("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")) AND ("user_profiles"."role" = ANY (ARRAY['org_admin'::"public"."system_role", 'director'::"public"."system_role", 'admissions'::"public"."system_role"]))))))));



CREATE POLICY "Access admission documents" ON "public"."admission_documents" TO "authenticated" USING (((EXISTS ( SELECT 1
   FROM "public"."admission_applications" "aa"
  WHERE (("aa"."id" = "admission_documents"."application_id") AND ("aa"."user_id" = ( SELECT "auth"."uid"() AS "uid"))))) OR (EXISTS ( SELECT 1
   FROM ("public"."admission_applications" "aa"
     JOIN "public"."user_profiles" "up" ON (("up"."organization_id" = "aa"."organization_id")))
  WHERE (("aa"."id" = "admission_documents"."application_id") AND ("up"."id" = ( SELECT "auth"."uid"() AS "uid")) AND ("up"."role" = ANY (ARRAY['org_admin'::"public"."system_role", 'director'::"public"."system_role", 'admissions'::"public"."system_role"])))))));



CREATE POLICY "Admin delete cycles" ON "public"."admission_cycles" FOR DELETE TO "authenticated" USING ((("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))) AND (EXISTS ( SELECT 1
   FROM "public"."user_profiles"
  WHERE (("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")) AND ("user_profiles"."role" = ANY (ARRAY['org_admin'::"public"."system_role", 'director'::"public"."system_role"])))))));



CREATE POLICY "Admin delete payments" ON "public"."payments" FOR DELETE TO "authenticated" USING ((("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))) AND (EXISTS ( SELECT 1
   FROM "public"."user_profiles"
  WHERE (("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")) AND ("user_profiles"."role" = ANY (ARRAY['org_admin'::"public"."system_role", 'finance'::"public"."system_role"])))))));



CREATE POLICY "Admin insert cycles" ON "public"."admission_cycles" FOR INSERT TO "authenticated" WITH CHECK ((("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))) AND (EXISTS ( SELECT 1
   FROM "public"."user_profiles"
  WHERE (("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")) AND ("user_profiles"."role" = ANY (ARRAY['org_admin'::"public"."system_role", 'director'::"public"."system_role"])))))));



CREATE POLICY "Admin insert payments" ON "public"."payments" FOR INSERT TO "authenticated" WITH CHECK ((("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))) AND (EXISTS ( SELECT 1
   FROM "public"."user_profiles"
  WHERE (("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")) AND ("user_profiles"."role" = ANY (ARRAY['org_admin'::"public"."system_role", 'finance'::"public"."system_role"])))))));



CREATE POLICY "Admin update cycles" ON "public"."admission_cycles" FOR UPDATE TO "authenticated" USING ((("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))) AND (EXISTS ( SELECT 1
   FROM "public"."user_profiles"
  WHERE (("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")) AND ("user_profiles"."role" = ANY (ARRAY['org_admin'::"public"."system_role", 'director'::"public"."system_role"])))))));



CREATE POLICY "Admin update payments" ON "public"."payments" FOR UPDATE TO "authenticated" USING ((("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))) AND (EXISTS ( SELECT 1
   FROM "public"."user_profiles"
  WHERE (("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")) AND ("user_profiles"."role" = ANY (ARRAY['org_admin'::"public"."system_role", 'finance'::"public"."system_role"])))))));



CREATE POLICY "Admins can update their organization" ON "public"."organizations" FOR UPDATE TO "authenticated" USING (("public"."is_superadmin"(( SELECT "auth"."uid"() AS "uid")) OR ("id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE (("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")) AND ("user_profiles"."role" = 'org_admin'::"public"."system_role"))))));



CREATE POLICY "Editar mi propio perfil" ON "public"."user_profiles" FOR UPDATE TO "authenticated" USING (("id" = ( SELECT "auth"."uid"() AS "uid")));



CREATE POLICY "Read families" ON "public"."student_families" FOR SELECT TO "authenticated" USING ((("parent_user_id" = ( SELECT "auth"."uid"() AS "uid")) OR (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))) AND (EXISTS ( SELECT 1
   FROM "public"."user_profiles"
  WHERE (("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")) AND ("user_profiles"."role" = ANY (ARRAY['org_admin'::"public"."system_role", 'director'::"public"."system_role", 'admissions'::"public"."system_role", 'teacher'::"public"."system_role"]))))))));



CREATE POLICY "Read organizations" ON "public"."organizations" FOR SELECT TO "authenticated" USING (("public"."is_superadmin"(( SELECT "auth"."uid"() AS "uid")) OR ("id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid"))))));



CREATE POLICY "Read payments" ON "public"."payments" FOR SELECT TO "authenticated" USING ((("application_id" IN ( SELECT "admission_applications"."id"
   FROM "public"."admission_applications"
  WHERE ("admission_applications"."user_id" = ( SELECT "auth"."uid"() AS "uid")))) OR (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))) AND (EXISTS ( SELECT 1
   FROM "public"."user_profiles"
  WHERE (("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")) AND ("user_profiles"."role" = ANY (ARRAY['org_admin'::"public"."system_role", 'finance'::"public"."system_role"]))))))));



CREATE POLICY "Solo staff autorizado ve chats" ON "public"."chat_sessions" FOR SELECT TO "authenticated" USING ((("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))) AND (EXISTS ( SELECT 1
   FROM "public"."user_profiles"
  WHERE (("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")) AND ("user_profiles"."role" = ANY (ARRAY['org_admin'::"public"."system_role", 'admissions'::"public"."system_role"])))))));



CREATE POLICY "Staff delete families" ON "public"."student_families" FOR DELETE TO "authenticated" USING ((("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))) AND (EXISTS ( SELECT 1
   FROM "public"."user_profiles"
  WHERE (("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")) AND ("user_profiles"."role" = ANY (ARRAY['org_admin'::"public"."system_role", 'director'::"public"."system_role", 'admissions'::"public"."system_role", 'teacher'::"public"."system_role"])))))));



CREATE POLICY "Staff insert families" ON "public"."student_families" FOR INSERT TO "authenticated" WITH CHECK ((("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))) AND (EXISTS ( SELECT 1
   FROM "public"."user_profiles"
  WHERE (("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")) AND ("user_profiles"."role" = ANY (ARRAY['org_admin'::"public"."system_role", 'director'::"public"."system_role", 'admissions'::"public"."system_role", 'teacher'::"public"."system_role"])))))));



CREATE POLICY "Staff update families" ON "public"."student_families" FOR UPDATE TO "authenticated" USING ((("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))) AND (EXISTS ( SELECT 1
   FROM "public"."user_profiles"
  WHERE (("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")) AND ("user_profiles"."role" = ANY (ARRAY['org_admin'::"public"."system_role", 'director'::"public"."system_role", 'admissions'::"public"."system_role", 'teacher'::"public"."system_role"])))))));



CREATE POLICY "Staff ve actividades" ON "public"."lead_activities" TO "authenticated" USING ((("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))) AND (EXISTS ( SELECT 1
   FROM "public"."user_profiles"
  WHERE (("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")) AND ("user_profiles"."role" = ANY (ARRAY['org_admin'::"public"."system_role", 'director'::"public"."system_role", 'admissions'::"public"."system_role"])))))));



CREATE POLICY "Staff ve mappings" ON "public"."social_mappings" TO "authenticated" USING ((("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))) AND (EXISTS ( SELECT 1
   FROM "public"."user_profiles"
  WHERE (("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")) AND ("user_profiles"."role" = ANY (ARRAY['org_admin'::"public"."system_role", 'director'::"public"."system_role", 'admissions'::"public"."system_role"])))))));



CREATE POLICY "Staff ve tareas" ON "public"."tasks" TO "authenticated" USING ((("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))) AND (EXISTS ( SELECT 1
   FROM "public"."user_profiles"
  WHERE (("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")) AND ("user_profiles"."role" = ANY (ARRAY['org_admin'::"public"."system_role", 'director'::"public"."system_role", 'admissions'::"public"."system_role", 'teacher'::"public"."system_role"])))))));



CREATE POLICY "Superadmin delete orgs" ON "public"."organizations" FOR DELETE TO "authenticated" USING ("public"."is_superadmin"(( SELECT "auth"."uid"() AS "uid")));



CREATE POLICY "Superadmin delete permissions" ON "public"."role_permissions" FOR DELETE TO "authenticated" USING ("public"."is_superadmin"(( SELECT "auth"."uid"() AS "uid")));



CREATE POLICY "Superadmin insert orgs" ON "public"."organizations" FOR INSERT TO "authenticated" WITH CHECK ("public"."is_superadmin"(( SELECT "auth"."uid"() AS "uid")));



CREATE POLICY "Superadmin insert permissions" ON "public"."role_permissions" FOR INSERT TO "authenticated" WITH CHECK ("public"."is_superadmin"(( SELECT "auth"."uid"() AS "uid")));



CREATE POLICY "Superadmin update permissions" ON "public"."role_permissions" FOR UPDATE TO "authenticated" USING ("public"."is_superadmin"(( SELECT "auth"."uid"() AS "uid")));



CREATE POLICY "Users can delete message queue from their organization's chats" ON "public"."message_queue" FOR DELETE TO "authenticated" USING (("chat_id" IN ( SELECT "chats"."id"
   FROM "public"."chats"
  WHERE ("chats"."organization_id" IN ( SELECT "user_profiles"."organization_id"
           FROM "public"."user_profiles"
          WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))))));



CREATE POLICY "Users can insert chats in their organization" ON "public"."chats" FOR INSERT TO "authenticated" WITH CHECK (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users can insert message queue for their organization's chats" ON "public"."message_queue" FOR INSERT TO "authenticated" WITH CHECK (("chat_id" IN ( SELECT "chats"."id"
   FROM "public"."chats"
  WHERE ("chats"."organization_id" IN ( SELECT "user_profiles"."organization_id"
           FROM "public"."user_profiles"
          WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))))));



CREATE POLICY "Users can insert messages in their organization" ON "public"."messages" FOR INSERT TO "authenticated" WITH CHECK (("chat_id" IN ( SELECT "c"."id"
   FROM "public"."chats" "c"
  WHERE ("c"."organization_id" IN ( SELECT "user_profiles"."organization_id"
           FROM "public"."user_profiles"
          WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))))));



CREATE POLICY "Users can update chats in their organization" ON "public"."chats" FOR UPDATE TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users can update message queue from their organization's chats" ON "public"."message_queue" FOR UPDATE TO "authenticated" USING (("chat_id" IN ( SELECT "chats"."id"
   FROM "public"."chats"
  WHERE ("chats"."organization_id" IN ( SELECT "user_profiles"."organization_id"
           FROM "public"."user_profiles"
          WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))))));



CREATE POLICY "Users can update messages in their organization" ON "public"."messages" FOR UPDATE TO "authenticated" USING (("chat_id" IN ( SELECT "c"."id"
   FROM "public"."chats" "c"
  WHERE ("c"."organization_id" IN ( SELECT "user_profiles"."organization_id"
           FROM "public"."user_profiles"
          WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))))));



CREATE POLICY "Users can view chats from their organization" ON "public"."chats" FOR SELECT TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users can view message queue from their organization's chats" ON "public"."message_queue" FOR SELECT TO "authenticated" USING (("chat_id" IN ( SELECT "chats"."id"
   FROM "public"."chats"
  WHERE ("chats"."organization_id" IN ( SELECT "user_profiles"."organization_id"
           FROM "public"."user_profiles"
          WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))))));



CREATE POLICY "Users can view messages in their organization" ON "public"."messages" FOR SELECT TO "authenticated" USING (("chat_id" IN ( SELECT "c"."id"
   FROM "public"."chats" "c"
  WHERE ("c"."organization_id" IN ( SELECT "user_profiles"."organization_id"
           FROM "public"."user_profiles"
          WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))))));



CREATE POLICY "Users insert admission_requirement_documents by org" ON "public"."admission_requirement_documents" FOR INSERT TO "authenticated" WITH CHECK (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = "auth"."uid"()))));



CREATE POLICY "Users insert announcements by org" ON "public"."announcements" FOR INSERT TO "authenticated" WITH CHECK (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users insert appointment_blackouts by org" ON "public"."appointment_blackouts" FOR INSERT TO "authenticated" WITH CHECK (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users insert appointment_settings by org" ON "public"."appointment_settings" FOR INSERT TO "authenticated" WITH CHECK (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users insert appointments by org" ON "public"."appointments" FOR INSERT TO "authenticated" WITH CHECK (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users insert availability_slots by org" ON "public"."availability_slots" FOR INSERT TO "authenticated" WITH CHECK (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users insert bot_capabilities by org" ON "public"."bot_capabilities" FOR INSERT TO "authenticated" WITH CHECK (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users insert bot_capability_contacts by org" ON "public"."bot_capability_contacts" FOR INSERT TO "authenticated" WITH CHECK (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users insert bot_capability_finance by org" ON "public"."bot_capability_finance" FOR INSERT TO "authenticated" WITH CHECK (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users insert bot_complaints by org" ON "public"."bot_complaints" FOR INSERT TO "authenticated" WITH CHECK (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users insert crm_contacts by org" ON "public"."crm_contacts" FOR INSERT TO "authenticated" WITH CHECK (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users insert directory_contacts by org" ON "public"."directory_contacts" FOR INSERT TO "authenticated" WITH CHECK (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users insert email_template_bases by org" ON "public"."email_template_bases" FOR INSERT TO "authenticated" WITH CHECK (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = "auth"."uid"()))));



CREATE POLICY "Users insert email_template_triggers by org" ON "public"."email_template_triggers" FOR INSERT TO "authenticated" WITH CHECK (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = "auth"."uid"()))));



CREATE POLICY "Users insert email_templates by org" ON "public"."email_templates" FOR INSERT TO "authenticated" WITH CHECK (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = "auth"."uid"()))));



CREATE POLICY "Users insert faqs by org" ON "public"."faqs" FOR INSERT TO "authenticated" WITH CHECK (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users insert leads by org" ON "public"."leads" FOR INSERT TO "authenticated" WITH CHECK (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users insert school_schedules by org" ON "public"."school_schedules" FOR INSERT TO "authenticated" WITH CHECK (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users insert special_schedules by org" ON "public"."special_schedules" FOR INSERT TO "authenticated" WITH CHECK (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users select admission_requirement_documents by org" ON "public"."admission_requirement_documents" FOR SELECT TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = "auth"."uid"()))));



CREATE POLICY "Users select announcements by org" ON "public"."announcements" FOR SELECT TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users select appointment_blackouts by org" ON "public"."appointment_blackouts" FOR SELECT TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users select appointment_settings by org" ON "public"."appointment_settings" FOR SELECT TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users select appointments by org" ON "public"."appointments" FOR SELECT TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users select availability_slots by org" ON "public"."availability_slots" FOR SELECT TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users select bot_capabilities by org" ON "public"."bot_capabilities" FOR SELECT TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users select bot_capability_contacts by org" ON "public"."bot_capability_contacts" FOR SELECT TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users select bot_capability_finance by org" ON "public"."bot_capability_finance" FOR SELECT TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users select bot_complaints by org" ON "public"."bot_complaints" FOR SELECT TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users select crm_contacts by org" ON "public"."crm_contacts" FOR SELECT TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users select directory_contacts by org" ON "public"."directory_contacts" FOR SELECT TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users select email_template_bases by org" ON "public"."email_template_bases" FOR SELECT TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = "auth"."uid"()))));



CREATE POLICY "Users select email_template_triggers by org" ON "public"."email_template_triggers" FOR SELECT TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = "auth"."uid"()))));



CREATE POLICY "Users select email_templates by org" ON "public"."email_templates" FOR SELECT TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = "auth"."uid"()))));



CREATE POLICY "Users select faqs by org" ON "public"."faqs" FOR SELECT TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users select leads by org" ON "public"."leads" FOR SELECT TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users select school_schedules by org" ON "public"."school_schedules" FOR SELECT TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users select special_schedules by org" ON "public"."special_schedules" FOR SELECT TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users update admission_requirement_documents by org" ON "public"."admission_requirement_documents" FOR UPDATE TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = "auth"."uid"()))));



CREATE POLICY "Users update announcements by org" ON "public"."announcements" FOR UPDATE TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users update appointment_blackouts by org" ON "public"."appointment_blackouts" FOR UPDATE TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users update appointment_settings by org" ON "public"."appointment_settings" FOR UPDATE TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users update appointments by org" ON "public"."appointments" FOR UPDATE TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users update availability_slots by org" ON "public"."availability_slots" FOR UPDATE TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users update bot_capabilities by org" ON "public"."bot_capabilities" FOR UPDATE TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users update bot_capability_contacts by org" ON "public"."bot_capability_contacts" FOR UPDATE TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users update bot_capability_finance by org" ON "public"."bot_capability_finance" FOR UPDATE TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users update bot_complaints by org" ON "public"."bot_complaints" FOR UPDATE TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users update crm_contacts by org" ON "public"."crm_contacts" FOR UPDATE TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users update directory_contacts by org" ON "public"."directory_contacts" FOR UPDATE TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users update email_template_bases by org" ON "public"."email_template_bases" FOR UPDATE TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = "auth"."uid"()))));



CREATE POLICY "Users update email_template_triggers by org" ON "public"."email_template_triggers" FOR UPDATE TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = "auth"."uid"()))));



CREATE POLICY "Users update email_templates by org" ON "public"."email_templates" FOR UPDATE TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = "auth"."uid"()))));



CREATE POLICY "Users update faqs by org" ON "public"."faqs" FOR UPDATE TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users update leads by org" ON "public"."leads" FOR UPDATE TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users update school_schedules by org" ON "public"."school_schedules" FOR UPDATE TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Users update special_schedules by org" ON "public"."special_schedules" FOR UPDATE TO "authenticated" USING (("organization_id" IN ( SELECT "user_profiles"."organization_id"
   FROM "public"."user_profiles"
  WHERE ("user_profiles"."id" = ( SELECT "auth"."uid"() AS "uid")))));



CREATE POLICY "Ver ciclos activos" ON "public"."admission_cycles" FOR SELECT TO "authenticated" USING (true);



CREATE POLICY "Ver perfiles de mi org" ON "public"."user_profiles" FOR SELECT TO "authenticated" USING ((("id" = ( SELECT "auth"."uid"() AS "uid")) OR ("organization_id" = "public"."get_my_org_id"())));



CREATE POLICY "Ver permisos" ON "public"."role_permissions" FOR SELECT TO "authenticated" USING (true);



ALTER TABLE "public"."admission_applications" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."admission_cycles" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."admission_documents" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."admission_requirement_documents" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."announcements" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."appointment_blackouts" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."appointment_settings" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."appointments" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."availability_slots" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."bot_capabilities" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."bot_capability_contacts" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."bot_capability_finance" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."bot_complaints" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."chat_sessions" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."chats" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."crm_contacts" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."directory_contacts" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."email_template_bases" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."email_template_triggers" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."email_templates" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."faqs" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."lead_activities" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."leads" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."message_queue" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."messages" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."organizations" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."payments" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."role_permissions" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."school_schedules" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."social_mappings" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."special_schedules" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."student_families" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."students" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."tasks" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."user_profiles" ENABLE ROW LEVEL SECURITY;




ALTER PUBLICATION "supabase_realtime" OWNER TO "postgres";






ALTER PUBLICATION "supabase_realtime" ADD TABLE ONLY "public"."appointments";



ALTER PUBLICATION "supabase_realtime" ADD TABLE ONLY "public"."chats";



ALTER PUBLICATION "supabase_realtime" ADD TABLE ONLY "public"."messages";






GRANT USAGE ON SCHEMA "public" TO "postgres";
GRANT USAGE ON SCHEMA "public" TO "anon";
GRANT USAGE ON SCHEMA "public" TO "authenticated";
GRANT USAGE ON SCHEMA "public" TO "service_role";








































































































































































































































































GRANT ALL ON TABLE "public"."message_queue" TO "anon";
GRANT ALL ON TABLE "public"."message_queue" TO "authenticated";
GRANT ALL ON TABLE "public"."message_queue" TO "service_role";



GRANT ALL ON FUNCTION "public"."accumulate_whatsapp_message"("p_chat_id" "uuid", "p_new_text" "text") TO "anon";
GRANT ALL ON FUNCTION "public"."accumulate_whatsapp_message"("p_chat_id" "uuid", "p_new_text" "text") TO "authenticated";
GRANT ALL ON FUNCTION "public"."accumulate_whatsapp_message"("p_chat_id" "uuid", "p_new_text" "text") TO "service_role";



GRANT ALL ON FUNCTION "public"."check_permission"("user_id" "uuid", "req_module" "text", "req_action" "text") TO "anon";
GRANT ALL ON FUNCTION "public"."check_permission"("user_id" "uuid", "req_module" "text", "req_action" "text") TO "authenticated";
GRANT ALL ON FUNCTION "public"."check_permission"("user_id" "uuid", "req_module" "text", "req_action" "text") TO "service_role";



GRANT ALL ON FUNCTION "public"."concat_names_mx"("first_name" "text", "middle_name" "text", "last_name_paternal" "text", "last_name_maternal" "text") TO "anon";
GRANT ALL ON FUNCTION "public"."concat_names_mx"("first_name" "text", "middle_name" "text", "last_name_paternal" "text", "last_name_maternal" "text") TO "authenticated";
GRANT ALL ON FUNCTION "public"."concat_names_mx"("first_name" "text", "middle_name" "text", "last_name_paternal" "text", "last_name_maternal" "text") TO "service_role";



GRANT ALL ON FUNCTION "public"."get_my_org_id"() TO "anon";
GRANT ALL ON FUNCTION "public"."get_my_org_id"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_my_org_id"() TO "service_role";



GRANT ALL ON FUNCTION "public"."is_superadmin"("user_id" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."is_superadmin"("user_id" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."is_superadmin"("user_id" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."notify_lead_created"() TO "anon";
GRANT ALL ON FUNCTION "public"."notify_lead_created"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."notify_lead_created"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_updated_at"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_updated_at"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_updated_at"() TO "service_role";


















GRANT ALL ON TABLE "public"."admission_applications" TO "anon";
GRANT ALL ON TABLE "public"."admission_applications" TO "authenticated";
GRANT ALL ON TABLE "public"."admission_applications" TO "service_role";



GRANT ALL ON TABLE "public"."admission_cycles" TO "anon";
GRANT ALL ON TABLE "public"."admission_cycles" TO "authenticated";
GRANT ALL ON TABLE "public"."admission_cycles" TO "service_role";



GRANT ALL ON TABLE "public"."admission_documents" TO "anon";
GRANT ALL ON TABLE "public"."admission_documents" TO "authenticated";
GRANT ALL ON TABLE "public"."admission_documents" TO "service_role";



GRANT ALL ON TABLE "public"."admission_requirement_documents" TO "anon";
GRANT ALL ON TABLE "public"."admission_requirement_documents" TO "authenticated";
GRANT ALL ON TABLE "public"."admission_requirement_documents" TO "service_role";



GRANT ALL ON TABLE "public"."announcements" TO "anon";
GRANT ALL ON TABLE "public"."announcements" TO "authenticated";
GRANT ALL ON TABLE "public"."announcements" TO "service_role";



GRANT ALL ON TABLE "public"."appointment_blackouts" TO "anon";
GRANT ALL ON TABLE "public"."appointment_blackouts" TO "authenticated";
GRANT ALL ON TABLE "public"."appointment_blackouts" TO "service_role";



GRANT ALL ON TABLE "public"."appointment_settings" TO "anon";
GRANT ALL ON TABLE "public"."appointment_settings" TO "authenticated";
GRANT ALL ON TABLE "public"."appointment_settings" TO "service_role";



GRANT ALL ON TABLE "public"."appointments" TO "anon";
GRANT ALL ON TABLE "public"."appointments" TO "authenticated";
GRANT ALL ON TABLE "public"."appointments" TO "service_role";



GRANT ALL ON TABLE "public"."availability_slots" TO "anon";
GRANT ALL ON TABLE "public"."availability_slots" TO "authenticated";
GRANT ALL ON TABLE "public"."availability_slots" TO "service_role";



GRANT ALL ON TABLE "public"."bot_capabilities" TO "anon";
GRANT ALL ON TABLE "public"."bot_capabilities" TO "authenticated";
GRANT ALL ON TABLE "public"."bot_capabilities" TO "service_role";



GRANT ALL ON TABLE "public"."bot_capability_contacts" TO "anon";
GRANT ALL ON TABLE "public"."bot_capability_contacts" TO "authenticated";
GRANT ALL ON TABLE "public"."bot_capability_contacts" TO "service_role";



GRANT ALL ON TABLE "public"."bot_capability_finance" TO "anon";
GRANT ALL ON TABLE "public"."bot_capability_finance" TO "authenticated";
GRANT ALL ON TABLE "public"."bot_capability_finance" TO "service_role";



GRANT ALL ON TABLE "public"."bot_complaints" TO "anon";
GRANT ALL ON TABLE "public"."bot_complaints" TO "authenticated";
GRANT ALL ON TABLE "public"."bot_complaints" TO "service_role";



GRANT ALL ON TABLE "public"."chat_sessions" TO "anon";
GRANT ALL ON TABLE "public"."chat_sessions" TO "authenticated";
GRANT ALL ON TABLE "public"."chat_sessions" TO "service_role";



GRANT ALL ON TABLE "public"."chats" TO "anon";
GRANT ALL ON TABLE "public"."chats" TO "authenticated";
GRANT ALL ON TABLE "public"."chats" TO "service_role";



GRANT ALL ON TABLE "public"."crm_contacts" TO "anon";
GRANT ALL ON TABLE "public"."crm_contacts" TO "authenticated";
GRANT ALL ON TABLE "public"."crm_contacts" TO "service_role";



GRANT ALL ON TABLE "public"."directory_contacts" TO "anon";
GRANT ALL ON TABLE "public"."directory_contacts" TO "authenticated";
GRANT ALL ON TABLE "public"."directory_contacts" TO "service_role";



GRANT ALL ON TABLE "public"."email_template_bases" TO "anon";
GRANT ALL ON TABLE "public"."email_template_bases" TO "authenticated";
GRANT ALL ON TABLE "public"."email_template_bases" TO "service_role";



GRANT ALL ON TABLE "public"."email_template_triggers" TO "anon";
GRANT ALL ON TABLE "public"."email_template_triggers" TO "authenticated";
GRANT ALL ON TABLE "public"."email_template_triggers" TO "service_role";



GRANT ALL ON TABLE "public"."email_templates" TO "anon";
GRANT ALL ON TABLE "public"."email_templates" TO "authenticated";
GRANT ALL ON TABLE "public"."email_templates" TO "service_role";



GRANT ALL ON TABLE "public"."event_outbox" TO "anon";
GRANT ALL ON TABLE "public"."event_outbox" TO "authenticated";
GRANT ALL ON TABLE "public"."event_outbox" TO "service_role";



GRANT ALL ON TABLE "public"."faqs" TO "anon";
GRANT ALL ON TABLE "public"."faqs" TO "authenticated";
GRANT ALL ON TABLE "public"."faqs" TO "service_role";



GRANT ALL ON TABLE "public"."lead_activities" TO "anon";
GRANT ALL ON TABLE "public"."lead_activities" TO "authenticated";
GRANT ALL ON TABLE "public"."lead_activities" TO "service_role";



GRANT ALL ON TABLE "public"."leads" TO "anon";
GRANT ALL ON TABLE "public"."leads" TO "authenticated";
GRANT ALL ON TABLE "public"."leads" TO "service_role";



GRANT ALL ON SEQUENCE "public"."leads_lead_number_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."leads_lead_number_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."leads_lead_number_seq" TO "service_role";



GRANT ALL ON TABLE "public"."messages" TO "anon";
GRANT ALL ON TABLE "public"."messages" TO "authenticated";
GRANT ALL ON TABLE "public"."messages" TO "service_role";



GRANT ALL ON TABLE "public"."organization_knowledge" TO "anon";
GRANT ALL ON TABLE "public"."organization_knowledge" TO "authenticated";
GRANT ALL ON TABLE "public"."organization_knowledge" TO "service_role";



GRANT ALL ON TABLE "public"."organizations" TO "anon";
GRANT ALL ON TABLE "public"."organizations" TO "authenticated";
GRANT ALL ON TABLE "public"."organizations" TO "service_role";



GRANT ALL ON TABLE "public"."payments" TO "anon";
GRANT ALL ON TABLE "public"."payments" TO "authenticated";
GRANT ALL ON TABLE "public"."payments" TO "service_role";



GRANT ALL ON TABLE "public"."role_permissions" TO "anon";
GRANT ALL ON TABLE "public"."role_permissions" TO "authenticated";
GRANT ALL ON TABLE "public"."role_permissions" TO "service_role";



GRANT ALL ON TABLE "public"."school_schedules" TO "anon";
GRANT ALL ON TABLE "public"."school_schedules" TO "authenticated";
GRANT ALL ON TABLE "public"."school_schedules" TO "service_role";



GRANT ALL ON TABLE "public"."social_mappings" TO "anon";
GRANT ALL ON TABLE "public"."social_mappings" TO "authenticated";
GRANT ALL ON TABLE "public"."social_mappings" TO "service_role";



GRANT ALL ON TABLE "public"."special_schedules" TO "anon";
GRANT ALL ON TABLE "public"."special_schedules" TO "authenticated";
GRANT ALL ON TABLE "public"."special_schedules" TO "service_role";



GRANT ALL ON TABLE "public"."student_families" TO "anon";
GRANT ALL ON TABLE "public"."student_families" TO "authenticated";
GRANT ALL ON TABLE "public"."student_families" TO "service_role";



GRANT ALL ON TABLE "public"."students" TO "anon";
GRANT ALL ON TABLE "public"."students" TO "authenticated";
GRANT ALL ON TABLE "public"."students" TO "service_role";



GRANT ALL ON TABLE "public"."tasks" TO "anon";
GRANT ALL ON TABLE "public"."tasks" TO "authenticated";
GRANT ALL ON TABLE "public"."tasks" TO "service_role";



GRANT ALL ON TABLE "public"."user_profiles" TO "anon";
GRANT ALL ON TABLE "public"."user_profiles" TO "authenticated";
GRANT ALL ON TABLE "public"."user_profiles" TO "service_role";









ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "service_role";































