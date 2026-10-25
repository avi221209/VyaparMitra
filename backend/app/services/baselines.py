"""
VyaparMitra - Benchmark Dispatch Baselines and Methods
Distribution Planning and Inventory Optimization Engine

Implements identical input dispatch policies:
  A    Min/Max Policy: Refill each destination up to fixed max from nearest warehouse;
       no forecast, no shelf-life awareness; published settings; truncated to physical limits.
  B    Proportional Split: Divide warehouse stock across destinations in proportion to last 14 days of sales;
       truncated to physical limits.
  C    Forecast + Greedy Heuristic: Same forecast and requirement as V; lowest cover first,
       nearest eligible source, FEFO batch selection; no optimizer.
  V    VyaparMitra Full Pipeline: Forecast + requirement + eligibility + two-stage PuLP optimizer.
  V-SS V with Safety Stock zero (z=0, Ntot = Ndem).
  V-SL V without Shelf-Life Rules (Eshort=0, FEFO caps disabled).
  O    True-Demand Oracle: Perfect foresight of realized 7-day demand (no safety stock). Upper bound.
"""

from copy import deepcopy
from dataclasses import dataclass
from datetime import date as dt_date, timedelta
import math
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from backend.app.models import Location, Product, Settings
from backend.app.services.eligibility import (
    BatchEligibilityResult,
    BatchInfo,
    LaneData,
    ProductInfo,
    evaluate_all_batches_eligibility,
)
from backend.app.services.forecast import ForecastService
from backend.app.services.optimizer import (
    AllocationLine,
    OptimizationResult,
    run_greedy_heuristic,
    solve_two_stage_optimization,
)
from backend.app.services.requirement import (
    LaneInfo,
    NetRequirement,
    compute_all_net_requirements,
    compute_net_requirement,
)


# Published Settings for Baseline A
BASELINE_A_SETTINGS: Dict[str, Any] = {
    "name": "Min/Max Refill Policy",
    "target_cover_days": 10,
    "min_cover_days": 3,
    "default_sources": {
        "D1": "W1",  # Metro Distributor East -> North Central Hub
        "D2": "W2",  # Central Wholesale Agency -> Western Mother DC
        "S1": "W2",  # South Retail Flagship -> Western Mother DC
        "S2": "W2",  # Suburban Retail Mart -> Western Mother DC
    },
    "shelf_life_aware": False,
    "forecast_aware": False,
}

# Published Settings for Baseline B
BASELINE_B_SETTINGS: Dict[str, Any] = {
    "name": "Proportional Sales Split",
    "lookback_days": 14,
    "shelf_life_aware": False,
    "forecast_aware": False,
}


def build_pure_domain_objects(
    products: List[Product],
    lanes: List[Any],
    batches: List[Any],
    plan_date: dt_date,
) -> Tuple[Dict[str, ProductInfo], List[LaneData], List[BatchInfo]]:
    """Convert DB / Simulator models into pure dataclasses used by engine."""
    products_pure = {
        p.id: ProductInfo(
            id=p.id,
            name=p.name,
            category=p.category,
            case_pack=p.case_pack,
            min_remaining_shelf_days=p.min_remaining_shelf_days,
            load_per_carton=p.load_per_carton,
            unit_cost=(p.unit_cost * p.case_pack) if (p.unit_cost and p.unit_cost > 0) else 50.0,
            unit_margin=(p.unit_margin * p.case_pack) if (p.unit_margin and p.unit_margin > 0) else 20.0,
        )
        for p in products
    }

    lanes_pure = [
        LaneData(
            source_id=l.source_id,
            destination_id=l.destination_id,
            lead_time_days=l.lead_time_days,
            cost_per_carton=l.cost_per_carton,
            capacity_load=l.capacity_load,
            distance_km=getattr(l, "distance_km", 0.0) or 0.0,
        )
        for l in lanes
    ]

    batches_pure = [
        BatchInfo(
            id=b.id,
            location_id=b.location_id,
            product_id=b.product_id,
            quantity=b.quantity,
            days_to_expiry_from_dispatch=(b.expiry_date - plan_date).days,
            expiry_date=b.expiry_date,
            cost_per_carton=getattr(b, "cost_per_carton", 50.0),
        )
        for b in batches
    ]

    return products_pure, lanes_pure, batches_pure


