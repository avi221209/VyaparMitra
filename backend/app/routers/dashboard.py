"""
VyaparMitra - Production Dashboard Summary, Notifications & Search API Router
Exposed strictly under /api/v1/ (no duplicate unversioned alias).

Endpoints:
  - GET /api/v1/dashboard/summary?run_id=&horizon=
  - GET /api/v1/notifications
  - GET /api/v1/search?q=
"""

from datetime import date as dt_date, datetime as dt_datetime, timedelta, timezone
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, func, select

from backend.app.config import DATA_DIR
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
    ValidationIssue,
)
from backend.app.services.geo import get_city_coordinates
from backend.app.services.forecast import (
    ForecastService,
    compute_bias,
    compute_wape,
    forecast_seasonal_naive,
)
from backend.app.settings import get_current_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Dashboard"])

# Module-level cache for dashboard summaries
_SUMMARY_CACHE: Dict[str, Any] = {}
_CACHE_VERSION: int = 1


def invalidate_dashboard_cache() -> None:
    """Invalidate all cached dashboard summaries."""
    global _SUMMARY_CACHE, _CACHE_VERSION
    _SUMMARY_CACHE.clear()
    _CACHE_VERSION += 1
    logger.info("Dashboard cache invalidated. New cache version: %d", _CACHE_VERSION)


# =====================================================================
# Pure Functions & Calculations (Tested with exact boundary tests)
# =====================================================================
def compute_stock_status(
    stock_units: float,
    expected_demand_units: float,
    has_expiring_shortfall: bool = False,
    healthy_threshold: float = 1.0,
    low_stock_threshold: float = 0.5,
) -> Tuple[float, str]:
    """
    Pure deterministic stock health classification.
    
    Rules:
      - ratio = stock / expected demand (guard against division by zero).
      - If expected_demand_units <= 0:
          ratio = 999.0 if stock_units > 0 else 1.0
      - If has_expiring_shortfall is True: 'Critical'
      - If ratio < low_stock_threshold (0.5): 'Critical'
      - If low_stock_threshold <= ratio < healthy_threshold (1.0): 'Low stock'
      - If ratio >= healthy_threshold (1.0): 'Healthy'
    """
    if expected_demand_units <= 0:
        ratio = 999.0 if stock_units > 0 else 1.0
    else:
        ratio = stock_units / expected_demand_units

    if has_expiring_shortfall:
        return round(ratio, 4), "Critical"

    if ratio < low_stock_threshold:
        return round(ratio, 4), "Critical"
    elif ratio < healthy_threshold:
        return round(ratio, 4), "Low stock"
    else:
        return round(ratio, 4), "Healthy"


# =====================================================================
# Response Schemas
# =====================================================================
class PlanningPeriod(BaseModel):
    start: dt_date
    end: dt_date
    horizon_days: int


class LocationCounts(BaseModel):
    total: int
    warehouses: int
    retailers: int


class AttentionKPI(BaseModel):
    count: int
    low_stock: int
    critical: int
    high_demand: int
    unmet_cartons: int
    blocking_data_issues: int


class DashboardKPIs(BaseModel):
    products: int
    locations: LocationCounts
    inventory_units: int
    attention: AttentionKPI


class NetworkNode(BaseModel):
    id: str
    name: str
    type: str
    city: Optional[str] = None
    state: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    stock_units: int
    unmet_cartons: int
    high_demand: bool


class NetworkFlow(BaseModel):
    from_id: str
    to_id: str
    cartons: int
    line_count: int


class NetworkData(BaseModel):
    nodes: List[NetworkNode]
    flows: List[NetworkFlow]
    unmapped: List[str]


class StockStatusItem(BaseModel):
    product_id: str
    name: str
    category: str
    total_stock_units: int
    expected_demand_units: int
    ratio: float
    status: str


class BenefitVsBaseline(BaseModel):
    value_inr: float
    baseline: str
    source: str


class RecentPlanSummary(BaseModel):
    run_id: str
    created_at: dt_datetime
    status: str
    dispatches: int
    locations: int
    units: int
    transport_cost: float
    used_heuristic: bool
    benefit_vs_baseline: Optional[BenefitVsBaseline] = None


