"""Maestro de técnicos de la empresa.

El legacy (CiberBase) no tiene maestro de técnicos: en cada OT los "intervinientes" son
personas sueltas y el técnico se elegía de una lista informal. El importador armó un maestro
por empresa con esos nombres (44 en Electrotecniref) para poder consultar el histórico, pero
no había forma de dar de alta uno nuevo ni de asignarlo a una orden.

Este endpoint hace ese maestro manejable desde la aplicación: listar, dar de alta, renombrar y
activar/desactivar. Los técnicos desactivados siguen en las órdenes donde ya estaban (el
histórico no se toca), pero no aparecen para asignar.
"""
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
from app.models.user import User
from app.models.work_area import Technician

router = APIRouter()


class TechnicianRead(BaseModel):
    id: int
    name: str
    active: bool
    legacy_code: int | None = None


class TechnicianInput(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    active: bool = True


class TechnicianUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    active: bool | None = None


def _normalizar(texto: str) -> str:
    """Compara nombres sin distinguir mayúsculas, acentos ni espacios de más."""
    plano = unicodedata.normalize("NFKD", texto.strip().lower())
    base = "".join(
        c
        for c in plano
        if not unicodedata.combining(c) and (c.isalnum() or c.isspace())
    )
    return " ".join(base.split())


def _buscar(db: Session, company_id: int, nombre: str, excluir_id: int | None = None):
    objetivo = _normalizar(nombre)
    for tecnico in db.query(Technician).filter_by(company_id=company_id).all():
        if excluir_id is not None and tecnico.id == excluir_id:
            continue
        if _normalizar(tecnico.name) == objetivo:
            return tecnico
    return None


@router.get("", response_model=list[TechnicianRead])
def list_technicians(
    company_id: int = Depends(get_current_company_id),
    _actor: User = Depends(
        require_any_permission("technicians.view", "work_orders.manage")
    ),
    db: Session = Depends(get_db),
):
    """Lista el maestro de la empresa.

    Se devuelve completo (activo e inactivo) y sin filtrar: el filtro por texto lo hace la
    pantalla, que compara sin acentos ni mayúsculas. El maestro es chico (decenas de personas).
    """
    return (
        db.query(Technician)
        .filter_by(company_id=company_id)
        .order_by(Technician.active.desc(), Technician.name)
        .all()
    )


@router.post("", response_model=TechnicianRead, status_code=201)
def create_technician(
    payload: TechnicianInput,
    company_id: int = Depends(get_current_company_id),
    _actor: User = Depends(require_permission("technicians.manage")),
    db: Session = Depends(get_db),
):
    nombre = " ".join(payload.name.split())
    if not nombre:
        raise HTTPException(422, detail="El nombre del técnico no puede estar vacío.")
    if _buscar(db, company_id, nombre):
        raise HTTPException(409, detail="Ya existe un técnico con ese nombre en esta empresa.")
    tecnico = Technician(
        company_id=company_id, name=nombre, active=payload.active
    )
    db.add(tecnico)
    db.commit()
    db.refresh(tecnico)
    return tecnico


@router.patch("/{technician_id}", response_model=TechnicianRead)
def update_technician(
    technician_id: int,
    payload: TechnicianUpdate,
    company_id: int = Depends(get_current_company_id),
    _actor: User = Depends(require_permission("technicians.manage")),
    db: Session = Depends(get_db),
):
    tecnico = (
        db.query(Technician)
        .filter_by(id=technician_id, company_id=company_id)
        .first()
    )
    if not tecnico:
        raise HTTPException(404, detail="Técnico no encontrado.")
    if payload.name is not None:
        nombre = " ".join(payload.name.split())
        if not nombre:
            raise HTTPException(422, detail="El nombre del técnico no puede estar vacío.")
        if _buscar(db, company_id, nombre, excluir_id=tecnico.id):
            raise HTTPException(409, detail="Ya existe un técnico con ese nombre en esta empresa.")
        tecnico.name = nombre
    if payload.active is not None:
        tecnico.active = payload.active
    db.commit()
    db.refresh(tecnico)
    return tecnico
