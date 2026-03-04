# storage_service
# Infrastructure de Stockage Souveraine & API Zero-Trust

## Guide de Déploiement

Ce guide est conçu pour permettre à un administrateur système de déployer et maintenir la plateforme de stockage sur une VM vierge.

### 1. Matériels
* Une machine virtuelle sous Ubuntu Server (Ubuntu 22.04 LTS utilisé ici)
* Espace disque: 20 GB

### 2. Logiciels requis
* Docker
* Docker compose
* Git : pour cloner le dépôt
* curl : pour tester l'API
* jq : pour parser le JSON (optionnel)
* MinIO Client (mc)

### 3. Composants
| Composant | Rôle |
|---|---|
| **FastAPI** | Moteur métier Zero-Trust : validation, streaming, orchestration |
| **Supabase Auth (GoTrue)** | Gestion des utilisateurs, envoi OTP, émission JWT |
| **Supabase REST (PostgREST)** | Exposition REST automatique de la table `files` |
| **PostgreSQL** | Persistance des métadonnées fichiers (id, email, sha256, mime, taille…) |
| **MinIO** | Stockage binaire des fichiers (compatible S3) |
| **Nginx** | Reverse proxy TLS, routing des 5 domaines |
| **MailHog** | Serveur SMTP de développement (capture des emails OTP) |
| **Loki + Promtail** | Agrégation et collecte des logs |
| **Grafana** | Visualisation des logs centralisés |

### 4. Déploiement
1. Mise à jour du système et installation des logiciels réquis

Tapez dans votre terminal ubuntu les commandes ci-après
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install curl git docker.io docker-compose jq -y
sudo usermod -aG docker $USER
newgrp docker
docker --version   # pour Vérifier si c'est bien installé
docker compose version
```

`Déboguage:` Si même après cela, la commande `docker compose` ne marche pas chez vous, faites ceci:

```bash
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install docker-compose-plugin
```

Une fois que vous aurez tous les logiciels requis installés, vous pouvez passer à l'étape suivante.


2. Récupération du code source

```bash
git clone https://github.com/BelmarBelmar/storage_service.git
cd storage_service
```


3. Configuration de l'environnement

```bash
cp .env.example .env

# Éditer avec vos valeurs
nano .env
```


4. Génération des certificats TLS

```bash
mkdir -p nginx/certs
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/certs/zerotrust.key \
  -out nginx/certs/zerotrust.crt \
  -subj "/CN=zerotrust.local" \
  -addext "subjectAltName=DNS:zerotrust.local,DNS:s3.zerotrust.local,DNS:console.zerotrust.local,DNS:monitoring.zerotrust.local,DNS:mail.zerotrust.local"
```

5. Configurer les DNS locaux

```bash
sudo tee -a /etc/hosts << EOF
127.0.0.1  zerotrust.local
127.0.0.1  s3.zerotrust.local
127.0.0.1  console.zerotrust.local
127.0.0.1  monitoring.zerotrust.local
127.0.0.1  mail.zerotrust.local
EOF
```


6. Lancement de la stack

```bash
docker compose pull
docker compose up -d

# Vérifier que tous les conteneurs sont lancés
docker compose ps
```


7. Initialiser la base de données

La table `files` est créée automatiquement via `supabase/init.sql` au premier démarrage. Pour vérifier :

```bash
docker exec supabase-db psql -U postgres -c "\dt public.*"
```


8. Appliquer le quota MinIO (500 Mo par utilisateur)

```bash
docker exec minio mc alias set local http://localhost:9000 \
  ${MINIO_ROOT_USER} ${MINIO_ROOT_PASSWORD}
docker exec minio mc quota set local/user-test-example-com --size 500MiB
```


9. Vérification

```bash
# Tester l'API
curl http://localhost:8000/health

