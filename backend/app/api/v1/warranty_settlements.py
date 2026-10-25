"""Cierre mensual a marcas: que ordenes estan en garantia y a que empresa hay que liquidarla.

Es el requerimiento nuevo. En el legacy no existia: el cierre a marcas se hacia a mano y no
quedaba registrado. La regla de inclusion y el por que estan asi estan explicados en
``app.services.warranty_settlements``.
"""
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_company_id, get_db, require_permission
from app.models.user import User
from app.models.warranty_settlement import WarrantySettlement
from app.services import warranty_settlements as service

router = APIRouter()


class CierreEmpresaRead(BaseModel):
    billing_customer_id: int
    billing_customer_name: str | None = None
    works_count: int
    total_amount: Decimal
    warranty_works_count: int
    warranty_amount: Decimal
    out_of_warranty_works_count: int
    out_of_warranty_amount: Decimal
    # garantia propia / de service (Alladio). Es garantia, pero no de terceros.
    own_warranty_works_count: int = 0
    own_warranty_amount: Decimal = Decimal(0)
    works: list[dict] = Field(default_factory=list)


class CierreTotalesRead(BaseModel):
    works_count: int
    total_amount: Decimal
    warranty_works_count: int
    warranty_amount: Decimal
    out_of_warranty_works_count: int
    out_of_warranty_amount: Decimal
    own_warranty_works_count: int = 0
    own_warranty_amount: Decimal = Decimal(0)


class CierreReporteRead(BaseModel):
    period: str
    companies: list[CierreEmpresaRead]
    totals: CierreTotalesRead


class CierreObraRead(BaseModel):
    work_order_id: int
    number: int
    legacy_number: str | None = None
    completed_at: datetime | None = None
    client_name: str | None = None
    work_area: str | None = None
    policy_code: str | None = None
    warranty_type: int
    amount: Decimal


class CierreRead(BaseModel):
    id: int
    period: str
    status: str
    billing_customer_id: int
    billing_customer_name: str | None = None
    works_count: int
    total_amount: Decimal
    warranty_works_count: int
    warranty_amount: Decimal
    out_of_warranty_works_count: int
    out_of_warranty_amount: Decimal
    own_warranty_works_count: int = 0
    own_warranty_amount: Decimal = Decimal(0)
    invoice_number: str | None = None
    notes: str | None = None
    generated_at: datetime
    issued_at: datetime | None = None
    settled_at: datetime | None = None
    works: list[CierreObraRead] = Field(default_factory=list)


class CierreListaRead(BaseModel):
    items: list[CierreRead]
    total: int


class GenerarCierreInput(BaseModel):
    period: str = Field(description="Periodo a liquidar, 'AAAA-MM' (por ejemplo '2025-06').")


class LiquidarCierreInput(BaseModel):
    invoice_number: str | None = Field(default=None, max_length=30)


def _periodo_valido(period: str) -> str:
    try:
        service.period_bounds(period)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return period


@router.get("", response_model=CierreReporteRead)
def ver_cierre(
    period: str = Query(..., description="Periodo a liquidar, 'AAAA-MM'"),
    company_id: int = Depends(get_current_company_id),
    _actor: User = Depends(require_permission("warranty_settlements.view")),
    db: Session = Depends(get_db),
):
    """Reporte en vivo: que se le liquida a cada empresa en el periodo.

    No modifica nada. Es la vista previa antes de generar el cierre.
    """
    _periodo_valido(period)
    return service.calcular_cierre(db, company_id, period)


@router.get("/registros", response_model=CierreListaRead)
def listar_cierres(
    period: str | None = Query(default=None, description="Filtra por periodo 'AAAA-MM'"),
    company_id: int = Depends(get_current_company_id),
    _actor: User = Depends(require_permission("warranty_settlements.view")),
    db: Session = Depends(get_db),
):
    """Los cierres ya registrados (los que se generaron y despues se emitieron o liquidaron)."""
    q = db.query(WarrantySettlement).filter(WarrantySettlement.company_id == company_id)
    if period:
        desde, _hasta = service.period_bounds(period)
        q = q.filter(WarrantySettlement.period == desde)
    total = q.count()
    filas = q.order_by(WarrantySettlement.period.desc(), WarrantySettlement.id).all()
    items = [service.detalle_cierre(db, company_id, f.id) for f in filas]
    return CierreListaRead(items=items, total=total)


@router.get("/{settlement_id}", response_model=CierreRead)
def ver_cierre_registrado(
    settlement_id: int,
    company_id: int = Depends(get_current_company_id),
    _actor: User = Depends(require_permission("warranty_settlements.view")),
    db: Session = Depends(get_db),
):
    try:
        return service.detalle_cierre(db, company_id, settlement_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/generate", response_model=CierreReporteRead)
def generar_cierre(
    payload: GenerarCierreInput,
    company_id: int = Depends(get_current_company_id),
    _actor: User = Depends(require_permission("warranty_settlements.manage")),
    db: Session = Depends(get_db),
):
    """Genera los cierres en borrador del periodo y deja el periodo registrado."""
    _periodo_valido(payload.period)
    try:
        return service.generar_cierre(db, company_id, payload.period, _actor)
    except service.CierreInvalido as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# La empresa va en la ruta y no en el cuerpo a proposito: un campo de mas en el cuerpo se
# ignora sin avisar y el pedido terminaria generando todo el periodo.
@router.post("/generate/{billing_customer_id}", response_model=CierreReporteRead)
def generar_cierre_empresa(
    billing_customer_id: int,
    payload: GenerarCierreInput,
    company_id: int = Depends(get_current_company_id),
    _actor: User = Depends(require_permission("warranty_settlements.manage")),
    db: Session = Depends(get_db),
):
    """Genera el cierre en borrador de una sola empresa; las demas del periodo no se tocan."""
    _periodo_valido(payload.period)
    try:
        return service.generar_cierre(db, company_id, payload.period, _actor, billing_customer_id)
    except service.CierreInvalido as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{settlement_id}/issue", response_model=CierreRead)
def emitir_cierre(
    settlement_id: int,
    company_id: int = Depends(get_current_company_id),
    _actor: User = Depends(require_permission("warranty_settlements.manage")),
    db: Session = Depends(get_db),
):
    """Emite el cierre: congela el periodo. Despues de esto los numeros ya no se tocan."""
    try:
        service.cambiar_estado(db, company_id, settlement_id, "issued")
        return service.detalle_cierre(db, company_id, settlement_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except service.CierreInvalido as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{settlement_id}/settle", response_model=CierreRead)
def liquidar_cierre(
    settlement_id: int,
    payload: LiquidarCierreInput,
    company_id: int = Depends(get_current_company_id),
    _actor: User = Depends(require_permission("warranty_settlements.manage")),
    db: Session = Depends(get_db),
):
    """Marca el cierre como liquidado, con el numero de factura de la marca."""
    try:
        service.cambiar_estado(db, company_id, settlement_id, "settled", payload.invoice_number)
        return service.detalle_cierre(db, company_id, settlement_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except service.CierreInvalido as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{settlement_id}/cancel", response_model=CierreRead)
def cancelar_cierre(
    settlement_id: int,
    company_id: int = Depends(get_current_company_id),
    _actor: User = Depends(require_permission("warranty_settlements.manage")),
    db: Session = Depends(get_db),
):
    """Anula el cierre. Sirve para un periodo generado por error, no para tapar una diferencia."""
    try:
        service.cambiar_estado(db, company_id, settlement_id, "cancelled")
        return service.detalle_cierre(db, company_id, settlement_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except service.CierreInvalido as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
