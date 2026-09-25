from fastapi import APIRouter, Depends, HTTPException
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.api.dependencies import (
    _user_permissions_for_company,
    decode_token,
    get_bearer_token,
    get_current_user,
    get_db,
)
from app.api.v1.schemas import (
    CompanyOption,
    LoginRequest,
    MeResponse,
    MembershipSummary,
    RefreshRequest,
    SelectCompanyRequest,
    TokenBundle,
)
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


@router.post("/login", response_model=TokenBundle)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == str(payload.email)).first()
    if not user or not user.active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return TokenBundle(
        access_token=create_access_token(user.id, superadmin=user.is_superadmin),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=TokenBundle)
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
    return TokenBundle(
        access_token=create_access_token(user.id, superadmin=user.is_superadmin)
    )


@router.post("/select-company", response_model=TokenBundle)
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
    return TokenBundle(
        access_token=create_access_token(
            user.id, company.id, superadmin=user.is_superadmin
        )
    )


@router.post("/leave-company", response_model=TokenBundle)
def leave_company(user: User = Depends(get_current_user)):
    """Devuelve al usuario al modo plataforma (sin empresa activa)."""
    return TokenBundle(
        access_token=create_access_token(user.id, superadmin=user.is_superadmin)
    )


@router.get("/me", response_model=MeResponse)
def me(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    memberships_q = (
        db.query(CompanyUser, Company)
        .join(Company, Company.id == CompanyUser.company_id)
        .filter(CompanyUser.user_id == user.id)
        .all()
    )
    memberships = [
        MembershipSummary(
            company_id=company.id,
            company_name=company.name,
            company_slug=company.slug,
            company_active=company.active,
            is_admin=membership.is_admin,
            role=membership.role,
            active=membership.active,
        )
        for membership, company in memberships_q
    ]
    permissions: set[str] = set()
    if user.is_superadmin:
        permissions.update(_platform_permissions())
    else:
        for membership, _ in memberships_q:
            if membership.active:
                permissions.update(_user_permissions_for_company(db, user.id, membership.company_id))

    return MeResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_superadmin=user.is_superadmin,
        active=user.active,
        memberships=memberships,
        permissions=sorted(permissions),
    )


@router.get("/companies", response_model=list[CompanyOption])
def my_companies(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Empresas disponibles para el usuario (selector de empresa)."""
    if user.is_superadmin:
        rows = (
            db.query(Company)
            .order_by(Company.active.desc(), Company.name)
            .all()
        )
        return [
            CompanyOption(
                id=row.id,
                name=row.name,
                slug=row.slug,
                active=row.active,
                is_admin=False,
            )
            for row in rows
        ]
    rows = (
        db.query(Company, CompanyUser)
        .join(CompanyUser, CompanyUser.company_id == Company.id)
        .filter(CompanyUser.user_id == user.id, CompanyUser.active.is_(True))
        .order_by(Company.active.desc(), Company.name)
        .all()
    )
    return [
        CompanyOption(
            id=company.id,
            name=company.name,
            slug=company.slug,
            active=company.active,
            is_admin=membership.is_admin,
        )
        for company, membership in rows
    ]


def _platform_permissions() -> set[str]:
    """Permisos concedidos al SuperAdmin independientemente de membresía."""
    from app.core.permissions import SUPERADMIN_PERMISSIONS

    return set(SUPERADMIN_PERMISSIONS)