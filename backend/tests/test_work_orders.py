from datetime import datetime,timezone
from zoneinfo import ZoneInfo

from app.api.v1 import dashboard as dashboard_module
from app.core.security import hash_password
from app.models.company import Company
from app.models.customer import Customer,Equipment,EquipmentCategory
from app.models.role import CompanyUserRole,Permission,Role,role_permissions
from app.models.user import CompanyUser,User
from app.models.work_order import WorkOrder,WorkOrderStatus

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
        WorkOrderStatus(company_id=company.id,name="Presupuestado",color="#8B5CF6",sort_order=30,active=True,is_initial=False,is_final=False),
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
    current=client.get("/api/v1/work-orders/"+str(created["id"]),headers=h)
    assert current.status_code==200 and current.json()["status_name"] in ("Recibido","Presupuestado")
    second=client.post(f"/api/v1/work-orders/{created['id']}/quotes",headers=h,json=payload)
    assert second.status_code==201 and second.json()["version"]==2
    events=client.get(f"/api/v1/work-orders/{created['id']}/events",headers=h).json()
    assert any(e["event_type"]=="QUOTE_CREATED" for e in events)
    assert any(e["event_type"]=="QUOTE_CREATED" for e in events)

def test_work_order_final_state_locked(client,db_session):
    company,_,customer,equipment=setup(db_session,"locked")
    h=login(client,"ot.locked@example.com",company.id)
    created=client.post("/api/v1/work-orders",headers=h,json={"customer_id":customer.id,"equipment_id":equipment.id,"reported_fault":"Pantalla rota"}).json()
    statuses=client.get("/api/v1/work-orders/statuses",headers=h).json()
    diagnostico=next(s for s in statuses if s["name"]=="En diagnóstico")
    entregado=next(s for s in statuses if s["is_final"])

    # 1. Mover a estado final (Entregado)
    r_delivered=client.post(f"/api/v1/work-orders/{created['id']}/status",headers=h,json={"status_id":entregado["id"]})
    assert r_delivered.status_code==200

    # 2. Intentar volver atrás (a "En diagnóstico") -> debe fallar con 409
    r_revert=client.post(f"/api/v1/work-orders/{created['id']}/status",headers=h,json={"status_id":diagnostico["id"]})
    assert r_revert.status_code==409
    assert "estado final" in r_revert.text

    # 3. Intentar agregar diagnóstico -> debe fallar con 409
    r_diag=client.put(f"/api/v1/work-orders/{created['id']}/diagnosis",headers=h,json={"diagnosis":"Nueva revisión","technical_notes":""})
    assert r_diag.status_code==409
    assert "estado final" in r_diag.text

    # 4. Intentar agregar cotización -> debe fallar con 409
    r_quote=client.post(f"/api/v1/work-orders/{created['id']}/quotes",headers=h,json={"items":[{"item_type":"PART","description":"Pantalla","quantity":1,"unit_cost":5000}]})
    assert r_quote.status_code==409
    assert "estado final" in r_quote.text

    # 5. Intentar cambiar fecha de entrega prevista -> debe fallar con 409
    r_delivery=client.patch(f"/api/v1/work-orders/{created['id']}/expected-delivery",headers=h,json={"expected_delivery_at":"2026-10-10T15:00:00Z"})
    assert r_delivery.status_code==409
    assert "estado final" in r_delivery.text




def test_company_dashboard_metrics_are_semantic_and_tenant_isolated(client,db_session):
    a,_,ca,ea=setup(db_session,"dash-a");b,_,cb,eb=setup(db_session,"dash-b")
    ha=login(client,"ot.dash-a@example.com",a.id);hb=login(client,"ot.dash-b@example.com",b.id)
    first=client.post("/api/v1/work-orders",headers=ha,json={"customer_id":ca.id,"equipment_id":ea.id,"reported_fault":"A"}).json()
    client.post("/api/v1/work-orders",headers=hb,json={"customer_id":cb.id,"equipment_id":eb.id,"reported_fault":"B"})
    statuses=client.get("/api/v1/work-orders/statuses",headers=ha).json()
    listo=next(s for s in statuses if s["marks_completed"])
    client.post(f"/api/v1/work-orders/{first['id']}/status",headers=ha,json={"status_id":listo["id"]})
    result=client.get("/api/v1/dashboard/company",headers=ha)
    assert result.status_code==200,result.text
    body=result.json()
    assert body["total"]==1
    assert body["summary"]["completed"]==1
    assert body["summary"]["delivered"]==0
    assert sum(s["count"] for s in body["statuses"])==1


