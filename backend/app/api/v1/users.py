from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_current_user,
    get_db,
    require_permission,
)
from app.api.v1.schemas import (
    MembershipCreate,
    MembershipRead,
    MembershipSummary,
    MembershipUpdate,
    UserCreate,
    UserDetail,
    UserListResponse,
    UserRead,
    UserUpdate,
)
from app.core.security import create_access_token, hash_password
from app.models.company import Company
from app.models.role import CompanyUserRole, Role
from app.models.user import CompanyUser, User

router = APIRouter()


# ---------- Helpers ----------
def _membership_summary(db: Session, membership: CompanyUser, company: Company) -> MembershipSummary:
    return MembershipSummary(
        company_id=company.id,
        company_name=company.name,
        company_slug=company.slug,
        company_active=company.active,
        is_admin=membership.is_admin,
        role=membership.role,
        active=membership.active,
    )


def _user_detail(db: Session, user: User, company_id: int | None = None) -> UserDetail:
    rows = (
        db.query(CompanyUser, Company)
        .join(Company, Company.id == CompanyUser.company_id)
        .filter(CompanyUser.user_id == user.id)
    )
    if company_id is not None:
        rows = rows.filter(CompanyUser.company_id == company_id)
    rows = rows.all()
    memberships = [_membership_summary(db, m, c) for m, c in rows]
    return UserDetail(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        active=user.active,
        is_superadmin=user.is_superadmin,
        created_at=user.created_at,
        memberships=memberships,
    )


def _actor_current_company_id(authorization: str, actor: User, db: Session) -> int:
    from app.api.dependencies import get_current_company_id as _cid

    return _cid(authorization=authorization, user=actor, db=db)


def _membership_read(db: Session, membership: CompanyUser) -> MembershipRead:
    role_ids = [
        row.role_id
        for row in db.query(CompanyUserRole.role_id).filter_by(
            company_user_id=membership.id, active=True
        )
    ]
    return MembershipRead(
        id=membership.id,
        user_id=membership.user_id,
        company_id=membership.company_id,
        role=membership.role,
        is_admin=membership.is_admin,
        active=membership.active,
        role_ids=role_ids,
    )


def _attach_membership(db: Session, user: User, payload: MembershipCreate, *, commit: bool = True) -> MembershipRead:
    membership = CompanyUser(
        company_id=payload.company_id,
        user_id=user.id,
        role=payload.role,
        is_admin=payload.is_admin or payload.role == "ADMIN",
        active=payload.active,
    )
    db.add(membership)
    db.flush()
    for role_id in payload.role_ids:
        role = db.get(Role, role_id)
        if not role or (role.company_id not in (None, payload.company_id)):
            continue
        db.add(
            CompanyUserRole(
                company_user_id=membership.id, role_id=role_id, active=True
            )
        )
    if commit:
        db.commit()
        db.refresh(membership)
    else:
        db.flush()
    return _membership_read(db, membership)


def _replace_roles(db: Session, membership: CompanyUser, role_ids: list[int]) -> None:
    existing = (
        db.query(CompanyUserRole).filter_by(company_user_id=membership.id).all()
    )
    keep = set(role_ids)
    for row in existing:
        if row.role_id in keep:
            row.active = True
        else:
            row.active = False
    for role_id in role_ids:
        if any(r.role_id == role_id for r in existing):
            continue
        role = db.get(Role, role_id)
        if not role:
            continue
        if role.company_id not in (None, membership.company_id):
            continue
        db.add(
            CompanyUserRole(
                company_user_id=membership.id, role_id=role_id, active=True
            )
        )


