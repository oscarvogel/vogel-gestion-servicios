from datetime import datetime
from decimal import Decimal
from sqlalchemy import DateTime,ForeignKey,Integer,Numeric,String,Text,UniqueConstraint,func
from sqlalchemy.orm import Mapped,mapped_column
from app.db.base import Base

class WorkOrderDiagnosis(Base):
    __tablename__="work_order_diagnoses"
    __table_args__=(UniqueConstraint("work_order_id",name="uq_work_order_diagnosis"),)
    id:Mapped[int]=mapped_column(primary_key=True)
    company_id:Mapped[int]=mapped_column(ForeignKey("companies.id",ondelete="CASCADE"),index=True)
    work_order_id:Mapped[int]=mapped_column(ForeignKey("work_orders.id",ondelete="CASCADE"),index=True)
    diagnosis:Mapped[str]=mapped_column(Text,nullable=False)
    technical_notes:Mapped[str|None]=mapped_column(Text)
    diagnosed_by_user_id:Mapped[int]=mapped_column(ForeignKey("users.id"),nullable=False)
    diagnosed_at:Mapped[datetime]=mapped_column(DateTime,server_default=func.now(),nullable=False)
    is_open:Mapped[bool]=mapped_column(nullable=False,default=True)
    revision:Mapped[int]=mapped_column(Integer,nullable=False,default=1)
    updated_at:Mapped[datetime]=mapped_column(DateTime,server_default=func.now(),onupdate=func.now(),nullable=False)

class WorkOrderQuote(Base):
    __tablename__="work_order_quotes"
    __table_args__=(UniqueConstraint("work_order_id","version",name="uq_work_order_quote_version"),)
    id:Mapped[int]=mapped_column(primary_key=True)
    company_id:Mapped[int]=mapped_column(ForeignKey("companies.id",ondelete="CASCADE"),index=True)
    work_order_id:Mapped[int]=mapped_column(ForeignKey("work_orders.id",ondelete="CASCADE"),index=True)
    version:Mapped[int]=mapped_column(Integer,nullable=False)
    status:Mapped[str]=mapped_column(String(20),nullable=False,default="DRAFT")
    notes:Mapped[str|None]=mapped_column(Text)
    diagnosis_snapshot:Mapped[str|None]=mapped_column(Text)
    diagnosis_revision:Mapped[int|None]=mapped_column(Integer)
    subtotal_parts:Mapped[Decimal]=mapped_column(Numeric(14,2),nullable=False,default=0)
    subtotal_labor:Mapped[Decimal]=mapped_column(Numeric(14,2),nullable=False,default=0)
    total:Mapped[Decimal]=mapped_column(Numeric(14,2),nullable=False,default=0)
    created_by_user_id:Mapped[int]=mapped_column(ForeignKey("users.id"),nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime,server_default=func.now(),nullable=False)
    sent_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    decided_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    updated_at:Mapped[datetime]=mapped_column(DateTime,server_default=func.now(),onupdate=func.now(),nullable=False)

class WorkOrderQuoteItem(Base):
    __tablename__="work_order_quote_items"
    id:Mapped[int]=mapped_column(primary_key=True)
    company_id:Mapped[int]=mapped_column(ForeignKey("companies.id",ondelete="CASCADE"),index=True)
    quote_id:Mapped[int]=mapped_column(ForeignKey("work_order_quotes.id",ondelete="CASCADE"),index=True)
    item_type:Mapped[str]=mapped_column(String(10),nullable=False)
    description:Mapped[str]=mapped_column(String(250),nullable=False)
    quantity:Mapped[Decimal]=mapped_column(Numeric(12,3),nullable=False,default=1)
    unit_cost:Mapped[Decimal]=mapped_column(Numeric(14,2),nullable=False,default=0)
    markup_percent:Mapped[Decimal]=mapped_column(Numeric(7,2),nullable=False,default=0)
    unit_price:Mapped[Decimal]=mapped_column(Numeric(14,2),nullable=False,default=0)
    line_total:Mapped[Decimal]=mapped_column(Numeric(14,2),nullable=False,default=0)
