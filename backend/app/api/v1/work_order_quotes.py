from decimal import Decimal
from datetime import datetime
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_company_id,get_db,require_permission
from app.services import work_orders as wo_service
from app.models.user import User
from app.models.work_order import WorkOrder,WorkOrderEvent,WorkOrderStatus
from app.models.work_order_quote import WorkOrderDiagnosis,WorkOrderQuote,WorkOrderQuoteItem,WorkOrderExecutionItem,WorkOrderFinalTest
router=APIRouter()
class DiagnosisInput(BaseModel):
    diagnosis:str=Field(min_length=1)
    technical_notes:str|None=None
class DiagnosisReopenInput(BaseModel):
    reason:str=Field(min_length=3,max_length=1000)
class ItemInput(BaseModel):
    item_type:str=Field(pattern="^(PART|LABOR)$")
    description:str=Field(min_length=1,max_length=250)
    quantity:Decimal=Field(gt=0)
    unit_cost:Decimal=Field(ge=0)
    unit_price:Decimal|None=Field(default=None,ge=0)
class QuoteDecisionInput(BaseModel):
    note:str|None=Field(default=None,max_length=1000)
class QuoteInput(BaseModel):
    items:list[ItemInput]=Field(min_length=1)
    notes:str|None=None
class ExecutionItemInput(BaseModel):
    item_type:str=Field(pattern="^(PART|LABOR)$")
    description:str=Field(min_length=1,max_length=250)
    quantity:Decimal=Field(gt=0)
    unit_cost:Decimal=Field(default=0,ge=0)
    unit_price:Decimal=Field(default=0,ge=0)
class FinalTestInput(BaseModel):
    passed:bool
    notes:str|None=Field(default=None,max_length=2000)
def order(db,cid,oid):
    row=db.query(WorkOrder).filter_by(id=oid,company_id=cid).first()
    if not row:raise HTTPException(404,"Orden de trabajo no encontrada.")
    return row

def _is_final(db,cid,oid,wo):
    """True cuando la OT está en un estado marcado como final (ej: entregada)."""
    if wo.status_id is None: return False
    st=db.get(WorkOrderStatus,wo.status_id)
    return bool(st and st.is_final)
def parameter_bool(db,cid,key,default=True):
    return wo_service.parameter_bool(db,cid,key,default)

def markup(db,cid):
    return wo_service.markup_partes(db,cid)
def money(v):return wo_service.money(v)
def quote_read(db,row):
    items=db.query(WorkOrderQuoteItem).filter_by(quote_id=row.id,company_id=row.company_id).order_by(WorkOrderQuoteItem.id).all()
    return {"id":row.id,"work_order_id":row.work_order_id,"version":row.version,"status":row.status,"notes":row.notes,"diagnosis_snapshot":row.diagnosis_snapshot,"diagnosis_revision":row.diagnosis_revision,"subtotal_parts":row.subtotal_parts,"subtotal_labor":row.subtotal_labor,"total":row.total,"created_at":row.created_at,"sent_at":row.sent_at,"decided_at":row.decided_at,"items":[{"id":i.id,"item_type":i.item_type,"description":i.description,"quantity":i.quantity,"unit_cost":i.unit_cost,"markup_percent":i.markup_percent,"unit_price":i.unit_price,"line_total":i.line_total} for i in items]}
@router.get("/{oid}/diagnosis")
def get_diagnosis(oid:int,cid:int=Depends(get_current_company_id),_a:User=Depends(require_permission("work_orders.view")),db:Session=Depends(get_db)):
    order(db,cid,oid);d=db.query(WorkOrderDiagnosis).filter_by(company_id=cid,work_order_id=oid).first()
    return None if not d else {"id":d.id,"diagnosis":d.diagnosis,"technical_notes":d.technical_notes,"diagnosed_at":d.diagnosed_at,"updated_at":d.updated_at,"is_open":d.is_open,"revision":d.revision}
