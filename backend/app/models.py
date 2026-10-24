from datetime import date as dt_date, datetime as dt_datetime, timezone
from typing import Optional
from sqlmodel import Field, SQLModel


def utc_now() -> dt_datetime:
    return dt_datetime.now(timezone.utc)


class Product(SQLModel, table=True):
    """FMCG Product SKU master."""
    __tablename__ = "product"

    id: str = Field(primary_key=True, description="Product SKU ID (e.g. SKU-ATTA-05KG)")
    name: str = Field(description="Product display name")
    category: str = Field(description="Staples, Packaged Food, Personal Care, Home Care, Beverages")
    unit: str = Field(default="units", description="Base unit of measure: pack, bottle, pouch, bag, bar")
    case_pack: int = Field(default=1, description="Number of primary units in one carton")
    load_per_carton: float = Field(default=1.0, description="Volume or weight units per carton for lane capacity")
    unit_cost: float = Field(default=0.0, description="Production or procurement cost per unit in INR")
    unit_margin: float = Field(default=0.0, description="Gross margin per unit in INR")
    min_remaining_shelf_days: int = Field(default=21, description="Shelf life threshold (days)")
    is_simulated: bool = Field(default=True)


class Location(SQLModel, table=True):
    """Network node: Warehouse, Distributor, or Retail Store."""
    __tablename__ = "location"

    id: str = Field(primary_key=True, description="Location ID (e.g. W1, W2, D1, D2, S1, S2)")
    name: str = Field(description="Location name")
    type: str = Field(description="warehouse | distributor | store")
    city: Optional[str] = Field(default=None)
    state: Optional[str] = Field(default=None)
    is_simulated: bool = Field(default=True)


class SalesDaily(SQLModel, table=True):
    """Daily sales / consumption observations per product-destination."""
    __tablename__ = "sales_daily"

    id: Optional[int] = Field(default=None, primary_key=True)
    date: dt_date = Field(index=True)
    product_id: str = Field(foreign_key="product.id", index=True)
    location_id: str = Field(foreign_key="location.id", index=True)
    units: int = Field(description="Daily sales in units")
    is_simulated: bool = Field(default=True)


class InventorySnapshot(SQLModel, table=True):
    """Inventory snapshot at a location."""
    __tablename__ = "inventory_snapshot"

    id: Optional[int] = Field(default=None, primary_key=True)
    location_id: str = Field(foreign_key="location.id", index=True)
    product_id: str = Field(foreign_key="product.id", index=True)
    on_hand: int = Field(default=0, description="Current on-hand inventory in cartons")
    reserved: int = Field(default=0, description="Reserved inventory in cartons")
    in_transit: int = Field(default=0, description="In-transit inbound inventory in cartons")
    snapshot_date: dt_date = Field(index=True)
    is_simulated: bool = Field(default=True)


class Batch(SQLModel, table=True):
    """Stock batch stored at a location with expiration date."""
    __tablename__ = "batch"

    id: str = Field(primary_key=True, description="Batch ID (e.g. B-W1-P01-1)")
    location_id: str = Field(foreign_key="location.id", index=True)
    product_id: str = Field(foreign_key="product.id", index=True)
    quantity: int = Field(description="Quantity in whole cartons")
    expiry_date: dt_date = Field(index=True)
    batch_code: Optional[str] = Field(default=None)
    cost_per_carton: float = Field(default=0.0)
    is_simulated: bool = Field(default=True)


class Lane(SQLModel, table=True):
    """Transportation route connecting a source location to a destination location."""
    __tablename__ = "lane"

    id: str = Field(primary_key=True, description="Lane ID (e.g. LANE-W1-D1)")
    source_id: str = Field(foreign_key="location.id", index=True)
    destination_id: str = Field(foreign_key="location.id", index=True)
    lead_time_days: int = Field(description="Transit lead time in whole days (1-3 days)")
    cost_per_carton: float = Field(description="Freight cost per carton in INR")
    capacity_load: Optional[float] = Field(default=None, nullable=True, description="Max load capacity (nullable)")
    distance_km: Optional[float] = Field(default=0.0)
    is_simulated: bool = Field(default=True)


class PlanRun(SQLModel, table=True):
    """Execution record for inventory optimization run."""
    __tablename__ = "plan_run"

    id: str = Field(primary_key=True, description="Plan run ID")
    created_at: dt_datetime = Field(default_factory=utc_now)
    planning_date: dt_date
    status: str = Field(default="DRAFT", description="DRAFT | OPTIMIZED | APPROVED | REJECTED")
    total_cost: float = Field(default=0.0)
    total_cartons: int = Field(default=0)
    total_demand_cartons: int = Field(default=0)
    total_unmet_cartons: int = Field(default=0)
    total_unmet_safety_stock_cartons: int = Field(default=0, description="Unmet safety stock gap in cartons")
    counterfactuals_json: str = Field(default="[]", description="JSON serialized list of counterfactual reports")
    settings_snapshot_json: str = Field(default="{}")
    run_by_role: str = Field(default="planner")
    notes: Optional[str] = Field(default=None)
    is_simulated: bool = Field(default=True)


