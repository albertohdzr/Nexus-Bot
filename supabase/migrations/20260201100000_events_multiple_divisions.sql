-- Allow events to target multiple divisions

alter table public.events
  add column if not exists divisions text[];

update public.events
set divisions = array[division]
where divisions is null
  and division is not null;

alter table public.events
  drop constraint if exists events_division_check;

alter table public.events
  drop column if exists division;

alter table public.events
  alter column divisions set not null;

alter table public.events
  add constraint events_divisions_check
  check (
    array_length(divisions, 1) > 0
    and divisions <@ array[
      'prenursery'::text,
      'early_child'::text,
      'elementary'::text,
      'middle_school'::text,
      'high_school'::text
    ]
  );

drop index if exists public.events_division_idx;

create index if not exists events_divisions_idx
  on public.events using gin (divisions);
