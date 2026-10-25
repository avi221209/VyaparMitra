"""
VyaparMitra - Two-Stage Deterministic Integer Programming Optimizer (PuLP + CBC)
Distribution Planning and Inventory Optimization Engine

Pure core optimization engine with CBC MILP solver and Greedy Heuristic fallback (Baseline C).

Variables:
 - y[b,d,k] >= 0 integer: Cartons shipped from batch b to destination d
 - udem[d,k] >= 0: Unmet base demand
 - utot[d,k] >= 0: Unmet total requirement (demand + safety stock)
 - uss[d,k] = utot[d,k] - udem[d,k] >= 0: Safety stock gap

Constraints:
 C1: Batch stock availability (after planner reserve)
 C2: Coverage: sum_b y + udem >= Ndem ; sum_b y + utot >= Ntot
 C3: No over-allocation: sum_b y <= Ntot
 C4: Eligibility: y = 0 where lane gap or acceptance-life fails
 C5: Cumulative FEFO sell-through caps
 C6: Lane capacity: sum_k load_per_carton * cartons <= capacity

Lexicographic Objectives:
 Stage 1 (Service First): minimize sum w_k * (udem + alpha * uss), w_k = unit margin
 Stage 2 (Cost Second): Stage-1 objective <= V1 + 1e-6,
                        minimize sum lane_cost * cartons + sum omega_k * stranded + epsilon * sum lead_time * cartons
"""

from dataclasses import dataclass, field
from datetime import date as dt_date, timedelta
import json
import math
import time
from typing import Any, Dict, List, Optional, Tuple
import pulp
from sqlmodel import Session, select

from backend.app.models import (
    Batch,
    DecisionLog,
    InventorySnapshot,
    Lane,
    Location,
    PlanLine,
    PlanRun,
    Product,
    SalesDaily,
    Settings,
)
from backend.app.services.eligibility import (
    BatchEligibilityResult,
    BatchInfo,
    LaneData,
    ProductInfo,
    evaluate_all_batches_eligibility,
)
from backend.app.services.forecast import ForecastService
from backend.app.services.requirement import (
    LaneInfo,
    NetRequirement,
    compute_all_net_requirements,
)
from backend.app.settings import get_current_settings


@dataclass
class AllocationLine:
    """Individual line item allocated by the optimizer or heuristic."""
    batch_id: str
    source_id: str
    destination_id: str
    product_id: str
    cartons: int
    cost: float
    arrival_date: dt_date
    lead_time_days: int
    flags: List[str] = field(default_factory=list)
    explanation: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OptimizationResult:
    """Complete output of the optimization engine."""
    run_id: str
    plan_date: dt_date
    status: str                         # "OPTIMIZED" | "HEURISTIC" | "FEASIBLE"
    lines: List[AllocationLine]
    total_cost: float
    total_cartons: int
    total_demand_cartons: int
    total_unmet_demand_cartons: int
    total_unmet_safety_stock_cartons: int
    unmet_by_destination_product: Dict[Tuple[str, str], Dict[str, float]]
    stage1_objective: float
    stage2_objective: float
    solver_status: str
    solve_time_seconds: float
    counterfactuals: List[Any] = field(default_factory=list)
    is_simulated: bool = True


