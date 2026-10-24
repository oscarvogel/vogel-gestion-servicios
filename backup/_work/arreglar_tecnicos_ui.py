"""Ajustes pedidos sobre el panel de técnicos.

1. El input "Agregar un tecnico..." del detalle de la OT salia blanco (el default del
   navegador): no vive dentro de un .field, asi que no heredaba el estilo del sitio.
2. Ver que tecnicos estan activos: los chips de los asignados muestran su estado
   (Inactivo) y los selectores aclaran que solo ofrecen los activos del maestro.
"""
from __future__ import annotations

import io

RUTA = "frontend/src/views/WorkOrdersView.vue"


def reemplazar(texto: str, viejo: str, nuevo: str, esperado: int = 1) -> str:
    n = texto.count(viejo)
    if n != esperado:
        raise SystemExit(f"Aparecen {n} veces (se esperaba {esperado}): {viejo[:80]!r}")
    return texto.replace(viejo, nuevo)


def main() -> None:
    texto = io.open(RUTA, encoding="utf-8").read()

    # 1) El input del panel de la OT con el estilo del sitio.
    texto = reemplazar(
        texto,
        ".technician-assign input{width:100%}",
        ".technician-assign input{width:100%;background:var(--color-surface);"
        "border:1px solid var(--color-border);border-radius:var(--radius-md);"
        "padding:10px 12px;color:var(--color-text-primary);outline:none;"
        "transition:border .18s ease,background .18s ease}\n"
        ".technician-assign input:focus{border-color:var(--color-primary);"
        "background:var(--color-surface-elevated)}\n"
        ".technician-assign input::placeholder{color:var(--color-text-muted)}",
    )

    # 2) El chip de un tecnico desactivado se ve distinto y lo dice.
    texto = reemplazar(
        texto,
        'class="technician-chip"><strong>{{t.name}}</strong>',
        'class="technician-chip" :class="{\'technician-chip--inactive\':!t.active}">'
        "<strong>{{t.name}}</strong>"
        '<span v-if="!t.active" class="technician-chip__state">Inactivo</span>',
    )
    texto = reemplazar(
        texto,
        ".technician-chip__remove{border:0;",
        ".technician-chip--inactive{background:rgba(100,116,139,.16);color:#94A3B8;"
        "border-color:rgba(100,116,139,.45)}\n"
        ".technician-chip__state{font-size:11px;letter-spacing:.06em;"
        "text-transform:uppercase;opacity:.85}\n"
        ".technician-chip__remove{border:0;",
    )

    # 3) Los selectores aclaran que solo ofrecen los tecnicos activos.
    texto = reemplazar(
        texto,
        'No hay m\u00e1s t\u00e9cnicos para asignar.',
        "No hay t\u00e9cnicos activos para asignar.",
    )
    texto = reemplazar(
        texto,
        '<h3>T\u00e9cnicos asignados</h3>',
        '<h3>T\u00e9cnicos asignados</h3>'
        '<small class="text-muted">Se muestran los t\u00e9cnicos activos del maestro; '
        "un t\u00e9cnico desactivado queda en las \u00f3rdenes que ya ten\u00eda "
        "asignado.</small>",
    )

    io.open(RUTA, "w", encoding="utf-8", newline="\n").write(texto)
    print("Listo: color del input, estado de los chips y aviso de activos.")


if __name__ == "__main__":
    main()
