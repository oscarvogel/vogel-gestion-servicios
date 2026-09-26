"""work order lifecycle dates and status semantics
Revision ID: 20260926_0007
Revises: 20260925_0006
"""
from alembic import op
import sqlalchemy as sa

revision="20260926_0007"
down_revision="20260925_0006"
branch_labels=None
depends_on=None

def upgrade():
    with op.batch_alter_table("work_order_statuses") as batch:
        batch.add_column(sa.Column("marks_completed",sa.Boolean(),nullable=False,server_default=sa.false()))
        batch.add_column(sa.Column("marks_delivered",sa.Boolean(),nullable=False,server_default=sa.false()))
    with op.batch_alter_table("work_orders") as batch:
        batch.add_column(sa.Column("expected_delivery_at",sa.DateTime(),nullable=True))
        batch.add_column(sa.Column("completed_at",sa.DateTime(),nullable=True))
        batch.add_column(sa.Column("delivered_at",sa.DateTime(),nullable=True))
    bind=op.get_bind()
    bind.execute(sa.text("UPDATE work_order_statuses SET marks_completed=1 WHERE name='Listo'"))
    bind.execute(sa.text("UPDATE work_order_statuses SET marks_delivered=1 WHERE name='Entregado'"))

def downgrade():
    with op.batch_alter_table("work_orders") as batch:
        batch.drop_column("delivered_at")
        batch.drop_column("completed_at")
        batch.drop_column("expected_delivery_at")
    with op.batch_alter_table("work_order_statuses") as batch:
        batch.drop_column("marks_delivered")
        batch.drop_column("marks_completed")