# =====================================================================
# Method A: Min/Max Policy
# =====================================================================
def solve_baseline_a(
    plan_date: dt_date,
    destinations: List[Location],
    products: List[Product],
    lanes: List[LaneData],
    batches: List[BatchInfo],
    destination_inventory: Dict[str, Dict[str, float]],
    sales_cache: Dict[Tuple[str, str], pd.Series],
    settings: Optional[Dict[str, Any]] = None,
) -> List[AllocationLine]:
    """
    Baseline A: Min/Max Decentralized Replenishment.
      - Refills each destination up to fixed maximum cover from nearest warehouse.
      - No forecast (uses 14-day historical trailing average sales).
      - No shelf-life awareness (does not check Eshort rejection or shelf-life caps).
      - Truncated to physical batch stock and lane capacity limits.
    """
    cfg = settings or BASELINE_A_SETTINGS
    target_cover = cfg.get("target_cover_days", 10)
    default_sources = cfg.get("default_sources", BASELINE_A_SETTINGS["default_sources"])

    lane_map: Dict[Tuple[str, str], LaneData] = {(l.source_id, l.destination_id): l for l in lanes}
    prod_map: Dict[str, Product] = {p.id: p for p in products}

    # Tracking remaining stock and lane capacity
    batch_remaining: Dict[str, int] = {b.id: b.quantity for b in batches}
    lane_capacity_remaining: Dict[Tuple[str, str], Optional[float]] = {
        (l.source_id, l.destination_id): l.capacity_load for l in lanes
    }

    lines: List[AllocationLine] = []

    # Sort destinations and products deterministically
    sorted_dests = sorted(destinations, key=lambda d: d.id)
    sorted_prods = sorted(products, key=lambda p: p.id)

    for dst in sorted_dests:
        src_wh = default_sources.get(dst.id, "W1")
        lane = lane_map.get((src_wh, dst.id))
        if not lane:
            continue

        lane_key = (src_wh, dst.id)

        for prod in sorted_prods:
            # 1. Trailing 14-day sales average (no forecast)
            series = sales_cache.get((prod.id, dst.id), pd.Series(dtype=float))
            history_14 = series[(series.index < plan_date) & (series.index >= plan_date - timedelta(days=14))]
            total_14_units = float(history_14.sum()) if not history_14.empty else 0.0
            avg_daily_cartons = max(0.1, total_14_units / (14.0 * prod.case_pack))

            # 2. Current inventory position
            pos = destination_inventory.get(dst.id, {}).get(prod.id, 0.0)
            target_cartons = int(math.ceil(target_cover * avg_daily_cartons))
            needed_cartons = max(0, target_cartons - int(pos))

            if needed_cartons <= 0:
                continue

            # 3. Pull batches from default warehouse without shelf-life awareness
            wh_batches = [
                b for b in batches
                if b.location_id == src_wh and b.product_id == prod.id and batch_remaining[b.id] > 0
            ]
            # Baseline A allocates FIFO / earliest expiry first, but without filtering on remaining shelf life
            wh_batches.sort(key=lambda b: (b.expiry_date, b.id))

            for b in wh_batches:
                if needed_cartons <= 0:
                    break

                avail_stock = batch_remaining[b.id]
                if avail_stock <= 0:
                    continue

                # Check lane capacity
                rem_cap = lane_capacity_remaining.get(lane_key)
                if rem_cap is not None:
                    max_cartons_lane = int(rem_cap / prod.load_per_carton)
                    if max_cartons_lane <= 0:
                        break
                    alloc_cartons = min(needed_cartons, avail_stock, max_cartons_lane)
                else:
                    alloc_cartons = min(needed_cartons, avail_stock)

                if alloc_cartons <= 0:
                    continue

                line_cost = round(alloc_cartons * lane.cost_per_carton, 2)
                arrival_date = plan_date + timedelta(days=lane.lead_time_days)

                lines.append(
                    AllocationLine(
                        batch_id=b.id,
                        source_id=src_wh,
                        destination_id=dst.id,
                        product_id=prod.id,
                        cartons=alloc_cartons,
                        cost=line_cost,
                        arrival_date=arrival_date,
                        lead_time_days=lane.lead_time_days,
                        flags=["BASELINE_A", "NO_SHELF_LIFE_CHECK"],
                        explanation={
                            "method": "A",
                            "rule": "Min/Max Refill",
                            "target_cover_days": target_cover,
                            "nearest_warehouse": src_wh,
                        },
                    )
                )

                batch_remaining[b.id] -= alloc_cartons
                if rem_cap is not None:
                    lane_capacity_remaining[lane_key] -= (alloc_cartons * prod.load_per_carton)
                needed_cartons -= alloc_cartons

    return lines


