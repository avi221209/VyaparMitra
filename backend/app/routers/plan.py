"""
VyaparMitra - Planning, Allocation, Explanation Card & Audit API Router
FMCG Distribution Intelligence and Inventory Optimization Engine
"""

from datetime import date as dt_date, datetime as dt_datetime, timedelta
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlmodel import Session, func, select

from backend.app.db import get_session
from backend.app.models import (
    Batch,
    DecisionLog,
    ForecastResult,
    InventorySnapshot,
    Lane,
    Location,
    PlanLine,
    PlanRun,
    Product,
    SalesDaily,
    Settings,
    SurplusListing,
)
from backend.app.schemas import (
    DeadStockWarningRead,
    RescueApplyRequest,
    SurplusListingRead,
)
from backend.app.services.surplus import (
    apply_shortfall_rescue,
    build_rescue_analysis_for_unmet,
    compute_dead_stock_warnings,
    compute_verified_spare_stock,
    undo_shortfall_rescue,
)
from backend.app.services.eligibility import (
    BatchEligibilityResult,
    BatchInfo,
    LaneData,
    ProductInfo,
    evaluate_all_batches_eligibility,
)
from backend.app.services.forecast import ForecastService
from backend.app.services.optimizer import OptimizationService
from backend.app.services.requirement import (
    LaneInfo,
    NetRequirement,
    compute_all_net_requirements,
)
from backend.app.services.rules import validate_plan_allocation
from backend.app.settings import get_current_settings


router = APIRouter(tags=["Plan & Allocation"])


# -------------------------------------------------------------------
# Request & Response Schemas
# -------------------------------------------------------------------

class PlanCreateRequest(BaseModel):
    horizon: Optional[int] = Field(default=None, ge=1, le=30, description="Planning horizon in days")
    as_of: Optional[dt_date] = Field(default=None, description="Planning date (default: 2026-10-24)")
    planner_reserve: Optional[int] = Field(default=None, ge=0, description="Cartons held back per batch")
    overrides: Optional[Dict[str, Any]] = Field(default=None, description="Optional network or demand overrides")
    notes: Optional[str] = Field(default=None, description="Planner notes")
    force_heuristic: Optional[bool] = Field(default=False, description="Force heuristic fallback for testing/drills")
    include_surplus: Optional[bool] = Field(default=False, description="Auto-allocate verified surplus rescue stock into the plan")


class LineApproveRequest(BaseModel):
    edited_cartons: Optional[int] = Field(default=None, ge=0, description="Optional edited carton allocation")
    notes: Optional[str] = Field(default=None, description="Reviewer/planner note")


class LineRejectRequest(BaseModel):
    reason: str = Field(..., description="Mandatory reason for rejection")
    notes: Optional[str] = Field(default=None)


class ScenarioOverrideRequest(BaseModel):
    source_id: Optional[str] = Field(default=None, description="Warehouse source ID e.g. W1")
    stock_percent: Optional[float] = Field(default=None, description="Percentage adjustment e.g. -20 for -20%")
    stock_absolute: Optional[int] = Field(default=None, ge=0, description="Absolute total stock cartons to set")
    destination_id: Optional[str] = Field(default=None, description="Destination location ID e.g. D1")
    demand_multiplier: Optional[float] = Field(default=None, gt=0, description="Multiplier for demand e.g. 1.2")
    as_of: Optional[dt_date] = Field(default=None)
    horizon: Optional[int] = Field(default=None)
    notes: Optional[str] = Field(default=None)


def verify_planner_or_reviewer_role(x_role: str = Header(default="planner")) -> str:
    """Enforce that human actions (approve, edit, reject) require planner or reviewer role."""
    clean_role = (x_role or "planner").lower().strip()
    if clean_role not in ("planner", "reviewer"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: role '{x_role}' is not authorized. Must be 'planner' or 'reviewer'.",
        )
    return clean_role


def get_current_role(x_role: str = Header(default="planner")) -> str:
    clean_role = (x_role or "planner").lower().strip()
    valid_roles = {"planner", "warehouse", "reviewer", "system"}
    if clean_role not in valid_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Invalid X-Role '{x_role}'. Allowed roles: {sorted(list(valid_roles))}",
        )
    return clean_role


