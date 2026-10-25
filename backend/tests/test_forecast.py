"""
Unit and Integration Tests for Demand Forecasting Service
Distribution Planning and Inventory Optimization Engine
"""

from datetime import date as dt_date, timedelta
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from backend.app.db import engine, init_db
from backend.app.main import app
from backend.app.models import ForecastResult, Location, Product, SalesDaily
from backend.app.services.forecast import (
    compute_bias,
    compute_wape,
    evaluate_rolling_origin,
    forecast_exp_smoothing_dow,
    forecast_moving_average_7,
    forecast_poisson_fallback,
    forecast_seasonal_naive,
    is_zero_heavy,
    ForecastService,
)
from backend.app.services.simulator import FMCGSimulator


@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    """Ensure database has tables and seeded data."""
    init_db()
    with Session(engine) as session:
        has_sales = session.exec(select(SalesDaily)).first()
        if not has_sales:
            sim = FMCGSimulator(seed=42)
            sim.seed_database(session)


# =====================================================================
# 1. WAPE Hand-Computation on Tiny Series
# =====================================================================
def test_wape_hand_computed_on_tiny_series():
    """
    Test WAPE on a hand-computed tiny series:
      actual:   [10, 20, 30]
      forecast: [12, 18, 33]
      |errors|: [ 2,  2,  3] -> sum = 7
      actual sum: 60
      WAPE = 7 / 60 = 0.1166667
      bias = (10-12 + 20-18 + 30-33) / 60 = -3 / 60 = -0.05
    """
    actual = [10.0, 20.0, 30.0]
    forecast = [12.0, 18.0, 33.0]

    wape = compute_wape(actual, forecast)
    bias = compute_bias(actual, forecast)

    expected_wape = 7.0 / 60.0
    expected_bias = -3.0 / 60.0

    assert wape == pytest.approx(expected_wape, abs=1e-5)
    assert bias == pytest.approx(expected_bias, abs=1e-5)

    # Edge cases
    assert compute_wape([0.0, 0.0], [0.0, 0.0]) == 0.0
    assert compute_bias([0.0, 0.0], [0.0, 0.0]) == 0.0
    assert compute_wape([0.0], [5.0]) == 1.0


# =====================================================================
# 2. Strict No-Leakage Guarantee
# =====================================================================
def test_no_leakage_guarantee():
    """
    Changing or inserting data strictly on or after as_of date
    MUST NOT alter the forecast, WAPE, bias, or sigma in any way.
    """
    as_of = dt_date(2026, 10, 1)
    base_dates = [as_of - timedelta(days=i) for i in range(40, 0, -1)]

    # Clean pre-as_of historical data
    rng = np.random.default_rng(123)
    clean_values = [float(val) for val in rng.integers(10, 50, size=len(base_dates))]
    series_original = pd.Series(clean_values, index=base_dates)

    # Run forecasts before any future tampering
    f_sn_orig = forecast_seasonal_naive(series_original, as_of=as_of, horizon=7)
    f_ma_orig = forecast_moving_average_7(series_original, as_of=as_of, horizon=7)
    f_es_orig = forecast_exp_smoothing_dow(series_original, as_of=as_of, horizon=7)
    eval_orig = evaluate_rolling_origin(series_original, as_of=as_of)

    # Now create a tampered series with massive anomalies AFTER or ON as_of
    tampered_dates = list(base_dates) + [as_of, as_of + timedelta(days=1), as_of + timedelta(days=5)]
    tampered_values = list(clean_values) + [999999.0, 888888.0, 777777.0]
    series_tampered = pd.Series(tampered_values, index=tampered_dates)

    # Run forecasts after future tampering
    f_sn_tamp = forecast_seasonal_naive(series_tampered, as_of=as_of, horizon=7)
    f_ma_tamp = forecast_moving_average_7(series_tampered, as_of=as_of, horizon=7)
    f_es_tamp = forecast_exp_smoothing_dow(series_tampered, as_of=as_of, horizon=7)
    eval_tamp = evaluate_rolling_origin(series_tampered, as_of=as_of)

    # All outputs must be 100% strictly identical
    assert f_sn_orig == f_sn_tamp
    assert f_ma_orig == f_ma_tamp
    assert f_es_orig == f_es_tamp
    assert eval_orig["chosen_model"] == eval_tamp["chosen_model"]
    assert eval_orig["chosen_wape"] == eval_tamp["chosen_wape"]
    assert eval_orig["chosen_bias"] == eval_tamp["chosen_bias"]
    assert eval_orig["chosen_sigma_series"] == eval_tamp["chosen_sigma_series"]


