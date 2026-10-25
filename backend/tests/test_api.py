from fastapi.testclient import TestClient


def test_api_health(client: TestClient):
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["is_simulated"] is True


def test_api_data_sample(client: TestClient):
    res = client.post(
        "/api/v1/data/sample",
        headers={"X-Role": "planner"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["counts"]["locations"] == 6
    assert data["counts"]["products"] == 24
    assert data["counts"]["lanes"] == 8
    assert data["counts"]["batches"] > 0
    assert data["counts"]["inventory_snapshots"] > 0
    assert data["counts"]["sales_daily"] > 0

    # Test master data endpoints
    loc_res = client.get("/api/v1/locations")
    assert loc_res.status_code == 200
    assert len(loc_res.json()) == 6

    prod_res = client.get("/api/v1/products")
    assert prod_res.status_code == 200
    assert len(prod_res.json()) == 24

    lane_res = client.get("/api/v1/lanes")
    assert lane_res.status_code == 200
    assert len(lane_res.json()) == 8

    # Test validation issues
    issues_res = client.get("/api/v1/validation-issues")
    assert issues_res.status_code == 200
