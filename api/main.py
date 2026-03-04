"""
Endpoints dispos:
  POST /auth/request-otp    : Demander un code OTP
  POST /auth/verify-otp     : Valider le code rt obtenir JWT
  POST /files/upload        : Uploader un fichier (JWT requis)
  GET  /files/{file_id}     : Obtenir une pre-signed URL
  GET  /files/              : Lister ses fichiers
  DELETE /files/{file_id}   : Supprimer un fichier
"""

import hashlib, os, secrets, uuid, magic, structlog
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from minio import Minio
from minio.error import S3Error
from pydantic import EmailStr
from auth import TokenResponse, UserEmail, create_access_token, get_current_user, otp_store, send_otp_email
from config import settings
from storage import StorageService
from database import insert_file_metadata, list_user_files, delete_file_metadata


structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ]
)
logger = structlog.get_logger()


# Client MinIO
minio_client: Minio | None = None
storage_service: StorageService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global minio_client, storage_service
    minio_client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    storage_service = StorageService(minio_client)
    from database import get_pool
    await get_pool()
    logger.info("startup", minio_endpoint=settings.minio_endpoint)
    yield
    logger.info("shutdown")


app = FastAPI(
    title="ZeroTrust File Transfer API",
    description="API de transfert de fichiers sécurisée — Zero Trust Architecture",
    version="1.0.0",
    docs_url=None,
    redoc_url="/redoc",
    root_path="/api",
    root_path_in_servers=False,
    lifespan=lifespan,
)

# CORS — restreint aux origines autorisées
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)



@app.post("/auth/request-otp", summary="Demander un code OTP par email", tags=["Authentification OTP"])
async def request_otp(body: UserEmail, request: Request):
    """Génère un code OTP à 6 chiffres, l'envoie par email"""
    otp_code = secrets.randbelow(10**settings.otp_length)
    otp_str = str(otp_code).zfill(settings.otp_length)

    # Stocker l'OTP avec expiration
    expiry = datetime.now(timezone.utc) + timedelta(seconds=settings.otp_expiry_seconds)
    otp_store[body.email] = {"code": otp_str, "expiry": expiry}

    # Envoyer par email
    await send_otp_email(body.email, otp_str)

    logger.info( # Pour debug
        "otp_generated",
        email=body.email,
        otp_preview=f"{otp_str[:2]}****",
        client_ip=request.client.host,
    )

    return {
        "message": f"Code OTP envoyé à {body.email}",
        "expires_in_seconds": settings.otp_expiry_seconds,
        "_dev_otp": otp_str if settings.debug else None,
    }


@app.post("/auth/verify-otp", response_model=TokenResponse, summary="Valider l'OTP et obtenir un JWT", tags=["Authentification OTP"])
async def verify_otp(email: EmailStr, otp_code: str, request: Request):
    """Valide le code OTP soumis"""
    stored = otp_store.get(email)

    if not stored:
        logger.warning("otp_not_found", email=email, client_ip=request.client.host)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Aucun OTP en attente pour cet email. Veuillez en demander un nouveau.",
        )

    # Vérifier l'expiration
    if datetime.now(timezone.utc) > stored["expiry"]:
        del otp_store[email]
        logger.warning("otp_expired", email=email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Code OTP expiré. Veuillez en demander un nouveau.",
        )

    # Vérifier le code (comparaison à temps constant pour éviter timing attacks)
    if not secrets.compare_digest(stored["code"], otp_code):
        logger.warning("otp_invalid", email=email, client_ip=request.client.host)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Code OTP invalide.",
        )

    del otp_store[email]

    # Générer le JWT
    token = create_access_token(subject=email)

    logger.info("otp_verified_success", email=email, client_ip=request.client.host)

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.jwt_expiry_seconds,
    )




# Upload en Streaming vers MinIO
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "text/plain",
    "text/csv",
    "application/zip",
    "application/x-zip-compressed",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

ALLOWED_EXTENSIONS = {
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".txt", ".csv", ".zip",
    ".docx", ".xlsx", ".pptx",
}


async def validate_file(file: UploadFile) -> tuple[str, bytes]:
    """Valide le fichier uploadé"""
    # Vérifier l'extension
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Extension '{ext}' non autorisée. Extensions valides : {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # Lire le fichier en mémoire pour valider
    max_size = settings.max_file_size_mb * 1024 * 1024

    chunks = []
    total_size = 0
    
    while True:
        chunk = await file.read(65536)  # 64 Ko par chunk
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > max_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Fichier trop volumineux. Limite : {settings.max_file_size_mb} Mo",
            )
        chunks.append(chunk)

    file_bytes = b"".join(chunks)

    # Détecter le vrai type MIME via magic bytes
    detected_mime = magic.from_buffer(file_bytes[:2048], mime=True)
    
    if detected_mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Type MIME '{detected_mime}' non autorisé. Le contenu réel du fichier ne correspond pas aux types acceptés.",
        )

    return detected_mime, file_bytes


