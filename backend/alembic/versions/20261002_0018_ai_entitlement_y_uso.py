"""ai entitlement per company and ai usage ledger
Revision ID: 20261002_0018
Revises: 20261002_0017
"""
from alembic import op
import sqlalchemy as sa

revision = "20261002_0018"
down_revision = "20261002_0017"
branch_labels = None
depends_on = None

# Descripcion de las columnas de ai_usage, para que el listado no este atado al modelo.
# provider/model: que se facturo, para poder cambiar de proveedor sin perder el historico.
# operation: que se pidio (chat, herramienta, transcripcion...), no el detalle.
# status: OK | ERROR | SIN_PERMISO | SIN_CUOTA. Un proveedor caido se cuenta como ERROR,
# y por eso el acumulado de consumo no se rompe aunque el servicio este caido.


def upgrade():
    # Las definiciones salen del catalogo de codigo (app/core/parameter_catalog.py) para
    # que la migracion y los tests no puedan divergir. Un test lo verifica.
    import importlib.util, pathlib
    _spec = importlib.util.spec_from_file_location(
        "_parameter_catalog", pathlib.Path(__file__).resolve().parents[2] / "app" / "core" / "parameter_catalog.py"
    )
    _catalog = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_catalog)
    for parameter, default, description, data_type, category, editable in _catalog.AI_PARAMETERS:
        op.execute(
            sa.text(
                "insert into parameter_definitions (parameter, default_value, description, data_type, category, editable, active, created_at, updated_at) "
                # CURRENT_TIMESTAMP y no now(): la suite de migraciones corre sobre SQLite,
                # donde now() no existe.
                "values (:p, :d, :desc, :t, :c, :e, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ).bindparams(p=parameter, d=default, desc=description, t=data_type, c=category, e=editable)
        )

    op.create_table(
        "ai_usage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        # Quien lo disparo. Puede ser null si fue un job automatico.
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model", sa.String(80), nullable=False),
        sa.Column("operation", sa.String(60), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        # Costo estimado en dolares, 6 decimales. Es lo que se factura.
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="OK"),
        # El motivo va truncado, pero nunca la key ni el cuerpo de la conversacion.
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ai_usage_company_id", "ai_usage", ["company_id"])
    op.create_index("ix_ai_usage_created_at", "ai_usage", ["created_at"])
    # Para el acumulado mensual por empresa, que es la consulta de cuota y de facturacion.
    op.create_index("ix_ai_usage_company_created", "ai_usage", ["company_id", "created_at"])


def downgrade():
    op.drop_table("ai_usage")
    for parameter in ("ai.enabled", "ai.monthly_quota_usd", "ai.monthly_request_limit"):
        op.execute(sa.text("delete from parameter_definitions where parameter = :p").bindparams(p=parameter))
