"""Deterministic event-to-obligation matching and alert creation."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alert, Event, Obligation


@dataclass(frozen=True)
class EventMonitoringResult:
    """Matches and alerts created for one event."""

    obligations: list[Obligation]
    alerts: list[Alert]


def computed_relative_deadline(
    occurred_at: datetime,
    obligation: Obligation,
) -> datetime | None:
    """Compute a due date for supported relative deadline units."""

    if obligation.time_constraint_type != "relative_deadline":
        return None
    if obligation.time_value is None or not obligation.time_unit:
        return None

    units = {
        "calendar_days": {"days": obligation.time_value},
        "days": {"days": obligation.time_value},
        "hours": {"hours": obligation.time_value},
        "calendar_hours": {"hours": obligation.time_value},
        "minutes": {"minutes": obligation.time_value},
        "calendar_minutes": {"minutes": obligation.time_value},
    }
    delta_kwargs = units.get(obligation.time_unit)
    if delta_kwargs is not None:
        return occurred_at + timedelta(**delta_kwargs)
    return None


def match_event(db: Session, event: Event) -> EventMonitoringResult:
    """Match one event by exact event type and create deterministic alerts."""

    obligations = db.scalars(
        select(Obligation)
        .where(Obligation.trigger_type == event.event_type)
        .order_by(Obligation.id)
    ).all()
    alerts: list[Alert] = []
    for obligation in obligations:
        computed_deadline = computed_relative_deadline(event.occurred_at, obligation)
        existing_alert_query = select(Alert.id).where(
            Alert.obligation_id == obligation.id,
            Alert.event_id == event.id,
        )
        if computed_deadline is None:
            existing_alert_query = existing_alert_query.where(
                Alert.computed_deadline.is_(None)
            )
        else:
            existing_alert_query = existing_alert_query.where(
                Alert.computed_deadline == computed_deadline
            )
        if db.scalar(existing_alert_query) is not None:
            continue

        alert = Alert(
            obligation_id=obligation.id,
            event_id=event.id,
            alert_type="event_triggered",
            reason=(
                f"A {event.event_type} event on "
                f"{event.occurred_at.strftime('%B %d, %Y').replace(' 0', ' ')} "
                "matched this obligation."
            ),
            computed_deadline=computed_deadline,
            evidence_text=obligation.evidence_text,
            evidence_page=obligation.page_number,
            status="pending_review",
        )
        db.add(alert)
        alerts.append(alert)
    return EventMonitoringResult(obligations=obligations, alerts=alerts)
