"""FastAPI application entry point."""

from datetime import date, datetime, time
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db, init_db
from app.models import Alert as AlertModel
from app.models import Event as EventModel
from app.models import Document as DocumentModel
from app.models import HumanDecision as HumanDecisionModel
from app.models import Obligation as ObligationModel
from app.schemas import (
    AlertResponse,
    DeadlineMonitorResponse,
    DocumentSummary,
    EventCreate,
    EventIngestionResponse,
    EventObligationMatch,
    EventResponse,
    HumanDecisionCreate,
    ParsedDocument,
    PersistedObligationExtractionResult,
    StoredDocument,
    StoredObligation,
    SimulationAdvanceRequest,
    SimulationDateResponse,
    TriggerEventCreate,
    TriggerEventResponse,
    TriggerableEventResponse,
    TriggerableEventsResponse,
    TriggerableObligationResponse,
)
from app.services.alert_state import refresh_alert_states
from app.services.document_parser import DocumentParsingError, parse_document
from app.services.deadline_monitor import (
    DeadlineMonitoringError,
    monitor_deadlines,
)
from app.services.obligation_extractor import (
    ObligationExtractionError,
    extract_obligations,
)
from app.services.event_monitor import (
    computed_relative_deadline,
    match_event,
    obligation_key,
)
from app.services.simulation import (
    advance_simulation_date,
    get_simulation_date,
    reset_simulation_date,
)

app = FastAPI(title="obmon")
init_db()


def _alert_response(alert: AlertModel) -> AlertResponse:
    """Convert an alert ORM row to its API representation."""

    return AlertResponse(
        id=alert.id,
        obligation_id=alert.obligation_id,
        event_id=alert.event_id,
        alert_type=alert.alert_type,
        reason=alert.reason,
        required_action=alert.obligation.required_action,
        computed_deadline=alert.computed_deadline,
        evidence_text=alert.evidence_text,
        evidence_page=alert.evidence_page,
        status=alert.status,
        review_status=alert.status,
        event_type=alert.event.event_type if alert.event is not None else None,
        event_occurred_at=(
            alert.event.occurred_at if alert.event is not None else None
        ),
        deadline_state=alert.deadline_state or "not_applicable",
        days_remaining=alert.days_remaining,
        days_overdue=alert.days_overdue,
        created_at=alert.created_at,
    )


def _event_matches(
    event: EventModel,
    obligations: list[ObligationModel],
) -> list[EventObligationMatch]:
    """Convert deterministic event matches into the shared API shape."""

    return [
        EventObligationMatch(
            obligation_id=obligation.id,
            required_action=obligation.required_action,
            trigger_type=obligation.trigger_type,
            time_constraint_type=obligation.time_constraint_type,
            time_value=obligation.time_value,
            time_unit=obligation.time_unit,
            fixed_deadline=obligation.fixed_deadline,
            computed_deadline=computed_relative_deadline(
                event.occurred_at,
                obligation,
            ),
            evidence_text=obligation.evidence_text,
            page_number=obligation.page_number,
        )
        for obligation in obligations
    ]


async def _parse_pdf_upload(file: UploadFile) -> ParsedDocument:
    """Write an uploaded PDF to a temporary file and parse it."""

    filename = file.filename or ""
    if not filename.lower().endswith(".pdf"):
        await file.close()
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported.",
        )

    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(suffix=".pdf", delete=False) as temporary_file:
            temporary_path = Path(temporary_file.name)
            while chunk := await file.read(1024 * 1024):
                temporary_file.write(chunk)

        return parse_document(temporary_path)
    except DocumentParsingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=400,
            detail="Unable to read the uploaded PDF.",
        ) from exc
    finally:
        await file.close()
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


@app.get("/health")
def health() -> dict[str, str]:
    """Return the service health status."""

    return {"status": "ok"}


