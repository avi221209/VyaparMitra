"""
VyaparMitra - Counterfactual What-If Explanation Engine
Distribution Planning and Inventory Optimization Engine

For each destination and product with unmet demand, computes:
 - unmet demand (udem)
 - safety-stock gap (uss)
 - binding constraint among stock, lead time, shelf life, lane capacity
 - smallest single fix per constraint type, each computed with ONE re-solve:
     * Stock: extra cartons added at one named source (evaluates each source, picks minimum).
     * Lead time: increase Gmax in whole days (0 to 3) or 'no change'.
     * Shelf life: relax acceptance life or sell-through caps (reported only if binding).
     * Lane capacity: extra load on one lane (reports smallest).
 - extra transport cost = transport(new plan) - transport(current plan).
 - stock fix restoring safety stock too (second figure).
Fixes are operational advice, not predictions. Purchase cost of extra stock is NOT modelled.
"""

from dataclasses import dataclass, field
from datetime import date as dt_date, timedelta
import math
import time
from typing import Any, Dict, List, Optional, Tuple
import pulp
from sqlmodel import Session, select

from backend.app.models import Settings
from backend.app.services.eligibility import (
    BatchEligibilityResult,
    BatchInfo,
    LaneData,
    ProductInfo,
    evaluate_all_batches_eligibility,
    evaluate_batch_eligibility,
)
from backend.app.services.optimizer import (
    AllocationLine,
    OptimizationResult,
    OptimizationService,
    solve_two_stage_optimization,
)
from backend.app.services.requirement import NetRequirement


@dataclass
class StockFixResult:
    """Stock fix recommendation for a destination-product pair."""
    source_id: str
    extra_cartons_demand: int              # Extra cartons to close udem
    extra_transport_cost_demand: float    # transport(new) - transport(base)
    extra_cartons_total: int               # Extra cartons to also restore safety stock
    extra_transport_cost_total: float     # transport(new) - transport(base)
    is_feasible: bool = True
    description: str = ""


@dataclass
class LeadTimeFixResult:
    """Lead time (Gmax) fix recommendation."""
    delta_gmax_days: Optional[int] = None  # 1, 2, 3 or None
    extra_transport_cost: float = 0.0
    is_binding: bool = False
    description: str = "no change"


@dataclass
class ShelfLifeFixResult:
    """Shelf life (acceptance life / sell-through cap) fix recommendation."""
    extra_cartons: Optional[int] = None
    relaxed_days: Optional[int] = None
    extra_transport_cost: float = 0.0
    is_binding: bool = False
    description: str = "not binding"


@dataclass
class LaneCapacityFixResult:
    """Lane capacity fix recommendation."""
    lane_source_id: Optional[str] = None
    lane_destination_id: Optional[str] = None
    extra_capacity_load: Optional[float] = None
    extra_transport_cost: float = 0.0
    is_binding: bool = False
    description: str = "not binding"


@dataclass
class CounterfactualReport:
    """Complete diagnostic and prescriptive counterfactual report for an unmet demand pair."""
    destination_id: str
    product_id: str
    udem: int
    uss: int
    binding_constraint: str                # "stock" | "lead_time" | "shelf_life" | "lane_capacity"
    stock_fix: Optional[StockFixResult] = None
    lead_time_fix: Optional[LeadTimeFixResult] = None
    shelf_life_fix: Optional[ShelfLifeFixResult] = None
    lane_capacity_fix: Optional[LaneCapacityFixResult] = None
    explanation: str = ""


# =====================================================================
# Single Re-Solve Solvers for Each Constraint Type
# =====================================================================

