"""garantia propia / de service en el cierre mensual a marcas

Revision ID: 20261022_0026
Revises: 20261022_0025

El desglose del cierre tenia dos casilleros: garantia de terceros (``warranty_type = 1``) y
fuera de garantia (``warranty_type = 0``). Pero el legacy tiene TRES: 0 fuera, 1 garantia de
fabricante o terceros, 2 garantia propia / de service.

El caso 2 es el de Alladio (``CodCli = 7634``), que no es una marca de fabrica sino un
service oficial / representante: sus politicas de "Garantia de Service" tienen ``Gt = 2``, o
sea que la garantia la da el service, no un tercero. Meterlo en "fuera de garantia" seria
mostrar como trabajo no cubierto lo que si cubre, y por lo tanto liquidar al service
oficial como si no pagara.

La decision es que Alladio se liquida, pero con su propio criterio: entra al cierre como
cualquier empresa con area propia, y su garantia propia va en su propio casillero. La
columna ``warranty_settlement_orders.warranty_type`` ya guardaba el 2; lo que faltaba era
el resumen.

Es aditiva: dos columnas con default 0, y nada de lo existente se recalcula ni se rompe.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261022_0026"
down_revision = "20261022_0025"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "warranty_settlements",
        sa.Column("own_warranty_works_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "warranty_settlements",
        sa.Column("own_warranty_amount", sa.Numeric(19, 6), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_column("warranty_settlements", "own_warranty_amount")
    op.drop_column("warranty_settlements", "own_warranty_works_count")
