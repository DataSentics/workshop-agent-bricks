"""
Request and response bodies for the REST API.

Only the bodies with a fixed shape are modelled. The mail and calendar operations return
either a payload or an {"error": ...} object, and the UI branches on that, so those
routes stay untyped rather than having a response model quietly drop the error key.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SendEmailRequest(BaseModel):
    """
    Body of the send-mail endpoint.

    Attributes:
        to: Address to deliver to.
        subject: Subject line.
        body: Message text.
    """

    model_config = ConfigDict(extra="forbid")

    to: str = Field(min_length=1)
    subject: str = ""
    body: str = ""


class DraftRequest(BaseModel):
    """
    Body of the create-draft endpoint.

    Every field has a default because a draft is allowed to be half-written; that is
    what separates it from a message being sent.
    """

    model_config = ConfigDict(extra="forbid")

    to: str = ""
    subject: str = ""
    body: str = ""


class DraftUpdateRequest(BaseModel):
    """
    Body of the update-draft endpoint, where an omitted field is left as it is.
    """

    model_config = ConfigDict(extra="forbid")

    to: str | None = None
    subject: str | None = None
    body: str | None = None


class CreateEventRequest(BaseModel):
    """
    Body of the create-event endpoint.

    Attributes:
        title: Event title.
        start_time: ISO start timestamp.
        end_time: ISO end timestamp.
        location: Room or link.
        attendees: Invitees; the caller alone when omitted.
        description: Agenda or notes.
    """

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    start_time: str
    end_time: str
    location: str = ""
    attendees: list[str] | None = None
    description: str = ""


class CallerResponse(BaseModel):
    """
    Who the UI is signed in as, and the clock the mailbox is stamped with.

    Attributes:
        user: Mail address the mailbox belongs to.
        now: Server time, so the calendar draws its current-time marker against the
            same clock the stored timestamps use rather than the browser's.
    """

    user: str
    now: str


class ResetResponse(BaseModel):
    """
    Outcome of rebuilding one mailbox from the seed.
    """

    status: str
    user: str


class HealthResponse(BaseModel):
    """
    Aggregate health of the process.

    Attributes:
        status: OK while the process can serve traffic.
        app: Application title.
        version: Application version.
        storage: "ok", or "unavailable" once the volume has refused a read or write.
    """

    status: str
    app: str
    version: str
    storage: str
