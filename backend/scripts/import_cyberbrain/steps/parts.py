"""Paso 5: lineas de la OT.

Las lineas del legacy (``dbo.CS_Partes``) tienen 13.327 filas historicas; en el corte
2020+ son 29.799, sobre 9.187 OTs (129 OTs no tienen ninguna linea).

Mapeo:

- ``line_no`` es el ``Item`` de la linea (dentro de la OT),
- ``unit_price`` es el precio de venta al cliente final y ``unit_cost`` el costo real.
  En garantia de terceros el legacy infla el precio
  (``@Unitario = @Costo * (1 + @PorcUtil/100)``), por eso ``VentaTotal`` sale
  aproximadamente el doble que ``CostoTotal``,
- ``commission_recipient_type`` traduce ``LiquidaComision``: 0 = sin comision,
  -1 = se divide entre todos, -2 = el responsable, -3 = el proveedor, > 0 = el codigo
  de un tecnico del legacy,
- ``supplier_technician_id`` es el tecnico que proveyo la parte (``Provee``).

La cotizacion del legacy es 1 en todas las lineas del corte (o sea, los importes ya
estan en la moneda de la empresa) y el destino no tiene tabla de monedas: por eso
``currency_code`` queda vacio.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select

from .. import mappers, source
from ..context import Contexto


def ejecutar(ctx: Contexto) -> None:
    """Importa las lineas de las OTs del corte."""
    tabla = ctx.tabla("work_order_parts")

    # Comisiones por linea: el legacy ya las calculo (CS_ComisionPartexInterviene).
    # Se suman para dejar el total de la linea en ``commission_amount``.
    comision_por_linea = ctx.fuente.comisiones_por_linea()

    # Lineas ya importadas (por OT y numero de linea), para no duplicar.
    existentes = {
        (fila[0], fila[1])
        for fila in ctx.session.execute(
            select(tabla.c.work_order_id, tabla.c.line_no).where(
                tabla.c.company_id == ctx.company_id
            )
        ).all()
    }
    # Ids de las lineas que ya estan en la base (para las comisiones por linea).
    for legacy_id, parte_id in ctx.session.execute(
        select(tabla.c.legacy_id, tabla.c.id).where(
            tabla.c.company_id == ctx.company_id, tabla.c.legacy_id.is_not(None)
        )
    ).all():
        ctx.partes_por_legacy_id[str(legacy_id)] = parte_id

    a_crear = []
    omitidas = 0
    sin_ot = 0
    costo_lineas = 0
    for (
        nro_orden,
        item,
        numero_parte,
        cantidad,
        descripcion,
        costo_unitario,
        unitario,
        tipo,
        liquida_comision,
        cotizacion,
        cotizacion_costo,
        provee,
        id_parte,
    ) in ctx.fuente.lineas():
        work_order_id = ctx.ot_por_legacy_id.get(source.texto(nro_orden))
        if work_order_id is None:
            sin_ot += 1
            continue
        line_no = source.entero(item, 0) or 0
        if (work_order_id, line_no) in existentes:
            omitidas += 1
            continue

        tipo_comision = mappers.tipo_comision(source.entero(liquida_comision, 0))
        recipient = None
        if tipo_comision > 0:
            recipient = ctx.tecnicos_por_codigo.get(str(tipo_comision))
        proveedor = ctx.tecnicos_por_codigo.get(source.texto(provee))
        cantidad_valor = source.decimal(cantidad)
        costo = source.decimal(costo_unitario)
        a_crear.append(
            {
                "company_id": ctx.company_id,
                "work_order_id": work_order_id,
                "line_no": line_no,
                "part_type": mappers.TIPO_PARTE.get(source.entero(tipo, 0) or 0, 0),
                "description": source.texto(descripcion) or None,
                "item_code": source.recortar("work_order_parts.item_code", source.texto(numero_parte), 60),
                "quantity": cantidad_valor,
                "unit_price": source.decimal(unitario),
                "unit_cost": costo,
                "currency_code": None,
                "cost_currency_code": None,
                "commission_recipient_type": tipo_comision,
                "commission_recipient_id": recipient,
                "supplier_technician_id": proveedor,
                "commission_amount": comision_por_linea.get(source.texto(id_parte), 0),
                "is_cost_excluded": False,
                "legacy_id": source.entero(id_parte, None),
            }
        )
        costo_lineas += cantidad_valor * costo

    ctx.insertar(tabla, a_crear)
    for fila in a_crear:
        if fila["legacy_id"] is not None:
            ctx.partes_por_legacy_id[str(fila["legacy_id"])] = int(fila["id"])

    ctx.reporte.linea(
        "work_order_parts",
        "CS_Partes",
        leidos=len(a_crear) + omitidas + sin_ot,
        insertados=len(a_crear),
        omitidos=omitidas,
        descartados=sin_ot,
        motivo=(
            "line_no = Item del legacy; comision_recipient_type = LiquidaComision; "
            f"{sin_ot} lineas sin OT en el corte"
        ),
        importes={"costo de lineas": costo_lineas},
    )
