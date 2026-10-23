"""Lectura del legacy: la base real de CiberBase (SQL Server).

El importador **no** lee los TSV de ``backup/_work/csv``: esos son el snapshot
auditable del export, utiles para cuadrar, pero la verdad es la base. Esta capa
habla con el SQL Server por TCP (``pymssql``) y trae los datos con los tipos
nativos del driver (``datetime``, ``Decimal``, ``int``).

Las consultas son las que ya estan escritas y verificadas en ``backup/_work/sql``:
mismos joins, mismo corte y mismo orden de columnas. Lo unico que se les cambia es
que dejan de castear todo a ``VARCHAR`` (para que el driver traiga los tipos
nativos) y que se les agrega el filtro de filas vacias.

Que el destino no cambie al cambiar el origen es parte del contrato: los pasos y los
mappers works con la misma semantica de parseo que tenian con los TSV:

- un ``NULL`` del SQL Server es un valor ausente (no la cadena ``'NULL'``),
- los importes son ``Decimal``, nunca ``float`` (el cierre mensual compara sumas y
  con punto flotante aparecen los centavos),
- la fecha ceros del legacy (``1900-01-01``) significa "sin liquidar",
- los textos que exceden el ancho de la columna del destino se recortan.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterator, Sequence

#: Cuantas filas se traen del driver por vuelta. El lado de Python nunca tiene las
#: 83.000 facturas en memoria.
TAMANO_LOTE = 1000

#: Corte del legacy: el alcance acordado es desde 2020.
CORTE_POR_DEFECTO = "20200101"

#: Variable de entorno con la password del SQL Server. **Nunca** va en el codigo ni
#: en un archivo del repo.
ENV_PASSWORD = "CB_SQLSERVER_PASSWORD"
ENV_HOST = "CB_SQLSERVER_HOST"
ENV_PUERTO = "CB_SQLSERVER_PORT"
ENV_USUARIO = "CB_SQLSERVER_USER"
ENV_BASE = "CB_SQLSERVER_DB"


class ErrorDeConexion(RuntimeError):
    """No se pudo leer el legacy: el mensaje dice que falta."""


@dataclass(frozen=True)
class Configuracion:
    """Como conectarse al legacy. Todo por entorno, menos la password, que es obligatoria."""

    host: str = "localhost"
    puerto: int = 1433
    usuario: str = "sa"
    password: str = ""
    base: str = "CiberBase"

    @classmethod
    def desde_entorno(cls) -> "Configuracion":
        """Arma la configuracion desde las variables de entorno.

        La password es obligatoria: si no esta, el error lo dice claro en vez de
        intentar conectar con una password vacia.
        """
        password = os.getenv(ENV_PASSWORD, "")
        if not password:
            raise ErrorDeConexion(
                f"Falta la variable de entorno {ENV_PASSWORD}.\n"
                "La password del SQL Server no va en el codigo: se pasa por entorno.\n"
                f"  $env:{ENV_PASSWORD}='...'"
            )
        puerto = os.getenv(ENV_PUERTO, "").strip()
        return cls(
            host=os.getenv(ENV_HOST, "").strip() or "localhost",
            puerto=int(puerto) if puerto else 1433,
            usuario=os.getenv(ENV_USUARIO, "").strip() or "sa",
            password=password,
            base=os.getenv(ENV_BASE, "").strip() or "CiberBase",
        )


# ---------------------------------------------------------------------------
# Consultas (adaptadas de backup/_work/sql/*.sql)
# ---------------------------------------------------------------------------

#: Politicas del legacy: las dos capas juntas (``Areas`` + ``TiposTrabajos`` +
#: ``Aux_PoliticasxArea``) a traves de la vista ``CS_PoliticasxArea``.
SQL_AREAS = """
SELECT
    P.ID,
    P.IDArea,
    P.Area,
    CASE WHEN P.Ppal = 1 THEN '' ELSE ISNULL(P.Codigo, '') END AS policy_code,
    CASE WHEN P.Ppal = 1 THEN '' ELSE ISNULL(P.Nombre, '') END AS policy_description,
    ISNULL(P.CodCli, 0) AS billing_codcli,
    ISNULL(P.Empresa, '') AS brand_name,
    P.Garantia,
    P.Liquidar,
    P.Utilidad,
    P.ComisionProd,
    P.MontoComisionProd,
    P.ComisionRep,
    P.MontoComisionRep,
    P.ComisionServ,
    P.MontoComisionServ,
    P.ComisionOtro,
    P.MontoComisionOtro
