-- Gestión de capacidades del chatbot y registro de quejas

-- Tabla principal de capacidades
create table if not exists public.bot_capabilities (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  slug text not null,
  title text not null,
  description text,
  instructions text,
  response_template text,
  type text default 'custom',
  enabled boolean not null default true,
  priority integer not null default 0,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint bot_capabilities_slug_unique_per_org unique (organization_id, slug)
);
create index if not exists bot_capabilities_org_priority_idx on public.bot_capabilities(organization_id, enabled, priority desc);

alter table public.bot_capabilities enable row level security;
drop policy if exists "Users select bot_capabilities by org" on public.bot_capabilities;
create policy "Users select bot_capabilities by org" on public.bot_capabilities
  for select to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));
drop policy if exists "Users insert bot_capabilities by org" on public.bot_capabilities;
create policy "Users insert bot_capabilities by org" on public.bot_capabilities
  for insert to authenticated
  with check (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));
drop policy if exists "Users update bot_capabilities by org" on public.bot_capabilities;
create policy "Users update bot_capabilities by org" on public.bot_capabilities
  for update to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));

-- Contactos por capacidad (ej. caja, admisiones)
create table if not exists public.bot_capability_contacts (
  id uuid primary key default gen_random_uuid(),
  capability_id uuid not null references public.bot_capabilities(id) on delete cascade,
  organization_id uuid not null references public.organizations(id) on delete cascade,
  name text not null,
  role text,
  email text,
  phone text,
  notes text,
  priority integer not null default 0,
  is_active boolean not null default true,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);
create index if not exists bot_capability_contacts_org_role_idx on public.bot_capability_contacts(organization_id, role, is_active);
create index if not exists bot_capability_contacts_capability_idx on public.bot_capability_contacts(capability_id);

alter table public.bot_capability_contacts enable row level security;
drop policy if exists "Users select bot_capability_contacts by org" on public.bot_capability_contacts;
create policy "Users select bot_capability_contacts by org" on public.bot_capability_contacts
  for select to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));
drop policy if exists "Users insert bot_capability_contacts by org" on public.bot_capability_contacts;
create policy "Users insert bot_capability_contacts by org" on public.bot_capability_contacts
  for insert to authenticated
  with check (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));
drop policy if exists "Users update bot_capability_contacts by org" on public.bot_capability_contacts;
create policy "Users update bot_capability_contacts by org" on public.bot_capability_contacts
  for update to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));

-- Información financiera / datos tabulares por capacidad
create table if not exists public.bot_capability_finance (
  id uuid primary key default gen_random_uuid(),
  capability_id uuid not null references public.bot_capabilities(id) on delete cascade,
  organization_id uuid not null references public.organizations(id) on delete cascade,
  item text not null,
  value text not null,
  notes text,
  valid_from date,
  valid_to date,
  priority integer not null default 0,
  is_active boolean not null default true,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);
create index if not exists bot_capability_finance_org_item_idx on public.bot_capability_finance(organization_id, item, is_active);
create index if not exists bot_capability_finance_capability_idx on public.bot_capability_finance(capability_id);

alter table public.bot_capability_finance enable row level security;
drop policy if exists "Users select bot_capability_finance by org" on public.bot_capability_finance;
create policy "Users select bot_capability_finance by org" on public.bot_capability_finance
  for select to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));
drop policy if exists "Users insert bot_capability_finance by org" on public.bot_capability_finance;
create policy "Users insert bot_capability_finance by org" on public.bot_capability_finance
  for insert to authenticated
  with check (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));
drop policy if exists "Users update bot_capability_finance by org" on public.bot_capability_finance;
create policy "Users update bot_capability_finance by org" on public.bot_capability_finance
  for update to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));

-- Registro de quejas capturadas por el bot
create table if not exists public.bot_complaints (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  capability_id uuid references public.bot_capabilities(id) on delete set null,
  channel text,
  customer_name text,
  customer_contact text,
  summary text not null,
  status text not null default 'open',
  created_by_profile_id uuid references public.user_profiles(id),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);
create index if not exists bot_complaints_org_status_idx on public.bot_complaints(organization_id, status);
create index if not exists bot_complaints_capability_idx on public.bot_complaints(capability_id);

alter table public.bot_complaints enable row level security;
drop policy if exists "Users select bot_complaints by org" on public.bot_complaints;
create policy "Users select bot_complaints by org" on public.bot_complaints
  for select to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));
drop policy if exists "Users insert bot_complaints by org" on public.bot_complaints;
create policy "Users insert bot_complaints by org" on public.bot_complaints
  for insert to authenticated
  with check (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));
drop policy if exists "Users update bot_complaints by org" on public.bot_complaints;
create policy "Users update bot_complaints by org" on public.bot_complaints
  for update to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));
