import magic
import os
import logging
from fastapi import HTTPException, UploadFile
from typing import Tuple
from ..config import settings


logger = logging.getLogger(__name__)

class FileValidator:
    @staticmethod
    async def validate_file(file: UploadFile) -> Tuple[str, int, str]:
        """
        Valide un fichier et retourne (extension, taille, mime_type) ou
        Lève HTTPException si invalide
        """
        #Vérifier l'extension
        filename = file.filename
        ext = os.path.splitext(filename)[1].lower()
        
        if ext not in settings.allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Extension {ext} non autorisée. Extensions autorisées: {settings.allowed_extensions}"
            )
        
        # Vérifier la taille
        content = await file.read()
        file_size = len(content)
        
        if file_size > settings.max_file_size_mb * 1024 * 1024:
            raise HTTPException(
                status_code=400,
                detail=f"Fichier trop grand. Maximum: {settings.max_file_size_mb}MB"
            )
        
        # Vérifier le type MIME réel
        mime_type = magic.from_buffer(content, mime=True)
        
        if mime_type not in settings.allowed_mime_types:
            raise HTTPException(
                status_code=400,
                detail=f"Type MIME {mime_type} non autorisé"
            )
        
        # Remettre le curseur au début pour le streaming
        await file.seek(0)
        
        return ext, file_size, mime_type
    

    @staticmethod
    def validate_filename(filename: str) -> str:
        """Nettoie et valide le nom de fichier"""
        filename = os.path.basename(filename)
        
        # Remplacer les caractères problématiques
        filename = "".join(c for c in filename if c.isalnum() or c in "._- ")
        
        if not filename:
            raise HTTPException(400, "Nom de fichier invalide")
        
        return filename