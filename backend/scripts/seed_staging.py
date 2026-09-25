from dataclasses import dataclass
import os
from pathlib import Path
import secrets
import sys

from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.permissions import PERMISSIONS
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.company import Company
from app.models.role import (
    CompanyUserRole,
    Permission,
    Role,
    role_permissions,
)
from app.models.user import CompanyUser, User


@dataclass(frozen=True)
class SeedCredentials:
    superadmin_email: str
    superadmin_password: str
    admin_a_email: str
    admin_a_password: str
    admin_b_email: str
    admin_b_password: str
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
        admin_a_email=os.getenv("STAGING_ADMIN_A_EMAIL", "admin.a@staging.local"),
        admin_a_password=_password("STAGING_ADMIN_A_PASSWORD"),
        admin_b_email=os.getenv("STAGING_ADMIN_B_EMAIL", "admin.b@staging.local"),
        admin_b_password=_password("STAGING_ADMIN_B_PASSWORD"),
        user_a_email=os.getenv("STAGING_USER_A_EMAIL", "usuario.a@staging.local"),
        user_a_password=_password("STAGING_USER_A_PASSWORD"),
        user_b_email=os.getenv("STAGING_USER_B_EMAIL", "usuario.b@staging.local"),
        user_b_password=_password("STAGING_USER_B_PASSWORD"),
        shared_email=os.getenv("STAGING_SHARED_EMAIL", "usuario.shared@staging.local"),
        shared_password=_password("STAGING_SHARED_PASSWORD"),
    )


def _get_or_create_company(db: Session, name: str, slug: str) -> Company:
    company = db.query(Company).filter_by(name=name).one_or_none()
    if company is None:
        company = Company(name=name, slug=slug, active=True)
        db.add(company)
        db.flush()
    else:
        company.active = True
        if not company.slug:
            company.slug = slug
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


def _ensure_permission_catalog(db: Session) -> dict[str, Permission]:
    existing = {p.code: p for p in db.query(Permission).all()}
    for perm in PERMISSIONS:
        if perm.code not in existing:
            new = Permission(
                code=perm.code,
                namespace=perm.namespace,
                description=perm.description,
            )
            db.add(new)
            db.flush()
            existing[perm.code] = new
    return existing


def _ensure_system_role(
    db: Session, company_id: int, name: str, description: str
) -> Role:
    role = (
        db.query(Role).filter_by(company_id=company_id, name=name).one_or_none()
    )
    if role is None:
        role = Role(
            company_id=company_id,
            name=name,
            description=description,
            is_system=True,
            active=True,
        )
        db.add(role)
        db.flush()
    else:
        role.is_system = True
        role.active = True
    return role


def _grant_all_permissions(db: Session, role: Role, perms: dict[str, Permission]) -> None:
    db.execute(
        role_permissions.delete().where(role_permissions.c.role_id == role.id)
    )
    for permission in perms.values():
        db.execute(
            role_permissions.insert().values(
                role_id=role.id, permission_id=permission.id
            )
        )


def _ensure_membership(
    db: Session,
    user_id: int,
    company_id: int,
    is_admin: bool,
    role_ids: list[int],
) -> CompanyUser:
    membership = (
        db.query(CompanyUser)
        .filter_by(user_id=user_id, company_id=company_id)
        .one_or_none()
    )
    if membership is None:
        membership = CompanyUser(
            user_id=user_id,
            company_id=company_id,
            role="ADMIN" if is_admin else "MEMBER",
            is_admin=is_admin,
            active=True,
        )
        db.add(membership)
        db.flush()
    else:
        membership.active = True
        membership.is_admin = is_admin if is_admin else membership.is_admin
        membership.role = "ADMIN" if is_admin else membership.role
    # Asignar roles explícitos.
    existing_roles = {
        row.role_id
        for row in db.query(CompanyUserRole).filter_by(company_user_id=membership.id)
    }
    for role_id in role_ids:
        if role_id in existing_roles:
            entry = (
                db.query(CompanyUserRole)
                .filter_by(company_user_id=membership.id, role_id=role_id)
                .one()
            )
            entry.active = True
        else:
            db.add(
                CompanyUserRole(
                    company_user_id=membership.id,
                    role_id=role_id,
                    active=True,
                )
            )
    return membership


def seed_staging(db: Session, credentials: SeedCredentials) -> None:
    perms = _ensure_permission_catalog(db)

    company_a = _get_or_create_company(db, "Empresa Demo A", "empresa-demo-a")
    company_b = _get_or_create_company(db, "Empresa Demo B", "empresa-demo-b")

    admin_role_a = _ensure_system_role(
        db, company_a.id, "Administrador", "Acceso completo sobre la empresa"
    )
    member_role_a = _ensure_system_role(
        db, company_a.id, "Miembro", "Acceso de miembro a la empresa"
    )
    admin_role_b = _ensure_system_role(
        db, company_b.id, "Administrador", "Acceso completo sobre la empresa"
    )
    member_role_b = _ensure_system_role(
        db, company_b.id, "Miembro", "Acceso de miembro a la empresa"
    )

    _grant_all_permissions(db, admin_role_a, perms)
    _grant_all_permissions(db, admin_role_b, perms)

    superadmin = _get_or_create_user(
        db,
        credentials.superadmin_email,
        "SuperAdmin Vogel",
        credentials.superadmin_password,
        is_superadmin=True,
    )
    admin_a = _get_or_create_user(
        db,
        credentials.admin_a_email,
        "Admin Empresa A",
        credentials.admin_a_password,
    )
    admin_b = _get_or_create_user(
        db,
        credentials.admin_b_email,
        "Admin Empresa B",
        credentials.admin_b_password,
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

    _ensure_membership(db, admin_a.id, company_a.id, is_admin=True, role_ids=[admin_role_a.id])
    _ensure_membership(db, admin_b.id, company_b.id, is_admin=True, role_ids=[admin_role_b.id])
    _ensure_membership(db, user_a.id, company_a.id, is_admin=False, role_ids=[member_role_a.id])
    _ensure_membership(db, user_b.id, company_b.id, is_admin=False, role_ids=[member_role_b.id])
    _ensure_membership(db, shared.id, company_a.id, is_admin=False, role_ids=[member_role_a.id])
    _ensure_membership(db, shared.id, company_b.id, is_admin=False, role_ids=[member_role_b.id])

    db.commit()


def main() -> None:
    credentials = load_credentials()
    with SessionLocal() as db:
        seed_staging(db, credentials)
    print("STAGING_SEED=OK")
    print("STAGING_SEED_PASSWORDS_SOURCE=environment_or_secure_generation")


if __name__ == "__main__":
    main()