FROM dbo.CS_PoliticasxArea P
ORDER BY P.IDArea, P.Ppal DESC
"""

#: Clientes del legacy + el CUIT mas frecuente de sus facturas.
#:
#: El CUIT solo se toma si tiene 11 digitos: en la base hay placeholders como
#: ``100000`` (6 digitos) y ``11111111`` (8) que no son CUIT.
SQL_CLIENTES = """
WITH cuit AS (
    SELECT F.CodCli,
           F.CUIT,
           ROW_NUMBER() OVER (PARTITION BY F.CodCli ORDER BY COUNT(*) DESC, F.CUIT) AS rn
    FROM dbo.CG_Facturas_Tabla F
    WHERE LEN(F.CUIT) = 11 AND F.CUIT NOT LIKE '%[^0-9]%'
    GROUP BY F.CodCli, F.CUIT
)
SELECT
    C.CodCli,
    C.Cliente,
    C.Telefonos,
    C.Email,
    C.Vendedor,
    C.Tipo,
    ISNULL(C.Calle, N'') + N' ' + ISNULL(CAST(C.Altura AS VARCHAR(20)), N'') + N', ' +
    ISNULL(C.Localidad, N'') + N' (' + ISNULL(C.CodigoPostal, N'') + N')' +
    CASE WHEN ISNULL(C.Partido, N'') <> N'' THEN N' - ' + C.Partido ELSE N'' END,
    C.NuestroCodigo,
    C.Liquidar,
    CU.CUIT
FROM dbo.CC_Clientes_Tabla C
LEFT JOIN cuit CU ON CU.CodCli = C.CodCli AND CU.rn = 1
ORDER BY C.CodCli
"""

#: Usuarios del legacy con sus tareas (1=Facturista, 2=Vendedor, 3=Tecnico, ...).
SQL_USUARIOS = """
SELECT
    U.Codigo,
    U.Nombre,
    U.EMail,
    U.Descripcion,
    MAX(CASE WHEN T.Tarea = N'Tecnico' THEN 1 ELSE 0 END),
    MAX(CASE WHEN T.Tarea = N'Vendedor' THEN 1 ELSE 0 END),
    MAX(CASE WHEN T.Tarea = N'Facturista' THEN 1 ELSE 0 END)
FROM dbo.CC_Usuarios U
LEFT JOIN dbo.CC_TareasxUsuario TU ON TU.Usuario = U.Codigo
LEFT JOIN dbo.CC_Tareas T ON T.ID = TU.Tarea
GROUP BY U.Codigo, U.Nombre, U.EMail, U.Descripcion
ORDER BY U.Codigo
"""

#: Ordenes de trabajo del corte. El corte es por ``FechaAlta``.
#:
#: ``Usuario`` va al final a proposito: es el nombre (texto libre) de quien abrio la
#: OT en el legacy. ``Responsable`` es el codigo del ``CC_Usuarios`` que recibio el
#: equipo. Los dos se usan para resolver ``received_by_user_id``.
SQL_ORDENES = """
SELECT
    T.IDTrabajo,
    T.NumeroOrden,
    T.CodCli,
    T.NroSerie,
    T.Equipo,
    T.Modelo,
    T.Cliente,
    T.Falla,
    T.Estado,
    T.FechaAlta,
    T.FechaOrden,
    T.FechaLista,
    T.FechaCerrada,
    T.Responsable,
    T.IDPolitica,
    T.CostoTotal,
    T.VentaTotal,
    ISNULL(T.TotalPresupuesto, 0),
    T.Ubicacion,
    T.Comprobante,
    T.FacturaEmitida,
    T.TrabajoRealizado,
    ISNULL(T.Liquidada, 0),
    T.Garantia,
    T.LiquidacionNro,
    T.Usuario
