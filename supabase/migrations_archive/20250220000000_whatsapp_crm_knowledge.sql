-- Extensions
create extension if not exists pgcrypto;

-- 1. Organizations adjustments
alter table public.organizations
  add column if not exists display_phone_number text,
  add column if not exists phone_number_id text;
create unique index if not exists organizations_phone_number_id_idx on public.organizations(phone_number_id);

-- 1.2 WhatsApp chats
alter table public.chats
  add column if not exists state text,
  add column if not exists state_context jsonb,
  add column if not exists last_message_at timestamptz,
  alter column organization_id set not null,
  alter column created_at set default timezone('utc', now()),
  alter column updated_at set default timezone('utc', now());
alter table public.chats drop constraint if exists chats_wa_id_key;
create unique index if not exists chats_wa_id_org_id_idx on public.chats(wa_id, organization_id);
create index if not exists chats_org_id_idx on public.chats(organization_id);
comment on table public.chats is 'Conversaciones de WhatsApp por organización';

-- 1.2 WhatsApp messages
alter table public.messages
  add column if not exists direction text,
  add column if not exists role text,
  add column if not exists wa_timestamp timestamptz,
  add column if not exists sent_at timestamptz,
  add column if not exists delivered_at timestamptz,
  add column if not exists read_at timestamptz,
  add column if not exists sender_profile_id uuid references public.user_profiles(id),
  add column if not exists sender_name text,
  add column if not exists payload jsonb,
  add column if not exists media_id text,
  add column if not exists media_url text,
  add column if not exists media_path text,
  add column if not exists media_mime_type text,
  alter column created_at set default timezone('utc', now()),
  alter column status set default 'received';
alter table public.messages drop constraint if exists messages_direction_check;
alter table public.messages add constraint messages_direction_check check (direction is null or direction in ('inbound', 'outbound'));
alter table public.messages drop constraint if exists messages_role_check;
alter table public.messages add constraint messages_role_check check (role is null or role in ('user', 'assistant', 'agent'));
create index if not exists messages_chat_id_created_at_idx on public.messages(chat_id, created_at);
create index if not exists messages_sender_profile_id_idx on public.messages(sender_profile_id);
comment on table public.messages is 'Mensajes individuales dentro de un chat de WhatsApp';

-- 1.3 RLS for WhatsApp tables
alter table public.chats enable row level security;
alter table public.messages enable row level security;

drop policy if exists "Users can view chats from their organization" on public.chats;
drop policy if exists "Users can insert chats for their organization" on public.chats;
drop policy if exists "Users can insert chats in their organization" on public.chats;
drop policy if exists "Users can update chats from their organization" on public.chats;
drop policy if exists "Users can update chats in their organization" on public.chats;

create policy "Users can view chats from their organization" on public.chats
  for select to authenticated
  using (
    organization_id in (
      select organization_id from public.user_profiles where id = auth.uid()
    )
  );

create policy "Users can insert chats in their organization" on public.chats
  for insert to authenticated
  with check (
    organization_id in (
      select organization_id from public.user_profiles where id = auth.uid()
    )
  );

create policy "Users can update chats in their organization" on public.chats
  for update to authenticated
  using (
    organization_id in (
      select organization_id from public.user_profiles where id = auth.uid()
    )
  );

drop policy if exists "Users can view messages from their organization's chats" on public.messages;
drop policy if exists "Users can view messages in their organization" on public.messages;
drop policy if exists "Users can insert messages for their organization's chats" on public.messages;
drop policy if exists "Users can insert messages in their organization" on public.messages;
drop policy if exists "Users can update messages in their organization" on public.messages;

create policy "Users can view messages in their organization" on public.messages
  for select to authenticated
  using (
    chat_id in (
      select c.id
      from public.chats c
      where c.organization_id in (
        select organization_id from public.user_profiles where id = auth.uid()
      )
    )
  );

