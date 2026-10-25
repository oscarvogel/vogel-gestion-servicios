"""Identidad del build que esta corriendo: que version y que commit se desplegaron.

Coolify define ``SOURCE_COMMIT`` con el commit desplegado. Queda disponible en el
contenedor aunque se excluya del build para no invalidar la cache de Docker, asi que
de ahi sale el commit que se muestra en el pie de la app.
"""

from __future__ import annotations

import os

# El nombre de la variable cambio entre versiones de Coolify, asi que se prueban varias.
_COMMIT_ENV_KEYS = (
    "SOURCE_COMMIT",
    "SOURCE_COMMIT_SHA",
    "GIT_COMMIT",
    "COMMIT_SHA",
)


def deployed_commit() -> str | None:
    """El commit completo del deploy, o None si el entorno no lo expone."""
    for key in _COMMIT_ENV_KEYS:
        value = (os.environ.get(key) or "").strip()
        if value:
            return value
    return None


def short_commit(length: int = 7) -> str | None:
    """El commit abreviado, que es lo que se muestra en pantalla."""
    commit = deployed_commit()
    if not commit:
        return None
    return commit[:length]


def backend_version() -> str:
    """La version del backend, leida de los metadatos del paquete instalado."""
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version("vogel-gestion-servicios-backend")
        except PackageNotFoundError:
            return "0.0.0"
    except Exception:  # pragma: no cover - metadatos no disponibles
        return "0.0.0"


def build_info() -> dict[str, str | None]:
    """Lo que la API devuelve para que el frontend muestre que build esta vivo."""
    return {"version": backend_version(), "commit": deployed_commit()}
