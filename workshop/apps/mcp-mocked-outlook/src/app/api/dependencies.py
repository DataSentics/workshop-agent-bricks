"""
Access to the objects shared for the lifetime of the application.

One instance of each is bound on the application state while it is built. Every getter
checks the type of what it finds and fails loudly, so a missing piece of wiring surfaces
as an error naming it rather than as None turning up somewhere far away. They take a
Starlette Request, which also makes them usable on a mounted sub-application.
"""

from __future__ import annotations

from starlette.requests import Request  # noqa: TC002

from app.core.identity import current_caller
from app.core.settings import Settings
from app.store.mailbox import MailboxStore


def get_settings(request: Request) -> Settings:
    """
    Return the settings the application was built with.

    Raises:
        RuntimeError: If they are absent or of an unexpected type.
    """
    settings = getattr(request.app.state, "settings", None)
    if not isinstance(settings, Settings):
        message = "Settings were not initialized on the app state."
        raise RuntimeError(message)
    return settings


def get_store(request: Request) -> MailboxStore:
    """
    Return the process-wide mailbox store from app state.

    Raises:
        RuntimeError: If it was never bound or has an unexpected type.
    """
    store = getattr(request.app.state, "store", None)
    if not isinstance(store, MailboxStore):
        message = "Mailbox store was not initialized on the app state."
        raise RuntimeError(message)
    return store


def get_caller(request: Request) -> str:
    """
    Return the mail address this request acts for.
    """
    return current_caller(get_settings(request).mailbox.default_user)
