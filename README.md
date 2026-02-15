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

### 3. Réseau
* Adresse IP fixe : 192.168.122.91 (à adapter à votre environnement)

### 4. Installation
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
openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout nginx/certs/server.key -out nginx/certs/server.crt
```

5. Configuration du fichier nginx/nginx.conf

À ce niveau, allez juste dans le fichier et remplacez toutes les occurences de l'adresse IP 192.168.122.91 par l'adresse IP de votre VM.


6. Lancement de la stack

```bash
docker compose pull
docker compose up -d

# Vérifier que tous les conteneurs sont lancés
docker compose ps
```


7. Initialisation de la base de données

COnfiguration simple:

```bash
docker exec -it storage_postgres psql -U postgres -c "CREATE ROLE anon nologin; CREATE ROLE authenticated nologin; CREATE ROLE service_role nologin;"
```

`Déboguage:` Au cas où vous aurez des problèmes avec la base de données après lancement, essayez ceci:

```bash
docker exec -it storage_postgres psql -U postgres -d storage_db -c "
CREATE SCHEMA IF NOT EXISTS auth;

DO \$\$ BEGIN
    CREATE TYPE auth.factor_type AS ENUM ('totp', 'webauthn', 'phone');
EXCEPTION WHEN duplicate_object THEN null; END \$\$;

DO \$\$ BEGIN
    CREATE TYPE auth.factor_status AS ENUM ('unverified', 'verified');
EXCEPTION WHEN duplicate_object THEN null; END \$\$;

DO \$\$ BEGIN
    CREATE TYPE auth.aal_level AS ENUM ('aal1', 'aal2', 'aal3');
EXCEPTION WHEN duplicate_object THEN null; END \$\$;

DO \$\$ BEGIN
    CREATE TYPE auth.code_challenge_method AS ENUM ('s256', 'plain');
EXCEPTION WHEN duplicate_object THEN null; END \$\$;
"
```


8. Configuration MinIO

```bash
# Installer MinIO Client
wget https://dl.min.io/client/mc/release/linux-amd64/mc
chmod +x mc
sudo mv mc /usr/local/bin/

# Configurer l'alias
mc alias set local http://192.168.122.91:9000 ${MINIO_ROOT_USER} ${MINIO_ROOT_PASSWORD} --api S3v4

# Redéfinir les quotas (optionnel)
mc quota set local/user-test-example-com --size 500MiB

# Vérifier le quota
mc quota info local/user-test-example-com

# Voir l'espace utilisé
mc du local/user-test-example-com

# Lister
mc ls local/user-test-example-com
```


9. Redémarrage

```bash
docker compose down
docker compose up -d
```


10. Vérification

```bash
# Tester l'API
curl http://localhost:8000/health

# Réponse attendue : {"status":"healthy"}



# Tester la console MinIO (navigateur)
# Ouvrir https://192.168.122.91/console/
# Se connecter avec admin / [mot de passe défini dans .env]
```



## Utilisation de l'API
### Authentification OTP
1. Demander un code OTP

```bash
curl -X POST http://localhost:8000/auth/request-otp \
  -H "Content-Type: application/json" \
  -d '{"email": "utilisateur@exemple.com"}'
```

2. Récupération de l'OTP

```bash
docker compose logs api | grep OTP
# Exemple de résultat : "OTP pour utilisateur@exemple.com: 483729 (valide 300s)"
```

3. Valider l'OTP et obtenir le token

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/verify-otp \
  -H "Content-Type: application/json" \
  -d '{"email": "utilisateur@exemple.com", "otp": "483729"}' | jq -r .access_token)

echo $TOKEN
# eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```


### Gestion des fichiers
1. Upload de fichier

```bash
curl -X POST http://localhost:8000/files/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@./test-image.jpg"
# le fichier test-image.jpg est dans le répertoire actuel. Vous pouvez le changer en mettant le chemin(@/chemin/vers/fichier)
```

2. Lister les fichiers
```bash
curl -X GET http://localhost:8000/files/ \
  -H "Authorization: Bearer $TOKEN" | jq .
```

3. Obtenir une URL de téléchargement

```bash
curl -X GET "http://localhost:8000/files/download/image.jpg" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

4. Tester le téléchargement avec l'url obtenue

```bash
curl -k -L "url_obtenue" --output downloaded_image.jpg


# Vérifier l'intégrité
md5sum test-image.jpg downloaded_image.jpg
# Les deux hash doivent être identiques
```

5. Script de test complet

Un script de test complet (`test_api.sh`) est disponible dans le répertoire dans le but d'automatiser les tests avec les fichiers.
Pour l'utiliser, remplacer toutes les occurences de l'adresse IP 192.168.122.91 par l'adresse IP de votre VM.

```bash
chmod +x test_api.sh
./test_api.sh
```



### Logs centralisés
Analyser les logs Nginx

```bash
tail -f logs/nginx/access.log
```


## Commandes Docker utiles
Quelques commandes utiles, qui pourront aider en cas de déboguage

```bash
# Voir l'état des conteneurs
docker compose ps

# Voir les logs
docker compose logs -f api        # API en temps réel
docker compose logs -f nginx      # Logs Nginx
docker compose logs -f minio      # Logs MinIO

# Redémarrer un service
docker compose restart api

# Arrêter tous les services
docker compose down

# Démarrer tous les services
docker compose up -d

# Reconstruire l'API après modification
docker compose build api
docker compose up -d api

# Arrêter et supprimer tout
docker compose down -v  # -v supprime aussi les volumes
```