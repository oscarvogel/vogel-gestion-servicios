from datetime import datetime
from decimal import Decimal,ROUND_HALF_UP
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_company_id,get_db,require_permission
from app.models.user import User
from app.models.work_order import WorkOrder,WorkOrderEvent,WorkOrderStatus
from app.models.work_order_quote import WorkOrderQuote,WorkOrderQuoteItem
from app.models.work_order_repair import WorkOrderRepair,WorkOrderRepairItem
router=APIRouter()

class RepairItemInput(BaseModel):
    item_type:str=Field(pattern="^(PART|LABOR)$")
    description:str=Field(min_length=1,max_length=250)
    quantity:Decimal=Field(gt=0)
    unit_cost:Decimal=Field(ge=0)
    unit_price:Decimal=Field(ge=0)
class RepairInput(BaseModel):
    technician_user_id:int|None=None
    notes:str|None=None
    final_tests:str|None=None
    items:list[RepairItemInput]=Field(default_factory=list)
class FinishInput(BaseModel):
    final_tests:str|None=None
    note:str|None=None

def _order(db,cid,oid):
    row=db.query(WorkOrder).filter_by(id=oid,company_id=cid).first()
    if not row:raise HTTPException(404,"Orden de trabajo no encontrada.")
    return row
def _money(v):return Decimal(v).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
def _read(db,row):
    if not row:return None
    items=db.query(WorkOrderRepairItem).filter_by(company_id=row.company_id,repair_id=row.id).order_by(WorkOrderRepairItem.id).all()
    return {"id":row.id,"work_order_id":row.work_order_id,"technician_user_id":row.technician_user_id,"notes":row.notes,"final_tests":row.final_tests,"started_at":row.started_at,"finished_at":row.finished_at,
      "items":[{"id":i.id,"item_type":i.item_type,"description":i.description,"quantity":i.quantity,"unit_cost":i.unit_cost,"unit_price":i.unit_price,"line_cost":i.line_cost,"line_total":i.line_total} for i in items],
      "total_cost":sum((i.line_cost for i in items),Decimal("0")),"total_price":sum((i.line_total for i in items),Decimal("0"))}
def _move_completed(db,cid,wo,user_id):
    target=db.query(WorkOrderStatus).filter_by(company_id=cid,marks_completed=True,active=True).order_by(WorkOrderStatus.sort_order).first()
    if not target:raise HTTPException(409,"La empresa no tiene configurado un estado que marque la OT como lista/finalizada.")
    previous=db.get(WorkOrderStatus,wo.status_id) if wo.status_id else None
    wo.status_id=target.id;wo.status=target.name.upper().replace(" ","_")[:30];wo.completed_at=wo.completed_at or datetime.utcnow()
    db.add(WorkOrderEvent(company_id=cid,work_order_id=wo.id,event_type="STATUS_CHANGE",status=wo.status,detail="Reparación finalizada. Estado: %s → %s."%((previous.name if previous else "sin estado"),target.name),user_id=user_id))

@router.get("/{oid}/repair")
def get_repair(oid:int,cid:int=Depends(get_current_company_id),_a:User=Depends(require_permission("work_orders.view")),db:Session=Depends(get_db)):
    _order(db,cid,oid);return _read(db,db.query(WorkOrderRepair).filter_by(company_id=cid,work_order_id=oid).first())

@router.post("/{oid}/repair/from-approved-quote",status_code=201)
def start_from_quote(oid:int,cid:int=Depends(get_current_company_id),a:User=Depends(require_permission("work_orders.manage")),db:Session=Depends(get_db)):
    wo=_order(db,cid,oid)
    if db.query(WorkOrderRepair).filter_by(company_id=cid,work_order_id=oid).first():raise HTTPException(409,"La reparación ya fue iniciada.")
    q=db.query(WorkOrderQuote).filter_by(company_id=cid,work_order_id=oid,status="APPROVED").order_by(WorkOrderQuote.version.desc()).first()
    if not q:raise HTTPException(409,"No hay un presupuesto aprobado para usar como base.")
    row=WorkOrderRepair(company_id=cid,work_order_id=oid,technician_user_id=a.id);db.add(row);db.flush()
    for i in db.query(WorkOrderQuoteItem).filter_by(company_id=cid,quote_id=q.id).order_by(WorkOrderQuoteItem.id):
        db.add(WorkOrderRepairItem(company_id=cid,repair_id=row.id,item_type=i.item_type,description=i.description,quantity=i.quantity,unit_cost=i.unit_cost,unit_price=i.unit_price,line_cost=_money(i.quantity*i.unit_cost),line_total=_money(i.quantity*i.unit_price)))
    db.add(WorkOrderEvent(company_id=cid,work_order_id=oid,event_type="REPAIR_STARTED",status=wo.status,detail="Reparación iniciada tomando como base el presupuesto aprobado v%d. Los consumos reales quedan editables."%q.version,user_id=a.id))
    db.commit();db.refresh(row);return _read(db,row)

@router.put("/{oid}/repair")
def save_repair(oid:int,p:RepairInput,cid:int=Depends(get_current_company_id),a:User=Depends(require_permission("work_orders.manage")),db:Session=Depends(get_db)):
    wo=_order(db,cid,oid);row=db.query(WorkOrderRepair).filter_by(company_id=cid,work_order_id=oid).first()
    if row and row.finished_at:raise HTTPException(409,"La reparación ya fue finalizada.")
    if not row:row=WorkOrderRepair(company_id=cid,work_order_id=oid);db.add(row);db.flush()
    row.technician_user_id=p.technician_user_id or a.id;row.notes=p.notes;row.final_tests=p.final_tests
    db.query(WorkOrderRepairItem).filter_by(company_id=cid,repair_id=row.id).delete()
    for x in p.items:
        db.add(WorkOrderRepairItem(company_id=cid,repair_id=row.id,item_type=x.item_type,description=x.description.strip(),quantity=x.quantity,unit_cost=_money(x.unit_cost),unit_price=_money(x.unit_price),line_cost=_money(x.quantity*x.unit_cost),line_total=_money(x.quantity*x.unit_price)))
    db.add(WorkOrderEvent(company_id=cid,work_order_id=oid,event_type="REPAIR_SAVED",status=wo.status,detail="Trabajo real de reparación actualizado.",user_id=a.id))
    db.commit();db.refresh(row);return _read(db,row)

@router.post("/{oid}/repair/finish")
def finish_repair(oid:int,p:FinishInput,cid:int=Depends(get_current_company_id),a:User=Depends(require_permission("work_orders.manage")),db:Session=Depends(get_db)):
    wo=_order(db,cid,oid);row=db.query(WorkOrderRepair).filter_by(company_id=cid,work_order_id=oid).first()
    if not row:raise HTTPException(409,"Primero debe registrar la reparación realizada.")
    if row.finished_at:raise HTTPException(409,"La reparación ya fue finalizada.")
    row.final_tests=p.final_tests if p.final_tests is not None else row.final_tests;row.finished_at=datetime.utcnow()
    db.add(WorkOrderEvent(company_id=cid,work_order_id=oid,event_type="REPAIR_FINISHED",status=wo.status,detail="Reparación finalizada."+(" "+p.note.strip() if p.note and p.note.strip() else ""),user_id=a.id))
    _move_completed(db,cid,wo,a.id);db.commit();db.refresh(row);return _read(db,row)
