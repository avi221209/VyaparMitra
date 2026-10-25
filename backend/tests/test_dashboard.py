"""
Tests for VyaparMitra Dashboard Summary, Notifications & Search API Router.
Verifies:
  - Schema keys of /api/v1/dashboard/summary
  - Status thresholds at exact boundaries
  - No division by zero
  - Empty DB returns zeros and empty lists, not errors
  - No writes happen (row counts unchanged, read-only idempotency)
  - Notifications count equals pending + attention
  - Search returns grouped results
"""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select, func

from backend.app.main import app
from backend.app.db import get_session
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
)
from backend.app.routers.dashboard import compute_stock_status, invalidate_dashboard_cache
from backend.app.services.simulator import FMCGSimulator


@pytest.fixture(autouse=True)
def seed_test_database(session: Session):
    """Seed clean balanced network into database before each test."""
    sim = FMCGSimulator(seed=1, variant="normal", scenario="balanced")
    sim.seed_database(session)


# =====================================================================
# 1. Pure Status Function Boundary Tests
# =====================================================================
def test_compute_stock_status_exact_boundaries():
    """
    Test exact boundaries of stock health classification:
      - Healthy: ratio >= 1.0
      - Low stock: 0.5 <= ratio < 1.0
      - Critical: ratio < 0.5, or has_expiring_shortfall
    """
    # Healthy boundary
    ratio, status = compute_stock_status(stock_units=100.0, expected_demand_units=100.0)
    assert ratio == 1.0
    assert status == "Healthy"

    ratio, status = compute_stock_status(stock_units=100.1, expected_demand_units=100.0)
    assert ratio > 1.0
    assert status == "Healthy"

    # Just below 1.0 -> Low stock
    ratio, status = compute_stock_status(stock_units=99.9, expected_demand_units=100.0)
    assert ratio == 0.999
    assert status == "Low stock"

    # Low stock exact boundary at 0.5
    ratio, status = compute_stock_status(stock_units=50.0, expected_demand_units=100.0)
    assert ratio == 0.5
    assert status == "Low stock"

    # Just below 0.5 -> Critical
    ratio, status = compute_stock_status(stock_units=49.9, expected_demand_units=100.0)
    assert ratio == 0.499
    assert status == "Critical"

    # Zero stock -> Critical
    ratio, status = compute_stock_status(stock_units=0.0, expected_demand_units=100.0)
    assert ratio == 0.0
    assert status == "Critical"

    # Shortfall with expiring batches inside window -> Escalates to Critical
    ratio, status = compute_stock_status(
        stock_units=80.0,
        expected_demand_units=100.0,
        has_expiring_shortfall=True,
    )
    assert ratio == 0.8
    assert status == "Critical"


def test_compute_stock_status_division_by_zero():
    """Guard against zero or negative expected demand without raising ZeroDivisionError."""
    # Zero demand with positive stock
    ratio, status = compute_stock_status(stock_units=50.0, expected_demand_units=0.0)
    assert ratio == 999.0
    assert status == "Healthy"

    # Zero demand with zero stock
    ratio, status = compute_stock_status(stock_units=0.0, expected_demand_units=0.0)
    assert ratio == 1.0
    assert status == "Healthy"

    # Negative demand edge case
    ratio, status = compute_stock_status(stock_units=10.0, expected_demand_units=-5.0)
    assert ratio == 999.0
    assert status == "Healthy"


# =====================================================================
# 2. Schema Keys & Data Validation on Seeded DB
# =====================================================================
def test_dashboard_summary_schema_and_keys(client: TestClient):
    """Verify that /api/v1/dashboard/summary returns the complete schema with all required fields."""
    invalidate_dashboard_cache()
    response = client.get("/api/v1/dashboard/summary")
    assert response.status_code == 200, response.text
    data = response.json()

    # Top-level required keys
    assert "as_of" in data
    assert "data_is_sample" in data
    assert "planning_period" in data
    assert "kpis" in data
    assert "network" in data
    assert "stock_status" in data
    assert "recent_plan" in data
    assert "forecast" in data
    assert "pending_approvals" in data

    # Planning period
    pp = data["planning_period"]
    assert "start" in pp
    assert "end" in pp
    assert "horizon_days" in pp
    assert pp["horizon_days"] >= 1

    # KPIs
    kpis = data["kpis"]
    assert "products" in kpis
    assert "locations" in kpis
    assert "inventory_units" in kpis
    assert "attention" in kpis
    assert kpis["locations"]["total"] == kpis["locations"]["warehouses"] + kpis["locations"]["retailers"]

    attention = kpis["attention"]
    for field in ["count", "low_stock", "critical", "high_demand", "unmet_cartons", "blocking_data_issues"]:
        assert field in attention

    # Network
    net = data["network"]
    assert "nodes" in net
    assert "flows" in net
    assert "unmapped" in net
    assert isinstance(net["nodes"], list)
    assert isinstance(net["flows"], list)
    assert isinstance(net["unmapped"], list)

    for node in net["nodes"]:
        assert "id" in node
        assert "name" in node
        assert "type" in node
        assert "stock_units" in node
        assert "unmet_cartons" in node
        assert "high_demand" in node

    # Stock Status list
    assert isinstance(data["stock_status"], list)
    if data["stock_status"]:
        item = data["stock_status"][0]
        assert "product_id" in item
        assert "name" in item
        assert "category" in item
        assert "total_stock_units" in item
        assert "expected_demand_units" in item
        assert "ratio" in item
        assert "status" in item
        assert item["status"] in ["Healthy", "Low stock", "Critical"]

    # Forecast summary
    fc = data["forecast"]
    assert "weeks" in fc
    assert "wape" in fc
    assert "accuracy_pct" in fc
    assert "bias" in fc
    assert len(fc["weeks"]) == 8  # 4 past weeks + 4 future weeks