# ---------- Routes ----------
@router.get("", response_model=UserListResponse)
def list_users(
    actor: User = Depends(get_current_user),
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: Optional[str] = None,
    active: Optional[bool] = None,
    company_id: Optional[int] = Query(default=None),
):
    base = db.query(User)
    if not actor.is_superadmin:
        current_company_id = _actor_current_company_id(authorization, actor, db)
        base = base.join(CompanyUser, CompanyUser.user_id == User.id).filter(
            CompanyUser.company_id == current_company_id,
            CompanyUser.active.is_(True),
        )
    elif company_id is not None:
        base = base.join(CompanyUser, CompanyUser.user_id == User.id).filter(
            CompanyUser.company_id == company_id, CompanyUser.active.is_(True)
        )
    if active is not None:
        base = base.filter(User.active.is_(active))
    if search:
        like = f"%{search.strip()}%"
        base = base.filter((User.email.ilike(like)) | (User.full_name.ilike(like)))
    total = base.with_entities(func.count(func.distinct(User.id))).scalar() or 0
    # Evitar SELECT DISTINCT sobre la entidad completa: con MySQL y joins de
    # membresías puede producir consultas frágiles. Primero paginamos IDs únicos
    # y después cargamos los usuarios por PK conservando el orden.
    user_ids = [
        row[0]
        for row in (
            base.with_entities(User.id)
            .group_by(User.id, User.active, User.full_name)
            .order_by(User.active.desc(), User.full_name, User.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
    ]
    users_by_id = {
        user.id: user
        for user in db.query(User).filter(User.id.in_(user_ids)).all()
    } if user_ids else {}
    rows = [users_by_id[user_id] for user_id in user_ids if user_id in users_by_id]
    detail_company_id = None if actor.is_superadmin else _actor_current_company_id(authorization, actor, db)
    items = [_user_detail(db, u, detail_company_id) for u in rows]
    return UserListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


@router.post("", response_model=UserDetail, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    actor: User = Depends(require_permission("users.create")),
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
):
    existing = db.query(User).filter(User.email == str(payload.email)).first()
    if existing:
        raise HTTPException(status_code=409, detail="El correo electrónico ya está registrado.")

    if payload.is_superadmin and not actor.is_superadmin:
        raise HTTPException(status_code=403, detail="No tiene permisos para crear un SuperAdmin.")

    memberships = list(payload.memberships)
    if not payload.is_superadmin and not memberships:
        raise HTTPException(
            status_code=422,
            detail="Debe asignar al menos una empresa al usuario.",
        )

    seen_company_ids: set[int] = set()
    actor_company_id: int | None = None
    if not actor.is_superadmin:
        actor_company_id = _actor_current_company_id(authorization, actor, db)

    for membership_data in memberships:
        if membership_data.company_id in seen_company_ids:
            raise HTTPException(status_code=422, detail="No puede repetir la misma empresa.")
        seen_company_ids.add(membership_data.company_id)

        company = db.get(Company, membership_data.company_id)
        if not company or not company.active:
            raise HTTPException(status_code=422, detail="La empresa seleccionada no es válida.")
        if actor_company_id is not None and membership_data.company_id != actor_company_id:
            raise HTTPException(
                status_code=403,
                detail="No tiene permisos para asignar usuarios a otra empresa.",
            )

    user = User(
        email=str(payload.email),
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        active=True,
        is_superadmin=payload.is_superadmin,
    )
    try:
        db.add(user)
        db.flush()
        for membership_data in memberships:
            _attach_membership(db, user, membership_data, commit=False)
        db.commit()
        db.refresh(user)
    except Exception:
        db.rollback()
        raise

    return _user_detail(db, user)


@router.get("/me", response_model=UserDetail)
def get_me(
    actor: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _user_detail(db, actor)


@router.get("/{user_id}", response_model=UserDetail)
def get_user(
    user_id: int,
    actor: User = Depends(get_current_user),
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    if not actor.is_superadmin:
        current_company_id = _actor_current_company_id(authorization, actor, db)
        shared = (
            db.query(CompanyUser)
            .filter_by(user_id=user.id, company_id=current_company_id, active=True)
            .first()
        )
        if not shared:
            raise HTTPException(status_code=403, detail="No tiene acceso a este usuario.")
    detail_company_id = None if actor.is_superadmin else current_company_id
    return _user_detail(db, user, detail_company_id)


@router.patch("/{user_id}", response_model=UserDetail)
def update_user(
    user_id: int,
    payload: UserUpdate,
    actor: User = Depends(require_permission("users.update")),
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    if not actor.is_superadmin:
        current_company_id = _actor_current_company_id(authorization, actor, db)
        same_company = (
            db.query(CompanyUser)
            .filter_by(user_id=user.id, company_id=current_company_id, active=True)
            .first()
        )
        if not same_company:
            raise HTTPException(status_code=403, detail="No tiene acceso a este usuario.")
    data = payload.model_dump(exclude_unset=True)
    if "email" in data and data["email"]:
        duplicate = (
            db.query(User)
            .filter(User.email == str(data["email"]), User.id != user.id)
            .first()
        )
        if duplicate:
            raise HTTPException(status_code=409, detail="El correo electrónico ya está registrado.")
        user.email = str(data["email"])
    if "full_name" in data and data["full_name"]:
        user.full_name = data["full_name"]
    if "password" in data and data["password"]:
        user.password_hash = hash_password(data["password"])
    if "active" in data and data["active"] is not None:
        if user.is_superadmin and not data["active"]:
            raise HTTPException(status_code=400, detail="No se puede desactivar un SuperAdmin.")
        user.active = data["active"]
    db.commit()
    db.refresh(user)
    return _user_detail(db, user)


@router.post("/{user_id}/enable", response_model=UserDetail)
def enable_user(
    user_id: int,
    actor: User = Depends(require_permission("users.disable")),
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    if not actor.is_superadmin:
        current_company_id = _actor_current_company_id(authorization, actor, db)
        shared = db.query(CompanyUser).filter_by(user_id=user.id, company_id=current_company_id, active=True).first()
        if not shared:
            raise HTTPException(status_code=403, detail="No tiene acceso a este usuario.")
    user.active = True
    db.commit()
    db.refresh(user)
    return _user_detail(db, user)


@router.post("/{user_id}/disable", response_model=UserDetail)
def disable_user(
    user_id: int,
    actor: User = Depends(require_permission("users.disable")),
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    if user.is_superadmin:
        raise HTTPException(status_code=400, detail="No se puede desactivar un SuperAdmin.")
    if not actor.is_superadmin:
        current_company_id = _actor_current_company_id(authorization, actor, db)
        shared = db.query(CompanyUser).filter_by(user_id=user.id, company_id=current_company_id, active=True).first()
        if not shared:
            raise HTTPException(status_code=403, detail="No tiene acceso a este usuario.")
    user.active = False
    db.commit()
    db.refresh(user)
    return _user_detail(db, user)


@router.get("/{user_id}/memberships", response_model=list[MembershipRead])
def list_memberships(
    user_id: int,
    actor: User = Depends(require_permission("users.view")),
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    if not actor.is_superadmin:
        current_company_id = _actor_current_company_id(authorization, actor, db)
        shared = (
            db.query(CompanyUser)
            .filter_by(user_id=user.id, company_id=current_company_id, active=True)
            .first()
        )
        if not shared:
            raise HTTPException(status_code=403, detail="No tiene acceso a este usuario.")
    memberships_query = db.query(CompanyUser).filter(CompanyUser.user_id == user.id)
    if not actor.is_superadmin:
        memberships_query = memberships_query.filter(CompanyUser.company_id == current_company_id)
    memberships = memberships_query.order_by(CompanyUser.id).all()
    return [_membership_read(db, m) for m in memberships]


@router.post(
    "/{user_id}/memberships",
    response_model=MembershipRead,
    status_code=status.HTTP_201_CREATED,
)
def add_membership(
    user_id: int,
    payload: MembershipCreate,
    actor: User = Depends(require_permission("users.update")),
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    if not actor.is_superadmin:
        current_company_id = _actor_current_company_id(authorization, actor, db)
        if payload.company_id != current_company_id:
            raise HTTPException(status_code=403, detail="No puede asignar una membresía a otra empresa.")
    company = db.get(Company, payload.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.")
    if not company.active:
        raise HTTPException(status_code=422, detail="La empresa seleccionada está inactiva.")
    existing = (
        db.query(CompanyUser)
        .filter_by(user_id=user.id, company_id=payload.company_id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="El usuario ya pertenece a esa empresa.")
    return _attach_membership(db, user, payload)


@router.patch("/{user_id}/memberships/{membership_id}", response_model=MembershipRead)
def update_membership(
    user_id: int,
    membership_id: int,
    payload: MembershipUpdate,
    actor: User = Depends(require_permission("users.update")),
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    membership = (
        db.query(CompanyUser)
        .filter_by(id=membership_id, user_id=user.id)
        .first()
    )
    if not membership:
        raise HTTPException(status_code=404, detail="Membresía no encontrada.")
    if not actor.is_superadmin:
        current_company_id = _actor_current_company_id(authorization, actor, db)
        if membership.company_id != current_company_id:
            raise HTTPException(status_code=403, detail="No tiene acceso a esta membresía.")
    data = payload.model_dump(exclude_unset=True)
    if "role" in data and data["role"]:
        membership.role = data["role"]
    if "is_admin" in data and data["is_admin"] is not None:
        membership.is_admin = data["is_admin"]
    if "active" in data and data["active"] is not None:
        membership.active = data["active"]
    if "role_ids" in data and data["role_ids"] is not None:
        _replace_roles(db, membership, data["role_ids"])
    db.commit()
    db.refresh(membership)
    return _membership_read(db, membership)