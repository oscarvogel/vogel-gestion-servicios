from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_company_id, get_db, require_company_admin_or_superadmin
from app.models.company import CompanyParameter, ParameterDefinition
from app.models.user import User

router=APIRouter()

class ParameterRead(BaseModel):
    parameter:str
    value:Any
    default_value:Any
    is_overridden:bool
    description:str
    data_type:str
    category:str
    editable:bool

class ParameterUpdate(BaseModel):
    value:Any

def _decode(value:str,data_type:str)->Any:
    if data_type=="bool": return str(value).lower() in ("1","true","yes","on")
    if data_type=="integer": return int(value)
    if data_type=="decimal": return float(value)
    return value

def _encode(definition:ParameterDefinition,value:Any)->str:
    if definition.data_type=="bool":
        if not isinstance(value,bool): raise HTTPException(422,detail="El parámetro requiere un valor verdadero/falso.")
        return "true" if value else "false"
    if definition.data_type=="integer":
        try:return str(int(value))
        except (TypeError,ValueError):raise HTTPException(422,detail="El parámetro requiere un número entero.")
    if definition.data_type=="decimal":
        try:
            number=float(value)
            if number<0: raise ValueError
            return str(number)
        except (TypeError,ValueError):raise HTTPException(422,detail="El parámetro requiere un número mayor o igual a cero.")
    return str(value)

def _read(definition:ParameterDefinition,override:CompanyParameter|None)->ParameterRead:
    effective=override.value if override else definition.default_value
    return ParameterRead(parameter=definition.parameter,value=_decode(effective,definition.data_type),default_value=_decode(definition.default_value,definition.data_type),is_overridden=override is not None,description=definition.description,data_type=definition.data_type,category=definition.category,editable=definition.editable)

@router.get("",response_model=list[ParameterRead])
def list_parameters(company_id:int=Depends(get_current_company_id),db:Session=Depends(get_db)):
    definitions=db.query(ParameterDefinition).filter_by(active=True).order_by(ParameterDefinition.category,ParameterDefinition.parameter).all()
    overrides={r.parameter_definition_id:r for r in db.query(CompanyParameter).filter_by(company_id=company_id).all()}
    return [_read(d,overrides.get(d.id)) for d in definitions]

@router.patch("/{parameter:path}",response_model=ParameterRead)
def update_parameter(parameter:str,payload:ParameterUpdate,company_id:int=Depends(get_current_company_id),_admin:User=Depends(require_company_admin_or_superadmin),db:Session=Depends(get_db)):
    definition=db.query(ParameterDefinition).filter_by(parameter=parameter,active=True).first()
    if not definition:raise HTTPException(404,detail="Parámetro no encontrado.")
    if not definition.editable:raise HTTPException(403,detail="Este parámetro no es editable.")
    encoded=_encode(definition,payload.value)
    override=db.query(CompanyParameter).filter_by(company_id=company_id,parameter_definition_id=definition.id).first()
    if encoded==definition.default_value:
        if override:db.delete(override)
        db.commit()
        return _read(definition,None)
    if override:override.value=encoded
    else:
        override=CompanyParameter(company_id=company_id,parameter_definition_id=definition.id,value=encoded);db.add(override)
    db.commit();db.refresh(override)
    return _read(definition,override)
