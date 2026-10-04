"""Propuestas de acciones de escritura: la IA propone, la persona confirma (#44 sub-issue 3).

Este modulo es el que hace verdadera la regla. Lo importante es lo que **no** hace:

- Ninguna herramienta de escritura escribe. Crean una fila en `ai_action_proposals` con
  estado `pendiente` y devuelven al modelo el id de la propuesta. El modelo nunca esta en el
  camino de la escritura.
- Confirmar es una llamada aparte, con la sesion de una persona y sus permisos. El modelo no
  puede llegar a esa llamada.
- **Se escribe lo que la persona confirmo, no lo que propuso el modelo.** Los argumentos
  propuestos y los confirmados quedan los dos guardados, y su diferencia es justamente lo que
  hay que poder auditar despues.

## El candado: una propuesta se aplica una sola vez

`confirmar` reclama la propuesta con un UPDATE condicional de `pendiente` a `aplicando`. Un
doble clic o un reintento del navegador llega cuando el estado ya no es `pendiente`, y ahi no
se vuelve a escribir: se devuelve el resultado que quedo guardado. El estado `aplicando` existe
precisamente para que, si el proceso se muere a mitad de camino, la propuesta quede en un
estado que un humano tiene que mirar y no en uno que se pueda reintentar solo.

## El riesgo se calcula al proponer, no al aplicar

`agregar_repuesto` mueve plata y `actualizar_ot` puede disparar un WhatsApp al cliente, que no
se puede deshacer. Si eso se supiera despues de aplicar, la persona ya confirmo a ciegas. Por
eso `risk` y `requires_notification` se resuelven cuando se propone, y se muestran en la
pantalla de confirmacion.
"""
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.ai_action_proposal import (
    APLICADA,
    APLICANDO,
    FALLIDA,
    PENDIENTE,
    RECHAZADA,
    RIESGO_COMUNICACION,
    RIESGO_FINANCIERO,
    RIESGO_NINGUNO,
    AiActionProposal,
)

# Error de negocio de una propuesta. No es un 500: es "esto no se puede aplicar", con motivo.
class ErrorDePropuesta(Exception):
    def __init__(self, mensaje: str, codigo: str = "no_aplicable"):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.codigo = codigo


class NoEncontrada(Exception):
    """La propuesta no existe o es de otra empresa. Son indistinguibles a proposito."""


class YaResuelta(Exception):
    """La propuesta ya se resolvio. Se devuelve el resultado guardado, sin volver a escribir."""

    def __init__(self, propuesta: AiActionProposal):
        super().__init__(propuesta.status)
        self.propuesta = propuesta


# --------------------------------------------------------------------------------------
# Crear
# --------------------------------------------------------------------------------------


def crear(
    db: Session,
    *,
    company_id: int,
    user_id: int,
    tool: str,
    argumentos: dict,
    riesgo: str = RIESGO_NINGUNO,
    notifica: bool = False,
) -> AiActionProposal:
    """Registra lo que el modelo quiere hacer. No escribe nada del dominio."""
    propuesta = AiActionProposal(
        company_id=company_id,
        tool=tool,
        status=PENDIENTE,
        proposed_by_user_id=user_id,
        proposed_arguments=json.dumps(argumentos, ensure_ascii=False, default=str),
        risk=riesgo,
        requires_notification=notifica,
    )
    db.add(propuesta)
    db.commit()
    db.refresh(propuesta)
    return propuesta


# --------------------------------------------------------------------------------------
# Leer
# --------------------------------------------------------------------------------------


def obtener(db: Session, proposal_id: int, company_id: int) -> AiActionProposal:
    """Busca la propuesta acotada a la empresa. Una propuesta ajena no existe."""
    propuesta = db.execute(
        select(AiActionProposal).where(
            AiActionProposal.id == proposal_id,
            AiActionProposal.company_id == company_id,
        )
    ).scalars().first()
    if propuesta is None:
        raise NoEncontrada()
    return propuesta


def listar(
    db: Session, company_id: int, *, estados: list[str] | None = None, limite: int = 50
) -> list[AiActionProposal]:
    consulta = select(AiActionProposal).where(AiActionProposal.company_id == company_id)
    if estados:
        consulta = consulta.where(AiActionProposal.status.in_(estados))
    # `scalars()` es lo que devuelve los modelos y no las filas: sin eso, `propuesta.status`
    # falla con un AttributeError confuso en vez de devolver la propuesta.
    return list(
        db.execute(consulta.order_by(AiActionProposal.id.desc()).limit(min(limite, 200)))
        .scalars()
        .all()
    )


