"""diagnosis and quotes for work orders
Revision ID: 20260926_0010
Revises: 20260926_0009
"""
from alembic import op
import sqlalchemy as sa
revision="20260926_0010";down_revision="20260926_0009";branch_labels=None;depends_on=None
def upgrade():
    op.create_table("work_order_diagnoses",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False),sa.Column("work_order_id",sa.Integer(),sa.ForeignKey("work_orders.id",ondelete="CASCADE"),nullable=False),sa.Column("diagnosis",sa.Text(),nullable=False),sa.Column("technical_notes",sa.Text()),sa.Column("diagnosed_by_user_id",sa.Integer(),sa.ForeignKey("users.id"),nullable=False),sa.Column("diagnosed_at",sa.DateTime(),server_default=sa.func.now(),nullable=False),sa.Column("updated_at",sa.DateTime(),server_default=sa.func.now(),nullable=False),sa.UniqueConstraint("work_order_id",name="uq_work_order_diagnosis"))
    op.create_index("ix_work_order_diagnoses_company_id","work_order_diagnoses",["company_id"]);op.create_index("ix_work_order_diagnoses_work_order_id","work_order_diagnoses",["work_order_id"])
    op.create_table("work_order_quotes",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False),sa.Column("work_order_id",sa.Integer(),sa.ForeignKey("work_orders.id",ondelete="CASCADE"),nullable=False),sa.Column("version",sa.Integer(),nullable=False),sa.Column("status",sa.String(20),nullable=False,server_default="DRAFT"),sa.Column("notes",sa.Text()),sa.Column("subtotal_parts",sa.Numeric(14,2),nullable=False,server_default="0"),sa.Column("subtotal_labor",sa.Numeric(14,2),nullable=False,server_default="0"),sa.Column("total",sa.Numeric(14,2),nullable=False,server_default="0"),sa.Column("created_by_user_id",sa.Integer(),sa.ForeignKey("users.id"),nullable=False),sa.Column("created_at",sa.DateTime(),server_default=sa.func.now(),nullable=False),sa.Column("updated_at",sa.DateTime(),server_default=sa.func.now(),nullable=False),sa.UniqueConstraint("work_order_id","version",name="uq_work_order_quote_version"))
    op.create_index("ix_work_order_quotes_company_id","work_order_quotes",["company_id"]);op.create_index("ix_work_order_quotes_work_order_id","work_order_quotes",["work_order_id"])
    op.create_table("work_order_quote_items",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False),sa.Column("quote_id",sa.Integer(),sa.ForeignKey("work_order_quotes.id",ondelete="CASCADE"),nullable=False),sa.Column("item_type",sa.String(10),nullable=False),sa.Column("description",sa.String(250),nullable=False),sa.Column("quantity",sa.Numeric(12,3),nullable=False),sa.Column("unit_cost",sa.Numeric(14,2),nullable=False),sa.Column("markup_percent",sa.Numeric(7,2),nullable=False),sa.Column("unit_price",sa.Numeric(14,2),nullable=False),sa.Column("line_total",sa.Numeric(14,2),nullable=False))
    op.create_index("ix_work_order_quote_items_company_id","work_order_quote_items",["company_id"]);op.create_index("ix_work_order_quote_items_quote_id","work_order_quote_items",["quote_id"])
def downgrade():
    op.drop_index("ix_work_order_quote_items_quote_id",table_name="work_order_quote_items")
    op.drop_index("ix_work_order_quote_items_company_id",table_name="work_order_quote_items")
    op.drop_table("work_order_quote_items")
    op.drop_index("ix_work_order_quotes_work_order_id",table_name="work_order_quotes")
    op.drop_index("ix_work_order_quotes_company_id",table_name="work_order_quotes")
    op.drop_table("work_order_quotes")
    op.drop_index("ix_work_order_diagnoses_work_order_id",table_name="work_order_diagnoses")
    op.drop_index("ix_work_order_diagnoses_company_id",table_name="work_order_diagnoses")
    op.drop_table("work_order_diagnoses")
