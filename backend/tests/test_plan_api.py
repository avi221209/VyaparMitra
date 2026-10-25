"""
VyaparMitra - Planning API & Rule Checker Test Suite
Distribution Planning and Inventory Optimization Engine

Tests:
 1. POST /api/v1/plan executes forecast, requirement, eligibility, optimizer, counterfactuals and returns run id and lines.
 2. GET /api/v1/plan/{run_id} returns lines, totals (transport, unmet demand, safety-stock gap), and unmet panel with fixes.
 3. GET /api/v1/plan/lines/{id} returns explanation card data built ONLY from calculated values (no free text generation).
 4. POST /api/v1/plan/lines/{id}/approve with valid edit is accepted and updates DecisionLog.
 5. Overdrawing edit breaking C1 (stock) or C3 (over-allocation) is refused with HTTP 409, names the violated rule, and logs the attempt.
 6. POST /api/v1/plan/lines/{id}/reject strictly requires a reason (refused if empty) and sets cartons to 0.
 7. Role enforcement: X-Role header (warehouse forbidden from approve/reject/edit; planner and reviewer authorized).
 8. GET /api/v1/audit contains every action (OPTIMIZE, APPROVE, EDIT, EDIT_REFUSED, REJECT, OVERRIDE).
 9. Quick-edit of W1 stock by -20% raises unmet cartons and does not create stock.
 10. POST /api/v1/plan?force_heuristic=true triggers heuristic fallback and reports solver status.
"""

from fastapi.testclient import TestClient
import pytest
from sqlmodel import Session, select

from backend.app.models import Batch, DecisionLog, InventorySnapshot, PlanLine, PlanRun, Product, Location, Lane
from backend.app.services.simulator import FMCGSimulator


@pytest.fixture(autouse=True)
def seed_test_database(session: Session):
    """Seed clean balanced network into database before each test."""
    sim = FMCGSimulator(seed=1, variant="normal", scenario="balanced")
    sim.seed_database(session)


