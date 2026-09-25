from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_company_id, get_current_user, get_db
from app.models.company import Company
from app.models.user import CompanyUser, User

router = APIRouter()


@router.get("")
def list_companies(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.is_superadmin:
        companies = db.query(Company).filter_by(active=True).order_by(Company.id).all()
    else:
        companies = (
            db.query(Company)
            .join(CompanyUser, CompanyUser.company_id == Company.id)
            .filter(
                CompanyUser.user_id == user.id,
                CompanyUser.active.is_(True),
                Company.active.is_(True),
            )
            .order_by(Company.id)
            .all()
        )
    return [{"id": company.id, "name": company.name} for company in companies]


@router.get("/current")
def current_company(
    company_id: int = Depends(get_current_company_id), db: Session = Depends(get_db)
):
    company = db.get(Company, company_id)
    return {"id": company.id, "name": company.name}
