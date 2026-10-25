"""
VyaparMitra - Surplus Rescue & Dead-Stock Intelligence Service
Team Stark | Triwizathon 2026 | PS2: Distribution Intelligence and Inventory Optimization Engine

Pure, deterministic business logic implementing:
  Feature A: Verified Spare Stock Gate (ring-fenced seller protection)
  Feature B: Explained Refusals (transparent 4-gate constraint filtering)
  Feature C: Gains-from-Trade Price Band (cooperative bargaining bounds)
  Feature D: Landed Cost-to-Serve Comparison (3-way economic analysis)
  Feature E: Shortfall Rescue Plan Integration & Decision Log Audit
  Feature F: Dead-Stock Early Warning (network-wide expiry risk detector)
"""

from datetime import date as dt_date, datetime as dt_datetime, timedelta, timezone
import json
import math
from typing import Any, Dict, List, Optional, Tuple
from sqlmodel import Session, func, select

from backend.app.models import (
    Batch,
    DecisionLog,
    Location,
    PlanLine,
    PlanRun,
    Product,
    SurplusListing,
)
from backend.app.schemas import (
    DeadStockWarningRead,
    GainsFromTradeRead,
    LandedCostComparisonOption,
    LandedCostComparisonRead,
    ShortfallRescueAnalysisRead,
    SurplusSourceEvaluation,
)


# =====================================================================
# Feature A: Verified Spare Stock Gate
# =====================================================================

def compute_verified_spare_stock(
    listing: SurplusListing,
    z: float = 1.65,
) -> Tuple[int, int, Optional[str]]:
    """
    Compute verified spare cartons ring-fencing seller's own forecast and safety stock.
    Formula:
      seller_protected_need = ceil(seller_daily_forecast * protection_days + z * seller_sigma * sqrt(protection_days))
      verified_spare_cartons = max(0, on_hand - reserved - seller_protected_need)

    Returns:
      (verified_spare_cartons, seller_protected_need, refusal_reason)
    """
    days = max(1, listing.protection_days)
    safety_component = z * listing.seller_sigma * math.sqrt(days)
    seller_protected_need = math.ceil(listing.seller_daily_forecast * days + safety_component)
    available_before_protection = max(0, listing.on_hand - listing.reserved)
    verified_spare_cartons = max(0, available_before_protection - seller_protected_need)

    refusal_reason: Optional[str] = None
    if listing.on_hand > 0 and verified_spare_cartons == 0:
        refusal_reason = (
            f"{listing.source_name} holds {listing.on_hand} cartons, but needs {seller_protected_need} "
            f"cartons to protect its own {listing.protection_days}-day forecast and safety stock. "
            f"0 spare cartons available. Excluded."
        )
    elif listing.on_hand <= 0:
        refusal_reason = f"{listing.source_name} holds 0 cartons on hand. Excluded."

    return verified_spare_cartons, seller_protected_need, refusal_reason


# =====================================================================
# Feature C: Gains-from-Trade Price Band
# =====================================================================

