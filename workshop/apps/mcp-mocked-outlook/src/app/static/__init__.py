"""
The Outlook-like web UI.

One self-contained page, served at the root so that opening the app in a browser lands
on the mailbox rather than on documentation. It is a single file with no build step and
no external requests: a Databricks App container has no CDN reachable from it, and a
workshop should not depend on one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router: APIRouter = APIRouter(tags=["ui"])

# Read once at import: the page ships inside the package and cannot change while the
# process runs, so re-reading it per request would only add a disk hit to every load.
_INDEX: Final[str] = (Path(__file__).resolve().parent / "index.html").read_text(
    encoding="utf-8",
)


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def index() -> HTMLResponse:
    """
    Serve the mailbox UI.

    Returns:
        The page, which fetches everything else it needs from the API prefix.
    """
    return HTMLResponse(_INDEX)
