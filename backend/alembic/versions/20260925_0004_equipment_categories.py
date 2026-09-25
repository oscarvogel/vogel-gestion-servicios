"""equipment categories
Revision ID: 20260925_0004
Revises: 20260925_0003
"""
from alembic import op
import sqlalchemy as sa
revision="20260925_0004"
down_revision="20260925_0003"
branch_labels=None
depends_on=None

def upgrade():
    bind=op.get_bind()
    inspector=sa.inspect(bind)
    tables=set(inspector.get_table_names())
    if "equipment_categories" not in tables:
        op.create_table("equipment_categories",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("company_id",sa.Integer(),nullable=False),
        sa.Column("name",sa.String(80),nullable=False),
        sa.Column("active",sa.Boolean(),nullable=False,server_default=sa.true()),
        sa.Column("created_at",sa.DateTime(),nullable=False,server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at",sa.DateTime(),nullable=False,server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["company_id"],["companies.id"],ondelete="CASCADE"),
            sa.UniqueConstraint("company_id","name",name="uq_equipment_categories_company_name"))
        op.create_index("ix_equipment_categories_company_id","equipment_categories",["company_id"])
    equipment_columns={column["name"] for column in sa.inspect(bind).get_columns("equipment")}
    rows=bind.execute(sa.text("SELECT DISTINCT company_id, category FROM equipment WHERE category IS NOT NULL AND category <> ''")).fetchall()
    for company_id,name in rows:
        bind.execute(sa.text("INSERT INTO equipment_categories (company_id,name,active) VALUES (:company_id,:name,1)"),{"company_id":company_id,"name":name})
    if "category_id" not in equipment_columns:
        with op.batch_alter_table("equipment") as batch:
            batch.add_column(sa.Column("category_id",sa.Integer(),nullable=True))
            batch.create_index("ix_equipment_category_id",["category_id"])
            batch.create_foreign_key("fk_equipment_category","equipment_categories",["category_id"],["id"])
    equipment_columns={column["name"] for column in sa.inspect(bind).get_columns("equipment")}
    if "category" in equipment_columns:
        bind.execute(sa.text("UPDATE equipment SET category_id=(SELECT ec.id FROM equipment_categories ec WHERE ec.company_id=equipment.company_id AND ec.name=equipment.category LIMIT 1) WHERE category_id IS NULL"))
        with op.batch_alter_table("equipment") as batch:
            batch.alter_column("category_id",nullable=False)
            batch.drop_column("category")

def downgrade():
    with op.batch_alter_table("equipment") as batch:
        batch.add_column(sa.Column("category",sa.String(80),nullable=True))
    bind=op.get_bind()
    bind.execute(sa.text("UPDATE equipment SET category=(SELECT ec.name FROM equipment_categories ec WHERE ec.id=equipment.category_id)"))
    with op.batch_alter_table("equipment") as batch:
        batch.alter_column("category",nullable=False)
        batch.drop_constraint("fk_equipment_category",type_="foreignkey")
        batch.drop_index("ix_equipment_category_id")
        batch.drop_column("category_id")
    op.drop_table("equipment_categories")