# --------------------------------------------------------------------------------------
# Resolver
# --------------------------------------------------------------------------------------


def confirmar(
    db: Session,
    proposal_id: int,
    *,
    company_id: int,
    user_id: int,
    argumentos: dict | None = None,
) -> AiActionProposal:
    """Aplica la accion, escribiendo **los argumentos confirmados**.

    ``argumentos`` es lo que la persona confirmo, que puede ser lo mismo que propuso el modelo
    o estar corregido. Si viene None se confirma tal cual lo propuso. Lo que se escribe sale de
    aca, no de ``proposed_arguments``: esa columna es el registro de lo que quiso el modelo, no
    una fuente de verdad.
    """
    propuesta = obtener(db, proposal_id, company_id)

    # Reclamo atomico. Un solo UPDATE condicional gana la carrera: el que pierde ve que ya no
    # esta pendiente y no escribe.
    reclamado = db.execute(
        update(AiActionProposal)
        .where(
            AiActionProposal.id == proposal_id,
            AiActionProposal.company_id == company_id,
            AiActionProposal.status == PENDIENTE,
        )
        .values(status=APLICANDO)
    ).rowcount
    db.commit()

    if not reclamado:
        db.refresh(propuesta)
        if propuesta.status == APLICADA:
            # Reintento: se devuelve lo que ya se hizo, sin escribir de nuevo.
            raise YaResuelta(propuesta)
        if propuesta.status == APLICANDO:
            raise ErrorDePropuesta(
                "Esta propuesta se esta aplicando en este momento. Recargá en un segundo.",
                codigo="en_curso",
            )
        raise ErrorDePropuesta(
            f"La propuesta ya está {propuesta.status} y no se puede volver a aplicar.",
            codigo="ya_resuelta",
        )

    confirmados = dict(propuesta.proposed_arguments and json.loads(propuesta.proposed_arguments) or {})
    if argumentos is not None:
        if not isinstance(argumentos, dict):
            raise ErrorDePropuesta("Los argumentos confirmados tienen que ser un objeto.",
                                   codigo="argumentos_invalidos")
        confirmados = argumentos

    propuesta.confirmed_arguments = json.dumps(confirmados, ensure_ascii=False, default=str)
    propuesta.confirmed_by_user_id = user_id
    propuesta.confirmed_at = datetime.utcnow()
    db.add(propuesta)

    try:
        referencia, notificado = _aplicar(db, propuesta.tool, company_id, user_id, confirmados)
    except ErrorDePropuesta as exc:
        db.rollback()
        # La propuesta queda registrada como fallida con su motivo: eso tambien es auditabilidad.
        fallida = db.execute(
            update(AiActionProposal)
            .where(AiActionProposal.id == proposal_id, AiActionProposal.company_id == company_id)
            .values(
                status=FALLIDA,
                result_error=str(exc.mensaje)[:500],
                confirmed_arguments=json.dumps(confirmados, ensure_ascii=False, default=str),
                confirmed_by_user_id=user_id,
                confirmed_at=datetime.utcnow(),
            )
        )
        db.commit()
        raise

    propuesta.status = APLICADA
    propuesta.applied_at = datetime.utcnow()
    propuesta.result_reference = json.dumps(referencia, ensure_ascii=False, default=str)
    propuesta.notified = bool(notificado)
    db.add(propuesta)
    db.commit()
    db.refresh(propuesta)
    return propuesta


def rechazar(db: Session, proposal_id: int, *, company_id: int) -> AiActionProposal:
    propuesta = obtener(db, proposal_id, company_id)
    if propuesta.status in (APLICADA, APLICANDO):
        raise ErrorDePropuesta("La propuesta ya se está aplicando: no se puede rechazar.",
                               codigo="ya_resuelta")
    if propuesta.status == RECHAZADA:
        return propuesta
    propuesta.status = RECHAZADA
    db.add(propuesta)
    db.commit()
    db.refresh(propuesta)
    return propuesta


# --------------------------------------------------------------------------------------
# Los aplicadores: uno por herramienta de escritura
# --------------------------------------------------------------------------------------


def _monto(valor: Any) -> Decimal:
    return Decimal(str(valor if valor is not None else 0)).quantize(Decimal("0.01"))


