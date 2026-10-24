from datetime import date as dt_date, datetime as dt_datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------
# Settings Schemas
# ---------------------------------------------------------
class SettingsBase(BaseModel):
    H: int = Field(default=7, ge=1, le=30, description="Planning horizon in days")
    z: float = Field(default=1.28, ge=0.0, le=4.0, description="Safety stock z-factor")
    alpha: float = Field(default=0.25, ge=0.01, le=1.0, description="Forecasting smoothing factor")
    Gmax: int = Field(default=1, ge=0, le=14, description="Max lane lead time gap (days)")
    Eshort: int = Field(default=21, ge=0, description="Min remaining shelf life days upon arrival")
    shrinkage: float = Field(default=0.5, ge=0.0, le=1.0, description="Shrinkage factor")
    planner_reserve: int = Field(default=0, ge=0, description="Cartons per batch held in reserve")
    epsilon: float = Field(default=0.001, ge=0.0, description="Tie breaker cost penalty weight")
    solver_time_limit: float = Field(default=10.0, ge=1.0, le=120.0, description="Solver time limit (seconds)")


class SettingsRead(SettingsBase):
    id: int
    updated_at: dt_datetime
    model_config = ConfigDict(from_attributes=True)


class SettingsUpdate(BaseModel):
    H: Optional[int] = Field(default=None, ge=1, le=30)
    z: Optional[float] = Field(default=None, ge=0.0, le=4.0)
    alpha: Optional[float] = Field(default=None, ge=0.01, le=1.0)
    Gmax: Optional[int] = Field(default=None, ge=0, le=14)
    Eshort: Optional[int] = Field(default=None, ge=0)
    shrinkage: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    planner_reserve: Optional[int] = Field(default=None, ge=0)
    epsilon: Optional[float] = Field(default=None, ge=0.0)
    solver_time_limit: Optional[float] = Field(default=None, ge=1.0, le=120.0)


# ---------------------------------------------------------
# Network Master Data Schemas
# ---------------------------------------------------------
class WarehouseBase(BaseModel):
    id: str
    code: str
    name: str
    city: str
    state: str
    zone: str
    capacity_cartons: int
    is_active: bool = True
    is_simulated: bool = True


class WarehouseRead(WarehouseBase):
    model_config = ConfigDict(from_attributes=True)


class DestinationBase(BaseModel):
    id: str
    code: str
    name: str
    city: str
    state: str
    zone: str
    tier: str = "Tier-1"
    current_stock_cartons: int = 0
    in_transit_cartons: int = 0
    is_active: bool = True
    is_simulated: bool = True


class DestinationRead(DestinationBase):
    model_config = ConfigDict(from_attributes=True)


class ProductBase(BaseModel):
    id: str
    sku_code: str
    name: str
    category: str
    case_pack: int = 1
    unit_price_inr: float = 0.0
    carton_cost_inr: float = 0.0
    shelf_life_days: int = 180
    is_active: bool = True
    is_simulated: bool = True


class ProductRead(ProductBase):
    model_config = ConfigDict(from_attributes=True)


class InventoryBatchBase(BaseModel):
    id: str
    warehouse_id: str
    product_id: str
    batch_code: str
    mfg_date: dt_date
    expiry_date: dt_date
    initial_cartons: int
    available_cartons: int
    reserved_cartons: int = 0
    cost_per_carton: float
    is_simulated: bool = True


class InventoryBatchRead(InventoryBatchBase):
    model_config = ConfigDict(from_attributes=True)


class LaneBase(BaseModel):
    id: str
    source_wh_id: str
    dest_id: str
    lead_time_days: int
    transit_cost_per_carton: float
    max_capacity_cartons: int
    min_dispatch_cartons: int = 1
    distance_km: float = 0.0
    is_active: bool = True
    is_simulated: bool = True


class LaneRead(LaneBase):
    model_config = ConfigDict(from_attributes=True)


class SalesRecordBase(BaseModel):
    date: dt_date
    destination_id: str
    product_id: str
    quantity_cartons: int
    quantity_units: int
    is_simulated: bool = True


class SalesRecordRead(SalesRecordBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------
# Planning & Allocation Schemas
# ---------------------------------------------------------
class PlanRunCreate(BaseModel):
    planning_date: Optional[dt_date] = None
    notes: Optional[str] = None


class PlanAllocationRead(BaseModel):
    id: str
    plan_id: str
    batch_id: str
    source_wh_id: str
    dest_id: str
    product_id: str
    allocated_cartons: int
    lead_time_days: int
    transit_cost: float
    status: str
    edited_cartons: Optional[int] = None
    reviewer_notes: Optional[str] = None
    actioned_by_role: Optional[str] = None
    actioned_at: Optional[dt_datetime] = None
    is_simulated: bool = True

    model_config = ConfigDict(from_attributes=True)


class PlanRunRead(BaseModel):
    id: str
    created_at: dt_datetime
    planning_date: dt_date
    status: str
    total_demand_cartons: int
    total_allocated_cartons: int
    total_unmet_cartons: int
    total_cost_inr: float
    settings_snapshot_json: str
    solver_status: str
    solve_time_seconds: float
    run_by_role: str
    notes: Optional[str]
    is_simulated: bool = True
    allocations: list[PlanAllocationRead] = []

    model_config = ConfigDict(from_attributes=True)


class AllocationActionRequest(BaseModel):
    action: str = Field(description="APPROVE, REJECT, or EDIT")
    edited_cartons: Optional[int] = Field(default=None, ge=0)
    notes: Optional[str] = None


class BulkAllocationActionRequest(BaseModel):
    allocation_ids: list[str]
    action: str = Field(description="APPROVE or REJECT")
    notes: Optional[str] = None


# ---------------------------------------------------------
# Audit Trail Schemas
# ---------------------------------------------------------
class AuditLogRead(BaseModel):
    id: int
    timestamp: dt_datetime
    role: str
    action: str
    entity_type: str
    entity_id: str
    details_json: str

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------
# Generic Status & Info Schemas
# ---------------------------------------------------------
class SystemStatusResponse(BaseModel):
    app_name: str
    version: str
    database_status: str
    total_warehouses: int
    total_destinations: int
    total_products: int
    total_batches: int
    total_lanes: int
    total_sales_records: int
    is_simulated: bool = True


# ---------------------------------------------------------
# Forecasting Schemas
# ---------------------------------------------------------
class ForecastSeriesResponse(BaseModel):
    product_id: str
    location_id: str
    as_of_date: dt_date
    chosen_model: str
    daily_forecast: list[float]
    wape: float
    bias: float
    sigma: float
    warning: Optional[str] = None
    details: Optional[dict[str, Any]] = None
    is_simulated: bool = True


class ForecastRunRequest(BaseModel):
    as_of: Optional[dt_date] = None
    horizon: Optional[int] = Field(default=None, ge=1, le=30)


class ForecastRunResponse(BaseModel):
    status: str = "success"
    as_of_date: dt_date
    total_series: int
    models_selected: dict[str, int]
    mean_wape: float
    mean_bias: float
    forecasts: list[ForecastSeriesResponse]
    is_simulated: bool = True

