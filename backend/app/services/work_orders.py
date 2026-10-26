"""Logica de dominio de la orden de trabajo, reutilizable.

Existe por una razon concreta: la API y las propuestas de la IA tienen que **escribir por el
mismo camino**. Si las herramientas de escritura reimplementaran la numeracion de orden, los
estados iniciales o el encolado de avisos, estarian aplicando reglas que la aplicacion no
aplica. Un mismo dominio con dos reglas siempre termina en dos reglas distintas, y la que
sobra es la que no tiene tests.

Por eso los handlers de `work_orders.py` delegan aca. Un error de negocio se levanta como
``ErrorDeDominio`` y cada capa lo traduce a lo suyo: la API a un 409/422, y las propuestas a un
motivo que se muestra en la pantalla de confirmacion.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core.warranty import ETIQUETA_GARANTIA, estado_de_garantia
from app.models.company import Company, CompanyParameter, ParameterDefinition
from app.models.customer import Customer, Equipment
from app.models.work_order import WorkOrder, WorkOrderCounter, WorkOrderEvent, WorkOrderNotification, WorkOrderStatus
from app.models.work_order_part import WorkOrderPart, WorkOrderTechnician
from app.models.work_area import Technician, WorkArea
from app.models.work_order_quote import (
    WorkOrderDiagnosis,
    WorkOrderExecutionItem,
    WorkOrderQuote,
    WorkOrderQuoteItem,
)
from app.services.notifications.enqueue import enqueue_for_event, plan_for_event


class ErrorDeDominio(Exception):
    """Regla de negocio incumplida. No es un error del sistema."""

    def __init__(self, mensaje: str, codigo: str = "no_aplicable", status_http: int = 422):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.codigo = codigo
        self.status_http = status_http


def utcnow() -> datetime:
    return datetime.utcnow()


# --------------------------------------------------------------------------------------
# Parametros de la empresa
# --------------------------------------------------------------------------------------


def parameter_bool(db: Session, company_id: int, key: str, default: bool = True) -> bool:
    """Lee un parametro booleano de la empresa, con el default de la definicion.

    Vive aca y no en la API porque lo consultan dos caminos: la pantalla y el calculo del
    presupuesto que hace la IA. Si cada uno leyera el valor por su cuenta, una empresa podria
    tener dos reglas distintas para el mismo parametro.
    """
    definicion = db.query(ParameterDefinition).filter_by(parameter=key, active=True).first()
    if definicion is None:
        return default
    valor = db.query(CompanyParameter).filter_by(
        company_id=company_id, parameter_definition_id=definicion.id
    ).first()
    crudo = valor.value if valor else definicion.default_value
    return str(crudo).strip().lower() in ("1", "true", "yes", "si", "sí", "on")


def markup_partes(db: Session, company_id: int) -> Decimal:
    """El margen que la empresa carga sobre los repuestos. La mano de obra no lleva."""
    definicion = db.query(ParameterDefinition).filter_by(
        parameter="pricing.parts_markup_percent", active=True
    ).first()
    if definicion is None:
        return Decimal("0")
    valor = db.query(CompanyParameter).filter_by(
        company_id=company_id, parameter_definition_id=definicion.id
    ).first()
    return Decimal(valor.value if valor else definicion.default_value)


def money(valor: Any) -> Decimal:
    return Decimal(valor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# --------------------------------------------------------------------------------------
# Consultas
# --------------------------------------------------------------------------------------


def leer_orden(db: Session, company_id: int, work_order_id: int) -> WorkOrder:
    orden = db.query(WorkOrder).filter_by(id=work_order_id, company_id=company_id).first()
    if orden is None:
        raise ErrorDeDominio("La orden de trabajo no existe en esta empresa.", "orden_invalida", 404)
    return orden


def es_final(db: Session, orden: WorkOrder) -> bool:
    """True cuando la orden esta en un estado marcado como final (por ejemplo, entregada)."""
    if orden.status_id is None:
        return False
    estado = db.get(WorkOrderStatus, orden.status_id)
    return bool(estado and estado.is_final)


def assert_no_final(db: Session, orden: WorkOrder) -> None:
    if es_final(db, orden):
        raise ErrorDeDominio(
            "La orden está en un estado final y no admite cambios ni trabajos nuevos.",
            "orden_final",
            409,
        )


def siguiente_numero(db: Session, company_id: int) -> int:
    """El proximo numero de orden de la empresa.

    MySQL usa LAST_INSERT_ID dentro de un INSERT ... ON DUPLICATE KEY UPDATE para que el
    contador se incremente en una sola sentencia y sin bloqueos. SQLite, que es lo que corre la
    suite, usa la fila del contador.
    """
    dialecto = db.get_bind().dialect.name
    if dialecto == "mysql":
        db.execute(
            text(
                "INSERT INTO work_order_counters (company_id,last_number) VALUES (:cid,LAST_INSERT_ID(1))"
                " ON DUPLICATE KEY UPDATE last_number=LAST_INSERT_ID(last_number+1)"
            ),
            {"cid": company_id},
        )
        return int(db.execute(text("SELECT LAST_INSERT_ID()")).scalar_one())
    contador = db.get(WorkOrderCounter, company_id)
    if not contador:
        contador = WorkOrderCounter(company_id=company_id, last_number=1)
        db.add(contador)
        db.flush()
        return 1
    contador.last_number += 1
    db.flush()
    return contador.last_number


# --------------------------------------------------------------------------------------
# Crear
# --------------------------------------------------------------------------------------


def crear_orden(
    db: Session,
    *,
    company_id: int,
    user_id: int,
    customer_id: int,
    equipment_id: int,
    reported_fault: str,
    physical_condition: str | None = None,
    accessories: str | None = None,
    notes: str | None = None,
    technician_id: int | None = None,
    work_area_id: int | None = None,
) -> WorkOrder:
    """Crea la orden con su numero y su evento de recepcion.

    No hace commit: la transaccion la cierra quien la llama, que puede ser el endpoint o la
    aplicacion de una propuesta.

    ``technician_id`` es opcional: el legacy asignaba el tecnico despues, en el taller. Si se
    pasa, la OT queda con ese tecnico asignado desde el arranque.

    ``work_area_id`` es opcional y es lo que decide si la OT entra al cierre a marcas: el
    cierre hace JOIN por el area y exige que el area tenga empresa a liquidar. Sin area, la
    OT se crea igual, pero no aparece en ningun cierre hasta que se le ponga una.
    """
    cliente = db.query(Customer).filter_by(
        id=customer_id, company_id=company_id, active=True
    ).first()
    if not cliente:
        raise ErrorDeDominio("El cliente no pertenece a esta empresa o está inactivo.",
                            "cliente_invalido", 422)
    equipo = db.query(Equipment).filter_by(
        id=equipment_id, customer_id=customer_id, company_id=company_id, active=True
    ).first()
    if not equipo:
        raise ErrorDeDominio("El equipo no pertenece al cliente y empresa activos.",
                            "equipo_invalido", 422)

    area = None
    if work_area_id is not None:
        area = db.query(WorkArea).filter_by(
            id=work_area_id, company_id=company_id
        ).first()
        if not area:
            raise ErrorDeDominio(
                "El área de trabajo no pertenece a esta empresa.", "area_invalida", 422
            )

    numero = siguiente_numero(db, company_id)
    inicial = (
        db.query(WorkOrderStatus)
        .filter_by(company_id=company_id, is_initial=True, active=True)
        .order_by(WorkOrderStatus.sort_order)
        .first()
    )
    orden = WorkOrder(
        company_id=company_id,
        number=numero,
        received_by_user_id=user_id,
        status="RECEIVED",
        status_id=inicial.id if inicial else None,
        customer_id=cliente.id,
        equipment_id=equipo.id,
        reported_fault=reported_fault,
        physical_condition=physical_condition,
        accessories=accessories,
        notes=notes,
        work_area_id=area.id if area else None,
        # La garantia de la OT es una copia de la del area: asi lo dejaba el legacy
        # (dbo.CS_PoliticasxArea.Garantia), y es lo que lee el cierre a marcas.
        warranty_status=estado_de_garantia(area.warranty_type) if area else None,
    )
    db.add(orden)
    db.flush()
    db.add(
        WorkOrderEvent(
            company_id=company_id,
            work_order_id=orden.id,
            event_type="RECEPTION",
            status="RECEIVED",
            detail=(
                "Equipo recibido y orden de trabajo generada. "
                + _detalle_area(db, area)
            ),
            user_id=user_id,
        )
    )
    db.flush()
    if technician_id is not None:
        tecnico = db.query(Technician).filter_by(
            id=technician_id, company_id=company_id
        ).first()
        if not tecnico:
            raise ErrorDeDominio(
                "El técnico no pertenece a esta empresa.", "tecnico_invalido", 422
            )
        if not tecnico.active:
            raise ErrorDeDominio(
                "El técnico está desactivado: activalo desde el maestro para poder asignarlo.",
                "tecnico_inactivo",
                409,
            )
        db.add(
            WorkOrderTechnician(
                company_id=company_id,
                work_order_id=orden.id,
                technician_id=tecnico.id,
            )
        )
        db.add(
            WorkOrderEvent(
                company_id=company_id,
                work_order_id=orden.id,
                event_type="technician_assigned",
                detail=f"Técnico asignado: {tecnico.name}",
                user_id=user_id,
            )
        )
        db.flush()
    return orden


def etiqueta_area(area: WorkArea | None) -> str:
    """Como se muestra un area: marca + politica (la politica vacia es la principal)."""
    if not area:
        return "sin área"
    if area.policy_code:
        return f"{area.area_name} · {area.policy_code}"
    return area.area_name


def _detalle_area(db: Session, area: WorkArea | None) -> str:
    """El area con su garantia y a quien se liquida, en una frase.

    Es lo que queda escrito en el historial de la orden: dejar explicito a quien se le
    liquida es lo que hace auditable el cierre, y lo que evita el "no se donde lo metieron".
    """
    if not area:
        return "Sin área de trabajo: la orden no entra al cierre a marcas."
    partes = [
        f"Área: {etiqueta_area(area)}",
        f"Garantía: {ETIQUETA_GARANTIA.get(area.warranty_type, ETIQUETA_GARANTIA[0])}",
    ]
    if area.billing_customer_id:
        empresa = db.get(Customer, area.billing_customer_id)
        if empresa:
            partes.append(f"Se liquida a: {empresa.name}")
    else:
        partes.append("No se liquida a ninguna empresa")
    return ". ".join(partes) + "."


def asignar_area(
    db: Session,
    *,
    orden: WorkOrder,
    company_id: int,
    user_id: int,
    work_area_id: int | None,
) -> WorkOrder:
    """Le pone (o le quita) el area de trabajo a una orden ya abierta.

    La garantia de la OT se recalcula desde el area: no se escribe suelta, para que la
    OT y el cierre a marcas no puedan discrepar.

    El cambio queda en el historial de la orden: corregir la garantia de una OT que ya
    estaba cargada es un cambio de criterio, y tiene que verse.
    """
    area = None
    if work_area_id is not None:
        area = db.query(WorkArea).filter_by(
            id=work_area_id, company_id=company_id
        ).first()
        if not area:
            raise ErrorDeDominio(
                "El área de trabajo no pertenece a esta empresa.", "area_invalida", 422
            )
    anterior = db.get(WorkArea, orden.work_area_id) if orden.work_area_id else None
    orden.work_area_id = area.id if area else None
    orden.warranty_status = estado_de_garantia(area.warranty_type) if area else None
    if anterior and area and anterior.id != area.id:
        detalle = (
            f"Área de trabajo cambiada: {etiqueta_area(anterior)} → "
            f"{etiqueta_area(area)}. {_detalle_area(db, area)}"
        )
    elif area:
        detalle = f"Área de trabajo: {etiqueta_area(area)}. {_detalle_area(db, area)}"
    else:
        detalle = "Área de trabajo quitada. La orden deja de entrar al cierre a marcas."
    db.add(
        WorkOrderEvent(
            company_id=company_id,
            work_order_id=orden.id,
            event_type="WORK_AREA_CHANGE",
            status=orden.status,
            detail=detalle,
            user_id=user_id,
        )
    )
    db.flush()
    return orden


# --------------------------------------------------------------------------------------
# Finalización técnica: lo que hace que la orden entre al cierre a marcas
# --------------------------------------------------------------------------------------


def tiene_costo_cargado(db: Session, orden: WorkOrder) -> bool:
    """True si la orden tiene algo que liquidar.

    El cierre liquida el **costo**: ``work_orders.cost_total`` en las ordenes que vienen del
    legacy, y para las nacidas en el sistema nuevo la suma de las lineas (costo x cantidad),
    que es el mismo criterio que usa ``warranty_settlements``.

    Se pregunta antes de anotar la finalizacion tecnica al entregar: una orden sin costo no
    mueve plata, y darla por finalizada seria dar por hecho un trabajo que no se cargo.
    """
    if (orden.cost_total or 0) > 0:
        return True
    total = (
        db.query(func.coalesce(func.sum(WorkOrderPart.unit_cost * WorkOrderPart.quantity), 0))
        .filter(WorkOrderPart.work_order_id == orden.id)
        .scalar()
    )
    return Decimal(str(total or 0)) > 0


def registrar_finalizacion_tecnica(
    db: Session,
    *,
    company_id: int,
    user_id: int,
    work_order_id: int,
    completed_at: datetime | None = None,
    motivo: str | None = None,
) -> WorkOrder:
    """Registra la finalizacion tecnica de una orden, **aunque ya este en estado final**.

    El cierre a marcas filtra por ``completed_at``, no por ``delivered_at``: una orden
    entregada sin finalizacion tecnica no aparece en ningun cierre. Ese era el hueco que
    dejaba sin liquidar trabajos de garantia que el taller ya habia entregado.

    A diferencia de cambiar el area o la fecha de entrega, aca **si** se puede tocar una
    orden en estado final: la finalizacion tecnica es un dato del trabajo hecho, no un
    cambio de estado, y corregirla es justamente lo que hace falta.

    El cambio queda escrito en el historial de la orden.
    """
    orden = leer_orden(db, company_id, work_order_id)
    if orden.completed_at is not None:
        raise ErrorDeDominio(
            "La orden ya tiene la finalización técnica registrada.",
            "finalizacion_ya_registrada",
            409,
        )
    momento = completed_at or utcnow()
    # Un reloj mal puesto no puede mandar la orden al futuro: ahi no la agarra ningun cierre.
    if momento > utcnow() + timedelta(minutes=5):
        raise ErrorDeDominio(
            "La finalización técnica no puede tener fecha futura.",
            "finalizacion_futura",
            422,
        )
    orden.completed_at = momento
    detalle = (
        "Finalización técnica registrada el "
        f"{momento.isoformat(sep=' ', timespec='minutes')}. "
        "Con esto la orden entra al cierre a marcas del período."
    )
    if motivo and motivo.strip():
        detalle += f" Observación: {motivo.strip()}"
    db.add(
        WorkOrderEvent(
            company_id=company_id,
            work_order_id=orden.id,
            event_type="TECHNICAL_COMPLETION",
            status=orden.status,
            detail=detalle,
            user_id=user_id,
        )
    )
    db.flush()
    return orden


# --------------------------------------------------------------------------------------
# Cambiar estado, y avisarle al cliente o no
# --------------------------------------------------------------------------------------


def planear_aviso(
    db: Session, *, company_id: int, work_order_id: int, status_id: int
) -> list[dict]:
    """Que avisos se mandarian si se aplicara ese cambio, **sin escribir nada**.

    Es lo que la propuesta muestra antes de que la persona confirme: si al aplicar se le va a
    escribir un WhatsApp al cliente, eso tiene que estar a la vista ANTES, porque un mensaje
    enviado no se puede deshacer.
    """
    orden = leer_orden(db, company_id, work_order_id)
    objetivo = db.query(WorkOrderStatus).filter_by(
        id=status_id, company_id=company_id, active=True
    ).first()
    if objetivo is None:
        raise ErrorDeDominio("El estado no pertenece a esta empresa o está inactivo.",
                            "estado_invalido", 422)
    empresa = db.get(Company, company_id)
    if empresa is None:
        return []
    return plan_for_event(db, empresa, orden, status=objetivo,
                          previous_status=db.get(WorkOrderStatus, orden.status_id) if orden.status_id else None)


def cambiar_estado(
    db: Session,
    *,
    company_id: int,
    user_id: int,
    work_order_id: int,
    status_id: int,
    note: str | None = None,
    overrides: dict | None = None,
) -> tuple[WorkOrder, list[int]]:
    """Mueve la orden a un estado, con su evento y el aviso que el estado pida.

    Devuelve la orden y los ids de las notificaciones encoladas. El encolado va en un
    savepoint: si falla, se revierte solo el encolado y el cambio de estado sigue. El commit
    lo hace quien la llama, asi que estado, evento y cola quedan juntos.
    """
    orden = leer_orden(db, company_id, work_order_id)
    if es_final(db, orden):
        raise ErrorDeDominio(
            "La orden de trabajo está en un estado final (entregada) y no puede cambiar de estado.",
            "orden_final", 409,
        )
    objetivo = db.query(WorkOrderStatus).filter_by(
        id=status_id, company_id=company_id, active=True
    ).first()
    if not objetivo:
        raise ErrorDeDominio("El estado no pertenece a esta empresa o está inactivo.",
                            "estado_invalido", 422)

    anterior = db.get(WorkOrderStatus, orden.status_id) if orden.status_id else None
    if orden.status_id == objetivo.id:
        return orden, []

    orden.status_id = objetivo.id
    orden.status = objetivo.name.upper().replace(" ", "_")[:30]
    ahora = utcnow()
    ciclo_de_vida = []
    if objetivo.marks_completed and orden.completed_at is None:
        orden.completed_at = ahora
        ciclo_de_vida.append("Se registró la finalización técnica.")
    elif (
        objetivo.marks_delivered
        and orden.completed_at is None
        and tiene_costo_cargado(db, orden)
    ):
        # El cierre a marcas filtra por `completed_at`. Una orden que se entrega con costo
        # cargado y sin finalizacion tecnica no entra en ningun cierre, asi que se anota
        # sola: el trabajo ya esta hecho y la plata hay que liquidarla.
        orden.completed_at = ahora
        ciclo_de_vida.append(
            "Se registró la finalización técnica: la orden tenía costo cargado y se entregó."
        )
    if objetivo.marks_delivered and orden.delivered_at is None:
        orden.delivered_at = ahora
        ciclo_de_vida.append("Se registró la entrega real al cliente.")

    detalle = f"Estado cambiado de {anterior.name if anterior else 'sin estado'} a {objetivo.name}."
    if ciclo_de_vida:
        detalle += " " + " ".join(ciclo_de_vida)
    if note and note.strip():
        detalle += f" Observación: {note.strip()}"

    evento = WorkOrderEvent(
        company_id=company_id,
        work_order_id=orden.id,
        event_type="STATUS_CHANGE",
        status=orden.status,
        detail=detalle,
        user_id=user_id,
    )
    db.add(evento)
    db.flush()

    encoladas: list[int] = []
    empresa = db.get(Company, company_id)
    if empresa is not None:
        try:
            with db.begin_nested():
                encoladas = [
                    n.id
                    for n in enqueue_for_event(
                        db, empresa, orden, evento, status=objetivo,
                        previous_status=anterior, overrides=overrides,
                    )
                ]
        except Exception:
            encoladas = []
    return orden, encoladas


# --------------------------------------------------------------------------------------
# Preparar un aviso al cliente sin mandarlo
# --------------------------------------------------------------------------------------


def planear_comunicacion(
    db: Session, *, company_id: int, work_order_id: int, overrides: dict | None = None
) -> list[dict]:
    """El aviso que se dejaria preparado **ahora**, sobre el estado en que esta la orden.

    No escribe nada, como `planear_aviso`. La diferencia es que aquel mira "que pasaria si la
    orden pasara a este otro estado" y este mira "que pasaria si preparase un aviso ahora".
    Las dos terminan en `plan_for_event`, que es el unico lugar donde se decide que se avisa y
    con que texto.
    """
    orden = leer_orden(db, company_id, work_order_id)
    empresa = db.get(Company, company_id)
    if empresa is None:
        return []
    estado = db.get(WorkOrderStatus, orden.status_id) if orden.status_id else None
    if estado is None or not (estado.notify_whatsapp or estado.notify_email):
        return []
    return plan_for_event(db, empresa, orden, status=estado, overrides=overrides)


def preparar_comunicacion(
    db: Session,
    *,
    company_id: int,
    user_id: int,
    work_order_id: int,
    overrides: dict | None = None,
) -> list[WorkOrderNotification]:
    """Deja el aviso **listo para enviar** y no lo envia. Devuelve las filas encoladas.

    Lo encolado va PENDIENTE, en la misma transaccion que su evento, como todos los avisos de
    #45. Quien lo manda es una persona, desde la OT, reviewing el texto exacto.

    Que sea una funcion aparte y no un `cambiar_estado` con la orden quieta es lo que evita el
    bug mas caro de esta parte: un aviso colgado de un evento de cambio de estado choca contra
    el unico (company_id, work_order_event_id, channel), y ademas el texto diria "paso a" algo
    que no paso. Por eso crea un evento propio, de tipo NOTICE.
    """
    orden = leer_orden(db, company_id, work_order_id)
    empresa = db.get(Company, company_id)
    estado = db.get(WorkOrderStatus, orden.status_id) if orden.status_id else None
    if empresa is None or estado is None:
        raise ErrorDeDominio(
            "La orden no tiene un estado del que sacar un aviso.", "estado_inexistente", 409
        )
    if not estado.notifications_active or not (estado.notify_whatsapp or estado.notify_email):
        raise ErrorDeDominio(
            f"El estado «{estado.name}» no tiene avisos al cliente configurados, así que no hay "
            "nada que preparar. Configuralos en Estados de OT, o pasá la orden a un estado que "
            "los tenga.",
            "sin_avisos_configurados", 422,
        )

    plan = plan_for_event(
        db, empresa, orden, status=estado, overrides=overrides
    )
    mandables = [p for p in plan if not p["skipped"]]
    if not mandables:
        # Se encolaria algo que el sistema sabe que no se puede mandar (sin numero, sin
        # email). Mejor decirlo ahora que dejar un SKIPPED que la persona tiene que
        # interpretar sola.
        razones = "; ".join(p["reason"] for p in plan if p.get("reason")) or "sin canales"
        raise ErrorDeDominio(
            f"No hay a quien mandarle el aviso: {razones}. Se puede preparar, pero no se va a "
            "enviar. Cargale un numero o un email al cliente.",
            "sin_destinatario", 422,
        )

    canales = ", ".join(p["channel"] for p in mandables)
    evento = WorkOrderEvent(
        company_id=company_id,
        work_order_id=orden.id,
        event_type="NOTICE",
        status=orden.status,
        detail=f"Aviso al cliente preparado para enviar por {canales}. Queda pendiente hasta que alguien lo envíe.",
        user_id=user_id,
    )
    db.add(evento)
    db.flush()

    encoladas = enqueue_for_event(
        db, empresa, orden, evento, status=estado, overrides=overrides
    )
    return encoladas


def actualizar_orden(
    db: Session,
    *,
    company_id: int,
    user_id: int,
    work_order_id: int,
    cambios: dict[str, Any],
) -> tuple[WorkOrder, list[int]]:
    """Aplica campos de la orden, incluido el estado si viene.

    ``cambios`` acepta ``expected_delivery_at``, ``notes``, ``physical_condition``,
    ``accessories`` y ``status_id``. El estado va por ``cambiar_estado`` para que los avisos
    sigan siendo los mismos que en la pantalla de la persona.
    """
    orden = leer_orden(db, company_id, work_order_id)
    status_id = cambios.get("status_id")
    encoladas: list[int] = []

    if status_id is not None:
        for clave in ("expected_delivery_at", "notes", "physical_condition", "accessories"):
            valor = cambios.get(clave)
            if valor is not None and hasattr(orden, clave):
                setattr(orden, clave, valor)
        orden, encoladas = cambiar_estado(
            db, company_id=company_id, user_id=user_id, work_order_id=orden.id,
            status_id=status_id, note=cambios.get("nota"),
        )
    else:
        assert_no_final(db, orden)
        for clave, valor in cambios.items():
            if clave in ("status_id", "nota") or valor is None:
                continue
            if hasattr(orden, clave):
                setattr(orden, clave, valor)
    db.flush()
    return orden, encoladas


# --------------------------------------------------------------------------------------
# Diagnostico
# --------------------------------------------------------------------------------------


def guardar_diagnostico(
    db: Session,
    *,
    company_id: int,
    user_id: int,
    work_order_id: int,
    diagnosis: str,
    technical_notes: str | None = None,
) -> WorkOrderDiagnosis:
    """Guarda el diagnostico de la orden. Es uno solo: si existe, se actualiza.

    Si un presupuesto cerro el diagnostico, no se toca: por eso el 409.
    """
    orden = leer_orden(db, company_id, work_order_id)
    actual = db.query(WorkOrderDiagnosis).filter_by(
        company_id=company_id, work_order_id=work_order_id
    ).first()
    if actual and not actual.is_open:
        raise ErrorDeDominio(
            "El diagnóstico está cerrado por un presupuesto. Reabrilo antes de modificarlo.",
            "diagnostico_cerrado", 409,
        )
    if actual:
        actual.diagnosis = diagnosis.strip()
        actual.technical_notes = technical_notes
        actual.diagnosed_by_user_id = user_id
        diagnostico = actual
    else:
        diagnostico = WorkOrderDiagnosis(
            company_id=company_id,
            work_order_id=work_order_id,
            diagnosis=diagnosis.strip(),
            technical_notes=technical_notes,
            diagnosed_by_user_id=user_id,
        )
        db.add(diagnostico)
    db.add(
        WorkOrderEvent(
            company_id=company_id,
            work_order_id=work_order_id,
            event_type="DIAGNOSIS",
            status=orden.status,
            detail="Diagnóstico técnico guardado.",
            user_id=user_id,
        )
    )
    db.flush()
    return diagnostico


# --------------------------------------------------------------------------------------
# Presupuesto
# --------------------------------------------------------------------------------------
#
# La regla que ordena todo este bloque: **una linea del presupuesto sale de un trabajo o un
# repuesto que esta cargado en la orden, y su precio sale de un dato real de esa linea**. Si no
# hay dato, la linea queda `pendiente` y el presupuesto no se puede generar. Nunca se completa
# un importe que no vino de la base.
#
# Por que no se rellena con un promedio, con "un precio tipico" o con lo que le suene al modelo:
# un presupuesto es lo que el cliente ve como compromiso. Un precio inventado que llega a la
# pantalla se ve igual que uno real, y la diferencia la descubre el cliente, no el sistema.
#
# `calcular_presupuesto` no escribe nada: arma el presupuesto en memoria y dice que le falta.
# `crear_presupuesto` es el unico que lo persiste.

# De donde salio el precio de una linea. Va en la respuesta para que se pueda auditar.
ORIGEN_PRECIO_CARGADO = "precio_cargado"
ORIGEN_COSTO_MAS_MARKUP = "costo_mas_markup"
ORIGEN_SIN_PRECIO = "sin_precio"


def _motivos_para_no_generar(
    db: Session, company_id: int, orden: WorkOrder, diagnostico: WorkOrderDiagnosis | None
) -> list[str]:
    """Las reglas de dominio que impiden emitir un presupuesto, en el orden que las corre la API."""
    motivos: list[str] = []
    if es_final(db, orden):
        motivos.append(
            "La orden de trabajo esta en un estado final (entregada) y no admite presupuestos."
        )
    if not parameter_bool(db, company_id, "work_orders.use_budget", True):
        motivos.append("Los presupuestos estan deshabilitados para esta empresa.")
    if parameter_bool(db, company_id, "work_orders.use_diagnosis", True) and diagnostico is None:
        motivos.append("Primero debe registrar el diagnostico tecnico de la orden.")
    return motivos


def calcular_presupuesto(db: Session, *, company_id: int, work_order_id: int) -> dict:
    """Arma el presupuesto de la orden **desde los datos reales que ya tiene cargados**.

    No escribe nada. Devuelve las lineas con el origen de cada precio, los subtotales, y sobre
    todo `puede_generar`: si hay lineas sin precio real, el presupuesto no se puede emitir y
    esto dice exactamente cual falta.

    Cada linea trae `origen_id`, que es el id del trabajo o repuesto del que salio. Es lo que
    hace auditable el importe: se puede volver a la linea de la orden y ver el dato.
    """
    orden = leer_orden(db, company_id, work_order_id)
    diagnostico = db.query(WorkOrderDiagnosis).filter_by(
        company_id=company_id, work_order_id=work_order_id
    ).first()

    # Si la empresa no muestra costos internos, la IA tampoco los ve: ni el costo, ni el
    # markup, ni el margen. Y tampoco puede derivar el precio desde el costo, porque el precio
    # asi calculado revela el costo: si el modelo ve 35000 y sabe que el markup es 0, ya sabe
    # cuanto costo. Por eso el costo no habilita el precio cuando los costos estan ocultos.
    costos_visibles = parameter_bool(db, company_id, "work_orders.show_internal_costs", True)
    markup_por_defecto = markup_partes(db, company_id)

    ejecuciones = (
        db.query(WorkOrderExecutionItem)
        .filter_by(company_id=company_id, work_order_id=work_order_id)
        .order_by(WorkOrderExecutionItem.id)
        .all()
    )

    pendientes: list[str] = []
    avisos: list[str] = []
    lineas: list[dict] = []
    subtotal_repuestos = Decimal("0")
    subtotal_manos_de_obra = Decimal("0")

    for ejecucion in ejecuciones:
        # Todo lo que no sea repuesto se trata como mano de obra. Es la misma regla que usa la
        # pantalla, y evita que un valor inesperado en la base se cuele como repuesto.
        es_repuesto = ejecucion.item_type == "PART"
        markup_aplicado = markup_por_defecto if es_repuesto else Decimal("0")

        origen_del_precio = ORIGEN_SIN_PRECIO
        precio: Decimal | None = None
        if ejecucion.unit_price > 0:
            precio = money(ejecucion.unit_price)
            origen_del_precio = ORIGEN_PRECIO_CARGADO
        elif costos_visibles and ejecucion.unit_cost > 0:
            precio = money(ejecucion.unit_cost * (Decimal("1") + markup_aplicado / Decimal("100")))
            origen_del_precio = ORIGEN_COSTO_MAS_MARKUP

        pendiente: str | None = None
        revisar: str | None = None
        if precio is None:
            if not costos_visibles:
                pendiente = (
                    "no tiene precio cargado, y esta empresa tiene los costos internos ocultos "
                    "asi que no se puede derivar el precio"
                )
            else:
                pendiente = "no tiene precio ni costo cargado"
            pendientes.append(f"{ejecucion.description}: {pendiente}.")
        elif origen_del_precio == ORIGEN_COSTO_MAS_MARKUP and not es_repuesto:
            # La mano de obra no lleva markup, asi que derivar el precio del costo devuelve el
            # costo mismo. El numero sale de un dato real, pero ofrecerlo al cliente como
            # precio deja margen cero. No se bloquea: se avisa para que la persona lo revise.
            revisar = (
                "el precio sale del costo sin margen, porque la mano de obra no lleva markup. "
                "Si se quiere cobrar otra cosa, cargalo como precio."
            )
            avisos.append(f"{ejecucion.description}: {revisar}.")

        total_linea = money(precio * ejecucion.quantity) if precio is not None else None
        if total_linea is not None:
            if es_repuesto:
                subtotal_repuestos += total_linea
            else:
                subtotal_manos_de_obra += total_linea

        linea = {
            "origen_id": ejecucion.id,
            "tipo": "PART" if es_repuesto else "LABOR",
            "descripcion": ejecucion.description,
            "cantidad": str(ejecucion.quantity),
            "precio_unitario": str(precio) if precio is not None else None,
            "total_linea": str(total_linea) if total_linea is not None else None,
            "origen_del_precio": origen_del_precio,
            "pendiente": pendiente,
            "revisar": revisar,
        }
        if costos_visibles:
            linea["costo_unitario"] = str(money(ejecucion.unit_cost))
            linea["markup"] = str(markup_aplicado)
            if precio is not None and ejecucion.unit_cost > 0:
                linea["margen"] = str(money(precio - ejecucion.unit_cost))
        lineas.append(linea)

    if not ejecuciones:
        pendientes.append(
            "La orden no tiene trabajos ni repuestos cargados, asi que no hay nada que "
            "presupuestar todavia."
        )

    motivos = _motivos_para_no_generar(db, company_id, orden, diagnostico)

    return {
        "orden": orden.id,
        "numero": orden.number,
        "puede_generar": not motivos and not pendientes and bool(lineas),
        "motivos_de_dominio": motivos,
        "costos_visibles": costos_visibles,
        "diagnostico": {
            "cargado": diagnostico is not None,
            "revision": diagnostico.revision if diagnostico else None,
            "texto": diagnostico.diagnosis if diagnostico else None,
        },
        "items": lineas,
        "subtotal_repuestos": str(money(subtotal_repuestos)),
        "subtotal_manos_de_obra": str(money(subtotal_manos_de_obra)),
        "total": str(money(subtotal_repuestos + subtotal_manos_de_obra)),
        "pendientes": pendientes,
        "avisos": avisos,
    }


def crear_presupuesto(
    db: Session,
    *,
    company_id: int,
    user_id: int,
    work_order_id: int,
    items: list[dict],
    notes: str | None = None,
) -> WorkOrderQuote:
    """Emite el presupuesto. Las reglas son las de la pantalla, no unas propias.

    ``items`` son las lineas ya resueltas: ``item_type``, ``description``, ``quantity``,
    ``unit_cost`` y ``unit_price`` (que puede venir None para que lo calcule el markup, como
    hace la pantalla cuando el precio queda en automatico).

    No hace commit: la transaccion la cierra quien la llama, que puede ser el endpoint o la
    aplicacion de una propuesta de la IA.
    """
    orden = leer_orden(db, company_id, work_order_id)
    if es_final(db, orden):
        raise ErrorDeDominio(
            "La orden de trabajo está en un estado final (entregada) y no admite presupuestos.",
            "orden_final", 409,
        )
    if not parameter_bool(db, company_id, "work_orders.use_budget", True):
        raise ErrorDeDominio(
            "Los presupuestos están deshabilitados para esta empresa.",
            "presupuestos_deshabilitados", 409,
        )
    diagnostico = db.query(WorkOrderDiagnosis).filter_by(
        company_id=company_id, work_order_id=work_order_id
    ).first()
    if parameter_bool(db, company_id, "work_orders.use_diagnosis", True) and diagnostico is None:
        raise ErrorDeDominio(
            "Primero debe registrar el diagnóstico técnico.",
            "diagnostico_requerido", 422,
        )

    version = (
        db.query(func.max(WorkOrderQuote.version))
        .filter_by(company_id=company_id, work_order_id=work_order_id)
        .scalar()
        or 0
    ) + 1

    presupuesto = WorkOrderQuote(
        company_id=company_id,
        work_order_id=work_order_id,
        version=version,
        status="ISSUED",
        notes=notes,
        diagnosis_snapshot=diagnostico.diagnosis if diagnostico else None,
        diagnosis_revision=diagnostico.revision if diagnostico else None,
        created_by_user_id=user_id,
    )
    db.add(presupuesto)
    db.flush()
    if diagnostico:
        # El diagnóstico queda cerrado por este presupuesto. Se puede reabrir, pero solo a
        # mano y desde el endpoint que lo pide explícitamente.
        diagnostico.is_open = False

    markup_por_defecto = markup_partes(db, company_id)
    repuestos = Decimal("0")
    mano_de_obra = Decimal("0")
    for item in items:
        es_repuesto = item["item_type"] == "PART"
        markup_aplicado = markup_por_defecto if es_repuesto else Decimal("0")
        costo = money(item.get("unit_cost") or 0)
        precio_pedido = item.get("unit_price")
        precio = (
            money(precio_pedido)
            if precio_pedido is not None
            else money(costo * (Decimal("1") + markup_aplicado / Decimal("100")))
        )
        cantidad = Decimal(str(item["quantity"]))
        db.add(
            WorkOrderQuoteItem(
                company_id=company_id,
                quote_id=presupuesto.id,
                item_type=item["item_type"],
                description=item["description"].strip(),
                quantity=cantidad,
                unit_cost=costo,
                markup_percent=markup_aplicado,
                unit_price=precio,
                line_total=money(cantidad * precio),
                # Trazabilidad del precio (#114). Solo si la linea viene del
                # catalogo de Flexxus: una linea de mano de obra no la tiene.
                item_code=item.get("item_code"),
                price_source=item.get("price_source"),
                price_synced_at=item.get("price_synced_at"),
            )
        )
        total = money(cantidad * precio)
        if es_repuesto:
            repuestos += total
        else:
            mano_de_obra += total

    presupuesto.subtotal_parts = money(repuestos)
    presupuesto.subtotal_labor = money(mano_de_obra)
    presupuesto.total = money(repuestos + mano_de_obra)

    db.add(
        WorkOrderEvent(
            company_id=company_id,
            work_order_id=work_order_id,
            event_type="QUOTE_CREATED",
            status=orden.status,
            detail=f"Presupuesto v{version} generado por ${presupuesto.total}.",
            user_id=user_id,
        )
    )

    # El estado "presupuestado" se asigna directo y no por `cambiar_estado`, igual que hace la
    # pantalla: emitir un presupuesto no es un cambio de estado pedido por una persona, y asi
    # este camino no dispara los avisos que tengan configurados los estados.
    objetivo = (
        db.query(WorkOrderStatus)
        .filter_by(company_id=company_id, marks_quoted=True, active=True)
        .order_by(WorkOrderStatus.sort_order)
        .first()
    )
    if objetivo and orden.status_id != objetivo.id:
        anterior = db.get(WorkOrderStatus, orden.status_id) if orden.status_id else None
        orden.status_id = objetivo.id
        orden.status = objetivo.name.upper().replace(" ", "_")[:30]
        db.add(
            WorkOrderEvent(
                company_id=company_id,
                work_order_id=work_order_id,
                event_type="STATUS_CHANGE",
                status=orden.status,
                detail=(
                    f"Estado cambiado de {anterior.name if anterior else 'sin estado'} a "
                    f"{objetivo.name} al emitir el presupuesto."
                ),
                user_id=user_id,
            )
        )
    db.flush()
    return presupuesto
