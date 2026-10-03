"""Registro de uso de IA: lo que se mide y lo que se factura.

Cada pedido al proveedor deja una fila, este vaya bien o mal. Un proveedor caido tiene que
quedar registrado: si solo anotamos los exitos, el acumulado de consumo miente justo cuando
la cosa esta peor.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ai_usage import AiUsage
from app.services.ai.providers.base import LlmResponse

OK = "OK"
ERROR = "ERROR"
SIN_PERMISO = "SIN_PERMISO"
SIN_CUOTA = "SIN_CUOTA"


def _month_start() -> datetime:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> Decimal:
    """Costo estimado con los precios por millon de tokens de la plataforma.

    Se estima y no se factura: el precio real lo manda la proveedor. El acumulado es para
    medir y para el additional de la empresa, no para cobrar centavo exacto.
    """
    millions = Decimal(input_tokens) / Decimal(1_000_000)
    millions_out = Decimal(output_tokens) / Decimal(1_000_000)
    value = millions * Decimal(str(settings.ai_price_input_per_million_usd)) + millions_out * Decimal(
        str(settings.ai_price_output_per_million_usd)
    )
    return value.quantize(Decimal("0.000001"))


def record(
    db: Session,
    company_id: int,
    provider: str,
    model: str,
    operation: str,
    *,
    user_id: int | None = None,
    response: LlmResponse | None = None,
    duration_ms: int = 0,
    status: str = OK,
    error: str | None = None,
) -> AiUsage:
    input_tokens = response.input_tokens if response else 0
    output_tokens = response.output_tokens if response else 0
    if response and response.raw.get("duration_ms"):
        duration_ms = int(response.raw["duration_ms"]) or duration_ms
    row = AiUsage(
        company_id=company_id,
        user_id=user_id,
        provider=provider,
        model=model,
        operation=operation,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=estimate_cost_usd(input_tokens, output_tokens) if response else Decimal("0"),
        duration_ms=duration_ms,
        status=status,
        error=(error or None) if error else None,
    )
    db.add(row)
    db.commit()
    return row


def month_totals(db: Session, company_id: int) -> dict:
    start = _month_start()
    total_requests = (
        db.query(func.count(AiUsage.id))
        .filter(AiUsage.company_id == company_id, AiUsage.created_at >= start)
        .scalar()
        or 0
    )
    # Las conversaciones con el usuario tambien consumen, asi que se cuentan para la cuota.
    billed = (
        db.query(func.count(AiUsage.id))
        .filter(
            AiUsage.company_id == company_id,
            AiUsage.created_at >= start,
            AiUsage.status.in_([OK, ERROR]),
        )
        .scalar()
        or 0
    )
    cost = (
        db.query(func.coalesce(func.sum(AiUsage.cost_usd), 0))
        .filter(AiUsage.company_id == company_id, AiUsage.created_at >= start)
        .scalar()
        or Decimal("0")
    )
    tokens = (
        db.query(
            func.coalesce(func.sum(AiUsage.input_tokens), 0),
            func.coalesce(func.sum(AiUsage.output_tokens), 0),
        )
        .filter(AiUsage.company_id == company_id, AiUsage.created_at >= start)
        .one()
    )
    return {
        "period_start": start,
        "requests": int(billed),
        "registros": int(total_requests),
        "cost_usd": float(cost),
        "input_tokens": int(tokens[0]),
        "output_tokens": int(tokens[1]),
    }


def last_period_cost(db: Session, company_id: int) -> float:
    """Costo del mes anterior, para mostrar la tendencia en la pantalla."""
    start = _month_start()
    previous_start = start - timedelta(days=1)
    value = (
        db.query(func.coalesce(func.sum(AiUsage.cost_usd), 0))
        .filter(AiUsage.company_id == company_id, AiUsage.created_at >= previous_start, AiUsage.created_at < start)
        .scalar()
        or Decimal("0")
    )
    return float(value)
