from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Invoice(Base):
    """Factura (legacy: ``dbo.CG_Facturas_Tabla``).

    Ojo con el numero: en el legacy es ``A0004-00002010`` = grupo + punto de venta + talonario
    de 8, **sin reinicio anual**. La clave real es ``(TipoDoc, Numero)``, asi que el unico
    del destino incluye el tipo.

    ``issued_at`` es ``CG_Facturas_Tabla.Fecha`` y **no** ``FechaComprobante``: la fecha del
    comprobante coincide con la de la tabla en 1 de 3.494 casos.

    La tabla del legacy termina el 2021-06-30. Despues, el numero de factura paso a
    ``CS_Trabajos.Comprobante``, que es **polimorfico**: 4.699 filas con formato de factura
    (que no existen en la tabla de facturas) y textos como ``STOCK``, ``NO CORRESPONDE`` o
    ``FALTA FACTURA``. Eso se conserva en ``work_orders.legacy_invoice_number``.
    """

    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "invoice_type", "number", name="uq_invoices_company_type_number"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    number: Mapped[str] = mapped_column(String(30), nullable=False)
    invoice_type: Mapped[str] = mapped_column(String(20), nullable=False, default="factura")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="issued", index=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    gross_amount: Mapped[float] = mapped_column(Numeric(19, 6), nullable=False, default=0)
    net_amount: Mapped[float] = mapped_column(Numeric(19, 6), nullable=False, default=0)
    total_amount: Mapped[float] = mapped_column(Numeric(19, 6), nullable=False, default=0)
    tax_id: Mapped[str | None] = mapped_column(String(15), nullable=True)
    seller_id: Mapped[int | None] = mapped_column(ForeignKey("sellers.id"), nullable=True)
    work_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("work_orders.id"), nullable=True, index=True
    )
    legacy_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
