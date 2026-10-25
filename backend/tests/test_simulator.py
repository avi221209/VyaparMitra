import json
from pathlib import Path
import pytest
from sqlmodel import Session, select
from backend.app.models import Batch, DecisionLog, InventorySnapshot, Lane, Location, Product, SalesDaily, ValidationIssue
from backend.app.services.simulator import FMCGSimulator


def test_simulator_determinism():
    sim1 = FMCGSimulator(seed=1)
    p1, loc1, s1, l1, b1, snap1, _ = sim1.generate_all()

    sim2 = FMCGSimulator(seed=1)
    p2, loc2, s2, l2, b2, snap2, _ = sim2.generate_all()

    assert len(p1) == len(p2) == 24
    assert len(loc1) == len(loc2) == 6
    assert len(s1) == len(s2) == 4 * 24 * 120  # 11,520 records
    assert len(l1) == len(l2) == 8
    assert len(b1) == len(b2)
    assert len(snap1) == len(snap2)

    assert [b.quantity for b in b1] == [b.quantity for b in b2]
    assert [s.units for s in s1[:50]] == [s.units for s in s2[:50]]


def test_simulator_structure_and_pure_sources():
    sim = FMCGSimulator(seed=1)
    products, locations, sales, lanes, batches, snapshots, _ = sim.generate_all()

    warehouses = [loc for loc in locations if loc.type == "warehouse"]
    destinations = [loc for loc in locations if loc.type != "warehouse"]

    assert len(warehouses) == 2
    assert {w.id for w in warehouses} == {"W1", "W2"}

    assert len(destinations) == 4
    assert {d.id for d in destinations} == {"D1", "D2", "S1", "S2"}
    distributors = [d for d in destinations if d.type == "distributor"]
    stores = [d for d in destinations if d.type == "store"]
    assert len(distributors) == 2
    assert len(stores) == 2

    # Check 24 products across 5 categories
    assert len(products) == 24
    categories = {p.category for p in products}
    assert categories == {"Staples", "Packaged Food", "Personal Care", "Home Care", "Beverages"}

    # Pure sources: no sales at warehouses!
    sales_locations = {s.location_id for s in sales}
    assert "W1" not in sales_locations
    assert "W2" not in sales_locations
    assert sales_locations == {"D1", "D2", "S1", "S2"}

    # 120 days sales per product-destination: 4 destinations * 24 products * 120 days = 11,520
    assert len(sales) == 4 * 24 * 120


def test_simulator_lanes_and_tight_capacity():
    sim = FMCGSimulator(seed=1)
    _, _, _, lanes, _, _, _ = sim.generate_all()

    # 8 lanes connecting all 2 warehouses to all 4 destinations
    assert len(lanes) == 8
    sources = {l.source_id for l in lanes}
    dests = {l.destination_id for l in lanes}
    assert sources == {"W1", "W2"}
    assert dests == {"D1", "D2", "S1", "S2"}

    for l in lanes:
        assert 1 <= l.lead_time_days <= 3
        assert l.cost_per_carton > 0

    # Exactly 2 lanes have tight capacity (~70% unconstrained flow), others are None
    tight_lanes = [l for l in lanes if l.capacity_load is not None]
    unconstrained_lanes = [l for l in lanes if l.capacity_load is None]
    assert len(tight_lanes) == 2
    assert len(unconstrained_lanes) == 6


def test_simulator_stock_scenarios():
    sim_scarce = FMCGSimulator(seed=1, scenario="scarce")
    _, _, _, _, b_scarce, _, _ = sim_scarce.generate_all()

    sim_balanced = FMCGSimulator(seed=1, scenario="balanced")
    _, _, _, _, b_balanced, _, _ = sim_balanced.generate_all()

    sim_abundant = FMCGSimulator(seed=1, scenario="abundant")
    _, _, _, _, b_abundant, _, _ = sim_abundant.generate_all()

    total_scarce = sum(b.quantity for b in b_scarce)
    total_balanced = sum(b.quantity for b in b_balanced)
    total_abundant = sum(b.quantity for b in b_abundant)

    assert total_scarce < total_balanced < total_abundant
    # Proportions approximately 0.8 : 1.0 : 1.3
    ratio_scarce = total_scarce / total_balanced
    ratio_abundant = total_abundant / total_balanced
    assert 0.75 <= ratio_scarce <= 0.85
    assert 1.25 <= ratio_abundant <= 1.35


