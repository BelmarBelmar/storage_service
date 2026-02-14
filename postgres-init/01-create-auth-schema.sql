-- Crée le schema auth si pas existant
CREATE SCHEMA IF NOT EXISTS auth;

-- Donne tous les droits à l'utilisateur Goture (remplace par ton POSTGRES_USER si différent)
GRANT ALL PRIVILEGES ON SCHEMA auth TO "${POSTGRES_USER}";

-- Force search_path pour cet utilisateur (important pour migrations sans préfixe schema)
ALTER ROLE "${POSTGRES_USER}" SET search_path TO auth, public;

-- Optionnel : log pour vérifier
DO $$     BEGIN RAISE NOTICE 'Schema auth created and privileges granted'; END     $$;
