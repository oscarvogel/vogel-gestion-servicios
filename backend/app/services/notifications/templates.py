"""Render de plantillas de aviso al cliente.

Solo una lista blanca de variables, resueltas contra la OT de la empresa del tenant. No
hay forma de alcanzar datos de otra empresa ni de escribir properties arbitrarias: el
contexto se arma aqui, no se pasa entero.

Un placeholder desconocido se deja literal a proposito. Si un administrador escribe
{{client}} en vez de {{cliente}}, el cliente ve {{client}} y el error se ve solo; vaciarlo
mandaria un mensaje roto sin ninguna senal.
"""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.customer import Customer, Equipment, EquipmentCategory
from app.models.work_order import WorkOrder, WorkOrderStatus

PLACEHOLDER = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")

# Se exponen al frontend para que la pantalla de configuracion documente las variables.
TEMPLATE_VARIABLES = [
    "cliente", "telefono", "email_cliente",
    "numero_ot", "equipo", "equipo_serie", "falla",
    "estado", "estado_anterior",
    "fecha_recepcion", "fecha_prevista", "fecha_finalizacion", "fecha_entrega",
    "empresa", "empresa_telefono", "empresa_email",
]

DEFAULT_TEMPLATE = "Hola {{cliente}}, tu orden de trabajo N° {{numero_ot}} ({{equipo}}) pasó a: {{estado}}."


def _fecha(value) -> str:
    return value.strftime("%d/%m/%Y %H:%M") if value else "a confirmar"


def build_context(
    db: Session,
    company: Company,
    order: WorkOrder,
    status: WorkOrderStatus | None = None,
    previous_status: WorkOrderStatus | None = None,
) -> dict[str, str]:
    """Arma el contexto de una plantilla, siempre desde el tenant ya validado."""
    customer = db.query(Customer).filter_by(id=order.customer_id, company_id=company.id).first()
    equipment = db.query(Equipment).filter_by(id=order.equipment_id, company_id=company.id).first()
    label = ""
    if equipment:
        category = db.query(EquipmentCategory).filter_by(id=equipment.category_id, company_id=company.id).first()
        label = " ".join(x for x in ((category.name if category else None), equipment.brand, equipment.model) if x)
    return {
        "cliente": (customer.name if customer else "") or "",
        "telefono": ((customer.whatsapp or customer.phone) if customer else "") or "",
        "email_cliente": (customer.email if customer else "") or "",
        "numero_ot": str(order.number),
        "equipo": label,
        "equipo_serie": (equipment.serial_number if equipment else "") or "",
        "falla": (order.reported_fault or "") or "",
        "estado": (status.name if status else "") or "",
        "estado_anterior": (previous_status.name if previous_status else "") or "",
        "fecha_recepcion": _fecha(order.received_at),
        "fecha_prevista": _fecha(order.expected_delivery_at),
        "fecha_finalizacion": _fecha(order.completed_at),
        "fecha_entrega": _fecha(order.delivered_at),
        "empresa": company.name or "",
        "empresa_telefono": company.phone or "",
        "empresa_email": company.notification_sender_email or "",
    }


def render(template: str | None, context: dict[str, str]) -> str:
    """Reemplaza los placeholders conocidos y deja intactos los desconocidos."""
    text = (template or "").strip()
    if not text:
        text = DEFAULT_TEMPLATE
    return PLACEHOLDER.sub(lambda m: context.get(m.group(1), m.group(0)), text)


def unknown_variables(template: str | None, context: dict[str, str]) -> list[str]:
    """Placeholders que no existen en el contexto, para avisarle a quien configura."""
    if not template:
        return []
    return sorted({m.group(1) for m in PLACEHOLDER.finditer(template) if m.group(1) not in context})
