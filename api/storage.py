import asyncio
import io
import re
import structlog
from datetime import timedelta
from typing import Any
from minio import Minio
from minio.commonconfig import Tags
from minio.error import S3Error


logger = structlog.get_logger()


class StorageService:
    """Service de stockage MinIO - Zero Trust."""

    def __init__(self, client: Minio):
        self.client = client

    def get_user_bucket(self, email: str) -> str:
        """Convertit un email en nom de bucket MinIO valide"""
        sanitized = re.sub(r"[^a-z0-9-]", "-", email.lower())
        sanitized = re.sub(r"-+", "-", sanitized).strip("-")
        bucket_name = f"user-{sanitized}"
        # Limiter à 63 caractères
        return bucket_name[:63]

    async def ensure_user_bucket(self, bucket_name: str, quota_mb: int = 500) -> None:
        """Crée le bucket utilisateur et Applique le quota de stockage (500 Mo par défaut)"""
        def _create():
            if not self.client.bucket_exists(bucket_name):
                self.client.make_bucket(bucket_name)
                logger.info("bucket_created", bucket=bucket_name)

            try:
                tags = Tags.new_bucket_tags()
                tags["quota-mb"] = str(quota_mb)
                tags["owner-email-hint"] = bucket_name
                self.client.set_bucket_tags(bucket_name, tags)
            except S3Error:
                pass  # Tags non critiques

        await asyncio.to_thread(_create)

    async def upload_stream(self, bucket_name: str, object_name: str, data: bytes, size: int, content_type: str, metadata: dict[str, str] | None = None) -> None:
        """Upload les bytes directement vers MinIO en streaming"""
        def _upload():
            self.client.put_object(
                bucket_name=bucket_name,
                object_name=object_name,
                data=io.BytesIO(data),
                length=size,
                content_type=content_type,
                metadata=metadata or {},
            )

        await asyncio.to_thread(_upload)
        logger.info(
            "object_uploaded",
            bucket=bucket_name,
            object=object_name,
            size=size,
        )

    async def generate_presigned_url(self, bucket_name: str, object_name: str, expiry_seconds: int = 900) -> str:
        """Génère une pre-signed URL"""
        def _presign():
            return self.client.presigned_get_object(
                bucket_name=bucket_name,
                object_name=object_name,
                expires=timedelta(seconds=expiry_seconds),
            )

        url = await asyncio.to_thread(_presign)
	# Remplacer l'URL interne MinIO par l'URL publique
        url = url.replace("http://minio:9000", "https://s3.zerotrust.local")

        logger.info(
            "presigned_url_created",
            bucket=bucket_name,
            object=object_name,
            expiry_seconds=expiry_seconds,
        )
        return url

    async def stat_object(self, bucket_name: str, object_name: str) -> Any:
        """Récupère les métadonnées d'un objet."""
        def _stat():
            return self.client.stat_object(bucket_name, object_name)

        return await asyncio.to_thread(_stat)

    async def list_objects(self, bucket_name: str) -> list[dict]:
        """Liste les objets d'un bucket."""
        def _list():
            objects = self.client.list_objects(bucket_name, recursive=True)
            return [
                {
                    "object_name": obj.object_name,
                    "size_bytes": obj.size,
                    "last_modified": obj.last_modified.isoformat() if obj.last_modified else None,
                    "etag": obj.etag,
                }
                for obj in objects
            ]

        return await asyncio.to_thread(_list)

    async def delete_object(self, bucket_name: str, object_name: str) -> None:
        """Supprime un objet."""
        def _delete():
            self.client.remove_object(bucket_name, object_name)

        await asyncio.to_thread(_delete)
        logger.info("object_deleted", bucket=bucket_name, object=object_name)