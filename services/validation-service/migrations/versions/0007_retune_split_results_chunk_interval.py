"""retune split_results chunk_time_interval to 90 days

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-02 00:00:00.000000

VS-027 (the validation-service half of DBOPT-004; see INGEST-016 for the
ingestion-service half): `0004_convert_split_results_to_hypertable.py`'s
`create_hypertable` call omitted `chunk_time_interval`, so
`validation.split_results` uses TimescaleDB's 7-day default. DBA-verified
live via `timescaledb_information.chunks`/`.dimensions`: 108 chunks, 7-day
interval, spanning 1970-01-01 -> 2026-08-06, 552 rows total -- an average of
~5 rows per chunk, far below TimescaleDB's own sizing guidance. This is a
real, measured contributor to VS-026's own 130ms planning-time finding --
most of that time is the planner walking all 108 chunks to build the
`Append` plan, not real work. This migration retunes the interval to 90
days.

**Binding, forward-only-effect caveat (do not contradict elsewhere in this
repo's docs/code)**: `set_chunk_time_interval` only changes the interval
used for chunks created *after* this call. It does not retroactively resize
or merge any existing chunk. The 108 existing chunks are unchanged in count
and boundaries immediately after this migration runs -- only chunks created
from this point forward will span 90 days instead of 7.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0007'
down_revision: Union[str, Sequence[str], None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_INTERVAL = "90 days"
_OLD_INTERVAL = "7 days"


def upgrade() -> None:
    """Upgrade schema.

    Postgres-only, same guard idiom as 0004_convert_split_results_to_
    hypertable.py/0006_add_split_results_tenant_run_index.py:
    `test_models.py::test_alembic_upgrade_head_creates_matching_schema` runs
    `alembic upgrade head` (this migration included) against a real
    `sqlite:///` DATABASE_URL, so this must no-op there, not error.

    Sets `validation.split_results`' chunk_time_interval to 90 days --
    forward-only effect, see this file's module docstring: pre-existing
    chunks (and their counts/boundaries) are untouched.
    """
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        f"SELECT public.set_chunk_time_interval("
        f"'validation.split_results', INTERVAL '{_NEW_INTERVAL}')"
    )


def downgrade() -> None:
    """Downgrade schema.

    Reverts `validation.split_results`' chunk_time_interval to
    TimescaleDB's original 7-day default. Same forward-only-effect caveat
    applies in reverse: this only changes the interval used for chunks
    created after this call runs -- any 90-day chunks already created by
    upgrade() are not retroactively resized or merged back down to 7 days.
    """
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        f"SELECT public.set_chunk_time_interval("
        f"'validation.split_results', INTERVAL '{_OLD_INTERVAL}')"
    )