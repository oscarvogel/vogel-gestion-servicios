"""normaliza `work_order_execution_items.item_type` de 'WORK' a 'LABOR'

Revision ID: 20261004_0022
Revises: 20261003_0021

El dominio habla dos valores y solo dos: `PART` y `LABOR`. Lo dice la API, que valida con
`^(PART|LABOR)$`; lo dice la pantalla, que separa con `item_type === "PART"`; y lo usan las
columnas de los presupuestos, que son `subtotal_parts` y `subtotal_labor`.

La herramienta `agregar_trabajo` del asistente (#44 sub-issue 3) escribia `WORK`. Nadie lo
veia roto: la pantalla cae en la rama "no es PART" y lo muestra como Trabajo, que era justo
como se deberia ver. El problema aparecio al usar el dato, no al mostrarlo: el calculo del
presupuesto (#44 sub-issue 4) distingue repuesto de mano de obra para aplicar el markup solo
a los repuestos, y con `WORK` la fila no era un repuesto ni era mano de obra. Dependia de que
alguien eligiera la convencion correcta en el momento de escribirla.

Esta migracion lleva las filas ya escritas al valor del dominio. Es un UPDATE de datos, no
cambia el esquema. Es idempotente: volver a correrla no hace nada.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261004_0022"
down_revision = "20261003_0021"
branch_labels = None
depends_on = None

# El valor mal escrito y el correcto. Se dejan como constantes porque el par es el contenido
# real de la migracion y aparece en el upgrade y en el downgrade.
VALOR_VIEJO = "WORK"
VALOR_NUEVO = "LABOR"


def upgrade():
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE work_order_execution_items SET item_type = :nuevo WHERE item_type = :viejo"
        ),
        {"nuevo": VALOR_NUEVO, "viejo": VALOR_VIEJO},
    )


def downgrade():
    """Vuelve las filas a `WORK`.

    No es un rollback exacto: las filas que se escribieron **despues** de esta migracion ya
    quedaron en `LABOR` porque la herramienta quedo corregida, asi que bajarla las mezcla con
    las viejas y devuelve un estado que nunca existio. Se documenta en vez de fingir que es
    reversible: el camino de ida, poner todo en `LABOR`, es el que importa, y ese no pierde
    informacion porque `PART` y `WORK` significan cosas distintas y `LABOR` no colisiona con
    ninguna.
    """
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE work_order_execution_items SET item_type = :viejo WHERE item_type = :nuevo"
        ),
        {"nuevo": VALOR_NUEVO, "viejo": VALOR_VIEJO},
    )
