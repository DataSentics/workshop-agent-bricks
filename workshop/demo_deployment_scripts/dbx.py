"""Shared Databricks helpers for the workshop seed scripts.

Loading path for tables: write Parquet locally, upload it to a staging area in a
volume, then CREATE OR REPLACE TABLE from it. Parquet rather than CSV so column
types survive the round trip instead of being guessed.

Table and column comments are written as part of the load. Genie leans on them
heavily, and a column called `reason_code` means nothing to it without one.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "databricks-config.yaml"


def load_config() -> dict:
    import yaml

    with CONFIG_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def schema_of(cfg: dict, key: str) -> str:
    """Resolve a schema key like 'ops' to its actual schema name."""
    return cfg["unity_catalog"]["schemas"][key]


def table_schema(cfg: dict, table: str) -> str:
    """Which schema a table belongs in, from the config's table grouping."""
    for key, names in cfg["tables"].items():
        if table in names:
            return schema_of(cfg, key)
    raise KeyError(f"{table} is not listed under tables: in databricks-config.yaml")


def fq_table(cfg: dict, table: str) -> str:
    return f"{cfg['unity_catalog']['catalog']}.{table_schema(cfg, table)}.{table}"


def all_tables(cfg: dict) -> list[str]:
    return [t for names in cfg["tables"].values() for t in names]


def fq_view(cfg: dict, view: str) -> str:
    for key, names in cfg.get("views", {}).items():
        if view in names:
            return f"{cfg['unity_catalog']['catalog']}.{schema_of(cfg, key)}.{view}"
    raise KeyError(f"{view} is not listed under views: in databricks-config.yaml")


def all_views(cfg: dict) -> list[str]:
    return [v for names in cfg.get("views", {}).values() for v in names]


def qualified_function(cfg: dict, name: str) -> str:
    """The three-part name of a UC function listed under functions: in the config."""
    for key, names in cfg.get("functions", {}).items():
        if name in names:
            return f"{cfg['unity_catalog']['catalog']}.{schema_of(cfg, key)}.{name}"
    raise KeyError(f"{name} is not listed under functions: in databricks-config.yaml")


def sql_string(value: str) -> str:
    """A SQL string literal. Doubling the quote is the only escape Databricks needs."""
    return "'" + value.replace("'", "''") + "'"


def volume_path(cfg: dict, key: str) -> str:
    """The /Volumes path for a configured volume."""
    v = cfg["volumes"][key]
    return f"/Volumes/{cfg['unity_catalog']['catalog']}/{schema_of(cfg, v['schema'])}/{v['name']}"


def ensure_schemas(w, cfg: dict) -> None:
    """Create the workshop schemas if they are missing.

    An existing schema comes back as BadRequest rather than ResourceAlreadyExists,
    so both have to be treated as success.
    """
    from databricks.sdk.errors import BadRequest, ResourceAlreadyExists

    for key, name in cfg["unity_catalog"]["schemas"].items():
        try:
            w.schemas.create(name=name, catalog_name=cfg["unity_catalog"]["catalog"],
                             comment=f"Agent Bricks workshop, Saldo demo: {key}.")
            print(f"created schema {name}")
        except (ResourceAlreadyExists, BadRequest) as exc:
            if "already exists" not in str(exc):
                raise


def data_dir(cfg: dict) -> Path:
    return REPO_ROOT / cfg["data"]["dir"]


def data_subdir(cfg: dict, key: str) -> Path:
    """The folder holding one destination's files: payroll, platform, docs, outlook."""
    return data_dir(cfg) / cfg["data"]["dirs"][key]


def data_file(cfg: dict, key: str) -> Path:
    """Path to a committed data file, as named in the config."""
    return data_dir(cfg) / cfg["data"]["files"][key]


def workspace(cfg: dict, profile: str | None = None):
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient(profile=profile or cfg["profile"])


