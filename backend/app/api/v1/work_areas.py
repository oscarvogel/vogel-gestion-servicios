"""Maestro de áreas de trabajo: la marca, la política, la garantía y a quién se liquida.

En el legacy (CiberBrain) esto no es un campo de la orden: son tres tablas encajadas
(``dbo.Areas``, ``dbo.TiposTrabajos`` y ``dbo.Aux_PoliticasxArea``). La garantía y la
empresa a liquidar salen de la **política** del área, no de la OT.

Acá quedó resuelto en ``work_areas``: una fila es una marca + política, y trae las dos
cosas que el cierre mensual a marcas necesita:

- ``billing_customer_id``: a qué empresa se le liquida (NULL = a nadie).
- ``warranty_type``: 0 fuera de garantía, 1 garantía de terceros, 2 garantía propia.

**Por qué este endpoint es el que faltaba:** el cierre (``app.services.warranty_settlements``)
hace JOIN por ``work_orders.work_area_id`` y exige ``billing_customer_id IS NOT NULL``.
Una OT sin área no tiene empresa a liquidar, así que **no entra al cierre**: las OTs
nacidas en la aplicación no aparecían nunca en "Cierre a marcas", y no había forma de
corregirlo.

La garantía **no se pregunta en la orden**: se deriva del área, que es como funciona el
legacy y como lee el cierre. Si se guardara suelta en la OT, la OT y el cierre
podrían discrepar sin que nadie lo note.
"""
from __future__ import annotations

import unicodedata

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_current_company_id,
    get_db,
    require_any_permission,
    require_permission,
)
from app.core.warranty import ETIQUETA_GARANTIA
from app.models.customer import Customer
from app.models.user import User
from app.models.work_area import WorkArea

router = APIRouter()


class WorkAreaRead(BaseModel):
    id: int
    area_code: str
    area_name: str
    policy_code: str
    policy_description: str | None = None
    is_principal: bool
    billing_customer_id: int | None = None
    billing_customer_name: str | None = None
    warranty_type: int
    warranty_label: str
    liquidate_mode: int
    active: bool


class WorkAreaInput(BaseModel):
    """Alta de un área.

    ``area_code`` es opcional: si no viene, se deriva del nombre (ver ``_codigo_area``).
    ``policy_code`` vacío significa "política principal" del área; no es NULL porque el
    índice único de MySQL trata los NULL como distintos entre sí.
    """

    area_code: str | None = Field(default=None, max_length=20)
    area_name: str = Field(min_length=1, max_length=120)
    policy_code: str | None = Field(default=None, max_length=20)
    policy_description: str | None = Field(default=None, max_length=150)
    billing_customer_id: int | None = None
    warranty_type: int = Field(default=0, ge=0, le=2)
    active: bool = True


class WorkAreaUpdate(BaseModel):
    """Edición de un área.

    Solo se toca lo que viene: ``billing_customer_id: null`` explícito saca la empresa a
    liquidar, pero si el campo no viene, se deja como está.
    """

    area_code: str | None = Field(default=None, max_length=20)
    area_name: str | None = Field(default=None, min_length=1, max_length=120)
    policy_code: str | None = Field(default=None, max_length=20)
    policy_description: str | None = Field(default=None, max_length=150)
    billing_customer_id: int | None = None
    warranty_type: int | None = Field(default=None, ge=0, le=2)
    active: bool | None = None


def _codigo_area(area_name: str) -> str:
    """Código de área derivado del nombre, cuando el operador no escribe uno.

    El código, junto con la política, es la clave única dentro de la empresa. Derivarlo
    evita tener que inventar un código en el alta, pero dos áreas con el mismo nombre
    chocarían: en ese caso el error dice que hay que escribir el código a mano.
    """
    plano = unicodedata.normalize("NFKD", area_name.strip().upper())
    base = "".join(c for c in plano if c.isalnum())
    return base[:20]


def _nombre_area(area: WorkArea) -> str:
    """Como se ve el área en los selectores: marca + política."""
    if area.policy_code:
        return f"{area.area_name} · {area.policy_code}"
    return area.area_name


def _read(area: WorkArea, nombre_empresa: str | None = None) -> dict:
    return {
        "id": area.id,
        "area_code": area.area_code,
        "area_name": area.area_name,
        "policy_code": area.policy_code,
        "policy_description": area.policy_description,
        "is_principal": area.policy_code == "",
        "billing_customer_id": area.billing_customer_id,
        "billing_customer_name": nombre_empresa,
        "warranty_type": area.warranty_type,
        "warranty_label": ETIQUETA_GARANTIA.get(area.warranty_type, ETIQUETA_GARANTIA[0]),
        "liquidate_mode": area.liquidate_mode,
        "active": area.active,
    }


def _cliente(db: Session, company_id: int, billing_customer_id: int | None) -> Customer | None:
    """La empresa a liquidar: tiene que ser un cliente de esta misma empresa."""
    if billing_customer_id is None:
        return None
    cliente = (
        db.query(Customer)
        .filter_by(id=billing_customer_id, company_id=company_id)
        .first()
    )
    if not cliente:
        raise HTTPException(
            422, detail="La empresa a liquidar no es un cliente de esta empresa."
        )
    return cliente


