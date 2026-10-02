"""Encolado y despacho de los avisos al cliente.

El encolado va en la MISMA transaccion que el cambio de estado: si el proceso muere justo
despues, la fila queda PENDING y el drenaje la recupera. El despacho va DESPUES del commit
y jamas puede hacer fallar el request.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.company import Company
from app.models.work_order import WorkOrder, WorkOrderEvent, WorkOrderNotification, WorkOrderStatus
from app.services.notifications.channels import EMAIL, WHATSAPP, EmailSender, SendResult, WhatsAppSender
from app.services.notifications.templates import build_context, render

PENDING, QUEUED, SENT, FAILED, SKIPPED = "PENDING", "QUEUED", "SENT", "FAILED", "SKIPPED"

# Registro de canales. Los tests lo monkeypatchean para no tocar la red.
SENDERS = {EMAIL: EmailSender(), WHATSAPP: WhatsAppSender()}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _skipped(db: Session, company_id: int, order: WorkOrder, event: WorkOrderEvent, channel: str, reason: str) -> None:
    """No se envia por falta de dato, pero queda registrado por que."""
    db.add(
        WorkOrderNotification(
            company_id=company_id,
            work_order_id=order.id,
            work_order_event_id=event.id,
            channel=channel,
            recipient="",
            body="",
            status=SKIPPED,
            error=reason[:500],
        )
    )


def enqueue_for_event(
    db: Session,
    company: Company,
    order: WorkOrder,
    event: WorkOrderEvent,
    status: WorkOrderStatus | None = None,
    previous_status: WorkOrderStatus | None = None,
) -> list[WorkOrderNotification]:
    """Encola los avisos que el estado de destino pide.

    No hace commit a proposito: las filas van en la misma transaccion que el cambio de
    estado, para que no se puedan perder si el proceso muere.

    La idempotencia no se implementa aca: la garantiza el unique
    (company_id, work_order_event_id, channel). Reencolar el mismo evento choca contra la
    base, que es la forma de estuviera que no dependa de que nadie se acuerde de chequear.
    """
    if not event.id:
        db.flush()
    target = status or (db.get(WorkOrderStatus, order.status_id) if order.status_id else None)
    if target is None or not target.notifications_active:
        return []
    if not (target.notify_whatsapp or target.notify_email):
        return []

    context = build_context(db, company, order, target, previous_status)
    created: list[WorkOrderNotification] = []

    if target.notify_whatsapp:
        phone = (context.get("telefono") or "").strip()
        if not phone:
            _skipped(db, company.id, order, event, WHATSAPP, "El cliente no tiene telefono ni WhatsApp")
        else:
            created.append(
                WorkOrderNotification(
                    company_id=company.id,
                    work_order_id=order.id,
                    work_order_event_id=event.id,
                    channel=WHATSAPP,
                    recipient=phone,
                    subject=None,
                    body=render(target.notification_template, context),
                    status=PENDING,
                )
            )

    if target.notify_email:
        address = (context.get("email_cliente") or "").strip()
        if not address:
            _skipped(db, company.id, order, event, EMAIL, "El cliente no tiene email")
        else:
            created.append(
                WorkOrderNotification(
                    company_id=company.id,
                    work_order_id=order.id,
                    work_order_event_id=event.id,
                    channel=EMAIL,
                    recipient=address,
                    subject=render(target.notification_email_subject, context) if target.notification_email_subject else None,
                    body=render(target.notification_template, context),
                    status=PENDING,
                )
            )

    for row in created:
        db.add(row)
    db.flush()
    return created


def dispatch(db: Session, notification_ids: list[int], actor_id: int | None = None) -> dict[str, int]:
    """Entrega las notificaciones indicadas. Nunca propaga una excepcion del proveedor."""
    summary = {"sent": 0, "queued": 0, "failed": 0}
    if not notification_ids:
        return summary
    for notification_id in notification_ids:
        row = db.get(WorkOrderNotification, notification_id)
        if row is None or row.status in (SENT, QUEUED, SKIPPED):
            continue
        company = db.get(Company, row.company_id)
        sender = SENDERS.get(row.channel)
        row.attempts = (row.attempts or 0) + 1
        if sender is None or company is None:
            row.status = FAILED
            row.error = f"Canal sin adapter: {row.channel}"[:500]
            db.commit()
            summary["failed"] += 1
            continue
        try:
            result: SendResult = sender.send(db, row, company)
        except Exception as exc:  # noqa: BLE001 - un adaptador no debe romper el despacho
            result = SendResult(ok=False, error=f"{type(exc).__name__}: {exc}"[:500])
        row.error = result.error
        row.provider_message_id = result.provider_message_id
        if result.ok:
            row.status = QUEUED if result.queued else SENT
            row.sent_at = _utcnow()
            summary["queued" if result.queued else "sent"] += 1
        else:
            row.status = FAILED
            summary["failed"] += 1
        db.commit()
    return summary


def dispatch_pending(db: Session, limit: int = 50, include_failed: bool = True) -> dict[str, int]:
    """Drenaje: toma lo pendiente (y lo fallado con intentos disponibles)."""
    max_attempts = settings.notification_max_attempts
    statuses = [PENDING, FAILED] if include_failed else [PENDING]
    rows = (
        db.query(WorkOrderNotification)
        .filter(WorkOrderNotification.status.in_(statuses), WorkOrderNotification.attempts < max_attempts)
        .order_by(WorkOrderNotification.id)
        .limit(limit)
        .all()
    )
    return dispatch(db, [row.id for row in rows])
