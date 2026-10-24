from datetime import date, datetime
from sqlmodel import Session, select
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
    Settings,
    ValidationIssue,
)


def test_product_model(session: Session):
    prod = Product(
        id="SKU-P01",
        name="Chakki Fresh Atta 5kg",
        category="Staples",
        unit="bag",
        case_pack=4,
        load_per_carton=20.0,
        unit_cost=180.0,
        unit_margin=40.0,
        min_remaining_shelf_days=21,
        is_simulated=True,
    )
    session.add(prod)
    session.commit()

    saved = session.get(Product, "SKU-P01")
    assert saved is not None
    assert saved.name == "Chakki Fresh Atta 5kg"
    assert saved.case_pack == 4
    assert saved.load_per_carton == 20.0
    assert saved.is_simulated is True


def test_location_model(session: Session):
    w1 = Location(
        id="W1",
        name="North Central Hub",
        type="warehouse",
        city="Gurgaon",
        state="Haryana",
        is_simulated=True,
    )
    d1 = Location(
        id="D1",
        name="Metro Distributor East",
        type="distributor",
        city="Kolkata",
        state="West Bengal",
        is_simulated=True,
    )
    session.add(w1)
    session.add(d1)
    session.commit()

    saved_w1 = session.get(Location, "W1")
    assert saved_w1 is not None
    assert saved_w1.type == "warehouse"

    saved_d1 = session.get(Location, "D1")
    assert saved_d1 is not None
    assert saved_d1.type == "distributor"


def test_batch_and_lane_relations(session: Session):
    w1 = Location(id="W1", name="W1", type="warehouse", is_simulated=True)
    d1 = Location(id="D1", name="D1", type="distributor", is_simulated=True)
    p1 = Product(
        id="SKU-P01",
        name="P1",
        category="Staples",
        unit="bag",
        case_pack=1,
        unit_cost=10,
        unit_margin=2,
        is_simulated=True,
    )
    session.add(w1)
    session.add(d1)
    session.add(p1)
    session.commit()

    batch = Batch(
        id="B-W1-P01-1",
        location_id=w1.id,
        product_id=p1.id,
        quantity=250,
        expiry_date=date(2027, 1, 1),
        batch_code="LOT-001",
        cost_per_carton=50.0,
        is_simulated=True,
    )
    lane = Lane(
        id="LANE-W1-D1",
        source_id=w1.id,
        destination_id=d1.id,
        lead_time_days=2,
        cost_per_carton=35.0,
        capacity_load=500.0,
        distance_km=850.0,
        is_simulated=True,
    )
    session.add(batch)
    session.add(lane)
    session.commit()

    saved_batch = session.get(Batch, "B-W1-P01-1")
    saved_lane = session.get(Lane, "LANE-W1-D1")

    assert saved_batch is not None
    assert saved_batch.quantity == 250
    assert saved_lane is not None
    assert saved_lane.capacity_load == 500.0
    assert saved_lane.lead_time_days == 2


def test_sales_and_inventory_snapshots(session: Session):
    d1 = Location(id="D1", name="D1", type="distributor", is_simulated=True)
    p1 = Product(id="SKU-P01", name="P1", category="Staples", case_pack=4, is_simulated=True)
    session.add(d1)
    session.add(p1)
    session.commit()

    sales = SalesDaily(
        date=date(2026, 10, 20),
        location_id=d1.id,
        product_id=p1.id,
        units=48,
        is_simulated=True,
    )
    snapshot = InventorySnapshot(
        location_id=d1.id,
        product_id=p1.id,
        on_hand=60,
        reserved=10,
        in_transit=25,
        snapshot_date=date(2026, 10, 24),
        is_simulated=True,
    )
    session.add(sales)
    session.add(snapshot)
    session.commit()

    saved_sales = session.exec(select(SalesDaily).where(SalesDaily.location_id == "D1")).first()
    assert saved_sales is not None
    assert saved_sales.units == 48

    saved_snap = session.exec(select(InventorySnapshot).where(InventorySnapshot.location_id == "D1")).first()
    assert saved_snap is not None
    assert saved_snap.on_hand == 60


def test_validation_issue_and_decision_log(session: Session):
    issue = ValidationIssue(
        type="NEGATIVE_STOCK",
        entity="InventorySnapshot:D1:P01",
        severity="ERROR",
        status="OPEN",
        description="On hand stock is -15",
        is_simulated=True,
    )
    log = DecisionLog(
        plan_line_id=None,
        actor_role="reviewer",
        action="OVERRIDE",
        old_value="50",
        new_value="60",
        note="Approved higher dispatch for festive bump",
    )
    session.add(issue)
    session.add(log)
    session.commit()

    saved_issue = session.exec(select(ValidationIssue).where(ValidationIssue.type == "NEGATIVE_STOCK")).first()
    assert saved_issue is not None
    assert saved_issue.severity == "ERROR"

    saved_log = session.exec(select(DecisionLog).where(DecisionLog.action == "OVERRIDE")).first()
    assert saved_log is not None
    assert saved_log.actor_role == "reviewer"
