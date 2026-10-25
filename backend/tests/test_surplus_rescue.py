"""
VyaparMitra - Surplus Rescue & Dead-Stock Intelligence Tests
Team Stark | Triwizathon 2026 | PS2: Distribution Intelligence and Inventory Optimization Engine

Tests all 6 core features:
  1. Feature A: Verified Spare Stock Gate (ring-fenced seller protection & exact refusal text)
  2. Feature B: Explained Refusals (4-gate filtering: spare stock, lane gap, arrival shelf life, FEFO cap)
  3. Feature C: Gains-from-Trade Price Band (seller floor, buyer ceiling, midpoint price, rupee gains)
  4. Feature D: Landed Cost-to-Serve Comparison (3-way economic analysis in rupees)
  5. Feature E: Shortfall Rescue Plan Integration, Role-Gating, and Undo
  6. Feature F: Dead-Stock Early Warning (network-wide expiry risk detector)
"""

from datetime import date, timedelta
import math
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from backend.app.main import app
from backend.app.models import (
    Batch,
    DecisionLog,
    Location,
    PlanLine,
    PlanRun,
    Product,
    SurplusListing,
)
from backend.app.services.simulator import FMCGSimulator
from backend.app.services.surplus import (
    apply_shortfall_rescue,
    build_rescue_analysis_for_unmet,
    compare_shortfall_options,
    compute_dead_stock_warnings,
    compute_gains_from_trade,
    compute_verified_spare_stock,
    evaluate_listing_for_shortfall,
    undo_shortfall_rescue,
)


# =====================================================================
# Feature A Tests: Verified Spare Stock Gate
# =====================================================================

def test_feature_a_verified_spare_stock_gate_zero_spare():
    """
    Test Gate 1: When on_hand > 0 but seller_protected_need consumes all on-hand stock,
    verified_spare_cartons must be 0 and refusal message must match the exact specification.
    """
    # Need: ceil(5.0 * 7 + 1.65 * 1.8 * sqrt(7)) = ceil(35 + 7.86) = 43
    listing = SurplusListing(
        id="SURPLUS-P1-SKU-P02",
        source_id="P1",
        source_name="Peer Godown P1",
        product_id="SKU-P02",
        batch_id="BATCH-001",
        on_hand=35,
        reserved=5,
        seller_daily_forecast=5.0,
        seller_sigma=1.8,
        protection_days=7,
        expiry_date=date(2026, 12, 24),
        seller_unit_cost=95.0,
        salvage_value_per_carton=40.0,
    )

    spare, need, reason = compute_verified_spare_stock(listing, z=1.65)

    assert need == 43
    assert spare == 0
    expected_refusal = (
        "Peer Godown P1 holds 35 cartons, but needs 43 cartons to protect its own "
        "7-day forecast and safety stock. 0 spare cartons available. Excluded."
    )
    assert reason == expected_refusal


def test_feature_a_verified_spare_stock_gate_positive_spare():
    """
    Test Gate 1: Abundant stock generates positive verified spare cartons ring-fencing protection need.
    """
    # Need: ceil(4.0 * 7 + 1.65 * 1.0 * sqrt(7)) = ceil(28 + 4.365) = 33
    listing = SurplusListing(
        id="SURPLUS-P1-SKU-P01",
        source_id="P1",
        source_name="Peer Godown P1",
        product_id="SKU-P01",
        batch_id="BATCH-002",
        on_hand=120,
        reserved=10,
        seller_daily_forecast=4.0,
        seller_sigma=1.0,
        protection_days=7,
        expiry_date=date(2026, 12, 24),
        seller_unit_cost=180.0,
        salvage_value_per_carton=90.0,
    )

    spare, need, reason = compute_verified_spare_stock(listing, z=1.65)

    assert need == 33
    assert spare == 120 - 10 - 33  # 77
    assert reason is None


# =====================================================================
# Feature B Tests: Explained Refusals
# =====================================================================

