"""Load the Saldo document set into a Unity Catalog volume.

The documents are the source of truth for the rest of the workshop dataset: the file
specification defines what a valid record looks like, which decides the error codes, which
decides what the log files and support cases can say. Seed these first.

The volume is split at the top level:

    saldo/      Saldo's own documentation. Identical for every customer.
    contracts/  Signed agreements. One per customer.

Knowledge Assistant sources can point at a volume directory, so those two can be registered
as separate sources with their own descriptions.

Dates are not hardcoded. Documents contain {{TOKEN}} placeholders that are resolved relative to
the workshop date, so a demo run months from now still reads as "this happened last week".

Usage:
    uv run workshop/scripts/seed_docs.py                     # anchor on today
    uv run workshop/scripts/seed_docs.py --date 2026-09-15   # anchor on a fixed workshop day
    uv run workshop/scripts/seed_docs.py --dry-run           # render locally, upload nothing
"""

from __future__ import annotations

import argparse
import io
import re
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "databricks-config.yaml"
TOKEN_RE = re.compile(r"\{\{([A-Z0-9_]+)\}\}")


def load_config() -> dict:
    import yaml

    with CONFIG_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def docs_dir(cfg: dict) -> Path:
    """Where the documents live in the repo.

    Read from the config rather than hardcoded, and resolved on demand rather
    than at import: the other generators import build_timeline from this module,
    and a constant computed at import time makes every one of them depend on the
    config being readable just to work out a date.
    """
    return REPO_ROOT / cfg["data"]["dir"] / cfg["data"]["dirs"]["docs"]


@dataclass(frozen=True)
class Timeline:
    """Every date in the workshop hangs off the incident."""

    workshop_day: date
    incident: date          # Alpine Retail's payroll run failed
    release_current: date   # 2026.8 removed the legacy conversion
    release_prev: date      # 2026.7
    release_2026_6: date
    deprecation: date       # 2026.5 announced the removal
    contract_signed: date   # Alpine Retail's subscription agreement
    contract_start: date
    contract_end: date


def build_timeline(workshop_day: date) -> Timeline:
    """Anchor the story: the incident is the most recent Tuesday, the breaking release
    landed in the Saturday maintenance window just before it."""
    days_since_tuesday = (workshop_day.weekday() - 1) % 7 or 7
    incident = workshop_day - timedelta(days=days_since_tuesday)
    release_current = incident - timedelta(days=3)  # the preceding Saturday

    # Alpine has been a customer for a while: signed ~14 months ago, live from the
    # 1st of the following month, on a 36-month term that is still running.
    signed = _months_before(workshop_day, 14)
    start = _first_of_next_month(signed)
    return Timeline(
        workshop_day=workshop_day,
        incident=incident,
        release_current=release_current,
        release_prev=release_current - timedelta(days=28),
        release_2026_6=release_current - timedelta(days=56),
        deprecation=release_current - timedelta(days=84),
        contract_signed=signed,
        contract_start=start,
        contract_end=_months_after(start, 36) - timedelta(days=1),
    )


