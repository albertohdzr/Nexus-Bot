-- Events module: tables, policies, and storage bucket

create table if not exists public.events (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  name text not null,
  description text,
  division text not null,
  starts_at timestamptz not null,
  ends_at timestamptz,
  requires_registration boolean not null default false,
  created_by_profile_id uuid references public.user_profiles(id),
  created_at timestamptz not null default timezone('utc'::text, now()),
  updated_at timestamptz not null default timezone('utc'::text, now()),
  constraint events_division_check check (
    division = any (array['prenursery'::text, 'early_child'::text, 'elementary'::text, 'middle_school'::text, 'high_school'::text])
  ),
  constraint events_time_check check (ends_at is null or ends_at > starts_at)
);

create index if not exists events_org_idx on public.events (organization_id);
create index if not exists events_starts_at_idx on public.events (starts_at);
create index if not exists events_division_idx on public.events (division);

create table if not exists public.event_documents (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  event_id uuid not null references public.events(id) on delete cascade,
  document_type text not null,
  file_path text not null,
  file_name text not null,
  mime_type text not null,
  storage_bucket text not null default 'events-documents'::text,
  created_by_profile_id uuid references public.user_profiles(id),
  created_at timestamptz not null default timezone('utc'::text, now())
);

create index if not exists event_documents_event_idx on public.event_documents (event_id);
create index if not exists event_documents_org_idx on public.event_documents (organization_id);

create table if not exists public.event_attendance (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  event_id uuid not null references public.events(id) on delete cascade,
  lead_id uuid not null references public.leads(id) on delete cascade,
  attended_at timestamptz not null default timezone('utc'::text, now()),
  created_at timestamptz not null default timezone('utc'::text, now()),
  unique (event_id, lead_id)
);

create index if not exists event_attendance_event_idx on public.event_attendance (event_id);
create index if not exists event_attendance_lead_idx on public.event_attendance (lead_id);
create index if not exists event_attendance_org_idx on public.event_attendance (organization_id);

alter table public.events enable row level security;
alter table public.event_documents enable row level security;
alter table public.event_attendance enable row level security;

create policy "Permissions access events" on public.events
  for all to authenticated
  using (
    organization_id in (select organization_id from public.user_profiles where id = (select auth.uid()))
    and public.check_permission((select auth.uid()), 'events', 'access')
  )
  with check (
    organization_id in (select organization_id from public.user_profiles where id = (select auth.uid()))
    and public.check_permission((select auth.uid()), 'events', 'access')
  );

create policy "Permissions access event documents" on public.event_documents
  for all to authenticated
  using (
    organization_id in (select organization_id from public.user_profiles where id = (select auth.uid()))
    and public.check_permission((select auth.uid()), 'events', 'access')
  )
  with check (
    organization_id in (select organization_id from public.user_profiles where id = (select auth.uid()))
    and public.check_permission((select auth.uid()), 'events', 'access')
  );

create policy "Permissions access event attendance" on public.event_attendance
  for all to authenticated
  using (
    organization_id in (select organization_id from public.user_profiles where id = (select auth.uid()))
    and public.check_permission((select auth.uid()), 'events', 'access')
  )
  with check (
    organization_id in (select organization_id from public.user_profiles where id = (select auth.uid()))
    and public.check_permission((select auth.uid()), 'events', 'access')
  );

insert into storage.buckets (id, name, public)
values ('events-documents', 'events-documents', false)
on conflict (id) do nothing;

create policy "Events documents read by org" on storage.objects
  for select to authenticated
  using (
    bucket_id = 'events-documents'
    and (split_part(name, '/', 2))::uuid in (
      select organization_id from public.user_profiles where id = (select auth.uid())
    )
  );

create policy "Events documents insert by org" on storage.objects
  for insert to authenticated
  with check (
    bucket_id = 'events-documents'
    and (split_part(name, '/', 2))::uuid in (
      select organization_id from public.user_profiles where id = (select auth.uid())
    )
  );

create policy "Events documents update by org" on storage.objects
  for update to authenticated
  using (
    bucket_id = 'events-documents'
    and (split_part(name, '/', 2))::uuid in (
      select organization_id from public.user_profiles where id = (select auth.uid())
    )
  )
  with check (
    bucket_id = 'events-documents'
    and (split_part(name, '/', 2))::uuid in (
      select organization_id from public.user_profiles where id = (select auth.uid())
    )
  );

create policy "Events documents delete by org" on storage.objects
  for delete to authenticated
  using (
    bucket_id = 'events-documents'
    and (split_part(name, '/', 2))::uuid in (
      select organization_id from public.user_profiles where id = (select auth.uid())
    )
  );

insert into public.role_permissions (role_id, module, permissions)
select r.id, 'events', '{"access": true}'::jsonb
from public.roles r
where r.slug in ('org_admin', 'director', 'admissions')
on conflict (role_id, module) do nothing;
