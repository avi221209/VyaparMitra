from fastapi.testclient import TestClient


def test_api_health(client: TestClient):
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["is_simulated"] is True


def test_api_data_seed_normal(client: TestClient):
    res = client.post(
        "/api/data/seed?variant=normal&seed=1&scenario=balanced",
        headers={"X-Role": "planner"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["variant"] == "normal"
    assert data["scenario"] == "balanced"
    assert data["counts"]["warehouses"] == 2
    assert data["counts"]["destinations"] == 4
    assert data["counts"]["lanes"] == 8
    assert data["counts"]["products"] == 24
    assert data["counts"]["sales_daily"] == 4 * 24 * 120
    assert data["counts"]["validation_issues"] == 0

    # Test master data endpoints
    loc_res = client.get("/api/locations")
    assert loc_res.status_code == 200
    assert len(loc_res.json()) == 6

    prod_res = client.get("/api/products")
    assert prod_res.status_code == 200
    assert len(prod_res.json()) == 24

    lane_res = client.get("/api/lanes")
    assert lane_res.status_code == 200
    assert len(lane_res.json()) == 8


def test_api_data_seed_defects(client: TestClient):
    res = client.post(
        "/api/data/seed?variant=defects&seed=1&scenario=balanced",
        headers={"X-Role": "planner"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["variant"] == "defects"
    assert 18 <= data["counts"]["validation_issues"] <= 22
    assert 18 <= len(data["defect_manifest"]) <= 22

    issues_res = client.get("/api/validation-issues")
    assert issues_res.status_code == 200
    assert len(issues_res.json()) >= 18


def test_api_data_seed_low_w1(client: TestClient):
    res = client.post(
        "/api/data/seed?variant=low_w1&seed=1&scenario=scarce",
        headers={"X-Role": "warehouse"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["variant"] == "low_w1"
    assert data["scenario"] == "scarce"
    assert data["stock_multiplier"] == 0.8