# -------------------------------------------------------------------
# Helper: Build Planning Domain Context
# -------------------------------------------------------------------
def build_domain_context(session: Session, as_of: dt_date, settings: Settings):
    """Load and prepare all pure dataclass inputs for requirement, eligibility, and rules."""
    products = list(session.exec(select(Product)).all())
    destinations = list(
        session.exec(
            select(Location).where(Location.type.in_(["distributor", "store"]))  # type: ignore
        ).all()
    )
    warehouses = list(session.exec(select(Location).where(Location.type == "warehouse")).all())
    lanes_db = list(session.exec(select(Lane)).all())
    batches_db = list(session.exec(select(Batch)).all())
    snapshots_db = list(session.exec(select(InventorySnapshot)).all())

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
            days_to_expiry_from_dispatch=(b.expiry_date - as_of).days,
            expiry_date=b.expiry_date,
            cost_per_carton=b.cost_per_carton,
        )
        for b in batches_db
    ]

    pos_map: Dict[str, Dict[str, float]] = {}
    res_map: Dict[str, Dict[str, float]] = {}
    transit_map: Dict[str, Dict[str, float]] = {}
    for s in snapshots_db:
        pos_map.setdefault(s.location_id, {})[s.product_id] = float(s.on_hand)
        res_map.setdefault(s.location_id, {})[s.product_id] = float(s.reserved)
        transit_map.setdefault(s.location_id, {})[s.product_id] = float(s.in_transit)

    cached_fc = list(
        session.exec(
            select(ForecastResult).where(ForecastResult.as_of_date == as_of)
        ).all()
    )
    fc_mean_map: Dict[str, Dict[str, float]] = {}
    fc_sigma_map: Dict[str, Dict[str, float]] = {}
    daily_fc_map: Dict[str, Dict[str, List[float]]] = {}

    if cached_fc:
        for r in cached_fc:
            d = r.location_id
            p = r.product_id
            dfc = json.loads(r.daily_forecast_json) if r.daily_forecast_json else [0.0]
            fc_mean_map.setdefault(d, {})[p] = float(sum(dfc) / len(dfc)) if dfc else 0.0
            fc_sigma_map.setdefault(d, {})[p] = float(r.sigma)
            daily_fc_map.setdefault(d, {})[p] = dfc
    else:
        fc_service = ForecastService(session)
        fc_results = fc_service.fit_and_select_all(as_of=as_of, horizon=settings.H, persist=False)
        for r in fc_results:
            d = r["location_id"]
            p = r["product_id"]
            fc_mean_map.setdefault(d, {})[p] = float(sum(r["daily_forecast"]) / len(r["daily_forecast"]))
            fc_sigma_map.setdefault(d, {})[p] = float(r["sigma"])
            daily_fc_map.setdefault(d, {})[p] = r["daily_forecast"]

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

    dest_ids = [d.id for d in destinations]
    prod_ids = [p.id for p in products]

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
        H=settings.H,
        z=settings.z,
        Gmax=settings.Gmax,
    )

    return {
        "products": products,
        "destinations": destinations,
        "warehouses": warehouses,
        "lanes_db": lanes_db,
        "batches_db": batches_db,
        "products_pure": products_pure,
        "lanes_pure": lanes_pure,
        "batches_pure": batches_pure,
        "requirements": requirements,
        "daily_fc_map": daily_fc_map,
        "fc_mean_map": fc_mean_map,
    }


# -------------------------------------------------------------------
# 1. POST /api/plan
# -------------------------------------------------------------------
@router.post("/api/v1/plan", tags=["Plan & Allocation"])
def create_plan(
    payload: Optional[PlanCreateRequest] = Body(default=None),
    horizon: Optional[int] = Query(default=None),
    as_of: Optional[dt_date] = Query(default=None),
    force_heuristic: Optional[bool] = Query(default=False),
    session: Session = Depends(get_session),
    role: str = Depends(get_current_role),
) -> dict:
    """
    Run complete distribution optimization pipeline:
    Runs cached forecast, net requirement, batch eligibility, lexicographic two-stage PuLP optimizer,
    and counterfactual what-if analysis. Persists run and returns run id and lines.
    """
    req_payload = payload or PlanCreateRequest()
    effective_h = horizon or req_payload.horizon
    effective_as_of = as_of or req_payload.as_of or dt_date(2026, 10, 24)
    planner_reserve = req_payload.planner_reserve
    effective_force_heuristic = bool(force_heuristic or req_payload.force_heuristic)

    # Apply temporary horizon override to settings if provided
    sys_settings = get_current_settings(session)
    if effective_h is not None and effective_h != sys_settings.H:
        sys_settings.H = effective_h

    opt_service = OptimizationService(session)
    opt_service.settings = sys_settings

    result = opt_service.run_plan(
        plan_date=effective_as_of,
        run_by_role=role,
        notes=req_payload.notes,
        planner_reserve_override=planner_reserve,
        force_heuristic=effective_force_heuristic,
    )

    # If include_surplus was requested, allocate verified surplus for any unmet demand
    if req_payload.include_surplus and result.unmet_by_destination_product:
        surplus_listings = list(session.exec(select(SurplusListing)).all())
        products_map = {p.id: p for p in session.exec(select(Product)).all()}
        for (d_id, p_id), unmet_info in result.unmet_by_destination_product.items():
            udem = unmet_info.get("udem", 0)
            if udem <= 0:
                continue
            prod = products_map.get(p_id)
            inv_pos = session.exec(
                select(InventorySnapshot.on_hand)
                .where(InventorySnapshot.location_id == d_id, InventorySnapshot.product_id == p_id)
            ).first() or 0
            daily_fc = session.exec(
                select(func.avg(SalesDaily.units))
                .where(SalesDaily.location_id == d_id, SalesDaily.product_id == p_id)
            ).first() or 5.0
            cover_days = inv_pos / max(0.1, daily_fc)

            analysis = build_rescue_analysis_for_unmet(
                destination_id=d_id,
                product_id=p_id,
                unmet_cartons=udem,
                listings=surplus_listings,
                as_of=effective_as_of,
                cover_days=cover_days,
                daily_forecast_dest=daily_fc,
                inv_position_dest=inv_pos,
                unit_cost=prod.unit_cost if prod else 100.0,
                unit_margin=prod.unit_margin if prod else 20.0,
                min_remaining_shelf_days=getattr(sys_settings, "min_remaining_shelf_life", 14),
                gmax=getattr(sys_settings, "Gmax", 2),
                z=getattr(sys_settings, "z", 1.65),
            )
            if analysis.best_rescue_source and analysis.best_rescue_source.eligible:
                try:
                    apply_shortfall_rescue(
                        session=session,
                        run_id=result.run_id,
                        destination_id=d_id,
                        product_id=p_id,
                        surplus_listing_id=analysis.best_rescue_source.listing_id,
                        cartons=min(udem, analysis.best_rescue_source.rescuable_cartons),
                        actor_role=role,
                        notes="Auto-allocated via include_surplus",
                    )
                except Exception:
                    pass

    plan_run_updated = session.get(PlanRun, result.run_id) or result
    persisted_lines = session.exec(
        select(PlanLine).where(PlanLine.run_id == result.run_id).order_by(PlanLine.id)  # type: ignore
    ).all()

    from backend.app.routers.dashboard import invalidate_dashboard_cache
    invalidate_dashboard_cache()

    return {
        "run_id": result.run_id,
        "planning_date": str(result.plan_date),
        "status": getattr(plan_run_updated, "status", result.status),
        "solver_status": result.solver_status,
        "total_cost": getattr(plan_run_updated, "total_cost", result.total_cost),
        "total_cartons": getattr(plan_run_updated, "total_cartons", result.total_cartons),
        "total_demand_cartons": result.total_demand_cartons,
        "total_unmet_cartons": getattr(plan_run_updated, "total_unmet_cartons", result.total_unmet_demand_cartons),
        "total_unmet_safety_stock_cartons": result.total_unmet_safety_stock_cartons,
        "lines_count": len(persisted_lines),
        "lines": [
            {
                "id": line.id,
                "run_id": line.run_id,
                "product_id": line.product_id,
                "source_id": line.source_id,
                "destination_id": line.destination_id,
                "batch_id": line.batch_id,
                "cartons": line.cartons,
                "cost": line.cost,
                "arrival_date": str(line.arrival_date),
                "flags": json.loads(line.flags_json) if line.flags_json else [],
                "status": line.status,
            }
            for line in persisted_lines
        ],
        "is_simulated": True,
    }


