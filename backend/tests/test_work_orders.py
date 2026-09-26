from app.core.security import hash_password
from app.models.company import Company
from app.models.customer import Customer,Equipment,EquipmentCategory
from app.models.role import CompanyUserRole,Permission,Role,role_permissions
from app.models.user import CompanyUser,User
from app.models.work_order import WorkOrderStatus

def setup(db,suffix):
    company=Company(name=f"OT {suffix}",slug=f"ot-{suffix}");db.add(company);db.flush()
    user=User(email=f"ot.{suffix}@example.com",full_name=f"Recepción {suffix}",password_hash=hash_password("Password1234"));db.add(user);db.flush()
    membership=CompanyUser(company_id=company.id,user_id=user.id,is_admin=True,role="ADMIN",active=True);db.add(membership);db.flush()
    role=Role(company_id=company.id,name="Administrador",is_system=True,active=True);db.add(role);db.flush()
    for code in ("customers.view","customers.manage","equipment.view","equipment.manage","work_orders.view","work_orders.manage"):
        p=db.query(Permission).filter_by(code=code).one();db.execute(role_permissions.insert().values(role_id=role.id,permission_id=p.id))
    db.add(CompanyUserRole(company_user_id=membership.id,role_id=role.id,active=True))
    db.add_all([
        WorkOrderStatus(company_id=company.id,name="Recibido",color="#10B981",sort_order=10,active=True,is_initial=True,is_final=False),
        WorkOrderStatus(company_id=company.id,name="En diagnóstico",color="#3B82F6",sort_order=20,active=True,is_initial=False,is_final=False),
        WorkOrderStatus(company_id=company.id,name="Listo",color="#22C55E",sort_order=70,active=True,is_initial=False,is_final=False,marks_completed=True),
        WorkOrderStatus(company_id=company.id,name="Entregado",color="#64748B",sort_order=80,active=True,is_initial=False,is_final=True,marks_delivered=True),
    ])
    db.commit()
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


def test_status_change_requires_explicit_post_and_audits_optional_note(client,db_session):
    company,_,customer,equipment=setup(db_session,"status")
    h=login(client,"ot.status@example.com",company.id)
    created=client.post("/api/v1/work-orders",headers=h,json={"customer_id":customer.id,"equipment_id":equipment.id,"reported_fault":"Intermitente"})
    assert created.status_code==201
    statuses=client.get("/api/v1/work-orders/statuses",headers=h).json()
    target=next(s for s in statuses if s["name"]=="En diagnóstico")
    changed=client.post(f"/api/v1/work-orders/{created.json()['id']}/status",headers=h,json={"status_id":target["id"],"note":"Se inicia revisión en banco"})
    assert changed.status_code==200,changed.text
    assert changed.json()["status_name"]=="En diagnóstico"
    events=client.get(f"/api/v1/work-orders/{created.json()['id']}/events",headers=h).json()
    assert events[-1]["event_type"]=="STATUS_CHANGE"
    assert "Se inicia revisión en banco" in events[-1]["detail"]


def test_expected_delivery_is_audited_and_tenant_isolated(client,db_session):
    a,_,ca,ea=setup(db_session,"dates-a");b,_,_,_=setup(db_session,"dates-b")
    ha=login(client,"ot.dates-a@example.com",a.id);hb=login(client,"ot.dates-b@example.com",b.id)
    created=client.post("/api/v1/work-orders",headers=ha,json={"customer_id":ca.id,"equipment_id":ea.id,"reported_fault":"No arranca"}).json()
    changed=client.patch(f"/api/v1/work-orders/{created['id']}/expected-delivery",headers=ha,json={"expected_delivery_at":"2026-09-30T18:00:00Z"})
    assert changed.status_code==200,changed.text
    assert changed.json()["expected_delivery_at"].startswith("2026-09-30T18:00:00")
    events=client.get(f"/api/v1/work-orders/{created['id']}/events",headers=ha).json()
    assert events[-1]["event_type"]=="EXPECTED_DELIVERY_CHANGE"
    assert client.patch(f"/api/v1/work-orders/{created['id']}/expected-delivery",headers=hb,json={"expected_delivery_at":"2026-10-01T18:00:00Z"}).status_code==404

