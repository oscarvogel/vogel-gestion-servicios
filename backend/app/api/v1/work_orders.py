from datetime import datetime,timezone
from fastapi import APIRouter,Depends,HTTPException,Query,status
from pydantic import BaseModel,Field
from sqlalchemy import or_,text
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_company_id,get_db,require_permission
from app.models.customer import Customer,Equipment,EquipmentCategory
from app.models.user import User
from app.models.work_order import WorkOrder,WorkOrderCounter,WorkOrderEvent,WorkOrderStatus

router=APIRouter()

class StatusInput(BaseModel):
    name:str=Field(min_length=1,max_length=60);color:str=Field(pattern=r"^#[0-9A-Fa-f]{6}$");sort_order:int=0;active:bool=True;is_initial:bool=False;is_final:bool=False;marks_completed:bool=False;marks_delivered:bool=False
class StatusRead(StatusInput):
    id:int
    model_config={"from_attributes":True}
class StatusChange(BaseModel):
    status_id:int
    note:str|None=Field(default=None,max_length=1000)

@router.get("/statuses",response_model=list[StatusRead])
def list_statuses(company_id:int=Depends(get_current_company_id),_actor:User=Depends(require_permission("work_orders.view")),db:Session=Depends(get_db)):
    return db.query(WorkOrderStatus).filter_by(company_id=company_id).order_by(WorkOrderStatus.sort_order,WorkOrderStatus.name).all()

@router.post("/statuses",response_model=StatusRead,status_code=201)
def create_status(payload:StatusInput,company_id:int=Depends(get_current_company_id),_actor:User=Depends(require_permission("work_orders.manage")),db:Session=Depends(get_db)):
    if db.query(WorkOrderStatus).filter(WorkOrderStatus.company_id==company_id,WorkOrderStatus.name.ilike(payload.name.strip())).first(): raise HTTPException(409,"Ya existe un estado con ese nombre.")
    if payload.is_initial: db.query(WorkOrderStatus).filter_by(company_id=company_id).update({"is_initial":False})
    row=WorkOrderStatus(company_id=company_id,**payload.model_dump());row.name=row.name.strip();db.add(row);db.commit();db.refresh(row);return row

@router.patch("/statuses/{status_id}",response_model=StatusRead)
def update_status(status_id:int,payload:StatusInput,company_id:int=Depends(get_current_company_id),_actor:User=Depends(require_permission("work_orders.manage")),db:Session=Depends(get_db)):
    row=db.query(WorkOrderStatus).filter_by(id=status_id,company_id=company_id).first()
    if not row: raise HTTPException(404,"Estado no encontrado.")
    if payload.is_initial: db.query(WorkOrderStatus).filter(WorkOrderStatus.company_id==company_id,WorkOrderStatus.id!=row.id).update({"is_initial":False})
    if payload.marks_completed: db.query(WorkOrderStatus).filter(WorkOrderStatus.company_id==company_id,WorkOrderStatus.id!=row.id).update({"marks_completed":False})
    if payload.marks_delivered: db.query(WorkOrderStatus).filter(WorkOrderStatus.company_id==company_id,WorkOrderStatus.id!=row.id).update({"marks_delivered":False})
    for k,v in payload.model_dump().items(): setattr(row,k,v.strip() if k=="name" else v)
    db.commit();db.refresh(row);return row

class ExpectedDeliveryInput(BaseModel):
    expected_delivery_at:datetime|None

class WorkOrderInput(BaseModel):
    customer_id:int;equipment_id:int
    reported_fault:str=Field(min_length=1)
    physical_condition:str|None=None;accessories:str|None=None;notes:str|None=None

class WorkOrderRead(BaseModel):
    id:int;company_id:int;number:int;customer_id:int;customer_name:str;customer_phone:str|None
    equipment_id:int;equipment_label:str;serial_number:str|None;received_at:datetime;expected_delivery_at:datetime|None;completed_at:datetime|None;delivered_at:datetime|None;reported_fault:str
    physical_condition:str|None;accessories:str|None;notes:str|None;received_by_user_id:int;received_by_name:str;status:str;status_id:int|None;status_name:str;status_color:str
    model_config={"from_attributes":True}

class WorkOrderList(BaseModel):
    items:list[WorkOrderRead];total:int;page:int;page_size:int

class EventRead(BaseModel):
    id:int;event_type:str;status:str|None;detail:str|None;user_id:int;user_name:str;created_at:datetime

