"""Generate payroll history and service availability, and write them to workshop/data/.

Run this before a workshop; commit the output. The seed script only loads what is
here. Everything is seeded and deterministic.

Two things are worth understanding before reading the code.

**Periods lag submission.** Czech and Slovak wages for month M are paid during
month M+1. A run submitted on 4 August is therefore July's payroll, not August's.
That matters here because it puts Alpine's failing run immediately after the
release that broke it rather than a month later.

**Rejections are not hardcoded.** Each run is validated against the rules that
were live on the day it was submitted, which is exactly what the real system
does. Before release 2026.8 a legacy bank account was silently converted and the
row was paid; from 2026.8 the same row rejects with VAL-014. So Alpine's earlier
runs succeed and the current one does not, without any special-casing, and the
same rule catches the other two customers holding legacy accounts.

Usage:
    uv run workshop/scripts/generate_payroll.py
    uv run workshop/scripts/generate_payroll.py --check
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

SEED = 20260810
PERIODS = 8          # how many monthly periods of history to produce
SERVICES = ["web", "sftp", "api", "payroll_engine"]
AVAILABILITY_DAYS = 180

# Czech employee deductions, near enough for a demo: 6.5% social + 4.5% health,
# then 15% income tax reduced by the monthly taxpayer credit.
SOCIAL_HEALTH = 0.11
TAX_RATE = 0.15
TAXPAYER_CREDIT = 2570


def net_from_gross(gross: float) -> float:
    tax = max(0.0, gross * TAX_RATE - TAXPAYER_CREDIT)
    return round(gross * (1 - SOCIAL_HEALTH) - tax, 2)


def month_start(d: date, back: int = 0) -> date:
    total = d.year * 12 + (d.month - 1) - back
    return date(total // 12, total % 12 + 1, 1)


def month_end(d: date) -> date:
    return month_start(d, -1) - timedelta(days=1)


def channel_for(plan: str, rng: random.Random) -> str:
    """Standard plan customers only have the web application."""
    if plan == "Standard":
        return "web"
    return rng.choices(["sftp", "api", "web"], weights=[50, 25, 25], k=1)[0]


def build(cfg: dict, workshop_day: date) -> dict[str, list[dict]]:
    rng = random.Random(SEED)
    timeline = build_timeline(workshop_day)
    release = timeline.release_current   # 2026.8: legacy accounts stop being converted

    clients = {c["client_id"]: c
               for c in json.loads(dbx.data_file(cfg, "clients").read_text(encoding="utf-8"))}

    employees: dict[str, list[dict]] = {}
    with dbx.data_file(cfg, "employees").open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            employees.setdefault(r["client_id"], []).append(r)

    # How each customer behaves: which working day of the following month they
    # normally submit, and how much they drift. CL-003 is the one whose health
    # note says they submit late, so their habit has to match that.
    habit = {cid: {"day": rng.randint(3, 12), "drift": rng.randint(0, 3)}
             for cid in sorted(clients)}
    habit["CL-003"] = {"day": 16, "drift": 4}     # "submits payroll late most months"
    habit["CL-001"] = {"day": 4, "drift": 1}      # Alpine: early, by SFTP from their HR system

    runs: list[dict] = []
    items: list[dict] = []
    seq = 0

    for cid in sorted(clients):
        client = clients[cid]
        if "Payroll" not in client["modules"]:
            continue
        staff = employees.get(cid, [])
        if not staff:
            continue

        customer_since = workshop_day - timedelta(days=client["months_as_customer"] * 30)
        channel = channel_for(client["plan"], rng)

        for back in range(PERIODS, 0, -1):
            period_start = month_start(workshop_day, back)
            period = f"{period_start:%Y-%m}"

            # Submitted during the month after the period being paid.
            pay_month = month_start(period_start, -1)
            day = min(habit[cid]["day"] + rng.randint(0, habit[cid]["drift"]), 27)
            submitted = date(pay_month.year, pay_month.month, day)

            # The hero run is pinned to the incident date rather than left to the
            # customer's usual habit, so the story ("on Tuesday, Alpine ran their
            # payroll") and the data cannot drift apart.
            if cid == "CL-001" and back == 1:
                submitted = timeline.incident

            if submitted > workshop_day or period_start < customer_since:
                continue

            # Only people employed during the period appear in the run.
            in_period = [e for e in staff if date.fromisoformat(e["started_on"]) <= month_end(period_start)]
            if not in_period:
                continue

            seq += 1
            run_id = f"PR-{period_start:%Y%m}-{seq:04d}"
            hour, minute = rng.randint(7, 16), rng.randint(0, 59)
            if cid == "CL-001":
                # Alpine's file is dropped by SFTP from their own HR system on a
                # schedule, so it arrives early and well inside the 12:00 SFTP
                # cut-off. An afternoon timestamp would imply a missed cut-off
                # that nothing else in the story mentions.
                hour, minute = 6, rng.randint(5, 25)
            submitted_at = datetime(submitted.year, submitted.month, submitted.day, hour, minute)
            validated_at = submitted_at + timedelta(minutes=rng.randint(1, 6))
            approved_at = validated_at + timedelta(hours=rng.randint(1, 30))

            accepted = rejected = 0
            gross_total = net_total = 0.0
            for e in in_period:
                if e["pay_basis"] == "hourly":
                    hours = round(rng.triangular(120, 184, 168), 2)
                    gross = round(hours * float(e["hourly_rate"]), 2)
                else:
                    hours = None
                    gross = float(e["monthly_salary"])
                bonus = round(gross * rng.choice([0, 0, 0, 0.05, 0.1]), 2)
                gross = round(gross + bonus, 2)

                # The rule the product applies, applied here: a legacy account was
                # converted silently until 2026.8 and rejects from then on.
                legacy = e["bank_account_format"] != "IBAN"
                fails = legacy and submitted >= release

                if fails:
                    rejected += 1
                    status, reason, net = "REJECTED", "VAL-014", None
                else:
                    accepted += 1
                    status, reason = "PAID", None
                    net = net_from_gross(gross)
                    gross_total += gross
                    net_total += net

                items.append({
                    "run_id": run_id,
                    "client_id": cid,
                    "employee_id": e["employee_id"],
                    "cost_centre": e["cost_centre"],
                    "hours_worked": hours,
                    "gross_amount": gross,
                    "net_amount": net,
                    "status": status,
                    "reason_code": reason,
                })

            runs.append({
                "run_id": run_id,
                "client_id": cid,
                "period": period,
                "channel": channel,
                "is_correction_run": False,
                "submitted_at": submitted_at,
                "validated_at": validated_at,
                "approved_at": approved_at,
                "value_date": submitted + timedelta(days=2),
                "employee_count": len(in_period),
                "accepted_count": accepted,
                "rejected_count": rejected,
                "total_gross": round(gross_total, 2),
                "total_net": round(net_total, 2),
                "status": "PARTIALLY_COMPLETED" if rejected else "COMPLETED",
            })

    availability = build_availability(rng, workshop_day, timeline)
    return {"payroll_runs": runs, "payroll_run_items": items,
            "service_availability_daily": availability}


def build_availability(rng: random.Random, workshop_day: date, timeline) -> list[dict]:
    """Daily availability per service.

    Deliberately boring, with a small number of real incidents placed on purpose.
    The day Alpine's run failed has to look completely normal - that is what lets
    the question "were we down?" be answered with evidence rather than a shrug.
    """
    # (days before the workshop, service, minutes lost) - genuine outages.
    incidents = {
        (118, "api"): 47,
        (96, "web"): 214,        # the one that took a month below its target
        (61, "sftp"): 38,
        (25, "payroll_engine"): 22,
    }
    rows = []
    for back in range(AVAILABILITY_DAYS, -1, -1):
        day = workshop_day - timedelta(days=back)
        for svc in SERVICES:
            lost = incidents.get((back, svc), 0)
            # Scheduled Saturday maintenance is excluded from availability by the SLA.
            planned = 240 if day.weekday() == 5 and rng.random() < 0.25 else 0
            measurable = 1440 - planned
            uptime = round(100 * (measurable - lost) / measurable, 4)
            rows.append({
                "day": day,
                "service": svc,
                "uptime_pct": uptime,
                "unavailable_minutes": lost,
                "planned_maintenance_minutes": planned,
                "avg_latency_ms": rng.randint(90, 260) + (rng.randint(200, 900) if lost else 0),
                "error_rate_pct": round(rng.uniform(0.01, 0.09) + (rng.uniform(1, 4) if lost else 0), 3),
            })
    return rows


COLUMNS = {
    "payroll_runs": ["run_id","client_id","period","channel","is_correction_run","submitted_at",
                     "validated_at","approved_at","value_date","employee_count","accepted_count",
                     "rejected_count","total_gross","total_net","status"],
    "payroll_run_items": ["run_id","client_id","employee_id","cost_centre","hours_worked",
                          "gross_amount","net_amount","status","reason_code"],
    "service_availability_daily": ["day","service","uptime_pct","unavailable_minutes",
                                   "planned_maintenance_minutes","avg_latency_ms","error_rate_pct"],
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
    runs, items = tables["payroll_runs"], tables["payroll_run_items"]

    print(f"workshop day      {workshop_day}")
    print(f"release 2026.8    {timeline.release_current}")
    for name, rows in tables.items():
        print(f"  {name:<28} {len(rows):>7} rows")

    failed = [r for r in runs if r["rejected_count"]]
    print(f"\nruns with rejections: {len(failed)}")
    for r in sorted(failed, key=lambda x: x["submitted_at"]):
        print(f"   {r['run_id']}  {r['client_id']}  period {r['period']}  "
              f"submitted {r['submitted_at']:%Y-%m-%d}  "
              f"{r['rejected_count']} of {r['employee_count']} rejected  {r['status']}")

    alpine = [r for r in runs if r["client_id"] == "CL-001"]
    print("\nAlpine Retail history:")
    for r in sorted(alpine, key=lambda x: x["period"]):
        print(f"   period {r['period']}  submitted {r['submitted_at']:%Y-%m-%d}  "
              f"{r['accepted_count']:>5} paid  {r['rejected_count']:>3} rejected  {r['status']}")

    if args.check:
        print("\nnothing written (--check)")
        return 0

    out_dir = dbx.data_subdir(cfg, "payroll")
    for name, rows in tables.items():
        path = out_dir / f"{name}.csv"
        with path.open("w", encoding="utf-8", newline="") as fh:
            wr = csv.DictWriter(fh, fieldnames=COLUMNS[name])
            wr.writeheader()
            wr.writerows(rows)
        print(f"\nwrote {path.relative_to(dbx.REPO_ROOT)}  ({path.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
