import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Document as DocumentModel
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


def _seed_matching_obligation() -> int:
    db = TestingSessionLocal()
    try:
        document = DocumentModel(filename="policy.pdf", total_pages=3)
        obligation = ObligationModel(
            document=document,
            obligation_type="notification",
            trigger_type="security_incident",
            required_action="Notify the customer in writing",
            time_constraint_type="relative_deadline",
            time_value=5,
            time_unit="calendar_days",
            fixed_deadline=None,
            evidence_text="The supplier must notify the customer within 5 calendar days.",
            page_number=3,
            confidence=0.95,
            requires_human_review=False,
        )
        db.add(obligation)
        db.commit()
        db.refresh(obligation)
        return obligation.id
    finally:
        db.close()


def _event_payload(external_id: str = "INC-001") -> dict[str, str]:
    return {
        "external_id": external_id,
        "event_type": "security_incident",
        "occurred_at": "2026-10-02T10:00:00",
        "description": "Production security incident detected",
        "source": "internal",
    }


def test_event_ingestion_matches_and_computes_calendar_day_deadline(client) -> None:
    obligation_id = _seed_matching_obligation()

    response = client.post("/events", json=_event_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["event"]["external_id"] == "INC-001"
    assert body["event"]["event_type"] == "security_incident"
    assert body["matches"] == [
        {
            "obligation_id": obligation_id,
            "required_action": "Notify the customer in writing",
            "trigger_type": "security_incident",
            "time_constraint_type": "relative_deadline",
            "time_value": 5,
            "time_unit": "calendar_days",
            "fixed_deadline": None,
            "computed_deadline": "2026-10-07T10:00:00",
            "evidence_text": "The supplier must notify the customer within 5 calendar days.",
            "page_number": 3,
        }
    ]


def test_event_ingestion_does_not_use_semantic_matching(client) -> None:
    _seed_matching_obligation()
    payload = _event_payload()
    payload["event_type"] = "security-incident"

    response = client.post("/events", json=payload)

    assert response.status_code == 200
    assert response.json()["matches"] == []


def test_event_external_id_must_be_unique(client) -> None:
    first = client.post("/events", json=_event_payload())
    second = client.post("/events", json=_event_payload())

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["detail"] == "An event with this external_id already exists."


def test_event_read_endpoints(client) -> None:
    created = client.post("/events", json=_event_payload())
    event_id = created.json()["event"]["id"]

    listed = client.get("/events")
    fetched = client.get(f"/events/{event_id}")

    assert listed.status_code == 200
    assert listed.json()[0]["id"] == event_id
    assert fetched.status_code == 200
    assert fetched.json()["external_id"] == "INC-001"
    assert client.get("/events/999").status_code == 404
