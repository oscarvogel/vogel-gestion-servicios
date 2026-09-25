"""add roles, permissions, audit columns

Revision ID: 20260925_0002
Revises: 20260925_0001
Create Date: 2026-09-25 11:14:47.831955
"""
from alembic import op
import sqlalchemy as sa


revision = "20260925_0002"
down_revision = "20260925_0001"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    ts_default = (
        sa.text("(CURRENT_TIMESTAMP)")
        if is_sqlite
        else sa.text("CURRENT_TIMESTAMP")
    )

    # --- roles / permissions / role_permissions / company_user_roles ---
    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("namespace", sa.String(length=40), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_permissions_code"),
    )
    op.create_index("ix_permissions_code", "permissions", ["code"], unique=True)
    op.create_index("ix_permissions_namespace", "permissions", ["namespace"], unique=False)

    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "name", name="uq_roles_company_name"),
    )
    op.create_index("ix_roles_company_id", "roles", ["company_id"], unique=False)

    op.create_table(
        "company_user_roles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_user_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(
            ["company_user_id"], ["company_users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_user_id", "role_id", name="uq_company_user_role"),
    )
    op.create_index(
        "ix_company_user_roles_company_user_id",
        "company_user_roles",
        ["company_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_company_user_roles_role_id",
        "company_user_roles",
        ["role_id"],
        unique=False,
    )

    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("permission_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
    )

    # --- audit columns & company extra fields ---
    op.add_column("companies", sa.Column("slug", sa.String(length=80), nullable=True))
    op.add_column("companies", sa.Column("email", sa.String(length=255), nullable=True))
    op.add_column("companies", sa.Column("phone", sa.String(length=60), nullable=True))
    op.add_column("companies", sa.Column("address", sa.String(length=250), nullable=True))
    op.add_column("companies", sa.Column("notes", sa.String(length=500), nullable=True))
    op.add_column(
        "companies",
        sa.Column("created_at", sa.DateTime(), server_default=ts_default, nullable=False),
    )
    op.add_column(
        "companies",
        sa.Column("updated_at", sa.DateTime(), server_default=ts_default, nullable=False),
    )
    op.create_index("ix_companies_slug", "companies", ["slug"], unique=False)
    op.create_index("ix_companies_tax_id", "companies", ["tax_id"], unique=False)

    op.add_column(
        "company_users",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "company_users",
        sa.Column("created_at", sa.DateTime(), server_default=ts_default, nullable=False),
    )
    op.add_column(
        "company_users",
        sa.Column("updated_at", sa.DateTime(), server_default=ts_default, nullable=False),
    )

    op.add_column(
        "users",
        sa.Column("created_at", sa.DateTime(), server_default=ts_default, nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("updated_at", sa.DateTime(), server_default=ts_default, nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)


def downgrade():
    op.drop_index("ix_users_email", table_name="users")
    op.drop_column("users", "updated_at")
    op.drop_column("users", "created_at")
    op.drop_column("company_users", "updated_at")
    op.drop_column("company_users", "created_at")
    op.drop_column("company_users", "is_admin")
    op.drop_index("ix_companies_tax_id", table_name="companies")
    op.drop_index("ix_companies_slug", table_name="companies")
    op.drop_column("companies", "updated_at")
    op.drop_column("companies", "created_at")
    op.drop_column("companies", "notes")
    op.drop_column("companies", "address")
    op.drop_column("companies", "phone")
    op.drop_column("companies", "email")
    op.drop_column("companies", "slug")
    op.drop_table("role_permissions")
    op.drop_index("ix_company_user_roles_role_id", table_name="company_user_roles")
    op.drop_index("ix_company_user_roles_company_user_id", table_name="company_user_roles")
    op.drop_table("company_user_roles")
    op.drop_index("ix_roles_company_id", table_name="roles")
    op.drop_table("roles")
    op.drop_index("ix_permissions_namespace", table_name="permissions")
    op.drop_index("ix_permissions_code", table_name="permissions")
    op.drop_table("permissions")