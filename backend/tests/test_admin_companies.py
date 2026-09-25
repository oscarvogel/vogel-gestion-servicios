"""Tests negativos de aislamiento multitenant y permisos."""
from app.core.security import create_access_token, hash_password
from app.models.company import Company
from app.models.role import CompanyUserRole, Permission, Role, role_permissions
from app.models.user import CompanyUser, User


def _login(client, email: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _select_company(client, token: str, company_id: int) -> str:
    response = client.post(
        "/api/v1/auth/select-company",
        headers={"Authorization": f"Bearer {token}"},
        json={"company_id": company_id},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


PERM_CODES = [
    "companies.view",
    "companies.create",
    "companies.update",
    "companies.disable",
    "companies.manage_users",
    "users.view",
    "users.create",
    "users.update",
    "users.disable",
    "roles.view",
    "roles.manage",
]


def _seed_full(db_session):
    company_a = Company(name="Empresa A")
    company_b = Company(name="Empresa B")
    db_session.add_all([company_a, company_b])
    db_session.flush()

    user_admin_a = User(
        email="admin.a@example.com",
        full_name="Admin A",
        password_hash=hash_password("admin-a"),
    )
    user_admin_b = User(
        email="admin.b@example.com",
        full_name="Admin B",
        password_hash=hash_password("admin-b"),
    )
    user_member_a = User(
        email="member.a@example.com",
        full_name="Miembro A",
        password_hash=hash_password("member-a"),
    )
    superadmin = User(
        email="root@example.com",
        full_name="SuperAdmin",
        password_hash=hash_password("root-pwd"),
        is_superadmin=True,
    )
    db_session.add_all([user_admin_a, user_admin_b, user_member_a, superadmin])
    db_session.flush()

    membership_admin_a = CompanyUser(
        company_id=company_a.id,
        user_id=user_admin_a.id,
        is_admin=True,
        role="ADMIN",
        active=True,
    )
    membership_admin_b = CompanyUser(
        company_id=company_b.id,
        user_id=user_admin_b.id,
        is_admin=True,
        role="ADMIN",
        active=True,
    )
    membership_member_a = CompanyUser(
        company_id=company_a.id,
        user_id=user_member_a.id,
        is_admin=False,
        role="MEMBER",
        active=True,
    )
    db_session.add_all(
        [membership_admin_a, membership_admin_b, membership_member_a]
    )
    db_session.flush()

    admin_role_a = Role(
        company_id=company_a.id,
        name="Administrador",
        is_system=True,
        active=True,
    )
    admin_role_b = Role(
        company_id=company_b.id,
        name="Administrador",
        is_system=True,
        active=True,
    )
    member_role_a = Role(
        company_id=company_a.id,
        name="Miembro",
        is_system=True,
        active=True,
    )
    db_session.add_all([admin_role_a, admin_role_b, member_role_a])
    db_session.flush()

    perms = {
        p.code: p
        for p in db_session.query(Permission).filter(Permission.code.in_(PERM_CODES)).all()
    }
    for role in (admin_role_a, admin_role_b):
        for code in PERM_CODES:
            db_session.execute(
                role_permissions.insert().values(
                    role_id=role.id, permission_id=perms[code].id
                )
            )
    db_session.add_all(
        [
            CompanyUserRole(
                company_user_id=membership_admin_a.id,
                role_id=admin_role_a.id,
                active=True,
            ),
            CompanyUserRole(
                company_user_id=membership_admin_b.id,
                role_id=admin_role_b.id,
                active=True,
            ),
            CompanyUserRole(
                company_user_id=membership_member_a.id,
                role_id=member_role_a.id,
                active=True,
            ),
        ]
    )
    db_session.commit()
    return {
        "company_a": company_a,
        "company_b": company_b,
        "admin_a": user_admin_a,
        "admin_b": user_admin_b,
        "member_a": user_member_a,
        "superadmin": superadmin,
    }


def test_admin_a_cannot_get_company_b(client, db_session):
    data = _seed_full(db_session)
    token = _login(client, "admin.a@example.com", "admin-a")
    response = client.get(
        f"/api/v1/companies/{data['company_b'].id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_admin_a_cannot_update_company_b(client, db_session):
    data = _seed_full(db_session)
    token = _login(client, "admin.a@example.com", "admin-a")
    response = client.patch(
        f"/api/v1/companies/{data['company_b'].id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Hack"},
    )
    assert response.status_code == 403


def test_admin_a_cannot_create_company(client, db_session):
    _seed_full(db_session)
    token = _login(client, "admin.a@example.com", "admin-a")
    response = client.post(
        "/api/v1/companies",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Empresa Hack"},
    )
    assert response.status_code == 403


def test_member_a_cannot_create_user(client, db_session):
    data = _seed_full(db_session)
    token = _login(client, "member.a@example.com", "member-a")
    ctx = _select_company(client, token, data["company_a"].id)
    response = client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {ctx}"},
        json={
            "email": "nuevo@example.com",
            "full_name": "Nuevo",
            "password": "Password1234",
        },
    )
    assert response.status_code == 403


def test_member_a_cannot_disable_user(client, db_session):
    data = _seed_full(db_session)
    token = _login(client, "member.a@example.com", "member-a")
    ctx = _select_company(client, token, data["company_a"].id)
    response = client.post(
        f"/api/v1/users/{data['admin_a'].id}/disable",
        headers={"Authorization": f"Bearer {ctx}"},
    )
    assert response.status_code == 403


def test_admin_a_cannot_access_user_from_company_b(client, db_session):
    data = _seed_full(db_session)
    token = _login(client, "admin.a@example.com", "admin-a")
    ctx = _select_company(client, token, data["company_a"].id)
    response = client.get(
        f"/api/v1/users/{data['admin_b'].id}",
        headers={"Authorization": f"Bearer {ctx}"},
    )
    assert response.status_code == 403


def test_admin_a_cannot_create_user_in_company_b(client, db_session):
    data = _seed_full(db_session)
    token = _login(client, "admin.a@example.com", "admin-a")
    ctx = _select_company(client, token, data["company_a"].id)
    response = client.post(
        f"/api/v1/users/{data['admin_a'].id}/memberships",
        headers={"Authorization": f"Bearer {ctx}"},
        json={"company_id": data["company_b"].id, "role": "MEMBER"},
    )
    assert response.status_code == 403


def test_forged_company_token_is_rejected(client, db_session):
    data = _seed_full(db_session)
    forged = create_access_token(
        data["admin_a"].id, company_id=data["company_b"].id
    )
    response = client.get(
        "/api/v1/companies/current",
        headers={"Authorization": f"Bearer {forged}"},
    )
    assert response.status_code == 403


def test_admin_a_without_company_context_cannot_use_scoped_endpoint(client, db_session):
    _seed_full(db_session)
    token = _login(client, "admin.a@example.com", "admin-a")
    response = client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 409


def test_admin_company_cannot_hit_superadmin_dashboard(client, db_session):
    data = _seed_full(db_session)
    token = _login(client, "admin.a@example.com", "admin-a")
    ctx = _select_company(client, token, data["company_a"].id)
    response = client.get(
        "/api/v1/dashboard/superadmin",
        headers={"Authorization": f"Bearer {ctx}"},
    )
    assert response.status_code == 403


def test_member_a_cannot_hit_roles_manage(client, db_session):
    data = _seed_full(db_session)
    token = _login(client, "member.a@example.com", "member-a")
    ctx = _select_company(client, token, data["company_a"].id)
    response = client.post(
        "/api/v1/roles",
        headers={"Authorization": f"Bearer {ctx}"},
        json={"name": "Operador", "permission_ids": []},
    )
    assert response.status_code == 403


def test_disabled_company_blocks_token(client, db_session):
    data = _seed_full(db_session)
    token = _login(client, "admin.a@example.com", "admin-a")
    ctx = _select_company(client, token, data["company_a"].id)
    data["company_a"].active = False
    db_session.commit()
    response = client.get(
        "/api/v1/companies/current",
        headers={"Authorization": f"Bearer {ctx}"},
    )
    assert response.status_code == 403


def test_disabled_user_cannot_login(client, db_session):
    data = _seed_full(db_session)
    data["admin_a"].active = False
    db_session.commit()
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin.a@example.com", "password": "admin-a"},
    )
    assert response.status_code == 401


