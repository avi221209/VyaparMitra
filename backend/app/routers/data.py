import io
from datetime import date, datetime
from typing import Any, Dict, List, Optional
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
    # Locations
    "location": "locations",
    "locations": "locations",
    "warehouse": "locations",
    "warehouses": "locations",
    "destination": "locations",
    "destinations": "locations",
    # Lanes
    "lane": "lanes",
    "lanes": "lanes",
    # Batches
    "batch": "batches",
    "batches": "batches",
    "inventory_batch": "batches",
    "inventory_batches": "batches",
    # Inventory snapshots
    "inventory": "inventory",
    "inventory_snapshot": "inventory",
    "inventory_snapshots": "inventory",
    "snapshots": "inventory",
    # Sales daily / sales history
    "sales": "sales",
    "sales_daily": "sales",
    "sales_history": "sales",
    "daily_sales": "sales",
}


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
    raw_name = name.lower().strip().replace(".csv", "")
    canonical_name = ENTITY_ALIASES.get(raw_name)
    if not canonical_name or canonical_name not in TEMPLATES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template '{name}' not found. Available entities: {sorted(list(TEMPLATES.keys()))} (Supported aliases: {sorted(list(ENTITY_ALIASES.keys()))})",
        )

    meta = TEMPLATES[canonical_name]
    header_line = ",".join(meta["columns"]) + "\n"
    content = header_line + meta["sample"]

    filename = f"{raw_name}_template.csv"
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
    Accepts CSV upload in exact template format.
    Validates that mandatory columns are present; missing columns are explicitly named.
    Inserts data and runs validation automatically.
    """
    # Deduce entity type from table_name or filename
    filename = file.filename or ""
    inferred_name = (table_name or filename).lower().replace(".csv", "").strip()

    # Map aliases (e.g. inventory_batches.csv -> batches, sales_history.csv -> sales)
    canonical_name = ENTITY_ALIASES.get(inferred_name)

    if not canonical_name or canonical_name not in TEMPLATES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unrecognized entity/table '{inferred_name}'. Allowed: {sorted(list(TEMPLATES.keys()))} (Supported aliases: {sorted(list(ENTITY_ALIASES.keys()))})",
        )

    meta = TEMPLATES[canonical_name]
    required_cols = set(meta["columns"])

    try:
        content_bytes = await file.read()
        if len(content_bytes) > settings.MAX_UPLOAD_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"File exceeds maximum upload size limit of {settings.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)} MB.",
            )
        df = pd.read_csv(io.BytesIO(content_bytes))
        if len(df) > settings.MAX_UPLOAD_ROWS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"CSV row count ({len(df)}) exceeds the maximum allowed limit of {settings.MAX_UPLOAD_ROWS} rows.",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse CSV file: {str(e)}",
        )

    # Check for missing mandatory columns
    actual_cols = {str(c).strip() for c in df.columns}
    missing_cols = sorted(list(required_cols - actual_cols))

    if missing_cols:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing mandatory column(s) for '{canonical_name}': {missing_cols}",
        )

    model_cls = meta["model"]

    # Delete existing rows for this table to replace cleanly
    existing_records = list(session.exec(select(model_cls)).all())
    for r in existing_records:
        session.delete(r)
    session.commit()

    # Parse and insert records
    inserted_count = 0
    records = df.to_dict(orient="records")
    for row in records:
        # Clean null values and convert date strings
        cleaned_row = {}
        for k, v in row.items():
            k_clean = str(k).strip()
            if pd.isna(v):
                cleaned_row[k_clean] = None
            elif "date" in k_clean and isinstance(v, str):
                try:
                    cleaned_row[k_clean] = date.fromisoformat(v.strip())
                except ValueError:
                    cleaned_row[k_clean] = v
            else:
                cleaned_row[k_clean] = v

        cleaned_row["is_simulated"] = True
        record_obj = model_cls(**cleaned_row)
        session.add(record_obj)
        inserted_count += 1

    session.commit()

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
        "rows_inserted": inserted_count,
        "validation_issues_detected": len(detected_issues),
        "is_simulated": True,
    }


# -------------------------------------------------------------------
# 3. Load Sample Dataset from data/sample/
# -------------------------------------------------------------------
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
