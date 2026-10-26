"""Cierre mensual a marcas: que hay que liquidarle a cada empresa y cuando se cierra.

El legacy (CiberBrain) no tiene nada de esto. Alli el cierre a marcas se hacia a mano y
**no quedaba registrado**: las OTs en garantia nunca tienen ``Liquidada = 1`` porque su
politica tiene ``Liquidar = 0``, y ese flag es del ciclo de vida de la OT, no del cierre.
Como el legacy tampoco guarda el importe liquidado a la marca, no hay contra que validar el
primer cierre: hay que compararlo contra una consulta equivalente escrita a mano.

**La regla de inclusion** (la unica que importa, y la que mas caro sale equivocar):

    Entra al cierre toda OT cuya politica pertenezca a un area con empresa a liquidar
    (``work_areas.billing_customer_id`` no nulo), y se le imputa a ese cliente.

El flag de garantia (``warranty_type``) **no** decide la inclusion: solo categoriza el
trabajo dentro del reporte. En el corte 2020+ son 6.418 OTs con empresa a liquidar
(73,2 M de costo), de las cuales 2.853 son garantia estricta (25,4 M) y 3.565 son trabajo
fuera de garantia que las marcas igual pagan (47,8 M). Filtrar por "es garantia" dejaria
fuera mas de la mitad de la plata.

El importe liquidado es el **costo** (``work_orders.cost_total``), no la venta: en garantia
de terceros el legacy infla el precio de venta (``@Unitario = @Costo * (1 + @PorcUtil/100)``),
por eso la venta sale aproximadamente el doble que el costo.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.customer import Customer, Equipment
from app.models.user import User
from app.models.warranty_settlement import WarrantySettlement, WarrantySettlementOrder
from app.models.work_area import Technician, WorkArea
from app.models.work_order import WorkOrder
from app.models.work_order_part import WorkOrderPart, WorkOrderTechnician
from app.models.work_order_quote import WorkOrderExecutionItem

# Transiciones validas del cierre. El periodo se congela al emitirlo: despues de eso, los
# numeros que se'ven no se tocan, salvo que se regenere explicitamente.
_TRANSICIONES = {
    "draft": {"issued", "cancelled"},
    "issued": {"settled", "cancelled"},
    "settled": set(),
    "cancelled": {"draft"},
}


class CierreInvalido(Exception):
    """Se pidio una transicion de estado que el cierre no permite."""


def period_bounds(period: str) -> tuple[date, date]:
    """'2025-06' -> (2025-06-01, 2025-07-01). El fin es exclusivo."""
    try:
        anio, mes = period.split("-")
        anio, mes = int(anio), int(mes)
        inicio = date(anio, mes, 1)
    except (AttributeError, ValueError) as exc:
        raise ValueError(f"Periodo invalido: {period!r}. Se espera 'AAAA-MM'.") from exc
    if not 1 <= mes <= 12:
        raise ValueError(f"Periodo invalido: {period!r}. Mes fuera de rango.")
    if mes == 12:
        fin = date(anio + 1, 1, 1)
    else:
        fin = date(anio, mes + 1, 1)
    return inicio, fin


def costo_desde_lineas(db: Session, ids: list[int]) -> dict[int, Decimal]:
    """Costo por OT calculado desde sus lineas.

    Se usa solo para las OTs que no traen ``cost_total`` (las nacidas en el sistema nuevo).
    Las importadas del legacy traen el valor del legacy, que es el que manda.

    Se suman **las dos** fuentes de lineas:

    - ``work_order_parts``: las del legacy (las importa CyberBrain).
    - ``work_order_execution_items``: las que se cargan en la app (trabajo y repuestos).

    Antes solo se leian las primeras, y como las OTs hechas en la app no tienen partes,
    **todas las ordenes del sistema nuevo entraban al cierre con cero**. No hacen falta
    las dos a la vez: una OT importada trae ``cost_total`` y no llega aca.
    """
    if not ids:
        return {}
    partes = (
        db.query(
            WorkOrderPart.work_order_id,
            func.coalesce(func.sum(WorkOrderPart.unit_cost * WorkOrderPart.quantity), 0),
        )
        .filter(WorkOrderPart.work_order_id.in_(ids))
        .group_by(WorkOrderPart.work_order_id)
        .all()
    )
    ejecucion = (
        db.query(
            WorkOrderExecutionItem.work_order_id,
            func.coalesce(
                func.sum(WorkOrderExecutionItem.unit_cost * WorkOrderExecutionItem.quantity), 0
            ),
        )
        .filter(WorkOrderExecutionItem.work_order_id.in_(ids))
        .group_by(WorkOrderExecutionItem.work_order_id)
        .all()
    )
    importes: dict[int, Decimal] = {fila[0]: Decimal(str(fila[1] or 0)) for fila in partes}
    for ot_id, total in ejecucion:
        importes[ot_id] = importes.get(ot_id, Decimal(0)) + Decimal(str(total or 0))
    return importes


def costo_lineas_de_ot(db: Session, work_order_id: int) -> Decimal:
    """Costo de una OT segun sus lineas (0 si no tiene ninguna con costo)."""
    return costo_desde_lineas(db, [work_order_id]).get(work_order_id, Decimal(0))


def _ot_por_id(db: Session, ids: list[int]) -> dict[int, tuple[str, str, str | None]]:
    """(nombre del equipo, numero de serie, modelo) por OT."""
    if not ids:
        return {}
    filas = (
        db.query(WorkOrder.id, Equipment.brand, Equipment.model, Equipment.serial_number)
        .join(Equipment, WorkOrder.equipment_id == Equipment.id)
        .filter(WorkOrder.id.in_(ids))
        .all()
    )
    return {f[0]: (f[1] or "", f[2] or "", f[3]) for f in filas}


def _tecnicos_por_ot(db: Session, ids: list[int]) -> dict[int, list[str]]:
    if not ids:
        return {}
    filas = (
        db.query(WorkOrderTechnician.work_order_id, Technician.name)
        .join(Technician, WorkOrderTechnician.technician_id == Technician.id)
        .filter(WorkOrderTechnician.work_order_id.in_(ids))
        .order_by(Technician.name)
        .all()
    )
    salida: dict[int, list[str]] = {}
    for ot_id, nombre in filas:
        salida.setdefault(ot_id, []).append(nombre)
    return salida


def calcular_cierre(db: Session, company_id: int, period: str) -> dict:
    """Reporte en vivo del cierre: que se le liquida a cada empresa en el periodo.

    No toca la base: es la vista previa antes de generar el cierre.
    """
    desde, hasta = period_bounds(period)

    filas = (
        db.query(
            WorkOrder.id,
            WorkOrder.number,
            WorkOrder.legacy_number,
            WorkOrder.customer_id,
            WorkOrder.completed_at,
            WorkOrder.cost_total,
            WorkArea.id,
            WorkArea.area_name,
            WorkArea.policy_code,
            WorkArea.warranty_type,
            WorkArea.billing_customer_id,
        )
        .join(WorkArea, WorkOrder.work_area_id == WorkArea.id)
        .filter(
            WorkOrder.company_id == company_id,
            WorkArea.billing_customer_id.isnot(None),
            WorkOrder.completed_at.isnot(None),
            WorkOrder.completed_at >= desde,
            WorkOrder.completed_at < hasta,
        )
        .all()
    )

    ids = [f[0] for f in filas]
    costos_lineas = costo_desde_lineas(db, ids)
    equipos = _ot_por_id(db, ids)
    tecnicos = _tecnicos_por_ot(db, ids)
    clientes = {
        cid: nombre
        for cid, nombre in db.query(Customer.id, Customer.name)
        .filter(Customer.id.in_([f[3] for f in filas if f[3]]))
        .all()
    } if filas else {}

    por_empresa: dict[int, dict] = {}
    for f in filas:
        (ot_id, numero, legacy_number, cliente_id, completed_at, cost_total,
         area_id, area_name, policy_code, warranty_type, billing_customer_id) = f

        importe = Decimal(str(cost_total or 0))
        if importe <= 0:
            importe = costos_lineas.get(ot_id, Decimal(0))

        empresa = por_empresa.setdefault(
            billing_customer_id,
            {
                "billing_customer_id": billing_customer_id,
                "billing_customer_name": None,
                "works_count": 0,
                "total_amount": Decimal(0),
                "warranty_works_count": 0,
                "warranty_amount": Decimal(0),
                "out_of_warranty_works_count": 0,
                "out_of_warranty_amount": Decimal(0),
                "own_warranty_works_count": 0,
                "own_warranty_amount": Decimal(0),
                "works": [],
            },
        )
        empresa["works_count"] += 1
        empresa["total_amount"] += importe
        # warranty_type: 0 = fuera de garantia, 1 = garantia de terceros,
        # 2 = garantia propia / de service. Los tres van en su propio casillero: la
        # garantia propia (Alladio) es garantia, pero no de terceros, y meterla en
        # "fuera de garantia" seria mostrar como trabajo no cubierto lo que si cubre.
        if warranty_type == 1:
            empresa["warranty_works_count"] += 1
            empresa["warranty_amount"] += importe
        elif warranty_type == 2:
            empresa["own_warranty_works_count"] += 1
            empresa["own_warranty_amount"] += importe
        else:
            empresa["out_of_warranty_works_count"] += 1
            empresa["out_of_warranty_amount"] += importe

        marca, modelo, serie = equipos.get(ot_id, ("", "", None))
        empresa["works"].append(
            {
                "work_order_id": ot_id,
                "number": numero,
                "legacy_number": legacy_number,
                "completed_at": completed_at,
                "client_name": clientes.get(cliente_id),
                "equipment": marca,
                "model": modelo,
                "serial_number": serie,
                "technicians": tecnicos.get(ot_id, []),
                "work_area_id": area_id,
                "work_area": area_name,
                "policy_code": policy_code or None,
                "warranty_type": warranty_type,
                "amount": importe,
            }
        )

    # El nombre de la empresa a liquidar se resuelve aparte: el informe lo necesita
    # si o si, y el nombre puede repetirse entre areas de la misma empresa.
    if por_empresa:
        nombres = {
            cid: nombre
            for cid, nombre in db.query(Customer.id, Customer.name)
            .filter(Customer.id.in_(list(por_empresa)))
            .all()
        }
        for cid, empresa in por_empresa.items():
            empresa["billing_customer_name"] = nombres.get(cid)

    companies = sorted(por_empresa.values(), key=lambda e: -float(e["total_amount"]))
    for empresa in companies:
        empresa["works"].sort(key=lambda w: (w["completed_at"] or datetime.min, w["work_order_id"]))

    totales = {
        "works_count": sum(e["works_count"] for e in companies),
        "total_amount": sum((e["total_amount"] for e in companies), Decimal(0)),
        "warranty_works_count": sum(e["warranty_works_count"] for e in companies),
        "warranty_amount": sum((e["warranty_amount"] for e in companies), Decimal(0)),
        "out_of_warranty_works_count": sum(e["out_of_warranty_works_count"] for e in companies),
        "out_of_warranty_amount": sum((e["out_of_warranty_amount"] for e in companies), Decimal(0)),
        "own_warranty_works_count": sum(e["own_warranty_works_count"] for e in companies),
        "own_warranty_amount": sum((e["own_warranty_amount"] for e in companies), Decimal(0)),
    }
    return {"period": period, "companies": companies, "totals": totales}


def _cerrar_una_empresa(
    db: Session, company_id: int, period: str, desde: date, hasta: date, empresa: dict
) -> WarrantySettlement:
    """Crea o actualiza el cierre (draft) de una empresa y su detalle."""
    existente = (
        db.query(WarrantySettlement)
        .filter_by(
            company_id=company_id,
            period=desde,
            billing_customer_id=empresa["billing_customer_id"],
        )
        .first()
    )
    if existente and existente.status != "draft":
        raise CierreInvalido(
            f"El cierre de {empresa['billing_customer_name']} para {period} esta "
            f"'{existente.status}' y no se puede regenerar. Reabrilo antes de volver a generarlo."
        )

    cierre = existente or WarrantySettlement(
        company_id=company_id, period=desde, billing_customer_id=empresa["billing_customer_id"]
    )
    cierre.status = "draft"
    cierre.works_count = empresa["works_count"]
    cierre.total_amount = empresa["total_amount"]
    cierre.warranty_works_count = empresa["warranty_works_count"]
    cierre.warranty_amount = empresa["warranty_amount"]
    cierre.out_of_warranty_works_count = empresa["out_of_warranty_works_count"]
    cierre.out_of_warranty_amount = empresa["out_of_warranty_amount"]
    cierre.own_warranty_works_count = empresa["own_warranty_works_count"]
    cierre.own_warranty_amount = empresa["own_warranty_amount"]
    cierre.generated_at = datetime.now()
    if cierre not in db:
        db.add(cierre)
    db.flush()

    # El detalle se rehace entero: si el periodo se regenera, no puede quedar una OT
    # vieja en el cierre.
    db.query(WarrantySettlementOrder).filter(
        WarrantySettlementOrder.warranty_settlement_id == cierre.id
    ).delete(synchronize_session=False)

    for obra in empresa["works"]:
        db.add(
            WarrantySettlementOrder(
                company_id=company_id,
                warranty_settlement_id=cierre.id,
                work_order_id=obra["work_order_id"],
                work_area_id=obra["work_area_id"],
                warranty_type=obra["warranty_type"],
                amount=obra["amount"],
                completed_at=obra["completed_at"],
            )
        )
    return cierre


def generar_cierre(
    db: Session,
    company_id: int,
    period: str,
    user: User | None = None,
    billing_customer_id: int | None = None,
) -> dict:
    """Genera (o regenera) los cierres en borrador del periodo.

    El reporte es el mismo que devuelve ``calcular_cierre``; lo que cambia es que ademas
    queda **registrado** en ``warranty_settlements``, para que el mes cerrado no se pueda
    modificar por accidente y quede auditado.

    Con ``billing_customer_id`` solo se genera esa empresa: sirve cuando otra del mismo
    periodo ya esta emitida y regenerar todo el periodo fallaria.
    """
    desde, hasta = period_bounds(period)
    reporte = calcular_cierre(db, company_id, period)

    empresas = reporte["companies"]
    if billing_customer_id is not None:
        empresas = [e for e in empresas if e["billing_customer_id"] == billing_customer_id]
        if not empresas:
            raise CierreInvalido(f"La empresa no tiene trabajos para liquidar en {period}.")

    for empresa in empresas:
        _cerrar_una_empresa(db, company_id, period, desde, hasta, empresa)

    db.commit()
    return reporte


def _cierre_de_empresa(db: Session, company_id: int, settlement_id: int) -> WarrantySettlement:
    cierre = (
        db.query(WarrantySettlement)
        .filter_by(id=settlement_id, company_id=company_id)
        .first()
    )
    if not cierre:
        raise LookupError("Cierre no encontrado.")
    return cierre


def cambiar_estado(
    db: Session, company_id: int, settlement_id: int, destino: str, invoice_number: str | None = None
) -> WarrantySettlement:
    """Mueve el cierre a otro estado, si la transicion es valida.

    ``draft -> issued`` congela el periodo (los numeros ya no se tocan). ``issued -> settled``
    lo marca como liquidado, que es cuando se le pone el numero de factura.
    """
    cierre = _cierre_de_empresa(db, company_id, settlement_id)
    if destino not in _TRANSICIONES.get(cierre.status, set()):
        raise CierreInvalido(
            f"No se puede pasar un cierre de '{cierre.status}' a '{destino}'."
        )
    cierre.status = destino
    if destino == "issued":
        cierre.issued_at = datetime.now()
    elif destino == "settled":
        cierre.settled_at = datetime.now()
        if invoice_number:
            cierre.invoice_number = invoice_number
    elif destino == "draft":
        cierre.issued_at = None
        cierre.settled_at = None
    db.commit()
    db.refresh(cierre)
    return cierre


def detalle_cierre(db: Session, company_id: int, settlement_id: int) -> dict:
    """El cierre con su detalle OT por OT."""
    cierre = _cierre_de_empresa(db, company_id, settlement_id)
    obras = (
        db.query(
            WarrantySettlementOrder,
            WorkOrder.number,
            WorkOrder.legacy_number,
            WorkOrder.completed_at,
            WorkOrder.customer_id,
        )
        .join(WorkOrder, WarrantySettlementOrder.work_order_id == WorkOrder.id)
        .filter(WarrantySettlementOrder.warranty_settlement_id == cierre.id)
        .order_by(WarrantySettlementOrder.completed_at, WorkOrder.id)
        .all()
    )
    clientes = {}
    ids_cliente = [o[4] for o in obras if o[4]]
    if ids_cliente:
        clientes = {
            cid: nombre
            for cid, nombre in db.query(Customer.id, Customer.name)
            .filter(Customer.id.in_(ids_cliente))
            .all()
        }
    areas = {
        aid: (nombre, policy_code)
        for aid, nombre, policy_code in db.query(WorkArea.id, WorkArea.area_name, WorkArea.policy_code).all()
    }
    empresa = db.query(Customer).filter_by(id=cierre.billing_customer_id).first()

    return {
        "id": cierre.id,
        "period": cierre.period.strftime("%Y-%m"),
        "status": cierre.status,
        "billing_customer_id": cierre.billing_customer_id,
        "billing_customer_name": empresa.name if empresa else None,
        "works_count": cierre.works_count,
        "total_amount": cierre.total_amount,
        "warranty_works_count": cierre.warranty_works_count,
        "warranty_amount": cierre.warranty_amount,
        "out_of_warranty_works_count": cierre.out_of_warranty_works_count,
        "out_of_warranty_amount": cierre.out_of_warranty_amount,
        "own_warranty_works_count": cierre.own_warranty_works_count,
        "own_warranty_amount": cierre.own_warranty_amount,
        "invoice_number": cierre.invoice_number,
        "notes": cierre.notes,
        "generated_at": cierre.generated_at,
        "issued_at": cierre.issued_at,
        "settled_at": cierre.settled_at,
        "works": [
            {
                "work_order_id": orden.work_order_id,
                "number": numero,
                "legacy_number": legacy_number,
                "completed_at": completed_at,
                "client_name": clientes.get(cliente_id),
                "work_area": areas.get(orden.work_area_id, (None, None))[0],
                "policy_code": areas.get(orden.work_area_id, (None, None))[1] or None,
                "warranty_type": orden.warranty_type,
                "amount": orden.amount,
            }
            for orden, numero, legacy_number, completed_at, cliente_id in obras
        ],
    }
