"""
Unit and Integration Tests for Two-Stage Optimizer (PuLP + CBC)
Distribution Planning and Inventory Optimization Engine
"""

from datetime import date as dt_date, timedelta
import random
import time
import pytest
from sqlmodel import Session, select

from backend.app.db import engine, init_db
from backend.app.models import Batch, Settings
from backend.app.services.eligibility import (
    BatchEligibilityResult,
    BatchInfo,
    LaneData,
    ProductInfo,
    evaluate_all_batches_eligibility,
    evaluate_batch_eligibility,
)
from backend.app.services.optimizer import (
    OptimizationService,
    run_greedy_heuristic,
    solve_two_stage_optimization,
)
from backend.app.services.requirement import (
    LaneInfo,
    NetRequirement,
    compute_all_net_requirements,
    compute_net_requirement,
)
from backend.app.services.simulator import FMCGSimulator


# =====================================================================
# 1. Worked-Example Test (Exact Reproduction from Specification)
# =====================================================================
def test_optimizer_reproduces_worked_example():
    """
    Test: reproduces the worked example from chunk 4:
      - W1 to D1: 70 cartons
      - W1 to D2: 20 cartons
      - W2 to D2: 60 cartons
      - Transport: 105 + 40 + 210 = 355
      - Unmet demand: 45 (at D2), 0 (at D1)
      - Safety-stock gaps: 11 (D1) and 24 (D2)
    """
    plan_date = dt_date(2026, 10, 24)
    H = 7
    z = 1.28
    Gmax = 1
    case_pack = 1

    # Product
    product = ProductInfo(
        id="SKU-TEST-01",
        name="Test SKU",
        case_pack=case_pack,
        min_remaining_shelf_days=21,
        load_per_carton=1.0,
    )
    products = {"SKU-TEST-01": product}

    # Batches: W1 holds 90, W2 holds 60 (expires in 42 days)
    batch_w1 = BatchInfo(
        id="B-W1",
        location_id="W1",
        product_id="SKU-TEST-01",
        quantity=90,
        days_to_expiry_from_dispatch=100,
    )
    batch_w2 = BatchInfo(
        id="B-W2",
        location_id="W2",
        product_id="SKU-TEST-01",
        quantity=60,
        days_to_expiry_from_dispatch=42,
    )
    batches = [batch_w1, batch_w2]

    # Lanes
    lanes = [
        LaneData(source_id="W1", destination_id="D1", lead_time_days=1, cost_per_carton=1.5),
        LaneData(source_id="W2", destination_id="D1", lead_time_days=3, cost_per_carton=4.0),
        LaneData(source_id="W1", destination_id="D2", lead_time_days=1, cost_per_carton=2.0),
        LaneData(source_id="W2", destination_id="D2", lead_time_days=2, cost_per_carton=3.5),
    ]

    # Requirements from chunk 4:
    # D1: pos=10, f=10, Ld=1, P=8, F=80, SS=10.86, Ndem=70, Ntot=81 (gap uss = 11)
    req_d1 = compute_net_requirement(
        destination_id="D1",
        product_id="SKU-TEST-01",
        on_hand=10.0,
        daily_forecast_mean=10.0,
        sigma=3.0,
        lanes=[LaneInfo(source_id="W1", destination_id="D1", lead_time_days=1), LaneInfo(source_id="W2", destination_id="D1", lead_time_days=3)],
        H=H,
        z=z,
        Gmax=Gmax,
    )
    # D2: pos=55, f=20, Ld=2, P=9, F=180, SS=23.04, Ndem=125, Ntot=149 (gap uss = 24)
    req_d2 = compute_net_requirement(
        destination_id="D2",
        product_id="SKU-TEST-01",
        on_hand=55.0,
        daily_forecast_mean=20.0,
        sigma=6.0,
        lanes=[LaneInfo(source_id="W1", destination_id="D2", lead_time_days=1), LaneInfo(source_id="W2", destination_id="D2", lead_time_days=2)],
        H=H,
        z=z,
        Gmax=Gmax,
    )
    requirements = {
        "D1": {"SKU-TEST-01": req_d1},
        "D2": {"SKU-TEST-01": req_d2},
    }

    # Eligibility
    covers = {"D1": {"SKU-TEST-01": req_d1.cover}, "D2": {"SKU-TEST-01": req_d2.cover}}
    f_means = {"D1": {"SKU-TEST-01": 10.0}, "D2": {"SKU-TEST-01": 20.0}}
    positions = {"D1": {"SKU-TEST-01": 10.0}, "D2": {"SKU-TEST-01": 55.0}}

    eligibility = evaluate_all_batches_eligibility(
        batches=batches,
        lanes=lanes,
        products=products,
        covers=covers,
        daily_forecast_means=f_means,
        positions=positions,
        Gmax=Gmax,
    )

    # Run optimizer
    result = solve_two_stage_optimization(
        plan_date=plan_date,
        requirements=requirements,
        eligibility=eligibility,
        batches=batches,
        lanes=lanes,
        products=products,
    )

    assert result.status == "OPTIMIZED"

    # Map allocations: (source, destination) -> cartons, cost
    alloc_map = {}
    for line in result.lines:
        alloc_map[(line.source_id, line.destination_id)] = (line.cartons, line.cost)

    # 1. W1 to D1: 70 cartons, cost 105.0
    assert (
        "W1",
        "D1",
    ) in alloc_map, "Missing allocation from W1 to D1"
    assert alloc_map[("W1", "D1")][0] == 70
    assert alloc_map[("W1", "D1")][1] == 105.0

    # 2. W1 to D2: 20 cartons, cost 40.0
    assert (
        "W1",
        "D2",
    ) in alloc_map, "Missing allocation from W1 to D2"
    assert alloc_map[("W1", "D2")][0] == 20
    assert alloc_map[("W1", "D2")][1] == 40.0

    # 3. W2 to D2: 60 cartons, cost 210.0
    assert (
        "W2",
        "D2",
    ) in alloc_map, "Missing allocation from W2 to D2"
    assert alloc_map[("W2", "D2")][0] == 60
    assert alloc_map[("W2", "D2")][1] == 210.0

    # 4. Total transport cost: 105 + 40 + 210 = 355
    assert result.total_cost == 355.0
    assert result.total_cartons == 150

    # 5. Unmet demand: D2 has 45 unmet demand, D1 has 0 unmet demand
    assert result.unmet_by_destination_product[("D2", "SKU-TEST-01")]["udem"] == 45
    assert result.unmet_by_destination_product[("D1", "SKU-TEST-01")]["udem"] == 0
    assert result.total_unmet_demand_cartons == 45

    # 6. Safety-stock gaps: 11 (D1) and 24 (D2)
    assert result.unmet_by_destination_product[("D1", "SKU-TEST-01")]["uss"] == 11
    assert result.unmet_by_destination_product[("D2", "SKU-TEST-01")]["uss"] == 24