def _set_bool_parameter(db,company,key,value):
    from app.models.company import ParameterDefinition,CompanyParameter
    d=db.query(ParameterDefinition).filter_by(parameter=key).first()
    if not d:
        d=ParameterDefinition(parameter=key,default_value="true",description=key,data_type="bool",category="ordenes",editable=True,active=True)
        db.add(d)
        db.flush()
    o=db.query(CompanyParameter).filter_by(company_id=company.id,parameter_definition_id=d.id).first()
    if o:
        o.value="true" if value else "false"
    else:
        db.add(CompanyParameter(company_id=company.id,parameter_definition_id=d.id,value="true" if value else "false"))
    db.commit()

def test_simple_shop_can_execute_without_diagnosis_budget_or_final_tests(client,db_session):
    company,_,customer,equipment=setup(db_session,"simple-flow")
    for key in ("work_orders.use_diagnosis","work_orders.use_budget","work_orders.require_budget_approval","work_orders.use_final_tests","work_orders.show_internal_costs"):_set_bool_parameter(db_session,company,key,False)
    h=login(client,"ot.simple-flow@example.com",company.id)
    wo=client.post("/api/v1/work-orders",headers=h,json={"customer_id":customer.id,"equipment_id":equipment.id,"reported_fault":"No enciende"}).json()
    executed=client.post(f"/api/v1/work-orders/{wo['id']}/execution",headers=h,json={"item_type":"LABOR","description":"Resoldado de conector","quantity":1,"unit_cost":5000,"unit_price":12000})
    assert executed.status_code==201,executed.text
    assert float(executed.json()["unit_cost"])==0
    assert client.put(f"/api/v1/work-orders/{wo['id']}/diagnosis",headers=h,json={"diagnosis":"x"}).status_code==409
    assert client.post(f"/api/v1/work-orders/{wo['id']}/quotes",headers=h,json={"items":[{"item_type":"LABOR","description":"x","quantity":1,"unit_cost":0,"unit_price":1}]}).status_code==409
    assert client.post(f"/api/v1/work-orders/{wo['id']}/final-tests",headers=h,json={"passed":True}).status_code==409
    statuses=client.get("/api/v1/work-orders/statuses",headers=h).json();listo=next(s for s in statuses if s["marks_completed"])
    assert client.post(f"/api/v1/work-orders/{wo['id']}/status",headers=h,json={"status_id":listo["id"]}).status_code==200

def test_full_shop_records_execution_and_final_test_without_mutating_quote(client,db_session):
    company,_,customer,equipment=setup(db_session,"full-flow")
    h=login(client,"ot.full-flow@example.com",company.id)
    wo=client.post("/api/v1/work-orders",headers=h,json={"customer_id":customer.id,"equipment_id":equipment.id,"reported_fault":"Falla fuente"}).json()
    assert client.put(f"/api/v1/work-orders/{wo['id']}/diagnosis",headers=h,json={"diagnosis":"Fuente dañada"}).status_code==200
    q=client.post(f"/api/v1/work-orders/{wo['id']}/quotes",headers=h,json={"items":[{"item_type":"PART","description":"Fuente presupuestada","quantity":1,"unit_cost":1000,"unit_price":2000}]}).json()
    assert client.post(f"/api/v1/work-orders/{wo['id']}/execution",headers=h,json={"item_type":"PART","description":"Fuente realmente utilizada","quantity":1,"unit_cost":1200,"unit_price":2300}).status_code==201
    test=client.post(f"/api/v1/work-orders/{wo['id']}/final-tests",headers=h,json={"passed":True,"notes":"Encendido y carga estables"})
    assert test.status_code==201,test.text
    quotes=client.get(f"/api/v1/work-orders/{wo['id']}/quotes",headers=h).json()
    assert quotes[0]["items"][0]["description"]=="Fuente presupuestada"
    execution=client.get(f"/api/v1/work-orders/{wo['id']}/execution",headers=h).json()
    assert execution[0]["description"]=="Fuente realmente utilizada"
    events=client.get(f"/api/v1/work-orders/{wo['id']}/events",headers=h).json()
    assert any(e["event_type"]=="WORK_EXECUTED" for e in events) and any(e["event_type"]=="FINAL_TEST" for e in events)