FROM dbo.CS_Trabajos T
WHERE T.FechaAlta >= %(corte)s
ORDER BY T.IDTrabajo
"""

#: Snapshot de cliente que el legacy copio a la OT.
#:
#: El 64 % de las OTs del corte no tienen ``CodCli`` (5.969 de 9.316), pero la OT
#: trae una **copia** del cliente: nombre, documento, telefono, email y direccion.
#: Esa copia es la que se usa para armar el cliente (decision D1 del brief).
#:
#: ``NroDocumento`` **no** es un documento confiable (D4 del brief): de los 1.360
#: documentos distintos hay 1.308 de 10 caracteres (DNI), 6 de 11 (CUIT), 30 de 8 y
#: several de 6, 7, 9, 13, 15, 16 y 17. Por eso no se usa como ``document``.
SQL_ORDENES_SIN_CLIENTE = """
SELECT
    T.Cliente,
    T.NroDocumento,
    T.Telefonos,
    T.EMail,
    ISNULL(T.Calle, N'') + N' ' + ISNULL(CAST(T.Altura AS VARCHAR(20)), N'') + N', ' +
    ISNULL(T.Localidad, N'') + N' (' + ISNULL(T.CodigoPostal, N'') + N')' +
    CASE WHEN ISNULL(T.Partido, N'') <> N'' THEN N' - ' + T.Partido ELSE N'' END,
    T.CodCli
FROM dbo.CS_Trabajos T
WHERE T.FechaAlta >= %(corte)s AND ISNULL(T.CodCli, 0) = 0
ORDER BY T.IDTrabajo
"""

#: Lineas de las OTs del corte.
SQL_LINEAS = """
SELECT
    P.NroOrden,
    P.Item,
    P.NumeroParte,
    P.Cantidad,
    P.Descripcion,
    P.CostoUnitario,
    P.Unitario,
    P.Tipo,
    ISNULL(P.LiquidaComision, 0),
    P.Cotizacion,
    P.CotizacionCosto,
    P.Provee,
    P.ID
FROM dbo.CS_Partes P
INNER JOIN dbo.CS_Trabajos T ON T.IDTrabajo = P.NroOrden
WHERE T.FechaAlta >= %(corte)s
ORDER BY P.NroOrden, P.Item
"""

#: Quien intervino en las OTs del corte y cuanto se le comisiona (importes ya
#: calculados por el legacy: no se recalculan).
SQL_INTERVENCIONES = """
SELECT
    I.Orden,
    I.Persona,
    ISNULL(I.ComisionProductos, 0),
    ISNULL(I.ComisionPartes, 0),
    ISNULL(I.ComisionServicios, 0),
    ISNULL(I.ComisionOtros, 0),
    I.Liquidacion,
    I.FechaLiquidacionTecnico,
    I.NroFactura
FROM dbo.Intervienen I
INNER JOIN dbo.CS_Trabajos T ON T.IDTrabajo = I.Orden
WHERE T.FechaAlta >= %(corte)s
ORDER BY I.Orden, I.Persona
"""

#: Comision por linea (legacy ``dbo.CS_ComisionPartexInterviene``).
SQL_COMISIONES_LINEA = """
SELECT
    C.ID,
    C.IDUsuario,
    ISNULL(C.Comision, 0)