create policy "Users can insert messages in their organization" on public.messages
  for insert to authenticated
  with check (
    chat_id in (
      select c.id
      from public.chats c
      where c.organization_id in (
        select organization_id from public.user_profiles where id = auth.uid()
      )
    )
  );

create policy "Users can update messages in their organization" on public.messages
  for update to authenticated
  using (
    chat_id in (
      select c.id
      from public.chats c
      where c.organization_id in (
        select organization_id from public.user_profiles where id = auth.uid()
      )
    )
  );

-- 2. Editable knowledge tables
create table if not exists public.school_schedules (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  level text not null,
  regular_entry_time time not null,
  regular_exit_time time not null,
  notes text,
  updated_at timestamptz not null default timezone('utc', now())
);
comment on table public.school_schedules is 'Horarios regulares por nivel educativo';
create index if not exists school_schedules_org_level_idx on public.school_schedules(organization_id, level);

alter table public.school_schedules enable row level security;
drop policy if exists "Users select school_schedules by org" on public.school_schedules;
drop policy if exists "Users insert school_schedules by org" on public.school_schedules;
drop policy if exists "Users update school_schedules by org" on public.school_schedules;
create policy "Users select school_schedules by org" on public.school_schedules
  for select to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = auth.uid()));
create policy "Users insert school_schedules by org" on public.school_schedules
  for insert to authenticated
  with check (organization_id in (select organization_id from public.user_profiles where id = auth.uid()));
create policy "Users update school_schedules by org" on public.school_schedules
  for update to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = auth.uid()));

create table if not exists public.special_schedules (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  level text not null,
  date date not null,
  entry_time time,
  exit_time time,
  reason text,
  updated_at timestamptz not null default timezone('utc', now())
);
comment on table public.special_schedules is 'Horarios especiales o excepciones por día';
create unique index if not exists special_schedules_org_level_date_key on public.special_schedules(organization_id, level, date);
create index if not exists special_schedules_org_level_idx on public.special_schedules(organization_id, level);

alter table public.special_schedules enable row level security;
drop policy if exists "Users select special_schedules by org" on public.special_schedules;
drop policy if exists "Users insert special_schedules by org" on public.special_schedules;
drop policy if exists "Users update special_schedules by org" on public.special_schedules;
create policy "Users select special_schedules by org" on public.special_schedules
  for select to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = auth.uid()));
create policy "Users insert special_schedules by org" on public.special_schedules
  for insert to authenticated
  with check (organization_id in (select organization_id from public.user_profiles where id = auth.uid()));
create policy "Users update special_schedules by org" on public.special_schedules
  for update to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = auth.uid()));

create table if not exists public.announcements (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  title text not null,
  body text not null,
  level text,
  topic text,
  valid_from date not null,
  valid_to date not null,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);
comment on table public.announcements is 'Avisos y comunicados para la comunidad escolar';
create index if not exists announcements_org_idx on public.announcements(organization_id);
create index if not exists announcements_topic_idx on public.announcements(topic);
create index if not exists announcements_valid_from_idx on public.announcements(valid_from);
create index if not exists announcements_valid_to_idx on public.announcements(valid_to);

alter table public.announcements enable row level security;
drop policy if exists "Users select announcements by org" on public.announcements;
drop policy if exists "Users insert announcements by org" on public.announcements;
drop policy if exists "Users update announcements by org" on public.announcements;
create policy "Users select announcements by org" on public.announcements
  for select to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = auth.uid()));
create policy "Users insert announcements by org" on public.announcements
  for insert to authenticated
  with check (organization_id in (select organization_id from public.user_profiles where id = auth.uid()));
create policy "Users update announcements by org" on public.announcements
  for update to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = auth.uid()));

create table if not exists public.directory_contacts (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  role_slug text not null,
  display_role text not null,
  name text not null,
  phone text,
  email text,
  notes text,
  is_active boolean not null default true,
  updated_at timestamptz not null default timezone('utc', now())
);
comment on table public.directory_contacts is 'Directorio interno de contactos clave para comunicación';
create unique index if not exists directory_contacts_org_role_slug_key on public.directory_contacts(organization_id, role_slug);
create index if not exists directory_contacts_org_idx on public.directory_contacts(organization_id);

