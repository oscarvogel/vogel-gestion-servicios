"""trazabilidad del precio de repuestos (#114)

Revision ID: 20261024_0029
Revises: 20261024_0028

Agrega a las lineas de presupuesto y de ejecucion los tres datos que permiten
saber de donde salio el precio de un repuesto:

- `item_code`: el codigo del articulo en el ERP (Flexxus).
- `price_source`: de que columna del ERP se leyo el precio
  (por ejemplo `flexxus:PRECIOVENTA1`).
- `price_synced_at`: cuando se leyo.

Sin esto, un presupuesto dice "ARANDELA GROWER 1/4 - $16,28" y no hay forma de
saber si ese precio vino del ERP, de la memoria del tecnico o de una carga a
mano. Con esto, la linea apunta al dato real del que salio.

Las columnas son nullable a proposito: las lineas de mano de obra y las que
always se cargaron a mano antes de este modulo no tienen origen en el ERP, y
no hay que inventarselo.

El `downgrade` las borra: el dato se pierde, pero el precio guardado en la
linea no se toca, asi que el presupuesto historico sigue diciendo lo que decia.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261024_0029"
down_revision = "20261024_0028"
branch_labels = None
depends_on = None

_TABLAS = ("work_order_quote_items", "work_order_execution_items")


def upgrade():
    for tabla in _TABLAS:
        op.add_column(tabla, sa.Column("item_code", sa.String(40), nullable=True))
        op.add_column(tabla, sa.Column("price_source", sa.String(60), nullable=True))
        op.add_column(tabla, sa.Column("price_synced_at", sa.DateTime(), nullable=True))


def downgrade():
    for tabla in _TABLAS:
        op.drop_column(tabla, "price_synced_at")
        op.drop_column(tabla, "price_source")
        op.drop_column(tabla, "item_code")
