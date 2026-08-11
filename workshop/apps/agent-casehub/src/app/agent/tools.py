"""
The tools the agent works the desk with, and the dispatch that runs them.

These are the same store methods the UI's routes call, described here in the schema a
chat-completions endpoint expects. The descriptions are written for the model rather
than for a developer: they say which of two similar-sounding things is meant, because
that is where a tool-calling loop actually goes wrong.

The caller is not in any schema. It is passed in by the dispatch from the identity the
HTTP middleware bound, so the model can neither see whose desk it is working nor aim a
write at somebody else's.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from app.store.cases import ENGINEERS, SEVERITIES, STATUSES, CaseError

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from app.store.cases import CaseStore

logger = logging.getLogger(__name__)

TOOLS: tuple[dict[str, Any], ...] = (
    {
        "type": "function",
        "function": {
            "name": "list_cases",
            "description": (
                "List support cases, most urgent first. Use it to find a case when you "
                "were not given an id, or to show the queue."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "open_only": {
                        "type": "boolean",
                        "description": (
                            "Everything not closed. This is what somebody means by "
                            "'open cases' unless they said the word Open as a status."
                        ),
                    },
                    "status": {
                        "type": "string",
                        "enum": list(STATUSES),
                        "description": (
                            "One exact status. 'Open' here means nobody has picked the "
                            "case up yet, NOT 'not closed'."
                        ),
                    },
                    "severity": {"type": "string", "enum": list(SEVERITIES)},
                    "customer": {
                        "type": "string",
                        "description": "Customer name, partial is fine, e.g. 'Alpine'.",
                    },
                    "assigned_to": {
                        "type": "string",
                        "description": "Engineer name, partial is fine.",
                    },
                    "limit": {"type": "integer", "description": "Default 25."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_case",
            "description": (
                "Everything on one case, including the narrative and the resolution."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "case_id": {"type": "string", "description": "e.g. CAS-40318"},
                },
                "required": ["case_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_cases",
            "description": (
                "Find cases whose subject or narrative contains some text. Literal "
                "substring matching, not meaning - use it for names, error codes and "
                "run ids."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_case",
            "description": (
                "Change a case's severity, status or assignee. Pass only what changes. "
                "Cannot close a case - use close_case for that."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "case_id": {"type": "string"},
                    "severity": {"type": "string", "enum": list(SEVERITIES)},
                    # Closed is left out of the vocabulary rather than only refused by
                    # the store, so the model has no reason to try it in the first
                    # place.
                    "status": {
                        "type": "string",
                        "enum": [status for status in STATUSES if status != "Closed"],
                    },
                    "assigned_to": {"type": "string", "enum": list(ENGINEERS)},
                },
                "required": ["case_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_note",
            "description": (
                "Append a note to the case narrative. Permanent, and stamped with who "
                "wrote it. Use it to record what you found or what you did."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "case_id": {"type": "string"},
                    "note": {"type": "string"},
                },
                "required": ["case_id", "note"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "close_case",
            "description": (
                "Close a case. Records the time and works out how long it took. The "
                "resolution is required: say what was actually done."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "case_id": {"type": "string"},
                    "resolution": {
                        "type": "string",
                        "description": "What was done about it.",
                    },
                    "root_cause": {
                        "type": "string",
                        "description": "Why it happened, if known.",
                    },
                },
                "required": ["case_id", "resolution"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "link_case",
            "description": (
                "Attach a case to the incident or the payroll run it is about."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "case_id": {"type": "string"},
                    "incident_id": {
                        "type": "string",
                        "description": "e.g. INC-0031",
                    },
                    "run_id": {
                        "type": "string",
                        "description": "e.g. PR-202607-0008",
                    },
                },
                "required": ["case_id"],
            },
        },
    },
)


def handlers(store: CaseStore) -> dict[str, Callable[..., Any]]:
    """
    The tools, bound to one store.

    Written out rather than resolved with getattr on the tool name: the name arrives
    from the model, and looking up an arbitrary attribute from it would make every
    method on the store reachable as a tool.

    Args:
        store: The desk the tools work on.

    Returns:
        Tool name to the callable that answers it, each taking the caller first.
    """
    return {
        "list_cases": store.list_cases,
        "get_case": store.get_case,
        "search_cases": store.search_cases,
        "update_case": store.update_case,
        "add_note": store.add_note,
        "close_case": store.close_case,
        "link_case": store.link_case,
    }


def call_tool(
    store: CaseStore,
    caller: str,
    name: str,
    arguments: Mapping[str, Any],
) -> str:
    """
    Run one tool and return what the model should see.

    A refused write comes back as an ordinary result rather than as an exception,
    because "you cannot close a case without a resolution" is something the model should
    read and act on, not a crash. The same goes for arguments that do not fit the
    signature: the model invented them and can correct them on the next turn.

    Args:
        store: The desk the tools work on.
        caller: Whose desk it is. Never visible to the model.
        name: The tool the model asked for.
        arguments: What it passed, already parsed out of the tool call.

    Returns:
        A JSON document, either the tool's result or an "error" the model can read.
    """
    handler = handlers(store).get(name)
    if handler is None:
        return json.dumps({"error": f"No such tool: {name}"})
    try:
        # Every tool works on the caller's own copy of the desk.
        result = handler(caller, **arguments)
    except CaseError as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    except TypeError as exc:
        return json.dumps(
            {"error": f"Wrong arguments for {name}: {exc}"},
            ensure_ascii=False,
        )
    # Anything else is a bug or an outage, and the model gets to see it and retry
    # rather than the whole request failing on one tool.
    except Exception as exc:
        logger.exception("tool %s blew up", name)
        return json.dumps({"error": f"{name} failed: {exc}"}, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False, default=str)