def _row(db:Session,company_id:int,work_order_id:int):
    row=db.query(WorkOrder).filter_by(id=work_order_id,company_id=company_id).first()
    if not row: raise HTTPException(404,"Orden de trabajo no encontrada.")
    return row

def _read(db:Session,row:WorkOrder):
    customer=db.query(Customer).filter_by(id=row.customer_id,company_id=row.company_id).one()
    equipment=db.query(Equipment).filter_by(id=row.equipment_id,company_id=row.company_id).one()
    category=db.query(EquipmentCategory).filter_by(id=equipment.category_id,company_id=row.company_id).one()
    receiver=db.get(User,row.received_by_user_id)
    label=" ".join(x for x in (category.name,equipment.brand,equipment.model) if x)
    return {"id":row.id,"company_id":row.company_id,"number":row.number,"customer_id":row.customer_id,"customer_name":customer.name,"customer_phone":customer.phone or customer.whatsapp,
        "equipment_id":row.equipment_id,"equipment_label":label,"serial_number":equipment.serial_number,"received_at":row.received_at,"expected_delivery_at":row.expected_delivery_at,"completed_at":row.completed_at,"delivered_at":row.delivered_at,"reported_fault":row.reported_fault,
        "physical_condition":row.physical_condition,"accessories":row.accessories,"notes":row.notes,"received_by_user_id":row.received_by_user_id,
        "received_by_name":receiver.full_name if receiver else "Usuario","status":row.status,
        "status_id":row.status_id,"status_name":(db.get(WorkOrderStatus,row.status_id).name if row.status_id and db.get(WorkOrderStatus,row.status_id) else row.status.title()),
        "status_color":(db.get(WorkOrderStatus,row.status_id).color if row.status_id and db.get(WorkOrderStatus,row.status_id) else "#10B981")}

def _next_number(db:Session,company_id:int)->int:
    dialect=db.get_bind().dialect.name
    if dialect=="mysql":
        db.execute(text("INSERT INTO work_order_counters (company_id,last_number) VALUES (:cid,LAST_INSERT_ID(1)) ON DUPLICATE KEY UPDATE last_number=LAST_INSERT_ID(last_number+1)"),{"cid":company_id})
        return int(db.execute(text("SELECT LAST_INSERT_ID()")).scalar_one())
    counter=db.get(WorkOrderCounter,company_id)
    if not counter:
        counter=WorkOrderCounter(company_id=company_id,last_number=1);db.add(counter);db.flush();return 1
    counter.last_number+=1;db.flush();return counter.last_number

@router.get("",response_model=WorkOrderList)
def list_orders(search:str|None=None,page:int=Query(1,ge=1),page_size:int=Query(30,ge=1,le=100),company_id:int=Depends(get_current_company_id),
                _actor:User=Depends(require_permission("work_orders.view")),db:Session=Depends(get_db)):
    q=db.query(WorkOrder).join(Customer,Customer.id==WorkOrder.customer_id).join(Equipment,Equipment.id==WorkOrder.equipment_id).filter(WorkOrder.company_id==company_id)
    if search and search.strip():
        term=search.strip();like=f"%{term}%";clauses=[Customer.name.ilike(like),Customer.phone.ilike(like),Customer.whatsapp.ilike(like),Equipment.brand.ilike(like),Equipment.model.ilike(like),Equipment.serial_number.ilike(like)]
        if term.isdigit(): clauses.append(WorkOrder.number==int(term))
        q=q.filter(or_(*clauses))
    total=q.count();rows=q.order_by(WorkOrder.id.desc()).offset((page-1)*page_size).limit(page_size).all()
    return {"items":[_read(db,r) for r in rows],"total":total,"page":page,"page_size":page_size}

@router.post("",response_model=WorkOrderRead,status_code=status.HTTP_201_CREATED)
def create_order(payload:WorkOrderInput,company_id:int=Depends(get_current_company_id),actor:User=Depends(require_permission("work_orders.manage")),db:Session=Depends(get_db)):
    customer=db.query(Customer).filter_by(id=payload.customer_id,company_id=company_id,active=True).first()
    equipment=db.query(Equipment).filter_by(id=payload.equipment_id,customer_id=payload.customer_id,company_id=company_id,active=True).first()
    if not customer: raise HTTPException(422,"El cliente no pertenece a esta empresa o está inactivo.")
    if not equipment: raise HTTPException(422,"El equipo no pertenece al cliente y empresa activos.")
    try:
        number=_next_number(db,company_id)
        initial=db.query(WorkOrderStatus).filter_by(company_id=company_id,is_initial=True,active=True).order_by(WorkOrderStatus.sort_order).first()
        row=WorkOrder(company_id=company_id,number=number,received_by_user_id=actor.id,status="RECEIVED",status_id=initial.id if initial else None,**payload.model_dump())
        db.add(row);db.flush()
        db.add(WorkOrderEvent(company_id=company_id,work_order_id=row.id,event_type="RECEPTION",status="RECEIVED",detail="Equipo recibido y orden de trabajo generada.",user_id=actor.id))
        db.commit();db.refresh(row);return _read(db,row)
    except Exception:
        db.rollback();raise

