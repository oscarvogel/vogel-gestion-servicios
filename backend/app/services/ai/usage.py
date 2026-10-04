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


def _month_start(meses_atras: int = 0) -> datetime:
    """Primer instante del mes, en UTC sin zona. ``meses_atras=1`` es el mes previo.

    Se hace aritmetica de meses en Python y no en SQL a proposito: la suite corre en SQLite y
    la migracion en MySQL, y las funciones de fecha no son las mismas en los dos motores.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if meses_atras == 0:
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total = now.year * 12 + (now.month - 1) - meses_atras
    year, month = divmod(total, 12)
    return datetime(year, month + 1, 1)


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


def desglose_por_operacion(db: Session, company_id: int, start: datetime) -> list[dict]:
    """Cuanto consumio cada tipo de operacion en el periodo.

    El desglose importa para entender el gasto: 300 pedidos de `chat` y 2 de `transcripcion`
    no se facturan igual, y un consumo que se dispara de golpe tiene que poder atribuirse a
    una operacion concreta antes de ir a buscarla.
    """
    filas = (
        db.query(
            AiUsage.operation,
            func.count(AiUsage.id),
            func.coalesce(func.sum(AiUsage.cost_usd), 0),
            func.coalesce(func.sum(AiUsage.input_tokens), 0),
            func.coalesce(func.sum(AiUsage.output_tokens), 0),
        )
        .filter(AiUsage.company_id == company_id, AiUsage.created_at >= start)
        .group_by(AiUsage.operation)
        .order_by(func.sum(AiUsage.cost_usd).desc())
        .all()
    )
    return [
        {
            "operation": operacion,
            "requests": int(pedidos),
            "cost_usd": float(costo),
            "input_tokens": int(entrada),
            "output_tokens": int(salida),
        }
        for operacion, pedidos, costo, entrada, salida in filas
    ]


def historial_mensual(db: Session, company_id: int, meses: int = 12) -> list[dict]:
    """Un acumulado por mes, para el historial con el que se factura el adicional.

    Los cortes de mes se calculan en Python en vez de usar `date_trunc` o `strftime` a
    proposito: la suite corre en SQLite y la migracion en MySQL, y las funciones de fecha no
    son las mismas. Un rango por mes funciona en los dos motores sin una sola funcion
    dependiente del motor.
    """
    if meses < 1 or meses > 36:
        meses = 12
    # El mes en curso no tiene corte: se toma un limite holgado hacia adelante, que para una
    # fila creada ahora es indistinguible de "hasta el final del mes".
    fin_del_curso = datetime(2999, 1, 1)
    filas = []
    for atras in range(meses - 1, -1, -1):
        desde = _month_start(atras)
        # El fin del mes `atras` es el primer instante del mes siguiente, o sea `_month_start`
        # del mes `atras - 1`. La fila va con `created_at < fin` para que los cortes no se
        # pisen entre meses.
        fin = _month_start(atras - 1) if atras else fin_del_curso
        fila = (
            db.query(
                func.count(AiUsage.id),
                func.coalesce(func.sum(AiUsage.cost_usd), 0),
                func.coalesce(func.sum(AiUsage.input_tokens), 0),
                func.coalesce(func.sum(AiUsage.output_tokens), 0),
            )
            .filter(AiUsage.company_id == company_id, AiUsage.created_at >= desde, AiUsage.created_at < fin)
            .one()
        )
        filas.append(
            {
                "period_start": desde.replace(day=1),
                "requests": int(fila[0]),
                "cost_usd": float(fila[1]),
                "input_tokens": int(fila[2]),
                "output_tokens": int(fila[3]),
            }
        )
    return filas
