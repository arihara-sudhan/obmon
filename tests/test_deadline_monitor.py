from datetime import datetime

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
from app.services.deadline_monitor import monitor_deadlines


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


def _seed_fixed_obligations() -> None:
    db = TestingSessionLocal()
    try:
        document = DocumentModel(filename="compliance.pdf", total_pages=2)
        db.add_all(
            [
                ObligationModel(
                    document=document,
                    obligation_type="reporting",
                    required_action="Submit quarterly compliance report",
                    time_constraint_type="fixed_deadline",
                    fixed_deadline="2026-10-10",
                    evidence_text="Submit the quarterly compliance report by October 10.",
                    page_number=1,
                    confidence=0.9,
                    requires_human_review=False,
                ),
                ObligationModel(
                    document=document,
                    obligation_type="reporting",
                    required_action="Submit annual compliance report",
                    time_constraint_type="fixed_deadline",
                    fixed_deadline="2026-11-01",
                    evidence_text="Submit the annual compliance report by November 1.",
                    page_number=2,
                    confidence=0.9,
                    requires_human_review=False,
                ),
            ]
        )
        db.commit()
    finally:
        db.close()


def test_deadline_monitor_creates_alert_for_deadline_in_warning_window(
    client,
    monkeypatch,
) -> None:
    _seed_fixed_obligations()
    fixed_now = datetime(2026, 10, 5)

    monkeypatch.setattr(
        "app.main.monitor_deadlines",
        lambda db, warning_days: monitor_deadlines(
            db,
            warning_days=warning_days,
            now=fixed_now,
        ),
    )

    response = client.post("/monitor/deadlines?warning_days=7")

    assert response.status_code == 200
    assert response.json() == {
        "obligations_checked": 2,
        "alerts_created": 1,
        "skipped_obligations": 1,
    }
    alerts = client.get("/alerts").json()
    assert len(alerts) == 1
    assert alerts[0]["alert_type"] == "deadline_approaching"
    assert alerts[0]["event_id"] is None
    assert alerts[0]["reason"] == (
        "Submit quarterly compliance report is due in 5 days."
    )
    assert alerts[0]["computed_deadline"] == "2026-10-10T00:00:00"
    assert alerts[0]["status"] == "pending_review"


def test_deadline_monitor_prevents_duplicate_active_alerts(client) -> None:
    _seed_fixed_obligations()
    db = TestingSessionLocal()
    try:
        first = monitor_deadlines(
            db,
            warning_days=7,
            now=datetime(2026, 10, 5),
        )
        second = monitor_deadlines(
            db,
            warning_days=7,
            now=datetime(2026, 10, 5),
        )
        alert_count = db.scalar(select(func.count()).select_from(AlertModel))
    finally:
        db.close()

    assert first.alerts_created == 1
    assert second.alerts_created == 0
    assert second.skipped_obligations == 2
    assert alert_count == 1


def test_deadline_monitor_respects_warning_days_and_validation(client) -> None:
    _seed_fixed_obligations()

    response = client.post("/monitor/deadlines?warning_days=3")
    invalid_response = client.post("/monitor/deadlines?warning_days=-1")

    assert response.status_code == 200
    assert response.json()["alerts_created"] == 0
    assert response.json()["skipped_obligations"] == 2
    assert invalid_response.status_code == 422