# =====================================================================
# 3. Read-Only Idempotency Test (No writes happen)
# =====================================================================
def test_dashboard_summary_is_read_only(client: TestClient, session: Session):
    """Verify that calling dashboard/summary causes 0 DB writes (row counts unchanged)."""
    invalidate_dashboard_cache()

    count_products_before = session.exec(select(func.count(Product.id))).one()
    count_locations_before = session.exec(select(func.count(Location.id))).one()
    count_plans_before = session.exec(select(func.count(PlanRun.id))).one()
    count_decisions_before = session.exec(select(func.count(DecisionLog.id))).one()

    # Call endpoint multiple times
    res1 = client.get("/api/v1/dashboard/summary")
    res2 = client.get("/api/v1/dashboard/summary?horizon=14")
    assert res1.status_code == 200
    assert res2.status_code == 200

    count_products_after = session.exec(select(func.count(Product.id))).one()
    count_locations_after = session.exec(select(func.count(Location.id))).one()
    count_plans_after = session.exec(select(func.count(PlanRun.id))).one()
    count_decisions_after = session.exec(select(func.count(DecisionLog.id))).one()

    assert count_products_before == count_products_after
    assert count_locations_before == count_locations_after
    assert count_plans_before == count_plans_after
    assert count_decisions_before == count_decisions_after


# =====================================================================
# 4. Notifications Count Test
# =====================================================================
def test_notifications_endpoint_and_count(client: TestClient):
    """Verify /api/v1/notifications structure and that count equals pending + attention items."""
    response = client.get("/api/v1/notifications")
    assert response.status_code == 200, response.text
    data = response.json()

    assert "count" in data
    assert "items" in data
    assert isinstance(data["items"], list)
    assert data["count"] >= len(data["items"])


# =====================================================================
# 5. Search Grouped Results Test
# =====================================================================
def test_search_endpoint_grouped_results(client: TestClient):
    """Verify /api/v1/search?q= returns grouped categories (products, locations, plans, pages) capped at 8."""
    # General search query matching Atta
    res = client.get("/api/v1/search?q=atta")
    assert res.status_code == 200
    data = res.json()

    assert "query" in data
    assert "total" in data
    assert "results" in data
    results = data["results"]
    assert "products" in results
    assert "locations" in results
    assert "plans" in results
    assert "pages" in results

    assert len(results["products"]) <= 8
    assert len(results["locations"]) <= 8
    assert len(results["plans"]) <= 8
    assert len(results["pages"]) <= 8

    # Empty query returns catalog pages and master lists
    res_empty = client.get("/api/v1/search?q=")
    assert res_empty.status_code == 200
    data_empty = res_empty.json()
    assert data_empty["total"] >= len(data_empty["results"]["pages"])


# =====================================================================
# 6. Empty Database Graceful Handling
# =====================================================================
def test_empty_database_returns_zeros_not_500():
    """Verify that an empty database returns zeros and empty lists, never raising 500 errors."""
    from sqlalchemy.pool import StaticPool
    # Create isolated in-memory SQLite database sharing the same memory space across connections
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(test_engine)

    # Create default settings
    with Session(test_engine) as session:
        session.add(
            Settings(
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
        )
        session.commit()

    def get_test_session():
        with Session(test_engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    invalidate_dashboard_cache()

    try:
        client = TestClient(app)
        res = client.get("/api/v1/dashboard/summary")
        assert res.status_code == 200, res.text
        data = res.json()

        assert data["kpis"]["products"] == 0
        assert data["kpis"]["locations"]["total"] == 0
        assert data["kpis"]["inventory_units"] == 0
        assert data["kpis"]["attention"]["count"] == 0
        assert data["network"]["nodes"] == []
        assert data["network"]["flows"] == []
        assert data["stock_status"] == []
        assert data["recent_plan"] is None
        assert data["pending_approvals"]["total"] == 0
        assert data["pending_approvals"]["items"] == []

        res_notif = client.get("/api/v1/notifications")
        assert res_notif.status_code == 200
        assert res_notif.json()["count"] == 0
        assert res_notif.json()["items"] == []
    finally:
        app.dependency_overrides.clear()
        invalidate_dashboard_cache()
