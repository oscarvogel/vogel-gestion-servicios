"""Paso 6: intervenciones y comisiones por linea.

Dos tablas del destino:

- ``work_order_technicians`` (legacy ``dbo.Intervienen``): quien intervino en la OT y
  cuanto se le comisiona. **Los importes se migran tal como los calculo el legacy**:
  no se recalcula ninguna comision, porque el destino todavia no tiene los esquemas
  ni las politicas para hacerlo.
- ``work_order_part_commissions`` (legacy ``dbo.CS_ComisionPartexInterviene``): la
  comision de una linea para un tecnico concreto. Se une por el ``ID`` de la linea del
  legacy, que es ``work_order_parts.legacy_id``.
"""

from __future__ import annotations

from sqlalchemy import select

from .. import source
from ..context import Contexto


def ejecutar(ctx: Contexto) -> None:
    """Importa las intervenciones y las comisiones por linea."""
    _intervenciones(ctx)
    _comisiones_por_linea(ctx)


def _intervenciones(ctx: Contexto) -> None:
    """``work_order_technicians``: quien intervino y cuanto se le comisiona."""
    tabla = ctx.tabla("work_order_technicians")
    existentes = {
        (fila[0], fila[1])
        for fila in ctx.session.execute(
            select(tabla.c.work_order_id, tabla.c.technician_id).where(
                tabla.c.company_id == ctx.company_id
            )
        ).all()
    }

    a_crear = []
    omitidas = 0
    sin_ot = 0
    sin_tecnico = 0
    total_comisiones = 0
    for (
        orden,
        persona,
        comision_productos,
        comision_partes,
        comision_servicios,
        comision_otros,
        liquidacion,
        fecha_liquidacion,
        nro_factura,
    ) in ctx.fuente.intervenciones():
        work_order_id = ctx.ot_por_legacy_id.get(source.texto(orden))
        if work_order_id is None:
            sin_ot += 1
            continue
        technician_id = ctx.tecnicos_por_codigo.get(source.texto(persona))
        if technician_id is None:
            sin_tecnico += 1
            continue
        if (work_order_id, technician_id) in existentes:
            omitidas += 1
            continue
        productos = source.decimal(comision_productos)
        partes = source.decimal(comision_partes)
        servicios = source.decimal(comision_servicios)
        otros = source.decimal(comision_otros)
        total_comisiones += productos + partes + servicios + otros
        a_crear.append(
            {
                "company_id": ctx.company_id,
                "work_order_id": work_order_id,
                "technician_id": technician_id,
                "commission_products": productos,
                "commission_parts": partes,
                "commission_services": servicios,
                "commission_other": otros,
                "settled_at": source.fecha_o_umbral(fecha_liquidacion),
                "settlement_invoice": source.recortar(
                    "work_order_technicians.settlement_invoice", source.texto(nro_factura), 30
                ),
            }
        )

    ctx.insertar(tabla, a_crear)
    ctx.reporte.linea(
        "work_order_technicians",
        "Intervienen",
        leidos=len(a_crear) + omitidas + sin_ot + sin_tecnico,
        insertados=len(a_crear),
        omitidos=omitidas,
        descartados=sin_ot + sin_tecnico,
        motivo="importes de comision migrados tal cual (no se recalculan)",
        importes={"comisiones": total_comisiones},
    )


def _comisiones_por_linea(ctx: Contexto) -> None:
    """``work_order_part_commissions``: comision de una linea para un tecnico."""
    tabla = ctx.tabla("work_order_part_commissions")
    existentes = {
        (fila[0], fila[1])
        for fila in ctx.session.execute(
            select(tabla.c.work_order_part_id, tabla.c.technician_id).where(
                tabla.c.company_id == ctx.company_id
            )
        ).all()
    }

    a_crear = []
    omitidas = 0
    sin_linea = 0
    sin_tecnico = 0
    total = 0
    for id_parte, persona, comision in ctx.fuente.comisiones_linea():
        parte_id = ctx.partes_por_legacy_id.get(source.texto(id_parte))
        if parte_id is None:
            sin_linea += 1
            continue
        technician_id = ctx.tecnicos_por_codigo.get(source.texto(persona))
        if technician_id is None:
            sin_tecnico += 1
            continue
        if (parte_id, technician_id) in existentes:
            omitidas += 1
            continue
        monto = source.decimal(comision)
        total += monto
        a_crear.append(
            {
                "company_id": ctx.company_id,
                "work_order_part_id": parte_id,
                "technician_id": technician_id,
                "amount": monto,
            }
        )

    ctx.insertar(tabla, a_crear)
    ctx.reporte.linea(
        "work_order_part_commissions",
        "CS_ComisionPartexInterviene",
        leidos=len(a_crear) + omitidas + sin_linea + sin_tecnico,
        insertados=len(a_crear),
        omitidos=omitidas,
        descartados=sin_linea + sin_tecnico,
        motivo="se une por work_order_parts.legacy_id (ID de CS_Partes)",
        importes={"comisiones por linea": total},
    )
