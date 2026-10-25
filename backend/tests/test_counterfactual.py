"""
Unit and Integration Tests for Counterfactual What-If Explanation Engine
Distribution Planning and Inventory Optimization Engine
"""

from datetime import date as dt_date
import random
import pytest

from backend.app.services.counterfactual import (
    CounterfactualReport,
    StockFixResult,
    LeadTimeFixResult,
    ShelfLifeFixResult,
    LaneCapacityFixResult,
    analyze_counterfactuals,
)
from backend.app.services.eligibility import (
    BatchEligibilityResult,
    BatchInfo,
    LaneData,
    ProductInfo,
    evaluate_all_batches_eligibility,
)
from backend.app.services.optimizer import (
    OptimizationResult,
    solve_two_stage_optimization,
)
from backend.app.services.requirement import (
    LaneInfo,
    NetRequirement,
    compute_net_requirement,
)


# =====================================================================
# 1. Worked-Example Test (Exact Reproduction from Specification)
# =====================================================================
def test_counterfactual_worked_example():
    """
    Tests with the worked example:
      - Stock fix: +45 cartons at W1 closes the D2 demand gap at +90 transport (45 x 2.0)
      - +80 also restores safety stock at +154.5
      - Lead time: allowing W2 to D1 changes nothing (still 45 unmet)
      - Shelf life and lane capacity: not binding
      - Binding constraint: stock
      - Unmet demand: 45, Safety-stock gap: 24
    """
    plan_date = dt_date(2026, 10, 24)
    H = 7
    z = 1.28
    Gmax = 1
    case_pack = 1

    product = ProductInfo(
        id="SKU-TEST-01",
        name="Test SKU",
        case_pack=case_pack,
        min_remaining_shelf_days=21,
        load_per_carton=1.0,
    )
    products = {"SKU-TEST-01": product}

    # W1 holds 90, W2 holds 60 (expires in 42 days)
    batch_w1 = BatchInfo(id="B-W1", location_id="W1", product_id="SKU-TEST-01", quantity=90, days_to_expiry_from_dispatch=100)
    batch_w2 = BatchInfo(id="B-W2", location_id="W2", product_id="SKU-TEST-01", quantity=60, days_to_expiry_from_dispatch=42)
    batches = [batch_w1, batch_w2]

    lanes = [
        LaneData(source_id="W1", destination_id="D1", lead_time_days=1, cost_per_carton=1.5),
        LaneData(source_id="W2", destination_id="D1", lead_time_days=3, cost_per_carton=4.0),
        LaneData(source_id="W1", destination_id="D2", lead_time_days=1, cost_per_carton=2.0),
        LaneData(source_id="W2", destination_id="D2", lead_time_days=2, cost_per_carton=3.5),
    ]

    req_d1 = compute_net_requirement(
        destination_id="D1",
        product_id="SKU-TEST-01",
        on_hand=10.0,
        daily_forecast_mean=10.0,
        sigma=3.0,
        lanes=[LaneInfo("W1", "D1", 1), LaneInfo("W2", "D1", 3)],
        H=H,
        z=z,
        Gmax=Gmax,
    )
    req_d2 = compute_net_requirement(
        destination_id="D2",
        product_id="SKU-TEST-01",
        on_hand=55.0,
        daily_forecast_mean=20.0,
        sigma=6.0,
        lanes=[LaneInfo("W1", "D2", 1), LaneInfo("W2", "D2", 2)],
        H=H,
        z=z,
        Gmax=Gmax,
    )
    requirements = {"D1": {"SKU-TEST-01": req_d1}, "D2": {"SKU-TEST-01": req_d2}}

    eligibility = evaluate_all_batches_eligibility(
        batches=batches,
        lanes=lanes,
        products=products,
        covers={"D1": {"SKU-TEST-01": req_d1.cover}, "D2": {"SKU-TEST-01": req_d2.cover}},
        daily_forecast_means={"D1": {"SKU-TEST-01": 10.0}, "D2": {"SKU-TEST-01": 20.0}},
        positions={"D1": {"SKU-TEST-01": 10.0}, "D2": {"SKU-TEST-01": 55.0}},
        Gmax=Gmax,
    )

    reports = analyze_counterfactuals(
        plan_date=plan_date,
        requirements=requirements,
        eligibility=eligibility,
        batches=batches,
        lanes=lanes,
        products=products,
    )

    # Exactly 1 destination has unmet demand (D2)
    assert len(reports) == 1
    r = reports[0]

    assert r.destination_id == "D2"
    assert r.product_id == "SKU-TEST-01"
    assert r.udem == 45
    assert r.uss == 24
    assert r.binding_constraint == "stock"

    # Stock fix: +45 cartons at W1 closes D2 demand gap at +90 transport (45 x 2.0)
    assert r.stock_fix is not None
    assert r.stock_fix.source_id == "W1"
    assert r.stock_fix.extra_cartons_demand == 45
    assert r.stock_fix.extra_transport_cost_demand == 90.0

    # Stock fix restoring safety stock too: +80 at +154.5 transport
    assert r.stock_fix.extra_cartons_total == 80
    assert r.stock_fix.extra_transport_cost_total == 154.5

    # Lead time: allowing W2 to D1 changes nothing (still 45 unmet)
    assert r.lead_time_fix is not None
    assert r.lead_time_fix.is_binding is False
    assert r.lead_time_fix.delta_gmax_days is None
    assert r.lead_time_fix.description == "no change"

    # Shelf life and lane capacity: not binding
    assert r.shelf_life_fix is not None
    assert r.shelf_life_fix.is_binding is False

    assert r.lane_capacity_fix is not None
    assert r.lane_capacity_fix.is_binding is False


