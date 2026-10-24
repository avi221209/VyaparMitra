"""
Worked-Example and Unit Tests for Requirement & Eligibility Services
Team Stark | Triwizathon 2026 | PS2: Distribution Intelligence and Inventory Optimization Engine

Pure function tests verifying exact specifications without DB access.
"""

import math
import pytest

from backend.app.services.requirement import (
    LaneInfo,
    NetRequirement,
    compute_net_requirement,
)
from backend.app.services.eligibility import (
    BatchInfo,
    LaneData,
    ProductInfo,
    compute_sell_through_cap,
    evaluate_batch_eligibility,
)


# =====================================================================
# 1. Official Worked-Example Test (Specification Benchmark)
# =====================================================================
def test_worked_example_exact_match():
    """
    WORKED-EXAMPLE TEST (must pass exactly).
    Cartons, case pack 1, H=7, z=1.28, Gmax=1.
    W1 holds 90, W2 holds 60 (batch expires in 42 days).

    D1: forecast 10/day, sigma 3, on hand 10, cover 1.00; lanes W1 (1 day, 1.5/carton), W2 (3 days, 4.0/carton)
    D2: forecast 20/day, sigma 6, on hand 55, cover 2.75; lanes W1 (1 day, 2.0), W2 (2 days, 3.5)

    Expected:
      - W2 to D1 excluded (gap 2 > 1).
      - D1: Ld=1, P=8, F=80, SS=10.86, Ndem=70, Ntot=81.
      - D2: Ld=2, P=9, F=180, SS=23.04, Ndem=125, Ntot=149.
    """
    H = 7
    z = 1.28
    Gmax = 1
    case_pack = 1

    # Product info
    product = ProductInfo(
        id="SKU-TEST-01",
        name="Test SKU",
        case_pack=case_pack,
        min_remaining_shelf_days=21,
        load_per_carton=1.0,
    )

    # Batches at warehouses
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
        days_to_expiry_from_dispatch=42,  # batch expires in 42 days
    )

    # Lanes into D1
    lane_w1_d1 = LaneInfo(source_id="W1", destination_id="D1", lead_time_days=1, cost_per_carton=1.5)
    lane_w2_d1 = LaneInfo(source_id="W2", destination_id="D1", lead_time_days=3, cost_per_carton=4.0)
    lanes_d1 = [lane_w1_d1, lane_w2_d1]

    # Lanes into D2
    lane_w1_d2 = LaneInfo(source_id="W1", destination_id="D2", lead_time_days=1, cost_per_carton=2.0)
    lane_w2_d2 = LaneInfo(source_id="W2", destination_id="D2", lead_time_days=2, cost_per_carton=3.5)
    lanes_d2 = [lane_w1_d2, lane_w2_d2]

    # -----------------------------------------------------------------
    # Part A: Net Requirement for D1
    # -----------------------------------------------------------------
    req_d1 = compute_net_requirement(
        destination_id="D1",
        product_id="SKU-TEST-01",
        on_hand=10.0,
        reserved=0.0,
        confirmed_in_transit=0.0,
        daily_forecast_mean=10.0,
        sigma=3.0,
        lanes=lanes_d1,
        H=H,
        z=z,
        Gmax=Gmax,
        case_pack=case_pack,
    )

    # D1 assertions
    assert req_d1.pos == 10.0
    assert req_d1.cover == pytest.approx(1.00, abs=1e-2)
    assert req_d1.eligible_lead_times == [1]  # Lane W1 (1d) has gap 0 <= 1; Lane W2 (3d) has gap 2 > 1
    assert req_d1.Ld == 1
    assert req_d1.P == 8
    assert req_d1.F == 80.0
    assert req_d1.SS == pytest.approx(10.86, abs=0.01)  # 1.28 * 3 * sqrt(8) = 10.86116
    assert req_d1.Ndem == 70
    assert req_d1.Ntot == 81

    # -----------------------------------------------------------------
    # Part B: Net Requirement for D2
    # -----------------------------------------------------------------
    req_d2 = compute_net_requirement(
        destination_id="D2",
        product_id="SKU-TEST-01",
        on_hand=55.0,
        reserved=0.0,
        confirmed_in_transit=0.0,
        daily_forecast_mean=20.0,
        sigma=6.0,
        lanes=lanes_d2,
        H=H,
        z=z,
        Gmax=Gmax,
        case_pack=case_pack,
    )

    # D2 assertions
    assert req_d2.pos == 55.0
    assert req_d2.cover == pytest.approx(2.75, abs=1e-2)
    assert req_d2.eligible_lead_times == [1, 2]  # Both W1 (gap 0) and W2 (gap 0) <= 1
    assert req_d2.Ld == 2
    assert req_d2.P == 9
    assert req_d2.F == 180.0
    assert req_d2.SS == pytest.approx(23.04, abs=0.01)  # 1.28 * 6 * sqrt(9) = 23.04
    assert req_d2.Ndem == 125
    assert req_d2.Ntot == 149

    # -----------------------------------------------------------------
    # Part C: Eligibility Evaluations for W2 to D1 and W2 to D2
    # -----------------------------------------------------------------
    # W2 to D1: lane lead time 3 days, cover 1.00 -> gap 2 > Gmax(1)
    lane_data_w2_d1 = LaneData(source_id="W2", destination_id="D1", lead_time_days=3, cost_per_carton=4.0)
    elig_w2_d1 = evaluate_batch_eligibility(
        batch=batch_w2,
        lane=lane_data_w2_d1,
        product=product,
        cover=req_d1.cover,
        daily_forecast_mean=10.0,
        pos=req_d1.pos,
        Gmax=Gmax,
    )

    assert elig_w2_d1.is_eligible is False
    assert "EXCLUDED_LANE_GAP" in elig_w2_d1.flags
    assert elig_w2_d1.lane_gap == pytest.approx(2.0, abs=1e-2)
    assert any("gap 2.00 > Gmax (1)" in r for r in elig_w2_d1.reasons)

    # W2 to D2: lane lead time 2 days, cover 2.75 -> gap 0 <= Gmax(1)
    # Days to expiry at arrival: 42 - 2 = 40 days >= 21
    # Sell-through cap: 20 * 40 - 55 = 745 cartons (batch has 60)
    lane_data_w2_d2 = LaneData(source_id="W2", destination_id="D2", lead_time_days=2, cost_per_carton=3.5)
    elig_w2_d2 = evaluate_batch_eligibility(
        batch=batch_w2,
        lane=lane_data_w2_d2,
        product=product,
        cover=req_d2.cover,
        daily_forecast_mean=20.0,
        pos=req_d2.pos,
        Gmax=Gmax,
    )

    assert elig_w2_d2.is_eligible is True
    assert elig_w2_d2.lane_gap == 0.0
    assert elig_w2_d2.days_to_expiry_at_arrival == 40
    assert elig_w2_d2.sell_through_cap == pytest.approx(745.0, abs=1e-2)
    assert elig_w2_d2.load_per_carton == 1.0


