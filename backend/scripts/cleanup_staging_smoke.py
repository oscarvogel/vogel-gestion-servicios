"""Limpieza segura de residuos de smoke tests en STAGING.

Sólo elimina empresas inequívocamente creadas por smoke tests (nombre/slug
con prefijo Smoke) y usuarios de prueba que quedan sin ninguna membresía.
No toca Empresa Demo A/B ni datos de producción.

Uso explícito:
    STAGING_CLEANUP_CONFIRM=YES python backend/scripts/cleanup_staging_smoke.py
"""

import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal
from app.models.company import Company
from app.models.role import CompanyUserRole, Role, role_permissions
from app.models.user import CompanyUser, User


def cleanup_staging_smoke(db) -> tuple[int, int]:
    companies = (
        db.query(Company)
        .filter(
            (Company.name.ilike("Smoke %"))
            | (Company.name.ilike("Smoke-%"))
            | (Company.slug.ilike("smoke-%"))
            | (Company.slug.ilike("smoke_%"))
        )
        .all()
    )
    company_ids = [company.id for company in companies]

    if company_ids:
        memberships = db.query(CompanyUser).filter(CompanyUser.company_id.in_(company_ids)).all()
        membership_ids = [membership.id for membership in memberships]
        if membership_ids:
            db.query(CompanyUserRole).filter(
                CompanyUserRole.company_user_id.in_(membership_ids)
            ).delete(synchronize_session=False)
        db.query(CompanyUser).filter(CompanyUser.company_id.in_(company_ids)).delete(
            synchronize_session=False
        )

        roles = db.query(Role).filter(Role.company_id.in_(company_ids)).all()
        role_ids = [role.id for role in roles]
        if role_ids:
            db.execute(role_permissions.delete().where(role_permissions.c.role_id.in_(role_ids)))
        db.query(Role).filter(Role.company_id.in_(company_ids)).delete(synchronize_session=False)
        db.query(Company).filter(Company.id.in_(company_ids)).delete(synchronize_session=False)

    orphan_smoke_users = (
        db.query(User)
        .outerjoin(CompanyUser, CompanyUser.user_id == User.id)
        .filter(
            CompanyUser.id.is_(None),
            User.is_superadmin.is_(False),
            (
                User.email.ilike("smoke-%")
                | User.email.ilike("smoke_%")
                | User.email.ilike("%@smoke.example.com")
                | User.email.ilike("%@smoke.local")
            ),
        )
        .all()
    )
    orphan_ids = [user.id for user in orphan_smoke_users]
    if orphan_ids:
        db.query(User).filter(User.id.in_(orphan_ids)).delete(synchronize_session=False)

    db.commit()
    return len(company_ids), len(orphan_ids)


def main() -> None:
    if os.getenv("STAGING_CLEANUP_CONFIRM") != "YES":
        raise SystemExit("CLEANUP_ABORTED: set STAGING_CLEANUP_CONFIRM=YES")
    environment = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "staging")).lower()
    if environment in {"production", "prod"}:
        raise SystemExit("CLEANUP_ABORTED: production is forbidden")

    with SessionLocal() as db:
        companies, users = cleanup_staging_smoke(db)
    print(f"STAGING_SMOKE_COMPANIES_REMOVED={companies}")
    print(f"STAGING_SMOKE_ORPHAN_USERS_REMOVED={users}")


if __name__ == "__main__":
    main()
