"""Interfaz de proveedor de IA.

El dominio no conoce a MiniMax ni a ningun otro: conoce esta interfaz. Cambiar o agregar
un proveedor es implementar ``LlmProvider`` y registrarlo, sin tocar ni una linea mas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

ROLE_SYSTEM = "system"
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"
# La gateway de texto de MiniMax (y el endpoint compatible con OpenAI) solo acepta estos
# tres roles. Mandar 'developer' o 'tool' es un 400.
ALLOWED_ROLES = (ROLE_SYSTEM, ROLE_USER, ROLE_ASSISTANT)


class ProviderError(RuntimeError):
    """Fallo del proveedor: red, credenciales, limite o respuesta ilegible.

    El mensaje es apto para mostrar: nunca lleva la API key ni el cuerpo de la conversacion.
    """


@dataclass(frozen=True)
class LlmMessage:
    role: str
    content: str

    def as_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class LlmResponse:
    text: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    finish_reason: str | None = None
    # thinking bloqueado por default: para operar el dominio no queremos que el modelo
    # gaste tokens pensando en voz alta, y el texto que ve el usuario tampoco.
    raw: dict = field(default_factory=dict)


@runtime_checkable
class LlmProvider(Protocol):
    name: str

    def is_configured(self) -> bool:
        """Si el proveedor tiene credenciales. Un False aca no es un error: es 'no hay IA'."""

    def model_id(self) -> str: ...

    def complete(self, messages: list[LlmMessage], max_tokens: int = 1024) -> LlmResponse:
        """Genera una respuesta. Lanza ``ProviderError`` si el proveedor no pudo."""