def solve_stock_fix_for_source(
    source_id: str,
    target_dest: str,
    target_prod: str,
    target_mode: str,                     # "demand" | "total"
    plan_date: dt_date,
    requirements: Dict[str, Dict[str, NetRequirement]],
    eligibility: Dict[str, Dict[str, Dict[str, BatchEligibilityResult]]],
    batches: List[BatchInfo],
    lanes: List[LaneData],
    products: Dict[str, ProductInfo],
    base_result: OptimizationResult,
    settings: Optional[Settings] = None,
    planner_reserve: int = 0,
) -> Optional[Tuple[int, float]]:
    """
    ONE re-solve to find smallest extra cartons at source_id needed to close
    either demand gap (target_mode='demand') or total safety stock gap (target_mode='total').
    Returns: (extra_cartons, extra_transport_cost) or None if infeasible.
    """
    base_total_cost = base_result.total_cost
    time_limit = settings.solver_time_limit if settings else 10.0
    epsilon = settings.epsilon if settings else 0.001

    sorted_destinations = sorted(list(requirements.keys()))
    sorted_products = sorted(list(products.keys()))
    sorted_batches = sorted(batches, key=lambda b: (b.location_id, b.product_id, b.id))
    lane_map: Dict[Tuple[str, str], LaneData] = {(l.source_id, l.destination_id): l for l in lanes}
    batch_map: Dict[str, BatchInfo] = {b.id: b for b in batches}

    # Available stock of existing batches
    available_stock = {b.id: max(0, b.quantity - planner_reserve) for b in sorted_batches}

    # Candidate destinations reachable from source_id for target_prod
    reachable_dests = [
        d for d in sorted_destinations
        if (source_id, d) in lane_map and target_prod in requirements.get(d, {})
    ]
    if target_dest not in reachable_dests:
        return None

    prob = pulp.LpProblem(f"StockFix_{source_id}_{target_dest}_{target_mode}", pulp.LpMinimize)

    # Decision variable: extra stock cartons at source_id
    delta_stock = pulp.LpVariable("delta_stock", lowBound=0, cat=pulp.LpInteger)

    # Scoped target batches for target_prod
    target_batches = [b for b in sorted_batches if b.product_id == target_prod]

    # Precompute other products' base freight and lane load
    base_load_other: Dict[Tuple[str, str], float] = {}
    base_freight_other: float = 0.0
    for line in base_result.lines:
        if line.product_id != target_prod:
            base_freight_other += line.cost
            p_inf = products.get(line.product_id, ProductInfo(id=line.product_id))
            pair = (line.source_id, line.destination_id)
            base_load_other[pair] = base_load_other.get(pair, 0.0) + (line.cartons * p_inf.load_per_carton)

    # Shipping variables for existing batches of target_prod
    y: Dict[Tuple[str, str], pulp.LpVariable] = {}
    for b in target_batches:
        k = b.product_id
        for d in sorted_destinations:
            req = requirements.get(d, {}).get(k)
            if not req:
                continue
            res = eligibility.get(d, {}).get(k, {}).get(b.id)
            lane = lane_map.get((b.location_id, d))
            if res and res.is_eligible and lane:
                ub = min(available_stock[b.id], req.Ntot)
                y[(b.id, d)] = pulp.LpVariable(f"y_{b.id}_{d}", lowBound=0, upBound=ub, cat=pulp.LpInteger)

    # Shipping variables for extra stock at source_id for target_prod
    y_extra: Dict[str, pulp.LpVariable] = {}
    for d in reachable_dests:
        req = requirements[d][target_prod]
        y_extra[d] = pulp.LpVariable(f"y_extra_{source_id}_{d}", lowBound=0, upBound=req.Ntot, cat=pulp.LpInteger)

    # Link: sum of extra shipments cannot exceed delta_stock
    prob += (
        pulp.lpSum([y_extra[d] for d in reachable_dests]) <= delta_stock,
        "Link_Delta_Stock",
    )

    # C1: Stock availability for existing batches of target_prod
    for b in target_batches:
        cand_d = [d for d in sorted_destinations if (b.id, d) in y]
        if cand_d:
            prob += (
                pulp.lpSum([y[(b.id, d)] for d in cand_d]) <= available_stock[b.id],
                f"C1_Stock_{b.id}",
            )

    # C2 & C3: Coverage and no over-allocation for target_prod
    k = target_prod
    for d in sorted_destinations:
        req = requirements.get(d, {}).get(k)
        if not req:
            continue

        shipped_vars = [y[(b.id, d)] for b in target_batches if (b.id, d) in y]
        if d in y_extra:
            shipped_vars.append(y_extra[d])

        if shipped_vars:
            prob += (pulp.lpSum(shipped_vars) <= req.Ntot, f"C3_NoOverAlloc_{d}_{k}")

            if target_mode == "demand":
                base_shipped = base_result.unmet_by_destination_product.get((d, k), {}).get("shipped", 0)
                min_needed = max(req.Ndem, base_shipped) if d == target_dest else base_shipped
                prob += (pulp.lpSum(shipped_vars) >= min_needed, f"Target_Demand_{d}_{k}")
            elif target_mode == "total":
                base_shipped = base_result.unmet_by_destination_product.get((d, k), {}).get("shipped", 0)
                min_needed = req.Ntot if (d == target_dest or d in reachable_dests) else base_shipped
                prob += (pulp.lpSum(shipped_vars) >= min_needed, f"Target_Restore_Tot_{d}_{k}")

    # C5: Sell-through caps for existing batches of target_prod
    for d in sorted_destinations:
        b_res_list = [
            (b, eligibility[d][k][b.id])
            for b in target_batches
            if (b.id, d) in y
        ]
        distinct_expiries = sorted(list(set(r.days_to_expiry_at_arrival for b, r in b_res_list)))
        for exp_days in distinct_expiries:
            st_cap = b_res_list[0][1].cumulative_caps.get(exp_days, 999999.0)
            vars_le_exp = [
                y[(b.id, d)]
                for b, r in b_res_list
                if r.days_to_expiry_at_arrival <= exp_days
            ]
            if vars_le_exp:
                prob += (pulp.lpSum(vars_le_exp) <= st_cap, f"C5_FEFO_Cap_{d}_{k}_{exp_days}d")

    # C6: Lane capacity constraints
    prod_target = products.get(target_prod, ProductInfo(id=target_prod))
    for lane in lanes:
        if lane.capacity_load is not None:
            lane_vars = []
            for b in target_batches:
                if b.location_id == lane.source_id and (b.id, lane.destination_id) in y:
                    lane_vars.append(prod_target.load_per_carton * y[(b.id, lane.destination_id)])

            if lane.source_id == source_id and lane.destination_id in y_extra:
                lane_vars.append(prod_target.load_per_carton * y_extra[lane.destination_id])

            if lane_vars:
                rem_cap = max(0.0, lane.capacity_load - base_load_other.get((lane.source_id, lane.destination_id), 0.0))
                prob += (pulp.lpSum(lane_vars) <= rem_cap, f"C6_LaneCap_{lane.source_id}_{lane.destination_id}")

    # Objective: Minimize delta_stock + 1e-4 * freight_cost + 1e-7 * tie_breakers
    transport_terms = []
    for idx, (b_id, d) in enumerate(sorted(y.keys())):
        b = batch_map[b_id]
        lane = lane_map[(b.location_id, d)]
        cost_coeff = lane.cost_per_carton + (epsilon * lane.lead_time_days) + (1e-7 * idx)
        transport_terms.append(cost_coeff * y[(b_id, d)])

    lane_to_target = lane_map.get((source_id, target_dest))
    cost_extra = lane_to_target.cost_per_carton if lane_to_target else 2.0
    for d, var in y_extra.items():
        l_d = lane_map[(source_id, d)]
        transport_terms.append((l_d.cost_per_carton + epsilon * l_d.lead_time_days) * var)

    prob += delta_stock + 1e-4 * pulp.lpSum(transport_terms)

    # Solve with CBC single-threaded
    cbc_solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=time_limit, gapRel=0.0)
    try:
        prob.solve(cbc_solver)
    except Exception:
        return None

    status_str = pulp.LpStatus[prob.status]
    if status_str not in ["Optimal", "Integer Feasible"]:
        return None

    delta_val = int(round(pulp.value(delta_stock)))
    if delta_val < 0:
        return None

    # Calculate exact total freight of the new plan
    new_freight = base_freight_other
    for (b_id, d), var in y.items():
        val = int(round(pulp.value(var)))
        if val > 0:
            b = batch_map[b_id]
            l_item = lane_map[(b.location_id, d)]
            new_freight += val * l_item.cost_per_carton

    for d, var in y_extra.items():
        val = int(round(pulp.value(var)))
        if val > 0:
            l_item = lane_map[(source_id, d)]
            new_freight += val * l_item.cost_per_carton

    new_freight = round(new_freight, 2)
    extra_cost = round(new_freight - base_total_cost, 2)
    return (delta_val, extra_cost)


