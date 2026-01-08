-- Track storage path for private bucket access.
alter table public.messages
  add column if not exists media_path text;
