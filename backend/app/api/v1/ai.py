"""API del modulo IA (#44).

Sub-issue 1: estado del modulo, entitlement, medicion y una conversacion de texto.
Sub-issue 2: herramientas de **solo lectura** sobre el dominio. Leen clientes, equipos e
historial, siempre con la empresa y los permisos de la sesion.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import (
    effective_permissions,
    get_current_company_id,
    get_db,
    require_permission,
)
from app.models.user import User
from app.services.ai import chat as ai_chat
from app.services.ai.entitlement import monthly_quota_usd, monthly_request_limit
from app.services.ai.providers.base import ALLOWED_INBOUND_ROLES, LlmMessage
from app.services.ai.tools import disponibles
from app.services.ai.usage import last_period_cost, month_totals

router = APIRouter()

# Permiso propio del modulo.
PERMISSION = "ai.use"

# El prompt tiene que decir que puede consultar, porque de lo contrario el modelo se
# limita a describir lo que haria. Lo que **no** puede hacer queda en las herramientas: no
# puede cambiar de empresa ni saltarse un permiso, porque no son cosas que se le pidan.
SYSTEM_PROMPT = (
    "Sos un asistente de un taller de servicio técnico. "
    "Podés consultar clientes, equipos e historial de órdenes de trabajo de esta empresa "
    "con las herramientas disponibles, y responder en texto. "
    "Todavía no podés ejecutar acciones: si te piden una, describí qué harías."
)


class ChatMessage(BaseModel):
    role: str
    content: str = Field(min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=40)
    max_tokens: int | None = Field(default=None, ge=64, le=8000)
    # El cliente puede apagar las herramientas sin cambiar de sesion. El servidor nunca las
    # enciende solo: por default una conversacion no lee la base del cliente.
    con_herramientas: bool = False


@router.get("/ai/status")
def ai_status(
    company_id: int = Depends(get_current_company_id),
    actor: User = Depends(require_permission(PERMISSION)),
    db: Session = Depends(get_db),
):
    """Si la IA esta disponible para esta empresa, y cuanto lleva gastado.

    No expone credenciales: solo nombre de proveedor, modelo y si hay key cargada.
    """
    outcome = ai_chat.availability(db, company_id)
    totals = month_totals(db, company_id)
    permisos = effective_permissions(db, actor, company_id)
    return {
        "enabled": outcome.reason != ai_chat.NO_HABILITADO,
        "available": outcome.ok,
        "reason": outcome.reason,
        "provider": outcome.provider or None,
        "model": outcome.model or None,
        "herramientas": sorted(t.name for t in disponibles(permisos)),
        "usage": {
            **totals,
            "monthly_quota_usd": monthly_quota_usd(db, company_id),
            "monthly_request_limit": monthly_request_limit(db, company_id),
            "previous_month_cost_usd": last_period_cost(db, company_id),
        },
    }


@router.post("/ai/chat")
def ai_chat_endpoint(
    payload: ChatRequest,
    company_id: int = Depends(get_current_company_id),
    actor: User = Depends(require_permission(PERMISSION)),
    db: Session = Depends(get_db),
):
    """Conversacion, con herramientas de lectura opcionalmente.

    Devuelve 200 tambien cuando la IA no esta disponible, con ``available: false`` y el
    motivo. La UI muestra "la IA no esta disponible" y el operador sigue trabajando; un
    500 lo dejaria sin sistema.
    """
    from app.core.config import settings

    history = [LlmMessage(role=m.role, content=m.content) for m in payload.messages if m.role in ALLOWED_INBOUND_ROLES]
    if not history:
        history = [LlmMessage(role="user", content=payload.messages[0].content)]
    else:
        history = [LlmMessage(role="system", content=SYSTEM_PROMPT), *history]

    # Los permisos salen de la sesion, no del cuerpo del pedido. Se pasan aun cuando el
    # cliente no pidio herramientas, para que el bucle tenga el mismo contexto en los dos
    # casos y no dependa de que el cliente se acuerde de activarlo.
    permisos = effective_permissions(db, actor, company_id) if payload.con_herramientas else None

    outcome = ai_chat.run_chat(
        db,
        company_id,
        actor.id,
        history,
        operation="chat",
        max_tokens=payload.max_tokens or settings.ai_max_tokens,
        permissions=permisos,
    )
    return outcome.as_dict()
