from datetime import datetime
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_company_id, get_db, require_permission
from app.models.customer import Customer, Equipment, EquipmentCategory
from app.models.user import User

router = APIRouter()

class CustomerInput(BaseModel):
    customer_type: Literal["PERSON", "COMPANY"] = "PERSON"
    name: str = Field(min_length=1, max_length=180)
    document: str | None = Field(default=None, max_length=30)
    phone: str | None = Field(default=None, max_length=60)
    whatsapp: str | None = Field(default=None, max_length=60)
    email: EmailStr | None = None
    address: str | None = Field(default=None, max_length=250)
    notes: str | None = None

class CustomerPatch(BaseModel):
    customer_type: Literal["PERSON", "COMPANY"] | None = None
    name: str | None = Field(default=None, min_length=1, max_length=180)
    document: str | None = Field(default=None, max_length=30)
    phone: str | None = Field(default=None, max_length=60)
    whatsapp: str | None = Field(default=None, max_length=60)
    email: EmailStr | None = None
    address: str | None = Field(default=None, max_length=250)
    notes: str | None = None
    active: bool | None = None

class CustomerRead(CustomerInput):
    id: int; company_id: int; active: bool; created_at: datetime; updated_at: datetime
    model_config = {"from_attributes": True}

class CustomerList(BaseModel):
    items: list[CustomerRead]; total: int; page: int; page_size: int

def _customer(db: Session, company_id: int, customer_id: int) -> Customer:
    row = db.query(Customer).filter_by(id=customer_id, company_id=company_id).first()
    if not row: raise HTTPException(status_code=404, detail="Cliente no encontrado.")
    return row

@router.get("", response_model=CustomerList)
def list_customers(search: str | None = None, active: bool | None = None, page: int = Query(1, ge=1),
                   page_size: int = Query(20, ge=1, le=100), company_id: int = Depends(get_current_company_id),
                   _actor: User = Depends(require_permission("customers.view")), db: Session = Depends(get_db)):
    q = db.query(Customer).filter(Customer.company_id == company_id)
    if active is not None: q = q.filter(Customer.active.is_(active))
    if search:
        like=f"%{search.strip()}%"
        q=q.filter(or_(Customer.name.ilike(like), Customer.document.ilike(like), Customer.phone.ilike(like), Customer.email.ilike(like)))
    total=q.count(); items=q.order_by(Customer.name, Customer.id).offset((page-1)*page_size).limit(page_size).all()
    return CustomerList(items=items,total=total,page=page,page_size=page_size)

@router.post("", response_model=CustomerRead, status_code=status.HTTP_201_CREATED)
def create_customer(payload: CustomerInput, company_id: int = Depends(get_current_company_id),
                    _actor: User = Depends(require_permission("customers.manage")), db: Session = Depends(get_db)):
    if payload.document and db.query(Customer).filter_by(company_id=company_id, document=payload.document).first():
        raise HTTPException(status_code=409, detail="Ya existe un cliente con ese DNI/CUIT en esta empresa.")
    row=Customer(company_id=company_id, **payload.model_dump()); db.add(row); db.commit(); db.refresh(row); return row

@router.get("/{customer_id}", response_model=CustomerRead)
def get_customer(customer_id:int, company_id:int=Depends(get_current_company_id),
                 _actor:User=Depends(require_permission("customers.view")), db:Session=Depends(get_db)):
    return _customer(db,company_id,customer_id)

@router.patch("/{customer_id}", response_model=CustomerRead)
def update_customer(customer_id:int,payload:CustomerPatch,company_id:int=Depends(get_current_company_id),
                    _actor:User=Depends(require_permission("customers.manage")),db:Session=Depends(get_db)):
    row=_customer(db,company_id,customer_id); data=payload.model_dump(exclude_unset=True)
    if data.get("document"):
        duplicate=db.query(Customer).filter(Customer.company_id==company_id,Customer.document==data["document"],Customer.id!=row.id).first()
        if duplicate: raise HTTPException(status_code=409,detail="Ya existe un cliente con ese DNI/CUIT en esta empresa.")
    for key,value in data.items(): setattr(row,key,value)
    db.commit();db.refresh(row);return row

class CategoryInput(BaseModel):
    name: str = Field(min_length=1,max_length=80)

class CategoryRead(CategoryInput):
    id:int; company_id:int; active:bool
    model_config={"from_attributes":True}

