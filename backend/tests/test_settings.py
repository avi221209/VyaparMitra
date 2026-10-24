from fastapi.testclient import TestClient
from sqlmodel import Session, select
from backend.app.models import DecisionLog, SettingsModel
from backend.app.schemas import SettingsUpdate
from backend.app.settings import (
    DEFAULT_SETTINGS,
    get_current_settings,
    reset_to_default_settings,
    update_system_settings,
)


def test_default_settings_match_spec(session: Session):
    settings = get_current_settings(session)
    assert settings.H == 7
    assert settings.z == 1.28
    assert settings.alpha == 0.25
    assert settings.Gmax == 1
    assert settings.Eshort == 21
    assert settings.shrinkage == 0.5
    assert settings.planner_reserve == 0
    assert settings.epsilon == 0.001
    assert settings.solver_time_limit == 10.0


def test_update_settings_and_audit(session: Session):
    updated = update_system_settings(
        session,
        SettingsUpdate(H=14, z=1.65, Eshort=30),
        role="planner",
    )
    assert updated.H == 14
    assert updated.z == 1.65
    assert updated.Eshort == 30
    assert updated.Gmax == 1  # Unchanged

    audit = session.exec(
        select(DecisionLog).where(DecisionLog.action == "UPDATE_SETTINGS")
    ).first()
    assert audit is not None
    assert audit.actor_role == "planner"
    assert "14" in audit.new_value


def test_reset_settings(session: Session):
    update_system_settings(session, SettingsUpdate(H=10), role="planner")
    reset = reset_to_default_settings(session, role="reviewer")

    assert reset.H == 7
    assert reset.z == 1.28

    audit = session.exec(
        select(DecisionLog).where(DecisionLog.action == "RESET_DEFAULT_SETTINGS")
    ).first()
    assert audit is not None
    assert audit.actor_role == "reviewer"


def test_settings_api(client: TestClient):
    # GET settings
    res = client.get("/api/v1/settings")
    assert res.status_code == 200
    data = res.json()
    assert data["H"] == 7
    assert data["z"] == 1.28

    # PUT settings with valid role
    put_res = client.put(
        "/api/v1/settings",
        json={"H": 10, "alpha": 0.3},
        headers={"X-Role": "planner"},
    )
    assert put_res.status_code == 200
    assert put_res.json()["H"] == 10
    assert put_res.json()["alpha"] == 0.3

    # PUT settings with invalid role
    bad_role_res = client.put(
        "/api/v1/settings",
        json={"H": 5},
        headers={"X-Role": "unauthorized_user"},
    )
    assert bad_role_res.status_code == 403

    # POST reset
    reset_res = client.post(
        "/api/v1/settings/reset",
        headers={"X-Role": "warehouse"},
    )
    assert reset_res.status_code == 200
    assert reset_res.json()["H"] == 7