def test_work_order_list_paginates_and_filters_server_side(client,db_session):
    company,_,customer,equipment=setup(db_session,"filters")
    h=login(client,"ot.filters@example.com",company.id)
    for n in range(27):
        r=client.post("/api/v1/work-orders",headers=h,json={"customer_id":customer.id,"equipment_id":equipment.id,"reported_fault":f"Falla {n}"})
        assert r.status_code==201
    first=client.get("/api/v1/work-orders",headers=h)
    assert first.status_code==200
    assert first.json()["total"]==27
    assert len(first.json()["items"])==25
    assert first.json()["page_size"]==25
    assert first.json()["items"][0]["number"]==27
    second=client.get("/api/v1/work-orders",headers=h,params={"page":2,"page_size":25})
    assert len(second.json()["items"])==2

    statuses=client.get("/api/v1/work-orders/statuses",headers=h).json()
    diagnostic=next(s for s in statuses if s["name"]=="En diagnóstico")
    target=first.json()["items"][0]
    assert client.post(f"/api/v1/work-orders/{target['id']}/status",headers=h,json={"status_id":diagnostic["id"]}).status_code==200
    filtered=client.get("/api/v1/work-orders",headers=h,params={"status_id":diagnostic["id"]})
    assert filtered.status_code==200
    assert filtered.json()["total"]==1
    assert filtered.json()["items"][0]["id"]==target["id"]

    by_customer=client.get("/api/v1/work-orders",headers=h,params={"customer":"Cliente filters"})
    assert by_customer.status_code==200 and by_customer.json()["total"]==27


def test_work_order_list_filters_by_received_date_range(client,db_session):
    from datetime import date,timedelta
    company,_,customer,equipment=setup(db_session,"dates")
    h=login(client,"ot.dates@example.com",company.id)
    r=client.post("/api/v1/work-orders",headers=h,json={"customer_id":customer.id,"equipment_id":equipment.id,"reported_fault":"Sin imagen"})
    assert r.status_code==201
    day=timedelta(days=1)
    inside=client.get("/api/v1/work-orders",headers=h,params={"date_from":(date.today()-day).isoformat(),"date_to":(date.today()+day).isoformat()})
    assert inside.status_code==200 and inside.json()["total"]==1
    future=client.get("/api/v1/work-orders",headers=h,params={"date_from":(date.today()+2*day).isoformat()})
    assert future.status_code==200 and future.json()["total"]==0
    past=client.get("/api/v1/work-orders",headers=h,params={"date_to":(date.today()-2*day).isoformat()})
    assert past.status_code==200 and past.json()["total"]==0


CORDOBA=ZoneInfo("America/Argentina/Cordoba")

def _utc_at(month,day,hour,minute=0):
    """Instante naive en UTC a partir de la hora local de la empresa, como guarda la base."""
    return datetime(2026,month,day,hour,minute,tzinfo=CORDOBA).astimezone(timezone.utc).replace(tzinfo=None)

def _utc(day,hour,minute=0):
    return _utc_at(10,day,hour,minute)