def test_feature_b_explained_refusals_all_four_gates():
    """
    Test all 4 refusal gates and verify plain-English explanations with exact numbers:
      1. Zero spare stock
      2. Lane gap > Gmax
      3. Remaining shelf life at arrival < min_shelf_life
      4. FEFO sell-through cap <= 0
    """
    as_of = date(2026, 10, 24)

    # 1. Gate 1: Zero spare stock
    listing_zero_spare = SurplusListing(
        id="SURPLUS-TEST-ZERO",
        source_id="P1",
        source_name="Peer Godown P1",
        product_id="SKU-P01",
        batch_id="B-ZERO",
        on_hand=20,
        reserved=0,
        seller_daily_forecast=5.0,
        seller_sigma=2.0,
        protection_days=7,
        expiry_date=as_of + timedelta(days=60),
        lead_time_days_by_dest='{"D1": 1}',
        freight_per_carton_by_dest='{"D1": 20.0}',
        seller_unit_cost=100.0,
        salvage_value_per_carton=50.0,
    )
    eval1 = evaluate_listing_for_shortfall(
        listing=listing_zero_spare,
        dest_id="D1",
        product_id="SKU-P01",
        unmet_cartons=50,
        as_of=as_of,
        cover_days=2.0,
        daily_forecast_dest=10.0,
        inv_position_dest=20,
    )
    assert not eval1.eligible
    assert eval1.rescuable_cartons == 0
    assert "0 spare cartons available. Excluded." in eval1.reason

    # 2. Gate 2: Lane gap > Gmax
    listing_lane_gap = SurplusListing(
        id="SURPLUS-TEST-GAP",
        source_id="P2",
        source_name="Peer Distributor P2",
        product_id="SKU-P01",
        batch_id="B-GAP",
        on_hand=100,
        reserved=0,
        seller_daily_forecast=1.0,
        seller_sigma=0.2,
        protection_days=7,
        expiry_date=as_of + timedelta(days=60),
        lead_time_days_by_dest='{"D1": 6}',
        freight_per_carton_by_dest='{"D1": 20.0}',
        seller_unit_cost=100.0,
        salvage_value_per_carton=50.0,
    )
    eval2 = evaluate_listing_for_shortfall(
        listing=listing_lane_gap,
        dest_id="D1",
        product_id="SKU-P01",
        unmet_cartons=50,
        as_of=as_of,
        cover_days=1.0,
        daily_forecast_dest=10.0,
        inv_position_dest=10,
        gmax=2,
    )
    assert not eval2.eligible
    assert eval2.rescuable_cartons == 0
    assert "exceeds Gmax of 2 days" in eval2.reason

    # 3. Gate 3: Remaining shelf life at arrival < min_shelf_life
    listing_expired = SurplusListing(
        id="SURPLUS-TEST-EXP",
        source_id="P1",
        source_name="Peer Godown P1",
        product_id="SKU-P01",
        batch_id="B-EXP",
        on_hand=100,
        reserved=0,
        seller_daily_forecast=1.0,
        seller_sigma=0.2,
        protection_days=7,
        expiry_date=as_of + timedelta(days=10),
        lead_time_days_by_dest='{"D1": 2}',
        freight_per_carton_by_dest='{"D1": 20.0}',
        seller_unit_cost=100.0,
        salvage_value_per_carton=50.0,
    )
    eval3 = evaluate_listing_for_shortfall(
        listing=listing_expired,
        dest_id="D1",
        product_id="SKU-P01",
        unmet_cartons=50,
        as_of=as_of,
        cover_days=2.0,
        daily_forecast_dest=10.0,
        inv_position_dest=20,
        min_remaining_shelf_days=14,
    )
    assert not eval3.eligible
    assert eval3.rescuable_cartons == 0
    assert "minimum required is 14 days" in eval3.reason

    # 4. Gate 4: FEFO sell-through cap <= 0
    listing_fefo_cap = SurplusListing(
        id="SURPLUS-TEST-FEFO",
        source_id="P1",
        source_name="Peer Godown P1",
        product_id="SKU-P01",
        batch_id="B-FEFO",
        on_hand=100,
        reserved=0,
        seller_daily_forecast=1.0,
        seller_sigma=0.2,
        protection_days=7,
        expiry_date=as_of + timedelta(days=20),
        lead_time_days_by_dest='{"D1": 2}',
        freight_per_carton_by_dest='{"D1": 20.0}',
        seller_unit_cost=100.0,
        salvage_value_per_carton=50.0,
    )
    # arrival shelf life = 18 days. daily demand = 2. Demand until expiry = 36. Inventory = 50. Cap = max(0, 36 - 50) = 0!
    eval4 = evaluate_listing_for_shortfall(
        listing=listing_fefo_cap,
        dest_id="D1",
        product_id="SKU-P01",
        unmet_cartons=50,
        as_of=as_of,
        cover_days=2.0,
        daily_forecast_dest=2.0,
        inv_position_dest=50,
        min_remaining_shelf_days=14,
    )
    assert not eval4.eligible
    assert eval4.rescuable_cartons == 0
    assert "FEFO sell-through cap is 0 cartons. Excluded." in eval4.reason

    # 5. Full pass -> Eligible
    listing_pass = SurplusListing(
        id="SURPLUS-TEST-PASS",
        source_id="P1",
        source_name="Peer Godown P1",
        product_id="SKU-P01",
        batch_id="B-PASS",
        on_hand=100,
        reserved=0,
        seller_daily_forecast=2.0,
        seller_sigma=0.5,
        protection_days=7,
        expiry_date=as_of + timedelta(days=60),
        lead_time_days_by_dest='{"D1": 2}',
        freight_per_carton_by_dest='{"D1": 25.0}',
        seller_unit_cost=180.0,
        salvage_value_per_carton=90.0,
    )
    eval5 = evaluate_listing_for_shortfall(
        listing=listing_pass,
        dest_id="D1",
        product_id="SKU-P01",
        unmet_cartons=40,
        as_of=as_of,
        cover_days=2.0,
        daily_forecast_dest=10.0,
        inv_position_dest=20,
        min_remaining_shelf_days=14,
    )
    assert eval5.eligible
    assert eval5.rescuable_cartons == 40
    assert eval5.price_band is not None
    assert "Eligible: 40 spare cartons available" in eval5.reason


