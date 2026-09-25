import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.permissions import PERMISSIONS
from app.main import app
from app.api.dependencies import get_db
from app.db.base import Base
from app.models.role import Permission


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    # Pre-poblar permisos para que los tests no tengan que hacerlo.
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = session_factory()
    try:
        for perm in PERMISSIONS:
            db.add(
                Permission(
                    code=perm.code,
                    namespace=perm.namespace,
                    description=perm.description,
                )
            )
        db.commit()
        yield db
    finally:
        db.close()
        engine.dispose()


@pytest.fixture
def client(db_session: Session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()