from sqlalchemy.orm import DeclarativeBase
class Base(DeclarativeBase):pass
from app.models.company import Company
from app.models.user import User,CompanyUser
