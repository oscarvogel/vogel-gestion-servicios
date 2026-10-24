"""Adaptador de solo lectura contra Flexxus (ERP de Suevos, Firebird 3050).

Este modulo es el unico que sabe de Firebird. El dominio no importa nada de
aca: recibe filas ya normalizadas.

Reglas que no se negocian (ver docs/plan-repuestos-flexxus.md):

- **Solo lectura.** La conexion se abre con ``readonly=True`` y todas las
  consultas son ``SELECT``. Nunca se escribe en el ERP.
- **Aguanta una base que no sea la esperada.** Si una tabla o una columna no
  existe, la consulta devuelve vacio en vez de reventar. El ERP tiene 671
  tablas y las bases cambian entre versiones: no se puede asumir.
- **Si el ERP no responde, se degrada.** ``FlexxusUnavailable`` y el servicio
  la transforma en una busqueda vacia con aviso. La OT tiene que seguir
  funcionando aunque el ERP este caido.
- **La base es la ruta del ``.gdb`` vista desde el servidor Firebird**, no una
  ruta local de la app.

Limites de este Firebird (2.5) que conviene no volver a descubrir a los golpes
- ``LIKE``, ``CONTAINING`` y ``POSITION`` cortan el **parametro de texto a los
  30 caracteres**: con uno mas largo la consulta revienta con "string right
  truncation" (-303). Por eso la busqueda trocea el texto en terminos.
- ``POSITION`` es **sensible a mayusculas**: hay que aplicar ``upper()`` a los
  dos lados.
- ``upper()`` **no convierte 'ñ' a 'Ñ'** con ISO8859_1: por eso la busqueda
  prueba las variantes con y sin tilde.
"""

from __future__ import annotations

import datetime as dt
import logging
import unicodedata
from typing import Any

LOGGER = logging.getLogger(__name__)

# Tablas del catalogo. Si alguna falta, se sigue con lo que haya.
TABLA_ARTICULOS = "ARTICULOS"
TABLA_STOCK = "STOCK"
TABLA_RUBROS = "RUBROS"
TABLA_MARCAS = "MARCAS"
TABLA_MONEDAS = "MONEDAS"


class FlexxusUnavailable(Exception):
    """El ERP no respondio, o la base no tiene lo que se le pidio.

    La busqueda degrada a vacio con aviso: nunca rompe la carga de la OT ni la
    generacion del presupuesto.
    """


def _sin_acentos(texto: str) -> str:
    """'Adaptador' -> 'ADAPTADOR'. Para que la busqueda sea insensible a acentos."""
    descompuesto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


# Letras que en el ERP pueden llevar tilde. Sirven para generar las variantes
# de una busqueda: con ISO8859_1, `upper()` NO convierte 'ñ' a 'Ñ', asi que
# buscar "cano" tiene que probar tambien "caño".
_LETRAS_CON_TILDE = {"A": "Á", "E": "É", "I": "Í", "O": "Ó", "U": "Ú", "N": "Ñ"}

# Firebird 2.5 corta los parametros de texto de las funciones de busqueda
# (`LIKE`, `CONTAINING`, `POSITION`) cuando superan este largo. Con 32 falla,
# con 30 no: el corte esta en 31.
_MAX_LARGO_TERMINO = 30
_MAX_TERMINOS = 4
_MAX_VARIANTES = 8


def _variantes(termino: str) -> list[str]:
    """Variantes con y sin tilde de un termino de busqueda.

    "cano" -> ["CANO", "CÁNO", "CAÑO", "CÁÑO"]. Asi "CAÑO SEMIRIGIDO" se
    encuentra tanto si el operador escribe "caño" como si escribe "cano".
    """
    base = termino.upper()
    posiciones = [i for i, c in enumerate(base) if c in _LETRAS_CON_TILDE]
    if not posiciones or len(posiciones) > 3:
        return [base]
    variantes = [base]
    for posicion in posiciones:
        nuevas: list[str] = []
        for variante in variantes:
            nuevas.append(variante)
            nuevas.append(
                variante[:posicion] + _LETRAS_CON_TILDE[base[posicion]] + variante[posicion + 1 :]
            )
        variantes = nuevas
    return list(dict.fromkeys(variantes))[:_MAX_VARIANTES]


