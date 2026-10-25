from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Optional
from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, func, select

from backend.app.config import settings
from backend.app.db import engine, get_session, init_db
from backend.app.models import (
    Batch,
    DecisionLog,
    InventorySnapshot,
    Lane,
    Location,
    PlanLine,
    PlanRun,
    Product,
    SalesDaily,
    Settings,
    ValidationIssue,
    ForecastResult,
)
from backend.app.schemas import (
    AuditLogRead,
    SettingsRead,
    SettingsUpdate,
)
from backend.app.services.simulator import FMCGSimulator
from backend.app.settings import (
    get_current_settings,
    reset_to_default_settings,
    update_system_settings,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    init_db()
    with Session(engine) as session:
        loc_count = session.exec(select(func.count(Location.id))).one()
        if loc_count == 0:
            simulator = FMCGSimulator(session=session)
            simulator.seed_deterministic(variant="normal", seed=1, scenario="balanced")
    yield



app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="VyaparMitra: FMCG Distribution Intelligence and Inventory Optimization Engine",
    lifespan=lifespan,
)

from backend.app.routers.data import router as data_router
from backend.app.routers.forecast import router as forecast_router
from backend.app.routers.plan import router as plan_router
from backend.app.routers.evaluate import router as evaluate_router
from backend.app.routers.dashboard import router as dashboard_router

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(data_router)
app.include_router(forecast_router)
app.include_router(plan_router)
app.include_router(evaluate_router)
app.include_router(dashboard_router)


def get_current_role(x_role: str = Header(default="planner")) -> str:
    """
    Demo role validation based on X-Role header (Rule 6).
    Allowed demo roles: planner | warehouse | reviewer | system
    """
    valid_roles = {"planner", "warehouse", "reviewer", "system"}
    cleaned_role = x_role.lower().strip()
    if cleaned_role not in valid_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Invalid X-Role '{x_role}'. Allowed demo roles: {sorted(list(valid_roles))}",
        )
    return cleaned_role


# -------------------------------------------------------------------
# Health & Status Endpoints
# -------------------------------------------------------------------
@app.get("/api/v1/health", tags=["System"])
def health_check() -> dict:
    return {
        "status": "healthy",
        "app": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "is_simulated": True,
    }


@app.get("/api/v1/status", tags=["System"])
def system_status(session: Session = Depends(get_session)) -> dict:
    loc_count = session.exec(select(func.count(Location.id))).one()
    prod_count = session.exec(select(func.count(Product.id))).one()
    batch_count = session.exec(select(func.count(Batch.id))).one()
    lane_count = session.exec(select(func.count(Lane.id))).one()
    snap_count = session.exec(select(func.count(InventorySnapshot.id))).one()
    sales_count = session.exec(select(func.count(SalesDaily.id))).one()
    issues_count = session.exec(select(func.count(ValidationIssue.id))).one()

    return {
        "app_name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "database_status": "connected",
        "counts": {
            "locations": loc_count,
            "products": prod_count,
            "lanes": lane_count,
            "batches": batch_count,
            "inventory_snapshots": snap_count,
            "sales_daily": sales_count,
            "validation_issues": issues_count,
        },
        "is_simulated": True,
    }


# -------------------------------------------------------------------
# Settings Endpoints (Defaults: H=7, z=1.28, alpha=0.25, Gmax=1, Eshort=21, etc.)
# -------------------------------------------------------------------
@app.get("/api/v1/settings", response_model=SettingsRead, tags=["Settings"])
def read_settings(session: Session = Depends(get_session)) -> Settings:
    return get_current_settings(session)


@app.put("/api/v1/settings", response_model=SettingsRead, tags=["Settings"])
def update_settings(
    payload: SettingsUpdate,
    session: Session = Depends(get_session),
    role: str = Depends(get_current_role),
) -> Settings:
    return update_system_settings(session, payload, role=role)


@app.post("/api/v1/settings/reset", response_model=SettingsRead, tags=["Settings"])
def reset_settings(
    session: Session = Depends(get_session),
    role: str = Depends(get_current_role),
) -> Settings:
    return reset_to_default_settings(session, role=role)


# -------------------------------------------------------------------
# Master Data Read Endpoints
# -------------------------------------------------------------------
@app.get("/api/v1/locations", tags=["Master Data"])
def list_locations(session: Session = Depends(get_session)) -> list[Location]:
    return list(session.exec(select(Location)).all())


@app.get("/api/v1/products", tags=["Master Data"])
def list_products(session: Session = Depends(get_session)) -> list[Product]:
    return list(session.exec(select(Product)).all())


@app.get("/api/v1/lanes", tags=["Master Data"])
def list_lanes(session: Session = Depends(get_session)) -> list[Lane]:
    return list(session.exec(select(Lane)).all())


@app.get("/api/v1/batches", tags=["Master Data"])
def list_batches(session: Session = Depends(get_session)) -> list[Batch]:
    return list(session.exec(select(Batch)).all())


@app.get("/api/v1/snapshots", tags=["Inventory"])
def list_snapshots(session: Session = Depends(get_session)) -> list[InventorySnapshot]:
    return list(session.exec(select(InventorySnapshot)).all())


@app.get("/api/v1/sales", tags=["Sales"])
def list_sales(
    limit: int = 100,
    product_id: Optional[str] = None,
    location_id: Optional[str] = None,
    session: Session = Depends(get_session),
) -> list[SalesDaily]:
    stmt = select(SalesDaily)
    if product_id:
        stmt = stmt.where(SalesDaily.product_id == product_id)
    if location_id:
        stmt = stmt.where(SalesDaily.location_id == location_id)
    stmt = stmt.order_by(SalesDaily.date.desc()).limit(limit)  # type: ignore
    return list(session.exec(stmt).all())


@app.get("/api/v1/validation-issues", tags=["Validation"])
def list_validation_issues(session: Session = Depends(get_session)) -> list[ValidationIssue]:
    return list(session.exec(select(ValidationIssue)).all())


@app.get("/api/v1/audit-logs", tags=["Audit"])
def list_decision_logs(
    limit: int = 50,
    session: Session = Depends(get_session),
) -> list[DecisionLog]:
    return list(
        session.exec(
            select(DecisionLog).order_by(DecisionLog.timestamp.desc()).limit(limit)  # type: ignore
        ).all()
    )
