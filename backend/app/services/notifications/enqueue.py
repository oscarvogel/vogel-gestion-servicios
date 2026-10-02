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


def plan_for_event(
    db: Session,
    company: Company,
    order: WorkOrder,
    event: WorkOrderEvent | None = None,
    status: WorkOrderStatus | None = None,
    previous_status: WorkOrderStatus | None = None,
    overrides: dict | None = None,
) -> list[dict]:
    """Que avisos se harian, sin escribir nada. Es lo que muestra el modal de confirmacion.

    Que exista una unica funcion que decide es lo que hace que lo que el usuario ve antes
    de confirmar sea exactamente lo que se va a mandar. Si el modal calculara por su cuenta,
    tarde o tempranoiria a discrepar de lo que se envia.
    """
    target = status or (db.get(WorkOrderStatus, order.status_id) if order.status_id else None)
    if target is None or not target.notifications_active:
        return []
    if not (target.notify_whatsapp or target.notify_email):
        return []
    overrides = overrides or {}
    context = build_context(db, company, order, target, previous_status)
    plan: list[dict] = []

    for channel, enabled in ((WHATSAPP, target.notify_whatsapp), (EMAIL, target.notify_email)):
        if not enabled:
            continue
        # WhatsApp usa el whatsapp del cliente y, si no tiene, el telefono.
        recipient = (context.get("telefono") or "").strip() if channel == WHATSAPP else (context.get("email_cliente") or "").strip()
        own = overrides.get(channel) or {}
        body = own.get("body") or render(target.notification_template, context)
        subject = own.get("subject") or (render(target.notification_email_subject, context) if target.notification_email_subject else None)
        if channel == WHATSAPP:
            subject = None
        edited = (own.get("recipient") or "").strip()
        # Destinatario editado a mano: manda sobre el de la ficha del cliente.
        if edited:
            recipient = edited
        item = {"channel": channel, "recipient": recipient, "subject": subject, "body": body, "skipped": False, "reason": None}
        if not recipient:
            item["skipped"] = True
            item["reason"] = "No hay numero de destino: el cliente no tiene y no se completo uno" if channel == WHATSAPP else "No hay email de destino: el cliente no tiene y no se completo uno"
        plan.append(item)
    return plan


def enqueue_for_event(
    db: Session,
    company: Company,
    order: WorkOrder,
    event: WorkOrderEvent,
    status: WorkOrderStatus | None = None,
    previous_status: WorkOrderStatus | None = None,
    overrides: dict | None = None,
) -> list[WorkOrderNotification]:
    """Encola los avisos que el estado de destino pide.

    No hace commit a proposito: las filas van en la misma transaccion que el cambio de
    estado, para que no se puedan perder si el proceso muere.

    La idempotencia no se implementa aca: la garantiza el unique
    (company_id, work_order_event_id, channel). Reencolar el mismo evento choca contra la
    base, que es mas de fiarse de que nadie se acuerde de chequear.
    """
    if not event.id:
        db.flush()
    created: list[WorkOrderNotification] = []
    for item in plan_for_event(db, company, order, event, status, previous_status, overrides):
        if item["skipped"]:
            # No se envia por falta de dato, pero queda registrado por que.
            db.add(
                WorkOrderNotification(
                    company_id=company.id,
                    work_order_id=order.id,
                    work_order_event_id=event.id,
                    channel=item["channel"],
                    recipient="",
                    body="",
                    status=SKIPPED,
                    error=item["reason"][:500],
                )
            )
            continue
        row = WorkOrderNotification(
            company_id=company.id,
            work_order_id=order.id,
            work_order_event_id=event.id,
            channel=item["channel"],
            recipient=item["recipient"],
            subject=item["subject"],
            body=item["body"],
            status=PENDING,
        )
        db.add(row)
        created.append(row)
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
