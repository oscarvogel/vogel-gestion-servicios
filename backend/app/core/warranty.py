"""La garantía de las órdenes: los tres tipos y cómo se traducen.

En el legacy (CiberBrain) **no hay un campo de garantía en la OT**. La garantía sale de la
**política** del área (``dbo.Aux_PoliticasxArea.TipoTrabajo``), y eso es lo que quedó
resuelto en ``work_areas.warranty_type``:

    0 = fuera de garantía
    1 = garantía de terceros (de fábrica)
    2 = garantía propia / de service

``work_orders.warranty_status`` guarda el mismo dato con el texto que usa la aplicación
(``out_of_warranty`` / ``warranty`` / ``own_warranty``), que es el que copiaba el
importador del legacy.

**Por qué vive acá y no en la API:** la garantía se deriva del área en tres lugares
distintos —la recepción, el cambio de área de una OT ya abierta y el alta/edición del
maestro— y tiene que ser la misma regla en los tres. Si cada uno lo calculara por su
cuenta, la OT y el cierre a marcas terminarían discrepando sin que nadie lo note.
"""
from __future__ import annotations

#: ``work_areas.warranty_type`` -> ``work_orders.warranty_status``.
GARANTIA_A_ESTADO: dict[int, str] = {
    0: "out_of_warranty",
    1: "warranty",
    2: "own_warranty",
}

#: Como se le muestra al operador.
ETIQUETA_GARANTIA: dict[int, str] = {
    0: "Fuera de garantía",
    1: "Garantía de terceros",
    2: "Garantía propia / de service",
}

#: Los tipos válidos de garantía.
TIPOS_GARANTIA: tuple[int, ...] = (0, 1, 2)


def estado_de_garantia(warranty_type: int | None) -> str | None:
    """El ``warranty_status`` que corresponde a un tipo de garantía.

    Devuelve ``None`` cuando no hay tipo: una OT sin área **no tiene** garantía, y no
    se le inventa "fuera de garantía". Eso sería decir que la marca no lo cubre, cuando
    lo que en realidad es que todavía no se sabe a quién se le liquida.
    """
    if warranty_type is None:
        return None
    return GARANTIA_A_ESTADO.get(warranty_type)


def etiqueta_de_garantia(warranty_type: int | None) -> str | None:
    """El texto de la garantía, para la pantalla."""
    if warranty_type is None:
        return None
    return ETIQUETA_GARANTIA.get(warranty_type, ETIQUETA_GARANTIA[0])