# -------------------------------------------------------------------
# 2. GET /api/plan/latest and GET /api/plan/{run_id}
# -------------------------------------------------------------------
@router.get("/api/v1/plan/latest", tags=["Plan & Allocation"])
def get_latest_plan(
    session: Session = Depends(get_session),
) -> dict:
    latest_run = session.exec(select(PlanRun).order_by(PlanRun.created_at.desc())).first()
    if not latest_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No plan run found in database.",
        )
    return get_plan(run_id=latest_run.id, session=session)


@router.get("/api/v1/plan/{run_id}", tags=["Plan & Allocation"])
def get_plan(
    run_id: str,
    session: Session = Depends(get_session),
) -> dict:
    """
    Fetch complete plan summary:
    Lines, totals (transport cost, total cartons, unmet demand, safety-stock gap),
    and unmet panel with prescription fixes.
    """
    plan_run = session.get(PlanRun, run_id)
    if not plan_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan run with ID '{run_id}' not found.",
        )

    lines = list(
        session.exec(
            select(PlanLine).where(PlanLine.run_id == run_id).order_by(PlanLine.id)  # type: ignore
        ).all()
    )

    unmet_panel = []
    if plan_run.counterfactuals_json and plan_run.counterfactuals_json != "[]":
        try:
            unmet_panel = json.loads(plan_run.counterfactuals_json)
        except Exception:
            unmet_panel = []

    # Surplus & Dead-Stock Intelligence Enrichment
    surplus_listings = list(session.exec(select(SurplusListing)).all())
    products_map = {p.id: p for p in session.exec(select(Product)).all()}
    sys_settings = get_current_settings(session)

    # Check already applied rescue lines in this plan
    rescue_lines_map: Dict[Tuple[str, str], int] = {}
    for line in lines:
        flags = json.loads(line.flags_json) if line.flags_json else []
        if any("Surplus rescue" in str(f) for f in flags):
            rescue_lines_map[(line.destination_id, line.product_id)] = (
                rescue_lines_map.get((line.destination_id, line.product_id), 0) + line.cartons
            )

    for item in unmet_panel:
        d_id = item.get("destination_id")
        p_id = item.get("product_id")
        raw_udem = item.get("udem", 0)
        rescued_cartons = rescue_lines_map.get((d_id, p_id), 0)
        effective_unmet = max(0, raw_udem - rescued_cartons)
        item["rescued_cartons"] = rescued_cartons
        item["effective_unmet_cartons"] = effective_unmet

        prod = products_map.get(p_id)
        inv_pos = session.exec(
            select(InventorySnapshot.on_hand)
            .where(InventorySnapshot.location_id == d_id, InventorySnapshot.product_id == p_id)
        ).first() or 0
        daily_fc = session.exec(
            select(func.avg(SalesDaily.units))
            .where(SalesDaily.location_id == d_id, SalesDaily.product_id == p_id)
        ).first() or 5.0
        cover_days = inv_pos / max(0.1, daily_fc)

        rescue_analysis = build_rescue_analysis_for_unmet(
            destination_id=d_id,
            product_id=p_id,
            unmet_cartons=effective_unmet if effective_unmet > 0 else raw_udem,
            listings=surplus_listings,
            as_of=plan_run.planning_date,
            cover_days=cover_days,
            daily_forecast_dest=daily_fc,
            inv_position_dest=inv_pos,
            unit_cost=prod.unit_cost if prod else 100.0,
            unit_margin=prod.unit_margin if prod else 20.0,
            min_remaining_shelf_days=getattr(sys_settings, "min_remaining_shelf_life", 14),
            gmax=getattr(sys_settings, "Gmax", 2),
            z=getattr(sys_settings, "z", 1.65),
        )
        item["rescue_analysis"] = rescue_analysis.model_dump()

    dead_stock_warnings = [
        w.model_dump()
        for w in compute_dead_stock_warnings(session, plan_date=plan_run.planning_date, plan_lines=lines)
    ]

    return {
        "run_id": plan_run.id,
        "planning_date": str(plan_run.planning_date),
        "created_at": plan_run.created_at.isoformat(),
        "status": plan_run.status,
        "solver_status": "FALLBACK_HEURISTIC" if plan_run.status == "HEURISTIC" else "OPTIMIZED",
        "run_by_role": plan_run.run_by_role,
        "totals": {
            "transport_cost": plan_run.total_cost,
            "transport": plan_run.total_cost,
            "total_cartons": plan_run.total_cartons,
            "total_demand_cartons": plan_run.total_demand_cartons,
            "unmet_demand_cartons": plan_run.total_unmet_cartons,
            "unmet_demand": plan_run.total_unmet_cartons,
            "safety_stock_gap_cartons": getattr(plan_run, "total_unmet_safety_stock_cartons", 0) or 0,
            "safety_stock_gap": getattr(plan_run, "total_unmet_safety_stock_cartons", 0) or 0,
        },
        "lines": [
            {
                "id": line.id,
                "run_id": line.run_id,
                "product_id": line.product_id,
                "source_id": line.source_id,
                "destination_id": line.destination_id,
                "batch_id": line.batch_id,
                "cartons": line.cartons,
                "cost": line.cost,
                "arrival_date": str(line.arrival_date),
                "flags": json.loads(line.flags_json) if line.flags_json else [],
                "status": line.status,
            }
            for line in lines
        ],
        "unmet_panel": unmet_panel,
        "dead_stock_warnings": dead_stock_warnings,
        "is_simulated": True,
    }





