from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class WorkOrderStatus(Base):
    __tablename__ = "work_order_statuses"
    __table_args__ = (UniqueConstraint("company_id","name",name="uq_work_order_status_company_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id",ondelete="CASCADE"),index=True)
    name: Mapped[str] = mapped_column(String(60),nullable=False)
    color: Mapped[str] = mapped_column(String(7),nullable=False,default="#3B82F6")
    sort_order: Mapped[int] = mapped_column(Integer,nullable=False,default=0)
    active: Mapped[bool] = mapped_column(nullable=False,default=True)
    is_initial: Mapped[bool] = mapped_column(nullable=False,default=False)
    is_final: Mapped[bool] = mapped_column(nullable=False,default=False)
    marks_quoted: Mapped[bool] = mapped_column(nullable=False,default=False)
    marks_awaiting_quote_approval: Mapped[bool] = mapped_column(nullable=False,default=False)
    marks_repair: Mapped[bool] = mapped_column(nullable=False,default=False)
    marks_waiting_parts: Mapped[bool] = mapped_column(nullable=False,default=False)
    marks_completed: Mapped[bool] = mapped_column(nullable=False,default=False)
    marks_delivered: Mapped[bool] = mapped_column(nullable=False,default=False)
    # Configuracion de aviso al cliente para este estado. La empresa decide su operatoria:
    # no se hardcodea ningun nombre de estado como disparador.
    notify_whatsapp: Mapped[bool] = mapped_column(nullable=False,default=False)
    notify_email: Mapped[bool] = mapped_column(nullable=False,default=False)
    notifications_active: Mapped[bool] = mapped_column(nullable=False,default=True)
    notification_template: Mapped[str | None] = mapped_column(Text,nullable=True)
    notification_email_subject: Mapped[str | None] = mapped_column(String(200),nullable=True)

class WorkOrderCounter(Base):
    __tablename__ = "work_order_counters"
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True)
    last_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

class WorkOrder(Base):
    __tablename__ = "work_orders"
    __table_args__ = (UniqueConstraint("company_id","number",name="uq_work_orders_company_number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id",ondelete="CASCADE"),index=True)
    number: Mapped[int] = mapped_column(Integer,nullable=False,index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"),index=True)
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id"),index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime,server_default=func.now(),nullable=False)
    expected_delivery_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime)
    reported_fault: Mapped[str] = mapped_column(Text,nullable=False)
    physical_condition: Mapped[str | None] = mapped_column(Text)
    accessories: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    received_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"),nullable=False)
    status: Mapped[str] = mapped_column(String(30),nullable=False,default="RECEIVED",index=True)
    status_id: Mapped[int | None] = mapped_column(ForeignKey("work_order_statuses.id"),nullable=True,index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime,server_default=func.now(),nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime,server_default=func.now(),onupdate=func.now(),nullable=False)

class WorkOrderEvent(Base):
    __tablename__ = "work_order_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id",ondelete="CASCADE"),index=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id",ondelete="CASCADE"),index=True)
    event_type: Mapped[str] = mapped_column(String(40),nullable=False)
    status: Mapped[str | None] = mapped_column(String(30))
    detail: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"),nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime,server_default=func.now(),nullable=False)

class WorkOrderNotification(Base):
    """Cola de salida y auditoria de los avisos al cliente.

    Vive en la misma transaccion que el cambio de estado, asi que un fallo del proveedor
    no puede revertir la OT. El unico (company_id, work_order_event_id, channel) es la
    idempotencia: reprocesar el mismo evento no genera un segundo envio.
    """

    __tablename__ = "work_order_notifications"
    __table_args__ = (
        UniqueConstraint("company_id", "work_order_event_id", "channel", name="uq_wo_notif_event_channel"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id", ondelete="CASCADE"), index=True)
    work_order_event_id: Mapped[int] = mapped_column(ForeignKey("work_order_events.id", ondelete="CASCADE"), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(200), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # PENDING: en la cola, sin entregar a la gateway. QUEUED: la gateway lo acepto (202),
    # que NO es lo mismo que entregado. SENT: entregado. FAILED: error del proveedor o de
    # la gateway. SKIPPED: no se envio por falta del dato de contacto, con el motivo.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class WorkOrderEvidence(Base):
    __tablename__ = "work_order_evidence"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id",ondelete="CASCADE"),index=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id",ondelete="CASCADE"),index=True)
    evidence_type: Mapped[str] = mapped_column(String(30),nullable=False,default="PHOTO")
    storage_key: Mapped[str] = mapped_column(String(500),nullable=False)
    description: Mapped[str | None] = mapped_column(String(250))
    created_at: Mapped[datetime] = mapped_column(DateTime,server_default=func.now(),nullable=False)
