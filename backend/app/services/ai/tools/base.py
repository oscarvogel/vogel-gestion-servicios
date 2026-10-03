"""Contrato de una herramienta de IA.

Acá vive la regla de seguridad del modulo: **la empresa, el usuario y los permisos salen de
la sesion, nunca del modelo**. `ToolContext` se construye una vez, en el endpoint, con lo que
ya sabe la API; la herramienta lo recibe y no lo pide. El modelo solo elige que herramienta
llamar y con que argumentos de negocio.

Por eso una herramienta de lectura no puede mostrar datos de otra empresa: no es que filtre
por empresa porque "se acuerda", es que el `company_id` que usa no lo puede influenciar nadie
externo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from sqlalchemy.orm import Session


# Motivos de error de una herramienta. El modelo los recibe como texto y puede explicarle al
# operador que paso, asi que son strings pensados para mostrarse.
SIN_PERMISO = "sin_permiso"
ARGUMENTOS_INVALIDOS = "argumentos_invalidos"
NO_ENCONTRADO = "no_encontrado"
ERROR_INTERNO = "error_interno"
DESCONOCIDA = "herramienta_desconocida"


class ToolError(Exception):
    """Falla controlada de una herramienta. Nunca es un 500 para el operador."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ToolContext:
    """Lo que una herramienta tiene permitido ver.

    ``company_id`` y ``user_id`` son de la sesion. ``permissions`` es el conjunto de permisos
    efectivos del actor en esa empresa, ya resuelto por la capa de permisos de la API.
    """

    db: Session
    company_id: int
    user_id: int | None
    permissions: frozenset[str] = frozenset()

    def has(self, permission: str) -> bool:
        return permission in self.permissions


@dataclass(frozen=True)
class ToolOutcome:
    """Lo que una herramienta devuelve. ``ok=False`` es un resultado, no una excepcion."""

    ok: bool
    data: Any = None
    error_code: str | None = None
    error_message: str | None = None

    def as_text(self) -> str:
        """Como lo ve el modelo: JSON compacto, o el motivo si fallo."""
        import json

        if self.ok:
            return json.dumps(self.data, ensure_ascii=False, default=str)
        return json.dumps(
            {"error": self.error_code, "detalle": self.error_message}, ensure_ascii=False
        )


@dataclass(frozen=True)
class ToolSpec:
    """Una herramienta: nombre, esquema de argumentos, permiso exigido y como corre."""

    name: str
    description: str
    parameters: dict
    permission: str
    run: Callable[[ToolContext, dict], ToolOutcome]

    def as_provider_schema(self) -> dict:
        """El catalogo en la forma que espera la API (estilo OpenAI function calling)."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class ToolCallRecord:
    """Como quedo registrada una ejecucion, para la auditoria de `ai_usage`."""

    name: str
    outcome: ToolOutcome
    arguments: dict = field(default_factory=dict)