# -------------------------------------------------------------------
# 3. GET /api/plan/lines/{id} (Explanation Card Data)
# -------------------------------------------------------------------
@router.get("/api/v1/plan/lines/{id}", tags=["Plan & Allocation"])
def get_plan_line_explanation_card(
    id: str,
    session: Session = Depends(get_session),
) -> dict:
    """
    Explanation card data per line.
    Built ONLY from calculated values, no free text generation:
     - sources considered (eligible/excluded with reason, cost, lead time, stock)
     - chosen and why (cheapest eligible subject to constraints)
     - constraints checked (stock, lead time gap, lane capacity, shelf life with days left and days to sell)
     - residual risk (unmet and safety-stock gap)
    """
    line = session.get(PlanLine, id)
    if not line:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan line with ID '{id}' not found.",
        )

    plan_run = session.get(PlanRun, line.run_id)
    if not plan_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan run '{line.run_id}' for line '{id}' not found.",
        )

    sys_settings = get_current_settings(session)
    plan_date = plan_run.planning_date
    ctx = build_domain_context(session, as_of=plan_date, settings=sys_settings)

    d = line.destination_id
    k = line.product_id
    s = line.source_id
    b_id = line.batch_id

    prod = ctx["products_pure"].get(k, ProductInfo(id=k))
    req = ctx["requirements"].get(d, {}).get(k)
    cover_days = req.cover if req else 0.0
    daily_f = req.daily_forecast_mean if req else 1.0

    # 1. Sources Considered
    sources_considered = []
    chosen_lane_data = None
    for wh in ctx["warehouses"]:
        lane = next(
            (l for l in ctx["lanes_pure"] if l.source_id == wh.id and l.destination_id == d),
            None,
        )

        if wh.id == s and lane:
            chosen_lane_data = lane

        if not lane:
            sources_considered.append({
                "source_id": wh.id,
                "source_name": wh.name,
                "cost_per_carton": None,
                "lead_time_days": None,
                "stock_available": 0,
                "is_eligible": False,
                "reason": f"No active lane exists to destination '{d}'",
            })
            continue

        # Check stock of SKU at this warehouse
        wh_batches = [b for b in ctx["batches_pure"] if b.location_id == wh.id and b.product_id == k]
        total_wh_qty = sum(b.quantity for b in wh_batches)
        available_wh_stock = sum(max(0, b.quantity - sys_settings.planner_reserve) for b in wh_batches)

        # Check Lead time gap
        lane_gap = max(0.0, float(lane.lead_time_days) - cover_days)
        gap_exceeded = lane_gap > float(sys_settings.Gmax)

        # Check Shelf Life
        shelf_valid_batches = [
            b for b in wh_batches
            if (b.days_to_expiry_from_dispatch - lane.lead_time_days) >= prod.min_remaining_shelf_days
        ]

        # Determine eligibility & exact reason
        if available_wh_stock <= 0:
            is_eligible = False
            reason = "Zero available stock after planner reserve"
        elif gap_exceeded:
            is_eligible = False
            reason = f"Lane gap {lane_gap:.2f}d exceeds Gmax ({sys_settings.Gmax}d)"
        elif not shelf_valid_batches:
            is_eligible = False
            reason = f"Shelf life at arrival below threshold ({prod.min_remaining_shelf_days}d)"
        else:
            is_eligible = True
            reason = "Eligible"

        sources_considered.append({
            "source_id": wh.id,
            "source_name": wh.name,
            "cost_per_carton": lane.cost_per_carton,
            "lead_time_days": lane.lead_time_days,
            "stock_available": available_wh_stock,
            "is_eligible": is_eligible,
            "reason": reason,
        })

    # Sort sources: eligible first, then by freight cost, then lead time
    sources_considered.sort(
        key=lambda sc: (0 if sc["is_eligible"] else 1, sc["cost_per_carton"] or 9999, sc["lead_time_days"] or 999)
    )

    # 2. Chosen and Why
    batch = next((b for b in ctx["batches_pure"] if b.id == b_id), None)
    chosen_cost = chosen_lane_data.cost_per_carton if chosen_lane_data else 0.0
    chosen_lead_time = chosen_lane_data.lead_time_days if chosen_lane_data else 0

    chosen_info = {
        "source_id": s,
        "batch_id": b_id,
        "cost_per_carton": chosen_cost,
        "lead_time_days": chosen_lead_time,
        "allocated_cartons": line.cartons,
        "why": "cheapest eligible subject to constraints",
    }

    # 3. Constraints Checked
    # C1: Stock
    batch_qty = batch.quantity if batch else 0
    available_batch_stock = max(0, batch_qty - sys_settings.planner_reserve) if batch else 0
    stock_passed = line.cartons <= available_batch_stock

    # C4: Lead time gap
    lane_gap_val = max(0.0, float(chosen_lead_time) - cover_days)
    lead_time_gap_passed = lane_gap_val <= float(sys_settings.Gmax)

    # C6: Lane capacity
    all_run_lines = session.exec(select(PlanLine).where(PlanLine.run_id == line.run_id)).all()
    total_lane_load = sum(
        l.cartons * ctx["products_pure"].get(l.product_id, ProductInfo(id=l.product_id)).load_per_carton
        for l in all_run_lines
        if l.source_id == s and l.destination_id == d
    )
    lane_cap = chosen_lane_data.capacity_load if chosen_lane_data else None
    lane_cap_passed = True if lane_cap is None else (total_lane_load <= lane_cap + 1e-4)

    # Shelf life
    days_to_expiry = batch.days_to_expiry_from_dispatch if batch else 0
    arrival_shelf_days = days_to_expiry - chosen_lead_time
    shelf_life_passed = arrival_shelf_days >= prod.min_remaining_shelf_days
    days_to_sell = round(cover_days, 1)

    constraints_checked = {
        "stock": {
            "batch_id": b_id,
            "batch_total_quantity": batch_qty,
            "planner_reserve": sys_settings.planner_reserve,
            "available_quantity": available_batch_stock,
            "allocated_cartons": line.cartons,
            "passed": stock_passed,
        },
        "lead_time_gap": {
            "lead_time_days": chosen_lead_time,
            "destination_cover_days": round(cover_days, 2),
            "lane_gap_days": round(lane_gap_val, 2),
            "gmax_days": sys_settings.Gmax,
            "passed": lead_time_gap_passed,
        },
        "lane_capacity": {
            "lane": f"{s}->{d}",
            "total_lane_load": round(total_lane_load, 2),
            "capacity_load": lane_cap,
            "passed": lane_cap_passed,
        },
        "shelf_life": {
            "days_to_expiry_from_dispatch": days_to_expiry,
            "days_left_at_arrival": arrival_shelf_days,
            "min_remaining_shelf_days": prod.min_remaining_shelf_days,
            "days_to_sell": days_to_sell,
            "passed": shelf_life_passed,
        },
    }

    # 4. Residual Risk
    total_allocated_pair = sum(
        l.cartons for l in all_run_lines if l.destination_id == d and l.product_id == k
    )
    ndem = req.Ndem if req else 0
    ntot = req.Ntot if req else 0
    udem = max(0, ndem - total_allocated_pair)
    utot = max(0, ntot - total_allocated_pair)
    uss = utot - udem

    residual_risk = {
        "destination_id": d,
        "product_id": k,
        "total_allocated_cartons": total_allocated_pair,
        "demand_requirement_cartons": ndem,
        "total_requirement_cartons": ntot,
        "unmet_demand_cartons": udem,
        "safety_stock_gap_cartons": uss,
        "has_unmet_demand": udem > 0,
        "has_safety_stock_gap": uss > 0,
    }

    flags = json.loads(line.flags_json) if line.flags_json else []
    is_surplus_rescue = any("Surplus rescue" in str(f) for f in flags)

    rescue_analysis_dict = None
    if is_surplus_rescue or residual_risk["has_unmet_demand"]:
        surplus_listings = list(session.exec(select(SurplusListing)).all())
        dest = session.get(Location, d)
        ra = build_rescue_analysis_for_unmet(
            session=session,
            destination_id=d,
            destination_name=dest.name if dest else d,
            product_id=k,
            product_name=prod.name if prod else k,
            unmet_cartons=residual_risk["unmet_demand_cartons"] or line.cartons,
            planning_date=plan_date,
            surplus_listings=surplus_listings,
            products_map={p.id: p for p in session.exec(select(Product)).all()},
            req=req,
            g_max=getattr(sys_settings, "Gmax", 2.0),
            z=getattr(sys_settings, "z", 1.65),
        )
        rescue_analysis_dict = ra.model_dump()

    return {
        "line_id": line.id,
        "run_id": line.run_id,
        "product_id": k,
        "destination_id": d,
        "source_id": s,
        "batch_id": b_id,
        "allocated_cartons": line.cartons,
        "line_cost": line.cost,
        "status": line.status,
        "flags": flags,
        "is_surplus_rescue": is_surplus_rescue,
        "rescue_analysis": rescue_analysis_dict,
        "sources_considered": sources_considered,
        "chosen": chosen_info,
        "constraints_checked": constraints_checked,
        "residual_risk": residual_risk,
        "is_simulated": True,
    }


