alter table public.leads
  add column if not exists decision_maker_name text,
  add column if not exists decision_maker_role text,
  add column if not exists decision_date date,
  add column if not exists budget_range text,
  add column if not exists visit_notes text,
  add column if not exists next_steps text;

create index if not exists leads_decision_date_idx on public.leads(decision_date);
