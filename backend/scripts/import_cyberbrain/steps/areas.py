"""Paso 2: marcas / areas de trabajo.

Una politica del legacy es una fila de ``dbo.CS_PoliticasxArea`` (la vista que une
``Areas`` + ``TiposTrabajos`` + ``Aux_PoliticasxArea``), no una marca: el legacy tiene
tres tablas encajadas y el destino guarda las dos capas en una sola tabla
(``area_name`` + ``policy_code``).

Ojo con dos cosas que son faciles de confundir:

- ``liquidate_mode`` NO es "a quien se liquida": es el **ciclo de vida** de la OT
  (0/3 = liquidacion manual, 1 = automatica, 2 = nunca). "A quien se liquida" es
  exclusivamente ``billing_codcli``, que es el ``CodCli`` del area.
- ``policy_code`` vacio significa "politica principal" del area (la que no tiene
  sub-tipo). Se guarda como cadena vacia y no como NULL para que el indice unico
  sirva: en MySQL los NULL de un indice unico son todos distintos entre si.
"""

from __future__ import annotations

from sqlalchemy import select

from .. import source
from ..context import Contexto


def ejecutar(ctx: Contexto) -> None:
    """Crea las areas (marcas) con sus politicas de garantia."""
    tabla = ctx.tabla("work_areas")

    # Las politicas que ya estan (por area_code + policy_code) se reutilizan: una
    # segunda corrida sin --replace no puede duplicarlas.
    existentes = {
        (str(fila[0]), str(fila[1])): fila[2]
        for fila in ctx.session.execute(
            select(tabla.c.area_code, tabla.c.policy_code, tabla.c.id).where(
                tabla.c.company_id == ctx.company_id
            )
        ).all()
    }
    garantias = {
        int(fila[0]): int(fila[1])
        for fila in ctx.session.execute(
            select(tabla.c.id, tabla.c.warranty_type).where(tabla.c.company_id == ctx.company_id)
        ).all()
    }
    facturadores = {
        int(fila[0]): int(fila[1])
        for fila in ctx.session.execute(
            select(tabla.c.id, tabla.c.billing_customer_id).where(
                tabla.c.company_id == ctx.company_id, tabla.c.billing_customer_id.is_not(None)
            )
        ).all()
    }

    a_crear: list[dict[str, object]] = []
    policy_ids: list[str] = []
    sin_cliente = 0
    for (
        policy_id,
        area_code,
        area_name,
        policy_code,
        policy_description,
        billing_codcli,
        brand_name,
        warranty_type,
        liquidate_mode,
        utility,
        comision_prod_mode,
        comision_prod_pct,
        comision_part_mode,
        comision_part_pct,
        comision_service_mode,
        comision_service_pct,
        comision_other_mode,
        comision_other_pct,
    ) in ctx.fuente.areas():
        codigo = source.texto(policy_code)
        clave = (source.texto(area_code), codigo)
        if clave in existentes:
            area_id = existentes[clave]
            ctx.areas_por_policy_id[source.texto(policy_id)] = area_id
            ctx.areas_por_clave[clave] = area_id
            ctx.warranty_por_area[area_id] = garantias.get(area_id, 0)
            if area_id in facturadores:
                ctx.billing_customer_por_area[area_id] = facturadores[area_id]
            continue
        cliente = ctx.clientes_por_codcli.get(source.texto(billing_codcli))
        if cliente is None:
            sin_cliente += 1
        a_crear.append(
            {
                "company_id": ctx.company_id,
                "area_code": source.recortar("work_areas.area_code", source.texto(area_code), 20)
                or source.texto(area_code),
                "area_name": source.recortar("work_areas.area_name", source.texto(area_name), 120)
                or source.texto(area_name),
                "policy_code": codigo,
                "policy_description": source.recortar(
                    "work_areas.policy_description", source.texto(policy_description), 150
                ),
                "is_principal": codigo == "",
                "billing_customer_id": cliente,
                "brand_name": source.recortar("work_areas.brand_name", source.texto(brand_name), 150),
                "warranty_type": source.entero(warranty_type, 0) or 0,
                "liquidate_mode": source.entero(liquidate_mode, 0) or 0,
                "warranty_period_months": None,
                "utility": source.entero(utility, 0) or 0,
                "commission_product_mode": source.entero(comision_prod_mode, None),
                "commission_product_pct": source.decimal(comision_prod_pct, None)
                if source.texto(comision_prod_pct)
                else None,
                "commission_part_mode": source.entero(comision_part_mode, None),
                "commission_part_pct": source.decimal(comision_part_pct, None)
                if source.texto(comision_part_pct)
                else None,
                "commission_service_mode": source.entero(comision_service_mode, None),
                "commission_service_pct": source.decimal(comision_service_pct, None)
                if source.texto(comision_service_pct)
                else None,
                "commission_other_mode": source.entero(comision_other_mode, None),
                "commission_other_pct": source.decimal(comision_other_pct, None)
                if source.texto(comision_other_pct)
                else None,
                "active": True,
            }
        )
        policy_ids.append(source.texto(policy_id))

    ctx.insertar(tabla, a_crear)
    for fila, policy_id in zip(a_crear, policy_ids):
        area_id = int(fila["id"])
        ctx.areas_por_policy_id[policy_id] = area_id
        ctx.areas_por_clave[(str(fila["area_code"]), str(fila["policy_code"]))] = area_id
        ctx.warranty_por_area[area_id] = int(fila["warranty_type"])
        if fila["billing_customer_id"] is not None:
            ctx.billing_customer_por_area[area_id] = int(fila["billing_customer_id"])

    ctx.reporte.linea(
        "work_areas",
        "CS_PoliticasxArea",
        leidos=len(a_crear) + len(existentes),
        insertados=len(a_crear),
        omitidos=len(existentes),
        descartados=sin_cliente,
        motivo=(
            "politicas del legacy (area principal + sub-tipos FUERA/AGU/...). "
            f"{sin_cliente} areas sin CodCli de facturacion (billing_customer_id NULL)"
        ),
    )
