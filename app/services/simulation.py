"""Persistence and deterministic time control for the demo simulation."""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ApplicationSetting


SIMULATION_DATE_KEY = "simulation_date"
DEFAULT_SIMULATION_DATE = date(2026, 10, 2)


def get_simulation_date(db: Session) -> date:
    """Return the persisted simulation date, creating the default when needed."""

    setting = db.scalar(
        select(ApplicationSetting).where(
            ApplicationSetting.key == SIMULATION_DATE_KEY
        )
    )
    if setting is None:
        setting = ApplicationSetting(
            key=SIMULATION_DATE_KEY,
            value=DEFAULT_SIMULATION_DATE.isoformat(),
        )
        db.add(setting)
        db.flush()
        return DEFAULT_SIMULATION_DATE
    return date.fromisoformat(setting.value)


def set_simulation_date(db: Session, simulation_date: date) -> date:
    """Persist and return a simulation date."""

    setting = db.scalar(
        select(ApplicationSetting).where(
            ApplicationSetting.key == SIMULATION_DATE_KEY
        )
    )
    if setting is None:
        setting = ApplicationSetting(key=SIMULATION_DATE_KEY, value="")
        db.add(setting)
    setting.value = simulation_date.isoformat()
    return simulation_date


def advance_simulation_date(db: Session, days: int) -> date:
    """Advance the persisted simulation date by a signed number of days."""

    current = get_simulation_date(db)
    return set_simulation_date(db, current + timedelta(days=days))


def reset_simulation_date(db: Session) -> date:
    """Reset the persisted simulation date to the demo baseline."""

    return set_simulation_date(db, DEFAULT_SIMULATION_DATE)
