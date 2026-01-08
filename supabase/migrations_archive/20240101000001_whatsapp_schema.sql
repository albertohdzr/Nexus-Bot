-- Add WhatsApp fields to organizations
alter table public.organizations 
add column if not exists display_phone_number text,
add column if not exists phone_number_id text unique;

-- Create chats table
create table if not exists public.chats (
  id uuid default gen_random_uuid() primary key,
  wa_id text not null unique,
  name text,
  phone_number text,
  organization_id uuid references public.organizations(id) on delete cascade,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,
  updated_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- Create messages table
create table if not exists public.messages (
  id uuid default gen_random_uuid() primary key,
  chat_id uuid references public.chats(id) on delete cascade not null,
  wa_message_id text unique,
  body text,
  type text,
  status text default 'received',
  payload jsonb,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- Enable RLS (Row Level Security)
alter table public.chats enable row level security;
alter table public.messages enable row level security;

-- Create policies with performance optimization: (select auth.uid())

-- CHATS POLICIES
create policy "Users can view chats from their organization" on public.chats
  for select to authenticated
  using (
    organization_id in (
      select organization_id from public.user_profiles where id = (select auth.uid())
    )
  );

create policy "Users can insert chats for their organization" on public.chats
  for insert to authenticated
  with check (
    organization_id in (
      select organization_id from public.user_profiles where id = (select auth.uid())
    )
  );

create policy "Users can update chats from their organization" on public.chats
  for update to authenticated
  using (
    organization_id in (
      select organization_id from public.user_profiles where id = (select auth.uid())
    )
  );

-- MESSAGES POLICIES
create policy "Users can view messages from their organization's chats" on public.messages
  for select to authenticated
  using (
    chat_id in (
      select id from public.chats where organization_id in (
        select organization_id from public.user_profiles where id = (select auth.uid())
      )
    )
  );

create policy "Users can insert messages for their organization's chats" on public.messages
  for insert to authenticated
  with check (
    chat_id in (
      select id from public.chats where organization_id in (
        select organization_id from public.user_profiles where id = (select auth.uid())
      )
    )
  );

-- Enable Realtime
alter publication supabase_realtime add table public.chats;
alter publication supabase_realtime add table public.messages;

-- Allow org_admin to update their own organization
drop policy if exists "Superadmin update orgs" on public.organizations;

create policy "Admins can update their organization" on public.organizations
  for update to authenticated
  using (
    is_superadmin((select auth.uid()))
    or id in (
      select organization_id from public.user_profiles 
      where id = (select auth.uid()) 
      and role = 'org_admin'
    )
  );
