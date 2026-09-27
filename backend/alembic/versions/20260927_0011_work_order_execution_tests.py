"""work order execution and final tests
Revision ID: 20260927_0011
Revises: 20260926_0010
"""
from alembic import op
import sqlalchemy as sa
revision="20260927_0011"
down_revision="20260926_0010"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table("work_order_execution_items",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False),
        sa.Column("work_order_id",sa.Integer(),sa.ForeignKey("work_orders.id",ondelete="CASCADE"),nullable=False),sa.Column("item_type",sa.String(10),nullable=False),
        sa.Column("description",sa.String(250),nullable=False),sa.Column("quantity",sa.Numeric(12,3),nullable=False,server_default="1"),
        sa.Column("unit_cost",sa.Numeric(14,2),nullable=False,server_default="0"),sa.Column("unit_price",sa.Numeric(14,2),nullable=False,server_default="0"),
        sa.Column("created_by_user_id",sa.Integer(),sa.ForeignKey("users.id"),nullable=False),sa.Column("created_at",sa.DateTime(),nullable=False,server_default=sa.func.now()))
    op.create_index("ix_execution_company","work_order_execution_items",["company_id"]);op.create_index("ix_execution_order","work_order_execution_items",["work_order_id"])
    op.create_table("work_order_final_tests",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False),
        sa.Column("work_order_id",sa.Integer(),sa.ForeignKey("work_orders.id",ondelete="CASCADE"),nullable=False),sa.Column("passed",sa.Boolean(),nullable=False),
        sa.Column("notes",sa.Text()),sa.Column("tested_by_user_id",sa.Integer(),sa.ForeignKey("users.id"),nullable=False),sa.Column("tested_at",sa.DateTime(),nullable=False,server_default=sa.func.now()))
    op.create_index("ix_final_tests_company","work_order_final_tests",["company_id"]);op.create_index("ix_final_tests_order","work_order_final_tests",["work_order_id"])

def downgrade():
    op.drop_table("work_order_final_tests");op.drop_table("work_order_execution_items")
