-- Cambiar campus por escuela actual en leads
do $$
begin
  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public' and table_name = 'leads' and column_name = 'campus'
  ) then
    alter table public.leads rename column campus to current_school;
  end if;
end$$;