alter table public.directory_contacts enable row level security;
drop policy if exists "Users select directory_contacts by org" on public.directory_contacts;
drop policy if exists "Users insert directory_contacts by org" on public.directory_contacts;
drop policy if exists "Users update directory_contacts by org" on public.directory_contacts;
create policy "Users select directory_contacts by org" on public.directory_contacts
  for select to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = auth.uid()));
create policy "Users insert directory_contacts by org" on public.directory_contacts
  for insert to authenticated
  with check (organization_id in (select organization_id from public.user_profiles where id = auth.uid()));
create policy "Users update directory_contacts by org" on public.directory_contacts
  for update to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = auth.uid()));

create table if not exists public.faqs (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  question text not null,
  answer text not null,
  tags text[],
  audience text,
  is_published boolean not null default true,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);
comment on table public.faqs is 'Base de conocimiento/FAQs para bots y atención';
create index if not exists faqs_org_idx on public.faqs(organization_id);
create index if not exists faqs_is_published_idx on public.faqs(is_published);
create index if not exists faqs_tags_gin_idx on public.faqs using gin(tags);

alter table public.faqs enable row level security;
drop policy if exists "Users select faqs by org" on public.faqs;
drop policy if exists "Users insert faqs by org" on public.faqs;
drop policy if exists "Users update faqs by org" on public.faqs;
create policy "Users select faqs by org" on public.faqs
  for select to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = auth.uid()));
create policy "Users insert faqs by org" on public.faqs
  for insert to authenticated
  with check (organization_id in (select organization_id from public.user_profiles where id = auth.uid()));
create policy "Users update faqs by org" on public.faqs
  for update to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = auth.uid()));

-- 3. CRM for bot
create table if not exists public.crm_contacts (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  first_name text,
  last_name text,
  full_name text not null,
  phone text,
  email text,
  whatsapp_wa_id text,
  notes text,
  source text,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);
comment on table public.crm_contacts is 'Personas/contactos en el CRM (padres, tutores, prospectos)';
create index if not exists crm_contacts_org_idx on public.crm_contacts(organization_id);
create index if not exists crm_contacts_whatsapp_wa_id_idx on public.crm_contacts(whatsapp_wa_id);

alter table public.crm_contacts enable row level security;
drop policy if exists "Users select crm_contacts by org" on public.crm_contacts;
drop policy if exists "Users insert crm_contacts by org" on public.crm_contacts;
drop policy if exists "Users update crm_contacts by org" on public.crm_contacts;
create policy "Users select crm_contacts by org" on public.crm_contacts
  for select to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = auth.uid()));
create policy "Users insert crm_contacts by org" on public.crm_contacts
  for insert to authenticated
  with check (organization_id in (select organization_id from public.user_profiles where id = auth.uid()));
create policy "Users update crm_contacts by org" on public.crm_contacts
  for update to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = auth.uid()));

-- Leads adjustments for bot CRM
alter table public.leads
  add column if not exists contact_id uuid references public.crm_contacts(id) on delete cascade,
  add column if not exists student_name text,
  add column if not exists grade_interest text,
  add column if not exists school_year text,
  add column if not exists campus text,
  add column if not exists wa_chat_id uuid references public.chats(id),
  add column if not exists wa_id text,
  add column if not exists metadata jsonb default '{}'::jsonb,
  alter column created_at set default timezone('utc', now()),
  alter column updated_at set default timezone('utc', now());

alter table public.leads alter column status drop default;
alter table public.leads alter column status type text using status::text;
alter table public.leads alter column status set default 'new';
alter table public.leads alter column status set not null;

alter table public.leads alter column source drop default;
alter table public.leads alter column source type text using source::text;
alter table public.leads alter column source set not null;

