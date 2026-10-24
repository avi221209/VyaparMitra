from backend.scripts.headroom import run_headroom_analysis


def test_headroom_analysis():
    results = run_headroom_analysis(seed=1)
    assert "scarce" in results
    assert "balanced" in results
    assert "abundant" in results

    for scen in ["scarce", "balanced", "abundant"]:
        data = results[scen]
        assert data["oracle_fill_rate"] >= data["baseline_fill_rate"]
        assert data["total_demand_cartons"] > 0
        assert data["oracle_fill_rate"] > 0.0
        # The headroom gap should be non-negative
        assert data["headroom_gap"] >= 0.0