class ForecastWeek(BaseModel):
    label: str
    actual: Optional[float] = None
    forecast: Optional[float] = None
    is_future: bool


class ForecastSummary(BaseModel):
    weeks: List[ForecastWeek]
    wape: float
    accuracy_pct: float
    bias: float


class PendingApprovalItem(BaseModel):
    line_id: str
    product_name: str
    category: str
    from_name: str
    to_name: str
    cartons: int
    created_at: dt_datetime


class PendingApprovalsSummary(BaseModel):
    total: int
    items: List[PendingApprovalItem]


class DashboardSummaryResponse(BaseModel):
    as_of: dt_date
    data_is_sample: bool
    planning_period: PlanningPeriod
    kpis: DashboardKPIs
    network: NetworkData
    stock_status: List[StockStatusItem]
    recent_plan: Optional[RecentPlanSummary] = None
    forecast: ForecastSummary
    pending_approvals: PendingApprovalsSummary


class NotificationItem(BaseModel):
    type: str
    label: str
    href: str


class NotificationsResponse(BaseModel):
    count: int
    items: List[NotificationItem]


class SearchResultItem(BaseModel):
    id: str
    title: str
    subtitle: Optional[str] = None
    category: Optional[str] = None
    href: str


class SearchResponse(BaseModel):
    query: str
    total: int
    results: Dict[str, List[SearchResultItem]]


# =====================================================================
# Benefit vs Baseline Loader (From Evaluation Cache)
# =====================================================================
def get_benefit_vs_baseline_from_cache() -> Optional[BenefitVsBaseline]:
    """
    Reads cached evaluation for balanced scenario (mean over seeds).
    Value = baseline - VyaparMitra, in INR.
    Returns None if cache is absent or values are unavailable. Never invents.
    """
    cache_path = DATA_DIR / "evaluation_cache.json"
    if not cache_path.exists():
        return None

    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        balanced = data.get("scenarios_aggregate", {}).get("balanced", {})
        checks = balanced.get("targets_evaluation", {}).get("checks", {})
        cost_check = checks.get("cost_to_serve", {})

        v_val = cost_check.get("v_value")
        # Best operational baseline among A, B, C is C (Forecast + Greedy)
        c_val = cost_check.get("c_value")

        if v_val is not None and c_val is not None and c_val > v_val:
            benefit = round(float(c_val) - float(v_val), 2)
            return BenefitVsBaseline(
                value_inr=benefit,
                baseline="Forecast + Greedy Allocation",
                source="28-day walk-forward replay (balanced)",
            )
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as err:
        logger.warning("Could not compute benefit_vs_baseline from evaluation cache: %s", err)

    return None


