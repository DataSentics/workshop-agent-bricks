"""
The mailbox itself: storage, and every operation the UI and the MCP tools perform on it.

Each user owns one file, <volume>/mailboxes/<sanitised-address>.json. A single shared
document would make every write last-write-wins across people, which in a workshop with
a room full of users means one person's send silently drops another's.

The volume is reached over the SDK Files API because a Unity Catalog volume is not
mounted into an App container. Read and write failures are logged and then tolerated:
the in-process cache stays authoritative, so a demo keeps running against a volume that
is missing or misconfigured, and /health reports that writes are not landing.

Every timestamp written here is naive UTC. Callers routinely send zone-aware values
(browsers call toISOString(), agents copy the Z suffix through), and comparing an aware
datetime to a naive one raises TypeError, so timestamps are normalised on the way in.

Every operation here runs on a worker thread, several at a time, so one person waiting
on the volume does not hold up the room. That makes the in-process cache shared mutable
state, and each operation therefore holds the lock for the mailbox it touches: see
_serialised and _lock_for below for the one rule that keeps it deadlock-free.
"""

from __future__ import annotations

import io
import json
import logging
import re
import threading
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, TypeVar

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.core.settings import MailboxSettings

logger = logging.getLogger(__name__)

FOLDERS: Final[tuple[str, ...]] = ("inbox", "sent", "drafts")

_SEED_PATH: Final[Path] = Path(__file__).resolve().parents[1] / "data/outlook_seed.json"
_UNSAFE_IN_FILENAME: Final = re.compile(r"[^a-z0-9._-]")

_T = TypeVar("_T")


def _serialised(method: Callable[..., _T]) -> Callable[..., _T]:
    """
    Hold one mailbox's lock for the whole of an operation on it.

    Reads and writes are a load, a mutation and a save, and the three have to look
    atomic to anyone else working the same mailbox: without this, two threads can
    both remove the same draft, or one can serialise the document to JSON while the
    other is still inserting into it.

    Only for methods that take the mailbox owner first and touch that mailbox alone.
    Anything reaching into a second mailbox - delivery - takes the two locks one after
    the other rather than one inside the other, because two people mailing each other
    at the same moment would otherwise deadlock.

    Args:
        method: Store method whose first argument is the owner's address.

    Returns:
        The same method, with the owner's lock held around it.
    """

    @wraps(method)
    def wrapper(self: MailboxStore, user: str, *args: Any, **kwargs: Any) -> _T:
        with self._lock_for(user):
            return method(self, user, *args, **kwargs)

    return wrapper