def _aplicar_crear_cliente(db: Session, company_id: int, user_id: int, a: dict) -> tuple[dict, bool]:
    from app.models.customer import Customer
    from app.services.ai.tools.validacion import (
        MAX_DIRECCION,
        MAX_DOCUMENTO,
        MAX_EMAIL,
        MAX_NOMBRE,
        MAX_TELEFONO,
        texto,
        texto_opcional,
    )

    nombre = texto(a.get("nombre"), "nombre", maximo=MAX_NOMBRE)
    documento = texto_opcional(a.get("documento"), "documento", maximo=MAX_DOCUMENTO)
    if documento:
        existe = db.execute(
            select(Customer.id).where(
                Customer.company_id == company_id, Customer.document == documento
            )
        ).first()
        if existe:
            raise ErrorDePropuesta(f"Ya hay un cliente con el documento {documento} en esta empresa.",
                                   codigo="documento_duplicado")
    fila = Customer(
        company_id=company_id,
        name=nombre,
        document=documento,
        phone=texto_opcional(a.get("telefono"), "telefono", maximo=MAX_TELEFONO),
        whatsapp=texto_opcional(a.get("whatsapp"), "whatsapp", maximo=MAX_TELEFONO),
        email=texto_opcional(a.get("email"), "email", maximo=MAX_EMAIL),
        address=texto_opcional(a.get("direccion"), "direccion", maximo=MAX_DIRECCION),
        notes=texto_opcional(a.get("notas"), "notas"),
    )
    db.add(fila)
    db.flush()
    return {"tipo": "cliente", "id": fila.id, "nombre": fila.name}, False


def _aplicar_crear_equipo(db: Session, company_id: int, user_id: int, a: dict) -> tuple[dict, bool]:
    from app.models.customer import Customer, Equipment, EquipmentCategory
    from app.services.ai.tools.validacion import (
        MAX_DESCRIPCION,
        MAX_MARCA,
        MAX_MODELO,
        MAX_NOMBRE,
        MAX_SERIE,
        entero,
        texto,
        texto_opcional,
    )

    cliente_id = entero(a.get("cliente_id"), "cliente_id", minimo=1)
    cliente = db.execute(
        select(Customer).where(
            Customer.id == cliente_id,
            Customer.company_id == company_id,
            Customer.active.is_(True),
        )
    ).scalars().first()
    if cliente is None:
        raise ErrorDePropuesta("El cliente no existe en esta empresa o está inactivo.",
                               codigo="cliente_invalido")

    # La categoria se busca por nombre: el modelo no deberia inventar un id de categoria, y las
    # categorias las crea la empresa con sus propios nombres.
    nombre_categoria = texto(a.get("categoria"), "categoria", maximo=MAX_NOMBRE)
    categoria = db.execute(
        select(EquipmentCategory).where(
            EquipmentCategory.company_id == company_id,
            EquipmentCategory.name == nombre_categoria,
            EquipmentCategory.active.is_(True),
        )
    ).scalars().first()
    if categoria is None:
        disponibles = [
            c for (c,) in db.execute(
                select(EquipmentCategory.name).where(
                    EquipmentCategory.company_id == company_id,
                    EquipmentCategory.active.is_(True),
                ).order_by(EquipmentCategory.name)
            ).all()
        ]
        raise ErrorDePropuesta(
            f'No existe la categoría "{nombre_categoria}" en esta empresa. '
            f"Las que hay son: {', '.join(disponibles) or 'ninguna, hay que crearla primero'}.",
            codigo="categoria_invalida",
        )

    fila = Equipment(
        company_id=company_id,
        customer_id=cliente.id,
        category_id=categoria.id,
        brand=texto_opcional(a.get("marca"), "marca", maximo=MAX_MARCA),
        model=texto_opcional(a.get("modelo"), "modelo", maximo=MAX_MODELO),
        serial_number=texto_opcional(a.get("numero_de_serie"), "numero_de_serie", maximo=MAX_SERIE),
        description=texto_opcional(a.get("descripcion"), "descripcion", maximo=MAX_DESCRIPCION),
        notes=texto_opcional(a.get("notas"), "notas"),
    )
    db.add(fila)
    db.flush()
    return {
        "tipo": "equipo",
        "id": fila.id,
        "cliente": cliente.name,
        "descripcion": fila.serial_number or fila.description or "",
    }, False


