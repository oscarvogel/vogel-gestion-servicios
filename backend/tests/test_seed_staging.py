from app.models.company import Company
from app.models.user import CompanyUser, User
from scripts.seed_staging import SeedCredentials, seed_staging


def test_seed_is_idempotent(db_session):
    credentials = SeedCredentials(
        superadmin_email="superadmin@staging.example.com",
        superadmin_password="super-secret",
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
    assert db_session.query(User).count() == 4
    assert db_session.query(CompanyUser).count() == 4
