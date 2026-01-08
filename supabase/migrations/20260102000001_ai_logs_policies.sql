create policy "Users select ai_logs by org"
on public.ai_logs
for select
to authenticated
using (
  organization_id in (
    select organization_id
    from public.user_profiles
    where id = auth.uid()
  )
);
