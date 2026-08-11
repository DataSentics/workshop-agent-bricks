"""
The support case desk, backed by Unity Catalog.

Unlike the mocked Outlook mailbox, which keeps its state in a JSON blob on a volume,
CaseHub reads and writes real tables. That is the point of it: when the agent moves a
case to S1, the Genie agent reporting on support load sees an S1, because there is only
one copy of the truth.

What it never writes to is the seeded tables. They are the story every person running
the workshop starts from, and a workshop where the first person to close a case changes
it for everyone else is not a workshop. Instead each person's changes are one row per
case in case_state keyed on their email, and every read lays those rows over the seed:

    support_cases   the story as everyone finds it       (read only)
    case_notes      the narrative as everyone finds it   (read only)
    case_state      what you personally did to it        (one row per case you touched)

deploy_state.py builds the support_cases_live and case_notes_live views over exactly
this join, and CaseHub cannot use them: it queries as its own service principal rather
than as the person talking to it, so where the views pass current_user() this module
passes a quoted email. That is the one place the join is written twice, and it is
written here in the same shape so the two can be read side by side.

Every statement goes through the SQL warehouse with the Statement Execution API. Values
reaching it come from an LLM, so every one of them goes through lit().

Resetting is deleting your own rows. Nothing you did was ever in the seeded tables, so
there is nothing to put back.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.core.settings import CatalogSettings

logger = logging.getLogger(__name__)

# The values the tables already use. An agent that invents "Critical" or "Resolved"
# would produce a row nothing else in the workshop can read, so writes are validated
# against these rather than passing free text through.
SEVERITIES: tuple[str, ...] = ("S1", "S2", "S3", "S4")
STATUSES: tuple[str, ...] = ("Open", "In progress", "Waiting for customer", "Closed")
ENGINEERS: tuple[str, ...] = (
    "Filip Doležal",
    "Ivana Kramářová",
    "Ondřej Bureš",
    "Tereza Marková",
)

# How a note the agent wrote signs itself. A note written by a person is signed with
# their email, so months later the two are told apart by reading them.
AGENT_AUTHOR = "CaseHub agent"

# How a statement that has not settled is waited on. The first wait is the warehouse's
# own, and only a warehouse that was asleep gets past it; polling that one flat out
# would spin a core and hold the worker thread that is serving somebody, so it is paced
# and it gives up rather than waiting for a warehouse that is never coming back.
POLL_INTERVAL_SECONDS = 1.0
POLL_TIMEOUT_SECONDS = 120.0

# The shape one row of the desk's SQL comes back in. The warehouse hands every column
# over as text, nulls included, which is what the UI and the agent both see.
CaseRow = dict[str, Any]

# What a case looks like once the client name is joined in and the timestamps are
# readable. `c` is the overlaid case, `cl` the customer that raised it.
_CASE_COLUMNS = """
    c.case_id, c.client_id, cl.short_name AS customer, c.subject, c.status, c.severity,
    c.category, c.channel, c.reported_by, c.assigned_to,
    date_format(c.opened_at, 'yyyy-MM-dd HH:mm') AS opened_at,
    date_format(c.closed_at, 'yyyy-MM-dd HH:mm') AS closed_at,
    c.resolution_days, c.linked_incident_id, c.linked_run_id
