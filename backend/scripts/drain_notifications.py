"""Drena la cola de avisos al cliente (#45).

Recupera lo que quedo PENDING (por ejemplo, si el proceso murio entre el commit del cambio
de estado y el envio) y reintenta lo que quedo FAILED mientras tenga intentos disponibles.

    python backend/scripts/drain_notifications.py --limit 50
    python backend/scripts/drain_notifications.py --company-id 3 --dry-run

Es idempotente: una notificacion QUEUED o SENT ya no se vuelve a tocar, y el unique
(company_id, work_order_event_id, channel) impide que el mismo evento genere dos avisos.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.work_order import WorkOrderNotification
from app.services.notifications.channels import EMAIL, WHATSAPP
from app.services.notifications.enqueue import FAILED, PENDING, QUEUED, SENT, SKIPPED, dispatch

LABELS = {WHATSAPP: "WhatsApp", EMAIL: "Email"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Envia los avisos al cliente pendientes.")
    parser.add_argument("--limit", type=int, default=50, help="Maximo de notificaciones a procesar.")
    parser.add_argument("--company-id", type=int, default=None, help="Limitar a una empresa.")
    parser.add_argument("--dry-run", action="store_true", help="Listar sin enviar.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        query = db.query(WorkOrderNotification).filter(
            WorkOrderNotification.status.in_([PENDING, FAILED]),
            WorkOrderNotification.attempts < settings.notification_max_attempts,
        )
        if args.company_id is not None:
            query = query.filter(WorkOrderNotification.company_id == args.company_id)
        rows = query.order_by(WorkOrderNotification.id).limit(args.limit).all()

        if not rows:
            print("No hay notificaciones pendientes.")
            return 0

        if args.dry_run:
            for row in rows:
                print(
                    f"  #{row.id} empresa={row.company_id} OT={row.work_order_id} "
                    f"{LABELS.get(row.channel, row.channel)} -> {row.recipient or '(sin destinatario)'} "
                    f"[{row.status}, intentos={row.attempts}]"
                )
            print(f"{len(rows)} notificaciones. No se envio nada (--dry-run).")
            return 0

        summary = dispatch(db, [row.id for row in rows])
        print(
            f"Procesadas {len(rows)}: entregadas={summary['sent']} "
            f"encoladas en la gateway={summary['queued']} fallidas={summary['failed']}"
        )
        fallidas = (
            db.query(WorkOrderNotification)
            .filter(WorkOrderNotification.id.in_([row.id for row in rows]), WorkOrderNotification.status == FAILED)
            .all()
        )
        for row in fallidas:
            print(f"  FALLO #{row.id} {LABELS.get(row.channel, row.channel)} -> {row.recipient}: {row.error}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
