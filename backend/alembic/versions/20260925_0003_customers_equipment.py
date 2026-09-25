"""customers and equipment multi-tenant
Revision ID: 20260925_0003
Revises: 20260925_0002
"""
from alembic import op
import sqlalchemy as sa
revision = "20260925_0003"
down_revision = "20260925_0002"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("customers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("customer_type", sa.String(20), nullable=False, server_default="PERSON"),
        sa.Column("name", sa.String(180), nullable=False), sa.Column("document", sa.String(30)),
        sa.Column("phone", sa.String(60)), sa.Column("whatsapp", sa.String(60)), sa.Column("email", sa.String(255)),
        sa.Column("address", sa.String(250)), sa.Column("notes", sa.Text()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("company_id", "document", name="uq_customers_company_document"))
    op.create_index("ix_customers_company_id", "customers", ["company_id"])
    op.create_index("ix_customers_name", "customers", ["name"]); op.create_index("ix_customers_phone", "customers", ["phone"])
    op.create_table("equipment",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False), sa.Column("category", sa.String(80), nullable=False),
        sa.Column("brand", sa.String(100)), sa.Column("model", sa.String(120)), sa.Column("serial_number", sa.String(120)),
        sa.Column("description", sa.String(300)), sa.Column("notes", sa.Text()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"))
    op.create_index("ix_equipment_company_id", "equipment", ["company_id"]); op.create_index("ix_equipment_customer_id", "equipment", ["customer_id"])
    op.create_index("ix_equipment_serial_number", "equipment", ["serial_number"])

def downgrade():
    op.drop_table("equipment"); op.drop_table("customers")