# =====================================================================
# Fallback Heuristic (Baseline C)
# =====================================================================
def run_greedy_heuristic(
    plan_date: dt_date,
    requirements: Dict[str, Dict[str, NetRequirement]],
    eligibility: Dict[str, Dict[str, Dict[str, BatchEligibilityResult]]],
    batches: List[BatchInfo],
    lanes: List[LaneData],
    products: Dict[str, ProductInfo],
    planner_reserve: int = 0,
    run_id: Optional[str] = None,
) -> OptimizationResult:
    """
    Greedy heuristic fallback (Baseline C):
      1. Destination urgency: lowest inventory cover (pos / f) first, ties broken by unit margin.
      2. Nearest eligible source: lowest lead time, then lowest lane cost.
      3. First-Expiry-First-Out (FEFO): earliest expiry date.
      4. Label plan as 'heuristic'.
    """
    start_time = time.time()
    effective_run_id = run_id or f"RUN-{plan_date.strftime('%Y%m%d')}-HEURISTIC"

    # Lane and batch lookup maps
    lane_map: Dict[Tuple[str, str], LaneData] = {(l.source_id, l.destination_id): l for l in lanes}
    batch_map: Dict[str, BatchInfo] = {b.id: b for b in batches}

    # Available stock per batch
    batch_remaining: Dict[str, int] = {
        b.id: max(0, b.quantity - planner_reserve) for b in batches
    }

    # Available lane capacity
    lane_capacity_remaining: Dict[Tuple[str, str], Optional[float]] = {
        (l.source_id, l.destination_id): l.capacity_load for l in lanes
    }

    # Cumulative sell-through caps remaining per (destination, product, expiry)
    sell_through_remaining: Dict[Tuple[str, str, int], float] = {}
    for d, p_dict in eligibility.items():
        for k, b_dict in p_dict.items():
            for b_id, res in b_dict.items():
                for exp_days, cap in res.cumulative_caps.items():
                    key = (d, k, exp_days)
                    if key not in sell_through_remaining:
                        sell_through_remaining[key] = cap

    # Flatten and order destination-product pairs by urgency (lowest cover first)
    dest_prod_list: List[Tuple[str, str, NetRequirement]] = []
    for d, p_dict in requirements.items():
        for k, req in p_dict.items():
            dest_prod_list.append((d, k, req))

    # Sort: lowest cover first (inf last), then higher unit margin, then d, k
    def urgency_key(item: Tuple[str, str, NetRequirement]) -> Tuple[float, float, str, str]:
        d, k, req = item
        prod = products.get(k, ProductInfo(id=k))
        cov = req.cover if not math.isinf(req.cover) else 999999.0
        return (cov, -prod.load_per_carton, d, k)

    dest_prod_list.sort(key=urgency_key)

    lines: List[AllocationLine] = []
    total_shipped_cartons = 0
    total_transport_cost = 0.0

    # Shipped per (d, k)
    shipped_by_dest_prod: Dict[Tuple[str, str], int] = {}

    for d, k, req in dest_prod_list:
        needed_cartons = req.Ntot
        shipped_by_dest_prod[(d, k)] = 0

        # Candidate eligible batches for (d, k)
        cand_batches = [b for b in batches if b.product_id == k and batch_remaining[b.id] > 0]

        # Filter by eligibility
        eligible_candidates: List[Tuple[BatchInfo, LaneData, BatchEligibilityResult]] = []
        for b in cand_batches:
            res = eligibility.get(d, {}).get(k, {}).get(b.id)
            lane = lane_map.get((b.location_id, d))
            if res and res.is_eligible and lane:
                eligible_candidates.append((b, lane, res))

        # Sort candidate batches: FEFO (earliest expiry), nearest source (lead time, cost), batch ID
        eligible_candidates.sort(
            key=lambda item: (
                item[2].days_to_expiry_at_arrival,
                item[1].lead_time_days,
                item[1].cost_per_carton,
                item[0].id,
            )
        )

        for b, lane, res in eligible_candidates:
            if needed_cartons <= 0:
                break
            if batch_remaining[b.id] <= 0:
                continue

            lane_key = (lane.source_id, lane.destination_id)
            prod = products.get(k, ProductInfo(id=k))

            # Constraints on maximum allocatable cartons
            max_alloc = min(needed_cartons, batch_remaining[b.id])

            # Check lane capacity
            if lane_capacity_remaining.get(lane_key) is not None:
                cap_rem = lane_capacity_remaining[lane_key]
                if cap_rem is not None and prod.load_per_carton > 0:
                    max_by_lane = int(cap_rem / prod.load_per_carton)
                    max_alloc = min(max_alloc, max_by_lane)

            # Check sell-through cap
            exp_days = res.days_to_expiry_at_arrival
            st_key = (d, k, exp_days)
            if st_key in sell_through_remaining:
                max_alloc = min(max_alloc, int(sell_through_remaining[st_key]))

            if max_alloc <= 0:
                continue

            # Allocate
            alloc_cartons = max_alloc
            line_cost = round(alloc_cartons * lane.cost_per_carton, 2)
            arrival_date = plan_date + timedelta(days=lane.lead_time_days)

            # Flags & Explanations
            flags: List[str] = []
            explanation: Dict[str, Any] = {
                "source": lane.source_id,
                "destination": lane.destination_id,
                "lead_time_days": lane.lead_time_days,
                "lane_cost_per_carton": lane.cost_per_carton,
                "allocated_cartons": alloc_cartons,
                "batch_days_to_expiry_at_arrival": exp_days,
            }

            if res.lane_gap > 0.0:
                flags.append("LANE_GAP_RISK")
                flags.append(f"expected lost sales: {round(res.unavoidable_lost_sales, 1):.1f} units")
                explanation["lane_gap"] = round(res.lane_gap, 2)
                explanation["expected_lost_sales"] = round(res.unavoidable_lost_sales, 1)
                explanation["unavoidable_lost_sales"] = round(res.unavoidable_lost_sales, 1)

            # Economic check: lane cost > unit margin
            unit_margin_carton = getattr(prod, "unit_margin", 20.0) or 20.0
            if lane.cost_per_carton > unit_margin_carton:
                flags.append("UNECONOMIC_SERVICE_FIRST")
                flags.append("uneconomic, service-first")
                explanation["uneconomic_note"] = "Freight cost exceeds gross margin (Service-First)"

            lines.append(
                AllocationLine(
                    batch_id=b.id,
                    source_id=lane.source_id,
                    destination_id=d,
                    product_id=k,
                    cartons=alloc_cartons,
                    cost=line_cost,
                    arrival_date=arrival_date,
                    lead_time_days=lane.lead_time_days,
                    flags=flags,
                    explanation=explanation,
                )
            )

            # Update remaining tracking
            batch_remaining[b.id] -= alloc_cartons
            if lane_capacity_remaining.get(lane_key) is not None:
                lane_capacity_remaining[lane_key] -= (alloc_cartons * prod.load_per_carton)
            if st_key in sell_through_remaining:
                sell_through_remaining[st_key] -= alloc_cartons

            needed_cartons -= alloc_cartons
            shipped_by_dest_prod[(d, k)] += alloc_cartons
            total_shipped_cartons += alloc_cartons
            total_transport_cost += line_cost

    # Calculate unmet statistics
    total_demand = 0
    total_unmet_demand = 0
    total_unmet_safety_stock = 0
    unmet_by_dest_prod: Dict[Tuple[str, str], Dict[str, float]] = {}

    for d, k, req in dest_prod_list:
        shipped = shipped_by_dest_prod.get((d, k), 0)
        udem = max(0, req.Ndem - shipped)
        utot = max(0, req.Ntot - shipped)
        uss = utot - udem

        total_demand += req.Ndem
        total_unmet_demand += udem
        total_unmet_safety_stock += uss

        unmet_by_dest_prod[(d, k)] = {
            "Ndem": req.Ndem,
            "Ntot": req.Ntot,
            "shipped": shipped,
            "udem": udem,
            "utot": utot,
            "uss": uss,
        }

    # Assert total cost equals sum of line costs
    sum_line_costs = round(sum(l.cost for l in lines), 2)
    assert abs(round(total_transport_cost, 2) - sum_line_costs) < 1e-4, "Total cost does not equal sum of line costs"

    elapsed = time.time() - start_time
    return OptimizationResult(
        run_id=effective_run_id,
        plan_date=plan_date,
        status="HEURISTIC",
        lines=lines,
        total_cost=round(total_transport_cost, 2),
        total_cartons=total_shipped_cartons,
        total_demand_cartons=total_demand,
        total_unmet_demand_cartons=total_unmet_demand,
        total_unmet_safety_stock_cartons=total_unmet_safety_stock,
        unmet_by_destination_product=unmet_by_dest_prod,
        stage1_objective=float(total_unmet_demand + 0.25 * total_unmet_safety_stock),
        stage2_objective=round(total_transport_cost, 2),
        solver_status="FALLBACK_HEURISTIC",
        solve_time_seconds=round(elapsed, 4),
        is_simulated=True,
    )


