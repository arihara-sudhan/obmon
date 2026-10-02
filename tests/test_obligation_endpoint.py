import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.schemas import ObligationExtractionResult
from tests.pdf_factory import build_pdf
from tests.test_document_parser import text_page


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


def test_extract_obligations_endpoint_parses_pdf_and_persists_document(
    monkeypatch,
    client,
) -> None:
    expected = ObligationExtractionResult(has_obligations=False, obligations=[])
    captured = {}

    def fake_extract(document):
        captured["document"] = document
        return expected

    monkeypatch.setattr("app.main.extract_obligations", fake_extract)

    response = client.post(
        "/documents/extract-obligations",
        files={
            "file": (
                "uploaded.pdf",
                build_pdf([text_page("No required actions here.")]),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "document_id": 1,
        "filename": "uploaded.pdf",
        "obligations": [],
    }
    assert captured["document"].filename == "uploaded.pdf"
    assert captured["document"].pages[0].page_number == 1


def test_extract_obligations_endpoint_persists_obligation_and_supports_reads(
    monkeypatch,
    client,
) -> None:
    expected = ObligationExtractionResult(
        has_obligations=True,
        obligations=[
            {
                "obligation_type": "delivery",
                "trigger_type": None,
                "required_action": "Deliver the report",
                "time_constraint_type": "relative_deadline",
                "time_value": 10,
                "time_unit": "days",
                "fixed_deadline": None,
                "evidence_text": "The supplier must deliver the report within 10 days.",
                "page_number": 1,
                "confidence": 0.9,
                "requires_human_review": False,
            }
        ],
    )
    monkeypatch.setattr("app.main.extract_obligations", lambda document: expected)

    response = client.post(
        "/documents/extract-obligations",
        files={
            "file": (
                "uploaded.pdf",
                build_pdf([text_page("The supplier must deliver the report within 10 days.")]),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 200
    obligation_id = response.json()["obligations"][0]["id"]
    assert response.json()["document_id"] == 1
    assert response.json()["obligations"][0]["document_id"] == 1

    assert client.get("/documents").status_code == 200
    document_response = client.get("/documents/1")
    assert document_response.status_code == 200
    assert document_response.json()["obligations"][0]["id"] == obligation_id

    obligations_response = client.get("/obligations")
    assert obligations_response.status_code == 200
    assert obligations_response.json()[0]["id"] == obligation_id
    assert client.get(f"/obligations/{obligation_id}").status_code == 200


def test_extract_obligations_endpoint_rejects_non_pdf(client) -> None:
    response = client.post(
        "/documents/extract-obligations",
        files={"file": ("notes.txt", b"plain text", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Only PDF files are supported."
