import io
import re
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile, status
from fastapi.responses import PlainTextResponse
import pandas as pd
from pathlib import Path
from sqlmodel import Session, select, delete

from backend.app.config import settings
from backend.app.db import get_session
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
    ValidationIssue,
)
from backend.app.services.simulator import FMCGSimulator
from backend.app.services.validation import (
    DataValidator,
    acknowledge_validation_issue,
    get_blocked_entities_for_planning,
    get_issues_summary,
    resolve_validation_issue,
)

router = APIRouter(prefix="/api/v1/data", tags=["Data & Validation"])


TEMPLATES: Dict[str, Dict[str, Any]] = {
    "products": {
        "columns": [
            "id",
            "name",
            "category",
            "unit",
            "case_pack",
            "load_per_carton",
            "unit_cost",
            "unit_margin",
            "min_remaining_shelf_days",
        ],
        "sample": "SKU-P01,Chakki Fresh Atta 5kg,Staples,bag,4,20.0,180.0,40.0,21\n",
        "model": Product,
    },
    "locations": {
        "columns": ["id", "name", "type", "city", "state"],
        "sample": "W1,North Central Hub,warehouse,Gurgaon,Haryana\nD1,Metro Distributor East,distributor,Kolkata,West Bengal\n",
        "model": Location,
    },
    "sales": {
        "columns": ["date", "product_id", "location_id", "units"],
        "sample": "2026-10-24,SKU-P01,D1,48\n",
        "model": SalesDaily,
    },
    "inventory": {
        "columns": ["location_id", "product_id", "on_hand", "reserved", "in_transit", "snapshot_date"],
        "sample": "D1,SKU-P01,60,10,25,2026-10-24\n",
        "model": InventorySnapshot,
    },
    "batches": {
        "columns": ["id", "location_id", "product_id", "quantity", "expiry_date", "batch_code", "cost_per_carton"],
        "sample": "B-W1-P01-1,W1,SKU-P01,250,2027-01-01,LOT-001,720.0\n",
        "model": Batch,
    },
    "lanes": {
        "columns": ["id", "source_id", "destination_id", "lead_time_days", "cost_per_carton", "capacity_load", "distance_km"],
        "sample": "LANE-W1-D1,W1,D1,3,55.0,500.0,1500.0\n",
        "model": Lane,
    },
}


ENTITY_ALIASES: Dict[str, str] = {
    # Products
    "product": "products",
    "products": "products",
    "product_master": "products",
    "products_master": "products",
    "sku": "products",
    "skus": "products",
    "item": "products",
    "items": "products",
    "catalog": "products",
    "product_catalog": "products",
    "sample_products": "products",
    "sample_product": "products",
    "vyaparmitra_products": "products",
    "vyaparmitra_product": "products",
    "vyaparmitra_sample_products": "products",
    "vyaparmitra_sample_product": "products",

    # Locations
    "location": "locations",
    "locations": "locations",
    "location_master": "locations",
    "locations_master": "locations",
    "warehouse": "locations",
    "warehouses": "locations",
    "destination": "locations",
    "destinations": "locations",
    "store": "locations",
    "stores": "locations",
    "depot": "locations",
    "depots": "locations",
    "node": "locations",
    "nodes": "locations",
    "sample_locations": "locations",
    "sample_location": "locations",
    "vyaparmitra_locations": "locations",
    "vyaparmitra_location": "locations",
    "vyaparmitra_sample_locations": "locations",
    "vyaparmitra_sample_location": "locations",

    # Lanes
    "lane": "lanes",
    "lanes": "lanes",
    "route": "lanes",
    "routes": "lanes",
    "transit": "lanes",
    "shipping_lane": "lanes",
    "shipping_lanes": "lanes",
    "freight": "lanes",
    "sample_lanes": "lanes",
    "sample_lane": "lanes",
    "vyaparmitra_lanes": "lanes",
    "vyaparmitra_lane": "lanes",
    "vyaparmitra_sample_lanes": "lanes",
    "vyaparmitra_sample_lane": "lanes",

    # Batches
    "batch": "batches",
    "batches": "batches",
    "inventory_batch": "batches",
    "inventory_batches": "batches",
    "lot": "batches",
    "lots": "batches",
    "expiry": "batches",
    "expiries": "batches",
    "sample_batches": "batches",
    "sample_batch": "batches",
    "vyaparmitra_batches": "batches",
    "vyaparmitra_batch": "batches",
    "vyaparmitra_sample_batches": "batches",
    "vyaparmitra_sample_batch": "batches",

    # Inventory snapshots
    "inventory": "inventory",
    "inventory_snapshot": "inventory",
    "inventory_snapshots": "inventory",
    "snapshot": "inventory",
    "snapshots": "inventory",
    "stock": "inventory",
    "stocks": "inventory",
    "stock_level": "inventory",
    "stock_levels": "inventory",
    "on_hand": "inventory",
    "sample_inventory": "inventory",
    "sample_inventory_snapshot": "inventory",
    "sample_inventory_snapshots": "inventory",
    "vyaparmitra_inventory": "inventory",
    "vyaparmitra_inventory_snapshot": "inventory",
    "vyaparmitra_inventory_snapshots": "inventory",
    "vyaparmitra_sample_inventory": "inventory",
    "vyaparmitra_sample_inventory_snapshot": "inventory",
    "vyaparmitra_sample_inventory_snapshots": "inventory",

    # Sales daily / sales history
    "sales": "sales",
    "sale": "sales",
    "sales_daily": "sales",
    "sales_history": "sales",
    "daily_sales": "sales",
    "demand": "sales",
    "consumption": "sales",
    "sample_sales": "sales",
    "sample_sales_daily": "sales",
    "vyaparmitra_sales": "sales",
    "vyaparmitra_sales_daily": "sales",
    "vyaparmitra_sample_sales": "sales",
    "vyaparmitra_sample_sales_daily": "sales",
}


