#!/bin/sh

set -e

MINIO_ALIAS="local"
MINIO_URL="http://minio:9000"

echo "== Attente démarrage MinIO..."
until mc alias set "${MINIO_ALIAS}" "${MINIO_URL}" "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}" 2>/dev/null; do
    sleep 2
done
echo "== MinIO disponible."


# 1. Configurer les paramètres globaux de sécurité
mc anonymous set none "${MINIO_ALIAS}"

echo "== Politiques anonymes désactivées."


# 2. Créer le bucket système (logs d'audit internes)
mc mb --ignore-existing "${MINIO_ALIAS}/system-logs"
mc anonymous set none "${MINIO_ALIAS}/system-logs"


# 3. Créer un utilisateur de service pour l'API
mc admin user add "${MINIO_ALIAS}" \
    "${MINIO_API_USER:-api_service}" \
    "${MINIO_API_PASSWORD:-ChangeAPIPassword!}" 2>/dev/null || true


# 4. Créer et appliquer la politique pour l'utilisateur API
cat /policies/api-service-policy.json | \
    mc admin policy create "${MINIO_ALIAS}" api-service-policy /dev/stdin 2>/dev/null || \
mc admin policy create "${MINIO_ALIAS}" api-service-policy /policies/api-service-policy.json

mc admin policy attach "${MINIO_ALIAS}" api-service-policy \
    --user "${MINIO_API_USER:-api_service}"

echo "== Utilisateur API créé avec politique restreinte."


# 5. Créer un bucket de démonstration avec quota 500 Mo
DEMO_BUCKET="${MINIO_ALIAS}/user-demo"
mc mb --ignore-existing "${DEMO_BUCKET}"
mc anonymous set none "${DEMO_BUCKET}"

# Appliquer le quota (500 Mo par défaut via variable)
mc quota set "${DEMO_BUCKET}" --size "${MINIO_QUOTA_MB}MiB"

echo "== Bucket demo créé avec quota ${MINIO_QUOTA_MB} Mo."


# 6. Activer les logs d'audit MinIO vers stdout
mc admin config set "${MINIO_ALIAS}" logger_webhook:audit \
    endpoint="http://loki:3100/loki/api/v1/push" 2>/dev/null || true

echo "== Initialisation MinIO terminée."
mc admin info "${MINIO_ALIAS}"