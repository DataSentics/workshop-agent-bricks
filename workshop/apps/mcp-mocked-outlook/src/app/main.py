"""
FastAPI application factory and uvicorn entrypoint.

The settings are loaded once, here, and passed on from there; the mailbox store is built
from them and bound on the application state. The intent is that this is the only place
either of them is constructed, and the application state the only place they are read
from.

The MCP server is mounted last, after every other route, and that ordering is the whole
reason this function is written as a sequence of steps. See _setup_mcp.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from functools import partial
from typing import TYPE_CHECKING

import anyio.to_thread
import uvicorn
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import calendar as calendar_api
from app.api import demo as demo_api
from app.api import mailbox as mailbox_api
from app.api import probes as probes_api
from app.core.identity import CallerIdentityMiddleware
from app.core.settings import Settings
from app.mcp.server import bind as bind_mcp_store
from app.mcp.server import mcp_server
from app.static import router as ui_router
from app.store.mailbox import MailboxStore

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = logging.getLogger(__name__)

# Domain routers are mounted under the API prefix (such as /api/...). Add them here; the
# probes and the UI deliberately stay at the root.
API_ROUTERS: tuple[APIRouter, ...] = (
    mailbox_api.router,
    calendar_api.router,
    demo_api.router,
)


@asynccontextmanager
async def _lifespan(app: FastAPI, settings: Settings) -> AsyncGenerator[None, None]:
    """
    Run the MCP session manager for as long as the application is up.

    The streamable-HTTP transport keeps its own task group, and posting to /mcp before
    it is running fails, so it is started here rather than lazily on first use.

    Args:
        app: Application being started, which already carries the store it serves from.
        settings: Configuration, for the line written when the application comes up.

    Yields:
        None, for as long as the application is running.
    """
    # Set here rather than at import because the limiter belongs to the running event
    # loop. Every volume round-trip happens on one of these threads, so this number is
    # how many people can be served at once before anybody has to queue.
    anyio.to_thread.current_default_thread_limiter().total_tokens = (
        settings.core.max_worker_threads
    )
    async with mcp_server.session_manager.run():
        logger.info(
            "Mocked Outlook started (version %s, mailboxes under %s, workers %d)",
            settings.core.app_version,
            settings.mailbox.volume_path,
            settings.core.max_worker_threads,
        )
        yield
    logger.info("Mocked Outlook stopped")


def _setup_logging(settings: Settings) -> None:
    """
    Configure the root logger.

    Args:
        settings: Configuration holding the level to log at.
    """
    # Configured during the call rather than at import, so that importing the package
    # does not depend on the environment.
    logging.basicConfig(
        level=settings.core.log_level.upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _setup_state(application: FastAPI, settings: Settings) -> None:
    """
    Build the mailbox store and hand it to both surfaces that serve from it.

    It is built here rather than in the lifespan because it opens nothing and holds
    nothing that needs releasing, and because the MCP tools have to be given it before
    the server is mounted.

    Args:
        application: Application the store is bound on.
        settings: Configuration the store is built from.
    """
    store = MailboxStore(settings.mailbox)
    application.state.settings = settings
    application.state.store = store
    # The REST routes reach the store through the request; the MCP tools have no request
    # to reach through, so they are handed the same instance directly. One store means
    # one cache: a second would drift away from this one mailbox by mailbox.
    bind_mcp_store(store, settings.mailbox.default_user)


def _setup_middleware(application: FastAPI, settings: Settings) -> None:
    """
    Install the middleware stack.

    Args:
        application: Application to install the middleware on.
        settings: Configuration for the individual middleware.
    """
    application.add_middleware(CallerIdentityMiddleware)
    # Each call of .add_middleware goes on the front of the stack, so this one ends up
    # outermost and answers the CORS preflight without the identity layer running first.
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.core.cors_allow_origins,
        allow_credentials=settings.core.cors_allow_credentials,
        allow_methods=settings.core.cors_allow_methods,
        allow_headers=settings.core.cors_allow_headers,
        expose_headers=settings.core.cors_expose_headers,
    )


def _setup_routers(application: FastAPI, settings: Settings) -> None:
    """
    Mount the probes and the UI at the root and the domain routes under the API prefix.

    Args:
        application: Application the routes are mounted on.
        settings: Configuration holding the API prefix.
    """
    application.include_router(probes_api.router)
    application.include_router(ui_router)

    api_router = APIRouter(prefix=settings.core.api_prefix)
    for router in API_ROUTERS:
        api_router.include_router(router)
    application.include_router(api_router)


def _setup_mcp(application: FastAPI) -> None:
    """
    Mount the MCP server, which must be the last route the application registers.

    FastMCP's ASGI app already serves the stream at its own /mcp path, so it is mounted
    at the root prefix rather than under /mcp: the latter would publish /mcp/mcp, and
    mounting at /mcp with an inner path of / makes Starlette redirect /mcp to /mcp/,
    which not every MCP client follows.

    A Mount at "" matches every path, and Starlette tries routes in registration order,
    so anything added after this is unreachable.

    Args:
        application: Application the MCP server is mounted on.
    """
    application.mount("", mcp_server.streamable_http_app())


def create_application(settings: Settings | None = None) -> FastAPI:
    """
    Build the ASGI application.

    Args:
        settings: Configuration to run with. When omitted, it is read from the
            environment.

    Returns:
        The configured application.
    """
    settings = settings or Settings()
    _setup_logging(settings)

    application = FastAPI(
        title=settings.core.app_title,
        description=settings.core.app_description,
        version=settings.core.app_version,
        lifespan=partial(_lifespan, settings=settings),
    )

    _setup_state(application, settings)
    _setup_middleware(application, settings)
    _setup_routers(application, settings)
    # Last, and it has to stay last.
    _setup_mcp(application)

    return application


def main() -> None:
    """
    Run the application with uvicorn under the outlook-server console script.
    """
    settings = Settings()
    uvicorn.run(
        "app.main:create_application",
        factory=True,
        host=settings.core.host,
        port=settings.core.port,
    )


if __name__ == "__main__":
    main()