def _aplicar_crear_ot(db: Session, company_id: int, user_id: int, a: dict) -> tuple[dict, bool]:
    from app.services.work_orders import crear_orden
    from app.services.ai.tools.validacion import MAX_TEXTO, entero, texto, texto_opcional

    orden = crear_orden(
        db,
        company_id=company_id,
        user_id=user_id,
        customer_id=entero(a.get("cliente_id"), "cliente_id", minimo=1),
        equipment_id=entero(a.get("equipo_id"), "equipo_id", minimo=1),
        reported_fault=texto(a.get("falla_reportada"), "falla_reportada", maximo=MAX_TEXTO),
        physical_condition=texto_opcional(a.get("condicion_fisica"), "condicion_fisica", maximo=MAX_TEXTO),
        accessories=texto_opcional(a.get("accesorios"), "accesorios", maximo=MAX_TEXTO),
        notes=texto_opcional(a.get("notas"), "notas", maximo=MAX_TEXTO),
    )
    return {
        "tipo": "orden_de_trabajo",
        "id": orden.id,
        "numero": orden.number,
        "cliente": orden.customer.name if orden.customer else "",
    }, False


def _aplicar_actualizar_ot(db: Session, company_id: int, user_id: int, a: dict) -> tuple[dict, bool]:
    from app.services.work_orders import actualizar_orden
    from app.services.ai.tools.validacion import MAX_TEXTO, entero, texto_opcional

    cambios = {
        "expected_delivery_at": a.get("entrega_estimada"),
        "notes": texto_opcional(a.get("notas"), "notas", maximo=MAX_TEXTO),
        "physical_condition": texto_opcional(a.get("condicion_fisica"), "condicion_fisica", maximo=MAX_TEXTO),
        "accessories": texto_opcional(a.get("accesorios"), "accesorios", maximo=MAX_TEXTO),
        "status_id": entero(a["estado_id"], "estado_id", minimo=1) if a.get("estado_id") is not None else None,
    }
    cambios = {k: v for k, v in cambios.items() if v is not None}
    if not cambios:
        raise ErrorDePropuesta("La propuesta no trae ningún campo para actualizar.",
                               codigo="sin_cambios")
    orden, notificado = actualizar_orden(
        db, company_id=company_id, user_id=user_id,
        work_order_id=entero(a.get("orden"), "orden", minimo=1), cambios=cambios,
    )
    return {"tipo": "orden_de_trabajo", "id": orden.id, "numero": orden.number,
            "campos": sorted(cambios)}, notificado


def _aplicar_agregar_diagnostico(db: Session, company_id: int, user_id: int, a: dict) -> tuple[dict, bool]:
    from app.services.work_orders import guardar_diagnostico
    from app.services.ai.tools.validacion import MAX_TEXTO, entero, texto, texto_opcional

    diagnostico = guardar_diagnostico(
        db, company_id=company_id, user_id=user_id,
        work_order_id=entero(a.get("orden"), "orden", minimo=1),
        diagnosis=texto(a.get("diagnostico"), "diagnostico", maximo=MAX_TEXTO),
        technical_notes=texto_opcional(a.get("notas_tecnicas"), "notas_tecnicas", maximo=MAX_TEXTO),
    )
    return {"tipo": "diagnostico", "id": diagnostico.id, "orden": diagnostico.work_order_id}, False


def _item_ejecucion(db: Session, company_id: int, user_id: int, a: dict, item_type: str) -> tuple[dict, bool]:
    from app.models.work_order import WorkOrder, WorkOrderEvent
    from app.models.work_order_quote import WorkOrderExecutionItem
    from app.services.ai.tools.validacion import (
        MAX_TEXTO_CORTO,
        decimal,
        entero,
        texto,
    )
    from app.services.work_orders import assert_no_final

    work_order_id = entero(a.get("orden"), "orden", minimo=1)
    orden = db.execute(
        select(WorkOrder).where(WorkOrder.id == work_order_id, WorkOrder.company_id == company_id)
    ).scalars().first()
    if orden is None:
        raise ErrorDePropuesta("La orden no existe en esta empresa.", codigo="orden_invalida")
    assert_no_final(db, orden)

    descripcion = texto(a.get("descripcion"), "descripcion", maximo=MAX_TEXTO_CORTO)
    cantidad = decimal(a.get("cantidad", 1), "cantidad", minimo="0.001")
    precio = decimal(a.get("precio_unitario", 0), "precio_unitario", minimo="0")

    # El costo interno **no** lo propone la IA. Es un dato del negocio, y ademas la empresa
    # puede tenerlos ocultos del cliente: que la IA pueda fijarlo seria escribir un dato que ni
    # siquiera el operador ve. La persona lo puede completar al confirmar.
    costo = decimal(a["costo_unitario"], "costo_unitario", minimo="0") if a.get("costo_unitario") is not None else None

    fila = WorkOrderExecutionItem(
        company_id=company_id,
        work_order_id=orden.id,
        item_type=item_type,
        description=descripcion,
        quantity=cantidad,
        unit_cost=_monto(costo) if costo is not None else Decimal("0"),
        unit_price=_monto(precio),
        created_by_user_id=user_id,
    )
    db.add(fila)
    db.add(
        WorkOrderEvent(
            company_id=company_id,
            work_order_id=orden.id,
            event_type="WORK_EXECUTED",
            status=orden.status,
            detail=("Repuesto utilizado: " if item_type == "PART" else "Trabajo realizado: ")
            + descripcion,
            user_id=user_id,
        )
    )
    db.flush()
    return {
        "tipo": "repuesto" if item_type == "PART" else "trabajo",
        "id": fila.id,
        "orden": orden.id,
        "precio_unitario": float(_monto(precio)),
    }, False


