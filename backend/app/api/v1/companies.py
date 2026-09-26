from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_current_company_id,
    get_current_user,
    get_db,
    require_superadmin,
)
from app.api.v1.schemas import (
    CompanyCreate,
    CompanyDetail,
    CompanyListResponse,
    CompanyRead,
    CompanyUpdate,
    TokenBundle,
)
from app.core.security import create_access_token, hash_password
from app.models.company import Company
from app.models.role import Permission, Role
from app.models.user import CompanyUser, User

router = APIRouter()


def _serialize(company: Company, user_count: int = 0) -> CompanyRead:
    return CompanyRead(
        id=company.id,
        name=company.name,
        legal_name=company.legal_name,
        tax_id=company.tax_id,
        slug=company.slug,
        email=company.email,
        phone=company.phone,
        address=company.address,
        notes=company.notes,
        timezone=company.timezone,
        locale=company.locale,
        active=company.active,
        created_at=company.created_at,
        updated_at=company.updated_at,
        user_count=user_count,
    )


# IMPORTANTE: las rutas estáticas (current, enter) deben declararse ANTES
# de las rutas con path parameter /{company_id} para no ser capturadas por
# la conversión a int (que devolvería 422).


@router.get("/current", response_model=CompanyRead)
def current_company(
    company_id: int = Depends(get_current_company_id), db: Session = Depends(get_db)
):
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.")
    return _serialize(company, user_count=_count_users(db, company.id))


