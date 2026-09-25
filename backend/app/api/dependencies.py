from fastapi import Depends, Header, HTTPException
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import ALGORITHM
from app.db.session import SessionLocal
from app.models.company import Company
from app.models.user import CompanyUser, User


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_bearer_token(authorization: str) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return authorization[7:]


def decode_token(token: str, expected_type: str) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
        if payload.get("type") != expected_type:
            raise ValueError("unexpected token type")
        return payload
    except (JWTError, ValueError, KeyError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid token")


def get_current_user(
    authorization: str = Header(default=""), db: Session = Depends(get_db)
) -> User:
    payload = decode_token(get_bearer_token(authorization), "access")
    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.get(User, user_id)
    if not user or not user.active:
        raise HTTPException(status_code=401, detail="Inactive user")
    return user


def get_current_company_id(
    authorization: str = Header(default=""),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> int:
    payload = decode_token(get_bearer_token(authorization), "access")
    try:
        company_id = int(payload["company_id"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=409, detail="Active company required")

    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    if not company.active:
        raise HTTPException(status_code=403, detail="Company inactive")
    if user.is_superadmin:
        return company_id
    membership = (
        db.query(CompanyUser)
        .filter_by(user_id=user.id, company_id=company_id, active=True)
        .first()
    )
    if not membership:
        raise HTTPException(status_code=403, detail="Company access denied")
    return company_id