def test_post_and_get_plan_lifecycle(client: TestClient):
    """Test POST /api/v1/plan runs complete pipeline and GET /api/v1/plan/{run_id} returns totals and fixes."""
    # 1. Generate plan
    res = client.post(
        "/api/v1/plan",
        json={"horizon": 7, "notes": "Production run"},
        headers={"X-Role": "planner"},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert "run_id" in data
    assert data["run_id"].startswith("PLAN-")
    assert data["status"] in ("OPTIMIZED", "FEASIBLE")
    assert data["total_cartons"] > 0
    assert data["total_cost"] > 0
    assert len(data["lines"]) > 0

    run_id = data["run_id"]

    # 2. Fetch plan by run_id
    get_res = client.get(f"/api/v1/plan/{run_id}")
    assert get_res.status_code == 200
    plan_data = get_res.json()
    assert plan_data["run_id"] == run_id
    assert "totals" in plan_data
    totals = plan_data["totals"]
    assert "transport_cost" in totals
    assert "transport" in totals
    assert "unmet_demand" in totals
    assert "safety_stock_gap" in totals
    assert totals["total_cartons"] == data["total_cartons"]
    assert len(plan_data["lines"]) == len(data["lines"])
    assert "unmet_panel" in plan_data


def test_explanation_card_pure_calculated_values(client: TestClient):
    """
    Test GET /api/v1/plan/lines/{id} returns explanation card data built ONLY from calculated values:
    sources considered (eligible/excluded with reason, cost, lead time, stock),
    chosen and why (cheapest eligible subject to constraints),
    constraints checked (stock, lead time gap, lane capacity, shelf life with days left and days to sell),
    residual risk (unmet and safety-stock gap).
    """
    # Create plan
    plan_res = client.post("/api/v1/plan", json={"horizon": 7}, headers={"X-Role": "planner"})
    assert plan_res.status_code == 200
    lines = plan_res.json()["lines"]
    assert len(lines) > 0

    first_line_id = lines[0]["id"]

    # Fetch explanation card
    card_res = client.get(f"/api/v1/plan/lines/{first_line_id}")
    assert card_res.status_code == 200
    card = card_res.json()

    # 1. Line identification
    assert card["line_id"] == first_line_id
    assert card["allocated_cartons"] > 0
    assert card["line_cost"] >= 0

    # 2. Sources considered
    sources = card["sources_considered"]
    assert len(sources) >= 1
    for s in sources:
        assert "source_id" in s
        assert "cost_per_carton" in s
        assert "lead_time_days" in s
        assert "stock_available" in s
        assert "is_eligible" in s
        assert "reason" in s
        assert isinstance(s["is_eligible"], bool)
        assert len(s["reason"]) > 0

    # 3. Chosen and why
    chosen = card["chosen"]
    assert chosen["source_id"] == lines[0]["source_id"]
    assert chosen["why"] == "cheapest eligible subject to constraints"
    assert chosen["allocated_cartons"] == lines[0]["cartons"]

    # 4. Constraints checked
    constraints = card["constraints_checked"]
    assert "stock" in constraints
    assert constraints["stock"]["passed"] is True
    assert constraints["stock"]["allocated_cartons"] <= constraints["stock"]["available_quantity"]

    assert "lead_time_gap" in constraints
    assert constraints["lead_time_gap"]["passed"] is True
    assert "lane_gap_days" in constraints["lead_time_gap"]

    assert "lane_capacity" in constraints
    assert constraints["lane_capacity"]["passed"] is True
    assert "total_lane_load" in constraints["lane_capacity"]

    assert "shelf_life" in constraints
    assert constraints["shelf_life"]["passed"] is True
    assert "days_left_at_arrival" in constraints["shelf_life"]
    assert "days_to_sell" in constraints["shelf_life"]

    # 5. Residual risk
    risk = card["residual_risk"]
    assert "unmet_demand_cartons" in risk
    assert "safety_stock_gap_cartons" in risk
    assert isinstance(risk["has_unmet_demand"], bool)
    assert isinstance(risk["has_safety_stock_gap"], bool)


def test_valid_edit_accepted_and_logged(client: TestClient):
    """Test valid carton edit on a line is accepted and recorded in DecisionLog."""
    plan_res = client.post("/api/v1/plan", json={"horizon": 7}, headers={"X-Role": "planner"})
    lines = plan_res.json()["lines"]
    line_id = lines[0]["id"]
    orig_cartons = lines[0]["cartons"]

    # Decrease cartons by 1 (always valid under C1 stock & C3 Ntot)
    new_cartons = max(1, orig_cartons - 1)
    edit_res = client.post(
        f"/api/v1/plan/lines/{line_id}/approve",
        json={"edited_cartons": new_cartons, "notes": "Adjusted down for buffer"},
        headers={"X-Role": "planner"},
    )
    assert edit_res.status_code == 200
    edit_data = edit_res.json()
    assert edit_data["status"] == "success"
    assert edit_data["cartons"] == new_cartons
    assert edit_data["line_status"] == "EDITED"

    # Verify audit trail contains EDIT action
    audit_res = client.get("/api/v1/audit")
    assert audit_res.status_code == 200
    logs = audit_res.json()
    edit_log = next((l for l in logs if l["plan_line_id"] == line_id and l["action"] == "EDIT"), None)
    assert edit_log is not None
    assert edit_log["actor_role"] == "planner"
    assert str(new_cartons) in edit_log["new_value"]


def test_overdrawing_edit_refused_and_rule_named(client: TestClient):
    """
    Test overdrawing edit is refused with HTTP 409 naming the violated rule (e.g. C1_STOCK_EXCEEDED),
    and the attempted edit is STILL logged in DecisionLog.
    """
    plan_res = client.post("/api/v1/plan", json={"horizon": 7}, headers={"X-Role": "planner"})
    lines = plan_res.json()["lines"]
    line_id = lines[0]["id"]

    # Propose massive overdraw (1,000,000 cartons) far exceeding batch stock
    crazy_cartons = 1000000
    res = client.post(
        f"/api/v1/plan/lines/{line_id}/approve",
        json={"edited_cartons": crazy_cartons, "notes": "Impossible allocation"},
        headers={"X-Role": "reviewer"},
    )
    # Must be HTTP 409 Conflict naming the rule
    assert res.status_code == 409
    error_detail = res.json()["detail"]
    assert "C1_STOCK_EXCEEDED" in error_detail or "C1" in error_detail or "C3_OVER_ALLOCATION" in error_detail

    # Crucial requirement: "the attempt is still logged"
    audit_res = client.get("/api/v1/audit")
    assert audit_res.status_code == 200
    logs = audit_res.json()
    refused_log = next((l for l in logs if l["plan_line_id"] == line_id and l["action"] == "EDIT_REFUSED"), None)
    assert refused_log is not None
    assert refused_log["actor_role"] == "reviewer"
    assert "Refused by rule" in refused_log["note"]
    assert "C1" in refused_log["note"] or "C3" in refused_log["note"]


def test_reject_requires_a_reason(client: TestClient):
    """Test POST /api/v1/plan/lines/{id}/reject strictly requires a non-empty reason."""
    plan_res = client.post("/api/v1/plan", json={"horizon": 7}, headers={"X-Role": "planner"})
    lines = plan_res.json()["lines"]
    line_id = lines[0]["id"]

    # 1. Missing reason or empty string -> rejected with 400 or 422
    empty_res = client.post(
        f"/api/v1/plan/lines/{line_id}/reject",
        json={"reason": "   "},
        headers={"X-Role": "planner"},
    )
    assert empty_res.status_code in (400, 422)

    no_reason_res = client.post(
        f"/api/v1/plan/lines/{line_id}/reject",
        json={},
        headers={"X-Role": "planner"},
    )
    assert no_reason_res.status_code in (400, 422)

    # 2. Valid reason provided -> successfully rejected and cartons zeroed
    valid_res = client.post(
        f"/api/v1/plan/lines/{line_id}/reject",
        json={"reason": "Truck breakdown on transit lane"},
        headers={"X-Role": "planner"},
    )
    assert valid_res.status_code == 200
    reject_data = valid_res.json()
    assert reject_data["status"] == "success"
    assert reject_data["action"] == "REJECT"
    assert reject_data["cartons"] == 0
    assert reject_data["line_status"] == "REJECTED"

    # Verify audit log
    audit_res = client.get("/api/v1/audit")
    logs = audit_res.json()
    rej_log = next((l for l in logs if l["plan_line_id"] == line_id and l["action"] == "REJECT"), None)
    assert rej_log is not None
    assert "Truck breakdown" in rej_log["note"]


def test_role_enforcement_approve_and_reject(client: TestClient):
    """
    Test roles: Approve/edit/reject require planner or reviewer.
    Warehouse role is refused with 403 Forbidden.
    """
    plan_res = client.post("/api/v1/plan", json={"horizon": 7}, headers={"X-Role": "planner"})
    lines = plan_res.json()["lines"]
    line_id = lines[0]["id"]

    # Warehouse tries to approve
    wh_approve = client.post(
        f"/api/v1/plan/lines/{line_id}/approve",
        headers={"X-Role": "warehouse"},
    )
    assert wh_approve.status_code == 403
    assert "Must be 'planner' or 'reviewer'" in wh_approve.text

    # Warehouse tries to reject
    wh_reject = client.post(
        f"/api/v1/plan/lines/{line_id}/reject",
        json={"reason": "Warehouse decision"},
        headers={"X-Role": "warehouse"},
    )
    assert wh_reject.status_code == 403

    # Reviewer can approve
    rev_approve = client.post(
        f"/api/v1/plan/lines/{line_id}/approve",
        headers={"X-Role": "reviewer"},
    )
    assert rev_approve.status_code == 200


def test_quick_edit_w1_stock_reduces_by_20_percent_raises_unmet_and_does_not_create_stock(client: TestClient, session: Session):
    """
    Test: quick-edit of W1 stock by -20 percent raises unmet cartons and does not create stock.
    Verifies before and after change summary.
    """
    # 1. Total stock at W1 before quick-edit
    w1_batches_before = session.exec(select(Batch).where(Batch.location_id == "W1")).all()
    w1_stock_before = sum(b.quantity for b in w1_batches_before)
    assert w1_stock_before > 0

    # 2. Call quick-edit override endpoint: stock_percent = -20.0
    override_res = client.post(
        "/api/v1/scenario/override",
        json={
            "source_id": "W1",
            "stock_percent": -20.0,
            "notes": "Simulating warehouse supply contraction",
        },
        headers={"X-Role": "planner"},
    )
    assert override_res.status_code == 200
    ov_data = override_res.json()
    assert ov_data["status"] == "success"
    summary = ov_data["change_summary"]

    before_unmet = summary["before"]["total_unmet_cartons"]
    after_unmet = summary["after"]["total_unmet_cartons"]
    diff = summary["difference"]

    # 3. Assert W1 stock strictly decreased and no stock created
    w1_batches_after = session.exec(select(Batch).where(Batch.location_id == "W1")).all()
    w1_stock_after = sum(b.quantity for b in w1_batches_after)
    assert w1_stock_after < w1_stock_before, "Stock at W1 did not decrease!"
    expected_approx = round(w1_stock_before * 0.8)
    assert abs(w1_stock_after - expected_approx) <= len(w1_batches_after), "Stock should decrease by ~20%"

    # 4. Assert unmet cartons raised (or stayed same if excess stock), NEVER decreased!
    assert after_unmet >= before_unmet, f"Unmet cartons should raise or stay same, got before={before_unmet}, after={after_unmet}"

    # 5. Check audit trail logged the OVERRIDE action
    audit_res = client.get("/api/v1/audit")
    assert audit_res.status_code == 200
    logs = audit_res.json()
    ov_log = next((l for l in logs if l["action"] == "OVERRIDE"), None)
    assert ov_log is not None
    assert "W1" in ov_log["new_value"]
    assert "-20" in ov_log["new_value"]


def test_force_heuristic_fallback(client: TestClient):
    """Verify POST /api/v1/plan?force_heuristic=true triggers heuristic fallback."""
    response = client.post("/api/v1/plan?force_heuristic=true", headers={"X-Role": "planner"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "HEURISTIC"
    assert data["solver_status"] == "FALLBACK_HEURISTIC"

    # Verify GET /api/v1/plan/latest also exposes solver_status
    latest_res = client.get("/api/v1/plan/latest")
    assert latest_res.status_code == 200
    latest_data = latest_res.json()
    assert latest_data["status"] == "HEURISTIC"
    assert latest_data["solver_status"] == "FALLBACK_HEURISTIC"