def compute_gains_from_trade(
    listing: SurplusListing,
    rescuable_cartons: int,
    dest_id: str,
    as_of: dt_date,
    unit_cost: float,
    unit_margin: float,
    regular_supplier_cost_per_carton: Optional[float] = None,
    freight_per_carton: Optional[float] = None,
) -> GainsFromTradeRead:
    """
    Compute cooperative bargaining price band [seller_floor, buyer_ceiling] and fair midpoint.
    Seller floor: weighted break-even between salvage value (stranded) and seller unit cost (non-stranded).
    Buyer ceiling: min(regular supplier cost + avoided lost margin, unit cost + unit margin) - freight.
    """
    days_to_expiry = max(0, (listing.expiry_date - as_of).days)
    seller_expected_sales = math.floor(listing.seller_daily_forecast * days_to_expiry)

    verified_spare, _, _ = compute_verified_spare_stock(listing)
    projected_stranded_units = max(0, verified_spare - seller_expected_sales)

    Q = max(1, rescuable_cartons)
    stranded_in_trade = min(Q, projected_stranded_units)
    non_stranded_in_trade = Q - stranded_in_trade

    seller_floor_raw = (
        (stranded_in_trade * listing.salvage_value_per_carton)
        + (non_stranded_in_trade * listing.seller_unit_cost)
    ) / float(Q)
    seller_floor = round(max(0.0, seller_floor_raw), 2)

    freight = freight_per_carton
    if freight is None:
        freight = listing.get_freight_dict().get(dest_id, 0.0)

    reg_cost = regular_supplier_cost_per_carton
    if reg_cost is None:
        reg_cost = listing.regular_supplier_cost_per_carton or unit_cost

    avoided_lead_time_lost_margin = unit_margin
    retail_value = unit_cost + unit_margin
    buyer_max_val = min(reg_cost + avoided_lead_time_lost_margin, retail_value)
    buyer_ceiling = round(max(seller_floor, buyer_max_val - freight), 2)

    suggested_price = round((seller_floor + buyer_ceiling) / 2.0, 2)
    seller_gain_inr = round(rescuable_cartons * max(0.0, suggested_price - seller_floor), 2)
    buyer_gain_inr = round(rescuable_cartons * max(0.0, buyer_ceiling - suggested_price), 2)

    return GainsFromTradeRead(
        seller_floor=seller_floor,
        buyer_ceiling=buyer_ceiling,
        suggested_price=suggested_price,
        seller_gain_inr=seller_gain_inr,
        buyer_gain_inr=buyer_gain_inr,
        rescuable_cartons=rescuable_cartons,
    )


# =====================================================================
# Feature B: Explained Refusals
# =====================================================================

