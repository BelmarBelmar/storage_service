#!/bin/bash

# Couleurs
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "=== Test de l'API ==="


# Demander un OTP
echo -e "\n${GREEN}1. Demande d'OTP...${NC}"
curl -s -X POST http://localhost:8000/auth/request-otp \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com"}'


# Attendre un peu et récupérer l'OTP des logs
echo -e "\n${GREEN}2. Récupération de l'OTP depuis les logs...${NC}"
sleep 2
OTP_LINE=$(docker compose logs api --tail 20 | grep "OTP pour" | tail -1)
OTP=$(echo $OTP_LINE | grep -oE '[0-9]{6}' | tail -1)

if [ -z "$OTP" ]; then
    echo -e "${RED}Erreur: Impossible de récupérer l'OTP${NC}"
    exit 1
fi

echo "OTP trouvé: $OTP"


# Vérifier l'OTP et obtenir le token
echo -e "\n${GREEN}3. Vérification OTP et obtention du token...${NC}"
RESPONSE=$(curl -s -X POST http://localhost:8000/auth/verify-otp \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"test@example.com\", \"otp\": \"$OTP\"}")

TOKEN=$(echo $RESPONSE | jq -r .access_token)

if [ "$TOKEN" = "null" ] || [ -z "$TOKEN" ]; then
    echo -e "${RED}Erreur: Token non reçu${NC}"
    echo "Réponse: $RESPONSE"
    exit 1
fi

echo "Token recu: ${TOKEN:0:20}..."


# Uploader un fichier
echo -e "\n${GREEN}4. Upload du fichier...${NC}"
if [ ! -f "./test-image.jpg" ]; then
    echo "Création d'un fichier de test..." # au cas où le fichier serai absent dans le repertoire
    echo "Ceci est un fichier de test" > ./test.txt
    FILE="./test.txt"
else
    FILE="./test-image.jpg"
fi

UPLOAD_RESPONSE=$(curl -s -X POST http://localhost:8000/files/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@$FILE")

echo "Réponse upload: $UPLOAD_RESPONSE"


# Lister les fichiers
echo -e "\n${GREEN}5. Liste des fichiers...${NC}"
curl -s -X GET http://localhost:8000/files/ \
  -H "Authorization: Bearer $TOKEN" | jq .


# Obtenir une URL de téléchargement
FILENAME=$(basename $FILE)
echo -e "\n${GREEN}6. Génération URL de téléchargement pour $FILENAME...${NC}"
curl -s -X GET "http://localhost:8000/files/download/$FILENAME" \
  -H "Authorization: Bearer $TOKEN" | jq .

echo "Réponse: $RESPONSE"

# Extraire l'URL et la convertir
INTERNAL_URL=$(echo $RESPONSE | jq -r .url)
if [ "$INTERNAL_URL" != "null" ] && [ ! -z "$INTERNAL_URL" ]; then
    # Remplacer minio:9000 par l'IP publique
    PUBLIC_URL=$(echo $INTERNAL_URL | sed 's/minio:9000/192.168.122.91/')
    PUBLIC_URL=$(echo $PUBLIC_URL | sed 's/http:/https:/')
    
    echo "URL interne: $INTERNAL_URL"
    echo "URL publique: $PUBLIC_URL"
    
    # Télécharger le fichier
    curl -k -L "$PUBLIC_URL" --output downloaded_${FILENAME}
    
    if [ -f "downloaded_${FILENAME}" ]; then
        echo "Fichier téléchargé: downloaded_${FILENAME}"
        file "downloaded_${FILENAME}"
    fi
else
    echo "Erreur: $RESPONSE"
fi


# Teste de vérification d'envoi de fichier invalide
echo -e "\n${GREEN}Teste de vérification d'envoi de fichier INVALIDE...${NC}"
echo -e "\n${GREEN}7. Upload du fichier INVALIDE...${NC}"
UPLOAD_RESPONSE=$(curl -s -X POST http://localhost:8000/files/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@./test.exe")

echo "$UPLOAD_RESPONSE"

echo -e "\n${GREEN}8. Upload d'un fichier valide pour confirmationn...${NC}"
UPLOAD_RESPONSE=$(curl -s -X POST http://localhost:8000/files/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@./test-valid.txt")
echo "$UPLOAD_RESPONSE"


echo -e "\n${GREEN}Test terminé !${NC}"