# -------------------------------------------------------------------
# 4. POST /api/plan/lines/{id}/approve
# -------------------------------------------------------------------
@router.post("/api/v1/plan/lines/{id}/approve", tags=["Plan & Allocation"])
def approve_plan_line(
    id: str,
    payload: Optional[LineApproveRequest] = Body(default=None),
    session: Session = Depends(get_session),
    role: str = Depends(verify_planner_or_reviewer_role),
) -> dict:
    """
    Approve an individual plan line, with optional edited carton allocation.
    Validates entire plan against C1-C6 and requirement rules if edited.
    Refuses rule-breaking edits with HTTP 409 naming the rule, logging the attempt in DecisionLog.
    """
    line = session.get(PlanLine, id)
    if not line:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan line '{id}' not found.",
        )

    req_payload = payload or LineApproveRequest()
    edited_cartons = req_payload.edited_cartons
    notes = req_payload.notes

    # If cartons are edited (or explicitly provided)
    if edited_cartons is not None and edited_cartons != line.cartons:
        plan_run = session.get(PlanRun, line.run_id)
        if not plan_run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Plan run '{line.run_id}' not found.",
            )

        sys_settings = get_current_settings(session)
        ctx = build_domain_context(session, as_of=plan_run.planning_date, settings=sys_settings)

        # Fetch all lines for this run and construct proposed updated plan
        all_lines = session.exec(select(PlanLine).where(PlanLine.run_id == line.run_id)).all()
        proposed_lines = []
        for l in all_lines:
            c = edited_cartons if l.id == line.id else l.cartons
            proposed_lines.append({
                "batch_id": l.batch_id,
                "source_id": l.source_id,
                "destination_id": l.destination_id,
                "product_id": l.product_id,
                "cartons": c,
            })

        # Run rule checker services/rules.py
        check_result = validate_plan_allocation(
            lines=proposed_lines,
            batches=ctx["batches_pure"],
            lanes=ctx["lanes_pure"],
            products=ctx["products_pure"],
            requirements=ctx["requirements"],
            Gmax=sys_settings.Gmax,
            planner_reserve=sys_settings.planner_reserve,
        )

        if not check_result.is_valid:
            rule_name = check_result.first_rule_name or "RULE_VIOLATION"
            msg = check_result.first_message or "Plan allocation violates constraints."

            # Log refused attempt to DecisionLog
            refused_log = DecisionLog(
                plan_line_id=line.id,
                actor_role=role,
                action="EDIT_REFUSED",
                old_value=str(line.cartons),
                new_value=str(edited_cartons),
                note=f"Refused by rule {rule_name}: {msg}",
            )
            session.add(refused_log)
            session.commit()

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Edit refused by rule: {rule_name}. {msg}",
            )

        # Valid edit accepted
        old_cartons = line.cartons
        lane = next(
            (l for l in ctx["lanes_pure"] if l.source_id == line.source_id and l.destination_id == line.destination_id),
            None,
        )
        cost_rate = lane.cost_per_carton if lane else 0.0

        line.cartons = edited_cartons
        line.cost = round(edited_cartons * cost_rate, 2)
        line.status = "EDITED"
        session.add(line)

        log_entry = DecisionLog(
            plan_line_id=line.id,
            actor_role=role,
            action="EDIT",
            old_value=f"{old_cartons} cartons",
            new_value=f"{edited_cartons} cartons",
            note=notes or f"Edited allocation cartons from {old_cartons} to {edited_cartons}",
        )
        session.add(log_entry)
        session.commit()

        return {
            "status": "success",
            "action": "EDIT",
            "line_id": line.id,
            "cartons": line.cartons,
            "cost": line.cost,
            "line_status": line.status,
            "message": f"Line '{id}' edited successfully to {edited_cartons} cartons.",
        }

    # Plain approval without carton change
    old_status = line.status
    line.status = "APPROVED"
    session.add(line)

    log_entry = DecisionLog(
        plan_line_id=line.id,
        actor_role=role,
        action="APPROVE",
        old_value=old_status,
        new_value="APPROVED",
        note=notes or f"Line approved without changes ({line.cartons} cartons)",
    )
    session.add(log_entry)
    session.commit()

    from backend.app.routers.dashboard import invalidate_dashboard_cache
    invalidate_dashboard_cache()

    return {
        "status": "success",
        "action": "APPROVE",
        "line_id": line.id,
        "cartons": line.cartons,
        "cost": line.cost,
        "line_status": line.status,
        "message": f"Line '{id}' approved successfully.",
    }


