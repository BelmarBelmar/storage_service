import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from typing import Optional
from ..models import FileInfo, FileListResponse, UploadResponse, DownloadUrlResponse
from ..services.minio_service import MinioService
from ..services.validation import FileValidator
from .auth import get_current_user


router = APIRouter(prefix="/files", tags=["files"])
minio_service = MinioService()
validator = FileValidator()
logger = logging.getLogger(__name__)


@router.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...), user: str = Depends(get_current_user)):
    """
    Upload un fichier avec validation complete (taille, extension, MIME)
    """
    try:
        # Valider le fichier (extension, taille, type MIME)
        ext, file_size, mime_type = await validator.validate_file(file)
        
        # Obtenir le nom séécurisé
        safe_filename = validator.validate_filename(file.filename)
        
        # Upload en streaming vers MinIO
        object_name = await minio_service.stream_upload(
            user_id=user,
            file_name=safe_filename,
            file_data=file.file,
            file_size=file_size,
            content_type=mime_type
        )
        
        # Récupérer les infos pour confirmation
        file_info = await minio_service.get_file_info(user, object_name)
        
        logger.info(f"Upload réussi: {object_name} ({file_size} bytes, {mime_type})")
        
        return UploadResponse(
            file_name=object_name,
            size=file_size,
            bucket=minio_service.get_user_bucket(user),
            etag=file_info["etag"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur upload: {e}")
        raise HTTPException(500, f"Erreur lors de l'upload: {str(e)}")


@router.get("/download/{file_name:path}")
async def download_file(file_name: str, user: str = Depends(get_current_user)):
    """
    Télécharge un fichier directement depuis MinIO
    Génère une URL pré-signée temporaire
    """
    try:
        # Vérifier que le fichier existe
        file_info = await minio_service.get_file_info(user, file_name)
        if not file_info:
            raise HTTPException(404, "Fichier non trouvé")
        
        # Générer URL pré-signée
        url = await minio_service.generate_download_url(user, file_name)
        
        return DownloadUrlResponse(
            url=url,
            expires_in=900,  # 15 minutes
            file_name=file_name,
            file_size=file_info["size"],
            file_hash=file_info["etag"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur téléchargement: {e}")
        raise HTTPException(500, f"Erreur lors du téléchargement: {str(e)}")


@router.get("/", response_model=FileListResponse)
async def list_files(prefix: Optional[str] = Query(None, description="Filtrer par préfixe"), user: str = Depends(get_current_user)):
    """Liste tous les fichiers de l'utilisateur"""
    try:
        files = await minio_service.list_user_files(user, prefix or "")
        
        total_size = sum(f["size"] for f in files)
        
        return FileListResponse(
            files=[FileInfo(**f) for f in files],
            total_size=total_size,
            file_count=len(files)
        )
        
    except Exception as e:
        logger.error(f"Erreur liste fichiers: {e}")
        raise HTTPException(500, "Erreur lors de la récupération des fichiers")


@router.get("/info/{file_name:path}", response_model=FileInfo)
async def file_info(file_name: str, user: str = Depends(get_current_user)):
    """Récupère les informations d'un fichier"""
    try:
        file_info = await minio_service.get_file_info(user, file_name)
        if not file_info:
            raise HTTPException(404, "Fichier non trouvé")
        
        return FileInfo(**file_info)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur infos fichier: {e}")
        raise HTTPException(500, "Erreur lors de la récupération des informations")