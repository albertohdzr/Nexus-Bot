create table if not exists public.admission_requirement_documents (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  division text not null,
  title text,
  file_path text not null,
  file_name text not null,
  mime_type text not null default 'application/pdf',
  storage_bucket text not null default 'whatsapp-media',
  is_active boolean not null default true,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint admission_requirement_documents_division_check check (
    division in ('prenursery', 'early_child', 'elementary', 'middle_school', 'high_school')
  )
);

create index if not exists admission_requirement_documents_org_idx
  on public.admission_requirement_documents(organization_id);
create index if not exists admission_requirement_documents_division_idx
  on public.admission_requirement_documents(division);

alter table public.admission_requirement_documents enable row level security;

drop policy if exists "Users select admission_requirement_documents by org"
  on public.admission_requirement_documents;
create policy "Users select admission_requirement_documents by org"
  on public.admission_requirement_documents
  for select to authenticated
  using (
    organization_id in (
      select organization_id from public.user_profiles where id = auth.uid()
    )
  );

drop policy if exists "Users insert admission_requirement_documents by org"
  on public.admission_requirement_documents;
create policy "Users insert admission_requirement_documents by org"
  on public.admission_requirement_documents
  for insert to authenticated
  with check (
    organization_id in (
      select organization_id from public.user_profiles where id = auth.uid()
    )
  );

drop policy if exists "Users update admission_requirement_documents by org"
  on public.admission_requirement_documents;
create policy "Users update admission_requirement_documents by org"
  on public.admission_requirement_documents
  for update to authenticated
  using (
    organization_id in (
      select organization_id from public.user_profiles where id = auth.uid()
    )
  );
