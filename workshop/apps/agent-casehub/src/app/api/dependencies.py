"""
Access to the objects shared for the lifetime of the application, and to the caller.

One store and one settings object are bound on the application state when the
application is built. Every getter checks the type of what it finds and fails loudly, so
a missing piece of wiring surfaces as an error naming it rather than as None turning up
somewhere far away. They take a Starlette Request, which also makes them usable on a
mounted sub-application.
"""

from __future__ import annotations

from starlette.requests import Request  # noqa: TC002

from app.core.identity import current_caller
from app.core.settings import AppSettings, Settings
from app.store.cases import CaseStore


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


def get_app_settings(request: Request) -> AppSettings:
    """
    Return the process and HTTP section of the settings.
    """
    return get_settings(request).core


def get_case_store(request: Request) -> CaseStore:
    """
    Return the process-wide case store from app state.

    Raises:
        RuntimeError: If it was never bound or has an unexpected type.
    """
    store = getattr(request.app.state, "case_store", None)
    if not isinstance(store, CaseStore):
        message = "Case store was not initialized on the app state."
        raise RuntimeError(message)
    return store


def get_caller() -> str:
    """
    Return whoever is driving this request.

    Read from the context the identity middleware bound rather than from the headers
    directly, so a route and the agent's tool calls cannot disagree about who is asking.
    """
    return current_caller()