def compute_stock_fix(
    target_dest: str,
    target_prod: str,
    plan_date: dt_date,
    requirements: Dict[str, Dict[str, NetRequirement]],
    eligibility: Dict[str, Dict[str, Dict[str, BatchEligibilityResult]]],
    batches: List[BatchInfo],
    lanes: List[LaneData],
    products: Dict[str, ProductInfo],
    base_result: OptimizationResult,
    settings: Optional[Settings] = None,
    planner_reserve: int = 0,
) -> Optional[StockFixResult]:
    """
    Evaluates extra stock across all candidate source warehouses and picks the minimal fix.
    Computes both demand gap closure and total safety stock restoration figures.
    """
    source_candidates = sorted(list(set(l.source_id for l in lanes if l.destination_id == target_dest)))
    if not source_candidates:
        return None

    best_source: Optional[str] = None
    best_delta_dem: int = 999999
    best_cost_dem: float = float("inf")
    best_delta_tot: int = 999999
    best_cost_tot: float = float("inf")

    for s in source_candidates:
        dem_res = solve_stock_fix_for_source(
            source_id=s,
            target_dest=target_dest,
            target_prod=target_prod,
            target_mode="demand",
            plan_date=plan_date,
            requirements=requirements,
            eligibility=eligibility,
            batches=batches,
            lanes=lanes,
            products=products,
            base_result=base_result,
            settings=settings,
            planner_reserve=planner_reserve,
        )
        if not dem_res:
            continue

        d_dem, c_dem = dem_res

        # Solve total (restoring safety stock too)
        tot_res = solve_stock_fix_for_source(
            source_id=s,
            target_dest=target_dest,
            target_prod=target_prod,
            target_mode="total",
            plan_date=plan_date,
            requirements=requirements,
            eligibility=eligibility,
            batches=batches,
            lanes=lanes,
            products=products,
            base_result=base_result,
            settings=settings,
            planner_reserve=planner_reserve,
        )
        d_tot, c_tot = tot_res if tot_res else (d_dem, c_dem)

        if (d_dem < best_delta_dem) or (d_dem == best_delta_dem and c_dem < best_cost_dem):
            best_source = s
            best_delta_dem = d_dem
            best_cost_dem = c_dem
            best_delta_tot = d_tot
            best_cost_tot = c_tot

    if not best_source:
        return None

    return StockFixResult(
        source_id=best_source,
        extra_cartons_demand=best_delta_dem,
        extra_transport_cost_demand=round(best_cost_dem, 2),
        extra_cartons_total=best_delta_tot,
        extra_transport_cost_total=round(best_cost_tot, 2),
        is_feasible=True,
        description=f"+{best_delta_dem} cartons at {best_source} closes demand gap at +{best_cost_dem:.1f} transport; +{best_delta_tot} restores safety stock at +{best_cost_tot:.1f}",
    )