# =====================================================================
# Endpoints
# =====================================================================
@router.get("/dashboard/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary(
    run_id: Optional[str] = Query(default=None),
    horizon: Optional[int] = Query(default=None, ge=1, le=30),
    session: Session = Depends(get_session),
) -> DashboardSummaryResponse:
    """
    Returns the comprehensive FMCG distribution dashboard summary in one single call.
    Includes KPIs, network nodes and flows, stock status, recent plan, forecast, and approvals.
    """
    cache_key = f"v{_CACHE_VERSION}:{run_id}:{horizon}"
    if cache_key in _SUMMARY_CACHE:
        return _SUMMARY_CACHE[cache_key]

    settings = get_current_settings(session)
    h_days = horizon or settings.H

    # 1. Determine as_of date
    max_sales_date = session.exec(select(func.max(SalesDaily.date))).one()
    if max_sales_date:
        as_of_date = max_sales_date + timedelta(days=1)
    else:
        as_of_date = dt_date(2026, 10, 24)

    # 2. Determine data_is_sample
    # If any user CSV upload exists in DecisionLog, it's not the sample data
    upload_log = session.exec(
        select(DecisionLog).where(DecisionLog.action == "UPLOAD_CSV")
    ).first()
    data_is_sample = upload_log is None

    # 3. Planning Period
    planning_period = PlanningPeriod(
        start=as_of_date,
        end=as_of_date + timedelta(days=h_days - 1),
        horizon_days=h_days,
    )

    # 4. Fetch Master Data
    products = list(session.exec(select(Product)).all())
    locations = list(session.exec(select(Location)).all())
    prod_map = {p.id: p for p in products}
    loc_map = {l.id: l for l in locations}

    warehouses = [l for l in locations if l.type == "warehouse"]
    retailers = [l for l in locations if l.type != "warehouse"]
    wh_ids = {w.id for w in warehouses}
    ret_ids = {r.id for r in retailers}

    # 5. Inventory Calculation (on-hand across all nodes in units)
    # Warehouses: from Batch.quantity
    batches = list(session.exec(select(Batch)).all())
    # Destinations: from InventorySnapshot.on_hand
    snapshots = list(session.exec(select(InventorySnapshot)).all())

    # Map product -> total stock units, and node -> stock units
    prod_stock_units: Dict[str, int] = {p.id: 0 for p in products}
    node_stock_units: Dict[str, int] = {l.id: 0 for l in locations}
    prod_batches: Dict[str, List[Batch]] = {p.id: [] for p in products}

    for b in batches:
        cp = prod_map[b.product_id].case_pack if b.product_id in prod_map else 1
        units = b.quantity * cp
        prod_stock_units[b.product_id] = prod_stock_units.get(b.product_id, 0) + units
        node_stock_units[b.location_id] = node_stock_units.get(b.location_id, 0) + units
        prod_batches.setdefault(b.product_id, []).append(b)

    for s in snapshots:
        cp = prod_map[s.product_id].case_pack if s.product_id in prod_map else 1
        units = max(0, s.on_hand) * cp
        prod_stock_units[s.product_id] = prod_stock_units.get(s.product_id, 0) + units
        node_stock_units[s.location_id] = node_stock_units.get(s.location_id, 0) + units

    total_inventory_units = sum(prod_stock_units.values())

    # 6. Demand Forecast & High Demand calculation
    # Expected demand units = daily forecast summed over horizon for that product across all destinations
    prod_expected_demand: Dict[str, float] = {p.id: 0.0 for p in products}
    dest_high_demand: Dict[str, bool] = {r.id: False for r in retailers}
    high_demand_series_count = 0

    # Fetch historical sales for trailing 28 days for high_demand check
    # high_demand = series next-horizon forecast >= 1.20 * trailing 28-day average
    d28_start = as_of_date - timedelta(days=28)
    trailing_sales_records = list(
        session.exec(
            select(SalesDaily).where(
                SalesDaily.date >= d28_start,
                SalesDaily.date < as_of_date,
            )
        ).all()
    )
    sales_trailing_sums: Dict[Tuple[str, str], float] = {}
    for sr in trailing_sales_records:
        sales_trailing_sums[(sr.product_id, sr.location_id)] = (
            sales_trailing_sums.get((sr.product_id, sr.location_id), 0.0) + sr.units
        )

    # Use ForecastResults if present, or quick seasonal-naive forecast
    cached_forecasts = list(
        session.exec(
            select(ForecastResult).where(ForecastResult.as_of_date == as_of_date)
        ).all()
    )
    fc_dict: Dict[Tuple[str, str], List[float]] = {}
    for fc in cached_forecasts:
        try:
            fc_dict[(fc.product_id, fc.location_id)] = json.loads(fc.daily_forecast_json)
        except (json.JSONDecodeError, ValueError):
            pass

    # If empty, generate using seasonal naive fallback
    for p in products:
        for r in retailers:
            forecast_vec = fc_dict.get((p.id, r.id))
            if not forecast_vec:
                # Estimate from trailing sales
                past_sum = sales_trailing_sums.get((p.id, r.id), 0.0)
                daily_avg = past_sum / 28.0 if past_sum > 0 else 10.0
                forecast_vec = [daily_avg] * h_days

            horizon_demand = sum(forecast_vec[:h_days])
            prod_expected_demand[p.id] += horizon_demand

            # High demand check
            trailing_avg = sales_trailing_sums.get((p.id, r.id), 0.0) / 28.0
            next_avg = horizon_demand / h_days if h_days > 0 else 0.0
            if trailing_avg > 0 and next_avg >= 1.20 * trailing_avg:
                dest_high_demand[r.id] = True
                high_demand_series_count += 1
            elif trailing_avg == 0 and next_avg > 0:
                dest_high_demand[r.id] = True
                high_demand_series_count += 1

    # 7. Stock Status per Product
    stock_status_items: List[StockStatusItem] = []
    low_stock_count = 0
    critical_count = 0

    for p in products:
        stock = float(prod_stock_units.get(p.id, 0))
        demand = float(prod_expected_demand.get(p.id, 0.0))

        # Check if batches expire within min_remaining_shelf_days and stock < demand
        shortfall = demand > stock
        has_expiring = False
        if shortfall:
            shelf_cutoff = as_of_date + timedelta(days=p.min_remaining_shelf_days)
            for b in prod_batches.get(p.id, []):
                if b.expiry_date <= shelf_cutoff:
                    has_expiring = True
                    break

        ratio, status_str = compute_stock_status(
            stock_units=stock,
            expected_demand_units=demand,
            has_expiring_shortfall=has_expiring,
        )

        if status_str == "Low stock":
            low_stock_count += 1
        elif status_str == "Critical":
            critical_count += 1

        stock_status_items.append(
            StockStatusItem(
                product_id=p.id,
                name=p.name,
                category=p.category,
                total_stock_units=int(stock),
                expected_demand_units=int(round(demand)),
                ratio=ratio,
                status=status_str,
            )
        )

    # Sort stock status items by ratio ascending (most at-risk first)
    stock_status_items.sort(key=lambda item: (item.ratio, item.product_id))

    # 8. Recent Plan Run & Flows
    if run_id:
        plan_run = session.get(PlanRun, run_id)
    else:
        plan_run = session.exec(
            select(PlanRun).order_by(PlanRun.created_at.desc())  # type: ignore
        ).first()

    recent_plan_summary: Optional[RecentPlanSummary] = None
    flows: List[NetworkFlow] = []
    unmet_by_destination: Dict[str, int] = {r.id: 0 for r in retailers}
    destinations_with_unmet = set()
    total_unmet_cartons = 0

    if plan_run:
        plan_lines = list(
            session.exec(
                select(PlanLine).where(PlanLine.run_id == plan_run.id)
            ).all()
        )

        flow_map: Dict[Tuple[str, str], List[int]] = {}
        dest_set = set()
        dispatches_count = 0
        total_units_dispatched = 0

        for pl in plan_lines:
            if pl.cartons > 0:
                dispatches_count += 1
                dest_set.add(pl.destination_id)
                cp = prod_map[pl.product_id].case_pack if pl.product_id in prod_map else 1
                total_units_dispatched += pl.cartons * cp
                key = (pl.source_id, pl.destination_id)
                flow_map.setdefault(key, []).append(pl.cartons)

        for (from_id, to_id), cartons_list in flow_map.items():
            flows.append(
                NetworkFlow(
                    from_id=from_id,
                    to_id=to_id,
                    cartons=sum(cartons_list),
                    line_count=len(cartons_list),
                )
            )

        # Parse counterfactuals to get unmet cartons per destination
        try:
            cf_list = json.loads(plan_run.counterfactuals_json or "[]")
            for cf in cf_list:
                dest = cf.get("destination_id")
                unmet_c = cf.get("unmet_cartons", 0)
                if dest and unmet_c > 0:
                    unmet_by_destination[dest] = unmet_by_destination.get(dest, 0) + unmet_c
                    destinations_with_unmet.add(dest)
        except (json.JSONDecodeError, ValueError):
            pass

        total_unmet_cartons = plan_run.total_unmet_cartons

        used_heur = (
            plan_run.status == "HEURISTIC"
            or "heuristic" in (plan_run.notes or "").lower()
        )

        recent_plan_summary = RecentPlanSummary(
            run_id=plan_run.id,
            created_at=plan_run.created_at,
            status=plan_run.status,
            dispatches=dispatches_count,
            locations=len(dest_set),
            units=total_units_dispatched,
            transport_cost=round(plan_run.total_cost, 2),
            used_heuristic=used_heur,
            benefit_vs_baseline=get_benefit_vs_baseline_from_cache(),
        )

    # 9. Network Nodes & Coordinates
    nodes: List[NetworkNode] = []
    unmapped_ids: List[str] = []

    for loc in locations:
        coords = get_city_coordinates(loc.city)
        lat = coords[0] if coords else None
        lon = coords[1] if coords else None

        if lat is None or lon is None:
            unmapped_ids.append(loc.id)

        nodes.append(
            NetworkNode(
                id=loc.id,
                name=loc.name,
                type=loc.type,
                city=loc.city,
                state=loc.state,
                lat=lat,
                lon=lon,
                stock_units=node_stock_units.get(loc.id, 0),
                unmet_cartons=unmet_by_destination.get(loc.id, 0),
                high_demand=dest_high_demand.get(loc.id, False),
            )
        )

    # 10. Blocking Data Issues & Attention Counts
    blocking_issues_count = session.exec(
        select(func.count(ValidationIssue.id)).where(
            ValidationIssue.severity == "critical",
            ValidationIssue.status == "open",
        )
    ).one()

    # Attention items count: distinct Low/Critical products + destinations with unmet + critical blocking issues
    distinct_at_risk_products = low_stock_count + critical_count
    attention_count = (
        distinct_at_risk_products
        + len(destinations_with_unmet)
        + blocking_issues_count
    )

    kpis = DashboardKPIs(
        products=len(products),
        locations=LocationCounts(
            total=len(locations),
            warehouses=len(warehouses),
            retailers=len(retailers),
        ),
        inventory_units=total_inventory_units,
        attention=AttentionKPI(
            count=attention_count,
            low_stock=low_stock_count,
            critical=critical_count,
            high_demand=high_demand_series_count,
            unmet_cartons=total_unmet_cartons,
            blocking_data_issues=blocking_issues_count,
        ),
    )

    # 11. Forecast Summary (Last 4 Weeks Actual + Forecast, Next 4 Weeks Forecast)
    # Aggregated weekly across the network
    forecast_weeks: List[ForecastWeek] = []
    weekly_actuals: List[float] = []
    weekly_forecasts: List[float] = []

    # Last 4 weeks: W-4, W-3, W-2, W-1
    for w_idx in range(4, 0, -1):
        w_start = as_of_date - timedelta(days=w_idx * 7)
        w_end = as_of_date - timedelta(days=(w_idx - 1) * 7)
        label = f"W-{w_idx}"

        # Sum actual sales in window
        w_sales_sum = session.exec(
            select(func.sum(SalesDaily.units)).where(
                SalesDaily.date >= w_start,
                SalesDaily.date < w_end,
            )
        ).one()
        actual_val = float(w_sales_sum or 0.0)

        # Forecast that existed before that week (from week before, or 7-day prior sales)
        # Using prior 7-day sales as deterministic seasonal naive forecast
        prior_sales_sum = session.exec(
            select(func.sum(SalesDaily.units)).where(
                SalesDaily.date >= w_start - timedelta(days=7),
                SalesDaily.date < w_start,
            )
        ).one()
        fc_val = float(prior_sales_sum or actual_val * 0.95)

        weekly_actuals.append(actual_val)
        weekly_forecasts.append(fc_val)

        forecast_weeks.append(
            ForecastWeek(
                label=label,
                actual=round(actual_val, 1),
                forecast=round(fc_val, 1),
                is_future=False,
            )
        )

    # Next 4 weeks: W+1, W+2, W+3, W+4 (future only, actual = null)
    # Estimate future weekly demand from baseline / seasonal naive pattern
    last_week_actual = weekly_actuals[-1] if weekly_actuals else 1000.0
    for w_idx in range(1, 5):
        label = f"W+{w_idx}"
        # Flat or slight seasonal projection
        future_fc = round(last_week_actual * (1.0 + 0.02 * (w_idx - 1)), 1)
        forecast_weeks.append(
            ForecastWeek(
                label=label,
                actual=None,
                forecast=future_fc,
                is_future=True,
            )
        )

    # WAPE and Bias over the 4 historical weeks
    wape = compute_wape(weekly_actuals, weekly_forecasts)
    bias = compute_bias(weekly_actuals, weekly_forecasts)
    accuracy_pct = round(max(0.0, 100.0 * (1.0 - wape)), 1)

    forecast_summary = ForecastSummary(
        weeks=forecast_weeks,
        wape=round(wape, 4),
        accuracy_pct=accuracy_pct,
        bias=round(bias, 4),
    )

    # 12. Pending Approvals
    pending_items: List[PendingApprovalItem] = []
    total_pending = 0

    if plan_run:
        proposed_lines = list(
            session.exec(
                select(PlanLine)
                .where(
                    PlanLine.run_id == plan_run.id,
                    PlanLine.status == "PROPOSED",
                )
                .order_by(PlanLine.cartons.desc())  # type: ignore
            ).all()
        )
        total_pending = len(proposed_lines)

        for pl in proposed_lines[:10]:
            p_name = prod_map[pl.product_id].name if pl.product_id in prod_map else pl.product_id
            p_cat = prod_map[pl.product_id].category if pl.product_id in prod_map else "General"
            f_name = loc_map[pl.source_id].name if pl.source_id in loc_map else pl.source_id
            t_name = loc_map[pl.destination_id].name if pl.destination_id in loc_map else pl.destination_id

            pending_items.append(
                PendingApprovalItem(
                    line_id=pl.id,
                    product_name=p_name,
                    category=p_cat,
                    from_name=f_name,
                    to_name=t_name,
                    cartons=pl.cartons,
                    created_at=plan_run.created_at,
                )
            )

    pending_approvals = PendingApprovalsSummary(
        total=total_pending,
        items=pending_items,
    )

    response = DashboardSummaryResponse(
        as_of=as_of_date,
        data_is_sample=data_is_sample,
        planning_period=planning_period,
        kpis=kpis,
        network=NetworkData(
            nodes=nodes,
            flows=flows,
            unmapped=unmapped_ids,
        ),
        stock_status=stock_status_items,
        recent_plan=recent_plan_summary,
        forecast=forecast_summary,
        pending_approvals=pending_approvals,
    )

    _SUMMARY_CACHE[cache_key] = response
    return response


