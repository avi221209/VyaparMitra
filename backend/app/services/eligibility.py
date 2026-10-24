"""
VyaparMitra - Batch Eligibility and Constraint Evaluation Service
Team Stark | Triwizathon 2026 | PS2: Distribution Intelligence and Inventory Optimization Engine

PURE FUNCTIONS ONLY - NO DATABASE ACCESS INSIDE.

Evaluates eligibility per (batch b at source s, destination d, product k):
 - Lane gap: G = max(0, L[s,d] - cover[d,k]). Allowed if G <= Gmax.
   Any line with G > 0 is flagged and its expected lost sales (f * G) reported as unavoidable before arrival.
 - Acceptance life: (days to expiry of batch at arrival) must be >= min_remaining_shelf_days of product, else excluded.
 - Cumulative FEFO sell-through cap: for each distinct days-to-expiry value e (measured from arrival),
   the cartons shipped to (d,k) from all batches with days-to-expiry <= e must not exceed max(0, f * e - pos).
   This makes a batch partly eligible.
 - Lane capacity: exposed here along with load_per_carton for the downstream optimizer.
"""

from dataclasses import dataclass, field
from datetime import date as dt_date
import math
from typing import Dict, List, Optional


@dataclass
class BatchInfo:
    """Pure data representation of an inventory batch at a source warehouse."""
    id: str
    location_id: str                     # Source warehouse ID (s)
    product_id: str                      # Product SKU ID (k)
    quantity: int                        # Available cartons at source
    days_to_expiry_from_dispatch: int    # Remaining shelf life days as of dispatch run date
    expiry_date: Optional[dt_date] = None
    cost_per_carton: float = 0.0


@dataclass
class ProductInfo:
    """Pure data representation of product characteristics."""
    id: str
    name: str = ""
    category: str = ""
    case_pack: int = 1
    min_remaining_shelf_days: int = 21   # Eshort acceptance life threshold
    load_per_carton: float = 1.0
    unit_cost: float = 50.0              # Cost per carton (omega_k)
    unit_margin: float = 20.0            # Margin per carton (w_k)


@dataclass
class LaneData:
    """Pure data representation of a lane between source and destination."""
    source_id: str
    destination_id: str
    lead_time_days: int
    cost_per_carton: float = 0.0
    capacity_load: Optional[float] = None
    distance_km: float = 0.0


@dataclass
class BatchEligibilityResult:
    """Result of eligibility and constraint evaluation for a (batch, destination, product) tuple."""
    batch_id: str
    source_id: str
    destination_id: str
    product_id: str
    is_eligible: bool
    sell_through_cap: float              # Individual max cartons allowed by sell-through
    days_to_expiry_at_arrival: int       # e (measured from arrival date)
    lane_lead_time: int                  # L[s, d]
    lane_gap: float                      # G = max(0, L[s,d] - cover[d,k])
    unavoidable_lost_sales: float        # f * G if G > 0 else 0.0
    lane_capacity: Optional[float]       # Expose lane capacity for optimizer
    load_per_carton: float               # Expose load per carton
    flags: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    cumulative_caps: Dict[int, float] = field(default_factory=dict)


def compute_sell_through_cap(
    daily_forecast_mean: float,          # f
    days_to_expiry_at_arrival: int,      # e
    pos: float,                          # on_hand - reserved + in_transit
) -> float:
    """
    Calculate the FEFO sell-through cap:
        cap = max(0, f * e - pos)
    Any cartons dispatched beyond this threshold cannot be sold before expiration.
    """
    if days_to_expiry_at_arrival <= 0:
        return 0.0
    demand_until_expiry = daily_forecast_mean * float(days_to_expiry_at_arrival)
    return max(0.0, demand_until_expiry - pos)