# -------------------------------------------------------------------
# 5. POST /api/plan/lines/{id}/reject
# -------------------------------------------------------------------
@router.post("/api/v1/plan/lines/{id}/reject", tags=["Plan & Allocation"])
def reject_plan_line(
    id: str,
    payload: Optional[LineRejectRequest] = Body(default=None),
    reason: Optional[str] = Query(default=None),
    session: Session = Depends(get_session),
    role: str = Depends(verify_planner_or_reviewer_role),
) -> dict:
    """
    Reject an individual plan line. Reason is required.
    Zeroes line cartons and sets status to REJECTED. Logs action to DecisionLog.
    """
    line = session.get(PlanLine, id)
    if not line:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan line '{id}' not found.",
        )

    # Reason required
    req_reason = None
    if payload and payload.reason:
        req_reason = payload.reason.strip()
    elif reason:
        req_reason = reason.strip()

    if not req_reason:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reject reason is required. Please provide a non-empty reason.",
        )

    old_cartons = line.cartons
    old_status = line.status

    line.cartons = 0
    line.cost = 0.0
    line.status = "REJECTED"
    session.add(line)

    log_entry = DecisionLog(
        plan_line_id=line.id,
        actor_role=role,
        action="REJECT",
        old_value=f"{old_cartons} cartons ({old_status})",
        new_value="0 cartons (REJECTED)",
        note=f"Rejected: {req_reason}",
    )
    session.add(log_entry)
    session.commit()

    from backend.app.routers.dashboard import invalidate_dashboard_cache
    invalidate_dashboard_cache()

    return {
        "status": "success",
        "action": "REJECT",
        "line_id": line.id,
        "cartons": line.cartons,
        "cost": line.cost,
        "line_status": line.status,
        "reason": req_reason,
        "message": f"Line '{id}' rejected: {req_reason}",
    }


