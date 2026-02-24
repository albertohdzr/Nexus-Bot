-- Migration: Lead Status History
-- Tabla para rastrear cambios de estado de los leads con trazabilidad completa

CREATE TABLE IF NOT EXISTS lead_status_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    previous_status TEXT,
    new_status TEXT NOT NULL,
    changed_by UUID REFERENCES auth.users(id),
    changed_by_name TEXT,
    reason TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Índices para búsquedas eficientes
CREATE INDEX IF NOT EXISTS idx_lead_status_history_lead_id ON lead_status_history(lead_id);
CREATE INDEX IF NOT EXISTS idx_lead_status_history_organization_id ON lead_status_history(organization_id);
CREATE INDEX IF NOT EXISTS idx_lead_status_history_created_at ON lead_status_history(created_at DESC);

-- RLS Policies
ALTER TABLE lead_status_history ENABLE ROW LEVEL SECURITY;

-- Ver historial de estados de leads de la misma organización
CREATE POLICY "Users can view lead status history in their organization"
    ON lead_status_history FOR SELECT
    USING (
        organization_id IN (
            SELECT organization_id FROM user_profiles WHERE id = auth.uid()
        )
    );

-- Insertar historial (solo usuarios autenticados de la misma org)
CREATE POLICY "Users can insert lead status history in their organization"
    ON lead_status_history FOR INSERT
    WITH CHECK (
        organization_id IN (
            SELECT organization_id FROM user_profiles WHERE id = auth.uid()
        )
    );

-- Trigger para registrar automáticamente cambios de estado
CREATE OR REPLACE FUNCTION log_lead_status_change()
RETURNS TRIGGER AS $$
BEGIN
    -- Solo registrar si el status cambió
    IF OLD.status IS DISTINCT FROM NEW.status THEN
        INSERT INTO lead_status_history (
            lead_id,
            organization_id,
            previous_status,
            new_status,
            changed_by,
            changed_by_name
        )
        VALUES (
            NEW.id,
            NEW.organization_id,
            OLD.status,
            NEW.status,
            auth.uid(),
            (SELECT full_name FROM user_profiles WHERE id = auth.uid())
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Crear el trigger
DROP TRIGGER IF EXISTS lead_status_change_trigger ON leads;
CREATE TRIGGER lead_status_change_trigger
    AFTER UPDATE ON leads
    FOR EACH ROW
    EXECUTE FUNCTION log_lead_status_change();

-- Comentarios
COMMENT ON TABLE lead_status_history IS 'Rastrea todos los cambios de estado de los leads para trazabilidad completa';
COMMENT ON COLUMN lead_status_history.previous_status IS 'Estado anterior del lead (null si es creación inicial)';
COMMENT ON COLUMN lead_status_history.new_status IS 'Nuevo estado al que cambió el lead';
COMMENT ON COLUMN lead_status_history.reason IS 'Razón opcional del cambio de estado';
COMMENT ON COLUMN lead_status_history.notes IS 'Notas adicionales sobre el cambio';
