"""tenant configurable work order statuses
Revision ID: 20260925_0006
Revises: 20260925_0005
"""
from alembic import op
import sqlalchemy as sa
revision="20260925_0006";down_revision="20260925_0005";branch_labels=None;depends_on=None

DEFAULTS=[("Recibido","#10B981",10,1,0),("En diagnóstico","#3B82F6",20,0,0),("Presupuestado","#8B5CF6",30,0,0),("Esperando aprobación","#F59E0B",40,0,0),("En reparación","#06B6D4",50,0,0),("Esperando repuesto","#F97316",60,0,0),("Listo","#22C55E",70,0,0),("Entregado","#64748B",80,0,1)]

def upgrade():
    op.create_table("work_order_statuses",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("company_id",sa.Integer(),nullable=False),
        sa.Column("name",sa.String(60),nullable=False),sa.Column("color",sa.String(7),nullable=False),
        sa.Column("sort_order",sa.Integer(),nullable=False,server_default="0"),sa.Column("active",sa.Boolean(),nullable=False,server_default=sa.true()),
        sa.Column("is_initial",sa.Boolean(),nullable=False,server_default=sa.false()),sa.Column("is_final",sa.Boolean(),nullable=False,server_default=sa.false()),
        sa.ForeignKeyConstraint(["company_id"],["companies.id"],ondelete="CASCADE"),sa.UniqueConstraint("company_id","name",name="uq_work_order_status_company_name"))
    op.create_index("ix_work_order_statuses_company_id","work_order_statuses",["company_id"])
    with op.batch_alter_table("work_orders") as batch:
        batch.add_column(sa.Column("status_id",sa.Integer(),nullable=True))
        batch.create_foreign_key("fk_work_orders_status_id","work_order_statuses",["status_id"],["id"])
        batch.create_index("ix_work_orders_status_id",["status_id"])
    bind=op.get_bind()
    for (cid,) in bind.execute(sa.text("SELECT id FROM companies")).fetchall():
        for name,color,order,initial,final in DEFAULTS:
            bind.execute(sa.text("INSERT INTO work_order_statuses (company_id,name,color,sort_order,active,is_initial,is_final) VALUES (:c,:n,:color,:o,1,:i,:f)"),
                         {"c":cid,"n":name,"color":color,"o":order,"i":initial,"f":final})
        sid=bind.execute(sa.text("SELECT id FROM work_order_statuses WHERE company_id=:c AND is_initial=1"),{"c":cid}).scalar()
        bind.execute(sa.text("UPDATE work_orders SET status_id=:s WHERE company_id=:c AND status_id IS NULL"),{"s":sid,"c":cid})

def downgrade():
    with op.batch_alter_table("work_orders") as batch:
        batch.drop_constraint("fk_work_orders_status_id",type_="foreignkey")
        batch.drop_index("ix_work_orders_status_id")
        batch.drop_column("status_id")
    op.drop_index("ix_work_order_statuses_company_id",table_name="work_order_statuses")
    op.drop_table("work_order_statuses")
