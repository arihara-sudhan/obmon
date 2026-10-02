from pathlib import Path

import pytest

from app.services.document_parser import DocumentParsingError, parse_document
from tests.pdf_factory import build_pdf


def text_page(text: str) -> bytes:
    return f"BT /F1 18 Tf 72 720 Td ({text}) Tj ET".encode()


def test_parse_valid_text_pdf(tmp_path: Path) -> None:
    pdf_path = tmp_path / "notice.pdf"
    pdf_path.write_bytes(build_pdf([text_page(" Hello world ")]))

    parsed = parse_document(pdf_path)

    assert parsed.filename == "notice.pdf"
    assert parsed.total_pages == 1
    assert parsed.pages[0].page_number == 1
    assert parsed.pages[0].text == "Hello world"


def test_parse_multiple_pages_preserves_page_numbers(tmp_path: Path) -> None:
    pdf_path = tmp_path / "multi-page.pdf"
    pdf_path.write_bytes(build_pdf([text_page("First"), text_page("Second")]))

    parsed = parse_document(pdf_path)

    assert parsed.total_pages == 2
    assert [(page.page_number, page.text) for page in parsed.pages] == [
        (1, "First"),
        (2, "Second"),
    ]


def test_parse_ignores_empty_page_but_keeps_original_number(tmp_path: Path) -> None:
    pdf_path = tmp_path / "with-empty-page.pdf"
    pdf_path.write_bytes(build_pdf([text_page("First"), b"", text_page("Third")]))

    parsed = parse_document(pdf_path)

    assert parsed.total_pages == 3
    assert [(page.page_number, page.text) for page in parsed.pages] == [
        (1, "First"),
        (3, "Third"),
    ]


def test_parse_invalid_pdf_raises_clear_error(tmp_path: Path) -> None:
    pdf_path = tmp_path / "broken.pdf"
    pdf_path.write_bytes(b"not a PDF")

    with pytest.raises(DocumentParsingError, match="invalid or corrupt"):
        parse_document(pdf_path)


def test_parse_pdf_with_no_extractable_text_mentions_ocr(tmp_path: Path) -> None:
    pdf_path = tmp_path / "scan.pdf"
    pdf_path.write_bytes(build_pdf([b"q 0 0 100 100 re S Q"]))

    with pytest.raises(DocumentParsingError, match="OCR may be required"):
        parse_document(pdf_path)