alter table public.leads alter column contact_id set not null;
alter table public.leads alter column student_name set not null;
alter table public.leads alter column grade_interest set not null;

create index if not exists leads_contact_id_idx on public.leads(contact_id);
create index if not exists leads_status_idx on public.leads(status);
create index if not exists leads_wa_chat_id_idx on public.leads(wa_chat_id);

alter table public.leads enable row level security;
drop policy if exists "Staff ve leads" on public.leads;
drop policy if exists "Users select leads by org" on public.leads;
drop policy if exists "Users insert leads by org" on public.leads;
drop policy if exists "Users update leads by org" on public.leads;
create policy "Users select leads by org" on public.leads
  for select to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = auth.uid()));
create policy "Users insert leads by org" on public.leads
  for insert to authenticated
  with check (organization_id in (select organization_id from public.user_profiles where id = auth.uid()));
create policy "Users update leads by org" on public.leads
  for update to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = auth.uid()));

create table if not exists public.availability_slots (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  starts_at timestamptz not null,
  ends_at timestamptz not null,
  campus text,
  max_appointments integer not null default 1,
  appointments_count integer not null default 0,
  is_active boolean not null default true,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);
comment on table public.availability_slots is 'Slots de disponibilidad para agendar citas de admisión';
create index if not exists availability_slots_org_idx on public.availability_slots(organization_id);
create index if not exists availability_slots_starts_at_idx on public.availability_slots(starts_at);
create index if not exists availability_slots_is_active_idx on public.availability_slots(is_active);

alter table public.availability_slots enable row level security;
drop policy if exists "Users select availability_slots by org" on public.availability_slots;
drop policy if exists "Users insert availability_slots by org" on public.availability_slots;
drop policy if exists "Users update availability_slots by org" on public.availability_slots;
create policy "Users select availability_slots by org" on public.availability_slots
  for select to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = auth.uid()));
create policy "Users insert availability_slots by org" on public.availability_slots
  for insert to authenticated
  with check (organization_id in (select organization_id from public.user_profiles where id = auth.uid()));
create policy "Users update availability_slots by org" on public.availability_slots
  for update to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = auth.uid()));

create table if not exists public.appointments (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  lead_id uuid not null references public.leads(id) on delete cascade,
  slot_id uuid references public.availability_slots(id),
  starts_at timestamptz not null,
  ends_at timestamptz,
  campus text,
  type text,
  status text not null default 'scheduled',
  created_by_profile_id uuid references public.user_profiles(id),
  notes text,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);
comment on table public.appointments is 'Citas de admisión programadas';
create index if not exists appointments_org_idx on public.appointments(organization_id);
create index if not exists appointments_lead_id_idx on public.appointments(lead_id);
create index if not exists appointments_status_idx on public.appointments(status);
create index if not exists appointments_starts_at_idx on public.appointments(starts_at);

alter table public.appointments enable row level security;
drop policy if exists "Users select appointments by org" on public.appointments;
drop policy if exists "Users insert appointments by org" on public.appointments;
drop policy if exists "Users update appointments by org" on public.appointments;
create policy "Users select appointments by org" on public.appointments
  for select to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = auth.uid()));
create policy "Users insert appointments by org" on public.appointments
  for insert to authenticated
  with check (organization_id in (select organization_id from public.user_profiles where id = auth.uid()));
create policy "Users update appointments by org" on public.appointments
  for update to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = auth.uid()));

-- 4. Realtime publication
do $$
begin
  if not exists (
    select 1 from pg_publication_tables where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'chats'
  ) then
    alter publication supabase_realtime add table public.chats;
  end if;
  if not exists (
    select 1 from pg_publication_tables where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'messages'
  ) then
    alter publication supabase_realtime add table public.messages;
  end if;
  if not exists (
    select 1 from pg_publication_tables where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'appointments'
  ) then
    alter publication supabase_realtime add table public.appointments;
  end if;
end
$$;
