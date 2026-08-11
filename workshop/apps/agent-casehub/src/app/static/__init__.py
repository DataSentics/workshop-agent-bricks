"""
The case desk itself: one page, served from inside the package.

index.html sits beside this module rather than in a directory of assets because there is
exactly one file and it has no build step - no bundler, no framework, no CDN. It is read
once at import, so serving it is a string rather than a stat and a read per request, and
so a missing file is noticed when the process starts rather than by the first person to
open the page.

The route is registered at the root, outside the API prefix. The page is what somebody
gets by opening the app, and it calls the same /api routes the agent's tools reach.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router: APIRouter = APIRouter(tags=["ui"])

_INDEX_HTML = (Path(__file__).parent / "index.html").read_text(encoding="utf-8")


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def index() -> HTMLResponse:
    """
    Serve the case desk.

    Returns:
        The page, as it was read at import.
    """
    return HTMLResponse(_INDEX_HTML)