# =====================================================================
# 3. Selection Picks Seasonal-Naive on Perfectly Weekly Series
# =====================================================================
def test_selection_picks_seasonal_naive_on_perfect_weekly_series():
    """
    When data follows a strict repeating 7-day pattern, seasonal-naive has 0 error.
    Rolling-origin selection must pick seasonal_naive with WAPE = 0.0.
    """
    as_of = dt_date(2026, 10, 24)
    # Repeating 7-day weekly profile: Mon=10, Tue=15, Wed=20, Thu=25, Fri=30, Sat=50, Sun=45
    weekly_pattern = [10.0, 15.0, 20.0, 25.0, 30.0, 50.0, 45.0]

    # Generate 10 weeks of history (70 days) strictly before as_of
    dates: list[dt_date] = []
    values: list[float] = []
    for day_offset in range(70, 0, -1):
        d = as_of - timedelta(days=day_offset)
        dates.append(d)
        values.append(weekly_pattern[d.weekday()])

    series = pd.Series(values, index=dates)

    eval_result = evaluate_rolling_origin(series, as_of=as_of)

    assert eval_result["chosen_model"] == "seasonal_naive"
    assert eval_result["chosen_wape"] == pytest.approx(0.0, abs=1e-5)
    assert eval_result["chosen_bias"] == pytest.approx(0.0, abs=1e-5)
    assert eval_result["chosen_sigma_series"] == pytest.approx(0.0, abs=1e-5)


# =====================================================================
# 4. Zero-Heavy Series Uses Poisson Fallback
# =====================================================================
def test_zero_heavy_series_uses_poisson_fallback():
    """
    Series with > 50% zeros in 28-day window uses Poisson fallback:
      forecast = 28-day flat mean, sigma = sqrt(mean).
    """
    as_of = dt_date(2026, 10, 24)
    dates_28 = [as_of - timedelta(days=i) for i in range(28, 0, -1)]

    # 20 zero days, 8 days with 7 units each = 56 total units
    # mean = 56 / 28 = 2.0
    # zero ratio = 20 / 28 = 71.4% > 50%
    vals = [0.0] * 20 + [7.0] * 8
    series = pd.Series(vals, index=dates_28)

    assert is_zero_heavy(series, as_of) is True

    f_vec, sigma = forecast_poisson_fallback(series, as_of=as_of, horizon=7)
    expected_mean = 56.0 / 28.0
    expected_sigma = float(np.sqrt(expected_mean))

    assert f_vec == [pytest.approx(expected_mean, abs=1e-5)] * 7
    assert sigma == pytest.approx(expected_sigma, abs=1e-5)


from backend.app.services.simulator import FMCGSimulator


# =====================================================================
# 5. Integration: API Endpoints POST /run and GET /{product}/{location}
# =====================================================================
def test_forecast_api_run_and_get(client: TestClient, session: Session):
    """Test POST /api/forecast/run and GET /api/forecast/{product}/{location}."""
    sim = FMCGSimulator(seed=1, variant="normal", scenario="balanced")
    sim.seed_database(session)

    # 1. Run forecast engine for all series
    run_resp = client.post("/api/v1/forecast/run")
    assert run_resp.status_code == 200
    run_data = run_resp.json()

    assert run_data["status"] == "success"
    assert run_data["total_series"] > 0
    assert "models_selected" in run_data
    assert len(run_data["models_selected"]) >= 1
    assert "mean_wape" in run_data
    assert "mean_bias" in run_data
    assert len(run_data["forecasts"]) == run_data["total_series"]

    sample_item = run_data["forecasts"][0]
    assert "product_id" in sample_item
    assert "location_id" in sample_item
    assert "chosen_model" in sample_item
    assert len(sample_item["daily_forecast"]) == 7
    assert sample_item["sigma"] >= 0.0

    # 2. Get specific forecast
    pid = sample_item["product_id"]
    lid = sample_item["location_id"]

    get_resp = client.get(f"/api/v1/forecast/{pid}/{lid}")
    assert get_resp.status_code == 200
    get_data = get_resp.json()

    assert get_data["product_id"] == pid
    assert get_data["location_id"] == lid
    assert get_data["chosen_model"] == sample_item["chosen_model"]
    assert get_data["daily_forecast"] == sample_item["daily_forecast"]
    assert get_data["wape"] == pytest.approx(sample_item["wape"], abs=1e-4)
    assert get_data["sigma"] == pytest.approx(sample_item["sigma"], abs=1e-4)
    assert get_data["is_simulated"] is True
