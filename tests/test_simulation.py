import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Alert as AlertModel
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


def _seed_relative_obligation() -> None:
    db = TestingSessionLocal()
    try:
        document = DocumentModel(filename="demo-policy.pdf", total_pages=1)
        db.add(
            ObligationModel(
                document=document,
                obligation_type="notification",
                trigger_type="security_incident",
                required_action="Notify the Customer in writing",
                time_constraint_type="relative_deadline",
                time_value=5,
                time_unit="calendar_days",
                evidence_text=(
                    "If a security incident occurs, the Supplier must notify "
                    "the Customer in writing within five calendar days."
                ),
                page_number=1,
                confidence=0.95,
                requires_human_review=False,
            )
        )
        db.commit()
    finally:
        db.close()


def test_simulation_clock_is_persisted_and_resettable(client) -> None:
    assert client.get("/simulation/date").json() == {
        "simulation_date": "2026-10-02"
    }
    assert client.post("/simulation/advance", json={"days": 1}).json() == {
        "simulation_date": "2026-10-03"
    }
    assert client.post("/simulation/advance", json={"days": -2}).json() == {
        "simulation_date": "2026-10-01"
    }
    assert client.post("/simulation/reset").json() == {
        "simulation_date": "2026-10-02"
    }


def test_triggerable_events_come_from_obligations_and_can_repeat(client) -> None:
    _seed_relative_obligation()

    triggerable = client.get("/events/triggerable")
    first = client.post(
        "/events/trigger",
        json={
            "event_type": "security_incident",
            "description": "Production security incident detected",
        },
    )
    second = client.post(
        "/events/trigger",
        json={"event_type": "security_incident"},
    )

    assert triggerable.status_code == 200
    assert triggerable.json()["triggerable_events"] == [
        {
            "event_type": "security_incident",
            "obligations": [
                {
                    "obligation_id": 1,
                    "required_action": "Notify the Customer in writing",
                    "time_constraint_type": "relative_deadline",
                    "time_value": 5,
                    "time_unit": "calendar_days",
                    "fixed_deadline": None,
                }
            ],
        }
    ]
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["event"]["event_type"] == "security_incident"
    assert first.json()["event"]["occurred_at"] == "2026-10-02T00:00:00"
    assert first.json()["matches"][0]["computed_deadline"] == "2026-10-07T00:00:00"
    assert len(first.json()["alerts"]) == 1
    assert first.json()["event"]["external_id"] != second.json()["event"]["external_id"]

    db = TestingSessionLocal()
    try:
        assert db.scalar(select(func.count()).select_from(AlertModel)) == 2
    finally:
        db.close()


def test_event_alert_state_follows_simulation_clock(client) -> None:
    _seed_relative_obligation()
    client.post(
        "/events/trigger",
        json={"event_type": "security_incident"},
    )

    assert client.get("/alerts").json()[0]["deadline_state"] == "upcoming"
    assert client.get("/alerts").json()[0]["days_remaining"] == 5

    client.post("/simulation/advance", json={"days": 3})
    assert client.get("/alerts").json()[0]["deadline_state"] == "approaching"
    assert client.get("/alerts").json()[0]["days_remaining"] == 2

    client.post("/simulation/advance", json={"days": 1})
    assert client.get("/alerts").json()[0]["deadline_state"] == "urgent"
    client.post("/simulation/advance", json={"days": 1})
    assert client.get("/alerts").json()[0]["deadline_state"] == "due_today"
    client.post("/simulation/advance", json={"days": 1})

    alert = client.get("/alerts").json()[0]
    assert alert["deadline_state"] == "overdue"
    assert alert["days_overdue"] == 1
    assert alert["review_status"] == "pending_review"
