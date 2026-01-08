-- =============================================
-- 1. CONFIGURACIÓN INICIAL Y EXTENSIONES
-- =============================================

CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp" SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS "pgcrypto" SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS "pg_trgm" SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS "unaccent" SCHEMA extensions;

-- Tipos ENUM (Vocabulario controlado del sistema)
CREATE TYPE plan_type AS ENUM ('trial', 'basic', 'professional', 'enterprise');
CREATE TYPE system_role AS ENUM ('superadmin', 'org_admin', 'director', 'admissions', 'teacher', 'finance', 'staff', 'parent', 'student');
CREATE TYPE lead_status AS ENUM ('new', 'contacted', 'qualified', 'visit_scheduled', 'visited', 'application_started', 'application_submitted', 'admitted', 'enrolled', 'lost');
CREATE TYPE lead_source AS ENUM ('website', 'whatsapp', 'facebook', 'instagram', 'google_ads', 'referral', 'walk_in', 'other');
CREATE TYPE task_priority AS ENUM ('low', 'medium', 'high', 'urgent');
CREATE TYPE task_status AS ENUM ('pending', 'in_progress', 'completed', 'cancelled');
CREATE TYPE app_status AS ENUM ('draft', 'submitted', 'under_review', 'changes_requested', 'approved', 'rejected', 'paid');
CREATE TYPE payment_status AS ENUM ('pending', 'completed', 'failed', 'refunded');
CREATE TYPE payment_provider AS ENUM ('stripe', 'mercadopago', 'transfer', 'cash');

-- =============================================
-- 2. CORE: ORGANIZACIONES Y USUARIOS
-- =============================================

CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    slug TEXT NOT NULL,
    logo_url TEXT,
    plan plan_type DEFAULT 'trial',
    settings JSONB DEFAULT '{}', -- Configuración general (colores, branding)
    ai_settings JSONB DEFAULT '{"enabled": false, "personality": "formal"}', -- Configuración del Bot
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX uniq_org_slug ON organizations(slug) WHERE deleted_at IS NULL;

-- Perfiles de usuario (Extensión de auth.users)
CREATE TABLE user_profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    role system_role NOT NULL DEFAULT 'parent',
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    full_name TEXT GENERATED ALWAYS AS (first_name || ' ' || last_name) STORED,
    email TEXT NOT NULL,
    phone TEXT,
    avatar_url TEXT,
    is_active BOOLEAN DEFAULT true,
    force_password_change BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(email, organization_id)
);

-- Permisos (RBAC Simplificado)
CREATE TABLE role_permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    role system_role NOT NULL,
    module TEXT NOT NULL, -- 'crm', 'finance', 'admissions'
    permissions JSONB NOT NULL DEFAULT '{}', -- {"create": true, "read": true}
    UNIQUE(organization_id, role, module)
);

-- =============================================
-- 3. CRM & OMNICANALIDAD (IA + CHATBOT)
-- =============================================

CREATE TABLE leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    lead_number SERIAL, -- Para referencia visual (L-102)
    status lead_status DEFAULT 'new',
    source lead_source NOT NULL,
    
    -- Datos del Estudiante Potencial
    student_first_name TEXT NOT NULL,
    student_last_name TEXT NOT NULL,
    student_dob DATE,
    student_grade_interest TEXT,
    
    -- Datos del Contacto (Padre/Tutor)
    contact_name TEXT NOT NULL,
    contact_email TEXT,
    contact_phone TEXT NOT NULL,
    
    -- Gestión
    assigned_to UUID REFERENCES user_profiles(id),
    score INTEGER DEFAULT 0,
    tags TEXT[],
    notes TEXT,
    
    -- Conversión
    converted_at TIMESTAMPTZ,
    converted_to_student_id UUID,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Mapeo de Identidades Sociales (Para el Chatbot)
