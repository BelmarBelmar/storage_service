import logging, aiosmtplib, structlog
from datetime import datetime, timedelta, timezone
from typing import Any
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr
from config import settings


logger = structlog.get_logger()


# Format : { email: { "code": "123456", "expiry": datetime } }
otp_store: dict[str, dict] = {}


# Schémas Pydantic
class UserEmail(BaseModel):
    email: EmailStr


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


# JWT
def create_access_token(subject: str) -> str:
    """Crée un JWT signé avec expiration."""
    expire = datetime.now(timezone.utc) + timedelta(seconds=settings.jwt_expiry_seconds)
    payload = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_access_token(token: str) -> dict[str, Any]:
    """Vérifie et décode un JWT. Lève HTTPException si invalide."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        if payload.get("type") != "access":
            raise JWTError("Invalid token type")
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token d'authentification invalide ou expiré.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security),) -> str:
    """Extrait l'email de l'utilisateur à partir du token JWT."""
    payload = verify_access_token(credentials.credentials)
    email = payload.get("sub")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide : sujet manquant.",
        )
    return email


# Envoi d'OTP par email
OTP_EMAIL_TEMPLATE = """\
Bonjour,

Votre code de vérification ZeroTrust est :

    {otp_code}

Ce code est valide pendant {expiry_minutes} minutes.

Si vous n'avez pas demandé ce code, ignorez cet email.

— L'équipe ZeroTrust-Storage_service
"""


async def send_otp_email(to_email: str, otp_code: str) -> None:
    """Envoie le code OTP par email via SMTP"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[ZeroTrust] Code de vérification : {otp_code}"
    msg["From"] = settings.smtp_from
    msg["To"] = to_email

    body = OTP_EMAIL_TEMPLATE.format(
        otp_code=otp_code,
        expiry_minutes=settings.otp_expiry_seconds // 60,
    )
    msg.attach(MIMEText(body, "plain"))

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user or None,
            password=settings.smtp_pass or None,
            start_tls=False,  # MailHog ne supporte pas STARTTLS
        )
        logger.info("otp_email_sent", to=to_email)
    except Exception as e:
        logger.error("otp_email_failed", to=to_email, error=str(e))
        if settings.debug:
            logger.warning(
                "DEV_MODE_OTP",
                otp_code=otp_code,
                email=to_email,
                note="Code affiché car SMTP indisponible en mode debug",
            )