@app.post("/documents/parse", response_model=ParsedDocument)
async def parse_uploaded_document(file: UploadFile = File(...)) -> ParsedDocument:
    """Extract text from an uploaded PDF using a temporary local file."""

    return await _parse_pdf_upload(file)


@app.post(
    "/documents/extract-obligations",
    response_model=PersistedObligationExtractionResult,
)
async def extract_uploaded_obligations(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> PersistedObligationExtractionResult:
    """Parse, extract, persist, and return obligations from an uploaded PDF."""

    document = await _parse_pdf_upload(file)
    try:
        extraction = await run_in_threadpool(extract_obligations, document)
    except ObligationExtractionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    try:
        stored_document = DocumentModel(
            filename=document.filename,
            total_pages=document.total_pages,
        )
        db.add(stored_document)
        db.flush()

        for extracted_obligation in extraction.obligations:
            db.add(
                ObligationModel(
                    document_id=stored_document.id,
                    obligation_type=extracted_obligation.obligation_type,
                    trigger_type=extracted_obligation.trigger_type,
                    required_action=extracted_obligation.required_action,
                    time_constraint_type=extracted_obligation.time_constraint_type,
                    time_value=extracted_obligation.time_value,
                    time_unit=extracted_obligation.time_unit,
                    fixed_deadline=extracted_obligation.fixed_deadline,
                    evidence_text=extracted_obligation.evidence_text,
                    page_number=extracted_obligation.page_number,
                    confidence=extracted_obligation.confidence,
                    requires_human_review=extracted_obligation.requires_human_review,
                )
            )

        db.commit()
        db.refresh(stored_document)
        return PersistedObligationExtractionResult(
            document_id=stored_document.id,
            filename=stored_document.filename,
            obligations=[
                StoredObligation.model_validate(obligation)
                for obligation in stored_document.obligations
            ],
        )
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to save the extracted obligations.",
        ) from exc


@app.post("/events", response_model=EventIngestionResponse)
def create_event(
    event: EventCreate,
    db: Session = Depends(get_db),
) -> EventIngestionResponse:
    """Store an event and deterministically match obligations by trigger type."""

    existing_event = db.scalar(
        select(EventModel).where(EventModel.external_id == event.external_id)
    )
    if existing_event is not None:
        raise HTTPException(
            status_code=409,
            detail="An event with this external_id already exists.",
        )

    stored_event = EventModel(
        external_id=event.external_id,
        event_type=event.event_type,
        occurred_at=event.occurred_at,
        description=event.description,
        source=event.source,
    )
    db.add(stored_event)
    try:
        db.flush()
        match_result = match_event(db, stored_event)
        simulation_date = get_simulation_date(db)
        refresh_alert_states(db, simulation_date)

        matches = _event_matches(stored_event, match_result.obligations)

        db.commit()
        db.refresh(stored_event)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="An event with this external_id already exists.",
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to save the event.",
        ) from exc

    return EventIngestionResponse(
        event=EventResponse.model_validate(stored_event),
        matches=matches,
    )


@app.get("/alerts", response_model=list[AlertResponse])
def list_alerts(db: Session = Depends(get_db)) -> list[AlertResponse]:
    """Return all persisted alerts."""

    simulation_date = get_simulation_date(db)
    refresh_alert_states(db, simulation_date)
    db.commit()
    alerts = db.scalars(
        select(AlertModel).order_by(AlertModel.created_at, AlertModel.id)
    ).all()
    return [_alert_response(alert) for alert in alerts]


