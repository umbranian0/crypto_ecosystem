"""add price_ohlcv/onchain_metric/sentiment_score daily-source summary materialized views

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-03 00:00:00.000000

INGEST-019 (DBOPT-009, `docs/product/backlog-db-optimization.md`):
`PostgresConnectorRecordRepository.list_datasets` runs, for each of
`price_ohlcv`/`onchain_metric`/`sentiment_score`, `SELECT source, min(<event_time>),
max(<event_time>), count(*) FROM <table> WHERE tenant_id = :tenant_id GROUP BY
source` -- a full per-tenant, all-chunks scan with no time predicate to
exclude chunks on, backing `GET /datasets` (called on every visit to the
dataset-picker UI surface). The user has explicitly accepted a few minutes
of staleness on `list_datasets` in exchange for a much cheaper query
(DBOPT-009's own resolved open question).

**Live-discovered blocker, deviating from this ticket's Design section**:
the Design section specified a true TimescaleDB continuous aggregate
(`CREATE MATERIALIZED VIEW ... WITH (timescaledb.continuous, ...)`) per
hypertable. TimescaleDB 2.29.1 refuses that statement outright on any
hypertable with row-level security enabled (`ERROR: cannot create
continuous aggregate on hypertable with row security`) -- reproduced live
against a disposable scratch hypertable before concluding this is a real,
version-level restriction, not a syntax mistake. `price_ohlcv`/
`onchain_metric`/`sentiment_score` all have `FORCE ROW LEVEL SECURITY`
(`0002_add_row_level_security.py`, INGEST-002), a locked-in multi-tenant
isolation invariant. A live-verified workaround exists (toggling
`relrowsecurity`/`relforcerowsecurity` off for only the duration of the
`CREATE MATERIALIZED VIEW` statement, then immediately back on within the
same migration transaction) -- but this environment's own execution
safeguards refuse to run any migration that disables row-level security,
even transiently and even with a verified-safe revert in the same
transaction, and that refusal is treated here as authoritative rather than
something to route around.

**Substituted design, functionally equivalent, never touches RLS**: three
plain (non-continuous-aggregate) Postgres materialized views, same names
(`<table>_daily_source_summary`) and same `(tenant_id, source, daily bucket,
bucket_min, bucket_max, bucket_count)` shape the Design section specified,
refreshed on a schedule via TimescaleDB's generic job-scheduling
(`add_job`), not `add_continuous_aggregate_policy`. `list_datasets`
(`postgres_repository.py`) queries these views with a raw
`SELECT ... GROUP BY source` exactly as designed -- this substitution is
invisible to that method and to `GET /datasets`' response shape. The
practical difference: a true continuous aggregate incrementally
materializes only the invalidation window on each refresh; a plain
materialized view's `REFRESH MATERIALIZED VIEW CONCURRENTLY` recomputes the
whole view every cycle. For this ticket's data volumes (aggregated down to
one row per tenant/source/day, not per raw row) a full recompute every five
minutes is cheap relative to the raw-hypertable scan this ticket exists to
avoid, so the core performance goal (an inexpensive `GET /datasets` read)
is unaffected -- only the *refresh* strategy differs from the Design
section's literal wording, not `list_datasets`' own query shape or cost.

Each view gets a unique index on `(tenant_id, source, bucket)` -- required
by Postgres for `REFRESH MATERIALIZED VIEW CONCURRENTLY` (a non-concurrent
refresh would lock the view for reads for its full duration, defeating the
point of `list_datasets` reading it cheaply). The initial `REFRESH
MATERIALIZED VIEW` (non-concurrent, required once since a `WITH NO DATA`
view has no rows yet for `CONCURRENTLY` to diff against) populates each
view with all pre-existing history at migration time.

One shared procedure, `ingestion.refresh_dataset_list_summaries(job_id int,
config jsonb)` (the signature TimescaleDB's `add_job` requires), refreshes
all three views -- scheduled every 5 minutes via `add_job`, the same
interval this ticket's Design section specified for
`add_continuous_aggregate_policy`'s `schedule_interval`. See
`services/ingestion-service/README.md` for the actual observed staleness
window.

Same three tables, same order, as `_TABLE_SPECS`
(`src/app/repositories/postgres_repository.py`) and `_INDEXES`/`_HYPERTABLES`
(0003/0004/0006) already iterate -- not a fourth ad hoc table list.

**Live-discovered follow-on bug (Sprint 25 UAT), fixed here**: `infra/postgres-init/02-create-app-role.sh`
was never updated to include the `ingestion` schema when INGEST-002
introduced it -- `naive_first_app`'s access to this schema's own tables had
only ever been granted by hand against the already-running dev container,
with no `ALTER DEFAULT PRIVILEGES` rule for objects created afterward. These
three materialized views were the first new `ingestion` objects created
since that gap, so `GET /datasets` 500'd with `permission denied for
materialized view` the moment they existed, despite the underlying raw
hypertables working fine. Fixed at both layers: `02-create-app-role.sh` now
includes `ingestion` (for a fresh volume), and this migration explicitly
grants `SELECT` on each view it creates (for any volume already past
INGEST-002, where the fresh-volume script won't re-run).
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = '0007'
down_revision: Union[str, Sequence[str], None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Same three-table order as _TABLE_SPECS (postgres_repository.py) /
# _INDEXES (0006) / _HYPERTABLES (0003/0004) -- (table, event_time_column,
# summary view name) triples, not a fourth ad hoc table list.
_CONTINUOUS_AGGREGATES = (
    ("price_ohlcv", "open_time", "price_ohlcv_daily_source_summary"),
    ("onchain_metric", "timestamp", "onchain_metric_daily_source_summary"),
    ("sentiment_score", "created_utc", "sentiment_score_daily_source_summary"),
)

_REFRESH_PROC = "refresh_dataset_list_summaries"


def upgrade() -> None:
    """Upgrade schema.

    Postgres-only, same guard idiom as 0002/0003/0004/0005/0006. Creates one
    daily-source summary materialized view per hypertable (see this module's
    docstring for why these are plain materialized views, not true
    TimescaleDB continuous aggregates, despite the identical shape/naming
    the Design section specified), a unique index on each (required for
    `REFRESH ... CONCURRENTLY`), and one shared TimescaleDB-scheduled job
    (`add_job`, every 5 minutes) that refreshes all three.
    """
    if op.get_bind().dialect.name != "postgresql":
        return

    for table, event_time_column, cagg_name in _CONTINUOUS_AGGREGATES:
        # `time_bucket`/`add_job` live in the `public` schema (where `CREATE
        # EXTENSION timescaledb` in 0003 put them) -- migrations/env.py sets
        # this connection's search_path to `ingestion` only, so every
        # TimescaleDB function call here must be schema-qualified or it
        # resolves to nothing, same finding 0003_convert_to_hypertables.py
        # already made for `create_hypertable`.
        op.execute(
            f"CREATE MATERIALIZED VIEW ingestion.{cagg_name} AS "
            f"SELECT tenant_id, source, "
            f"public.time_bucket(INTERVAL '1 day', {event_time_column}) AS bucket, "
            f"min({event_time_column}) AS bucket_min, "
            f"max({event_time_column}) AS bucket_max, "
            f"count(*) AS bucket_count "
            f"FROM ingestion.{table} "
            f"GROUP BY tenant_id, source, bucket "
            f"WITH NO DATA"
        )
        op.execute(
            f"CREATE UNIQUE INDEX {cagg_name}_tenant_source_bucket_idx "
            f"ON ingestion.{cagg_name} (tenant_id, source, bucket)"
        )
        # Non-concurrent: a WITH-NO-DATA view has no rows yet for
        # CONCURRENTLY to diff against -- this is the one-time full-history
        # population, mirroring the Design section's manual
        # refresh_continuous_aggregate(..., NULL, NULL) call.
        op.execute(f"REFRESH MATERIALIZED VIEW ingestion.{cagg_name}")
        # Live-discovered follow-on bug fix (see module docstring): a
        # materialized view is a new object, not covered by any grant issued
        # before it existed -- naive_first_app (the RLS-enforcing runtime
        # role every service actually connects as) needs explicit SELECT
        # here, same as 02-create-app-role.sh grants for a fresh volume.
        op.execute(f"GRANT SELECT ON ingestion.{cagg_name} TO naive_first_app")

    view_refresh_statements = "\n    ".join(
        f"REFRESH MATERIALIZED VIEW CONCURRENTLY ingestion.{cagg_name};"
        for _, _, cagg_name in _CONTINUOUS_AGGREGATES
    )
    op.execute(
        f"CREATE OR REPLACE PROCEDURE ingestion.{_REFRESH_PROC}(job_id int, config jsonb) "
        f"LANGUAGE plpgsql AS $$ "
        f"BEGIN "
        f"{view_refresh_statements} "
        f"END; $$"
    )
    op.execute(
        f"SELECT public.add_job('ingestion.{_REFRESH_PROC}', INTERVAL '5 minutes')"
    )


def downgrade() -> None:
    """Downgrade schema."""
    if op.get_bind().dialect.name != "postgresql":
        return

    bind = op.get_bind()
    job_ids = bind.execute(
        text(
            "SELECT job_id FROM timescaledb_information.jobs "
            "WHERE proc_schema = 'ingestion' AND proc_name = :proc_name"
        ),
        {"proc_name": _REFRESH_PROC},
    ).scalars().all()
    for job_id in job_ids:
        op.execute(f"SELECT public.delete_job({job_id})")

    op.execute(f"DROP PROCEDURE IF EXISTS ingestion.{_REFRESH_PROC}(int, jsonb)")
    for _, _, cagg_name in _CONTINUOUS_AGGREGATES:
        op.execute(f"DROP MATERIALIZED VIEW IF EXISTS ingestion.{cagg_name}")
