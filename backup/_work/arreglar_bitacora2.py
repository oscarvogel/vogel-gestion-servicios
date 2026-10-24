"""Agrega a la bitacora la seccion 6 (ajustes de UI del panel de tecnicos)."""
from __future__ import annotations

import io

RUTA = "docs/sesion-2026-10-23-tecnicos.md"

NUEVO = """### 5.5 Dos ajustes mas sobre los tecnicos (a pedido del cliente)

**El input "Agregar un tecnico..." salia blanco.** En el detalle de la OT ese input no
vive dentro de un `.field`, asi que no heredaba la regla `.field input{background:
var(--color-surface); border: 1px solid var(--color-border); ...}` y se veia con el
default del navegador: un rectangulo blanco en medio de la pantalla oscura. Ahora
`.technician-assign input` lleva el mismo estilo (fondo, borde, radio, padding, color) y
el mismo estado de foco (`.technician-assign input:focus`) que el resto del sitio. El
input de la recepcion ya estaba bien: ese si esta dentro de un `.field`.

**Ver cuales tecnicos estan activos.** El maestro ya mostraba el estado de cada fila y el
contador ("44 activos de 44"), pero faltaba poder ver de un vistazo solo los activos, y
en la OT no se distinguishia un tecnico desactivado de uno activo. Ahora:

- El maestro tiene tres filtros con el mismo patron de chips de la pantalla de Empresas:
  **Todos / Activos (44) / Desactivados (0)**.
- Los chips de "Tecnicos asignados" en el detalle de la OT marcan **Inactivo** a los
  desactivados (chip apagado, no azul). Un tecnico desactivado sigue en las ordenes que
  ya tenia asignado (el historico no se toca), asi que hay que poder ver que ya no esta
  activo.
- Los selectores (recepcion y detalle de la OT) **solo ofrecen tecnicos activos**: el
  backend tambien lo rechaza con 409 ("El tecnico esta desactivado: activalo desde el
  maestro para poder asignarlo").
- El texto del selector de la recepcion ahora dice que solo se ofrecen los activos.

Test: `frontend/src/__tests__/tecnicos-activos.test.ts` (4 tests). Frontend: 60 tests en
verde.

---

"""


def main() -> None:
    texto = io.open(RUTA, encoding="utf-8").read()
    crlf = texto.count("\r\n") > texto.count("\n") / 2
    nl = "\r\n" if crlf else "\n"

    marca = "## 6. Pendientes"
    i = texto.find(marca)
    if i < 0:
        raise SystemExit("No se encontro la seccion de pendientes")
    bloque = texto[:i] + NUEVO.replace("\n", nl) + texto[i:]
    io.open(RUTA, "wb").write(bloque.encode("utf-8"))
    print(f"Bitacora actualizada (nl={nl!r})")


if __name__ == "__main__":
    main()
