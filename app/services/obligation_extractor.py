"""Gemini-backed obligation extraction service."""

import os

from app.schemas import ObligationExtractionResult, ParsedDocument

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency is installed in the app environment
    load_dotenv = None

try:
    from google import genai
    from google.genai import types
except ImportError:  # pragma: no cover - dependency is installed in the app environment
    genai = None
    types = None


if load_dotenv is not None:
    load_dotenv()


GEMINI_MODEL = "gemini-3.8-flash"


class ObligationExtractionError(Exception):
    """Raised when obligations cannot be extracted from a document."""


_EXTRACTION_PROMPT = """You extract actual contractual or business obligations from documents.

Extract every actual required action in the supplied document. One document may contain
zero, one, or many obligations. Extract the required action separately from the
condition that activates it. Never invent an obligation, trigger, deadline, duration,
or other missing information.

For each obligation:
- Preserve the exact relevant sentence or clause in evidence_text. It must be copied
  verbatim from the source, never paraphrased, and must not be empty.
- Preserve the correct source page_number for that exact evidence.
- If an event or condition activates the obligation, set trigger_type to a specific,
  concise lowercase snake_case condition derived from the text. Examples include
  security_incident, critical_service_outage_over_2_hours,
  security_incident_closed, and payment_overdue_30_days.
- Never use generic trigger_type values such as event, incident, trigger, or condition.
- If no reliable event trigger exists, set trigger_type to null. Do not invent one.

Classify time constraints carefully:
- "within five calendar days" means time_constraint_type="relative_deadline",
  with time_value=5 and time_unit="calendar_days".
- "no later than October 10, 2026" means time_constraint_type="fixed_deadline"
  and fixed_deadline="2026-10-10".
- "for at least ninety calendar days" usually means
  time_constraint_type="minimum_duration", with time_value=90 and
  time_unit="calendar_days". Do not treat a retention duration as an action due date.
- "within no more than 48 hours" means time_constraint_type="maximum_duration",
  with time_value=48 and time_unit="hours".
- "promptly", "reasonably", and "as soon as practicable" mean
  time_constraint_type="ambiguous" and requires_human_review=true.
- Use time_constraint_type="none" when no time requirement is stated.
- Set requires_human_review=true whenever the time requirement or obligation is unclear.

If no exact source evidence reliably supports an obligation, do not output that
obligation. If there are no obligations, return has_obligations=false and obligations=[].
Return only JSON matching the supplied response schema.

The document follows, with page boundaries marked explicitly:

"""


def _document_text(document: ParsedDocument) -> str:
    """Serialize parsed pages with boundaries that Gemini can cite accurately."""

    pages = [f"--- PAGE {page.page_number} ---\n{page.text}" for page in document.pages]
    return "\n\n".join(pages)


def _normalise_result(result: ObligationExtractionResult) -> ObligationExtractionResult:
    """Enforce invariants that are deterministic from the structured response."""

    obligations = [
        obligation.model_copy(update={"requires_human_review": True})
        if obligation.time_constraint_type == "ambiguous"
        else obligation
        for obligation in result.obligations
    ]
    return ObligationExtractionResult(
        has_obligations=bool(obligations),
        obligations=obligations,
    )


def extract_obligations(document: ParsedDocument) -> ObligationExtractionResult:
    """Extract obligations from parsed PDF text using Gemini structured output."""

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ObligationExtractionError("GEMINI_API_KEY is not configured.")
    if genai is None or types is None:
        raise ObligationExtractionError(
            "The google-genai package is not installed; run 'uv sync' first."
        )

    prompt = _EXTRACTION_PROMPT + _document_text(document)
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ObligationExtractionResult,
            ),
        )
        response_text = response.text
        if not response_text:
            raise ObligationExtractionError(
                "Gemini returned no structured obligation extraction result."
            )
        result = ObligationExtractionResult.model_validate_json(response_text)
    except ObligationExtractionError:
        raise
    except Exception as exc:
        raise ObligationExtractionError(
            "Gemini could not extract obligations from the document."
        ) from exc

    return _normalise_result(result)
