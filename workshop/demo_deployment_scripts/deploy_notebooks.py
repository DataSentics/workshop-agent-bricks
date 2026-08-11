"""Publish the workshop notebooks to a shared folder everyone can run.

Notebooks go to /Shared so attendees do not have to clone anything, and the
folder is granted to the workspace `users` group rather than to people one at a
time.

Two details that decide whether this actually works on the day:

Dependencies are pinned, and the only thing anybody maintains is
notebooks/pyproject.toml with its uv.lock. Databricks' %pip cannot read a
lockfile, so the exact versions are exported out of it at publish time and
uploaded beside the notebooks as requirements.txt - a build artefact, not a file
to edit, and not in git. The alternative, `%pip install --upgrade`, is how a
notebook that worked in rehearsal breaks in front of a room.

And --run actually runs one, end to end, on serverless. A notebook that imports
cleanly on a laptop can still fail in the workspace - different Python, no local
profile, a library that resolves differently - and the only way to know is to
run it there. It asks the supervisor real questions, so it takes a few minutes
and is a check of the whole environment rather than only of the notebook.

Usage:
    uv run workshop/demo_deployment_scripts/deploy_notebooks.py --dry-run
    uv run workshop/demo_deployment_scripts/deploy_notebooks.py
    uv run workshop/demo_deployment_scripts/deploy_notebooks.py --run
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dbx  # noqa: E402

NOTEBOOK_DIR = dbx.REPO_ROOT / "workshop" / "notebooks"


def local_notebooks() -> list[Path]:
    return sorted(p for p in NOTEBOOK_DIR.glob("*.py") if p.is_file())


def export_pins() -> str:
    """The locked versions, as a requirements file the notebook can install.

    Read out of uv.lock rather than kept alongside it: two files saying the same
    thing is one file too many, and the one nobody regenerates is the one that
    goes stale.
    """
    import subprocess

    result = subprocess.run(
        ["uv", "export", "--frozen", "--no-hashes", "--no-emit-project",
         "--no-annotate", "--quiet"],
        cwd=NOTEBOOK_DIR, capture_output=True, text=True, check=True,
    )
    lines = [ln for ln in result.stdout.splitlines()
             if ln.strip() and not ln.lstrip().startswith("#")]
    header = ("# Generated from pyproject.toml and uv.lock by deploy_notebooks.py.\n"
              "# Do not edit; edit pyproject.toml and re-run `make deploy/notebooks`.\n")
    return header + "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="list what would be published")
    ap.add_argument("--run", action="store_true",
                    help="after publishing, run a notebook on serverless to prove it works")
    ap.add_argument("--profile", help="Databricks CLI profile")
    args = ap.parse_args()

    cfg = dbx.load_config()
    folder = cfg["notebooks"]["folder"]
    group = cfg["notebooks"]["grant_to"]
    files = local_notebooks()
    pins = export_pins()

    print(f"{folder}   (granted to '{group}')")
    for path in files:
        print(f"  {path.name:<28} {path.stat().st_size // 1024 or 1} KB")
    print(f"  requirements.txt             {len(pins.splitlines()) - 2} pinned packages "
          f"(from pyproject.toml + uv.lock)")

    if args.dry_run:
        print("\nnothing published (--dry-run)")
        return 0

    import io

    from databricks.sdk.service.iam import PermissionLevel
    from databricks.sdk.service.workspace import ImportFormat, Language, WorkspaceObjectAccessControlRequest

    w = dbx.workspace(cfg, args.profile)
    w.workspace.mkdirs(folder)

    for path in files:
        # SOURCE format keeps the `# COMMAND ----------` cell markers, so the file
        # in git and the notebook in the workspace are the same thing.
        w.workspace.upload(f"{folder}/{path.stem}", io.BytesIO(path.read_bytes()),
                           format=ImportFormat.SOURCE, language=Language.PYTHON,
                           overwrite=True)
        print(f"  published {folder}/{path.stem}")

    w.workspace.upload(f"{folder}/requirements.txt", io.BytesIO(pins.encode("utf-8")),
                       format=ImportFormat.AUTO, overwrite=True)
    print(f"  published {folder}/requirements.txt")

    obj = w.workspace.get_status(folder)
    w.workspace.set_permissions(
        workspace_object_type="directories",
        workspace_object_id=str(obj.object_id),
        access_control_list=[
            WorkspaceObjectAccessControlRequest(
                group_name=group, permission_level=PermissionLevel.CAN_RUN),
        ],
    )
    print(f"\n  granted CAN_RUN on {folder} to '{group}'")

    if not args.run:
        print(f"\n  {w.config.host.rstrip('/')}/#workspace{folder}")
        return 0

    return verify_run(w, cfg, folder)


def verify_run(w, cfg: dict, folder: str) -> int:
    """Run a notebook on serverless and report whether it succeeded.

    Uses a one-off submitted run rather than a saved job, so nothing is left
    behind in the workspace for somebody to wonder about later.
    """
    from databricks.sdk.service.compute import Environment
    from databricks.sdk.service.jobs import JobEnvironment, NotebookTask, SubmitTask

    notebook = f"{folder}/{cfg['notebooks']['verify_with']}"
    print(f"\n  running {notebook} on serverless")

    # Pin the serverless environment version. Left unpinned, a submitted run can
    # land on an old default - one measured here was Python 3.10 with no uv on it -
    # so the check would be exercising something no attendee will ever see.
    version = str(cfg["notebooks"]["serverless_env_version"])
    run = w.jobs.submit(
        run_name="agent-bricks-ws notebook check",
        environments=[
            JobEnvironment(environment_key="workshop",
                           spec=Environment(environment_version=version)),
        ],
        tasks=[
            SubmitTask(
                task_key="verify",
                environment_key="workshop",
                notebook_task=NotebookTask(notebook_path=notebook),
                timeout_seconds=1800,
            ),
        ],
    )
    print(f"  serverless environment version {version}")
    print(f"  run {run.run_id}: {w.config.host.rstrip('/')}/jobs/runs/{run.run_id}")

    deadline = time.time() + 1800
    state = None
    while time.time() < deadline:
        info = w.jobs.get_run(run_id=run.run_id)
        state = info.state
        life = getattr(state, "life_cycle_state", None)
        if life and str(life).endswith(("TERMINATED", "SKIPPED", "INTERNAL_ERROR")):
            break
        time.sleep(20)

    result = getattr(state, "result_state", None)
    message = getattr(state, "state_message", "") or ""
    print(f"  result: {result}  {message[:200]}")
    return 0 if result and str(result).endswith("SUCCESS") else 1


if __name__ == "__main__":
    sys.exit(main())
