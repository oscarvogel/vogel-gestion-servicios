"""Paso 3: equipos.

El legacy **no tiene maestro de equipos**: ``dbo.DatosEquipos`` tiene exactamente
56.619 filas, una por OT (Equipo, Modelo, NroSerie, Usuario, Falla...), o sea que es
otro snapshot por OT y no un maestro. El equipo sale de la propia OT
(``CS_Trabajos.Equipo`` / ``.Modelo`` / ``.NroSerie``).

Decision D3: **un equipo por OT** (9.316), con ``customer_id`` = el cliente de esa
OT. NO se deduplica por serie: el legacy no lo hace, el 87 % de las series son
placeholders (``ILEGIBLE``, ``S/N``, ``FALTA``) y hay 92 pares (equipo + serie) que
comparten clientes distintos. Deduplicar seria inventar datos que el legacy no
tiene.

La serie solo se guarda si sirve: ``ILEGIBLE``, ``FALTA``, ``S/N``, ``NO TIENE`` y
variantes no son series. Cuando no hay serie, el equipo queda con
``serial_number`` NULL (y eso se cuenta en el cuadre).

La **categoria** sale de un catalogo curado: los 60 valores mas frecuentes del corte
(tipo + marca, como ``LAVARROPAS DREAN``) y todo lo demas va a ``OTROS``. La
categoria no reemplaza al texto original: el ``description`` del equipo guarda
``CS_Trabajos.Equipo`` tal cual.
"""

from __future__ import annotations

from collections import Counter

from sqlalchemy import select

from .. import mappers, source
from ..context import Contexto
from .customers import MARCA_LEGACY


def ejecutar(ctx: Contexto) -> None:
    """Crea un equipo por cada OT del corte."""
    categorias = _catalogo(ctx)
    categoria_id = _crear_categorias(ctx, categorias)

    tabla = ctx.tabla("equipment")
    # Equipos ya importados: se reconocen por la marca del ``notes``, que guarda el
    # id de la OT del legacy. Asi una segunda corrida sin --replace no duplica.
    existentes: dict[str, int] = {}
    for equipo_id, notas in ctx.session.execute(
        select(tabla.c.id, tabla.c.notes).where(tabla.c.company_id == ctx.company_id)
    ).all():
        if notas and notas.startswith(MARCA_LEGACY):
            for parte in notas.splitlines():
                if parte.startswith("ot="):
                    existentes[parte.split("=", 1)[1].strip()] = equipo_id
                    break

    sin_serie = 0
    sin_modelo = 0
    sin_equipo = 0

    def _filas():
        """Generador de equipos: recorre las OTs del corte y arma un equipo por OT."""
        nonlocal sin_serie, sin_modelo, sin_equipo
        for fila in ctx.fuente.ordenes():
            legacy_id = source.texto(fila[0])
            if legacy_id in existentes:
                continue
            cliente_id = ctx.cliente_de_ot(fila[2], fila[6])
            serie = mappers.serie_util(fila[3])
            equipo = source.texto(fila[4])
            modelo = source.texto(fila[5])
            if serie is None:
                sin_serie += 1
            if not modelo:
                sin_modelo += 1
            if not equipo:
                sin_equipo += 1
            tipo, marca = mappers.clave_categoria_equipo(equipo)
            nombre_categoria = mappers.nombre_categoria(tipo, marca)
            if nombre_categoria not in categoria_id:
                nombre_categoria = mappers.CATEGORIA_OTROS
            yield {
                "company_id": ctx.company_id,
                "customer_id": cliente_id,
                "category_id": categoria_id[nombre_categoria],
                "brand": None,
                "model": source.recortar("equipment.model", modelo, 120),
                "serial_number": source.recortar("equipment.serial_number", serie, 120),
                "description": source.recortar("equipment.description", equipo, 300),
                "notes": (
                    f"{MARCA_LEGACY}\not={legacy_id}\n"
                    f"serie={source.texto(fila[3]) or '(vacia)'}"
                ),
                "active": True,
            }

    ids = ctx.insertar(tabla, _filas(), clave=lambda fila: _ot_de_notas(str(fila["notes"])))
    ctx.equipos_por_ot.update({clave: int(valor) for clave, valor in ids.items()})
    ctx.equipos_por_ot.update(existentes)

    ctx.reporte.linea(
        "equipment_categories",
        "CS_Trabajos.Equipo",
        leidos=len(categorias),
        insertados=len(categorias),
        motivo=(
            f"catalogo curado: {mappers.CANTIDAD_CATEGORIAS} categorias mas frecuentes "
            f"+ '{mappers.CATEGORIA_OTROS}'"
        ),
    )
    ctx.reporte.linea(
        "equipment",
        "CS_Trabajos",
        leidos=len(ids) + len(existentes),
        insertados=len(ids),
        omitidos=len(existentes),
        motivo="un equipo por OT (D3): no se deduplica por serie",
    )
    ctx.reporte.descartes(
        "equipos",
        {
            "equipos creados (uno por OT)": len(ids),
            "sin numero de serie utilizable": sin_serie,
            "sin modelo": sin_modelo,
            "sin descripcion de equipo": sin_equipo,
            "series descartadas por ser placeholder": sin_serie,
        },
    )


def _ot_de_notas(notas: str) -> str:
    """Saca el id de la OT del legacy de las notas del equipo."""
    for parte in notas.splitlines():
        if parte.startswith("ot="):
            return parte.split("=", 1)[1].strip()
    return ""


def _catalogo(ctx: Contexto) -> list[str]:
    """Nombres de las categorias del catalogo curado.

    Se cuentan las OTs por cada par (tipo, marca) y se quedan los
    ``CANTIDAD_CATEGORIAS`` mas frecuentes. Lo que queda fuera va a ``OTROS``.
    """
    frecuencias: Counter[tuple[str | None, str | None]] = Counter()
    for equipo, cantidad in ctx.fuente.frecuencias_equipo():
        tipo, marca = mappers.clave_categoria_equipo(equipo)
        frecuencias[(tipo, marca)] += cantidad
    nombres = []
    for (tipo, marca), _ in frecuencias.most_common(mappers.CANTIDAD_CATEGORIAS):
        nombre = mappers.nombre_categoria(tipo, marca)
        if nombre not in nombres:
            nombres.append(nombre)
    if mappers.CATEGORIA_OTROS not in nombres:
        nombres.append(mappers.CATEGORIA_OTROS)
    return nombres


def _crear_categorias(ctx: Contexto, nombres: list[str]) -> dict[str, int]:
    """Crea las categorias que falten y devuelve el mapa nombre -> id."""
    tabla = ctx.tabla("equipment_categories")
    existentes = {
        fila[0]: fila[1]
        for fila in ctx.session.execute(
            select(tabla.c.name, tabla.c.id).where(tabla.c.company_id == ctx.company_id)
        ).all()
    }
    a_crear = [
        {"company_id": ctx.company_id, "name": nombre, "active": True}
        for nombre in nombres
        if nombre not in existentes
    ]
    ctx.insertar(tabla, a_crear)
    mapa = dict(existentes)
    for fila in a_crear:
        mapa[str(fila["name"])] = int(fila["id"])
    return mapa