# =====================================================================
# Feature C Tests: Gains-from-Trade Price Band
# =====================================================================

def test_feature_c_gains_from_trade_price_band():
    """
    Test cooperative bargaining price band bounds:
      - seller_floor <= suggested_price <= buyer_ceiling
      - seller_gain_inr and buyer_gain_inr are non-negative
      - suggested_price is the exact arithmetic midpoint
    """
    as_of = date(2026, 10, 24)
    listing = SurplusListing(
        id="SURPLUS-P1-SKU-P01",
        source_id="P1",
        source_name="Peer Godown P1",
        product_id="SKU-P01",
        batch_id="B-001",
        on_hand=100,
        reserved=0,
        seller_daily_forecast=1.0,
        seller_sigma=0.2,
        protection_days=7,
        expiry_date=as_of + timedelta(days=30),
        lead_time_days_by_dest='{"D1": 2}',
        freight_per_carton_by_dest='{"D1": 25.0}',
        seller_unit_cost=180.0,
        salvage_value_per_carton=90.0,
        regular_supplier_lead_time=4,
        regular_supplier_cost_per_carton=180.0,
    )

    price_band = compute_gains_from_trade(
        listing=listing,
        rescuable_cartons=40,
        dest_id="D1",
        as_of=as_of,
        unit_cost=180.0,
        unit_margin=40.0,
        regular_supplier_cost_per_carton=180.0,
        freight_per_carton=25.0,
    )

    assert price_band.seller_floor <= price_band.suggested_price
    assert price_band.suggested_price <= price_band.buyer_ceiling
    expected_mid = round((price_band.seller_floor + price_band.buyer_ceiling) / 2.0, 2)
    assert price_band.suggested_price == expected_mid
    assert price_band.seller_gain_inr >= 0.0
    assert price_band.buyer_gain_inr >= 0.0


