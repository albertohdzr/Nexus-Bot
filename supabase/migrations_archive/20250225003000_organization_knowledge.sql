-- Knowledge base per organization for bot context

create table if not exists public.organization_knowledge (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  title text not null,
  category text,
  content text,
  created_by uuid references public.user_profiles(id) on delete set null,
  updated_by uuid references public.user_profiles(id) on delete set null,
  created_at timestamptz default now() not null,
  updated_at timestamptz default now() not null
);

create index if not exists organization_knowledge_org_id_idx on public.organization_knowledge(organization_id);
create index if not exists organization_knowledge_category_idx on public.organization_knowledge(category);

-- Basic bot configuration stored alongside the organization
alter table public.organizations
  add column if not exists bot_name text default 'Asistente',
  add column if not exists bot_instructions text,
  add column if not exists bot_tone text,
  add column if not exists bot_language text default 'es',
  add column if not exists bot_model text default 'gpt-4o-mini';