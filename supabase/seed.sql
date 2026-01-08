-- Create a default organization
INSERT INTO public.organizations (id, name, slug, is_active)
VALUES
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Nexus Core', 'nexus-core', true)
ON CONFLICT (id) DO NOTHING;

-- Create the user in auth.users
INSERT INTO auth.users (
    instance_id,
    id,
    aud,
    role,
    email,
    encrypted_password,
    email_confirmed_at,
    raw_app_meta_data,
    raw_user_meta_data,
    created_at,
    updated_at,
    confirmation_token,
    email_change,
    email_change_token_new,
    recovery_token
) VALUES (
    '00000000-0000-0000-0000-000000000000',
    'd0d8c19c-3b3d-4f4e-9f9a-8b8c8d8e8f8a',
    'authenticated',
    'authenticated',
    'albertohdzr98@gmail.com',
    extensions.crypt('Otrebla98!', extensions.gen_salt('bf')),
    now(),
    '{"provider": "email", "providers": ["email"]}',
    '{}',
    now(),
    now(),
    '',
    '',
    '',
    ''
) ON CONFLICT (id) DO NOTHING;

-- Create the user profile
INSERT INTO public.user_profiles (
    id,
    organization_id,
    role,
    first_name,
    last_name_paternal,
    email,
    is_active
) VALUES (
    'd0d8c19c-3b3d-4f4e-9f9a-8b8c8d8e8f8a', -- Must match auth.users.id
    'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', -- Must match organization.id
    'superadmin',
    'Alberto',
    'Hernandez',
    'albertohdzr98@gmail.com',
    true
) ON CONFLICT (id) DO NOTHING;
