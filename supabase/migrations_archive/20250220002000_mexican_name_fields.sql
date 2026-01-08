-- Ajustes de nombres conforme formato MX: primer nombre, segundo nombre (opcional), apellido paterno, apellido materno.

-- Función auxiliar inmutable para nombres completos sin dobles espacios
create or replace function public.concat_names_mx(first_name text, middle_name text, last_name_paternal text, last_name_maternal text)
returns text
language sql
immutable
as $$
select trim(both ' ' from
  (case when coalesce(first_name, '') <> '' then coalesce(first_name, '') || ' ' else '' end) ||
  (case when coalesce(middle_name, '') <> '' then coalesce(middle_name, '') || ' ' else '' end) ||
  (case when coalesce(last_name_paternal, '') <> '' then coalesce(last_name_paternal, '') || ' ' else '' end) ||
  coalesce(last_name_maternal, '')
);
$$;

-- user_profiles: renombrar y añadir columnas, regenerar full_name
do $$
begin
  if exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'user_profiles' and column_name = 'full_name'
  ) then
    alter table public.user_profiles drop column full_name;
  end if;

  if exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'user_profiles' and column_name = 'last_name'
  ) then
    alter table public.user_profiles rename column last_name to last_name_paternal;
  end if;
end$$;

alter table public.user_profiles
  add column if not exists middle_name text,
  add column if not exists last_name_maternal text;

alter table public.user_profiles drop column if exists full_name;
alter table public.user_profiles
  add column full_name text generated always as (
    public.concat_names_mx(first_name, middle_name, last_name_paternal, last_name_maternal)
  ) stored;

-- crm_contacts: renombrar y añadir columnas, regenerar full_name
do $$
begin
  if exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'crm_contacts' and column_name = 'full_name'
  ) then
    alter table public.crm_contacts drop column full_name;
  end if;

  if exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'crm_contacts' and column_name = 'last_name'
  ) then
    alter table public.crm_contacts rename column last_name to last_name_paternal;
  end if;
end$$;

alter table public.crm_contacts
  add column if not exists middle_name text,
  add column if not exists last_name_maternal text;

alter table public.crm_contacts drop column if exists full_name;
alter table public.crm_contacts
  add column full_name text generated always as (
    public.concat_names_mx(first_name, middle_name, last_name_paternal, last_name_maternal)
  ) stored;

-- leads: separar nombres de estudiante y contacto
do $$
begin
  if exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'leads' and column_name = 'student_last_name'
  ) then
    alter table public.leads rename column student_last_name to student_last_name_paternal;
  end if;
end$$;

alter table public.leads
  add column if not exists student_middle_name text,
  add column if not exists student_last_name_maternal text;

alter table public.leads drop column if exists student_name;
alter table public.leads
  add column student_name text generated always as (
    public.concat_names_mx(student_first_name, student_middle_name, student_last_name_paternal, student_last_name_maternal)
  ) stored;

-- Contacto del lead en formato MX
alter table public.leads
  add column if not exists contact_first_name text,
  add column if not exists contact_middle_name text,
  add column if not exists contact_last_name_paternal text,
  add column if not exists contact_last_name_maternal text;

alter table public.leads alter column contact_name drop not null;

alter table public.leads drop column if exists contact_full_name;
alter table public.leads
  add column contact_full_name text generated always as (
    public.concat_names_mx(contact_first_name, contact_middle_name, contact_last_name_paternal, contact_last_name_maternal)
  ) stored;

-- students: nombres en formato MX
do $$
begin
  if exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'students' and column_name = 'last_name'
  ) then
    alter table public.students rename column last_name to last_name_paternal;
  end if;
end$$;

alter table public.students
  add column if not exists middle_name text,
  add column if not exists last_name_maternal text;

alter table public.students drop column if exists full_name;
alter table public.students
  add column full_name text generated always as (
    public.concat_names_mx(first_name, middle_name, last_name_paternal, last_name_maternal)
  ) stored;
