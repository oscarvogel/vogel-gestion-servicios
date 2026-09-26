"""work order actual repair
Revision ID: 20260926_0012
Revises: 20260926_0011
"""
from alembic import op
import sqlalchemy as sa
revision="20260926_0012";down_revision="20260926_0011";branch_labels=None;depends_on=None
def upgrade():
    op.create_table("work_order_repairs",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False),
        sa.Column("work_order_id",sa.Integer(),sa.ForeignKey("work_orders.id",ondelete="CASCADE"),nullable=False,unique=True),
        sa.Column("technician_user_id",sa.Integer(),sa.ForeignKey("users.id"),nullable=True),
        sa.Column("notes",sa.Text()),sa.Column("final_tests",sa.Text()),
        sa.Column("started_at",sa.DateTime(),server_default=sa.func.now(),nullable=False),
        sa.Column("finished_at",sa.DateTime()),sa.Column("created_at",sa.DateTime(),server_default=sa.func.now(),nullable=False),
        sa.Column("updated_at",sa.DateTime(),server_default=sa.func.now(),nullable=False))
    op.create_index("ix_work_order_repairs_company_id","work_order_repairs",["company_id"])
    op.create_index("ix_work_order_repairs_work_order_id","work_order_repairs",["work_order_id"])
    op.create_table("work_order_repair_items",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False),
        sa.Column("repair_id",sa.Integer(),sa.ForeignKey("work_order_repairs.id",ondelete="CASCADE"),nullable=False),
        sa.Column("item_type",sa.String(10),nullable=False),sa.Column("description",sa.String(250),nullable=False),
        sa.Column("quantity",sa.Numeric(12,3),nullable=False),sa.Column("unit_cost",sa.Numeric(14,2),nullable=False),
        sa.Column("unit_price",sa.Numeric(14,2),nullable=False),sa.Column("line_cost",sa.Numeric(14,2),nullable=False),
        sa.Column("line_total",sa.Numeric(14,2),nullable=False))
    op.create_index("ix_work_order_repair_items_company_id","work_order_repair_items",["company_id"])
    op.create_index("ix_work_order_repair_items_repair_id","work_order_repair_items",["repair_id"])
def downgrade():
    op.drop_table("work_order_repair_items");op.drop_table("work_order_repairs")
