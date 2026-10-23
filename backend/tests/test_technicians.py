"""Maestro de tecnicos y asignacion de tecnicos a las ordenes de trabajo.

Cubre lo que el legacy no tenia: un maestro manejable (alta, renombre, activar) y el vinculo
entre un tecnico y una OT, tanto al crear la orden como despues.
"""
from app.core.security import hash_password
from app.models.company import Company
from app.models.customer import Customer,Equipment,EquipmentCategory
from app.models.role import CompanyUserRole,Permission,Role,role_permissions
from app.models.user import CompanyUser,User
from app.models.work_area import Technician
from app.models.work_order import WorkOrderStatus


def setup(db,suffix,permisos=("customers.view","customers.manage","equipment.view","equipment.manage","work_orders.view","work_orders.manage","technicians.view","technicians.manage")):
    company=Company(name=f"OT {suffix}",slug=f"ot-{suffix}");db.add(company);db.flush()
    user=User(email=f"ot.{suffix}@example.com",full_name=f"Recepción {suffix}",password_hash=hash_password("Password1234"));db.add(user);db.flush()
    membership=CompanyUser(company_id=company.id,user_id=user.id,is_admin=True,role="ADMIN",active=True);db.add(membership);db.flush()
    role=Role(company_id=company.id,name="Administrador",is_system=True,active=True);db.add(role);db.flush()
    for code in permisos:
        p=db.query(Permission).filter_by(code=code).one();db.execute(role_permissions.insert().values(role_id=role.id,permission_id=p.id))
    db.add(CompanyUserRole(company_user_id=membership.id,role_id=role.id,active=True))
    db.add(WorkOrderStatus(company_id=company.id,name="Recibido",color="#10B981",sort_order=10,active=True,is_initial=True,is_final=False))
    db.commit()
    customer=Customer(company_id=company.id,name=f"Cliente {suffix}");db.add(customer);db.flush()
    cat=EquipmentCategory(company_id=company.id,name="Televisor");db.add(cat);db.flush()
    equipment=Equipment(company_id=company.id,customer_id=customer.id,category_id=cat.id,brand="Samsung",model="QLED",serial_number=f"SER-{suffix}");db.add(equipment);db.commit()
    return company,user,customer,equipment


def login(client,email,cid):
    token=client.post("/api/v1/auth/login",json={"email":email,"password":"Password1234"}).json()["access_token"]
    r=client.post("/api/v1/auth/select-company",headers={"Authorization":f"Bearer {token}"},json={"company_id":cid})
    return {"Authorization":f"Bearer {r.json()['access_token']}"}


def test_maestro_tecnicos_alta_renombre_y_desactivar(client,db_session):
    company,_,_,_=setup(db_session,"tec")
    h=login(client,"ot.tec@example.com",company.id)

    alta=client.post("/api/v1/technicians",headers=h,json={"name":"  Britez   Sebastian  "})
    assert alta.status_code==201,alta.text
    assert alta.json()["name"]=="Britez Sebastian"   # los espacios de mas se limpian
    assert alta.json()["active"] is True

    # No se puede repetir el nombre (ni con acentos o mayusculas distintas).
    repetido=client.post("/api/v1/technicians",headers=h,json={"name":"britéz sebastian"})
    assert repetido.status_code==409,repetido.text

    renombrado=client.patch(f"/api/v1/technicians/{alta.json()['id']}",headers=h,json={"name":"Britez, Sebastian"})
    assert renombrado.status_code==200 and renombrado.json()["name"]=="Britez, Sebastian"

    desactivado=client.patch(f"/api/v1/technicians/{alta.json()['id']}",headers=h,json={"active":False})
    assert desactivado.status_code==200 and desactivado.json()["active"] is False

    listado=client.get("/api/v1/technicians",headers=h)
    assert listado.status_code==200 and len(listado.json())==1


def test_tecnico_de_otra_empresa_no_se_ve_ni_se_asigna(client,db_session):
    a,_,ca,ea=setup(db_session,"a");b,_,cb,eb=setup(db_session,"b")
    ha=login(client,"ot.a@example.com",a.id);hb=login(client,"ot.b@example.com",b.id)

    tecnico=client.post("/api/v1/technicians",headers=ha,json={"name":"Técnico de A"}).json()

    # El maestro es por empresa.
    assert client.get("/api/v1/technicians",headers=hb).json()==[]

    ot=client.post("/api/v1/work-orders",headers=hb,json={"customer_id":cb.id,"equipment_id":eb.id,"reported_fault":"No enciende"})
    assert ot.status_code==201

    # No se puede asignar un tecnico de otra empresa.
    cruzado=client.post(f"/api/v1/work-orders/{ot.json()['id']}/technicians",headers=hb,json={"technician_id":tecnico["id"]})
    assert cruzado.status_code==404,cruzado.text
    # Tampoco tocar el maestro ajeno.
    assert client.patch(f"/api/v1/technicians/{tecnico['id']}",headers=hb,json={"name":"Robado"}).status_code==404