def evaluate_listing_for_shortfall(
    listing: SurplusListing,
    dest_id: str,
    product_id: str,
    unmet_cartons: int,
    as_of: dt_date,
    cover_days: float,
    daily_forecast_dest: float,
    inv_position_dest: int,
    min_remaining_shelf_days: int = 14,
    gmax: int = 2,
    z: float = 1.65,
    unit_cost: float = 100.0,
    unit_margin: float = 20.0,
) -> SurplusSourceEvaluation:
    """
    Evaluate candidate surplus listing against 4 sequential FMCG gates:
      Gate 1: Verified Spare Stock Gate (ring-fencing seller needs)
      Gate 2: Lane gap G = max(0, L_sd - cover_d) <= Gmax
      Gate 3: Remaining shelf life at arrival >= min_remaining_shelf_days
      Gate 4: FEFO sell-through cap = max(0, floor(daily_forecast_dest * days_to_expiry_at_arrival - inv_pos))
    """
    lead_time_dict = listing.get_lead_time_dict()
    freight_dict = listing.get_freight_dict()
    L_sd = lead_time_dict.get(dest_id, 99)
    freight_per_carton = freight_dict.get(dest_id, 0.0)

    # 1. Gate 1: Verified Spare Stock Gate
    verified_spare, protected_need, spare_reason = compute_verified_spare_stock(listing, z=z)
    if verified_spare <= 0:
        return SurplusSourceEvaluation(
            listing_id=listing.id,
            source_id=listing.source_id,
            source_name=listing.source_name,
            batch_id=listing.batch_id,
            eligible=False,
            on_hand=listing.on_hand,
            seller_protected_need=protected_need,
            verified_spare_cartons=verified_spare,
            rescuable_cartons=0,
            reason=spare_reason or f"{listing.source_name} has 0 verified spare cartons. Excluded.",
            price_band=None,
            lead_time_days=L_sd,
            freight_per_carton=freight_per_carton,
        )

    # 2. Gate 2: Transit Lane Availability & Lead-time Gap
    if dest_id not in lead_time_dict:
        return SurplusSourceEvaluation(
            listing_id=listing.id,
            source_id=listing.source_id,
            source_name=listing.source_name,
            batch_id=listing.batch_id,
            eligible=False,
            on_hand=listing.on_hand,
            seller_protected_need=protected_need,
            verified_spare_cartons=verified_spare,
            rescuable_cartons=0,
            reason=f"No transit lane exists from {listing.source_name} to {dest_id}. Excluded.",
            price_band=None,
            lead_time_days=L_sd,
            freight_per_carton=freight_per_carton,
        )

    lane_gap = max(0.0, float(L_sd) - float(cover_days))
    if lane_gap > float(gmax):
        return SurplusSourceEvaluation(
            listing_id=listing.id,
            source_id=listing.source_id,
            source_name=listing.source_name,
            batch_id=listing.batch_id,
            eligible=False,
            on_hand=listing.on_hand,
            seller_protected_need=protected_need,
            verified_spare_cartons=verified_spare,
            rescuable_cartons=0,
            reason=(
                f"Transit lead time from {listing.source_name} is {L_sd} days, creating a stockout gap of "
                f"{lane_gap:.1f} days (exceeds Gmax of {gmax} days). Excluded."
            ),
            price_band=None,
            lead_time_days=L_sd,
            freight_per_carton=freight_per_carton,
        )

    # 3. Gate 3: Remaining Shelf Life at Arrival
    days_to_expiry_today = (listing.expiry_date - as_of).days
    days_to_expiry_at_arrival = days_to_expiry_today - L_sd
    if days_to_expiry_at_arrival < min_remaining_shelf_days:
        return SurplusSourceEvaluation(
            listing_id=listing.id,
            source_id=listing.source_id,
            source_name=listing.source_name,
            batch_id=listing.batch_id,
            eligible=False,
            on_hand=listing.on_hand,
            seller_protected_need=protected_need,
            verified_spare_cartons=verified_spare,
            rescuable_cartons=0,
            reason=(
                f"Batch {listing.batch_id} arrives with only {days_to_expiry_at_arrival} days of shelf life "
                f"remaining (minimum required is {min_remaining_shelf_days} days). Excluded."
            ),
            price_band=None,
            lead_time_days=L_sd,
            freight_per_carton=freight_per_carton,
        )

    # 4. Gate 4: FEFO Sell-Through Cap at Destination
    demand_until_expiry = daily_forecast_dest * max(0, days_to_expiry_at_arrival)
    sell_through_cap = max(0, math.floor(demand_until_expiry - inv_position_dest))
    if sell_through_cap <= 0:
        return SurplusSourceEvaluation(
            listing_id=listing.id,
            source_id=listing.source_id,
            source_name=listing.source_name,
            batch_id=listing.batch_id,
            eligible=False,
            on_hand=listing.on_hand,
            seller_protected_need=protected_need,
            verified_spare_cartons=verified_spare,
            rescuable_cartons=0,
            reason=(
                f"Destination {dest_id} current stock ({inv_position_dest} cartons) exceeds demand before expiry "
                f"({math.floor(demand_until_expiry)} cartons). FEFO sell-through cap is 0 cartons. Excluded."
            ),
            price_band=None,
            lead_time_days=L_sd,
            freight_per_carton=freight_per_carton,
        )

    # All gates passed -> Eligible
    rescuable_cartons = min(unmet_cartons, verified_spare, sell_through_cap)
    if rescuable_cartons <= 0:
        return SurplusSourceEvaluation(
            listing_id=listing.id,
            source_id=listing.source_id,
            source_name=listing.source_name,
            batch_id=listing.batch_id,
            eligible=False,
            on_hand=listing.on_hand,
            seller_protected_need=protected_need,
            verified_spare_cartons=verified_spare,
            rescuable_cartons=0,
            reason="Rescuable cartons calculated to 0 under current allocation limits.",
            price_band=None,
            lead_time_days=L_sd,
            freight_per_carton=freight_per_carton,
        )

    price_band = compute_gains_from_trade(
        listing=listing,
        rescuable_cartons=rescuable_cartons,
        dest_id=dest_id,
        as_of=as_of,
        unit_cost=unit_cost,
        unit_margin=unit_margin,
        freight_per_carton=freight_per_carton,
    )

    reason = (
        f"Eligible: {rescuable_cartons} spare cartons available from {listing.source_name} "
        f"(lead time {L_sd}d, arrives with {days_to_expiry_at_arrival}d shelf life)."
    )

    return SurplusSourceEvaluation(
        listing_id=listing.id,
        source_id=listing.source_id,
        source_name=listing.source_name,
        batch_id=listing.batch_id,
        eligible=True,
        on_hand=listing.on_hand,
        seller_protected_need=protected_need,
        verified_spare_cartons=verified_spare,
        rescuable_cartons=rescuable_cartons,
        reason=reason,
        price_band=price_band,
        lead_time_days=L_sd,
        freight_per_carton=freight_per_carton,
    )


