from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.base import Base
from app.models.company import Company
from app.models.user import User,CompanyUser
def test_membership_isolation():
    e=create_engine("sqlite+pysqlite:///:memory:");Base.metadata.create_all(e);db=sessionmaker(bind=e)()
    a,b=Company(name="A"),Company(name="B");u=User(email="u@test.local",full_name="U",password_hash="x");db.add_all([a,b,u]);db.flush();db.add(CompanyUser(company_id=a.id,user_id=u.id));db.commit()
    assert db.query(CompanyUser).filter_by(user_id=u.id,company_id=a.id).first()
    assert not db.query(CompanyUser).filter_by(user_id=u.id,company_id=b.id).first()