class PlanLine(SQLModel, table=True):
    """Individual allocation line decided by the optimizer or modified by a human."""
    __tablename__ = "plan_line"

    id: str = Field(primary_key=True, description="Plan line item ID")
    run_id: str = Field(foreign_key="plan_run.id", index=True)
    product_id: str = Field(foreign_key="product.id", index=True)
    source_id: str = Field(foreign_key="location.id", index=True)
    destination_id: str = Field(foreign_key="location.id", index=True)
    batch_id: Optional[str] = Field(default=None, foreign_key="batch.id", nullable=True)
    cartons: int = Field(description="Cartons allocated to ship")
    cost: float = Field(default=0.0, description="Computed shipping cost")
    arrival_date: dt_date = Field(description="Expected arrival date")
    flags_json: str = Field(default="{}", description="Flags JSON e.g. TIGHT_LANE, SHORT_SHELF_LIFE")
    explanation_json: str = Field(default="{}", description="Explanation JSON")
    status: str = Field(default="PROPOSED", description="PROPOSED | APPROVED | EDITED | REJECTED")
    is_simulated: bool = Field(default=True)


class ValidationIssue(SQLModel, table=True):
    """Discovered validation defects or data quality issues."""
    __tablename__ = "validation_issue"

    id: Optional[int] = Field(default=None, primary_key=True)
    type: str = Field(description="DUPLICATE_SKU | MIXED_UNITS | NEGATIVE_STOCK | INVALID_DATE | MISSING_SALES_DAYS | CONTRADICTORY_STOCK")
    entity: str = Field(description="Entity identifier or key e.g. Product:SKU-P01, InventorySnapshot:D1:P01")
    severity: str = Field(default="warning", description="critical | warning")
    status: str = Field(default="open", description="open | acknowledged | resolved")
    description: Optional[str] = Field(default=None)
    fix_first: bool = Field(default=False, description="Flagged as fix first if critical and open")
    created_at: dt_datetime = Field(default_factory=utc_now)
    is_simulated: bool = Field(default=True)


class DecisionLog(SQLModel, table=True):
    """Immutable audit log of human approval/edit/reject actions."""
    __tablename__ = "decision_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    plan_line_id: Optional[str] = Field(default=None, foreign_key="plan_line.id", nullable=True, index=True)
    actor_role: str = Field(description="planner | warehouse | reviewer | system")
    action: str = Field(description="APPROVE | EDIT | REJECT | OVERRIDE | SEED")
    old_value: Optional[str] = Field(default=None)
    new_value: Optional[str] = Field(default=None)
    note: Optional[str] = Field(default=None)
    timestamp: dt_datetime = Field(default_factory=utc_now, index=True)


class Settings(SQLModel, table=True):
    """System settings table with FMCG defaults."""
    __tablename__ = "settings"

    id: Optional[int] = Field(default=1, primary_key=True)
    H: int = Field(default=7, description="Planning horizon in days")
    z: float = Field(default=1.28, description="Safety stock z-score (~90% service level)")
    alpha: float = Field(default=0.25, description="Exponential smoothing factor")
    Gmax: int = Field(default=1, description="Maximum allowed lane lead-time gap in days")
    Eshort: int = Field(default=21, description="Minimum shelf life days remaining upon arrival")
    shrinkage: float = Field(default=0.5, description="Safety buffer / shrinkage factor")
    planner_reserve: int = Field(default=0, description="Reserved cartons per batch held back")
    epsilon: float = Field(default=0.001, description="Secondary tie-breaker penalty weight")
    solver_time_limit: float = Field(default=10.0, description="PuLP CBC solver time limit in seconds")
    updated_at: dt_datetime = Field(default_factory=utc_now)


class ForecastResult(SQLModel, table=True):
    """Forecast result cached per product-destination series."""
    __tablename__ = "forecast_result"

    id: Optional[int] = Field(default=None, primary_key=True)
    as_of_date: dt_date = Field(index=True)
    product_id: str = Field(foreign_key="product.id", index=True)
    location_id: str = Field(foreign_key="location.id", index=True)
    chosen_model: str = Field(description="seasonal_naive | moving_average_7 | exp_smoothing_dow | poisson_fallback")
    daily_forecast_json: str = Field(description="JSON list of daily forecasted units for horizon H")
    wape: float = Field(default=0.0, description="Pooled WAPE over three 7-day folds")
    bias: float = Field(default=0.0, description="Pooled forecast bias: sum(error) / sum(actual)")
    sigma: float = Field(default=0.0, description="Uncertainty standard deviation with group shrinkage or Poisson")
    warning: Optional[str] = Field(default=None, description="Warning if history < 60 days or marked insufficient")
    details_json: str = Field(default="{}", description="JSON string with candidate model WAPEs, fold errors, etc.")
    created_at: dt_datetime = Field(default_factory=utc_now)
    is_simulated: bool = Field(default=True)


# Backward-compatible model aliases
SettingsModel = Settings
AuditLog = DecisionLog
PlanAllocation = PlanLine
InventoryBatch = Batch
SalesRecord = SalesDaily
Warehouse = Location
Destination = Location