def resolve_canonical_entity(
    name: Optional[str] = None,
    columns: Optional[Iterable[str]] = None,
) -> Optional[str]:
    """
    Resolve a canonical entity name ('products', 'locations', 'sales', 'inventory', 'batches', 'lanes')
    from either a candidate name (table_name or filename) and/or CSV columns.
    """
    if name:
        raw = str(name).lower().strip()
        for ext in [".csv", ".tsv", ".txt"]:
            if raw.endswith(ext):
                raw = raw[: -len(ext)]
        raw = raw.strip()

        # 1. Direct alias match
        if raw in ENTITY_ALIASES:
            return ENTITY_ALIASES[raw]

        # 2. Strip standard prefixes/suffixes
        stripped = raw
        for prefix in ["vyaparmitra_sample_", "vyaparmitra_", "sample_", "fmcg_", "test_", "demo_"]:
            if stripped.startswith(prefix):
                stripped = stripped[len(prefix):]
                break
        for suffix in ["_template", "_sample", "_export", "_data", "_dataset", "_file", "_records", "_master", "_list"]:
            if stripped.endswith(suffix):
                stripped = stripped[:-len(suffix)]
                break
        if stripped in ENTITY_ALIASES:
            return ENTITY_ALIASES[stripped]

        # 3. Token check
        tokens = [t for t in re.split(r"[_\-\s\.]+", raw) if t]
        for token in reversed(tokens):
            if token in ENTITY_ALIASES:
                return ENTITY_ALIASES[token]

    # 4. Column signature inspection
    if columns is not None:
        cols = {str(c).lower().strip() for c in columns}

        # Lanes: requires source_id and destination_id
        if {"source_id", "destination_id"}.issubset(cols):
            return "lanes"

        # Batches: requires expiry_date and (batch_code or quantity)
        if "expiry_date" in cols and ("batch_code" in cols or "quantity" in cols):
            return "batches"

        # Inventory: requires location_id, product_id, and (on_hand or snapshot_date or reserved or in_transit)
        if {"product_id", "location_id"}.issubset(cols) and ("on_hand" in cols or "snapshot_date" in cols or "reserved" in cols or "in_transit" in cols):
            return "inventory"

        # Sales: requires units and date
        if {"units", "date"}.issubset(cols) and ("product_id" in cols or "location_id" in cols):
            return "sales"

        # Products: case_pack or load_per_carton or unit_margin or min_remaining_shelf_days
        product_indicators = {"case_pack", "load_per_carton", "unit_margin", "min_remaining_shelf_days", "category"}
        if len(product_indicators.intersection(cols)) >= 2 or "case_pack" in cols:
            return "products"

        # Locations: requires type and (city or state or name) without product_id
        if "type" in cols and ("city" in cols or "state" in cols or "name" in cols) and "product_id" not in cols:
            return "locations"

    return None


def get_current_role(x_role: str = Header(default="planner")) -> str:
    valid_roles = {"planner", "warehouse", "reviewer", "system"}
    cleaned = x_role.lower().strip()
    if cleaned not in valid_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Invalid X-Role '{x_role}'. Allowed: {sorted(list(valid_roles))}",
        )
    return cleaned


