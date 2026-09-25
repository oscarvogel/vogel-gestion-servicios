"""foundation multiempresa"""

from alembic import op
import sqlalchemy as sa

revision = "20260925_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("legal_name", sa.String(200)),
        sa.Column("tax_id", sa.String(30)),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "timezone",
            sa.String(64),
            nullable=False,
            server_default="America/Argentina/Cordoba",
        ),
        sa.Column("locale", sa.String(16), nullable=False, server_default="es-AR"),
        sa.UniqueConstraint("name", name="uq_companies_name"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("full_name", sa.String(150), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_superadmin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "company_users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(50), nullable=False, server_default="ADMIN"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("company_id", "user_id", name="uq_company_user"),
    )
    op.create_index("ix_company_users_company_id", "company_users", ["company_id"])
    op.create_index("ix_company_users_user_id", "company_users", ["user_id"])


def downgrade():
    op.drop_table("company_users")
    op.drop_table("users")
    op.drop_table("companies")
