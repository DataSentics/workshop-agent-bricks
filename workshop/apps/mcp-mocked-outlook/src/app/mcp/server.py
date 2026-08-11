"""
The MCP server and the tools it publishes.

The server object is built at import so that the tool decorators can register against it
and so that anything wanting to inspect the tool list can do so without starting an
application. The store it works on arrives later, through bind(), because the factory
owns the store and there must be exactly one of it: a second store would mean a second
in-process cache, and the two would drift apart mailbox by mailbox.

Tools take no identity argument. Which mailbox a call lands in is decided by the
forwarded identity of the HTTP request carrying it, never by the agent, so an agent
cannot read or write somebody else's mail by asking nicely.

Every tool is async and does its actual work on a worker thread. FastMCP calls a
synchronous tool inline on the event loop, and each of these tools waits on a Unity
Catalog volume over HTTPS, so a synchronous tool would stop the whole process for the
length of that round-trip: with a room full of people driving agents at once, every
tool call would queue behind whichever one is in flight. See _offload.
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any, Final

import anyio.to_thread
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from app.core.identity import current_caller

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.store.mailbox import MailboxStore

INSTRUCTIONS: Final = (
    "This MCP server simulates Microsoft Outlook email and calendar. "
    "Use the tools to read emails, send messages, manage calendar events, "
    "and check availability. All data is scoped to the authenticated user. "
    "Data is persisted in a Databricks Volume and shared across users."
)

mcp_server: FastMCP = FastMCP(
    "Mocked Outlook",
    # Every request must be self-contained. The Databricks clients (AI Playground, Agent
    # Bricks, Genie) do not perform the initialize handshake and send no mcp-session-id
    # header, so a stateful server turns them away with "400 Bad Request: Missing
    # session ID". Stateless also survives Apps spreading requests across replicas.
    stateless_http=True,
    # The SDK enables DNS-rebinding protection by default with an EMPTY origin allow
    # list, so it rejects any request carrying an Origin header with "403 Invalid Origin
    # header". Databricks adds MCP servers from the browser, which always sends Origin,
    # so the server looks unreachable. The app already sits behind the Apps OAuth proxy,
    # where an untrusted page cannot mint a valid token.
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
    instructions=INSTRUCTIONS,
)


class _Binding:
    """
    The one slot the application fills in before it starts serving.

    A module-level singleton is right for the store, which is process-wide by design;
    it would be wrong for the caller, which is per-request and therefore read from the
    context rather than kept here.

    Attributes:
        store: The mailbox store every tool works on.
        default_user: Mailbox used when a request carries no forwarded identity.
    """

    store: MailboxStore | None = None
    default_user: str = ""


_binding: Final = _Binding()


def bind(store: MailboxStore, default_user: str) -> None:
    """
    Give the tools the store they operate on.

    Args:
        store: The process-wide mailbox store.
        default_user: Mailbox to use when no forwarded identity is present, which is
            the case for local runs.
    """
    _binding.store = store
    _binding.default_user = default_user


def _mailbox() -> tuple[MailboxStore, str]:
    """
    Return the store and the address the call in flight acts for.

    Returns:
        The store, and the caller's mail address.

    Raises:
        RuntimeError: If no store has been bound, which means the server is being
            driven outside the application that owns it.
    """
    store = _binding.store
    if store is None:
        message = "The MCP server has no mailbox store bound; build the application."
        raise RuntimeError(message)
    return store, current_caller(_binding.default_user)


async def _offload(work: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """
    Run one store call on a worker thread, leaving the event loop free.

    The caller is resolved before this is reached, on the loop, where the identity
    middleware bound it. anyio copies the context into the worker anyway, so the store
    would see the same answer either way, but resolving it first keeps the rule that
    identity is read once per request in one place.

    Args:
        work: The store call, with its arguments already bound.

    Returns:
        Whatever the store returned.
    """
    return await anyio.to_thread.run_sync(work)


@mcp_server.tool()
async def list_emails(
    folder: str = "inbox",
    unread_only: bool = False,
) -> dict[str, Any]:
    """
    List emails from a specific folder (inbox, sent, or drafts).

    Args:
        folder: Folder to read; one of inbox, sent or drafts.
        unread_only: Keep only unread mail, which the inbox alone can have.

    Returns:
        The folder's messages in summary form, or an error for an unknown folder.
    """
    store, user = _mailbox()
    return await _offload(partial(store.list_emails, user, folder, unread_only))


@mcp_server.tool()
async def get_email(email_id: str) -> dict[str, Any]:
    """
    Get full content of an email by ID.

    Args:
        email_id: Identifier of the message.

    Returns:
        The message and the folder holding it, or an error when there is no such
        message. Reading an unread inbox message marks it read.
    """
    store, user = _mailbox()
    return await _offload(partial(store.get_email, user, email_id))


@mcp_server.tool()
async def send_email(to: str, subject: str, body: str) -> dict[str, Any]:
    """
    Send an email. It will appear in your Sent folder and recipient's Inbox.

    Args:
        to: Address to deliver to.
        subject: Subject line.
        body: Message text.

    Returns:
        The message as sent.
    """
    store, user = _mailbox()
    return await _offload(partial(store.send_email, user, to, subject, body))


@mcp_server.tool()
async def draft_email(to: str, subject: str, body: str) -> dict[str, Any]:
    """
    Write an email and leave it in the user's Drafts folder without sending it.

    Prefer this over send_email when the message is going to a customer or anyone
    outside the company, so a person reads it before it goes out.

    Args:
        to: Intended recipient, which a draft is allowed to leave empty.
        subject: Subject line.
        body: Message text.

    Returns:
        The draft as saved, with a note making clear that nothing was sent.
    """
    store, user = _mailbox()
    return await _offload(partial(store.draft_email, user, to, subject, body))


@mcp_server.tool()
async def update_draft(
    draft_id: str,
    to: str | None = None,
    subject: str | None = None,
    body: str | None = None,
) -> dict[str, Any]:
    """
    Revise a draft that is already in the Drafts folder. Omitted fields are left alone.

    Args:
        draft_id: Identifier of the draft.
        to: New recipient, or omitted to keep the current one.
        subject: New subject, or omitted to keep the current one.
        body: New text, or omitted to keep the current one.

    Returns:
        The revised draft, or an error when there is no such draft.
    """
    store, user = _mailbox()
    return await _offload(
        partial(store.update_draft, user, draft_id, to, subject, body),
    )


@mcp_server.tool()
async def send_draft(draft_id: str) -> dict[str, Any]:
    """
    Send a draft that is sitting in the Drafts folder.

    This actually delivers the message. Only do it when the user has asked you to send,
    rather than to prepare something for them.

    Args:
        draft_id: Identifier of the draft.

    Returns:
        The message as sent, or an error when there is no such draft or it has no
        recipient.
    """
    store, user = _mailbox()
    return await _offload(partial(store.send_draft, user, draft_id))


@mcp_server.tool()
async def discard_draft(draft_id: str) -> dict[str, Any]:
    """
    Delete a draft from the Drafts folder without sending it.

    Args:
        draft_id: Identifier of the draft.

    Returns:
        What was discarded, or an error when there is no such draft.
    """
    store, user = _mailbox()
    return await _offload(partial(store.discard_draft, user, draft_id))


@mcp_server.tool()
async def reply_to_email(email_id: str, body: str) -> dict[str, Any]:
    """
    Reply to an email by ID.

    Args:
        email_id: Identifier of the message being replied to.
        body: Reply text.

    Returns:
        The reply as sent, or an error when there is no such message.
    """
    store, user = _mailbox()
    return await _offload(partial(store.reply_to_email, user, email_id, body))


@mcp_server.tool()
async def search_emails(query: str) -> dict[str, Any]:
    """
    Search emails by keyword across all folders.

    Args:
        query: Text to look for in subjects and bodies, matched case-insensitively.

    Returns:
        One entry per match, naming the folder it was found in.
    """
    store, user = _mailbox()
    return await _offload(partial(store.search_emails, user, query))


@mcp_server.tool()
async def list_calendar_events(upcoming: bool = True) -> dict[str, Any]:
    """
    List calendar events (upcoming or past).

    Args:
        upcoming: True for events that have not started, False for past ones.

    Returns:
        The matching events in summary form, earliest first.
    """
    store, user = _mailbox()
    return await _offload(partial(store.list_calendar_events, user, upcoming))


@mcp_server.tool()
async def get_calendar_event(event_id: str) -> dict[str, Any]:
    """
    Get full details of a calendar event by ID.

    Args:
        event_id: Identifier of the event.

    Returns:
        The event, or an error when there is no such event.
    """
    store, user = _mailbox()
    return await _offload(partial(store.get_calendar_event, user, event_id))


@mcp_server.tool()
async def create_calendar_event(
    title: str,
    start_time: str,
    end_time: str,
    location: str = "",
    attendees: list[str] | None = None,
    description: str = "",
) -> dict[str, Any]:
    """
    Create a new calendar event.

    Args:
        title: Event title.
        start_time: ISO start timestamp.
        end_time: ISO end timestamp, which must be after the start.
        location: Room or meeting link.
        attendees: Invitees; the caller alone when omitted.
        description: Agenda or notes.

    Returns:
        The event as created, or an error when the times do not make sense.
    """
    store, user = _mailbox()
    return await _offload(
        partial(
            store.create_calendar_event,
            user,
            title,
            start_time,
            end_time,
            location,
            attendees,
            description,
        ),
    )


@mcp_server.tool()
async def delete_calendar_event(event_id: str) -> dict[str, Any]:
    """
    Delete a calendar event by ID.

    Args:
        event_id: Identifier of the event.

    Returns:
        What was deleted, or an error when there is no such event.
    """
    store, user = _mailbox()
    return await _offload(partial(store.delete_calendar_event, user, event_id))


@mcp_server.tool()
async def get_free_busy(
    date: str, start_hour: int = 8, end_hour: int = 18
) -> dict[str, Any]:
    """
    Check free/busy status for a specific date.

    Args:
        date: ISO date to look at.
        start_hour: First hour of the working day, reported back for context.
        end_hour: Last hour of the working day, reported back for context.

    Returns:
        The day's busy slots, or an error when the date cannot be read.
    """
    store, user = _mailbox()
    return await _offload(
        partial(store.get_free_busy, user, date, start_hour, end_hour),
    )