CREATE TABLE social_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    lead_id UUID REFERENCES leads(id) ON DELETE SET NULL,
    user_id UUID REFERENCES user_profiles(id) ON DELETE SET NULL, -- Si ya es usuario registrado
    platform TEXT NOT NULL, -- 'whatsapp', 'instagram'
    platform_user_id TEXT NOT NULL, -- El wa_id o ig_id
    profile_data JSONB DEFAULT '{}',
    last_interaction_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(organization_id, platform, platform_user_id)
);

-- Sesiones de Chat (Memoria para la IA)
CREATE TABLE chat_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    social_mapping_id UUID REFERENCES social_mappings(id),
    status TEXT DEFAULT 'active', -- active, closed, handover
    ai_enabled BOOLEAN DEFAULT true, -- Si el bot debe responder
    summary TEXT, -- Resumen generado por IA de la charla
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Mensajes (Historial)
CREATE TABLE chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    sender_type TEXT NOT NULL, -- 'user', 'bot', 'agent'
    content TEXT,
    media_url TEXT,
    metadata JSONB DEFAULT '{}', -- Tokens usados, confianza IA
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Actividades Clásicas del CRM
CREATE TABLE lead_activities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    lead_id UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    type TEXT NOT NULL, -- call, email, meeting, visit
    subject TEXT,
    notes TEXT,
    completed_at TIMESTAMPTZ,
    created_by UUID REFERENCES user_profiles(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Tareas
CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    title TEXT NOT NULL,
    description TEXT,
    due_date TIMESTAMPTZ,
    priority task_priority DEFAULT 'medium',
    status task_status DEFAULT 'pending',
    assigned_to UUID REFERENCES user_profiles(id),
    related_lead_id UUID REFERENCES leads(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================
-- 4. ADMISSIONS (INSCRIPCIONES) & PAGOS
-- =============================================

CREATE TABLE admission_cycles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    name TEXT NOT NULL, -- "Ciclo 2025-2026"
    start_date DATE,
    end_date DATE,
    is_active BOOLEAN DEFAULT true,
    registration_fee DECIMAL(10,2) DEFAULT 0
);

-- La Solicitud de Inscripción (El formulario que llena el padre)
CREATE TABLE admission_applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    cycle_id UUID REFERENCES admission_cycles(id),
    lead_id UUID REFERENCES leads(id), -- Vincula con el CRM
    user_id UUID REFERENCES user_profiles(id), -- El padre que llena la form (si ya tiene cuenta)
    
    -- Estado
    status app_status DEFAULT 'draft',
    step_completed INTEGER DEFAULT 0, -- Para wizard de frontend
    
    -- Datos JSONB para flexibilidad (Formularios dinámicos)
    student_data JSONB NOT NULL DEFAULT '{}', 
    medical_data JSONB DEFAULT '{}',
    family_data JSONB DEFAULT '{}',
    
    reviewer_notes TEXT,
    submitted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE admission_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id UUID NOT NULL REFERENCES admission_applications(id) ON DELETE CASCADE,
    type TEXT NOT NULL, -- 'acta_nacimiento', 'curp', 'boleta'
    file_url TEXT NOT NULL,
    status TEXT DEFAULT 'pending', -- pending, approved, rejected
    rejection_reason TEXT,
    uploaded_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    application_id UUID REFERENCES admission_applications(id),
    amount DECIMAL(10,2) NOT NULL,
    currency TEXT DEFAULT 'MXN',
    status payment_status DEFAULT 'pending',
    provider payment_provider NOT NULL,
    provider_transaction_id TEXT, -- Stripe ID
    receipt_url TEXT,
    paid_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================
-- 5. ERP BASE: ESTUDIANTES Y FAMILIAS
-- =============================================

CREATE TABLE students (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    student_id_number TEXT, -- Matrícula oficial
    current_grade TEXT,
    section TEXT, -- Grupo A, B
    status TEXT DEFAULT 'active', -- active, inactive, graduated
    
    -- Relación histórica
    original_lead_id UUID REFERENCES leads(id),
    admission_application_id UUID REFERENCES admission_applications(id),
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Tabla pivote para Familias (Un padre puede tener varios hijos, hermanos en mismo colegio)
CREATE TABLE student_families (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    student_id UUID REFERENCES students(id) ON DELETE CASCADE,
    parent_user_id UUID REFERENCES user_profiles(id) ON DELETE CASCADE,
    relationship TEXT NOT NULL, -- Padre, Madre, Tutor
    is_financial_responsible BOOLEAN DEFAULT false,
    UNIQUE(student_id, parent_user_id)
);

-- =============================================
-- 6. FUNCIONES AUXILIARES
-- =============================================

-- Verificar Superadmin
CREATE OR REPLACE FUNCTION is_superadmin(user_id UUID)
RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (SELECT 1 FROM user_profiles WHERE id = user_id AND role = 'superadmin');
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, extensions;

-- Verificar Permisos por Módulo
CREATE OR REPLACE FUNCTION check_permission(user_id UUID, req_module TEXT, req_action TEXT)
RETURNS BOOLEAN AS $$
DECLARE
    user_role system_role;
    user_org UUID;
    has_perm BOOLEAN;
BEGIN
    SELECT role, organization_id INTO user_role, user_org FROM user_profiles WHERE id = user_id;
    
    IF user_role IN ('superadmin', 'org_admin') THEN RETURN TRUE; END IF;
    
    SELECT (permissions->>req_action)::BOOLEAN INTO has_perm
    FROM role_permissions
    WHERE organization_id = user_org AND role = user_role AND module = req_module;
    
    RETURN COALESCE(has_perm, FALSE);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, extensions;

-- =============================================
-- 7. SEGURIDAD: ROW LEVEL SECURITY (RLS)
-- =============================================

-- Habilitar RLS en todas las tablas
ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE admission_applications ENABLE ROW LEVEL SECURITY;
ALTER TABLE students ENABLE ROW LEVEL SECURITY;
ALTER TABLE payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE student_families ENABLE ROW LEVEL SECURITY;
ALTER TABLE admission_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE admission_cycles ENABLE ROW LEVEL SECURITY;
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE lead_activities ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_mappings ENABLE ROW LEVEL SECURITY;
ALTER TABLE role_permissions ENABLE ROW LEVEL SECURITY;

-- --- POLÍTICAS DE ORGANIZACIONES ---
CREATE POLICY "Superadmin insert orgs" ON organizations 
    FOR INSERT TO authenticated WITH CHECK (is_superadmin((select auth.uid())));

CREATE POLICY "Superadmin update orgs" ON organizations 
    FOR UPDATE TO authenticated USING (is_superadmin((select auth.uid())));

CREATE POLICY "Superadmin delete orgs" ON organizations 
    FOR DELETE TO authenticated USING (is_superadmin((select auth.uid())));

CREATE POLICY "Read organizations" ON organizations 
    FOR SELECT TO authenticated 
    USING (
        is_superadmin((select auth.uid())) 
        OR id IN (SELECT organization_id FROM user_profiles WHERE id = (select auth.uid()))
    );

-- --- POLÍTICAS DE PERFILES ---
CREATE OR REPLACE FUNCTION get_my_org_id()
RETURNS UUID AS $$
    SELECT organization_id FROM user_profiles WHERE id = (select auth.uid());
$$ LANGUAGE sql SECURITY DEFINER SET search_path = public, extensions;

CREATE POLICY "Ver perfiles de mi org" ON user_profiles
    FOR SELECT TO authenticated
    USING (
        id = (select auth.uid()) -- Can always see own profile
        OR organization_id = get_my_org_id() -- Can see profiles in same org
    );

CREATE POLICY "Editar mi propio perfil" ON user_profiles
    FOR UPDATE TO authenticated
    USING (id = (select auth.uid()));

-- --- POLÍTICAS DE CRM (Leads) ---
CREATE POLICY "Staff ve leads" ON leads
    FOR ALL TO authenticated
    USING (
        organization_id IN (SELECT organization_id FROM user_profiles WHERE id = (select auth.uid()))
        AND (
            EXISTS (
                SELECT 1 FROM user_profiles 
                WHERE id = (select auth.uid()) 
                AND role IN ('org_admin', 'director', 'admissions')
            ) 
            OR assigned_to = (select auth.uid())
        )
    );

-- --- POLÍTICAS DE CHATBOT (Privacidad) ---
CREATE POLICY "Solo staff autorizado ve chats" ON chat_sessions
    FOR SELECT TO authenticated
    USING (
        organization_id IN (SELECT organization_id FROM user_profiles WHERE id = (select auth.uid()))
        AND EXISTS (
            SELECT 1 FROM user_profiles 
            WHERE id = (select auth.uid()) 
            AND role IN ('org_admin', 'admissions')
        )
    );

-- --- POLÍTICAS DE ADMISSIONS (Clave para padres) ---
-- 1. Los padres pueden ver y editar SOLO sus propias solicitudes
CREATE POLICY "Access admission applications" ON admission_applications
    FOR ALL TO authenticated
    USING (
        user_id = (select auth.uid())
        OR (
            organization_id IN (SELECT organization_id FROM user_profiles WHERE id = (select auth.uid()))
            AND EXISTS (
                SELECT 1 FROM user_profiles 
                WHERE id = (select auth.uid()) 
                AND role IN ('org_admin', 'director', 'admissions')
            )
        )
    );

-- --- POLÍTICAS DE PAGOS ---
CREATE POLICY "Read payments" ON payments
    FOR SELECT TO authenticated
    USING (
        application_id IN (SELECT id FROM admission_applications WHERE user_id = (select auth.uid()))
        OR (
            organization_id IN (SELECT organization_id FROM user_profiles WHERE id = (select auth.uid()))
            AND EXISTS (
                SELECT 1 FROM user_profiles 
                WHERE id = (select auth.uid()) 
                AND role IN ('org_admin', 'finance')
            )
        )
    );

CREATE POLICY "Admin insert payments" ON payments
    FOR INSERT TO authenticated WITH CHECK (
        organization_id IN (SELECT organization_id FROM user_profiles WHERE id = (select auth.uid()))
        AND EXISTS (
            SELECT 1 FROM user_profiles 
            WHERE id = (select auth.uid()) 
            AND role IN ('org_admin', 'finance')
        )
    );

CREATE POLICY "Admin update payments" ON payments
    FOR UPDATE TO authenticated USING (
        organization_id IN (SELECT organization_id FROM user_profiles WHERE id = (select auth.uid()))
        AND EXISTS (
            SELECT 1 FROM user_profiles 
            WHERE id = (select auth.uid()) 
            AND role IN ('org_admin', 'finance')
        )
    );

CREATE POLICY "Admin delete payments" ON payments
    FOR DELETE TO authenticated USING (
        organization_id IN (SELECT organization_id FROM user_profiles WHERE id = (select auth.uid()))
        AND EXISTS (
            SELECT 1 FROM user_profiles 
            WHERE id = (select auth.uid()) 
            AND role IN ('org_admin', 'finance')
        )
    );

-- =============================================
-- 8. TRIGGERS AUTOMÁTICOS
-- =============================================

-- Función para updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = public, extensions;

-- --- POLÍTICAS DE STUDENT FAMILIES ---
CREATE POLICY "Read families" ON student_families
    FOR SELECT TO authenticated
    USING (
        parent_user_id = (select auth.uid())
        OR (
            organization_id IN (SELECT organization_id FROM user_profiles WHERE id = (select auth.uid()))
            AND EXISTS (
                SELECT 1 FROM user_profiles 
                WHERE id = (select auth.uid()) 
                AND role IN ('org_admin', 'director', 'admissions', 'teacher')
            )
        )
    );

CREATE POLICY "Staff insert families" ON student_families
    FOR INSERT TO authenticated WITH CHECK (
        organization_id IN (SELECT organization_id FROM user_profiles WHERE id = (select auth.uid()))
        AND EXISTS (
            SELECT 1 FROM user_profiles 
            WHERE id = (select auth.uid()) 
            AND role IN ('org_admin', 'director', 'admissions', 'teacher')
        )
    );

CREATE POLICY "Staff update families" ON student_families
    FOR UPDATE TO authenticated USING (
        organization_id IN (SELECT organization_id FROM user_profiles WHERE id = (select auth.uid()))
        AND EXISTS (
            SELECT 1 FROM user_profiles 
            WHERE id = (select auth.uid()) 
            AND role IN ('org_admin', 'director', 'admissions', 'teacher')
        )
    );

CREATE POLICY "Staff delete families" ON student_families
    FOR DELETE TO authenticated USING (
        organization_id IN (SELECT organization_id FROM user_profiles WHERE id = (select auth.uid()))
        AND EXISTS (
            SELECT 1 FROM user_profiles 
            WHERE id = (select auth.uid()) 
            AND role IN ('org_admin', 'director', 'admissions', 'teacher')
        )
    );

-- --- POLÍTICAS DE ADMISSION DOCUMENTS ---
CREATE POLICY "Access admission documents" ON admission_documents
    FOR ALL TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM admission_applications aa
            WHERE aa.id = admission_documents.application_id
            AND aa.user_id = (select auth.uid())
        )
        OR EXISTS (
            SELECT 1 FROM admission_applications aa
            JOIN user_profiles up ON up.organization_id = aa.organization_id
            WHERE aa.id = admission_documents.application_id
            AND up.id = (select auth.uid())
            AND up.role IN ('org_admin', 'director', 'admissions')
        )
    );

