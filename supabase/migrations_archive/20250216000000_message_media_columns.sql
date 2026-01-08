-- Add media fields to messages for images and linked WhatsApp media IDs.
alter table public.messages
  add column if not exists media_id text,
  add column if not exists media_url text;