# =====================================================================
# Feature D: Landed Cost-to-Serve Comparison
# =====================================================================

def compare_shortfall_options(
    destination_id: str,
    product_id: str,
    unmet_cartons: int,
    unit_cost: float,
    unit_margin: float,
    daily_forecast_dest: float,
    cover_days: float,
    best_listing: Optional[SurplusListing] = None,
    best_eval: Optional[SurplusSourceEvaluation] = None,
    regular_supplier_lead_time: int = 4,
    regular_supplier_cost_per_carton: Optional[float] = None,
    regular_freight_per_carton: float = 12.0,
) -> LandedCostComparisonRead:
    """
    Return 3-row landed cost-to-serve comparison in rupees:
      1. Leave unmet: transport ₹0, lost margin U * unit_margin, total cost-to-serve.
      2. Regular supplier reorder: transfer cost, freight, lead-time gap lost sales while waiting.
      3. Shortfall rescue: transfer cost (at suggested price), freight, residual unmet margin.
    """
    U = max(0, unmet_cartons)
    reg_unit_cost = regular_supplier_cost_per_carton or unit_cost

    # 1. Option 1: Leave unmet
    lost_margin_unmet = round(U * unit_margin, 2)
    opt1 = LandedCostComparisonOption(
        option_key="leave_unmet",
        title="Leave unmet",
        transfer_cost=0.0,
        freight_cost=0.0,
        lost_margin=lost_margin_unmet,
        total_cost_to_serve=lost_margin_unmet,
    )

    # 2. Option 2: Regular supplier reorder
    reg_gap = max(0.0, float(regular_supplier_lead_time) - float(cover_days))
    reg_lost_sales_cartons = min(U, math.ceil(daily_forecast_dest * reg_gap))
    reg_lost_margin = round(reg_lost_sales_cartons * unit_margin, 2)
    reg_transfer_cost = round(U * reg_unit_cost, 2)
    reg_freight_cost = round(U * regular_freight_per_carton, 2)
    reg_total_cost = round(reg_transfer_cost + reg_freight_cost + reg_lost_margin, 2)

    opt2 = LandedCostComparisonOption(
        option_key="regular_supplier",
        title=f"Regular supplier reorder ({regular_supplier_lead_time}d lead time)",
        transfer_cost=reg_transfer_cost,
        freight_cost=reg_freight_cost,
        lost_margin=reg_lost_margin,
        total_cost_to_serve=reg_total_cost,
    )

    # 3. Option 3: Shortfall rescue (best surplus source)
    if best_listing and best_eval and best_eval.eligible and best_eval.price_band:
        Q = min(U, best_eval.rescuable_cartons)
        residual_unmet = max(0, U - Q)
        transfer_cost = round(Q * best_eval.price_band.suggested_price, 2)
        freight_cost = round(Q * best_eval.freight_per_carton, 2)
        lost_margin_residual = round(residual_unmet * unit_margin, 2)
        rescue_total_cost = round(transfer_cost + freight_cost + lost_margin_residual, 2)

        opt3 = LandedCostComparisonOption(
            option_key="surplus_rescue",
            title=f"Shortfall rescue ({best_eval.source_name})",
            transfer_cost=transfer_cost,
            freight_cost=freight_cost,
            lost_margin=lost_margin_residual,
            total_cost_to_serve=rescue_total_cost,
            net_savings_vs_leave_unmet=round(opt1.total_cost_to_serve - rescue_total_cost, 2),
            net_savings_vs_regular_supplier=round(opt2.total_cost_to_serve - rescue_total_cost, 2),
        )
    else:
        opt3 = LandedCostComparisonOption(
            option_key="surplus_rescue",
            title="Shortfall rescue (No eligible peer stock)",
            transfer_cost=0.0,
            freight_cost=0.0,
            lost_margin=lost_margin_unmet,
            total_cost_to_serve=lost_margin_unmet,
            net_savings_vs_leave_unmet=0.0,
            net_savings_vs_regular_supplier=0.0,
        )

    options = [opt1, opt2, opt3]
    # Pick lowest cost-to-serve as best option
    best_opt = min(options, key=lambda o: o.total_cost_to_serve)

    return LandedCostComparisonRead(
        destination_id=destination_id,
        product_id=product_id,
        unmet_cartons=U,
        options=options,
        best_option=best_opt.option_key,
    )


