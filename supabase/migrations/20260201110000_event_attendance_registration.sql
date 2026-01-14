alter table public.event_attendance
  add column if not exists status text not null default 'registered',
  add column if not exists registered_at timestamptz not null default timezone('utc'::text, now());
