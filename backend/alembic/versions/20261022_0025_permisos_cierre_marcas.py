"""permisos del cierre mensual a marcas

Revision ID: 20261022_0025
Revises: 20261022_0024

El cierre mensual a marcas es un modulo nuevo (`warranty_settlements.*`). Necesita sus propios
permisos y no puede reusar los de ordenes de trabajo, por una razon que no es de estilo: el
cierre **congela un periodo** y lo marca como liquidado. Ver un reporte y emitir un cierre
no es lo mismo, igual que no es lo mismo editar una orden y cerrar un mes.

Se siembran y se dan a los Administradores de empresa, igual que hicieron 0003, 0005 y 0019.
Las empresas que se creen en el futuro los reciben solas por `_grant_all_company_permissions`.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261022_0025"
down_revision = "20261022_0024"
branch_labels = None
depends_on = None

_NAMESPACE = "warranty_settlements"


def _catalogo():
    import importlib.util, pathlib, sys

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
    """Saca solo lo que esta migracion creo.

    Los permisos de ordenes de trabajo, clientes, equipos y los del nucleo quedan como
    estaban: devolverlos seria romper el estado previo real.
    """
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