@router.put("/{oid}/diagnosis")
def save_diagnosis(oid:int,p:DiagnosisInput,cid:int=Depends(get_current_company_id),a:User=Depends(require_permission("work_orders.manage")),db:Session=Depends(get_db)):
    wo=order(db,cid,oid)
    if _is_final(db,cid,oid,wo):raise HTTPException(409,"La orden de trabajo está en un estado final (entregada) y no admite diagnóstico.")
    if not parameter_bool(db,cid,"work_orders.use_diagnosis",True):raise HTTPException(409,"El diagnóstico técnico está deshabilitado para esta empresa.")
    d=db.query(WorkOrderDiagnosis).filter_by(company_id=cid,work_order_id=oid).first()
    if d and not d.is_open:raise HTTPException(409,"El diagnóstico está cerrado por un presupuesto. Reabrilo antes de modificarlo.")
    if d:d.diagnosis=p.diagnosis.strip();d.technical_notes=p.technical_notes
    else:d=WorkOrderDiagnosis(company_id=cid,work_order_id=oid,diagnosis=p.diagnosis.strip(),technical_notes=p.technical_notes,diagnosed_by_user_id=a.id);db.add(d)
    db.add(WorkOrderEvent(company_id=cid,work_order_id=oid,event_type="DIAGNOSIS",status=wo.status,detail="Diagnóstico técnico guardado.",user_id=a.id));db.commit();db.refresh(d)
    return {"id":d.id,"diagnosis":d.diagnosis,"technical_notes":d.technical_notes,"diagnosed_at":d.diagnosed_at,"updated_at":d.updated_at,"is_open":d.is_open,"revision":d.revision}
@router.get("/{oid}/quotes")
def list_quotes(oid:int,cid:int=Depends(get_current_company_id),_a:User=Depends(require_permission("work_orders.view")),db:Session=Depends(get_db)):
    order(db,cid,oid);return [quote_read(db,row) for row in db.query(WorkOrderQuote).filter_by(company_id=cid,work_order_id=oid).order_by(WorkOrderQuote.version.desc()).all()]
@router.get("/{oid}/quotes/preview")
def preview_quote(oid:int,cid:int=Depends(get_current_company_id),_a:User=Depends(require_permission("work_orders.view")),db:Session=Depends(get_db)):
    """El presupuesto tal como quedaria, calculado con los datos de ahora. No escribe nada.

    Lo usa el dialogo de confirmacion del asistente: una propuesta que mueve plata tiene que
    mostrar los importes antes de que la persona confirme, no despues. Es la misma funcion que
    usa la herramienta de IA, asi que lo que se muestra aca es exactamente lo que se va a
    guardar, y si entre medio cambio algo, muestra el estado actual y no el de la propuesta.
    """
    order(db,cid,oid)
    try:
        return wo_service.calcular_presupuesto(db,company_id=cid,work_order_id=oid)
    except wo_service.ErrorDeDominio as exc:
        raise HTTPException(exc.status_http,exc.mensaje)


@router.post("/{oid}/quotes",status_code=201)
def create_quote(oid:int,p:QuoteInput,cid:int=Depends(get_current_company_id),a:User=Depends(require_permission("work_orders.manage")),db:Session=Depends(get_db)):
    order(db,cid,oid)
    try:
        row=wo_service.crear_presupuesto(db,company_id=cid,user_id=a.id,work_order_id=oid,notes=p.notes,items=[dict(x) for x in p.items])
    except wo_service.ErrorDeDominio as exc:raise HTTPException(exc.status_http,exc.mensaje)
    db.commit();db.refresh(row);return quote_read(db,row)

def _move_status(db,cid,wo,marker,user_id,detail):
    target=db.query(WorkOrderStatus).filter(getattr(WorkOrderStatus,marker).is_(True),WorkOrderStatus.company_id==cid,WorkOrderStatus.active.is_(True)).order_by(WorkOrderStatus.sort_order).first()
    if target and wo.status_id!=target.id:
        previous=db.get(WorkOrderStatus,wo.status_id) if wo.status_id else None
        wo.status_id=target.id;wo.status=target.name.upper().replace(" ","_")[:30]
        db.add(WorkOrderEvent(company_id=cid,work_order_id=wo.id,event_type="STATUS_CHANGE",status=wo.status,detail=detail+" Estado: %s → %s."%((previous.name if previous else "sin estado"),target.name),user_id=user_id))

def _quote(db,cid,oid,qid):
    q=db.query(WorkOrderQuote).filter_by(id=qid,work_order_id=oid,company_id=cid).first()
    if not q:raise HTTPException(404,"Presupuesto no encontrado.")
    return q

