alter table public.leads
  add column if not exists division text,
  add column if not exists address_street text,
  add column if not exists address_number text,
  add column if not exists address_neighborhood text,
  add column if not exists address_postal_code text,
  add column if not exists address_city text,
  add column if not exists address_state text,
  add column if not exists address_country text,
  add column if not exists nationality text,
  add column if not exists native_language text,
  add column if not exists secondary_language text;

create index if not exists leads_division_idx on public.leads(division);