def _make_order(client,db,headers,customer,equipment,received_at,completed_at=None,delivered_at=None):
    created=client.post("/api/v1/work-orders",headers=headers,json={"customer_id":customer.id,"equipment_id":equipment.id,"reported_fault":"Falla reportada"})
    assert created.status_code==201,created.text
    row=db.get(WorkOrder,created.json()["id"])
    row.received_at=received_at
    if completed_at is not None: row.completed_at=completed_at
    if delivered_at is not None: row.delivered_at=delivered_at
    db.commit()
    return row


def test_dashboard_today_uses_the_company_day_not_the_utc_day(client,db_session,monkeypatch):
    """El corte del día es la medianoche local de la empresa, no la del servidor.

    Las ventanas quedan desfasadas 3 horas, así que hay órdenes dentro de una y no de
    la otra. Los conteos correctos son 3, 1 y 2; tomar el día UTC daría 2, 2 y 1: los
    tres números cambian, y los tres tests fallan con la implementación en UTC.
    """
    company,_,customer,equipment=setup(db_session,"today-tz")
    h=login(client,"ot.today-tz@example.com",company.id)
    # 2026-10-02T23:00Z == 2026-10-02 20:00 hora de Córdoba.
    monkeypatch.setattr(dashboard_module,"_utcnow",lambda:datetime(2026,10,2,23,0,tzinfo=timezone.utc))

    # Ingresadas: dos de la tarde/madrugada del 2 que solo existen en la ventana local
    # (22:00 y 23:00 ya son UTC del 3) y una que solo existe en la UTC (22:00 del 1).
    _make_order(client,db_session,h,customer,equipment,_utc(2,10))
    _make_order(client,db_session,h,customer,equipment,_utc(2,22))
    _make_order(client,db_session,h,customer,equipment,_utc(2,23))
    _make_order(client,db_session,h,customer,equipment,_utc(1,22))
    # Terminadas: una dentro del día local y otra que solo cae en el día UTC.
    # Las dos llegaron ayer, que es lo normal para una OT que hoy se termina.
    _make_order(client,db_session,h,customer,equipment,_utc(1,10),completed_at=_utc(2,16))
    _make_order(client,db_session,h,customer,equipment,_utc(1,15),completed_at=_utc(1,22,30))
    # Entregadas: una a la tarde y otra a la noche del 2, ya en UTC del 3.
    _make_order(client,db_session,h,customer,equipment,_utc(1,9),delivered_at=_utc(2,18))
    _make_order(client,db_session,h,customer,equipment,_utc(1,9),delivered_at=_utc(2,22,30))

    body=client.get("/api/v1/dashboard/company",headers=h).json()["today"]
    assert body["date"]=="2026-10-02",body
    assert body["received"]==3,body
    assert body["completed"]==1,body
    assert body["delivered"]==2,body


def test_dashboard_today_counts_only_the_active_company(client,db_session,monkeypatch):
    monkeypatch.setattr(dashboard_module,"_utcnow",lambda:datetime(2026,10,2,23,0,tzinfo=timezone.utc))
    a,_,ca,ea=setup(db_session,"today-iso-a");b,_,cb,eb=setup(db_session,"today-iso-b")
    ha=login(client,"ot.today-iso-a@example.com",a.id);hb=login(client,"ot.today-iso-b@example.com",b.id)
    _make_order(client,db_session,ha,ca,ea,_utc(2,10),completed_at=_utc(2,16),delivered_at=_utc(2,18))
    _make_order(client,db_session,ha,ca,ea,_utc(2,11))
    _make_order(client,db_session,hb,cb,eb,_utc(2,12),completed_at=_utc(2,17),delivered_at=_utc(2,19))
    _make_order(client,db_session,hb,cb,eb,_utc(2,13),completed_at=_utc(2,18))

    own=client.get("/api/v1/dashboard/company",headers=ha).json()["today"]
    assert own=={"date":"2026-10-02","received":2,"completed":1,"delivered":1},own
    other=client.get("/api/v1/dashboard/company",headers=hb).json()["today"]
    assert other=={"date":"2026-10-02","received":2,"completed":2,"delivered":1},other