# =====================================================================
# Two-Stage Integer Program (PuLP + CBC)
# =====================================================================
def solve_two_stage_optimization(
    plan_date: dt_date,
    requirements: Dict[str, Dict[str, NetRequirement]],
    eligibility: Dict[str, Dict[str, Dict[str, BatchEligibilityResult]]],
    batches: List[BatchInfo],
    lanes: List[LaneData],
    products: Dict[str, ProductInfo],
    settings: Optional[Settings] = None,
    planner_reserve: int = 0,
    run_id: Optional[str] = None,
    force_heuristic: bool = False,
) -> OptimizationResult:
    """
    Two-Stage Lexicographic Integer Program:
      Stage 1: Minimize unmet demand and safety-stock gap weighted by unit margin:
               min sum w_k * (udem + alpha * uss) -> optimal value V1
      Stage 2: Restrict Stage 1 objective <= V1 + 1e-6:
               min sum lane_cost * cartons + sum omega_k * stranded + epsilon * sum lead_time * cartons

    Deterministic variable ordering and fixed solver options.
    Falls back to run_greedy_heuristic if CBC solver times out or errors.
    """
    start_time = time.time()
    effective_run_id = run_id or f"RUN-{plan_date.strftime('%Y%m%d')}"

    if force_heuristic:
        return run_greedy_heuristic(
            plan_date=plan_date,
            requirements=requirements,
            eligibility=eligibility,
            batches=batches,
            lanes=lanes,
            products=products,
            planner_reserve=planner_reserve,
            run_id=effective_run_id,
        )

    # Solver parameters from settings or FMCG defaults
    alpha = settings.alpha if settings else 0.25
    epsilon = settings.epsilon if settings else 0.001
    Eshort = settings.Eshort if settings else 21
    total_time_limit = getattr(settings, "solver_time_limit", 5.0) or 5.0
    stage_time_limit = max(1.0, min(float(total_time_limit) / 2.0, 2.4))

    # Deterministic sorting of entities (Rule 2)
    sorted_destinations = sorted(list(requirements.keys()))
    sorted_products = sorted(list(products.keys()))
    sorted_batches = sorted(batches, key=lambda b: (b.location_id, b.product_id, b.id))
    sorted_lanes = sorted(lanes, key=lambda l: (l.source_id, l.destination_id))

    lane_map: Dict[Tuple[str, str], LaneData] = {(l.source_id, l.destination_id): l for l in lanes}
    batch_map: Dict[str, BatchInfo] = {b.id: b for b in batches}

    # Available stock per batch after planner reserve
    available_stock: Dict[str, int] = {
        b.id: max(0, b.quantity - planner_reserve) for b in sorted_batches
    }

    # Decision Variables:
    # y[b_id, dest_id] >= 0 integer
    # udem[dest_id, prod_id] >= 0
    # utot[dest_id, prod_id] >= 0
    # uss[dest_id, prod_id] = utot - udem >= 0
    y: Dict[Tuple[str, str], pulp.LpVariable] = {}
    udem: Dict[Tuple[str, str], pulp.LpVariable] = {}
    utot: Dict[Tuple[str, str], pulp.LpVariable] = {}
    uss: Dict[Tuple[str, str], pulp.LpVariable] = {}

    # Define variables deterministically
    for d in sorted_destinations:
        for k in sorted_products:
            req = requirements.get(d, {}).get(k)
            if not req:
                continue
            udem[(d, k)] = pulp.LpVariable(f"udem_{d}_{k}", lowBound=0, cat=pulp.LpContinuous)
            utot[(d, k)] = pulp.LpVariable(f"utot_{d}_{k}", lowBound=0, cat=pulp.LpContinuous)
            uss[(d, k)] = pulp.LpVariable(f"uss_{d}_{k}", lowBound=0, cat=pulp.LpContinuous)

    # Shipping variables y[b, d]
    eligible_pairs: List[Tuple[str, str]] = []
    for b in sorted_batches:
        k = b.product_id
        for d in sorted_destinations:
            req = requirements.get(d, {}).get(k)
            if not req:
                continue

            # Check eligibility from service
            res = eligibility.get(d, {}).get(k, {}).get(b.id)
            lane = lane_map.get((b.location_id, d))

            if res and res.is_eligible and lane:
                var_name = f"y_{b.id}_{d}"
                # Upper bound cannot exceed batch stock or total requirement
                ub = min(available_stock[b.id], req.Ntot)
                y[(b.id, d)] = pulp.LpVariable(var_name, lowBound=0, upBound=ub, cat=pulp.LpInteger)
                eligible_pairs.append((b.id, d))

    # =================================================================
    # STAGE 1: Service First
    # =================================================================
    prob1 = pulp.LpProblem("Stage1_ServiceFirst", pulp.LpMinimize)

    # Stage 1 Objective: min sum w_k * (udem + alpha * uss)
    # w_k = unit margin per carton
    obj1_terms = []
    for d in sorted_destinations:
        for k in sorted_products:
            if (d, k) not in udem:
                continue
            prod = products.get(k, ProductInfo(id=k))
            w_k = getattr(prod, "unit_margin", 20.0) or 20.0
            obj1_terms.append(w_k * udem[(d, k)] + alpha * w_k * uss[(d, k)])

    prob1 += pulp.lpSum(obj1_terms)

    # Helper function to add C1 - C6 constraints to a problem
    def add_core_constraints(prob: pulp.LpProblem) -> None:
        # C1: Stock availability: sum_d y[b, d] <= available_stock[b]
        for b in sorted_batches:
            cand_d = [d for d in sorted_destinations if (b.id, d) in y]
            if cand_d:
                prob += (
                    pulp.lpSum([y[(b.id, d)] for d in cand_d]) <= available_stock[b.id],
                    f"C1_Stock_{b.id}",
                )

        # C2 & C3: Coverage & No Over-Allocation
        for d in sorted_destinations:
            for k in sorted_products:
                req = requirements.get(d, {}).get(k)
                if not req:
                    continue

                shipped_vars = [y[(b.id, d)] for b in sorted_batches if b.product_id == k and (b.id, d) in y]

                # uss = utot - udem >= 0
                prob += (
                    uss[(d, k)] >= utot[(d, k)] - udem[(d, k)],
                    f"Link_USS_{d}_{k}",
                )

                # Coverage C2: sum_b y + udem >= Ndem ; sum_b y + utot >= Ntot
                if shipped_vars:
                    prob += (
                        pulp.lpSum(shipped_vars) + udem[(d, k)] >= req.Ndem,
                        f"C2_Cov_Dem_{d}_{k}",
                    )
                    prob += (
                        pulp.lpSum(shipped_vars) + utot[(d, k)] >= req.Ntot,
                        f"C2_Cov_Tot_{d}_{k}",
                    )
                    # C3: No over-allocation: sum_b y <= Ntot
                    prob += (
                        pulp.lpSum(shipped_vars) <= req.Ntot,
                        f"C3_NoOverAlloc_{d}_{k}",
                    )
                else:
                    prob += (udem[(d, k)] >= req.Ndem, f"C2_NoShip_Dem_{d}_{k}")
                    prob += (utot[(d, k)] >= req.Ntot, f"C2_NoShip_Tot_{d}_{k}")

        # C5: Cumulative FEFO Sell-Through Caps
        # For each distinct expiry e at destination d for product k:
        # sum_{b: e_b <= e} y[b, d] <= max(0, f * e - pos)
        for d in sorted_destinations:
            for k in sorted_products:
                req = requirements.get(d, {}).get(k)
                if not req:
                    continue

                # Group eligible batches for (d, k) by days to expiry at arrival
                b_res_list = [
                    (b, eligibility[d][k][b.id])
                    for b in sorted_batches
                    if b.product_id == k and (b.id, d) in y
                ]

                # Collect distinct arrival expiry days
                distinct_expiries = sorted(list(set(r.days_to_expiry_at_arrival for b, r in b_res_list)))

                for exp_days in distinct_expiries:
                    st_cap = b_res_list[0][1].cumulative_caps.get(exp_days, 999999.0)
                    vars_le_exp = [
                        y[(b.id, d)]
                        for b, r in b_res_list
                        if r.days_to_expiry_at_arrival <= exp_days
                    ]
                    if vars_le_exp:
                        prob += (
                            pulp.lpSum(vars_le_exp) <= st_cap,
                            f"C5_FEFO_Cap_{d}_{k}_{exp_days}d",
                        )

        # C6: Lane Capacity Constraints
        for lane in sorted_lanes:
            if lane.capacity_load is not None:
                lane_vars = []
                for b in sorted_batches:
                    if b.location_id == lane.source_id and (b.id, lane.destination_id) in y:
                        prod = products.get(b.product_id, ProductInfo(id=b.product_id))
                        lane_vars.append(prod.load_per_carton * y[(b.id, lane.destination_id)])

                if lane_vars:
                    prob += (
                        pulp.lpSum(lane_vars) <= lane.capacity_load,
                        f"C6_LaneCap_{lane.source_id}_{lane.destination_id}",
                    )

    add_core_constraints(prob1)

    # Solve Stage 1 with CBC (single-threaded for Windows stability and determinism)
    cbc_solver = pulp.PULP_CBC_CMD(
        msg=False,
        timeLimit=stage_time_limit,
        gapRel=0.005,
    )

    try:
        prob1.solve(cbc_solver)
    except Exception as exc:
        # Solver failure fallback to heuristic
        return run_greedy_heuristic(
            plan_date=plan_date,
            requirements=requirements,
            eligibility=eligibility,
            batches=batches,
            lanes=lanes,
            products=products,
            planner_reserve=planner_reserve,
            run_id=effective_run_id,
        )

    # Check Stage 1 status
    stage1_status = pulp.LpStatus[prob1.status]
    if stage1_status not in ["Optimal", "Integer Feasible"]:
        # Fallback to heuristic
        return run_greedy_heuristic(
            plan_date=plan_date,
            requirements=requirements,
            eligibility=eligibility,
            batches=batches,
            lanes=lanes,
            products=products,
            planner_reserve=planner_reserve,
            run_id=effective_run_id,
        )

    V1 = float(pulp.value(prob1.objective))

    # =================================================================
    # STAGE 2: Cost Second (Lexicographic)
    # =================================================================
    prob2 = pulp.LpProblem("Stage2_CostSecond", pulp.LpMinimize)
    add_core_constraints(prob2)

    # Lexicographic freeze constraint: Stage 1 objective <= V1 + 1e-6
    prob2 += (
        pulp.lpSum(obj1_terms) <= V1 + 1e-6,
        "Lexicographic_Service_Freeze",
    )

    # Stage 2 Objective:
    # minimize sum lane_cost * cartons + sum omega_k * stranded + epsilon * sum lead_time * cartons
    obj2_terms = []

    # 1. Transport freight cost + lead time tie-breaker
    # Include infinitesimal tie-breaker for deterministic identifier ordering
    for idx, (b_id, d) in enumerate(sorted(y.keys())):
        b = batch_map[b_id]
        lane = lane_map[(b.location_id, d)]
        cost_coeff = lane.cost_per_carton + (epsilon * lane.lead_time_days) + (1e-7 * idx)
        obj2_terms.append(cost_coeff * y[(b_id, d)])

    # 2. Stranded inventory penalty for batches expiring within Eshort days
    for b in sorted_batches:
        if b.days_to_expiry_from_dispatch <= Eshort:
            prod = products.get(b.product_id, ProductInfo(id=b.product_id))
            omega_k = getattr(prod, "unit_cost", 50.0) or 50.0
            shipped_d = [y[(b.id, d)] for d in sorted_destinations if (b.id, d) in y]
            if shipped_d:
                # stranded = available - sum_d y -> penalty = omega_k * (avail - sum y)
                # Minimizing this gives a bonus of -omega_k * sum_d y to shipping expiring batches
                obj2_terms.append(-omega_k * pulp.lpSum(shipped_d))

    prob2 += pulp.lpSum(obj2_terms)

    try:
        prob2.solve(cbc_solver)
    except Exception:
        return run_greedy_heuristic(
            plan_date=plan_date,
            requirements=requirements,
            eligibility=eligibility,
            batches=batches,
            lanes=lanes,
            products=products,
            planner_reserve=planner_reserve,
            run_id=effective_run_id,
        )

    stage2_status = pulp.LpStatus[prob2.status]
    if stage2_status not in ["Optimal", "Integer Feasible"]:
        return run_greedy_heuristic(
            plan_date=plan_date,
            requirements=requirements,
            eligibility=eligibility,
            batches=batches,
            lanes=lanes,
            products=products,
            planner_reserve=planner_reserve,
            run_id=effective_run_id,
        )

    # Build Allocation Lines from Stage 2 solution
    lines: List[AllocationLine] = []
    total_transport_cost = 0.0
    total_shipped_cartons = 0

    shipped_by_dest_prod: Dict[Tuple[str, str], int] = {}
    for d in sorted_destinations:
        for k in sorted_products:
            shipped_by_dest_prod[(d, k)] = 0

    # Sort allocation lines deterministically by destination, product, source, batch
    for (b_id, d) in sorted(y.keys(), key=lambda pair: (pair[1], batch_map[pair[0]].product_id, batch_map[pair[0]].location_id, pair[0])):
        val = int(round(pulp.value(y[(b_id, d)])))
        if val <= 0:
            continue

        b = batch_map[b_id]
        lane = lane_map[(b.location_id, d)]
        k = b.product_id
        res = eligibility[d][k][b.id]

        line_cost = round(val * lane.cost_per_carton, 2)
        arrival_date = plan_date + timedelta(days=lane.lead_time_days)

        flags: List[str] = []
        explanation: Dict[str, Any] = {
            "source": lane.source_id,
            "destination": d,
            "lead_time_days": lane.lead_time_days,
            "lane_cost_per_carton": lane.cost_per_carton,
            "allocated_cartons": val,
            "batch_days_to_expiry_at_arrival": res.days_to_expiry_at_arrival,
        }

        if res.lane_gap > 0.0:
            flags.append("LANE_GAP_RISK")
            flags.append(f"expected lost sales: {round(res.unavoidable_lost_sales, 1):.1f} units")
            explanation["lane_gap"] = round(res.lane_gap, 2)
            explanation["expected_lost_sales"] = round(res.unavoidable_lost_sales, 1)
            explanation["unavoidable_lost_sales"] = round(res.unavoidable_lost_sales, 1)

        # Economic check
        prod = products.get(k, ProductInfo(id=k))
        unit_margin_carton = getattr(prod, "unit_margin", 20.0) or 20.0
        if lane.cost_per_carton > unit_margin_carton:
            flags.append("UNECONOMIC_SERVICE_FIRST")
            flags.append("uneconomic, service-first")
            explanation["uneconomic_note"] = "Freight cost exceeds gross margin (Service-First)"

        lines.append(
            AllocationLine(
                batch_id=b_id,
                source_id=lane.source_id,
                destination_id=d,
                product_id=k,
                cartons=val,
                cost=line_cost,
                arrival_date=arrival_date,
                lead_time_days=lane.lead_time_days,
                flags=flags,
                explanation=explanation,
            )
        )

        total_shipped_cartons += val
        total_transport_cost += line_cost
        shipped_by_dest_prod[(d, k)] += val

    # Verify total cost equals sum of line costs (Required spec assertion)
    sum_line_costs = round(sum(l.cost for l in lines), 2)
    assert abs(round(total_transport_cost, 2) - sum_line_costs) < 1e-4, "Total cost does not equal sum of line costs"

    # Compute fulfillment & unmet metrics
    total_demand = 0
    total_unmet_demand = 0
    total_unmet_safety_stock = 0
    unmet_by_dest_prod: Dict[Tuple[str, str], Dict[str, float]] = {}

    for d in sorted_destinations:
        for k in sorted_products:
            req = requirements.get(d, {}).get(k)
            if not req:
                continue

            shipped = shipped_by_dest_prod.get((d, k), 0)
            u_dem = max(0, req.Ndem - shipped)
            u_tot = max(0, req.Ntot - shipped)
            u_ss = u_tot - u_dem

            total_demand += req.Ndem
            total_unmet_demand += u_dem
            total_unmet_safety_stock += u_ss

            unmet_by_dest_prod[(d, k)] = {
                "Ndem": req.Ndem,
                "Ntot": req.Ntot,
                "shipped": shipped,
                "udem": u_dem,
                "utot": u_tot,
                "uss": u_ss,
            }

    elapsed = time.time() - start_time
    return OptimizationResult(
        run_id=effective_run_id,
        plan_date=plan_date,
        status="OPTIMIZED",
        lines=lines,
        total_cost=round(total_transport_cost, 2),
        total_cartons=total_shipped_cartons,
        total_demand_cartons=total_demand,
        total_unmet_demand_cartons=total_unmet_demand,
        total_unmet_safety_stock_cartons=total_unmet_safety_stock,
        unmet_by_destination_product=unmet_by_dest_prod,
        stage1_objective=round(V1, 4),
        stage2_objective=round(float(pulp.value(prob2.objective)), 4),
        solver_status=stage2_status,
        solve_time_seconds=round(elapsed, 4),
        is_simulated=True,
    )


