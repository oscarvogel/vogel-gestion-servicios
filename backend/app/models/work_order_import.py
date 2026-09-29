from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class WorkOrderImportBatch(Base):
    __tablename__ = "work_order_import_batches"
    __table_args__ = (UniqueConstraint("company_id", "file_sha256", name="uq_wo_import_company_file"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    imported_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class WorkOrderImportRow(Base):
    __tablename__ = "work_order_import_rows"
    __table_args__ = (
        UniqueConstraint("company_id", "batch_id", "source_sheet", "source_row", name="uq_wo_import_source_row"),
        UniqueConstraint("work_order_id", name="uq_wo_import_work_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("work_order_import_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False)
    source_sheet: Mapped[str] = mapped_column(String(80), nullable=False)
    source_row: Mapped[int] = mapped_column(Integer, nullable=False)
    legacy_ficha: Mapped[str | None] = mapped_column(String(120))
    legacy_status: Mapped[str | None] = mapped_column(String(180))
    row_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    legacy_fields: Mapped[dict] = mapped_column(JSON, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)