def utc_now() -> datetime:
    """
    Return the clock every stored timestamp is written in: naive UTC.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def parse_timestamp(value: str) -> datetime:
    """
    Parse an ISO timestamp into a naive UTC datetime.

    Args:
        value: ISO 8601 timestamp, with or without a zone.

    Returns:
        The same instant with the zone stripped, comparable to utc_now().

    Raises:
        ValueError: If the value is not an ISO timestamp.
    """
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def mailbox_slug(user: str) -> str:
    """
    Reduce a mail address to something safe to use as a file name.

    Args:
        user: Mail address of the mailbox owner.

    Returns:
        The address lowercased, with every character outside [a-z0-9._-] replaced by
        an underscore.
    """
    return _UNSAFE_IN_FILENAME.sub("_", user.strip().lower())


def _load_seed() -> dict[str, Any]:
    """
    Read the seed document.

    Returns:
        The seed, freshly parsed. It is read per materialisation rather than cached so
        that no two mailboxes end up sharing a nested list.
    """
    with _SEED_PATH.open(encoding="utf-8") as handle:
        seed: dict[str, Any] = json.load(handle)
    return seed


def _seeded_message(
    entry: dict[str, Any],
    message_id: str,
    *,
    sender: str,
    recipient: str,
) -> dict[str, Any]:
    """
    Map one seed entry onto a stored message.

    All eight keys are always present, because every reader indexes them directly
    rather than checking first. The seed's display names are dropped: only the inbox
    carries one, and the UI derives a name from the address anyway.

    Args:
        entry: One inbox, sent or drafts entry from the seed.
        message_id: Identifier to give the message.
        sender: Address the message is from.
        recipient: Address the message is to.

    Returns:
        The stored message.
    """
    return {
        "id": message_id,
        "from": sender,
        "to": recipient,
        "subject": entry["subject"],
        "body": entry["body"],
        # Seed dates are absolute and deliberately aligned with the Delta tables the
        # rest of the workshop reads, so they are used exactly as written.
        "date": entry["date"],
        "read": entry["read"],
        "has_attachments": entry["has_attachments"],
    }


def _seeded_event(
    entry: dict[str, Any],
    event_id: str,
    *,
    organizer: str,
) -> dict[str, Any]:
    """
    Map one seed calendar entry onto a stored event.

    Args:
        entry: One calendar entry from the seed.
        event_id: Identifier to give the event.
        organizer: Address the event is organised by.

    Returns:
        The stored event.
    """
    return {
        "id": event_id,
        "title": entry["title"],
        "start_time": entry["start"],
        "end_time": entry["end"],
        "location": entry["location"],
        "attendees": entry["attendees"],
        "description": entry["description"],
        "is_recurring": entry["is_recurring"],
        "organizer": organizer,
    }


def materialise(user: str) -> dict[str, Any]:
    """
    Build a user's mailbox from the seed.

    The seed is written from one person's point of view, so it is rewritten for whoever
    is being seeded: inbox mail is addressed to them, sent mail and drafts come from
    them, and their calendar is theirs to organise.

    Args:
        user: Mail address of the mailbox owner.

    Returns:
        A complete mailbox, ready to be stored.
    """
    seed = _load_seed()
    slug = mailbox_slug(user)
    return {
        "emails": {
            "inbox": [
                _seeded_message(
                    entry,
                    f"email-{slug}-i{number:03d}",
                    sender=entry["from"],
                    recipient=user,
                )
                for number, entry in enumerate(seed["inbox"], start=1)
            ],
            "sent": [
                _seeded_message(
                    entry,
                    f"email-{slug}-s{number:03d}",
                    sender=user,
                    recipient=entry["to"],
                )
                for number, entry in enumerate(seed["sent"], start=1)
            ],
            "drafts": [
                _seeded_message(
                    entry,
                    f"email-{slug}-d{number:03d}",
                    sender=user,
                    recipient=entry["to"],
                )
                for number, entry in enumerate(seed["drafts"], start=1)
            ],
        },
        "calendar": [
            _seeded_event(entry, f"cal-{slug}-{number:03d}", organizer=user)
            for number, entry in enumerate(seed["calendar"], start=1)
        ],
    }


class MailboxStore:
    """
    Every user's mailbox, cached in this process and persisted one file per user.

    The cache is keyed by the same slug the file is named after, not by the address as
    it arrived: the proxy is free to forward Tomas.Richter@Saldo.CZ today and the
    lowercase form tomorrow, and two cache entries over one file would quietly undo each
    other's writes. It is never invalidated: within a replica it is the truth, and the
    volume is where that truth survives a restart. Two replicas editing the same mailbox
    would still diverge, which is acceptable for a demo and is why each user is at least
    kept out of everybody else's file.

    Several people are served at once, on worker threads, so the cache is reached from
    more than one thread at a time. One lock per mailbox is what makes that safe, and
    per mailbox rather than one for the store so that a slow volume round-trip for one
    person does not stop everybody else being served.
    """

    def __init__(self, settings: MailboxSettings) -> None:
        self._directory = settings.volume_path.rstrip("/") + "/mailboxes"
        self._cache: dict[str, dict[str, Any]] = {}
        self._workspace: WorkspaceClient | None = None
        self._directory_ready = False
        self._persistent = True
        # Re-entrant, because the outer operation holds the lock and the load and save
        # inside it take the same one again.
        self._locks: dict[str, threading.RLock] = {}
        # Guards the lock table itself, and is held only long enough to read or add an
        # entry - never across the volume.
        self._locks_guard = threading.Lock()
        self._client_guard = threading.Lock()

    def _lock_for(self, user: str) -> threading.RLock:
        """
        Return the lock for one mailbox, creating it the first time it is asked for.

        Keyed by the slug rather than the address as it arrived, for the same reason
        the cache is: two locks over one file would not exclude each other.

        Args:
            user: Mail address of the mailbox owner.

        Returns:
            The lock guarding that mailbox.
        """
        slug = mailbox_slug(user)
        with self._locks_guard:
            lock = self._locks.get(slug)
            if lock is None:
                lock = self._locks[slug] = threading.RLock()
            return lock

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------

    def storage_status(self) -> str:
        """
        Report whether the volume is currently taking reads and writes.

        Returns:
            "ok", or "unavailable" once an operation against the volume has failed.
        """
        return "ok" if self._persistent else "unavailable"

    def _client(self) -> WorkspaceClient:
        """
        Return the workspace client, built on first use.

        Constructing it looks for credentials, so it is deliberately not done while the
        application is being built: a local run with no Databricks configuration should
        start and serve from memory rather than fail at import.

        Checked, locked, then checked again: several threads reach this at once on the
        first request, and building one client per thread would open a connection pool
        per thread and throw all but one away.
        """
        if self._workspace is None:
            with self._client_guard:
                if self._workspace is None:
                    self._workspace = WorkspaceClient()
        return self._workspace

    def _path(self, user: str) -> str:
        """
        Return the volume path holding one user's mailbox.
        """
        return f"{self._directory}/{mailbox_slug(user)}.json"

    def _download(self, user: str) -> dict[str, Any] | None:
        """
        Read one mailbox file.

        Args:
            user: Mail address of the mailbox owner.

        Returns:
            The stored mailbox, or None when the user has no file yet or the volume
            could not be read.
        """
        path = self._path(user)
        try:
            response = self._client().files.download(path)
            payload = response.contents.read().decode("utf-8")  # type: ignore[union-attr]
        except NotFound:
            return None
        except Exception:
            logger.warning(
                "Cannot read %s; serving it from memory",
                path,
                exc_info=True,
            )
            self._persistent = False
            return None
        self._persistent = True
        mailbox: dict[str, Any] = json.loads(payload)
        return mailbox

    def _upload(self, user: str, mailbox: dict[str, Any]) -> None:
        """
        Write one mailbox file, tolerating a volume that will not take it.

        Args:
            user: Mail address of the mailbox owner.
            mailbox: Document to store.
        """
        path = self._path(user)
        payload = json.dumps(mailbox, indent=2).encode("utf-8")
        try:
            if not self._directory_ready:
                # Uploading into a directory that does not exist fails, and the
                # mailboxes directory is ours to create the first time round.
                self._client().files.create_directory(self._directory)
                self._directory_ready = True
            self._client().files.upload(path, io.BytesIO(payload), overwrite=True)
        except Exception:
            logger.warning(
                "Cannot write %s; the change is in memory only",
                path,
                exc_info=True,
            )
            self._persistent = False
            return
        self._persistent = True

    @_serialised
    def load(self, user: str) -> dict[str, Any]:
        """
        Return a user's mailbox, seeding it the first time they are seen.

        Args:
            user: Mail address of the mailbox owner.

        Returns:
            The mailbox, which the caller may mutate before handing it back to save().
        """
        cached = self._cache.get(mailbox_slug(user))
        if cached is not None:
            return cached

        stored = self._download(user)
        if stored is not None:
            self._cache[mailbox_slug(user)] = stored
            return stored

        logger.info("Seeding a mailbox for %s", user)
        mailbox = materialise(user)
        self.save(user, mailbox)
        return mailbox

    @_serialised
    def save(self, user: str, mailbox: dict[str, Any]) -> None:
        """
        Store a user's mailbox.

        Args:
            user: Mail address of the mailbox owner.
            mailbox: Document to store.
        """
        self._cache[mailbox_slug(user)] = mailbox
        self._upload(user, mailbox)

    @_serialised
    def reset(self, user: str) -> dict[str, Any]:
        """
        Rebuild one user's mailbox from the seed, discarding what is there.

        Args:
            user: Mail address of the mailbox owner.

        Returns:
            The status body the demo endpoint returns.
        """
        self.save(user, materialise(user))
        logger.info("Reset the mailbox of %s", user)
        return {"status": "reset", "user": user}

    # ------------------------------------------------------------------
    # Mail
    # ------------------------------------------------------------------

    @_serialised
    def list_emails(
        self,
        user: str,
        folder: str = "inbox",
        unread_only: bool = False,
    ) -> dict[str, Any]:
        """
        Summarise one folder.

        Args:
            user: Mail address of the mailbox owner.
            folder: inbox, sent or drafts.
            unread_only: Keep only unread mail; meaningful in the inbox alone.

        Returns:
            The folder's summaries, or an error when the folder name is unknown.
        """
        if folder not in FOLDERS:
            return {
                "error": (
                    f"Invalid folder '{folder}'. Use 'inbox', 'sent', or 'drafts'."
                ),
            }

        mailbox = self.load(user)
        emails = mailbox["emails"][folder]
        if unread_only and folder == "inbox":
            emails = [email for email in emails if not email["read"]]

        summaries = [
            {
                "id": email["id"],
                "from": email["from"],
                "to": email["to"],
                "subject": email["subject"],
                "date": email["date"],
                "read": email["read"],
                "has_attachments": email["has_attachments"],
                "preview": " ".join(email.get("body", "").split())[:120],
            }
            for email in emails
        ]
        return {"folder": folder, "count": len(summaries), "emails": summaries}

    @_serialised
    def get_email(self, user: str, email_id: str) -> dict[str, Any]:
        """
        Return one message in full, marking inbox mail as read.

        Args:
            user: Mail address of the mailbox owner.
            email_id: Identifier of the message.

        Returns:
            The message and the folder it sits in, or an error when there is no such
            message.
        """
        mailbox = self.load(user)
        for folder in FOLDERS:
            for email in mailbox["emails"][folder]:
                if email["id"] != email_id:
                    continue
                if folder == "inbox" and not email["read"]:
                    email["read"] = True
                    self.save(user, mailbox)
                return {"folder": folder, "email": email}

        return {"error": f"Email with id '{email_id}' not found."}

    def send_email(self, user: str, to: str, subject: str, body: str) -> dict[str, Any]:
        """
        Send a message: into the sender's Sent folder and the recipient's Inbox.

        Args:
            user: Mail address of the sender.
            to: Address to deliver to.
            subject: Subject line.
            body: Message text.

        Returns:
            The message as stored.
        """
        email = {
            "id": f"email-{int(utc_now().timestamp() * 1000)}",
            "from": user,
            "to": to,
            "subject": subject,
            "body": body,
            "date": utc_now().isoformat(),
            "read": True,
            "has_attachments": False,
        }
        with self._lock_for(user):
            mailbox = self.load(user)
            mailbox["emails"]["sent"].insert(0, email)
            self.save(user, mailbox)
        # Deliberately after the sender's lock is released rather than inside it.
        # _deliver takes the recipient's, and two people mailing each other at the same
        # moment would each hold one and wait for the other's forever.
        self._deliver(user, to, email)
        return {"status": "sent", "email": email}

    def _deliver(self, sender: str, recipient: str, email: dict[str, Any]) -> None:
        """
        Drop a copy of a sent message into the recipient's own mailbox file.

        Takes the recipient's lock and no other. Callers must not already hold a
        mailbox lock when they call this; see send_email for why.

        Args:
            sender: Address the message came from, for the log line.
            recipient: Address whose inbox receives it.
            email: The message as stored on the sender's side.
        """
        with self._lock_for(recipient):
            mailbox = self.load(recipient)
            # A copy, not the same object: the recipient's copy is unread while the
            # sender's stays read, and the two now live in different files.
            delivered = email.copy()
            delivered["read"] = False
            mailbox["emails"]["inbox"].insert(0, delivered)
            self.save(recipient, mailbox)
        logger.info("Delivered mail from %s to %s", sender, recipient)

    @_serialised
    def draft_email(
        self,
        user: str,
        to: str,
        subject: str,
        body: str,
    ) -> dict[str, Any]:
        """
        Write a message into the Drafts folder without sending it.

        Args:
            user: Mail address of the mailbox owner.
            to: Intended recipient, which a draft is allowed to leave empty.
            subject: Subject line.
            body: Message text.

        Returns:
            The draft as stored, with a note making clear nothing was sent.
        """
        mailbox = self.load(user)
        # The same eight fields as any other message: folder membership is the only
        # thing that makes this a draft, and every reader indexes these keys.
        draft = {
            "id": f"draft-{int(utc_now().timestamp() * 1000)}",
            "from": user,
            "to": to,
            "subject": subject,
            "body": body,
            "date": utc_now().isoformat(),
            # Drafts are never "unread": the UI styles unread messages bold with a
            # notification dot, which would be wrong for something you wrote yourself.
            "read": True,
            "has_attachments": False,
        }
        mailbox["emails"]["drafts"].insert(0, draft)
        self.save(user, mailbox)

        logger.info("Drafted '%s' for %s (not sent)", subject, user)
        return {
            "status": "drafted",
            "draft": draft,
            "note": (
                "Saved to Drafts. Nothing has been sent. "
                "Call send_draft to send it, or the user can "
                "review it in Outlook first."
            ),
        }

    @_serialised
    def update_draft(
        self,
        user: str,
        draft_id: str,
        to: str | None = None,
        subject: str | None = None,
        body: str | None = None,
    ) -> dict[str, Any]:
        """
        Revise a draft in place, leaving omitted fields alone.

        Args:
            user: Mail address of the mailbox owner.
            draft_id: Identifier of the draft.
            to: New recipient, or None to keep the current one.
            subject: New subject, or None to keep the current one.
            body: New text, or None to keep the current one.

        Returns:
            The revised draft, or an error when there is no such draft.
        """
        mailbox = self.load(user)
        draft = _find_draft(mailbox, draft_id)
        if draft is None:
            return {
                "error": (
                    f"No draft with id '{draft_id}'. "
                    "Use list_emails(folder='drafts') to see them."
                ),
            }

        for field, value in (("to", to), ("subject", subject), ("body", body)):
            if value is not None:
                draft[field] = value
        draft["date"] = utc_now().isoformat()
        self.save(user, mailbox)

        return {"status": "updated", "draft": draft}

    def send_draft(self, user: str, draft_id: str) -> dict[str, Any]:
        """
        Send a draft that is sitting in the Drafts folder.

        Args:
            user: Mail address of the mailbox owner.
            draft_id: Identifier of the draft.

        Returns:
            The message as sent, or an error when there is no such draft or it has no
            recipient.
        """
        with self._lock_for(user):
            mailbox = self.load(user)
            draft = _find_draft(mailbox, draft_id)
            if draft is None:
                return {"error": f"No draft with id '{draft_id}'."}
            if not (draft.get("to") or "").strip():
                return {
                    "error": (
                        "This draft has no recipient. "
                        "Set one with update_draft before sending."
                    ),
                }

            # A draft carries no status field, so sending it means physically moving the
            # message out of drafts and into sent. The date is stamped now, because what
            # matters on a sent message is when it went, not when it was written.
            mailbox["emails"]["drafts"].remove(draft)
            draft["date"] = utc_now().isoformat()
            mailbox["emails"]["sent"].insert(0, draft)
            self.save(user, mailbox)
            recipient = str(draft["to"])

        # Outside the sender's lock, for the reason given in send_email.
        self._deliver(user, recipient, draft)

        logger.info("Sent draft %s from %s to %s", draft_id, user, recipient)
        return {"status": "sent", "email": draft}

    @_serialised
    def discard_draft(self, user: str, draft_id: str) -> dict[str, Any]:
        """
        Delete a draft without sending it.

        Args:
            user: Mail address of the mailbox owner.
            draft_id: Identifier of the draft.

        Returns:
            What was discarded, or an error when there is no such draft.
        """
        mailbox = self.load(user)
        draft = _find_draft(mailbox, draft_id)
        if draft is None:
            return {"error": f"No draft with id '{draft_id}'."}

        mailbox["emails"]["drafts"].remove(draft)
        self.save(user, mailbox)
        return {"status": "discarded", "discarded_subject": draft["subject"]}

    def reply_to_email(self, user: str, email_id: str, body: str) -> dict[str, Any]:
        """
        Reply to a message, to whichever side of it is not the mailbox owner.

        Args:
            user: Mail address of the mailbox owner.
            email_id: Identifier of the message being replied to.
            body: Reply text.

        Returns:
            The reply as sent, or an error when there is no such message.
        """
        # The lock covers finding the message and nothing more: send_email takes it
        # again for the write and then delivers with it released, and holding it across
        # that call would put this thread inside two mailboxes at once.
        with self._lock_for(user):
            mailbox = self.load(user)
            original = None
            for folder in FOLDERS:
                for email in mailbox["emails"][folder]:
                    if email["id"] == email_id:
                        original = email
                        break
                if original:
                    break

            if not original:
                return {"error": f"Email with id '{email_id}' not found."}

            reply_to = original["from"] if original["from"] != user else original["to"]
            subject = f"Re: {original['subject']}"

        return self.send_email(user, reply_to, subject, body)

    @_serialised
    def search_emails(self, user: str, query: str) -> dict[str, Any]:
        """
        Search subjects and bodies across every folder.

        Args:
            user: Mail address of the mailbox owner.
            query: Text to look for, matched case-insensitively.

        Returns:
            One entry per match, naming the folder it was found in.
        """
        mailbox = self.load(user)
        needle = query.lower()

        results = [
            {
                "id": email["id"],
                "folder": folder,
                "from": email["from"],
                "to": email["to"],
                "subject": email["subject"],
                "date": email["date"],
            }
            for folder in FOLDERS
            for email in mailbox["emails"][folder]
            if needle in email["subject"].lower() or needle in email["body"].lower()
        ]
        return {"query": query, "count": len(results), "results": results}

    # ------------------------------------------------------------------
    # Calendar
    # ------------------------------------------------------------------

    @_serialised
    def list_calendar_events(self, user: str, upcoming: bool = True) -> dict[str, Any]:
        """
        Summarise the calendar, either side of now.

        Args:
            user: Mail address of the mailbox owner.
            upcoming: True for events that have not started, False for past ones.

        Returns:
            The matching events, earliest first.
        """
        mailbox = self.load(user)
        now = utc_now()

        events = [
            event
            for event in mailbox["calendar"]
            if (parse_timestamp(event["start_time"]) >= now) == upcoming
        ]
        events.sort(key=lambda event: event["start_time"])

        summaries = [
            {
                "id": event["id"],
                "title": event["title"],
                "start_time": event["start_time"],
                "end_time": event["end_time"],
                "location": event["location"],
                "is_recurring": event["is_recurring"],
            }
            for event in events
        ]
        return {
            "type": "upcoming" if upcoming else "past",
            "count": len(summaries),
            "events": summaries,
        }

    @_serialised
    def get_calendar_event(self, user: str, event_id: str) -> dict[str, Any]:
        """
        Return one event in full.

        Args:
            user: Mail address of the mailbox owner.
            event_id: Identifier of the event.

        Returns:
            The event, or an error when there is no such event.
        """
        mailbox = self.load(user)
        for event in mailbox["calendar"]:
            if event["id"] == event_id:
                return {"event": event}

        return {"error": f"Calendar event with id '{event_id}' not found."}

    @_serialised
    def create_calendar_event(
        self,
        user: str,
        title: str,
        start_time: str,
        end_time: str,
        location: str = "",
        attendees: list[str] | None = None,
        description: str = "",
    ) -> dict[str, Any]:
        """
        Add an event to the calendar.

        Args:
            user: Mail address of the mailbox owner, who organises it.
            title: Event title.
            start_time: ISO start timestamp.
            end_time: ISO end timestamp, which must be after the start.
            location: Room or link.
            attendees: Invitees; the owner alone when omitted.
            description: Agenda or notes.

        Returns:
            The event as stored, or an error when the times do not make sense.
        """
        # Normalised on write, so everything in storage is naive-UTC ISO whatever
        # format the caller used.
        try:
            starts_at = parse_timestamp(start_time)
            ends_at = parse_timestamp(end_time)
        except ValueError:
            return {
                "error": (
                    "Invalid start_time or end_time. "
                    "Use ISO format like '2026-03-15T14:00:00'."
                ),
            }
        if ends_at <= starts_at:
            return {"error": "end_time must be after start_time."}

        mailbox = self.load(user)
        event = {
            "id": f"cal-{int(utc_now().timestamp() * 1000)}",
            "title": title,
            "start_time": starts_at.isoformat(),
            "end_time": ends_at.isoformat(),
            "location": location,
            "attendees": attendees or [user],
            "description": description,
            "is_recurring": False,
            "organizer": user,
        }
        mailbox["calendar"].append(event)
        self.save(user, mailbox)

        logger.info("User %s created event: %s", user, title)
        return {"status": "created", "event": event}

    @_serialised
    def delete_calendar_event(self, user: str, event_id: str) -> dict[str, Any]:
        """
        Remove an event from the calendar.

        Args:
            user: Mail address of the mailbox owner.
            event_id: Identifier of the event.

        Returns:
            What was deleted, or an error when there is no such event.
        """
        mailbox = self.load(user)
        for index, event in enumerate(mailbox["calendar"]):
            if event["id"] == event_id:
                removed = mailbox["calendar"].pop(index)
                self.save(user, mailbox)
                logger.info("User %s deleted event: %s", user, removed["title"])
                return {"status": "deleted", "deleted_event": removed["title"]}

        return {"error": f"Calendar event with id '{event_id}' not found."}

    @_serialised
    def get_free_busy(
        self,
        user: str,
        date: str,
        start_hour: int = 8,
        end_hour: int = 18,
    ) -> dict[str, Any]:
        """
        Report what is booked on one day.

        Args:
            user: Mail address of the mailbox owner.
            date: ISO date to look at.
            start_hour: First hour of the working day, reported back for context.
            end_hour: Last hour of the working day, reported back for context.

        Returns:
            The day's busy slots, or an error when the date cannot be read.
        """
        try:
            day = parse_timestamp(date).date()
        except ValueError:
            return {
                "error": (
                    f"Invalid date format: '{date}'. Use ISO format like '2024-03-15'."
                ),
            }

        mailbox = self.load(user)
        busy_slots = [
            {
                "title": event["title"],
                "start": event["start_time"],
                "end": event["end_time"],
            }
            for event in mailbox["calendar"]
            if parse_timestamp(event["start_time"]).date() == day
        ]
        busy_slots.sort(key=lambda slot: slot["start"])

        return {
            "date": date,
            "business_hours": f"{start_hour}:00 - {end_hour}:00",
            "busy_slots": busy_slots,
            "total_meetings": len(busy_slots),
            "status": "busy" if busy_slots else "free",
        }


def _find_draft(mailbox: dict[str, Any], draft_id: str) -> dict[str, Any] | None:
    """
    Find one draft by identifier.

    Args:
        mailbox: The owner's mailbox.
        draft_id: Identifier to look for.

    Returns:
        The draft, still attached to the mailbox so edits to it are saved, or None.
    """
    for draft in mailbox["emails"]["drafts"]:
        if draft["id"] == draft_id:
            return draft
    return None
