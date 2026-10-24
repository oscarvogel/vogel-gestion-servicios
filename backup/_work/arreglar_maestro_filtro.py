"""Filtro por estado en el maestro de técnicos.

El maestro ya mostraba el estado de cada fila y el contador de activos, pero no había
forma de ver "solo los activos" de un vistazo: ahora hay tres filtros (Todos / Activos /
Desactivados) con el mismo patron de chips que usa la pantalla de Empresas.
"""
from __future__ import annotations

import io

RUTA = "frontend/src/views/TecnicosView.vue"


def reemplazar(texto: str, viejo: str, nuevo: str) -> str:
    n = texto.count(viejo)
    if n != 1:
        raise SystemExit(f"Aparecen {n} veces: {viejo[:80]!r}")
    return texto.replace(viejo, nuevo)


def main() -> None:
    texto = io.open(RUTA, encoding="utf-8").read()

    texto = reemplazar(
        texto,
        "const search = ref(\"\");\n",
        "const search = ref(\"\");\nconst filtroEstado = ref<\"\" | \"active\" | \"inactive\">(\"\");\n",
    )

    texto = reemplazar(
        texto,
        "const filtrados = computed<Technician[]>(() => {\n"
        "  const query = normalizar(search.value);\n"
        "  if (!query) return technicians.value;\n"
        "  return technicians.value.filter((t) => normalizar(t.name).includes(query));\n"
        "});",
        "const filtrados = computed<Technician[]>(() => {\n"
        "  const query = normalizar(search.value);\n"
        "  return technicians.value.filter((t) => {\n"
        "    if (filtroEstado.value === \"active\" && !t.active) return false;\n"
        "    if (filtroEstado.value === \"inactive\" && t.active) return false;\n"
        "    if (!query) return true;\n"
        "    return normalizar(t.name).includes(query);\n"
        "  });\n"
        "});",
    )

    texto = reemplazar(
        texto,
        '        aria-label="Buscar t\u00e9cnico"\n'
        "      />\n"
        "    </div>",
        '        aria-label="Buscar t\u00e9cnico"\n'
        "      />\n"
        '      <div class="toolbar__filters">\n'
        "        <button\n"
        "          :class=\"['toolbar__chip', { 'is-active': filtroEstado === '' }]\"\n"
        "          type=\"button\"\n"
        "          @click=\"filtroEstado = ''\"\n"
        "        >\n"
        "          Todos\n"
        "        </button>\n"
        "        <button\n"
        "          :class=\"['toolbar__chip', { 'is-active': filtroEstado === 'active' }]\"\n"
        "          type=\"button\"\n"
        "          @click=\"filtroEstado = 'active'\"\n"
        "        >\n"
        "          Activos ({{ activos }})\n"
        "        </button>\n"
        "        <button\n"
        "          :class=\"['toolbar__chip', { 'is-active': filtroEstado === 'inactive' }]\"\n"
        "          type=\"button\"\n"
        "          @click=\"filtroEstado = 'inactive'\"\n"
        "        >\n"
        "          Desactivados ({{ technicians.length - activos }})\n"
        "        </button>\n"
        "      </div>\n"
        "    </div>",
    )

    io.open(RUTA, "w", encoding="utf-8", newline="\n").write(texto)
    print("Listo: filtro Todos / Activos / Desactivados en el maestro.")


if __name__ == "__main__":
    main()
