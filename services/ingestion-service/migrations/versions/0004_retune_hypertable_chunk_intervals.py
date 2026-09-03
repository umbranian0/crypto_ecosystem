"""retune price_ohlcv/onchain_metric/sentiment_score chunk_time_interval to 90 days

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-02 00:00:00.000000

INGEST-016 (the ingestion-service half of DBOPT-004; see VS-027 for the
validation-service half): `0003_convert_to_hypertables.py`'s `create_hypertable`
calls omitted `chunk_time_interval`, so all three hypertables use TimescaleDB's
7-day default. Against 9-17 years of real backfilled history that produces
hundreds of undersized chunks (`price_ohlcv`: 472 chunks, ~258 rows/chunk;
`onchain_metric`: 922 chunks, ~21 rows/chunk -- both DBA-verified live via
`timescaledb_information.chunks`/`.dimensions`), which hurts every query
against these tables on chunk-count-driven planning cost, not row-count. This
migration retunes all three to a 90-day interval.

**Binding, forward-only-effect caveat (do not contradict elsewhere in this
repo's docs/code)**: `set_chunk_time_interval` only changes the interval used
for chunks created *after* this call. It does not retroactively resize or
merge any existing chunk. The 472/922 existing chunks on `price_ohlcv`/
`onchain_metric` are unchanged in count and boundaries immediately after this
migration runs -- only chunks created from this point forward (new data,
including ongoing `sentiment_score` ingestion) will span 90 days instead of 7.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Same per-table-iteration shape as 0003_convert_to_hypertables.py's
# _HYPERTABLES tuple, reused here rather than inventing a new shape (this
# migration also acts on all three tables, one call each) -- just the
# interval, not the partitioning column, since set_chunk_time_interval takes
# the hypertable name only.
_HYPERTABLES = ("price_ohlcv", "onchain_metric", "sentiment_score")

_NEW_INTERVAL = "90 days"
_OLD_INTERVAL = "7 days"


def upgrade() -> None:
    """Upgrade schema.

    Postgres-only, same guard idiom as 0002_add_row_level_security.py /
    0003_convert_to_hypertables.py. Sets each hypertable's
    chunk_time_interval to 90 days -- forward-only effect, see this file's
    module docstring: pre-existing chunks (and their counts) are untouched.
    """
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in _HYPERTABLES:
        op.execute(
            f"SELECT public.set_chunk_time_interval("
            f"'ingestion.{table}', INTERVAL '{_NEW_INTERVAL}')"
        )


def downgrade() -> None:
    """Downgrade schema.

    Reverts each hypertable's chunk_time_interval to TimescaleDB's original
    7-day default. Same forward-only-effect caveat applies in reverse: this
    only changes the interval used for chunks created after this call runs --
    any 90-day chunks already created by upgrade() are not retroactively
    resized or merged back down to 7 days.
    """
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in _HYPERTABLES:
        op.execute(
            f"SELECT public.set_chunk_time_interval("
            f"'ingestion.{table}', INTERVAL '{_OLD_INTERVAL}')"
        )