def test_dashboard_today_follows_the_real_status_flow(client,db_session):
    """Sin congelar el reloj: las fechas que estampa el flujo tienen que contar hoy."""
    company,_,customer,equipment=setup(db_session,"today-flow")
    h=login(client,"ot.today-flow@example.com",company.id)
    created=client.post("/api/v1/work-orders",headers=h,json={"customer_id":customer.id,"equipment_id":equipment.id,"reported_fault":"No enciende"})
    assert created.status_code==201,created.text
    statuses=client.get("/api/v1/work-orders/statuses",headers=h).json()
    today=client.get("/api/v1/dashboard/company",headers=h).json()["today"]
    assert today["received"]==1 and today["completed"]==0 and today["delivered"]==0,today

    listo=next(s for s in statuses if s["marks_completed"])
    assert client.post(f"/api/v1/work-orders/{created.json()['id']}/status",headers=h,json={"status_id":listo["id"]}).status_code==200
    today=client.get("/api/v1/dashboard/company",headers=h).json()["today"]
    assert today["completed"]==1 and today["delivered"]==0,today

    entregado=next(s for s in statuses if s["marks_delivered"])
    assert client.post(f"/api/v1/work-orders/{created.json()['id']}/status",headers=h,json={"status_id":entregado["id"]}).status_code==200
    today=client.get("/api/v1/dashboard/company",headers=h).json()["today"]
    assert today["completed"]==1 and today["delivered"]==1,today


def test_dashboard_today_survives_a_broken_company_timezone(client,db_session,monkeypatch):
    """Una zona horaria inválida no puede romper el dashboard: cae a la de Córdoba."""
    company,_,customer,equipment=setup(db_session,"today-badtz")
    company.timezone="Marte/Olympus_Mons"
    db_session.commit()
    h=login(client,"ot.today-badtz@example.com",company.id)
    monkeypatch.setattr(dashboard_module,"_utcnow",lambda:datetime(2026,10,2,23,0,tzinfo=timezone.utc))
    _make_order(client,db_session,h,customer,equipment,_utc(2,22))
    response=client.get("/api/v1/dashboard/company",headers=h)
    assert response.status_code==200,response.text
    assert response.json()["today"]=={"date":"2026-10-02","received":1,"completed":0,"delivered":0}


def _attention(body,key):
    return next(item for item in body["attention"] if item["key"]==key)


def _follow_link(client,headers,item):
    """Lleva el destino que devuelve el dashboard al listado, como haria el link."""
    params={}
    for status_id in item.get("status_ids") or []: params.setdefault("status_id",[]).append(status_id)
    if "date_to" in item: params["date_to"]=item["date_to"]
    if item.get("open_only"): params["open_only"]="true"
    response=client.get("/api/v1/work-orders",headers=headers,params=params)
    assert response.status_code==200,response.text
    return response.json()


def _add_status(client,headers,name,sort_order,flag,color="#F59E0B"):
    """Crea un estado con su flag semantico. El setup base no trae todos los pasos."""
    created=client.post("/api/v1/work-orders/statuses",headers=headers,json={"name":name,"color":color,"sort_order":sort_order,"active":True,flag:True})
    assert created.status_code==201,created.text
    return created.json()["id"]


def _move(client,headers,row,status_id):
    changed=client.post(f"/api/v1/work-orders/{row.id}/status",headers=headers,json={"status_id":status_id})
    assert changed.status_code==200,changed.text


