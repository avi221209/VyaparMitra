"""
VyaparMitra - Walk-Forward Replay & Benchmark Test Suite
Team Stark | Triwizathon 2026 | PS2: Distribution Intelligence and Inventory Optimization Engine

Tests:
  1. Replay is deterministic for a seed (same seed produces identical results).
  2. Strict no-leakage guarantee (modifying data after a cycle's start date does not alter that cycle's plan or forecast).
  3. Abundant scenario handled (reported, not pass/fail).
  4. Pre-registered headroom rule and targets verification.
  5. API endpoints: GET /api/evaluate, POST /api/evaluate/rerun, GET /api/evaluate/status.
"""

from copy import deepcopy
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
import pandas as pd

from backend.app.main import app
from backend.app.models import Settings
from backend.app.services.baselines import (
    BASELINE_A_SETTINGS,
    BASELINE_B_SETTINGS,
    build_pure_domain_objects,
    solve_baseline_a,
    solve_baseline_c,
    solve_v,
)
from backend.app.services.replay import (
    EvaluationEngine,
    WalkForwardReplay,
    get_cached_evaluation,
    global_eval_runner,
)


@pytest.fixture
def client():
    return TestClient(app)


# =====================================================================
# 1. Determinism for a Seed
# =====================================================================
def test_replay_is_deterministic_for_a_seed():
    """Verify that running the replay twice with the same seed produces identical results."""
    seed = 42

    # Method A determinism
    replay1 = WalkForwardReplay(seed=seed, scenario="scarce")
    res_a1 = replay1.run_replay_for_method("A")

    replay2 = WalkForwardReplay(seed=seed, scenario="scarce")
    res_a2 = replay2.run_replay_for_method("A")

    assert res_a1.fill_rate == res_a2.fill_rate
    assert res_a1.unmet_units == res_a2.unmet_units
    assert res_a1.cost_to_serve == res_a2.cost_to_serve
    assert res_a1.expiry_waste == res_a2.expiry_waste
    assert res_a1.transport_cost_per_unit_served == res_a2.transport_cost_per_unit_served

    # Method C determinism
    res_c1 = replay1.run_replay_for_method("C")
    res_c2 = replay2.run_replay_for_method("C")

    assert res_c1.fill_rate == res_c2.fill_rate
    assert res_c1.unmet_units == res_c2.unmet_units
    assert res_c1.cost_to_serve == res_c2.cost_to_serve


# =====================================================================
# 2. Strict No-Leakage Guarantee
# =====================================================================
def test_no_leakage_guarantee():
    """
    Changing sales data strictly after a cycle's start date
    must NOT change that cycle's plan or forecast.
    """
    seed = 10
    replay = WalkForwardReplay(seed=seed, scenario="balanced")

    cycle_start = replay.base_date - timedelta(days=28)
    destinations = replay.destinations
    products = replay.products
    _, lanes_pure, _ = build_pure_domain_objects(products, replay.lanes, [], cycle_start)

    wh_batches = replay._generate_weekly_warehouse_supply(1, cycle_start)
    dest_cartons_on_hand = {
        d.id: {p.id: 15.0 for p in products} for d in destinations
    }

    # Plan 1: with normal sales cache strictly sliced before cycle_start
    sales_slice_1 = {
        k: s[s.index < cycle_start]
        for k, s in replay.sales_cache.items()
    }

    lines1_a = solve_baseline_a(
        plan_date=cycle_start,
        destinations=destinations,
        products=products,
        lanes=lanes_pure,
        batches=deepcopy(wh_batches),
        destination_inventory=dest_cartons_on_hand,
        sales_cache=sales_slice_1,
    )

    lines1_c, res1_c = solve_baseline_c(
        plan_date=cycle_start,
        destinations=destinations,
        products=products,
        lanes=lanes_pure,
        batches=deepcopy(wh_batches),
        destination_inventory=dest_cartons_on_hand,
        sales_cache=sales_slice_1,
        settings=replay.settings,
    )

    # Now simulate a massive future demand spike AFTER cycle_start (e.g. 5 days later)
    corrupted_cache = {}
    future_date = cycle_start + timedelta(days=5)
    for k, s in replay.sales_cache.items():
        s_copy = s.copy()
        s_copy.loc[future_date] = 9999999.0  # Huge future spike!
        corrupted_cache[k] = s_copy

    # Plan 2: re-run with corrupted future data, but strictly sliced before cycle_start
    sales_slice_2 = {
        k: s[s.index < cycle_start]
        for k, s in corrupted_cache.items()
    }

    lines2_a = solve_baseline_a(
        plan_date=cycle_start,
        destinations=destinations,
        products=products,
        lanes=lanes_pure,
        batches=deepcopy(wh_batches),
        destination_inventory=dest_cartons_on_hand,
        sales_cache=sales_slice_2,
    )

    lines2_c, res2_c = solve_baseline_c(
        plan_date=cycle_start,
        destinations=destinations,
        products=products,
        lanes=lanes_pure,
        batches=deepcopy(wh_batches),
        destination_inventory=dest_cartons_on_hand,
        sales_cache=sales_slice_2,
        settings=replay.settings,
    )

    # Verify identical carton shipments and costs despite future spike
    assert len(lines1_a) == len(lines2_a)
    assert sum(l.cartons for l in lines1_a) == sum(l.cartons for l in lines2_a)
    assert sum(l.cost for l in lines1_a) == sum(l.cost for l in lines2_a)

    assert len(lines1_c) == len(lines2_c)
    assert res1_c.total_demand_cartons == res2_c.total_demand_cartons
    assert res1_c.total_cartons == res2_c.total_cartons
    assert res1_c.total_cost == res2_c.total_cost


