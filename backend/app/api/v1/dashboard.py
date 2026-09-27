from __future__ import annotations

from fastapi import APIRouter, Depends
from datetime import datetime, timedelta

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_company_id, get_db, require_permission, require_superadmin
from app.models.company import Company
from app.models.user import CompanyUser, User
from app.models.work_order import WorkOrder, WorkOrderStatus

router = APIRouter()


@router.get("/company")
def company_dashboard(
    company_id: int = Depends(get_current_company_id),
    _actor: User = Depends(require_permission("work_orders.view")),
    db: Session = Depends(get_db),
):
    """Operational KPI snapshot for the active company.

    Semantic status flags are used instead of status names so every tenant can
    customize its workflow without breaking dashboard metrics.
    """
    status = WorkOrderStatus
    rows = (
        db.query(
            status.id,
            status.name,
            status.color,
            status.sort_order,
            status.is_initial,
            status.is_final,
            status.marks_quoted,
            status.marks_awaiting_quote_approval,
            status.marks_repair,
            status.marks_completed,
            status.marks_delivered,
            func.count(WorkOrder.id).label("count"),
        )
        .outerjoin(
            WorkOrder,
            (WorkOrder.status_id == status.id) & (WorkOrder.company_id == company_id),
        )
        .filter(status.company_id == company_id, status.active.is_(True))
        .group_by(
            status.id, status.name, status.color, status.sort_order,
            status.is_initial, status.is_final, status.marks_quoted,
            status.marks_awaiting_quote_approval, status.marks_repair,
            status.marks_completed, status.marks_delivered,
        )
        .order_by(status.sort_order, status.name)
        .all()
    )

    total = db.query(func.count(WorkOrder.id)).filter(WorkOrder.company_id == company_id).scalar() or 0
    open_count = sum(int(r.count) for r in rows if not r.is_final and not r.marks_delivered)
    delivered = sum(int(r.count) for r in rows if r.marks_delivered)
    completed = sum(int(r.count) for r in rows if r.marks_completed and not r.marks_delivered)
    repair = sum(int(r.count) for r in rows if r.marks_repair)
    awaiting_quote = sum(int(r.count) for r in rows if r.marks_awaiting_quote_approval)
    quoted = sum(int(r.count) for r in rows if r.marks_quoted)

    now = datetime.now()
    open_orders = (
        db.query(WorkOrder.received_at)
        .outerjoin(status, WorkOrder.status_id == status.id)
        .filter(
            WorkOrder.company_id == company_id,
            func.coalesce(status.is_final, False).is_(False),
            func.coalesce(status.marks_delivered, False).is_(False),
        )
        .all()
    )
    aging = {"0_2": 0, "3_7": 0, "8_15": 0, "16_plus": 0}
    for order in open_orders:
        days = max(0, (now - order.received_at).days)
        if days <= 2: aging["0_2"] += 1
        elif days <= 7: aging["3_7"] += 1
        elif days <= 15: aging["8_15"] += 1
        else: aging["16_plus"] += 1

    week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    trend = []
    for offset in range(7, -1, -1):
        start = week_start - timedelta(weeks=offset)
        end = start + timedelta(weeks=1)
        received = db.query(func.count(WorkOrder.id)).filter(
            WorkOrder.company_id == company_id, WorkOrder.received_at >= start, WorkOrder.received_at < end,
        ).scalar() or 0
        finished = db.query(func.count(WorkOrder.id)).filter(
            WorkOrder.company_id == company_id, WorkOrder.completed_at.isnot(None),
            WorkOrder.completed_at >= start, WorkOrder.completed_at < end,
        ).scalar() or 0
        trend.append({"label": start.strftime("%d/%m"), "received": int(received), "finished": int(finished)})

    resolution_days = [
        (completed_at - received_at).total_seconds() / 86400
        for received_at, completed_at in db.query(WorkOrder.received_at, WorkOrder.completed_at)
        .filter(WorkOrder.company_id == company_id, WorkOrder.completed_at.isnot(None)).all()
        if completed_at >= received_at
    ]
    avg_resolution_days = round(sum(resolution_days) / len(resolution_days), 1) if resolution_days else None
    attention = {
        "older_than_15_days": aging["16_plus"],
        "awaiting_quote_approval": awaiting_quote,
        "waiting_parts": sum(int(r.count) for r in rows if "repuesto" in r.name.lower()),
        "ready_to_deliver": completed,
    }

    return {
        "total": int(total),
        "summary": {
            "open": open_count,
            "awaiting_quote_approval": awaiting_quote,
            "quoted": quoted,
            "repair": repair,
            "completed": completed,
            "delivered": delivered,
        },
        "aging": aging,
        "trend": trend,
        "avg_resolution_days": avg_resolution_days,
        "attention": attention,
        "statuses": [
            {
                "id": r.id,
                "name": r.name,
                "color": r.color,
                "count": int(r.count),
                "is_final": r.is_final,
                "marks_delivered": r.marks_delivered,
            }
            for r in rows
        ],
    }


@router.get("/superadmin")
def superadmin_dashboard(
    _admin: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    total_companies = db.query(func.count(Company.id)).scalar() or 0
    active_companies = db.query(func.count(Company.id)).filter(Company.active.is_(True)).scalar() or 0
    total_users = db.query(func.count(User.id)).scalar() or 0
    active_users = db.query(func.count(User.id)).filter(User.active.is_(True)).scalar() or 0
    total_admins = db.query(func.count(CompanyUser.id)).filter(CompanyUser.is_admin.is_(True), CompanyUser.active.is_(True)).scalar() or 0
    total_superadmins = db.query(func.count(User.id)).filter(User.is_superadmin.is_(True), User.active.is_(True)).scalar() or 0
    recent_companies = db.query(Company).order_by(Company.created_at.desc(), Company.id.desc()).limit(5).all()
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
            {"id": c.id, "name": c.name, "slug": c.slug, "active": c.active, "created_at": c.created_at.isoformat()}
            for c in recent_companies
        ],
        "recent_activity": [],
        "quick_actions": [
            {"id": "new-company", "label": "Nueva empresa", "icon": "plus"},
            {"id": "new-user", "label": "Nuevo usuario", "icon": "user-plus"},
            {"id": "manage-roles", "label": "Roles y permisos", "icon": "shield"},
        ],
    }