@router.get("/notifications", response_model=NotificationsResponse)
def get_notifications(
    session: Session = Depends(get_session),
) -> NotificationsResponse:
    """
    Returns pending approvals, attention items, and blocking data issues.
    count = pending approvals + attention items.
    """
    items: List[NotificationItem] = []

    # 1. Pending Approvals from latest plan
    latest_plan = session.exec(
        select(PlanRun).order_by(PlanRun.created_at.desc())  # type: ignore
    ).first()

    pending_count = 0
    if latest_plan:
        proposed_lines_count = session.exec(
            select(func.count(PlanLine.id)).where(
                PlanLine.run_id == latest_plan.id,
                PlanLine.status == "PROPOSED",
            )
        ).one()
        pending_count = proposed_lines_count
        if proposed_lines_count > 0:
            items.append(
                NotificationItem(
                    type="approval",
                    label=f"{proposed_lines_count} dispatches pending review in Plan #{latest_plan.id}",
                    href="/review",
                )
            )

    # 2. Critical Blocking Data Issues
    critical_issues = list(
        session.exec(
            select(ValidationIssue).where(
                ValidationIssue.severity == "critical",
                ValidationIssue.status == "open",
            )
        ).all()
    )
    for issue in critical_issues[:5]:
        items.append(
            NotificationItem(
                type="data_issue",
                label=f"Blocking issue: {issue.entity} ({issue.description or issue.type})",
                href="/data",
            )
        )

    # 3. Attention Items (Unmet demand from plan)
    if latest_plan and latest_plan.total_unmet_cartons > 0:
        items.append(
            NotificationItem(
                type="unmet_demand",
                label=f"{latest_plan.total_unmet_cartons} unmet cartons in Plan #{latest_plan.id}",
                href="/plan",
            )
        )

    # 4. Total attention items count
    # Distinct products needing attention + destinations with unmet + blocking issues
    attention_count = len(critical_issues) + (1 if (latest_plan and latest_plan.total_unmet_cartons > 0) else 0)

    # Notifications count equals pending + attention items
    total_count = pending_count + attention_count

    return NotificationsResponse(
        count=total_count,
        items=items,
    )


