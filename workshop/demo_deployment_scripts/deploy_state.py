"""Give every person running the workshop their own copy of the case desk.

The problem: two people demoing at once both escalate Alpine's case, and they
overwrite each other. The obvious fix - a copy of the tables per person - means
copying the schema, repointing Genie, and reseeding on every join. Too much
machinery for a workshop.

What is here instead: the seeded tables stay exactly as they are and are never
written to, and one extra table records what each person changed.

    support_cases   the story as everyone finds it       (read only)
    case_state      what you personally did to it        (one row per case you touched)
    *_live          the two joined, filtered to you       (what everything reads)

The views filter on current_user(), so nobody has to pass an identity: Genie runs
its SQL as whoever is asking, which was worth confirming before building on it.
CaseHub cannot use them, because it queries as its own service principal rather
than as the person talking to it, so it applies the same join with an explicit
email. That is the one place the logic is written twice, and live_join() below is
shared between them so it cannot drift.

Resetting is deleting your own rows. Nothing you did was ever in the seeded
table, so there is nothing to put back.

Usage:
    uv run workshop/scripts/deploy_state.py --dry-run
    uv run workshop/scripts/deploy_state.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dbx  # noqa: E402

STATE_TABLE = "case_state"

STATE_COLUMNS = {
    "demo_user": "Who made the change. Everything is filtered on this, and it is what "
                 "keeps two people demoing at once out of each other's way.",
    "case_id": "The case that was changed.",
    "severity": "Severity this person set, or null if they did not touch it.",
    "status": "Status this person set, or null.",
    "assigned_to": "Who they reassigned it to, or null.",
    "closed_at": "When they closed it, or null if they did not.",
    "resolution_days": "How long it had been open when they closed it.",
    "linked_incident_id": "Incident they linked, or null.",
    "linked_run_id": "Payroll run they linked, or null.",
    "notes_appended": "Notes they added, appended to the original narrative rather "
                      "than replacing it.",
    "resolution_notes": "What they recorded as the resolution.",
    "root_cause": "What they recorded as the cause.",
    "updated_at": "When they last changed anything on this case.",
}


def live_join(cfg: dict, who: str) -> tuple[str, str]:
    """The FROM/JOIN clauses that lay one person's changes over the seeded rows.

    `who` is a SQL expression, not a value: the views pass current_user() and
    CaseHub passes a quoted email. Returning the fragment rather than the whole
    statement is what keeps the two callers honest.
    """
    cases = dbx.fq_table(cfg, "support_cases")
    notes = dbx.fq_table(cfg, "case_notes")
    state = f"{cfg['unity_catalog']['catalog']}.{dbx.schema_of(cfg, 'platform')}.{STATE_TABLE}"
    return (
        f"{cases} c LEFT JOIN {state} s ON s.case_id = c.case_id AND s.demo_user = {who}",
        f"{notes} n LEFT JOIN {state} s ON s.case_id = n.case_id AND s.demo_user = {who}",
    )


def cases_select(cfg: dict, who: str) -> str:
    join, _ = live_join(cfg, who)
    return f"""
        SELECT
          c.case_id, c.client_id, c.opened_at, c.category, c.channel, c.subject,
          c.reported_by,
          coalesce(s.severity, c.severity)                     AS severity,
          coalesce(s.status, c.status)                         AS status,
          coalesce(s.assigned_to, c.assigned_to)               AS assigned_to,
          coalesce(s.closed_at, c.closed_at)                   AS closed_at,
          coalesce(s.resolution_days, c.resolution_days)       AS resolution_days,
          coalesce(s.linked_incident_id, c.linked_incident_id) AS linked_incident_id,
          coalesce(s.linked_run_id, c.linked_run_id)           AS linked_run_id
        FROM {join}
    """


def notes_select(cfg: dict, who: str) -> str:
    _, join = live_join(cfg, who)
    return f"""
        SELECT
          n.case_id, n.client_id, n.opened_on, n.category, n.subject,
          coalesce(s.severity, n.severity)                 AS severity,
          -- Notes are appended to the story, not a replacement for it. concat_ws
          -- skips nulls, so an untouched case reads exactly as it was seeded.
          concat_ws('\\n\\n', nullif(n.description, ''),
                    nullif(s.notes_appended, ''))          AS description,
          coalesce(s.resolution_notes, n.resolution_notes) AS resolution_notes,
          coalesce(s.root_cause, n.root_cause)             AS root_cause,
          n.search_text
        FROM {join}
    """


def statements(cfg: dict) -> list[tuple[str, str]]:
    catalog = cfg["unity_catalog"]["catalog"]
    schema = dbx.schema_of(cfg, "platform")
    state = f"{catalog}.{schema}.{STATE_TABLE}"
    cases_view = f"{catalog}.{schema}.support_cases_live"
    notes_view = f"{catalog}.{schema}.case_notes_live"

    out: list[tuple[str, str]] = [(
        f"table {STATE_TABLE}",
        f"""
        CREATE TABLE IF NOT EXISTS {state} (
          demo_user STRING, case_id STRING,
          severity STRING, status STRING, assigned_to STRING,
          closed_at TIMESTAMP, resolution_days DOUBLE,
          linked_incident_id STRING, linked_run_id STRING,
          notes_appended STRING, resolution_notes STRING, root_cause STRING,
          updated_at TIMESTAMP
        )
        COMMENT 'What each person running the workshop changed on a case. The seeded
                 tables are never written to; this is laid over them by the _live views,
                 so two people can work the same case without colliding. Resetting a
                 demo deletes that person rows.'
        """,
    )]
    for column, comment in STATE_COLUMNS.items():
        out.append((f"comment {STATE_TABLE}.{column}",
                    f"ALTER TABLE {state} ALTER COLUMN {column} COMMENT {dbx.sql_string(comment)}"))

    out.append(("view support_cases_live", f"""
        CREATE OR REPLACE VIEW {cases_view}
        COMMENT 'Support cases as the person asking has them: the seeded case plus
                 whatever they changed through CaseHub. Read this rather than
                 support_cases, which is the untouched starting point everyone shares.'
        AS {cases_select(cfg, 'current_user()')}
    """))
    out.append(("view case_notes_live", f"""
        CREATE OR REPLACE VIEW {notes_view}
        COMMENT 'Case narratives with the current person notes appended.'
        AS {notes_select(cfg, 'current_user()')}
    """))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="print the DDL, create nothing")
    ap.add_argument("--profile", help="Databricks CLI profile")
    args = ap.parse_args()

    cfg = dbx.load_config()
    todo = statements(cfg)

    if args.dry_run:
        for label, sql in todo:
            if label.startswith("comment"):
                continue
            print(f"-- {label}\n{sql.strip()}\n")
        print(f"{len(todo)} statements, nothing run (--dry-run)")
        return 0

    w = dbx.workspace(cfg, args.profile)
    for label, sql in todo:
        dbx.sql(w, cfg["warehouse_id"], sql)
        if not label.startswith("comment"):
            print(f"  created {label}")

    schema = f"{cfg['unity_catalog']['catalog']}.{dbx.schema_of(cfg, 'platform')}"
    rows = dbx.sql(w, cfg["warehouse_id"],
                   f"SELECT count(*) FROM {schema}.support_cases_live").result.data_array[0][0]
    users = dbx.sql(w, cfg["warehouse_id"],
                    f"SELECT count(DISTINCT demo_user) FROM {schema}.{STATE_TABLE}"
                    ).result.data_array[0][0]
    print(f"\n  support_cases_live returns {rows} rows for you")
    print(f"  {users} person(s) currently have changes recorded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