FROM dbo.CS_ComisionPartexInterviene C
INNER JOIN dbo.CS_Partes P ON P.ID = C.ID
INNER JOIN dbo.CS_Trabajos T ON T.IDTrabajo = P.NroOrden
WHERE T.FechaAlta >= %(corte)s
ORDER BY C.ID, C.IDUsuario
"""

#: Facturas del legacy que **una OT reclama**.
#:
#: El vinculo no existe como tabla puente: la OT guarda el numero de factura en
#: ``CS_Trabajos.FacturaEmitida``. El export original lo resolvia con un subquery
#: correlacionado por factura (``MIN(T.IDTrabajo)``); aca se resuelve con un
#: ``LEFT JOIN`` agrupado, que es lo mismo pero no recorre la tabla 83.164 veces.
#:
#: **El filtro es explicito**: entra la factura que una OT reclama (``HAVING
#: MIN(T.IDTrabajo) IS NOT NULL``). Las 83.164 - 1.962 restantes son facturacion de
#: mostrador, que no tiene OT y no entra en este corte.
SQL_FACTURAS = """
SELECT
    F.ID,
    F.Numero,
    F.TipoDoc,
    F.CodCli,
    F.Cliente,
    F.Fecha,
    F.Vencimiento,
    F.Bruto,
    F.Neto,
    F.Total,
    F.CUIT,
    F.Vendedor,
    F.RealizadoPor,
    F.Anulado,
    F.CAI,
    MIN(T.IDTrabajo) AS id_trabajo
FROM dbo.CG_Facturas_Tabla F
LEFT JOIN dbo.CS_Trabajos T ON T.FacturaEmitida = F.Numero
GROUP BY F.ID, F.Numero, F.TipoDoc, F.CodCli, F.Cliente, F.Fecha, F.Vencimiento,
         F.Bruto, F.Neto, F.Total, F.CUIT, F.Vendedor, F.RealizadoPor, F.Anulado, F.CAI
HAVING MIN(T.IDTrabajo) IS NOT NULL
"""

#: Frecuencia de los textos de equipo del corte: del ahi sale el catalogo curado.
SQL_FRECUENCIAS_EQUIPO = """
SELECT T.Equipo, COUNT(*)
FROM dbo.CS_Trabajos T
WHERE T.FechaAlta >= %(corte)s
GROUP BY T.Equipo
"""

#: Ubicaciones distintas del corte: del ahi sale el maestro de mesas.
SQL_UBICACIONES = """
SELECT DISTINCT T.Ubicacion
FROM dbo.CS_Trabajos T
WHERE T.FechaAlta >= %(corte)s
  AND T.Ubicacion IS NOT NULL
  AND LTRIM(RTRIM(T.Ubicacion)) <> N''
