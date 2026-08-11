"""
Request and response bodies for the case desk, its demo controls and its probes.

Every column comes back from the SQL warehouse as text, nulls included, so the case
fields are typed as strings rather than as dates and numbers they are not.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Case(BaseModel):
    """
    A case as the desk shows it: the row, the customer it belongs to, and the
    narrative when the whole case was asked for.
    """

    case_id: str
    client_id: str | None = None
    customer: str | None = None
    subject: str | None = None
    status: str | None = None
    severity: str | None = None
    category: str | None = None
    channel: str | None = None
    reported_by: str | None = None
    assigned_to: str | None = None
    opened_at: str | None = None
    closed_at: str | None = None
    resolution_days: str | None = None
    linked_incident_id: str | None = None
    linked_run_id: str | None = None

    # Only a single case carries these; a listing leaves them out.
    description: str | None = None
    resolution_notes: str | None = None
    root_cause: str | None = None


class CaseListResponse(BaseModel):
    """
    A queue, filtered or searched.
    """

    cases: list[Case]


class MeResponse(BaseModel):
    """
    Who the desk thinks is working it, and the vocabularies the tables use.

    The UI holds no copy of these: severity, status and the engineer list live in the
    tables and are reported from here, so the two cannot drift.
    """

    user: str
    engineers: list[str]
    severities: list[str]
    statuses: list[str]


class StatsResponse(BaseModel):
    """
    The counters along the top of the desk.
    """

    total: str | None = None
    open_cases: str | None = None
    urgent: str | None = None
    avg_days: str | None = None


class CaseUpdateRequest(BaseModel):
    """
    A change to a case's severity, status or assignee. Only what changes is sent.
    """

    severity: str | None = None
    status: str | None = None
    assigned_to: str | None = None


class NoteRequest(BaseModel):
    """
    A note to append to a case's narrative.
    """

    note: str = ""


class CloseRequest(BaseModel):
    """
    What was done about a case, and why it happened if that is known.
    """

    resolution: str = ""
    root_cause: str | None = None


class LinkRequest(BaseModel):
    """
    The incident or the payroll run a case is about.
    """

    incident_id: str | None = None
    run_id: str | None = None


class CaseChangedResponse(BaseModel):
    """
    The result of a change, including what moved so the desk can say it out loud.
    """

    case_id: str
    changed: list[str] = Field(default_factory=list)
    case: Case


class CaseWriteResponse(BaseModel):
    """
    The result of a write that speaks for itself: the case as it now stands.
    """

    case_id: str
    case: Case


class NoteAddedResponse(BaseModel):
    """
    The entry as it was written onto the narrative, stamp and signature included.
    """

    case_id: str
    added: str


class ResetResponse(BaseModel):
    """
    The result of putting one person's demo back to how the workshop starts.
    """

    status: str
    user: str
    cases_restored: int


class HealthResponse(BaseModel):
    """
    Whether the process can serve traffic.
    """

    status: str = Field(description="OK or UNAVAILABLE.")
    app: str
    version: str


class ErrorResponse(BaseModel):
    """
    Uniform error body.

    The desk's refusals are sentences written for a person - "Closing a case needs a
    resolution" - and the UI shows them unchanged, so the field is called what the UI
    reads.
    """

    error: str
