-- Fix duplicate index from unique constraint on organizations.phone_number_id
drop index if exists public.organizations_phone_number_id_idx;

-- RLS performance: wrap auth.uid() with (select auth.uid()) in all policies

-- school_schedules
drop policy if exists "Users select school_schedules by org" on public.school_schedules;
create policy "Users select school_schedules by org" on public.school_schedules
  for select to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));

drop policy if exists "Users insert school_schedules by org" on public.school_schedules;
create policy "Users insert school_schedules by org" on public.school_schedules
  for insert to authenticated
  with check (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));

drop policy if exists "Users update school_schedules by org" on public.school_schedules;
create policy "Users update school_schedules by org" on public.school_schedules
  for update to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));

-- special_schedules
drop policy if exists "Users select special_schedules by org" on public.special_schedules;
create policy "Users select special_schedules by org" on public.special_schedules
  for select to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));

drop policy if exists "Users insert special_schedules by org" on public.special_schedules;
create policy "Users insert special_schedules by org" on public.special_schedules
  for insert to authenticated
  with check (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));

drop policy if exists "Users update special_schedules by org" on public.special_schedules;
create policy "Users update special_schedules by org" on public.special_schedules
  for update to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));

-- announcements
drop policy if exists "Users select announcements by org" on public.announcements;
create policy "Users select announcements by org" on public.announcements
  for select to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));

drop policy if exists "Users insert announcements by org" on public.announcements;
create policy "Users insert announcements by org" on public.announcements
  for insert to authenticated
  with check (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));

drop policy if exists "Users update announcements by org" on public.announcements;
create policy "Users update announcements by org" on public.announcements
  for update to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));

-- directory_contacts
drop policy if exists "Users select directory_contacts by org" on public.directory_contacts;
create policy "Users select directory_contacts by org" on public.directory_contacts
  for select to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));

drop policy if exists "Users insert directory_contacts by org" on public.directory_contacts;
create policy "Users insert directory_contacts by org" on public.directory_contacts
  for insert to authenticated
  with check (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));

drop policy if exists "Users update directory_contacts by org" on public.directory_contacts;
create policy "Users update directory_contacts by org" on public.directory_contacts
  for update to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));

-- faqs
drop policy if exists "Users select faqs by org" on public.faqs;
create policy "Users select faqs by org" on public.faqs
  for select to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));

drop policy if exists "Users insert faqs by org" on public.faqs;
create policy "Users insert faqs by org" on public.faqs
  for insert to authenticated
  with check (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));

drop policy if exists "Users update faqs by org" on public.faqs;
create policy "Users update faqs by org" on public.faqs
  for update to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));

-- crm_contacts
drop policy if exists "Users select crm_contacts by org" on public.crm_contacts;
create policy "Users select crm_contacts by org" on public.crm_contacts
  for select to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));

drop policy if exists "Users insert crm_contacts by org" on public.crm_contacts;
create policy "Users insert crm_contacts by org" on public.crm_contacts
  for insert to authenticated
  with check (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));

drop policy if exists "Users update crm_contacts by org" on public.crm_contacts;
create policy "Users update crm_contacts by org" on public.crm_contacts
  for update to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));

-- leads
drop policy if exists "Users select leads by org" on public.leads;
create policy "Users select leads by org" on public.leads
  for select to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));

drop policy if exists "Users insert leads by org" on public.leads;
create policy "Users insert leads by org" on public.leads
  for insert to authenticated
  with check (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));

drop policy if exists "Users update leads by org" on public.leads;
create policy "Users update leads by org" on public.leads
  for update to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));

-- availability_slots
drop policy if exists "Users select availability_slots by org" on public.availability_slots;
create policy "Users select availability_slots by org" on public.availability_slots
  for select to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));

drop policy if exists "Users insert availability_slots by org" on public.availability_slots;
create policy "Users insert availability_slots by org" on public.availability_slots
  for insert to authenticated
  with check (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));

drop policy if exists "Users update availability_slots by org" on public.availability_slots;
create policy "Users update availability_slots by org" on public.availability_slots
  for update to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));

-- appointments
drop policy if exists "Users select appointments by org" on public.appointments;
create policy "Users select appointments by org" on public.appointments
  for select to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));

drop policy if exists "Users insert appointments by org" on public.appointments;
create policy "Users insert appointments by org" on public.appointments
  for insert to authenticated
  with check (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));

drop policy if exists "Users update appointments by org" on public.appointments;
create policy "Users update appointments by org" on public.appointments
  for update to authenticated
  using (organization_id in (select organization_id from public.user_profiles where id = (select auth.uid())));

-- chats
drop policy if exists "Users can view chats from their organization" on public.chats;
create policy "Users can view chats from their organization" on public.chats
  for select to authenticated
  using (
    organization_id in (
      select organization_id from public.user_profiles where id = (select auth.uid())
    )
  );

drop policy if exists "Users can insert chats in their organization" on public.chats;
create policy "Users can insert chats in their organization" on public.chats
  for insert to authenticated
  with check (
    organization_id in (
      select organization_id from public.user_profiles where id = (select auth.uid())
    )
  );

drop policy if exists "Users can update chats in their organization" on public.chats;
create policy "Users can update chats in their organization" on public.chats
  for update to authenticated
  using (
    organization_id in (
      select organization_id from public.user_profiles where id = (select auth.uid())
    )
  );

-- messages
drop policy if exists "Users can view messages in their organization" on public.messages;
create policy "Users can view messages in their organization" on public.messages
  for select to authenticated
  using (
    chat_id in (
      select c.id
      from public.chats c
      where c.organization_id in (
        select organization_id from public.user_profiles where id = (select auth.uid())
      )
    )
  );

drop policy if exists "Users can insert messages in their organization" on public.messages;
create policy "Users can insert messages in their organization" on public.messages
  for insert to authenticated
  with check (
    chat_id in (
      select c.id
      from public.chats c
      where c.organization_id in (
        select organization_id from public.user_profiles where id = (select auth.uid())
      )
    )
  );

drop policy if exists "Users can update messages in their organization" on public.messages;
create policy "Users can update messages in their organization" on public.messages
  for update to authenticated
  using (
    chat_id in (
      select c.id
      from public.chats c
      where c.organization_id in (
        select organization_id from public.user_profiles where id = (select auth.uid())
      )
    )
  );
