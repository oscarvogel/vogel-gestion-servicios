"""los parametros de la IA dejan de ser editables por la empresa

Revision ID: 20261004_0023
Revises: 20261004_0022

La IA es un adicional comercial. Que su interruptor (`ai.enabled`) y su techo de uso
(`ai.monthly_quota_usd`, `ai.monthly_request_limit`) estuvieran en la pantalla de Parametros
—con los mismos permisos que la configuracion del cliente— dejaba dos agujeros:

1. Un administrador de empresa se prendia solo el adicional.
2. Con lo anterior, podia ademas ponerse la cuota en 0, que significa **sin cuota**: un techo
   que el cliente puede levantar no es un techo.

La migracion 0018 los sembro con `editable` tomado del catalogo de codigo, asi que en las
instalaciones nuevas ya nacen bien. Esta va para las que ya los tienen en `true`.

El cambio de `editable` a `false` no es solo cosmetico: `company_parameters.py` corta el
PATCH con 403 cuando el parametro no es editable, asi que el administrador recibe el no en el
servidor y no solo un switch apagado en la pantalla.

Los tres siguen **visibles** para la empresa, de lectura. Que un cliente vea "IA no incluida
en tu plan" es honesto; esconderlo seria dejar un modulo que no aparece sin explicacion.

Quien los habilita ahora es la plataforma, con `PUT /companies/{id}/ai`, que es superadmin.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261004_0023"
down_revision = "20261004_0022"
branch_labels = None
depends_on = None


def _nombres() -> list[str]:
    """Los nombres salen del catalogo de codigo, como en la 0018, para no poder divergir."""
    import importlib.util
    import pathlib

    _spec = importlib.util.spec_from_file_location(
        "_parameter_catalog",
        pathlib.Path(__file__).resolve().parents[2] / "app" / "core" / "parameter_catalog.py",
    )
    _catalog = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_catalog)
    return [parametro[0] for parametro in _catalog.AI_PARAMETERS]


def upgrade():
    for nombre in _nombres():
        op.execute(
            sa.text("update parameter_definitions set editable = false where parameter = :p")
            .bindparams(p=nombre)
        )


def downgrade():
    """Vuelve a editables.

    Se deja el downgrade simple y no simula un historial: volver atrás reabre el agujero
    comercial, asi que es una operacion que hay que hacer a proposito, no por reflejo. Por
    eso no se adivina nada de cuando se aplico: la fila queda con el valor que tenia antes de
    este PR, que es `true`, y los overrides por empresa quedan intactos.
    """
    for nombre in _nombres():
        op.execute(
            sa.text("update parameter_definitions set editable = true where parameter = :p")
            .bindparams(p=nombre)
        )