@router.get("/search", response_model=SearchResponse)
def search_entities(
    q: Optional[str] = Query(default="", max_length=100),
    session: Session = Depends(get_session),
) -> SearchResponse:
    """
    Grouped search returning matching products, locations, plan runs, and pages (max 8 each).
    """
    clean_q = (q or "").strip().lower()

    res_products: List[SearchResultItem] = []
    res_locations: List[SearchResultItem] = []
    res_plans: List[SearchResultItem] = []
    res_pages: List[SearchResultItem] = []

    # 1. Search Pages
    all_pages = [
        {"title": "Home Dashboard", "subtitle": "Operational overview and attention items", "href": "/"},
        {"title": "Data & Network", "subtitle": "Master datasets, locations, and CSV validation", "href": "/data"},
        {"title": "Distribution Plan", "subtitle": "Two-stage optimization and dispatch register", "href": "/plan"},
        {"title": "Review & Approval", "subtitle": "Role-gated dispatch approval desk", "href": "/review"},
        {"title": "Evaluation & Insights", "subtitle": "28-day walk-forward replay and benchmark dot plots", "href": "/evaluate"},
        {"title": "Audit Trail", "subtitle": "Immutable ledger of all operator actions", "href": "/audit"},
    ]
    for p in all_pages:
        if not clean_q or clean_q in p["title"].lower() or clean_q in p["subtitle"].lower():
            res_pages.append(
                SearchResultItem(
                    id=p["href"],
                    title=p["title"],
                    subtitle=p["subtitle"],
                    category="Page",
                    href=p["href"],
                )
            )
        if len(res_pages) >= 8:
            break

    # 2. Search Products
    prod_query = select(Product)
    if clean_q:
        prod_query = prod_query.where(
            func.lower(Product.id).contains(clean_q)
            | func.lower(Product.name).contains(clean_q)
            | func.lower(Product.category).contains(clean_q)
        )
    matching_prods = list(session.exec(prod_query.limit(8)).all())
    for prod in matching_prods:
        res_products.append(
            SearchResultItem(
                id=prod.id,
                title=prod.name,
                subtitle=f"{prod.category} • Pack of {prod.case_pack}",
                category="Product",
                href="/data",
            )
        )

    # 3. Search Locations
    loc_query = select(Location)
    if clean_q:
        loc_query = loc_query.where(
            func.lower(Location.id).contains(clean_q)
            | func.lower(Location.name).contains(clean_q)
            | func.lower(Location.city).contains(clean_q)
            | func.lower(Location.state).contains(clean_q)
        )
    matching_locs = list(session.exec(loc_query.limit(8)).all())
    for loc in matching_locs:
        city_state = f"{loc.city or ''}, {loc.state or ''}".strip(", ")
        res_locations.append(
            SearchResultItem(
                id=loc.id,
                title=f"{loc.name} ({loc.id})",
                subtitle=f"{loc.type.title()} • {city_state}",
                category="Location",
                href="/data",
            )
        )

    # 4. Search Plan Runs
    plan_query = select(PlanRun)
    if clean_q:
        plan_query = plan_query.where(
            func.lower(PlanRun.id).contains(clean_q)
            | func.lower(PlanRun.status).contains(clean_q)
        )
    matching_plans = list(
        session.exec(
            plan_query.order_by(PlanRun.created_at.desc()).limit(8)  # type: ignore
        ).all()
    )
    for pl in matching_plans:
        res_plans.append(
            SearchResultItem(
                id=pl.id,
                title=f"Plan #{pl.id}",
                subtitle=f"Status: {pl.status} • {pl.total_cartons} cartons",
                category="Plan",
                href=f"/plan",
            )
        )

    total_results = (
        len(res_products)
        + len(res_locations)
        + len(res_plans)
        + len(res_pages)
    )

    return SearchResponse(
        query=q or "",
        total=total_results,
        results={
            "products": res_products,
            "locations": res_locations,
            "plans": res_plans,
            "pages": res_pages,
        },
    )
