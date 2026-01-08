alter table public.whatsapp_templates
  add column if not exists quality_score text,
  add column if not exists last_meta_event jsonb default '{}'::jsonb,
  add column if not exists meta_updated_at timestamptz;
