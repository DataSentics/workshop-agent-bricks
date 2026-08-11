"""Load the Saldo operational tables into Unity Catalog.

Everything is read from committed files under workshop/data. Nothing is invented
at load time, so seeding the same commit twice gives the same rows.

    clients, contacts, client_modules   from clients.json
    reason_codes                        parsed from the error reference document
    employees                           from employees.csv
    payroll_runs, payroll_run_items     from the payroll generator
    service_availability_daily          from the payroll generator
    support_cases, incidents, changes   from the support generator

Two things are worth knowing. The client roster is hand-authored: prose was
written company by company, but the numeric and categorical fields were assigned
deliberately, because distributions chosen by a model are not convincing - an
early draft gave eight of eleven customers the same tenure and identical modules.

And reason_codes is parsed out of the published error reference rather than
restated here, so the table cannot drift from what the documentation says.

Usage:
    uv run workshop/scripts/seed_tables.py --dry-run
    uv run workshop/scripts/seed_tables.py
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dbx  # noqa: E402
import generate_support  # noqa: E402
from seed_docs import build_timeline  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]

ERROR_SECTIONS = {
    "File-level errors": "file",
    "Row errors — a problem in the submitted file": "row",
    "Employee record errors — a problem in the employee master": "employee_record",
    "Downstream errors": "downstream",
}


def months_before(d: date, months: int) -> date:
    total = d.year * 12 + (d.month - 1) - months
    return date(total // 12, total % 12 + 1, min(d.day, 28))


def parse_reason_codes(cfg: dict) -> list[dict]:
    """Read the validation codes out of the published error reference."""
    doc = dbx.data_dir(cfg) / cfg["data"]["derived_from_docs"]["reason_codes"]
    section = None
    rows: list[dict] = []
    for line in doc.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
        m = re.match(r"^\|\s*`([A-Z]{3}-\d{3})`\s*\|(.+)$", line)
        if m and section in ERROR_SECTIONS:
            cells = [c.strip() for c in m.group(2).split("|")]
            rows.append({
                "reason_code": m.group(1),
                "category": ERROR_SECTIONS[section],
                "message": cells[0],
                "cause": cells[1],
                "resolution": cells[2],
                "rejects_whole_file": ERROR_SECTIONS[section] == "file",
            })
    if len(rows) < 15:
        raise SystemExit(
            f"only parsed {len(rows)} reason codes from {doc.name}; "
            "the document format probably changed"
        )
    return rows


def build_rows(cfg: dict, workshop_day: date) -> dict[str, list[dict]]:
    roster = json.loads(dbx.data_file(cfg, "clients").read_text(encoding="utf-8"))
    support = generate_support.build(cfg, workshop_day)

    clients: list[dict] = []
    contacts: list[dict] = []
    modules: list[dict] = []
    centres: list[dict] = []

    cc_src = json.loads(dbx.data_file(cfg, "cost_centres").read_text(encoding="utf-8"))
    headcount = collections.Counter()
    with dbx.data_file(cfg, "employees").open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            headcount[(r["client_id"], r["cost_centre"])] += 1
    for entry in cc_src:
        for cc in entry["cost_centres"]:
            centres.append({
                "client_id": entry["client_id"],
                "cost_centre": cc["code"],
                "name": cc["name"],
                "kind": cc["kind"],
                "city": cc["city"],
                "employees": headcount.get((entry["client_id"], cc["code"]), 0),
            })

    for c in roster:
        since = months_before(workshop_day, c["months_as_customer"])
        clients.append({
            "client_id": c["client_id"],
            "legal_name": c["legal_name"],
            # What everyone actually calls them. The legal name carries the legal
            # form ("Alpine Retail a.s.") and nobody says that out loud, so a
            # question about "Alpine Retail" has nothing to match on without this.
            "short_name": c["legal_name"].removesuffix(" " + c["legal_form"]).strip(),
            "legal_form": c["legal_form"],
            "industry": c["industry"],
            "description": c["description"],
            "hq_city": c["hq_city"],
            "country": c["country"],
            "employees": c["employees"],
            "plan": c["plan"],
            "customer_since": since,
            "months_as_customer": c["months_as_customer"],
            "account_manager": c["account_manager"],
            "health_note": c.get("health_note"),
            "rate_per_employee": c["rate_per_employee"],
            "minimum_monthly_charge": c["minimum_monthly_charge"],
            # What they actually pay this month. Derived the same way the invoice
            # is: per active employee, floored at the plan minimum.
            "monthly_fee": max((c["rate_per_employee"] or 0) * c["employees"],
                               c["minimum_monthly_charge"]),
            "term_months": c["term_months"],
            "discount_pct": c["discount_pct"],
        })
        for module in c["modules"]:
            modules.append({
                "client_id": c["client_id"],
                "module": module,
                "active_since": since,
            })
        for i, p in enumerate(c["contacts"], start=1):
            contacts.append({
                "contact_id": f"{c['client_id']}-C{i:02d}",
                "client_id": c["client_id"],
                "name": p["name"],
                "role": p["role"],
                "email": p["email"],
                "is_primary": p["is_primary"],
            })

    return {
        "clients": clients,
        "contacts": contacts,
        "client_modules": modules,
        "cost_centres": centres,
        "reason_codes": parse_reason_codes(cfg),
        "employees": read_employees(cfg),
        "payroll_runs": read_csv(cfg, "payroll_runs", TYPES["payroll_runs"]),
        "payroll_run_items": read_csv(cfg, "payroll_run_items", TYPES["payroll_run_items"]),
        "service_availability_daily": read_csv(
            cfg, "service_availability_daily", TYPES["service_availability_daily"]),
        # Derived here rather than read from a committed CSV. cases.json,
        # incidents.json and changes.json are the written source; a CSV beside
        # them would be the same rows a second time, differing only in whether
        # the date is an anchor or a resolved timestamp - and the two would
        # disagree the moment somebody edited one and forgot to regenerate.
        **split_cases(support["support_cases"]),
        "incidents": support["incidents"],
        "changes": support["changes"],
    }


def split_cases(rows: list[dict]) -> dict[str, list[dict]]:
    """Separate the case record from the case notes.

    The record is what you aggregate: who, when, how urgent, how long it took.
    The notes are what you read: the customer's report and the engineer's account
    of what turned out to be true. Free text of that length has no place in a
    semantic layer, and searching it needs embeddings rather than SQL, so the two
    live apart. Only the notes feed the AI Search index.
    """
    record, notes = [], []
    for r in rows:
        resolution_days = None
        if r["closed_at"] and r["opened_at"]:
            resolution_days = round((r["closed_at"] - r["opened_at"]).total_seconds() / 86400, 1)
        record.append({
            "case_id": r["case_id"], "client_id": r["client_id"],
            "opened_at": r["opened_at"], "closed_at": r["closed_at"],
            "resolution_days": resolution_days,
            "status": r["status"], "severity": r["severity"], "category": r["category"],
            "channel": r["channel"], "subject": r["subject"],
            "reported_by": r["reported_by"], "assigned_to": r["assigned_to"],
            "linked_incident_id": r["linked_incident_id"], "linked_run_id": r["linked_run_id"],
        })
        parts = [r["subject"]]
        if r["description"]:
            parts.append(f"Customer reported: {r['description']}")
        if r["resolution_notes"]:
            parts.append(f"What we found and did: {r['resolution_notes']}")
        if r["root_cause"]:
            parts.append(f"Root cause: {r['root_cause']}")
        notes.append({
            "case_id": r["case_id"], "client_id": r["client_id"],
            # A date rather than a timestamp: AI Search indexes cannot carry
            # timestamp_ntz columns, and the day is all a search result needs.
            "opened_on": r["opened_at"].date(), "category": r["category"],
            "severity": r["severity"],
            "subject": r["subject"], "description": r["description"],
            "resolution_notes": r["resolution_notes"], "root_cause": r["root_cause"],
            "search_text": "\n\n".join(parts),
        })
    return {"support_cases": record, "case_notes": notes}


def _d(v):    return date.fromisoformat(v) if v else None
def _ts(v):   return datetime.fromisoformat(v) if v else None
def _i(v):    return int(v) if v not in ("", None) else None
def _f(v):    return float(v) if v not in ("", None) else None
def _b(v):    return v == "True"
def _s(v):    return v if v != "" else None

TYPES = {
    "payroll_runs": {
        "run_id": _s, "client_id": _s, "period": _s, "channel": _s,
        "is_correction_run": _b, "submitted_at": _ts, "validated_at": _ts,
        "approved_at": _ts, "value_date": _d, "employee_count": _i,
        "accepted_count": _i, "rejected_count": _i, "total_gross": _f,
        "total_net": _f, "status": _s,
    },
    "payroll_run_items": {
        "run_id": _s, "client_id": _s, "employee_id": _s, "cost_centre": _s,
        "hours_worked": _f, "gross_amount": _f, "net_amount": _f,
        "status": _s, "reason_code": _s,
    },
    "support_cases": {
        "case_id": _s, "client_id": _s, "opened_at": _ts, "closed_at": _ts, "status": _s,
        "severity": _s, "category": _s, "channel": _s, "subject": _s, "description": _s,
        "resolution_notes": _s, "root_cause": _s, "reported_by": _s, "assigned_to": _s,
        "linked_incident_id": _s, "linked_run_id": _s,
    },
    "incidents": {
        "incident_id": _s, "component": _s, "severity": _s, "opened_at": _ts,
        "resolved_at": _ts, "unavailable_minutes": _i, "summary": _s, "detail": _s,
        "root_cause": _s, "linked_change_id": _s, "customers_affected": _s,
    },
    "changes": {
        "change_id": _s, "release": _s, "component": _s, "deployed_at": _ts, "title": _s,
        "description": _s, "risk": _s, "customer_action_required": _b, "backed_out": _b,
        "deployed_by": _s,
    },
    "service_availability_daily": {
        "day": _d, "service": _s, "uptime_pct": _f, "unavailable_minutes": _i,
        "planned_maintenance_minutes": _i, "avg_latency_ms": _i, "error_rate_pct": _f,
    },
}


def read_csv(cfg: dict, key: str, types: dict) -> list[dict]:
    """Load a committed CSV, applying the column types the table needs."""
    path = dbx.data_file(cfg, key)
    if not path.exists():
        raise SystemExit(
            f"{path.name} is missing. Run: uv run workshop/scripts/generate_payroll.py"
        )
    with path.open(encoding="utf-8", newline="") as fh:
        return [{c: fn(r[c]) for c, fn in types.items()} for r in csv.DictReader(fh)]


def read_employees(cfg: dict) -> list[dict]:
    """The employee master is generated separately and committed; see
    generate_employees.py. Loading only ever reads it."""
    path = dbx.data_file(cfg, "employees")
    if not path.exists():
        raise SystemExit(
            f"{path.name} is missing. Run: uv run workshop/scripts/generate_employees.py"
        )
    rows = []
    with path.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            rows.append({
                "employee_id": r["employee_id"],
                "client_id": r["client_id"],
                "first_name": r["first_name"],
                "last_name": r["last_name"],
                "personal_number": r["personal_number"],
                "bank_account": r["bank_account"],
                "bank_account_format": r["bank_account_format"],
                "cost_centre": r["cost_centre"],
                "contract_type": r["contract_type"],
                "pay_basis": r["pay_basis"],
                "monthly_salary": int(r["monthly_salary"]) if r["monthly_salary"] else None,
                "hourly_rate": int(r["hourly_rate"]) if r["hourly_rate"] else None,
                "started_on": date.fromisoformat(r["started_on"]),
                "ended_on": date.fromisoformat(r["ended_on"]) if r["ended_on"] else None,
                "is_active": r["is_active"] == "True",
                "record_updated_on": date.fromisoformat(r["record_updated_on"]),
            })
    return rows


SPEC = {
    "support_cases": {
        "columns": ["case_id","client_id","opened_at","closed_at","resolution_days","status",
                    "severity","category","channel","subject","reported_by","assigned_to",
                    "linked_incident_id","linked_run_id"],
        "comment": "The support case record: who raised what, when, how urgent it was and how long "
                   "it took. Use this to count and compare cases. The narrative - what the customer "
                   "said and what the engineer found - is not here; it is in case_notes, which is "
                   "searched rather than queried.",
        "column_comments": {
            "case_id": "Case reference, e.g. CAS-40318.",
            "client_id": "The customer who raised it. Joins to clients.client_id.",
            "opened_at": "When the case was raised.",
            "closed_at": "When it was closed. Null while still open.",
            "resolution_days": "Days from opening to closing. Null while still open.",
            "status": "Open, In progress, Waiting for customer or Closed.",
            "severity": "S1 critical, S2 high, S3 medium, S4 low. Set by Saldo on the facts, not by "
                        "the customer's plan. A payroll run with rejected rows is normally S3.",
            "category": "Payroll, Invoicing, Banking, Bookkeeping, Data import, Reporting, Access "
                        "or Billing.",
            "channel": "How it arrived: email, phone or in-product.",
            "subject": "One-line summary of the case.",
            "reported_by": "Email address of the person who raised it. Joins to contacts.email.",
            "assigned_to": "The Saldo support engineer handling it.",
            "linked_incident_id": "Set when the case turned out to be caused by a platform incident. "
                                  "Null when the cause was at the customer's end, which is most of "
                                  "the time.",
            "linked_run_id": "The payroll run the case concerns, when there is one.",
        },
    },
    "case_notes": {
        "columns": ["case_id","client_id","opened_on","category","severity","subject",
                    "description","resolution_notes","root_cause","search_text"],
        "comment": "What was actually written on each support case. description is the customer's "
                   "report in their own words, often wrong about the cause; resolution_notes is the "
                   "engineer's account of what turned out to be true and what was done about it. "
                   "This table is the source for the case search index and is not meant to be "
                   "queried with SQL - finding the case that resembles a new problem needs meaning, "
                   "not keywords.",
        "column_comments": {
            "case_id": "Case reference. Joins to support_cases.case_id.",
            "client_id": "The customer who raised it.",
            "opened_on": "The day the case was raised.",
            "category": "What area the case was about.",
            "severity": "How urgent it was judged to be.",
            "subject": "One-line summary.",
            "description": "The customer's report, in their terms.",
            "resolution_notes": "What the engineer found and did. Null while the case is open.",
            "root_cause": "Short statement of the actual cause, once known.",
            "search_text": "Subject, customer report, resolution and root cause in one field. This is "
                           "the column the search index embeds, because a case is only useful as "
                           "precedent when the problem and its fix are read together.",
        },
    },
    "incidents": {
        "columns": ["incident_id","component","severity","opened_at","resolved_at",
                    "unavailable_minutes","summary","detail","root_cause","linked_change_id",
                    "customers_affected"],
        "comment": "Saldo's own incidents: things that went wrong on the platform, as opposed to "
                   "problems in a customer's data. If a customer's problem is not linked to one of "
                   "these, it was not caused by Saldo being broken.",
        "column_comments": {
            "incident_id": "Incident reference, e.g. INC-2041.",
            "component": "web, sftp, api, payroll_engine or banking.",
            "severity": "S1 to S4.",
            "opened_at": "When the incident started.",
            "resolved_at": "When service was restored.",
            "unavailable_minutes": "Minutes of genuine unavailability. Zero for degradations that "
                                   "did not take the service down.",
            "summary": "One-line description.",
            "detail": "What happened and what was done about it.",
            "root_cause": "The underlying cause.",
            "linked_change_id": "The change that caused it, where there was one. Joins to "
                                "changes.change_id.",
            "customers_affected": "Who was affected: all, a channel, or a subset.",
        },
    },
    "changes": {
        "columns": ["change_id","release","component","deployed_at","title","description","risk",
                    "customer_action_required","backed_out","deployed_by"],
        "comment": "Everything Saldo deployed, with dates. When a customer says something started "
                   "failing on a particular day, this is the table that says what changed just "
                   "before it. Releases go out in the Saturday maintenance window.",
        "column_comments": {
            "change_id": "Change reference, e.g. CHG-0488.",
            "release": "Release it belongs to, e.g. 2026.8, or 'infra' / 'hotfix'.",
            "component": "Which part of the platform it touched.",
            "deployed_at": "When it went live. Compare against when a customer's problem started.",
            "title": "One-line description.",
            "description": "What changed and why.",
            "risk": "low, medium or high, as assessed before deployment.",
            "customer_action_required": "True when customers have to do something themselves, such "
                                        "as changing data or an integration. These are the changes "
                                        "that break customers who did not act.",
            "backed_out": "True if the change was rolled back.",
            "deployed_by": "The team that deployed it.",
        },
    },
    "payroll_runs": {
        "columns": ["run_id","client_id","period","channel","is_correction_run","submitted_at",
                    "validated_at","approved_at","value_date","employee_count","accepted_count",
                    "rejected_count","total_gross","total_net","status"],
        "comment": "One row per payroll run. A run is one batch of employee payments for one pay "
                   "period at one customer. Note that a period is paid during the FOLLOWING month, "
                   "so a run submitted in August is normally July's payroll. Use this table to ask "
                   "whether a customer's payroll worked, when they submitted it, and how many "
                   "people were actually paid.",
        "column_comments": {
            "run_id": "Run identifier, e.g. PR-202607-0008.",
            "client_id": "The customer whose payroll this is. Joins to clients.client_id.",
            "period": "The month being paid, as YYYY-MM. Earlier than the submission month.",
            "channel": "How the file arrived: web application, sftp or api. Standard-plan customers "
                       "only have the web application.",
            "is_correction_run": "True if this run re-pays only employees who were rejected in an "
                                 "earlier run for the same period. Correction runs are never charged.",
            "submitted_at": "When the customer uploaded the file. This decides which validation "
                            "rules applied, so it matters when behaviour changed in a release.",
            "validated_at": "When validation finished.",
            "approved_at": "When an authorised user at the customer released the run for payment.",
            "value_date": "The date the money reaches employees.",
            "employee_count": "How many employees were in the submission.",
            "accepted_count": "How many were paid.",
            "rejected_count": "How many were not paid. Greater than zero means some employees got "
                              "no salary from this run.",
            "total_gross": "Total gross pay across accepted rows, in local currency.",
            "total_net": "Total net pay actually transferred, after statutory deductions.",
            "status": "COMPLETED when everyone was paid, PARTIALLY_COMPLETED when some rows were "
                      "rejected. PARTIALLY_COMPLETED is a normal outcome, not a system fault.",
        },
    },
    "payroll_run_items": {
        "columns": ["run_id","client_id","employee_id","cost_centre","hours_worked",
                    "gross_amount","net_amount","status","reason_code"],
        "comment": "One row per employee per payroll run: what they were owed and whether they were "
                   "actually paid. This is where to look to find exactly which people did not get "
                   "their salary, and why.",
        "column_comments": {
            "run_id": "Joins to payroll_runs.run_id.",
            "client_id": "The customer. Denormalised from the run so this table can be filtered directly.",
            "employee_id": "Joins to employees.employee_id.",
            "cost_centre": "The site, store or team the employee is allocated to.",
            "hours_worked": "Hours submitted for hourly employees. Null for salaried employees.",
            "gross_amount": "Gross pay for this employee for this period, including any bonus.",
            "net_amount": "Net pay actually transferred. Null when the row was rejected and nobody was paid.",
            "status": "PAID or REJECTED.",
            "reason_code": "Why the row was rejected. Joins to reason_codes.reason_code. Null when paid.",
        },
    },
    "service_availability_daily": {
        "columns": ["day","service","uptime_pct","unavailable_minutes",
                    "planned_maintenance_minutes","avg_latency_ms","error_rate_pct"],
        "comment": "Daily availability of each Saldo service, as measured for service level "
                   "reporting. Use this to establish whether Saldo was actually down on a given "
                   "day, which is a different question from whether a customer's payroll worked. "
                   "Scheduled maintenance is excluded from the measurement, as the SLA requires.",
        "column_comments": {
            "day": "The calendar day measured.",
            "service": "web, sftp, api or payroll_engine.",
            "uptime_pct": "Percentage of measurable minutes the service was available that day. "
                          "Monthly averages are what the SLA target of 99.9% applies to.",
            "unavailable_minutes": "Minutes the service was genuinely unavailable. Zero on a normal day.",
            "planned_maintenance_minutes": "Announced maintenance, excluded from the availability "
                                           "calculation under the SLA.",
            "avg_latency_ms": "Average response time that day.",
            "error_rate_pct": "Percentage of requests returning an error.",
        },
    },
    "employees": {
        "columns": ["employee_id","client_id","first_name","last_name","personal_number",
                    "bank_account","bank_account_format","cost_centre","contract_type",
                    "pay_basis","monthly_salary","hourly_rate","started_on","ended_on",
                    "is_active","record_updated_on"],
        "comment": "The employee master: every person Saldo's customers pay. Payroll files are "
                   "validated against this table - the file supplies hours and bonuses, this "
                   "supplies who the person is and where the money goes. A payroll row is "
                   "rejected when the employee's record here cannot be paid, even if the "
                   "submitted file was perfectly correct.",
        "column_comments": {
            "employee_id": "Identifier used by the customer in their payroll submissions.",
            "client_id": "The customer that employs this person. Joins to clients.client_id.",
            "first_name": "Given name.",
            "last_name": "Surname.",
            "personal_number": "Czech or Slovak national identifier, format NNNNNN/NNNN.",
            "bank_account": "Where this employee's salary is paid. Must be a valid IBAN. Records "
                            "still holding the pre-IBAN Czech domestic format (prefix-number/bank) "
                            "are rejected with VAL-014 from release 2026.8 onward.",
            "bank_account_format": "Either 'IBAN' or 'legacy_domestic'. Anything not IBAN cannot be paid.",
            "cost_centre": "Which site, store or team the employee is allocated to for payroll reporting.",
            "contract_type": "HPP (standard employment), HPP part-time, DPC or DPP (Czech and Slovak "
                             "short-form agreements used for seasonal and casual work).",
            "pay_basis": "'hourly' or 'monthly'. Decides whether the payroll file must supply hours "
                         "or a gross amount for this person.",
            "monthly_salary": "Gross monthly salary in local currency, for salaried employees. Null if hourly.",
            "hourly_rate": "Gross hourly rate in local currency, for hourly employees. Null if salaried.",
            "started_on": "First day of employment.",
            "ended_on": "Last day of employment. Null while still employed.",
            "is_active": "True while the employee is currently employed.",
            "record_updated_on": "When this employee's record was last changed. Records migrated in "
                                 "bulk at onboarding and never edited since all share the migration date.",
        },
    },
    "cost_centres": {
        "columns": ["client_id","cost_centre","name","kind","city","employees"],
        "comment": "The sites, teams and departments customers allocate their employees to. Use this "
                   "to turn a cost centre code into somewhere a person would recognise, and to tell "
                   "a shop or plant apart from a head office. Payroll reporting is broken down by "
                   "these.",
        "column_comments": {
            "client_id": "Joins to clients.client_id.",
            "cost_centre": "The code as it appears on employee records and payroll runs. "
                           "Joins to employees.cost_centre and payroll_run_items.cost_centre.",
            "name": "What people at the customer call this place or team, in Czech or Slovak.",
            "kind": "store, production, warehouse, depot, clinic, office, field or delivery. Use this "
                    "to separate customer-facing sites from head office and support functions.",
            "city": "Where it is.",
            "employees": "How many people are currently allocated here.",
        },
    },
    "clients": {
        "columns": ["client_id","legal_name","short_name","legal_form","industry","description","hq_city",
                    "country","employees","plan","customer_since","months_as_customer",
                    "account_manager","health_note","rate_per_employee","minimum_monthly_charge",
                    "monthly_fee","term_months","discount_pct"],
        "comment": "Saldo's customers. One row per company that subscribes to Saldo. "
                   "The spine of the dataset - every other table joins back to client_id.",
        "column_comments": {
            "client_id": "Unique customer identifier, e.g. CL-001.",
            "legal_name": "Registered company name including its legal form, as it appears on the "
                          "contract and the invoice.",
            "short_name": "What the customer is called in conversation, without the legal form - "
                          "'Alpine Retail' rather than 'Alpine Retail a.s.'. Match customer names "
                          "against this column, not legal_name.",
            "legal_form": "Czech or Slovak legal form: s.r.o. (limited company) or a.s. (joint stock).",
            "industry": "What sector the customer operates in.",
            "description": "One or two sentences describing what the company actually does.",
            "hq_city": "City of the customer's head office.",
            "country": "CZ (Czech Republic) or SK (Slovakia). Saldo operates only in these two.",
            "employees": "Current headcount at the customer. Drives what they pay for the Payroll module.",
            "plan": "Subscription plan: Standard, Professional or Enterprise. Determines availability "
                    "target, support hours and which channels are available. Not strictly tied to size - "
                    "some large customers stay on a cheaper plan.",
            "customer_since": "Date the customer started using Saldo.",
            "months_as_customer": "Whole months between customer_since and today.",
            "account_manager": "The Saldo employee who owns the commercial relationship.",
            "health_note": "Free-text observation a support engineer recorded about this account. "
                           "Null for most customers - only written when there is something worth knowing.",
            "rate_per_employee": "Contracted price per active employee per month, in local currency. "
                                 "Below list price where the customer negotiated a discount. Null for "
                                 "customers without the Payroll module.",
            "minimum_monthly_charge": "Floor on the monthly charge, set by the plan.",
            "monthly_fee": "What this customer is billed per month: employees times the rate, floored "
                           "at the minimum. Service credits under the SLA are a percentage of this.",
            "term_months": "Length of the current contract term.",
            "discount_pct": "Discount against list price, as a whole percentage.",
        },
    },
    "contacts": {
        "columns": ["contact_id","client_id","name","role","email","is_primary"],
        "comment": "People at Saldo's customers. Use this to find who to contact at a customer, "
                   "and to link an email address back to the company it belongs to.",
        "column_comments": {
            "contact_id": "Unique contact identifier.",
            "client_id": "The customer this person works for. Joins to clients.client_id.",
            "name": "Full name.",
            "role": "Job title at the customer.",
            "email": "Work email address. Some smaller customers use a shared mailbox rather than "
                     "a personal address.",
            "is_primary": "True for the main point of contact at that customer. Exactly one per customer.",
        },
    },
    "client_modules": {
        "columns": ["client_id","module","active_since"],
        "comment": "Which Saldo modules each customer subscribes to. One row per customer per module. "
                   "A customer without the Payroll module never appears in payroll_runs.",
        "column_comments": {
            "client_id": "Joins to clients.client_id.",
            "module": "Bookkeeping, Invoicing, Payroll, Tax or Banking.",
            "active_since": "Date the module became active for this customer.",
        },
    },
    "reason_codes": {
        "columns": ["reason_code","category","message","cause","resolution","rejects_whole_file"],
        "comment": "Validation codes Saldo returns when a payroll submission is rejected. "
                   "Parsed from the published Validation Error Reference so the two stay in step. "
                   "Look a code up here to find out what it means and whose problem it is.",
        "column_comments": {
            "reason_code": "The code itself, e.g. VAL-014.",
            "category": "Where the fault lies: 'file' (whole submission rejected), 'row' (a problem in "
                        "the submitted file), 'employee_record' (the file was fine, the employee's stored "
                        "record cannot be paid), or 'downstream' (a failure after validation, during payment).",
            "message": "The message shown to the customer.",
            "cause": "What actually triggers this code.",
            "resolution": "What has to be done to fix it.",
            "rejects_whole_file": "True if this code rejects the entire submission rather than one row.",
        },
    },
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", help="workshop date as YYYY-MM-DD (overrides the config)")
    ap.add_argument("--dry-run", action="store_true", help="build rows locally, load nothing")
    ap.add_argument("--profile", help="Databricks CLI profile (overrides the config)")
    args = ap.parse_args()

    cfg = dbx.load_config()
    pinned = args.date or cfg.get("workshop", {}).get("date")
    workshop_day = date.fromisoformat(str(pinned)) if pinned else date.today()
    timeline = build_timeline(workshop_day)

    tables = build_rows(cfg, workshop_day)

    print(f"Workshop day  {timeline.workshop_day}")
    print(f"Incident      {timeline.incident}\n")
    for name, rows in tables.items():
        print(f"  {name:<26} {len(rows):>6} rows")

    # The committed payroll history is dated. Documents resolve their dates at
    # seed time, but these rows do not, so a dataset generated weeks ago would
    # quietly put the incident in the distant past and the story stops matching.
    latest = max((r["submitted_at"].date() for r in tables["payroll_runs"]), default=None)
    if latest and (workshop_day - latest).days > 21:
        print(f"\n  WARNING  most recent payroll run is {(workshop_day - latest).days} days old "
              f"({latest}).\n           Run `make generate/data` and commit before the workshop.")

    if args.dry_run:
        print("\nnothing loaded (--dry-run)")
        return 0

    catalog = cfg["unity_catalog"]["catalog"]
    w = dbx.workspace(cfg, args.profile)
    dbx.ensure_schemas(w, cfg)
    staging = dbx.ensure_volume(
        w, cfg, "staging",
        "Parquet staging for workshop table loads. Not part of the workshop itself.",
    )

    print()
    for name, rows in tables.items():
        spec = SPEC[name]
        schema = dbx.table_schema(cfg, name)
        n = dbx.load_table(
            w,
            warehouse_id=cfg["warehouse_id"],
            catalog=catalog,
            schema=schema,
            table=name,
            rows=rows,
            columns=spec["columns"],
            comment=spec["comment"],
            column_comments=spec["column_comments"],
            staging_root=staging,
        )
        print(f"  loaded {schema}.{name:<28} {n:>6} rows")

    return 0


if __name__ == "__main__":
    sys.exit(main())
