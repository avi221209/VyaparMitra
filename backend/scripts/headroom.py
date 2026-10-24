"""
Phase 0 Spike: Headroom Analysis Script
Compares True-Demand Oracle Fill Rate vs Baseline A (Simple Min/Max Policy)
across three warehouse stock scenarios: scarce (0.8), balanced (1.0), and abundant (1.3).
If the headroom gap (Oracle - Baseline A) is under 3 percentage points, prints 'NO HEADROOM'.
"""

import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from datetime import timedelta
from typing import Any, Dict, List, Tuple
import numpy as np

from backend.app.models import Batch, Lane, Location, Product, SalesDaily
from backend.app.services.simulator import FMCGSimulator


def compute_true_demand(
    sales: List[SalesDaily],
    products: List[Product],
    destinations: List[Location],
    horizon_days: int = 7,
) -> Dict[Tuple[str, str], int]:
    """
    Compute true net carton demand per (destination, product) over a 7-day horizon
    based on the last 7 days of historical consumption.
    """
    case_pack_map = {p.id: p.case_pack for p in products}
    # Group by destination and product over the last horizon_days
    latest_date = max(s.date for s in sales)
    cutoff_date = latest_date - timedelta(days=horizon_days - 1)

    demand: Dict[Tuple[str, str], int] = {}
    for s in sales:
        if s.date >= cutoff_date and s.location_id in [d.id for d in destinations if d.type != "warehouse"]:
            key = (s.location_id, s.product_id)
            cp = case_pack_map.get(s.product_id, 1)
            cartons = int(np.ceil(s.units / cp))
            demand[key] = demand.get(key, 0) + cartons

    return demand


def evaluate_oracle_fill_rate(
    demand: Dict[Tuple[str, str], int],
    batches: List[Batch],
    lanes: List[Lane],
    base_date,
    E_short: int = 21,
) -> Tuple[float, int, int]:
    """
    True-Demand Oracle:
    Global coordinator with perfect foresight of forward demand.
    Routes inventory from any warehouse having eligible batches (expiry >= arrival + E_short)
    to destinations, respecting batch quantities and lane capacities.
    """
    total_demand = sum(demand.values())
    if total_demand == 0:
        return 100.0, 0, 0

    # Lane map: (source, destination) -> Lane
    lane_map = {(l.source_id, l.destination_id): l for l in lanes}
    # Lane flow usage tracking
    lane_usage = {l.id: 0 for l in lanes}

    # Available cartons per (warehouse, product) from eligible batches
    wh_stock: Dict[Tuple[str, str], int] = {}
    for b in batches:
        # Check shelf life: batch expiry must be >= base_date + lead_time + E_short
        # Look up max lead time across lanes from this warehouse
        lts = [l.lead_time_days for l in lanes if l.source_id == b.location_id]
        min_lt = min(lts) if lts else 1
        rem_life = (b.expiry_date - (base_date + timedelta(days=min_lt))).days
        if rem_life >= E_short:
            key = (b.location_id, b.product_id)
            wh_stock[key] = wh_stock.get(key, 0) + b.quantity

    fulfilled_cartons = 0

    # Oracle fills demand by examining candidate warehouses
    # Prioritizes direct/cheapest paths, but dynamically reroutes if a warehouse is empty or lane full
    for (dest_id, prod_id), req_cartons in demand.items():
        needed = req_cartons

        # Candidate warehouses serving this destination
        candidate_lanes = [l for l in lanes if l.destination_id == dest_id]
        # Sort candidate lanes by cost per carton ascending
        candidate_lanes.sort(key=lambda x: (x.cost_per_carton, x.lead_time_days))

        for lane in candidate_lanes:
            if needed <= 0:
                break
            src_wh = lane.source_id
            avail_stock = wh_stock.get((src_wh, prod_id), 0)
            if avail_stock <= 0:
                continue

            # Check lane capacity
            avail_lane_cap = 999999
            if lane.capacity_load is not None:
                avail_lane_cap = max(0, int(lane.capacity_load) - lane_usage[lane.id])

            ship_cartons = min(needed, avail_stock, avail_lane_cap)
            if ship_cartons > 0:
                wh_stock[(src_wh, prod_id)] -= ship_cartons
                lane_usage[lane.id] += ship_cartons
                fulfilled_cartons += ship_cartons
                needed -= ship_cartons

    fill_rate = (fulfilled_cartons / total_demand) * 100.0
    return fill_rate, fulfilled_cartons, total_demand


