from app.models.company import Company,CompanyParameter,ParameterDefinition
from app.models.user import CompanyUser,User
from app.core.security import hash_password

def _login(client,db,name,email):
    company=Company(name=name,slug=name.lower().replace(" ","-"));db.add(company);db.flush()
    user=User(email=email,full_name="Admin Params",password_hash=hash_password("Password1234"));db.add(user);db.flush()
    db.add(CompanyUser(company_id=company.id,user_id=user.id,is_admin=True,role="ADMIN",active=True));db.commit()
    token=client.post("/api/v1/auth/login",json={"email":email,"password":"Password1234"}).json()["access_token"]
    selected=client.post("/api/v1/auth/select-company",headers={"Authorization":f"Bearer {token}"},json={"company_id":company.id}).json()["access_token"]
    return company,{"Authorization":f"Bearer {selected}"}

def test_new_company_inherits_catalog_default_without_rows(client,db_session):
    definition=ParameterDefinition(parameter="pricing.parts_markup_percent",default_value="35",description="Recargo",data_type="decimal",category="precios",editable=True,active=True)
    db_session.add(definition);db_session.commit()
    company,h=_login(client,db_session,"Params Co","params@example.com")
    rows=client.get("/api/v1/company-parameters",headers=h)
    assert rows.status_code==200 and rows.json()[0]["value"]==35.0
    assert rows.json()[0]["is_overridden"] is False
    assert db_session.query(CompanyParameter).filter_by(company_id=company.id).count()==0

def test_override_is_tenant_scoped_and_default_restores_without_null(client,db_session):
    definition=ParameterDefinition(parameter="work_orders.use_budget",default_value="true",description="Presupuesto",data_type="bool",category="ordenes",editable=True,active=True)
    db_session.add(definition);db_session.commit()
    a,ha=_login(client,db_session,"Params A","params.a@example.com")
    b,hb=_login(client,db_session,"Params B","params.b@example.com")
    changed=client.patch("/api/v1/company-parameters/work_orders.use_budget",headers=ha,json={"value":False})
    assert changed.status_code==200 and changed.json()["value"] is False and changed.json()["is_overridden"] is True
    assert client.get("/api/v1/company-parameters",headers=hb).json()[0]["value"] is True
    restored=client.patch("/api/v1/company-parameters/work_orders.use_budget",headers=ha,json={"value":True})
    assert restored.status_code==200 and restored.json()["value"] is True and restored.json()["is_overridden"] is False
    assert db_session.query(CompanyParameter).filter_by(company_id=a.id).count()==0
