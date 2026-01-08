-- Track timestamps for WhatsApp delivery states and who sent an outgoing message.
alter table public.messages
  add column if not exists wa_timestamp timestamptz,
  add column if not exists sent_at timestamptz,
  add column if not exists delivered_at timestamptz,
  add column if not exists read_at timestamptz,
  add column if not exists sender_profile_id uuid references public.user_profiles(id),
  add column if not exists sender_name text;
