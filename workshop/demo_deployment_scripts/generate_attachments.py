"""Build the files attached to support cases and upload them to a UC volume.

These are the artefacts a support engineer would have pulled together while
working a case: the rejection report from the run detail screen, a copy of the
file the customer actually submitted, and the validator log for the run.

Everything here is DERIVED from the committed tables rather than written by
hand. The 47 people named in Alpine's rejection report are the same 47 rows that
payroll_run_items marks REJECTED, carrying the same account values that sit in
employees.csv. If these were authored separately they would drift, and the first
person to cross-check a name against the table would see the dataset is fake.

What the files are for: the answer to "was the customer's file wrong?" is not in
any table. It is only visible by opening the submitted file and noticing it has
no bank account column at all - the format specification says bank details come
from the employee master, and here is the proof. That is a question an agent has
to compute rather than look up.

Usage:
    uv run workshop/scripts/generate_attachments.py --check
    uv run workshop/scripts/generate_attachments.py
"""

from __future__ import annotations

import argparse
import csv
import io
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dbx  # noqa: E402

SEED = 20260812
HERO_RUN = "PR-202607-0008"
HERO_CASE = "CAS-40318"
PAST_CASE = "CAS-38702"      # Fenmark, period column rejected the whole file


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def sc(rows: list[dict], columns: list[str]) -> bytes:
    """Semicolon-delimited UTF-8, as the file specification requires."""
    buf = io.StringIO()
    wr = csv.DictWriter(buf, fieldnames=columns, delimiter=";", lineterminator="\r\n")
    wr.writeheader()
    wr.writerows(rows)
    return buf.getvalue().encode("utf-8")


def build(cfg: dict) -> dict[str, bytes]:
    rng = random.Random(SEED)

    employees = {e["employee_id"]: e for e in read_csv(dbx.data_file(cfg, "employees"))}
    runs = {r["run_id"]: r for r in read_csv(dbx.data_file(cfg, "payroll_runs"))}
    items = read_csv(dbx.data_file(cfg, "payroll_run_items"))

    run = runs[HERO_RUN]
    submitted = datetime.fromisoformat(run["submitted_at"])
    hero_items = [i for i in items if i["run_id"] == HERO_RUN]
    rejected = [i for i in hero_items if i["status"] == "REJECTED"]
    if not rejected:
        raise SystemExit(f"{HERO_RUN} has no rejected rows; regenerate the payroll data first")

    files: dict[str, bytes] = {}

    # 1. The rejection report, as downloaded from the run detail screen.
    #    Since release 2026.8 it names the failing column (CHG-0487).
    report = []
    for i in rejected:
        e = employees[i["employee_id"]]
        report.append({
            "run_id": HERO_RUN,
            "employee_id": e["employee_id"],
            "employee_name": f"{e['first_name']} {e['last_name']}",
            "cost_centre": i["cost_centre"],
            "error_code": i["reason_code"],
            "error_message": "Bank account is not a valid IBAN",
            "failing_column": "bank_account",
            "stored_value": e["bank_account"],
            "record_updated_on": e["record_updated_on"],
        })
    report.sort(key=lambda r: r["employee_id"])
    files[f"{HERO_CASE}/rejection_report_{HERO_RUN}.csv"] = sc(report, list(report[0]))

    # 2. A copy of the file the customer actually submitted. The point of this
    #    one is what it does NOT contain: there is no bank account column, so
    #    the file cannot be the cause of a bank account rejection.
    submitted_rows = []
    for i in sorted(hero_items, key=lambda x: x["employee_id"]):
        e = employees[i["employee_id"]]
        submitted_rows.append({
            "employee_id": i["employee_id"],
            "period": run["period"],
            "hours_worked": i["hours_worked"] or "",
            "gross_amount": "" if i["hours_worked"] else i["gross_amount"],
            "bonus": "",
            "absence_days": "0",
            "cost_centre": i["cost_centre"],
            "note": f"Payroll {run['period'][5:]}/{run['period'][:4]}",
        })
    files[f"{HERO_CASE}/payroll_input_{run['period']}.csv"] = sc(
        submitted_rows, list(submitted_rows[0]))

    # 3. Validator log for the run. Interleaved with other customers' runs from
    #    the same morning, so it has to be filtered rather than just read.
    files[f"{HERO_CASE}/validator_{submitted:%Y-%m-%d}.log"] = build_log(
        rng, submitted, run, rejected, employees)

    # 4. One historical attachment so the volume is not a single-case artefact.
    #    Fenmark's whole file rejected on the period column, 163 days ago.
    fen = [e for e in employees.values() if e["client_id"] == "CL-004"][:18]
    past = [{
        "run_id": "PR-202602-0021",
        "employee_id": e["employee_id"],
        "employee_name": f"{e['first_name']} {e['last_name']}",
        "cost_centre": e["cost_centre"],
        "error_code": "VAL-013",
        "error_message": "Period mismatch",
        "failing_column": "period",
        "stored_value": "2026-03",
        "record_updated_on": "",
    } for e in fen]
    files[f"{PAST_CASE}/rejection_report_PR-202602-0021.csv"] = sc(past, list(past[0]))

    return files