def test_attention_links_land_on_exactly_the_orders_they_count(client,db_session,monkeypatch):
    """El criterio que manda: seguir el link tiene que dar el mismo total que el contador.

    Si el contador dice 4 y el link abre 37, la seccion esta mintiendo.
    """
    company,_,customer,equipment=setup(db_session,"attn-link")
    h=login(client,"ot.attn-link@example.com",company.id)
    monkeypatch.setattr(dashboard_module,"_utcnow",lambda:datetime(2026,10,2,23,0,tzinfo=timezone.utc))
    base={s["name"]:s["id"] for s in client.get("/api/v1/work-orders/statuses",headers=h).json()}
    esperando_repuesto=_add_status(client,h,"Esperando repuesto",45,"marks_waiting_parts")
    esperando_aprobacion=_add_status(client,h,"Esperando aprobacion del cliente",46,"marks_awaiting_quote_approval",color="#8B5CF6")

    # Una OT por categoria, mas ruido que NO debe entrar en ninguna.
    _move(client,h,_make_order(client,db_session,h,customer,equipment,_utc(2,9)),esperando_repuesto)
    _move(client,h,_make_order(client,db_session,h,customer,equipment,_utc(2,9)),esperando_aprobacion)
    _move(client,h,_make_order(client,db_session,h,customer,equipment,_utc(2,9)),base["Listo"])
    # Vieja y abierta: solo esta entra en la alerta de antiguedad.
    _move(client,h,_make_order(client,db_session,h,customer,equipment,_utc_at(9,10,10)),base["En diagnostico"] if "En diagnostico" in base else base["En diagnóstico"])
    # Vieja pero entregada: no es "abierta", no puede aparecer en ninguna alerta.
    _move(client,h,_make_order(client,db_session,h,customer,equipment,_utc_at(9,10,10)),base["Entregado"])
    # Nueva y entregada: tampoco es "abierta".
    _move(client,h,_make_order(client,db_session,h,customer,equipment,_utc(2,9)),base["Entregado"])

    body=client.get("/api/v1/dashboard/company",headers=h).json()
    counts={item["key"]:item["count"] for item in body["attention"]}
    assert counts=={"awaiting_quote_approval":1,"waiting_parts":1,"ready_to_deliver":1,"older_than_15_days":1},counts
    for key,count in counts.items():
        item=_attention(body,key)
        listed=_follow_link(client,h,item)
        assert listed["total"]==count,f"{key}: contador {count} pero el link abre {listed['total']} ({item})"


def test_attention_resolves_waiting_parts_by_flag_not_by_status_name(client,db_session):
    """El nombre del estado no puede decidir el contador. Era lo que pasaba antes.

    El nombre elegido ni siquiera contiene la palabra que se buscaba antes, asi que el
    test no puede pasar por la misma regla accidentalmente.
    """
    company,_,customer,equipment=setup(db_session,"attn-flag")
    h=login(client,"ot.attn-flag@example.com",company.id)
    created=client.post("/api/v1/work-orders",headers=h,json={"customer_id":customer.id,"equipment_id":equipment.id,"reported_fault":"Falla"})
    assert created.status_code==201,created.text
    nuevo=client.post("/api/v1/work-orders/statuses",headers=h,json={"name":"A la espera de material","color":"#F59E0B","sort_order":50,"active":True,"marks_waiting_parts":True})
    assert nuevo.status_code==201,nuevo.text
    assert client.post(f"/api/v1/work-orders/{created.json()['id']}/status",headers=h,json={"status_id":nuevo.json()["id"]}).status_code==200
    count=_attention(client.get("/api/v1/dashboard/company",headers=h).json(),"waiting_parts")["count"]
    assert count==1,count


def test_open_only_filter_excludes_final_and_delivered_orders(client,db_session):
    company,_,customer,equipment=setup(db_session,"open-only")
    h=login(client,"ot.open-only@example.com",company.id)
    base={s["name"]:s["id"] for s in client.get("/api/v1/work-orders/statuses",headers=h).json()}
    abiertas=[_make_order(client,db_session,h,customer,equipment,_utc(2,9)) for _ in range(3)]
    cerrada=_make_order(client,db_session,h,customer,equipment,_utc(2,9))
    _move(client,h,cerrada,base["Entregado"])
    listed=client.get("/api/v1/work-orders",headers=h,params={"open_only":"true","page_size":100}).json()
    encontrados={o["id"] for o in listed["items"]}
    assert len(abiertas)==3
    assert cerrada.id not in encontrados
    assert listed["total"]==3,listed["total"]
    # Sin el filtro siguen estando todas: el filtro agrega, no oculta.
    assert client.get("/api/v1/work-orders",headers=h,params={"page_size":100}).json()["total"]==4


