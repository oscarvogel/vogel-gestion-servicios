"""Cifrado de credenciales por empresa.

La API key de la gateway se guarda por empresa, cifrada con Fernet usando una clave
maestra de plataforma (CREDENTIALS_ENCRYPTION_KEY). Sin esa clave maestra no se guarda
nada: se prefiere fallar a tener credenciales en claro en la base.
"""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

MISSING_MASTER_KEY = (
    "No se puede guardar la API key: falta CREDENTIALS_ENCRYPTION_KEY en la plataforma. "
    "Sin clave maestra no se guardan credenciales en claro."
)


class CredentialError(RuntimeError):
    """Se lanza cuando no se puede cifrar o descifrar. Nunca arrastra la credencial."""


def is_available() -> bool:
    return bool((settings.credentials_encryption_key or "").strip())


def _fernet() -> Fernet:
    key = (settings.credentials_encryption_key or "").strip()
    if not key:
        raise CredentialError(MISSING_MASTER_KEY)
    try:
        return Fernet(key.encode())
    except Exception as exc:  # noqa: BLE001
        # El mensaje no incluye la clave: si aparece en un log, no sirve de nada.
        raise CredentialError("CREDENTIALS_ENCRYPTION_KEY no es una clave Fernet valida.") from exc


def encrypt(plain: str) -> str:
    if plain is None:
        return None
    value = plain.strip()
    if not value:
        return None
    return _fernet().encrypt(value.encode()).decode()


def decrypt(cipher: str | None) -> str | None:
    if not cipher:
        return None
    try:
        return _fernet().decrypt(cipher.encode()).decode()
    except InvalidToken as exc:
        # Clave maestra rotada o dato corrupto. Se distingue de "no hay key" para que el
        # operador sepa que hay que volver a cargar la credencial.
        raise CredentialError(
            "No se pudo descifrar la API key: la clave maestra de la plataforma no coincide "
            "o el dato guardado esta corrupto. Hay que volver a cargar la credencial."
        ) from exc
