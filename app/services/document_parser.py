"""PDF text extraction service."""

from pathlib import Path

import pdfplumber

from app.schemas import ParsedDocument, ParsedPage


class DocumentParsingError(Exception):
    """Raised when a PDF cannot be parsed into usable text."""


def parse_document(file_path: str | Path) -> ParsedDocument:
    """Extract non-empty page text from a PDF while preserving page numbers."""

    path = Path(file_path)

    try:
        with pdfplumber.open(path) as pdf:
            pages: list[ParsedPage] = []

            for page_number, page in enumerate(pdf.pages, start=1):
                text = page.extract_text()
                if text is None or not text.strip():
                    continue

                pages.append(
                    ParsedPage(
                        page_number=page_number,
                        text=text.strip(),
                    )
                )

            if not pages:
                raise DocumentParsingError(
                    "The PDF contains no extractable text; OCR may be required."
                )

            return ParsedDocument(
                filename=path.name,
                total_pages=len(pdf.pages),
                pages=pages,
            )
    except DocumentParsingError:
        raise
    except Exception as exc:
        raise DocumentParsingError(
            f"Unable to parse PDF '{path.name}': the file may be invalid or corrupt."
        ) from exc
