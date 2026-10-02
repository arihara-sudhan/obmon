"""Minimal Streamlit presentation layer for the OBMON API."""

from __future__ import annotations

import html
import os
from datetime import date, datetime, time
from typing import Any

import requests
import streamlit as st


API_URL = os.getenv("OBMON_API_URL", "http://127.0.0.1:8000").rstrip("/")
REQUEST_TIMEOUT_SECONDS = 30
UPLOAD_TIMEOUT_SECONDS = 120


st.set_page_config(
    page_title="OBMON",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="collapsed",
)


st.markdown(
    """
    <style>
    :root {
        --obmon-black: #050705;
        --obmon-panel: #0a0f0a;
        --obmon-panel-strong: #0d140d;
        --obmon-green: #35e875;
        --obmon-green-soft: #183d25;
        --obmon-text: #f1f5f1;
        --obmon-muted: #a9b4aa;
    }

    .stApp,
    [data-testid="stAppViewContainer"],
    [data-testid="stHeader"] {
        background: var(--obmon-black);
        color: var(--obmon-text);
    }

    [data-testid="stSidebar"] {
        background: var(--obmon-black);
        border-right: 1px solid var(--obmon-green-soft);
    }

    .block-container {
        max-width: 1180px;
        padding-top: 2.5rem;
        padding-bottom: 3rem;
    }

    .obmon-header {
        border-bottom: 1px solid var(--obmon-green-soft);
        margin-bottom: 1.5rem;
        padding-bottom: 1.35rem;
    }

    .obmon-kicker,
    .obmon-section-label,
    .obmon-card-label {
        color: var(--obmon-green);
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.14em;
        text-transform: uppercase;
    }

    .obmon-title {
        color: var(--obmon-text);
        font-size: 2.25rem;
        font-weight: 700;
        letter-spacing: -0.03em;
        line-height: 1.1;
        margin: 0.25rem 0 0.35rem;
    }

    .obmon-subtitle {
        color: var(--obmon-muted);
        font-size: 1rem;
        margin: 0;
    }

    .obmon-card {
        background: var(--obmon-panel);
        border: 1px solid var(--obmon-green-soft);
        border-radius: 0.45rem;
        margin: 0.75rem 0;
        padding: 1.1rem 1.2rem;
    }

    .obmon-card-title {
        color: var(--obmon-text);
        font-size: 1.05rem;
        font-weight: 650;
        margin: 0.2rem 0 0.9rem;
    }

    .obmon-grid {
        display: grid;
        gap: 0.9rem 1.5rem;
        grid-template-columns: repeat(3, minmax(0, 1fr));
    }

    .obmon-field-label {
        color: var(--obmon-muted);
        font-size: 0.72rem;
        letter-spacing: 0.05em;
        text-transform: uppercase;
    }

    .obmon-field-value {
        color: var(--obmon-text);
        font-size: 0.95rem;
        line-height: 1.45;
        margin-top: 0.2rem;
        overflow-wrap: anywhere;
    }

    .obmon-evidence {
        background: var(--obmon-panel-strong);
        border-left: 2px solid var(--obmon-green);
        color: var(--obmon-muted);
        line-height: 1.55;
        padding: 0.75rem 0.9rem;
        white-space: pre-wrap;
    }

    .obmon-notice {
        background: var(--obmon-panel);
        border-left: 2px solid var(--obmon-green);
        color: var(--obmon-text);
        margin: 0.8rem 0;
        padding: 0.75rem 0.9rem;
    }

    .obmon-muted {
        color: var(--obmon-muted);
    }

    [data-testid="stRadio"] label,
    [data-testid="stCheckbox"] label,
    [data-testid="stMarkdownContainer"] p,
    [data-testid="stMarkdownContainer"] li {
        color: var(--obmon-text);
    }

    div[role="radiogroup"] {
        display: flex;
        gap: 0.35rem;
        justify-content: flex-start;
        width: max-content;
        max-width: 100%;
    }

    div[role="radiogroup"] label {
        flex: 0 0 auto;
        background: var(--obmon-panel);
        border: 1px solid transparent;
        border-radius: 0.35rem;
        padding: 0.4rem 0.75rem;
    }

    div[role="radiogroup"] label:has(input:checked) {
        border-color: var(--obmon-green);
    }

    input,
    textarea,
    [data-baseweb="select"] > div,
    [data-baseweb="input"] > div,
    [data-testid="stFileUploaderDropzone"] {
        background: var(--obmon-panel) !important;
        border-color: var(--obmon-green-soft) !important;
        color: var(--obmon-text) !important;
    }

    input:focus,
    textarea:focus,
    [data-baseweb="input"] > div:focus-within {
        border-color: var(--obmon-green) !important;
        box-shadow: 0 0 0 1px var(--obmon-green) !important;
    }

    .stButton > button,
    .stFormSubmitButton > button {
        background: var(--obmon-green);
        border: 1px solid var(--obmon-green);
        border-radius: 0.35rem;
        color: #000000;
        font-weight: 700;
    }

    .stButton > button:hover,
    .stFormSubmitButton > button:hover {
        background: #6af29b;
        border-color: #6af29b;
        color: #000000;
    }

    .stButton > button[kind="secondary"] {
        background: var(--obmon-panel);
        border-color: var(--obmon-green-soft);
        color: #000000;
    }

    [data-testid="stExpander"] {
        background: var(--obmon-panel);
        border: 1px solid var(--obmon-green-soft);
        border-radius: 0.35rem;
    }

    [data-testid="stMetric"] {
        background: var(--obmon-panel);
        border: 1px solid var(--obmon-green-soft);
        padding: 0.85rem 1rem;
    }

    [data-testid="stMetricLabel"] {
        color: var(--obmon-muted) !important;
    }

    [data-testid="stMetricValue"] {
        color: var(--obmon-green) !important;
    }

    hr {
        border-color: var(--obmon-green-soft);
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _safe(value: Any) -> str:
    """Escape API content before putting it into a small HTML card."""

    return html.escape("" if value is None else str(value))


def _show_notice(message: str) -> None:
    st.markdown(f'<div class="obmon-notice">{_safe(message)}</div>', unsafe_allow_html=True)


def _display_date(value: Any) -> str:
    try:
        parsed = date.fromisoformat(str(value))
        return parsed.strftime("%B %d, %Y").replace(" 0", " ")
    except ValueError:
        return str(value)


def _load_simulation_date() -> str | None:
    ok, payload, error = _api_request("GET", "/simulation/date")
    if not ok:
        _show_notice(error or "Unable to load the simulation date.")
        return None
    simulation_date = payload.get("simulation_date")
    if simulation_date:
        st.session_state["simulation_date"] = simulation_date
    return simulation_date


def _render_simulation_controls() -> None:
    simulation_date = _load_simulation_date()
    if not simulation_date:
        return

    st.markdown(
        f"""
        <div class="obmon-card">
          <div class="obmon-card-label">Simulation Date</div>
          <div class="obmon-card-title">{_safe(_display_date(simulation_date))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    previous_col, advance_col, reset_col, _ = st.columns([1.25, 1.25, 0.8, 5.5])
    with previous_col:
        previous = st.button("Previous Day", type="secondary", key="previous_day")
    with advance_col:
        advance = st.button("Advance 1 Day", type="primary", key="advance_day")
    with reset_col:
        reset = st.button("Reset", type="secondary", key="reset_simulation")

    if previous or advance:
        days = -1 if previous else 1
        ok, _, error = _api_request(
            "POST",
            "/simulation/advance",
            json={"days": days},
        )
        if ok:
            st.rerun()
        _show_notice(error or "Unable to advance the simulation date.")
    if reset:
        ok, _, error = _api_request("POST", "/simulation/reset")
        if ok:
            st.rerun()
        _show_notice(error or "Unable to reset the simulation date.")


def _api_request(
    method: str,
    path: str,
    *,
    timeout: int = REQUEST_TIMEOUT_SECONDS,
    **kwargs: Any,
) -> tuple[bool, Any, str | None]:
    """Call the backend and return success, decoded payload, and an error."""

    try:
        response = requests.request(
            method,
            f"{API_URL}{path}",
            timeout=timeout,
            **kwargs,
        )
    except requests.RequestException as exc:
        return False, None, f"Backend unavailable: {exc}"

    try:
        payload = response.json()
    except ValueError:
        payload = None

    if response.ok:
        return True, payload, None

    if isinstance(payload, dict):
        detail = payload.get("detail")
        if detail:
            return False, payload, str(detail)
    return False, payload, f"Backend returned HTTP {response.status_code}."


def _format_time_requirement(obligation: dict[str, Any]) -> str:
    constraint_type = obligation.get("time_constraint_type")
    value = obligation.get("time_value")
    unit = str(obligation.get("time_unit") or "").replace("_", " ")
    if constraint_type == "relative_deadline":
        return f"{value} {unit}".strip() if value is not None else "Relative deadline"
    if constraint_type == "fixed_deadline":
        fixed_deadline = str(obligation.get("fixed_deadline") or "Fixed deadline")
        try:
            parsed = datetime.fromisoformat(fixed_deadline)
            return parsed.strftime("%B %d, %Y").replace(" 0", " ")
        except ValueError:
            return fixed_deadline
    if constraint_type == "minimum_duration":
        return f"At least {value} {unit}".strip() if value is not None else "Minimum duration"
    if constraint_type == "maximum_duration":
        return f"At most {value} {unit}".strip() if value is not None else "Maximum duration"
    if constraint_type == "ambiguous":
        return "Requires human interpretation"
    return "No explicit time requirement"


def _format_confidence(value: Any) -> str:
    try:
        return f"{float(value):.0%}"
    except (TypeError, ValueError):
        return "—"


def _render_obligation(obligation: dict[str, Any], *, title: str | None = None) -> None:
    heading = title or obligation.get("obligation_type") or "Obligation"
    trigger = obligation.get("trigger_type") or "None"
    review = "Required" if obligation.get("requires_human_review") else "Not required"
    st.markdown(
        f"""
        <div class="obmon-card">
          <div class="obmon-card-label">Obligation Type</div>
          <div class="obmon-card-title">{_safe(heading)}</div>
          <div class="obmon-grid">
            <div><div class="obmon-field-label">Trigger</div><div class="obmon-field-value">{_safe(trigger)}</div></div>
            <div><div class="obmon-field-label">Required Action</div><div class="obmon-field-value">{_safe(obligation.get("required_action"))}</div></div>
            <div><div class="obmon-field-label">Time Requirement</div><div class="obmon-field-value">{_safe(_format_time_requirement(obligation))}</div></div>
            <div><div class="obmon-field-label">Source Page</div><div class="obmon-field-value">{_safe(obligation.get("page_number"))}</div></div>
            <div><div class="obmon-field-label">Confidence</div><div class="obmon-field-value">{_safe(_format_confidence(obligation.get("confidence")))}</div></div>
            <div><div class="obmon-field-label">Human Review Required</div><div class="obmon-field-value">{_safe(review)}</div></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.expander("Evidence", expanded=False):
        st.markdown(
            f'<div class="obmon-evidence">{_safe(obligation.get("evidence_text"))}</div>',
            unsafe_allow_html=True,
        )


def _render_alert_card(alert: dict[str, Any]) -> None:
    deadline = alert.get("computed_deadline") or "No computed deadline"
    event_type = alert.get("event_type")
    event_occurred_at = alert.get("event_occurred_at")
    if event_type and event_occurred_at:
        try:
            triggered_by = (
                f"{event_type} on "
                f"{_display_date(event_occurred_at[:10])}"
            )
        except (IndexError, TypeError):
            triggered_by = event_type
    else:
        triggered_by = "Fixed deadline monitoring"

    days_remaining = alert.get("days_remaining")
    days_overdue = alert.get("days_overdue") or 0
    if days_remaining is None:
        time_remaining = "Not applicable"
    elif days_remaining > 0:
        time_remaining = f"{days_remaining} day{'s' if days_remaining != 1 else ''}"
    elif days_remaining == 0:
        time_remaining = "Due today"
    else:
        time_remaining = (
            f"{days_overdue} day{'s' if days_overdue != 1 else ''} overdue"
        )
    deadline_state = str(alert.get("deadline_state") or "not_applicable")
    deadline_state_label = deadline_state.replace("_", " ").title()
    review_status = alert.get("review_status") or alert.get("status")
    st.markdown(
        f"""
        <div class="obmon-card">
          <div class="obmon-card-label">{_safe(alert.get("alert_type"))}</div>
          <div class="obmon-card-title">{_safe(alert.get("required_action"))}</div>
          <div class="obmon-grid">
            <div><div class="obmon-field-label">Triggered By</div><div class="obmon-field-value">{_safe(triggered_by)}</div></div>
            <div><div class="obmon-field-label">Deadline</div><div class="obmon-field-value">{_safe(deadline)}</div></div>
            <div><div class="obmon-field-label">Time Remaining</div><div class="obmon-field-value">{_safe(time_remaining)}</div></div>
            <div><div class="obmon-field-label">Deadline State</div><div class="obmon-field-value">{_safe(deadline_state_label)}</div></div>
            <div><div class="obmon-field-label">Review Status</div><div class="obmon-field-value">{_safe(review_status)}</div></div>
            <div><div class="obmon-field-label">Alert Type</div><div class="obmon-field-value">{_safe(alert.get("alert_type"))}</div></div>
          </div>
          <div class="obmon-field-label" style="margin-top: 0.9rem;">Reason</div>
          <div class="obmon-field-value">{_safe(alert.get("reason"))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.expander("Evidence", expanded=False):
        st.markdown(
            f'<div class="obmon-evidence">{_safe(alert.get("evidence_text"))}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="obmon-muted">Source Page: {_safe(alert.get("evidence_page"))}</div>',
            unsafe_allow_html=True,
        )


def _render_documents() -> None:
    st.markdown('<div class="obmon-section-label">Documents</div>', unsafe_allow_html=True)
    st.markdown("Upload a PDF to extract and store its obligations.")
    uploaded_file = st.file_uploader("PDF document", type=["pdf"], label_visibility="collapsed")

    if st.button("Extract Obligations", type="primary", disabled=uploaded_file is None):
        files = {
            "file": (
                uploaded_file.name,
                uploaded_file.getvalue(),
                uploaded_file.type or "application/pdf",
            )
        }
        ok, payload, error = _api_request(
            "POST",
            "/documents/extract-obligations",
            files=files,
            timeout=UPLOAD_TIMEOUT_SECONDS,
        )
        if ok:
            st.session_state["extraction_result"] = payload
        else:
            _show_notice(error or "Extraction failed.")

    result = st.session_state.get("extraction_result")
    if not result:
        return
    st.markdown(
        f'<div class="obmon-muted">Stored document: {_safe(result.get("filename"))}</div>',
        unsafe_allow_html=True,
    )
    obligations = result.get("obligations", [])
    if not obligations:
        _show_notice("No obligations were found in this document.")
        return
    for obligation in obligations:
        _render_obligation(obligation)


def _readable_event_type(event_type: str) -> str:
    return event_type.replace("_", " ").title()


def _triggerable_time_requirement(obligation: dict[str, Any]) -> str:
    constraint_type = obligation.get("time_constraint_type")
    requirement = _format_time_requirement(obligation)
    if constraint_type == "relative_deadline":
        return f"Within {requirement}"
    if constraint_type == "minimum_duration":
        return f"At least {requirement.removeprefix('At least ')}"
    if constraint_type == "maximum_duration":
        return f"At most {requirement.removeprefix('At most ')}"
    return requirement


def _render_trigger_result(result: dict[str, Any]) -> None:
    event = result.get("event", {})
    st.markdown('<div class="obmon-section-label">Event Created</div>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="obmon-card">
          <div class="obmon-card-label">Triggered Event</div>
          <div class="obmon-card-title">{_safe(_readable_event_type(event.get("event_type", "")))}</div>
          <div class="obmon-field-value">{_safe(event.get("occurred_at"))}</div>
          <div class="obmon-muted">{_safe(event.get("description") or "No description")}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="obmon-section-label">Matched Obligations</div>', unsafe_allow_html=True)
    matches = result.get("matches", [])
    if not matches:
        _show_notice("No obligations matched this event.")
    for match in matches:
        st.markdown(
            f"""
            <div class="obmon-card">
              <div class="obmon-card-title">{_safe(match.get("required_action"))}</div>
              <div class="obmon-grid">
                <div><div class="obmon-field-label">Time Requirement</div><div class="obmon-field-value">{_safe(_triggerable_time_requirement(match))}</div></div>
                <div><div class="obmon-field-label">Computed Deadline</div><div class="obmon-field-value">{_safe(match.get("computed_deadline") or "Not applicable")}</div></div>
                <div><div class="obmon-field-label">Source Page</div><div class="obmon-field-value">{_safe(match.get("page_number"))}</div></div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

def _render_events() -> None:
    st.markdown('<div class="obmon-section-label">Events</div>', unsafe_allow_html=True)
    st.markdown("Trigger operational events derived from stored obligation conditions.")

    triggerable_ok, triggerable_payload, triggerable_error = _api_request(
        "GET",
        "/events/triggerable",
    )
    if not triggerable_ok:
        _show_notice(triggerable_error or "Unable to load triggerable events.")
    else:
        triggerable_events = triggerable_payload.get("triggerable_events", [])
        st.markdown('<div class="obmon-section-label">Triggerable Events</div>', unsafe_allow_html=True)
        if not triggerable_events:
            _show_notice("Upload a document with event-triggered obligations to enable event triggering.")
        for triggerable in triggerable_events:
            event_type = triggerable.get("event_type", "")
            st.markdown(
                f"""
                <div class="obmon-card">
                  <div class="obmon-card-label">Event Type</div>
                  <div class="obmon-card-title">{_safe(_readable_event_type(event_type))}</div>
                  <div class="obmon-muted">{_safe(event_type)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            for obligation in triggerable.get("obligations", []):
                st.markdown(
                    f"""
                    <div class="obmon-card">
                      <div class="obmon-field-label">Will Activate</div>
                      <div class="obmon-field-value">{_safe(obligation.get("required_action"))}</div>
                      <div class="obmon-field-label" style="margin-top: 0.65rem;">Time Requirement</div>
                      <div class="obmon-field-value">{_safe(_triggerable_time_requirement(obligation))}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            description = st.text_input(
                "Optional description",
                key=f"trigger_description_{event_type}",
                placeholder="Production operational event detected",
            )
            if st.button(
                "Trigger Event",
                type="primary",
                key=f"trigger_event_{event_type}",
            ):
                ok, payload, error = _api_request(
                    "POST",
                    "/events/trigger",
                    json={
                        "event_type": event_type,
                        "description": description or None,
                    },
                )
                if ok:
                    st.session_state["last_trigger_result"] = payload
                    st.rerun()
                _show_notice(error or "Event triggering failed.")

    trigger_result = st.session_state.get("last_trigger_result")
    if trigger_result:
        _render_trigger_result(trigger_result)

    st.markdown('<div class="obmon-section-label">Event History</div>', unsafe_allow_html=True)
    events_ok, events, events_error = _api_request("GET", "/events")
    if not events_ok:
        _show_notice(events_error or "Unable to load event history.")
    elif events:
        for event in events:
            st.markdown(
                f"""
                <div class="obmon-card">
                  <div class="obmon-card-label">{_safe(_readable_event_type(event.get("event_type", "")))}</div>
                  <div class="obmon-card-title">{_safe(event.get("occurred_at"))}</div>
                  <div class="obmon-field-value">{_safe(event.get("description") or "No description")}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    elif events_ok:
        _show_notice("No events have been created.")

    with st.form("event_form", clear_on_submit=False):
        col1, col2 = st.columns(2)
        with col1:
            external_id = st.text_input("External ID", placeholder="INC-001")
            event_type = st.text_input("Event Type", placeholder="event_type_from_triggerable_list")
            simulation_date = st.session_state.get("simulation_date")
            default_date = (
                date.fromisoformat(simulation_date)
                if simulation_date
                else date(2026, 10, 2)
            )
            occurred_date = st.date_input("Occurred Date", value=default_date)
        with col2:
            occurred_time = st.time_input("Occurred Time", value=time(0, 0))
            description = st.text_area("Description", height=100)
            source = st.text_input("Source", placeholder="internal")
        submitted = st.form_submit_button("Create Event")

    if submitted:
        if not external_id.strip() or not event_type.strip():
            _show_notice("External ID and Event Type are required.")
        else:
            payload = {
                "external_id": external_id.strip(),
                "event_type": event_type.strip(),
                "occurred_at": datetime.combine(occurred_date, occurred_time).isoformat(),
                "description": description or None,
                "source": source or None,
            }
            ok, response, error = _api_request("POST", "/events", json=payload)
            if ok:
                st.session_state["last_event_result"] = response
            else:
                _show_notice(error or "Event creation failed.")

    result = st.session_state.get("last_event_result")
    if not result:
        return
    event = result.get("event", {})
    st.markdown(
        f'<div class="obmon-muted">Stored event: {_safe(event.get("external_id"))}</div>',
        unsafe_allow_html=True,
    )
    matches = result.get("matches", [])
    st.markdown('<div class="obmon-section-label">Matched Obligations</div>', unsafe_allow_html=True)
    if matches:
        for match in matches:
            _render_obligation(
                {
                    "obligation_type": "Matched obligation",
                    "trigger_type": match.get("trigger_type"),
                    "required_action": match.get("required_action"),
                    "time_constraint_type": match.get("time_constraint_type", "none"),
                    "time_value": match.get("time_value"),
                    "time_unit": match.get("time_unit"),
                    "fixed_deadline": match.get("fixed_deadline"),
                    "page_number": match.get("page_number"),
                    "evidence_text": match.get("evidence_text"),
                    "confidence": None,
                    "requires_human_review": False,
                }
            )
    else:
        _show_notice("No obligations matched this event.")

def _render_deadline_monitor() -> None:
    st.markdown('<div class="obmon-section-label">Deadline Monitor</div>', unsafe_allow_html=True)
    st.markdown("Check fixed deadlines within a deterministic warning window.")
    _render_simulation_controls()
    warning_days = st.number_input("Warning Window", min_value=0, value=7, step=1)
    if st.button("Run Monitor", type="primary"):
        ok, payload, error = _api_request(
            "POST",
            f"/monitor/deadlines?warning_days={int(warning_days)}",
        )
        if ok:
            st.session_state["monitor_result"] = payload
        else:
            _show_notice(error or "Deadline monitoring failed.")

    result = st.session_state.get("monitor_result")
    if result:
        col1, col2, col3 = st.columns(3)
        col1.metric("Obligations Checked", result.get("obligations_checked", 0))
        col2.metric("Alerts Created", result.get("alerts_created", 0))
        col3.metric("Skipped", result.get("skipped_obligations", 0))


def _review_alert(alert_id: int, decision: str, comment: str) -> tuple[bool, str | None]:
    ok, _, error = _api_request(
        "POST",
        f"/alerts/{alert_id}/review",
        json={"decision": decision, "comment": comment or None},
    )
    return ok, error


def _render_alerts() -> None:
    st.markdown('<div class="obmon-section-label">Alerts</div>', unsafe_allow_html=True)
    st.markdown("Review obligations matched by events or approaching fixed deadlines.")
    ok, alerts, error = _api_request("GET", "/alerts")
    if not ok:
        _show_notice(error or "Unable to load alerts.")
        return
    if not alerts:
        _show_notice("No alerts have been created.")
        return

    for alert in alerts:
        _render_alert_card(alert)
        if alert.get("status") == "pending_review":
            comment = st.text_area(
                "Review comment",
                key=f"review_comment_{alert['id']}",
                placeholder="Optional",
                height=70,
            )
            confirm_col, reject_col = st.columns(2)
            with confirm_col:
                if st.button(
                    "Confirm",
                    key=f"confirm_{alert['id']}",
                    type="primary",
                ):
                    success, review_error = _review_alert(alert["id"], "confirmed", comment)
                    if success:
                        st.rerun()
                    _show_notice(review_error or "Review could not be saved.")
            with reject_col:
                if st.button(
                    "Reject",
                    key=f"reject_{alert['id']}",
                    type="secondary",
                ):
                    success, review_error = _review_alert(alert["id"], "rejected", comment)
                    if success:
                        st.rerun()
                    _show_notice(review_error or "Review could not be saved.")


st.markdown(
    """
    <div class="obmon-header">
      <div class="obmon-kicker">OBMON</div>
      <div class="obmon-title">Obligation Monitoring &amp; Alerting</div>
      <p class="obmon-subtitle">A focused operational view of documents, events, deadlines, and reviewable alerts.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

section = st.radio(
    "Navigation",
    ["Documents", "Events", "Deadline Monitor", "Alerts"],
    horizontal=True,
    label_visibility="collapsed",
)

if section == "Documents":
    _render_documents()
elif section == "Events":
    _render_events()
elif section == "Deadline Monitor":
    _render_deadline_monitor()
else:
    _render_alerts()
