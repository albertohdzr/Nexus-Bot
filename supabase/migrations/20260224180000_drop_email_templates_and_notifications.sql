-- Drop all email template and notification-related tables
-- Order: triggers -> templates -> bases (respects FK dependencies)

-- 1. Drop policies first
drop policy if exists "Users select email_template_triggers by org" on public.email_template_triggers;
drop policy if exists "Users insert email_template_triggers by org" on public.email_template_triggers;
drop policy if exists "Users update email_template_triggers by org" on public.email_template_triggers;

drop policy if exists "Users select email_templates by org" on public.email_templates;
drop policy if exists "Users insert email_templates by org" on public.email_templates;
drop policy if exists "Users update email_templates by org" on public.email_templates;

drop policy if exists "Users select email_template_bases by org" on public.email_template_bases;
drop policy if exists "Users insert email_template_bases by org" on public.email_template_bases;
drop policy if exists "Users update email_template_bases by org" on public.email_template_bases;

-- 2. Drop tables (order matters for FK)
drop table if exists public.email_template_triggers;
drop table if exists public.email_templates;
drop table if exists public.email_template_bases;
