-- Link messages to AI responses and sessions, reuse chat_sessions, drop unused chat_messages

drop table if exists public.chat_messages cascade;

alter table public.chat_sessions
  add column if not exists chat_id uuid references public.chats(id) on delete cascade,
  add column if not exists conversation_id text,
  add column if not exists last_response_at timestamptz,
  add column if not exists closed_at timestamptz;

alter table public.chats
  add column if not exists active_session_id uuid references public.chat_sessions(id) on delete set null,
  add column if not exists last_session_closed_at timestamptz;

alter table public.messages
  add column if not exists chat_session_id uuid references public.chat_sessions(id) on delete set null,
  add column if not exists response_id text;

create index if not exists chat_sessions_chat_id_idx on public.chat_sessions(chat_id);
create index if not exists chat_sessions_conversation_id_idx on public.chat_sessions(conversation_id);
create index if not exists chats_active_session_id_idx on public.chats(active_session_id);
create index if not exists messages_chat_session_id_idx on public.messages(chat_session_id);
create index if not exists messages_response_id_idx on public.messages(response_id);
