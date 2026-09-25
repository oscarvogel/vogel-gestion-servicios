from dataclasses import dataclass
import os
from pathlib import Path
import secrets
import sys

from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.company import Company
from app.models.user import CompanyUser, User


@dataclass(frozen=True)
class SeedCredentials:
    superadmin_email: str
    superadmin_password: str
    user_a_email: str
    user_a_password: str
    user_b_email: str
    user_b_password: str
    shared_email: str
    shared_password: str


def _password(name: str) -> str:
    return os.getenv(name) or secrets.token_urlsafe(24)


def load_credentials() -> SeedCredentials:
    return SeedCredentials(
        superadmin_email=os.getenv("STAGING_SUPERADMIN_EMAIL", "superadmin@staging.local"),
        superadmin_password=_password("STAGING_SUPERADMIN_PASSWORD"),
        user_a_email=os.getenv("STAGING_USER_A_EMAIL", "usuario.a@staging.local"),
        user_a_password=_password("STAGING_USER_A_PASSWORD"),
        user_b_email=os.getenv("STAGING_USER_B_EMAIL", "usuario.b@staging.local"),
        user_b_password=_password("STAGING_USER_B_PASSWORD"),
        shared_email=os.getenv("STAGING_SHARED_EMAIL", "usuario.shared@staging.local"),
        shared_password=_password("STAGING_SHARED_PASSWORD"),
    )


def _get_or_create_company(db: Session, name: str) -> Company:
    company = db.query(Company).filter_by(name=name).one_or_none()
    if company is None:
        company = Company(name=name, active=True)
        db.add(company)
        db.flush()
    else:
        company.active = True
    return company


def _get_or_create_user(
    db: Session,
    email: str,
    full_name: str,
    password: str,
    is_superadmin: bool = False,
) -> User:
    user = db.query(User).filter_by(email=email).one_or_none()
    if user is None:
        user = User(
            email=email,
            full_name=full_name,
            password_hash=hash_password(password),
            active=True,
            is_superadmin=is_superadmin,
        )
        db.add(user)
        db.flush()
    else:
        user.active = True
        if is_superadmin:
            user.is_superadmin = True
    return user


def _ensure_membership(db: Session, user_id: int, company_id: int) -> None:
    membership = (
        db.query(CompanyUser)
        .filter_by(user_id=user_id, company_id=company_id)
        .one_or_none()
    )
    if membership is None:
        db.add(CompanyUser(user_id=user_id, company_id=company_id, active=True, role="ADMIN"))
    elif not membership.active:
        membership.active = True


def seed_staging(db: Session, credentials: SeedCredentials) -> None:
    company_a = _get_or_create_company(db, "Empresa Demo A")
    company_b = _get_or_create_company(db, "Empresa Demo B")
    superadmin = _get_or_create_user(
        db,
        credentials.superadmin_email,
        "SuperAdmin Vogel",
        credentials.superadmin_password,
        is_superadmin=True,
    )
    user_a = _get_or_create_user(
        db, credentials.user_a_email, "Usuario Empresa A", credentials.user_a_password
    )
    user_b = _get_or_create_user(
        db, credentials.user_b_email, "Usuario Empresa B", credentials.user_b_password
    )
    shared = _get_or_create_user(
        db, credentials.shared_email, "Usuario Compartido", credentials.shared_password
    )
    _ensure_membership(db, user_a.id, company_a.id)
    _ensure_membership(db, user_b.id, company_b.id)
    _ensure_membership(db, shared.id, company_a.id)
    _ensure_membership(db, shared.id, company_b.id)
    db.commit()


def main() -> None:
    credentials = load_credentials()
    with SessionLocal() as db:
        seed_staging(db, credentials)
    print("STAGING_SEED=OK")
    print("STAGING_SEED_PASSWORDS_SOURCE=environment_or_secure_generation")


if __name__ == "__main__":
    main()
