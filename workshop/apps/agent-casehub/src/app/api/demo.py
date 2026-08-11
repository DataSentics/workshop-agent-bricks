"""
The controls that make the workshop repeatable.

A demo is meant to be broken: escalate the case, close it, write the wrong note. Putting
it back is deleting the rows recording what this person did, because that is the only
place their changes ever were.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_caller, get_case_store
from app.schemas.cases import ResetResponse
from app.store.cases import CaseStore  # noqa: TC001

router: APIRouter = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/reset")
def reset(
    caller: Annotated[str, Depends(get_caller)],
    store: Annotated[CaseStore, Depends(get_case_store)],
) -> ResetResponse:
    """
    Discard this caller's changes and leave everybody else's alone.

    Returns:
        Who was reset and how many cases went back to the way they were seeded.
    """
    return ResetResponse(
        status="reset",
        user=caller,
        cases_restored=store.reset(caller),
    )
