"""
VyaparMitra - Distribution Plan Rule Checker Service
Team Stark | Triwizathon 2026 | PS2: Distribution Intelligence and Inventory Optimization Engine

Validates proposed distribution plans or human edits against C1 to C6 and requirement limits:
 C1 Stock: sum_d y[b, d] <= batch.quantity - planner_reserve
 C2/C3 Requirements: sum_b y <= Ntot
 C4 Eligibility: lane gap <= Gmax and shelf_life >= min_remaining_shelf_days
 C5 Sell-Through Caps: sum_{e' <= e} y <= cap_e
 C6 Lane Capacity: sum_k load_k * cartons <= lane.capacity_load

Refuses invalid edits with specific rule identification.
"""

from dataclasses import dataclass
from datetime import date as dt_date
from typing import Dict, List, Optional, Tuple

from backend.app.services.eligibility import (
    BatchEligibilityResult,
    BatchInfo,
    LaneData,
    ProductInfo,
    compute_sell_through_cap,
)
from backend.app.services.requirement import NetRequirement


@dataclass
class RuleViolation:
    rule: str                           # "C1_STOCK_EXCEEDED" | "C3_OVER_ALLOCATION" | "C4_INELIGIBLE" | "C5_CAP_EXCEEDED" | "C6_LANE_CAP_EXCEEDED"
    message: str
    details: Dict[str, any]


@dataclass
class RuleCheckResult:
    is_valid: bool
    violations: List[RuleViolation]

    @property
    def first_rule_name(self) -> Optional[str]:
        return self.violations[0].rule if self.violations else None

    @property
    def first_message(self) -> Optional[str]:
        return self.violations[0].message if self.violations else None


