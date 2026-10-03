from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

HEAD_REVISION = "20261003_0020"
REVISION_BEFORE_EQUIPMENT_CATEGORIES = "20260925_0003"
REVISION_EQUIPMENT_CATEGORIES = "20260925_0004"
REVISION_BEFORE_ADMIN_BACKFILL = "20261003_0019"


def _alembic_config(database_path: Path) -> Config:
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).parents[1] / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    return config


def _schema_signature(database_path: Path) -> dict:
    """Estructura de la base, para comparar una recuperación contra un upgrade limpio."""
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        inspector = inspect(engine)
        signature = {}
        for table in sorted(inspector.get_table_names()):
            if table == "alembic_version":
                continue
            signature[table] = {
                "columns": sorted(column["name"] for column in inspector.get_columns(table)),
                "indexes": sorted(index["name"] for index in inspector.get_indexes(table)),
                "foreign_keys": sorted(
                    f"{fk['constrained_columns']}->{fk['referred_table']}.{fk['referred_columns']}"
                    for fk in inspector.get_foreign_keys(table)
                ),
                "unique_constraints": sorted(
                    uc["name"] or "" for uc in inspector.get_unique_constraints(table)
                ),
            }
        return signature
    finally:
        engine.dispose()


def _assert_schema_matches_clean_upgrade(monkeypatch, tmp_path, database_path):
    """Una base recuperada de un deploy parcial debe quedar igual que una migrada de cero."""
    reference_path = tmp_path / "clean-reference.sqlite3"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{reference_path}")
    command.upgrade(_alembic_config(reference_path), "head")
    assert _schema_signature(database_path) == _schema_signature(reference_path)


def _seed_legacy_equipment(database_path: Path) -> None:
    """Empresa, cliente y dos equipos con la columna legacy `category` (estado previo a 0004)."""
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO companies (id, name) VALUES (1, 'Vogel')"))
            connection.execute(
                text("INSERT INTO customers (id, company_id, name) VALUES (1, 1, 'Cliente Uno')")
            )
            connection.execute(
                text(
                    "INSERT INTO equipment (id, company_id, customer_id, category) VALUES"
                    " (1, 1, 1, 'Bomba'), (2, 1, 1, 'Compresor')"
                )
            )
    finally:
        engine.dispose()


def _unstamp_revision(database_path: Path, revision: str) -> None:
    """Simula un deploy que aplicó el DDL pero no llegó a registrar la revisión."""
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE alembic_version SET version_num = :revision"), {"revision": revision}
            )
    finally:
        engine.dispose()


def _seed_admin_con_permisos_de_0003_y_0005(database_path: Path) -> None:
    """Una empresa con su Administrador en el estado en que lo dejaron esas migraciones.

    Es el estado real de producción: el rol existe, tiene los seis permisos que 0003 y 0005
    le dieron a los Administradores de ese momento, y no tiene los del núcleo. Nadie
    lo completó después, porque al arrancar no se completa nada.
    """
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO companies (id, name) VALUES (1, 'Traid Walter')"))
            connection.execute(
                text(
                    "INSERT INTO roles (id, company_id, name, is_system, active)"
                    " VALUES (1, 1, 'Administrador', 0, 1)"
                )
            )
            for code in (
                "customers.view",
                "customers.manage",
                "equipment.view",
                "equipment.manage",
                "work_orders.view",
                "work_orders.manage",
            ):
                pid = connection.execute(
                    text("SELECT id FROM permissions WHERE code = :code"), {"code": code}
                ).scalar()
                connection.execute(
                    text("INSERT INTO role_permissions (role_id, permission_id) VALUES (1, :pid)"),
                    {"pid": pid},
                )
    finally:
        engine.dispose()


def test_alembic_upgrade_head_creates_foundation(monkeypatch):
    database_path = Path(__file__).with_name("migration-test.sqlite3")
    if database_path.exists():
        database_path.unlink()
    # env.py prioriza DATABASE_URL sobre sqlalchemy.url: sin esto el test correría
    # migraciones contra la base real de quien tenga esa variable seteada.
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    config = _alembic_config(database_path)

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
        "work_order_execution_items",
        "work_order_final_tests",
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
                == HEAD_REVISION
            )
    finally:
        if engine is not None:
            engine.dispose()
        database_path.unlink(missing_ok=True)


def test_migration_0004_resumes_when_revision_was_not_stamped(monkeypatch, tmp_path):
    """Issue #35: la 0004 quedó aplicada pero Alembic no la registró.

    Eso dejaba `equipment_categories` creada y, en cada arranque, la migración volvía a
    ejecutar CREATE TABLE y el backend moría con MySQL 1050. El reintento tiene que
    completar sin perder datos ni duplicar categorías.
    """
    database_path = tmp_path / "partial-deploy.sqlite3"

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    config = _alembic_config(database_path)
    command.upgrade(config, REVISION_BEFORE_EQUIPMENT_CATEGORIES)
    _seed_legacy_equipment(database_path)

    # Primer arranque: crea la tabla y migra las categorías legacy.
    command.upgrade(config, REVISION_EQUIPMENT_CATEGORIES)
    _unstamp_revision(database_path, REVISION_BEFORE_EQUIPMENT_CATEGORIES)

    # Reintento: antes de las guardas por paso esto re-ejecutaba CREATE TABLE y fallaba.
    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path}")
    try:
        inspector = inspect(engine)
        assert "equipment_categories" in set(inspector.get_table_names())
        columns = {column["name"] for column in inspector.get_columns("equipment")}
        assert "category_id" in columns
        assert "category" not in columns
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT name FROM equipment_categories ORDER BY name")
            ).scalars().all() == ["Bomba", "Compresor"]
            assert connection.execute(text("SELECT COUNT(*) FROM equipment")).scalar_one() == 2
            assert connection.execute(
                text("SELECT COUNT(*) FROM equipment WHERE category_id IS NOT NULL")
            ).scalar_one() == 2
            assert connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one() == HEAD_REVISION
    finally:
        engine.dispose()

    _assert_schema_matches_clean_upgrade(monkeypatch, tmp_path, database_path)