# =====================================================================
# 2. Determinism Across 3 Runs
# =====================================================================
def test_optimizer_determinism_across_3_runs():
    """Optimizer output must be 100% byte-for-byte identical across repeated runs."""
    plan_date = dt_date(2026, 10, 24)
    products = {"P1": ProductInfo(id="P1", load_per_carton=1.0)}
    batches = [
        BatchInfo(id="B1", location_id="W1", product_id="P1", quantity=50, days_to_expiry_from_dispatch=100),
        BatchInfo(id="B2", location_id="W2", product_id="P1", quantity=50, days_to_expiry_from_dispatch=100),
    ]
    lanes = [
        LaneData(source_id="W1", destination_id="D1", lead_time_days=1, cost_per_carton=2.0),
        LaneData(source_id="W2", destination_id="D1", lead_time_days=1, cost_per_carton=2.0),
    ]
    req = compute_net_requirement(
        destination_id="D1",
        product_id="P1",
        on_hand=10.0,
        daily_forecast_mean=10.0,
        lanes=[LaneInfo(source_id="W1", destination_id="D1", lead_time_days=1)],
    )
    requirements = {"D1": {"P1": req}}
    eligibility = evaluate_all_batches_eligibility(
        batches=batches,
        lanes=lanes,
        products=products,
        covers={"D1": {"P1": req.cover}},
        daily_forecast_means={"D1": {"P1": 10.0}},
        positions={"D1": {"P1": 10.0}},
    )

    runs = []
    for _ in range(3):
        res = solve_two_stage_optimization(
            plan_date=plan_date,
            requirements=requirements,
            eligibility=eligibility,
            batches=batches,
            lanes=lanes,
            products=products,
        )
        lines_summary = [(l.source_id, l.destination_id, l.batch_id, l.cartons, l.cost) for l in res.lines]
        runs.append((res.total_cost, res.total_cartons, lines_summary))

    assert runs[0] == runs[1] == runs[2]


