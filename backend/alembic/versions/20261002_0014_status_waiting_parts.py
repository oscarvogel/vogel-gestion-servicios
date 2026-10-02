"""add marks_waiting_parts to work order statuses
Revision ID: 20261002_0014
Revises: 20260929_0013
"""
from alembic import op
import sqlalchemy as sa

revision = "20261002_0014"
down_revision = "20260929_0013"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "work_order_statuses",
        sa.Column("marks_waiting_parts", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column("work_order_statuses", "marks_waiting_parts")
