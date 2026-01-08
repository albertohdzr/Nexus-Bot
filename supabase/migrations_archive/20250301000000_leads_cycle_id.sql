-- Add explicit admission cycle relation to leads

alter table public.leads
  add column if not exists cycle_id uuid references public.admission_cycles(id) on delete set null;

create index if not exists leads_cycle_id_idx on public.leads(cycle_id);
