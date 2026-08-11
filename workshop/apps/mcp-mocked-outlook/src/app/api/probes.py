"""
Container probe endpoints.

/live answers whether the process itself is alive, and /health answers whether it can
serve traffic. They are separate endpoints because they answer separate questions.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.dependencies import get_settings, get_store
from app.core.settings import Settings  # noqa: TC001
from app.schemas.mail import HealthResponse
from app.store.mailbox import MailboxStore  # noqa: TC001

router: APIRouter = APIRouter(tags=["probes"])


@router.get("/live", status_code=HTTPStatus.NO_CONTENT)
def live() -> Response:
    """
    Report that the process is alive, without consulting anything else.

    Returns:
        An empty response with status 204.
    """
    return Response(status_code=HTTPStatus.NO_CONTENT)


@router.get("/health")
def health(
    settings: Annotated[Settings, Depends(get_settings)],
    store: Annotated[MailboxStore, Depends(get_store)],
) -> HealthResponse:
    """
    Report that the process can serve traffic, and whether writes reach the volume.

    A volume that cannot be reached is reported rather than treated as fatal: mailboxes
    stay in memory and the demo carries on, so failing the probe would take a usable app
    out of rotation over something a demo can live without.

    Returns:
        The process metadata and the storage status.
    """
    return HealthResponse(
        status="OK",
        app=settings.core.app_title,
        version=settings.core.app_version,
        storage=store.storage_status(),
    )