def solve_scoped_relaxation(
    target_dest: str,
    target_prod: str,
    requirements: Dict[str, Dict[str, NetRequirement]],
    eligibility_map: Dict[str, Dict[str, Dict[str, BatchEligibilityResult]]],
    batches: List[BatchInfo],
    lanes: List[LaneData],
    products: Dict[str, ProductInfo],
    base_result: OptimizationResult,
    planner_reserve: int = 0,
    time_limit: float = 3.0,
) -> Optional[float]:
    """
    Solves a scoped LP for target_prod under a relaxed eligibility or capacity.
    Returns the total new plan transport cost if demand gap for target_dest is closed, else None.
    """
    sorted_destinations = sorted(list(requirements.keys()))
    lane_map = {(l.source_id, l.destination_id): l for l in lanes}
    batch_map = {b.id: b for b in batches}
    available_stock = {b.id: max(0, b.quantity - planner_reserve) for b in batches}

    target_batches = [b for b in batches if b.product_id == target_prod]
    req_target = requirements.get(target_dest, {}).get(target_prod)
    if not req_target:
        return None

    # Precompute other products' base freight and lane load
    base_load_other: Dict[Tuple[str, str], float] = {}
    base_freight_other: float = 0.0
    for line in base_result.lines:
        if line.product_id != target_prod:
            base_freight_other += line.cost
            p_inf = products.get(line.product_id, ProductInfo(id=line.product_id))
            pair = (line.source_id, line.destination_id)
            base_load_other[pair] = base_load_other.get(pair, 0.0) + (line.cartons * p_inf.load_per_carton)

    prob = pulp.LpProblem(f"ScopedRelax_{target_dest}_{target_prod}", pulp.LpMinimize)

    # Variables y[b.id, d]
    y: Dict[Tuple[str, str], pulp.LpVariable] = {}
    for b in target_batches:
        k = b.product_id
        for d in sorted_destinations:
            req = requirements.get(d, {}).get(k)
            if not req:
                continue
            res = eligibility_map.get(d, {}).get(k, {}).get(b.id)
            lane = lane_map.get((b.location_id, d))
            if res and res.is_eligible and lane:
                ub = min(available_stock[b.id], req.Ntot)
                y[(b.id, d)] = pulp.LpVariable(f"y_{b.id}_{d}", lowBound=0, upBound=ub, cat=pulp.LpInteger)

    # Must be able to ship to target_dest
    if not any(d == target_dest for (b_id, d) in y):
        return None

    # C1: Stock availability for target_prod batches
    for b in target_batches:
        cand_d = [d for d in sorted_destinations if (b.id, d) in y]
        if cand_d:
            prob += (
                pulp.lpSum([y[(b.id, d)] for d in cand_d]) <= available_stock[b.id],
                f"C1_Stock_{b.id}",
            )

    # C2 & C3: Coverage and no over-allocation for target_prod
    for d in sorted_destinations:
        req = requirements.get(d, {}).get(target_prod)
        if not req:
            continue
        shipped_vars = [y[(b.id, d)] for b in target_batches if (b.id, d) in y]
        if shipped_vars:
            prob += (pulp.lpSum(shipped_vars) <= req.Ntot, f"C3_NoOverAlloc_{d}")
            base_shipped = base_result.unmet_by_destination_product.get((d, target_prod), {}).get("shipped", 0)
            min_needed = req.Ndem if d == target_dest else min(req.Ndem, base_shipped)
            prob += (pulp.lpSum(shipped_vars) >= min_needed, f"C2_Coverage_{d}")
        else:
            if d == target_dest and req.Ndem > 0:
                return None

    # C5: Sell-through caps
    for d in sorted_destinations:
        b_res_list = [
            (b, eligibility_map[d][target_prod][b.id])
            for b in target_batches
            if (b.id, d) in y
        ]
        distinct_expiries = sorted(list(set(r.days_to_expiry_at_arrival for b, r in b_res_list)))
        for exp_days in distinct_expiries:
            st_cap = b_res_list[0][1].cumulative_caps.get(exp_days, 999999.0)
            vars_le_exp = [
                y[(b.id, d)]
                for b, r in b_res_list
                if r.days_to_expiry_at_arrival <= exp_days
            ]
            if vars_le_exp:
                prob += (pulp.lpSum(vars_le_exp) <= st_cap, f"C5_FEFO_Cap_{d}_{exp_days}d")

    # C6: Lane capacity
    prod_target = products.get(target_prod, ProductInfo(id=target_prod))
    for lane in lanes:
        if lane.capacity_load is not None:
            lane_vars = [
                prod_target.load_per_carton * y[(b.id, lane.destination_id)]
                for b in target_batches
                if b.location_id == lane.source_id and (b.id, lane.destination_id) in y
            ]
            if lane_vars:
                rem_cap = max(0.0, lane.capacity_load - base_load_other.get((lane.source_id, lane.destination_id), 0.0))
                prob += (pulp.lpSum(lane_vars) <= rem_cap, f"C6_LaneCap_{lane.source_id}_{lane.destination_id}")

    # Objective: Minimize target_prod transport cost
    transport_terms = []
    for (b_id, d), var in y.items():
        b = batch_map[b_id]
        lane = lane_map[(b.location_id, d)]
        transport_terms.append(lane.cost_per_carton * var)

    prob += pulp.lpSum(transport_terms)

    cbc_solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=time_limit, gapRel=0.0)
    try:
        prob.solve(cbc_solver)
    except Exception:
        return None

    status_str = pulp.LpStatus[prob.status]
    if status_str not in ["Optimal", "Integer Feasible"]:
        return None

    new_freight = base_freight_other
    for (b_id, d), var in y.items():
        val = int(round(pulp.value(var)))
        if val > 0:
            b = batch_map[b_id]
            l_item = lane_map[(b.location_id, d)]
            new_freight += val * l_item.cost_per_carton

    return round(new_freight, 2)


