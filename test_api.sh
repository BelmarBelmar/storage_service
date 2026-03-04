#!/bin/bash

# 1. OTP
echo "=== Demande OTP ==="
curl -sk -X POST https://zerotrust.local/api/auth/request-otp \
  -H "Content-Type: application/json" \
  -d '{"email": "test2@example.com"}' > /dev/null
sleep 2

OTP=$(docker exec mailhog wget -qO- http://localhost:8025/api/v2/messages \
  | jq -r '.items[0].MIME.Parts[0].Body' \
  | tr -d '\r\n' \
  | base64 -d \
  | grep -oP '\b\d{6}\b' | head -1)
echo "OTP: $OTP"
echo ""

# 2. JWT
echo "=== Génération du JWT ==="
TOKEN=$(curl -sk -X POST \
  "https://zerotrust.local/api/auth/verify-otp?email=test2@example.com&otp_code=$OTP" \
  | jq -r '.access_token')
echo "TOKEN: ${TOKEN:0:20}..."
echo ""

# 3. Upload
echo "=== Upload de fichier ==="
UPLOAD=$(curl -sk -X POST https://zerotrust.local/api/files/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@./test.txt")
echo $UPLOAD | jq .
FILE_ID=$(echo $UPLOAD | jq -r '.file_id')
echo ""

# 4. Pre-signed URL
echo "=== Génération du pre-signed URL ==="
DL=$(curl -sk "https://zerotrust.local/api/files/$FILE_ID/download?filename=test.txt" \
  -H "Authorization: Bearer $TOKEN")
echo $DL | jq .
DOWNLOAD_URL=$(echo $DL | jq -r '.download_url')
SHA256_EXPECTED=$(echo $DL | jq -r '.sha256')
echo ""

# 5. Téléchargement et vérification de l'intégrité
echo "=== Téléchargement et vérification SHA-256 ==="
curl -sk "$DOWNLOAD_URL" -o fichier_recu.txt
SHA256_ACTUAL=$(sha256sum fichier_recu.txt | cut -d' ' -f1)
echo "SHA256 attendu : $SHA256_EXPECTED"
echo "SHA256 reçu    : $SHA256_ACTUAL"
[ "$SHA256_EXPECTED" = "$SHA256_ACTUAL" ] && echo "INTÉGRITÉ VÉRIFIÉE" || echo "HASH DIFFÉRENT"
echo ""

# 6. Lister ses fichiers
echo "=== Lister ses fichiers ==="
curl -sk https://zerotrust.local/api/files/ \
  -H "Authorization: Bearer $TOKEN" | jq .
echo ""

# 7. Extension non autorisée
echo "=== Test extension non autorisée ==="
curl -sk -X POST https://zerotrust.local/api/files/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@./test_script.sh" | jq .
echo ""

# 8. Upload sans token
echo "=== Test sans token ==="
curl -sk -X POST https://zerotrust.local/api/files/upload \
  -F "file=@./test.txt" | jq .
echo ""
