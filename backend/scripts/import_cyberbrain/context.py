"""Estado compartido de la importacion.

El importador resuelve todas las referencias **en memoria** (``codcli`` ->
``customer_id``, ``id_trabajo`` -> ``work_order_id``, etc.) y despues escribe cada
entidad por lotes. Con 9.316 OTs, 29.799 lineas y 18.383 intervenciones, ir a la
base a buscar cada referencia seria lentisimo.

El contexto lleva ese mapa y tambien los helpers de escritura: los inserts son
"executemany" con los id asignados por el propio script, asi el paso siguiente ya
sabe el id de lo que se acaba de escribir sin volver a preguntar a la base.

Del lado del legacy no hay mapas en memoria: las consultas van enstreaming (el
driver trae las filas de a 1.000) y cada paso vuelve a consultar lo que necesita.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from sqlalchemy import Table, func, select
from sqlalchemy.orm import Session

from app.db.base import Base

from . import source
from .report import Reporte
from .source import FuenteCiberBase

#: Cuantas filas van por cada INSERT. Con 1.000 el paquete SQL entra de sobra en el
#: ``max_allowed_packet`` de MySQL y el round trip se amortiza.
TAMANO_LOTE = 1000


def _trozos(items: Sequence[Any], tamano: int) -> Iterator[Sequence[Any]]:
    """Parte una secuencia en trozos de ``tamano``."""
    for inicio in range(0, len(items), tamano):
        yield items[inicio : inicio + tamano]


@dataclass
class Contexto:
    """Lo que comparten los pasos: sesion, empresa, mapas y cuadre."""

    session: Session
    company_id: int
    fuente: FuenteCiberBase
    dry_run: bool
    replace: bool
    reporte: Reporte

    # --- mapas de referencia (se llenan en los pasos) ---
    #: Codigo de CC_Usuarios -> users.id
    usuarios_por_codigo: dict[str, int] = field(default_factory=dict)
    #: Nombre normalizado de CC_Usuarios -> users.id (para el campo Usuario de la OT)
    usuarios_por_nombre: dict[str, int] = field(default_factory=dict)
    #: Usuario de respaldo para los responsables que ya no existen en el legacy
    usuario_respaldo: int | None = None
    #: Codigo de CC_Usuarios -> sellers.id
    vendedores_por_codigo: dict[str, int] = field(default_factory=dict)
    #: Codigo de CC_Usuarios -> technicians.id
    tecnicos_por_codigo: dict[str, int] = field(default_factory=dict)
    #: Codigo de cliente del legacy -> customers.id
    clientes_por_codcli: dict[str, int] = field(default_factory=dict)
    #: Nombre normalizado de cliente -> customers.id (para emparejar OTs sin cliente)
    clientes_por_nombre: dict[str, int] = field(default_factory=dict)
    #: Nombre del cliente "sin identificar"
    cliente_sin_identificar: int | None = None
    #: areas.tsv.policy_id -> work_areas.id
    areas_por_policy_id: dict[str, int] = field(default_factory=dict)
    #: (area_code, policy_code) -> work_areas.id
    areas_por_clave: dict[tuple[str, str], int] = field(default_factory=dict)
    #: work_areas.id -> warranty_type (0 fuera, 1 terceros, 2 propia)
    warranty_por_area: dict[int, int] = field(default_factory=dict)
    #: work_areas.id -> billing_customer_id (a quien se liquida el area)
    billing_customer_por_area: dict[int, int] = field(default_factory=dict)
    #: work_benches.normalized_code -> work_benches.id
    mesas_por_codigo: dict[str, int] = field(default_factory=dict)
    #: id_trabajo del legacy -> equipment.id (un equipo por OT, decision D3)
    equipos_por_ot: dict[str, int] = field(default_factory=dict)
    #: work_orders.legacy_id -> work_orders.id
    ot_por_legacy_id: dict[str, int] = field(default_factory=dict)
    #: work_order_parts.legacy_id -> work_order_parts.id
    partes_por_legacy_id: dict[str, int] = field(default_factory=dict)

    _contadores: dict[str, int] = field(default_factory=dict)

    #: Contadores libres de los pasos, para el cuadre (de donde salio cada match, etc.)
    contadores: dict[str, int] = field(default_factory=dict)

    # -- escritura --------------------------------------------------------
    def tabla(self, nombre: str) -> Table:
        """Tabla del destino, desde los modelos (que son el contrato)."""
        return Base.metadata.tables[nombre]

    def _proximo_id(self, tabla: Table) -> int:
        """Primer id libre de la tabla.

        Los ids se asignan desde el importador y no desde el auto-incremento para
        poder usar ``executemany`` y saber el id de cada fila sin volver a leer la
        tabla. Se arranca en ``MAX(id) + 1``, asi que convive con filas que ya
        existan.
        """
        if self.dry_run:
            return self._contadores.get(tabla.name, 0) + 1
        maximo = self.session.execute(
            select(func.coalesce(func.max(tabla.c.id), 0))
        ).scalar_one()
        return int(maximo) + 1

    def insertar(
        self,
        tabla: Table,
        filas: Iterable[dict[str, Any]],
        clave: Callable[[dict[str, Any]], Any] | None = None,
    ) -> dict[Any, int]:
        """Escribe las filas por lotes y devuelve el mapa ``clave -> id``.

        ``filas`` puede ser un generador: el importador no carga las 29.799 lineas
        en memoria, las va pasando de a 1.000 al INSERT. Con ``clave`` se devuelve
        el mapa de ids (por ejemplo ``legacy_id -> id``), que es lo que despues
        usan los pasos siguientes para resolver referencias.

        En ``--dry-run`` no toca la base: solo cuenta y asigna ids virtuales, para
        que el cuadre diga exactamente lo que pasaria.
        """
        ids: dict[Any, int] = {}
        buffer: list[dict[str, Any]] = []
        siguiente = self._proximo_id(tabla)
        for fila in filas:
            fila["id"] = siguiente
            siguiente += 1
            if clave is not None:
                ids[clave(fila)] = fila["id"]
            buffer.append(fila)
            if len(buffer) >= TAMANO_LOTE:
                self._escribir(tabla, buffer)
                buffer = []
        if buffer:
            self._escribir(tabla, buffer)
        if self.dry_run:
            self._contadores[tabla.name] = siguiente - 1
        return ids

    def _escribir(self, tabla: Table, filas: list[dict[str, Any]]) -> None:
        """Un INSERT multi-fila. Nunca fila por fila: son ~150.000 filas."""
        if self.dry_run or not filas:
            return
        self.session.execute(tabla.insert().values(filas))

    def ejecutar(self, sentencia: str, **parametros: Any) -> None:
        """Ejecuta SQL crudo (lo que el ORM no cubre: borrados de ``--replace``)."""
        if self.dry_run:
            return
        self.session.connection().exec_driver_sql(sentencia, parametros)

    def cliente_de_ot(self, codcli: str, nombre: str) -> int:
        """Cliente de una OT.

        Primero por ``CodCli``; si la OT no trae cliente (5.969 de las 9.316 del
        corte), se empareja por el nombre de ``work_orders.cliente`` contra el
        maestro; si tampoco coincide, va al cliente "sin identificar".

        Que la OT quede sin identificar no bloquea el cierre mensual: el cierre
        agrupa por *empresa a liquidar* (el area), no por cliente final.
        """
        codigo = source.texto(codcli)
        if codigo not in ("", "0"):
            cliente = self.clientes_por_codcli.get(codigo)
            if cliente is not None:
                return cliente
        from . import mappers

        por_nombre = self.clientes_por_nombre.get(mappers.normalizar_nombre(nombre))
        if por_nombre is not None:
            return por_nombre
        if self.cliente_sin_identificar is None:
            raise RuntimeError(
                "El cliente 'sin identificar' no esta cargado: se crea en el paso de "
                "clientes, que tiene que correr antes."
            )
        return self.cliente_sin_identificar
