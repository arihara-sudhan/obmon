"""SQLAlchemy models for persisted documents and obligations."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Document(Base):
    """A parsed PDF document stored for later retrieval."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    total_pages: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    obligations: Mapped[list["Obligation"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )


class Obligation(Base):
    """An obligation extracted from a stored document."""

    __tablename__ = "obligations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id"),
        nullable=False,
        index=True,
    )
    obligation_type: Mapped[str] = mapped_column(String(255), nullable=False)
    trigger_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    required_action: Mapped[str] = mapped_column(Text, nullable=False)
    time_constraint_type: Mapped[str] = mapped_column(String(32), nullable=False)
    time_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    time_unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fixed_deadline: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Kept only so databases created before the time-constraint migration remain
    # writable. These fields are not exposed by the API schemas.
    legacy_deadline_type: Mapped[str | None] = mapped_column(
        "deadline_type",
        String(32),
        nullable=True,
    )
    legacy_deadline_value: Mapped[int | None] = mapped_column(
        "deadline_value",
        Integer,
        nullable=True,
    )
    legacy_deadline_unit: Mapped[str | None] = mapped_column(
        "deadline_unit",
        String(64),
        nullable=True,
    )
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    requires_human_review: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    document: Mapped[Document] = relationship(back_populates="obligations")
    alerts: Mapped[list["Alert"]] = relationship(
        back_populates="obligation",
        cascade="all, delete-orphan",
    )


@event.listens_for(Obligation, "before_insert")
def _populate_legacy_deadline_fields(
    _mapper: object,
    _connection: object,
    obligation: Obligation,
) -> None:
    """Keep pre-migration SQLite columns populated for existing databases."""

    legacy_type_by_constraint = {
        "relative_deadline": "relative",
        "fixed_deadline": "fixed",
        "ambiguous": "ambiguous",
        "none": "none",
    }
    if obligation.legacy_deadline_type is None:
        obligation.legacy_deadline_type = legacy_type_by_constraint.get(
            obligation.time_constraint_type,
            "none",
        )
    if obligation.legacy_deadline_type != "relative":
        obligation.legacy_deadline_value = None
        obligation.legacy_deadline_unit = None


class Event(Base):
    """An operational event received from an external source."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(255), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    alerts: Mapped[list["Alert"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
    )


class ApplicationSetting(Base):
    """A small persisted application setting used by the demo layer."""

    __tablename__ = "application_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class Alert(Base):
    """A reviewable alert created when an event matches an obligation."""

    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_review', 'confirmed', 'rejected', 'resolved')",
            name="ck_alert_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    obligation_id: Mapped[int] = mapped_column(
        ForeignKey("obligations.id"),
        nullable=False,
        index=True,
    )
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("events.id"),
        nullable=True,
        index=True,
    )
    alert_type: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    computed_deadline: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_page: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        default="pending_review",
        nullable=False,
    )
    deadline_state: Mapped[str] = mapped_column(
        String(32),
        default="not_applicable",
        nullable=False,
    )
    days_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)
    days_overdue: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    obligation: Mapped[Obligation] = relationship(back_populates="alerts")
    event: Mapped[Event | None] = relationship(back_populates="alerts")
    human_decisions: Mapped[list["HumanDecision"]] = relationship(
        back_populates="alert",
        cascade="all, delete-orphan",
    )


class HumanDecision(Base):
    """A human confirmation or rejection of an alert."""

    __tablename__ = "human_decisions"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('confirmed', 'rejected')",
            name="ck_human_decision",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_id: Mapped[int] = mapped_column(
        ForeignKey("alerts.id"),
        nullable=False,
        index=True,
    )
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    alert: Mapped[Alert] = relationship(back_populates="human_decisions")