def _aplicar_agregar_repuesto(db: Session, company_id: int, user_id: int, a: dict) -> tuple[dict, bool]:
    return _item_ejecucion(db, company_id, user_id, a, "PART")


def _aplicar_agregar_trabajo(db: Session, company_id: int, user_id: int, a: dict) -> tuple[dict, bool]:
    # "LABOR", no "WORK": es el valor que usa el resto del dominio. La API lo valida con
    # ^(PART|LABOR)$ y la pantalla separa con `item_type === "PART"`. Con "WORK" la fila
    # quedaba fuera del vocabulario. El calculo del presupuesto no se enteraba porque trata
    # como repuesto solo lo que dice "PART", pero cualquier consulta que filtre
    # `item_type = 'LABOR'` dejaba estas filas afuera, y no por una decision sino por un
    # valor mal escrito. Dependia de que al escribir la fila alguien se acordara.
    return _item_ejecucion(db, company_id, user_id, a, "LABOR")


def _aplicar_generar_presupuesto(db: Session, company_id: int, user_id: int, a: dict) -> tuple[dict, bool]:
    """Emite el presupuesto con las lineas que salen de la orden en este momento.

    Las lineas se vuelven a calcular aca y no se leen de lo que propuso el modelo, por dos
    razones. La primera es que la propuesta no trae importes: no hay de donde copiarlos. La
    segunda es que entre que se propuso y se confirmo la orden pudo cambiar, y lo que vale es
    lo que hay ahora.
    """
    from app.services import work_orders as wo_service
    from app.services.ai.tools.validacion import MAX_TEXTO, entero, texto_opcional

    orden_id = entero(a.get("orden"), "orden", minimo=1)
    notas = texto_opcional(a.get("notas"), "notas", maximo=MAX_TEXTO)

    try:
        calculo = wo_service.calcular_presupuesto(
            db, company_id=company_id, work_order_id=orden_id
        )
    except wo_service.ErrorDeDominio as exc:
        raise ErrorDePropuesta(exc.mensaje, codigo=exc.codigo) from None

    if not calculo["puede_generar"]:
        motivos = list(calculo["motivos_de_dominio"]) + list(calculo["pendientes"])
        raise ErrorDePropuesta(
            "El presupuesto ya no se puede generar: " + " ".join(motivos),
            codigo="presupuesto_incompleto",
        )

    items = [
        {
            "item_type": linea["tipo"],
            "description": linea["descripcion"],
            "quantity": linea["cantidad"],
            "unit_cost": linea.get("costo_unitario") or 0,
            # El precio ya viene resuelto por el calculo. Pasarlo explicito evita que el
            # servicio lo vuelva a multiplicar por el markup y termine en otra cifra.
            "unit_price": linea["precio_unitario"],
        }
        for linea in calculo["items"]
    ]

    try:
        presupuesto = wo_service.crear_presupuesto(
            db, company_id=company_id, user_id=user_id,
            work_order_id=orden_id, items=items, notes=notas,
        )
    except wo_service.ErrorDeDominio as exc:
        raise ErrorDePropuesta(exc.mensaje, codigo=exc.codigo) from None

    return {
        "tipo": "presupuesto",
        "id": presupuesto.id,
        "orden": orden_id,
        "version": presupuesto.version,
        "total": float(presupuesto.total),
        "lineas": len(items),
    }, False


