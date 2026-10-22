"""marca, garantia, comisiones, facturas y cierre mensual a marcas (migracion CiberBrain)

Revision ID: 20261022_0024
Revises: 20261004_0023

Todo lo que hace falta para importar el legacy de CiberBrain (SQL Server) y para el
requerimiento nuevo de fin de mes: saber que ordenes estan en garantia y a que empresa
hay que liquidarle.

**El modelo de garantia del legacy no es un campo, son tres tablas encajadas:**

  - ``dbo.Areas``               una fila por area (la marca). ``CodCli`` = a quien se le
                                liquida. ``Empresa`` es texto viejo y desactualizado.
  - ``dbo.TiposTrabajos``       sub-tipos dentro del area (``FUERA``, ``AGU``, ``AAC``, ...).
  - ``dbo.Aux_PoliticasxArea``  la politica real: (Area, TipoTrabajo). ``CS_Trabajos.IDPolitica``
                                apunta aca, no a ``Areas``.

``dbo.CS_PoliticasxArea`` es una vista que une las dos capas y ya resuelve ``Garantia`` y
``Liquidar``. Por eso ``work_areas`` guarda las dos: ``area_name`` + ``policy_code``, con la
garantia ya resuelta en ``warranty_type``.

**El error caro que esta migracion evita:** ``Liquidar`` NO es "a quien se liquida". Es el
ciclo de vida de la OT (0/3 = liquidacion manual, 1 = automatica, 2 = nunca), segun
``proc_CS_EstadoPosible``. Si el cierre filtrara por el, se excluiria justo la garantia, que
es lo que hay que liquidar. "A quien se liquida" es exclusivamente ``Areas.CodCli``.

Por eso ``warranty_settlements`` se registra **por empresa a liquidar y periodo**, y el
desglose garantia / fuera de garantia va en columnas aparte: la inclusion es "la OT tiene
empresa a liquidar", el flag de garantia solo categoriza.

La migracion es **aditiva**: no toca ni renombra columnas existentes, salvo agregar
``work_orders.cost_total`` / ``sale_total`` / ``quoted_total`` (con default 0, asi que las
OTs que ya estan no cambian de valor) y ``customers.seller_id``.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261022_0024"
down_revision = "20261004_0023"
branch_labels = None
depends_on = None


def upgrade():
    # ------------------------------------------------------------------
    # 1. Vendedores y tecnicos (los dos son CC_Usuarios del legacy)
    # ------------------------------------------------------------------
    op.create_table(
        "sellers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("legacy_code", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "legacy_code", name="uq_sellers_company_legacy_code"),
    )
    op.create_index("ix_sellers_company_id", "sellers", ["company_id"])
    op.create_index("ix_sellers_name", "sellers", ["name"])

    op.create_table(
        "technicians",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("legacy_code", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "legacy_code", name="uq_technicians_company_legacy_code"),
    )
    op.create_index("ix_technicians_company_id", "technicians", ["company_id"])
    op.create_index("ix_technicians_name", "technicians", ["name"])

    # ------------------------------------------------------------------
    # 2. Mesas de trabajo (maestro normalizado; en el legacy es texto libre)
    # ------------------------------------------------------------------
    op.create_table(
        "work_benches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("normalized_code", sa.String(length=80), nullable=False),
        sa.Column("legacy_aliases", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "normalized_code", name="uq_work_benches_company_code"),
    )
    op.create_index("ix_work_benches_company_id", "work_benches", ["company_id"])

    # ------------------------------------------------------------------
    # 3. Marcas / areas: las DOS capas del legacy
    # ------------------------------------------------------------------
    op.create_table(
        "work_areas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("area_code", sa.String(length=20), nullable=False),
        sa.Column("area_name", sa.String(length=120), nullable=False),
        # "" = politica principal del area (la que no tiene sub-tipo)
        sa.Column("policy_code", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("policy_description", sa.String(length=150), nullable=True),
        sa.Column("is_principal", sa.Boolean(), nullable=False, server_default=sa.true()),
        # dbo.Areas.CodCli -> customers.id. NULL = el area no se liquida a nadie.
        sa.Column("billing_customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("brand_name", sa.String(length=150), nullable=True),
        # 0 fuera de garantia, 1 garantia de terceros, 2 garantia propia/de service
        sa.Column("warranty_type", sa.Integer(), nullable=False, server_default="0"),
        # ciclo de vida de la OT: 0/3 manual, 1 automatica, 2 nunca
        sa.Column("liquidate_mode", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warranty_period_months", sa.Integer(), nullable=True),
        sa.Column("utility", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("commission_service_mode", sa.Integer(), nullable=True),
        sa.Column("commission_service_pct", sa.Numeric(9, 2), nullable=True),
        sa.Column("commission_product_mode", sa.Integer(), nullable=True),
        sa.Column("commission_product_pct", sa.Numeric(9, 2), nullable=True),
        sa.Column("commission_part_mode", sa.Integer(), nullable=True),
        sa.Column("commission_part_pct", sa.Numeric(9, 2), nullable=True),
        sa.Column("commission_other_mode", sa.Integer(), nullable=True),
        sa.Column("commission_other_pct", sa.Numeric(9, 2), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "area_code", "policy_code", name="uq_work_areas_company_area_policy"),
    )
    op.create_index("ix_work_areas_company_id", "work_areas", ["company_id"])
    op.create_index("ix_work_areas_area_name", "work_areas", ["area_name"])
    op.create_index("ix_work_areas_billing_customer_id", "work_areas", ["billing_customer_id"])

    # ------------------------------------------------------------------
    # 4. Cliente -> vendedor (referencia, no obligatorio)
    # ------------------------------------------------------------------
    # `batch_alter_table` y no `op.add_column` + `op.create_foreign_key` sueltos: SQLite no
    # soporta ALTER de restricciones y revienta la suite con "No support for ALTER of
    # constraints in SQLite dialect". En MySQL el batch emite los ALTER de siempre.
    with op.batch_alter_table("customers") as batch:
        batch.add_column(sa.Column("seller_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_customers_seller_id", "sellers", ["seller_id"], ["id"])

    # ------------------------------------------------------------------
    # 5. La OT: marca, mesa, garantia, importes y referencias del legacy
    # ------------------------------------------------------------------
    # Todo en un solo batch: mismo motivo que arriba (SQLite no altera constraints).
    with op.batch_alter_table("work_orders") as batch:
        batch.add_column(sa.Column("legacy_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("legacy_number", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("work_area_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("work_bench_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("warranty_status", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("legacy_guarantee", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("legacy_policy_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("cost_total", sa.Numeric(19, 6), nullable=False, server_default="0"))
        batch.add_column(sa.Column("sale_total", sa.Numeric(19, 6), nullable=False, server_default="0"))
        batch.add_column(sa.Column("quoted_total", sa.Numeric(19, 6), nullable=True))
        batch.add_column(sa.Column("legacy_invoice_number", sa.String(length=50), nullable=True))
        batch.create_index("ix_work_orders_legacy_id", ["legacy_id"])
        batch.create_index("ix_work_orders_work_area_id", ["work_area_id"])
        batch.create_index("ix_work_orders_warranty_status", ["warranty_status"])
        batch.create_foreign_key("fk_work_orders_work_area_id", "work_areas", ["work_area_id"], ["id"])
        batch.create_foreign_key("fk_work_orders_work_bench_id", "work_benches", ["work_bench_id"], ["id"])

    # ------------------------------------------------------------------
    # 6. Lineas de la OT (dbo.CS_Partes)
    # ------------------------------------------------------------------
    op.create_table(
        "work_order_parts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("part_type", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("item_code", sa.String(length=60), nullable=True),
        sa.Column("quantity", sa.Numeric(19, 6), nullable=False, server_default="0"),
        sa.Column("unit_price", sa.Numeric(19, 6), nullable=False, server_default="0"),
        sa.Column("unit_cost", sa.Numeric(19, 6), nullable=False, server_default="0"),
        sa.Column("currency_code", sa.String(length=10), nullable=True),
        sa.Column("cost_currency_code", sa.String(length=10), nullable=True),
        sa.Column("commission_recipient_type", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("commission_recipient_id", sa.Integer(), sa.ForeignKey("technicians.id"), nullable=True),
        sa.Column("supplier_technician_id", sa.Integer(), sa.ForeignKey("technicians.id"), nullable=True),
        sa.Column("commission_amount", sa.Numeric(19, 6), nullable=False, server_default="0"),
        sa.Column("is_cost_excluded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("legacy_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("work_order_id", "line_no", name="uq_work_order_parts_wo_line"),
    )
    op.create_index("ix_work_order_parts_company_id", "work_order_parts", ["company_id"])
    op.create_index("ix_work_order_parts_work_order_id", "work_order_parts", ["work_order_id"])

    # ------------------------------------------------------------------
    # 7. Quien intervino y cuanto se le comisiona (dbo.Intervienen)
    # ------------------------------------------------------------------
    op.create_table(
        "work_order_technicians",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("technician_id", sa.Integer(), sa.ForeignKey("technicians.id"), nullable=False),
        sa.Column("commission_products", sa.Numeric(19, 6), nullable=False, server_default="0"),
        sa.Column("commission_parts", sa.Numeric(19, 6), nullable=False, server_default="0"),
        sa.Column("commission_services", sa.Numeric(19, 6), nullable=False, server_default="0"),
        sa.Column("commission_other", sa.Numeric(19, 6), nullable=False, server_default="0"),
        sa.Column("settled_at", sa.DateTime(), nullable=True),
        sa.Column("settlement_invoice", sa.String(length=30), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("work_order_id", "technician_id", name="uq_work_order_technicians_wo_tech"),
    )
    op.create_index("ix_work_order_technicians_company_id", "work_order_technicians", ["company_id"])
    op.create_index("ix_work_order_technicians_work_order_id", "work_order_technicians", ["work_order_id"])
    op.create_index("ix_work_order_technicians_technician_id", "work_order_technicians", ["technician_id"])

    # ------------------------------------------------------------------
    # 8. Comision por linea (dbo.CS_ComisionPartexInterviene)
    # ------------------------------------------------------------------
    op.create_table(
        "work_order_part_commissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_order_part_id", sa.Integer(), sa.ForeignKey("work_order_parts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("technician_id", sa.Integer(), sa.ForeignKey("technicians.id"), nullable=False),
        sa.Column("amount", sa.Numeric(19, 6), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("work_order_part_id", "technician_id", name="uq_work_order_part_commissions_part_tech"),
    )
    op.create_index("ix_work_order_part_commissions_company_id", "work_order_part_commissions", ["company_id"])
    op.create_index("ix_work_order_part_commissions_work_order_part_id", "work_order_part_commissions", ["work_order_part_id"])
    op.create_index("ix_work_order_part_commissions_technician_id", "work_order_part_commissions", ["technician_id"])

    # ------------------------------------------------------------------
    # 9. Facturas (dbo.CG_Facturas_Tabla)
    # ------------------------------------------------------------------
    op.create_table(
        "invoices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("number", sa.String(length=30), nullable=False),
        sa.Column("invoice_type", sa.String(length=20), nullable=False, server_default="factura"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="issued"),
        sa.Column("issued_at", sa.DateTime(), nullable=False),
        sa.Column("gross_amount", sa.Numeric(19, 6), nullable=False, server_default="0"),
        sa.Column("net_amount", sa.Numeric(19, 6), nullable=False, server_default="0"),
        sa.Column("total_amount", sa.Numeric(19, 6), nullable=False, server_default="0"),
        sa.Column("tax_id", sa.String(length=15), nullable=True),
        sa.Column("seller_id", sa.Integer(), sa.ForeignKey("sellers.id"), nullable=True),
        sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("work_orders.id"), nullable=True),
        sa.Column("legacy_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "invoice_type", "number", name="uq_invoices_company_type_number"),
    )
    op.create_index("ix_invoices_company_id", "invoices", ["company_id"])
    op.create_index("ix_invoices_customer_id", "invoices", ["customer_id"])
    op.create_index("ix_invoices_status", "invoices", ["status"])
    op.create_index("ix_invoices_issued_at", "invoices", ["issued_at"])
    op.create_index("ix_invoices_work_order_id", "invoices", ["work_order_id"])

    # ------------------------------------------------------------------
    # 10. Cierre mensual a marcas (NO existe en el legacy)
    # ------------------------------------------------------------------
    op.create_table(
        "warranty_settlements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period", sa.Date(), nullable=False),
        sa.Column("billing_customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("works_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_amount", sa.Numeric(19, 6), nullable=False, server_default="0"),
        sa.Column("warranty_works_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warranty_amount", sa.Numeric(19, 6), nullable=False, server_default="0"),
        sa.Column("out_of_warranty_works_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("out_of_warranty_amount", sa.Numeric(19, 6), nullable=False, server_default="0"),
        sa.Column("invoice_number", sa.String(length=30), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("issued_at", sa.DateTime(), nullable=True),
        sa.Column("settled_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "period", "billing_customer_id", name="uq_warranty_settlements_period_customer"),
    )
    op.create_index("ix_warranty_settlements_company_id", "warranty_settlements", ["company_id"])
    op.create_index("ix_warranty_settlements_period", "warranty_settlements", ["period"])
    op.create_index("ix_warranty_settlements_billing_customer_id", "warranty_settlements", ["billing_customer_id"])
    op.create_index("ix_warranty_settlements_status", "warranty_settlements", ["status"])

    op.create_table(
        "warranty_settlement_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("warranty_settlement_id", sa.Integer(), sa.ForeignKey("warranty_settlements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("work_orders.id"), nullable=False),
        sa.Column("work_area_id", sa.Integer(), sa.ForeignKey("work_areas.id"), nullable=True),
        sa.Column("warranty_type", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("amount", sa.Numeric(19, 6), nullable=False, server_default="0"),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("warranty_settlement_id", "work_order_id", name="uq_warranty_settlement_orders_unique"),
    )
    op.create_index("ix_warranty_settlement_orders_company_id", "warranty_settlement_orders", ["company_id"])
    op.create_index("ix_warranty_settlement_orders_warranty_settlement_id", "warranty_settlement_orders", ["warranty_settlement_id"])
    op.create_index("ix_warranty_settlement_orders_work_order_id", "warranty_settlement_orders", ["work_order_id"])


def downgrade():
    op.drop_table("warranty_settlement_orders")
    op.drop_table("warranty_settlements")
    op.drop_table("invoices")
    op.drop_table("work_order_part_commissions")
    op.drop_table("work_order_technicians")
    op.drop_table("work_order_parts")

    with op.batch_alter_table("work_orders") as batch:
        batch.drop_constraint("fk_work_orders_work_bench_id", type_="foreignkey")
        batch.drop_constraint("fk_work_orders_work_area_id", type_="foreignkey")
        batch.drop_index("ix_work_orders_warranty_status")
        batch.drop_index("ix_work_orders_work_area_id")
        batch.drop_index("ix_work_orders_legacy_id")
        batch.drop_column("legacy_invoice_number")
        batch.drop_column("quoted_total")
        batch.drop_column("sale_total")
        batch.drop_column("cost_total")
        batch.drop_column("legacy_policy_id")
        batch.drop_column("legacy_guarantee")
        batch.drop_column("warranty_status")
        batch.drop_column("work_bench_id")
        batch.drop_column("work_area_id")
        batch.drop_column("legacy_number")
        batch.drop_column("legacy_id")

    with op.batch_alter_table("customers") as batch:
        batch.drop_constraint("fk_customers_seller_id", type_="foreignkey")
        batch.drop_column("seller_id")

    op.drop_table("work_areas")
    op.drop_table("work_benches")
    op.drop_table("technicians")
    op.drop_table("sellers")
