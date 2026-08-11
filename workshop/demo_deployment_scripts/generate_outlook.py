"""Write the mailbox and calendar the workshop starts from.

Until now the mocked Outlook was seeded with generic filler: meetings called
"Project Sync", mail from a fictional CTO. It had nothing to do with Saldo, so
the moment anyone opened it the story fell apart.

This builds the mailbox of somebody on Saldo's side of the Alpine Retail problem.
Every date is read out of the committed tables rather than typed here, so the mail
about the failed run carries the timestamp the run actually has, and the calendar
entry for the escalation call sits after the case was opened. If the tables are
regenerated on a different anchor date, this moves with them.

The named people are the ones in clients.json and support_cases.csv, spelled the
same way. Someone will check.

The output is one committed JSON file. The app materialises a copy of it per
person, so nothing in here is written to at runtime.

Usage:
    uv run workshop/scripts/generate_outlook.py --check
    uv run workshop/scripts/generate_outlook.py
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dbx  # noqa: E402
import generate_support  # noqa: E402

OUT = "outlook_seed.json"

# Saldo's own people. The support engineers are the four in support_cases.csv.
SALDO = {
    "ondrej": ("Ondřej Bureš", "ondrej.bures@saldo.cz"),
    "tereza": ("Tereza Marková", "tereza.markova@saldo.cz"),
    "filip": ("Filip Doležal", "filip.dolezal@saldo.cz"),
    "ivana": ("Ivana Kramářová", "ivana.kramarova@saldo.cz"),
    "tomas": ("Tomáš Richter", "tomas.richter@saldo.cz"),
    "release": ("Saldo Release Notes", "no-reply@saldo.cz"),
    "platform": ("Saldo Platform", "no-reply@saldo.cz"),
}
ALPINE = {
    "marketa": ("Markéta Sedláčková", "marketa.sedlackova@alpineretail.cz"),
    "lenka": ("Lenka Marešová", "lenka.maresova@alpineretail.cz"),
    "jakub": ("Jakub Horák", "jakub.horak@alpineretail.cz"),
}


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def at(day: datetime, hhmm: str, shift_days: int = 0) -> str:
    h, m = (int(x) for x in hhmm.split(":"))
    return (day.replace(hour=h, minute=m, second=0, microsecond=0)
            + timedelta(days=shift_days)).isoformat()


def build(cfg: dict, workshop_day: date) -> dict:
    runs = {r["run_id"]: r for r in read_csv(dbx.data_file(cfg, "payroll_runs"))}
    # Built from the same written source the loader uses, so the mail cannot
    # carry a timestamp the table does not have.
    support = generate_support.build(cfg, workshop_day)
    cases = {c["case_id"]: c for c in support["support_cases"]}
    changes = {c["change_id"]: c for c in support["changes"]}

    run = runs["PR-202607-0008"]
    case = cases["CAS-40318"]
    chg = changes["CHG-0488"]

    # payroll_runs is still a committed CSV, so its timestamps arrive as text.
    # The support rows are built in memory and are already datetimes.
    submitted = datetime.fromisoformat(run["submitted_at"])       # the run that failed
    opened = case["opened_at"]                                    # the case
    deployed = chg["deployed_at"]                                 # release 2026.8
    rejected = int(run["rejected_count"])
    period = run["period"]

    marketa, lenka, jakub = ALPINE["marketa"], ALPINE["lenka"], ALPINE["jakub"]
    ondrej, tomas = SALDO["ondrej"], SALDO["tomas"]

    inbox = [
        # The escalation. This is the mail the demo answers.
        {
            "from": marketa[1], "from_name": marketa[0],
            "subject": f"{rejected} of our people have not been paid",
            "date": at(opened, "12:18"),
            "read": False, "has_attachments": False,
            "body": (
                "Good afternoon,\n\n"
                f"I have {rejected} people in my office who were not paid on Friday, and I have no "
                "answer for them. Our July file went to you the same way it goes every month. "
                "Nobody here changed anything.\n\n"
                "Lenka tells me your system rejected them. I need to know why it rejected our "
                "people and not everyone else's, when we will be paying them, and whether this "
                "happens again in August.\n\n"
                "I would also like to understand what compensation we are entitled to. We have "
                "store managers dealing with very upset staff at the end of the month.\n\n"
                "Please call me today.\n\n"
                "Markéta Sedláčková\n"
                "Finance Director, Alpine Retail a.s."
            ),
        },
        # The operational report that came first.
        {
            "from": lenka[1], "from_name": lenka[0],
            "subject": f"July run - rejected rows ({run['run_id']})",
            "date": at(submitted, "09:47"),
            "read": True, "has_attachments": True,
            "body": (
                "Hello,\n\n"
                f"I submitted the {period} payroll yesterday morning as usual and the run came "
                f"back partially completed. {rejected} rows rejected, the rest went through.\n\n"
                "I have looked at the rejection report and I do not understand it. It says the "
                "bank account is not valid, but these are people who have been paid every month "
                "for years. I have not touched their records.\n\n"
                "Report attached. Can somebody look before Friday's payment date?\n\n"
                "Thanks,\nLenka Marešová\nPayroll Manager, Alpine Retail"
            ),
        },
        # The system notification, timed to the run itself.
        {
            "from": SALDO["platform"][1], "from_name": SALDO["platform"][0],
            "subject": f"[Saldo] Run {run['run_id']} completed with rejections",
            "date": at(submitted, "06:14"),
            "read": True, "has_attachments": False,
            "body": (
                f"Customer:  Alpine Retail a.s. (CL-001)\n"
                f"Run:       {run['run_id']}\n"
                f"Period:    {period}\n"
                f"Channel:   {run['channel']}\n"
                f"Submitted: {run['submitted_at'].replace('T', ' ')}\n\n"
                f"Rows submitted: {run['employee_count']}\n"
                f"Accepted:       {run['accepted_count']}\n"
                f"Rejected:       {rejected}\n"
                f"Status:         {run['status']}\n\n"
                "The accepted rows have continued to calculation. Rejected rows are listed in "
                "the run detail screen.\n\n"
                "This is an automated message."
            ),
        },
        # The release that caused it, sent before anything went wrong.
        {
            "from": SALDO["release"][1], "from_name": SALDO["release"][0],
            "subject": f"Saldo {chg['release']} went out on Saturday",
            "date": at(deployed, "07:30"),
            "read": True, "has_attachments": False,
            # Deliberately says a release happened and nothing about what was in
            # it. Naming the change here would put the answer in the mailbox, and
            # the mail tool would then solve a case that is supposed to need the
            # change records.
            "body": (
                f"Release {chg['release']} went out in the Saturday maintenance window and "
                "everything came back clean.\n\n"
                "The change log has the full list as usual. Anything customer-facing is flagged "
                "there.\n\n"
                "This is an automated message."
            ),
        },
        # The account manager, worried about the commercial side.
        {
            "from": tomas[1], "from_name": tomas[0],
            "subject": "Alpine - they are asking about the contract",
            "date": at(opened, "16:40"),
            "read": False, "has_attachments": False,
            "body": (
                "Markéta called me straight after she mailed you. She is asking for a service "
                "credit and she used the word terminate, which she has not done before.\n\n"
                "Before I go back to her I need to know where we actually stand. Was this us or "
                "was it their data? And are they owed anything under the SLA, or am I offering "
                "goodwill?\n\n"
                "They are 1,240 employees on Professional, Brno. Renewal is not close, but I do "
                "not want this sitting there.\n\n"
                "Tomáš"
            ),
        },
        # The engineer who owns the case.
        {
            "from": ondrej[1], "from_name": ondrej[0],
            "subject": f"Re: {case['case_id']} - what I have so far",
            "date": at(opened, "17:55"),
            "read": False, "has_attachments": False,
            "body": (
                "I have been through the run.\n\n"
                "Every rejected row carries the same error code, and the run before this one was "
                "clean. Same customer, same channel, nothing different on their side that I can "
                "see.\n\n"
                "I do not want to go back to Markéta with a guess. Can somebody check what went "
                "out recently and whether anything else has come in like this?\n\n"
                "Ondřej"
            ),
        },
        # The customer's own mail, forwarded by whoever the case is assigned to.
        # assigned_to is read from support_cases, so the name on this forward and
        # the name on the case in CaseHub cannot drift apart.
        {
            "from": ondrej[1], "from_name": ondrej[0],
            "subject": f"FW: {rejected} of our people have not been paid",
            "date": at(opened, "13:05"),
            "read": False, "has_attachments": False,
            "body": (
                f"Forwarding this one - it is {case['case_id']}, raised this lunchtime.\n\n"
                "I have the run open and I am going through the rejected rows, but she is asking "
                "about compensation as well and that is not mine to answer. Can you pick up that "
                "side of it?\n\n"
                "Ondřej\n\n"
                "-----Original message-----\n"
                f"From: {marketa[0]} <{marketa[1]}>\n"
                f"Sent: {opened:%d %B %Y} 12:18\n"
                f"To: support@saldo.cz\n"
                f"Subject: {rejected} of our people have not been paid\n\n"
                "Good afternoon,\n\n"
                f"I have {rejected} people in my office who were not paid on Friday, and I have "
                "no answer for them. Our July file went to you the same way it goes every month. "
                "Nobody here changed anything.\n\n"
                "Lenka tells me your system rejected them. I need to know why it rejected our "
                "people and not everyone else's, when we will be paying them, and whether this "
                "happens again in August.\n\n"
                "I would also like to understand what compensation we are entitled to.\n\n"
                "Markéta Sedláčková\n"
                "Finance Director, Alpine Retail a.s."
            ),
        },
        # Their IT manager, ready to act.
        {
            "from": jakub[1], "from_name": jakub[0],
            "subject": "Re: employee master - what format do you need?",
            "date": at(opened, "18:20", shift_days=1),
            "read": False, "has_attachments": False,
            "body": (
                "Markéta asked me to sort this out from our side.\n\n"
                "I can pull the affected people out of our HR system and re-upload them, but I "
                "need to know exactly what you want in the bank account column and whether I "
                "upload only those people or the whole master again.\n\n"
                "Also - our SFTP job runs at 06:00. If we re-upload today does it get picked up "
                "with the August run or do you need to reprocess July separately?\n\n"
                "Jakub Horák\nIT Manager, Alpine Retail"
            ),
        },
        # Ordinary traffic, so the mailbox is not one thread.
        {
            "from": SALDO["ivana"][1], "from_name": SALDO["ivana"][0],
            "subject": "Cost centre export for Kroupa - who owns this one?",
            "date": at(opened, "11:05", shift_days=-1),
            "read": True, "has_attachments": False,
            "body": (
                "Kroupa Obrábění want their year-to-date labour cost split by production "
                "section. It is sitting unassigned and I am on the Naldex migration all week.\n\n"
                "Can somebody pick it up?\n\nIvana"
            ),
        },
        {
            "from": SALDO["platform"][1], "from_name": SALDO["platform"][0],
            "subject": "[Saldo] Scheduled maintenance this Saturday, 02:00-04:00 CET",
            "date": at(opened, "08:00", shift_days=-2),
            "read": True, "has_attachments": False,
            "body": (
                "The web application and the API will be unavailable between 02:00 and 04:00 CET "
                "on Saturday for planned database maintenance.\n\n"
                "SFTP submissions received during the window are queued and processed afterwards. "
                "Scheduled maintenance is excluded from the availability measurement.\n\n"
                "This is an automated message."
            ),
        },
    ]

    sent = [
        {
            "to": lenka[1],
            "subject": f"Re: July run - rejected rows ({run['run_id']})",
            "date": at(submitted, "11:20"),
            "read": True, "has_attachments": False,
            "body": (
                "Hello Lenka,\n\n"
                "Thanks for the report. I have raised this as "
                f"{case['case_id']} and I am looking at the run now.\n\n"
                "One thing that would help straight away: can you confirm whether your submitted "
                "file contains a bank account column at all? I want to rule the file in or out "
                "before I go further.\n\n"
                "I will come back to you today.\n\n"
                "Kind regards"
            ),
        },
        {
            "to": tomas[1],
            "subject": "Re: Alpine - they are asking about the contract",
            "date": at(opened, "17:02"),
            "read": True, "has_attachments": False,
            "body": (
                "Give me until tomorrow morning before you call her back. I do not want to say "
                "anything about credits until I know whether we were actually down, which I do "
                "not think we were.\n\n"
                "Their run failed on validation. That is not the same thing, and the two get "
                "confused every time."
            ),
        },
    ]

    # One draft, deliberately about something else. The draft the agent writes
    # during the demo should be the one that stands out in this folder.
    drafts = [
        {
            "to": SALDO["filip"][1],
            "subject": "Handover notes - week of the 2026.8 release",
            "date": at(opened, "19:30"),
            "read": True, "has_attachments": False,
            "body": (
                "Filip,\n\n"
                "Things to keep an eye on while I am out:\n\n"
                "- Alpine Retail, the big one. Case is open.\n"
                "- Fenmark still have not moved their period column, so expect a repeat.\n"
                "- "
            ),
        },
    ]

    calendar = [
        {
            "title": "Alpine Retail - July payroll, call with Markéta",
            "start": at(opened, "09:00", shift_days=1), "end": at(opened, "09:45", shift_days=1),
            "location": "Teams", "is_recurring": False,
            "attendees": [marketa[1], tomas[1], ondrej[1]],
            "description": (
                f"Markéta wants an answer on the {rejected} unpaid employees, when they get paid, "
                "and whether they are owed a service credit. Have the run detail open."
            ),
        },
        {
            "title": f"{case['case_id']} - review before we reply",
            "start": at(opened, "08:15", shift_days=1), "end": at(opened, "08:45", shift_days=1),
            "location": "Meeting room 2", "is_recurring": False,
            "attendees": [ondrej[1], tomas[1]],
            "description": "Agree what we tell them about cause and about compensation.",
        },
        {
            "title": "Support standup",
            "start": at(opened, "09:00"), "end": at(opened, "09:15"),
            "location": "Teams", "is_recurring": True,
            "attendees": [ondrej[1], SALDO["tereza"][1], SALDO["filip"][1], SALDO["ivana"][1]],
            "description": "Queue, escalations, anything blocked.",
        },
        {
            "title": "Release 2026.9 - go / no go",
            "start": at(deployed, "14:00", shift_days=21), "end": at(deployed, "15:00", shift_days=21),
            "location": "Teams", "is_recurring": False,
            "attendees": [ondrej[1], tomas[1], SALDO["tereza"][1]],
            "description": "Nothing in this release needs customer action. Confirm that.",
        },
        {
            "title": "Alpine Retail - quarterly service review",
            "start": at(opened, "10:00", shift_days=9), "end": at(opened, "11:00", shift_days=9),
            "location": "Brno, customer site", "is_recurring": False,
            "attendees": [marketa[1], jakub[1], tomas[1]],
            "description": "Standing quarterly. July will dominate it this time.",
        },
        {
            "title": "Naldex migration - working session",
            "start": at(opened, "13:00", shift_days=2), "end": at(opened, "14:30", shift_days=2),
            "location": "Teams", "is_recurring": False,
            "attendees": [SALDO["ivana"][1], SALDO["filip"][1]],
            "description": "Employee master mapping.",
        },
        {
            "title": "Payroll platform - weekly",
            "start": at(opened, "11:00", shift_days=3), "end": at(opened, "12:00", shift_days=3),
            "location": "Teams", "is_recurring": True,
            "attendees": [ondrej[1], SALDO["tereza"][1]],
            "description": "Validation changes, rejection volumes, anything customers are hitting.",
        },
    ]

    return {
        "generated_from": {
            "run": run["run_id"], "case": case["case_id"], "change": chg["change_id"],
            "note": "Dates are read from the committed tables. Do not edit them here.",
        },
        "inbox": inbox, "sent": sent, "drafts": drafts, "calendar": calendar,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="build it, write nothing")
    args = ap.parse_args()

    cfg = dbx.load_config()
    pinned = cfg.get("workshop", {}).get("date")
    workshop_day = date.fromisoformat(str(pinned)) if pinned else date.today()
    seed = build(cfg, workshop_day)
    target = dbx.data_file(cfg, "outlook_seed")

    print(f"  inbox    {len(seed['inbox']):>2} messages")
    print(f"  sent     {len(seed['sent']):>2}")
    print(f"  drafts   {len(seed['drafts']):>2}")
    print(f"  calendar {len(seed['calendar']):>2} events")
    print(f"  anchored on {seed['generated_from']}")

    if args.check:
        first = seed["inbox"][0]
        print(f"\n  newest: {first['date']}  {first['subject']}")
        print("  nothing written (--check)")
        return 0

    target.write_text(json.dumps(seed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n  wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
