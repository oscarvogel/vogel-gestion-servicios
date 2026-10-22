from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WorkOrderPart(Base):
    """Linea de la OT (legacy: ``dbo.CS_Partes``).

    ``unit_price`` es el precio de venta al cliente final y ``unit_cost`` el costo real.
    El legacy infla el precio en garantia de terceros (``@Unitario = @Costo * (1 + @PorcUtil/100)``),
    por eso ``VentaTotal`` sale aproximadamente el doble que ``CostoTotal``.

    ``commission_recipient_type`` traduce ``CS_Partes.LiquidaComision``:
      0 = sin comision, -1 = se divide entre todos los que intervinieron,
      -2 = el responsable de la OT, -3 = el proveedor que dio la parte.
    Un valor > 0 es el ``legacy_code`` de un tecnico concreto.
    """

    __tablename__ = "work_order_parts"
    __table_args__ = (
        UniqueConstraint("work_order_id", "line_no", name="uq_work_order_parts_wo_line"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    work_order_id: Mapped[int] = mapped_column(
        ForeignKey("work_orders.id", ondelete="CASCADE"), index=True
    )
    line_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # legacy CS_Partes.Tipo: 0 producto, 1 repuesto, 2 servicio, 3 otros
    part_type: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    item_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    quantity: Mapped[float] = mapped_column(Numeric(19, 6), nullable=False, default=0)
    unit_price: Mapped[float] = mapped_column(Numeric(19, 6), nullable=False, default=0)
    unit_cost: Mapped[float] = mapped_column(Numeric(19, 6), nullable=False, default=0)
    currency_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    cost_currency_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    commission_recipient_type: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    commission_recipient_id: Mapped[int | None] = mapped_column(
        ForeignKey("technicians.id"), nullable=True
    )
    supplier_technician_id: Mapped[int | None] = mapped_column(
        ForeignKey("technicians.id"), nullable=True
    )
    commission_amount: Mapped[float] = mapped_column(Numeric(19, 6), nullable=False, default=0)
    is_cost_excluded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    legacy_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class WorkOrderTechnician(Base):
    """Quien intervino en la OT y cuanto se le comisiona (legacy: ``dbo.Intervienen``).

    Se migra el importe **ya calculado** por el legacy, no se recalcula: cambiar un
    porcentaje no se puede hacer todavia en el sistema nuevo.
    """

    __tablename__ = "work_order_technicians"
    __table_args__ = (
        UniqueConstraint("work_order_id", "technician_id", name="uq_work_order_technicians_wo_tech"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    work_order_id: Mapped[int] = mapped_column(
        ForeignKey("work_orders.id", ondelete="CASCADE"), index=True
    )
    technician_id: Mapped[int] = mapped_column(ForeignKey("technicians.id"), index=True)
    commission_products: Mapped[float] = mapped_column(Numeric(19, 6), nullable=False, default=0)
    commission_parts: Mapped[float] = mapped_column(Numeric(19, 6), nullable=False, default=0)
    commission_services: Mapped[float] = mapped_column(Numeric(19, 6), nullable=False, default=0)
    commission_other: Mapped[float] = mapped_column(Numeric(19, 6), nullable=False, default=0)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    settlement_invoice: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class WorkOrderPartCommission(Base):
    """Comision de una linea para un tecnico (legacy: ``dbo.CS_ComisionPartexInterviene``).

    El legacy lo guarda por ``CS_Partes.ID`` + persona. Aca cuelga de la linea ya importada.
    """

    __tablename__ = "work_order_part_commissions"
    __table_args__ = (
        UniqueConstraint(
            "work_order_part_id", "technician_id", name="uq_work_order_part_commissions_part_tech"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    work_order_part_id: Mapped[int] = mapped_column(
        ForeignKey("work_order_parts.id", ondelete="CASCADE"), index=True
    )
    technician_id: Mapped[int] = mapped_column(ForeignKey("technicians.id"), index=True)
    amount: Mapped[float] = mapped_column(Numeric(19, 6), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