# =====================================================================
# Feature E: Shortfall Rescue Analysis & Plan Action
# =====================================================================

def build_rescue_analysis_for_unmet(
    destination_id: str,
    product_id: str,
    unmet_cartons: int,
    listings: List[SurplusListing],
    as_of: dt_date,
    cover_days: float,
    daily_forecast_dest: float,
    inv_position_dest: int,
    unit_cost: float,
    unit_margin: float,
    min_remaining_shelf_days: int = 14,
    gmax: int = 2,
    z: float = 1.65,
) -> ShortfallRescueAnalysisRead:
    """
    Evaluate all surplus listings for product_id and destination_id,
    rank candidates, pick best rescue source, and build full 3-way landed cost comparison.
    """
    matching_listings = [l for l in listings if l.product_id == product_id]
    evaluations: List[SurplusSourceEvaluation] = []

    for listing in matching_listings:
        evaluation = evaluate_listing_for_shortfall(
            listing=listing,
            dest_id=destination_id,
            product_id=product_id,
            unmet_cartons=unmet_cartons,
            as_of=as_of,
            cover_days=cover_days,
            daily_forecast_dest=daily_forecast_dest,
            inv_position_dest=inv_position_dest,
            min_remaining_shelf_days=min_remaining_shelf_days,
            gmax=gmax,
            z=z,
            unit_cost=unit_cost,
            unit_margin=unit_margin,
        )
        evaluations.append(evaluation)

    eligible_evals = [e for e in evaluations if e.eligible and e.rescuable_cartons > 0 and e.price_band]
    best_eval: Optional[SurplusSourceEvaluation] = None
    best_listing: Optional[SurplusListing] = None

    if eligible_evals:
        # Sort by buyer savings / landed cost: lowest (suggested_price + freight) first
        listing_lookup = {l.id: l for l in matching_listings}
        best_eval = min(
            eligible_evals,
            key=lambda e: (
                (e.price_band.suggested_price if e.price_band else 9999.0) + e.freight_per_carton,
                -e.rescuable_cartons,
            ),
        )
        best_listing = listing_lookup.get(best_eval.listing_id)

    cost_comparison = compare_shortfall_options(
        destination_id=destination_id,
        product_id=product_id,
        unmet_cartons=unmet_cartons,
        unit_cost=unit_cost,
        unit_margin=unit_margin,
        daily_forecast_dest=daily_forecast_dest,
        cover_days=cover_days,
        best_listing=best_listing,
        best_eval=best_eval,
        regular_supplier_lead_time=best_listing.regular_supplier_lead_time if best_listing else 4,
        regular_supplier_cost_per_carton=best_listing.regular_supplier_cost_per_carton if best_listing else unit_cost,
    )

    return ShortfallRescueAnalysisRead(
        destination_id=destination_id,
        product_id=product_id,
        unmet_cartons=unmet_cartons,
        sources_considered=evaluations,
        best_rescue_source=best_eval,
        cost_comparison=cost_comparison,
    )


