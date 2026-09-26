from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_company_id, get_db, require_company_admin_or_superadmin
from app.models.company import CompanyParameter
from app.models.user import User

router=APIRouter()

DEFAULTS=[
 ("work_orders.use_diagnosis","true","Habilita diagnóstico técnico formal en las órdenes de trabajo.","bool","ordenes"),
 ("work_orders.use_budget","true","Habilita presupuestos dentro del circuito de órdenes de trabajo.","bool","ordenes"),
 ("work_orders.require_budget_approval","true","Habilita el registro de aprobación o rechazo de presupuestos.","bool","ordenes"),
 ("work_orders.show_internal_costs","true","Habilita costos internos y margen para la empresa.","bool","precios"),
 ("work_orders.use_final_tests","true","Habilita el registro de pruebas finales.","bool","ordenes"),
 ("pricing.parts_markup_percent","35","Recargo predeterminado sobre el costo de repuestos. Sugiere precio de venta y puede modificarse en cada OT.","decimal","precios"),
]

class ParameterRead(BaseModel):
    parameter:str
    value:Any
    description:str
    data_type:str
    category:str
    editable:bool

class ParameterUpdate(BaseModel):
    value:Any

def _decode(row:CompanyParameter)->Any:
    if row.data_type=="bool": return str(row.value).lower() in ("1","true","yes","on")
    if row.data_type=="integer": return int(row.value)
    if row.data_type=="decimal": return float(row.value)
    return row.value

def _encode(row:CompanyParameter,value:Any)->str:
    if row.data_type=="bool":
        if not isinstance(value,bool): raise HTTPException(422,detail="El parámetro requiere un valor verdadero/falso.")
        return "true" if value else "false"
    if row.data_type=="integer":
        try:return str(int(value))
        except (TypeError,ValueError):raise HTTPException(422,detail="El parámetro requiere un número entero.")
    if row.data_type=="decimal":
        try:
            number=float(value)
            if number<0: raise ValueError
            return str(number)
        except (TypeError,ValueError):raise HTTPException(422,detail="El parámetro requiere un número mayor o igual a cero.")
    return str(value)

def seed_company_parameters(db:Session,company_id:int)->None:
    existing={r[0] for r in db.query(CompanyParameter.parameter).filter_by(company_id=company_id).all()}
    for p,v,d,t,c in DEFAULTS:
        if p not in existing:db.add(CompanyParameter(company_id=company_id,parameter=p,value=v,description=d,data_type=t,category=c,editable=True))

@router.get("",response_model=list[ParameterRead])
def list_parameters(company_id:int=Depends(get_current_company_id),db:Session=Depends(get_db)):
    rows=db.query(CompanyParameter).filter_by(company_id=company_id).order_by(CompanyParameter.category,CompanyParameter.parameter).all()
    return [ParameterRead(parameter=r.parameter,value=_decode(r),description=r.description,data_type=r.data_type,category=r.category,editable=r.editable) for r in rows]

@router.patch("/{parameter:path}",response_model=ParameterRead)
def update_parameter(parameter:str,payload:ParameterUpdate,company_id:int=Depends(get_current_company_id),_admin:User=Depends(require_company_admin_or_superadmin),db:Session=Depends(get_db)):
    row=db.query(CompanyParameter).filter_by(company_id=company_id,parameter=parameter).first()
    if not row:raise HTTPException(404,detail="Parámetro no encontrado.")
    if not row.editable:raise HTTPException(403,detail="Este parámetro no es editable.")
    row.value=_encode(row,payload.value);db.commit();db.refresh(row)
    return ParameterRead(parameter=row.parameter,value=_decode(row),description=row.description,data_type=row.data_type,category=row.category,editable=row.editable)
