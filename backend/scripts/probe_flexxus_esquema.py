"""Probe read-only del esquema de Flexxus (Firebird, puerto 3050).

Cierra el spike de #114 antes de escribir el servicio de repuestos: descubre
en que tabla o columna vive el PRECIO DE VENTA de un articulo, en vez de
asumirlo.

Restricciones (ver docs/plan-repuestos-flexxus.md):

- Solo lectura. La conexion se abre con ``readonly=True`` y todas las
  consultas son SELECT. Nunca se escribe en el ERP.
- La base es la ruta del ``.gdb`` vista DESDE EL SERVIDOR Firebird
  (p. ej. ``C:\\FLEXXUS\\DB\\ETR\\DB-ETR.gdb``), no una ruta local.
- La contraseña sale de la variable de entorno ``FLEXXUS_PASSWORD`` y no se
  imprime nunca en la salida ni en los logs.

Uso:

    $env:FLEXXUS_PASSWORD = "<clave>"
    .\\.venv\\Scripts\\python.exe scripts\\probe_flexxus_esquema.py
    .\\.venv\\Scripts\\python.exe scripts\\probe_flexxus_esquema.py --salida ..\\docs\\spike-esquema-flexxus.md
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from typing import Any

try:
    import firebirdsql
except ModuleNotFoundError:  # pragma: no cover - depende del entorno
    print(
        "Falta el driver firebirdsql. Instalalo con:\n"
        "    .\\.venv\\Scripts\\python.exe -m pip install -e .[flexxus]",
        file=sys.stderr,
    )
    raise SystemExit(2)


HOST = os.environ.get("FLEXXUS_HOST", "suevos.ddns.net")
PORT = int(os.environ.get("FLEXXUS_PORT", "3050"))
USER = os.environ.get("FLEXXUS_USER", "ELECTROTR")
PASSWORD_ENV = "FLEXXUS_PASSWORD"
CHARSET = os.environ.get("FLEXXUS_CHARSET", "ISO8859_1")
TIMEOUT = float(os.environ.get("FLEXXUS_TIMEOUT", "10"))

# Rutas vista desde el servidor Firebird (mismo criterio que dashboard_suevos).
DEFAULT_DATABASES = (
    r"C:\FLEXXUS\DB\ETR\DB-ETR.gdb",
    r"C:\FLEXXUS\DB\ETR\DB-MLT-ETR.gdb",
)

# Tablas del catalogo que el modulo de repuestos necesita.
CATALOG_TABLES = (
    "ARTICULOS",
    "STOCK",
    "RUBROS",
    "MARCAS",
    "MONEDAS",
)

# Palabras que delatan una candidata de precio.
PRICE_HINTS = ("PRECIO", "LISTA", "TARIFA", "VALOR")

SAMPLE_ROWS = 3


def password() -> str:
    value = os.environ.get(PASSWORD_ENV)
    if not value:
        raise RuntimeError(f"Falta definir la variable de entorno {PASSWORD_ENV}.")
    return value


def connect(database: str):
    """Abre una conexion de solo lectura contra el ERP."""
    return firebirdsql.connect(
        host=HOST,
        port=PORT,
        database=database,
        user=USER,
        password=password(),
        charset=CHARSET,
        timeout=TIMEOUT,
        readonly=True,
    )


def user_tables(cursor) -> list[str]:
    cursor.execute(
        """
        select trim(rdb$relation_name)
        from rdb$relations
        where coalesce(rdb$system_flag, 0) = 0
          and rdb$view_blr is null
        order by 1
        """
    )
    return [row[0] for row in cursor.fetchall()]


def table_exists(cursor, table: str) -> bool:
    cursor.execute(
        """
        select count(*)
        from rdb$relations
        where coalesce(rdb$system_flag, 0) = 0
          and trim(rdb$relation_name) = ?
        """,
        (table,),
    )
    return bool(cursor.fetchone()[0])


def columns_of(cursor, table: str) -> list[tuple[str, str]]:
    """Devuelve (nombre, tipo) de las columnas de una tabla.

    Ojo con el nombre de la columna: ``rdb$fields.rdb$field_name`` es el
    DOMINIO (CADENA15, DOBLE, ...), no la columna. El nombre real de la
    columna vive en ``rdb$relation_fields.rdb$field_name``; el vinculo con
    ``rdb$fields`` es por ``rdb$field_source`` -> ``rdb$fields.rdb$field_name``.
    """
    cursor.execute(
        """
        select trim(rf.rdb$field_name), coalesce(t.rdb$type_name, '?')
        from rdb$relation_fields rf
        join rdb$fields f on f.rdb$field_name = rf.rdb$field_source
        left join rdb$types t
          on t.rdb$type = f.rdb$field_type
         and t.rdb$field_name = 'RDB$FIELD_TYPE'
        where rf.rdb$relation_name = ?
        order by rf.rdb$field_position
        """,
        (table,),
    )
    return [(row[0], row[1]) for row in cursor.fetchall()]


def price_columns_schema(cursor) -> list[tuple[str, str, str]]:
    """Toda columna del esquema cuyo nombre huele a precio, en una sola consulta.

    Devuelve (tabla, columna, tipo). Evita una consulta por tabla: el esquema
    de DB-ETR tiene 671 tablas.
    """
    cursor.execute(
        """
        select trim(rf.rdb$relation_name), trim(rf.rdb$field_name),
               coalesce(t.rdb$type_name, '?')
        from rdb$relation_fields rf
        join rdb$fields f on f.rdb$field_name = rf.rdb$field_source
        left join rdb$types t
          on t.rdb$type = f.rdb$field_type
         and t.rdb$field_name = 'RDB$FIELD_TYPE'
        where rf.rdb$field_name containing 'PRECIO'
           or rf.rdb$field_name containing 'LISTA'
           or rf.rdb$field_name containing 'TARIFA'
           or rf.rdb$field_name containing 'VALOR'
        order by 1, 2
        """
    )
    return [(row[0], row[1], row[2]) for row in cursor.fetchall()]


def count_rows(cursor, table: str) -> int:
    cursor.execute(f'select count(*) from "{table}"')
    return int(cursor.fetchone()[0] or 0)


def sample_rows(cursor, table: str, limit: int = SAMPLE_ROWS) -> list[dict[str, Any]]:
    cursor.execute(f'select first {int(limit)} * from "{table}"')
    names = [desc[0].strip() for desc in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _render_value(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, (bytes, bytearray)):
        return value.decode("latin-1", errors="replace")
    text = str(value)
    return text.replace("\r", " ").replace("\n", " ").replace("|", "/")


def _render_table(rows: list[dict[str, Any]], max_columns: int = 14) -> list[str]:
    if not rows:
        return ["_(sin filas)_"]
    names = list(rows[0].keys())[:max_columns]
    lines = ["| " + " | ".join(names) + " |", "|" + "|".join(["---"] * len(names)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(_render_value(row.get(name)) for name in names) + " |")
    if len(rows[0]) > max_columns:
        lines.append(f"_({len(rows[0]) - max_columns} columnas mas no mostradas)_")
    return lines


def probe_database(database: str) -> list[str]:
    """Devuelve el informe del probe para una base, en markdown."""
    out: list[str] = []
    out.append(f"## Base `{database}`")
    out.append("")

    try:
        connection = connect(database)
    except Exception as exc:
        out.append(f"**NO SE PUDO CONECTAR**: `{type(exc).__name__}: {exc}`")
        out.append("")
        return out

    try:
        cursor = connection.cursor()
        cursor.execute("select current_timestamp from rdb$database")
        server_ts = cursor.fetchone()[0]
        tables = user_tables(cursor)
        out.append(f"- Conexion: **OK** (readonly=True), timestamp del servidor: `{server_ts}`")
        out.append(f"- Host: `{HOST}:{PORT}` | usuario: `{USER}` | charset: `{CHARSET}`")
        out.append(f"- Tablas de usuario: **{len(tables)}**")
        out.append("")

        # --- 1. Tablas del catalogo ---
        out.append("### 1. Tablas del catalogo")
        out.append("")
        out.append("| Tabla | Existe | Filas |")
        out.append("|---|---|---|")
        for table in CATALOG_TABLES:
            exists = table_exists(cursor, table)
            rows = count_rows(cursor, table) if exists else 0
            out.append(f"| `{table}` | {'si' if exists else 'NO'} | {rows} |")
        out.append("")

        # --- 2. Columnas de ARTICULOS ---
        out.append("### 2. Columnas de `ARTICULOS`")
        out.append("")
        if table_exists(cursor, "ARTICULOS"):
            art_columns = columns_of(cursor, "ARTICULOS")
            out.append(f"Total de columnas: **{len(art_columns)}**")
            out.append("")
            out.append("| # | Columna | Tipo |")
            out.append("|---|---|---|")
            for index, (name, col_type) in enumerate(art_columns, start=1):
                out.append(f"| {index} | `{name}` | {col_type} |")
            out.append("")
            out.append("#### Muestra de `ARTICULOS`")
            out.append("")
            out.extend(_render_table(sample_rows(cursor, "ARTICULOS")))
            out.append("")
        else:
            out.append("`ARTICULOS` no existe en esta base.")
            out.append("")

        # --- 3. Columnas de STOCK ---
        out.append("### 3. Columnas de `STOCK`")
        out.append("")
        if table_exists(cursor, "STOCK"):
            stock_columns = columns_of(cursor, "STOCK")
            out.append("| # | Columna | Tipo |")
            out.append("|---|---|---|")
            for index, (name, col_type) in enumerate(stock_columns, start=1):
                out.append(f"| {index} | `{name}` | {col_type} |")
            out.append("")
        else:
            out.append("`STOCK` no existe en esta base.")
            out.append("")

        # --- 4. Candidatas de precio por nombre de TABLA ---
        out.append("### 4. Tablas candidatas de precio (nombre contiene PRECIO / LISTA / TARIFA / VALOR)")
        out.append("")
        candidates = [
            table for table in tables if any(hint in table.upper() for hint in PRICE_HINTS)
        ]
        if not candidates:
            out.append("Ninguna. No hay tabla de listas/tarifas en esta base.")
            out.append("")
        else:
            for table in candidates:
                out.append(f"#### `{table}`")
                out.append("")
                table_columns = columns_of(cursor, table)
                out.append("Columnas: " + ", ".join(f"`{name}` ({col_type})" for name, col_type in table_columns))
                out.append("")
                out.extend(_render_table(sample_rows(cursor, table)))
                out.append("")

        # --- 5. Candidatas de precio por nombre de COLUMNA en ARTICULOS ---
        out.append("### 5. Columnas de precio dentro de `ARTICULOS`")
        out.append("")
        if table_exists(cursor, "ARTICULOS"):
            price_columns = [
                (name, col_type)
                for name, col_type in columns_of(cursor, "ARTICULOS")
                if any(hint in name.upper() for hint in PRICE_HINTS)
            ]
            if not price_columns:
                out.append("`ARTICULOS` no tiene columnas de precio.")
                out.append("")
            else:
                out.append("| Columna | Tipo |")
                out.append("|---|---|")
                for name, col_type in price_columns:
                    out.append(f"| `{name}` | {col_type} |")
                out.append("")
                selected = ", ".join(f'a."{name}"' for name, _ in price_columns)
                cursor.execute(
                    f"select first {SAMPLE_ROWS} a.\"CODIGOARTICULO\", {selected} "
                    f'from "ARTICULOS" a where a."CODIGOARTICULO" is not null'
                )
                names = [desc[0].strip() for desc in cursor.description]
                rows = [dict(zip(names, row)) for row in cursor.fetchall()]
                out.extend(_render_table(rows))
                out.append("")

        # --- 6. Resumen de columnas de precio en todo el esquema ---
        out.append("### 6. Resumen: toda columna del esquema cuyo nombre contiene PRECIO / LISTA / TARIFA / VALOR")
        out.append("")
        try:
            schema_prices = price_columns_schema(cursor)
            if not schema_prices:
                out.append("Ninguna columna de precio en todo el esquema.")
            else:
                out.append(f"Total: **{len(schema_prices)}** columnas.")
                out.append("")
                current = None
                for table, name, col_type in schema_prices:
                    if table != current:
                        current = table
                        out.append(f"- **`{table}`**")
                    out.append(f"    - `{name}` ({col_type})")
        except Exception as exc:
            out.append(f"**ERROR en el resumen del esquema**: `{type(exc).__name__}: {exc}`")
        out.append("")

    except Exception as exc:
        out.append(f"**ERROR durante el probe**: `{type(exc).__name__}: {exc}`")
        out.append("")
    finally:
        try:
            connection.close()
        except Exception:
            pass

    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe read-only del esquema de Flexxus.")
    parser.add_argument(
        "--database",
        action="append",
        dest="databases",
        help="Ruta del .gdb vista desde el servidor. Se puede repetir. Por defecto, las dos bases de ETR.",
    )
    parser.add_argument(
        "--salida",
        dest="salida",
        help="Escribe el informe en ese archivo (ademas de stdout).",
    )
    args = parser.parse_args()

    databases = args.databases or list(DEFAULT_DATABASES)

    report: list[str] = []
    report.append("# Spike de esquema Flexxus (Firebird)")
    report.append("")
    report.append(f"- Generado: `{dt.datetime.now().isoformat(timespec='seconds')}`")
    report.append(f"- Herramienta: `backend/scripts/probe_flexxus_esquema.py` (solo lectura, `readonly=True`)")
    report.append(f"- Objetivo: confirmar donde vive el **precio de venta** de un articulo.")
    report.append("")

    for database in databases:
        report.extend(probe_database(database))
        report.append("")

    text = "\n".join(report)

    if args.salida:
        with open(args.salida, "w", encoding="utf-8", errors="replace") as handle:
            handle.write(text + "\n")
        print(f"Informe escrito en {args.salida}")
    else:
        print(text)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