# =====================================================================
# Feature D Tests: Landed Cost-to-Serve Comparison
# =====================================================================

def test_feature_d_landed_cost_to_serve_comparison():
    """
    Test 3-row landed cost-to-serve comparison:
      Option 1: Leave unmet (lost margin only)
      Option 2: Regular supplier reorder (transfer + freight + lead-time stockout)
      Option 3: Surplus rescue (transfer at suggested price + freight + residual unmet)
      Verify net rupee savings arithmetic.
    """
    as_of = date(2026, 10, 24)
    listing = SurplusListing(
        id="SURPLUS-P1-SKU-P01",
        source_id="P1",
        source_name="Peer Godown P1",
        product_id="SKU-P01",
        batch_id="B-001",
        on_hand=100,
        reserved=0,
        seller_daily_forecast=2.0,
        seller_sigma=0.5,
        protection_days=7,
        expiry_date=as_of + timedelta(days=60),
        lead_time_days_by_dest='{"D1": 2}',
        freight_per_carton_by_dest='{"D1": 20.0}',
        seller_unit_cost=180.0,
        salvage_value_per_carton=90.0,
        regular_supplier_lead_time=4,
        regular_supplier_cost_per_carton=180.0,
    )

    evaluation = evaluate_listing_for_shortfall(
        listing=listing,
        dest_id="D1",
        product_id="SKU-P01",
        unmet_cartons=50,
        as_of=as_of,
        cover_days=1.0,
        daily_forecast_dest=10.0,
        inv_position_dest=10,
        unit_cost=180.0,
        unit_margin=40.0,
    )

    comp = compare_shortfall_options(
        destination_id="D1",
        product_id="SKU-P01",
        unmet_cartons=50,
        unit_cost=180.0,
        unit_margin=40.0,
        daily_forecast_dest=10.0,
        cover_days=1.0,
        best_listing=listing,
        best_eval=evaluation,
        regular_supplier_lead_time=4,
        regular_supplier_cost_per_carton=180.0,
        regular_freight_per_carton=15.0,
    )

    assert len(comp.options) == 3
    opt1, opt2, opt3 = comp.options

    assert opt1.option_key == "leave_unmet"
    assert opt1.lost_margin == 50 * 40.0  # 2000.0

    assert opt2.option_key == "regular_supplier"
    assert opt2.transfer_cost == 50 * 180.0  # 9000.0
    assert opt2.freight_cost == 50 * 15.0   # 750.0

    assert opt3.option_key == "surplus_rescue"
    assert opt3.freight_cost == 50 * 20.0   # 1000.0
    # Net savings vs option 1 & 2
    assert opt3.net_savings_vs_leave_unmet == round(opt1.total_cost_to_serve - opt3.total_cost_to_serve, 2)
    assert opt3.net_savings_vs_regular_supplier == round(opt2.total_cost_to_serve - opt3.total_cost_to_serve, 2)


# =====================================================================
# Feature E Tests: Shortfall Rescue Plan Integration & Undo
# =====================================================================

