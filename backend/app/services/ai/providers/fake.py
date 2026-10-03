"""Proveedor falso, para tests y para cuando no hay credenciales cargadas.

Sirve para dos cosas distintas y deliberadamente son la misma clase:
- en los tests, para no tocar la red;
- en un ambiente sin API key, para que el sistema responda algo coherente en vez de
  romperse. Es el doble del criterio 'el sistema debe seguir siendo utilizable si el
  proveedor de IA esta caido'.
"""
from __future__ import annotations

from app.core.config import settings
from app.services.ai.providers.base import LlmMessage, LlmResponse, ProviderError


class FakeProvider:
    """Responde de forma determinista. Con ``fails=True`` simula al proveedor caido."""

    name = "fake"

    def __init__(self, text: str = "Respuesta de prueba del proveedor simulado.", fails: bool = False):
        self._text = text
        self._fails = fails
        self.calls: list[list[LlmMessage]] = []

    def is_configured(self) -> bool:
        # Siempre configurado, incluso cuando falla. 'Sin key cargada' y 'el proveedor esta
        # caido' son motivos distintos y la UI los muestra distinto: si el doble se
        # declarara no configurado, nunca se ejercitaria el camino de proveedor caido.
        return True

    def model_id(self) -> str:
        return settings.ai_fallback_model

    def complete(self, messages: list[LlmMessage], max_tokens: int = 1024) -> LlmResponse:
        self.calls.append(list(messages))
        if self._fails:
            raise ProviderError("Proveedor simulado caido.")
        return LlmResponse(
            text=self._text,
            model=self.model_id(),
            provider=self.name,
            input_tokens=sum(len(m.content) // 4 for m in messages),
            output_tokens=max_tokens // 4,
            finish_reason="stop",
        )
