"""Create or update the workshop's Genie Agents.

There are two, not one. Databricks is explicit that an agent should answer
questions for a particular topic and audience rather than range across domains,
and recommends aiming for five or fewer tables; a single agent over all thirteen
was worse on both counts and its instructions had grown long enough to dilute
themselves.

    Saldo payroll operations   what happened to a customer's payroll
    Saldo platform health      was the platform healthy, and what is it costing
                               us in support

The line between them is a real one. The payroll tables are tightly joined to
each other and barely touch availability or deployments, and in a real company
the two sets are owned by different teams. It also means the supervisor has to
route between them, which is the point of the chapter that introduces it.

case_notes is in neither. Finding the case that resembles a new problem is a
question about meaning rather than one SQL can answer, so it is reached through
the search index instead.

Table and column comments are not repeated here. They are written by the table
loader and Genie reads them from Unity Catalog.

Usage:
    uv run workshop/scripts/deploy_genie.py --dry-run
    uv run workshop/scripts/deploy_genie.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dbx  # noqa: E402

PAYROLL_INSTRUCTIONS = """\
You answer questions about the customers of Saldo, a cloud accounting platform used by companies
in the Czech Republic and Slovakia, and about the payroll Saldo runs for them.

- A payroll run pays one month for one customer, and the period being paid is the month BEFORE
  the run was submitted. A run submitted in August is normally July's payroll. When somebody asks
  about "this month's payroll", check whether they mean the period or the submission.
- A run with status PARTIALLY_COMPLETED is not a system failure. It means some rows were rejected
  and the rest were paid normally.
- Rejected rows carry a reason_code. Look it up in reason_codes to see whose problem it is. Codes
  in the 'employee_record' category mean the submitted file was fine and the employee's stored
  record could not be paid. Codes in the 'row' category mean the file itself was wrong.
- employees.bank_account_format is either IBAN or legacy_domestic. Anything that is not IBAN
  cannot be paid.
- Cost centre codes like STORE-BRNO-01 mean nothing on their own. Join cost_centres to get the
  name, the city, and whether it is a shop, a plant or a head office.
- Money is in CZK. clients.monthly_fee is what a customer is billed per month.
- Customers are named two ways. clients.legal_name is the registered name and ends in the legal
  form, like 'Alpine Retail a.s.'; clients.short_name is what people say, like 'Alpine Retail'.
  Match a customer named in a question against short_name. Never test legal_name for equality -
  it will find nothing.

You cannot see whether Saldo itself was up or down, or what was deployed and when. If asked, say
that platform health is a separate subject and answer only the part you can.

Refer to customers by short_name rather than client_id, and use legal_name only when
the question is about the contract or the invoice.
"""

PLATFORM_INSTRUCTIONS = """\
You answer questions about whether Saldo's own platform is healthy: what has been deployed, what
has broken, and what support load that has produced.

- Availability is measured per service per day. Whether Saldo was down is a completely different
  question from whether a customer's payroll worked, so answer it from
  service_availability_daily and not by inference from anything else.
- The service level target is monthly, so compare a monthly average rather than a single day.
  Scheduled maintenance is excluded from the measurement and appears in its own column.
- When somebody asks why something started failing on a particular day, look at what was deployed
  just before it. changes.customer_action_required marks the changes that break customers who did
  not act on them.
- incidents.linked_change_id says which deployment caused an incident, where one did.
- support_cases records only which customer raised a case, as a client_id. Join clients to say
  who that is, and call them by clients.short_name. If a question names a customer, match it
  against short_name rather than legal_name, which ends in a legal form like 'a.s.'.
- support_cases_live holds the case record only: who raised what, when, how urgent, how long it took.
  What was actually written on a case is not here. If somebody asks what happened on a case, what
  was done about it, or whether we have seen a problem like this before, say the case notes are
  searched separately and answer only the part you can count.