@router.post("/{oid}/quotes/{qid}/send")
def send_quote(oid:int,qid:int,p:QuoteDecisionInput,cid:int=Depends(get_current_company_id),a:User=Depends(require_permission("work_orders.manage")),db:Session=Depends(get_db)):
    wo=order(db,cid,oid);q=_quote(db,cid,oid,qid)
    if _is_final(db,cid,oid,wo):raise HTTPException(409,"La orden de trabajo está en un estado final (entregada) y no admite envío de presupuesto.")
    if q.status in ("APPROVED","REJECTED"):raise HTTPException(409,"El presupuesto ya tiene una decisión registrada.")
    q.sent_at=q.sent_at or datetime.utcnow()
    approval=parameter_bool(db,cid,"work_orders.require_budget_approval",True)
    q.status="PENDING_APPROVAL" if approval else "ISSUED"
    detail="Presupuesto v%d marcado como enviado al cliente."%q.version
    if p.note and p.note.strip():detail+=" Observación: "+p.note.strip()
    db.add(WorkOrderEvent(company_id=cid,work_order_id=oid,event_type="QUOTE_SENT",status=wo.status,detail=detail,user_id=a.id))
    if approval:_move_status(db,cid,wo,"marks_awaiting_quote_approval",a.id,"Presupuesto enviado y pendiente de aprobación.")
    db.commit();db.refresh(q);return quote_read(db,q)

@router.post("/{oid}/quotes/{qid}/approve")
def approve_quote(oid:int,qid:int,p:QuoteDecisionInput,cid:int=Depends(get_current_company_id),a:User=Depends(require_permission("work_orders.manage")),db:Session=Depends(get_db)):
    wo=order(db,cid,oid);q=_quote(db,cid,oid,qid)
    if _is_final(db,cid,oid,wo):raise HTTPException(409,"La orden de trabajo está en un estado final (entregada) y no admite decisión sobre el presupuesto.")
    if q.status=="REJECTED":raise HTTPException(409,"El presupuesto fue rechazado.")
    q.status="APPROVED";q.decided_at=datetime.utcnow()
    detail="Presupuesto v%d aprobado por el cliente."%q.version
    if p.note and p.note.strip():detail+=" Observación: "+p.note.strip()
    db.add(WorkOrderEvent(company_id=cid,work_order_id=oid,event_type="QUOTE_APPROVED",status=wo.status,detail=detail,user_id=a.id))
    _move_status(db,cid,wo,"marks_repair",a.id,"Presupuesto aprobado.")
    db.commit();db.refresh(q);return quote_read(db,q)

@router.post("/{oid}/quotes/{qid}/reject")
def reject_quote(oid:int,qid:int,p:QuoteDecisionInput,cid:int=Depends(get_current_company_id),a:User=Depends(require_permission("work_orders.manage")),db:Session=Depends(get_db)):
    wo=order(db,cid,oid);q=_quote(db,cid,oid,qid)
    if _is_final(db,cid,oid,wo):raise HTTPException(409,"La orden de trabajo está en un estado final (entregada) y no admite decisión sobre el presupuesto.")
    if q.status=="APPROVED":raise HTTPException(409,"El presupuesto ya fue aprobado.")
    q.status="REJECTED";q.decided_at=datetime.utcnow()
    detail="Presupuesto v%d rechazado por el cliente."%q.version
    if p.note and p.note.strip():detail+=" Motivo: "+p.note.strip()
    db.add(WorkOrderEvent(company_id=cid,work_order_id=oid,event_type="QUOTE_REJECTED",status=wo.status,detail=detail,user_id=a.id))
    db.commit();db.refresh(q);return quote_read(db,q)

@router.post("/{oid}/diagnosis/reopen")
def reopen_diagnosis(oid:int,p:DiagnosisReopenInput,cid:int=Depends(get_current_company_id),a:User=Depends(require_permission("work_orders.manage")),db:Session=Depends(get_db)):
    wo=order(db,cid,oid);d=db.query(WorkOrderDiagnosis).filter_by(company_id=cid,work_order_id=oid).first()
    if not d:raise HTTPException(404,"Diagnóstico no encontrado.")
    if _is_final(db,cid,oid,wo):raise HTTPException(409,"La orden de trabajo está en un estado final (entregada) y no admite re-apertura del diagnóstico.")
    if d.is_open:raise HTTPException(409,"El diagnóstico ya está abierto.")
    d.is_open=True;d.revision+=1
    db.add(WorkOrderEvent(company_id=cid,work_order_id=oid,event_type="DIAGNOSIS_REOPENED",status=wo.status,detail="Diagnóstico reabierto. Motivo: "+p.reason.strip(),user_id=a.id))
    db.commit();db.refresh(d)
    return {"id":d.id,"diagnosis":d.diagnosis,"technical_notes":d.technical_notes,"diagnosed_at":d.diagnosed_at,"updated_at":d.updated_at,"is_open":d.is_open,"revision":d.revision}


