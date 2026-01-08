-- Temporary queue for accumulating WhatsApp messages per chat
create table if not exists public.message_queue (
  chat_id uuid primary key references public.chats(id) on delete cascade,
  combined_text text not null default '',
  last_added_at timestamptz not null default now(),
  is_processing boolean not null default false
);

-- Enable RLS
alter table public.message_queue enable row level security;

-- Policies aligned with chats/messages organization access
create policy "Users can view message queue from their organization's chats" on public.message_queue
  for select to authenticated
  using (
    chat_id in (
      select id from public.chats where organization_id in (
        select organization_id from public.user_profiles where id = (select auth.uid())
      )
    )
  );

create policy "Users can insert message queue for their organization's chats" on public.message_queue
  for insert to authenticated
  with check (
    chat_id in (
      select id from public.chats where organization_id in (
        select organization_id from public.user_profiles where id = (select auth.uid())
      )
    )
  );

create policy "Users can update message queue from their organization's chats" on public.message_queue
  for update to authenticated
  using (
    chat_id in (
      select id from public.chats where organization_id in (
        select organization_id from public.user_profiles where id = (select auth.uid())
      )
    )
  );

create policy "Users can delete message queue from their organization's chats" on public.message_queue
  for delete to authenticated
  using (
    chat_id in (
      select id from public.chats where organization_id in (
        select organization_id from public.user_profiles where id = (select auth.uid())
      )
    )
  );

-- Index for processing queue scans
create index if not exists message_queue_processing_idx
  on public.message_queue (is_processing, last_added_at);

-- Atomically accumulate message text for a chat
create or replace function public.accumulate_whatsapp_message(
  p_chat_id uuid,
  p_new_text text
)
returns setof public.message_queue as $$
begin
  return query
  insert into public.message_queue (chat_id, combined_text, last_added_at)
  values (p_chat_id, coalesce(p_new_text, ''), now())
  on conflict (chat_id) do update
  set combined_text = case
        when message_queue.combined_text is null or message_queue.combined_text = '' then excluded.combined_text
        when excluded.combined_text is null or excluded.combined_text = '' then message_queue.combined_text
        else message_queue.combined_text || ' ' || excluded.combined_text
      end,
      last_added_at = now()
  returning *;
end;
$$ language plpgsql set search_path = public, extensions;
