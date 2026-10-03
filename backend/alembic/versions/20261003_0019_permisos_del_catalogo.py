"""permisos del catalogo que ninguna migracion inserta

Revision ID: 20261003_0019
Revises: 20261002_0018

Las migraciones 0003 y 0005 insertan a mano los permisos de `customers.*`, `equipment.*` y
`work_orders.*`, pero los del nucleo (`companies.*`, `users.*`, `roles.*`) y el `ai.use` de
#44 quedaron solo en el catalogo de codigo. Nadie los inserta al arrancar: el unico lugar que
los crea es `GET /roles/permissions`, que los agrega como efecto colateral de leer la
pantalla de roles.

Eso hacia que un permiso nuevo estuviera muerto hasta que un administrador abriera esa
pantalla. Consecuencia concreta: `ai.use` llego a produccion sin existir en la tabla
`permissions`, asi que todos los endpoints de #44 devolvian 403, en cualquier empresa y para
cualquier usuario, sin error en el arranque ni sintoma en los logs.

Esta migracion inserta todo el catalogo que falte, sin código duropeado: recorre la misma
lista que usa la aplicacion, asi que el proximo permiso que se agregue queda cubierto por el
mismo mecanismo en vez de necesitar acordarse de escribirlo aca.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261003_0019"
down_revision = "20261002_0018"
branch_labels = None
depends_on = None


def _catalogo():
    """El catalogo de permisos de codigo, cargado por ruta como hace la 0018.

    No se importa `app` porque en el contexto de alembic el paquete puede no estar en el
    path, y porque el catalogo tiene que ser legible sin levantar la aplicacion.

    El modulo se registra en `sys.modules` antes de ejecutarlo: `permissions.py` usa
    `from __future__ import annotations` con un `@dataclass`, y el dataclass busca su
    propio modulo en `sys.modules` al crearse. Sin el registro, revienta con
    `AttributeError: 'NoneType' object has no attribute '__dict__'`.
    """
    import importlib.util, pathlib, sys

    spec = importlib.util.spec_from_file_location(
        "_permissions",
        pathlib.Path(__file__).resolve().parents[2] / "app" / "core" / "permissions.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return [(p.code, p.namespace, p.description) for p in module.PERMISSIONS]


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
        # Ya estaba todo: no se tocan los roles. En una base que ya corrio esto, este camino
        # es el normal y no debe cambiar una sola asignacion.
        return

    # Los permisos ya existian con otra asignacion de roles y se respetan; a los nuevos se les
    # da a los Administradores, igual que hicieron 0003 y 0005. Las empresas que se creen en
    # el futuro los reciben solas por `_grant_all_company_permissions`.
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
                        "INSERT INTO role_permissions (role_id, permission_id) VALUES (:rid, :pid)"
                    ),
                    {"rid": rid, "pid": pid},
                )


def downgrade():
    # Solo se pueden quitar los permisos que esta migracion creo. Los que ya venian de 0003 y
    # 0005 quedan como estaban, asi que el downgrade no rompe el estado previo real.
    bind = op.get_bind()
    existentes = {
        code
        for (code,) in bind.execute(sa.text("SELECT code FROM permissions")).fetchall()
    }
    objetivo = {code for code, _, _ in _catalogo() if code not in _PREEXISTENTES}
    for code in sorted(objetivo & existentes):
        pid = bind.execute(
            sa.text("SELECT id FROM permissions WHERE code = :code"), {"code": code}
        ).scalar()
        if pid:
            bind.execute(
                sa.text("DELETE FROM role_permissions WHERE permission_id = :pid"), {"pid": pid}
            )
            bind.execute(sa.text("DELETE FROM permissions WHERE id = :pid"), {"pid": pid})


# Los que inserts 0003 y 0005, que ya venian de ahi antes de este sub-issue.
_PREEXISTENTES = frozenset(
    {
        "customers.view",
        "customers.manage",
        "equipment.view",
        "equipment.manage",
        "work_orders.view",
        "work_orders.manage",
    }
)