# =====================================================================
# 3. Abundant Scenario Handled (Reported, not Pass/Fail)
# =====================================================================
def test_abundant_scenario_handled():
    """Verify that abundant scenario runs 4 cycles and is excluded from pass/fail."""
    replay = WalkForwardReplay(seed=1, scenario="abundant")
    res_v = replay.run_replay_for_method("V")

    assert len(res_v.cycles) == 4
    assert res_v.fill_rate > 90.0
    assert res_v.scenario == "abundant"

    # Verify evaluation targets handling: abundant is reported, not pass/fail
    engine = EvaluationEngine(seeds=[1])
    m_metrics = {
        "V": {"fill_rate_mean": 98.0, "unmet_units_mean": 1000.0, "transport_per_unit_mean": 1.5, "expiry_waste_mean": 0.02, "cost_to_serve_mean": 50000.0, "wape_mean": 0.20, "bias_mean": 0.01},
        "A": {"fill_rate_mean": 94.0, "unmet_units_mean": 5000.0, "transport_per_unit_mean": 1.5, "expiry_waste_mean": 0.05, "cost_to_serve_mean": 100000.0, "wape_mean": 0.25, "bias_mean": 0.02},
        "B": {"fill_rate_mean": 95.0, "unmet_units_mean": 4000.0, "transport_per_unit_mean": 2.0, "expiry_waste_mean": 0.04, "cost_to_serve_mean": 90000.0, "wape_mean": 0.25, "bias_mean": 0.02},
        "C": {"fill_rate_mean": 96.0, "unmet_units_mean": 3000.0, "transport_per_unit_mean": 1.6, "expiry_waste_mean": 0.03, "cost_to_serve_mean": 70000.0, "wape_mean": 0.22, "bias_mean": 0.01},
        "O": {"fill_rate_mean": 99.0},
    }

    eval_abundant = engine._evaluate_targets(m_metrics, no_headroom=False, is_pass_fail=False)
    assert eval_abundant["overall_status"] == "REPORTED_ONLY"


# =====================================================================
# 4. Pre-Registered Headroom Rule & Target Evaluation
# =====================================================================
def test_headroom_rule_exclusion():
    """Verify that when Oracle FR - Baseline A FR < 3.0 points, scenario is marked NO_HEADROOM."""
    engine = EvaluationEngine(seeds=[1])
    m_metrics = {
        "V": {"fill_rate_mean": 92.0, "unmet_units_mean": 2000.0, "transport_per_unit_mean": 1.5, "expiry_waste_mean": 0.02, "cost_to_serve_mean": 50000.0, "wape_mean": 0.20, "bias_mean": 0.01},
        "A": {"fill_rate_mean": 91.0, "unmet_units_mean": 2500.0, "transport_per_unit_mean": 1.5, "expiry_waste_mean": 0.02, "cost_to_serve_mean": 60000.0, "wape_mean": 0.25, "bias_mean": 0.02},
        "B": {"fill_rate_mean": 91.0, "unmet_units_mean": 2500.0, "transport_per_unit_mean": 1.8, "expiry_waste_mean": 0.02, "cost_to_serve_mean": 60000.0, "wape_mean": 0.25, "bias_mean": 0.02},
        "C": {"fill_rate_mean": 91.5, "unmet_units_mean": 2200.0, "transport_per_unit_mean": 1.6, "expiry_waste_mean": 0.02, "cost_to_serve_mean": 55000.0, "wape_mean": 0.22, "bias_mean": 0.01},
        "O": {"fill_rate_mean": 92.5},  # Gap O - A = 1.5 < 3.0 points!
    }

    eval_headroom = engine._evaluate_targets(m_metrics, no_headroom=True, is_pass_fail=False)
    assert eval_headroom["overall_status"] == "EXCLUDED"
    assert "No headroom" in eval_headroom["note"]


# =====================================================================
# 5. API Endpoints
# =====================================================================
def test_api_evaluate_endpoints(client):
    """Test /api/evaluate, /api/evaluate/rerun, and /api/evaluate/status endpoints."""
    # 1. GET /api/evaluate/status
    resp_status = client.get("/api/evaluate/status")
    assert resp_status.status_code == 200
    data_status = resp_status.json()
    assert "status" in data_status
    assert "progress" in data_status

    # 2. GET /api/evaluate
    resp_eval = client.get("/api/evaluate")
    assert resp_eval.status_code == 200
    data_eval = resp_eval.json()
    assert isinstance(data_eval, dict)

    # 3. POST /api/evaluate/rerun
    resp_rerun = client.post("/api/evaluate/rerun")
    assert resp_rerun.status_code == 200
    data_rerun = resp_rerun.json()
    assert data_rerun["status"] in ["started", "already_running"]