"""


class CaseError(Exception):
    """
    Something the caller asked for that the case desk will not do.
    """


def lit(value: Any) -> str:
    """
    Render a value as a SQL literal.

    Everything reaching this comes from an LLM or from a text box, so nothing is
    interpolated raw: strings are quoted and their quotes doubled.

    Args:
        value: The value to render.

    Returns:
        A literal safe to concatenate into a statement.
    """
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    return "'" + str(value).replace("\\", "\\\\").replace("'", "''") + "'"


def _require(value: str, allowed: tuple[str, ...], what: str) -> str:
    """
    Match a value case-insensitively and return the table's own spelling.

    An agent will say "in progress" or "IN PROGRESS"; the column holds "In progress".
    Correcting that is kinder than rejecting it, but an unrecognised value is refused
    rather than written.

    Args:
        value: What the caller asked for.
        allowed: The vocabulary the column uses.
        what: Name of the field, for the refusal.

    Returns:
        The allowed value, spelled as the table spells it.

    Raises:
        CaseError: If the value is not one of the allowed ones.
    """
    for candidate in allowed:
        if candidate.lower() == str(value).strip().lower():
            return candidate
    message = f"{value!r} is not a valid {what}. Use one of: {', '.join(allowed)}."
    raise CaseError(message)


class CaseStore:
    """
    Read and write support cases as one particular person sees them.

    Every method takes the caller's email first. Reads lay that person's overrides over
    the seed, and writes go to their rows of case_state and nowhere else, so nothing one
    person does is visible to another.
    """

    def __init__(self, settings: CatalogSettings) -> None:
        self._settings = settings
        self._client: WorkspaceClient | None = None
        self._client_guard = threading.Lock()

    @property
    def workspace(self) -> WorkspaceClient:
        """
        The app's own service principal, whose credentials Databricks Apps injects.

        Built on first use rather than in the constructor, so an application that cannot
        reach the workspace still starts and reports the failure per request.

        Checked, locked, then checked again: requests are served on several threads at
        once, so without the lock the first few would each build a client, each with a
        connection pool of its own, and all but one would be thrown away.
        """
        if self._client is None:
            with self._client_guard:
                if self._client is None:
                    self._client = WorkspaceClient()
        return self._client

    # -- statements ---------------------------------------------------------------

    def run(self, statement: str) -> list[CaseRow]:
        """
        Execute one statement and return its rows as dicts.

        Args:
            statement: The SQL to run.

        Returns:
            One dict per row, keyed by column name; empty for statements that return no
            result set.

        Raises:
            CaseError: If the warehouse rejected the statement.
        """
        client = self.workspace
        response = client.statement_execution.execute_statement(
            statement=statement,
            warehouse_id=self._settings.warehouse_id,
            wait_timeout="50s",
        )
        state = response.status.state if response.status else None
        # A warehouse that was asleep answers PENDING well past the wait timeout, so
        # this polls until it settles rather than reading the first answer as final.
        # The sleep is what makes it a poll rather than a spin: this runs on a worker
        # thread, and a tight loop here would burn a core and starve the thread pool
        # everybody else is being served from.
        deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
        while state in (StatementState.PENDING, StatementState.RUNNING):
            if time.monotonic() >= deadline:
                client.statement_execution.cancel_execution(response.statement_id)
                message = (
                    "The case system took too long to answer. The warehouse may be "
                    "starting up - try again in a moment."
                )
                raise CaseError(message)
            time.sleep(POLL_INTERVAL_SECONDS)
            response = client.statement_execution.get_statement(response.statement_id)
            state = response.status.state if response.status else None
        if state != StatementState.SUCCEEDED:
            detail = str(state)
            if response.status and response.status.error:
                detail = response.status.error.message or detail
            logger.error("statement failed: %s\n%s", detail, statement[:400])
            message = f"The case system rejected that: {detail}"
            raise CaseError(message)

        manifest = response.manifest
        if not manifest or not manifest.schema or not manifest.schema.columns:
            return []
        columns = [column.name for column in manifest.schema.columns]
        rows = (response.result.data_array if response.result else None) or []
        return [dict(zip(columns, row)) for row in rows]

    def _one(self, statement: str) -> CaseRow | None:
        """
        Execute a statement expected to return at most one row.
        """
        rows = self.run(statement)
        return rows[0] if rows else None

    # -- the per-person overlay ----------------------------------------------------

    def live_cases(self, caller: str) -> str:
        """
        Cases as this caller has them: the seeded row with their changes laid over it.

        The same join deploy_state.py compiles into support_cases_live, with a quoted
        email where the view has current_user(). If the columns change here, change them
        there, or Genie and CaseHub start disagreeing about the same case.

        Args:
            caller: Whose changes to lay over the seed.

        Returns:
            A parenthesised subquery, ready to be selected from.
        """
        return f"""(
            SELECT
              c.case_id, c.client_id, c.opened_at, c.category, c.channel, c.subject,
              c.reported_by,
              coalesce(s.severity, c.severity)                     AS severity,
              coalesce(s.status, c.status)                         AS status,
              coalesce(s.assigned_to, c.assigned_to)               AS assigned_to,
              coalesce(s.closed_at, c.closed_at)                   AS closed_at,
              coalesce(s.resolution_days, c.resolution_days)       AS resolution_days,
              coalesce(s.linked_incident_id, c.linked_incident_id)
                                                                AS linked_incident_id,
              coalesce(s.linked_run_id, c.linked_run_id)           AS linked_run_id
            FROM {self._settings.cases_table} c
            LEFT JOIN {self._settings.state_table} s
              ON s.case_id = c.case_id AND s.demo_user = {lit(caller)}
        )"""

    def live_notes(self, caller: str) -> str:
        """
        Narratives as this caller has them, their own notes appended to the story.

        Args:
            caller: Whose notes to append.

        Returns:
            A parenthesised subquery, ready to be joined against.
        """
        return f"""(
            SELECT
              n.case_id,
              concat_ws('\\n\\n', nullif(n.description, ''),
                        nullif(s.notes_appended, ''))          AS description,
              coalesce(s.resolution_notes, n.resolution_notes) AS resolution_notes,
              coalesce(s.root_cause, n.root_cause)             AS root_cause
            FROM {self._settings.notes_table} n
            LEFT JOIN {self._settings.state_table} s
              ON s.case_id = n.case_id AND s.demo_user = {lit(caller)}
        )"""

    def _desk(self, caller: str) -> str:
        """
        The FROM clause every case read starts from.
        """
        return (
            f"{self.live_cases(caller)} c"
            f" LEFT JOIN {self._settings.clients_table} cl USING (client_id)"
        )

    # -- reads --------------------------------------------------------------------

    def list_cases(
        self,
        caller: str,
        *,
        status: str | None = None,
        customer: str | None = None,
        severity: str | None = None,
        assigned_to: str | None = None,
        open_only: bool = False,
        limit: int = 25,
    ) -> list[CaseRow]:
        """
        List cases, most urgent first.

        Everything after the caller is keyword-only. It used to be positional, and
        adding open_only in the middle silently turned the UI's `limit` argument into
        `open_only=50`, which hid every closed case from the queue - a case would be
        closed and then vanish rather than show as closed.

        open_only exists because "open cases" means two different things. Colloquially
        it means everything that is not closed; in this table 'Open' is also a specific
        status, meaning nobody has picked the case up yet.

        Args:
            caller: Whose view of the queue to return.
            status: Exact status to filter on.
            customer: Customer name, matched as a substring.
            severity: Exact severity to filter on.
            assigned_to: Engineer name, matched as a substring.
            open_only: Everything that is not closed.
            limit: Most rows to return.

        Returns:
            The matching cases.
        """
        where = ["1=1"]
        if open_only:
            where.append("c.status <> 'Closed'")
        if status:
            where.append(f"c.status = {lit(status)}")
        if severity:
            where.append(f"c.severity = {lit(severity)}")
        if customer:
            where.append(
                f"lower(cl.short_name) LIKE lower({lit('%' + customer + '%')})",
            )
        if assigned_to:
            where.append(
                f"lower(c.assigned_to) LIKE lower({lit('%' + assigned_to + '%')})",
            )
        return self.run(f"""
            SELECT {_CASE_COLUMNS}
            FROM {self._desk(caller)}
            WHERE {" AND ".join(where)}
            ORDER BY c.severity, c.opened_at DESC
            LIMIT {int(limit)}
        """)

    def get_case(self, caller: str, case_id: str) -> CaseRow:
        """
        One case, with the narrative from case_notes folded in.

        The split between the two tables is a reporting decision, not something a person
        working the case should have to know about, so the desk shows one thing.

        Args:
            caller: Whose view of the case to return.
            case_id: The case, matched case-insensitively.

        Returns:
            The case, including its description, resolution notes and root cause.

        Raises:
            CaseError: If there is no such case.
        """
        row = self._one(f"""
            SELECT {_CASE_COLUMNS},
                   n.description, n.resolution_notes, n.root_cause
            FROM {self._desk(caller)}
            LEFT JOIN {self.live_notes(caller)} n ON n.case_id = c.case_id
            WHERE upper(c.case_id) = upper({lit(case_id)})
        """)
        if row is None:
            message = f"There is no case {case_id}."
            raise CaseError(message)
        return row

    def search_cases(self, caller: str, query: str, limit: int = 15) -> list[CaseRow]:
        """
        Substring search over the subject, the narrative, the customer and the ids.

        Deliberately not semantic. Finding the case that *resembles* a new problem is
        what the AI Search index over case_notes is for, and duplicating it here would
        give the supervisor two tools that answer the same question differently.

        Customer name and the linked ids are in scope because the first thing anyone
        types is a company name or a run id, and a search that comes back empty for
        "Alpine" reads as broken rather than as precise.

        Args:
            caller: Whose view of the cases to search.
            query: Text to look for.
            limit: Most rows to return.

        Returns:
            The matching cases, newest first.
        """
        like = lit("%" + query + "%")
        return self.run(f"""
            SELECT {_CASE_COLUMNS}
            FROM {self._desk(caller)}
            LEFT JOIN {self.live_notes(caller)} n ON n.case_id = c.case_id
            WHERE lower(c.subject) LIKE lower({like})
               OR lower(coalesce(n.description, '')) LIKE lower({like})
               OR lower(coalesce(cl.short_name, '')) LIKE lower({like})
               OR lower(c.case_id) LIKE lower({like})
               OR lower(coalesce(c.linked_run_id, '')) LIKE lower({like})
               OR lower(coalesce(c.linked_incident_id, '')) LIKE lower({like})
            ORDER BY c.opened_at DESC
            LIMIT {int(limit)}
        """)

    def stats(self, caller: str) -> CaseRow:
        """
        The counters along the top of the desk, as this caller has them.

        Args:
            caller: Whose queue to count.

        Returns:
            Totals for the whole queue; every value arrives as text.
        """
        row = self._one(f"""
            SELECT count(*) AS total,
                   sum(CASE WHEN status <> 'Closed' THEN 1 ELSE 0 END) AS open_cases,
                   sum(CASE WHEN severity IN ('S1','S2') AND status <> 'Closed'
                            THEN 1 ELSE 0 END) AS urgent,
                   round(avg(resolution_days), 1) AS avg_days
            FROM {self.live_cases(caller)}
        """)
        return row or {}

    # -- writes, all of them against case_state and never the seeded tables ---------

    def merge_state(
        self,
        caller: str,
        case_id: str,
        updates: Mapping[str, str],
    ) -> None:
        """
        Record a change against this caller's copy of a case.

        `updates` maps a column to a SQL expression rather than to a value, so a caller
        can append to a column by referring to its current value (`t.notes_appended`)
        rather than reading it back first.

        One MERGE keyed on (demo_user, case_id), because a person may be the first to
        touch a case or the fifth and the two should not be different code paths.

        Args:
            caller: Whose change this is.
            case_id: The case, spelled as the seeded table spells it.
            updates: Column to the SQL expression producing its new value.
        """
        columns = list(updates)
        set_clause = ", ".join(f"{column} = {updates[column]}" for column in columns)

        def for_insert(expression: str) -> str:
            """
            The same expression, for the branch where no row exists yet.

            An expression that reads the current value has nothing to read on insert, so
            those references become NULL. concat_ws then collapses to just the new text,
            which is what appending to nothing should give.
            """
            for column in columns:
                expression = expression.replace(f"t.{column}", "NULL")
            return expression

        insert_columns = ", ".join(["demo_user", "case_id", *columns, "updated_at"])
        insert_values = ", ".join(
            [lit(caller), lit(case_id)]
            + [for_insert(updates[column]) for column in columns]
            + ["current_timestamp()"],
        )

        self.run(f"""
            MERGE INTO {self._settings.state_table} t
            USING (SELECT {lit(caller)} AS demo_user, {lit(case_id)} AS case_id) src
              ON t.demo_user = src.demo_user AND t.case_id = src.case_id
            WHEN MATCHED THEN UPDATE SET {set_clause}, updated_at = current_timestamp()
            WHEN NOT MATCHED THEN INSERT ({insert_columns}) VALUES ({insert_values})
        """)

    def update_case(
        self,
        caller: str,
        case_id: str,
        severity: str | None = None,
        status: str | None = None,
        assigned_to: str | None = None,
    ) -> CaseRow:
        """
        Change a case's severity, status or assignee.

        Args:
            caller: Whose change this is.
            case_id: The case to change.
            severity: New severity, if it changes.
            status: New status, if it changes. Not Closed; close_case does that.
            assigned_to: New assignee, if it changes.

        Returns:
            What changed, in words, and the case as it now stands.

        Raises:
            CaseError: If nothing was passed, a value is not in the vocabulary, or the
                status asked for was Closed.
        """
        case = self.get_case(caller, case_id)
        updates: dict[str, str] = {}
        changed: list[str] = []

        if severity:
            value = _require(severity, SEVERITIES, "severity")
            updates["severity"] = lit(value)
            changed.append(f"severity {case['severity']} -> {value}")
        if status:
            value = _require(status, STATUSES, "status")
            # Closing through this path would leave closed_at empty and resolution_days
            # null, which is what the SLA reporting counts on. close_case exists to do
            # it properly.
            if value == "Closed":
                message = (
                    "Use close_case to close a case - it records when it closed and "
                    "how long it took, which setting the status alone would not."
                )
                raise CaseError(message)
            updates["status"] = lit(value)
            changed.append(f"status {case['status']} -> {value}")
        if assigned_to:
            value = _require(assigned_to, ENGINEERS, "assignee")
            updates["assigned_to"] = lit(value)
            changed.append(f"assignee {case['assigned_to']} -> {value}")

        if not updates:
            message = "Nothing to change. Pass a severity, a status or an assignee."
            raise CaseError(message)

        self.merge_state(caller, case["case_id"], updates)
        logger.info("%s updated %s: %s", caller, case_id, "; ".join(changed))
        return {
            "case_id": case["case_id"],
            "changed": changed,
            "case": self.get_case(caller, case_id),
        }

    def add_note(
        self,
        caller: str,
        case_id: str,
        note: str,
        author: str = AGENT_AUTHOR,
    ) -> CaseRow:
        """
        Append to the narrative on a case.

        The note is appended to this caller's notes_appended, which reads lay after the
        seeded description rather than in place of it, so the story everyone starts from
        survives. The stamp matters: when this text is read back months later, whether a
        human or an agent wrote it is the first thing you want to know.

        Args:
            caller: Whose note this is.
            case_id: The case to write on.
            note: What to record.
            author: Who the note signs itself as.

        Returns:
            The case id and the entry as it was written.

        Raises:
            CaseError: If the case does not exist or the note is empty.
        """
        case = self.get_case(caller, case_id)
        if not note.strip():
            message = "The note is empty."
            raise CaseError(message)

        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        entry = f"[{stamp}] {author}: {note.strip()}"
        self.merge_state(
            caller,
            case["case_id"],
            {
                "notes_appended": (
                    f"concat_ws('\\n\\n', nullif(t.notes_appended, ''), {lit(entry)})"
                ),
            },
        )
        logger.info("note added to %s by %s", case_id, author)
        return {"case_id": case["case_id"], "added": entry}

    def close_case(
        self,
        caller: str,
        case_id: str,
        resolution: str,
        root_cause: str | None = None,
    ) -> CaseRow:
        """
        Close a case, recording when and why.

        resolution_days is computed by the warehouse from the seeded opened_at rather
        than passed in, so it cannot disagree with the timestamps already in the table.

        Args:
            caller: Whose change this is.
            case_id: The case to close.
            resolution: What was actually done about it.
            root_cause: Why it happened, if it is known.

        Returns:
            The case id and the case as it now stands.

        Raises:
            CaseError: If the case is already closed or no resolution was given.
        """
        case = self.get_case(caller, case_id)
        if case["status"] == "Closed":
            message = f"{case['case_id']} is already closed."
            raise CaseError(message)
        if not resolution.strip():
            message = (
                "Closing a case needs a resolution - what was actually done about it."
            )
            raise CaseError(message)

        updates = {
            "status": lit("Closed"),
            "closed_at": "current_timestamp()",
            "resolution_days": (
                f"(SELECT round(datediff(current_timestamp(), opened_at)"
                f" + (hour(current_timestamp()) - hour(opened_at)) / 24.0, 2)"
                f" FROM {self._settings.cases_table}"
                f" WHERE case_id = {lit(case['case_id'])})"
            ),
            "resolution_notes": lit(resolution.strip()),
        }
        if root_cause and root_cause.strip():
            updates["root_cause"] = lit(root_cause.strip())

        self.merge_state(caller, case["case_id"], updates)
        logger.info("%s closed %s", caller, case_id)
        return {"case_id": case["case_id"], "case": self.get_case(caller, case_id)}

    def link_case(
        self,
        caller: str,
        case_id: str,
        incident_id: str | None = None,
        run_id: str | None = None,
    ) -> CaseRow:
        """
        Point a case at the incident or the payroll run it is about.

        Args:
            caller: Whose change this is.
            case_id: The case to link.
            incident_id: Incident the case is about.
            run_id: Payroll run the case is about.

        Returns:
            The case id and the case as it now stands.

        Raises:
            CaseError: If neither an incident nor a run was passed.
        """
        case = self.get_case(caller, case_id)
        updates: dict[str, str] = {}
        if incident_id:
            updates["linked_incident_id"] = lit(incident_id.strip())
        if run_id:
            updates["linked_run_id"] = lit(run_id.strip())
        if not updates:
            message = "Pass an incident_id or a run_id to link."
            raise CaseError(message)

        self.merge_state(caller, case["case_id"], updates)
        return {"case_id": case["case_id"], "case": self.get_case(caller, case_id)}

    def reset(self, caller: str) -> int:
        """
        Put this caller's case desk back to how the workshop starts.

        Only their own rows go. Nothing they did was ever written to the seeded tables,
        so there is nothing to restore and nobody else is affected.

        Args:
            caller: Whose changes to discard.

        Returns:
            How many cases went back to the way they were seeded.
        """
        # Counted before the delete rather than read off the delete: how many cases the
        # person gets back is what the UI reports, and Delta answers a DML statement
        # with a count of touched rows only when it touched any.
        touched = self._one(
            f"SELECT count(*) AS n FROM {self._settings.state_table}"
            f" WHERE demo_user = {lit(caller)}",
        )
        self.run(
            f"DELETE FROM {self._settings.state_table} WHERE demo_user = {lit(caller)}",
        )
        restored = int((touched or {}).get("n") or 0)
        logger.info("reset the case desk for %s (%s restored)", caller, restored)
        return restored
