from decimal import Decimal,ROUND_HALF_UP
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_company_id,get_db,require_permission
from app.models.company import CompanyParameter,ParameterDefinition
from app.models.user import User
from app.models.work_order import WorkOrder,WorkOrderEvent,WorkOrderStatus
from app.models.work_order_quote import WorkOrderDiagnosis,WorkOrderQuote,WorkOrderQuoteItem
router=APIRouter()
class DiagnosisInput(BaseModel):
    diagnosis:str=Field(min_length=1)
    technical_notes:str|None=None
class ItemInput(BaseModel):
    item_type:str=Field(pattern="^(PART|LABOR)$")
    description:str=Field(min_length=1,max_length=250)
    quantity:Decimal=Field(gt=0)
    unit_cost:Decimal=Field(ge=0)
    unit_price:Decimal|None=Field(default=None,ge=0)
class QuoteInput(BaseModel):
    items:list[ItemInput]=Field(min_length=1)
    notes:str|None=None
def order(db,cid,oid):
    row=db.query(WorkOrder).filter_by(id=oid,company_id=cid).first()
    if not row:raise HTTPException(404,"Orden de trabajo no encontrada.")
    return row
def parameter_bool(db,cid,key,default=True):
    d=db.query(ParameterDefinition).filter_by(parameter=key,active=True).first()
    if not d:return default
    o=db.query(CompanyParameter).filter_by(company_id=cid,parameter_definition_id=d.id).first()
    raw=(o.value if o else d.default_value)
    return str(raw).strip().lower() in ("1","true","yes","si","sí","on")

def markup(db,cid):
    d=db.query(ParameterDefinition).filter_by(parameter="pricing.parts_markup_percent",active=True).first()
    if not d:return Decimal("0")
    o=db.query(CompanyParameter).filter_by(company_id=cid,parameter_definition_id=d.id).first()
    return Decimal(o.value if o else d.default_value)
def money(v):return Decimal(v).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
def quote_read(db,row):
    items=db.query(WorkOrderQuoteItem).filter_by(quote_id=row.id,company_id=row.company_id).order_by(WorkOrderQuoteItem.id).all()
    return {"id":row.id,"work_order_id":row.work_order_id,"version":row.version,"status":row.status,"notes":row.notes,"subtotal_parts":row.subtotal_parts,"subtotal_labor":row.subtotal_labor,"total":row.total,"created_at":row.created_at,"items":[{"id":i.id,"item_type":i.item_type,"description":i.description,"quantity":i.quantity,"unit_cost":i.unit_cost,"markup_percent":i.markup_percent,"unit_price":i.unit_price,"line_total":i.line_total} for i in items]}
@router.get("/{oid}/diagnosis")
def get_diagnosis(oid:int,cid:int=Depends(get_current_company_id),_a:User=Depends(require_permission("work_orders.view")),db:Session=Depends(get_db)):
    order(db,cid,oid);d=db.query(WorkOrderDiagnosis).filter_by(company_id=cid,work_order_id=oid).first()
    return None if not d else {"id":d.id,"diagnosis":d.diagnosis,"technical_notes":d.technical_notes,"diagnosed_at":d.diagnosed_at,"updated_at":d.updated_at}
@router.put("/{oid}/diagnosis")
def save_diagnosis(oid:int,p:DiagnosisInput,cid:int=Depends(get_current_company_id),a:User=Depends(require_permission("work_orders.manage")),db:Session=Depends(get_db)):
    wo=order(db,cid,oid)
    if not parameter_bool(db,cid,"work_orders.use_diagnosis",True):raise HTTPException(409,"El diagnóstico técnico está deshabilitado para esta empresa.")
    d=db.query(WorkOrderDiagnosis).filter_by(company_id=cid,work_order_id=oid).first()
    if d:d.diagnosis=p.diagnosis.strip();d.technical_notes=p.technical_notes
    else:d=WorkOrderDiagnosis(company_id=cid,work_order_id=oid,diagnosis=p.diagnosis.strip(),technical_notes=p.technical_notes,diagnosed_by_user_id=a.id);db.add(d)
    db.add(WorkOrderEvent(company_id=cid,work_order_id=oid,event_type="DIAGNOSIS",status=wo.status,detail="Diagnóstico técnico guardado.",user_id=a.id));db.commit();db.refresh(d)
    return {"id":d.id,"diagnosis":d.diagnosis,"technical_notes":d.technical_notes,"diagnosed_at":d.diagnosed_at,"updated_at":d.updated_at}
@router.get("/{oid}/quotes")
def list_quotes(oid:int,cid:int=Depends(get_current_company_id),_a:User=Depends(require_permission("work_orders.view")),db:Session=Depends(get_db)):
    order(db,cid,oid);return [quote_read(db,row) for row in db.query(WorkOrderQuote).filter_by(company_id=cid,work_order_id=oid).order_by(WorkOrderQuote.version.desc()).all()]
@router.post("/{oid}/quotes",status_code=201)
def create_quote(oid:int,p:QuoteInput,cid:int=Depends(get_current_company_id),a:User=Depends(require_permission("work_orders.manage")),db:Session=Depends(get_db)):
    wo=order(db,cid,oid)
    if not parameter_bool(db,cid,"work_orders.use_budget",True):raise HTTPException(409,"Los presupuestos están deshabilitados para esta empresa.")
    if parameter_bool(db,cid,"work_orders.use_diagnosis",True) and not db.query(WorkOrderDiagnosis).filter_by(company_id=cid,work_order_id=oid).first():raise HTTPException(422,"Primero debe registrar el diagnóstico técnico.")
    version=(db.query(func.max(WorkOrderQuote.version)).filter_by(company_id=cid,work_order_id=oid).scalar() or 0)+1
    row=WorkOrderQuote(company_id=cid,work_order_id=oid,version=version,status="ISSUED",notes=p.notes,created_by_user_id=a.id);db.add(row);db.flush()
    default_markup=markup(db,cid);parts=Decimal("0");labor=Decimal("0")
    for x in p.items:
        m=default_markup if x.item_type=="PART" else Decimal("0");price=money(x.unit_price if x.unit_price is not None else (x.unit_cost*(Decimal("1")+m/Decimal("100"))));total=money(x.quantity*price)
        db.add(WorkOrderQuoteItem(company_id=cid,quote_id=row.id,item_type=x.item_type,description=x.description.strip(),quantity=x.quantity,unit_cost=money(x.unit_cost),markup_percent=m,unit_price=price,line_total=total))
        if x.item_type=="PART":parts+=total
        else:labor+=total
    row.subtotal_parts=money(parts);row.subtotal_labor=money(labor);row.total=money(parts+labor)
    db.add(WorkOrderEvent(company_id=cid,work_order_id=oid,event_type="QUOTE_CREATED",status=wo.status,detail="Presupuesto v%d generado por $%s."%(version,row.total),user_id=a.id))
    target=db.query(WorkOrderStatus).filter_by(company_id=cid,name="Presupuestado",active=True).first()
    if target and wo.status_id!=target.id:
        previous=db.get(WorkOrderStatus,wo.status_id) if wo.status_id else None
        wo.status_id=target.id;wo.status=target.name.upper().replace(" ","_")[:30]
        db.add(WorkOrderEvent(company_id=cid,work_order_id=oid,event_type="STATUS_CHANGE",status=wo.status,detail="Estado cambiado de %s a %s al emitir el presupuesto."%((previous.name if previous else "sin estado"),target.name),user_id=a.id))
    db.commit();db.refresh(row);return quote_read(db,row)