# =====================================================================
# 3. Lane Capacity Trade-Off Test (Two Products Compete for Tight Lane)
# =====================================================================
def test_lane_capacity_forces_trade_off():
    """
    Two products compete for a single tight lane:
      - Product A: High gross margin (₹50/carton), needs 40 cartons
      - Product B: Low gross margin (₹10/carton), needs 40 cartons
      - Total demand = 80 cartons
      - Lane capacity = 50 cartons
    Expected:
      - Stage 1 service objective prioritizes Product A (gets 40 cartons)
      - Product B gets only remaining capacity (10 cartons)
      - Lane capacity strictly respected: total load <= 50
    """
    plan_date = dt_date(2026, 10, 24)
    prod_a = ProductInfo(id="SKU-A", load_per_carton=1.0, unit_margin=50.0)
    prod_b = ProductInfo(id="SKU-B", load_per_carton=1.0, unit_margin=10.0)
    products = {"SKU-A": prod_a, "SKU-B": prod_b}

    batches = [
        BatchInfo(id="B-A", location_id="W1", product_id="SKU-A", quantity=100, days_to_expiry_from_dispatch=100),
        BatchInfo(id="B-B", location_id="W1", product_id="SKU-B", quantity=100, days_to_expiry_from_dispatch=100),
    ]

    # Lane with capacity 50 cartons
    lanes = [
        LaneData(source_id="W1", destination_id="D1", lead_time_days=1, cost_per_carton=2.0, capacity_load=50.0)
    ]

    req_a = compute_net_requirement(
        destination_id="D1",
        product_id="SKU-A",
        on_hand=0.0,
        daily_forecast_mean=5.0,
        lanes=[LaneInfo(source_id="W1", destination_id="D1", lead_time_days=1)],
        H=7,
    )
    req_a.Ndem = 40
    req_a.Ntot = 40

    req_b = compute_net_requirement(
        destination_id="D1",
        product_id="SKU-B",
        on_hand=0.0,
        daily_forecast_mean=5.0,
        lanes=[LaneInfo(source_id="W1", destination_id="D1", lead_time_days=1)],
        H=7,
    )
    req_b.Ndem = 40
    req_b.Ntot = 40

    requirements = {"D1": {"SKU-A": req_a, "SKU-B": req_b}}

    eligibility = evaluate_all_batches_eligibility(
        batches=batches,
        lanes=lanes,
        products=products,
        covers={"D1": {"SKU-A": 0.0, "SKU-B": 0.0}},
        daily_forecast_means={"D1": {"SKU-A": 5.0, "SKU-B": 5.0}},
        positions={"D1": {"SKU-A": 0.0, "SKU-B": 0.0}},
    )

    result = solve_two_stage_optimization(
        plan_date=plan_date,
        requirements=requirements,
        eligibility=eligibility,
        batches=batches,
        lanes=lanes,
        products=products,
    )

    # Shipped per product
    shipped_a = sum(l.cartons for l in result.lines if l.product_id == "SKU-A")
    shipped_b = sum(l.cartons for l in result.lines if l.product_id == "SKU-B")

    # Product A must be fulfilled first up to demand 40
    assert shipped_a == 40
    # Product B gets only the remaining 10 cartons
    assert shipped_b == 10
    # Total cartons cannot exceed lane capacity of 50
    assert result.total_cartons == 50
    assert (shipped_a + shipped_b) <= 50.0