# =====================================================================
# 2. Binding Constraint Diagnostic Tests
# =====================================================================
def test_counterfactual_lane_capacity_binding():
    """When stock is plentiful but lane capacity is tight, lane_capacity is binding."""
    plan_date = dt_date(2026, 10, 24)
    products = {"P1": ProductInfo(id="P1", load_per_carton=1.0)}
    batches = [BatchInfo(id="B1", location_id="W1", product_id="P1", quantity=100, days_to_expiry_from_dispatch=100)]
    lanes = [LaneData(source_id="W1", destination_id="D1", lead_time_days=1, cost_per_carton=2.0, capacity_load=30.0)]

    req = compute_net_requirement("D1", "P1", on_hand=0.0, daily_forecast_mean=10.0, lanes=[LaneInfo("W1", "D1", 1)])
    req.Ndem = 50
    req.Ntot = 50
    requirements = {"D1": {"P1": req}}

    eligibility = evaluate_all_batches_eligibility(
        batches=batches,
        lanes=lanes,
        products=products,
        covers={"D1": {"P1": 0.0}},
        daily_forecast_means={"D1": {"P1": 10.0}},
        positions={"D1": {"P1": 0.0}},
    )

    reports = analyze_counterfactuals(plan_date, requirements, eligibility, batches, lanes, products)
    assert len(reports) == 1
    r = reports[0]
    assert r.udem == 20  # 50 - 30 = 20
    assert r.binding_constraint == "lane_capacity"
    assert r.lane_capacity_fix.is_binding is True


def test_counterfactual_lead_time_binding():
    """When stock exists at an alternate warehouse with higher lead time, lead_time is binding."""
    plan_date = dt_date(2026, 10, 24)
    products = {"P1": ProductInfo(id="P1", load_per_carton=1.0)}
    # W1 has 0, W2 has 60 cartons
    batches = [
        BatchInfo(id="B1", location_id="W1", product_id="P1", quantity=0, days_to_expiry_from_dispatch=100),
        BatchInfo(id="B2", location_id="W2", product_id="P1", quantity=60, days_to_expiry_from_dispatch=100),
    ]
    # W1 is nearby (L=1), W2 is further (L=3). Base Gmax=1 -> lane W2-D1 is excluded (gap=3 > 1)
    lanes = [
        LaneData(source_id="W1", destination_id="D1", lead_time_days=1, cost_per_carton=1.5),
        LaneData(source_id="W2", destination_id="D1", lead_time_days=3, cost_per_carton=3.0),
    ]
    req = compute_net_requirement("D1", "P1", on_hand=0.0, daily_forecast_mean=5.0, lanes=[LaneInfo("W1", "D1", 1)])
    req.Ndem = 40
    req.Ntot = 40
    requirements = {"D1": {"P1": req}}

    eligibility = evaluate_all_batches_eligibility(
        batches=batches,
        lanes=lanes,
        products=products,
        covers={"D1": {"P1": 0.0}},
        daily_forecast_means={"D1": {"P1": 5.0}},
        positions={"D1": {"P1": 0.0}},
        Gmax=1,
    )

    reports = analyze_counterfactuals(plan_date, requirements, eligibility, batches, lanes, products)
    assert len(reports) == 1
    r = reports[0]
    assert r.udem == 40
    assert r.binding_constraint == "lead_time"
    assert r.lead_time_fix.is_binding is True
    assert r.lead_time_fix.delta_gmax_days == 2  # Gmax=1 + 2 = 3 allows L=3