def _aplicar_preparar_comunicacion_cliente(
    db: Session, company_id: int, user_id: int, a: dict
) -> tuple[dict, bool]:
    """Encola el aviso en PENDING. Devolver `False` en el segundo valor es lo que hace que
    `_despachar` no lo mande: confirmar la propuesta **no** envia el mensaje.

    Ese `False` es el mecanismo, no una convencion. Si volviera True, confirmar seria enviar,
    y el sub-issue pide justo lo contrario: preparar y que lo mande una persona.
    """
    from app.services import work_orders as wo_service
    from app.services.ai.tools.validacion import MAX_TEXTO, entero, texto, texto_opcional
    from app.services.notifications.channels import EMAIL, WHATSAPP

    orden_id = entero(a.get("orden"), "orden", minimo=1)
    mensaje = texto_opcional(a.get("mensaje"), "mensaje", maximo=MAX_TEXTO)
    canal = a.get("canal")
    canales: dict[str, dict] = {}
    if canal is not None:
        elegido = texto(canal, "canal", maximo=20).upper()
        if elegido not in (EMAIL, WHATSAPP):
            raise ErrorDePropuesta(
                f"El canal tiene que ser {WHATSAPP} o {EMAIL}.", codigo="canal_invalido"
            )
        canales[elegido] = {}
    if mensaje is not None:
        for nombre in canales or {EMAIL: {}, WHATSAPP: {}}:
            canales.setdefault(nombre, {})["body"] = mensaje

    try:
        filas = wo_service.preparar_comunicacion(
            db, company_id=company_id, user_id=user_id,
            work_order_id=orden_id, overrides=canales or None,
        )
    except wo_service.ErrorDeDominio as exc:
        raise ErrorDePropuesta(exc.mensaje, codigo=exc.codigo) from None

    return {
        "tipo": "aviso",
        "orden": orden_id,
        "notificaciones": [f.id for f in filas],
        "canales": [f.channel for f in filas],
        "estado": "pendiente de envío",
    }, False


APLICADORES: dict[str, Callable[..., tuple[dict, bool]]] = {
    "crear_cliente": _aplicar_crear_cliente,
    "crear_equipo": _aplicar_crear_equipo,
    "crear_ot": _aplicar_crear_ot,
    "actualizar_ot": _aplicar_actualizar_ot,
    "agregar_diagnostico": _aplicar_agregar_diagnostico,
    "agregar_trabajo": _aplicar_agregar_trabajo,
    "agregar_repuesto": _aplicar_agregar_repuesto,
    "generar_presupuesto": _aplicar_generar_presupuesto,
    "preparar_comunicacion_cliente": _aplicar_preparar_comunicacion_cliente,
}


def _aplicar(
    db: Session, tool: str, company_id: int, user_id: int, argumentos: dict
) -> tuple[dict, bool]:
    aplicador = APLICADORES.get(tool)
    if aplicador is None:
        raise ErrorDePropuesta(f'No hay aplicador para la herramienta "{tool}".',
                               codigo="herramienta_desconocida")
    return aplicador(db, company_id, user_id, argumentos)


# --------------------------------------------------------------------------------------
# Serializacion para la API
# --------------------------------------------------------------------------------------


def serializar(propuesta: AiActionProposal) -> dict:
    """La propuesta como la ve la pantalla, con lo propuesto y lo confirmado por separado.

    La diferencia entre los dos es el dato mas importante de toda la pantalla: es ahi donde se
    ve que la persona corrigio al modelo.
    """
    propuesto = json.loads(propuesta.proposed_arguments) if propuesta.proposed_arguments else {}
    confirmado = (
        json.loads(propuesta.confirmed_arguments) if propuesta.confirmed_arguments else None
    )
    corregido = (
        {k: v for k, v in (confirmado or {}).items() if (propuesto or {}).get(k) != v}
        if confirmado is not None
        else None
    )
    return {
        "id": propuesta.id,
        "tool": propuesta.tool,
        "status": propuesta.status,
        "riesgo": propuesta.risk,
        "notifica_cliente": propuesta.requires_notification,
        "notificado": propuesta.notified,
        "argumentos_propuestos": propuesto,
        "argumentos_confirmados": confirmado,
        "lo_que_cambio": corregido,
        "resultado": json.loads(propuesta.result_reference) if propuesta.result_reference else None,
        "error": propuesta.result_error,
        "propuesta_por": propuesta.proposed_by_user_id,
        "confirmada_por": propuesta.confirmed_by_user_id,
        "confirmada_en": propuesta.confirmed_at.isoformat() if propuesta.confirmed_at else None,
        "aplicada_en": propuesta.applied_at.isoformat() if propuesta.applied_at else None,
        "creada_en": propuesta.created_at.isoformat() if propuesta.created_at else None,
    }
