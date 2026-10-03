from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AiUsage(Base):
    """Una fila por pedido al proveedor. Es el registro de uso y de facturacion del adicional.

    Se escribe tambien cuando el pedido falla: si solo se anotaran los exitos, el acumulado
    de consumo miente justo cuando el proveedor esta caido.
    """

    __tablename__ = "ai_usage"
    __table_args__ = (
        # La consulta de cuota y de facturacion es siempre por empresa y por mes.
        Index("ix_ai_usage_company_created", "company_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    # Null cuando fue un job automatico y no una persona.
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    operation: Mapped[str] = mapped_column(String(60), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, default=Decimal("0"))
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # OK | ERROR | SIN_PERMISO | SIN_CUOTA
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OK")
    # Motivo truncado. Nunca la API key ni el cuerpo de la conversacion.
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