def evaluate_batch_eligibility(
    batch: BatchInfo,
    lane: LaneData,
    product: ProductInfo,
    cover: float,                        # Inventory cover at destination (pos / f)
    daily_forecast_mean: float,          # f
    pos: float,                          # Effective stock at destination
    Gmax: int = 1,                       # Max allowed lane gap threshold
    min_shelf_life_override: Optional[int] = None,
) -> BatchEligibilityResult:
    """
    Pure evaluation of a single batch from source s to destination d for product k.

    Checks:
      1. Lane Gap: G = max(0, L[s,d] - cover). Must be <= Gmax.
      2. Acceptance Life: e = days_to_expiry - L[s,d] >= min_remaining_shelf_days.
      3. FEFO Sell-Through Cap: max(0, f * e - pos).
      4. Exposes lane capacity and load_per_carton.
    """
    flags: List[str] = []
    reasons: List[str] = []
    is_eligible = True

    lead_time = lane.lead_time_days
    f = max(0.0, daily_forecast_mean)

    # 1. Lane Gap Check
    if math.isinf(cover):
        lane_gap = 0.0
    else:
        lane_gap = max(0.0, float(lead_time) - cover)

    unavoidable_lost_sales = 0.0
    if lane_gap > Gmax:
        is_eligible = False
        flags.append("EXCLUDED_LANE_GAP")
        reasons.append(f"Lane gap {lane_gap:.2f} > Gmax ({Gmax}) from {lane.source_id} to {lane.destination_id}")
    elif lane_gap > 0.0:
        unavoidable_lost_sales = float(f * lane_gap)
        flags.append("LANE_GAP_RISK")
        reasons.append(
            f"Lane gap {lane_gap:.2f} days causes unavoidable lost sales of {unavoidable_lost_sales:.1f} units before arrival"
        )

    # 2. Acceptance Life Check (Days to Expiry at Arrival)
    days_at_arrival = batch.days_to_expiry_from_dispatch - lead_time
    min_shelf = min_shelf_life_override if min_shelf_life_override is not None else product.min_remaining_shelf_days

    if days_at_arrival < min_shelf:
        is_eligible = False
        flags.append("EXCLUDED_ACCEPTANCE_LIFE")
        reasons.append(
            f"Remaining shelf life at arrival ({days_at_arrival} days) < minimum threshold ({min_shelf} days)"
        )

    # 3. Cumulative FEFO Sell-Through Cap
    sell_through_cap = compute_sell_through_cap(f, days_at_arrival, pos)
    cumulative_caps = {days_at_arrival: sell_through_cap}

    if is_eligible:
        if sell_through_cap <= 0.0:
            is_eligible = False
            flags.append("EXCLUDED_ZERO_SELL_THROUGH_CAP")
            reasons.append(
                f"Sell-through cap is 0: current stock ({pos:.1f}) satisfies all demand through expiry ({f * days_at_arrival:.1f} units)"
            )
        elif sell_through_cap < batch.quantity:
            flags.append("PARTIALLY_ELIGIBLE_CAP")
            reasons.append(
                f"Partially eligible: capped at {sell_through_cap:.1f} cartons (batch holds {batch.quantity})"
            )

    return BatchEligibilityResult(
        batch_id=batch.id,
        source_id=lane.source_id,
        destination_id=lane.destination_id,
        product_id=product.id,
        is_eligible=is_eligible,
        sell_through_cap=sell_through_cap,
        days_to_expiry_at_arrival=days_at_arrival,
        lane_lead_time=lead_time,
        lane_gap=lane_gap,
        unavoidable_lost_sales=unavoidable_lost_sales,
        lane_capacity=lane.capacity_load,
        load_per_carton=product.load_per_carton,
        flags=flags,
        reasons=reasons,
        cumulative_caps=cumulative_caps,
    )


def evaluate_all_batches_eligibility(
    batches: List[BatchInfo],
    lanes: List[LaneData],
    products: Dict[str, ProductInfo],
    covers: Dict[str, Dict[str, float]],                 # dest_id -> {prod_id: cover}
    daily_forecast_means: Dict[str, Dict[str, float]],   # dest_id -> {prod_id: f}
    positions: Dict[str, Dict[str, float]],              # dest_id -> {prod_id: pos}
    Gmax: int = 1,
) -> Dict[str, Dict[str, Dict[str, BatchEligibilityResult]]]:
    """
    Batch pure evaluation of all (batch, destination, product) combinations.
    Returns nested dictionary: results[dest_id][prod_id][batch_id] = BatchEligibilityResult.
    Also computes the cumulative caps mapping for distinct days-to-expiry values per (d, k).
    """
    results: Dict[str, Dict[str, Dict[str, BatchEligibilityResult]]] = {}

    # Map lanes by (source_id, destination_id)
    lane_map: Dict[tuple, LaneData] = {(l.source_id, l.destination_id): l for l in lanes}

    # Group batches by product
    batches_by_prod: Dict[str, List[BatchInfo]] = {}
    for b in batches:
        batches_by_prod.setdefault(b.product_id, []).append(b)

    for dest_id, prod_dict in daily_forecast_means.items():
        results[dest_id] = {}
        for prod_id, f in prod_dict.items():
            results[dest_id][prod_id] = {}
            cover = covers.get(dest_id, {}).get(prod_id, float("inf"))
            pos = positions.get(dest_id, {}).get(prod_id, 0.0)
            prod_info = products.get(prod_id, ProductInfo(id=prod_id))

            cand_batches = batches_by_prod.get(prod_id, [])

            # Track cumulative caps across distinct days-to-expiry for (dest_id, prod_id)
            distinct_e_caps: Dict[int, float] = {}

            for b in cand_batches:
                lane_key = (b.location_id, dest_id)
                lane = lane_map.get(lane_key)
                if not lane:
                    continue

                res = evaluate_batch_eligibility(
                    batch=b,
                    lane=lane,
                    product=prod_info,
                    cover=cover,
                    daily_forecast_mean=f,
                    pos=pos,
                    Gmax=Gmax,
                )
                results[dest_id][prod_id][b.id] = res

                if res.days_to_expiry_at_arrival > 0:
                    e = res.days_to_expiry_at_arrival
                    if e not in distinct_e_caps:
                        distinct_e_caps[e] = compute_sell_through_cap(f, e, pos)

            # Assign combined cumulative caps dictionary to all results for this (d, k)
            for res in results[dest_id][prod_id].values():
                res.cumulative_caps = distinct_e_caps

    return results
