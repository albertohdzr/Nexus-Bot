-- Email templates and base settings per organization

create table if not exists public.email_template_bases (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  logo_url text,
  header_html text,
  footer_html text,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create unique index if not exists email_template_bases_org_unique on public.email_template_bases(organization_id);
create index if not exists email_template_bases_org_idx on public.email_template_bases(organization_id);

create table if not exists public.email_templates (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  base_id uuid references public.email_template_bases(id) on delete set null,
  name text not null,
  subject text not null,
  category text,
  channel text not null default 'email',
  status text not null default 'active',
  body_html text not null,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index if not exists email_templates_org_idx on public.email_templates(organization_id);
create index if not exists email_templates_status_idx on public.email_templates(status);

create table if not exists public.email_template_triggers (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  template_id uuid not null references public.email_templates(id) on delete cascade,
  event_type text not null,
  source text not null default 'any',
  rules jsonb not null default '[]'::jsonb,
  is_active boolean not null default true,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index if not exists email_template_triggers_org_idx on public.email_template_triggers(organization_id);
create index if not exists email_template_triggers_template_idx on public.email_template_triggers(template_id);
create index if not exists email_template_triggers_event_idx on public.email_template_triggers(event_type);

alter table public.email_template_bases enable row level security;
alter table public.email_templates enable row level security;
alter table public.email_template_triggers enable row level security;

drop policy if exists "Users select email_template_bases by org" on public.email_template_bases;
drop policy if exists "Users insert email_template_bases by org" on public.email_template_bases;
drop policy if exists "Users update email_template_bases by org" on public.email_template_bases;
create policy "Users select email_template_bases by org" on public.email_template_bases
  for select to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = auth.uid()));
create policy "Users insert email_template_bases by org" on public.email_template_bases
  for insert to authenticated
  with check (organization_id in (select organization_id from public.user_profiles where id = auth.uid()));
create policy "Users update email_template_bases by org" on public.email_template_bases
  for update to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = auth.uid()));

drop policy if exists "Users select email_templates by org" on public.email_templates;
drop policy if exists "Users insert email_templates by org" on public.email_templates;
drop policy if exists "Users update email_templates by org" on public.email_templates;
create policy "Users select email_templates by org" on public.email_templates
  for select to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = auth.uid()));
create policy "Users insert email_templates by org" on public.email_templates
  for insert to authenticated
  with check (organization_id in (select organization_id from public.user_profiles where id = auth.uid()));
create policy "Users update email_templates by org" on public.email_templates
  for update to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = auth.uid()));

drop policy if exists "Users select email_template_triggers by org" on public.email_template_triggers;
drop policy if exists "Users insert email_template_triggers by org" on public.email_template_triggers;
drop policy if exists "Users update email_template_triggers by org" on public.email_template_triggers;
create policy "Users select email_template_triggers by org" on public.email_template_triggers
  for select to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = auth.uid()));
create policy "Users insert email_template_triggers by org" on public.email_template_triggers
  for insert to authenticated
  with check (organization_id in (select organization_id from public.user_profiles where id = auth.uid()));
create policy "Users update email_template_triggers by org" on public.email_template_triggers
  for update to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = auth.uid()));
