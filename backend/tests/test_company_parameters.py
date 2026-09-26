from app.models.company import Company,CompanyParameter
from app.models.user import CompanyUser,User
from app.core.security import hash_password

def _login(client,db):
    company=Company(name="Params Co",slug="params-co");db.add(company);db.flush()
    user=User(email="params@example.com",full_name="Admin Params",password_hash=hash_password("Password1234"));db.add(user);db.flush()
    db.add(CompanyUser(company_id=company.id,user_id=user.id,is_admin=True,role="ADMIN",active=True))
    db.add(CompanyParameter(company_id=company.id,parameter="pricing.parts_markup_percent",value="35",description="Recargo",data_type="decimal",category="precios",editable=True))
    db.commit()
    token=client.post("/api/v1/auth/login",json={"email":user.email,"password":"Password1234"}).json()["access_token"]
    selected=client.post("/api/v1/auth/select-company",headers={"Authorization":f"Bearer {token}"},json={"company_id":company.id}).json()["access_token"]
    return company,{"Authorization":f"Bearer {selected}"}

def test_company_parameters_are_tenant_scoped_and_admin_editable(client,db_session):
    company,h=_login(client,db_session)
    rows=client.get("/api/v1/company-parameters",headers=h)
    assert rows.status_code==200 and rows.json()[0]["value"]==35.0
    changed=client.patch("/api/v1/company-parameters/pricing.parts_markup_percent",headers=h,json={"value":42.5})
    assert changed.status_code==200 and changed.json()["value"]==42.5
    assert db_session.query(CompanyParameter).filter_by(company_id=company.id).one().value=="42.5"