@router.post("/{company_id}/enter", response_model=TokenBundle)
def enter_company(
    company_id: int,
    user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.")
    if not company.active:
        raise HTTPException(status_code=403, detail="La empresa está inactiva.")
    return TokenBundle(
        access_token=create_access_token(
            user.id, company.id, superadmin=user.is_superadmin
        )
    )


@router.get("", response_model=CompanyListResponse)
def list_companies(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: Optional[str] = None,
    active: Optional[bool] = None,
):
    base = db.query(Company)
    if user.is_superadmin:
        query = base
    else:
        query = base.join(CompanyUser, CompanyUser.company_id == Company.id).filter(
            CompanyUser.user_id == user.id, CompanyUser.active.is_(True)
        )
    if active is not None:
        query = query.filter(Company.active.is_(active))
    if search:
        like = f"%{search.strip()}%"
        query = query.filter(
            (Company.name.ilike(like))
            | (Company.legal_name.ilike(like))
            | (Company.tax_id.ilike(like))
            | (Company.slug.ilike(like))
        )
    total = query.with_entities(func.count(Company.id)).scalar() or 0
    rows = (
        query.order_by(Company.active.desc(), Company.name)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    user_counts = dict(
        db.query(CompanyUser.company_id, func.count(CompanyUser.id))
        .filter(CompanyUser.active.is_(True))
        .group_by(CompanyUser.company_id)
        .all()
    )
    items = [_serialize(c, user_counts.get(c.id, 0)) for c in rows]
    return CompanyListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


@router.post("", response_model=CompanyRead, status_code=status.HTTP_201_CREATED)
def create_company(
    payload: CompanyCreate,
    _admin: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    """Crea una empresa. Sólo SuperAdmin (companies.create)."""
    if db.query(Company).filter(Company.name == payload.name).first():
        raise HTTPException(status_code=409, detail="Ya existe una empresa con ese nombre.")
    slug = payload.slug or _slugify(payload.name)
    if db.query(Company).filter(Company.slug == slug).first():
        raise HTTPException(status_code=409, detail="Ya existe una empresa con ese identificador.")
    company = Company(
        name=payload.name,
        legal_name=payload.legal_name,
        tax_id=payload.tax_id,
        slug=slug,
        email=payload.email,
        phone=payload.phone,
        address=payload.address,
        notes=payload.notes,
        timezone=payload.timezone or "America/Argentina/Cordoba",
        locale=payload.locale or "es-AR",
        active=payload.active,
    )
    db.add(company)
    db.flush()
    from app.api.v1.company_parameters import seed_company_parameters
    seed_company_parameters(db, company.id)
    from app.models.work_order import WorkOrderStatus
    for name,color,order,initial,final,completed,delivered in [
        ("Recibido","#10B981",10,True,False,False,False),("En diagnóstico","#3B82F6",20,False,False,False,False),
        ("Presupuestado","#8B5CF6",30,False,False,False,False),("Esperando aprobación","#F59E0B",40,False,False,False,False),
        ("En reparación","#06B6D4",50,False,False,False,False),("Esperando repuesto","#F97316",60,False,False,False,False),
        ("Listo","#22C55E",70,False,False,True,False),("Entregado","#64748B",80,False,True,False,True)]:
        db.add(WorkOrderStatus(company_id=company.id,name=name,color=color,sort_order=order,active=True,is_initial=initial,is_final=final,marks_completed=completed,marks_delivered=delivered))

    if payload.admin_email:
        admin_user = db.query(User).filter(User.email == str(payload.admin_email)).first()
        if admin_user is None:
            if not payload.admin_password or not payload.admin_full_name:
                raise HTTPException(
                    status_code=400,
                    detail="Debe indicar nombre completo y contraseña para crear el administrador inicial.",
                )
            admin_user = User(
                email=str(payload.admin_email),
                full_name=payload.admin_full_name,
                password_hash=hash_password(payload.admin_password),
                active=True,
            )
            db.add(admin_user)
            db.flush()
        admin_role = (
            db.query(Role)
            .filter_by(company_id=company.id, name="Administrador")
            .first()
        )
        if admin_role is None:
            admin_role = Role(
                company_id=company.id,
                name="Administrador",
                description="Acceso completo sobre la empresa",
                is_system=True,
                active=True,
            )
            db.add(admin_role)
            db.flush()
            _grant_all_company_permissions(db, admin_role)
        membership = CompanyUser(
            company_id=company.id,
            user_id=admin_user.id,
            role="ADMIN",
            is_admin=True,
            active=True,
        )
        db.add(membership)
        db.flush()
        from app.models.role import CompanyUserRole

        db.add(
            CompanyUserRole(
                company_user_id=membership.id, role_id=admin_role.id, active=True
            )
        )
    db.commit()
    db.refresh(company)
    return _serialize(company, user_count=_count_users(db, company.id))


@router.get("/{company_id}", response_model=CompanyDetail)
def get_company(
    company_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.")
    if not user.is_superadmin:
        membership = (
            db.query(CompanyUser)
            .filter_by(user_id=user.id, company_id=company.id, active=True)
            .first()
        )
        if not membership:
            raise HTTPException(status_code=403, detail="No tiene acceso a esta empresa.")
    users_total = _count_users(db, company.id)
    admin_total = (
        db.query(func.count(CompanyUser.id))
        .filter_by(company_id=company.id, active=True, is_admin=True)
        .scalar()
        or 0
    )
    return CompanyDetail(
        id=company.id,
        name=company.name,
        legal_name=company.legal_name,
        tax_id=company.tax_id,
        slug=company.slug,
        email=company.email,
        phone=company.phone,
        address=company.address,
        notes=company.notes,
        timezone=company.timezone,
        locale=company.locale,
        active=company.active,
        created_at=company.created_at,
        updated_at=company.updated_at,
        user_count=users_total,
        admin_count=int(admin_total),
        member_count=users_total - int(admin_total),
        is_active=company.active,
    )


@router.patch("/{company_id}", response_model=CompanyRead)
def update_company(
    company_id: int,
    payload: CompanyUpdate,
    _admin: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] != company.name:
        if db.query(Company).filter(Company.name == data["name"]).first():
            raise HTTPException(status_code=409, detail="Ya existe una empresa con ese nombre.")
    if "slug" in data and data["slug"] and data["slug"] != company.slug:
        if db.query(Company).filter(Company.slug == data["slug"]).first():
            raise HTTPException(status_code=409, detail="Ya existe una empresa con ese identificador.")
    for key, value in data.items():
        setattr(company, key, value)
    db.commit()
    db.refresh(company)
    return _serialize(company, user_count=_count_users(db, company.id))


@router.post("/{company_id}/enable", response_model=CompanyRead)
def enable_company(
    company_id: int,
    _admin: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.")
    company.active = True
    db.commit()
    db.refresh(company)
    return _serialize(company, user_count=_count_users(db, company.id))


@router.post("/{company_id}/disable", response_model=CompanyRead)
def disable_company(
    company_id: int,
    _admin: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.")
    company.active = False
    db.commit()
    db.refresh(company)
    return _serialize(company, user_count=_count_users(db, company.id))


# ---------- Helpers ----------
def _slugify(value: str) -> str:
    out = []
    for char in value.lower():
        if char.isalnum():
            out.append(char)
        elif char in (" ", "-", "_"):
            out.append("-")
    slug = "".join(out).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug[:80] or "empresa"


def _count_users(db: Session, company_id: int) -> int:
    return (
        db.query(func.count(CompanyUser.id))
        .filter_by(company_id=company_id, active=True)
        .scalar()
        or 0
    )


def _grant_all_company_permissions(db: Session, role: Role) -> None:
    from app.core.permissions import PERMISSIONS

    codes = [p.code for p in PERMISSIONS]
    permissions = db.query(Permission).filter(Permission.code.in_(codes)).all()
    for permission in permissions:
        from app.models.role import role_permissions

        db.execute(
            role_permissions.insert().values(role_id=role.id, permission_id=permission.id)
        )