# =====================================================================
# Method B: Proportional Split
# =====================================================================
def solve_baseline_b(
    plan_date: dt_date,
    warehouses: List[Location],
    destinations: List[Location],
    products: List[Product],
    lanes: List[LaneData],
    batches: List[BatchInfo],
    sales_cache: Dict[Tuple[str, str], pd.Series],
    settings: Optional[Dict[str, Any]] = None,
) -> List[AllocationLine]:
    """
    Baseline B: Proportional Split Policy.
      - Divides each warehouse's stock across reachable destinations in proportion to last 14 days of sales.
      - Truncated to physical batch stock and lane capacity limits.
    """
    lane_map: Dict[Tuple[str, str], LaneData] = {(l.source_id, l.destination_id): l for l in lanes}
    prod_map: Dict[str, Product] = {p.id: p for p in products}

    batch_remaining: Dict[str, int] = {b.id: b.quantity for b in batches}
    lane_capacity_remaining: Dict[Tuple[str, str], Optional[float]] = {
        (l.source_id, l.destination_id): l.capacity_load for l in lanes
    }

    lines: List[AllocationLine] = []

    sorted_whs = sorted(warehouses, key=lambda w: w.id)
    sorted_prods = sorted(products, key=lambda p: p.id)

    for wh in sorted_whs:
        # Find reachable destinations from this warehouse
        reachable_dests = [
            d for d in destinations
            if (wh.id, d.id) in lane_map
        ]
        reachable_dests.sort(key=lambda d: d.id)

        if not reachable_dests:
            continue

        for prod in sorted_prods:
            wh_batches = [
                b for b in batches
                if b.location_id == wh.id and b.product_id == prod.id and batch_remaining[b.id] > 0
            ]
            total_wh_stock = sum(batch_remaining[b.id] for b in wh_batches)
            if total_wh_stock <= 0:
                continue

            # Compute last 14 days of sales for each reachable destination
            dest_sales: Dict[str, float] = {}
            for dst in reachable_dests:
                series = sales_cache.get((prod.id, dst.id), pd.Series(dtype=float))
                history_14 = series[(series.index < plan_date) & (series.index >= plan_date - timedelta(days=14))]
                dest_sales[dst.id] = float(history_14.sum()) if not history_14.empty else 0.0

            total_sales = sum(dest_sales.values())

            # Determine desired cartons per destination
            dest_desired_cartons: Dict[str, int] = {}
            for dst in reachable_dests:
                if total_sales > 0:
                    weight = dest_sales[dst.id] / total_sales
                else:
                    weight = 1.0 / len(reachable_dests)
                dest_desired_cartons[dst.id] = int(math.floor(total_wh_stock * weight))

            # Distribute batches in FIFO order to destinations based on desired cartons
            wh_batches.sort(key=lambda b: (b.expiry_date, b.id))

            for dst in reachable_dests:
                needed = dest_desired_cartons[dst.id]
                lane = lane_map[(wh.id, dst.id)]
                lane_key = (wh.id, dst.id)

                for b in wh_batches:
                    if needed <= 0:
                        break
                    avail = batch_remaining[b.id]
                    if avail <= 0:
                        continue

                    rem_cap = lane_capacity_remaining.get(lane_key)
                    if rem_cap is not None:
                        max_lane = int(rem_cap / prod.load_per_carton)
                        if max_lane <= 0:
                            break
                        alloc = min(needed, avail, max_lane)
                    else:
                        alloc = min(needed, avail)

                    if alloc <= 0:
                        continue

                    line_cost = round(alloc * lane.cost_per_carton, 2)
                    arrival_date = plan_date + timedelta(days=lane.lead_time_days)

                    lines.append(
                        AllocationLine(
                            batch_id=b.id,
                            source_id=wh.id,
                            destination_id=dst.id,
                            product_id=prod.id,
                            cartons=alloc,
                            cost=line_cost,
                            arrival_date=arrival_date,
                            lead_time_days=lane.lead_time_days,
                            flags=["BASELINE_B", "PROPORTIONAL_SPLIT"],
                            explanation={
                                "method": "B",
                                "rule": "Proportional 14-day Split",
                                "sales_share": dest_sales[dst.id] / total_sales if total_sales > 0 else 0.25,
                            },
                        )
                    )

                    batch_remaining[b.id] -= alloc
                    if rem_cap is not None:
                        lane_capacity_remaining[lane_key] -= (alloc * prod.load_per_carton)
                    needed -= alloc

    return lines


