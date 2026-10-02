import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Document as DocumentModel
from app.models import HumanDecision as HumanDecisionModel
from app.models import Obligation as ObligationModel


TEST_ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=TEST_ENGINE, autoflush=False, autocommit=False)


@pytest.fixture
def client():
    Base.metadata.drop_all(bind=TEST_ENGINE)
    Base.metadata.create_all(bind=TEST_ENGINE)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _seed_obligation() -> None:
    db = TestingSessionLocal()
    try:
        document = DocumentModel(filename="policy.pdf", total_pages=3)
        db.add(
            ObligationModel(
                document=document,
                obligation_type="notification",
                trigger_type="security_incident",
                required_action="Notify the customer in writing",
                time_constraint_type="relative_deadline",
                time_value=5,
                time_unit="calendar_days",
                evidence_text="The Supplier must notify the customer within 5 calendar days.",
                page_number=3,
                confidence=0.95,
                requires_human_review=False,
            )
        )
        db.commit()
    finally:
        db.close()


def _create_event(client):
    return client.post(
        "/events",
        json={
            "external_id": "INC-001",
            "event_type": "security_incident",
            "occurred_at": "2026-10-02T10:00:00",
            "description": "Production security incident detected",
            "source": "internal",
        },
    )


def test_matching_event_creates_pending_review_alert(client) -> None:
    _seed_obligation()

    event_response = _create_event(client)
    alert_response = client.get("/alerts")

    assert event_response.status_code == 200
    assert alert_response.status_code == 200
    alerts = alert_response.json()
    assert len(alerts) == 1
    assert alerts[0]["alert_type"] == "event_triggered"
    assert alerts[0]["reason"] == (
        "A security_incident event matched this obligation."
    )
    assert alerts[0]["required_action"] == "Notify the customer in writing"
    assert alerts[0]["computed_deadline"] == "2026-10-07T10:00:00"
    assert alerts[0]["evidence_text"] == (
        "The Supplier must notify the customer within 5 calendar days."
    )
    assert alerts[0]["evidence_page"] == 3
    assert alerts[0]["status"] == "pending_review"

    alert_id = alerts[0]["id"]
    assert client.get(f"/alerts/{alert_id}").json()["id"] == alert_id


def test_alert_review_saves_decision_and_updates_status(client) -> None:
    _seed_obligation()
    _create_event(client)
    alert_id = client.get("/alerts").json()[0]["id"]

    response = client.post(
        f"/alerts/{alert_id}/review",
        json={
            "decision": "confirmed",
            "comment": "This obligation is applicable.",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"
    assert client.get(f"/alerts/{alert_id}").json()["status"] == "confirmed"

    db = TestingSessionLocal()
    try:
        decision = db.scalar(
            select(HumanDecisionModel).where(
                HumanDecisionModel.alert_id == alert_id,
            )
        )
        assert decision is not None
        assert decision.decision == "confirmed"
        assert decision.comment == "This obligation is applicable."
    finally:
        db.close()


def test_alert_review_only_accepts_confirmed_or_rejected(client) -> None:
    _seed_obligation()
    _create_event(client)
    alert_id = client.get("/alerts").json()[0]["id"]

    response = client.post(
        f"/alerts/{alert_id}/review",
        json={"decision": "resolved"},
    )

    assert response.status_code == 422
    assert client.get(f"/alerts/{alert_id}").json()["status"] == "pending_review"


def test_unmatched_event_creates_no_alert(client) -> None:
    _create_event(client)

    assert client.get("/alerts").json() == []
    assert client.get("/alerts/999").status_code == 404
