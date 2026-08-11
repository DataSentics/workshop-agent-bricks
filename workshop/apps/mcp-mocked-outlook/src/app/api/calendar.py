"""
Calendar routes.

The handlers are plain `def` for the same reason as the mail ones: the store blocks on
the volume, so FastAPI runs them in a worker thread.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.api.dependencies import get_caller, get_store
from app.schemas.mail import CreateEventRequest  # noqa: TC001
from app.store.mailbox import MailboxStore  # noqa: TC001

router: APIRouter = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("")
def list_events(
    caller: Annotated[str, Depends(get_caller)],
    store: Annotated[MailboxStore, Depends(get_store)],
    upcoming: bool = True,
) -> dict[str, Any]:
    """
    Summarise the calendar, either side of now.
    """
    return store.list_calendar_events(caller, upcoming)


@router.post("/create")
def create_event(
    request: CreateEventRequest,
    caller: Annotated[str, Depends(get_caller)],
    store: Annotated[MailboxStore, Depends(get_store)],
) -> dict[str, Any]:
    """
    Add an event to the calendar.
    """
    return store.create_calendar_event(
        caller,
        request.title,
        request.start_time,
        request.end_time,
        request.location,
        request.attendees,
        request.description,
    )


@router.get("/{event_id}")
def get_event(
    event_id: str,
    caller: Annotated[str, Depends(get_caller)],
    store: Annotated[MailboxStore, Depends(get_store)],
) -> dict[str, Any]:
    """
    Return one event in full.
    """
    return store.get_calendar_event(caller, event_id)


@router.delete("/{event_id}")
def delete_event(
    event_id: str,
    caller: Annotated[str, Depends(get_caller)],
    store: Annotated[MailboxStore, Depends(get_store)],
) -> dict[str, Any]:
    """
    Remove an event from the calendar.
    """
    return store.delete_calendar_event(caller, event_id)