def test_simulator_defects_variant_and_manifest():
    sim = FMCGSimulator(seed=1, variant="defects")
    products, locations, sales, lanes, batches, snapshots, issues = sim.generate_all()

    # Defect manifest has about 20 entries
    assert 18 <= len(sim.defect_manifest) <= 22
    assert len(issues) == len(sim.defect_manifest)

    defect_types = {m["type"] for m in sim.defect_manifest}
    assert "DUPLICATE_SKU" in defect_types
    assert "MIXED_UNITS" in defect_types
    assert "NEGATIVE_STOCK" in defect_types
    assert "INVALID_DATE" in defect_types
    assert "MISSING_SALES_DAYS" in defect_types


def test_simulator_low_w1_variant():
    sim_normal = FMCGSimulator(seed=1, variant="normal")
    _, _, _, _, b_normal, _, _ = sim_normal.generate_all()

    sim_low_w1 = FMCGSimulator(seed=1, variant="low_w1")
    _, _, _, _, b_low_w1, _, _ = sim_low_w1.generate_all()

    w1_normal_qty = sum(b.quantity for b in b_normal if b.location_id == "W1")
    w1_low_qty = sum(b.quantity for b in b_low_w1 if b.location_id == "W1")

    # W2 should be identical
    w2_normal_qty = sum(b.quantity for b in b_normal if b.location_id == "W2")
    w2_low_qty = sum(b.quantity for b in b_low_w1 if b.location_id == "W2")

    assert w2_normal_qty == w2_low_qty
    # W1 stock cut by ~20%
    ratio = w1_low_qty / w1_normal_qty
    assert 0.75 <= ratio <= 0.85


def test_simulator_all_labelled_simulated():
    sim = FMCGSimulator(seed=1)
    products, locations, sales, lanes, batches, snapshots, _ = sim.generate_all()

    assert all(p.is_simulated for p in products)
    assert all(loc.is_simulated for loc in locations)
    assert all(s.is_simulated for s in sales)
    assert all(l.is_simulated for l in lanes)
    assert all(b.is_simulated for b in batches)
    assert all(snap.is_simulated for snap in snapshots)


def test_seed_database_and_export_csv(session: Session, tmp_path: Path):
    sim = FMCGSimulator(seed=1, scenario="balanced", variant="defects")
    res = sim.seed_database(session)

    assert res["counts"]["locations"] == 6
    assert res["counts"]["warehouses"] == 2
    assert res["counts"]["destinations"] == 4
    assert res["counts"]["lanes"] == 8
    assert res["counts"]["products"] >= 24
    assert res["counts"]["validation_issues"] >= 18

    # Check DecisionLog was written
    logs = session.exec(select(DecisionLog).where(DecisionLog.action == "SEED")).all()
    assert len(logs) >= 1

    # Test export
    paths = sim.export_to_csv(output_dir=tmp_path)
    for name, p in paths.items():
        assert Path(p).exists()

    manifest_file = tmp_path / "manifest.json"
    assert manifest_file.exists()
    defect_manifest_file = tmp_path / "defect_manifest.json"
    assert defect_manifest_file.exists()


def test_simulator_constructor_compatibility(session: Session):
    """Test that FMCGSimulator constructs cleanly with or without session keyword argument."""
    # 1. Without session keyword
    sim1 = FMCGSimulator(seed=1, variant="normal", scenario="balanced")
    assert sim1.session is None
    res1 = sim1.seed_database(session)
    assert res1["counts"]["locations"] == 6

    # 2. With session keyword
    sim2 = FMCGSimulator(session=session, seed=1, variant="normal", scenario="balanced")
    assert sim2.session is session
    # Test seed_deterministic alias
    res2 = sim2.seed_deterministic(variant="normal", seed=1, scenario="balanced")
    assert res2["counts"]["locations"] == 6


@pytest.mark.anyio
async def test_fastapi_lifespan_startup_on_clean_db():
    """Verify that FastAPI lifespan executes cleanly on an empty database without raising TypeError."""
    from backend.app.main import lifespan, app
    from sqlmodel import SQLModel, create_engine, func
    from sqlmodel.pool import StaticPool
    import backend.app.main as main_module

    # Create temporary isolated in-memory engine
    clean_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(clean_engine)

    orig_engine = main_module.engine
    main_module.engine = clean_engine

    try:
        # Run lifespan context manager (triggers init_db and seed_database)
        async with lifespan(app):
            with Session(clean_engine) as session:
                loc_count = session.exec(select(func.count(Location.id))).one()
                assert loc_count == 6
    finally:
        main_module.engine = orig_engine
