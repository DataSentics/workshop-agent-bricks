"""Create the case search index: an AI Search Delta Sync index over case_notes.

This is the agent's memory of what support has actually done before. Genie can
count cases; only this can find the one that resembles a new problem, because
the resemblance is in the prose and not in any column you could filter on.

Design decisions worth knowing:

  * The embedded column is search_text, which is the subject, the customer's
    report, the resolution and the root cause joined together. Embedding the
    description alone would retrieve on the symptom and lose the fix, and the fix
    is what makes an old case worth reading.
  * Delta Sync rather than Direct Vector Access, because Supervisor Agent only
    supports Delta Sync indexes. That needs Change Data Feed on the source table,
    which the table loader now sets.
  * databricks-qwen3-embedding-0-6b, which Databricks recommends and which is
    also one of the three models a Knowledge Assistant will accept if the index
    is ever reused that way.
  * TRIGGERED sync rather than CONTINUOUS. The data only changes when somebody
    reseeds it, and continuous sync would keep a compute cluster running.

Built with the ordinary Databricks SDK rather than databricks-ai-search, which
wants a personal access token or a service principal secret of its own. Every
other script here authenticates through the CLI profile in the config, and one
auth path is better than two.

Usage:
    uv run workshop/scripts/deploy_search.py --dry-run
    uv run workshop/scripts/deploy_search.py
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dbx  # noqa: E402
from databricks.sdk.errors import BadRequest, NotFound  # noqa: E402

SOURCE_TABLE = "case_notes"
EMBEDDING_MODEL = "databricks-qwen3-embedding-0-6b"
PRIMARY_KEY = "case_id"
EMBED_COLUMN = "search_text"
SYNC_COLUMNS = ["case_id", "client_id", "opened_on", "category", "severity",
                "subject", "resolution_notes", "root_cause"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="print the plan, create nothing")
    ap.add_argument("--profile", help="Databricks CLI profile")
    args = ap.parse_args()

    from databricks.sdk.service.vectorsearch import (
        DeltaSyncVectorIndexSpecRequest, EmbeddingSourceColumn,
        EndpointType, PipelineType, VectorIndexType,
    )

    cfg = dbx.load_config()
    catalog = cfg["unity_catalog"]["catalog"]
    schema = dbx.schema_of(cfg, cfg["ai_search"]["schema"])
    endpoint = cfg["ai_search"]["endpoint"]
    index_name = f"{catalog}.{schema}.{cfg['ai_search']['index']}"
    source = dbx.fq_table(cfg, SOURCE_TABLE)

    print(f"endpoint   {endpoint}")
    print(f"index      {index_name}")
    print(f"source     {source}")
    print(f"embeds     {EMBED_COLUMN} using {EMBEDDING_MODEL}")

    if args.dry_run:
        print("\nnothing created (--dry-run)")
        return 0

    w = dbx.workspace(cfg, args.profile)

    names = {e.name for e in (w.vector_search_endpoints.list_endpoints() or [])}
    if endpoint in names:
        print(f"\nendpoint {endpoint} already exists")
    else:
        print(f"\ncreating endpoint {endpoint}, this takes a few minutes")
        w.vector_search_endpoints.create_endpoint_and_wait(
            name=endpoint, endpoint_type=EndpointType.STANDARD, timeout=timedelta(minutes=40))
    state = w.vector_search_endpoints.get_endpoint(endpoint).endpoint_status.state
    print(f"endpoint state {state.value if state else '?'}")

    fresh = False
    try:
        w.vector_search_indexes.get_index(index_name)
        print(f"index {index_name} already exists")
    except NotFound:
        fresh = True
        print(f"creating index {index_name}")
        w.vector_search_indexes.create_index(
            name=index_name,
            endpoint_name=endpoint,
            primary_key=PRIMARY_KEY,
            index_type=VectorIndexType.DELTA_SYNC,
            delta_sync_index_spec=DeltaSyncVectorIndexSpecRequest(
                source_table=source,
                pipeline_type=PipelineType.TRIGGERED,
                columns_to_sync=SYNC_COLUMNS,
                embedding_source_columns=[EmbeddingSourceColumn(
                    name=EMBED_COLUMN,
                    embedding_model_endpoint_name=EMBEDDING_MODEL)],
            ),
        )

    # A newly created Delta Sync index performs its first sync on its own, and
    # asking it to sync while it is still provisioning is rejected. So wait for
    # it to become ready first, and only trigger a sync when the index already
    # existed and the underlying data has moved on since.
    print("waiting for the index to build")
    deadline = time.time() + 30 * 60
    last = None
    ready = False
    while time.time() < deadline:
        st = w.vector_search_indexes.get_index(index_name).status
        msg = (st.message if st else None) or "provisioning"
        if msg != last:
            print(f"    {msg}")
            last = msg
        if st and st.ready:
            ready = True
            break
        time.sleep(20)

    if not ready:
        print("    still building; it will finish on its own")
        return 0

    if not fresh:
        # An index can report ready while its pipeline is still setting up, and a
        # sync in that window is refused. Nothing is wrong when that happens - the
        # initial load has already populated it - so say so and carry on.
        try:
            w.vector_search_indexes.sync_index(index_name)
            print("sync triggered")
        except BadRequest as exc:
            print(f"sync not needed yet: {str(exc).split('.')[0]}")

    st = w.vector_search_indexes.get_index(index_name).status
    print(f"\nindex ready, {st.indexed_row_count} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