@router.get("/{oid}/execution")
def list_execution(oid:int,cid:int=Depends(get_current_company_id),_a:User=Depends(require_permission("work_orders.view")),db:Session=Depends(get_db)):
    order(db,cid,oid)
    rows=db.query(WorkOrderExecutionItem).filter_by(company_id=cid,work_order_id=oid).order_by(WorkOrderExecutionItem.id).all()
    return [{"id":r.id,"item_type":r.item_type,"description":r.description,"quantity":r.quantity,"unit_cost":r.unit_cost,"unit_price":r.unit_price,"created_at":r.created_at} for r in rows]

@router.post("/{oid}/execution",status_code=201)
def add_execution(oid:int,p:ExecutionItemInput,cid:int=Depends(get_current_company_id),a:User=Depends(require_permission("work_orders.manage")),db:Session=Depends(get_db)):
    wo=order(db,cid,oid)
    if _is_final(db,cid,oid,wo):raise HTTPException(409,"La orden está finalizada y no admite trabajos o repuestos.")
    show_costs=parameter_bool(db,cid,"work_orders.show_internal_costs",True)
    row=WorkOrderExecutionItem(company_id=cid,work_order_id=oid,item_type=p.item_type,description=p.description.strip(),quantity=p.quantity,unit_cost=(money(p.unit_cost) if show_costs else Decimal("0")),unit_price=money(p.unit_price),created_by_user_id=a.id)
    db.add(row);db.add(WorkOrderEvent(company_id=cid,work_order_id=oid,event_type="WORK_EXECUTED",status=wo.status,detail=("Repuesto utilizado: " if p.item_type=="PART" else "Trabajo realizado: ")+p.description.strip(),user_id=a.id));db.commit();db.refresh(row)
    return {"id":row.id,"item_type":row.item_type,"description":row.description,"quantity":row.quantity,"unit_cost":row.unit_cost,"unit_price":row.unit_price,"created_at":row.created_at}

@router.get("/{oid}/final-tests")
def list_final_tests(oid:int,cid:int=Depends(get_current_company_id),_a:User=Depends(require_permission("work_orders.view")),db:Session=Depends(get_db)):
    order(db,cid,oid);rows=db.query(WorkOrderFinalTest).filter_by(company_id=cid,work_order_id=oid).order_by(WorkOrderFinalTest.id.desc()).all()
    return [{"id":r.id,"passed":r.passed,"notes":r.notes,"tested_at":r.tested_at} for r in rows]

@router.post("/{oid}/final-tests",status_code=201)
def add_final_test(oid:int,p:FinalTestInput,cid:int=Depends(get_current_company_id),a:User=Depends(require_permission("work_orders.manage")),db:Session=Depends(get_db)):
    wo=order(db,cid,oid)
    if _is_final(db,cid,oid,wo):raise HTTPException(409,"La orden está finalizada y no admite pruebas.")
    if not parameter_bool(db,cid,"work_orders.use_final_tests",True):raise HTTPException(409,"Las pruebas finales están deshabilitadas para esta empresa.")
    row=WorkOrderFinalTest(company_id=cid,work_order_id=oid,passed=p.passed,notes=p.notes,tested_by_user_id=a.id);db.add(row)
    detail=("Prueba final satisfactoria." if p.passed else "Prueba final no satisfactoria.")+((" "+p.notes.strip()) if p.notes and p.notes.strip() else "")
    db.add(WorkOrderEvent(company_id=cid,work_order_id=oid,event_type="FINAL_TEST",status=wo.status,detail=detail,user_id=a.id));db.commit();db.refresh(row)
    return {"id":row.id,"passed":row.passed,"notes":row.notes,"tested_at":row.tested_at}