-- --- POLÍTICAS DE ADMISSION CYCLES ---
CREATE POLICY "Ver ciclos activos" ON admission_cycles
    FOR SELECT TO authenticated
    USING (true);

CREATE POLICY "Admin insert cycles" ON admission_cycles
    FOR INSERT TO authenticated WITH CHECK (
        organization_id IN (SELECT organization_id FROM user_profiles WHERE id = (select auth.uid()))
        AND EXISTS (
            SELECT 1 FROM user_profiles 
            WHERE id = (select auth.uid()) 
            AND role IN ('org_admin', 'director')
        )
    );

CREATE POLICY "Admin update cycles" ON admission_cycles
    FOR UPDATE TO authenticated USING (
        organization_id IN (SELECT organization_id FROM user_profiles WHERE id = (select auth.uid()))
        AND EXISTS (
            SELECT 1 FROM user_profiles 
            WHERE id = (select auth.uid()) 
            AND role IN ('org_admin', 'director')
        )
    );

CREATE POLICY "Admin delete cycles" ON admission_cycles
    FOR DELETE TO authenticated USING (
        organization_id IN (SELECT organization_id FROM user_profiles WHERE id = (select auth.uid()))
        AND EXISTS (
            SELECT 1 FROM user_profiles 
            WHERE id = (select auth.uid()) 
            AND role IN ('org_admin', 'director')
        )
    );

