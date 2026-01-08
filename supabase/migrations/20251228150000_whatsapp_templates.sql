do $$
begin
  if not exists (
    select 1
    from pg_type t
    join pg_namespace n on n.oid = t.typnamespace
    where t.typname = 'whatsapp_template_category'
      and n.nspname = 'public'
  ) then
    create type public.whatsapp_template_category as enum (
      'UTILITY',
      'MARKETING',
      'AUTHENTICATION'
    );
  end if;

  if not exists (
    select 1
    from pg_type t
    join pg_namespace n on n.oid = t.typnamespace
    where t.typname = 'whatsapp_template_parameter_format'
      and n.nspname = 'public'
  ) then
    create type public.whatsapp_template_parameter_format as enum (
      'positional',
      'named'
    );
  end if;
end $$;

create table if not exists public.whatsapp_templates (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  external_id text,
  name text not null,
  language text not null,
  category public.whatsapp_template_category not null,
  status text not null default 'draft'::text,
  parameter_format public.whatsapp_template_parameter_format not null default 'positional'::public.whatsapp_template_parameter_format,
  components jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default timezone('utc'::text, now()),
  updated_at timestamptz not null default timezone('utc'::text, now())
);

create index if not exists whatsapp_templates_org_idx
  on public.whatsapp_templates (organization_id);

create index if not exists whatsapp_templates_name_idx
  on public.whatsapp_templates (name);

create unique index if not exists whatsapp_templates_org_name_lang_unique
  on public.whatsapp_templates (organization_id, name, language);

alter table public.whatsapp_templates enable row level security;

create policy "Users select whatsapp_templates by org" on public.whatsapp_templates
  for select to authenticated
  using (organization_id in (
    select user_profiles.organization_id
    from public.user_profiles
    where user_profiles.id = auth.uid()
  ));

create policy "Users insert whatsapp_templates by org" on public.whatsapp_templates
  for insert to authenticated
  with check (organization_id in (
    select user_profiles.organization_id
    from public.user_profiles
    where user_profiles.id = auth.uid()
  ));

create policy "Users update whatsapp_templates by org" on public.whatsapp_templates
  for update to authenticated
  using (organization_id in (
    select user_profiles.organization_id
    from public.user_profiles
    where user_profiles.id = auth.uid()
  ));

create policy "Users delete whatsapp_templates by org" on public.whatsapp_templates
  for delete to authenticated
  using (organization_id in (
    select user_profiles.organization_id
    from public.user_profiles
    where user_profiles.id = auth.uid()
  ));

grant all on table public.whatsapp_templates to anon;
grant all on table public.whatsapp_templates to authenticated;
grant all on table public.whatsapp_templates to service_role;
