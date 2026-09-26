"""company personalization parameter catalog and overrides
Revision ID: 20260926_0008
Revises: 20260926_0007
"""
from alembic import op
import sqlalchemy as sa

revision="20260926_0008"
down_revision="20260926_0007"
branch_labels=None
depends_on=None

DEFINITIONS=[
 ("work_orders.use_diagnosis","true","Habilita diagnóstico técnico formal en las órdenes de trabajo.","bool","ordenes"),
 ("work_orders.use_budget","true","Habilita presupuestos dentro del circuito de órdenes de trabajo.","bool","ordenes"),
 ("work_orders.require_budget_approval","true","Habilita el registro de aprobación o rechazo de presupuestos.","bool","ordenes"),
 ("work_orders.show_internal_costs","true","Habilita costos internos y margen para la empresa.","bool","precios"),
 ("work_orders.use_final_tests","true","Habilita el registro de pruebas finales.","bool","ordenes"),
 ("pricing.parts_markup_percent","35","Recargo predeterminado sobre el costo de repuestos. Sugiere precio de venta y puede modificarse en cada OT.","decimal","precios"),
]

def upgrade():
    op.create_table("parameter_definitions",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("parameter",sa.String(100),nullable=False,unique=True),
        sa.Column("default_value",sa.Text(),nullable=False),
        sa.Column("description",sa.String(500),nullable=False),
        sa.Column("data_type",sa.String(20),nullable=False,server_default="string"),
        sa.Column("category",sa.String(60),nullable=False,server_default="general"),
        sa.Column("editable",sa.Boolean(),nullable=False,server_default=sa.true()),
        sa.Column("active",sa.Boolean(),nullable=False,server_default=sa.true()),
        sa.Column("created_at",sa.DateTime(),nullable=False,server_default=sa.func.now()),
        sa.Column("updated_at",sa.DateTime(),nullable=False,server_default=sa.func.now()))
    op.create_table("company_parameters",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False),
        sa.Column("parameter_definition_id",sa.Integer(),sa.ForeignKey("parameter_definitions.id",ondelete="CASCADE"),nullable=False),
        sa.Column("value",sa.Text(),nullable=False),
        sa.Column("created_at",sa.DateTime(),nullable=False,server_default=sa.func.now()),
        sa.Column("updated_at",sa.DateTime(),nullable=False,server_default=sa.func.now()),
        sa.UniqueConstraint("company_id","parameter_definition_id",name="uq_company_parameter"))
    op.create_index("ix_company_parameters_company_id","company_parameters",["company_id"])
    op.create_index("ix_company_parameters_parameter_definition_id","company_parameters",["parameter_definition_id"])
    table=sa.table("parameter_definitions",sa.column("parameter"),sa.column("default_value"),sa.column("description"),sa.column("data_type"),sa.column("category"),sa.column("editable"),sa.column("active"))
    op.bulk_insert(table,[{"parameter":p,"default_value":v,"description":d,"data_type":t,"category":c,"editable":True,"active":True} for p,v,d,t,c in DEFINITIONS])

def downgrade():
    op.drop_index("ix_company_parameters_parameter_definition_id",table_name="company_parameters")
    op.drop_index("ix_company_parameters_company_id",table_name="company_parameters")
    op.drop_table("company_parameters")
    op.drop_table("parameter_definitions")