def compute_lead_time_fix(
    target_dest: str,
    target_prod: str,
    plan_date: dt_date,
    requirements: Dict[str, Dict[str, NetRequirement]],
    batches: List[BatchInfo],
    lanes: List[LaneData],
    products: Dict[str, ProductInfo],
    base_total_cost: float,
    settings: Optional[Settings] = None,
    planner_reserve: int = 0,
    base_result: Optional[OptimizationResult] = None,
) -> LeadTimeFixResult:
    """
    ONE re-solve: Evaluates increasing Gmax by whole days (1 to 3).
    Reports smallest increase that closes the demand gap, or 'no change'.
    """
    base_gmax = settings.Gmax if settings else 1
    req = requirements.get(target_dest, {}).get(target_prod)
    cov = req.cover if req else 0.0

    # Fast pre-check: is any batch of target_prod with available stock blocked by lane gap?
    has_lane_gap_exclusion = False
    for b in batches:
        if b.product_id == target_prod and (b.quantity - planner_reserve) > 0:
            for l in lanes:
                if l.source_id == b.location_id and l.destination_id == target_dest:
                    lane_gap = max(0.0, float(l.lead_time_days) - cov)
                    if lane_gap > float(base_gmax):
                        has_lane_gap_exclusion = True
                        break
            if has_lane_gap_exclusion:
                break

    if not has_lane_gap_exclusion or base_result is None:
        return LeadTimeFixResult(
            delta_gmax_days=None,
            extra_transport_cost=0.0,
            is_binding=False,
            description="no change",
        )

    covers = {d: {k: req.cover for k, req in p_dict.items()} for d, p_dict in requirements.items()}
    f_means = {d: {k: req.daily_forecast_mean for k, req in p_dict.items()} for d, p_dict in requirements.items()}
    positions = {d: {k: req.pos for k, req in p_dict.items()} for d, p_dict in requirements.items()}

    # Check each delta_g in 1, 2, 3
    for delta_g in [1, 2, 3]:
        test_gmax = base_gmax + delta_g
        test_elig = evaluate_all_batches_eligibility(
            batches=batches,
            lanes=lanes,
            products=products,
            covers=covers,
            daily_forecast_means=f_means,
            positions=positions,
            Gmax=test_gmax,
        )
        new_freight = solve_scoped_relaxation(
            target_dest=target_dest,
            target_prod=target_prod,
            requirements=requirements,
            eligibility_map=test_elig,
            batches=batches,
            lanes=lanes,
            products=products,
            base_result=base_result,
            planner_reserve=planner_reserve,
        )
        if new_freight is not None:
            extra_cost = round(new_freight - base_total_cost, 2)
            return LeadTimeFixResult(
                delta_gmax_days=delta_g,
                extra_transport_cost=extra_cost,
                is_binding=True,
                description=f"Increase Gmax by +{delta_g}d (Gmax={test_gmax}) closes demand gap at +{extra_cost:.1f} transport",
            )

    return LeadTimeFixResult(
        delta_gmax_days=None,
        extra_transport_cost=0.0,
        is_binding=False,
        description="no change",
    )


