-- Track handoff requests and disable bot when human is requested

alter table public.chats
  add column if not exists requested_handoff boolean default false;

alter table public.chat_sessions
  alter column ai_enabled set default true;
