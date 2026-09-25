from app.core.security import hash_password
from app.models.company import Company
from app.models.customer import Customer,Equipment,EquipmentCategory
from app.models.role import CompanyUserRole,Permission,Role,role_permissions
from app.models.user import CompanyUser,User

def setup(db,suffix):
    company=Company(name=f"OT {suffix}",slug=f"ot-{suffix}");db.add(company);db.flush()
    user=User(email=f"ot.{suffix}@example.com",full_name=f"Recepción {suffix}",password_hash=hash_password("Password1234"));db.add(user);db.flush()
    membership=CompanyUser(company_id=company.id,user_id=user.id,is_admin=True,role="ADMIN",active=True);db.add(membership);db.flush()
    role=Role(company_id=company.id,name="Administrador",is_system=True,active=True);db.add(role);db.flush()
    for code in ("customers.view","customers.manage","equipment.view","equipment.manage","work_orders.view","work_orders.manage"):
        p=db.query(Permission).filter_by(code=code).one();db.execute(role_permissions.insert().values(role_id=role.id,permission_id=p.id))
    db.add(CompanyUserRole(company_user_id=membership.id,role_id=role.id,active=True));db.commit()
    token_client=None
    customer=Customer(company_id=company.id,name=f"Cliente {suffix}");db.add(customer);db.flush()
    cat=EquipmentCategory(company_id=company.id,name="Televisor");db.add(cat);db.flush()
    equipment=Equipment(company_id=company.id,customer_id=customer.id,category_id=cat.id,brand="Samsung",model="QLED",serial_number=f"SER-{suffix}");db.add(equipment);db.commit()
    return company,user,customer,equipment

def login(client,email,cid):
    token=client.post("/api/v1/auth/login",json={"email":email,"password":"Password1234"}).json()["access_token"]
    r=client.post("/api/v1/auth/select-company",headers={"Authorization":f"Bearer {token}"},json={"company_id":cid})
    return {"Authorization":f"Bearer {r.json()['access_token']}"}

def test_reception_generates_company_number_timeline_and_isolation(client,db_session):
    a,_,ca,ea=setup(db_session,"a");b,_,cb,eb=setup(db_session,"b")
    ha=login(client,"ot.a@example.com",a.id);hb=login(client,"ot.b@example.com",b.id)
    payload={"customer_id":ca.id,"equipment_id":ea.id,"reported_fault":"No enciende","physical_condition":"Sin golpes","accessories":"Control remoto"}
    first=client.post("/api/v1/work-orders",headers=ha,json=payload);second=client.post("/api/v1/work-orders",headers=ha,json=payload)
    assert first.status_code==201,first.text;assert second.status_code==201,second.text
    assert first.json()["number"]==1;assert second.json()["number"]==2;assert first.json()["status"]=="RECEIVED"
    events=client.get(f"/api/v1/work-orders/{first.json()['id']}/events",headers=ha)
    assert events.status_code==200 and events.json()[0]["event_type"]=="RECEPTION"
    assert client.get(f"/api/v1/work-orders/{first.json()['id']}",headers=hb).status_code==404
    other=client.post("/api/v1/work-orders",headers=hb,json={"customer_id":cb.id,"equipment_id":eb.id,"reported_fault":"Sin imagen"})
    assert other.status_code==201 and other.json()["number"]==1
    cross=client.post("/api/v1/work-orders",headers=hb,json={"customer_id":ca.id,"equipment_id":ea.id,"reported_fault":"Intento cruzado"})
    assert cross.status_code==422

def test_search_by_order_customer_phone_equipment_and_serial(client,db_session):
    a,_,customer,equipment=setup(db_session,"search");customer.phone="3743123456";db_session.commit()
    h=login(client,"ot.search@example.com",a.id)
    created=client.post("/api/v1/work-orders",headers=h,json={"customer_id":customer.id,"equipment_id":equipment.id,"reported_fault":"Audio bajo"})
    assert created.status_code==201
    for term in ("1","Cliente search","3743123456","Samsung","SER-search"):
        r=client.get("/api/v1/work-orders",headers=h,params={"search":term});assert r.status_code==200 and r.json()["total"]==1
