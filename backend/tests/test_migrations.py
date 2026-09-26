from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_alembic_upgrade_head_creates_foundation():
    database_path = Path(__file__).with_name("migration-test.sqlite3")
    if database_path.exists():
        database_path.unlink()
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).parents[1] / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")

    engine = None
    try:
        command.upgrade(config, "head")

        engine = create_engine(f"sqlite:///{database_path}")
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert {
            "companies",
            "users",
            "company_users",
            "roles",
            "permissions",
            "role_permissions",
            "company_user_roles",
            "alembic_version",
            "customers",
            "equipment",
            "equipment_categories",
        "work_orders",
        "work_order_events",
        "work_order_evidence",
        "work_order_counters",
        "work_order_statuses",
        "company_parameters",
        "parameter_definitions",
        } <= tables
        assert {constraint["name"] for constraint in inspector.get_unique_constraints("companies")} == {
            "uq_companies_name"
        }
        assert {constraint["name"] for constraint in inspector.get_unique_constraints("company_users")} == {
            "uq_company_user"
        }
        assert {constraint["name"] for constraint in inspector.get_unique_constraints("roles")} == {
            "uq_roles_company_name"
        }
        assert {constraint["name"] for constraint in inspector.get_unique_constraints("permissions")} == {
            "uq_permissions_code"
        }
        assert {index["name"] for index in inspector.get_indexes("company_users")} == {
            "ix_company_users_company_id",
            "ix_company_users_user_id",
        }
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                == "20260926_0008"
            )
    finally:
        if engine is not None:
            engine.dispose()
        database_path.unlink(missing_ok=True)