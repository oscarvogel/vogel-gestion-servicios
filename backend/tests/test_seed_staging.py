from app.models.company import Company
from app.models.role import CompanyUserRole, Permission, Role
from app.models.user import CompanyUser, User
from scripts.seed_staging import SeedCredentials, seed_staging


def test_seed_is_idempotent(db_session):
    credentials = SeedCredentials(
        superadmin_email="superadmin@staging.example.com",
        superadmin_password="super-secret",
        admin_a_email="admin.a@staging.example.com",
        admin_a_password="admin-a-secret",
        admin_b_email="admin.b@staging.example.com",
        admin_b_password="admin-b-secret",
        user_a_email="a@staging.example.com",
        user_a_password="a-secret",
        user_b_email="b@staging.example.com",
        user_b_password="b-secret",
        shared_email="shared@staging.example.com",
        shared_password="shared-secret",
    )

    seed_staging(db_session, credentials)
    seed_staging(db_session, credentials)

    assert db_session.query(Company).count() == 2
    assert db_session.query(User).count() == 6
    assert db_session.query(CompanyUser).count() == 6
    assert db_session.query(Role).count() >= 4
    assert db_session.query(Permission).count() >= 11
    assert db_session.query(CompanyUserRole).count() >= 6


def test_seed_creates_admin_roles_for_each_company(db_session):
    credentials = SeedCredentials(
        superadmin_email="superadmin@staging.example.com",
        superadmin_password="super-secret",
        admin_a_email="admin.a@staging.example.com",
        admin_a_password="admin-a-secret",
        admin_b_email="admin.b@staging.example.com",
        admin_b_password="admin-b-secret",
        user_a_email="a@staging.example.com",
        user_a_password="a-secret",
        user_b_email="b@staging.example.com",
        user_b_password="b-secret",
        shared_email="shared@staging.example.com",
        shared_password="shared-secret",
    )
    seed_staging(db_session, credentials)
    companies = db_session.query(Company).order_by(Company.name).all()
    for company in companies:
        admin_role = (
            db_session.query(Role)
            .filter_by(company_id=company.id, name="Administrador")
            .first()
        )
        assert admin_role is not None
        assert admin_role.is_system is True
        assert admin_role.active is True