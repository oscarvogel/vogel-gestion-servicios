from __future__ import annotations

from fastapi import APIRouter, Depends
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_company_id, get_db, require_permission, require_superadmin, user_has_permission
from app.models.company import Company
from app.models.customer import Customer, Equipment, EquipmentCategory
from app.models.user import CompanyUser, User
from app.models.work_order import WorkOrder, WorkOrderStatus

router = APIRouter()

FALLBACK_TIMEZONE = "America/Argentina/Cordoba"
# Días que una OT abierta puede permanecer antes de entrar en "requieren atención".
AGING_DAYS = 15


def _utcnow() -> datetime:
    """Reloj inyectable para que los tests fijen el instante y no dependan del reloj."""
    return datetime.now(timezone.utc)


def _company_zone(company: Company | None) -> ZoneInfo:
    """Zona horaria de la empresa, cayendo a la de Córdoba si el dato no es usable."""
    name = (getattr(company, "timezone", None) or "").strip() or FALLBACK_TIMEZONE
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(FALLBACK_TIMEZONE)


def _to_utc_naive(value: datetime) -> datetime:
    """Naive en UTC, que es como la base guarda las fechas del flujo."""
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _day_window(zone: ZoneInfo, now_utc: datetime) -> tuple[datetime, datetime]:
    """Ventana [start, end) del día calendario local de la empresa que contiene now_utc.

    Los dos bordes son medianoche local convertidos por separado, así que un cambio
    de horario de verano da una ventana de 23 o 25 horas y no una de 24 mal corrida.
    """
    local = now_utc.astimezone(zone)
    local_start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return _to_utc_naive(local_start), _to_utc_naive(local_start + timedelta(days=1))


@router.get("/company")
def company_dashboard(
    company_id: int = Depends(get_current_company_id),
    actor: User = Depends(require_permission("work_orders.view")),
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
            status.marks_waiting_parts,
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
            status.marks_waiting_parts, status.marks_completed, status.marks_delivered,
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

    # "Hoy" y los cortes de semana se calculan en la zona horaria de la empresa: las
    # fechas del flujo están guardadas en UTC naive y comparar contra la hora del
    # servidor correría el corte del día y de la semana.
    zone = _company_zone(db.get(Company, company_id))
    now_utc = _utcnow()
    now = _to_utc_naive(now_utc)
    day_start, day_end = _day_window(zone, now_utc)
    local_today = now_utc.astimezone(zone)
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
        elif days <= AGING_DAYS: aging["8_15"] += 1
        else: aging["16_plus"] += 1

    week_start = (local_today - timedelta(days=local_today.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    trend = []
    for offset in range(7, -1, -1):
        local_start = week_start - timedelta(weeks=offset)
        start = _to_utc_naive(local_start)
        end = _to_utc_naive(local_start + timedelta(weeks=1))
        received = db.query(func.count(WorkOrder.id)).filter(
            WorkOrder.company_id == company_id, WorkOrder.received_at >= start, WorkOrder.received_at < end,
        ).scalar() or 0
        finished = db.query(func.count(WorkOrder.id)).filter(
            WorkOrder.company_id == company_id, WorkOrder.completed_at.isnot(None),
            WorkOrder.completed_at >= start, WorkOrder.completed_at < end,
        ).scalar() or 0
        trend.append({"label": local_start.strftime("%d/%m"), "received": int(received), "finished": int(finished)})

    resolution_days = [
        (completed_at - received_at).total_seconds() / 86400
        for received_at, completed_at in db.query(WorkOrder.received_at, WorkOrder.completed_at)
        .filter(WorkOrder.company_id == company_id, WorkOrder.completed_at.isnot(None)).all()
        if completed_at >= received_at
    ]
    avg_resolution_days = round(sum(resolution_days) / len(resolution_days), 1) if resolution_days else None

    def _count_in_day(column) -> int:
        # Comparar contra la ventana excluye los NULL, así que una OT sin fecha de
        # finalización o entrega no cuenta como terminada ni entregada hoy.
        return int(
            db.query(func.count(WorkOrder.id))
            .filter(WorkOrder.company_id == company_id, column >= day_start, column < day_end)
            .scalar()
            or 0
        )

    today = {
        "date": local_today.date().isoformat(),
        "received": _count_in_day(WorkOrder.received_at),
        "completed": _count_in_day(WorkOrder.completed_at),
        "delivered": _count_in_day(WorkOrder.delivered_at),
    }

    # Cada categoría lleva su propio destino para que el frontend no tenga que reconstruir
    # la regla ni conocer los estados de la empresa. Los conteos salen de los flags
    # semánticos, nunca del nombre del estado: una empresa que llame al estado "Esperando
    # componente" tiene que ver el mismo número que una que lo llame "Esperando repuesto".
    def _statuses_with(flag: str) -> list[int]:
        return [int(r.id) for r in rows if getattr(r, flag)]

    attention = [
        {
            "key": "awaiting_quote_approval",
            "count": awaiting_quote,
            "status_ids": _statuses_with("marks_awaiting_quote_approval"),
        },
        {
            "key": "waiting_parts",
            "count": sum(int(r.count) for r in rows if r.marks_waiting_parts),
            "status_ids": _statuses_with("marks_waiting_parts"),
        },
        {
            "key": "ready_to_deliver",
            "count": completed,
            "status_ids": [int(r.id) for r in rows if r.marks_completed and not r.marks_delivered],
        },
        {
            "key": "older_than_15_days",
            "count": aging["16_plus"],
            # date_to es inclusivo en el listado (received_at < date_to + 1 día), así que
            # el borde va un día antes para que el link no muestre un día de más.
            "date_to": (local_today - timedelta(days=AGING_DAYS + 1)).date().isoformat(),
            "open_only": True,
        },
    ]

    recent_orders = (
        db.query(WorkOrder)
        .filter(WorkOrder.company_id == company_id)
        .order_by(WorkOrder.received_at.desc(), WorkOrder.id.desc())
        .limit(8)
        .all()
    )
    recent_work_orders = []
    for order in recent_orders:
        customer = db.query(Customer).filter_by(id=order.customer_id, company_id=company_id).first()
        equipment = db.query(Equipment).filter_by(id=order.equipment_id, company_id=company_id).first()
        equipment_label = ""
        serial_number = None
        if equipment:
            category = db.query(EquipmentCategory).filter_by(id=equipment.category_id, company_id=company_id).first()
            equipment_label = " ".join(x for x in ((category.name if category else None), equipment.brand, equipment.model) if x)
            serial_number = equipment.serial_number
        status_row = db.get(WorkOrderStatus, order.status_id) if order.status_id else None
        recent_work_orders.append(
            {
                "id": order.id,
                "number": order.number,
                "customer_name": customer.name if customer else "—",
                "customer_phone": (customer.phone or customer.whatsapp) if customer else None,
                "equipment_label": equipment_label or "—",
                "serial_number": serial_number,
                "status_name": (status_row.name if status_row else order.status.title()),
                "status_color": (status_row.color if status_row else "#3B82F6"),
                "received_at": order.received_at.isoformat() if order.received_at else None,
                "expected_delivery_at": order.expected_delivery_at.isoformat() if order.expected_delivery_at else None,
            }
        )

    can_create = user_has_permission(db, actor, company_id, "work_orders.manage")

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
        "today": today,
        "avg_resolution_days": avg_resolution_days,
        "attention": attention,
        "recent_work_orders": recent_work_orders,
        "can_create_work_orders": bool(can_create),
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
