from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # MinIO
    minio_endpoint: str = "minio:9000"
    minio_access_key: str
    minio_secret_key: str
    minio_bucket_prefix: str = "user-"
    minio_secure: bool = False  # False car derrière proxy
    
    # JWT et OTP
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    otp_expiry_seconds: int = 300  # 5 minutes
    otp_length: int = 6
    
    # File validation
    max_file_size_mb: int = 500
    allowed_extensions: list = [".jpg", ".jpeg", ".png", ".pdf", ".txt", ".mp4", ".mov"]
    allowed_mime_types: list = [
        "image/jpeg", "image/png", "application/pdf",
        "text/plain", "video/mp4", "video/quicktime"
    ]
    
    # Pre-signed URLs
    presigned_url_expiry: int = 900  # 15 minutes
    
    redis_url: Optional[str] = None
    
    # Email (simulé en logs pour  l'instant)
    smtp_server: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    email_from: str = "noreply@storage.local"
    
    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()