def apply_shortfall_rescue(
    session: Session,
    run_id: str,
    destination_id: str,
    product_id: str,
    surplus_listing_id: str,
    cartons: Optional[int] = None,
    actor_role: str = "planner",
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Apply a verified surplus rescue allocation to an existing PlanRun:
      - Validates listing availability and verified spare stock
      - Creates or updates a PlanLine with badge 'Surplus rescue'
      - Reserves stock on SurplusListing
      - Recomputes PlanRun totals (cartons, unmet, cost)
      - Appends audit entry into DecisionLog with Undo payload
    """
    plan_run = session.get(PlanRun, run_id)
    if not plan_run:
        raise ValueError(f"PlanRun '{run_id}' not found.")

    listing = session.get(SurplusListing, surplus_listing_id)
    if not listing:
        raise ValueError(f"SurplusListing '{surplus_listing_id}' not found.")

    verified_spare, _, refusal_reason = compute_verified_spare_stock(listing)
    if verified_spare <= 0:
        raise ValueError(f"Cannot rescue: {refusal_reason or 'No verified spare cartons available.'}")

    cartons_to_rescue = min(verified_spare, cartons) if cartons is not None else verified_spare
    if cartons_to_rescue <= 0:
        raise ValueError("Cartons to rescue must be at least 1.")

    product = session.get(Product, product_id)
    unit_cost = product.unit_cost if product else listing.seller_unit_cost
    unit_margin = product.unit_margin if product else 20.0

    # Pricing & Freight
    freight_per_carton = listing.get_freight_dict().get(destination_id, 15.0)
    lead_time = listing.get_lead_time_dict().get(destination_id, 2)
    arrival_date = plan_run.planning_date + timedelta(days=lead_time)

    price_band = compute_gains_from_trade(
        listing=listing,
        rescuable_cartons=cartons_to_rescue,
        dest_id=destination_id,
        as_of=plan_run.planning_date,
        unit_cost=unit_cost,
        unit_margin=unit_margin,
        freight_per_carton=freight_per_carton,
    )

    line_cost = round(cartons_to_rescue * freight_per_carton, 2)
    line_id = f"LINE-RESCUE-{run_id}-{product_id}-{destination_id}"

    existing_line = session.get(PlanLine, line_id)
    prev_line_cartons = existing_line.cartons if existing_line else 0
    delta_cartons = cartons_to_rescue - prev_line_cartons

    if existing_line:
        existing_line.cartons = cartons_to_rescue
        existing_line.cost = line_cost
        existing_line.flags_json = json.dumps([
            "Surplus rescue",
            f"Source: {listing.source_name}",
            f"Transfer: ₹{price_band.suggested_price}/ctn",
            f"Buyer Gain: ₹{price_band.buyer_gain_inr}",
        ])
        existing_line.status = "APPROVED"
        session.add(existing_line)
    else:
        new_line = PlanLine(
            id=line_id,
            run_id=run_id,
            product_id=product_id,
            source_id=listing.source_id,
            destination_id=destination_id,
            batch_id=listing.batch_id,
            cartons=cartons_to_rescue,
            cost=line_cost,
            arrival_date=arrival_date,
            flags_json=json.dumps([
                "Surplus rescue",
                f"Source: {listing.source_name}",
                f"Transfer: ₹{price_band.suggested_price}/ctn",
                f"Buyer Gain: ₹{price_band.buyer_gain_inr}",
            ]),
            status="APPROVED",
            is_simulated=True,
        )
        session.add(new_line)

    # Reserve inventory on listing
    listing.reserved += delta_cartons
    session.add(listing)

    # Update PlanRun totals
    plan_run.total_cartons += delta_cartons
    plan_run.total_cost += round(delta_cartons * freight_per_carton, 2)
    plan_run.total_unmet_cartons = max(0, plan_run.total_unmet_cartons - delta_cartons)
    session.add(plan_run)

    # Audit Log
    undo_payload = {
        "run_id": run_id,
        "line_id": line_id,
        "surplus_listing_id": surplus_listing_id,
        "cartons_rescued": cartons_to_rescue,
        "delta_cartons": delta_cartons,
        "previous_line_cartons": prev_line_cartons,
    }
    decision_log = DecisionLog(
        run_id=run_id,
        line_id=line_id,
        actor_role=actor_role,
        action="APPLY_RESCUE",
        previous_cartons=prev_line_cartons,
        new_cartons=cartons_to_rescue,
        delta_cartons=delta_cartons,
        reason=notes or f"Applied shortfall rescue of {cartons_to_rescue} cartons from {listing.source_name}",
        note=json.dumps(undo_payload),
        timestamp=dt_datetime.now(timezone.utc),
    )
    session.add(decision_log)
    session.commit()

    return {
        "status": "success",
        "action": "APPLY_RESCUE",
        "run_id": run_id,
        "line_id": line_id,
        "cartons_rescued": cartons_to_rescue,
        "source_name": listing.source_name,
        "suggested_price": price_band.suggested_price,
        "buyer_gain_inr": price_band.buyer_gain_inr,
        "seller_gain_inr": price_band.seller_gain_inr,
        "undo_token": str(decision_log.id),
    }


def undo_shortfall_rescue(
    session: Session,
    log_id: int,
    actor_role: str = "planner",
) -> Dict[str, Any]:
    """
    Undo a previously applied shortfall rescue using its DecisionLog entry.
    """
    log_entry = session.get(DecisionLog, log_id)
    if not log_entry or log_entry.action != "APPLY_RESCUE" or not log_entry.note:
        raise ValueError(f"DecisionLog entry '{log_id}' is not a reversible rescue action.")

    undo_payload = json.loads(log_entry.note)
    run_id = undo_payload["run_id"]
    line_id = undo_payload["line_id"]
    surplus_listing_id = undo_payload["surplus_listing_id"]
    delta_cartons = undo_payload["delta_cartons"]
    prev_line_cartons = undo_payload.get("previous_line_cartons", 0)

    listing = session.get(SurplusListing, surplus_listing_id)
    if listing:
        listing.reserved = max(0, listing.reserved - delta_cartons)
        session.add(listing)

    plan_run = session.get(PlanRun, run_id)
    line = session.get(PlanLine, line_id)

    if line:
        if prev_line_cartons <= 0:
            session.delete(line)
        else:
            line.cartons = prev_line_cartons
            session.add(line)

    if plan_run:
        plan_run.total_cartons = max(0, plan_run.total_cartons - delta_cartons)
        plan_run.total_unmet_cartons += delta_cartons
        session.add(plan_run)

    undo_log = DecisionLog(
        run_id=run_id,
        line_id=line_id,
        actor_role=actor_role,
        action="UNDO_RESCUE",
        previous_cartons=undo_payload["cartons_rescued"],
        new_cartons=prev_line_cartons,
        delta_cartons=-delta_cartons,
        reason=f"Reversed shortfall rescue of {undo_payload['cartons_rescued']} cartons",
        timestamp=dt_datetime.now(timezone.utc),
    )
    session.add(undo_log)
    session.commit()

    return {
        "status": "success",
        "action": "UNDO_RESCUE",
        "run_id": run_id,
        "line_id": line_id,
        "reversed_cartons": delta_cartons,
    }


# =====================================================================
# Feature F: Dead-Stock Early Warning
# =====================================================================

def compute_dead_stock_warnings(
    session: Session,
    plan_date: dt_date,
    plan_lines: Optional[List[PlanLine]] = None,
) -> List[DeadStockWarningRead]:
    """
    Identify internal warehouse batches where unshipped_cartons > 0 after planning
    and projected network sales before expiry leave stranded_cartons > 0.
    Returns:
      List[DeadStockWarningRead] with recommended action ('Transfer to {dest}', 'List as verified surplus', or 'Hold').
    """
    batches = session.exec(select(Batch)).all()
    products = {p.id: p for p in session.exec(select(Product)).all()}
    destinations = session.exec(select(Location).where(Location.type != "warehouse")).all()

    # Pre-calculate allocated cartons per batch from plan lines
    allocated_map: Dict[str, int] = {}
    if plan_lines:
        for line in plan_lines:
            allocated_map[line.batch_id] = allocated_map.get(line.batch_id, 0) + line.cartons

    # Pre-calculate network daily forecast per product
    from backend.app.models import SalesDaily
    recent_sales = session.exec(
        select(
            SalesDaily.product_id,
            SalesDaily.location_id,
            func.avg(SalesDaily.units).label("avg_units")
        )
        .where(SalesDaily.date >= plan_date - timedelta(days=28))
        .group_by(SalesDaily.product_id, SalesDaily.location_id)
    ).all()

    daily_network_sales_by_prod: Dict[str, float] = {}
    for prod_id, _, avg_units in recent_sales:
        daily_network_sales_by_prod[prod_id] = daily_network_sales_by_prod.get(prod_id, 0.0) + (avg_units or 0.0)

    warnings: List[DeadStockWarningRead] = []

    for batch in batches:
        # Check warehouse batches
        allocated = allocated_map.get(batch.id, 0)
        unshipped_cartons = max(0, batch.quantity - allocated)
        if unshipped_cartons <= 0:
            continue

        days_to_expiry = (batch.expiry_date - plan_date).days
        if days_to_expiry < 0:
            days_to_expiry = 0

        prod = products.get(batch.product_id)
        prod_name = prod.name if prod else batch.product_id
        unit_cost = prod.unit_cost if prod else 50.0

        daily_network_sales = daily_network_sales_by_prod.get(batch.product_id, 5.0)
        projected_network_sales = math.floor(daily_network_sales * float(days_to_expiry))

        stranded_cartons = max(0, unshipped_cartons - projected_network_sales)
        if stranded_cartons > 0:
            value_at_risk_inr = round(stranded_cartons * unit_cost, 2)

            # Recommend action:
            # If days to expiry < 45, recommend surplus listing; if long expiry, hold; or transfer to destination with highest share
            if days_to_expiry <= 45:
                recommended_action = "List as verified surplus"
            elif destinations:
                recommended_action = f"Transfer to {destinations[0].id}"
            else:
                recommended_action = "Hold"

            warnings.append(
                DeadStockWarningRead(
                    batch_id=batch.id,
                    location_id=batch.location_id,
                    product_id=batch.product_id,
                    product_name=prod_name,
                    days_to_expiry=days_to_expiry,
                    expiry_date=batch.expiry_date,
                    unshipped_cartons=unshipped_cartons,
                    projected_network_sales=projected_network_sales,
                    stranded_cartons=stranded_cartons,
                    value_at_risk_inr=value_at_risk_inr,
                    recommended_action=recommended_action,
                )
            )

    # Sort by value at risk descending
    warnings.sort(key=lambda w: w.value_at_risk_inr, reverse=True)
    return warnings
