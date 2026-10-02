from fastapi.testclient import TestClient

from app.main import app
from tests.pdf_factory import build_pdf
from tests.test_document_parser import text_page


client = TestClient(app)


def test_parse_endpoint_returns_parsed_document() -> None:
    response = client.post(
        "/documents/parse",
        files={
            "file": (
                "uploaded.pdf",
                build_pdf([text_page("Endpoint text")]),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "filename": "uploaded.pdf",
        "total_pages": 1,
        "pages": [{"page_number": 1, "text": "Endpoint text"}],
    }


def test_parse_endpoint_rejects_non_pdf() -> None:
    response = client.post(
        "/documents/parse",
        files={"file": ("notes.txt", b"plain text", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Only PDF files are supported."