# =====================================================================
# 3. SUFFICIENCY and MINIMALITY Tests on 50 Randomized Shortfalls
# =====================================================================
def test_counterfactual_sufficiency_and_minimality_50_shortfalls():
    """
    SUFFICIENCY and MINIMALITY tests across 50 randomized shortfall scenarios:
      - Applying the stock fix closes the unmet demand gap (Sufficiency: udem == 0).
      - Applying one carton less leaves an unmet demand gap (Minimality: udem >= 1).
    """
    plan_date = dt_date(2026, 10, 24)
    rng = random.Random(101)

    tested_scenarios = 0
    attempt = 0

    while tested_scenarios < 50 and attempt < 200:
        attempt += 1
        pid = f"SKU-RND-{tested_scenarios}"
        prod = ProductInfo(id=pid, min_remaining_shelf_days=21, load_per_carton=1.0)
        products = {pid: prod}

        # Warehouses W1, W2
        qty_w1 = rng.randint(10, 40)
        qty_w2 = rng.randint(10, 40)
        batches = [
            BatchInfo(id=f"B-W1-{attempt}", location_id="W1", product_id=pid, quantity=qty_w1, days_to_expiry_from_dispatch=100),
            BatchInfo(id=f"B-W2-{attempt}", location_id="W2", product_id=pid, quantity=qty_w2, days_to_expiry_from_dispatch=100),
        ]

        lanes = [
            LaneData(source_id="W1", destination_id="D1", lead_time_days=1, cost_per_carton=1.5),
            LaneData(source_id="W2", destination_id="D1", lead_time_days=2, cost_per_carton=2.5),
        ]

        # Generate demand that exceeds total stock (ensures a shortfall)
        total_supply = qty_w1 + qty_w2
        demand_target = total_supply + rng.randint(10, 50)

        req = compute_net_requirement("D1", pid, on_hand=0.0, daily_forecast_mean=10.0, lanes=[LaneInfo("W1", "D1", 1)])
        req.Ndem = demand_target
        req.Ntot = demand_target + 10
        requirements = {"D1": {pid: req}}

        eligibility = evaluate_all_batches_eligibility(
            batches=batches,
            lanes=lanes,
            products=products,
            covers={"D1": {pid: 0.0}},
            daily_forecast_means={"D1": {pid: 10.0}},
            positions={"D1": {pid: 0.0}},
        )

        base_res = solve_two_stage_optimization(
            plan_date=plan_date,
            requirements=requirements,
            eligibility=eligibility,
            batches=batches,
            lanes=lanes,
            products=products,
        )

        base_udem = base_res.unmet_by_destination_product.get(("D1", pid), {}).get("udem", 0)
        if base_udem <= 0:
            continue

        reports = analyze_counterfactuals(
            plan_date=plan_date,
            requirements=requirements,
            eligibility=eligibility,
            batches=batches,
            lanes=lanes,
            products=products,
            base_result=base_res,
        )

        if not reports or not reports[0].stock_fix:
            continue

        r = reports[0]
        K = r.stock_fix.extra_cartons_demand
        source_s = r.stock_fix.source_id

        assert K == base_udem, f"Scenario {tested_scenarios}: Expected K={base_udem}, got {K}"

        # 1. SUFFICIENCY: Add K cartons at source_s -> udem MUST be 0
        suff_batches = [
            BatchInfo(
                id=b.id,
                location_id=b.location_id,
                product_id=b.product_id,
                quantity=b.quantity + (K if b.location_id == source_s else 0),
                days_to_expiry_from_dispatch=b.days_to_expiry_from_dispatch,
            )
            for b in batches
        ]
        suff_elig = evaluate_all_batches_eligibility(
            batches=suff_batches,
            lanes=lanes,
            products=products,
            covers={"D1": {pid: 0.0}},
            daily_forecast_means={"D1": {pid: 10.0}},
            positions={"D1": {pid: 0.0}},
        )
        suff_res = solve_two_stage_optimization(
            plan_date=plan_date,
            requirements=requirements,
            eligibility=suff_elig,
            batches=suff_batches,
            lanes=lanes,
            products=products,
        )
        suff_udem = suff_res.unmet_by_destination_product[("D1", pid)]["udem"]
        assert suff_udem == 0, f"Scenario {tested_scenarios}: Sufficiency failed! udem={suff_udem} with +{K} cartons"

        # 2. MINIMALITY: Add K - 1 cartons at source_s -> udem MUST be >= 1
        mini_batches = [
            BatchInfo(
                id=b.id,
                location_id=b.location_id,
                product_id=b.product_id,
                quantity=b.quantity + (K - 1 if b.location_id == source_s else 0),
                days_to_expiry_from_dispatch=b.days_to_expiry_from_dispatch,
            )
            for b in batches
        ]
        mini_elig = evaluate_all_batches_eligibility(
            batches=mini_batches,
            lanes=lanes,
            products=products,
            covers={"D1": {pid: 0.0}},
            daily_forecast_means={"D1": {pid: 10.0}},
            positions={"D1": {pid: 0.0}},
        )
        mini_res = solve_two_stage_optimization(
            plan_date=plan_date,
            requirements=requirements,
            eligibility=mini_elig,
            batches=mini_batches,
            lanes=lanes,
            products=products,
        )
        mini_udem = mini_res.unmet_by_destination_product[("D1", pid)]["udem"]
        assert mini_udem >= 1, f"Scenario {tested_scenarios}: Minimality failed! udem={mini_udem} with +{K-1} cartons"

        tested_scenarios += 1

    assert tested_scenarios == 50, f"Completed {tested_scenarios} scenarios instead of 50"
