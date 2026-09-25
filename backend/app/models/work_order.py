from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

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
    reported_fault: Mapped[str] = mapped_column(Text,nullable=False)
    physical_condition: Mapped[str | None] = mapped_column(Text)
    accessories: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    received_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"),nullable=False)
    status: Mapped[str] = mapped_column(String(30),nullable=False,default="RECEIVED",index=True)
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

class WorkOrderEvidence(Base):
    __tablename__ = "work_order_evidence"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id",ondelete="CASCADE"),index=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id",ondelete="CASCADE"),index=True)
    evidence_type: Mapped[str] = mapped_column(String(30),nullable=False,default="PHOTO")
    storage_key: Mapped[str] = mapped_column(String(500),nullable=False)
    description: Mapped[str | None] = mapped_column(String(250))
    created_at: Mapped[datetime] = mapped_column(DateTime,server_default=func.now(),nullable=False)
