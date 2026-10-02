from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EquipmentDocument(Base):
    """Metadatos y referencia de un archivo del equipo. El binario vive en el storage.

    Solo metadatos: aca no hay contenido de archivo. MySQL se backs uppea, se replica y
    se consulta todo el tiempo; meterle fotos de video engorda los backups sin ganar
    nada.
    """

    __tablename__ = "equipment_documents"
    __table_args__ = (
        UniqueConstraint("storage_key", name="uq_equipment_documents_storage_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id", ondelete="CASCADE"), index=True)
    # Nullable a proposito: el archivo es del historial del equipo y opcionalmente se
    # vincula a una OT. Los que cuelgan de una OT siguen visibles desde el equipo.
    work_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("work_orders.id", ondelete="SET NULL"), index=True
    )
    # El nombre que subio el usuario es informativo. La clave real la genera el servidor.
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    uploaded_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    # Borrado logico. El archivo no se borra del storage al dar de baja la fila.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    @property
    def size_mb(self) -> float:
        return round(self.size_bytes / 1048576, 2)