"""

#: Suma de las comisiones por linea del corte (para el importe de la linea).
SQL_COMISIONES_POR_LINEA = """
SELECT C.ID, SUM(ISNULL(C.Comision, 0))
FROM dbo.CS_ComisionPartexInterviene C
INNER JOIN dbo.CS_Partes P ON P.ID = C.ID
INNER JOIN dbo.CS_Trabajos T ON T.IDTrabajo = P.NroOrden
WHERE T.FechaAlta >= %(corte)s
GROUP BY C.ID
"""


class FuenteCiberBase:
    """Lectura del legacy. Se abre, se leen los datos y se cierra."""

    def __init__(self, config: Configuracion, corte: str = CORTE_POR_DEFECTO) -> None:
        self.config = config
        self.corte = corte
        self._conexion = None

    # -- conexion ---------------------------------------------------------
    def abrir(self) -> "FuenteCiberBase":
        """Abre la conexion. Si falla, el error dice por que."""
        if not self.config.password:
            raise ErrorDeConexion(
                f"Falta la variable de entorno {ENV_PASSWORD}: la password del SQL "
                "Server es obligatoria y no va en el codigo."
            )
        try:
            import pymssql
        except ImportError as error:  # pragma: no cover - depende del entorno
            raise ErrorDeConexion(
                "Falta pymssql, que es el driver del legacy (SQL Server).\n"
                "Se instala con el extra del backend:  pip install -e '.[import]'"
            ) from error
        try:
            self._conexion = pymssql.connect(
                server=self.config.host,
                port=self.config.puerto,
                user=self.config.usuario,
                password=self.config.password,
                database=self.config.base,
                login_timeout=20,
                timeout=300,
                autocommit=True,
            )
        except Exception as error:  # noqa: BLE001 - el mensaje es lo que importa
            raise ErrorDeConexion(
                f"No se pudo conectar al legacy {self.config.base} en "
                f"{self.config.host}:{self.config.puerto} como '{self.config.usuario}': "
                f"{error}"
            ) from error
        return self

    def cerrar(self) -> None:
        """Cierra la conexion."""
        if self._conexion is not None:
            self._conexion.close()
            self._conexion = None

    def __enter__(self) -> "FuenteCiberBase":
        return self.abrir()

    def __exit__(self, *_excepcion) -> None:
        self.cerrar()

    # -- consultas --------------------------------------------------------
    def consultar(
        self, sql: str, parametros: dict[str, Any] | None = None
    ) -> Iterator[tuple]:
        """Ejecuta una consulta y la devuelve por lotes.

        El driver no trae todo el resultado en memoria de una: se pide de a
        ``TAMANO_LOTE`` filas.
        """
        if self._conexion is None:
            raise ErrorDeConexion("La conexion al legacy no esta abierta.")
        cursor = self._conexion.cursor()
        try:
            if parametros:
                cursor.execute(sql, parametros)
            else:
                cursor.execute(sql)
            while True:
                filas = cursor.fetchmany(TAMANO_LOTE)
                if not filas:
                    break
                for fila in filas:
                    yield fila
        finally:
            cursor.close()

    # -- lecturas ---------------------------------------------------------
    def areas(self) -> Iterator[tuple]:
        """Politicas del legacy (126 filas)."""
        return self.consultar(SQL_AREAS)

    def clientes(self) -> Iterator[tuple]:
        """Clientes del legacy (14.730 filas)."""
        return self.consultar(SQL_CLIENTES)

    def usuarios(self) -> Iterator[tuple]:
        """Usuarios del legacy con sus tareas (44 filas)."""
        return self.consultar(SQL_USUARIOS)

    def ordenes(self) -> Iterator[tuple]:
        """Ordenes de trabajo del corte (9.316 filas)."""
        return self.consultar(SQL_ORDENES, {"corte": self.corte})

    def ordenes_sin_cliente(self) -> Iterator[tuple]:
        """Snapshot de cliente de las OTs sin ``CodCli`` (5.969 filas).

        Es la copia del cliente que el legacy copio a la OT: de ahi se deducen los
        clientes que no estan en ``CC_Clientes_Tabla``.
        """
        return self.consultar(SQL_ORDENES_SIN_CLIENTE, {"corte": self.corte})

    def lineas(self) -> Iterator[tuple]:
        """Lineas de las OTs del corte (29.799 filas)."""
        return self.consultar(SQL_LINEAS, {"corte": self.corte})

    def intervenciones(self) -> Iterator[tuple]:
        """Intervenciones del corte (18.383 filas)."""
        return self.consultar(SQL_INTERVENCIONES, {"corte": self.corte})

    def comisiones_linea(self) -> Iterator[tuple]:
        """Comisiones por linea del corte (10.509 filas)."""
        return self.consultar(SQL_COMISIONES_LINEA, {"corte": self.corte})

    def facturas(self) -> Iterator[tuple]:
        """Facturas del corte que una OT reclama (1.962 filas)."""
        return self.consultar(SQL_FACTURAS)

    def frecuencias_equipo(self) -> list[tuple[str, int]]:
        """Frecuencia de cada texto de equipo del corte (2.588 filas)."""
        return [
            (texto(equipo), int(cantidad))
            for equipo, cantidad in self.consultar(SQL_FRECUENCIAS_EQUIPO, {"corte": self.corte})
        ]

    def ubicaciones(self) -> list[str]:
        """Textos de ubicacion distintos del corte."""
        return [texto(valor) for valor in self.consultar(SQL_UBICACIONES, {"corte": self.corte})]

    def comisiones_por_linea(self) -> dict[str, Decimal]:
        """Suma de las comisiones de cada linea del corte."""
        return {
            str(identificador): Decimal(cantidad)
            for identificador, cantidad in self.consultar(
                SQL_COMISIONES_POR_LINEA, {"corte": self.corte}
            )
        }


# ---------------------------------------------------------------------------
# Semantica de parseo (la misma que usaba el export a TSV)
# ---------------------------------------------------------------------------

#: Cuantos valores hubo que recortar por exceder el ancho de la columna del destino.
RECORTADOS: dict[str, int] = {}


def texto(valor: Any) -> str:
    """Texto limpio del legacy.

    Viene de varias columnas y tipos: se pasan por el mismo filtro que el export
    (sin CR, sin LF, sin ``|``) para que un texto con saltos de linea no rompa la
    pantalla. Un ``NULL`` es texto vacio.
    """
    if valor is None:
        return ""
    if isinstance(valor, str):
        limpio = valor
    elif isinstance(valor, Decimal):
        limpio = str(valor)
    else:
        limpio = str(valor)
    limpio = limpio.replace("\r", " ").replace("\n", " ").replace("|", " ")
    limpio = " ".join(limpio.split())
    if limpio.upper() == "NULL":
        return ""
    return limpio


def entero(valor: Any, por_defecto: int | None = None) -> int | None:
    """Convierte a ``int``. Devuelve ``por_defecto`` si no hay numero."""
    if valor is None:
        return por_defecto
    if isinstance(valor, bool):
        return int(valor)
    if isinstance(valor, int):
        return valor
    limpio = texto(valor)
    if limpio == "":
        return por_defecto
    try:
        return int(limpio)
    except ValueError:
        return por_defecto


def decimal(valor: Any, por_defecto: Decimal = Decimal("0")) -> Decimal | None:
    """Convierte a ``Decimal``. Un importe no numerico (o ``NULL``) vale 0.

    Se usa ``Decimal`` y no ``float`` porque el cierre mensual compara suma de costos
    contra el legacy: con punto flotante la diferencia aparece en los centavos.
    """
    if valor is None:
        return por_defecto
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, bool):
        return Decimal(int(valor))
    if isinstance(valor, int):
        return Decimal(valor)
    if isinstance(valor, float):
        return Decimal(str(valor))
    limpio = texto(valor)
    if limpio == "":
        return por_defecto
    try:
        return Decimal(limpio)
    except InvalidOperation:
        return por_defecto


def fecha(valor: Any) -> datetime | None:
    """Fecha del legacy (``datetime`` del driver) o ``None``."""
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor
    limpio = texto(valor)
    if limpio == "":
        return None
    for formato in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(limpio, formato)
        except ValueError:
            continue
    return None


def fecha_o_umbral(valor: Any) -> datetime | None:
    """Como :func:`fecha`, pero descarta la fecha ceros del legacy (1900-01-01).

    El legacy usa ``1900-01-01`` como "sin liquidar": en el destino queda NULL.
    """
    resultado = fecha(valor)
    if resultado is None:
        return None
    if resultado.year <= 1900:
        return None
    return resultado


def recortar(etiqueta: str, valor: Any, largo: int) -> str | None:
    """Recorta un texto al ancho de la columna del destino.

    El legacy no tiene limites de ancho y el destino si: hay telefonos de 64
    caracteres y la columna de clientes tiene 60. Se recorta (se pierde la cola del
    texto) y se cuenta, para que el cuadre diga que paso.
    """
    limpio = texto(valor)
    if len(limpio) <= largo:
        return limpio or None
    RECORTADOS[etiqueta] = RECORTADOS.get(etiqueta, 0) + 1
    return limpio[:largo]