def test_patch_status_keeps_flags_that_the_caller_did_not_send(client,db_session):
    """Regresión del editor de estados que vive dentro de la pantalla de OT.

    Ese editor manda solo siete campos. Con el PATCH anterior los flags ausentes llegaban
    como False y se borraban, rompiendo en silencio las transiciones que buscan el estado
    destino por flag (el presupuesto deja de mover la OT) y los conteos del dashboard.
    """
    company,_,customer,equipment=setup(db_session,"attn-patch")
    h=login(client,"ot.attn-patch@example.com",company.id)
    objetivo=_add_status(client,h,"Con presupuesto emitido",35,"marks_quoted",color="#8B5CF6")
    antes={s["name"]:{k:v for k,v in s.items() if k.startswith("marks_")} for s in client.get("/api/v1/work-orders/statuses",headers=h).json()}
    assert antes["Con presupuesto emitido"]["marks_quoted"] is True
    # Exactamente el payload que manda WorkOrdersView.saveStatus.
    partial={"name":"Con presupuesto emitido","color":"#8B5CF6","sort_order":35,"active":True,
             "is_initial":False,"is_final":False,"marks_completed":False,"marks_delivered":False}
    changed=client.patch(f"/api/v1/work-orders/statuses/{objetivo}",headers=h,json=partial)
    assert changed.status_code==200,changed.text
    despues=client.get("/api/v1/work-orders/statuses",headers=h).json()
    assert next(s for s in despues if s["id"]==objetivo)["marks_quoted"] is True
    for s in despues: assert {k:v for k,v in s.items() if k.startswith("marks_")}==antes[s["name"]],s["name"]


def test_a_flag_belongs_to_a_single_status_per_company_and_stays_within_the_tenant(client,db_session):
    """Un flag activo en dos estados deja a _move_status sin saber a cual saltar."""
    company,_,customer,equipment=setup(db_session,"attn-excl")
    h=login(client,"ot.attn-excl@example.com",company.id)
    primero=_add_status(client,h,"Esperando repuesto",60,"marks_waiting_parts")
    estados={s["name"]:s for s in client.get("/api/v1/work-orders/statuses",headers=h).json()}
    assert estados["Esperando repuesto"]["marks_waiting_parts"] is True
    # El alta de un segundo estado con el mismo flag le saca el flag al primero.
    segundo=_add_status(client,h,"A la espera de material",61,"marks_waiting_parts",color="#0EA5E9")
    estados={s["name"]:s for s in client.get("/api/v1/work-orders/statuses",headers=h).json()}
    assert estados["A la espera de material"]["marks_waiting_parts"] is True
    assert estados["Esperando repuesto"]["marks_waiting_parts"] is False
    # Y el PATCH hace lo mismo, para cuando se corrige un estado ya cargado.
    client.patch(f"/api/v1/work-orders/statuses/{segundo}",headers=h,json={"name":"A la espera de material","color":"#0EA5E9","sort_order":61,"active":True,"marks_waiting_parts":False,"marks_repair":True})
    estados={s["name"]:s for s in client.get("/api/v1/work-orders/statuses",headers=h).json()}
    assert estados["A la espera de material"]["marks_waiting_parts"] is False
    assert estados["A la espera de material"]["marks_repair"] is True
    # Ninguna empresa toca los estados de la otra.
    otra,_,_,_=setup(db_session,"attn-excl-b")
    h2=login(client,"ot.attn-excl-b@example.com",otra.id)
    ajena=_add_status(client,h2,"Material propio",61,"marks_waiting_parts")
    assert next(s for s in client.get("/api/v1/work-orders/statuses",headers=h2).json() if s["id"]==ajena)["marks_waiting_parts"] is True
    assert next(s for s in client.get("/api/v1/work-orders/statuses",headers=h).json() if s["id"]==primero)["marks_waiting_parts"] is False
