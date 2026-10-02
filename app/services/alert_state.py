"""Deterministic alert state derivation from the simulation date."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alert


def derive_deadline_state(days_remaining: int) -> str:
    """Map days remaining to the deterministic demo state labels."""

    if days_remaining > 7:
        return "scheduled"
    if days_remaining >= 4:
        return "upcoming"
    if days_remaining >= 2:
        return "approaching"
    if days_remaining == 1:
        return "urgent"
    if days_remaining == 0:
        return "due_today"
    return "overdue"


def refresh_alert_states(db: Session, simulation_date: date) -> list[Alert]:
    """Refresh derived timing fields without changing human review status."""

    # The application deliberately uses autoflush=False. Flush newly-created
    # alerts before querying so their derived state is also correct in the
    # same response that created them.
    db.flush()
    alerts = db.scalars(select(Alert).order_by(Alert.id)).all()
    for alert in alerts:
        if alert.computed_deadline is None:
            alert.deadline_state = "not_applicable"
            alert.days_remaining = None
            alert.days_overdue = None
            continue

        days_remaining = (alert.computed_deadline.date() - simulation_date).days
        alert.days_remaining = days_remaining
        alert.days_overdue = max(0, -days_remaining)
        alert.deadline_state = derive_deadline_state(days_remaining)

        if alert.alert_type == "deadline_approaching":
            if days_remaining < 0:
                alert.reason = (
                    f"{alert.obligation.required_action} is overdue by "
                    f"{alert.days_overdue} days."
                )
            elif days_remaining == 0:
                alert.reason = f"{alert.obligation.required_action} is due today."
            else:
                alert.reason = (
                    f"{alert.obligation.required_action} is due in "
                    f"{days_remaining} days."
                )

    return alerts
