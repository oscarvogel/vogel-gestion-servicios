"""semantic quoted marker for work order statuses
Revision ID: 20260926_0009
Revises: 20260926_0008
"""
from alembic import op
import sqlalchemy as sa

revision="20260926_0009"
down_revision="20260926_0008"
branch_labels=None
depends_on=None

def upgrade():
    with op.batch_alter_table("work_order_statuses") as batch:
        batch.add_column(sa.Column("marks_quoted",sa.Boolean(),nullable=False,server_default=sa.false()))
    bind=op.get_bind()
    bind.execute(sa.text("UPDATE work_order_statuses SET marks_quoted=1 WHERE LOWER(name)=LOWER(:name)"),{"name":"Presupuestado"})

def downgrade():
    with op.batch_alter_table("work_order_statuses") as batch:
        batch.drop_column("marks_quoted")
