from fastapi import APIRouter, Depends, HTTPException
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.core.config import settings
from app.core.security import (
    ALGORITHM,
    create_access_token,
    create_refresh_token,
    verify_password,
)
from app.models.company import Company
from app.models.user import CompanyUser, User

router = APIRouter()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class SelectCompanyRequest(BaseModel):
    company_id: int


def token_response(user_id: int) -> dict[str, str]:
    return {
        "access_token": create_access_token(user_id),
        "refresh_token": create_refresh_token(user_id),
        "token_type": "bearer",
    }


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == str(payload.email)).first()
    if not user or not user.active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return token_response(user.id)


@router.post("/refresh")
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    try:
        token_payload = jwt.decode(
            payload.refresh_token, settings.jwt_secret, algorithms=[ALGORITHM]
        )
        if token_payload.get("type") != "refresh":
            raise ValueError("unexpected token type")
        user_id = int(token_payload["sub"])
    except (JWTError, KeyError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user = db.get(User, user_id)
    if not user or not user.active:
        raise HTTPException(status_code=401, detail="Inactive user")
    return {"access_token": create_access_token(user.id), "token_type": "bearer"}


@router.post("/select-company")
def select_company(
    payload: SelectCompanyRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    company = db.get(Company, payload.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    if not company.active:
        raise HTTPException(status_code=403, detail="Company inactive")
    if not user.is_superadmin:
        membership = (
            db.query(CompanyUser)
            .filter_by(user_id=user.id, company_id=company.id, active=True)
            .first()
        )
        if not membership:
            raise HTTPException(status_code=403, detail="Company access denied")
    return {"access_token": create_access_token(user.id, company.id), "token_type": "bearer"}