def test_asignar_y_quitar_tecnico_en_una_ot(client,db_session):
    company,_,customer,equipment=setup(db_session,"asig")
    h=login(client,"ot.asig@example.com",company.id)
    tecnico=client.post("/api/v1/technicians",headers=h,json={"name":"Alladio"}).json()

    ot=client.post("/api/v1/work-orders",headers=h,json={"customer_id":customer.id,"equipment_id":equipment.id,"reported_fault":"Falla"})
    assert ot.status_code==201 and ot.json()["technicians"]==[]

    asignado=client.post(f"/api/v1/work-orders/{ot.json()['id']}/technicians",headers=h,json={"technician_id":tecnico["id"]})
    assert asignado.status_code==200,asignado.text
    assert [t["name"] for t in asignado.json()["technicians"]]==["Alladio"]

    # Asignar dos veces no duplica.
    repetido=client.post(f"/api/v1/work-orders/{ot.json()['id']}/technicians",headers=h,json={"technician_id":tecnico["id"]})
    assert repetido.status_code==200 and len(repetido.json()["technicians"])==1

    # Queda registrado en el historial.
    events=client.get(f"/api/v1/work-orders/{ot.json()['id']}/events",headers=h).json()
    assert any(e["event_type"]=="technician_assigned" for e in events)

    quitado=client.delete(f"/api/v1/work-orders/{ot.json()['id']}/technicians/{tecnico['id']}",headers=h)
    assert quitado.status_code==200 and quitado.json()["technicians"]==[]
    # Y tambien en el historial.
    events=client.get(f"/api/v1/work-orders/{ot.json()['id']}/events",headers=h).json()
    assert any(e["event_type"]=="technician_unassigned" for e in events)


def test_recepcion_puede_asignar_el_tecnico(client,db_session):
    company,_,customer,equipment=setup(db_session,"recep")
    h=login(client,"ot.recep@example.com",company.id)
    tecnico=client.post("/api/v1/technicians",headers=h,json={"name":"Técnico de reception"}).json()

    ot=client.post("/api/v1/work-orders",headers=h,json={"customer_id":customer.id,"equipment_id":equipment.id,"reported_fault":"Falla","technician_id":tecnico["id"]})
    assert ot.status_code==201,ot.text
    assert [t["name"] for t in ot.json()["technicians"]]==["Técnico de reception"]

    # Un tecnico de otra empresa no se puede colar por la recepcion.
    otra,_,_,_=setup(db_session,"otra")
    ajeno=db_session.query(Technician).filter_by(company_id=otra.id).first()
    if ajeno is None:
        ajeno=Technician(company_id=otra.id,name="Ajeno");db_session.add(ajeno);db_session.commit()
    colado=client.post("/api/v1/work-orders",headers=h,json={"customer_id":customer.id,"equipment_id":equipment.id,"reported_fault":"Falla","technician_id":ajeno.id})
    assert colado.status_code==422,colado.text


def test_tecnico_desactivado_no_se_puede_asignar(client,db_session):
    company,_,customer,equipment=setup(db_session,"desact")
    h=login(client,"ot.desact@example.com",company.id)
    tecnico=client.post("/api/v1/technicians",headers=h,json={"name":" Baja "}).json()
    client.patch(f"/api/v1/technicians/{tecnico['id']}",headers=h,json={"active":False})

    ot=client.post("/api/v1/work-orders",headers=h,json={"customer_id":customer.id,"equipment_id":equipment.id,"reported_fault":"Falla"})
    asignado=client.post(f"/api/v1/work-orders/{ot.json()['id']}/technicians",headers=h,json={"technician_id":tecnico["id"]})
    assert asignado.status_code==409,asignado.text

    colado=client.post("/api/v1/work-orders",headers=h,json={"customer_id":customer.id,"equipment_id":equipment.id,"reported_fault":"Falla","technician_id":tecnico["id"]})
    assert colado.status_code==409,colado.text


def test_permisos_del_maestro(client,db_session):
    # Sin technicians.manage no puede dar de alta ni editar, pero si listar (lo necesita
    # para asignar a una orden).
    company,_,customer,equipment=setup(db_session,"perm",permisos=("customers.view","customers.manage","equipment.view","equipment.manage","work_orders.view","work_orders.manage"))
    h=login(client,"ot.perm@example.com",company.id)

    assert client.get("/api/v1/technicians",headers=h).status_code==200
    assert client.post("/api/v1/technicians",headers=h,json={"name":"Alguien"}).status_code==403

    # Sin work_orders.manage tampoco puede crear ordenes ni asignar, aunque pueda ver el
    # maestro: asignar un tecnico es parte de gestionar la orden.
    otra,_,_,_=setup(db_session,"sinot",permisos=("technicians.view","technicians.manage"))
    h2=login(client,"ot.sinot@example.com",otra.id)
    tecnico=client.post("/api/v1/technicians",headers=h2,json={"name":"Solo maestro"}).json()
    assert client.get("/api/v1/technicians",headers=h2).status_code==200
    ot=client.post("/api/v1/work-orders",headers=h2,json={"customer_id":customer.id,"equipment_id":equipment.id,"reported_fault":"Falla"})
    assert ot.status_code==403,ot.text
