"""backfill de permisos del rol Administrador de empresa

Revision ID: 20261003_0020
Revises: 20261003_0019

Las migraciones 0003 y 0005 gave sus permisos a los Administradores que existian en ese
momento. Los del nucleo (`companies.*`, `users.*`, `roles.*`) nunca se le dieron a nadie,
porque ningun arranque inserta permisos: el unico lugar que lo hacia era
`GET /roles/permissions`, como efecto colateral de leer la pantalla de roles.

El efecto es que un Administrador de empresa creado antes de esas migraciones queda con
permisos de a poco. En produccion, `Traid Walter` tiene 7 de 18: puede ver clientes, equipos
y ordenes de trabajo, pero **no puede administrar los usuarios de su empresa, ni ver los
roles, ni gestionar la empresa**. En cuanto Walter entre a dar de alta a otro usuario se va
a topar con un 403 sin aviso.

Esta migracion alinea los Administradores de empresa con lo que la aplicacion ya hace con los
nuevos: `_grant_all_company_permissions` le da al Administrador de cada empresa que se crea
**todo** el catalogo. O sea que el estado anterior no era una decision, era un forgets.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261003_0020"
down_revision = "20261003_0019"
branch_labels = None
depends_on = None

# Los namespaces que las migraciones 0003 y 0005 ya le dabamos a los Administradores, y que
# por lo tanto esta migracion no agrega. Sirven tambien para que el downgrade sepa que
# sacar: exactamente estos namespaces son los que el upgrade no toco.
_YA_CONCEDIDOS = ("customers", "equipment", "work_orders")


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
    return [(p.code, p.namespace) for p in module.PERMISSIONS]


def upgrade():
    bind = op.get_bind()
    catalogo = _catalogo()
    faltan = [(code, ns) for code, ns in catalogo if ns not in _YA_CONCEDIDOS]
    if not faltan:
        return

    pids = {}
    for code, _ns in faltan:
        pid = bind.execute(
            sa.text("SELECT id FROM permissions WHERE code = :code"), {"code": code}
        ).scalar()
        # Si 0019 no corrio, el permiso no existe. No se inserta aqui a proposito: el
        # unico que sabe crear permisos es 0019, y meterlo tambien aca duplicaria la
        # responsabilidad. Se avisa en vez de inventar el dato.
        if pid is not None:
            pids[pid] = code
    if not pids:
        return

    # Solo Administradores **de empresa** (company_id no nulo). El rol global del sistema,
    # si existe, no se toca: el superadmin no pasa por role_permissions.
    for (rid,) in bind.execute(
        sa.text("SELECT id FROM roles WHERE name = 'Administrador' AND active = 1 AND company_id IS NOT NULL")
    ).fetchall():
        ya_tiene = {
            row[0]
            for row in bind.execute(
                sa.text("SELECT permission_id FROM role_permissions WHERE role_id = :rid"),
                {"rid": rid},
            ).fetchall()
        }
        for pid in pids:
            if pid not in ya_tiene:
                bind.execute(
                    sa.text(
                        "INSERT INTO role_permissions (role_id, permission_id) VALUES (:rid, :pid)"
                    ),
                    {"rid": rid, "pid": pid},
                )


def downgrade():
    """Saca de los Administradores de empresa lo unico que agrego esta migracion.

    O sea, los permisos de los namespaces del nucleo. **No saca** `ai.use`, que lo dio 0019,
    ni los de clientes/equipos/ordenes, que los dieron 0003 y 0005: devolverlos es justamente
    el estado roto que esta migracion vino a arreglar.

    Salvedad: si despues se agrego un namespace nuevo al catalogo y quedo asignado a mano,
    este downgrade tambien se lo lleva. Es la unica parte del rollback que no es exacta, y
    esta anotada para que no sorprenda.
    """
    bind = op.get_bind()
    for code, namespace in _catalogo():
        if namespace in _YA_CONCEDIDOS:
            continue
        pid = bind.execute(
            sa.text("SELECT id FROM permissions WHERE code = :code"), {"code": code}
        ).scalar()
        if not pid:
            continue
        for (rid,) in bind.execute(
            sa.text(
                "SELECT id FROM roles WHERE name = 'Administrador' AND active = 1"
                " AND company_id IS NOT NULL"
            )
        ).fetchall():
            bind.execute(
                sa.text(
                    "DELETE FROM role_permissions WHERE role_id = :rid AND permission_id = :pid"
                ),
                {"rid": rid, "pid": pid},
            )
