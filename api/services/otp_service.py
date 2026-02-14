import secrets
import string
import hmac
import time
import logging
from datetime import datetime
from ..config import settings


logger = logging.getLogger(__name__)

class OTPService:
    def __init__(self):
        self._otp_store = {}
    

    def _generate_otp(self) -> str:
        """Génère un code OTP sécurisé"""
        alphabet = string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(settings.otp_length))
    

    async def create_otp(self, email: str) -> str:
        """Crée un OTP pour un email"""
        otp = self._generate_otp()
        expiry = time.time() + settings.otp_expiry_seconds
        
        self._otp_store[email] = {
            "code": otp,
            "expiry": expiry
        }

        # simulation de mail dans les logs
        logger.info(f"OTP pour {email}: {otp} (valide {settings.otp_expiry_seconds}s)")
        
        # Simuler un envoi d'email
        await self._simulate_email_send(email, otp)
        
        return otp
    

    async def verify_otp(self, email: str, code: str) -> bool:
        """Vérifie un code OTP"""
        if email not in self._otp_store:
            return False
        
        stored = self._otp_store[email]
        
        # Vérifier expiration
        if time.time() > stored["expiry"]:
            del self._otp_store[email]
            return False
        
        # Vérification constante en temps pour éviter timing attacks
        if hmac.compare_digest(stored["code"], code):
            del self._otp_store[email]
            return True
        
        return False
    

    async def _simulate_email_send(self, email: str, otp: str):
        """Simule l'envoi d'email (logs uniquement)"""
        logger.info(f"[EMAIL SIMULÉ] À: {email}, Sujet: Votre code OTP, Corps: {otp}")
        
        # écrire dans un fichier pour faciliiter les tests
        with open("/tmp/otp_logs.txt", "a") as f:
            f.write(f"{datetime.now()}: {email} -> {otp}\n")