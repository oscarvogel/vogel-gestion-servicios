"""work orders reception
Revision ID: 20260925_0005
Revises: 20260925_0004
"""
from alembic import op
import sqlalchemy as sa
revision="20260925_0005";down_revision="20260925_0004";branch_labels=None;depends_on=None

def upgrade():
    op.create_table("work_order_counters",
        sa.Column("company_id",sa.Integer(),primary_key=True),sa.Column("last_number",sa.Integer(),nullable=False,server_default="0"),
        sa.ForeignKeyConstraint(["company_id"],["companies.id"],ondelete="CASCADE"))
    op.create_table("work_orders",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("company_id",sa.Integer(),nullable=False),
        sa.Column("number",sa.Integer(),nullable=False),sa.Column("customer_id",sa.Integer(),nullable=False),
        sa.Column("equipment_id",sa.Integer(),nullable=False),sa.Column("received_at",sa.DateTime(),nullable=False,server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("reported_fault",sa.Text(),nullable=False),sa.Column("physical_condition",sa.Text()),sa.Column("accessories",sa.Text()),
        sa.Column("notes",sa.Text()),sa.Column("received_by_user_id",sa.Integer(),nullable=False),sa.Column("status",sa.String(30),nullable=False,server_default="RECEIVED"),
        sa.Column("created_at",sa.DateTime(),nullable=False,server_default=sa.text("CURRENT_TIMESTAMP")),sa.Column("updated_at",sa.DateTime(),nullable=False,server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["company_id"],["companies.id"],ondelete="CASCADE"),sa.ForeignKeyConstraint(["customer_id"],["customers.id"]),
        sa.ForeignKeyConstraint(["equipment_id"],["equipment.id"]),sa.ForeignKeyConstraint(["received_by_user_id"],["users.id"]),
        sa.UniqueConstraint("company_id","number",name="uq_work_orders_company_number"))
    for name,cols in [("ix_work_orders_company_id",["company_id"]),("ix_work_orders_number",["number"]),("ix_work_orders_customer_id",["customer_id"]),("ix_work_orders_equipment_id",["equipment_id"]),("ix_work_orders_status",["status"])]: op.create_index(name,"work_orders",cols)
    op.create_table("work_order_events",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("company_id",sa.Integer(),nullable=False),sa.Column("work_order_id",sa.Integer(),nullable=False),
        sa.Column("event_type",sa.String(40),nullable=False),sa.Column("status",sa.String(30)),sa.Column("detail",sa.Text()),sa.Column("user_id",sa.Integer(),nullable=False),
        sa.Column("created_at",sa.DateTime(),nullable=False,server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["company_id"],["companies.id"],ondelete="CASCADE"),sa.ForeignKeyConstraint(["work_order_id"],["work_orders.id"],ondelete="CASCADE"),sa.ForeignKeyConstraint(["user_id"],["users.id"]))
    op.create_index("ix_work_order_events_company_id","work_order_events",["company_id"]);op.create_index("ix_work_order_events_work_order_id","work_order_events",["work_order_id"])
    op.create_table("work_order_evidence",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("company_id",sa.Integer(),nullable=False),sa.Column("work_order_id",sa.Integer(),nullable=False),
        sa.Column("evidence_type",sa.String(30),nullable=False,server_default="PHOTO"),sa.Column("storage_key",sa.String(500),nullable=False),sa.Column("description",sa.String(250)),
        sa.Column("created_at",sa.DateTime(),nullable=False,server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["company_id"],["companies.id"],ondelete="CASCADE"),sa.ForeignKeyConstraint(["work_order_id"],["work_orders.id"],ondelete="CASCADE"))
    op.create_index("ix_work_order_evidence_company_id","work_order_evidence",["company_id"]);op.create_index("ix_work_order_evidence_work_order_id","work_order_evidence",["work_order_id"])
    bind=op.get_bind()
    for code,desc in [("work_orders.view","Ver órdenes de trabajo"),("work_orders.manage","Crear y gestionar órdenes de trabajo")]:
        bind.execute(sa.text("INSERT INTO permissions (code,namespace,description) VALUES (:code,'work_orders',:description)"),{"code":code,"description":desc})
        pid=bind.execute(sa.text("SELECT id FROM permissions WHERE code=:code"),{"code":code}).scalar()
        for (rid,) in bind.execute(sa.text("SELECT id FROM roles WHERE name='Administrador' AND active=1")).fetchall():
            bind.execute(sa.text("INSERT INTO role_permissions (role_id,permission_id) VALUES (:rid,:pid)"),{"rid":rid,"pid":pid})

def downgrade():
    bind=op.get_bind()
    for code in ("work_orders.manage","work_orders.view"):
        pid=bind.execute(sa.text("SELECT id FROM permissions WHERE code=:code"),{"code":code}).scalar()
        if pid:
            bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id=:pid"),{"pid":pid});bind.execute(sa.text("DELETE FROM permissions WHERE id=:pid"),{"pid":pid})
    op.drop_table("work_order_evidence");op.drop_table("work_order_events");op.drop_table("work_orders");op.drop_table("work_order_counters")
