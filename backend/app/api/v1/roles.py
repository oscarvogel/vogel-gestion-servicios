from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_current_user,
    get_db,
    require_permission,
    require_superadmin,
)
from app.api.v1.schemas import (
    PermissionRead,
    RoleCreate,
    RoleListResponse,
    RoleRead,
    RoleUpdate,
)
from app.core.permissions import PERMISSIONS
from app.models.company import Company
from app.models.role import Permission, Role, role_permissions
from app.models.user import CompanyUser, User

router = APIRouter()


def _role_to_read(db: Session, role: Role) -> RoleRead:
    codes = [
        code
        for (code,) in (
            db.query(Permission.code)
            .join(role_permissions, role_permissions.c.permission_id == Permission.id)
            .filter(role_permissions.c.role_id == role.id)
            .all()
        )
    ]
    return RoleRead(
        id=role.id,
        company_id=role.company_id,
        name=role.name,
        description=role.description,
        is_system=role.is_system,
        active=role.active,
        permission_codes=sorted(codes),
    )


@router.get("/permissions", response_model=list[PermissionRead])
def list_permissions(_admin: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(Permission).order_by(Permission.namespace, Permission.code).all()
    )
    # Asegurar que el catálogo completo existe (incluye permisos recién definidos
    # si la migración hubiera sido previa).
    existing_codes = {row.code for row in rows}
    for perm in PERMISSIONS:
        if perm.code not in existing_codes:
            new = Permission(
                code=perm.code, namespace=perm.namespace, description=perm.description
            )
            db.add(new)
    db.commit()
    rows = (
        db.query(Permission).order_by(Permission.namespace, Permission.code).all()
    )
    return [
        PermissionRead(id=row.id, code=row.code, namespace=row.namespace, description=row.description)
        for row in rows
    ]


@router.get("", response_model=RoleListResponse)
def list_roles(
    actor: User = Depends(get_current_user),
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
):
    base = db.query(Role)
    if actor.is_superadmin:
        rows = base.order_by(Role.company_id.is_(None).desc(), Role.name).all()
    else:
        from app.api.dependencies import get_current_company_id as _cid


        current_company_id = _cid(
            authorization=authorization, user=actor, db=db
        )
        rows = (
            base.filter(Role.company_id == current_company_id)
            .order_by(Role.is_system.desc(), Role.name)
            .all()
        )
    return RoleListResponse(items=[_role_to_read(db, r) for r in rows])


@router.post("", response_model=RoleRead, status_code=status.HTTP_201_CREATED)
def create_role(
    payload: RoleCreate,
    actor: User = Depends(get_current_user),
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
):
    company_id = None
    if not actor.is_superadmin:
        from app.api.dependencies import get_current_company_id as _cid


        company_id = _cid(
            authorization=authorization, user=actor, db=db
        )
        _require_company_admin(actor, company_id, db)
    if company_id is not None:
        exists = db.query(Role).filter_by(company_id=company_id, name=payload.name).first()
    else:
        exists = db.query(Role).filter_by(company_id=None, name=payload.name).first()
    if exists:
        raise HTTPException(status_code=409, detail="Role name already exists")
    role = Role(
        company_id=company_id,
        name=payload.name,
        description=payload.description,
        active=payload.active,
        is_system=False,
    )
    db.add(role)
    db.flush()
    _set_role_permissions(db, role, payload.permission_ids)
    db.commit()
    db.refresh(role)
    return _role_to_read(db, role)


@router.patch("/{role_id}", response_model=RoleRead)
def update_role(
    role_id: int,
    payload: RoleUpdate,
    actor: User = Depends(get_current_user),
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
):
    role = db.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if not actor.is_superadmin:
        from app.api.dependencies import get_current_company_id as _cid


        current_company_id = _cid(
            authorization=authorization, user=actor, db=db
        )
        _require_company_admin(actor, current_company_id, db)
        if role.company_id != current_company_id:
            raise HTTPException(status_code=403, detail="Role access denied")
        if role.is_system and payload.name and payload.name != role.name:
            raise HTTPException(status_code=400, detail="Cannot rename system role")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"]:
        role.name = data["name"]
    if "description" in data:
        role.description = data["description"]
    if "active" in data and data["active"] is not None:
        role.active = data["active"]
    if "permission_ids" in data and data["permission_ids"] is not None:
        _set_role_permissions(db, role, data["permission_ids"])
    db.commit()
    db.refresh(role)
    return _role_to_read(db, role)


@router.post("/{role_id}/permissions/{permission_id}", response_model=RoleRead)
def grant_permission(
    role_id: int,
    permission_id: int,
    _admin: User = Depends(require_permission("roles.manage")),
    db: Session = Depends(get_db),
):
    role = db.get(Role, role_id)
    permission = db.get(Permission, permission_id)
    if not role or not permission:
        raise HTTPException(status_code=404, detail="Role or permission not found")
    exists = (
        db.query(role_permissions)
        .filter_by(role_id=role.id, permission_id=permission.id)
        .first()
    )
    if not exists:
        db.execute(
            role_permissions.insert().values(role_id=role.id, permission_id=permission.id)
        )
        db.commit()
    db.refresh(role)
    return _role_to_read(db, role)


@router.delete("/{role_id}/permissions/{permission_id}", response_model=RoleRead)
def revoke_permission(
    role_id: int,
    permission_id: int,
    _admin: User = Depends(require_permission("roles.manage")),
    db: Session = Depends(get_db),
):
    role = db.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    db.execute(
        role_permissions.delete().where(
            (role_permissions.c.role_id == role.id)
            & (role_permissions.c.permission_id == permission_id)
        )
    )
    db.commit()
    db.refresh(role)
    return _role_to_read(db, role)


# ---------- Helpers ----------
def _set_role_permissions(db: Session, role: Role, permission_ids: list[int]) -> None:
    db.execute(
        role_permissions.delete().where(role_permissions.c.role_id == role.id)
    )
    if not permission_ids:
        return
    rows = (
        db.query(Permission).filter(Permission.id.in_(permission_ids)).all()
    )
    for permission in rows:
        db.execute(
            role_permissions.insert().values(
                role_id=role.id, permission_id=permission.id
            )
        )


def _require_company_admin(user: User, company_id: int, db: Session) -> None:
    membership = (
        db.query(CompanyUser)
        .filter_by(user_id=user.id, company_id=company_id, active=True)
        .first()
    )
    if not membership or not membership.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Company admin required",
        )