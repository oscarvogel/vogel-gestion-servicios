#!/usr/bin/env python
"""Importador del legacy de CiberBrain (SQL Server) al sistema destino (MySQL).

El origen es la base real (``CiberBase``, SQL Server 2022 restaurada) y el destino es
MySQL. No hay archivos intermedios: el importador consulta el legacy por TCP
(``pymssql``) y escribe en el destino por lotes.

La password del legacy se pasa **siempre por variable de entorno**
(``CB_SQLSERVER_PASSWORD``): nunca va en el codigo ni en un archivo del repo.

Ejemplos:

    # Empresa nueva, primera importacion
    $env:DATABASE_URL='mysql+pymysql://vogel:change_me@127.0.0.1:3307/vogel_gestion_servicios'
    $env:CB_SQLSERVER_PASSWORD='...'
    python backend/scripts/import_cyberbrain.py --company-name Electrotecniref

    # Reimportar (borra lo importado previamente de esa empresa y vuelve a armar)
    python backend/scripts/import_cyberbrain.py --company-name Electrotecniref --replace

    # Ver que pasaria, sin tocar la base
    python backend/scripts/import_cyberbrain.py --company-name Electrotecniref --dry-run

El ``DATABASE_URL`` es obligatorio: el script no adivina la base. Y por seguridad no
corre contra una base que no sea local salvo que se pase ``--allow-remote-db``.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.company import Company  # noqa: E402
from app.models.customer import Customer, Equipment  # noqa: E402,F401
from app.models.invoice import Invoice  # noqa: E402,F401
from app.models.role import CompanyUserRole, Permission, Role  # noqa: E402,F401
from app.models.user import CompanyUser, User  # noqa: E402,F401
from app.models.work_area import Seller, Technician, WorkArea, WorkBench  # noqa: E402,F401
from app.models.work_order import (  # noqa: E402,F401
    WorkOrder,
    WorkOrderCounter,
    WorkOrderStatus,
)
from app.models.work_order_part import (  # noqa: E402,F401
    WorkOrderPart,
    WorkOrderPartCommission,
    WorkOrderTechnician,
)

from import_cyberbrain.context import Contexto  # noqa: E402
from import_cyberbrain.report import Reporte  # noqa: E402
from import_cyberbrain.source import (  # noqa: E402
    CORTE_POR_DEFECTO,
    Configuracion,
    ErrorDeConexion,
    FuenteCiberBase,
)
from import_cyberbrain import source  # noqa: E402
from import_cyberbrain.steps import STEPS  # noqa: E402
from import_cyberbrain.steps.customers import MARCA_LEGACY  # noqa: E402

#: Raiz del repo (dos niveles arriba de backend/scripts).
RAIZ = Path(__file__).resolve().parents[2]

#: Empresa por defecto: la unica empresa del legacy.
EMPRESA_POR_DEFECTO = "Electrotecniref"

#: Hosts que se consideran locales (la base de pruebas).
HOSTS_LOCALES = {"localhost", "127.0.0.1", "::1"}


def _argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="import_cyberbrain.py",
        description=(
            "Importa el legacy de CiberBrain (SQL Server, por TCP) al sistema destino "
            "(MySQL)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Variables de entorno:\n"
            "  CB_SQLSERVER_PASSWORD  obligatoria: la password del legacy\n"
            "  CB_SQLSERVER_HOST      por omision localhost\n"
            "  CB_SQLSERVER_PORT      por omision 1433\n"
            "  CB_SQLSERVER_USER      por omision sa\n"
            "  CB_SQLSERVER_DB        por omision CiberBase\n"
            "  DATABASE_URL           obligatoria: el destino MySQL\n"
            "\n"
            "El importador es idempotente: se puede re-ejecutar. Con --replace borra\n"
            "lo importado previamente de esa empresa y reimporta desde cero."
        ),
    )
    parser.add_argument(
        "--company-id",
        type=int,
        default=None,
        help="Id de la empresa destino. Mutuamente excluido con --company-name.",
    )
    parser.add_argument(
        "--company-name",
        default=EMPRESA_POR_DEFECTO,
        help=(
            "Nombre de la empresa destino. Si no existe, se crea con los 8 estados "
            f"por defecto (por omision: {EMPRESA_POR_DEFECTO})."
        ),
    )
    parser.add_argument(
        "--desde",
        default=CORTE_POR_DEFECTO,
        help=(
            "Corte del legacy por FechaAlta (AAAAMMDD). El alcance acordado es "
            f"desde 2020 (por omision: {CORTE_POR_DEFECTO})."
        ),
    )
    parser.add_argument(
        "--report-dir",
        default=str(RAIZ / "backup" / "_work"),
        help="Carpeta donde se deja el cuadre de la importacion.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help=(
            "Borra lo importado previamente de esa empresa (las filas con legacy_id, "
            "con cascada) y reimporta desde cero."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Calcula y muestra el cuadre sin tocar la base.",
    )
    parser.add_argument(
        "--allow-remote-db",
        action="store_true",
        help="Permite correr contra una base que no sea local (por omision, no).",
    )
    return parser.parse_args()


def _database_url() -> str:
    """El ``DATABASE_URL`` del entorno. Si no esta, se corta con un mensaje claro."""
    url = os.getenv("DATABASE_URL")
    if not url or not url.strip():
        raise SystemExit(
            "Falta la variable de entorno DATABASE_URL.\n"
            "El importador no adivina la base de destino. Por ejemplo:\n"
            "  $env:DATABASE_URL='mysql+pymysql://vogel:change_me@127.0.0.1:3307/"
            "vogel_gestion_servicios'"
        )
    return url.strip()


def _controlar_destino(url: str, permitir_remoto: bool) -> None:
    """Se niega a correr contra una base que no sea local.

    El destino de este importador es una base de pruebas: un ``--replace`` contra
    produccion borraria datos de verdad.
    """
    host = make_url(url).host or ""
    if permitir_remoto:
        return
    if host.lower() not in HOSTS_LOCALES:
        raise SystemExit(
            f"El DATABASE_URL apunta a '{host}', que no es una base local.\n"
            "El importador borra datos en --replace: contra produccion o staging "
            "eso no se hace por omision. Si la base es correcta, pasá "
            "--allow-remote-db."
        )


def _empresa(session, company_id: int | None, nombre: str, dry_run: bool) -> Company:
    """Busca la empresa destino y la crea si no existe."""
    if company_id is not None:
        empresa = session.get(Company, company_id)
        if empresa is None:
            raise SystemExit(f"No existe la empresa con id {company_id}.")
        return empresa
    empresa = session.execute(
        select(Company).where(Company.name == nombre)
    ).scalars().first()
    if empresa is not None:
        return empresa
    if dry_run:
        raise SystemExit(
            f"La empresa '{nombre}' no existe y el importador esta en --dry-run "
            "(no crea nada). Importala primero sin --dry-run o usá --company-id."
        )
    empresa = Company(name=nombre, slug=_slug(nombre), active=True)
    session.add(empresa)
    session.flush()
    session.commit()
    return empresa


def _slug(nombre: str) -> str:
    """Identificador de la empresa a partir del nombre (como el endpoint de alta)."""
    partes = []
    for caracter in nombre.lower():
        if caracter.isalnum():
            partes.append(caracter)
        elif caracter in (" ", "-", "_"):
            partes.append("-")
    return "".join(partes).strip("-")


def SessionLocal(url: str):  # noqa: N802 - es el nombre que usa el resto del repo
    """Sesion propia del script contra el ``DATABASE_URL`` del entorno.

    El importador no usa la sesion de la aplicacion: corre por fuera del servidor y
    necesita un motor propio (y sin que los errores impriman los 30.000 parametros
    de un INSERT fallido).
    """
    motor = create_engine(url, pool_pre_ping=True, hide_parameters=True)
    return sessionmaker(bind=motor, autocommit=False, autoflush=False)()


def _borrar_importado(session, company_id: int, codigos_area: list[str]) -> dict[str, int]:
    """Borra lo importado previamente de esa empresa.

    Se borra por la marca de lo importado, no por "todo lo de la empresa": en la
    base de pruebas puede haber filas cargadas a mano que no hay que tocar.

    El orden de los borrados lo imponen las claves foraneas: las facturas y las OTs
    primero (las areas y los clientes los referencian), despues los clientes (que
    se lleva por cascada los equipos) y por ultimo los vendedores y los tecnicos.
    """
    area_marca = ",".join(f"'{codigo}'" for codigo in codigos_area) or "''"
    borrados: dict[str, int] = {}
    sentencias = [
        (
            "invoices",
            "DELETE FROM invoices WHERE company_id = %(company_id)s AND legacy_id IS NOT NULL",
        ),
        (
            "work_orders",
            "DELETE FROM work_orders WHERE company_id = %(company_id)s AND legacy_id IS NOT NULL",
        ),
        (
            "work_areas",
            f"DELETE FROM work_areas WHERE company_id = %(company_id)s AND area_code IN ({area_marca})",
        ),
        (
            "equipment",
            "DELETE FROM equipment WHERE company_id = %(company_id)s AND notes LIKE %(marca)s",
        ),
        (
            "customers",
            "DELETE FROM customers WHERE company_id = %(company_id)s AND notes LIKE %(marca)s",
        ),
        (
            "work_benches",
            "DELETE FROM work_benches WHERE company_id = %(company_id)s "
            "AND legacy_aliases IS NOT NULL",
        ),
        (
            "technicians",
            "DELETE FROM technicians WHERE company_id = %(company_id)s AND legacy_code IS NOT NULL",
        ),
        (
            "sellers",
            "DELETE FROM sellers WHERE company_id = %(company_id)s AND legacy_code IS NOT NULL",
        ),
    ]
    for nombre, sentencia in sentencias:
        resultado = session.connection().exec_driver_sql(
            sentencia,
            {"company_id": company_id, "marca": f"{MARCA_LEGACY}%"},
        )
        borrados[nombre] = int(resultado.rowcount or 0)
    session.commit()
    return borrados


def main() -> int:
    argumentos = _argumentos()
    url = _database_url()
    _controlar_destino(url, argumentos.allow_remote_db)

    modo = "reimportacion (--replace)" if argumentos.replace else "importacion"
    if argumentos.dry_run:
        modo += ", simulacion (--dry-run)"

    try:
        configuracion = Configuracion.desde_entorno()
    except ErrorDeConexion as error:
        raise SystemExit(str(error)) from None

    fuente = FuenteCiberBase(configuracion, corte=argumentos.desde)
    try:
        fuente.abrir()
    except ErrorDeConexion as error:
        raise SystemExit(str(error)) from None

    session = SessionLocal(url)
    try:
        empresa = _empresa(
            session, argumentos.company_id, argumentos.company_name, argumentos.dry_run
        )
        reporte = Reporte(
            empresa=empresa.name,
            origen=(
                f"{configuracion.base} en {configuracion.host}:{configuracion.puerto} "
                f"(corte FechaAlta >= {argumentos.desde})"
            ),
            modo=modo,
        )

        if argumentos.replace:
            codigos_area = [
                source.texto(fila[1]) for fila in fuente.areas()
            ]
            if argumentos.dry_run:
                reporte.observacion(
                    "--replace en --dry-run: se mostraria el borrado de lo importado "
                    "previamente, pero no se borra nada."
                )
            else:
                borrados = _borrar_importado(session, empresa.id, codigos_area)
                for nombre, cantidad in borrados.items():
                    if cantidad:
                        reporte.observacion(
                            f"--replace: {cantidad} filas borradas de {nombre}"
                        )

        ctx = Contexto(
            session=session,
            company_id=empresa.id,
            fuente=fuente,
            dry_run=argumentos.dry_run,
            replace=argumentos.replace,
            reporte=reporte,
        )

        for nombre, funcion in STEPS:
            inicio = time.time()
            try:
                funcion(ctx)
                session.commit()
            except Exception as error:  # noqa: BLE001 - se reporta y se corta
                session.rollback()
                print(f"ERROR en el paso '{nombre}': {error}", file=sys.stderr)
                print(
                    "El paso se revirtio. Los pasos anteriores quedaron confirmados.",
                    file=sys.stderr,
                )
                raise
            print(f"  paso '{nombre}': ok ({time.time() - inicio:.1f}s)")

        for etiqueta, cantidad in source.RECORTADOS.items():
            reporte.observacion(
                f"{cantidad} valores recortados por el ancho de la columna '{etiqueta}'"
            )

        ruta = Path(argumentos.report_dir) / f"import_{_slug(empresa.name)}_cuadre.txt"
        if not argumentos.dry_run:
            reporte.escribir(ruta)
            print(f"Cuadre escrito en {ruta}")
        print(reporte.render())
    finally:
        session.close()
        fuente.cerrar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