# -------------------------------------------------------------------
# 6. POST /api/scenario/override
# -------------------------------------------------------------------
@router.post("/api/v1/scenario/override", tags=["Scenario"])
def quick_edit_scenario_override(
    payload: ScenarioOverrideRequest,
    session: Session = Depends(get_session),
    role: str = Depends(get_current_role),
) -> dict:
    """
    Quick-edit: set a source's stock (percent or absolute) or a destination's demand multiplier.
    Computes and returns a before-and-after change summary (unmet units and cost).
    """
    effective_as_of = payload.as_of or dt_date(2026, 10, 24)
    sys_settings = get_current_settings(session)
    opt_service = OptimizationService(session)

    # 1. Capture BEFORE state from latest plan run if present, or run base plan
    latest_run = session.exec(select(PlanRun).order_by(PlanRun.created_at.desc())).first()
    if latest_run and latest_run.planning_date == effective_as_of:
        before_cost = latest_run.total_cost
        before_unmet_demand = latest_run.total_unmet_cartons
        before_unmet_safety_stock = getattr(latest_run, "total_unmet_safety_stock_cartons", 0) or 0
        before_total_cartons = latest_run.total_cartons
    else:
        before_result = opt_service.run_plan(plan_date=effective_as_of, run_by_role="system")
        before_cost = before_result.total_cost
        before_unmet_demand = before_result.total_unmet_demand_cartons
        before_unmet_safety_stock = before_result.total_unmet_safety_stock_cartons
        before_total_cartons = before_result.total_cartons

    # 2. Apply Override to Data
    override_desc = []

    if payload.source_id:
        src = payload.source_id.upper().strip()
        batches = session.exec(select(Batch).where(Batch.location_id == src)).all()
        if not batches:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Source location '{src}' has no inventory batches.",
            )

        if payload.stock_percent is not None:
            pct = payload.stock_percent
            # Handle -20 or -0.20
            factor = (1.0 + pct / 100.0) if abs(pct) > 1.0 else (1.0 + pct)
            total_before_stock = sum(b.quantity for b in batches)
            for b in batches:
                b.quantity = max(0, int(round(b.quantity * factor)))
                session.add(b)
            total_after_stock = sum(b.quantity for b in batches)
            override_desc.append(
                f"Source '{src}' stock scaled by {pct}% ({total_before_stock} -> {total_after_stock} cartons)"
            )

        elif payload.stock_absolute is not None:
            total_before_stock = sum(b.quantity for b in batches)
            target = payload.stock_absolute
            if total_before_stock > 0:
                scale = target / total_before_stock
                for b in batches:
                    b.quantity = max(0, int(round(b.quantity * scale)))
                    session.add(b)
            else:
                for b in batches:
                    b.quantity = target // len(batches)
                    session.add(b)
            override_desc.append(f"Source '{src}' stock set to {target} cartons")

        # Sync InventorySnapshot on_hand for source
        for b in batches:
            snap = session.exec(
                select(InventorySnapshot).where(
                    InventorySnapshot.location_id == src,
                    InventorySnapshot.product_id == b.product_id,
                )
            ).first()
            if snap:
                snap.on_hand = sum(
                    item.quantity for item in batches if item.product_id == b.product_id
                )
                session.add(snap)

    if payload.destination_id and payload.demand_multiplier is not None:
        dest = payload.destination_id.upper().strip()
        mult = payload.demand_multiplier
        sales_records = session.exec(
            select(SalesDaily).where(SalesDaily.location_id == dest)
        ).all()
        for s in sales_records:
            s.units = max(0, int(round(s.units * mult)))
            session.add(s)
        override_desc.append(f"Destination '{dest}' demand scaled by {mult}x")

    # Record DecisionLog
    decision_note = "; ".join(override_desc) if override_desc else "Scenario quick-edit applied"
    session.add(
        DecisionLog(
            plan_line_id=None,
            actor_role=role,
            action="OVERRIDE",
            old_value=f"Before: unmet demand={before_unmet_demand}, cost=₹{before_cost}",
            new_value=decision_note,
            note=payload.notes or decision_note,
        )
    )
    session.commit()

    # 3. Capture AFTER state by running new plan
    after_result = opt_service.run_plan(plan_date=effective_as_of, run_by_role=role)
    after_cost = after_result.total_cost
    after_unmet_demand = after_result.total_unmet_demand_cartons
    after_unmet_safety_stock = after_result.total_unmet_safety_stock_cartons
    after_total_cartons = after_result.total_cartons

    return {
        "status": "success",
        "action": "OVERRIDE",
        "applied_override": decision_note,
        "new_run_id": after_result.run_id,
        "change_summary": {
            "before": {
                "unmet_demand_cartons": before_unmet_demand,
                "unmet_safety_stock_cartons": before_unmet_safety_stock,
                "total_unmet_cartons": before_unmet_demand + before_unmet_safety_stock,
                "total_shipped_cartons": before_total_cartons,
                "total_transport_cost": before_cost,
            },
            "after": {
                "unmet_demand_cartons": after_unmet_demand,
                "unmet_safety_stock_cartons": after_unmet_safety_stock,
                "total_unmet_cartons": after_unmet_demand + after_unmet_safety_stock,
                "total_shipped_cartons": after_total_cartons,
                "total_transport_cost": after_cost,
            },
            "difference": {
                "unmet_demand_change": after_unmet_demand - before_unmet_demand,
                "unmet_safety_stock_change": after_unmet_safety_stock - before_unmet_safety_stock,
                "total_unmet_change": (after_unmet_demand + after_unmet_safety_stock) - (before_unmet_demand + before_unmet_safety_stock),
                "cost_change": round(after_cost - before_cost, 2),
            },
        },
        "is_simulated": True,
    }


