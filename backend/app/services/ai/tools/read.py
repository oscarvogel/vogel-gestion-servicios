"""Herramientas de solo lectura sobre el dominio (#44 sub-issue 2).

Las tres son de lectura y las tres filtran por `ctx.company_id`, que viene de la sesion. No
hay ningun camino por el que el modelo pueda pedir datos de otra empresa: no acepta un
`company_id` como argumento, y el id de la sesion se usa tal cual en el filtro.

Criterio del sub-issue: una herramienta de otra empresa devuelve **vacio**, no datos ajenos ni
un error. Un `not found` de un id que existe pero es de otra empresa y un id que no existe
son indistinguibles para quien pregunta, y asi se evita además que el modelo pueda usar el
error para enumerar ids de otras empresas.
"""
from __future__ import annotations

from sqlalchemy import or_, select

from app.models.customer import Customer, Equipment, EquipmentCategory
from app.models.work_order import WorkOrder, WorkOrderStatus
from app.services.ai.tools.base import (
    ARGUMENTOS_INVALIDOS,
    ToolContext,
    ToolError,
    ToolOutcome,
    ToolSpec,
)
from app.services.ai.tools.validacion import (
    escape_like as _escape_like,
    entero as _id,
    limite as _limite,
    texto as _texto,
)

# --------------------------------------------------------------------------------------
# buscar_cliente
# --------------------------------------------------------------------------------------


def _buscar_cliente(ctx: ToolContext, args: dict) -> ToolOutcome:
    consulta = _texto(args.get("texto"), "texto")
    limite = _limite(args.get("limite"), 5)
    # El escape es para que un '%' tipeado por el operador no traiga toda la base.
    patron = f"%{_escape_like(consulta)}%"

    filas = ctx.db.execute(
        select(Customer, _cantidad_equipos())
        .where(
            Customer.company_id == ctx.company_id,
            Customer.active.is_(True),
            or_(
                Customer.name.like(patron, escape="\\"),
                Customer.document.like(patron, escape="\\"),
                Customer.phone.like(patron, escape="\\"),
                Customer.whatsapp.like(patron, escape="\\"),
                Customer.email.like(patron, escape="\\"),
            ),
        )
        .order_by(Customer.name)
        .limit(limite)
    ).all()

    resultados = [
        {
            "id": c.id,
            "nombre": c.name,
            "tipo": c.customer_type,
            "documento": c.document,
            "telefono": c.phone,
            "whatsapp": c.whatsapp,
            "email": c.email,
            "cantidad_de_equipos": int(cantidad or 0),
        }
        for c, cantidad in filas
    ]
    return ToolOutcome(ok=True, data={"consulta": consulta, "resultados": resultados})


def _cantidad_equipos():
    from sqlalchemy import func

    return (
        select(func.count(Equipment.id))
        .where(Equipment.customer_id == Customer.id, Equipment.company_id == Customer.company_id)
        .correlate(Customer)
        .scalar_subquery()
    )


# --------------------------------------------------------------------------------------
# buscar_equipo
# --------------------------------------------------------------------------------------


def _buscar_equipo(ctx: ToolContext, args: dict) -> ToolOutcome:
    consulta = _texto(args.get("texto"), "texto")
    limite = _limite(args.get("limite"), 5)
    patron = f"%{_escape_like(consulta)}%"

    filas = ctx.db.execute(
        select(Equipment, Customer, EquipmentCategory)
        .join(Customer, Customer.id == Equipment.customer_id)
        .join(EquipmentCategory, EquipmentCategory.id == Equipment.category_id)
        .where(
            Equipment.company_id == ctx.company_id,
            Equipment.active.is_(True),
            # El filtro de empresa va en las dos tablas: que el `join` no pueda traer un
            # cliente de otra empresa colgado de un equipo de esta.
            Customer.company_id == ctx.company_id,
            or_(
                Equipment.serial_number.like(patron, escape="\\"),
                Equipment.description.like(patron, escape="\\"),
                Equipment.brand.like(patron, escape="\\"),
                Equipment.model.like(patron, escape="\\"),
                Customer.name.like(patron, escape="\\"),
            ),
        )
        .order_by(Customer.name, Equipment.id)
        .limit(limite)
    ).all()

    resultados = [
        {
            "id": e.id,
            "cliente": c.name,
            "cliente_id": c.id,
            "categoria": cat.name,
            "marca": e.brand,
            "modelo": e.model,
            "numero_de_serie": e.serial_number,
            "descripcion": e.description,
        }
        for e, c, cat in filas
    ]
    return ToolOutcome(ok=True, data={"consulta": consulta, "resultados": resultados})


