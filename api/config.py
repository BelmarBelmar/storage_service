from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # MinIO
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "minio_admin"
    minio_secret_key: str = "changeme"
    minio_secure: bool = False
    minio_bucket_prefix: str = "user"
    minio_quota_mb: int = 500
    database_url: str = "postgresql+asyncpg://postgres:changeme@db:5432/postgres"

    # Auth-JWT
    jwt_secret: str = "changeme_jwt_secret"
    jwt_algorithm: str = "HS256"
    jwt_expiry_seconds: int = 3600

    # OTP
    otp_expiry_seconds: int = 300
    otp_length: int = 6

    # SMTP
    smtp_host: str = "mailhog"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_from: str = "noreply@zerotrust.local"

    # Fichiers
    max_file_size_mb: int = 100
    presigned_url_expiry_seconds: int = 900  # 15 mins

    # CORS
    allowed_origins: list[str] = ["https://zerotrust.local"]

    # Dev
    debug: bool = False


settings = Settings()