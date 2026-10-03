"""Orquestador de una operacion de IA.

Acá vive la regla que mas importa de este primer sub-issue: **una falla del proveedor
nunca es una excepcion que se propaga**. Si MiniMax esta caido, sin credenciales o sin
cuota, la respuesta es un resultado con `ok=False` y un motivo, no un 500. El operador ve
"la IA no esta disponible" y sigue trabajando con el sistema normal.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.services.ai.entitlement import (
    is_enabled,
    monthly_quota_usd,
    monthly_request_limit,
)
from app.services.ai.providers.base import LlmMessage, ProviderError
from app.services.ai.registry import get_provider
from app.services.ai.usage import ERROR, OK, SIN_CUOTA, record

# Motivos de no disponibilidad. La API los expone para que el frontend distinga
# "no lo contrate" de "se cayo" de "se le acabo la cuota": son tres mensajes distintos.
NO_HABILITADO = "no_habilitado"
PROVEEDOR_SIN_CONFIGURAR = "proveedor_sin_configurar"
PROVEEDOR_CAIDO = "proveedor_caido"
CUOTA_EXCEDIDA = "cuota_excedida"

DISPONIBLE = "disponible"
NO_DISPONIBLE = "no_disponible"


@dataclass
class AiOutcome:
    ok: bool
    status: str
    text: str = ""
    provider: str = ""
    model: str = ""
    reason: str | None = None
    detail: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "text": self.text,
            "provider": self.provider,
            "model": self.model,
            "reason": self.reason,
            "detail": self.detail,
            "usage": self.usage,
        }


def availability(db: Session, company_id: int) -> AiOutcome:
    """Si la IA se puede usar ahora, sin llamarla. Para el endpoint de estado."""
    if not is_enabled(db, company_id):
        return AiOutcome(ok=False, status=NO_DISPONIBLE, reason=NO_HABILITADO)
    provider = get_provider()
    if not provider.is_configured():
        return AiOutcome(ok=False, status=NO_DISPONIBLE, reason=PROVEEDOR_SIN_CONFIGURAR, provider=provider.name)
    if _over_quota(db, company_id):
        return AiOutcome(ok=False, status=NO_DISPONIBLE, reason=CUOTA_EXCEDIDA, provider=provider.name)
    return AiOutcome(ok=True, status=DISPONIBLE, provider=provider.name, model=provider.model_id())


def _over_quota(db: Session, company_id: int) -> bool:
    from app.services.ai.usage import month_totals

    totals = month_totals(db, company_id)
    quota = monthly_quota_usd(db, company_id)
    if quota and totals["cost_usd"] >= quota:
        return True
    limit = monthly_request_limit(db, company_id)
    return bool(limit and totals["requests"] >= limit)


def run_chat(
    db: Session,
    company_id: int,
    user_id: int | None,
    messages: list[LlmMessage],
    *,
    operation: str = "chat",
    max_tokens: int = 1024,
) -> AiOutcome:
    """Ejecuta una conversacion. No levanta nunca una excepcion por el proveedor."""
    gate = availability(db, company_id)
    if not gate.ok and gate.reason != CUOTA_EXCEDIDA:
        # Ni habilitado ni configurado: ni siquiera se registra uso, porque no hubo
        # pedido a ningun proveedor. Se responde el motivo y listo.
        return gate

    provider = get_provider()
    if gate.reason == CUOTA_EXCEDIDA:
        record(db, company_id, provider.name, provider.model_id(), operation,
               user_id=user_id, status=SIN_CUOTA, error="Cuota mensual excedida")
        return gate

    try:
        response = provider.complete(messages, max_tokens=max_tokens)
    except ProviderError as exc:
        # Se registra el intento fallido: si solo anotamos los exitos, el acumulado de
        # consumo miente justo cuando la cosa esta peor.
        record(db, company_id, provider.name, provider.model_id(), operation,
               user_id=user_id, status=ERROR, error=str(exc))
        return AiOutcome(
            ok=False,
            status=NO_DISPONIBLE,
            reason=PROVEEDOR_CAIDO,
            detail=str(exc),
            provider=provider.name,
            model=provider.model_id(),
        )
    except Exception as exc:  # noqa: BLE001 - un adaptador no puede romper el request
        record(db, company_id, provider.name, provider.model_id(), operation,
               user_id=user_id, status=ERROR, error=f"{type(exc).__name__}")
        return AiOutcome(
            ok=False,
            status=NO_DISPONIBLE,
            reason=PROVEEDOR_CAIDO,
            detail="El proveedor fallo de forma inesperada.",
            provider=provider.name,
        )

    record(db, company_id, response.provider, response.model, operation,
           user_id=user_id, response=response, status=OK)
    return AiOutcome(
        ok=True,
        status=DISPONIBLE,
        text=response.text,
        provider=response.provider,
        model=response.model,
    )
