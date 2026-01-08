-- =============================================
-- Lead created webhook trigger 
-- =============================================

create extension if not exists pg_net;

-- (Opcional pero recomendado) Outbox para evitar duplicados
create table if not exists public.event_outbox (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null,
  event_type text not null,
  entity_id uuid not null,
  created_at timestamptz not null default now(),
  unique (organization_id, event_type, entity_id)
);

create or replace function public.notify_lead_created()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
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

drop trigger if exists lead_created_webhook on public.leads;
create trigger lead_created_webhook
after insert on public.leads
for each row execute function public.notify_lead_created();
