import logging
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt
from datetime import datetime, timedelta
from ..models import OTPRequest, OTPVerify, TokenResponse
from ..services.otp_service import OTPService
from ..config import settings


router = APIRouter(prefix="/auth", tags=["authentication"])
security = HTTPBearer()
otp_service = OTPService()
logger = logging.getLogger(__name__)


@router.post("/request-otp", response_model=dict)
async def request_otp(request: OTPRequest):
    """Demande un code OTP pour un email"""
    try:
        otp = await otp_service.create_otp(request.email)
        return {"message": "Code OTP envoyé", "email": request.email}
    except Exception as e:
        logger.error(f"Erreur OTP: {e}")
        raise HTTPException(500, "Erreur lors de la génération OTP")


@router.post("/verify-otp", response_model=TokenResponse)
async def verify_otp(request: OTPVerify):
    """Vérifie l'OTP et retourne un token JWT"""
    # Vérifier l'OTP
    is_valid = await otp_service.verify_otp(request.email, request.otp)
    
    if not is_valid:
        raise HTTPException(401, "Code OTP invalide ou expiré")
    
    # Créer le token JWT
    expires_delta = timedelta(seconds=settings.otp_expiry_seconds)
    expire = datetime.utcnow() + expires_delta
    
    to_encode = {
        "sub": request.email,
        "exp": expire,
        "type": "access"
    }
    
    encoded_jwt = jwt.encode(
        to_encode, 
        settings.jwt_secret, 
        algorithm=settings.jwt_algorithm
    )
    
    return TokenResponse(
        access_token=encoded_jwt,
        expires_in=settings.otp_expiry_seconds
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    """Dépendance pour obtenir l'utilisateur courant"""
    token = credentials.credentials
    
    try:
        payload = jwt.decode(
            token, 
            settings.jwt_secret, 
            algorithms=[settings.jwt_algorithm]
        )
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(401, "Token invalide")
        return email
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expiré")
    except jwt.JWTError:
        raise HTTPException(401, "Token invalide")