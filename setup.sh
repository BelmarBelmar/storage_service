set -euo pipefail

MODE="${1:---dev}"
CERTS_DIR="nginx/certs"

echo "============================================================"
echo "  ZeroTrust Storage Platform - Setup"
echo "============================================================"

# 1. Vérifier les dépendances
for cmd in docker openssl; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "ERREUR : '$cmd' requis mais introuvable."
        exit 1
    fi
done


# 2. Créer les répertoires nécessaires
mkdir -p "$CERTS_DIR" nginx/conf.d minio/policies supabase api


# 3. Générer les certificats TLS auto-signés (dev)
if [[ "$MODE" == "--dev" ]]; then
    if [[ ! -f "$CERTS_DIR/zerotrust.crt" ]]; then
        echo "-- Génération des certificats TLS auto-signés..."
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout "$CERTS_DIR/zerotrust.key" \
            -out "$CERTS_DIR/zerotrust.crt" \
            -subj "/C=FR/ST=IDF/L=Paris/O=ZeroTrust/CN=zerotrust.local" \
            -addext "subjectAltName=DNS:zerotrust.local,DNS:*.zerotrust.local,IP:127.0.0.1"
        echo "-- Certificats générés dans $CERTS_DIR/"
    else
        echo "-- Certificats existants conservés."
    fi
fi


# 4. Créer le .env si absent
if [[ ! -f ".env" ]]; then
    echo "-- Création du fichier .env depuis le modèle..."
    cp .env.example .env 2>/dev/null || true
    
    # Générer un JWT_SECRET
    JWT_SECRET=$(openssl rand -base64 64 | tr -d '\n')
    sed -i "s|REPLACE_WITH_STRONG_RANDOM_SECRET_openssl_rand_base64_64|${JWT_SECRET}|" .env
    echo "-- JWT_SECRET généré automatiquement."
    echo "!!! ATTENTION : Changez les mots de passe dans .env avant de déployer !!!"
fi


# 5. Ajouter les entrées /etc/hosts (dev)
if [[ "$MODE" == "--dev" ]]; then
    DOMAINS="zerotrust.local s3.zerotrust.local console.zerotrust.local monitoring.zerotrust.local mail.zerotrust.local"
    for domain in $DOMAINS; do
        if ! grep -q "$domain" /etc/hosts 2>/dev/null; then
            echo "-- Ajout de '127.0.0.1 $domain' dans /etc/hosts (sudo requis)"
            echo "127.0.0.1 $domain" | sudo tee -a /etc/hosts >/dev/null || true
        fi
    done
fi

# 6. Lancer la stack
echo ""
echo "-- Démarrage de la stack Docker..."
docker compose pull --quiet
docker compose up -d --build

echo ""
echo "============================================================"
echo "  Stack démarrée ! URLs disponibles :"
echo ""
echo "  API ZeroTrust  : https://zerotrust.local/docs"
echo "  MinIO Console  : https://console.zerotrust.local"
echo "  MailHog (OTP)  : https://mail.zerotrust.local"
echo "  Grafana Logs   : https://monitoring.zerotrust.local"
echo "============================================================"