# =====================================================================
# Shared Forecasting & Net Requirement Pipeline for Advanced Methods
# =====================================================================
def prepare_forecast_and_requirements(
    plan_date: dt_date,
    destinations: List[Location],
    products: List[Product],
    lanes: List[LaneData],
    destination_inventory: Dict[str, Dict[str, float]],
    sales_cache: Dict[Tuple[str, str], pd.Series],
    settings: Optional[Settings] = None,
    z_override: Optional[float] = None,
) -> Tuple[
    Dict[str, Dict[str, NetRequirement]],
    Dict[str, Dict[str, float]],
    Dict[str, Dict[str, float]],
    List[Dict[str, Any]],
]:
    """Execute product ForecastService and compute_all_net_requirements."""
    eff_settings = settings or Settings()
    h = eff_settings.H
    z = z_override if z_override is not None else eff_settings.z
    gmax = eff_settings.Gmax

    fc_service = ForecastService(sales_cache=sales_cache, settings_override=eff_settings)
    fc_results = fc_service.fit_and_select_all(
        as_of=plan_date,
        horizon=h,
        products_override=products,
        destinations_override=destinations,
        persist=False,
    )

    fc_mean_map: Dict[str, Dict[str, float]] = {}
    fc_sigma_map: Dict[str, Dict[str, float]] = {}
    daily_fc_map: Dict[str, Dict[str, List[float]]] = {}

    for r in fc_results:
        d = r["location_id"]
        p = r["product_id"]
        fc_mean_map.setdefault(d, {})[p] = float(sum(r["daily_forecast"]) / len(r["daily_forecast"]))
        fc_sigma_map.setdefault(d, {})[p] = float(r["sigma"])
        daily_fc_map.setdefault(d, {})[p] = r["daily_forecast"]

    dest_ids = [d.id for d in destinations]
    prod_ids = [p.id for p in products]

    req_lanes = [
        LaneInfo(
            source_id=l.source_id,
            destination_id=l.destination_id,
            lead_time_days=l.lead_time_days,
            cost_per_carton=l.cost_per_carton,
            capacity_load=l.capacity_load,
        )
        for l in lanes
    ]

    cp_map = {p.id: p.case_pack for p in products}
    # Convert carton inventory to units for requirement and cover calculation
    dest_units_inventory = {
        d: {p: destination_inventory.get(d, {}).get(p, 0.0) * cp_map.get(p, 1) for p in prod_ids}
        for d in dest_ids
    }

    requirements = compute_all_net_requirements(
        destinations=dest_ids,
        products=prod_ids,
        inventory_positions=dest_units_inventory,
        forecast_means=fc_mean_map,
        forecast_sigmas=fc_sigma_map,
        lanes=req_lanes,
        daily_forecasts=daily_fc_map,
        case_packs=cp_map,
        H=h,
        z=z,
        Gmax=gmax,
    )

    return requirements, fc_mean_map, fc_sigma_map, fc_results