@router.get("/{work_order_id}",response_model=WorkOrderRead)
def get_order(work_order_id:int,company_id:int=Depends(get_current_company_id),_actor:User=Depends(require_permission("work_orders.view")),db:Session=Depends(get_db)):
    return _read(db,_row(db,company_id,work_order_id))

@router.get("/{work_order_id}/events",response_model=list[EventRead])
def events(work_order_id:int,company_id:int=Depends(get_current_company_id),_actor:User=Depends(require_permission("work_orders.view")),db:Session=Depends(get_db)):
    _row(db,company_id,work_order_id)
    rows=db.query(WorkOrderEvent).filter_by(company_id=company_id,work_order_id=work_order_id).order_by(WorkOrderEvent.id).all()
    result=[]
    for e in rows:
        u=db.get(User,e.user_id);result.append({"id":e.id,"event_type":e.event_type,"status":e.status,"detail":e.detail,"user_id":e.user_id,"user_name":u.full_name if u else "Usuario","created_at":e.created_at})
    return result



@router.patch("/{work_order_id}/expected-delivery",response_model=WorkOrderRead)
def update_expected_delivery(work_order_id:int,payload:ExpectedDeliveryInput,company_id:int=Depends(get_current_company_id),actor:User=Depends(require_permission("work_orders.manage")),db:Session=Depends(get_db)):
    row=_row(db,company_id,work_order_id)
    previous=row.expected_delivery_at
    requested=payload.expected_delivery_at
    if requested and requested.tzinfo is not None:
        requested=requested.astimezone(timezone.utc).replace(tzinfo=None)
    if previous==requested:
        return _read(db,row)
    row.expected_delivery_at=requested
    old=previous.isoformat(sep=" ",timespec="minutes") if previous else "sin fecha"
    new=requested.isoformat(sep=" ",timespec="minutes") if requested else "sin fecha"
    db.add(WorkOrderEvent(company_id=company_id,work_order_id=row.id,event_type="EXPECTED_DELIVERY_CHANGE",status=row.status,detail=f"Entrega prevista cambiada de {old} a {new}.",user_id=actor.id))
    db.commit();db.refresh(row);return _read(db,row)

@router.post("/{work_order_id}/status",response_model=WorkOrderRead)
def change_status(work_order_id:int,payload:StatusChange,company_id:int=Depends(get_current_company_id),actor:User=Depends(require_permission("work_orders.manage")),db:Session=Depends(get_db)):
    row=_row(db,company_id,work_order_id)
    target=db.query(WorkOrderStatus).filter_by(id=payload.status_id,company_id=company_id,active=True).first()
    if not target: raise HTTPException(422,"El estado no pertenece a esta empresa o está inactivo.")
    previous=db.get(WorkOrderStatus,row.status_id) if row.status_id else None
    if row.status_id==target.id:return _read(db,row)
    row.status_id=target.id
    row.status=target.name.upper().replace(" ","_")[:30]
    now=datetime.utcnow()
    lifecycle=[]
    if target.marks_completed and row.completed_at is None:
        row.completed_at=now
        lifecycle.append("Se registró la finalización técnica.")
    if target.marks_delivered and row.delivered_at is None:
        row.delivered_at=now
        lifecycle.append("Se registró la entrega real al cliente.")
    detail=f"Estado cambiado de {previous.name if previous else 'sin estado'} a {target.name}."
    if lifecycle:
        detail+=" "+" ".join(lifecycle)
    if payload.note and payload.note.strip():
        detail+=f" Observación: {payload.note.strip()}"
    db.add(WorkOrderEvent(company_id=company_id,work_order_id=row.id,event_type="STATUS_CHANGE",status=row.status,detail=detail,user_id=actor.id))
    db.commit();db.refresh(row);return _read(db,row)
