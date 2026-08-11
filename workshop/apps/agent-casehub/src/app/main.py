"""
FastAPI application factory and uvicorn entrypoint.

CaseHub wears two faces on one process:

    /                    the case desk a support engineer would use
    /api/*               what that UI calls
    /live, /health       the container probes
    /responses           the agent, in the OpenAI Responses schema
    /invocations         the same agent, MLflow's own route
    /agent/info          discovery: what kind of agent this is

The second set is not written here. MLflow's AgentServer registers those routes, which
is what makes this app acceptable to the Agent Bricks Supervisor as a custom agent
rather than merely a web app with an HTTP API. Databricks documents exactly one naming
rule for it - the app name has to start with `agent-`, the same way an MCP app has to
start with `mcp-`.

The settings are loaded once, here, and passed on from there; the case store is built
from them and bound on the application state. The intent is that this is the only place
either of them is constructed, and the application state the only place they are read
from.

The mount ordering at the bottom is the one thing here that will silently break if it is
moved.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from functools import partial
from http import HTTPStatus
from typing import TYPE_CHECKING

import anyio.to_thread
import uvicorn
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import iterate_in_threadpool, run_in_threadpool

from app import static as static_api
from app.api import cases as cases_api
from app.api import demo as demo_api
from app.api import probes as probes_api
from app.core.identity import CallerIdentityMiddleware
from app.core.settings import Settings
from app.schemas.cases import ErrorResponse
from app.store.cases import CaseError, CaseStore

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from app.core.settings import AgentSettings

logger = logging.getLogger(__name__)

# Domain routers are mounted under the API prefix (such as /api/... ). Add them here;
# the probes, the page itself and the agent routes deliberately stay at the root, where
# the platform and the supervisor reach them without knowing how the API is namespaced.
API_ROUTERS: tuple[APIRouter, ...] = (cases_api.router, demo_api.router)


@asynccontextmanager
async def _lifespan(app: FastAPI, settings: Settings) -> AsyncGenerator[None, None]:
    """
    Report what the process is pointed at, once, when it starts serving.

    Args:
        app: The running application. Nothing is bound here; the store is built in the
            factory because the agent, mounted at build time, holds it too.
        settings: Configuration the application was built with.

    Yields:
        None, for as long as the application is running.
    """
    # Set here rather than at import because the limiter belongs to the running event
    # loop. Every blocking thing this app does - the warehouse, the model, the whole
    # agent run - happens on one of these threads, so this number is how many people
    # can be served at once before anybody has to queue.
    anyio.to_thread.current_default_thread_limiter().total_tokens = (
        settings.core.max_worker_threads
    )
    logger.info(
        "application started: catalog=%s warehouse=%s llm=%s workers=%d",
        settings.catalog.catalog,
        settings.catalog.warehouse_id,
        settings.agent.llm_endpoint,
        settings.core.max_worker_threads,
    )
    yield
    logger.info("application stopped")


def _setup_logging(settings: Settings) -> None:
    """
    Send the application's own logs where Databricks Apps collects them.

    uvicorn configures its loggers and leaves the root alone, so without this every
    logger.info in the application would be dropped and the app log would show requests
    and nothing about what the desk actually did.

    Args:
        settings: Configuration holding the level to log at.
    """
    logging.basicConfig(level=settings.core.log_level.upper())


def _setup_middleware(application: FastAPI) -> None:
    """
    Install the middleware stack.

    Args:
        application: Application to install the middleware on.
    """
    # Middleware wraps the whole application, mounted sub-applications included, which
    # is the only reason the agent's tool calls know whose desk they are working.
    application.add_middleware(CallerIdentityMiddleware)


def _setup_routers(application: FastAPI, settings: Settings) -> None:
    """
    Mount the probes and the page at the root, and the domain routes under the prefix.

    Args:
        application: Application the routes are mounted on.
        settings: Configuration holding the API prefix.
    """
    # Registered before anything else, deliberately: the agent server mounted at the end
    # of create_application serves a /health of its own, and Starlette matches routes in
    # registration order. This is what makes /health answer with the application's own
    # health rather than the agent runtime's.
    application.include_router(probes_api.router)
    application.include_router(static_api.router)

    api_router = APIRouter(prefix=settings.core.api_prefix)
    for router in API_ROUTERS:
        api_router.include_router(router)
    application.include_router(api_router)


def _setup_exception_handlers(application: FastAPI) -> None:
    """
    Map the case desk's refusals to a body the UI can show.

    Args:
        application: Application the handler is installed on.
    """

    @application.exception_handler(CaseError)
    async def _case_error_handler(  # pyright: ignore[reportUnusedFunction]
        _request: Request,
        exc: Exception,
    ) -> JSONResponse:
        """
        Answer a refusal with the sentence it was refused in.

        "Closing a case needs a resolution" is written for a person and the UI shows it
        unchanged, so it is handed over as the message rather than replaced with a
        status code's own wording.
        """
        body = ErrorResponse(error=str(exc))
        return JSONResponse(
            status_code=HTTPStatus.BAD_REQUEST,
            content=body.model_dump(),
        )


def _build_agent_app(store: CaseStore, settings: AgentSettings) -> FastAPI:
    """
    Build the MLflow agent server around a CaseHub agent.

    MLflow is imported here rather than at module scope so that the case desk still
    comes up if the agent runtime cannot be loaded: a UI that starts with a clear log
    line beats a container that will not start at all.

    Args:
        store: The desk the agent's tools work on.
        settings: The model the agent thinks with and how long for.

    Returns:
        The ASGI application carrying /responses, /invocations, /agent/info and /health.
    """
    from mlflow.genai.agent_server import AgentServer, invoke, stream  # noqa: PLC0415
    from mlflow.types.responses import ResponsesAgentRequest  # noqa: PLC0415, TC002

    from app.agent.agent import CaseHubAgent  # noqa: PLC0415

    agent = CaseHubAgent(store, settings)

    # Both handlers are async and hand the actual run to a worker thread. MLflow's
    # AgentServer awaits a coroutine but calls a plain function inline on the event
    # loop, and a run is several seconds of blocking calls - the serving endpoint, then
    # the warehouse, once per tool. Left on the loop, one person's question stops the
    # process answering anybody at all: not the other agents, not the case desk UI, not
    # even the container's health probe. Measured at eight seconds of dead air for six
    # people asking at once, against one and a half with this.
    #
    # Both helpers copy the context into the worker, so the caller the identity
    # middleware bound is still the one the agent's tools read.

    @invoke()
    async def _invoke(  # pyright: ignore[reportUnusedFunction]
        request: ResponsesAgentRequest,
    ) -> object:
        """
        Answer /invocations and the non-streaming half of /responses.
        """
        return await run_in_threadpool(agent.predict, request)

    @stream()
    async def _stream(  # pyright: ignore[reportUnusedFunction]
        request: ResponsesAgentRequest,
    ) -> AsyncGenerator[object, None]:
        """
        Answer the streaming half of /responses.

        The generator is created here and then pulled one event at a time from a worker
        thread, so the loop is free between events as well as during them, and each
        event still reaches the caller as soon as it is produced.
        """
        async for event in iterate_in_threadpool(agent.predict_stream(request)):
            yield event

    return AgentServer("ResponsesAgent", enable_chat_proxy=False).app


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
    # Constructing the store opens no connection, so a warehouse that is unreachable
    # leaves the process started and failing per request rather than failing to boot.
    store = CaseStore(settings.catalog)
    application.state.settings = settings
    application.state.case_store = store

    _setup_middleware(application)
    _setup_routers(application, settings)
    _setup_exception_handlers(application)

    # LAST, and it has to stay last. Mounting the agent server at the root prefix puts
    # /responses, /invocations, /agent/info and /health at the paths the supervisor
    # expects; mounting it under a prefix would bury /responses at /something/responses
    # and the supervisor would never find it. Starlette compiles Mount("") into a
    # catch-all and matches routes in registration order, so anything registered after
    # this line is unreachable.
    try:
        application.mount("", _build_agent_app(store, settings.agent))
    except Exception:
        logger.exception("agent surface failed to mount - the UI and /api/* still work")
    else:
        logger.info("agent surface mounted: /responses, /invocations, /agent/info")

    return application


def main() -> None:
    """
    Run the application with uvicorn under the casehub-server console script.
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