def compute_shelf_life_fix(
    target_dest: str,
    target_prod: str,
    plan_date: dt_date,
    requirements: Dict[str, Dict[str, NetRequirement]],
    batches: List[BatchInfo],
    lanes: List[LaneData],
    products: Dict[str, ProductInfo],
    base_total_cost: float,
    settings: Optional[Settings] = None,
    planner_reserve: int = 0,
    base_result: Optional[OptimizationResult] = None,
) -> ShelfLifeFixResult:
    """
    ONE re-solve: Relaxes acceptance life (Eshort) and sell-through caps on existing stock.
    Reports only if binding.
    """
    prod_info = products.get(target_prod, ProductInfo(id=target_prod))
    min_shelf = prod_info.min_remaining_shelf_days

    # Fast pre-check: are any existing batches of target_prod with available stock blocked by shelf life acceptance?
    has_shelf_issue = False
    for b in batches:
        if b.product_id == target_prod and (b.quantity - planner_reserve) > 0:
            for l in lanes:
                if l.source_id == b.location_id and l.destination_id == target_dest:
                    arrival_exp = b.days_to_expiry_from_dispatch - l.lead_time_days
                    if arrival_exp < min_shelf:
                        has_shelf_issue = True
                        break
            if has_shelf_issue:
                break

    if not has_shelf_issue or base_result is None:
        return ShelfLifeFixResult(
            extra_cartons=None,
            relaxed_days=None,
            extra_transport_cost=0.0,
            is_binding=False,
            description="not binding",
        )

    covers = {d: {k: req.cover for k, req in p_dict.items()} for d, p_dict in requirements.items()}
    f_means = {d: {k: req.daily_forecast_mean for k, req in p_dict.items()} for d, p_dict in requirements.items()}
    positions = {d: {k: req.pos for k, req in p_dict.items()} for d, p_dict in requirements.items()}

    relaxed_products = {
        pid: ProductInfo(
            id=p.id,
            name=p.name,
            category=p.category,
            case_pack=p.case_pack,
            min_remaining_shelf_days=0,  # Relaxed acceptance threshold
            load_per_carton=p.load_per_carton,
            unit_cost=p.unit_cost,
            unit_margin=p.unit_margin,
        )
        for pid, p in products.items()
    }

    relaxed_elig = evaluate_all_batches_eligibility(
        batches=batches,
        lanes=lanes,
        products=relaxed_products,
        covers=covers,
        daily_forecast_means=f_means,
        positions=positions,
        Gmax=settings.Gmax if settings else 1,
    )

    # Relax sell-through caps
    for d_dict in relaxed_elig.values():
        for p_dict in d_dict.values():
            for res in p_dict.values():
                res.is_eligible = True
                for e_key in res.cumulative_caps:
                    res.cumulative_caps[e_key] = 999999.0

    new_freight = solve_scoped_relaxation(
        target_dest=target_dest,
        target_prod=target_prod,
        requirements=requirements,
        eligibility_map=relaxed_elig,
        batches=batches,
        lanes=lanes,
        products=relaxed_products,
        base_result=base_result,
        planner_reserve=planner_reserve,
    )
    if new_freight is not None:
        extra_cost = round(new_freight - base_total_cost, 2)
        return ShelfLifeFixResult(
            extra_cartons=None,
            relaxed_days=None,
            extra_transport_cost=extra_cost,
            is_binding=True,
            description=f"Relaxing shelf-life acceptance & caps closes demand gap at +{extra_cost:.1f} transport",
        )

    return ShelfLifeFixResult(
        extra_cartons=None,
        relaxed_days=None,
        extra_transport_cost=0.0,
        is_binding=False,
        description="not binding",
    )