def _revisar_duplicado(
    db: Session, company_id: int, area_code: str, policy_code: str, excluir_id: int | None = None
) -> None:
    existente = (
        db.query(WorkArea)
        .filter_by(company_id=company_id, area_code=area_code, policy_code=policy_code)
        .first()
    )
    if existente and existente.id != excluir_id:
        raise HTTPException(
            409,
            detail=(
                "Ya existe un área con ese código y esa política en esta empresa. "
                "Si es otra política de la misma marca, poné otro código o otra política."
            ),
        )


@router.get("", response_model=list[WorkAreaRead])
def list_work_areas(
    company_id: int = Depends(get_current_company_id),
    _actor: User = Depends(
        require_any_permission("work_areas.view", "work_orders.manage")
    ),
    db: Session = Depends(get_db),
):
    """El maestro de la empresa, activo e inactivo.

    Se devuelve completo y sin filtrar: el filtro por texto lo hace la pantalla, que
    compara sin acentos ni mayúsculas.
    """
    filas = (
        db.query(WorkArea, Customer.name)
        .outerjoin(Customer, Customer.id == WorkArea.billing_customer_id)
        .filter(WorkArea.company_id == company_id)
        .order_by(WorkArea.active.desc(), WorkArea.area_name, WorkArea.policy_code)
        .all()
    )
    return [_read(area, nombre) for area, nombre in filas]


@router.post("", response_model=WorkAreaRead, status_code=201)
def create_work_area(
    payload: WorkAreaInput,
    company_id: int = Depends(get_current_company_id),
    _actor: User = Depends(require_permission("work_areas.manage")),
    db: Session = Depends(get_db),
):
    nombre = " ".join(payload.area_name.split())
    if not nombre:
        raise HTTPException(422, detail="El nombre del área no puede estar vacío.")
    codigo = (payload.area_code or "").strip().upper() or _codigo_area(nombre)
    if not codigo:
        raise HTTPException(
            422,
            detail="El código del área no puede quedar vacío: escribilo a mano.",
        )
    politica = (payload.policy_code or "").strip().upper()
    _revisar_duplicado(db, company_id, codigo, politica)
    cliente = _cliente(db, company_id, payload.billing_customer_id)
    area = WorkArea(
        company_id=company_id,
        area_code=codigo,
        area_name=nombre,
        policy_code=politica,
        policy_description=(payload.policy_description or "").strip() or None,
        is_principal=politica == "",
        billing_customer_id=cliente.id if cliente else None,
        warranty_type=payload.warranty_type,
        active=payload.active,
    )
    db.add(area)
    db.commit()
    db.refresh(area)
    return _read(area, cliente.name if cliente else None)


@router.patch("/{work_area_id}", response_model=WorkAreaRead)
def update_work_area(
    work_area_id: int,
    payload: WorkAreaUpdate,
    company_id: int = Depends(get_current_company_id),
    _actor: User = Depends(require_permission("work_areas.manage")),
    db: Session = Depends(get_db),
):
    area = (
        db.query(WorkArea)
        .filter_by(id=work_area_id, company_id=company_id)
        .first()
    )
    if not area:
        raise HTTPException(404, detail="Área de trabajo no encontrada.")

    data = payload.model_dump(exclude_unset=True)

    codigo = area.area_code
    if "area_code" in data:
        if data["area_code"] is None:
            raise HTTPException(422, detail="El código del área no puede quedar vacío.")
        codigo = data["area_code"].strip().upper()
        if not codigo:
            raise HTTPException(422, detail="El código del área no puede quedar vacío.")

    nombre = area.area_name
    if "area_name" in data and data["area_name"]:
        nombre = " ".join(data["area_name"].split())
        if not nombre:
            raise HTTPException(422, detail="El nombre del área no puede estar vacío.")

    politica = area.policy_code
    if "policy_code" in data:
        politica = (data["policy_code"] or "").strip().upper()

    _revisar_duplicado(db, company_id, codigo, politica, excluir_id=area.id)

    cliente = None
    if "billing_customer_id" in data:
        cliente = _cliente(db, company_id, data["billing_customer_id"])

    garantia_cambio = "warranty_type" in data and data["warranty_type"] != area.warranty_type

    area.area_code = codigo
    area.area_name = nombre
    area.policy_code = politica
    area.is_principal = politica == ""
    if "policy_description" in data:
        area.policy_description = (data["policy_description"] or "").strip() or None
    if "billing_customer_id" in data:
        area.billing_customer_id = cliente.id if cliente else None
    if "warranty_type" in data:
        area.warranty_type = data["warranty_type"]
    if "active" in data and data["active"] is not None:
        area.active = data["active"]

    db.flush()
    if garantia_cambio:
        # La garantia de la OT es una copia de la del area (asi lo dejaba el legacy).
        # Si el area cambia de tipo, las ordenes que la usan tienen que dejar de
        # mostrar la garantia vieja: si no, la OT y el cierre discreparian.
        from app.core.warranty import estado_de_garantia
        from app.models.work_order import WorkOrder

        db.query(WorkOrder).filter(
            WorkOrder.company_id == company_id, WorkOrder.work_area_id == area.id
        ).update(
            {"warranty_status": estado_de_garantia(area.warranty_type)},
            synchronize_session=False,
        )

    db.commit()
    db.refresh(area)
    nombre_empresa = None
    if area.billing_customer_id:
        empresa = db.get(Customer, area.billing_customer_id)
        nombre_empresa = empresa.name if empresa else None
    return _read(area, nombre_empresa)
