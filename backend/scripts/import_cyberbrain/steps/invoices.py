"""Paso 7: facturas.

La tabla de facturas del legacy tiene 83.164 filas y termina el 2021-06-30: despues
el numero de factura paso a ``CS_Trabajos.Comprobante`` (que es polimorfico: numeros
de factura y textos como ``STOCK`` o ``NO CORRESPONDE``).

De este corte entra **solo lo que una OT reclama**: las filas con ``id_trabajo`` no
vacio, que son las que el export encontro por ``CS_Trabajos.FacturaEmitida``. El resto
son facturacion de mostrador, que no entra en el corte.

Detalles:

- ``issued_at`` es ``CG_Facturas_Tabla.Fecha`` y **no** ``FechaComprobante``: la fecha
  del comprobante coincide con la de la tabla en 1 de 3.494 casos,
- ``invoice_type``: ``TipoDoc`` 1 = "factura", 31 = "factura_mipyme",
- ``status``: "cancelled" si la factura esta anulada, si no "issued".
"""

from __future__ import annotations

from sqlalchemy import select

from .. import mappers, source
from ..context import Contexto


def ejecutar(ctx: Contexto) -> None:
    """Importa las facturas del corte que una OT reclama."""
    tabla = ctx.tabla("invoices")

    existentes = {
        (fila[0], fila[1])
        for fila in ctx.session.execute(
            select(tabla.c.invoice_type, tabla.c.number).where(
                tabla.c.company_id == ctx.company_id
            )
        ).all()
    }
    legacy_ya_importados = {
        str(fila[0])
        for fila in ctx.session.execute(
            select(tabla.c.legacy_id).where(
                tabla.c.company_id == ctx.company_id, tabla.c.legacy_id.is_not(None)
            )
        ).all()
    }

    a_crear = []
    omitidas = 0
    sin_ot = 0
    sin_cliente = 0
    anuladas = 0
    total = 0
    for (
        id_factura,
        numero,
        tipo_doc,
        codcli,
        cliente,
        fecha,
        vencimiento,
        bruto,
        neto,
        total_factura,
        cuit,
        vendedor,
        realizado_por,
        anulado,
        cai,
        id_trabajo,
    ) in ctx.fuente.facturas():
        if not source.texto(id_trabajo):
            continue
        if source.texto(id_factura) in legacy_ya_importados:
            omitidas += 1
            continue
        emitida = source.fecha(fecha)
        if emitida is None:
            # ``issued_at`` es NOT NULL: una factura sin fecha no se puede importar.
            continue
        invoice_type = mappers.tipo_invoice(source.entero(tipo_doc, 1))
        if (invoice_type, source.texto(numero)) in existentes:
            omitidas += 1
            continue

        work_order_id = ctx.ot_por_legacy_id.get(source.texto(id_trabajo))
        if work_order_id is None:
            sin_ot += 1
        customer_id = ctx.clientes_por_codcli.get(source.texto(codcli))
        if customer_id is None:
            customer_id = ctx.cliente_sin_identificar
            sin_cliente += 1
        importe = source.decimal(total_factura)
        total += importe
        anulada = (source.entero(anulado, 0) or 0) == 1
        if anulada:
            anuladas += 1
        a_crear.append(
            {
                "company_id": ctx.company_id,
                "customer_id": customer_id,
                "number": source.recortar("invoices.number", source.texto(numero), 30),
                "invoice_type": invoice_type,
                "status": "cancelled" if anulada else "issued",
                "issued_at": emitida,
                "gross_amount": source.decimal(bruto),
                "net_amount": source.decimal(neto),
                "total_amount": importe,
                "tax_id": source.recortar("invoices.tax_id", _cuit_factura(cuit), 15),
                "seller_id": ctx.vendedores_por_codigo.get(source.texto(vendedor)),
                "work_order_id": work_order_id,
                "legacy_id": source.entero(id_factura, None),
            }
        )

    ctx.insertar(tabla, a_crear)
    ctx.reporte.linea(
        "invoices",
        "CG_Facturas_Tabla",
        leidos=len(a_crear) + omitidas,
        insertados=len(a_crear),
        omitidos=omitidas,
        motivo=(
            "solo las facturas que una OT reclama (id_trabajo no vacio): "
            "83.164 del legacy, 1.962 con id_trabajo; "
            f"{sin_ot} de las importadas apuntan a una OT fuera del corte "
            "(work_order_id NULL)"
        ),
        importes={"total facturado": total},
    )
    ctx.reporte.descartes(
        "facturas",
        {
            "facturas del legacy": 83164,
            "sin id_trabajo (facturacion de mostrador, no entra)": 83164 - 1962,
            "con id_trabajo (importadas)": len(a_crear),
            "de las importadas, con la OT fuera del corte": sin_ot,
            "de las importadas, con la OT en el corte": len(a_crear) - sin_ot,
            "anuladas (status = cancelled)": anuladas,
        },
    )
    if sin_cliente:
        ctx.reporte.observacion(
            f"{sin_cliente} facturas quedaron con el cliente 'sin identificar' "
            f"(su CodCli no esta en el maestro de clientes)."
        )


def _cuit_factura(cuit: str) -> str | None:
    """CUIT de la factura, si parece un CUIT.

    Se guardan los 11 digitos (sin guiones). Los placeholders del legacy
    (``11111111``) no son CUIT y quedan fuera.
    """
    digitos = "".join(caracter for caracter in (cuit or "") if caracter.isdigit())
    return digitos if len(digitos) == 11 else None