def evaluate_baseline_a_fill_rate(
    demand: Dict[Tuple[str, str], int],
    batches: List[Batch],
    lanes: List[Lane],
    base_date,
    E_short: int = 21,
) -> Tuple[float, int, int]:
    """
    Baseline A (Simple Min/Max Policy):
    Decentralized, naive ordering rule.
    Each destination orders strictly from its fixed default warehouse:
      - D1 orders from W1 (North)
      - D2 orders from W2 (West)
      - S1 orders from W2 (West)
      - S2 orders from W2 (West)
    Does NOT reroute to alternate warehouses when stockouts occur.
    If orders exceed tight lane capacity, excess is clipped.
    If batches violate E_short, shipments are rejected at arrival.
    """
    total_demand = sum(demand.values())
    if total_demand == 0:
        return 100.0, 0, 0

    default_source = {
        "D1": "W1",
        "D2": "W2",
        "S1": "W2",
        "S2": "W2",
    }

    lane_map = {(l.source_id, l.destination_id): l for l in lanes}
    lane_usage = {l.id: 0 for l in lanes}

    # Available stock per batch
    batch_stock = {b.id: b.quantity for b in batches}
    batch_meta = {b.id: b for b in batches}

    fulfilled_cartons = 0

    for (dest_id, prod_id), req_cartons in demand.items():
        needed = req_cartons
        src_wh = default_source.get(dest_id, "W1")
        lane = lane_map.get((src_wh, dest_id))
        if not lane:
            continue

        # Check lane capacity availability
        lane_cap_avail = 999999
        if lane.capacity_load is not None:
            lane_cap_avail = max(0, int(lane.capacity_load) - lane_usage[lane.id])

        # Find batches at default warehouse for this product
        matching_batches = [
            b for b in batches
            if b.location_id == src_wh and b.product_id == prod_id and batch_stock[b.id] > 0
        ]
        # Baseline A orders FIFO without checking shelf-life rejection gate
        matching_batches.sort(key=lambda x: x.expiry_date)

        for b in matching_batches:
            if needed <= 0 or lane_cap_avail <= 0:
                break
            pull_qty = min(needed, batch_stock[b.id], lane_cap_avail)
            if pull_qty > 0:
                batch_stock[b.id] -= pull_qty
                lane_usage[lane.id] += pull_qty
                lane_cap_avail -= pull_qty
                needed -= pull_qty

                # Shelf-life check at destination gate:
                # Arriving batches with remaining shelf life < E_short are rejected!
                arrival_date = base_date + timedelta(days=lane.lead_time_days)
                rem_days = (b.expiry_date - arrival_date).days
                if rem_days >= E_short:
                    fulfilled_cartons += pull_qty
                else:
                    # Rejected at gate due to shelf-life breach (unfulfilled)
                    pass

    fill_rate = (fulfilled_cartons / total_demand) * 100.0
    return fill_rate, fulfilled_cartons, total_demand


def run_headroom_analysis(seed: int = 1) -> Dict[str, Dict[str, Any]]:
    """
    Run headroom analysis across scarce, balanced, and abundant scenarios.
    Returns comparison dictionary.
    """
    scenarios = ["scarce", "balanced", "abundant"]
    results = {}

    for scen in scenarios:
        sim = FMCGSimulator(seed=seed, scenario=scen, variant="normal")
        products, locations, sales, lanes, batches, snapshots, _ = sim.generate_all()

        demand = compute_true_demand(sales, products, locations, horizon_days=7)

        oracle_fr, oracle_fulfilled, total_demand = evaluate_oracle_fill_rate(
            demand, batches, lanes, sim.base_date, E_short=21
        )
        baseline_fr, baseline_fulfilled, _ = evaluate_baseline_a_fill_rate(
            demand, batches, lanes, sim.base_date, E_short=21
        )

        gap = oracle_fr - baseline_fr
        no_headroom = gap < 3.0

        results[scen] = {
            "scenario": scen,
            "stock_multiplier": sim.stock_multiplier,
            "total_demand_cartons": total_demand,
            "oracle_fill_rate": round(oracle_fr, 2),
            "baseline_fill_rate": round(baseline_fr, 2),
            "headroom_gap": round(gap, 2),
            "no_headroom": no_headroom,
        }

    return results


def main():
    print("=" * 78)
    print("VYAPARMITRA: PHASE 0 SPIKE - HEADROOM ANALYSIS")
    print("True-Demand Oracle vs Baseline A (Min/Max Policy)")
    print("=" * 78)

    results = run_headroom_analysis(seed=1)

    for scen, data in results.items():
        gap = data["headroom_gap"]
        print(f"\nScenario: {scen.upper()} (Stock Scale: {data['stock_multiplier']:.1f}x)")
        print(f"  Total 7-Day Net Demand : {data['total_demand_cartons']:,} cartons")
        print(f"  True-Demand Oracle FR  : {data['oracle_fill_rate']:.2f}%")
        print(f"  Baseline A (Min/Max) FR: {data['baseline_fill_rate']:.2f}%")
        print(f"  Headroom Gap           : {gap:+.2f} percentage points")

        if data["no_headroom"]:
            print(f"  Result                 : NO HEADROOM (gap < 3.0 points)")
        else:
            print(f"  Result                 : SIGNIFICANT HEADROOM ({gap:.2f} points)")

    print("\n" + "=" * 78)


if __name__ == "__main__":
    main()