# -------------------------------------------------------------------
# 1. Template Download Endpoint
# -------------------------------------------------------------------
@router.get("/template/{name}", response_class=PlainTextResponse)
def get_csv_template(name: str):
    """Download clean CSV template for a data entity with alias support."""
    canonical_name = resolve_canonical_entity(name=name)
    if not canonical_name or canonical_name not in TEMPLATES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template '{name}' not found. Available entities: {sorted(list(TEMPLATES.keys()))} (Supported aliases: {sorted(list(ENTITY_ALIASES.keys()))})",
        )

    meta = TEMPLATES[canonical_name]
    header_line = ",".join(meta["columns"]) + "\n"
    content = header_line + meta["sample"]

    clean_name = name.lower().strip().replace(".csv", "")
    filename = f"{clean_name}_template.csv"
    return PlainTextResponse(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# -------------------------------------------------------------------
# 2. CSV Upload & Ingestion Endpoint
# -------------------------------------------------------------------
@router.post("/upload")
async def upload_csv_file(
    file: UploadFile = File(...),
    table_name: Optional[str] = Form(default=None),
    session: Session = Depends(get_session),
    role: str = Depends(get_current_role),
):
    """
    Accepts CSV upload via drag-and-drop or file picker.
    Resolves entity using table_name, file name, and CSV column signatures.
    Validates mandatory columns, filters safe model fields, handles empty values,
    inserts records, and automatically triggers validation.
    """
    filename = file.filename or ""

    try:
        content_bytes = await file.read()
        if len(content_bytes) > settings.MAX_UPLOAD_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"File exceeds maximum upload size limit of {settings.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)} MB.",
            )
        if not content_bytes or len(content_bytes.strip()) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty (0 bytes). Please upload a valid CSV file.",
            )

        df = pd.read_csv(io.BytesIO(content_bytes))
        if len(df) > settings.MAX_UPLOAD_ROWS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"CSV row count ({len(df)}) exceeds the maximum allowed limit of {settings.MAX_UPLOAD_ROWS} rows.",
            )
        if len(df) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="CSV file contains no data rows.",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse CSV file: {str(e)}",
        )

    actual_cols = {str(c).strip() for c in df.columns}

    # Resolve entity canonical name from candidate name or column signature
    candidate_identifier = table_name or filename
    canonical_name = resolve_canonical_entity(name=candidate_identifier, columns=actual_cols)

    if not canonical_name or canonical_name not in TEMPLATES:
        inferred_label = candidate_identifier.lower().replace(".csv", "").strip() or "unknown"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unrecognized entity/table '{inferred_label}'. "
                f"Allowed: {sorted(list(TEMPLATES.keys()))}. "
                f"Could not identify supported entity from filename or columns {sorted(list(actual_cols))}."
            ),
        )

    meta = TEMPLATES[canonical_name]
    required_cols = set(meta["columns"])
    missing_cols = sorted(list(required_cols - actual_cols))

    if missing_cols:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing mandatory column(s) for '{canonical_name}': {missing_cols}",
        )

    model_cls = meta["model"]
    model_fields = model_cls.model_fields

    # Delete existing rows for this table to replace cleanly
    existing_records = list(session.exec(select(model_cls)).all())
    for r in existing_records:
        session.delete(r)
    session.commit()

    # Parse and insert records
    inserted_count = 0
    records = df.to_dict(orient="records")
    for row_idx, row in enumerate(records, start=1):
        cleaned_row = {}
        for k, v in row.items():
            k_clean = str(k).strip()
            if k_clean not in model_fields:
                continue
            if pd.isna(v):
                cleaned_row[k_clean] = None
            elif "date" in k_clean and isinstance(v, str):
                try:
                    cleaned_row[k_clean] = date.fromisoformat(v.strip())
                except ValueError:
                    cleaned_row[k_clean] = v
            else:
                cleaned_row[k_clean] = v

        # Handle autoincrement ID for models where id is Optional[int] (e.g. SalesDaily, InventorySnapshot)
        if "id" in cleaned_row:
            val = cleaned_row["id"]
            if val is None or val == "" or pd.isna(val):
                del cleaned_row["id"]
            else:
                try:
                    cleaned_row["id"] = int(val)
                except (ValueError, TypeError):
                    field_info = model_fields["id"]
                    if field_info.annotation != str:
                        del cleaned_row["id"]

        cleaned_row["is_simulated"] = True
        try:
            record_obj = model_cls(**cleaned_row)
            session.add(record_obj)
            inserted_count += 1
        except Exception as err:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Validation error in row {row_idx} for '{canonical_name}': {str(err)}",
            )

    try:
        session.commit()
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Database integrity error inserting '{canonical_name}': {str(e)}",
        )

    # Automatically re-run validation
    validator = DataValidator(session)
    detected_issues = validator.run_all(persist=True)

    # Log action to DecisionLog
    log = DecisionLog(
        actor_role=role,
        action="UPLOAD_CSV",
        note=f"Uploaded {inserted_count} rows for '{canonical_name}' from {filename}. Detected {len(detected_issues)} issues.",
    )
    session.add(log)
    session.commit()

    from backend.app.routers.dashboard import invalidate_dashboard_cache
    invalidate_dashboard_cache()

    return {
        "status": "success",
        "table": canonical_name,
        "entity": canonical_name,
        "rows_inserted": inserted_count,
        "validation_issues_detected": len(detected_issues),
        "message": f"Successfully ingested {inserted_count} rows for '{canonical_name}'. Detected {len(detected_issues)} validation issues.",
        "is_simulated": True,
    }


