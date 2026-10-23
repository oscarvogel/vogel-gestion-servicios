from jose import jwt

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.models.user import User
from tests.test_tenant_isolation import bearer, seed_companies_and_users


def test_login_returns_tokens_without_company_context(client, db_session):
    seed_companies_and_users(db_session)

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "password-a"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]
    assert payload["refresh_token"]
    access_payload = jwt.decode(
        payload["access_token"], settings.jwt_secret, algorithms=["HS256"]
    )
    assert "company_id" not in access_payload


def test_login_rejects_invalid_password(client, db_session):
    seed_companies_and_users(db_session)

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "wrong"},
    )

    assert response.status_code == 401


def test_refresh_returns_access_token_without_company_context(client, db_session):
    seed_companies_and_users(db_session)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "password-a"},
    )

    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login.json()["refresh_token"]},
    )

    assert response.status_code == 200
    payload = jwt.decode(
        response.json()["access_token"], settings.jwt_secret, algorithms=["HS256"]
    )
    assert payload["type"] == "access"
    assert "company_id" not in payload


def test_refresh_rejects_access_token(client, db_session):
    _, _, _, user_a, _, _ = seed_companies_and_users(db_session)
    access_token = create_access_token(user_a.id)

    response = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": access_token}
    )

    assert response.status_code == 401


def test_select_company_returns_a_refresh_token_with_the_company(client, db_session):
    """Elegir empresa tiene que devolver un refresh token con esa empresa.

    Si el refresh token no la lleva, la proxima renovacion del access token deja
    al usuario en modo plataforma: todas las consultas de empresa responden 409 y la
    pantalla queda en cero sin explicar nada.
    """
    company_a, _, _, user_a, _, _ = seed_companies_and_users(db_session)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "password-a"},
    ).json()

    response = client.post(
        "/api/v1/auth/select-company",
        headers=bearer(login["access_token"]),
        json={"company_id": company_a.id},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["refresh_token"]
    refresh_payload = jwt.decode(
        payload["refresh_token"], settings.jwt_secret, algorithms=["HS256"]
    )
    assert refresh_payload["type"] == "refresh"
    assert refresh_payload["company_id"] == company_a.id


def test_refresh_after_select_company_keeps_the_company_context(client, db_session):
    """Renovar el token no puede sacar al usuario de la empresa."""
    company_a, _, _, user_a, _, _ = seed_companies_and_users(db_session)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "password-a"},
    ).json()
    selected = client.post(
        "/api/v1/auth/select-company",
        headers=bearer(login["access_token"]),
        json={"company_id": company_a.id},
    ).json()

    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": selected["refresh_token"]},
    )

    assert response.status_code == 200
    access_token = response.json()["access_token"]
    payload = jwt.decode(access_token, settings.jwt_secret, algorithms=["HS256"])
    assert payload["company_id"] == company_a.id

    # Y con ese token las consultas de empresa responden 200, no 409.
    empresas = client.get("/api/v1/companies/current", headers=bearer(access_token))
    assert empresas.status_code == 200, empresas.text
    assert empresas.json()["id"] == company_a.id


def test_leave_company_returns_a_refresh_token_without_company(client, db_session):
    """Salir de la empresa devuelve el refresh token al modo plataforma."""
    company_a, _, _, user_a, _, _ = seed_companies_and_users(db_session)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "password-a"},
    ).json()
    selected = client.post(
        "/api/v1/auth/select-company",
        headers=bearer(login["access_token"]),
        json={"company_id": company_a.id},
    ).json()

    response = client.post(
        "/api/v1/auth/leave-company", headers=bearer(selected["access_token"])
    )

    assert response.status_code == 200
    refresh_payload = jwt.decode(
        response.json()["refresh_token"], settings.jwt_secret, algorithms=["HS256"]
    )
    assert "company_id" not in refresh_payload


def test_inactive_user_cannot_login(client, db_session):
    user = User(
        email="inactive@example.com",
        full_name="Inactive",
        password_hash=hash_password("password"),
        active=False,
    )
    db_session.add(user)
    db_session.commit()

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "inactive@example.com", "password": "password"},
    )

    assert response.status_code == 401