# =====================================================================
# Method C: Forecast + Greedy Heuristic
# =====================================================================
def solve_baseline_c(
    plan_date: dt_date,
    destinations: List[Location],
    products: List[Product],
    lanes: List[LaneData],
    batches: List[BatchInfo],
    destination_inventory: Dict[str, Dict[str, float]],
    sales_cache: Dict[Tuple[str, str], pd.Series],
    settings: Optional[Settings] = None,
) -> Tuple[List[AllocationLine], OptimizationResult]:
    """Baseline C: Forecast + Net Requirement + Greedy Urgency Heuristic (no optimizer)."""
    eff_settings = settings or Settings()
    products_pure, lanes_pure, batches_pure = build_pure_domain_objects(products, lanes, batches, plan_date)

    requirements, fc_mean_map, _, _ = prepare_forecast_and_requirements(
        plan_date, destinations, products, lanes_pure, destination_inventory, sales_cache, eff_settings
    )

    cover_map = {d: {k: req.cover for k, req in p_dict.items()} for d, p_dict in requirements.items()}
    effective_pos_map = {d: {k: req.pos for k, req in p_dict.items()} for d, p_dict in requirements.items()}

    eligibility = evaluate_all_batches_eligibility(
        batches=batches_pure,
        lanes=lanes_pure,
        products=products_pure,
        covers=cover_map,
        daily_forecast_means=fc_mean_map,
        positions=effective_pos_map,
        Gmax=eff_settings.Gmax,
    )

    result = run_greedy_heuristic(
        plan_date=plan_date,
        requirements=requirements,
        eligibility=eligibility,
        batches=batches_pure,
        lanes=lanes_pure,
        products=products_pure,
        planner_reserve=eff_settings.planner_reserve,
        run_id=f"REPLAY-C-{plan_date.strftime('%Y%m%d')}",
    )

    return result.lines, result


# =====================================================================
# Method V: VyaparMitra Full Pipeline
# =====================================================================
def solve_v(
    plan_date: dt_date,
    destinations: List[Location],
    products: List[Product],
    lanes: List[LaneData],
    batches: List[BatchInfo],
    destination_inventory: Dict[str, Dict[str, float]],
    sales_cache: Dict[Tuple[str, str], pd.Series],
    settings: Optional[Settings] = None,
) -> Tuple[List[AllocationLine], OptimizationResult]:
    """Method V: VyaparMitra Full Optimization Pipeline."""
    eff_settings = settings or Settings()
    products_pure, lanes_pure, batches_pure = build_pure_domain_objects(products, lanes, batches, plan_date)

    requirements, fc_mean_map, _, _ = prepare_forecast_and_requirements(
        plan_date, destinations, products, lanes_pure, destination_inventory, sales_cache, eff_settings
    )

    cover_map = {d: {k: req.cover for k, req in p_dict.items()} for d, p_dict in requirements.items()}
    effective_pos_map = {d: {k: req.pos for k, req in p_dict.items()} for d, p_dict in requirements.items()}

    eligibility = evaluate_all_batches_eligibility(
        batches=batches_pure,
        lanes=lanes_pure,
        products=products_pure,
        covers=cover_map,
        daily_forecast_means=fc_mean_map,
        positions=effective_pos_map,
        Gmax=eff_settings.Gmax,
    )

    result = solve_two_stage_optimization(
        plan_date=plan_date,
        requirements=requirements,
        eligibility=eligibility,
        batches=batches_pure,
        lanes=lanes_pure,
        products=products_pure,
        settings=eff_settings,
        planner_reserve=eff_settings.planner_reserve,
        run_id=f"REPLAY-V-{plan_date.strftime('%Y%m%d')}",
    )

    return result.lines, result