@app.get("/alerts/{alert_id}", response_model=AlertResponse)
def get_alert(alert_id: int, db: Session = Depends(get_db)) -> AlertResponse:
    """Return one persisted alert."""

    simulation_date = get_simulation_date(db)
    refresh_alert_states(db, simulation_date)
    alert = db.get(AlertModel, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found.")
    db.commit()
    return _alert_response(alert)


@app.post("/alerts/{alert_id}/review", response_model=AlertResponse)
def review_alert(
    alert_id: int,
    decision: HumanDecisionCreate,
    db: Session = Depends(get_db),
) -> AlertResponse:
    """Record a human decision and update the alert status."""

    alert = db.get(AlertModel, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found.")

    refresh_alert_states(db, get_simulation_date(db))
    alert.status = decision.decision
    db.add(
        HumanDecisionModel(
            alert_id=alert.id,
            decision=decision.decision,
            comment=decision.comment,
        )
    )
    try:
        db.commit()
        db.refresh(alert)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to save the alert review.",
        ) from exc
    return _alert_response(alert)


@app.post("/monitor/deadlines", response_model=DeadlineMonitorResponse)
def run_deadline_monitor(
    warning_days: int = Query(7, ge=0),
    db: Session = Depends(get_db),
) -> DeadlineMonitorResponse:
    """Create reviewable alerts for fixed deadlines within the warning window."""

    try:
        result = monitor_deadlines(
            db,
            warning_days=warning_days,
        )
    except DeadlineMonitoringError as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc
    return DeadlineMonitorResponse(
        obligations_checked=result.obligations_checked,
        alerts_created=result.alerts_created,
        skipped_obligations=result.skipped_obligations,
    )


@app.get("/simulation/date", response_model=SimulationDateResponse)
def read_simulation_date(db: Session = Depends(get_db)) -> SimulationDateResponse:
    """Return the persisted demo simulation date."""

    simulation_date = get_simulation_date(db)
    refresh_alert_states(db, simulation_date)
    db.commit()
    return SimulationDateResponse(simulation_date=simulation_date)


def _save_simulation_change(db: Session, simulation_date: date) -> date:
    """Persist a clock change and bring fixed-deadline alerts into the window."""

    try:
        monitor_deadlines(
            db,
            warning_days=7,
            simulation_date=simulation_date,
            commit=False,
        )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to update the simulation clock.",
        ) from exc
    return simulation_date


@app.post("/simulation/advance", response_model=SimulationDateResponse)
def advance_simulation(
    request: SimulationAdvanceRequest,
    db: Session = Depends(get_db),
) -> SimulationDateResponse:
    """Move the demo simulation date by a signed number of days."""

    simulation_date = advance_simulation_date(db, request.days)
    return SimulationDateResponse(
        simulation_date=_save_simulation_change(db, simulation_date)
    )


@app.post("/simulation/reset", response_model=SimulationDateResponse)
def reset_simulation(db: Session = Depends(get_db)) -> SimulationDateResponse:
    """Reset the demo simulation date and refresh deadline alerts."""

    simulation_date = reset_simulation_date(db)
    return SimulationDateResponse(
        simulation_date=_save_simulation_change(db, simulation_date)
    )


@app.get("/events/triggerable", response_model=TriggerableEventsResponse)
def list_triggerable_events(
    db: Session = Depends(get_db),
) -> TriggerableEventsResponse:
    """List distinct event types derived from stored obligation triggers."""

    obligations = db.scalars(
        select(ObligationModel)
        .where(
            ObligationModel.trigger_type.is_not(None),
            ObligationModel.trigger_type != "",
        )
        .order_by(ObligationModel.trigger_type, ObligationModel.id)
    ).all()
    grouped: dict[str, list[TriggerableObligationResponse]] = {}
    seen_by_trigger: dict[str, set[tuple[str, ...]]] = {}
    for obligation in obligations:
        trigger_type = obligation.trigger_type
        if trigger_type is None:
            continue
        key = obligation_key(obligation)
        if key in seen_by_trigger.setdefault(trigger_type, set()):
            continue
        seen_by_trigger[trigger_type].add(key)
        grouped.setdefault(trigger_type, []).append(
            TriggerableObligationResponse(
                obligation_id=obligation.id,
                required_action=obligation.required_action,
                time_constraint_type=obligation.time_constraint_type,
                time_value=obligation.time_value,
                time_unit=obligation.time_unit,
                fixed_deadline=obligation.fixed_deadline,
            )
        )

    return TriggerableEventsResponse(
        triggerable_events=[
            TriggerableEventResponse(event_type=event_type, obligations=related)
            for event_type, related in grouped.items()
        ]
    )