# =====================================================================
# 2. Shelf-Life Illustration Test
# =====================================================================
def test_shelf_life_illustration_cap():
    """
    Shelf-life illustration test:
    A destination selling 2/day holding 10 with a batch expiring in 30 days
    caps shipments at 2 * 30 - 10 = 50.
    """
    cap = compute_sell_through_cap(
        daily_forecast_mean=2.0,
        days_to_expiry_at_arrival=30,
        pos=10.0,
    )
    assert cap == 50.0


# =====================================================================
# 3. Acceptance Life & Negative Sell-Through Cap Edge Cases
# =====================================================================
def test_acceptance_life_exclusion():
    """Batches arriving with days-to-expiry < min_remaining_shelf_days are excluded."""
    product = ProductInfo(id="SKU-SHORT", min_remaining_shelf_days=21)
    lane = LaneData(source_id="W1", destination_id="D1", lead_time_days=2)

    # Batch expires in 22 days from dispatch -> arrival at day 2 -> 20 days remaining < 21
    batch = BatchInfo(
        id="B-SHORT",
        location_id="W1",
        product_id="SKU-SHORT",
        quantity=100,
        days_to_expiry_from_dispatch=22,
    )

    res = evaluate_batch_eligibility(
        batch=batch,
        lane=lane,
        product=product,
        cover=5.0,
        daily_forecast_mean=10.0,
        pos=50.0,
        Gmax=1,
    )

    assert res.is_eligible is False
    assert "EXCLUDED_ACCEPTANCE_LIFE" in res.flags
    assert res.days_to_expiry_at_arrival == 20


def test_zero_sell_through_cap_exclusion():
    """If pos >= f * e, sell-through cap is 0 and batch is excluded."""
    # f = 2, e = 10, pos = 25 -> f * e - pos = 20 - 25 = -5 -> cap = 0
    cap = compute_sell_through_cap(daily_forecast_mean=2.0, days_to_expiry_at_arrival=10, pos=25.0)
    assert cap == 0.0

    product = ProductInfo(id="SKU-01", min_remaining_shelf_days=5)
    lane = LaneData(source_id="W1", destination_id="D1", lead_time_days=1)
    batch = BatchInfo(id="B-EXCESS", location_id="W1", product_id="SKU-01", quantity=50, days_to_expiry_from_dispatch=11)

    res = evaluate_batch_eligibility(
        batch=batch,
        lane=lane,
        product=product,
        cover=15.0,
        daily_forecast_mean=2.0,
        pos=25.0,
        Gmax=1,
    )

    assert res.is_eligible is False
    assert "EXCLUDED_ZERO_SELL_THROUGH_CAP" in res.flags


def test_unavoidable_lost_sales_flag():
    """When 0 < G <= Gmax, line is allowed but flagged with unavoidable lost sales."""
    product = ProductInfo(id="SKU-01", min_remaining_shelf_days=5)
    lane = LaneData(source_id="W1", destination_id="D1", lead_time_days=3)
    batch = BatchInfo(id="B-01", location_id="W1", product_id="SKU-01", quantity=50, days_to_expiry_from_dispatch=50)

    # cover = 2.5 days, lead_time = 3 days -> G = 0.5 days <= Gmax (1)
    # f = 10 -> unavoidable lost sales = 10 * 0.5 = 5.0 units
    res = evaluate_batch_eligibility(
        batch=batch,
        lane=lane,
        product=product,
        cover=2.5,
        daily_forecast_mean=10.0,
        pos=25.0,
        Gmax=1,
    )

    assert res.is_eligible is True
    assert "LANE_GAP_RISK" in res.flags
    assert res.lane_gap == 0.5
    assert res.unavoidable_lost_sales == 5.0


def test_case_pack_rounding_in_requirement():
    """Conversion to cartons rounds up with ceil considering case pack."""
    lane = LaneInfo(source_id="W1", destination_id="D1", lead_time_days=1)
    # F = 8 * 10 = 80, pos = 10 -> unrounded Ndem = 70 units
    # If case_pack = 12: ceil(70 / 12) = ceil(5.833) = 6 cartons
    req = compute_net_requirement(
        destination_id="D1",
        product_id="SKU-CP12",
        on_hand=10.0,
        daily_forecast_mean=10.0,
        lanes=[lane],
        H=7,
        case_pack=12,
    )

    assert req.Ndem == 6
    assert req.unrounded_Ndem == 70.0
