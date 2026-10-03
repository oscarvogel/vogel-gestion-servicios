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
# `tool` es el cuarto rol que hace falta para el round trip de herramientas: el modelo pide
# una herramienta, nosotros la ejecutamos y le mandamos el resultado con `tool_call_id`.
# Verificado contra la API real el 2026-10-03: la acepta y el modelo usa el resultado
# correctamente. `developer` si da 400.
ROLE_TOOL = "tool"
ALLOWED_ROLES = (ROLE_SYSTEM, ROLE_USER, ROLE_ASSISTANT, ROLE_TOOL)
# Los roles que puede escribir el usuario de la API. `tool` queda afuera a proposito: un
# cliente no puede inyectarse un resultado de herramienta en la conversacion.
ALLOWED_INBOUND_ROLES = (ROLE_SYSTEM, ROLE_USER, ROLE_ASSISTANT)


class ProviderError(RuntimeError):
    """Fallo del proveedor: red, credenciales, limite o respuesta ilegible.

    El mensaje es apto para mostrar: nunca lleva la API key ni el cuerpo de la conversacion.
    """


@dataclass(frozen=True)
class LlmMessage:
    role: str
    content: str
    # Solo para el mensaje `tool`: el id de la llamada que este resultado responde.
    tool_call_id: str | None = None
    # Solo para el mensaje `assistant` que originó llamadas a herramientas.
    tool_calls: tuple["LlmToolCall", ...] | None = None

    def as_dict(self) -> dict:
        """Payload para la API. Los roles sin campos extra no los mandamos vacios."""
        data: dict = {"role": self.role, "content": self.content}
        if self.role == ROLE_TOOL and self.tool_call_id:
            data["tool_call_id"] = self.tool_call_id
        if self.role == ROLE_ASSISTANT and self.tool_calls:
            data["tool_calls"] = [
                {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments_json}}
                for c in self.tool_calls
            ]
        return data


@dataclass(frozen=True)
class LlmToolCall:
    """Una llamada a herramienta que el modelo pide ejecutar.

    ``arguments`` ya viene parseado a dict: el proveedor lo entrega como string JSON y
    parsearlo aca evita que cada consumidor tenga que acordarse de hacerlo.
    """

    id: str
    name: str
    arguments: dict

    @property
    def arguments_json(self) -> str:
        import json

        return json.dumps(self.arguments, ensure_ascii=False)


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
    # Llamadas a herramientas que el modelo pide. Vacio si esta respuesta es de texto.
    tool_calls: list[LlmToolCall] = field(default_factory=list)

    @property
    def wants_tools(self) -> bool:
        return bool(self.tool_calls)


@runtime_checkable
class LlmProvider(Protocol):
    name: str

    def is_configured(self) -> bool:
        """Si el proveedor tiene credenciales. Un False aca no es un error: es 'no hay IA'."""

    def model_id(self) -> str: ...

    def complete(
        self,
        messages: list[LlmMessage],
        max_tokens: int = 1024,
        tools: list[dict] | None = None,
    ) -> LlmResponse:
        """Genera una respuesta. Lanza ``ProviderError`` si el proveedor no pudo.

        ``tools`` es el catalogo en formato JSON Schema. Cuando se pasa, la respuesta puede
        venir con ``tool_calls`` en lugar de texto.
        """
