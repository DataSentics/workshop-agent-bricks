"""
Who the current request is acting for.

Databricks Apps terminate OAuth in front of the container and pass the signed-in user
down in a forwarded header. The identity is held in a ContextVar rather than a module
global: a global is shared by every in-flight request, so two people calling at the same
time race and one reads the other's mailbox. Stateless MCP makes that the normal case
rather than an edge case, because every tool call arrives as its own request.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING, Final

from starlette.datastructures import Headers

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send

# In the order the proxy prefers them: the mail address is the identity the mailbox is
# keyed by, and the other two are what remains when the directory has no address.
IDENTITY_HEADERS: Final[tuple[str, ...]] = (
    "X-Forwarded-Email",
    "X-Forwarded-Preferred-Username",
    "X-Forwarded-User",
)

_caller: ContextVar[str | None] = ContextVar("outlook_caller", default=None)


def current_caller(fallback: str) -> str:
    """
    Return the address the current request acts for.

    Args:
        fallback: Address to use when no forwarded identity was seen, which is the
            case for local runs and for anything reaching the app off the proxy.

    Returns:
        The caller's mail address.
    """
    return _caller.get() or fallback


class CallerIdentityMiddleware:
    """
    Bind the forwarded identity to the context the request runs in.

    Written as plain ASGI rather than as a BaseHTTPMiddleware subclass so that the
    endpoint, and any MCP tool it invokes, runs in the same task and therefore reads the
    value set here.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        Read the identity headers, then run the rest of the stack with it bound.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        caller = next(
            (headers[name] for name in IDENTITY_HEADERS if headers.get(name)),
            None,
        )
        token = _caller.set(caller)
        try:
            await self.app(scope, receive, send)
        finally:
            _caller.reset(token)
