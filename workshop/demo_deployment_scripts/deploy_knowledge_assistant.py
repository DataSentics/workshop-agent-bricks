"""Create or update the Knowledge Assistant over the Saldo document volume.

This exists to be compared with something. The supervisor can already reach the
same documents through a volume tool, and the two behave quite differently:

    volume tool          lists the files and reads them at query time. Always
                         current, but the agent has to decide which file to open,
                         which is why an instruction like "first ask for the list
                         of files" ends up in the supervisor's prompt.

    Knowledge Assistant  ingests, chunks and indexes the documents up front, then
                         answers semantically with citations. No file-picking, but
                         it answers from its own snapshot.

That last point is the one that bites. A Knowledge Assistant does not notice that
the volume changed; it keeps answering from the last ingest. So the sync is part
of this script rather than something to remember, and `make deploy/data` runs the
documents first and this immediately after.

Usage:
    uv run workshop/demo_deployment_scripts/deploy_knowledge_assistant.py --dry-run
    uv run workshop/demo_deployment_scripts/deploy_knowledge_assistant.py
    uv run workshop/demo_deployment_scripts/deploy_knowledge_assistant.py --no-wait
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dbx  # noqa: E402

INSTRUCTIONS = """\
You answer questions about Saldo from its published documentation: the service description, the
payroll run guide, the input file specification, the validation error reference, the guide to
managing employee data, the service level agreement, the support policy, the fee schedule, and
the signed customer contracts.

Answer from the documents and say which one you are drawing on. Quote the wording where the
exact phrasing matters, which it usually does for anything in the SLA or a contract.

You are reading published documentation, not the running system. You cannot see a customer's
payroll runs, what was deployed and when, or the state of any support case. If a question needs
those, say plainly that the documents do not carry it and answer the part they do.
"""

EXAMPLES = [
    ("What has to be in the bank account field for an employee?",
     "Answer from the input file specification and the employee data guide. State the rule; do "
     "not speculate about why a particular payment failed."),
    ("When is a customer entitled to a service credit, and how much?",
     "Answer from the service level agreement. Give the availability target for the plan and the "
     "credit table, and say what section 6 excludes."),
    ("What does error VAL-014 mean?",
     "Answer from the validation error reference: the message, which category it falls in, and "
     "the stated resolution."),
    ("How much notice does Alpine Retail get before a change that needs them to act?",
     "Answer from Alpine Retail's subscription agreement and quote the notice period."),
]


def find(w, display_name: str):
    for a in w.knowledge_assistants.list_knowledge_assistants():
        if a.display_name == display_name:
            return a
    return None


def wait_until_ready(w, name: str, timeout: float = 900.0) -> str:
    """Poll until every source has finished ingesting.

    Ingestion is asynchronous and a Knowledge Assistant answers "I could not find
    that" rather than erroring while it is still working, so a deploy that
    returns before this finishes looks successful and demos badly.
    """
    from databricks.sdk.service.knowledgeassistants import KnowledgeSourceState

    deadline = time.time() + timeout
    while time.time() < deadline:
        states = [s.state for s in w.knowledge_assistants.list_knowledge_sources(parent=name)]
        if states and all(s == KnowledgeSourceState.UPDATED for s in states):
            return "UPDATED"
        if any(s == KnowledgeSourceState.FAILED_UPDATE for s in states):
            return "FAILED_UPDATE"
        time.sleep(15)
    return "TIMED_OUT"


def register_examples(w, name: str) -> None:
    """Seed the question/guideline pairs, skipping any that are already there."""
    from databricks.sdk.service.knowledgeassistants import Example

    have = {e.question for e in w.knowledge_assistants.list_examples(parent=name)}
    added = 0
    for question, guidelines in EXAMPLES:
        if question not in have:
            w.knowledge_assistants.create_example(
                parent=name,
                example=Example(question=question, guidelines=guidelines),
            )
            added += 1
    print(f"  examples: {added} added, {len(EXAMPLES) - added} already present")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="print what would be created")
    ap.add_argument("--no-wait", action="store_true", help="trigger the sync but do not wait")
    ap.add_argument("--profile", help="Databricks CLI profile")
    args = ap.parse_args()

    cfg = dbx.load_config()
    spec = cfg["knowledge_assistant"]
    # A trailing slash: the source is the directory, not a file with that name.
    source_path = dbx.volume_path(cfg, spec["volume"]) + "/"

    print(f"{spec['name']}")
    print(f"  source  {source_path}")
    print(f"  {len(EXAMPLES)} example question(s)")

    if args.dry_run:
        print("\n" + INSTRUCTIONS)
        print("nothing created (--dry-run)")
        return 0

    from databricks.sdk.common.types.fieldmask import FieldMask
    from databricks.sdk.service.knowledgeassistants import (
        FilesSpec,
        KnowledgeAssistant,
        KnowledgeSource,
    )

    w = dbx.workspace(cfg, args.profile)
    existing = find(w, spec["name"])

    if existing is None:
        created = w.knowledge_assistants.create_knowledge_assistant(
            knowledge_assistant=KnowledgeAssistant(
                display_name=spec["name"],
                description=spec["description"],
                instructions=INSTRUCTIONS.strip(),
            ),
        )
        name = created.name
        print(f"\n  created {name}")
    else:
        name = existing.name
        w.knowledge_assistants.update_knowledge_assistant(
            name=name,
            knowledge_assistant=KnowledgeAssistant(
                display_name=spec["name"],
                description=spec["description"],
                instructions=INSTRUCTIONS.strip(),
            ),
            # A FieldMask, not a string: the SDK calls ToJsonString on it.
            update_mask=FieldMask(["description", "instructions"]),
        )
        print(f"\n  updated {name}")

    # One source per volume path. Adding it twice would ingest the documents
    # twice and answer from both copies.
    sources = {s.files.path: s for s in w.knowledge_assistants.list_knowledge_sources(parent=name)
               if s.files}
    if source_path not in sources:
        w.knowledge_assistants.create_knowledge_source(
            parent=name,
            knowledge_source=KnowledgeSource(
                display_name="Saldo documentation",
                description=(
                    "Saldo's published product and policy documentation, and the signed "
                    "customer contracts. What the company says about itself in writing."
                ),
                source_type="files",
                files=FilesSpec(path=source_path),
            ),
        )
        print(f"  added source {source_path}")
    else:
        print(f"  source already registered")

    w.knowledge_assistants.sync_knowledge_sources(name=name)
    print("  sync triggered")

    if args.no_wait:
        print("\n  not waiting (--no-wait). It answers 'not found' until ingestion finishes.")
        return 0

    print("  waiting for ingestion", end="", flush=True)
    state = wait_until_ready(w, name)
    print(f"\n  sources: {state}")

    # Examples go on last. The endpoint that lists them blocks while the
    # assistant is still being provisioned, long enough for the SDK to give up,
    # and they are a refinement rather than something the assistant needs to
    # answer - so a failure here should not fail the deploy.
    try:
        register_examples(w, name)
    except Exception as exc:  # noqa: BLE001
        print(f"  examples not registered ({type(exc).__name__}); rerun to add them")

    final = w.knowledge_assistants.get_knowledge_assistant(name=name)
    print(f"  state:    {final.state}")
    print(f"  endpoint: {final.endpoint_name}")
    if final.error_info:
        print(f"  error:    {final.error_info}")
    return 0 if state == "UPDATED" else 1


if __name__ == "__main__":
    sys.exit(main())
