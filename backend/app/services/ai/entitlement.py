"""Entitlement del modulo IA por empresa.

La IA es un adicional comercial: se habilita por empresa y se mide por empresa. Apagada
por default, para que una empresa que no lo contrate no vea nada aunque haya key cargada
en la plataforma.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.company import Company, CompanyParameter, ParameterDefinition

PARAM_ENABLED = "ai.enabled"
PARAM_MONTHLY_QUOTA_USD = "ai.monthly_quota_usd"
PARAM_MONTHLY_REQUEST_LIMIT = "ai.monthly_request_limit"


def read_parameter(db: Session, company_id: int, name: str, default: str = "") -> str:
    """Valor efectivo del parametro: el override de la empresa o el default del catalogo.

    Se resuelve con la misma precedencia que usa la pantalla de Parametros, para que lo
    que el usuario ve configurado sea lo que la IA realmente respeta.
    """
    definition = db.query(ParameterDefinition).filter_by(parameter=name, active=True).first()
    if definition is None:
        return default
    override = db.query(CompanyParameter).filter_by(parameter_definition_id=definition.id, company_id=company_id).first()
    return (override.value if override and override.value is not None else definition.default_value) or default


def is_enabled(db: Session, company_id: int) -> bool:
    raw = read_parameter(db, company_id, PARAM_ENABLED, "false").strip().lower()
    return raw in ("1", "true", "yes", "si", "sí", "on")


def monthly_quota_usd(db: Session, company_id: int) -> float:
    """0 significa sin cuota. Un presupuesto negativo se trata como sin cuota."""
    try:
        value = float(read_parameter(db, company_id, PARAM_MONTHLY_QUOTA_USD, "0").strip() or 0)
    except (TypeError, ValueError):
        return 0.0
    return value if value > 0 else 0.0


def monthly_request_limit(db: Session, company_id: int) -> int:
    try:
        value = int(float(read_parameter(db, company_id, PARAM_MONTHLY_REQUEST_LIMIT, "0").strip() or 0))
    except (TypeError, ValueError):
        return 0
    return value if value > 0 else 0
