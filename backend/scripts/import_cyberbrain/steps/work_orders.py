"""Paso 4: ordenes de trabajo.

Es el corazon de la importacion: 9.316 OTs del corte 2020+.

Detalles del legacy que hay que respetar:

- ``NumeroOrden`` **no es unico** (42.694 con numero para 12.886 distintos, hasta 60
  repeticiones), asi que va a ``legacy_number``. El numero de la OT en el destino es
  un **correlativo propio por empresa** (``work_order_counters``).
- ``Estado`` es un entero del legacy; se resuelve contra los estados de la empresa
  (``status_id``) y ademas se copia el nombre al campo ``status`` (que es un texto y
  lo compara el servicio de OTs).
- ``Responsable`` es un ``CC_Usuarios.Codigo`` y ``received_by_user_id`` es NOT NULL:
  los responsables que ya no existen van al usuario de respaldo.
- ``Falla`` es NOT NULL en el destino: si viene vacia se deja "Sin descripcion".
- La garantia sale del **area** (la politica), no del flag crudo de la OT: los dos
  difieren en 184 OTs del historico.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select

from .. import mappers, source
from ..context import Contexto

#: Texto que se deja cuando el legacy no informa la falla (``reported_fault`` es
#: NOT NULL en el destino).
FALTA_SIN_DESCRIPCION = "Sin descripción"


def ejecutar(ctx: Contexto) -> None:
    """Importa las ordenes de trabajo del corte."""
    mesas = _mesas(ctx)
    estados = _estados(ctx)

    tabla = ctx.tabla("work_orders")
    existentes = {
        str(legacy_id): fila_id
        for legacy_id, fila_id in ctx.session.execute(
            select(tabla.c.legacy_id, tabla.c.id).where(
                tabla.c.company_id == ctx.company_id, tabla.c.legacy_id.is_not(None)
            )
        ).all()
    }
    ctx.ot_por_legacy_id.update(existentes)

    numero_inicial = _proximo_numero(ctx, rearmar=ctx.replace)
    numero = numero_inicial
    omitidas = len(existentes)
    acumulado = {
        "costo": 0,
        "venta": 0,
        "con_empresa": 0,
        "costo_con_empresa": 0,
        "en_garantia": 0,
        "costo_garantia": 0,
        "sin_empresa": 0,
        "costo_sin_empresa": 0,
        "usuario_por_nombre": 0,
        "usuario_por_responsable": 0,
        "usuario_de_respaldo": 0,
    }

    def _filas():
        """Generador de OTs: recorre el legacy y arma las filas del destino."""
        nonlocal numero
        for fila in ctx.fuente.ordenes():
            legacy_id = source.texto(fila[0])
            if legacy_id in existentes:
                continue

            cliente_id = ctx.cliente_de_ot(fila[2], fila[6])
            equipo_id = ctx.equipos_por_ot.get(legacy_id)
            if equipo_id is None:
                raise RuntimeError(
                    f"La OT {legacy_id} no tiene equipo resuelto: el paso de equipos "
                    f"tiene que correr antes."
                )

            area_id = ctx.areas_por_policy_id.get(source.texto(fila[14]))
            warranty_type = ctx.warranty_por_area.get(area_id, 0) if area_id else 0

            nombre_estado = mappers.estado_destino(source.entero(fila[8], None))

            notas = source.texto(fila[21])
            ubicacion = source.texto(fila[18])
            if ubicacion and not _es_mesa(ubicacion):
                # La ubicacion del legacy se usa tambien para anotar la retirada del
                # equipo ("Retirada el 10/09/2022"): no es una mesa, pero no se tira.
                notas = (notas + "\n" if notas else "") + f"[Ubicación legacy: {ubicacion}]"

            costo = source.decimal(fila[15])
            venta = source.decimal(fila[16])
            presupuesto = source.decimal(fila[17])

            acumulado["costo"] += costo
            acumulado["venta"] += venta
            if area_id and ctx.billing_customer_por_area.get(area_id):
                acumulado["con_empresa"] += 1
                acumulado["costo_con_empresa"] += costo
                if warranty_type == 1:
                    acumulado["en_garantia"] += 1
                    acumulado["costo_garantia"] += costo
            else:
                acumulado["sin_empresa"] += 1
                acumulado["costo_sin_empresa"] += costo

            recibido_por, origen_usuario = _usuario_de_recepcion(ctx, fila)

            yield {
                "company_id": ctx.company_id,
                "number": numero,
                "customer_id": cliente_id,
                "equipment_id": equipo_id,
                "received_at": source.fecha(fila[9]) or source.fecha(fila[10]) or datetime.now(),
                "completed_at": source.fecha(fila[11]),
                "delivered_at": source.fecha(fila[12]),
                "reported_fault": source.texto(fila[7]) or FALTA_SIN_DESCRIPCION,
                "notes": notas or None,
                "received_by_user_id": recibido_por,
                "status": nombre_estado,
                "status_id": estados.get(nombre_estado),
                "legacy_id": int(legacy_id),
                "legacy_number": source.recortar(
                    "work_orders.legacy_number", source.texto(fila[1]), 20
                ),
                "work_area_id": area_id,
                "work_bench_id": mesas.get(_codigo_mesa(ubicacion)),
                "warranty_status": mappers.GARANTIA_A_ESTADO.get(warranty_type, "out_of_warranty"),
                "legacy_guarantee": source.entero(fila[23], None),
                "legacy_policy_id": source.entero(fila[14], None),
                "cost_total": costo,
                "sale_total": venta,
                "quoted_total": presupuesto,
                "legacy_invoice_number": source.recortar(
                    "work_orders.legacy_invoice_number",
                    source.texto(fila[19]) or source.texto(fila[20]),
                    50,
                ),
            }
            numero += 1

    ids = ctx.insertar(tabla, _filas(), clave=lambda fila: str(fila["legacy_id"]))
    ctx.ot_por_legacy_id.update({clave: int(valor) for clave, valor in ids.items()})
    _guardar_contador(ctx, numero_inicial + len(ids))

    ctx.reporte.linea(
        "work_orders",
        "CS_Trabajos",
        leidos=len(ids) + omitidas,
        insertados=len(ids),
        omitidos=omitidas,
        importes={
            "costo total": acumulado["costo"],
            "venta total": acumulado["venta"],
        },
    )
    ctx.reporte.seccion(
        "CIERRE MENSUAL A MARCAS (criterio B: todo lo que tiene empresa a liquidar)",
        [
            f"Con empresa a liquidar : {acumulado['con_empresa']:>6} OTs   "
            f"costo {acumulado['costo_con_empresa']:>18,.2f}",
            f"  de ellas, en garantia : {acumulado['en_garantia']:>6} OTs   "
            f"costo {acumulado['costo_garantia']:>18,.2f}",
            f"Sin empresa a liquidar  : {acumulado['sin_empresa']:>6} OTs   "
            f"costo {acumulado['costo_sin_empresa']:>18,.2f}",
            f"Total                   : {len(ids):>6} OTs   costo {acumulado['costo']:>18,.2f}",
        ],
    )
    ctx.reporte.observacion(
        "Numero de OT: correlativo propio por empresa (work_order_counters). El "
        "NumeroOrden del legacy va a legacy_number porque no es unico (12.886 numeros "
        "para 56.619 OTs, con hasta 60 repeticiones y 69 % vacio)."
    )
    ctx.reporte.descartes(
        "ordenes de trabajo",
        {
            "OTs del corte": len(ids) + omitidas,
            "importadas": len(ids),
            "recibidas por el 'Usuario' de la OT (D5)": ctx.contadores.get("usuario_por_nombre", 0),
            "recibidas por el 'Responsable' de la OT": ctx.contadores.get(
                "usuario_por_responsable", 0
            ),
            "recibidas por el usuario de respaldo": ctx.contadores.get("usuario_de_respaldo", 0),
            "sin empresa a liquidar": acumulado["sin_empresa"],
            "en garantia (warranty_type = 1)": acumulado["en_garantia"],
        },
    )


def _usuario_de_recepcion(ctx: Contexto, fila: list) -> tuple[int, str]:
    """Resuelve quien recibio el equipo (``received_by_user_id``, NOT NULL).

    Decision D5: se mapea el ``Usuario`` de la OT contra los 44 usuarios del legacy
    (``CC_Usuarios``). Ese campo es un nombre libre y viene vacio en el 91 % de las
    OTs, asi que cuando no matchea se recurre al ``Responsable`` de la OT (que si es
    el codigo del ``CC_Usuarios`` que recibio el equipo) y, si tampoco hay match, al
    usuario de respaldo del importador ("Importación / legacy").

    Se devuelve tambien de donde salio el match, para que el cuadre lo muestre.
    """
    usuario = source.texto(fila[25]) if len(fila) > 25 else ""
    if usuario:
        por_nombre = ctx.usuarios_por_nombre.get(mappers.normalizar_nombre(usuario))
        if por_nombre is not None:
            ctx.contadores["usuario_por_nombre"] = (
                ctx.contadores.get("usuario_por_nombre", 0) + 1
            )
            return por_nombre, "Usuario"
    responsable = source.texto(fila[13])
    por_codigo = ctx.usuarios_por_codigo.get(responsable)
    if por_codigo is not None:
        ctx.contadores["usuario_por_responsable"] = (
            ctx.contadores.get("usuario_por_responsable", 0) + 1
        )
        return por_codigo, "Responsable"
    ctx.contadores["usuario_de_respaldo"] = (
        ctx.contadores.get("usuario_de_respaldo", 0) + 1
    )
    return ctx.usuario_respaldo, "respaldo"


def _es_mesa(ubicacion: str) -> bool:
    """Si el texto de ubicacion del legacy es una mesa (y no una nota de retirada)."""
    return mappers.normalizar_mesa(ubicacion) is not None


def _codigo_mesa(ubicacion: str) -> str | None:
    """Codigo normalizado de la mesa, o ``None`` si el texto no es una mesa."""
    normalizado = mappers.normalizar_mesa(ubicacion)
    return normalizado[0] if normalizado else None


def _mesas(ctx: Contexto) -> dict[str, int]:
    """Crea el maestro de mesas y devuelve el mapa texto normalizado -> id.

    El maestro guarda tambien los textos de origen (``legacy_aliases``): la misma
    mesa esta escrita de varias maneras en el legacy y conviene dejar registro.
    """
    tabla = ctx.tabla("work_benches")
    aliases: dict[str, set[str]] = {}
    for ubicacion in ctx.fuente.ubicaciones():
        normalizado = mappers.normalizar_mesa(ubicacion)
        if normalizado is None:
            continue
        aliases.setdefault(normalizado[0], set()).add(ubicacion)

    existentes = {
        fila[0]: fila[1]
        for fila in ctx.session.execute(
            select(tabla.c.normalized_code, tabla.c.id).where(tabla.c.company_id == ctx.company_id)
        ).all()
    }
    a_crear = []
    for codigo, textos in aliases.items():
        if codigo in existentes:
            continue
        a_crear.append(
            {
                "company_id": ctx.company_id,
                "name": source.recortar("work_benches.name", codigo, 80) or codigo,
                "normalized_code": source.recortar("work_benches.normalized_code", codigo, 80)
                or codigo,
                "legacy_aliases": " | ".join(sorted(textos)),
                "active": True,
            }
        )
    ctx.insertar(tabla, a_crear)
    mapa = dict(existentes)
    for fila in a_crear:
        mapa[str(fila["normalized_code"])] = int(fila["id"])
    ctx.mesas_por_codigo.update(mapa)
    return mapa


def _estados(ctx: Contexto) -> dict[str, int]:
    """Mapa nombre de estado -> id, de los estados de la empresa."""
    tabla = ctx.tabla("work_order_statuses")
    return {
        fila[0]: fila[1]
        for fila in ctx.session.execute(
            select(tabla.c.name, tabla.c.id).where(tabla.c.company_id == ctx.company_id)
        ).all()
    }


def _proximo_numero(ctx: Contexto, rearmar: bool) -> int:
    """Primer numero de OT a asignar.

    Con ``--replace`` el correlativo se rearma a MAX(number) de las OTs que quedan
    (las que no son del legacy), para que reimportar de cero devuelva **los mismos
    numeros** que la vuelta anterior.
    """
    tabla = ctx.tabla("work_orders")
    if rearmar:
        maximo = ctx.session.execute(
            select(func.coalesce(func.max(tabla.c.number), 0)).where(
                tabla.c.company_id == ctx.company_id, tabla.c.legacy_id.is_(None)
            )
        ).scalar_one()
        return int(maximo) + 1
    contador = ctx.tabla("work_order_counters")
    ultimo = ctx.session.execute(
        select(contador.c.last_number).where(contador.c.company_id == ctx.company_id)
    ).scalar_one_or_none()
    return int(ultimo or 0) + 1


def _guardar_contador(ctx: Contexto, ultimo: int) -> None:
    """Guarda el correlativo en ``work_order_counters``.

    La tabla tiene clave primaria compuesta (``company_id``) y no tiene ``id``, asi
    que no se puede insertar con el helper generico.
    """
    contador = ctx.tabla("work_order_counters")
    existente = ctx.session.execute(
        select(contador.c.last_number).where(contador.c.company_id == ctx.company_id)
    ).scalar_one_or_none()
    if existente is None:
        if not ctx.dry_run:
            ctx.session.execute(
                contador.insert().values(company_id=ctx.company_id, last_number=ultimo)
            )
    elif not ctx.dry_run:
        ctx.session.execute(
            contador.update()
            .where(contador.c.company_id == ctx.company_id)
            .values(last_number=ultimo)
        )
