"""work order import provenance
Revision ID: 20260929_0013
Revises: 20260927_0012
"""
from alembic import op
import sqlalchemy as sa

revision = "20260929_0013"
down_revision = "20260927_0012"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "work_order_import_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("imported_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "file_sha256", name="uq_wo_import_company_file"),
    )
    op.create_index("ix_work_order_import_batches_company_id", "work_order_import_batches", ["company_id"])
    op.create_table(
        "work_order_import_rows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("work_order_import_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_sheet", sa.String(80), nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=False),
        sa.Column("legacy_ficha", sa.String(120)),
        sa.Column("legacy_status", sa.String(180)),
        sa.Column("row_sha256", sa.String(64), nullable=False),
        sa.Column("legacy_fields", sa.JSON(), nullable=False),
        sa.Column("imported_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "batch_id", "source_sheet", "source_row", name="uq_wo_import_source_row"),
        sa.UniqueConstraint("work_order_id", name="uq_wo_import_work_order"),
    )
    op.create_index("ix_work_order_import_rows_company_id", "work_order_import_rows", ["company_id"])
    op.create_index("ix_work_order_import_rows_batch_id", "work_order_import_rows", ["batch_id"])


def downgrade():
    op.drop_table("work_order_import_rows")
    op.drop_table("work_order_import_batches")