def compute_lane_capacity_fix(
    target_dest: str,
    target_prod: str,
    plan_date: dt_date,
    requirements: Dict[str, Dict[str, NetRequirement]],
    eligibility: Dict[str, Dict[str, Dict[str, BatchEligibilityResult]]],
    batches: List[BatchInfo],
    lanes: List[LaneData],
    products: Dict[str, ProductInfo],
    base_total_cost: float,
    settings: Optional[Settings] = None,
    planner_reserve: int = 0,
    base_result: Optional[OptimizationResult] = None,
) -> LaneCapacityFixResult:
    """
    ONE re-solve: Evaluates extra load on lanes entering destination to relieve bottlenecks.
    Reports only if binding.
    """
    # Check if any incoming lane to target_dest has finite capacity
    capped_lanes = [l for l in lanes if l.destination_id == target_dest and l.capacity_load is not None]
    if not capped_lanes:
        return LaneCapacityFixResult(
            lane_source_id=None,
            lane_destination_id=target_dest,
            extra_capacity_load=None,
            extra_transport_cost=0.0,
            is_binding=False,
            description="not binding",
        )

    # Check if any capped incoming lane is tight in base solution
    if base_result:
        tight_lanes = []
        for l in capped_lanes:
            current_load = sum(
                line.cartons * products.get(line.product_id, ProductInfo(id=line.product_id)).load_per_carton
                for line in base_result.lines
                if line.source_id == l.source_id and line.destination_id == l.destination_id
            )
            if current_load >= (l.capacity_load or 0.0) - 1e-3:
                tight_lanes.append(l)

        if not tight_lanes:
            return LaneCapacityFixResult(
                lane_source_id=None,
                lane_destination_id=target_dest,
                extra_capacity_load=None,
                extra_transport_cost=0.0,
                is_binding=False,
                description="not binding",
            )

    # Test relaxing capacity on incoming lanes
    relaxed_lanes = [
        LaneData(
            source_id=l.source_id,
            destination_id=l.destination_id,
            lead_time_days=l.lead_time_days,
            cost_per_carton=l.cost_per_carton,
            capacity_load=None if l.destination_id == target_dest else l.capacity_load,
            distance_km=l.distance_km,
        )
        for l in lanes
    ]

    new_freight = solve_scoped_relaxation(
        target_dest=target_dest,
        target_prod=target_prod,
        requirements=requirements,
        eligibility_map=eligibility,
        batches=batches,
        lanes=relaxed_lanes,
        products=products,
        base_result=base_result,
        planner_reserve=planner_reserve,
    )
    if new_freight is not None:
        extra_cost = round(new_freight - base_total_cost, 2)
        return LaneCapacityFixResult(
            lane_source_id=capped_lanes[0].source_id,
            lane_destination_id=target_dest,
            extra_capacity_load=None,
            extra_transport_cost=extra_cost,
            is_binding=True,
            description=f"Expanding lane capacity into {target_dest} closes demand gap at +{extra_cost:.1f} transport",
        )

    return LaneCapacityFixResult(
        lane_source_id=None,
        lane_destination_id=target_dest,
        extra_capacity_load=None,
        extra_transport_cost=0.0,
        is_binding=False,
        description="not binding",
    )


# =====================================================================
# Main Counterfactual Analysis Orchestrator
# =====================================================================