-- --- POLÍTICAS DE TASKS ---
CREATE POLICY "Staff ve tareas" ON tasks
    FOR ALL TO authenticated
    USING (
        organization_id IN (SELECT organization_id FROM user_profiles WHERE id = (select auth.uid()))
        AND EXISTS (
            SELECT 1 FROM user_profiles 
            WHERE id = (select auth.uid()) 
            AND role IN ('org_admin', 'director', 'admissions', 'teacher')
        )
    );

-- --- POLÍTICAS DE LEAD ACTIVITIES ---
CREATE POLICY "Staff ve actividades" ON lead_activities
    FOR ALL TO authenticated
    USING (
        organization_id IN (SELECT organization_id FROM user_profiles WHERE id = (select auth.uid()))
        AND EXISTS (
            SELECT 1 FROM user_profiles 
            WHERE id = (select auth.uid()) 
            AND role IN ('org_admin', 'director', 'admissions')
        )
    );

-- --- POLÍTICAS DE SOCIAL MAPPINGS ---
CREATE POLICY "Staff ve mappings" ON social_mappings
    FOR ALL TO authenticated
    USING (
        organization_id IN (SELECT organization_id FROM user_profiles WHERE id = (select auth.uid()))
        AND EXISTS (
            SELECT 1 FROM user_profiles 
            WHERE id = (select auth.uid()) 
            AND role IN ('org_admin', 'director', 'admissions')
        )
    );

