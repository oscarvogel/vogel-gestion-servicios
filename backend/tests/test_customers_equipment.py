from app.core.security import hash_password
from app.models.company import Company
from app.models.role import CompanyUserRole, Permission, Role, role_permissions
from app.models.user import CompanyUser, User

def setup_company(db, suffix):
    company=Company(name=f"Taller {suffix}",slug=f"taller-{suffix}");db.add(company);db.flush()
    user=User(email=f"admin.{suffix}@example.com",full_name=f"Admin {suffix}",password_hash=hash_password("Password1234"));db.add(user);db.flush()
    membership=CompanyUser(company_id=company.id,user_id=user.id,is_admin=True,role="ADMIN",active=True);db.add(membership);db.flush()
    role=Role(company_id=company.id,name="Administrador",is_system=True,active=True);db.add(role);db.flush()
    for code in ("customers.view","customers.manage","equipment.view","equipment.manage"):
        perm=db.query(Permission).filter_by(code=code).one()
        db.execute(role_permissions.insert().values(role_id=role.id,permission_id=perm.id))
    db.add(CompanyUserRole(company_user_id=membership.id,role_id=role.id,active=True));db.commit()
    return company,user

def login_company(client,email,company_id):
    token=client.post("/api/v1/auth/login",json={"email":email,"password":"Password1234"}).json()["access_token"]
    response=client.post("/api/v1/auth/select-company",headers={"Authorization":f"Bearer {token}"},json={"company_id":company_id})
    assert response.status_code==200,response.text
    return {"Authorization":f"Bearer {response.json()['access_token']}"}

def test_same_customer_can_exist_in_two_companies_and_is_isolated(client,db_session):
    a,_=setup_company(db_session,"a");b,_=setup_company(db_session,"b")
    ha=login_company(client,"admin.a@example.com",a.id);hb=login_company(client,"admin.b@example.com",b.id)
    payload={"name":"Oscar Vogel","document":"12345678","phone":"3743000000"}
    ra=client.post("/api/v1/customers",headers=ha,json=payload);rb=client.post("/api/v1/customers",headers=hb,json=payload)
    assert ra.status_code==201,ra.text;assert rb.status_code==201,rb.text
    assert ra.json()["company_id"]==a.id;assert rb.json()["company_id"]==b.id
    la=client.get("/api/v1/customers",headers=ha).json()["items"]
    lb=client.get("/api/v1/customers",headers=hb).json()["items"]
    assert {x["company_id"] for x in la}=={a.id};assert {x["company_id"] for x in lb}=={b.id}

def test_equipment_cannot_cross_customer_tenant(client,db_session):
    a,_=setup_company(db_session,"a");b,_=setup_company(db_session,"b")
    ha=login_company(client,"admin.a@example.com",a.id);hb=login_company(client,"admin.b@example.com",b.id)
    ca=client.post("/api/v1/customers",headers=ha,json={"name":"Oscar A"}).json()
    cb=client.post("/api/v1/customers",headers=hb,json={"name":"Oscar B"}).json()
    category=client.post("/api/v1/customers/equipment-categories",headers=ha,json={"name":"TV"}).json()
    ok=client.post(f"/api/v1/customers/{ca['id']}/equipment",headers=ha,json={"customer_id":ca["id"],"category_id":category["id"],"brand":"Samsung"})
    assert ok.status_code==201,ok.text
    denied=client.get(f"/api/v1/customers/{ca['id']}/equipment",headers=hb)
    assert denied.status_code==404
    mismatch=client.post(f"/api/v1/customers/{cb['id']}/equipment",headers=hb,json={"customer_id":ca["id"],"category_id":category["id"]})
    assert mismatch.status_code==422

def test_categories_are_tenant_scoped_and_case_insensitive(client,db_session):
    a,_=setup_company(db_session,"cat-a");b,_=setup_company(db_session,"cat-b")
    ha=login_company(client,"admin.cat-a@example.com",a.id);hb=login_company(client,"admin.cat-b@example.com",b.id)
    first=client.post("/api/v1/customers/equipment-categories",headers=ha,json={"name":"Notebook"})
    again=client.post("/api/v1/customers/equipment-categories",headers=ha,json={"name":" notebook "})
    other=client.post("/api/v1/customers/equipment-categories",headers=hb,json={"name":"Notebook"})
    assert first.status_code==201 and again.status_code==201 and other.status_code==201
    assert first.json()["id"]==again.json()["id"]
    assert first.json()["company_id"]==a.id and other.json()["company_id"]==b.id
    assert {x["company_id"] for x in client.get("/api/v1/customers/equipment-categories/search",headers=ha).json()}=={a.id}
    assert mismatch.status_code==422