def ensure_volume(w, cfg: dict, key: str, comment: str = "") -> str:
    """Create a configured volume if it is missing. Returns its /Volumes path."""
    from databricks.sdk.errors import ResourceAlreadyExists
    from databricks.sdk.service.catalog import VolumeType

    v = cfg["volumes"][key]
    try:
        w.volumes.create(
            catalog_name=cfg["unity_catalog"]["catalog"],
            schema_name=schema_of(cfg, v["schema"]),
            name=v["name"],
            volume_type=VolumeType.MANAGED,
            comment=comment,
        )
    except ResourceAlreadyExists:
        pass
    return volume_path(cfg, key)


def sql(w, warehouse_id: str, statement: str) -> Any:
    """Run one SQL statement and raise with the statement text if it fails."""
    from databricks.sdk.service.sql import StatementState

    resp = w.statement_execution.execute_statement(
        warehouse_id=warehouse_id,
        statement=statement,
        wait_timeout="50s",
    )
    while resp.status.state in (StatementState.PENDING, StatementState.RUNNING):
        resp = w.statement_execution.get_statement(resp.statement_id)

    if resp.status.state != StatementState.SUCCEEDED:
        error = resp.status.error.message if resp.status.error else "unknown error"
        head = " ".join(statement.split())[:200]
        raise RuntimeError(f"SQL failed: {error}\n  statement: {head}...")
    return resp


def rows_to_parquet(rows: Sequence[dict], columns: Sequence[str]) -> bytes:
    """Serialise rows to Parquet, preserving column order and letting pyarrow
    infer types from the Python values."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    table = pa.table({col: [r.get(col) for r in rows] for col in columns})
    buf = io.BytesIO()
    pq.write_table(table, buf)
    return buf.getvalue()


def load_table(
    w,
    *,
    warehouse_id: str,
    catalog: str,
    schema: str,
    table: str,
    rows: Sequence[dict],
    columns: Sequence[str],
    comment: str,
    column_comments: dict[str, str],
    staging_root: str,
) -> int:
    """Replace a Delta table with these rows, and document it."""
    if not rows:
        raise ValueError(f"{table}: refusing to load zero rows")

    missing = set(column_comments) - set(columns)
    if missing:
        raise ValueError(f"{table}: comments for unknown columns {sorted(missing)}")
    undocumented = set(columns) - set(column_comments)
    if undocumented:
        raise ValueError(f"{table}: columns without a comment {sorted(undocumented)}")

    payload = rows_to_parquet(rows, columns)
    stage_dir = f"{staging_root}/{table}"
    stage_file = f"{stage_dir}/data.parquet"

    # Clear the staging directory so a shrinking dataset cannot leave old parts behind.
    try:
        for entry in w.files.list_directory_contents(stage_dir):
            if not entry.is_directory:
                w.files.delete(entry.path)
    except Exception:
        pass

    w.files.upload(stage_file, io.BytesIO(payload), overwrite=True)

    # Name the columns explicitly: read_files otherwise adds a _rescued_data column,
    # which would show up in Genie as a real field.
    select_list = ", ".join(f"`{c}`" for c in columns)
    fq = f"`{catalog}`.`{schema}`.`{table}`"
    # Change Data Feed is switched on for every table. AI Search will not build a
    # Delta Sync index on a standard endpoint without it, and turning it on later
    # means rebuilding the table anyway.
    sql(w, warehouse_id, f"""
        CREATE OR REPLACE TABLE {fq}
        TBLPROPERTIES (delta.enableChangeDataFeed = true)
        AS SELECT {select_list} FROM read_files('{stage_dir}', format => 'parquet')
    """)
    sql(w, warehouse_id, f"COMMENT ON TABLE {fq} IS {quote(comment)}")
    for col, text in column_comments.items():
        sql(w, warehouse_id, f"ALTER TABLE {fq} ALTER COLUMN `{col}` COMMENT {quote(text)}")

    # The Parquet has been read into the table, so the staged copy is dead weight.
    # Leaving it behind means the staging volume slowly fills with the residue of
    # every table ever loaded, including ones since renamed or dropped.
    try:
        w.files.delete(stage_file)
        w.files.delete_directory(stage_dir)
    except Exception:
        pass

    return len(rows)


def quote(text: str) -> str:
    """SQL string literal."""
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"
