from fastapi import Depends, Header, HTTPException, status
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import ALGORITHM
from app.db.session import SessionLocal
from app.models.company import Company
from app.models.role import CompanyUserRole, Permission, Role, role_permissions
from app.models.user import CompanyUser, User


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_bearer_token(authorization: str) -> str:
    if not authorization or not authorization.startswith("Bearer "):
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


def require_superadmin(user: User = Depends(get_current_user)) -> User:
    if not user.is_superadmin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="SuperAdmin required")
    return user


def _ensure_company_active(company: Company | None) -> Company:
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    if not company.active:
        raise HTTPException(status_code=403, detail="Company inactive")
    return company


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

    company = _ensure_company_active(db.get(Company, company_id))
    if user.is_superadmin:
        return company.id
    membership = (
        db.query(CompanyUser)
        .filter_by(user_id=user.id, company_id=company.id, active=True)
        .first()
    )
    if not membership:
        raise HTTPException(status_code=403, detail="Company access denied")
    return company.id


def get_current_company(
    company_id: int = Depends(get_current_company_id), db: Session = Depends(get_db)
) -> Company:
    return _ensure_company_active(db.get(Company, company_id))


def _user_permissions_for_company(db: Session, user_id: int, company_id: int) -> set[str]:
    """Devuelve el set de códigos de permiso efectivos para el usuario en la empresa."""
    rows = (
        db.query(Permission.code)
        .join(role_permissions, role_permissions.c.permission_id == Permission.id)
        .join(Role, Role.id == role_permissions.c.role_id)
        .join(CompanyUserRole, CompanyUserRole.role_id == Role.id)
        .join(CompanyUser, CompanyUser.id == CompanyUserRole.company_user_id)
        .filter(
            CompanyUser.user_id == user_id,
            CompanyUser.company_id == company_id,
            CompanyUser.active.is_(True),
            CompanyUserRole.active.is_(True),
            Role.active.is_(True),
        )
        .all()
    )
    return {code for (code,) in rows}


def user_has_permission(db: Session, user: User, company_id: int, permission_code: str) -> bool:
    if user.is_superadmin:
        return True
    return permission_code in _user_permissions_for_company(db, user.id, company_id)


def require_permission(permission_code: str):
    """Dependencia que valida membresía + permiso a nivel empresa.

    SuperAdmin siempre pasa el control (permisos platform-wide).
    El resto de los usuarios deben tener un company_id válido en el token
    y el permiso dentro de esa empresa.
    """

    def _checker(
        authorization: str = Header(default=""),
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if user.is_superadmin:
            return user
        company_id = get_current_company_id(
            authorization=authorization, user=user, db=db
        )
        if not user_has_permission(db, user, company_id, permission_code):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {permission_code}",
            )
        return user

    return _checker


def require_company_admin_or_superadmin(
    user: User = Depends(get_current_user),
    company_id: int = Depends(get_current_company_id),
    db: Session = Depends(get_db),
) -> User:
    """Permite operar si el usuario es SuperAdmin o admin explícito de la empresa."""
    if user.is_superadmin:
        return user
    membership = (
        db.query(CompanyUser)
        .filter_by(user_id=user.id, company_id=company_id, active=True)
        .first()
    )
    if not membership or not membership.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Company admin required"
        )
    return user