"""equipment documents metadata
Revision ID: 20261002_0017
Revises: 20261002_0016
"""
from alembic import op
import sqlalchemy as sa

revision = "20261002_0017"
down_revision = "20261002_0016"
branch_labels = None
depends_on = None


def upgrade():
    # Solo metadatos y la referencia al objeto. El binario vive en el storage, nunca en
    # MySQL: aca no hay ninguna columna de contenido.
    op.create_table(
        "equipment_documents",
        # Va dentro del create_table y no como create_unique_constraint aparte: SQLite
        # no soporta ALTER de constraints, y la suite de migraciones corre en SQLite.
        sa.UniqueConstraint("storage_key", name="uq_equipment_documents_storage_key"),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("equipment_id", sa.Integer(), sa.ForeignKey("equipment.id", ondelete="CASCADE"), nullable=False),
        # Nullable a proposito: el archivo es del historial del equipo y opcionalmente
        # se vincula a una OT.
        sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("work_orders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        # Generado por el servidor. Nunca es el nombre que manda el frontend.
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("uploaded_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        # Borrado logico: el archivo no se borra de(storage al dar de baja la fila.
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_equipment_documents_company_id", "equipment_documents", ["company_id"])
    op.create_index("ix_equipment_documents_equipment_id", "equipment_documents", ["equipment_id"])
    op.create_index("ix_equipment_documents_work_order_id", "equipment_documents", ["work_order_id"])


def downgrade():
    op.drop_table("equipment_documents")
