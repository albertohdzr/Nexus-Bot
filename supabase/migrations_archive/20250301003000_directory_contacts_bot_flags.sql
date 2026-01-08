-- Campos extra para directorio de contactos y toggle global para el bot

alter table public.organizations
  add column if not exists bot_directory_enabled boolean not null default false;

alter table public.directory_contacts
  add column if not exists extension text,
  add column if not exists mobile text,
  add column if not exists allow_bot_share boolean not null default false,
  add column if not exists share_email boolean not null default false,
  add column if not exists share_phone boolean not null default false,
  add column if not exists share_extension boolean not null default false,
  add column if not exists share_mobile boolean not null default false;

create index if not exists directory_contacts_bot_share_idx
  on public.directory_contacts(organization_id, allow_bot_share, is_active);