-- --- POLÍTICAS DE ROLE PERMISSIONS ---
CREATE POLICY "Ver permisos" ON role_permissions
    FOR SELECT TO authenticated
    USING (true);

CREATE POLICY "Superadmin insert permissions" ON role_permissions
    FOR INSERT TO authenticated WITH CHECK (is_superadmin((select auth.uid())));

CREATE POLICY "Superadmin update permissions" ON role_permissions
    FOR UPDATE TO authenticated USING (is_superadmin((select auth.uid())));

CREATE POLICY "Superadmin delete permissions" ON role_permissions
    FOR DELETE TO authenticated USING (is_superadmin((select auth.uid())));

CREATE TRIGGER update_orgs_time BEFORE UPDATE ON organizations FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER update_leads_time BEFORE UPDATE ON leads FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER update_apps_time BEFORE UPDATE ON admission_applications FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- =============================================
-- 10. ÍNDICES DE RENDIMIENTO (Foreign Keys)
-- =============================================

CREATE INDEX idx_admission_applications_cycle_id ON admission_applications(cycle_id);
CREATE INDEX idx_admission_applications_lead_id ON admission_applications(lead_id);
CREATE INDEX idx_admission_applications_organization_id ON admission_applications(organization_id);
CREATE INDEX idx_admission_applications_user_id ON admission_applications(user_id);

