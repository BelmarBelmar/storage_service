import re
import hashlib
import logging
from minio import Minio
from minio.error import S3Error
from typing import BinaryIO
from fastapi import HTTPException
from ..config import settings
from datetime import timedelta


logger = logging.getLogger(__name__)

class MinioService:
    def __init__(self):
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure
        )
    

    def _normalize_bucket_name(self, user_id: str) -> str:
        """
        Normalise un email en nom de bucket valide pour MinIO: minuscules, chiffres, traits d'union uniqument
        """
        # Remplacer @ et . par des traits d'union
        normalized = user_id.lower().replace('@', '-').replace('.', '-')
        
        # Supprimer les caractères non autorisés
        normalized = re.sub(r'[^a-z0-9-]', '', normalized)
        
        # Supprimer les traits d'union multiples ou en début/fin
        normalized = re.sub(r'-+', '-', normalized).strip('-')
        
        # Ajoute un préfixe pour éviter les noms trop courts ou numériques
        bucket_name = f"{settings.minio_bucket_prefix}{normalized}"
        
        # MinIO exiges des noms entre 3 et 63 caractères
        if len(bucket_name) < 3:
            bucket_name = f"{bucket_name}-bucket"
        if len(bucket_name) > 63:
            # Utiliser un hash si trop long
            hash_suffix = hashlib.md5(user_id.encode()).hexdigest()[:8]
            bucket_name = f"{settings.minio_bucket_prefix}{hash_suffix}"
        
        return bucket_name
    

    def get_user_bucket(self, user_id: str) -> str:
        """Retourne le nom du bucket pour un utilisateur"""
        return self._normalize_bucket_name(user_id)
    

    async def ensure_user_bucket(self, user_id: str):
        """Crée le bucket utilisateur s'il n'existe pas"""
        bucket_name = self.get_user_bucket(user_id)
        try:
            if not self.client.bucket_exists(bucket_name):
                self.client.make_bucket(bucket_name)
                logger.info(f"Bucket créé pour l'utilisateur {user_id}: {bucket_name}")
                
                # définir une politique de quota par défaut
                try:
                    self.client.set_bucket_quota(
                        bucket_name,
                        quota=settings.max_file_size_mb * 1024 * 1024
                    )
                except:
                    pass
        except S3Error as e:
            logger.error(f"Erreur création bucket {bucket_name}: {e}")
            raise
    
    
    async def stream_upload(self, user_id: str, file_name: str, file_data: BinaryIO, file_size: int, content_type: str) -> str:
        """Upload un fichier en streaming direct vers MinIO"""
        bucket_name = self.get_user_bucket(user_id)
        await self.ensure_user_bucket(user_id)
        
        result = self.client.put_object(
            bucket_name,
            file_name,
            file_data,
            file_size,
            content_type=content_type
        )
        
        return result.object_name
    
    async def generate_download_url(self, user_id: str, file_name: str, expires: int = settings.presigned_url_expiry) -> str:
        """Génère une URL pré-signée pour téléchargement"""
        bucket_name = self.get_user_bucket(user_id)
        
        try:
            # Vérifier que le fichier existe
            try:
                self.client.stat_object(bucket_name, file_name)
            except S3Error as e:
                if e.code == "NoSuchKey":
                    raise HTTPException(404, "Fichier non trouvé")
                raise
            
            # Générer l'URL avec timedelta
            expiry = timedelta(seconds=expires)
            url = self.client.presigned_get_object(
                bucket_name,
                file_name,
                expires=expiry
            )
            
            logger.info(f"URL générée (interne): {url}")
            return url
            
        except S3Error as e:
            logger.error(f"Erreur S3: {e}")
            raise HTTPException(500, f"Erreur lors de la génération de l'URL: {str(e)}")
        except Exception as e:
            logger.error(f"Erreur inattendue: {e}")
            raise HTTPException(500, f"Erreur lors de la génération de l'URL: {str(e)}")


    async def get_file_info(self, user_id: str, file_name: str) -> dict:
        """Récupère les infos d'un fichier"""
        bucket_name = self.get_user_bucket(user_id)
        try:
            obj = self.client.stat_object(bucket_name, file_name)
            return {
                "name": obj.object_name,
                "size": obj.size,
                "last_modified": obj.last_modified,
                "content_type": obj.content_type,
                "etag": obj.etag.strip('"')
            }
        except S3Error as e:
            if e.code == "NoSuchKey":
                return None
            raise
    

    async def list_user_files(self, user_id: str, prefix: str = "") -> list:
        """Liste les fichiers d'un utilisateur"""
        bucket_name = self.get_user_bucket(user_id)
        try:
            objects = self.client.list_objects(bucket_name, prefix=prefix, recursive=True)
            
            files = []
            for obj in objects:
                files.append({
                    "name": obj.object_name,
                    "size": obj.size,
                    "last_modified": obj.last_modified,
                    "etag": obj.etag.strip('"') if obj.etag else None
                })
            return files
        except S3Error as e:
            if e.code == "NoSuchBucket":
                return []
            raise