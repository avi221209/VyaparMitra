import json
from datetime import datetime, timezone
from sqlmodel import Session, select
from backend.app.models import DecisionLog, SettingsModel
from backend.app.schemas import SettingsUpdate

DEFAULT_SETTINGS = {
    "H": 7,
    "z": 1.28,
    "alpha": 0.25,
    "Gmax": 1,
    "Eshort": 21,
    "shrinkage": 0.5,
    "planner_reserve": 0,
    "epsilon": 0.001,
    "solver_time_limit": 10.0,
}


def get_current_settings(session: Session) -> SettingsModel:
    """Retrieve current system settings. If not found, initializes default."""
    settings_obj = session.exec(select(SettingsModel).where(SettingsModel.id == 1)).first()
    if not settings_obj:
        settings_obj = SettingsModel(id=1, **DEFAULT_SETTINGS)
        session.add(settings_obj)
        session.commit()
        session.refresh(settings_obj)
    return settings_obj


def update_system_settings(
    session: Session,
    updates: SettingsUpdate,
    role: str = "planner",
) -> SettingsModel:
    """Update settings and record in audit log."""
    settings_obj = get_current_settings(session)
    old_data = settings_obj.model_dump()
    update_data = updates.model_dump(exclude_unset=True)

    if not update_data:
        return settings_obj

    for key, value in update_data.items():
        setattr(settings_obj, key, value)

    settings_obj.updated_at = datetime.now(timezone.utc)
    session.add(settings_obj)

    # Log to audit trail
    audit_entry = DecisionLog(
        actor_role=role,
        action="UPDATE_SETTINGS",
        old_value=json.dumps(old_data, default=str),
        new_value=json.dumps(update_data, default=str),
        note=f"Settings updated by {role}",
    )
    session.add(audit_entry)

    session.commit()
    session.refresh(settings_obj)
    return settings_obj


def reset_to_default_settings(session: Session, role: str = "planner") -> SettingsModel:
    """Reset system settings to standard mandated defaults."""
    settings_obj = get_current_settings(session)
    old_data = settings_obj.model_dump()

    for key, value in DEFAULT_SETTINGS.items():
        setattr(settings_obj, key, value)

    settings_obj.updated_at = datetime.now(timezone.utc)
    session.add(settings_obj)

    audit_entry = DecisionLog(
        actor_role=role,
        action="RESET_DEFAULT_SETTINGS",
        old_value=json.dumps(old_data, default=str),
        new_value=json.dumps(DEFAULT_SETTINGS, default=str),
        note=f"Settings reset to default by {role}",
    )
    session.add(audit_entry)

    session.commit()
    session.refresh(settings_obj)
    return settings_obj
