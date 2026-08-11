"""
Who is driving the request.

Everything the case desk writes is filed under this identity, so it decides which
overrides a read lays over the seed and whose rows a reset deletes. Databricks Apps puts
the signed-in person in a forwarded header; the same header arrives on the agent routes,
carrying whoever the supervisor is calling on behalf of.

It is bound on a context variable rather than passed down as an argument because the
agent's tool calls run below MLflow's own request handling, which hands the agent a
ResponsesAgentRequest and no HTTP request. Binding it once, in middleware that wraps the
whole application including the mounted agent, is what makes the UI and the agent agree
about who is asking.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING

from starlette.datastructures import Headers

if TYPE_CHECKING:
    from collections.abc import Mapping

    from starlette.types import ASGIApp, Receive, Scope, Send

# In the order Databricks Apps prefers them: the email is the identity the case desk
# files changes under, the other two are what a proxy without one sends instead.
CALLER_HEADERS: tuple[str, ...] = (
    "X-Forwarded-Email",
    "X-Forwarded-Preferred-Username",
    "X-Forwarded-User",
)

# Running outside the platform there is no header at all. Answering with one shared
# identity keeps a local run working, and it is the only way two people can collide.
ANONYMOUS_CALLER = "demo-user@company.com"

_caller: ContextVar[str] = ContextVar("caller", default=ANONYMOUS_CALLER)


def caller_from_headers(headers: Mapping[str, str]) -> str:
    """
    Read the caller out of the forwarded headers.

    Args:
        headers: Request headers, matched case-insensitively.

    Returns:
        The caller's email, or the anonymous identity when nothing was forwarded.
    """
    for header in CALLER_HEADERS:
        value = headers.get(header)
        if value:
            return value
    return ANONYMOUS_CALLER


def current_caller() -> str:
    """
    Return the caller bound for this request.
    """
    return _caller.get()


class CallerIdentityMiddleware:
    """
    Bind the caller for the duration of one request.

    Written as raw ASGI rather than as a BaseHTTPMiddleware so the value is set on the
    same task that runs the endpoint, which is what the mounted agent reads it from.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        Resolve the caller, run the request with it bound, and unbind it afterwards.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        token = _caller.set(caller_from_headers(Headers(scope=scope)))
        try:
            await self.app(scope, receive, send)
        finally:
            _caller.reset(token)