# Réponse attendue : {"status":"ok","service":"zerotrust-api"}
```


### URLs d'accès (tester aussi dans le navigateur)

| Service | URL |
|---|---|
| **API Health** | https://zerotrust.local/api/health |
| **MinIO Console** | https://console.zerotrust.local |
| **MailHog** | https://mail.zerotrust.local |
| **Grafana** | https://monitoring.zerotrust.local |



## Utilisation de l'API
### Authentification OTP
1. Demander un code OTP

```bash
curl -k -s -X POST https://zerotrust.local/api/auth/request-otp \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com"}' | jq .
```

2. Récupérer l'OTP depuis MailHog

```bash
OTP=$(docker exec mailhog wget -qO- http://localhost:8025/api/v2/messages \
  | jq -r '.items[0].MIME.Parts[0].Body' \
  | tr -d '\r\n' \
  | base64 -d \
  | grep -oP '\b\d{6}\b' | head -1)
echo "OTP: $OTP"
```

3. Valider l'OTP et obtenir un JWT

```bash
TOKEN=$(curl -k -s -X POST \
  "https://zerotrust.local/api/auth/verify-otp?email=test@example.com&otp_code=${OTP}" \
  | jq -r '.access_token')
echo "TOKEN: ${TOKEN:0:20}..."
```



### Gestion des fichiers
1. Upload de fichier

```bash
echo "Contenu de test" > /tmp/test.txt

UPLOAD=$(curl -k -s -X POST https://zerotrust.local/api/files/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/tmp/test.txt")
echo $UPLOAD | jq .
FILE_ID=$(echo $UPLOAD | jq -r '.file_id')
```


2. Vérifier les métadonnées dans PostgreSQL

```bash
docker exec supabase-db psql -U postgres \
  -c "SELECT id, user_email, filename, size_bytes, mime_type, uploaded_at FROM public.files;"
```


3. Lister ses fichiers

```bash
curl -k -s https://zerotrust.local/api/files/ \
  -H "Authorization: Bearer $TOKEN" | jq .
```


4. Obtenir une pre-signed URL et télécharger

```bash
DL=$(curl -k -s \
  "https://zerotrust.local/api/files/${FILE_ID}/download?filename=test.txt" \
  -H "Authorization: Bearer $TOKEN")
echo $DL | jq .

DOWNLOAD_URL=$(echo $DL | jq -r '.download_url')
SHA256_EXPECTED=$(echo $DL | jq -r '.sha256')

curl -k -s "$DOWNLOAD_URL" -o /tmp/fichier_recu.txt

SHA256_ACTUAL=$(sha256sum /tmp/fichier_recu.txt | cut -d' ' -f1)
[ "$SHA256_EXPECTED" = "$SHA256_ACTUAL" ] \
  && echo "INTÉGRITÉ VÉRIFIÉE" \
  || echo "HASH DIFFÉRENT"
```


5. Tests de sécurité

```bash
# Upload sans token
curl -k -s -X POST https://zerotrust.local/api/files/upload \
  -F "file=@/tmp/test.txt" | jq .

# Extension interdite
curl -k -s -X POST https://zerotrust.local/api/files/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@script.sh" | jq .

# Token invalide
curl -k -s https://zerotrust.local/api/files/ \
  -H "Authorization: Bearer token_invalide" | jq .
```

6. Script de test complet

Un script de test complet (`test_api.sh`) est disponible dans le répertoire dans le but d'automatiser les tests avec les fichiers.

```bash
chmod +x test_api.sh
bash test_api.sh
```



---

## Déboguage

**supabase-auth en boucle de redémarrage**
```bash
# Créer le rôle requis par GoTrue
docker exec supabase-db psql -U postgres -c "
CREATE SCHEMA IF NOT EXISTS auth;
CREATE ROLE supabase_auth_admin WITH LOGIN PASSWORD 'votre_password' SUPERUSER;
GRANT ALL ON SCHEMA auth TO supabase_auth_admin;
"
# S'assurer que PostgreSQL écoute sur toutes les interfaces
docker exec supabase-db psql -U postgres -c "ALTER SYSTEM SET listen_addresses = '*';"
docker compose restart db auth
```

**L'API ne se connecte pas à PostgreSQL**
```bash
docker exec supabase-db psql -U postgres -c "SHOW listen_addresses;"
# Doit retourner '*'
```

**MinIO - Erreur SignatureDoesNotMatch**
```bash
# La variable MINIO_SERVER_URL doit être absente du docker-compose.yml
grep MINIO_SERVER_URL docker-compose.yml
```

**Tout réinitialiser**
```bash
docker compose down -v
sudo rm -rf data/postgres/*
docker compose up -d
```

---