@app.post("/files/upload", summary="Uploader un fichier (streaming vers MinIO)", tags=["Gestion des fichiers"])
async def upload_file(file: UploadFile = File(...), current_user: str = Depends(get_current_user), request: Request = None):
    """Upload un fichier en streaming direct vers MinIO"""
    # Valider le fichier
    mime_type, file_bytes = await validate_file(file)

    # Calculer le hash SHA-256 pour l'intégrité
    sha256_hash = hashlib.sha256(file_bytes).hexdigest()
    file_size = len(file_bytes)

    # Générer un ID unique pour le fichier
    file_id = str(uuid.uuid4())
    safe_filename = f"{file_id}/{file.filename}"

    # Bucket de l'utilisateur 
    bucket_name = storage_service.get_user_bucket(current_user)

    # Créer le bucket si nécessaire et appliquer quota
    await storage_service.ensure_user_bucket(bucket_name, quota_mb=settings.minio_quota_mb)

    # Streaming vers MinIO (pas de fichier temporaire sur disque !)
    await storage_service.upload_stream(
        bucket_name=bucket_name,
        object_name=safe_filename,
        data=file_bytes,
        size=file_size,
        content_type=mime_type,
        metadata={
            "sha256": sha256_hash,
            "original-filename": file.filename or "unknown",
            "uploaded-by": current_user,
            "upload-timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

    await insert_file_metadata(
        file_id=file_id,
        user_email=current_user,
        filename=file.filename or "unknown",
        bucket_name=bucket_name,
        object_name=safe_filename,
        size_bytes=file_size,
        mime_type=mime_type,
        sha256=sha256_hash,
    )

    logger.info(
        "file_uploaded",
        user=current_user,
        file_id=file_id,
        filename=file.filename,
        mime_type=mime_type,
        size_bytes=file_size,
        sha256=sha256_hash,
        client_ip=getattr(request.client, "host", "unknown"),
    )

    return {
        "file_id": file_id,
        "filename": file.filename,
        "size_bytes": file_size,
        "mime_type": mime_type,
        "sha256": sha256_hash,
        "bucket": bucket_name,
        "message": "Fichier uploadé avec succès",
    }


# Distribution Sécurisée via Pre-signed URLs
@app.get("/files/{file_id}/download", summary="Obtenir une pre-signed URL de téléchargement", tags=["Distribution sécurisée"])
async def get_download_url(file_id: str, filename: str, current_user: str = Depends(get_current_user)):
    """Génère une pre-signed URL valide 15 minutes pour télécharger un fichier."""
    bucket_name = storage_service.get_user_bucket(current_user)
    object_name = f"{file_id}/{filename}"

    # Récupérer les métadonnées pour l'intégrité
    try:
        stat = await storage_service.stat_object(bucket_name, object_name)
        sha256 = stat.metadata.get("x-amz-meta-sha256", "")
    except S3Error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Fichier '{filename}' introuvable.",
        )

    # Générer la pre-signed URL
    presigned_url = await storage_service.generate_presigned_url(
        bucket_name=bucket_name,
        object_name=object_name,
        expiry_seconds=settings.presigned_url_expiry_seconds,
    )

    expiry_time = datetime.now(timezone.utc) + timedelta(
        seconds=settings.presigned_url_expiry_seconds
    )

    logger.info(
        "presigned_url_generated",
        user=current_user,
        file_id=file_id,
        expires_at=expiry_time.isoformat(),
    )

    return {
        "download_url": presigned_url,
        "expires_at": expiry_time.isoformat(),
        "expires_in_seconds": settings.presigned_url_expiry_seconds,
        "sha256": sha256,
        "instructions": (
            "Téléchargez le fichier via cette URL avant son expiration. "
            "Vérifiez l'intégrité en comparant le hash SHA-256 du fichier téléchargé."
        ),
    }


@app.get("/files/", summary="Lister les fichiers de l'utilisateur", tags=["Gestion des fichiers"])
async def list_files(current_user: str = Depends(get_current_user)):
    """Liste tous les fichiers"""
    files = await list_user_files(current_user)
    return {
        "files": [
            {
                "file_id": str(f["id"]),
                "filename": f["filename"],
                "size_bytes": f["size_bytes"],
                "mime_type": f["mime_type"],
                "sha256": f["sha256"],
                "uploaded_at": f["uploaded_at"].isoformat(),
            }
            for f in files
        ],
        "total": len(files),
    }


@app.delete("/files/{file_id}", summary="Supprimer un fichier", tags=["Gestion des fichiers"])
async def delete_file(file_id: str, filename: str,current_user: str = Depends(get_current_user)):
    """Supprime un fichier du bucket utilisateur."""
    bucket_name = storage_service.get_user_bucket(current_user)
    object_name = f"{file_id}/{filename}"

    try:
        await storage_service.delete_object(bucket_name, object_name)
        await delete_file_metadata(file_id, current_user)
    except S3Error:
        raise HTTPException(status_code=404, detail="Fichier introuvable.")

    logger.info("file_deleted", user=current_user, file_id=file_id, filename=filename)
    return {"message": "Fichier supprimé avec succès"}


# Health check
@app.get("/health", tags=["Système"])
async def health_check():
    return {"status": "ok", "service": "zerotrust-api"}


# documentation personnalisée (Swagger UI)
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui():
    import swagger_ui_bundle
    swagger_path = swagger_ui_bundle.swagger_ui_path
    with open(f"{swagger_path}/swagger-ui-bundle.js") as f:
        js = f.read()
    with open(f"{swagger_path}/swagger-ui.css") as f:
        css = f.read()
    return HTMLResponse(f"""<!DOCTYPE html>
<html><head><title>ZeroTrust API</title>
<style>{css}</style></head>
<body><div id="swagger-ui"></div>
<script>{js}</script>
<script>
SwaggerUIBundle({{url:"/openapi.json",dom_id:"#swagger-ui",
presets:[SwaggerUIBundle.presets.apis,SwaggerUIBundle.SwaggerUIStandalonePreset],
layout:"BaseLayout",tryItOutEnabled:true}})
</script></body></html>""")
