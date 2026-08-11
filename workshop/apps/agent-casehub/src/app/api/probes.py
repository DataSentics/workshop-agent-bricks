"""
Container probe endpoints.

/live answers whether the process itself is alive, and /health whether it can serve
traffic. Neither of them touches the SQL warehouse: a warehouse that is asleep takes
seconds to answer its first query, and reporting the app unhealthy for that would have
the platform restart something that is working. The case routes report a warehouse
failure where it actually matters, on the request that needed it.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.dependencies import get_app_settings
from app.core.settings import AppSettings  # noqa: TC001
from app.schemas.cases import HealthResponse

router: APIRouter = APIRouter(tags=["probes"])


@router.get("/live", status_code=HTTPStatus.NO_CONTENT)
async def live() -> Response:
    """
    Report that the process is alive.

    Returns:
        An empty response with status 204.
    """
    return Response(status_code=HTTPStatus.NO_CONTENT)


@router.get("/health", response_model=HealthResponse)
async def health(
    app_settings: Annotated[AppSettings, Depends(get_app_settings)],
) -> HealthResponse:
    """
    Report that the application is serving.

    Returns:
        The application's name and version, with status OK.
    """
    return HealthResponse(
        status="OK",
        app=app_settings.app_title,
        version=app_settings.app_version,
    )