def _months_before(d: date, months: int) -> date:
    total = d.year * 12 + (d.month - 1) - months
    return date(total // 12, total % 12 + 1, min(d.day, 28))


def _months_after(d: date, months: int) -> date:
    total = d.year * 12 + (d.month - 1) + months
    return date(total // 12, total % 12 + 1, min(d.day, 28))


def _first_of_next_month(d: date) -> date:
    return date(d.year + d.month // 12, d.month % 12 + 1, 1)


def _human(d: date) -> str:
    return f"{d.day} {d:%B %Y}"


def tokens_for(t: Timeline) -> dict[str, str]:
    return {
        "REL_CURRENT_DATE": _human(t.release_current),
        "REL_PREV_DATE": _human(t.release_prev),
        "REL_2026_6_DATE": _human(t.release_2026_6),
        "REL_DEPRECATION_DATE": _human(t.deprecation),
        "INCIDENT_DATE": _human(t.incident),
        "CONTRACT_SIGNED_DATE": _human(t.contract_signed),
        "CONTRACT_START_DATE": _human(t.contract_start),
        "CONTRACT_END_DATE": _human(t.contract_end),
    }


def render(text: str, tokens: dict[str, str], where: str) -> str:
    unknown = {m for m in TOKEN_RE.findall(text) if m not in tokens}
    if unknown:
        raise SystemExit(f"{where}: unknown token(s) {sorted(unknown)}")
    return TOKEN_RE.sub(lambda m: tokens[m.group(1)], text)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", help="workshop date as YYYY-MM-DD (overrides the config)")
    ap.add_argument("--dry-run", action="store_true", help="render only, do not upload")
    ap.add_argument("--profile", help="Databricks CLI profile (overrides the config)")
    args = ap.parse_args()

    cfg = load_config()
    profile = args.profile or cfg["profile"]

    pinned = args.date or cfg.get("workshop", {}).get("date")
    workshop_day = date.fromisoformat(str(pinned)) if pinned else date.today()
    timeline = build_timeline(workshop_day)
    tokens = tokens_for(timeline)

    print(f"Workshop day     {timeline.workshop_day}")
    print(f"Incident         {timeline.incident}  (Alpine Retail payroll run)")
    print(f"Release 2026.8   {timeline.release_current}  (legacy conversion removed)")
    print(f"Release 2026.5   {timeline.deprecation}  (removal announced)")
    print(f"Alpine contract  {timeline.contract_start} to {timeline.contract_end}")
    notice_days = (timeline.release_current - timeline.deprecation).days
    print(f"Notice given     {notice_days} days  (contract requires 60)")
    print()

    root = docs_dir(cfg)
    files = sorted(root.rglob("*.md"))
    if not files:
        raise SystemExit(f"no documents found under {root}")

    rendered: list[tuple[str, bytes]] = []
    for path in files:
        rel = path.relative_to(root).as_posix()
        body = render(path.read_text(encoding="utf-8"), tokens, rel)
        rendered.append((rel, body.encode("utf-8")))

    if args.dry_run:
        for rel, body in rendered:
            print(f"  {rel:<60} {len(body):>6} bytes")
        print(f"\n{len(rendered)} documents rendered, nothing uploaded.")
        return 0

    from databricks.sdk import WorkspaceClient
    from databricks.sdk.errors import ResourceAlreadyExists
    from databricks.sdk.service.catalog import VolumeType

    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent))
    import dbx

    w = WorkspaceClient(profile=profile)
    dbx.ensure_schemas(w, cfg)
    root = dbx.ensure_volume(
        w, cfg, "docs",
        "Saldo product documentation and customer contracts (workshop, synthetic).")
    expected: set[str] = set()
    for rel, body in rendered:
        target = f"{root}/{rel}"
        w.files.upload(target, io.BytesIO(body), overwrite=True)
        expected.add(target)
        print(f"  uploaded {rel:<60} {len(body):>6} bytes")

    # Uploading does not remove anything, so a renamed or deleted document would
    # linger in the volume and be indexed alongside its replacement. Drop whatever
    # is no longer part of the set.
    stale = sorted(set(_walk(w, root)) - expected)
    for path in stale:
        w.files.delete(path)
        print(f"  removed  {path[len(root) + 1:]}")

    # Deleting files leaves the directories behind, so a reorganised tree keeps its
    # old empty folders. Prune them too.
    for path in _prune_empty_dirs(w, root):
        print(f"  pruned   {path[len(root) + 1:]}/")

    print(f"\n{len(rendered)} documents in {root}")
    return 0


def _walk(w, path: str) -> list[str]:
    """Every file under a volume path, recursively."""
    found: list[str] = []
    for entry in w.files.list_directory_contents(path):
        if entry.is_directory:
            found.extend(_walk(w, entry.path))
        else:
            found.append(entry.path)
    return found


def _prune_empty_dirs(w, path: str, *, top: bool = True) -> list[str]:
    """Remove directories that no longer contain any files. Deepest first."""
    removed: list[str] = []
    entries = list(w.files.list_directory_contents(path))
    for entry in entries:
        if entry.is_directory:
            removed.extend(_prune_empty_dirs(w, entry.path, top=False))
    if not top and not list(w.files.list_directory_contents(path)):
        w.files.delete_directory(path)
        removed.append(path)
    return removed


if __name__ == "__main__":
    sys.exit(main())
