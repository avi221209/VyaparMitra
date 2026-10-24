import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from backend.app.main import app
from backend.app.models import DecisionLog, PlanLine, PlanRun


@pytest.fixture
def client():
    return TestClient(app)


def test_load_backup_demo_state(client):
    """Verify POST /api/demo/backup loads backup_demo_plan.json without running solver."""
    response = client.post("/api/demo/backup", headers={"X-Role": "planner"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert "message" in data
    assert "run_id" in data
    assert data["run_id"] == "PLAN-20261024-1792880580"
    assert len(data["plan"]["lines"]) > 0

    # Verify latest plan returns this backup run
    latest_res = client.get("/api/plan/latest")
    assert latest_res.status_code == 200
    latest_data = latest_res.json()
    assert latest_data["run_id"] == "PLAN-20261024-1792880580"
    assert latest_data["totals"]["transport_cost"] > 0

    # Verify audit log recorded the restore
    audit_res = client.get("/api/audit")
    assert audit_res.status_code == 200
    logs = audit_res.json()
    assert any(l["action"] == "RESTORE_BACKUP" for l in logs)


def test_force_heuristic_fallback(client):
    """Verify POST /api/plan?force_heuristic=true triggers heuristic fallback."""
    response = client.post("/api/plan?force_heuristic=true", headers={"X-Role": "planner"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "HEURISTIC"
    assert data["solver_status"] == "FALLBACK_HEURISTIC"

    # Verify GET /api/plan/latest also exposes solver_status
    latest_res = client.get("/api/plan/latest")
    assert latest_res.status_code == 200
    latest_data = latest_res.json()
    assert latest_data["status"] == "HEURISTIC"
    assert latest_data["solver_status"] == "FALLBACK_HEURISTIC"