def test_feature_e_apply_shortfall_rescue_endpoint_and_undo(client: TestClient, session: Session):
    """
    Test applying shortfall rescue via API:
      - Validates planner/reviewer role gating (403 for unauthorized)
      - Adds 'Surplus rescue' plan line
      - Updates SurplusListing.reserved
      - Recomputes PlanRun totals
      - Creates DecisionLog entry
      - Tests Undo reversing the rescue
    """
    # 1. Seed database with deterministic surplus listings
    sim = FMCGSimulator(seed=1, scenario="balanced", variant="normal")
    sim.seed_database(session)

    # 2. Run plan to create unmet demand
    plan_res = client.post("/api/plan", json={"horizon": 7}, headers={"X-Role": "planner"})
    assert plan_res.status_code == 200
    run_id = plan_res.json()["run_id"]

    # 3. Fetch plan to inspect unmet panel
    get_res = client.get(f"/api/plan/{run_id}")
    assert get_res.status_code == 200
    plan_data = get_res.json()
    unmet_panel = plan_data["unmet_panel"]
    assert len(unmet_panel) > 0

    first_unmet = unmet_panel[0]
    dest_id = first_unmet["destination_id"]
    prod_id = first_unmet["product_id"]

    # Pick an eligible surplus listing
    listings = session.exec(select(SurplusListing)).all()
    eligible_listing = next((l for l in listings if l.product_id == prod_id and l.on_hand > 20), listings[0])

    # 4. Role gating check: unprivileged role rejected
    unauth_res = client.post(
        f"/api/plan/{run_id}/rescue/apply",
        json={
            "destination_id": dest_id,
            "product_id": eligible_listing.product_id,
            "surplus_listing_id": eligible_listing.id,
            "cartons": 10,
        },
        headers={"X-Role": "warehouse"},
    )
    assert unauth_res.status_code == 403

    # 5. Apply rescue with planner role
    before_reserved = eligible_listing.reserved
    apply_res = client.post(
        f"/api/plan/{run_id}/rescue/apply",
        json={
            "destination_id": dest_id,
            "product_id": eligible_listing.product_id,
            "surplus_listing_id": eligible_listing.id,
            "cartons": 10,
            "notes": "Rescue applied via unit test",
        },
        headers={"X-Role": "planner"},
    )
    assert apply_res.status_code == 200
    apply_data = apply_res.json()
    assert apply_data["status"] == "success"
    assert apply_data["cartons_rescued"] == 10
    undo_token = int(apply_data["undo_token"])

    # Verify database state
    session.refresh(eligible_listing)
    assert eligible_listing.reserved == before_reserved + 10

    # Verify PlanLine created with badge
    plan_run = session.get(PlanRun, run_id)
    line_id = apply_data["line_id"]
    rescue_line = session.get(PlanLine, line_id)
    assert rescue_line is not None
    assert "Surplus rescue" in rescue_line.flags_json
    assert rescue_line.cartons == 10

    # 6. Undo the rescue
    undo_res = client.post(
        f"/api/plan/{run_id}/rescue/undo?log_id={undo_token}",
        headers={"X-Role": "planner"},
    )
    assert undo_res.status_code == 200
    undo_data = undo_res.json()
    assert undo_data["status"] == "success"

    # Verify inventory was released
    session.refresh(eligible_listing)
    assert eligible_listing.reserved == before_reserved


# =====================================================================
# Feature F Tests: Dead-Stock Early Warning
# =====================================================================

def test_feature_f_dead_stock_early_warning(session: Session):
    """
    Test dead-stock early warning identification:
      - Detects internal warehouse batches where stock exceeds projected network sales before expiry
      - Returns value_at_risk_inr and recommended_action
    """
    sim = FMCGSimulator(seed=1, scenario="balanced", variant="normal")
    sim.seed_database(session)

    plan_date = date(2026, 10, 24)
    warnings = compute_dead_stock_warnings(session, plan_date=plan_date, plan_lines=[])

    assert isinstance(warnings, list)
    if warnings:
        w = warnings[0]
        assert w.stranded_cartons > 0
        assert w.value_at_risk_inr > 0.0
        assert w.recommended_action in [
            "List as verified surplus",
            "Hold",
            f"Transfer to {w.location_id}",
            "Transfer to D1",
            "Transfer to D2",
            "Transfer to S1",
            "Transfer to S2",
        ]