# =====================================================================
# Method V-SS: V with Safety Stock set to Zero
# =====================================================================
def solve_v_ss(
    plan_date: dt_date,
    destinations: List[Location],
    products: List[Product],
    lanes: List[LaneData],
    batches: List[BatchInfo],
    destination_inventory: Dict[str, Dict[str, float]],
    sales_cache: Dict[Tuple[str, str], pd.Series],
    settings: Optional[Settings] = None,
) -> Tuple[List[AllocationLine], OptimizationResult]:
    """Method V-SS: VyaparMitra Pipeline with Safety Stock = 0 (z=0, Ntot = Ndem)."""
    eff_settings = settings or Settings()
    products_pure, lanes_pure, batches_pure = build_pure_domain_objects(products, lanes, batches, plan_date)

    # z_override = 0.0 zeroes out safety stock
    requirements, fc_mean_map, _, _ = prepare_forecast_and_requirements(
        plan_date, destinations, products, lanes_pure, destination_inventory, sales_cache, eff_settings, z_override=0.0
    )

    cover_map = {d: {k: req.cover for k, req in p_dict.items()} for d, p_dict in requirements.items()}
    effective_pos_map = {d: {k: req.pos for k, req in p_dict.items()} for d, p_dict in requirements.items()}

    eligibility = evaluate_all_batches_eligibility(
        batches=batches_pure,
        lanes=lanes_pure,
        products=products_pure,
        covers=cover_map,
        daily_forecast_means=fc_mean_map,
        positions=effective_pos_map,
        Gmax=eff_settings.Gmax,
    )

    result = solve_two_stage_optimization(
        plan_date=plan_date,
        requirements=requirements,
        eligibility=eligibility,
        batches=batches_pure,
        lanes=lanes_pure,
        products=products_pure,
        settings=eff_settings,
        planner_reserve=eff_settings.planner_reserve,
        run_id=f"REPLAY-VSS-{plan_date.strftime('%Y%m%d')}",
    )

    return result.lines, result


# =====================================================================
# Method V-SL: V without Shelf-Life Rules
# =====================================================================
def solve_v_sl(
    plan_date: dt_date,
    destinations: List[Location],
    products: List[Product],
    lanes: List[LaneData],
    batches: List[BatchInfo],
    destination_inventory: Dict[str, Dict[str, float]],
    sales_cache: Dict[Tuple[str, str], pd.Series],
    settings: Optional[Settings] = None,
) -> Tuple[List[AllocationLine], OptimizationResult]:
    """Method V-SL: VyaparMitra Pipeline without Shelf-Life Rules (Eshort=0, no sell-through caps)."""
    base_settings = settings or Settings()
    sl_settings = deepcopy(base_settings)
    sl_settings.Eshort = 0  # Acceptance life rule disabled

    products_pure, lanes_pure, batches_pure = build_pure_domain_objects(products, lanes, batches, plan_date)

    # Set min_remaining_shelf_days to 0 on all products
    for p in products_pure.values():
        p.min_remaining_shelf_days = 0

    requirements, fc_mean_map, _, _ = prepare_forecast_and_requirements(
        plan_date, destinations, products, lanes_pure, destination_inventory, sales_cache, sl_settings
    )

    cover_map = {d: {k: req.cover for k, req in p_dict.items()} for d, p_dict in requirements.items()}
    effective_pos_map = {d: {k: req.pos for k, req in p_dict.items()} for d, p_dict in requirements.items()}

    eligibility = evaluate_all_batches_eligibility(
        batches=batches_pure,
        lanes=lanes_pure,
        products=products_pure,
        covers=cover_map,
        daily_forecast_means=fc_mean_map,
        positions=effective_pos_map,
        Gmax=sl_settings.Gmax,
    )

    # Disable FEFO cumulative sell-through caps
    for d, p_dict in eligibility.items():
        for k, b_dict in p_dict.items():
            for b_id, res in b_dict.items():
                for exp_k in res.cumulative_caps:
                    res.cumulative_caps[exp_k] = 999999.0
                if res.reasons and any("shelf" in r.lower() or "expiry" in r.lower() for r in res.reasons):
                    res.is_eligible = True
                    res.reasons = [r for r in res.reasons if "shelf" not in r.lower() and "expiry" not in r.lower()]

    result = solve_two_stage_optimization(
        plan_date=plan_date,
        requirements=requirements,
        eligibility=eligibility,
        batches=batches_pure,
        lanes=lanes_pure,
        products=products_pure,
        settings=sl_settings,
        planner_reserve=sl_settings.planner_reserve,
        run_id=f"REPLAY-VSL-{plan_date.strftime('%Y%m%d')}",
    )

    return result.lines, result


