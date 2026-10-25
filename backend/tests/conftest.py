import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from backend.app.db import get_session, init_db
from backend.app.main import app
from backend.app.models import SettingsModel


@pytest.fixture(scope="session", autouse=True)
def initialize_database_schema():
    """Ensure database schema is created on disk even if lifespan did not trigger."""
    init_db()


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        # Seed default settings
        default_settings = SettingsModel(
            id=1,
            H=7,
            z=1.28,
            alpha=0.25,
            Gmax=1,
            Eshort=21,
            shrinkage=0.5,
            planner_reserve=0,
            epsilon=0.001,
            solver_time_limit=10.0,
        )
        session.add(default_settings)
        session.commit()
        yield session


@pytest.fixture(name="client")
def client_fixture(session: Session):
    def get_session_override():
        return session

    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()
