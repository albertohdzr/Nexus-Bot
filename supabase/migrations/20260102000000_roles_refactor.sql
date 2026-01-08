-- Roles and permissions refactor: org-scoped roles + module permissions

create table if not exists public.roles (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid references public.organizations(id) on delete cascade,
  name text not null,
  slug text not null,
  description text,
  is_system boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists roles_org_slug_key on public.roles(organization_id, slug);
create unique index if not exists roles_global_slug_key on public.roles(slug)
  where organization_id is null;

alter table public.user_profiles
  add column if not exists role_id uuid references public.roles(id);

-- Drop role-based policies before altering role column type
drop policy if exists "Staff ve leads" on public.leads;
drop policy if exists "Solo staff autorizado ve chats" on public.chat_sessions;
drop policy if exists "Access admission applications" on public.admission_applications;
drop policy if exists "Read payments" on public.payments;
drop policy if exists "Admin insert payments" on public.payments;
drop policy if exists "Admin update payments" on public.payments;
drop policy if exists "Admin delete payments" on public.payments;
drop policy if exists "Read families" on public.student_families;
drop policy if exists "Staff insert families" on public.student_families;
drop policy if exists "Staff update families" on public.student_families;
drop policy if exists "Staff delete families" on public.student_families;
drop policy if exists "Access admission documents" on public.admission_documents;
drop policy if exists "Ver ciclos activos" on public.admission_cycles;
drop policy if exists "Admin insert cycles" on public.admission_cycles;
drop policy if exists "Admin update cycles" on public.admission_cycles;
drop policy if exists "Admin delete cycles" on public.admission_cycles;
drop policy if exists "Staff ve tareas" on public.tasks;
drop policy if exists "Staff ve actividades" on public.lead_activities;
drop policy if exists "Staff ve mappings" on public.social_mappings;
drop policy if exists "Admins can update their organization" on public.organizations;

alter table public.user_profiles
  alter column role drop default,
  alter column role type text using role::text,
  alter column role set default 'parent';

do $$
begin
  if exists (
    select 1
    from information_schema.tables
    where table_schema = 'public'
      and table_name = 'role_permissions'
  ) then
    alter table public.role_permissions rename to role_permissions_legacy;
  end if;
end $$;

create table if not exists public.role_permissions (
  id uuid primary key default gen_random_uuid(),
  role_id uuid not null references public.roles(id) on delete cascade,
  module text not null,
  permissions jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (role_id, module)
);

create or replace function public.is_superadmin(user_id uuid)
returns boolean as $$
declare
  role_slug text;
begin
  select coalesce(r.slug, up.role::text)
    into role_slug
  from public.user_profiles up
  left join public.roles r on r.id = up.role_id
  where up.id = user_id;

  return role_slug = 'superadmin';
end;
$$ language plpgsql security definer set search_path = public, extensions;

create or replace function public.check_permission(user_id uuid, req_module text, req_action text)
returns boolean as $$
declare
  user_role_id uuid;
  user_role_slug text;
  has_perm boolean;
begin
  select up.role_id,
         coalesce(r.slug, up.role::text)
    into user_role_id, user_role_slug
  from public.user_profiles up
  left join public.roles r on r.id = up.role_id
  where up.id = user_id;

  if user_role_slug in ('superadmin', 'org_admin') then
    return true;
  end if;

  select (rp.permissions->>req_action)::boolean
    into has_perm
  from public.role_permissions rp
  where rp.role_id = user_role_id
    and rp.module = req_module;

  if has_perm is null then
    select (rp.permissions->>req_action)::boolean
      into has_perm
    from public.roles r
    join public.role_permissions rp on rp.role_id = r.id
    where r.organization_id is null
      and r.slug = user_role_slug
      and rp.module = req_module;
  end if;

  return coalesce(has_perm, false);
end;
$$ language plpgsql security definer set search_path = public, extensions;

-- Seed global system roles from enum values
insert into public.roles (organization_id, name, slug, is_system)
select
  null,
  initcap(replace(role_value::text, '_', ' ')),
  role_value::text,
  true
from unnest(enum_range(null::public.system_role)) as role_value
on conflict (slug) where organization_id is null do nothing;

-- Seed org roles from existing profiles
insert into public.roles (organization_id, name, slug, is_system)
select distinct
  up.organization_id,
  initcap(replace(up.role::text, '_', ' ')),
  up.role::text,
  true
from public.user_profiles up
where up.organization_id is not null
on conflict (organization_id, slug) do nothing;

-- Backfill role_id on profiles (prefer global superadmin)
update public.user_profiles up
set role_id = r.id
from public.roles r
where r.organization_id is null
  and r.slug = 'superadmin'
  and up.role = 'superadmin';

update public.user_profiles up
set role_id = r.id
from public.roles r
where r.organization_id is not distinct from up.organization_id
  and r.slug = up.role::text
  and up.role_id is null;

do $$
begin
  if exists (
    select 1
    from information_schema.tables
    where table_schema = 'public'
      and table_name = 'role_permissions_legacy'
  ) then
    insert into public.role_permissions (role_id, module, permissions)
    select r.id, rp.module, rp.permissions
    from public.role_permissions_legacy rp
    join public.roles r
      on r.slug = rp.role::text
     and r.organization_id is not distinct from rp.organization_id
    on conflict (role_id, module) do nothing;
  end if;
end $$;

-- Seed default module access + management permissions
with permission_seed as (
  select 'org_admin'::text as slug, 'crm'::text as module,
    '{"access": true, "manage_appointments": true, "manage_templates": true, "manage_whatsapp_templates": true}'::jsonb as perms
  union all
  select 'org_admin', 'admissions', '{"access": true}'::jsonb
  union all
  select 'org_admin', 'finance', '{"access": true}'::jsonb
  union all
  select 'org_admin', 'erp', '{"access": true}'::jsonb
  union all
  select 'org_admin', 'ai_audit', '{"access": true}'::jsonb
  union all
  select 'org_admin', 'settings',
    '{"access": true, "manage_org": true, "manage_team": true, "manage_roles": true, "manage_directory": true, "manage_bot": true}'::jsonb
  union all
  select 'director', 'crm', '{"access": true, "manage_appointments": true}'::jsonb
  union all
  select 'director', 'admissions', '{"access": true}'::jsonb
  union all
  select 'director', 'erp', '{"access": true}'::jsonb
  union all
  select 'director', 'settings', '{"access": false, "manage_directory": true, "manage_bot": true}'::jsonb
  union all
  select 'admissions', 'crm', '{"access": true, "manage_appointments": true}'::jsonb
  union all
  select 'admissions', 'admissions', '{"access": true}'::jsonb
  union all
  select 'admissions', 'settings', '{"access": false, "manage_directory": true, "manage_bot": true}'::jsonb
  union all
  select 'finance', 'finance', '{"access": true}'::jsonb
  union all
  select 'teacher', 'erp', '{"access": true}'::jsonb
  union all
  select 'staff', 'erp', '{"access": true}'::jsonb
  union all
  select 'superadmin', 'superadmin', '{"access": true}'::jsonb
)
insert into public.role_permissions (role_id, module, permissions)
select r.id, seed.module, seed.perms
from public.roles r
join permission_seed seed on seed.slug = r.slug
on conflict (role_id, module) do nothing;

create or replace function public.seed_org_roles(p_org_id uuid)
returns void as $$
begin
  insert into public.roles (organization_id, name, slug, description, is_system)
  select p_org_id, r.name, r.slug, r.description, true
  from public.roles r
  where r.organization_id is null
    and r.slug <> 'superadmin'
  on conflict (organization_id, slug) do nothing;

  insert into public.role_permissions (role_id, module, permissions)
  select r_org.id, rp.module, rp.permissions
  from public.roles r_org
  join public.roles r_global
    on r_global.organization_id is null
   and r_global.slug = r_org.slug
  join public.role_permissions rp on rp.role_id = r_global.id
  where r_org.organization_id = p_org_id
  on conflict (role_id, module) do nothing;
end;
$$ language plpgsql security definer set search_path = public, extensions;

select public.seed_org_roles(id) from public.organizations;

-- Enable RLS for new tables
alter table public.roles enable row level security;
alter table public.role_permissions enable row level security;

drop policy if exists "Ver permisos" on public.role_permissions;
drop policy if exists "Superadmin insert permissions" on public.role_permissions;
drop policy if exists "Superadmin update permissions" on public.role_permissions;
drop policy if exists "Superadmin delete permissions" on public.role_permissions;

create policy "View roles by org" on public.roles
  for select to authenticated
  using (
    public.is_superadmin((select auth.uid()))
    or organization_id is null
    or organization_id in (
      select organization_id from public.user_profiles where id = (select auth.uid())
    )
  );

create policy "Manage roles by org admins" on public.roles
  for all to authenticated
  using (
    public.check_permission((select auth.uid()), 'settings', 'manage_roles')
    and organization_id in (
      select organization_id from public.user_profiles where id = (select auth.uid())
    )
  )
  with check (
    organization_id in (
      select organization_id from public.user_profiles where id = (select auth.uid())
    )
  );

create policy "View permissions by org" on public.role_permissions
  for select to authenticated
  using (
    public.is_superadmin((select auth.uid()))
    or role_id in (
      select r.id
      from public.roles r
      where r.organization_id in (
        select organization_id from public.user_profiles where id = (select auth.uid())
      )
    )
  );

create policy "Manage permissions by org admins" on public.role_permissions
  for all to authenticated
  using (
    public.check_permission((select auth.uid()), 'settings', 'manage_roles')
    and role_id in (
      select r.id
      from public.roles r
      where r.organization_id in (
        select organization_id from public.user_profiles where id = (select auth.uid())
      )
    )
  )
  with check (
    role_id in (
      select r.id
      from public.roles r
      where r.organization_id in (
        select organization_id from public.user_profiles where id = (select auth.uid())
      )
    )
  );

drop policy if exists "Editar mi propio perfil" on public.user_profiles;

create policy "Update own profile" on public.user_profiles
  for update to authenticated
  using (id = (select auth.uid()));

create policy "Org admins insert profiles" on public.user_profiles
  for insert to authenticated
  with check (
    public.check_permission((select auth.uid()), 'settings', 'manage_team')
    and organization_id in (
      select organization_id from public.user_profiles where id = (select auth.uid())
    )
  );

create policy "Org admins update profiles" on public.user_profiles
  for update to authenticated
  using (
    public.check_permission((select auth.uid()), 'settings', 'manage_team')
    and organization_id in (
      select organization_id from public.user_profiles where id = (select auth.uid())
    )
  );

-- Permission-based access for core modules (allows custom roles)
create policy "Permissions access leads" on public.leads
  for all to authenticated
  using (
    organization_id in (select organization_id from public.user_profiles where id = (select auth.uid()))
    and public.check_permission((select auth.uid()), 'crm', 'access')
  )
  with check (
    organization_id in (select organization_id from public.user_profiles where id = (select auth.uid()))
    and public.check_permission((select auth.uid()), 'crm', 'access')
  );

create policy "Permissions access lead activities" on public.lead_activities
  for all to authenticated
  using (
    organization_id in (select organization_id from public.user_profiles where id = (select auth.uid()))
    and public.check_permission((select auth.uid()), 'crm', 'access')
  )
  with check (
    organization_id in (select organization_id from public.user_profiles where id = (select auth.uid()))
    and public.check_permission((select auth.uid()), 'crm', 'access')
  );

create policy "Permissions access tasks" on public.tasks
  for all to authenticated
  using (
    organization_id in (select organization_id from public.user_profiles where id = (select auth.uid()))
    and public.check_permission((select auth.uid()), 'crm', 'access')
  )
  with check (
    organization_id in (select organization_id from public.user_profiles where id = (select auth.uid()))
    and public.check_permission((select auth.uid()), 'crm', 'access')
  );

create policy "Permissions access chat sessions" on public.chat_sessions
  for all to authenticated
  using (
    organization_id in (select organization_id from public.user_profiles where id = (select auth.uid()))
    and public.check_permission((select auth.uid()), 'crm', 'access')
  )
  with check (
    organization_id in (select organization_id from public.user_profiles where id = (select auth.uid()))
    and public.check_permission((select auth.uid()), 'crm', 'access')
  );

create policy "Permissions access social mappings" on public.social_mappings
  for all to authenticated
  using (
    organization_id in (select organization_id from public.user_profiles where id = (select auth.uid()))
    and public.check_permission((select auth.uid()), 'crm', 'access')
  )
  with check (
    organization_id in (select organization_id from public.user_profiles where id = (select auth.uid()))
    and public.check_permission((select auth.uid()), 'crm', 'access')
  );

create policy "Permissions access admissions applications" on public.admission_applications
  for all to authenticated
  using (
    organization_id in (select organization_id from public.user_profiles where id = (select auth.uid()))
    and public.check_permission((select auth.uid()), 'admissions', 'access')
  )
  with check (
    organization_id in (select organization_id from public.user_profiles where id = (select auth.uid()))
    and public.check_permission((select auth.uid()), 'admissions', 'access')
  );

create policy "Permissions access admission cycles" on public.admission_cycles
  for all to authenticated
  using (
    organization_id in (select organization_id from public.user_profiles where id = (select auth.uid()))
    and public.check_permission((select auth.uid()), 'admissions', 'access')
  )
  with check (
    organization_id in (select organization_id from public.user_profiles where id = (select auth.uid()))
    and public.check_permission((select auth.uid()), 'admissions', 'access')
  );

create policy "Permissions access payments" on public.payments
  for all to authenticated
  using (
    organization_id in (select organization_id from public.user_profiles where id = (select auth.uid()))
    and public.check_permission((select auth.uid()), 'finance', 'access')
  )
  with check (
    organization_id in (select organization_id from public.user_profiles where id = (select auth.uid()))
    and public.check_permission((select auth.uid()), 'finance', 'access')
  );

create policy "Permissions access students" on public.students
  for all to authenticated
  using (
    organization_id in (select organization_id from public.user_profiles where id = (select auth.uid()))
    and public.check_permission((select auth.uid()), 'erp', 'access')
  )
  with check (
    organization_id in (select organization_id from public.user_profiles where id = (select auth.uid()))
    and public.check_permission((select auth.uid()), 'erp', 'access')
  );

create policy "Permissions access student families" on public.student_families
  for all to authenticated
  using (
    organization_id in (select organization_id from public.user_profiles where id = (select auth.uid()))
    and public.check_permission((select auth.uid()), 'erp', 'access')
  )
  with check (
    organization_id in (select organization_id from public.user_profiles where id = (select auth.uid()))
    and public.check_permission((select auth.uid()), 'erp', 'access')
  );

create policy "Permissions update organizations" on public.organizations
  for update to authenticated
  using (
    public.check_permission((select auth.uid()), 'settings', 'manage_org')
    and id in (select organization_id from public.user_profiles where id = (select auth.uid()))
  );