def _terminos(texto: str) -> list[str]:
    """Parte la consulta en palabras que el ERP pueda buscar.

    Cada palabra es un termino y **todas** tienen que aparecer: buscar
    "arandela plana zinc" tiene que dar articulos que tengan las tres
    palabras, no los que tengan cualquiera de las tres.

    Los terminos salen en MAYUSCULAS y sin acentos: asi el SQL y el filtro
    de Python comparan exactamente lo mismo.
    """
    limpio = _sin_acentos(texto or "").strip().upper()
    if not limpio:
        return []
    partes = [p for p in limpio.split() if p]
    if not partes:
        return []
    if len(partes) == 1:
        return [partes[0][:_MAX_LARGO_TERMINO]]
    return [p[:_MAX_LARGO_TERMINO] for p in partes[:_MAX_TERMINOS]]


class FlexxusClient:
    """Cliente read-only defensivo contra una base de Flexxus."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        user: str,
        password: str | None,
        charset: str,
        database: str,
        timeout: float = 10.0,
    ) -> None:
        self.host = host
        self.port = port
        self.user = user
        self._password = password
        self.charset = charset
        self.database = database
        self.timeout = timeout

    # --- Conexion ---------------------------------------------------

    @staticmethod
    def _driver():
        """Import perezoso: `firebirdsql` es un extra, no puede ser obligatorio."""
        try:
            import firebirdsql  # noqa: PLC0415
        except ModuleNotFoundError as exc:  # pragma: no cover - depende del entorno
            raise FlexxusUnavailable(
                "El driver firebirdsql no esta instalado (extra 'flexxus')."
            ) from exc
        return firebirdsql

    def _conectar(self):
        if not self._password:
            raise FlexxusUnavailable("No hay credencial configurada para Flexxus.")
        try:
            return self._driver().connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self._password,
                charset=self.charset,
                timeout=self.timeout,
                readonly=True,
            )
        except Exception as exc:  # noqa: BLE001 - el ERP puede fallar de mil maneras
            raise FlexxusUnavailable(f"El ERP no respondio: {type(exc).__name__}") from exc

    # --- Introspeccion defensiva -------------------------------------

    @staticmethod
    def _tabla_existe(cursor, tabla: str) -> bool:
        cursor.execute(
            """
            select count(*)
            from rdb$relations
            where coalesce(rdb$system_flag, 0) = 0
              and trim(rdb$relation_name) = ?
            """,
            (tabla,),
        )
        return bool(cursor.fetchone()[0])

    @staticmethod
    def _columnas(cursor, tabla: str) -> set[str]:
        """Nombres de columna de una tabla. Vacio si la tabla no existe."""
        if not FlexxusClient._tabla_existe(cursor, tabla):
            return set()
        cursor.execute(
            """
            select trim(rf.rdb$field_name)
            from rdb$relation_fields rf
            where rf.rdb$relation_name = ?
            """,
            (tabla,),
        )
        return {row[0] for row in cursor.fetchall()}

    # --- Consultas ---------------------------------------------------

    def buscar_articulos(
        self,
        texto: str,
        limite: int = 20,
        precio_lista: int = 1,
    ) -> list[dict[str, Any]]:
        """Busca articulos por codigo o descripcion.

        Devuelve las filas normalizadas que pide el servicio. Si la base no
        tiene el catalogo, o no se puede leer, levanta ``FlexxusUnavailable``.
        """
        texto = (texto or "").strip()
        if not texto:
            return []

        conexion = self._conectar()
        try:
            cursor = conexion.cursor()
            if not self._tabla_existe(cursor, TABLA_ARTICULOS):
                raise FlexxusUnavailable(
                    f"La base {self.database} no tiene la tabla {TABLA_ARTICULOS}."
                )

            columnas_articulos = self._columnas(cursor, TABLA_ARTICULOS)
            columnas_stock = self._columnas(cursor, TABLA_STOCK)
            columnas_rubros = self._columnas(cursor, TABLA_RUBROS)
            columnas_marcas = self._columnas(cursor, TABLA_MARCAS)
            columnas_monedas = self._columnas(cursor, TABLA_MONEDAS)

            # La busqueda va con POSITION y no con LIKE: en Firebird 2.5 el
            # parametro de texto de `LIKE`/`CONTAINING` se corta a los 30
            # caracteres y revienta la consulta ("string right truncation").
            # POSITION no tiene ese corte.
            #
            # El filtro SQL es grueso (mayusculas y tildes por variantes). El
            # fino, con acentos, se hace en Python sobre las filas candidatas.
            terminos = _terminos(texto)
            if not terminos:
                return []

            seleccion = ["a.CODIGOARTICULO"]
            if "DESCRIPCION" in columnas_articulos:
                seleccion.append("a.DESCRIPCION")
            if "CODIGORUBRO" in columnas_articulos:
                seleccion.append("a.CODIGORUBRO")
            if "CODIGOMARCA" in columnas_articulos:
                seleccion.append("a.CODIGOMARCA")
            if "CODIGOMONEDA" in columnas_articulos:
                seleccion.append("a.CODIGOMONEDA")
            if "PRECIOCOMPRA" in columnas_articulos:
                seleccion.append("a.PRECIOCOMPRA")

            columna_precio = None
            for indice in range(1, 6):
                nombre = f"PRECIOVENTA{indice}"
                if nombre in columnas_articulos:
                    seleccion.append(f"a.{nombre}")
                    if indice == precio_lista:
                        columna_precio = nombre
            if "ACTIVO" in columnas_articulos:
                seleccion.append("a.ACTIVO")
            if "BLOQUEADO" in columnas_articulos:
                seleccion.append("a.BLOQUEADO")

            joins = []
            if columnas_stock and "CODIGOARTICULO" in columnas_stock:
                if "STOCKACTUAL" in columnas_stock:
                    seleccion.append("s.STOCKACTUAL")
                if "STOCKMINIMO" in columnas_stock:
                    seleccion.append("s.STOCKMINIMO")
                joins.append('left join "STOCK" s on s.CODIGOARTICULO = a.CODIGOARTICULO')
            if (
                columnas_rubros
                and "CODIGORUBRO" in columnas_rubros
                and "DESCRIPCION" in columnas_rubros
            ):
                # Alias propio: RUBROS y MARCAS tienen las dos DESCRIPCION.
                seleccion.append("r.DESCRIPCION as RUBRO_DESCRIPCION")
                joins.append('left join "RUBROS" r on r.CODIGORUBRO = a.CODIGORUBRO')
            if (
                columnas_marcas
                and "CODIGOMARCA" in columnas_marcas
                and "DESCRIPCION" in columnas_marcas
            ):
                seleccion.append("m.DESCRIPCION as MARCA_DESCRIPCION")
                joins.append('left join "MARCAS" m on m.CODIGOMARCA = a.CODIGOMARCA')

            filtros = []
            params: list[Any] = []
            for termino in terminos:
                ramas = []
                for variante in _variantes(termino):
                    # El `cast` no es cosmetico: sin el, Firebird infiere el
                    # tipo del parametro por el PRIMER uso (CODIGOARTICULO es
                    # VARCHAR(15)) y el mismo parametro, mas largo, se corta
                    # en el segundo uso con "string right truncation".
                    #
                    # El `upper()` va solo del lado de la columna: aplicarlo al
                    # parametro tambien hace que Firebird infiera un tipo
                    # corto. La aguja ya viene en mayusculas.
                    ramas.append(
                        "(position(cast(? as varchar(255)) in upper(a.CODIGOARTICULO)) > 0"
                        " or position(cast(? as varchar(255)) in upper(a.DESCRIPCION)) > 0)"
                    )
                    params.extend([variante, variante])
                filtros.append("(" + " or ".join(ramas) + ")")
            if "ACTIVO" in columnas_articulos:
                filtros.append("coalesce(a.ACTIVO, 1) = 1")
            if "BLOQUEADO" in columnas_articulos:
                filtros.append("coalesce(a.BLOQUEADO, 0) = 0")

            # Tope de filas traidas: el filtro fino con acentos va en Python.
            tope = min(max(limite * 6, 30), 300)

            def _consultar(where: str, parametros: tuple) -> list[dict[str, Any]]:
                cursor.execute(
                    f"select first {tope} "
                    + ", ".join(seleccion)
                    + ' from "ARTICULOS" a '
                    + " ".join(joins)
                    + where
                    + " order by a.DESCRIPCION",
                    parametros,
                )
                nombres = [d[0].strip().split(".")[-1] for d in cursor.description]
                return [dict(zip(nombres, row)) for row in cursor.fetchall()]

            def _coincide(fila: dict[str, Any]) -> bool:
                """Filtro fino en Python: mismo criterio que el SQL.

                Sin acentos y en mayusculas, con las mismas variantes con tilde
                que prueba el SQL: si no, el filtro de Python descartaria
                resultados que el ERP si devolvio.
                """
                codigo = _sin_acentos(str(fila.get("CODIGOARTICULO") or "")).upper()
                descripcion = _sin_acentos(str(fila.get("DESCRIPCION") or "")).upper()
                for termino in terminos:
                    variantes = [termino] + [
                        v for v in _variantes(termino) if v != termino
                    ]
                    if not any(
                        v in codigo or v in descripcion for v in variantes
                    ):
                        return False
                return True

            crudas = _consultar(" where " + " and ".join(filtros), tuple(params))
            coincidencias = [fila for fila in crudas if _coincide(fila)]

            if not coincidencias:
                # El SQL trae filas que el filtro fino descarta (pasa con
                # acentos en medio de palabra). Se reintenta sin filtro de
                # texto para no perder resultados legitimos. Sin acentos ni
                # mayusculas: el filtro fino vuelve a decidir.
                todas = _consultar("", ())
                coincidencias = [fila for fila in todas if _coincide(fila)]

            cambios = self._cambios_moneda(cursor, columnas_monedas)
            return [
                self._normalizar(fila, columna_precio, cambios)
                for fila in coincidencias[:limite]
            ]
        except FlexxusUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            raise FlexxusUnavailable(
                f"No se pudo leer el catalogo: {type(exc).__name__}"
            ) from exc
        finally:
            try:
                conexion.close()
            except Exception:  # noqa: BLE001
                pass

    def obtener_articulo(
        self, codigo: str, precio_lista: int = 1
    ) -> dict[str, Any] | None:
        """Un articulo por codigo, o None si no existe."""
        codigo = (codigo or "").strip()
        if not codigo:
            return None
        resultados = self.buscar_articulos(codigo, limite=5, precio_lista=precio_lista)
        for fila in resultados:
            if str(fila.get("code") or "") == codigo:
                return fila
        return resultados[0] if resultados else None

    # --- Normalizacion ------------------------------------------------

    def _cambios_moneda(self, cursor, columnas_monedas: set[str]) -> dict[str, float]:
        """Cambio de cada moneda contra la moneda base. Vacio si no hay MONEDAS."""
        if (
            not columnas_monedas
            or "CAMBIO" not in columnas_monedas
            or "CODIGOMONEDA" not in columnas_monedas
        ):
            return {}
        try:
            cursor.execute(
                'select trim(CODIGOMONEDA), CAMBIO from "MONEDAS" where CAMBIO is not null'
            )
            return {str(row[0]).upper(): float(row[1]) for row in cursor.fetchall()}
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("No se pudieron leer los cambios de moneda: %s", exc)
            return {}

    @staticmethod
    def _numero(valor: Any) -> float | None:
        if valor is None:
            return None
        try:
            return float(valor)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _texto(valor: Any) -> str:
        """Texto limpio: el ERP tiene descripciones con saltos de linea."""
        if valor is None:
            return ""
        return " ".join(str(valor).split()).strip()

    def _normalizar(
        self,
        fila: dict[str, Any],
        columna_precio: str | None,
        cambios: dict[str, float],
    ) -> dict[str, Any]:
        """Convierte una fila cruda del ERP en la forma que consume el servicio."""
        moneda = str(fila.get("CODIGOMONEDA") or "").upper() or None
        cambio = cambios.get(moneda or "", 1.0) if moneda else 1.0

        costo = self._numero(fila.get("PRECIOCOMPRA"))
        precio_venta = self._numero(fila.get(columna_precio)) if columna_precio else None

        # El ERP guarda el precio en la moneda del articulo (PESOS o DOLARES).
        # El sistema trabaja en pesos: se convierte con el cambio del ERP.
        costo_pesos = costo * cambio if costo is not None else None
        precio_pesos = precio_venta * cambio if precio_venta is not None else None

        return {
            "code": self._texto(fila.get("CODIGOARTICULO")),
            "description": self._texto(fila.get("DESCRIPCION")),
            "rubro_code": self._texto(fila.get("CODIGORUBRO")) or None,
            "rubro": self._texto(fila.get("RUBRO_DESCRIPCION")) or None,
            "marca_code": self._texto(fila.get("CODIGOMARCA")) or None,
            "marca": self._texto(fila.get("MARCA_DESCRIPCION")) or None,
            "stock": self._numero(fila.get("STOCKACTUAL")),
            "stock_minimo": self._numero(fila.get("STOCKMINIMO")),
            "cost": costo_pesos,
            "cost_currency": "ARS",
            "cost_source_currency": moneda,
            "sale_price": precio_pesos,
            "sale_price_currency": "ARS",
            "price_source": f"flexxus:{columna_precio}" if columna_precio else None,
            "price_synced_at": dt.datetime.now(dt.timezone.utc),
        }
