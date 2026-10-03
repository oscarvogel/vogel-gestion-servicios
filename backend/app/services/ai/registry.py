"""Registro de proveedores de IA.

Un solo lugar decide que proveedor se usa. Cambiar de proveedor es cambiar una variable
de entorno; agregar uno es registrarlo aca.
"""
from __future__ import annotations

from app.core.config import settings
from app.services.ai.providers.base import LlmProvider
from app.services.ai.providers.fake import FakeProvider
from app.services.ai.providers.minimax import MinimaxProvider

PROVIDERS: dict[str, type] = {
    "minimax": MinimaxProvider,
    "fake": FakeProvider,
}


def build_provider(name: str | None = None) -> LlmProvider:
    key = (name or settings.ai_provider or "minimax").strip().lower()
    factory = PROVIDERS.get(key)
    if factory is None:
        # No se cae a un proveedor por defecto en silencio: si el nombre esta mal
        # escrito, el operador tiene que enterarse, no talking to another vendor.
        from app.services.ai.providers.base import ProviderError

        raise ProviderError(f"Proveedor de IA desconocido: {key}")
    return factory()  # type: ignore[return-value]


def get_provider(name: str | None = None) -> LlmProvider:
    return build_provider(name)
