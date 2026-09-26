from datetime import datetime
from decimal import Decimal
from sqlalchemy import DateTime,ForeignKey,Integer,Numeric,String,Text,func
from sqlalchemy.orm import Mapped,mapped_column
from app.db.base import Base

class WorkOrderRepair(Base):
    __tablename__="work_order_repairs"
    id:Mapped[int]=mapped_column(primary_key=True)
    company_id:Mapped[int]=mapped_column(ForeignKey("companies.id",ondelete="CASCADE"),index=True)
    work_order_id:Mapped[int]=mapped_column(ForeignKey("work_orders.id",ondelete="CASCADE"),unique=True,index=True)
    technician_user_id:Mapped[int|None]=mapped_column(ForeignKey("users.id"),nullable=True)
    notes:Mapped[str|None]=mapped_column(Text)
    final_tests:Mapped[str|None]=mapped_column(Text)
    started_at:Mapped[datetime]=mapped_column(DateTime,server_default=func.now(),nullable=False)
    finished_at:Mapped[datetime|None]=mapped_column(DateTime)
    created_at:Mapped[datetime]=mapped_column(DateTime,server_default=func.now(),nullable=False)
    updated_at:Mapped[datetime]=mapped_column(DateTime,server_default=func.now(),onupdate=func.now(),nullable=False)

class WorkOrderRepairItem(Base):
    __tablename__="work_order_repair_items"
    id:Mapped[int]=mapped_column(primary_key=True)
    company_id:Mapped[int]=mapped_column(ForeignKey("companies.id",ondelete="CASCADE"),index=True)
    repair_id:Mapped[int]=mapped_column(ForeignKey("work_order_repairs.id",ondelete="CASCADE"),index=True)
    item_type:Mapped[str]=mapped_column(String(10),nullable=False)
    description:Mapped[str]=mapped_column(String(250),nullable=False)
    quantity:Mapped[Decimal]=mapped_column(Numeric(12,3),nullable=False,default=1)
    unit_cost:Mapped[Decimal]=mapped_column(Numeric(14,2),nullable=False,default=0)
    unit_price:Mapped[Decimal]=mapped_column(Numeric(14,2),nullable=False,default=0)
    line_cost:Mapped[Decimal]=mapped_column(Numeric(14,2),nullable=False,default=0)
    line_total:Mapped[Decimal]=mapped_column(Numeric(14,2),nullable=False,default=0)
