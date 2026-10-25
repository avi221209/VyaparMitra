from typing import Generator
from sqlmodel import Session, SQLModel, create_engine, select
from backend.app.config import settings
from backend.app.models import SettingsModel

connect_args = {"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
engine = create_engine(settings.DATABASE_URL, echo=False, connect_args=connect_args)


def init_db() -> None:
    """Initialize database tables and ensure default settings exist."""
    SQLModel.metadata.create_all(engine)

    # Lightweight SQLite schema migration for newly added fields
    if "sqlite" in settings.DATABASE_URL:
        with engine.connect() as conn:
            tables = [t[0] for t in conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            if "validation_issue" in tables:
                cols = [c[1] for c in conn.exec_driver_sql("PRAGMA table_info(validation_issue)").fetchall()]
                if "fix_first" not in cols:
                    conn.exec_driver_sql("ALTER TABLE validation_issue ADD COLUMN fix_first BOOLEAN DEFAULT 0")
                if "created_at" not in cols:
                    conn.exec_driver_sql("ALTER TABLE validation_issue ADD COLUMN created_at TIMESTAMP")
                conn.commit()
            if "plan_run" in tables:
                cols = [c[1] for c in conn.exec_driver_sql("PRAGMA table_info(plan_run)").fetchall()]
                if "total_unmet_safety_stock_cartons" not in cols:
                    conn.exec_driver_sql("ALTER TABLE plan_run ADD COLUMN total_unmet_safety_stock_cartons INTEGER DEFAULT 0")
                if "counterfactuals_json" not in cols:
                    conn.exec_driver_sql("ALTER TABLE plan_run ADD COLUMN counterfactuals_json TEXT")
                conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_plan_run_created_at ON plan_run(created_at)")
                conn.commit()
            if "sales_daily" in tables:
                conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_sales_daily_composite ON sales_daily(date, product_id, location_id)")
                conn.commit()

    with Session(engine) as session:
        existing_settings = session.exec(select(SettingsModel).where(SettingsModel.id == 1)).first()
        if not existing_settings:
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


def get_session() -> Generator[Session, None, None]:
    """Dependency injection helper for FastAPI endpoints."""
    with Session(engine) as session:
        yield session
