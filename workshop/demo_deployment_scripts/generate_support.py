"""Resolve the support corpus against the workshop date and write it to CSV.

cases.json, incidents.json and changes.json are hand-authored and store dates as
`days_ago` rather than as calendar dates, so they never go stale. This script
turns them into dated rows.

A few records anchor to the story timeline instead of a fixed offset - the
release that removed automatic account conversion has to land where the release
notes and the payroll history say it did, not at an arbitrary number of days.

Usage:
    uv run workshop/scripts/generate_support.py
    uv run workshop/scripts/generate_support.py --check
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dbx  # noqa: E402
from seed_docs import build_timeline  # noqa: E402

SEED = 20260811


def resolve(record: dict, workshop_day: date, timeline) -> date:
    """A record is dated either from the story timeline or by days_ago."""
    anchor = record.get("anchor")
    if anchor == "release_current":
        return timeline.release_current
    if anchor == "deprecation":
        return timeline.deprecation
    return workshop_day - timedelta(days=record["days_ago"])


def build(cfg: dict, workshop_day: date) -> dict[str, list[dict]]:
    rng = random.Random(SEED)
    timeline = build_timeline(workshop_day)

    changes = []
    for c in json.loads(dbx.data_file(cfg, "changes").read_text(encoding="utf-8")):
        day = resolve(c, workshop_day, timeline)
        changes.append({
            "change_id": c["change_id"],
            "release": c["release"],
            "component": c["component"],
            "title": c["title"],
            "description": c["description"],
            "risk": c["risk"],
            "customer_action_required": c["customer_action_required"],
            "backed_out": c["backed_out"],
            "deployed_by": c["deployed_by"],
            # Releases go out in the Saturday maintenance window, 02:00-06:00.
            "deployed_at": datetime(day.year, day.month, day.day, 2, rng.randint(5, 55)),
        })

    incidents = []
    for i in json.loads(dbx.data_file(cfg, "incidents").read_text(encoding="utf-8")):
        day = resolve(i, workshop_day, timeline)
        opened = datetime(day.year, day.month, day.day, rng.randint(6, 15), rng.randint(0, 59))
        minutes = i["unavailable_minutes"] or rng.randint(45, 400)
        incidents.append({
            "incident_id": i["incident_id"],
            "component": i["component"],
            "severity": i["severity"],
            "summary": i["summary"],
            "detail": i["detail"],
            "root_cause": i["root_cause"],
            "linked_change_id": i["linked_change_id"],
            "customers_affected": i["customers_affected"],
            "unavailable_minutes": i["unavailable_minutes"],
            "opened_at": opened,
            "resolved_at": opened + timedelta(minutes=minutes),
        })

    contacts = {}
    for c in json.loads(dbx.data_file(cfg, "clients").read_text(encoding="utf-8")):
        for p in c["contacts"]:
            contacts[(c["client_id"], p["role"])] = p["email"]

    cases = []
    for c in json.loads(dbx.data_file(cfg, "cases").read_text(encoding="utf-8")):
        opened_day = workshop_day - timedelta(days=c["days_ago"])
        opened = datetime(opened_day.year, opened_day.month, opened_day.day,
                          rng.randint(7, 17), rng.randint(0, 59))
        closed = None
        if c["duration_days"] is not None:
            closed = opened + timedelta(days=c["duration_days"], hours=rng.randint(0, 8))
        # Reporter resolves to a real contact at that customer, so a case can be
        # joined back to the mailbox and to the person who raised it.
        email = contacts.get((c["client_id"], c["reported_by_role"]))
        if email is None:                       # role not present at that customer
            email = next(v for (cid, _), v in contacts.items() if cid == c["client_id"])
        cases.append({
            "case_id": c["case_id"],
            "client_id": c["client_id"],
            "opened_at": opened,
            "closed_at": closed,
            "status": c["status"],
            "severity": c["severity"],
            "category": c["category"],
            "channel": c["channel"],
            "subject": c["subject"],
            "description": c["description"],
            "resolution_notes": c["resolution_notes"],
            "root_cause": c["root_cause"],
            "reported_by": email,
            "assigned_to": c["assigned_to"],
            "linked_incident_id": c["linked_incident_id"],
            "linked_run_id": c["linked_run_id"],
        })

    cases.sort(key=lambda r: r["opened_at"])
    incidents.sort(key=lambda r: r["opened_at"])
    changes.sort(key=lambda r: r["deployed_at"])
    return {"support_cases": cases, "incidents": incidents, "changes": changes}


COLUMNS = {
    "support_cases": ["case_id","client_id","opened_at","closed_at","status","severity","category",
                      "channel","subject","description","resolution_notes","root_cause",
                      "reported_by","assigned_to","linked_incident_id","linked_run_id"],
    "incidents": ["incident_id","component","severity","opened_at","resolved_at",
                  "unavailable_minutes","summary","detail","root_cause","linked_change_id",
                  "customers_affected"],
    "changes": ["change_id","release","component","deployed_at","title","description","risk",
                "customer_action_required","backed_out","deployed_by"],
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", help="workshop date as YYYY-MM-DD (overrides the config)")
    ap.add_argument("--check", action="store_true", help="build and report, write nothing")
    args = ap.parse_args()

    cfg = dbx.load_config()
    pinned = args.date or cfg.get("workshop", {}).get("date")
    workshop_day = date.fromisoformat(str(pinned)) if pinned else date.today()
    timeline = build_timeline(workshop_day)

    tables = build(cfg, workshop_day)
    for name, rows in tables.items():
        print(f"  {name:<20} {len(rows):>5} rows")

    open_cases = [c for c in tables["support_cases"] if c["closed_at"] is None]
    print(f"\nopen cases: {len(open_cases)}")
    for c in open_cases:
        print(f"   {c['case_id']}  {c['client_id']}  {c['severity']}  "
              f"opened {c['opened_at']:%Y-%m-%d}  {c['subject'][:52]}")

    rel = [c for c in tables["changes"] if c["change_id"] == "CHG-0488"][0]
    print(f"\nCHG-0488 deployed {rel['deployed_at']:%Y-%m-%d %H:%M}  "
          f"(release 2026.8 = {timeline.release_current})")

    # Nothing is written. The written source is cases.json, incidents.json and
    # changes.json; these rows are built from them at load time by
    # seed_tables.py, so there is no second copy on disk to fall out of step.
    # Running this on its own is a way to check the source still resolves.
    print("\nnothing written - these rows are built at load time from the .json source")
    return 0


if __name__ == "__main__":
    sys.exit(main())