CREATE INDEX idx_admission_cycles_organization_id ON admission_cycles(organization_id);

CREATE INDEX idx_admission_documents_application_id ON admission_documents(application_id);

CREATE INDEX idx_chat_messages_session_id ON chat_messages(session_id);

CREATE INDEX idx_chat_sessions_organization_id ON chat_sessions(organization_id);
CREATE INDEX idx_chat_sessions_social_mapping_id ON chat_sessions(social_mapping_id);

CREATE INDEX idx_lead_activities_created_by ON lead_activities(created_by);
CREATE INDEX idx_lead_activities_lead_id ON lead_activities(lead_id);
CREATE INDEX idx_lead_activities_organization_id ON lead_activities(organization_id);

CREATE INDEX idx_leads_assigned_to ON leads(assigned_to);
CREATE INDEX idx_leads_organization_id ON leads(organization_id);

CREATE INDEX idx_payments_application_id ON payments(application_id);
CREATE INDEX idx_payments_organization_id ON payments(organization_id);

CREATE INDEX idx_social_mappings_lead_id ON social_mappings(lead_id);
CREATE INDEX idx_social_mappings_user_id ON social_mappings(user_id);

CREATE INDEX idx_student_families_organization_id ON student_families(organization_id);
CREATE INDEX idx_student_families_parent_user_id ON student_families(parent_user_id);

CREATE INDEX idx_students_admission_application_id ON students(admission_application_id);
CREATE INDEX idx_students_organization_id ON students(organization_id);
CREATE INDEX idx_students_original_lead_id ON students(original_lead_id);

CREATE INDEX idx_tasks_assigned_to ON tasks(assigned_to);
CREATE INDEX idx_tasks_organization_id ON tasks(organization_id);
CREATE INDEX idx_tasks_related_lead_id ON tasks(related_lead_id);

CREATE INDEX idx_user_profiles_organization_id ON user_profiles(organization_id);

-- =============================================
-- 11. DATOS SEMILLA (Seed Data)
-- =============================================

-- Permisos por defecto para roles estándar
-- NOTA: organization_id NULL significa "permiso plantilla global"
INSERT INTO role_permissions (organization_id, role, module, permissions) VALUES
(NULL, 'admissions', 'crm', '{"read": true, "create": true, "edit": true, "delete": false}'),
(NULL, 'admissions', 'admissions', '{"read": true, "approve": true, "reject": true}'),
(NULL, 'finance', 'finance', '{"read": true, "manage_payments": true}'),
(NULL, 'teacher', 'erp', '{"view_students": true, "grade": true}');