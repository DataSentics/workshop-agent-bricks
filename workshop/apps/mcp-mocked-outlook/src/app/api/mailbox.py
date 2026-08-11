"""
Mail routes: the folders, the messages in them, and the drafts.

The handlers are plain `def` rather than `async def` on purpose. The store writes to the
volume over the SDK, which blocks, so FastAPI runs these in a worker thread instead of
holding up the event loop for every other request in flight.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.api.dependencies import get_caller, get_store
from app.schemas.mail import (
    CallerResponse,
    DraftRequest,
    DraftUpdateRequest,
    SendEmailRequest,
)
from app.store.mailbox import MailboxStore, utc_now

# No prefix: these are two sibling collections, /emails and /drafts, plus the identity
# the UI opens with.
router: APIRouter = APIRouter(tags=["mail"])


@router.get("/me")
def me(caller: Annotated[str, Depends(get_caller)]) -> CallerResponse:
    """
    Return who the caller is and what the server thinks the time is.
    """
    return CallerResponse(user=caller, now=utc_now().isoformat())


@router.get("/emails")
def list_emails(
    caller: Annotated[str, Depends(get_caller)],
    store: Annotated[MailboxStore, Depends(get_store)],
    folder: str = "inbox",
    unread_only: bool = False,
) -> dict[str, Any]:
    """
    Summarise one folder.
    """
    return store.list_emails(caller, folder, unread_only)


@router.post("/emails/send")
def send_email(
    request: SendEmailRequest,
    caller: Annotated[str, Depends(get_caller)],
    store: Annotated[MailboxStore, Depends(get_store)],
) -> dict[str, Any]:
    """
    Send a message to the recipient's inbox.
    """
    return store.send_email(caller, request.to, request.subject, request.body)


@router.get("/emails/{email_id}")
def get_email(
    email_id: str,
    caller: Annotated[str, Depends(get_caller)],
    store: Annotated[MailboxStore, Depends(get_store)],
) -> dict[str, Any]:
    """
    Return one message in full, marking inbox mail as read.
    """
    return store.get_email(caller, email_id)


@router.post("/drafts")
def create_draft(
    request: DraftRequest,
    caller: Annotated[str, Depends(get_caller)],
    store: Annotated[MailboxStore, Depends(get_store)],
) -> dict[str, Any]:
    """
    Save a message to Drafts without sending it.
    """
    return store.draft_email(caller, request.to, request.subject, request.body)


@router.patch("/drafts/{draft_id}")
def update_draft(
    draft_id: str,
    request: DraftUpdateRequest,
    caller: Annotated[str, Depends(get_caller)],
    store: Annotated[MailboxStore, Depends(get_store)],
) -> dict[str, Any]:
    """
    Revise a draft, leaving omitted fields alone.
    """
    return store.update_draft(
        caller,
        draft_id,
        request.to,
        request.subject,
        request.body,
    )


@router.post("/drafts/{draft_id}/send")
def send_draft(
    draft_id: str,
    caller: Annotated[str, Depends(get_caller)],
    store: Annotated[MailboxStore, Depends(get_store)],
) -> dict[str, Any]:
    """
    Send a draft as it currently stands.
    """
    return store.send_draft(caller, draft_id)


@router.delete("/drafts/{draft_id}")
def discard_draft(
    draft_id: str,
    caller: Annotated[str, Depends(get_caller)],
    store: Annotated[MailboxStore, Depends(get_store)],
) -> dict[str, Any]:
    """
    Delete a draft without sending it.
    """
    return store.discard_draft(caller, draft_id)