def test_migrations_insert_every_permission_in_the_code_catalog(monkeypatch, tmp_path):
    """Todo permiso del catalogo de codigo tiene que existir despues de migrar.

    Este es el test que faltaba. Los fixtures de `conftest.py` arman los permisos desde
    `app/core/permissions.py`, no desde las migraciones, asi que un permiso agregado al
    catalogo y olvidado en la migracion pasaba los 137 tests y en un ambiente desplegado
    daba 403 en todos los endpoints que lo exigen. Paso con `ai.use`: la 0018 creo la tabla
    de uso y los parametros, pero no inserto el permiso.
    """
    from app.core.permissions import permission_codes

    database_path = tmp_path / "catalogo-vs-migraciones.sqlite3"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    command.upgrade(_alembic_config(database_path), "head")

    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.connect() as connection:
            en_la_base = set(
                connection.execute(text("SELECT code FROM permissions")).scalars().all()
            )
    finally:
        engine.dispose()

    faltan = sorted(set(permission_codes()) - en_la_base)
    assert not faltan, (
        "estos permisos del catalogo de codigo no los inserta ninguna migracion, "
        f"asi que require_permission() devuelve 403 en un ambiente real: {faltan}"
    )


def test_migration_0020_completa_los_permisos_del_administrador_incompleto(
    monkeypatch, tmp_path
):
    """Un Administrador de empresa no puede quedar con la mitad de los permisos.

    Este test arma el estado que se encontró en producción: un Administrador con los permisos
    que las migraciones 0003 y 0005 le dieron en su momento, y sin los del núcleo. En
    `Traid Walter` eso son 7 permisos de 18, o sea que el administrador de la empresa no
    puede administrar usuarios ni ver roles.

    Lo que fija la migración 0020 es que el Administrador de empresa termine con **todo** el
    catálogo, que es lo que `_grant_all_company_permissions` ya le da al Administrador de
    cada empresa nueva. Si este test falla, o el backfill no corrió, o a algún rol le
    faltaron permisos.
    """
    from app.core.permissions import permission_codes

    database_path = tmp_path / "admin-a-medias.sqlite3"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    config = _alembic_config(database_path)

    # Estado previo a la 0020, con el Administrador como lo dejó la historia.
    command.upgrade(config, REVISION_BEFORE_ADMIN_BACKFILL)
    _seed_admin_con_permisos_de_0003_y_0005(database_path)

    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.connect() as connection:
            antes = sorted(
                r[0]
                for r in connection.execute(
                    text(
                        "SELECT p.code from role_permissions rp"
                        " join permissions p on p.id = rp.permission_id"
                        " where rp.role_id = 1"
                    )
                ).fetchall()
            )
    finally:
        engine.dispose()
    assert "users.manage" not in antes, "el seed deberia reproducir el rol incompleto"
    assert "users.create" not in antes, "el seed deberia reproducir el rol incompleto"

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.connect() as connection:
            despues = sorted(
                r[0]
                for r in connection.execute(
                    text(
                        "SELECT p.code from role_permissions rp"
                        " join permissions p on p.id = rp.permission_id"
                        " where rp.role_id = 1"
                    )
                ).fetchall()
            )
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
    finally:
        engine.dispose()

    # Primero los permisos, que es lo que importa: si la 0020 no corrio, este assert tiene que
    # ser el que falla y decir que permisos faltan, no el de la revision de abajo.
    faltan = sorted(set(permission_codes()) - set(despues))
    assert not faltan, (
        "el Administrador de empresa quedo sin estos permisos del catalogo, o sea que el "
        f"admin de la empresa no puede usarlos: {faltan}"
    )
    assert revision == HEAD_REVISION


def test_migration_0004_does_not_duplicate_categories_when_column_survives(monkeypatch, tmp_path):
    """El otro corte posible: la tabla y `category_id` ya existen pero el texto legacy
    `category` sigue en `equipment`. Al reintentar, el backfill no debe duplicar categorías
    ni perder el vínculo equipo->categoría.
    """
    database_path = tmp_path / "partial-column.sqlite3"

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    config = _alembic_config(database_path)
    command.upgrade(config, REVISION_BEFORE_EQUIPMENT_CATEGORIES)
    _seed_legacy_equipment(database_path)
    command.upgrade(config, REVISION_EQUIPMENT_CATEGORIES)

    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE equipment ADD COLUMN category VARCHAR(80)"))
            connection.execute(
                text(
                    "UPDATE equipment SET category = ("
                    "SELECT ec.name FROM equipment_categories ec WHERE ec.id = equipment.category_id)"
                )
            )
    finally:
        engine.dispose()
    _unstamp_revision(database_path, REVISION_BEFORE_EQUIPMENT_CATEGORIES)

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path}")
    try:
        inspector = inspect(engine)
        columns = {column["name"] for column in inspector.get_columns("equipment")}
        assert "category" not in columns
        assert "category_id" in columns
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT name, COUNT(*) FROM equipment_categories GROUP BY name ORDER BY name")
            ).all() == [("Bomba", 1), ("Compresor", 1)]
            assert connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one() == HEAD_REVISION
    finally:
        engine.dispose()

    _assert_schema_matches_clean_upgrade(monkeypatch, tmp_path, database_path)