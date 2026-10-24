"""parametros de empresa para el modulo de repuestos de Flexxus (#114)

Revision ID: 20261024_0028
Revises: 20261023_0027

Define los tres parametros que decide **quien** ve el catalogo de repuestos de
Flexxus, y con que base y lista de precios.

El catalogo de Flexxus es el de Electrotecniref: si se encendiera para otra
empresa, esa empresa veria el catalogo y los precios de otro. Por eso los
tres son **de plataforma** (`editable = false`): el administrador de la empresa
no los puede cambiar ni aunque mande el PATCH a mano, porque
`company_parameters.py` corta con 403. Los habilita la plataforma.

`flexxus.enabled` queda en false: una empresa que no lo tenga no ve nada,
aunque el ERP este configurado y accesible. Apagado por default, como los
parametros de la IA.

Las definiciones salen del catalogo de codigo (`app/core/parameter_catalog.py`)
para que la migracion y los tests no puedan divergir. Un test lo verifica.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261024_0028"
down_revision = "20261023_0027"
branch_labels = None
depends_on = None


def _nombres() -> list[str]:
    """Los nombres salen del catalogo de codigo, como en la 0018, para no poder divergir."""
    import importlib.util
    import pathlib
    import sys

    _spec = importlib.util.spec_from_file_location(
        "_parameter_catalog",
        pathlib.Path(__file__).resolve().parents[2] / "app" / "core" / "parameter_catalog.py",
    )
    _catalog = importlib.util.module_from_spec(_spec)
    # El modulo usa `from __future__ import annotations`; sin el registro en
    # `sys.modules` la importacion falla al crear el dataclass.
    sys.modules[_spec.name] = _catalog
    _spec.loader.exec_module(_catalog)
    return [parametro[0] for parametro in _catalog.FLEXXUS_PARAMETERS]


def _catalogo() -> list[tuple[str, str, str, str, str, bool]]:
    import importlib.util
    import pathlib
    import sys

    _spec = importlib.util.spec_from_file_location(
        "_parameter_catalog",
        pathlib.Path(__file__).resolve().parents[2] / "app" / "core" / "parameter_catalog.py",
    )
    _catalog = importlib.util.module_from_spec(_spec)
    sys.modules[_spec.name] = _catalog
    _spec.loader.exec_module(_catalog)
    return list(_catalog.FLEXXUS_PARAMETERS)


def upgrade():
    for parameter, default, description, data_type, category, editable in _catalogo():
        op.execute(
            sa.text(
                "insert into parameter_definitions (parameter, default_value, description, data_type, category, editable, active, created_at, updated_at) "
                # CURRENT_TIMESTAMP y no now(): la suite de migraciones corre sobre SQLite,
                # donde now() no existe.
                "values (:p, :d, :desc, :t, :c, :e, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ).bindparams(
                p=parameter, d=default, desc=description, t=data_type, c=category, e=editable
            )
        )


def downgrade():
    """Saca solo las definiciones que esta migracion creo.

    Los overrides por empresa quedan huerfanos: el `parameter_definition_id`
    apunta a una definicion que ya no existe. No se borran aca porque no se
    puede saber desde la migracion cuales son los de Flexxus y cuales los de
    otros parametros sin mirar el esquema.
    """
    for nombre in _nombres():
        op.execute(
            sa.text("delete from parameter_definitions where parameter = :p").bindparams(
                p=nombre
            )
        )