# =====================================================================
# Database Pipeline Runner & Persistence
# =====================================================================
class OptimizationService:
    """
    End-to-end optimization pipeline orchestrating forecast, requirement,
    eligibility, PuLP solver, and database persistence.
    """

    def __init__(self, session: Session):
        self.session = session
        self.settings = get_current_settings(session)

    def run_plan(
        self,
        plan_date: Optional[dt_date] = None,
        run_by_role: str = "planner",
        notes: Optional[str] = None,
        planner_reserve_override: Optional[int] = None,
        compute_counterfactuals: bool = False,
        force_heuristic: bool = False,
    ) -> OptimizationResult:
        """Run complete two-stage distribution optimization pipeline and persist results."""
        effective_date = plan_date or dt_date(2026, 10, 24)
        run_id = f"PLAN-{effective_date.strftime('%Y%m%d')}-{int(time.time() * 1000)}"
        reserve = planner_reserve_override if planner_reserve_override is not None else self.settings.planner_reserve

        # 1. Load network master data
        products = list(self.session.exec(select(Product)).all())
        destinations = list(
            self.session.exec(
                select(Location).where(Location.type.in_(["distributor", "store"]))  # type: ignore
            ).all()
        )
        warehouses = list(
            self.session.exec(select(Location).where(Location.type == "warehouse")).all()
        )
        lanes_db = list(self.session.exec(select(Lane)).all())
        batches_db = list(self.session.exec(select(Batch)).all())
        snapshots_db = list(self.session.exec(select(InventorySnapshot)).all())

        # Snapshots mapped by (location_id, product_id)
        pos_map: Dict[str, Dict[str, float]] = {}
        res_map: Dict[str, Dict[str, float]] = {}
        transit_map: Dict[str, Dict[str, float]] = {}
        for s in snapshots_db:
            pos_map.setdefault(s.location_id, {})[s.product_id] = float(s.on_hand)
            res_map.setdefault(s.location_id, {})[s.product_id] = float(s.reserved)
            transit_map.setdefault(s.location_id, {})[s.product_id] = float(s.in_transit)

        # 2. Get Forecasts
        fc_service = ForecastService(self.session)
        fc_results = fc_service.fit_and_select_all(as_of=effective_date, horizon=self.settings.H)
        fc_mean_map: Dict[str, Dict[str, float]] = {}
        fc_sigma_map: Dict[str, Dict[str, float]] = {}
        daily_fc_map: Dict[str, Dict[str, List[float]]] = {}

        for r in fc_results:
            d = r["location_id"]
            p = r["product_id"]
            fc_mean_map.setdefault(d, {})[p] = float(sum(r["daily_forecast"]) / len(r["daily_forecast"]))
            fc_sigma_map.setdefault(d, {})[p] = float(r["sigma"])
            daily_fc_map.setdefault(d, {})[p] = r["daily_forecast"]

        # Convert to pure domain representations
        lanes_pure = [
            LaneData(
                source_id=l.source_id,
                destination_id=l.destination_id,
                lead_time_days=l.lead_time_days,
                cost_per_carton=l.cost_per_carton,
                capacity_load=l.capacity_load,
                distance_km=l.distance_km or 0.0,
            )
            for l in lanes_db
        ]

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

        batches_pure = [
            BatchInfo(
                id=b.id,
                location_id=b.location_id,
                product_id=b.product_id,
                quantity=b.quantity,
                days_to_expiry_from_dispatch=(b.expiry_date - effective_date).days,
                expiry_date=b.expiry_date,
                cost_per_carton=b.cost_per_carton,
            )
            for b in batches_db
        ]

        # 3. Compute Requirements
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
            for l in lanes_db
        ]

        requirements = compute_all_net_requirements(
            destinations=dest_ids,
            products=prod_ids,
            inventory_positions=pos_map,
            forecast_means=fc_mean_map,
            forecast_sigmas=fc_sigma_map,
            lanes=req_lanes,
            daily_forecasts=daily_fc_map,
            reserved_map=res_map,
            in_transit_map=transit_map,
            case_packs={p.id: p.case_pack for p in products},
            H=self.settings.H,
            z=self.settings.z,
            Gmax=self.settings.Gmax,
        )

        # 4. Evaluate Eligibility
        cover_map: Dict[str, Dict[str, float]] = {
            d: {k: req.cover for k, req in p_dict.items()}
            for d, p_dict in requirements.items()
        }
        effective_pos_map: Dict[str, Dict[str, float]] = {
            d: {k: req.pos for k, req in p_dict.items()}
            for d, p_dict in requirements.items()
        }

        eligibility = evaluate_all_batches_eligibility(
            batches=batches_pure,
            lanes=lanes_pure,
            products=products_pure,
            covers=cover_map,
            daily_forecast_means=fc_mean_map,
            positions=effective_pos_map,
            Gmax=self.settings.Gmax,
        )

        # 5. Run Two-Stage Solver (with heuristic fallback)
        opt_result = solve_two_stage_optimization(
            plan_date=effective_date,
            requirements=requirements,
            eligibility=eligibility,
            batches=batches_pure,
            lanes=lanes_pure,
            products=products_pure,
            settings=self.settings,
            planner_reserve=reserve,
            run_id=run_id,
            force_heuristic=force_heuristic,
        )

        # 6. Compute Counterfactuals if requested and there are any unmet pairs
        cf_serialized = []
        if compute_counterfactuals and opt_result.total_unmet_demand_cartons > 0:
            from backend.app.services.counterfactual import analyze_counterfactuals
            cf_reports = analyze_counterfactuals(
                plan_date=effective_date,
                requirements=requirements,
                eligibility=eligibility,
                batches=batches_pure,
                lanes=lanes_pure,
                products=products_pure,
                base_result=opt_result,
                settings=self.settings,
                planner_reserve=reserve,
            )
            opt_result.counterfactuals = cf_reports
            for r in cf_reports:
                cf_serialized.append({
                    "destination_id": r.destination_id,
                    "product_id": r.product_id,
                    "udem": r.udem,
                    "uss": r.uss,
                    "binding_constraint": r.binding_constraint,
                    "explanation": r.explanation,
                    "fixes": {
                        "stock": {
                            "source_id": r.stock_fix.source_id if r.stock_fix else None,
                            "extra_cartons_demand": r.stock_fix.extra_cartons_demand if r.stock_fix else 0,
                            "extra_transport_cost_demand": r.stock_fix.extra_transport_cost_demand if r.stock_fix else 0.0,
                            "extra_cartons_total": r.stock_fix.extra_cartons_total if r.stock_fix else 0,
                            "extra_transport_cost_total": r.stock_fix.extra_transport_cost_total if r.stock_fix else 0.0,
                            "is_feasible": r.stock_fix.is_feasible if r.stock_fix else False,
                            "description": r.stock_fix.description if r.stock_fix else "",
                        } if r.stock_fix else None,
                        "lead_time": {
                            "delta_gmax_days": r.lead_time_fix.delta_gmax_days if r.lead_time_fix else None,
                            "extra_transport_cost": r.lead_time_fix.extra_transport_cost if r.lead_time_fix else 0.0,
                            "is_binding": r.lead_time_fix.is_binding if r.lead_time_fix else False,
                            "description": r.lead_time_fix.description if r.lead_time_fix else "no change",
                        } if r.lead_time_fix else None,
                        "shelf_life": {
                            "extra_cartons": r.shelf_life_fix.extra_cartons if r.shelf_life_fix else None,
                            "relaxed_days": r.shelf_life_fix.relaxed_days if r.shelf_life_fix else None,
                            "extra_transport_cost": r.shelf_life_fix.extra_transport_cost if r.shelf_life_fix else 0.0,
                            "is_binding": r.shelf_life_fix.is_binding if r.shelf_life_fix else False,
                            "description": r.shelf_life_fix.description if r.shelf_life_fix else "not binding",
                        } if r.shelf_life_fix else None,
                        "lane_capacity": {
                            "lane_source_id": r.lane_capacity_fix.lane_source_id if r.lane_capacity_fix else None,
                            "lane_destination_id": r.lane_capacity_fix.lane_destination_id if r.lane_capacity_fix else None,
                            "extra_capacity_load": r.lane_capacity_fix.extra_capacity_load if r.lane_capacity_fix else None,
                            "extra_transport_cost": r.lane_capacity_fix.extra_transport_cost if r.lane_capacity_fix else 0.0,
                            "is_binding": r.lane_capacity_fix.is_binding if r.lane_capacity_fix else False,
                            "description": r.lane_capacity_fix.description if r.lane_capacity_fix else "not binding",
                        } if r.lane_capacity_fix else None,
                    },
                })
        elif opt_result.total_unmet_demand_cartons > 0:
            for (d_id, p_id), unmet_dict in opt_result.unmet_by_destination_product.items():
                udem = unmet_dict.get("udem", 0)
                uss = unmet_dict.get("uss", 0)
                if udem > 0 or uss > 0:
                    cf_serialized.append({
                        "destination_id": d_id,
                        "product_id": p_id,
                        "udem": udem,
                        "uss": uss,
                        "binding_constraint": "stock",
                        "explanation": f"Unmet demand of {udem} cartons at {d_id} for {p_id}.",
                        "fixes": {},
                    })

        # 7. Persist PlanRun and PlanLines into DB
        self.persist_plan(
            opt_result,
            run_by_role=run_by_role,
            notes=notes,
            counterfactuals_json=json.dumps(cf_serialized),
        )
        return opt_result

    def persist_plan(
        self,
        result: OptimizationResult,
        run_by_role: str = "planner",
        notes: Optional[str] = None,
        counterfactuals_json: Optional[str] = None,
    ) -> PlanRun:
        """Persist PlanRun and PlanLine rows into SQLite."""
        plan_run = PlanRun(
            id=result.run_id,
            planning_date=result.plan_date,
            status=result.status,
            total_cost=result.total_cost,
            total_cartons=result.total_cartons,
            total_demand_cartons=result.total_demand_cartons,
            total_unmet_cartons=result.total_unmet_demand_cartons,
            total_unmet_safety_stock_cartons=result.total_unmet_safety_stock_cartons,
            counterfactuals_json=counterfactuals_json or "[]",
            settings_snapshot_json=json.dumps({
                "H": self.settings.H,
                "z": self.settings.z,
                "alpha": self.settings.alpha,
                "Gmax": self.settings.Gmax,
                "Eshort": self.settings.Eshort,
                "shrinkage": self.settings.shrinkage,
                "planner_reserve": self.settings.planner_reserve,
            }),
            run_by_role=run_by_role,
            notes=notes,
            is_simulated=True,
        )
        self.session.add(plan_run)

        # Remove any previous lines for this run_id
        old_lines = self.session.exec(select(PlanLine).where(PlanLine.run_id == result.run_id)).all()
        for ol in old_lines:
            self.session.delete(ol)

        for idx, line in enumerate(result.lines):
            p_line = PlanLine(
                id=f"{result.run_id}-L{idx+1:04d}",
                run_id=result.run_id,
                product_id=line.product_id,
                source_id=line.source_id,
                destination_id=line.destination_id,
                batch_id=line.batch_id,
                cartons=line.cartons,
                cost=line.cost,
                arrival_date=line.arrival_date,
                flags_json=json.dumps(line.flags),
                explanation_json=json.dumps(line.explanation),
                status="PROPOSED",
                is_simulated=True,
            )
            self.session.add(p_line)

        # Log action to DecisionLog
        log_entry = DecisionLog(
            plan_line_id=None,
            actor_role=run_by_role,
            action="OPTIMIZE",
            old_value=None,
            new_value=f"Generated {len(result.lines)} plan lines ({result.total_cartons} cartons, ₹{result.total_cost})",
            note=notes or f"Optimizer executed with status {result.status}",
        )
        self.session.add(log_entry)

        self.session.commit()
        return plan_run
