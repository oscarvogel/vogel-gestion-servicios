"""permisos del maestro de areas de trabajo

Revision ID: 20261025_0030
Revises: 20261024_0029

El cierre mensual a marcas se armaba sobre `work_orders.work_area_id`: el area de
trabajo es la que trae la garantia y la empresa a liquidar. El cierre existia y
funcionaba, pero el area era algo que solo aparecia importado desde el legacy: no
habia API ni pantalla para darla de alta, ni para elegirla en una orden.

Consecuencia: **una orden creada en la aplicacion no entraba nunca al cierre**, porque
nacia sin area y el cierre hace JOIN por ese campo.

Estos permisos dan acceso a esa parte:
- work_areas.view: ver el maestro de areas y elegir area, garantia y empresa al liquidar
  una orden (los que arman la OT).
- work_areas.manage: dar de alta, editar y activar/desactivar areas.

Siguen el patron de la 0027: se insertan los permisos que falten y se los concede a los
roles "Administrador" de cada empresa. Los demas roles se siguen tocando desde la
pantalla de Roles y permisos.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261025_0030"
down_revision = "20261024_0029"
branch_labels = None
depends_on = None

_NAMESPACE = "work_areas"


def _catalogo():
    import importlib.util
    import pathlib
    import sys

    spec = importlib.util.spec_from_file_location(
        "_permissions",
        pathlib.Path(__file__).resolve().parents[2] / "app" / "core" / "permissions.py",
    )
    module = importlib.util.module_from_spec(spec)
    # `permissions.py` usa `from __future__ import annotations` con un `@dataclass`, que al
    # crearse busca su modulo en `sys.modules`. Sin el registro, revienta.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return [
        (p.code, p.namespace, p.description)
        for p in module.PERMISSIONS
        if p.namespace == _NAMESPACE
    ]


def upgrade():
    bind = op.get_bind()
    insertados = []
    for code, namespace, description in _catalogo():
        pid = bind.execute(
            sa.text("SELECT id FROM permissions WHERE code = :code"), {"code": code}
        ).scalar()
        if pid is None:
            bind.execute(
                sa.text(
                    "INSERT INTO permissions (code, namespace, description)"
                    " VALUES (:code, :ns, :desc)"
                ),
                {"code": code, "ns": namespace, "desc": description},
            )
            pid = bind.execute(
                sa.text("SELECT id FROM permissions WHERE code = :code"), {"code": code}
            ).scalar()
            insertados.append(pid)

    if not insertados:
        # Ya estaban: no se toca ninguna asignacion de roles.
        return

    for (rid,) in bind.execute(
        sa.text("SELECT id FROM roles WHERE name = 'Administrador' AND active = 1")
    ).fetchall():
        for pid in insertados:
            ya_esta = bind.execute(
                sa.text(
                    "SELECT 1 FROM role_permissions WHERE role_id = :rid AND permission_id = :pid"
                    " LIMIT 1"
                ),
                {"rid": rid, "pid": pid},
            ).scalar()
            if not ya_esta:
                bind.execute(
                    sa.text(
                        "INSERT INTO role_permissions (role_id, permission_id)"
                        " VALUES (:rid, :pid)"
                    ),
                    {"rid": rid, "pid": pid},
                )


def downgrade():
    """Saca solo lo que esta migracion creo."""
    bind = op.get_bind()
    for code, _namespace, _description in _catalogo():
        pid = bind.execute(
            sa.text("SELECT id FROM permissions WHERE code = :code"), {"code": code}
        ).scalar()
        if not pid:
            continue
        bind.execute(
            sa.text("DELETE FROM role_permissions WHERE permission_id = :pid"), {"pid": pid}
        )
        bind.execute(
            sa.text("DELETE FROM permissions WHERE id = :pid"), {"pid": pid}
        )