@app.post("/events/trigger", response_model=TriggerEventResponse)
def trigger_event(
    request: TriggerEventCreate,
    db: Session = Depends(get_db),
) -> TriggerEventResponse:
    """Create and process one event using the current simulation date."""

    has_trigger = db.scalar(
        select(ObligationModel.id).where(
            ObligationModel.trigger_type == request.event_type,
        )
    )
    if has_trigger is None:
        raise HTTPException(
            status_code=404,
            detail="No stored obligation is triggerable by this event_type.",
        )

    simulation_date = get_simulation_date(db)
    stored_event = EventModel(
        external_id=f"SIM-{uuid4().hex.upper()}",
        event_type=request.event_type,
        occurred_at=datetime.combine(simulation_date, time.min),
        description=request.description,
        source="simulation",
    )
    db.add(stored_event)
    try:
        db.flush()
        match_result = match_event(db, stored_event)
        matches = _event_matches(stored_event, match_result.obligations)
        refresh_alert_states(db, simulation_date)
        alert_ids = [alert.id for alert in match_result.alerts]
        db.commit()
        db.refresh(stored_event)
        alerts = (
            db.scalars(
                select(AlertModel)
                .where(AlertModel.id.in_(alert_ids))
                .order_by(AlertModel.id)
            ).all()
            if alert_ids
            else []
        )
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Unable to create a unique triggered event.",
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to save the triggered event.",
        ) from exc

    return TriggerEventResponse(
        event=EventResponse.model_validate(stored_event),
        matches=matches,
        alerts=[_alert_response(alert) for alert in alerts],
    )


@app.get("/events", response_model=list[EventResponse])
def list_events(db: Session = Depends(get_db)) -> list[EventResponse]:
    """Return all stored events."""

    events = db.scalars(
        select(EventModel).order_by(EventModel.created_at, EventModel.id)
    ).all()
    return [EventResponse.model_validate(event) for event in events]


@app.get("/events/{event_id}", response_model=EventResponse)
def get_event(event_id: int, db: Session = Depends(get_db)) -> EventResponse:
    """Return one stored event."""

    event = db.get(EventModel, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found.")
    return EventResponse.model_validate(event)


@app.get("/documents", response_model=list[DocumentSummary])
def list_documents(db: Session = Depends(get_db)) -> list[DocumentSummary]:
    """Return all stored documents."""

    documents = db.scalars(
        select(DocumentModel).order_by(DocumentModel.created_at, DocumentModel.id)
    ).all()
    return [DocumentSummary.model_validate(document) for document in documents]


@app.get("/documents/{document_id}", response_model=StoredDocument)
def get_document(document_id: int, db: Session = Depends(get_db)) -> StoredDocument:
    """Return one stored document with all extracted obligations."""

    document = db.get(DocumentModel, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return StoredDocument.model_validate(document)


@app.get("/obligations", response_model=list[StoredObligation])
def list_obligations(db: Session = Depends(get_db)) -> list[StoredObligation]:
    """Return all stored obligations."""

    obligations = db.scalars(
        select(ObligationModel).order_by(
            ObligationModel.created_at,
            ObligationModel.id,
        )
    ).all()
    return [StoredObligation.model_validate(obligation) for obligation in obligations]


@app.get("/obligations/{obligation_id}", response_model=StoredObligation)
def get_obligation(
    obligation_id: int,
    db: Session = Depends(get_db),
) -> StoredObligation:
    """Return one stored obligation."""

    obligation = db.get(ObligationModel, obligation_id)
    if obligation is None:
        raise HTTPException(status_code=404, detail="Obligation not found.")
    return StoredObligation.model_validate(obligation)
