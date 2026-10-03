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

from app.services.ai.answer import construir_ficha, estados_de_la_empresa, sanear
from app.services.ai.entitlement import (
    is_enabled,
    monthly_quota_usd,
    monthly_request_limit,
)
from app.services.ai.providers.base import (
    ROLE_ASSISTANT,
    ROLE_TOOL,
    LlmMessage,
    LlmResponse,
    ProviderError,
)
from app.services.ai.registry import get_provider
from app.services.ai.tools.base import ToolContext
from app.services.ai.tools.registry import catalogo_para_proveedor, ejecutar
from app.services.ai.usage import ERROR, OK, SIN_CUOTA, record

# Motivos de no disponibilidad. La API los expone para que el frontend distinga
# "no lo contrate" de "se cayo" de "se le acabo la cuota": son tres mensajes distintos.
NO_HABILITADO = "no_habilitado"
PROVEEDOR_SIN_CONFIGURAR = "proveedor_sin_configurar"
PROVEEDOR_CAIDO = "proveedor_caido"
CUOTA_EXCEDIDA = "cuota_excedida"

DISPONIBLE = "disponible"
NO_DISPONIBLE = "no_disponible"

# Tope de vueltas del bucle de herramientas (una llamada al proveedor por vuelta). Cuatro
# alcanza para "buscar el cliente, despues el equipo, despues el historial y responder", que
# es lo mas largo que se le pide. Si se supera, se corta y se responde igual: una
# conversation infinita de herramientas seria un costo sin fin.
MAX_VUELTAS_HERRAMIENTAS = 4


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
    # Herramientas que se ejecutaron en esta conversacion, en orden, con su motivo si
    # fallaron. La UI los puede mostrar y el operador puede ver que se leyo algo de su base.
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    # Los datos, armados por el servidor. Es la fuente autoritativa de la respuesta.
    ficha: dict[str, Any] = field(default_factory=dict)
    # Si se pidió usar herramientas y el modelo no consultó ninguna. Sin esto, una respuesta
    # sin ficha parece igual que una con ficha, y el operador no tiene cómo distinguirla.
    consulto: bool = False
    # True cuando el texto del modelo tenía datos y se reemplazó por la frase neutra.
    texto_saneado: bool = False

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
            "tool_calls": self.tool_calls,
            "ficha": self.ficha,
            "consulto": self.consulto,
            "texto_saneado": self.texto_saneado,
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
    permissions: frozenset[str] | None = None,
) -> AiOutcome:
    """Ejecuta una conversacion. No levanta nunca una excepcion por el proveedor.

    Si ``permissions`` viene informado, el modelo recibe las herramientas de lectura que el
    actor tiene permitidas y puede pedir que se ejecuten. El contexto de esas herramientas
    (empresa y usuario) se arma con la sesion: el modelo elige **que** herramienta llamar y
    **con que argumentos de negocio**, nunca a quien le pertenece la informacion.
    """
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

    contexto: ToolContext | None = None
    catalogo: list[dict] = []
    if permissions is not None:
        contexto = ToolContext(
            db=db, company_id=company_id, user_id=user_id, permissions=permissions
        )
        catalogo = catalogo_para_proveedor(permissions)

    return _conversar(
        db=db,
        company_id=company_id,
        user_id=user_id,
        provider=provider,
        contexto=contexto,
        mensajes=list(messages),
        operation=operation,
        max_tokens=max_tokens,
        catalogo=catalogo,
    )


