"""quote approval workflow
Revision ID: 20260926_0010
Revises: 20260926_0009
"""
from alembic import op
import sqlalchemy as sa
revision="20260926_0010";down_revision="20260926_0009";branch_labels=None;depends_on=None
def upgrade():
    with op.batch_alter_table("work_order_statuses") as b:
        b.add_column(sa.Column("marks_awaiting_quote_approval",sa.Boolean(),nullable=False,server_default=sa.false()))
        b.add_column(sa.Column("marks_repair",sa.Boolean(),nullable=False,server_default=sa.false()))
    with op.batch_alter_table("work_order_quotes") as b:
        b.add_column(sa.Column("sent_at",sa.DateTime(),nullable=True))
        b.add_column(sa.Column("decided_at",sa.DateTime(),nullable=True))
    bind=op.get_bind()
    bind.execute(sa.text("UPDATE work_order_statuses SET marks_awaiting_quote_approval=1 WHERE LOWER(name)=LOWER(:n)"),{"n":"Esperando aprobación"})
    bind.execute(sa.text("UPDATE work_order_statuses SET marks_repair=1 WHERE LOWER(name)=LOWER(:n)"),{"n":"En reparación"})
def downgrade():
    with op.batch_alter_table("work_order_quotes") as b:
        b.drop_column("decided_at");b.drop_column("sent_at")
    with op.batch_alter_table("work_order_statuses") as b:
        b.drop_column("marks_repair");b.drop_column("marks_awaiting_quote_approval")
