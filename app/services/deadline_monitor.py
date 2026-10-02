"""Deterministic monitoring for obligations with fixed deadlines."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Alert, Obligation
from app.services.alert_state import refresh_alert_states


@dataclass(frozen=True)
class DeadlineMonitorResult:
    """Summary of one deadline-monitoring run."""

    obligations_checked: int
    alerts_created: int
    skipped_obligations: int


class DeadlineMonitoringError(Exception):
    """Raised when deadline monitoring cannot be persisted."""


def _parse_fixed_deadline(value: str) -> datetime | None:
    """Parse an ISO date or datetime stored in fixed_deadline."""

    normalized = value.strip()
    if not normalized:
        return None

    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        try:
            return datetime.combine(date.fromisoformat(normalized), time.min)
        except ValueError:
            return None


def _comparable_deadline(deadline: datetime, current: datetime) -> datetime:
    """Keep comparisons safe for mixed naive/aware ISO values."""

    if deadline.tzinfo is not None and current.tzinfo is None:
        return deadline.replace(tzinfo=None)
    if deadline.tzinfo is None and current.tzinfo is not None:
        return deadline.replace(tzinfo=current.tzinfo)
    return deadline


def monitor_deadlines(
    db: Session,
    warning_days: int = 7,
    now: datetime | None = None,
    simulation_date: date | None = None,
    commit: bool = True,
) -> DeadlineMonitorResult:
    """Create pending alerts for fixed deadlines in or past the warning window."""

    if simulation_date is None and now is None:
        # The persisted demo clock is the default operational clock. The
        # explicit ``now`` argument remains available for isolated tests and
        # non-demo callers.
        from app.services.simulation import get_simulation_date

        simulation_date = get_simulation_date(db)

    current = (
        datetime.combine(simulation_date, time.min)
        if simulation_date is not None
        else now or datetime.now()
    )
    obligations = db.scalars(
        select(Obligation).where(
            Obligation.time_constraint_type == "fixed_deadline",
            Obligation.fixed_deadline.is_not(None),
        )
    ).all()

    alerts_created = 0
    skipped_obligations = 0
    window_end = current + timedelta(days=warning_days)

    for obligation in obligations:
        fixed_deadline = _parse_fixed_deadline(obligation.fixed_deadline or "")
        if fixed_deadline is None:
            skipped_obligations += 1
            continue

        comparable_deadline = _comparable_deadline(fixed_deadline, current)
        if comparable_deadline > window_end:
            skipped_obligations += 1
            continue

        # SQLite's DateTime column is timezone-naive in this prototype.
        stored_deadline = fixed_deadline.replace(tzinfo=None)

        duplicate_alert = db.scalar(
            select(Alert.id).where(
                Alert.obligation_id == obligation.id,
                Alert.computed_deadline == stored_deadline,
                Alert.status.in_(["pending_review", "confirmed"]),
            )
        )
        if duplicate_alert is not None:
            skipped_obligations += 1
            continue

        days_until = (comparable_deadline.date() - current.date()).days
        db.add(
            Alert(
                obligation_id=obligation.id,
                event_id=None,
                alert_type="deadline_approaching",
                reason=(
                    f"{obligation.required_action} is due in {days_until} days."
                ),
                computed_deadline=stored_deadline,
                evidence_text=obligation.evidence_text,
                evidence_page=obligation.page_number,
                status="pending_review",
            )
        )
        alerts_created += 1

    refresh_alert_states(db, current.date())
    if commit:
        try:
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            raise DeadlineMonitoringError(
                "Unable to save deadline monitoring alerts."
            ) from exc

    return DeadlineMonitorResult(
        obligations_checked=len(obligations),
        alerts_created=alerts_created,
        skipped_obligations=skipped_obligations,
    )
