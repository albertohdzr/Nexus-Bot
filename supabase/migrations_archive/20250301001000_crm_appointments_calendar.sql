-- Ajustes para calendario de citas en CRM

-- Configuración base por organización
create table if not exists public.appointment_settings (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  slot_duration_minutes integer not null default 60,
  days_of_week smallint[] not null default '{1,2,3,4,5}', -- 0=domingo ... 6=sábado
  start_time time not null default '08:00',
  end_time time not null default '14:00',
  timezone text default 'America/Mexico_City',
  buffer_minutes integer not null default 0,
  allow_overbooking boolean not null default false,
  updated_at timestamptz not null default timezone('utc', now()),
  constraint appointment_settings_time_check check (end_time > start_time),
  constraint appointment_settings_days_check check (
    array_length(days_of_week, 1) > 0
    and days_of_week <@ ARRAY[0::smallint,1::smallint,2::smallint,3::smallint,4::smallint,5::smallint,6::smallint]
  )
);
create unique index if not exists appointment_settings_org_idx on public.appointment_settings(organization_id);

alter table public.appointment_settings enable row level security;
drop policy if exists "Users select appointment_settings by org" on public.appointment_settings;
create policy "Users select appointment_settings by org" on public.appointment_settings
  for select to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));
drop policy if exists "Users insert appointment_settings by org" on public.appointment_settings;
create policy "Users insert appointment_settings by org" on public.appointment_settings
  for insert to authenticated
  with check (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));
drop policy if exists "Users update appointment_settings by org" on public.appointment_settings;
create policy "Users update appointment_settings by org" on public.appointment_settings
  for update to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));

-- Bloqueos manuales por día o rango horario
create table if not exists public.appointment_blackouts (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  date date not null,
  start_time time not null default '00:00',
  end_time time not null default '23:59:59',
  reason text,
  created_by_profile_id uuid references public.user_profiles(id),
  created_at timestamptz not null default timezone('utc', now())
);
create unique index if not exists appointment_blackouts_org_date_time_idx
  on public.appointment_blackouts(organization_id, date, start_time, end_time);

alter table public.appointment_blackouts enable row level security;
drop policy if exists "Users select appointment_blackouts by org" on public.appointment_blackouts;
create policy "Users select appointment_blackouts by org" on public.appointment_blackouts
  for select to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));
drop policy if exists "Users insert appointment_blackouts by org" on public.appointment_blackouts;
create policy "Users insert appointment_blackouts by org" on public.appointment_blackouts
  for insert to authenticated
  with check (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));
drop policy if exists "Users update appointment_blackouts by org" on public.appointment_blackouts;
create policy "Users update appointment_blackouts by org" on public.appointment_blackouts
  for update to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));

-- Campos de bloqueo directo en slots
alter table public.availability_slots
  add column if not exists is_blocked boolean not null default false,
  add column if not exists block_reason text,
  add column if not exists blocked_by_profile_id uuid references public.user_profiles(id),
  add constraint availability_slots_time_check check (ends_at > starts_at);

create unique index if not exists availability_slots_org_start_end_key
  on public.availability_slots(organization_id, starts_at, ends_at);

-- Validación de tiempo en appointments
alter table public.appointments
  add constraint appointments_time_check check (ends_at is null or ends_at > starts_at);
