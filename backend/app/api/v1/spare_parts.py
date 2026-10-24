"""API del catalogo de repuestos de Flexxus (#114).

El endpoint es el que ve el frontend. No decide nada de negocio: el servicio
`app.services.spare_parts` ya resolvio la habilitacion por empresa.

Respuesta siempre 200, con `disponible` en false cuando el modulo no aplica
o el ERP no responde. Asi el frontend puede distinguishes los tres casos con
el mismo camino de codigo:

- `disponible: true`  -> hay resultados (puede ser la lista vacia).
- `disponible: false` -> no aplica a esta empresa, o el ERP no respondio.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_company_id, get_db, require_permission
from app.models.user import User
from app.services import spare_parts

router = APIRouter()


class SparePartRead(BaseModel):
    code: str
    description: str
    rubro_code: str | None = None
    rubro: str | None = None
    marca_code: str | None = None
    marca: str | None = None
    stock: float | None = None
    stock_minimo: float | None = None
    cost: float | None = None
    cost_currency: str = "ARS"
    cost_source_currency: str | None = None
    sale_price: float | None = None
    sale_price_currency: str = "ARS"
    price_source: str | None = None
    price_synced_at: dt.datetime | None = None


class SparePartSearchResponse(BaseModel):
    disponible: bool
    aviso: str | None = None
    items: list[SparePartRead]


class SparePartStatusResponse(BaseModel):
    disponible: bool
    motivo: str | None = None
    # True cuando el catalogo corresponde pero no se puede usar (ERP caido,
    # credencial faltante). False cuando la empresa simplemente no tiene el
    # modulo: en ese caso no se muestra ningun aviso, porque no hay nada que
    # avisar y la pantalla se ve igual que antes del modulo.
    falla: bool = False


@router.get("/status", response_model=SparePartStatusResponse)
def estado_del_catalogo(
    company_id: int = Depends(get_current_company_id),
    _actor: User = Depends(require_permission("work_orders.view")),
    db: Session = Depends(get_db),
):
    """Si el catalogo de repuestos aplica a esta empresa.

    **No abre conexion al ERP**: el frontend lo consulta al montar el combo
    para saber si tiene que exigir elegir una opcion o si deja escribir a
    mano (que es lo que corresponde cuando el ERP esta caido).
    """
    return spare_parts.estado(db, company_id)


@router.get("/search", response_model=SparePartSearchResponse)
def buscar_repuestos(
    q: str = Query(min_length=1, max_length=120),
    limit: int = Query(default=20, ge=1, le=50),
    company_id: int = Depends(get_current_company_id),
    _actor: User = Depends(require_permission("work_orders.view")),
    db: Session = Depends(get_db),
):
    """Busca repuestos por codigo o descripcion en el catalogo de Flexxus.

    El tenant sale del token (`get_current_company_id`), nunca de un
    `company_id` que mande el frontend: no hay forma de pedir el catalogo de
    otra empresa.
    """
    resultado = spare_parts.buscar_repuestos(db, company_id, q, limite=limit)
    return {
        "disponible": resultado["disponible"],
        "aviso": resultado["aviso"],
        "items": resultado["items"],
    }
