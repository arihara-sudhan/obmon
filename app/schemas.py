"""Pydantic schemas for the obmon API."""

import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


class ParsedPage(BaseModel):
    """Text extracted from one PDF page."""

    page_number: int
    text: str


class ParsedDocument(BaseModel):
    """Text extracted from a PDF, retaining page boundaries."""

    filename: str
    total_pages: int
    pages: list[ParsedPage]


class Obligation(BaseModel):
    """A required action identified in a parsed document."""

    obligation_type: str
    trigger_type: str | None = None
    required_action: str
    time_constraint_type: Literal[
        "relative_deadline",
        "fixed_deadline",
        "minimum_duration",
        "maximum_duration",
        "none",
        "ambiguous",
    ]
    time_value: int | None = None
    time_unit: str | None = None
    fixed_deadline: str | None = None
    evidence_text: str
    page_number: int
    confidence: float
    requires_human_review: bool

    @field_validator("trigger_type")
    @classmethod
    def validate_trigger_type(cls, value: str | None) -> str | None:
        """Require specific normalized trigger names when a trigger exists."""

        if value is None:
            return None
        generic_values = {"event", "incident", "trigger", "condition"}
        if value in generic_values or not re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)*", value):
            raise ValueError(
                "trigger_type must be a specific lowercase snake_case condition."
            )
        return value

    @field_validator("evidence_text")
    @classmethod
    def validate_evidence_text(cls, value: str) -> str:
        """Reject obligations that do not have exact supporting evidence."""

        if not value.strip():
            raise ValueError("evidence_text cannot be blank.")
        return value


class ObligationExtractionResult(BaseModel):
    """Structured obligations extracted from a parsed document."""

    has_obligations: bool
    obligations: list[Obligation]


class StoredObligation(Obligation):
    """An obligation including its persistence identifiers and timestamp."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    created_at: datetime


class DocumentSummary(BaseModel):
    """Stored document metadata returned by the collection endpoint."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    total_pages: int
    created_at: datetime


class StoredDocument(DocumentSummary):
    """A stored document and all obligations extracted from it."""

    obligations: list[StoredObligation]


class PersistedObligationExtractionResult(BaseModel):
    """Result returned after extraction and persistence complete."""

    document_id: int
    filename: str
    obligations: list[StoredObligation]


class EventCreate(BaseModel):
    """Input payload for an operational event."""

    external_id: str
    event_type: str
    occurred_at: datetime
    description: str | None = None
    source: str | None = None


class EventResponse(EventCreate):
    """An operational event including its database identifiers."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


class EventObligationMatch(BaseModel):
    """An obligation matched deterministically to an operational event."""

    obligation_id: int
    required_action: str
    trigger_type: str | None = None
    time_constraint_type: Literal[
        "relative_deadline",
        "fixed_deadline",
        "minimum_duration",
        "maximum_duration",
        "none",
        "ambiguous",
    ]
    time_value: int | None = None
    time_unit: str | None = None
    fixed_deadline: str | None = None
    computed_deadline: datetime | None = None
    evidence_text: str
    page_number: int


class EventIngestionResponse(BaseModel):
    """An ingested event and the obligations matched to it."""

    event: EventResponse
    matches: list[EventObligationMatch]


class TriggerableObligationResponse(BaseModel):
    """An obligation that can be activated by its stored trigger type."""

    obligation_id: int
    required_action: str
    time_constraint_type: Literal[
        "relative_deadline",
        "fixed_deadline",
        "minimum_duration",
        "maximum_duration",
        "none",
        "ambiguous",
    ]
    time_value: int | None = None
    time_unit: str | None = None
    fixed_deadline: str | None = None


class TriggerableEventResponse(BaseModel):
    """One distinct trigger type and its related obligations."""

    event_type: str
    obligations: list[TriggerableObligationResponse]


class TriggerableEventsResponse(BaseModel):
    """All event types currently available from stored obligations."""

    triggerable_events: list[TriggerableEventResponse]


class TriggerEventCreate(BaseModel):
    """Request to trigger an event using the simulation clock."""

    event_type: str
    description: str | None = None


class AlertResponse(BaseModel):
    """A persisted alert with the required action available for review."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    obligation_id: int
    event_id: int | None
    alert_type: str
    reason: str
    required_action: str
    computed_deadline: datetime | None
    evidence_text: str
    evidence_page: int
    status: Literal["pending_review", "confirmed", "rejected", "resolved"]
    review_status: Literal["pending_review", "confirmed", "rejected", "resolved"]
    event_type: str | None = None
    event_occurred_at: datetime | None = None
    deadline_state: Literal[
        "scheduled",
        "upcoming",
        "approaching",
        "urgent",
        "due_today",
        "overdue",
        "not_applicable",
    ]
    days_remaining: int | None = None
    days_overdue: int | None = None
    created_at: datetime


class TriggerEventResponse(BaseModel):
    """An automatically-created event, matches, and resulting alerts."""

    event: EventResponse
    matches: list[EventObligationMatch]
    alerts: list[AlertResponse]


class HumanDecisionCreate(BaseModel):
    """Input payload for reviewing an alert."""

    decision: Literal["confirmed", "rejected"]
    comment: str | None = None


class DeadlineMonitorResponse(BaseModel):
    """Summary returned by a deadline monitoring run."""

    obligations_checked: int
    alerts_created: int
    skipped_obligations: int


class SimulationDateResponse(BaseModel):
    """The current persisted demo simulation date."""

    simulation_date: date


class SimulationAdvanceRequest(BaseModel):
    """A signed number of days by which to move the simulation clock."""

    days: int
