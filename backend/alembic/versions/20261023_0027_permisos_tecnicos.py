"""permisos del maestro de tecnicos

Revision ID: 20261023_0027
Revises: 20261022_0026

El legacy (CiberBase) no tiene maestro de tecnicos: los "intervinientes" de cada OT son
personas sueltas, y el importador armó un maestro por empresa con esos nombres (44 en
Electrotecniref) para que el historico se pueda consultar.

Pero el maestro no servia para nada: no habia API ni pantalla para dar de alta un tecnico,
ni para asignarlo a una orden de trabajo. Sin eso, una OT nueva no tiene a quien hacerla
(asignarla despues en el taller era un paso que el sistema no permitia registrar).

Estos permisos dan acceso a esa nueva parte:
- technicians.view: ver el maestro y la lista de tecnicos (los que arman la OT).
- technicians.manage: dar de alta, editar, activar/desactivar y asignar a las ordenes.

Siguen el patron de la 0025: se insertan los permisos que falten y se los concede a los
roles "Administrador" de cada empresa. Los demas roles se siguen tocando desde la pantalla
de Roles y permisos, como con los demas permisos.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261023_0027"
down_revision = "20261022_0026"
branch_labels = None
depends_on = None

_NAMESPACE = "technicians"


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