def test_superadmin_can_list_all_companies(client, db_session):
    _seed_full(db_session)
    token = _login(client, "root@example.com", "root-pwd")
    response = client.get(
        "/api/v1/companies",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2


def test_superadmin_can_create_company_with_admin(client, db_session):
    _seed_full(db_session)
    token = _login(client, "root@example.com", "root-pwd")
    response = client.post(
        "/api/v1/companies",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Empresa C",
            "admin_email": "admin.c@example.com",
            "admin_full_name": "Admin C",
            "admin_password": "Password1234",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Empresa C"


def test_role_manage_requires_admin(client, db_session):
    data = _seed_full(db_session)
    token = _login(client, "member.a@example.com", "member-a")
    ctx = _select_company(client, token, data["company_a"].id)
    response = client.post(
        "/api/v1/roles",
        headers={"Authorization": f"Bearer {ctx}"},
        json={"name": "Operador", "permission_ids": []},
    )
    assert response.status_code == 403


def test_me_returns_permissions_for_active_companies(client, db_session):
    data = _seed_full(db_session)
    token = _login(client, "admin.a@example.com", "admin-a")
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "companies.create" in body["permissions"]
    ids = {m["company_id"] for m in body["memberships"]}
    assert data["company_a"].id in ids
    assert data["company_b"].id not in ids


def test_superadmin_user_list_tolerates_legacy_invalid_email(client, db_session):
    data = _seed_full(db_session)
    data["admin_a"].email = "legacy@localhost"
    db_session.commit()
    token = _login(client, "root@example.com", "root-pwd")
    response = client.get(
        "/api/v1/users?page=1&page_size=20",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    item = next(row for row in response.json()["items"] if row["id"] == data["admin_a"].id)
    assert item["email"] == "legacy@localhost"
