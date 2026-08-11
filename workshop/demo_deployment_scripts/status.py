"""Show what is currently deployed to the workspace named in databricks-config.yaml."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dbx  # noqa: E402
from dbx import load_config  # noqa: E402


def walk(w, path: str) -> list[str]:
    out: list[str] = []
    for entry in w.files.list_directory_contents(path):
        if entry.is_directory:
            out.extend(walk(w, entry.path))
        else:
            out.append(entry.path)
    return out


def main() -> int:
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.errors import NotFound

    cfg = load_config()
    catalog = cfg["unity_catalog"]["catalog"]
    w = WorkspaceClient(profile=cfg["profile"])

    for label in cfg["volumes"]:
        root = dbx.volume_path(cfg, label)
        print(f"== {label}: {root}")
        try:
            files = sorted(walk(w, root))
        except NotFound:
            print("   not created yet\n")
            continue
        for f in files:
            print(f"   {f[len(root) + 1:]}")
        print(f"   {len(files)} file(s)\n")

    for key, names in cfg["tables"].items():
        print(f"== tables in {dbx.schema_of(cfg, key)}")
        for table in names:
            try:
                r = dbx.sql(w, cfg["warehouse_id"],
                            f"SELECT count(*) FROM {dbx.fq_table(cfg, table)}")
                print(f"   {table:<28} {r.result.data_array[0][0]:>8} rows")
            except Exception:
                print(f"   {table:<28} {'not loaded':>8}")
        print()

    print("== genie agents")
    for s in (w.genie.list_spaces().spaces or []):
        if s.title and s.title.startswith("Saldo"):
            print(f"   {s.space_id}  {s.title}")
    print()

    print("== apps")
    # The prefix is not cosmetic: Databricks only recognises an app as an MCP
    # server if it starts with mcp-, and as a custom agent if it starts with agent-.
    mine = {a["name"] for a in cfg["apps"].values()}
    for app in w.apps.list():
        if not app.name.startswith(("mcp-", "agent-")):
            continue
        state = app.compute_status.state.value if app.compute_status else "?"
        kind = "MCP server" if app.name.startswith("mcp-") else "agent"
        tag = " <-- workshop" if app.name in mine else ""
        print(f"   {app.name:<28} {kind:<11} {state:<10} {app.url}{tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
