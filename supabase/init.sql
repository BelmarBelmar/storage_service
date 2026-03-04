-- Créer les rôles Supabase nécessaires
CREATE ROLE anon NOLOGIN;
CREATE ROLE authenticated NOLOGIN;
CREATE ROLE service_role NOLOGIN BYPASSRLS;

-- Rôle authenticator pour PostgREST
CREATE ROLE authenticator NOINHERIT LOGIN PASSWORD 'supabase_auth_pass';
GRANT anon TO authenticator;
GRANT authenticated TO authenticator;
GRANT service_role TO authenticator;

-- Rôle pour GoTrue (auth)
CREATE ROLE supabase_auth_admin NOINHERIT LOGIN PASSWORD 'supabase_auth_pass';
CREATE SCHEMA IF NOT EXISTS auth AUTHORIZATION supabase_auth_admin;
GRANT ALL ON SCHEMA auth TO supabase_auth_admin;

-- Table : métadonnées des fichiers uploadé
CREATE TABLE IF NOT EXISTS public.file_metadata (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_email    TEXT NOT NULL,
    filename      TEXT NOT NULL,
    object_name   TEXT NOT NULL,
    bucket_name   TEXT NOT NULL,
    size_bytes    BIGINT NOT NULL,
    mime_type     TEXT NOT NULL,
    sha256        TEXT NOT NULL,
    uploaded_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at    TIMESTAMPTZ,

    CONSTRAINT file_metadata_sha256_check CHECK (length(sha256) = 64)
);

-- Index pour recherche par utilisateur
CREATE INDEX idx_file_metadata_user ON public.file_metadata(user_email);
CREATE INDEX idx_file_metadata_uploaded ON public.file_metadata(uploaded_at DESC);

-- RLS (Row Level Security): chaque utilisateur ne voit que ses fichiers
ALTER TABLE public.file_metadata ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own files"
    ON public.file_metadata FOR SELECT
    USING (user_email = current_setting('request.jwt.claims', true)::json->>'email');

CREATE POLICY "Users can insert own files"
    ON public.file_metadata FOR INSERT
    WITH CHECK (user_email = current_setting('request.jwt.claims', true)::json->>'email');

-- Table : logs d'accès centralisés
CREATE TABLE IF NOT EXISTS public.access_logs (
    id          BIGSERIAL PRIMARY KEY,
    event_type  TEXT NOT NULL,  -- 'otp_request', 'upload', 'download', 'delete'
    user_email  TEXT,
    client_ip   TEXT,
    file_id     UUID,
    details     JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_access_logs_user ON public.access_logs(user_email);
CREATE INDEX idx_access_logs_created ON public.access_logs(created_at DESC);
CREATE INDEX idx_access_logs_type ON public.access_logs(event_type);

-- Table : OTP
CREATE TABLE IF NOT EXISTS public.otp_codes (
    email       TEXT PRIMARY KEY,
    code_hash   TEXT NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Nettoyage automatique des OTP expirés
CREATE OR REPLACE FUNCTION cleanup_expired_otps()
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    DELETE FROM public.otp_codes WHERE expires_at < NOW();
END;
$$;

GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
GRANT SELECT, INSERT ON public.file_metadata TO authenticated;
GRANT INSERT ON public.access_logs TO authenticated, anon;