def build_log(rng, submitted, run, rejected, employees) -> bytes:
    """The payroll engine's validator log.

    The line that matters reads the account off the employee master and prints
    when that record was last touched. Every rejected row shows the same date,
    which is the day the customer's master was migrated.
    """
    t = submitted.replace(second=3, microsecond=412000)
    lines: list[str] = []

    def add(offset_ms: int, level: str, msg: str) -> None:
        nonlocal t
        t = t + timedelta(milliseconds=offset_ms)
        lines.append(f"{t:%Y-%m-%d %H:%M:%S}.{t.microsecond // 1000:03d} {level:<5} [validator] {msg}")

    add(0, "INFO", f"run={run['run_id']} client={run['client_id']} channel={run['channel']} "
                   f"file=payroll_{run['period']}.csv rows={run['employee_count']}")
    add(180, "INFO", f"run={run['run_id']} file-level checks passed (encoding=UTF-8 delimiter=';' "
                     f"columns=8)")
    add(240, "INFO", f"run={run['run_id']} resolving employee master for "
                     f"{run['employee_count']} rows")

    # Another customer's run running at the same time, so the log needs filtering.
    add(90, "INFO", "run=PR-202607-0071 client=CL-011 channel=web file=payroll_2026-07.csv rows=62")
    add(60, "INFO", "run=PR-202607-0071 file-level checks passed (encoding=UTF-8 delimiter=';' columns=8)")

    for n, i in enumerate(sorted(rejected, key=lambda x: x["employee_id"])):
        e = employees[i["employee_id"]]
        add(rng.randint(20, 90), "WARN",
            f"run={run['run_id']} row={n + 1} employee={e['employee_id']} {i['reason_code']} "
            f"bank_account rejected: stored value '{e['bank_account']}' is not a valid IBAN "
            f"(format={e['bank_account_format']} source=employee_master "
            f"record_updated_on={e['record_updated_on']})")
        if n == 11:
            add(40, "WARN", "run=PR-202607-0071 row=58 employee=E011-00058 VAL-014 "
                            "bank_account rejected: stored value '19-4471209/0800' is not a valid "
                            "IBAN (format=legacy_domestic source=employee_master "
                            "record_updated_on=2024-09-02)")

    add(120, "INFO", f"run={run['run_id']} validation complete "
                     f"accepted={run['accepted_count']} rejected={run['rejected_count']}")
    add(15, "INFO", f"run={run['run_id']} status=PARTIALLY_COMPLETED, continuing to calculation "
                    f"with {run['accepted_count']} rows")
    add(400, "INFO", "run=PR-202607-0071 validation complete accepted=61 rejected=1")
    return ("\r\n".join(lines) + "\r\n").encode("utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="build locally, upload nothing")
    ap.add_argument("--profile", help="Databricks CLI profile")
    args = ap.parse_args()

    cfg = dbx.load_config()
    files = build(cfg)

    for name, body in sorted(files.items()):
        print(f"  {name:<58} {len(body):>8} bytes")

    if args.check:
        hero = next(v for k, v in files.items() if "payroll_input" in k)
        header = hero.decode("utf-8").splitlines()[0]
        print(f"\nsubmitted file columns: {header}")
        print(f"contains a bank account column: {'bank' in header.lower()}")
        print("\nnothing uploaded (--check)")
        return 0

    w = dbx.workspace(cfg, args.profile)
    dbx.ensure_schemas(w, cfg)
    root = dbx.ensure_volume(
        w, cfg, "attachments",
        "Files attached to Saldo support cases (workshop, synthetic).")

    expected = set()
    for name, body in sorted(files.items()):
        target = f"{root}/{name}"
        w.files.upload(target, io.BytesIO(body), overwrite=True)
        expected.add(target)
        print(f"  uploaded {name}")

    for path in sorted(set(_walk(w, root)) - expected):
        w.files.delete(path)
        print(f"  removed  {path[len(root) + 1:]}")

    print(f"\n{len(files)} files in {root}")
    return 0


def _walk(w, path: str) -> list[str]:
    out: list[str] = []
    try:
        entries = list(w.files.list_directory_contents(path))
    except Exception:
        return out
    for e in entries:
        out.extend(_walk(w, e.path)) if e.is_directory else out.append(e.path)
    return out


if __name__ == "__main__":
    sys.exit(main())
