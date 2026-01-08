create table if not exists public.ai_logs (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  organization_id uuid,
  chat_id uuid,
  conversation_id text,
  event_type text not null,
  payload jsonb not null default '{}'::jsonb
);

create index if not exists ai_logs_org_created_idx
  on public.ai_logs (organization_id, created_at desc);

create index if not exists ai_logs_chat_created_idx
  on public.ai_logs (chat_id, created_at desc);

create index if not exists ai_logs_event_type_idx
  on public.ai_logs (event_type);

alter table public.ai_logs enable row level security;

create or replace function public.purge_ai_logs()
returns integer
language plpgsql
as $$
declare
  deleted_count integer := 0;
begin
  delete from public.ai_logs
  where created_at < now() - interval '3 months';

  get diagnostics deleted_count = row_count;
  return deleted_count;
end;
$$;
