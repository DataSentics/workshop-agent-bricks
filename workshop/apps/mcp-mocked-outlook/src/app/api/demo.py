"""
Demo housekeeping.

Deliberately not exposed as an MCP tool: an agent should not be able to wipe the mailbox
it is working in, and this endpoint exists for the person running the demo.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_caller, get_store
from app.schemas.mail import ResetResponse
from app.store.mailbox import MailboxStore  # noqa: TC001

router: APIRouter = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/reset")
def reset(
    caller: Annotated[str, Depends(get_caller)],
    store: Annotated[MailboxStore, Depends(get_store)],
) -> ResetResponse:
    """
    Rebuild the caller's mailbox from the seed, leaving everybody else's alone.

    Returns:
        The status and the mailbox that was reset.
    """
    return ResetResponse(**store.reset(caller))