# -------------------------------------------------------------------
# 7. GET /api/audit
# -------------------------------------------------------------------
@router.get("/api/v1/audit", tags=["Audit"])
def get_audit_trail(
    limit: int = Query(default=100, ge=1, le=1000),
    session: Session = Depends(get_session),
) -> list[dict]:
    """
    Returns complete immutable DecisionLog audit trail ordered by timestamp descending.
    Captures actor role, action, old value, new value, note, and timestamp.
    """
    logs = session.exec(
        select(DecisionLog).order_by(DecisionLog.timestamp.desc()).limit(limit)  # type: ignore
    ).all()

    return [
        {
            "id": log.id,
            "plan_line_id": log.plan_line_id,
            "actor_role": log.actor_role,
            "action": log.action,
            "old_value": log.old_value,
            "new_value": log.new_value,
            "note": log.note,
            "timestamp": log.timestamp.isoformat(),
        }
        for log in logs
    ]


# -------------------------------------------------------------------
# 8. Surplus Rescue & Dead-Stock Intelligence Endpoints
# -------------------------------------------------------------------

@router.post("/api/v1/plan/{run_id}/rescue/apply", tags=["Plan & Allocation"])
def apply_rescue_endpoint(
    run_id: str,
    payload: RescueApplyRequest,
    session: Session = Depends(get_session),
    role: str = Depends(verify_planner_or_reviewer_role),
) -> dict:
    """
    Apply a verified surplus rescue allocation to an existing PlanRun.
    Role-gated to planner or reviewer.
    """
    try:
        res = apply_shortfall_rescue(
            session=session,
            run_id=run_id,
            destination_id=payload.destination_id,
            product_id=payload.product_id,
            surplus_listing_id=payload.surplus_listing_id,
            cartons=payload.cartons,
            actor_role=role,
            notes=payload.notes,
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/api/v1/plan/{run_id}/rescue/undo", tags=["Plan & Allocation"])
def undo_rescue_endpoint(
    run_id: str,
    log_id: int = Query(..., description="DecisionLog ID of the rescue action to undo"),
    session: Session = Depends(get_session),
    role: str = Depends(verify_planner_or_reviewer_role),
) -> dict:
    """
    Undo a previously applied surplus rescue.
    Role-gated to planner or reviewer.
    """
    try:
        res = undo_shortfall_rescue(
            session=session,
            log_id=log_id,
            actor_role=role,
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/api/v1/surplus/listings", tags=["Plan & Allocation"])
def get_surplus_listings(session: Session = Depends(get_session)) -> list[dict]:
    """
    Return all peer and depot surplus listings with verified spare calculations.
    """
    listings = session.exec(select(SurplusListing)).all()
    results = []
    for l in listings:
        spare, need, _ = compute_verified_spare_stock(l)
        d = l.model_dump()
        d["lead_time_days_by_dest"] = l.get_lead_time_dict()
        d["freight_per_carton_by_dest"] = l.get_freight_dict()
        d["verified_spare_cartons"] = spare
        d["seller_protected_need"] = need
        results.append(d)
    return results


@router.get("/api/v1/plan/{run_id}/dead-stock", tags=["Plan & Allocation"])
def get_dead_stock(run_id: str, session: Session = Depends(get_session)) -> list[dict]:
    """
    Return dead-stock early warnings for warehouse batches under this plan run.
    """
    plan_run = session.get(PlanRun, run_id)
    if not plan_run:
        raise HTTPException(status_code=404, detail="PlanRun not found")
    lines = list(session.exec(select(PlanLine).where(PlanLine.run_id == run_id)).all())
    warnings = compute_dead_stock_warnings(session, plan_date=plan_run.planning_date, plan_lines=lines)
    return [w.model_dump() for w in warnings]

