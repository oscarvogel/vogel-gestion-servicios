from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WarrantySettlement(Base):
    """Cierre mensual a marcas: lo que hay que liquidarle a cada empresa.

    No existe en el legacy. Alli el cierre se hacia a mano y no quedaba registrado: las OTs
    en garantia nunca tienen ``Liquidada = 1`` porque su politica tiene ``Liquidar = 0``, y
    esa bandera es del ciclo de vida de la OT, no del cierre (ver ``app.models.work_area``).

    Una fila por (empresa, periodo). El detalle esta en ``WarrantySettlementOrder``.

    **El criterio de inclusion** es "la OT tiene empresa a liquidar" (``work_areas.billing_customer_id``
    no nulo), no "la OT es garantia". El flag de garantia se usa para el desglose, no para
    dejar fuera OTs: en 2020+ son 6.418 OTs con empresa (73,2 M de costo), de las cuales
    2.853 son garantia estricta (25,4 M) y 3.565 son trabajo fuera de garantia que las
    marcas igual pagan (47,8 M).
    """

    __tablename__ = "warranty_settlements"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "period", "billing_customer_id", name="uq_warranty_settlements_period_customer"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    # primer dia del mes liquidado
    period: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # la empresa a liquidar
    billing_customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    # DRAFT -> ISSUED -> SETTLED (o CANCELLED)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)
    works_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_amount: Mapped[float] = mapped_column(Numeric(19, 6), nullable=False, default=0)
    # desglose por tipo de garantia (1 = garantia de terceros, 0 = fuera de garantia)
    warranty_works_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warranty_amount: Mapped[float] = mapped_column(Numeric(19, 6), nullable=False, default=0)
    out_of_warranty_works_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    out_of_warranty_amount: Mapped[float] = mapped_column(Numeric(19, 6), nullable=False, default=0)
    invoice_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class WarrantySettlementOrder(Base):
    """Una OT dentro de un cierre. Es el detalle que se revisa antes de emitir."""

    __tablename__ = "warranty_settlement_orders"
    __table_args__ = (
        UniqueConstraint(
            "warranty_settlement_id", "work_order_id", name="uq_warranty_settlement_orders_unique"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    warranty_settlement_id: Mapped[int] = mapped_column(
        ForeignKey("warranty_settlements.id", ondelete="CASCADE"), index=True
    )
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id"), index=True)
    work_area_id: Mapped[int | None] = mapped_column(ForeignKey("work_areas.id"), nullable=True)
    # 1 = garantia, 0 = fuera de garantia
    warranty_type: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    amount: Mapped[float] = mapped_column(Numeric(19, 6), nullable=False, default=0)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
