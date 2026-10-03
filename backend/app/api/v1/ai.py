"""API del modulo IA (#44).

Sub-issue 1: estado del modulo, entitlement, medicion y una conversacion de texto.
Sub-issue 2: herramientas de **solo lectura** sobre el dominio. Leen clientes, equipos e
historial, siempre con la empresa y los permisos de la sesion.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import (
    effective_permissions,
    get_current_company_id,
    get_db,
    require_permission,
    user_has_permission,
)
from app.models.ai_action_proposal import PENDIENTE
from app.models.user import User
from app.services.ai import chat as ai_chat
from app.services.ai import proposals
from app.services.ai.entitlement import monthly_quota_usd, monthly_request_limit
from app.services.ai.providers.base import ALLOWED_INBOUND_ROLES, LlmMessage
from app.services.ai.tools import disponibles
from app.services.ai.usage import last_period_cost, month_totals
from app.services.work_orders import ErrorDeDominio

router = APIRouter()

# Permiso propio del modulo.
PERMISSION = "ai.use"

# El prompt tiene que decir dos cosas: que puede consultar, y que lo que consulte lo
# decide el sistema. Lo que **no** puede hacer queda en las herramientas: no puede cambiar
# de empresa ni saltarse un permiso, porque no son cosas que se le pidan.
#
# Y hay que decirle explicitamente que no escriba datos. No por confianza: porque se midio
# que las escribe. El backend tiene una red que descarta cualquier texto con numeros o
# estados, asi que el prompt solo evita trabajo de sobra.
SYSTEM_PROMPT = (
    "Sos un asistente de un taller de servicio técnico. "
    "Podés consultar clientes, equipos e historial de órdenes de trabajo de esta empresa "
    "con las herramientas disponibles. "
    "Tu texto NO puede contener datos: ni cantidades, ni fechas, ni números de orden, ni "
    "nombres de estado. Esos valores están en la ficha que muestra el sistema; vos solo "
    "escribís el comentario alrededor. Si no consultaste, decilo. "
    "Para cambiar algo del sistema usá las herramientas de escritura: dejan una propuesta "
    "que una persona tiene que confirmar, así que explicá qué proponés y nunca digas que ya "
    "está hecho. "
    "Todavía no podés ejecutar acciones por tu cuenta: si te piden una que no tenés, decilo."
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
    cuerpo = outcome.as_dict()
    # Las propuestas que quedaron pendientes de esta conversacion. Van en la respuesta para que
    # la pantalla muestre lo que hay que confirmar sin que el operador tenga que ir a buscarlas.
    if payload.con_herramientas:
        cuerpo["propuestas"] = [
            proposals.serializar(p)
            for p in proposals.listar(db, company_id, estados=[PENDIENTE], limite=20)
        ]
    return cuerpo


# --------------------------------------------------------------------------------------
# Propuestas de escritura: la parte donde decide una persona (#44 sub-issue 3)
# --------------------------------------------------------------------------------------


class ConfirmarPropuesta(BaseModel):
    # Lo que la persona confirmo, que puede ser lo mismo que propuso el modelo o estar
    # corregido. **Se escribe esto, no lo propuesto.**
    argumentos: dict | None = None
    nota: str | None = Field(default=None, max_length=500)


@router.get("/ai/propuestas")
def listar_propuestas(
    estado: str | None = None,
    company_id: int = Depends(get_current_company_id),
    _actor: User = Depends(require_permission(PERMISSION)),
    db: Session = Depends(get_db),
):
    estados = [e.strip() for e in estado.split(",") if e.strip()] if estado else None
    return [proposals.serializar(p) for p in proposals.listar(db, company_id, estados=estados)]


@router.get("/ai/propuestas/{propuesta_id}")
def ver_propuesta(
    propuesta_id: int,
    company_id: int = Depends(get_current_company_id),
    _actor: User = Depends(require_permission(PERMISSION)),
    db: Session = Depends(get_db),
):
    try:
        return proposals.serializar(proposals.obtener(db, propuesta_id, company_id))
    except proposals.NoEncontrada:
        raise HTTPException(404, "La propuesta no existe en esta empresa.")


@router.post("/ai/propuestas/{propuesta_id}/confirmar")
def confirmar_propuesta(
    propuesta_id: int,
    payload: ConfirmarPropuesta,
    company_id: int = Depends(get_current_company_id),
    actor: User = Depends(require_permission(PERMISSION)),
    db: Session = Depends(get_db),
):
    """Aplica lo que la persona confirmo.

    El permiso exigido es el de la **herramienta** que se va a aplicar, no solo ``ai.use``: que
    alguien pueda usar el asistente no lo convierte en alguien que pueda dar de alta clientes
    o cambiar estados.
    """
    try:
        propuesta = proposals.obtener(db, propuesta_id, company_id)
    except proposals.NoEncontrada:
        raise HTTPException(404, "La propuesta no existe en esta empresa.")

    herramienta = _por_nombre(propuesta.tool)
    if herramienta is None:
        raise HTTPException(409, f'La herramienta "{propuesta.tool}" ya no existe en el sistema.')
    if not user_has_permission(db, actor, company_id, herramienta.permission):
        raise HTTPException(
            403,
            "Tu usuario no tiene permiso para aplicar esta acción. "
            f'Necesita "{herramienta.permission}".',
        )

    try:
        aplicada = proposals.confirmar(
            db, propuesta_id, company_id=company_id, user_id=actor.id,
            argumentos=payload.argumentos,
        )
    except proposals.YaResuelta as ya:
        # Reintento: se devuelve lo que ya se hizo, sin escribir de nuevo.
        cuerpo = proposals.serializar(ya.propuesta)
        cuerpo["ya_se_habia_aplicado"] = True
        return cuerpo
    except ErrorDeDominio as exc:
        # Regla de negocio incumplida: 422, con su motivo.
        raise HTTPException(exc.status_http, exc.mensaje)
    except proposals.ErrorDePropuesta as exc:
        raise HTTPException(409, exc.mensaje)

    cuerpo = proposals.serializar(aplicada)
    # Si la acción encoló un aviso al cliente, se despacha aca: el envio va despues del
    # commit, igual que en la pantalla, y nunca puede hacer fallar la confirmacion.
    cuerpo["avisos_enviados"] = _despachar(db, aplicada)
    return cuerpo


@router.post("/ai/propuestas/{propuesta_id}/rechazar")
def rechazar_propuesta(
    propuesta_id: int,
    company_id: int = Depends(get_current_company_id),
    _actor: User = Depends(require_permission(PERMISSION)),
    db: Session = Depends(get_db),
):
    try:
        return proposals.serializar(proposals.rechazar(db, propuesta_id, company_id=company_id))
    except proposals.NoEncontrada:
        raise HTTPException(404, "La propuesta no existe en esta empresa.")
    except proposals.ErrorDePropuesta as exc:
        raise HTTPException(409, exc.mensaje)


def _por_nombre(nombre: str):
    from app.services.ai.tools.registry import TODAS

    return next((t for t in TODAS if t.name == nombre), None)


def _despachar(db: Session, propuesta) -> dict:
    """Manda los avisos que la aplicacion encolo, si hubo alguno."""
    try:
        referencia = json.loads(propuesta.result_reference or "{}")
    except (TypeError, ValueError):
        return {}
    orden_id = referencia.get("orden") or referencia.get("id")
    if not orden_id or not propuesta.notified:
        return {}
    from app.models.work_order import WorkOrderNotification
    from app.services.notifications.enqueue import PENDING, dispatch

    filas = (
        db.query(WorkOrderNotification)
        .filter(
            WorkOrderNotification.work_order_id == orden_id,
            WorkOrderNotification.status == PENDING,
        )
        .all()
    )
    if not filas:
        return {}
    try:
        return dispatch(db, [f.id for f in filas], actor_id=propuesta.confirmed_by_user_id)
    except Exception:
        # La fila queda PENDING o FAILED y la toma el drenaje. Confirmar no puede fallar por
        # culpa de la gateway de WhatsApp.
        return {}