# =====================================================================
# 4. 100 Randomized Scenarios With No Violated Constraints
# =====================================================================
def test_100_randomized_scenarios_no_violated_constraints():
    """
    Generate 100 randomized supply, demand, capacity, shelf-life scenarios.
    Assert zero constraints are violated across all 100 solved scenarios.
    """
    plan_date = dt_date(2026, 10, 24)
    rng = random.Random(42)

    for scenario_idx in range(100):
        # 1-3 products, 2 destinations, 2 warehouses
        prod_ids = [f"SKU-{p}" for p in range(rng.randint(1, 3))]
        products = {
            pid: ProductInfo(
                id=pid,
                min_remaining_shelf_days=21,
                load_per_carton=rng.choice([1.0, 1.5]),
            )
            for pid in prod_ids
        }

        # Warehouses W1, W2; Destinations D1, D2
        batches = []
        for pid in prod_ids:
            batches.append(
                BatchInfo(
                    id=f"B-W1-{pid}",
                    location_id="W1",
                    product_id=pid,
                    quantity=rng.randint(20, 100),
                    days_to_expiry_from_dispatch=rng.randint(25, 120),
                )
            )
            batches.append(
                BatchInfo(
                    id=f"B-W2-{pid}",
                    location_id="W2",
                    product_id=pid,
                    quantity=rng.randint(20, 100),
                    days_to_expiry_from_dispatch=rng.randint(25, 120),
                )
            )

        lanes = [
            LaneData(source_id="W1", destination_id="D1", lead_time_days=1, cost_per_carton=1.5, capacity_load=rng.choice([None, 80.0])),
            LaneData(source_id="W1", destination_id="D2", lead_time_days=2, cost_per_carton=2.5, capacity_load=rng.choice([None, 80.0])),
            LaneData(source_id="W2", destination_id="D1", lead_time_days=2, cost_per_carton=3.0, capacity_load=rng.choice([None, 80.0])),
            LaneData(source_id="W2", destination_id="D2", lead_time_days=1, cost_per_carton=1.8, capacity_load=rng.choice([None, 80.0])),
        ]

        # Requirements
        requirements = {}
        covers = {}
        f_means = {}
        positions = {}
        for d in ["D1", "D2"]:
            requirements[d] = {}
            covers[d] = {}
            f_means[d] = {}
            positions[d] = {}
            for pid in prod_ids:
                on_hand = float(rng.randint(5, 40))
                f = float(rng.randint(5, 25))
                sig = float(rng.randint(1, 5))
                req = compute_net_requirement(
                    destination_id=d,
                    product_id=pid,
                    on_hand=on_hand,
                    daily_forecast_mean=f,
                    sigma=sig,
                    lanes=[LaneInfo(source_id=l.source_id, destination_id=l.destination_id, lead_time_days=l.lead_time_days) for l in lanes],
                )
                requirements[d][pid] = req
                covers[d][pid] = req.cover
                f_means[d][pid] = f
                positions[d][pid] = on_hand

        eligibility = evaluate_all_batches_eligibility(
            batches=batches,
            lanes=lanes,
            products=products,
            covers=covers,
            daily_forecast_means=f_means,
            positions=positions,
        )

        res = solve_two_stage_optimization(
            plan_date=plan_date,
            requirements=requirements,
            eligibility=eligibility,
            batches=batches,
            lanes=lanes,
            products=products,
        )

        # Verification of constraints:
        # C1: Stock availability: sum_d y[b, d] <= quantity
        batch_shipped = {}
        for l in res.lines:
            batch_shipped[l.batch_id] = batch_shipped.get(l.batch_id, 0) + l.cartons
        for b in batches:
            shipped = batch_shipped.get(b.id, 0)
            assert shipped <= b.quantity, f"Scenario {scenario_idx}: C1 violated for batch {b.id}"

        # C2 & C3: sum_b y <= Ntot
        dest_prod_shipped = {}
        for l in res.lines:
            key = (l.destination_id, l.product_id)
            dest_prod_shipped[key] = dest_prod_shipped.get(key, 0) + l.cartons
        for d in ["D1", "D2"]:
            for pid in prod_ids:
                shipped = dest_prod_shipped.get((d, pid), 0)
                req = requirements[d][pid]
                assert shipped <= req.Ntot, f"Scenario {scenario_idx}: C3 over-allocated at {d}-{pid}"

        # C6: Lane capacity load <= capacity
        lane_load = {}
        for l in res.lines:
            prod = products[l.product_id]
            key = (l.source_id, l.destination_id)
            lane_load[key] = lane_load.get(key, 0.0) + (l.cartons * prod.load_per_carton)
        for lane in lanes:
            if lane.capacity_load is not None:
                load = lane_load.get((lane.source_id, lane.destination_id), 0.0)
                assert load <= lane.capacity_load + 1e-4, f"Scenario {scenario_idx}: C6 lane capacity exceeded"


# =====================================================================
# 5. Performance Test: Plan Time <= 5s at 24x4x2 Network
# =====================================================================
def test_plan_time_at_most_5s_at_full_network():
    """
    Performance benchmark on 24 products x 4 destinations x 2 warehouses.
    Must solve within 5.0 seconds.
    """
    init_db()
    with Session(engine) as session:
        has_sales = session.exec(select(Batch)).first()
        if not has_sales:
            sim = FMCGSimulator(seed=42)
            sim.seed_database(session)

        service = OptimizationService(session)
        start = time.time()
        result = service.run_plan(plan_date=dt_date(2026, 10, 24))
        elapsed = time.time() - start

        assert result.status in ["OPTIMIZED", "HEURISTIC"]
        assert len(result.lines) > 0
        assert result.total_cost > 0.0
        # Time budget: at most 5.0 seconds
        assert result.solve_time_seconds <= 5.0, f"Plan time {result.solve_time_seconds:.2f}s exceeded 5s limit"
        assert elapsed <= 6.0
