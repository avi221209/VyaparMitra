import io
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from backend.app.models import Product, ValidationIssue
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

