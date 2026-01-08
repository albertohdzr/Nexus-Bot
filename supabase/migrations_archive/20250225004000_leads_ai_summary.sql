-- Add AI summary fields for leads captured via bot

alter table public.leads
  add column if not exists ai_summary text,
  add column if not exists ai_metadata jsonb default '{}'::jsonb;
