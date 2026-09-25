from jose import jwt

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.models.company import Company
from app.models.user import CompanyUser, User


def seed_companies_and_users(db_session):
    company_a = Company(name="Empresa A")
    company_b = Company(name="Empresa B")
    inactive = Company(name="Empresa Inactiva", active=False)
    user_a = User(
        email="a@example.com",
        full_name="Usuario A",
        password_hash=hash_password("password-a"),
    )
    user_b = User(
        email="b@example.com",
        full_name="Usuario B",
        password_hash=hash_password("password-b"),
    )
    superadmin = User(
        email="superadmin@example.com",
        full_name="SuperAdmin",
        password_hash=hash_password("password-super"),
        is_superadmin=True,
    )
    db_session.add_all([company_a, company_b, inactive, user_a, user_b, superadmin])
    db_session.flush()
    db_session.add_all(
        [
            CompanyUser(company_id=company_a.id, user_id=user_a.id, role="ADMIN"),
            CompanyUser(company_id=company_b.id, user_id=user_b.id, role="ADMIN"),
        ]
    )
    db_session.commit()
    return company_a, company_b, inactive, user_a, user_b, superadmin


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_user_a_can_select_company_a(client, db_session):
    company_a, _, _, _, _, _ = seed_companies_and_users(db_session)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "password-a"},
    )

    response = client.post(
        "/api/v1/auth/select-company",
        headers=bearer(login.json()["access_token"]),
        json={"company_id": company_a.id},
    )

    assert response.status_code == 200
    payload = jwt.decode(
        response.json()["access_token"],
        settings.jwt_secret,
        algorithms=["HS256"],
    )
    assert int(payload["company_id"]) == company_a.id
    current = client.get(
        "/api/v1/companies/current",
        headers=bearer(response.json()["access_token"]),
    )
    assert current.status_code == 200
    assert current.json()["id"] == company_a.id


def test_user_a_cannot_select_company_b(client, db_session):
    _, company_b, _, _, _, _ = seed_companies_and_users(db_session)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "password-a"},
    )

    response = client.post(
        "/api/v1/auth/select-company",
        headers=bearer(login.json()["access_token"]),
        json={"company_id": company_b.id},
    )

    assert response.status_code == 403


def test_user_b_cannot_select_company_a(client, db_session):
    company_a, _, _, _, _, _ = seed_companies_and_users(db_session)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "b@example.com", "password": "password-b"},
    )

    response = client.post(
        "/api/v1/auth/select-company",
        headers=bearer(login.json()["access_token"]),
        json={"company_id": company_a.id},
    )

    assert response.status_code == 403


def test_missing_company_is_rejected(client, db_session):
    seed_companies_and_users(db_session)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "password-a"},
    )

    response = client.post(
        "/api/v1/auth/select-company",
        headers=bearer(login.json()["access_token"]),
        json={"company_id": 99999},
    )

    assert response.status_code == 404


def test_inactive_company_is_rejected(client, db_session):
    _, _, inactive, _, _, _ = seed_companies_and_users(db_session)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "password-a"},
    )

    response = client.post(
        "/api/v1/auth/select-company",
        headers=bearer(login.json()["access_token"]),
        json={"company_id": inactive.id},
    )

    assert response.status_code == 403


def test_inactive_company_is_rejected_by_tenant_context(client, db_session):
    company_a, _, _, _, _, _ = seed_companies_and_users(db_session)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "password-a"},
    )
    selected = client.post(
        "/api/v1/auth/select-company",
        headers=bearer(login.json()["access_token"]),
        json={"company_id": company_a.id},
    )
    company_a.active = False
    db_session.commit()

    response = client.get(
        "/api/v1/companies/current",
        headers=bearer(selected.json()["access_token"]),
    )

    assert response.status_code == 403


def test_access_token_without_company_cannot_use_tenant_endpoint(client, db_session):
    seed_companies_and_users(db_session)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "password-a"},
    )

    response = client.get(
        "/api/v1/companies/current",
        headers=bearer(login.json()["access_token"]),
    )

    assert response.status_code == 409


def test_forged_company_id_does_not_cross_tenant(client, db_session):
    _, company_b, _, user_a, _, _ = seed_companies_and_users(db_session)
    forged = create_access_token(user_a.id, company_id=company_b.id)

    response = client.get("/api/v1/companies/current", headers=bearer(forged))

    assert response.status_code == 403


def test_superadmin_can_select_active_company(client, db_session):
    company_a, _, _, _, _, _ = seed_companies_and_users(db_session)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "superadmin@example.com", "password": "password-super"},
    )

    response = client.post(
        "/api/v1/auth/select-company",
        headers=bearer(login.json()["access_token"]),
        json={"company_id": company_a.id},
    )

    assert response.status_code == 200


def test_superadmin_cannot_select_missing_or_inactive_company(client, db_session):
    _, _, inactive, _, _, _ = seed_companies_and_users(db_session)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "superadmin@example.com", "password": "password-super"},
    )
    headers = bearer(login.json()["access_token"])

    inactive_response = client.post(
        "/api/v1/auth/select-company",
        headers=headers,
        json={"company_id": inactive.id},
    )
    missing_response = client.post(
        "/api/v1/auth/select-company",
        headers=headers,
        json={"company_id": 99999},
    )

    assert inactive_response.status_code == 403
    assert missing_response.status_code == 404