def _conversar(
    *,
    db: Session,
    company_id: int,
    user_id: int | None,
    provider: Any,
    contexto: ToolContext | None,
    mensajes: list[LlmMessage],
    operation: str,
    max_tokens: int,
    catalogo: list[dict],
) -> AiOutcome:
    """Llama al proveedor y, si pide herramientas, las ejecuta y le manda el resultado.

    El numero de vueltas esta acotado a proposito: un modelo que se pide una herramienta a si
    mismo para siempre tiene que terminar, y en el peor caso tiene que terminar con una
    respuesta. Cuando se agota el tope se devuelve la ultima respuesta que haya, que puede
    venir vacia: es preferible una respuesta incompleta a un request colgado.
    """
    ejecutadas: list[dict[str, Any]] = []
    resultados_herramientas: list[tuple[str, Any]] = []
    ultima: LlmResponse | None = None
    estados: set[str] = set()
    # El modelo puede pedir la misma herramienta con los mismos argumentos varias vueltas
    # seguidas. Se responde con el resultado ya calculado en vez de volver a pegarle a la
    # base: sale mas barato y, sobre todo, la ficha no se llena de copias del mismo bloque.
    ya_calculado: dict[str, Any] = {}
    if contexto is not None:
        estados = estados_de_la_empresa(db, company_id)

    def _salir(respuesta: LlmResponse) -> AiOutcome:
        """Arma la respuesta final: ficha del servidor y texto del modelo ya saneado."""
        ficha = construir_ficha(resultados_herramientas)
        texto, saneado = sanear(respuesta.text, estados)
        return AiOutcome(
            ok=True,
            status=DISPONIBLE,
            text=texto,
            provider=respuesta.provider,
            model=respuesta.model,
            tool_calls=ejecutadas,
            ficha=ficha.as_dict(),
            consulto=bool(ejecutadas),
            texto_saneado=saneado,
        )

    for _vuelta in range(MAX_VUELTAS_HERRAMIENTAS):
        try:
            respuesta = provider.complete(mensajes, max_tokens=max_tokens, tools=catalogo or None)
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
                tool_calls=ejecutadas,
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
                tool_calls=ejecutadas,
            )

        ultima = respuesta

        # Sin herramientas, o sin contexto para ejecutarlas, esta era la ultima llamada.
        if not respuesta.wants_tools or contexto is None:
            record(db, company_id, respuesta.provider, respuesta.model, operation,
                   user_id=user_id, response=respuesta, status=OK)
            return _salir(respuesta)

        # El pedido de herramientas se registra por separado, con su propia operacion: el
        # gasto de una vuelta que todavia no termino tiene que poder atribuirse.
        record(db, company_id, respuesta.provider, respuesta.model,
               f"{operation}:peticion_herramientas", user_id=user_id, response=respuesta)

        mensajes = mensajes + [
            LlmMessage(
                role=ROLE_ASSISTANT,
                content=respuesta.text or "",
                tool_calls=tuple(respuesta.tool_calls),
            )
        ]

        for llamada in respuesta.tool_calls:
            clave = llamada.name + "\x00" + llamada.arguments_json
            repetida = clave in ya_calculado
            if repetida:
                resultado = ya_calculado[clave]
            else:
                resultado = ejecutar(llamada.name, llamada.arguments, contexto)
                ya_calculado[clave] = resultado
            ejecutadas.append(
                {"name": llamada.name, "ok": resultado.ok, "error": resultado.error_code,
                 "repetida": repetida}
            )
            # Solo entra en la ficha la primera vez: si se repite, la ficha mostraria el
            # mismo bloque dos veces.
            if not repetida and resultado.ok and resultado.data is not None:
                resultados_herramientas.append((llamada.name, resultado.data))
            # Cada herramienta queda registrada por separado: el acumulado tiene que poder
            # atribuir el gasto a la herramienta y no solo a la conversacion.
            record(
                db,
                company_id,
                provider.name,
                provider.model_id(),
                f"herramienta:{llamada.name}",
                user_id=user_id,
                status=OK if resultado.ok else ERROR,
                error=resultado.error_message if not resultado.ok else None,
            )
            mensajes = mensajes + [
                LlmMessage(role=ROLE_TOOL, content=resultado.as_text(), tool_call_id=llamada.id)
            ]

    # Se agoto el tope de vueltas. Se devuelve lo que haya, que puede ser una respuesta sin
    # texto si el modelo solo vino pidiendo herramientas.
    if ultima is not None:
        return _salir(ultima)
    return AiOutcome(
        ok=True,
        status=DISPONIBLE,
        provider=provider.name,
        model=provider.model_id(),
        tool_calls=ejecutadas,
        ficha=construir_ficha(resultados_herramientas).as_dict(),
        consulto=bool(ejecutadas),
    )