# -------------------------------------------------------------------
# 3. Load Sample Dataset & Seed Simulator
# -------------------------------------------------------------------
@router.post("/seed")
def seed_dataset(
    variant: str = Query(default="normal"),
    scenario: str = Query(default="balanced"),
    seed: int = Query(default=1),
    session: Session = Depends(get_session),
    role: str = Depends(get_current_role),
) -> dict:
    """Seed database with specified variant ('normal' or 'defects') and scenario."""
    sim = FMCGSimulator(seed=seed, variant=variant, scenario=scenario)
    res = sim.seed_database(session)
    from backend.app.routers.dashboard import invalidate_dashboard_cache
    invalidate_dashboard_cache()
    return res


@router.post("/sample")
def load_sample_dataset(
    session: Session = Depends(get_session),
    role: str = Depends(get_current_role),
) -> dict:
    """
    Load bundled regional FMCG sample dataset directly from data/sample/ CSV files.
    """
    sample_dir = Path("data/sample")
    if not sample_dir.exists():
        sample_dir = Path(__file__).resolve().parents[3] / "data" / "sample"
    if not sample_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bundled sample data directory 'data/sample' not found.",
        )

    # Clear existing planning and data records
    for model in [ValidationIssue, PlanLine, PlanRun, Batch, InventorySnapshot, SalesDaily, Lane, Product, Location]:
        session.exec(delete(model))
    session.commit()

    # 1. Locations
    loc_file = sample_dir / "locations.csv"
    if loc_file.exists():
        df_loc = pd.read_csv(loc_file)
        for _, row in df_loc.iterrows():
            session.add(Location(
                id=str(row["id"]),
                name=str(row["name"]),
                type=str(row["type"]),
                city=str(row["city"]),
                state=str(row["state"]),
                is_simulated=True,
            ))
        session.commit()

    # 2. Products
    prod_file = sample_dir / "products.csv"
    if prod_file.exists():
        df_prod = pd.read_csv(prod_file)
        for _, row in df_prod.iterrows():
            session.add(Product(
                id=str(row["id"]),
                name=str(row["name"]),
                category=str(row["category"]),
                unit=str(row["unit"]),
                case_pack=int(row["case_pack"]),
                load_per_carton=float(row.get("load_per_carton", 1.0)),
                unit_cost=float(row.get("unit_cost", 10.0)),
                unit_margin=float(row.get("unit_margin", 2.0)),
                min_remaining_shelf_days=int(row.get("min_remaining_shelf_days", 21)),
                is_simulated=True,
            ))
        session.commit()

    # 3. Lanes
    lanes_file = sample_dir / "lanes.csv"
    if lanes_file.exists():
        df_lanes = pd.read_csv(lanes_file)
        for _, row in df_lanes.iterrows():
            session.add(Lane(
                id=str(row["id"]),
                source_id=str(row["source_id"]),
                destination_id=str(row["destination_id"]),
                lead_time_days=int(row["lead_time_days"]),
                cost_per_carton=float(row["cost_per_carton"]),
                capacity_load=float(row["capacity_load"]) if pd.notna(row.get("capacity_load")) else None,
                distance_km=float(row["distance_km"]) if pd.notna(row.get("distance_km")) else None,
                is_simulated=True,
            ))
        session.commit()

    # 4. Batches
    batches_file = sample_dir / "batches.csv"
    if batches_file.exists():
        df_batches = pd.read_csv(batches_file)
        for _, row in df_batches.iterrows():
            exp_date = datetime.strptime(str(row["expiry_date"]), "%Y-%m-%d").date()
            session.add(Batch(
                id=str(row["id"]),
                location_id=str(row["location_id"]),
                product_id=str(row["product_id"]),
                quantity=int(row["quantity"]),
                expiry_date=exp_date,
                batch_code=str(row.get("batch_code", "")),
                cost_per_carton=float(row.get("cost_per_carton", 100.0)),
                is_simulated=True,
            ))
        session.commit()

    # 5. Inventory Snapshots
    snap_file = sample_dir / "inventory_snapshots.csv"
    if snap_file.exists():
        df_snap = pd.read_csv(snap_file)
        for _, row in df_snap.iterrows():
            s_date = datetime.strptime(str(row["snapshot_date"]), "%Y-%m-%d").date() if pd.notna(row.get("snapshot_date")) else date(2026, 10, 24)
            session.add(InventorySnapshot(
                location_id=str(row["location_id"]),
                product_id=str(row["product_id"]),
                on_hand=int(row["on_hand"]),
                reserved=int(row.get("reserved", 0)),
                in_transit=int(row.get("in_transit", 0)),
                snapshot_date=s_date,
                is_simulated=True,
            ))
        session.commit()

    # 6. Sales Daily
    sales_file = sample_dir / "sales_daily.csv"
    if sales_file.exists():
        df_sales = pd.read_csv(sales_file)
        for _, row in df_sales.iterrows():
            s_date = datetime.strptime(str(row["date"]), "%Y-%m-%d").date()
            session.add(SalesDaily(
                date=s_date,
                product_id=str(row["product_id"]),
                location_id=str(row["location_id"]),
                units=int(row["units"]),
                is_simulated=True,
            ))
        session.commit()

    # Run data validation
    validator = DataValidator(session)
    issues = validator.run_all(persist=True)

    # Log to decision log
    session.add(DecisionLog(
        action="LOAD_SAMPLE_DATA",
        actor_role=role,
        entity="System",
        note="Loaded bundled sample dataset from data/sample/",
        diff={"source": "data/sample/"},
    ))
    session.commit()

    from backend.app.routers.dashboard import invalidate_dashboard_cache
    invalidate_dashboard_cache()

    return {
        "status": "success",
        "message": "Sample data loaded successfully from data/sample/",
        "is_simulated": True,
        "counts": {
            "locations": len(session.exec(select(Location)).all()),
            "products": len(session.exec(select(Product)).all()),
            "lanes": len(session.exec(select(Lane)).all()),
            "batches": len(session.exec(select(Batch)).all()),
            "inventory_snapshots": len(session.exec(select(InventorySnapshot)).all()),
            "sales_daily": len(session.exec(select(SalesDaily)).all()),
            "validation_issues": len(issues),
        },
    }


