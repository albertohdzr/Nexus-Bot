create or replace function public.can_manage_appointments_for_org(p_org_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select
    coalesce(
      nullif(current_setting('request.jwt.claim.role', true), ''),
      nullif((nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'role'), ''),
      ''
    ) = 'service_role'
    or exists (
      select 1
      from public.user_profiles up
      where up.id = auth.uid()
        and up.organization_id = p_org_id
        and public.check_permission(up.id, 'crm', 'manage_appointments')
    );
$$;

create or replace function public.book_admission_appointment(
  p_org_id uuid,
  p_lead_id uuid,
  p_slot_id uuid,
  p_notes text default null,
  p_type text default 'Campus visit',
  p_created_by_profile_id uuid default null
)
returns table(
  success boolean,
  message text,
  appointment_id uuid,
  starts_at timestamptz,
  ends_at timestamptz
)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_slot public.availability_slots%rowtype;
  v_lead_id uuid;
  v_existing_id uuid;
  v_count integer;
  v_appointment_id uuid;
begin
  if not public.can_manage_appointments_for_org(p_org_id) then
    return query select false, 'No autorizado para administrar citas.'::text, null::uuid, null::timestamptz, null::timestamptz;
    return;
  end if;

  select l.id
    into v_lead_id
  from public.leads l
  where l.id = p_lead_id
    and l.organization_id = p_org_id;

  if v_lead_id is null then
    return query select false, 'No se encontró el lead para esta organización.'::text, null::uuid, null::timestamptz, null::timestamptz;
    return;
  end if;

  select a.id
    into v_existing_id
  from public.appointments a
  where a.organization_id = p_org_id
    and a.lead_id = p_lead_id
    and a.status = 'scheduled'
  order by a.starts_at asc
  limit 1;

  if v_existing_id is not null then
    return query select false, 'Este lead ya tiene una cita programada. Cancela o reagenda la cita existente antes de crear otra.'::text, v_existing_id, null::timestamptz, null::timestamptz;
    return;
  end if;

  select *
    into v_slot
  from public.availability_slots
  where id = p_slot_id
    and organization_id = p_org_id
  for update;

  if not found then
    return query select false, 'El horario seleccionado no existe.'::text, null::uuid, null::timestamptz, null::timestamptz;
    return;
  end if;

  if not v_slot.is_active or v_slot.is_blocked then
    return query select false, 'El horario seleccionado ya no está disponible.'::text, null::uuid, v_slot.starts_at, v_slot.ends_at;
    return;
  end if;

  if v_slot.starts_at <= now() then
    return query select false, 'El horario seleccionado ya pasó.'::text, null::uuid, v_slot.starts_at, v_slot.ends_at;
    return;
  end if;

  select count(*)::integer
    into v_count
  from public.appointments a
  where a.slot_id = p_slot_id
    and a.status = 'scheduled';

  if v_count >= v_slot.max_appointments then
    update public.availability_slots
       set appointments_count = v_count,
           updated_at = timezone('utc'::text, now())
     where id = p_slot_id;

    return query select false, 'El horario seleccionado ya está lleno.'::text, null::uuid, v_slot.starts_at, v_slot.ends_at;
    return;
  end if;

  insert into public.appointments (
    organization_id,
    lead_id,
    slot_id,
    starts_at,
    ends_at,
    campus,
    type,
    status,
    created_by_profile_id,
    notes
  )
  values (
    p_org_id,
    p_lead_id,
    p_slot_id,
    v_slot.starts_at,
    v_slot.ends_at,
    v_slot.campus,
    coalesce(nullif(p_type, ''), 'Campus visit'),
    'scheduled',
    p_created_by_profile_id,
    coalesce(nullif(p_notes, ''), 'Agendado via WhatsApp Bot')
  )
  returning id into v_appointment_id;

  update public.availability_slots
     set appointments_count = v_count + 1,
         updated_at = timezone('utc'::text, now())
   where id = p_slot_id;

  update public.leads
     set status = 'visit_scheduled',
         updated_at = timezone('utc'::text, now())
   where id = p_lead_id
     and organization_id = p_org_id;

  return query select true, 'Cita agendada exitosamente.'::text, v_appointment_id, v_slot.starts_at, v_slot.ends_at;
end;
$$;

create or replace function public.reschedule_admission_appointment(
  p_org_id uuid,
  p_appointment_id uuid,
  p_new_slot_id uuid,
  p_notes text default null,
  p_type text default null
)
returns table(
  success boolean,
  message text,
  appointment_id uuid,
  starts_at timestamptz,
  ends_at timestamptz
)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_appt public.appointments%rowtype;
  v_new_slot public.availability_slots%rowtype;
  v_new_count integer;
  v_old_count integer;
begin
  if not public.can_manage_appointments_for_org(p_org_id) then
    return query select false, 'No autorizado para administrar citas.'::text, null::uuid, null::timestamptz, null::timestamptz;
    return;
  end if;

  select *
    into v_appt
  from public.appointments
  where id = p_appointment_id
    and organization_id = p_org_id
  for update;

  if not found then
    return query select false, 'No se encontró la cita.'::text, null::uuid, null::timestamptz, null::timestamptz;
    return;
  end if;

  if v_appt.status = 'cancelled' then
    return query select false, 'No se puede reagendar una cita cancelada.'::text, v_appt.id, v_appt.starts_at, v_appt.ends_at;
    return;
  end if;

  select *
    into v_new_slot
  from public.availability_slots
  where id = p_new_slot_id
    and organization_id = p_org_id
  for update;

  if not found then
    return query select false, 'El nuevo horario no existe.'::text, v_appt.id, v_appt.starts_at, v_appt.ends_at;
    return;
  end if;

  if not v_new_slot.is_active or v_new_slot.is_blocked then
    return query select false, 'El nuevo horario ya no está disponible.'::text, v_appt.id, v_new_slot.starts_at, v_new_slot.ends_at;
    return;
  end if;

  if v_new_slot.starts_at <= now() then
    return query select false, 'El nuevo horario ya pasó.'::text, v_appt.id, v_new_slot.starts_at, v_new_slot.ends_at;
    return;
  end if;

  if v_appt.slot_id is distinct from p_new_slot_id then
    select count(*)::integer
      into v_new_count
    from public.appointments a
    where a.slot_id = p_new_slot_id
      and a.status = 'scheduled';

    if v_new_count >= v_new_slot.max_appointments then
      update public.availability_slots
         set appointments_count = v_new_count,
             updated_at = timezone('utc'::text, now())
       where id = p_new_slot_id;

      return query select false, 'El nuevo horario ya está lleno.'::text, v_appt.id, v_new_slot.starts_at, v_new_slot.ends_at;
      return;
    end if;
  end if;

  update public.appointments
     set slot_id = p_new_slot_id,
         starts_at = v_new_slot.starts_at,
         ends_at = v_new_slot.ends_at,
         campus = v_new_slot.campus,
         type = coalesce(nullif(p_type, ''), v_appt.type),
         notes = coalesce(p_notes, v_appt.notes),
         updated_at = timezone('utc'::text, now())
   where id = p_appointment_id;

  if v_appt.slot_id is distinct from p_new_slot_id then
    if v_appt.slot_id is not null then
      select count(*)::integer
        into v_old_count
      from public.appointments a
      where a.slot_id = v_appt.slot_id
        and a.status = 'scheduled';

      update public.availability_slots
         set appointments_count = v_old_count,
             updated_at = timezone('utc'::text, now())
       where id = v_appt.slot_id;
    end if;

    select count(*)::integer
      into v_new_count
    from public.appointments a
    where a.slot_id = p_new_slot_id
      and a.status = 'scheduled';

    update public.availability_slots
       set appointments_count = v_new_count,
           updated_at = timezone('utc'::text, now())
     where id = p_new_slot_id;
  end if;

  return query select true, 'Cita actualizada exitosamente.'::text, p_appointment_id, v_new_slot.starts_at, v_new_slot.ends_at;
end;
$$;

create or replace function public.cancel_admission_appointment(
  p_org_id uuid,
  p_appointment_id uuid,
  p_reason text default null
)
returns table(
  success boolean,
  message text,
  appointment_id uuid
)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_appt public.appointments%rowtype;
  v_count integer;
begin
  if not public.can_manage_appointments_for_org(p_org_id) then
    return query select false, 'No autorizado para administrar citas.'::text, null::uuid;
    return;
  end if;

  select *
    into v_appt
  from public.appointments
  where id = p_appointment_id
    and organization_id = p_org_id
  for update;

  if not found then
    return query select false, 'No se encontró la cita.'::text, null::uuid;
    return;
  end if;

  if v_appt.status = 'cancelled' then
    return query select true, 'La cita ya estaba cancelada.'::text, v_appt.id;
    return;
  end if;

  update public.appointments
     set status = 'cancelled',
         notes = trim(both from concat(coalesce(notes, ''), E'\nCancelado. Razón: ', coalesce(nullif(p_reason, ''), 'No especificada'))),
         updated_at = timezone('utc'::text, now())
   where id = p_appointment_id;

  if v_appt.slot_id is not null then
    perform 1
    from public.availability_slots
    where id = v_appt.slot_id
      and organization_id = p_org_id
    for update;

    select count(*)::integer
      into v_count
    from public.appointments a
    where a.slot_id = v_appt.slot_id
      and a.status = 'scheduled';

    update public.availability_slots
       set appointments_count = v_count,
           updated_at = timezone('utc'::text, now())
     where id = v_appt.slot_id;
  end if;

  update public.leads
     set status = 'contacted',
         updated_at = timezone('utc'::text, now())
   where id = v_appt.lead_id
     and organization_id = p_org_id
     and status = 'visit_scheduled';

  return query select true, 'Cita cancelada exitosamente.'::text, v_appt.id;
end;
$$;

grant execute on function public.can_manage_appointments_for_org(uuid) to authenticated, service_role;
grant execute on function public.book_admission_appointment(uuid, uuid, uuid, text, text, uuid) to authenticated, service_role;
grant execute on function public.reschedule_admission_appointment(uuid, uuid, uuid, text, text) to authenticated, service_role;
grant execute on function public.cancel_admission_appointment(uuid, uuid, text) to authenticated, service_role;