def validate_plan_allocation(
    lines: List[Dict[str, any]],          # [{"batch_id": ..., "source_id": ..., "destination_id": ..., "product_id": ..., "cartons": ...}]
    batches: List[BatchInfo],
    lanes: List[LaneData],
    products: Dict[str, ProductInfo],
    requirements: Dict[str, Dict[str, NetRequirement]],
    eligibility: Optional[Dict[str, Dict[str, Dict[str, BatchEligibilityResult]]]] = None,
    Gmax: int = 1,
    planner_reserve: int = 0,
) -> RuleCheckResult:
    """
    Validate a complete set of proposed plan lines against all physical and operational constraints (C1 - C6).
    """
    violations: List[RuleViolation] = []

    batch_map: Dict[str, BatchInfo] = {b.id: b for b in batches}
    lane_map: Dict[Tuple[str, str], LaneData] = {(l.source_id, l.destination_id): l for l in lanes}

    # -------------------------------------------------------------
    # C1: Stock Availability (sum_d y[b, d] <= batch quantity - reserve)
    # -------------------------------------------------------------
    batch_allocated: Dict[str, int] = {}
    for line in lines:
        b_id = line.get("batch_id")
        cartons = int(line.get("cartons", 0))
        if b_id:
            batch_allocated[b_id] = batch_allocated.get(b_id, 0) + cartons

    for b_id, alloc in batch_allocated.items():
        batch = batch_map.get(b_id)
        if not batch:
            violations.append(
                RuleViolation(
                    rule="C1_STOCK_EXCEEDED",
                    message=f"Batch '{b_id}' does not exist in inventory master.",
                    details={"batch_id": b_id, "allocated": alloc},
                )
            )
            continue

        available = max(0, batch.quantity - planner_reserve)
        if alloc > available:
            violations.append(
                RuleViolation(
                    rule="C1_STOCK_EXCEEDED",
                    message=f"C1 Stock Exceeded: Batch '{b_id}' allocated {alloc} cartons, but only {available} available ({batch.quantity} total - {planner_reserve} reserve).",
                    details={"batch_id": b_id, "allocated": alloc, "available": available, "overdraft": alloc - available},
                )
            )

    # -------------------------------------------------------------
    # C2 & C3: No Over-Allocation (sum_b y <= Ntot)
    # -------------------------------------------------------------
    dest_prod_allocated: Dict[Tuple[str, str], int] = {}
    for line in lines:
        d = line.get("destination_id")
        k = line.get("product_id")
        cartons = int(line.get("cartons", 0))
        dest_prod_allocated[(d, k)] = dest_prod_allocated.get((d, k), 0) + cartons

    for (d, k), alloc in dest_prod_allocated.items():
        req = requirements.get(d, {}).get(k)
        if req and alloc > req.Ntot:
            violations.append(
                RuleViolation(
                    rule="C3_OVER_ALLOCATION",
                    message=f"C3 Over-Allocation: Destination '{d}' SKU '{k}' allocated {alloc} cartons, exceeding total requirement Ntot of {req.Ntot}.",
                    details={"destination_id": d, "product_id": k, "allocated": alloc, "Ntot": req.Ntot},
                )
            )

    # -------------------------------------------------------------
    # C4: Eligibility (Lane gap <= Gmax, shelf life >= min_shelf_days)
    # -------------------------------------------------------------
    for line in lines:
        cartons = int(line.get("cartons", 0))
        if cartons <= 0:
            continue

        s = line.get("source_id")
        d = line.get("destination_id")
        k = line.get("product_id")
        b_id = line.get("batch_id")

        lane = lane_map.get((s, d))
        prod = products.get(k, ProductInfo(id=k))
        batch = batch_map.get(b_id) if b_id else None

        if not lane:
            violations.append(
                RuleViolation(
                    rule="C4_INELIGIBLE_LANE",
                    message=f"C4 Ineligible: No active lane exists from '{s}' to '{d}'.",
                    details={"source_id": s, "destination_id": d},
                )
            )
            continue

        req = requirements.get(d, {}).get(k)
        cover = req.cover if req else 0.0
        lane_gap = max(0.0, float(lane.lead_time_days) - cover)

        if lane_gap > float(Gmax):
            violations.append(
                RuleViolation(
                    rule="C4_LANE_GAP_EXCEEDED",
                    message=f"C4 Ineligible: Lane '{s}->{d}' lead-time gap {lane_gap:.2f}d exceeds Gmax ({Gmax}d).",
                    details={"source_id": s, "destination_id": d, "lane_gap": lane_gap, "Gmax": Gmax},
                )
            )

        if batch:
            arrival_exp = batch.days_to_expiry_from_dispatch - lane.lead_time_days
            if arrival_exp < prod.min_remaining_shelf_days:
                violations.append(
                    RuleViolation(
                        rule="C4_ACCEPTANCE_LIFE_FAILED",
                        message=f"C4 Ineligible: Batch '{b_id}' expires in {arrival_exp}d upon arrival, below acceptance life threshold of {prod.min_remaining_shelf_days}d.",
                        details={"batch_id": b_id, "days_at_arrival": arrival_exp, "threshold": prod.min_remaining_shelf_days},
                    )
                )

    # -------------------------------------------------------------
    # C5: Cumulative FEFO Sell-Through Caps
    # -------------------------------------------------------------
    # Group lines by (dest, prod)
    dest_prod_batches: Dict[Tuple[str, str], List[Dict[str, any]]] = {}
    for line in lines:
        cartons = int(line.get("cartons", 0))
        if cartons > 0 and line.get("batch_id"):
            dest_prod_batches.setdefault((line["destination_id"], line["product_id"]), []).append(line)

    for (d, k), line_list in dest_prod_batches.items():
        req = requirements.get(d, {}).get(k)
        if not req:
            continue

        f = req.daily_forecast_mean
        pos = req.pos

        # Calculate arrival expiry for each line
        annotated_lines = []
        for l in line_list:
            b = batch_map.get(l["batch_id"])
            lane = lane_map.get((l["source_id"], l["destination_id"]))
            if b and lane:
                e = b.days_to_expiry_from_dispatch - lane.lead_time_days
                annotated_lines.append((e, int(l["cartons"])))

        distinct_expiries = sorted(list(set(e for e, _ in annotated_lines)))
        for exp_val in distinct_expiries:
            shipped_le_exp = sum(cartons for e, cartons in annotated_lines if e <= exp_val)
            cap = compute_sell_through_cap(f, exp_val, pos)
            if shipped_le_exp > cap + 1e-4:
                violations.append(
                    RuleViolation(
                        rule="C5_SELL_THROUGH_CAP_EXCEEDED",
                        message=f"C5 Cap Exceeded: {shipped_le_exp} cartons arriving with <= {exp_val}d expiry exceeds sell-through cap of {cap:.1f} cartons at destination '{d}'.",
                        details={"destination_id": d, "product_id": k, "exp_days": exp_val, "shipped": shipped_le_exp, "cap": cap},
                    )
                )

    # -------------------------------------------------------------
    # C6: Lane Capacity Limits
    # -------------------------------------------------------------
    lane_load: Dict[Tuple[str, str], float] = {}
    for line in lines:
        cartons = int(line.get("cartons", 0))
        if cartons <= 0:
            continue
        s = line.get("source_id")
        d = line.get("destination_id")
        k = line.get("product_id")
        prod = products.get(k, ProductInfo(id=k))
        lane_load[(s, d)] = lane_load.get((s, d), 0.0) + (cartons * prod.load_per_carton)

    for (s, d), total_load in lane_load.items():
        lane = lane_map.get((s, d))
        if lane and lane.capacity_load is not None:
            if total_load > lane.capacity_load + 1e-4:
                violations.append(
                    RuleViolation(
                        rule="C6_LANE_CAPACITY_EXCEEDED",
                        message=f"C6 Lane Capacity Exceeded: Lane '{s}->{d}' total load {total_load:.1f} exceeds capacity limit of {lane.capacity_load:.1f}.",
                        details={"source_id": s, "destination_id": d, "total_load": total_load, "capacity": lane.capacity_load},
                    )
                )

    return RuleCheckResult(
        is_valid=len(violations) == 0,
        violations=violations,
    )