# -------------------------------------------------------------------
# 4. Validation Issues Endpoints
# -------------------------------------------------------------------
@router.get("/issues")
def list_validation_issues(session: Session = Depends(get_session)):
    """Retrieve all validation issues grouped by severity with counts."""
    return get_issues_summary(session)


@router.post("/issues/{issue_id}/resolve")
def resolve_issue_endpoint(
    issue_id: int,
    note: Optional[str] = Form(default=None),
    session: Session = Depends(get_session),
    role: str = Depends(get_current_role),
):
    """
    Resolve/correct a validation issue.
    Unblocks the record for planning if previously fix-first.
    """
    try:
        updated = resolve_validation_issue(session, issue_id, actor_role=role, note=note)
        return {
            "status": "success",
            "message": f"Validation issue #{issue_id} resolved",
            "issue": updated.model_dump(),
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/issues/{issue_id}/acknowledge")
def acknowledge_issue_endpoint(
    issue_id: int,
    note: Optional[str] = Form(default=None),
    session: Session = Depends(get_session),
    role: str = Depends(get_current_role),
):
    """
    Acknowledge a validation issue.
    Explicitly excludes the affected record from planning.
    """
    try:
        updated = acknowledge_validation_issue(session, issue_id, actor_role=role, note=note)
        return {
            "status": "success",
            "message": f"Validation issue #{issue_id} acknowledged and excluded from planning",
            "issue": updated.model_dump(),
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/blocked-planning-entities")
def list_blocked_planning_entities(session: Session = Depends(get_session)):
    """Return all entities currently blocked from planning by the Fix First gate."""
    blocked = get_blocked_entities_for_planning(session)
    return {
        "blocked_entities_count": len(blocked),
        "blocked_entities": sorted(list(blocked)),
        "is_simulated": True,
    }
