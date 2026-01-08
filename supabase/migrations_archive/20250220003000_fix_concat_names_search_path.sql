-- Ensure concat_names_mx has immutable search_path for security
create or replace function public.concat_names_mx(first_name text, middle_name text, last_name_paternal text, last_name_maternal text)
returns text
language sql
immutable
set search_path = public, pg_temp
as $$
select trim(both ' ' from
  (case when coalesce(first_name, '') <> '' then coalesce(first_name, '') || ' ' else '' end) ||
  (case when coalesce(middle_name, '') <> '' then coalesce(middle_name, '') || ' ' else '' end) ||
  (case when coalesce(last_name_paternal, '') <> '' then coalesce(last_name_paternal, '') || ' ' else '' end) ||
  coalesce(last_name_maternal, '')
);
$$;