@router.get("/equipment-categories/search", response_model=list[CategoryRead])
def search_categories(q:str="",company_id:int=Depends(get_current_company_id),
                      _actor:User=Depends(require_permission("equipment.view")),db:Session=Depends(get_db)):
    query=db.query(EquipmentCategory).filter_by(company_id=company_id,active=True)
    if q.strip(): query=query.filter(EquipmentCategory.name.ilike(f"%{q.strip()}%"))
    return query.order_by(EquipmentCategory.name).limit(30).all()

@router.post("/equipment-categories", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
def create_category(payload:CategoryInput,company_id:int=Depends(get_current_company_id),
                    _actor:User=Depends(require_permission("equipment.manage")),db:Session=Depends(get_db)):
    name=" ".join(payload.name.split()).strip()
    existing=db.query(EquipmentCategory).filter(EquipmentCategory.company_id==company_id,func.lower(EquipmentCategory.name)==name.lower()).first()
    if existing:
        if not existing.active: existing.active=True;db.commit();db.refresh(existing)
        return existing
    row=EquipmentCategory(company_id=company_id,name=name);db.add(row);db.commit();db.refresh(row);return row

class EquipmentInput(BaseModel):
    customer_id: int
    category_id: int
    brand: str | None = Field(default=None,max_length=100)
    model: str | None = Field(default=None,max_length=120)
    serial_number: str | None = Field(default=None,max_length=120)
    description: str | None = Field(default=None,max_length=300)
    notes: str | None = None

class EquipmentPatch(BaseModel):
    category_id: int | None = None
    brand: str | None = Field(default=None,max_length=100)
    model: str | None = Field(default=None,max_length=120)
    serial_number: str | None = Field(default=None,max_length=120)
    description: str | None = Field(default=None,max_length=300)
    notes: str | None = None
    active: bool | None = None

class EquipmentRead(EquipmentInput):
    id:int;company_id:int;active:bool;created_at:datetime;updated_at:datetime
    category_name:str
    model_config={"from_attributes":True}

def _equipment_read(row:Equipment,db:Session)->dict:
    category=db.query(EquipmentCategory).filter_by(id=row.category_id,company_id=row.company_id).one()
    return {**{key:getattr(row,key) for key in ("id","company_id","customer_id","category_id","brand","model","serial_number","description","notes","active","created_at","updated_at")},"category_name":category.name}

@router.get("/{customer_id}/equipment", response_model=list[EquipmentRead])
def list_equipment(customer_id:int,company_id:int=Depends(get_current_company_id),
                   _actor:User=Depends(require_permission("equipment.view")),db:Session=Depends(get_db)):
    _customer(db,company_id,customer_id)
    rows=db.query(Equipment).filter_by(company_id=company_id,customer_id=customer_id).order_by(Equipment.id.desc()).all()
    return [_equipment_read(row,db) for row in rows]

@router.post("/{customer_id}/equipment", response_model=EquipmentRead, status_code=status.HTTP_201_CREATED)
def create_equipment(customer_id:int,payload:EquipmentInput,company_id:int=Depends(get_current_company_id),
                     _actor:User=Depends(require_permission("equipment.manage")),db:Session=Depends(get_db)):
    _customer(db,company_id,customer_id)
    if payload.customer_id != customer_id: raise HTTPException(status_code=422,detail="El cliente del equipo no coincide.")
    category=db.query(EquipmentCategory).filter_by(id=payload.category_id,company_id=company_id,active=True).first()
    if not category: raise HTTPException(status_code=422,detail="La categoría no pertenece a esta empresa o está inactiva.")
    row=Equipment(company_id=company_id,**payload.model_dump());db.add(row);db.commit();db.refresh(row);return _equipment_read(row,db)

@router.patch("/{customer_id}/equipment/{equipment_id}", response_model=EquipmentRead)
def update_equipment(customer_id:int,equipment_id:int,payload:EquipmentPatch,company_id:int=Depends(get_current_company_id),
                     _actor:User=Depends(require_permission("equipment.manage")),db:Session=Depends(get_db)):
    _customer(db,company_id,customer_id)
    row=db.query(Equipment).filter_by(id=equipment_id,company_id=company_id,customer_id=customer_id).first()
    if not row: raise HTTPException(status_code=404,detail="Equipo no encontrado.")
    data=payload.model_dump(exclude_unset=True)
    if data.get("category_id") and not db.query(EquipmentCategory).filter_by(id=data["category_id"],company_id=company_id,active=True).first():
        raise HTTPException(status_code=422,detail="La categoría no pertenece a esta empresa o está inactiva.")
    for key,value in data.items():setattr(row,key,value)
    db.commit();db.refresh(row);return _equipment_read(row,db)
