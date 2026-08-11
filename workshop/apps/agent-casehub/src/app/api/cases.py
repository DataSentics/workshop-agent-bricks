"""
What the case desk UI calls.

These are the same routes the agent's tools reach, taking the same caller and the same
store, so a change made by hand and a change made by the agent land in exactly the same
place. The router carries no prefix of its own: /me and /stats sit beside /cases, and
the API prefix is applied where the routers are mounted.

Every handler is a plain def rather than a coroutine. The Statement Execution API client
is blocking, so FastAPI running these in a worker thread is what keeps one slow
warehouse query from holding up every other request.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_caller, get_case_store
from app.schemas.cases import (
    Case,
    CaseChangedResponse,
    CaseListResponse,
    CaseUpdateRequest,
    CaseWriteResponse,
    CloseRequest,
    LinkRequest,
    MeResponse,
    NoteAddedResponse,
    NoteRequest,
    StatsResponse,
)
from app.store.cases import (
    ENGINEERS,
    SEVERITIES,
    STATUSES,
    CaseStore,
)

router: APIRouter = APIRouter(tags=["cases"])


@router.get("/me")
def me(caller: Annotated[str, Depends(get_caller)]) -> MeResponse:
    """
    Report who is working the desk and the vocabularies the tables use.
    """
    return MeResponse(
        user=caller,
        engineers=list(ENGINEERS),
        severities=list(SEVERITIES),
        statuses=list(STATUSES),
    )


@router.get("/stats")
def stats(
    caller: Annotated[str, Depends(get_caller)],
    store: Annotated[CaseStore, Depends(get_case_store)],
) -> StatsResponse:
    """
    Return the counters for the queue as this caller has it.
    """
    return StatsResponse.model_validate(store.stats(caller))


@router.get("/cases")
def list_cases(
    caller: Annotated[str, Depends(get_caller)],
    store: Annotated[CaseStore, Depends(get_case_store)],
    status: str = "",
    customer: str = "",
    severity: str = "",
    assigned_to: str = "",
    q: str = "",
    limit: int = 50,
) -> CaseListResponse:
    """
    Return the queue, either filtered or searched.

    A free-text query replaces the filters rather than narrowing them: search reads the
    narrative as well as the row, and the UI switches the filters off while one is set
    rather than showing dropdowns that no longer apply.
    """
    if q:
        rows = store.search_cases(caller, q, limit)
    else:
        # Keyword arguments deliberately, and the store insists on them: they were
        # positional once, and inserting open_only into the middle of the signature
        # turned `limit` into `open_only=50`, which hid every closed case from the
        # queue.
        rows = store.list_cases(
            caller,
            status=status or None,
            customer=customer or None,
            severity=severity or None,
            assigned_to=assigned_to or None,
            limit=limit,
        )
    return CaseListResponse(cases=[Case.model_validate(row) for row in rows])


@router.get("/cases/{case_id}")
def get_case(
    case_id: str,
    caller: Annotated[str, Depends(get_caller)],
    store: Annotated[CaseStore, Depends(get_case_store)],
) -> Case:
    """
    Return one case in full, narrative included.
    """
    return Case.model_validate(store.get_case(caller, case_id))


@router.patch("/cases/{case_id}")
def update_case(
    case_id: str,
    request: CaseUpdateRequest,
    caller: Annotated[str, Depends(get_caller)],
    store: Annotated[CaseStore, Depends(get_case_store)],
) -> CaseChangedResponse:
    """
    Change a case's severity, status or assignee.
    """
    return CaseChangedResponse.model_validate(
        store.update_case(
            caller,
            case_id,
            request.severity,
            request.status,
            request.assigned_to,
        ),
    )


@router.post("/cases/{case_id}/notes")
def add_note(
    case_id: str,
    request: NoteRequest,
    caller: Annotated[str, Depends(get_caller)],
    store: Annotated[CaseStore, Depends(get_case_store)],
) -> NoteAddedResponse:
    """
    Append a note to a case, signed with the caller's own name.
    """
    return NoteAddedResponse.model_validate(
        store.add_note(caller, case_id, request.note, author=caller),
    )


@router.post("/cases/{case_id}/close")
def close_case(
    case_id: str,
    request: CloseRequest,
    caller: Annotated[str, Depends(get_caller)],
    store: Annotated[CaseStore, Depends(get_case_store)],
) -> CaseWriteResponse:
    """
    Close a case, recording when it closed and what was done about it.
    """
    return CaseWriteResponse.model_validate(
        store.close_case(caller, case_id, request.resolution, request.root_cause),
    )


@router.post("/cases/{case_id}/link")
def link_case(
    case_id: str,
    request: LinkRequest,
    caller: Annotated[str, Depends(get_caller)],
    store: Annotated[CaseStore, Depends(get_case_store)],
) -> CaseWriteResponse:
    """
    Point a case at the incident or the payroll run it is about.
    """
    return CaseWriteResponse.model_validate(
        store.link_case(caller, case_id, request.incident_id, request.run_id),
    )
