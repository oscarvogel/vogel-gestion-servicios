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

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.customer import Customer, Equipment
from app.models.work_order import WorkOrder, WorkOrderCounter, WorkOrderEvent, WorkOrderStatus
from app.models.work_order_quote import WorkOrderDiagnosis
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
) -> WorkOrder:
    """Crea la orden con su numero y su evento de recepcion.

    No hace commit: la transaccion la cierra quien la llama, que puede ser el endpoint o la
    aplicacion de una propuesta.
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
    )
    db.add(orden)
    db.flush()
    db.add(
        WorkOrderEvent(
            company_id=company_id,
            work_order_id=orden.id,
            event_type="RECEPTION",
            status="RECEIVED",
            detail="Equipo recibido y orden de trabajo generada.",
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
