import io
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from backend.app.models import (
    Batch,
    InventorySnapshot,
    Lane,
    Location,
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
from backend.scripts.measure_validation import evaluate_validation_metrics


def test_defect_file_finds_injected_defects(session: Session):
    """Verify that validation finds all 20 of 20 injected defects with >= 90% recall and <= 5% false flags."""
    metrics = evaluate_validation_metrics(seed=1)

    assert metrics["total_injected_defects"] == 20
    assert metrics["true_positives"] == 20
    assert metrics["false_negatives"] == 0
    assert metrics["recall"] == 1.0  # 100% recall
    assert metrics["passes_recall_threshold"] is True

    assert metrics["false_positives"] == 0
    assert metrics["false_flag_rate"] == 0.0  # 0% false flags
    assert metrics["passes_false_flag_threshold"] is True


def test_clean_file_produces_no_critical_issues(session: Session):
    """Verify that clean seeded data produces zero critical issues."""
    sim = FMCGSimulator(seed=1, scenario="balanced", variant="normal")
    sim.seed_database(session)

    validator = DataValidator(session)
    issues = validator.run_all(persist=True)

    critical_issues = [i for i in issues if i.severity == "critical"]
    assert len(critical_issues) == 0, f"Clean data should have no critical issues, found: {critical_issues}"


def test_csv_template_endpoint(client: TestClient):
    """Verify GET /api/v1/data/template/{name} returns downloadable CSVs with required columns."""
    template_expected_cols = {
        "products": ["id", "name", "category", "unit", "case_pack", "load_per_carton", "unit_cost", "unit_margin", "min_remaining_shelf_days"],
        "locations": ["id", "name", "type", "city", "state"],
        "sales": ["date", "product_id", "location_id", "units"],
        "inventory": ["location_id", "product_id", "on_hand", "reserved", "in_transit", "snapshot_date"],
        "batches": ["id", "location_id", "product_id", "quantity", "expiry_date", "batch_code", "cost_per_carton"],
        "lanes": ["id", "source_id", "destination_id", "lead_time_days", "cost_per_carton", "capacity_load", "distance_km"],
    }

    for name, expected_cols in template_expected_cols.items():
        res = client.get(f"/api/v1/data/template/{name}")
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/csv")
        content = res.text
        header_line = content.splitlines()[0]
        actual_cols = header_line.split(",")
        for col in expected_cols:
            assert col in actual_cols

    # Unknown template should 404
    bad_res = client.get("/api/v1/data/template/nonexistent_table")
    assert bad_res.status_code == 404


def test_upload_csv_with_missing_columns_names_them(client: TestClient):
    """Verify that uploading a CSV with missing mandatory columns returns 400 naming the missing columns."""
    # Defective CSV for products missing 'case_pack' and 'load_per_carton'
    defective_csv = (
        "id,name,category,unit,unit_cost,unit_margin,min_remaining_shelf_days\n"
        "SKU-TEST,Test Product,Staples,bag,100.0,20.0,30\n"
    )

    files = {"file": ("products.csv", io.BytesIO(defective_csv.encode("utf-8")), "text/csv")}
    data = {"table_name": "products"}

    res = client.post("/api/v1/data/upload", files=files, data=data, headers={"X-Role": "planner"})
    assert res.status_code == 400
    err_detail = res.json()["detail"]

    # Must name the missing columns
    assert "case_pack" in err_detail
    assert "load_per_carton" in err_detail


def test_upload_valid_csv_and_auto_validation(client: TestClient):
    """Verify that uploading a valid CSV succeeds and runs validation."""
    valid_csv = (
        "id,name,category,unit,case_pack,load_per_carton,unit_cost,unit_margin,min_remaining_shelf_days\n"
        "SKU-U01,Clean Atta 5kg,Staples,bag,4,20.0,180.0,40.0,30\n"
        "SKU-U02,Clean Rice 1kg,Staples,pouch,10,10.0,90.0,20.0,60\n"
    )

    files = {"file": ("products.csv", io.BytesIO(valid_csv.encode("utf-8")), "text/csv")}
    data = {"table_name": "products"}

    res = client.post("/api/v1/data/upload", files=files, data=data, headers={"X-Role": "planner"})
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["status"] == "success"
    assert res_data["rows_inserted"] == 2


def test_fix_first_gate_and_resolution_endpoints(client: TestClient, session: Session):
    """Test Fix First gate, issue grouping by severity, and resolve/acknowledge endpoints."""
    # Seed defect dataset directly to get issues
    sim = FMCGSimulator(seed=1, variant="defects", scenario="balanced")
    sim.seed_database(session)

    # 1. GET /api/v1/data/issues
    issues_res = client.get("/api/v1/data/issues")
    assert issues_res.status_code == 200
    summary = issues_res.json()
    assert summary["critical_count"] > 0
    assert summary["warning_count"] > 0
    assert "critical" in summary["by_severity"]
    assert "warning" in summary["by_severity"]

    # 2. Blocked planning entities
    blocked_res = client.get("/api/v1/data/blocked-planning-entities")
    assert blocked_res.status_code == 200
    blocked_data = blocked_res.json()
    assert blocked_data["blocked_entities_count"] > 0
    blocked_set = set(blocked_data["blocked_entities"])

    # 3. Resolve an issue
    open_critical_issues = [
        i for i in summary["by_severity"]["critical"] if i["status"] == "open"
    ]
    target_issue = open_critical_issues[0]
    issue_id = target_issue["id"]

    resolve_res = client.post(
        f"/api/v1/data/issues/{issue_id}/resolve",
        data={"note": "Correction verified"},
        headers={"X-Role": "reviewer"},
    )
    assert resolve_res.status_code == 200
    assert resolve_res.json()["issue"]["status"] == "resolved"
    assert resolve_res.json()["issue"]["fix_first"] is False

    # 4. Acknowledge another issue
    target_ack = open_critical_issues[1]
    ack_res = client.post(
        f"/api/v1/data/issues/{target_ack['id']}/acknowledge",
        data={"note": "Excluded from planning by reviewer"},
        headers={"X-Role": "reviewer"},
    )
    assert ack_res.status_code == 200
    assert ack_res.json()["issue"]["status"] == "acknowledged"


def test_upload_size_limit_rejection(client: TestClient, monkeypatch):
    """Verify that oversized uploads trigger HTTP 413 Request Entity Too Large."""
    from backend.app.config import settings
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_BYTES", 50)

    oversized_csv = "id,name,category,unit,case_pack,load_per_carton,unit_cost,unit_margin,min_remaining_shelf_days\n" * 5
    files = {"file": ("products.csv", io.BytesIO(oversized_csv.encode("utf-8")), "text/csv")}
    data = {"table_name": "products"}

    res = client.post("/api/v1/data/upload", files=files, data=data, headers={"X-Role": "planner"})
    assert res.status_code == 413
    assert "maximum upload size limit" in res.json()["detail"]


def test_upload_exact_failing_identifier_vyaparmitra_sample_inventory(client: TestClient, session: Session):
    """
    Direct regression test for observed bug:
    Dragging and dropping 'vyaparmitra_sample_inventory.csv' without table_name
    must resolve to 'inventory' entity and persist to the database.
    """
    csv_content = (
        "location_id,product_id,on_hand,reserved,in_transit,snapshot_date\n"
        "D1,SKU-P01,150,10,20,2026-10-24\n"
        "D2,SKU-P02,200,0,50,2026-10-24\n"
    )
    files = {"file": ("vyaparmitra_sample_inventory.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}

    # Note: No table_name sent, matching frontend drag-and-drop & file picker payload
    res = client.post("/api/v1/data/upload", files=files, headers={"X-Role": "planner"})
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
    data = res.json()
    assert data["status"] == "success"
    assert data["table"] == "inventory"
    assert data["rows_inserted"] == 2

    # Verify persistence in SQLite database
    persisted = list(session.exec(select(InventorySnapshot)).all())
    assert len(persisted) == 2
    sku_ids = {p.product_id for p in persisted}
    assert sku_ids == {"SKU-P01", "SKU-P02"}


def test_upload_all_canonical_entities_and_aliases_without_table_name(client: TestClient, session: Session):
    """Verify that all 6 canonical entities and their common aliases resolve and import correctly without table_name."""
    test_cases = [
        # (filename, csv_content, expected_table, expected_model)
        (
            "products.csv",
            "id,name,category,unit,case_pack,load_per_carton,unit_cost,unit_margin,min_remaining_shelf_days\n"
            "SKU-T1,Test Product 1,Staples,bag,4,1.0,100.0,20.0,30\n",
            "products",
            Product,
        ),
        (
            "sample_locations.csv",
            "id,name,type,city,state\n"
            "LOC-1,Test Warehouse,warehouse,Mumbai,Maharashtra\n",
            "locations",
            Location,
        ),
        (
            "daily_sales.csv",
            "date,product_id,location_id,units\n"
            "2026-10-24,SKU-T1,LOC-1,45\n",
            "sales",
            SalesDaily,
        ),
        (
            "inventory_batches.csv",
            "id,location_id,product_id,quantity,expiry_date,batch_code,cost_per_carton\n"
            "B-LOC1-T1-1,LOC-1,SKU-T1,100,2027-01-01,LOT-100,500.0\n",
            "batches",
            Batch,
        ),
        (
            "lanes.csv",
            "id,source_id,destination_id,lead_time_days,cost_per_carton,capacity_load,distance_km\n"
            "LANE-LOC1-LOC2,LOC-1,LOC-2,2,45.0,200.0,800.0\n",
            "lanes",
            Lane,
        ),
        (
            "snapshots.csv",
            "location_id,product_id,on_hand,reserved,in_transit,snapshot_date\n"
            "LOC-1,SKU-T1,80,5,15,2026-10-24\n",
            "inventory",
            InventorySnapshot,
        ),
    ]

    for filename, csv_content, expected_table, model_cls in test_cases:
        files = {"file": (filename, io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
        res = client.post("/api/v1/data/upload", files=files, headers={"X-Role": "planner"})
        assert res.status_code == 200, f"Failed for {filename}: {res.text}"
        data = res.json()
        assert data["table"] == expected_table
        assert data["rows_inserted"] == 1

        # Verify DB persistence
        records = list(session.exec(select(model_cls)).all())
        assert len(records) >= 1, f"Expected records persisted for {expected_table}"


def test_upload_column_signature_autodetection_generic_filename(client: TestClient, session: Session):
    """Verify that an arbitrary filename (e.g. export_data_20261025.csv) resolves to inventory via column signatures."""
    generic_csv = (
        "location_id,product_id,on_hand,reserved,in_transit,snapshot_date\n"
        "W1,SKU-P01,500,50,100,2026-10-24\n"
    )
    files = {"file": ("export_data_20261025.csv", io.BytesIO(generic_csv.encode("utf-8")), "text/csv")}
    res = client.post("/api/v1/data/upload", files=files, headers={"X-Role": "planner"})
    assert res.status_code == 200
    data = res.json()
    assert data["table"] == "inventory"
    assert data["rows_inserted"] == 1


def test_upload_empty_file_rejection(client: TestClient):
    """Verify that an empty file (0 bytes) returns HTTP 400 with a clear message."""
    files = {"file": ("empty.csv", io.BytesIO(b""), "text/csv")}
    res = client.post("/api/v1/data/upload", files=files, headers={"X-Role": "planner"})
    assert res.status_code == 400
    assert "empty (0 bytes)" in res.json()["detail"]


def test_upload_csv_with_no_data_rows_rejection(client: TestClient):
    """Verify that a CSV with headers but no data rows returns HTTP 400."""
    header_only_csv = "location_id,product_id,on_hand,reserved,in_transit,snapshot_date\n"
    files = {"file": ("inventory.csv", io.BytesIO(header_only_csv.encode("utf-8")), "text/csv")}
    res = client.post("/api/v1/data/upload", files=files, headers={"X-Role": "planner"})
    assert res.status_code == 400
    assert "contains no data rows" in res.json()["detail"]


def test_upload_unsupported_entity_rejection(client: TestClient):
    """Verify that genuinely unsupported entity names and schemas are rejected with HTTP 400 naming allowed entities."""
    unsupported_csv = (
        "customer_id,name,phone,email\n"
        "C01,John Doe,9876543210,john@example.com\n"
    )
    files = {"file": ("customer_master.csv", io.BytesIO(unsupported_csv.encode("utf-8")), "text/csv")}
    res = client.post("/api/v1/data/upload", files=files, headers={"X-Role": "planner"})
    assert res.status_code == 400
    detail = res.json()["detail"]
    assert "Unrecognized entity/table" in detail
    assert "customer_master" in detail
    assert "Allowed:" in detail


def test_upload_with_extra_columns_and_empty_id_safe_ingestion(client: TestClient, session: Session):
    """
    Verify that extra unknown columns and empty string 'id' (typical in exported CSVs)
    do not crash model construction and autoincrement ID works cleanly.
    """
    dirty_csv = (
        "location_id,product_id,on_hand,reserved,in_transit,snapshot_date,is_simulated,id,random_extra_column\n"
        "W1,SKU-P01,300,20,40,2026-10-24,True,,extra_data_value\n"
    )
    files = {"file": ("inventory.csv", io.BytesIO(dirty_csv.encode("utf-8")), "text/csv")}
    res = client.post("/api/v1/data/upload", files=files, headers={"X-Role": "planner"})
    assert res.status_code == 200
    data = res.json()
    assert data["rows_inserted"] == 1

    record = session.exec(select(InventorySnapshot)).first()
    assert record is not None
    assert record.id is not None
    assert record.on_hand == 300


def test_template_download_endpoints_and_aliases(client: TestClient):
    """Verify template download works for canonical entities and aliases, including vyaparmitra_sample_inventory."""
    # 1. Alias vyaparmitra_sample_inventory -> should return 200 with inventory columns
    res_inv = client.get("/api/v1/data/template/vyaparmitra_sample_inventory")
    assert res_inv.status_code == 200
    assert "location_id,product_id,on_hand" in res_inv.text

    # 2. Canonical products
    res_prod = client.get("/api/v1/data/template/products")
    assert res_prod.status_code == 200
    assert "case_pack" in res_prod.text

    # 3. Unsupported template -> 404
    res_unknown = client.get("/api/v1/data/template/unknown_entity_table")
    assert res_unknown.status_code == 404
    assert "not found" in res_unknown.json()["detail"]


