from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime


# Authentification
class OTPRequest(BaseModel):
    email: EmailStr

class OTPVerify(BaseModel):
    email: EmailStr
    otp: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


# Fichiers
class FileInfo(BaseModel):
    name: str
    size: int
    last_modified: datetime
    etag: Optional[str] = None
    content_type: Optional[str] = None

class FileListResponse(BaseModel):
    files: List[FileInfo]
    total_size: int
    file_count: int

class UploadResponse(BaseModel):
    file_name: str
    size: int
    bucket: str
    etag: str

class DownloadUrlResponse(BaseModel):
    url: str
    expires_in: int
    file_name: str
    file_size: int
    file_hash: Optional[str] = None


# Erreurs
class ErrorResponse(BaseModel):
    detail: str
    code: Optional[str] = None