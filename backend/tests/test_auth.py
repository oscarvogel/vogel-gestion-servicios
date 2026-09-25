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