def test_completion_and_delivery_dates_follow_semantic_status_and_survive_revert(client,db_session):
    company,_,customer,equipment=setup(db_session,"lifecycle")
    h=login(client,"ot.lifecycle@example.com",company.id)
    created=client.post("/api/v1/work-orders",headers=h,json={"customer_id":customer.id,"equipment_id":equipment.id,"reported_fault":"Sin audio"}).json()
    statuses=client.get("/api/v1/work-orders/statuses",headers=h).json()
    listo=next(s for s in statuses if s["marks_completed"])
    entregado=next(s for s in statuses if s["marks_delivered"])
    diagnostico=next(s for s in statuses if s["name"]=="En diagnóstico")
    completed=client.post(f"/api/v1/work-orders/{created['id']}/status",headers=h,json={"status_id":listo["id"]}).json()
    assert completed["completed_at"] is not None and completed["delivered_at"] is None
    reverted=client.post(f"/api/v1/work-orders/{created['id']}/status",headers=h,json={"status_id":diagnostico["id"],"note":"Se reabre para control"}).json()
    assert reverted["completed_at"]==completed["completed_at"]
    delivered=client.post(f"/api/v1/work-orders/{created['id']}/status",headers=h,json={"status_id":entregado["id"]}).json()
    assert delivered["completed_at"] is not None and delivered["delivered_at"] is not None

def test_diagnosis_and_versioned_quote_uses_company_parts_markup(client,db_session):
    from app.models.company import ParameterDefinition,CompanyParameter
    company,_,customer,equipment=setup(db_session,"quote")
    h=login(client,"ot.quote@example.com",company.id)
    created=client.post("/api/v1/work-orders",headers=h,json={"customer_id":customer.id,"equipment_id":equipment.id,"reported_fault":"No enciende"}).json()
    blocked=client.post(f"/api/v1/work-orders/{created['id']}/quotes",headers=h,json={"items":[{"item_type":"PART","description":"Fuente","quantity":1,"unit_cost":1000}]})
    assert blocked.status_code==422
    d=client.put(f"/api/v1/work-orders/{created['id']}/diagnosis",headers=h,json={"diagnosis":"Fuente dañada","technical_notes":"Sin salida secundaria"})
    assert d.status_code==200,d.text
    definition=db_session.query(ParameterDefinition).filter_by(parameter="pricing.parts_markup_percent").first()
    if not definition:
        definition=ParameterDefinition(parameter="pricing.parts_markup_percent",default_value="35",description="Margen repuestos",data_type="decimal",category="pricing",editable=True,active=True);db_session.add(definition);db_session.flush()
    db_session.add(CompanyParameter(company_id=company.id,parameter_definition_id=definition.id,value="50"));db_session.commit()
    payload={"items":[{"item_type":"PART","description":"Fuente","quantity":2,"unit_cost":1000},{"item_type":"LABOR","description":"Reparación","quantity":1,"unit_cost":8000,"unit_price":8000}]}
    first=client.post(f"/api/v1/work-orders/{created['id']}/quotes",headers=h,json=payload)
    assert first.status_code==201,first.text
    assert first.json()["version"]==1 and float(first.json()["subtotal_parts"])==3000 and float(first.json()["total"])==11000
    second=client.post(f"/api/v1/work-orders/{created['id']}/quotes",headers=h,json=payload)
    assert second.status_code==201 and second.json()["version"]==2
    events=client.get(f"/api/v1/work-orders/{created['id']}/events",headers=h).json()
    assert events[-1]["event_type"]=="QUOTE_CREATED"