# --------------------------------------------------------------------------------------
# consultar_historial_equipo
# --------------------------------------------------------------------------------------


def _consultar_historial_equipo(ctx: ToolContext, args: dict) -> ToolOutcome:
    equipo_id = _id(args.get("equipo_id"), "equipo_id")
    limite = _limite(args.get("limite"), 10)
    consulta = f"equipo_id={equipo_id}"

    # El equipo se busca por id **y** por empresa. Si no esta, es que no existe o es de otra:
    # las dos cosas devuelven el mismo vacio.
    equipo = ctx.db.execute(
        select(Equipment, Customer, EquipmentCategory)
        .join(Customer, Customer.id == Equipment.customer_id)
        .join(EquipmentCategory, EquipmentCategory.id == Equipment.category_id)
        .where(Equipment.id == equipo_id, Equipment.company_id == ctx.company_id)
    ).first()

    if equipo is None:
        return ToolOutcome(
            ok=True,
            data={
                "consulta": consulta,
                "encontrado": False,
                "historial": [],
                "nota": "No hay ningun equipo con ese identificador en esta empresa.",
            },
        )

    e, c, cat = equipo
    ordenes = ctx.db.execute(
        select(WorkOrder, WorkOrderStatus)
        .outerjoin(WorkOrderStatus, WorkOrderStatus.id == WorkOrder.status_id)
        .where(WorkOrder.company_id == ctx.company_id, WorkOrder.equipment_id == e.id)
        .order_by(WorkOrder.received_at.desc())
        .limit(limite)
    ).all()

    historial = [
        {
            "orden": o.number,
            "estado": (st.name if st else o.status),
            "recibida": o.received_at.isoformat() if o.received_at else None,
            "entrega_estimada": o.expected_delivery_at.isoformat() if o.expected_delivery_at else None,
            "completada": o.completed_at.isoformat() if o.completed_at else None,
            "entregada": o.delivered_at.isoformat() if o.delivered_at else None,
            "falla_reportada": o.reported_fault,
        }
        for o, st in ordenes
    ]
    return ToolOutcome(
        ok=True,
        data={
            "consulta": consulta,
            "encontrado": True,
            "equipo": {
                "id": e.id,
                "cliente": c.name,
                "categoria": cat.name,
                "marca": e.brand,
                "modelo": e.model,
                "numero_de_serie": e.serial_number,
                "descripcion": e.description,
            },
            "cantidad_de_ordenes": len(historial),
            "historial": historial,
        },
    )


# --------------------------------------------------------------------------------------
# Catalogo
# --------------------------------------------------------------------------------------

TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="buscar_cliente",
        description=(
            "Busca clientes de la empresa por nombre, documento, telefono, whatsapp o email. "
            "Usala cuando el operador mencione a una persona o empresa."
        ),
        parameters={
            "type": "object",
            "properties": {
                "texto": {
                    "type": "string",
                    "description": "Nombre, documento, telefono o email a buscar.",
                },
                "limite": {
                    "type": "integer",
                    "description": "Maximo de resultados, de 1 a 20. Por defecto 5.",
                },
            },
            "required": ["texto"],
        },
        permission="customers.view",
        run=_buscar_cliente,
    ),
    ToolSpec(
        name="buscar_equipo",
        description=(
            "Busca equipos de la empresa por numero de serie, descripcion, marca, modelo o "
            "nombre del cliente."
        ),
        parameters={
            "type": "object",
            "properties": {
                "texto": {"type": "string", "description": "Texto a buscar."},
                "limite": {
                    "type": "integer",
                    "description": "Maximo de resultados, de 1 a 20. Por defecto 5.",
                },
            },
            "required": ["texto"],
        },
        permission="equipment.view",
        run=_buscar_equipo,
    ),
    ToolSpec(
        name="consultar_historial_equipo",
        description=(
            "Devuelve las ordenes de trabajo de un equipo: estados, fechas y la falla reportada "
            "en cada una. Usala despues de buscar_equipo para contarle al operador el "
            "historial del equipo."
        ),
        parameters={
            "type": "object",
            "properties": {
                "equipo_id": {"type": "integer", "description": "Id del equipo."},
                "limite": {
                    "type": "integer",
                    "description": "Maximo de ordenes, de 1 a 20. Por defecto 10.",
                },
            },
            "required": ["equipo_id"],
        },
        permission="work_orders.view",
        run=_consultar_historial_equipo,
    ),
)