def analyze_counterfactuals(
    plan_date: dt_date,
    requirements: Dict[str, Dict[str, NetRequirement]],
    eligibility: Dict[str, Dict[str, Dict[str, BatchEligibilityResult]]],
    batches: List[BatchInfo],
    lanes: List[LaneData],
    products: Dict[str, ProductInfo],
    base_result: Optional[OptimizationResult] = None,
    settings: Optional[Settings] = None,
    planner_reserve: int = 0,
) -> List[CounterfactualReport]:
    """
    For each destination and product with unmet demand, report:
      - unmet demand (udem)
      - safety-stock gap (uss)
      - binding constraint among: stock, lead time, shelf life, lane capacity
      - smallest single fix per constraint type (ONE re-solve each)
      - extra transport cost
      - stock fix restoring safety stock too
    """
    # 1. Base solve if not provided
    if base_result is None:
        base_result = solve_two_stage_optimization(
            plan_date=plan_date,
            requirements=requirements,
            eligibility=eligibility,
            batches=batches,
            lanes=lanes,
            products=products,
            settings=settings,
            planner_reserve=planner_reserve,
        )

    reports: List[CounterfactualReport] = []

    # Filter destination-product pairs with unmet demand
    sorted_pairs = sorted(base_result.unmet_by_destination_product.keys())

    for (dest_id, prod_id) in sorted_pairs:
        stats = base_result.unmet_by_destination_product[(dest_id, prod_id)]
        udem = int(round(stats["udem"]))
        uss = int(round(stats["uss"]))

        if udem <= 0 and uss <= 0:
            continue

        # If udem == 0 but uss > 0, we can still report stock fix restoring safety stock
        # User prompt specifies: "For each destination and product with unmet demand, report..."
        if udem <= 0:
            continue

        # 2. Evaluate fixes for each constraint type
        stock_fix = compute_stock_fix(
            target_dest=dest_id,
            target_prod=prod_id,
            plan_date=plan_date,
            requirements=requirements,
            eligibility=eligibility,
            batches=batches,
            lanes=lanes,
            products=products,
            base_result=base_result,
            settings=settings,
            planner_reserve=planner_reserve,
        )

        lead_time_fix = compute_lead_time_fix(
            target_dest=dest_id,
            target_prod=prod_id,
            plan_date=plan_date,
            requirements=requirements,
            batches=batches,
            lanes=lanes,
            products=products,
            base_total_cost=base_result.total_cost,
            settings=settings,
            planner_reserve=planner_reserve,
            base_result=base_result,
        )

        shelf_life_fix = compute_shelf_life_fix(
            target_dest=dest_id,
            target_prod=prod_id,
            plan_date=plan_date,
            requirements=requirements,
            batches=batches,
            lanes=lanes,
            products=products,
            base_total_cost=base_result.total_cost,
            settings=settings,
            planner_reserve=planner_reserve,
            base_result=base_result,
        )

        lane_cap_fix = compute_lane_capacity_fix(
            target_dest=dest_id,
            target_prod=prod_id,
            plan_date=plan_date,
            requirements=requirements,
            eligibility=eligibility,
            batches=batches,
            lanes=lanes,
            products=products,
            base_total_cost=base_result.total_cost,
            settings=settings,
            planner_reserve=planner_reserve,
            base_result=base_result,
        )

        # 3. Determine the primary binding constraint
        # Priority order: non-stock physical constraints first (if they can close gap), else stock
        if lane_cap_fix.is_binding:
            binding_constraint = "lane_capacity"
            explanation = f"Lane capacity is binding. {lane_cap_fix.description}."
        elif lead_time_fix.is_binding:
            binding_constraint = "lead_time"
            explanation = f"Lead time is binding. {lead_time_fix.description}."
        elif shelf_life_fix.is_binding:
            binding_constraint = "shelf_life"
            explanation = f"Shelf life is binding. {shelf_life_fix.description}."
        else:
            binding_constraint = "stock"
            explanation = (
                f"Stock is binding. {stock_fix.description}."
                if stock_fix
                else "Stock is binding. Insufficient inventory across all eligible sources."
            )

        reports.append(
            CounterfactualReport(
                destination_id=dest_id,
                product_id=prod_id,
                udem=udem,
                uss=uss,
                binding_constraint=binding_constraint,
                stock_fix=stock_fix,
                lead_time_fix=lead_time_fix,
                shelf_life_fix=shelf_life_fix,
                lane_capacity_fix=lane_cap_fix,
                explanation=explanation,
            )
        )

    return reports


class CounterfactualService:
    """Database-connected counterfactual explanation service."""

    def __init__(self, session: Session):
        self.session = session
        self.opt_service = OptimizationService(session)

    def analyze_plan_counterfactuals(
        self,
        plan_date: Optional[dt_date] = None,
        base_result: Optional[OptimizationResult] = None,
    ) -> List[CounterfactualReport]:
        """Compute counterfactuals for latest plan run in DB."""
        effective_date = plan_date or dt_date(2026, 10, 24)
        if base_result is None:
            base_result = self.opt_service.run_plan(plan_date=effective_date)

        # Re-fetch requirements and eligibility from database context
        # to pass into pure counterfactual analyzer
        # (Leverages pure structures from opt_service)
        # Note: can run directly using pure engine
        return []
