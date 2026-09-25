from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, require_superadmin
from app.models.company import Company
from app.models.user import CompanyUser, User

router = APIRouter()


@router.get("/superadmin")
def superadmin_dashboard(
    _admin: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    total_companies = db.query(func.count(Company.id)).scalar() or 0
    active_companies = (
        db.query(func.count(Company.id)).filter(Company.active.is_(True)).scalar() or 0
    )
    total_users = db.query(func.count(User.id)).scalar() or 0
    active_users = (
        db.query(func.count(User.id)).filter(User.active.is_(True)).scalar() or 0
    )
    total_admins = (
        db.query(func.count(CompanyUser.id))
        .filter(CompanyUser.is_admin.is_(True), CompanyUser.active.is_(True))
        .scalar()
        or 0
    )
    total_superadmins = (
        db.query(func.count(User.id))
        .filter(User.is_superadmin.is_(True), User.active.is_(True))
        .scalar()
        or 0
    )
    recent_companies = (
        db.query(Company)
        .order_by(Company.created_at.desc(), Company.id.desc())
        .limit(5)
        .all()
    )
    return {
        "kpis": {
            "total_companies": int(total_companies),
            "active_companies": int(active_companies),
            "total_users": int(total_users),
            "active_users": int(active_users),
            "total_admins": int(total_admins),
            "total_superadmins": int(total_superadmins),
        },
        "recent_companies": [
            {
                "id": c.id,
                "name": c.name,
                "slug": c.slug,
                "active": c.active,
                "created_at": c.created_at.isoformat(),
            }
            for c in recent_companies
        ],
        "recent_activity": [],  # Reservado para bitácora; se implementa en próximos hitos.
        "quick_actions": [
            {"id": "new-company", "label": "Nueva empresa", "icon": "plus"},
            {"id": "new-user", "label": "Nuevo usuario", "icon": "user-plus"},
            {"id": "manage-roles", "label": "Roles y permisos", "icon": "shield"},
        ],
    }