# =====================================================================
# Method O: True-Demand Oracle (Upper Bound)
# =====================================================================
def solve_oracle(
    plan_date: dt_date,
    destinations: List[Location],
    products: List[Product],
    lanes: List[LaneData],
    batches: List[BatchInfo],
    destination_inventory: Dict[str, Dict[str, float]],
    future_sales: Dict[Tuple[str, str], List[float]],
    settings: Optional[Settings] = None,
) -> Tuple[List[AllocationLine], OptimizationResult]:
    """
    Method O: True-Demand Oracle.
      - Given TRUE future 7-day realized demand.
      - No safety stock (perfect foresight).
      - Upper bound benchmark, not a competitor.
    """
    eff_settings = settings or Settings()
    products_pure, lanes_pure, batches_pure = build_pure_domain_objects(products, lanes, batches, plan_date)

    dest_ids = [d.id for d in destinations]
    prod_ids = [p.id for p in products]

    # Compute true demand requirement for each destination and product
    requirements: Dict[str, Dict[str, NetRequirement]] = {}
    fc_mean_map: Dict[str, Dict[str, float]] = {}

    req_lanes = [
        LaneInfo(
            source_id=l.source_id,
            destination_id=l.destination_id,
            lead_time_days=l.lead_time_days,
            cost_per_carton=l.cost_per_carton,
            capacity_load=l.capacity_load,
        )
        for l in lanes_pure
    ]

    for d in dest_ids:
        requirements[d] = {}
        fc_mean_map[d] = {}
        for p in products:
            k = p.id
            fut_units = future_sales.get((k, d), [0.0] * 7)
            tot_units = sum(fut_units)
            daily_mean = max(0.1, tot_units / 7.0)
            fc_mean_map[d][k] = daily_mean

            pos_cartons = destination_inventory.get(d, {}).get(k, 0.0)
            req = compute_net_requirement(
                destination_id=d,
                product_id=k,
                on_hand=pos_cartons * p.case_pack,
                daily_forecast=fut_units,
                daily_forecast_mean=daily_mean,
                sigma=0.0,
                lanes=req_lanes,
                H=eff_settings.H,
                z=0.0,  # No safety stock for Oracle
                Gmax=eff_settings.Gmax,
                case_pack=p.case_pack,
            )
            requirements[d][k] = req

    cover_map = {d: {k: req.cover for k, req in p_dict.items()} for d, p_dict in requirements.items()}
    effective_pos_map = {d: {k: req.pos for k, req in p_dict.items()} for d, p_dict in requirements.items()}

    eligibility = evaluate_all_batches_eligibility(
        batches=batches_pure,
        lanes=lanes_pure,
        products=products_pure,
        covers=cover_map,
        daily_forecast_means=fc_mean_map,
        positions=effective_pos_map,
        Gmax=eff_settings.Gmax,
    )

    result = solve_two_stage_optimization(
        plan_date=plan_date,
        requirements=requirements,
        eligibility=eligibility,
        batches=batches_pure,
        lanes=lanes_pure,
        products=products_pure,
        settings=eff_settings,
        planner_reserve=0,
        run_id=f"REPLAY-ORACLE-{plan_date.strftime('%Y%m%d')}",
    )

    return result.lines, result
