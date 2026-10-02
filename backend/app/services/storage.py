"""Adaptador de almacenamiento de archivos.

El dominio (equipos, documentos) no sabe si el binario vive en un disco o en un bucket:
habla con esta interfaz. Agregar S3-compatible es implementar ``Storage`` y registrarla
en ``build_storage``; ningun otro modulo cambia.

La implementacion por defecto es el sistema de archivos sobre un volumen persistente, que
es lo mismo que ya hace la gateway de WhatsApp con la multimedia inbound. No depende de
ningun servicio externo.
"""
from __future__ import annotations

import os
import shutil
import uuid
from dataclasses import dataclass
from typing import BinaryIO, Protocol

from app.core.config import settings


@dataclass
class StoredObject:
    key: str
    size_bytes: int
    content_type: str


class StorageError(RuntimeError):
    """Falla del backend de almacenamiento. El mensaje no lleva rutas del servidor."""


class Storage(Protocol):
    def put(self, key: str, stream: BinaryIO, content_type: str) -> StoredObject: ...
    def open(self, key: str) -> BinaryIO: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...
    def size(self, key: str) -> int: ...


def build_key(company_id: int, equipment_id: int, filename: str) -> str:
    """Clave del objeto, generada en el servidor.

    Nunca se usa el nombre que manda el frontend: un nombre de archivo es entrada de
    usuario y no puede ser una clave de almacenamiento. Va company/equipment y un
    identificador aleatorio, con la extension sola y saneada.
    """
    suffix = os.path.splitext(filename or "")[1].lower()
    suffix = "".join(ch for ch in suffix if ch.isalnum() or ch == ".")[:16]
    if suffix and not suffix.startswith("."):
        suffix = "." + suffix
    return f"company-{company_id}/equipment-{equipment_id}/{uuid.uuid4().hex}{suffix}"


class FilesystemStorage:
    """Binarios en un volumen persistente. La implementacion por defecto."""

    def __init__(self, root: str):
        self.root = os.path.abspath(root)

    def _path(self, key: str) -> str:
        # Defensa extra: aunque build_key ya es seguro, se verifica que la clave
        # resuelva dentro de la raiz.
        full = os.path.abspath(os.path.join(self.root, key))
        if not full.startswith(self.root + os.sep):
            raise StorageError("Clave de almacenamiento invalida")
        return full

    def put(self, key: str, stream: BinaryIO, content_type: str) -> StoredObject:
        path = self._path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path, "wb") as target:
                shutil.copyfileobj(stream, target)
        except OSError as exc:
            raise StorageError(f"No se pudo guardar el archivo: {type(exc).__name__}") from exc
        return StoredObject(key=key, size_bytes=os.path.getsize(path), content_type=content_type)

    def open(self, key: str) -> BinaryIO:
        path = self._path(key)
        if not os.path.exists(path):
            raise StorageError("El archivo no esta en el almacenamiento")
        return open(path, "rb")

    def delete(self, key: str) -> None:
        path = self._path(key)
        if os.path.exists(path):
            os.remove(path)

    def exists(self, key: str) -> bool:
        try:
            return os.path.exists(self._path(key))
        except StorageError:
            return False

    def size(self, key: str) -> int:
        path = self._path(key)
        if not os.path.exists(path):
            raise StorageError("El archivo no esta en el almacenamiento")
        return os.path.getsize(path)


def build_storage() -> Storage:
    """El backend sale de configuracion, no del codigo."""
    backend = (settings.storage_backend or "filesystem").strip().lower()
    if backend == "filesystem":
        return FilesystemStorage(settings.storage_local_root)
    # Un backend desconocido no cae a filesystem en silencio: falla de forma explicita,
    # porque escribir en el disco cuando se pidio un bucket es peor que no escribir nada.
    raise StorageError(f"Backend de almacenamiento desconocido: {backend}")
