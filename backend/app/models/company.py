from sqlalchemy import Boolean,String
from sqlalchemy.orm import Mapped,mapped_column
from app.db.base import Base
class Company(Base):
    __tablename__="companies"
    id:Mapped[int]=mapped_column(primary_key=True)
    name:Mapped[str]=mapped_column(String(150),nullable=False)
    legal_name:Mapped[str|None]=mapped_column(String(200))
    tax_id:Mapped[str|None]=mapped_column(String(30),index=True)
    active:Mapped[bool]=mapped_column(Boolean,default=True,nullable=False)
    timezone:Mapped[str]=mapped_column(String(64),default="America/Argentina/Cordoba")
    locale:Mapped[str]=mapped_column(String(16),default="es-AR")