"""

AGENTS = {
    "payroll": {
        "title": "Saldo payroll operations",
        "description": "Saldo's customers, the employees they pay, and how their payroll runs went.",
        "instructions": PAYROLL_INSTRUCTIONS,
        "tables": ["clients", "contacts", "cost_centres", "employees",
                   "payroll_runs", "payroll_run_items", "reason_codes"],
        "examples": [
            ("How did Alpine Retail's most recent payroll run go?", """
                SELECT r.run_id, r.period, r.submitted_at, r.employee_count,
                       r.accepted_count, r.rejected_count, r.status
                FROM {payroll_runs} r JOIN {clients} cl USING (client_id)
                WHERE cl.short_name = 'Alpine Retail'
                ORDER BY r.period DESC LIMIT 1"""),
            ("Why were employees rejected on run PR-202607-0008, and whose fault is it?", """
                SELECT i.reason_code, rc.message, rc.category, rc.resolution,
                       count(*) AS rows_rejected
                FROM {payroll_run_items} i JOIN {reason_codes} rc USING (reason_code)
                WHERE i.run_id = 'PR-202607-0008' AND i.status = 'REJECTED'
                GROUP BY ALL"""),
            ("Which employees were not paid, and which sites are they at?", """
                SELECT e.employee_id, e.first_name, e.last_name, cc.name AS site,
                       cc.kind, cc.city, e.bank_account, e.record_updated_on
                FROM {payroll_run_items} i JOIN {employees} e USING (employee_id)
                JOIN {cost_centres} cc
                  ON cc.client_id = e.client_id AND cc.cost_centre = e.cost_centre
                WHERE i.run_id = 'PR-202607-0008' AND i.status = 'REJECTED'
                ORDER BY cc.name"""),
            ("Is this affecting other customers as well?", """
                SELECT cl.short_name, r.period, r.rejected_count,
                       date(r.submitted_at) AS submitted
                FROM {payroll_runs} r JOIN {clients} cl USING (client_id)
                WHERE r.rejected_count > 0
                ORDER BY r.rejected_count DESC"""),
            ("Has Alpine Retail ever had a payroll rejection before?", """
                SELECT r.period, r.employee_count, r.accepted_count,
                       r.rejected_count, r.status
                FROM {payroll_runs} r JOIN {clients} cl USING (client_id)
                WHERE cl.short_name = 'Alpine Retail'
                ORDER BY r.period"""),
            ("How many employees at each customer have a bank account that cannot be paid?", """
                SELECT cl.short_name, count(*) AS employees_affected,
                       count(DISTINCT e.cost_centre) AS sites
                FROM {employees} e JOIN {clients} cl USING (client_id)
                WHERE e.bank_account_format <> 'IBAN'
                GROUP BY cl.short_name ORDER BY employees_affected DESC"""),
            ("What does Alpine Retail pay us per month, and who do we talk to there?", """
                SELECT cl.short_name, cl.plan, cl.employees, cl.rate_per_employee,
                       cl.monthly_fee, ct.name, ct.role, ct.email
                FROM {clients} cl JOIN {contacts} ct USING (client_id)
                WHERE cl.short_name = 'Alpine Retail' AND ct.is_primary"""),
        ],
    },
    "platform": {
        "title": "Saldo platform health",
        "description": "Saldo's own availability, incidents, deployments and support case load.",
        "instructions": PLATFORM_INSTRUCTIONS,
        # support_cases_live rather than support_cases: each person sees the case as
        # they have left it, which is what makes a shared workshop workable.
        "tables": ["service_availability_daily", "incidents", "changes",
                   "support_cases_live", "clients"],
        "examples": [
            ("Were any Saldo services unavailable in July 2026?", """
                SELECT service, round(avg(uptime_pct), 4) AS monthly_uptime_pct,
                       sum(unavailable_minutes) AS minutes_lost
                FROM {service_availability_daily}
                WHERE day BETWEEN '2026-07-01' AND '2026-07-31'
                GROUP BY service ORDER BY monthly_uptime_pct"""),
            ("What did we deploy in the week before 4 August 2026?", """
                SELECT change_id, date(deployed_at) AS deployed, release, component,
                       customer_action_required, title
                FROM {changes}
                WHERE deployed_at BETWEEN '2026-07-28' AND '2026-08-04'
                ORDER BY deployed_at"""),
            ("Which changes forced customers to do something themselves?", """
                SELECT change_id, date(deployed_at) AS deployed, release, title, description
                FROM {changes} WHERE customer_action_required
                ORDER BY deployed_at DESC"""),
            ("Which incidents were caused by something we deployed?", """
                SELECT i.incident_id, date(i.opened_at) AS opened, i.severity, i.component,
                       i.summary, i.unavailable_minutes, c.change_id, c.title AS change_title
                FROM {incidents} i LEFT JOIN {changes} c ON c.change_id = i.linked_change_id
                ORDER BY i.opened_at DESC"""),
            ("How long do we take to close cases, by severity?", """
                SELECT severity, count(*) AS cases,
                       round(avg(resolution_days), 1) AS avg_days_to_close
                FROM {support_cases_live} WHERE closed_at IS NOT NULL
                GROUP BY severity ORDER BY severity"""),
            ("Show me open support cases, most urgent first", """
                SELECT c.case_id, cl.short_name AS customer, c.severity,
                       date(c.opened_at) AS opened, c.assigned_to, c.subject
                FROM {support_cases_live} c JOIN {clients} cl USING (client_id)
                WHERE c.closed_at IS NULL
                ORDER BY c.severity, c.opened_at"""),
            ("Which customers have raised the most cases this year?", """
                SELECT cl.short_name AS customer, cl.plan, count(*) AS cases,
                       sum(CASE WHEN c.severity = 'S1' THEN 1 ELSE 0 END) AS s1_cases
                FROM {support_cases_live} c JOIN {clients} cl USING (client_id)
                GROUP BY cl.short_name, cl.plan
                ORDER BY cases DESC"""),
        ],
    },
}


def stable_id(text: str) -> str:
    """A 32-hex lowercase id, as the API requires, derived from the content, so
    redeploying updates entries in place rather than churning them."""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def tidy(sql: str, cfg: dict) -> str:
    names = {t: dbx.fq_table(cfg, t) for t in dbx.all_tables(cfg)}
    names.update({v: dbx.fq_view(cfg, v) for v in dbx.all_views(cfg)})
    body = sql.format(**names).strip("\n")
    lines = [ln.strip() for ln in body.splitlines()]
    return "\n".join(lines).strip()


def serialized_space(cfg: dict, spec: dict) -> dict:
    return {
        "version": 2,
        # The API rejects an unsorted table list.
        "data_sources": {
            "tables": sorted(
                ({"identifier": (dbx.fq_view(cfg, t) if t in dbx.all_views(cfg)
                                 else dbx.fq_table(cfg, t))} for t in spec["tables"]),
                key=lambda x: x["identifier"],
            )
        },
        "instructions": {
            "text_instructions": [
                {"id": stable_id(spec["title"]), "content": [spec["instructions"].strip()]}
            ],
            # question and sql are arrays, every entry needs a 32-hex id, and the
            # list must be sorted by that id. None of that is in the reference.
            "example_question_sqls": sorted(
                ({"id": stable_id(q), "question": [q], "sql": [tidy(s, cfg)]}
                 for q, s in spec["examples"]),
                key=lambda e: e["id"],
            ),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="print the definitions, create nothing")
    ap.add_argument("--profile", help="Databricks CLI profile")
    args = ap.parse_args()

    cfg = dbx.load_config()
    built = {k: serialized_space(cfg, spec) for k, spec in AGENTS.items()}

    for key, spec in AGENTS.items():
        s = built[key]
        print(f"{spec['title']:<28} {len(s['data_sources']['tables'])} tables, "
              f"{len(s['instructions']['example_question_sqls'])} examples")

    if args.dry_run:
        print()
        print(json.dumps(built["payroll"], indent=1)[:900])
        print("\nnothing created (--dry-run)")
        return 0

    w = dbx.workspace(cfg, args.profile)
    existing = {s.title: s.space_id for s in (w.genie.list_spaces().spaces or []) if s.title}

    print()
    for key, spec in AGENTS.items():
        payload = json.dumps(built[key])
        title = spec["title"]
        if title in existing:
            w.genie.update_space(
                space_id=existing[title], title=title, description=spec["description"],
                warehouse_id=cfg["warehouse_id"], serialized_space=payload)
            space_id = existing[title]
            print(f"updated {title}")
        else:
            created = w.genie.create_space(
                warehouse_id=cfg["warehouse_id"], serialized_space=payload,
                title=title, description=spec["description"])
            space_id = created.space_id
            print(f"created {title}")
        print(f"  {w.config.host.rstrip('/')}/genie/rooms/{space_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
