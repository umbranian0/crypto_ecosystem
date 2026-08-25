"""convert split_results to a TimescaleDB hypertable

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-24 00:00:00.000000

INF-010: convert `validation.split_results` (and no other table) into a
TimescaleDB hypertable, partitioned on `test_start`.

**Partitioning column choice**: `test_start` -- a `DateTime` column already
present on this table per VS-002's schema, representing the split's own
time-series position (the start of the out-of-sample test window). Not
`created_at` (that column doesn't exist on `split_results` -- only `runs`
has it), and not `split_index` (an integer ordinal describing a split's
position *within a run*, not a point in time; TimescaleDB hypertables
partition on a genuine time or integer-range column, and `test_start` is
the column that gives this table its actual time-series meaning, per
solution-design.md section 4's schema).

This is a schema-level performance change only -- no new query surface is
added anywhere in this diff (see docs/tickets/INF-010.md's Design section).
`PostgresSplitResultRepository`'s existing `add_splits`/`get_splits` queries
are unaffected: a hypertable remains queryable via plain SQL exactly like an
ordinary table.

Chained after '0003' (`0003_add_client_baseline_results.py`, VS-017's
`client_baseline_results` column addition, the current head at the time
this migration was authored) rather than '0002' -- Alembic requires a
single linear head, and 0003 already occupied that slot.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Postgres-only, same guard idiom as 0002_add_row_level_security.py:
    `test_models.py::test_alembic_upgrade_head_creates_matching_schema` runs
    `alembic upgrade head` (this migration included) against a real
    `sqlite:///` DATABASE_URL, so this must no-op there, not error.
    """
    if op.get_bind().dialect.name != "postgresql":
        return

    # The `timescale/timescaledb:latest-pg16` image ships the extension's
    # shared library, but the extension itself (its functions, e.g.
    # `create_hypertable`) still has to be created per-database -- it was not
    # yet present on this database before this migration (verified live
    # against the running Compose Postgres container).
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

    # TimescaleDB requires every unique index/primary key on a hypertable to
    # include its partitioning column -- the existing single-column `id`
    # primary key does not, and `create_hypertable` fails outright against it
    # (verified live: "cannot create a unique index without the column
    # ... used in partitioning"). Widening the primary key to (id,
    # test_start) is the standard fix for a surrogate-key table being
    # converted to a hypertable; `id` (a UUID-shaped string minted by the
    # application) remains unique in practice, it's just no longer the sole
    # column Postgres enforces that uniqueness through.
    op.execute("ALTER TABLE validation.split_results DROP CONSTRAINT split_results_pkey")
    op.execute("ALTER TABLE validation.split_results ADD PRIMARY KEY (id, test_start)")

    # `create_hypertable` lives in the `public` schema (where `CREATE
    # EXTENSION` above put it) -- migrations/env.py sets this connection's
    # search_path to `validation` only (not `validation, public`), so the
    # call must be schema-qualified or it resolves to nothing (verified
    # live). `if_not_exists => TRUE` keeps this migration idempotent-safe on
    # re-run; `migrate_data => TRUE` is required because `split_results`
    # already has rows in every environment this migration will actually
    # run against.
    op.execute(
        "SELECT public.create_hypertable("
        "'validation.split_results', 'test_start', "
        "if_not_exists => TRUE, migrate_data => TRUE)"
    )


def downgrade() -> None:
    """Downgrade schema.

    TimescaleDB does not support cleanly converting a hypertable back into a
    plain table (there is no `drop_hypertable`/un-hypertable API) -- the
    documented, deliberate choice here is a no-op with a loud warning rather
    than attempting a destructive rebuild (e.g. CREATE TABLE ... AS SELECT +
    swap), which would risk silent data loss for a step nobody has asked for
    yet. If a real downgrade is ever needed, do it by hand: create a plain
    table, copy the data across, and swap it in -- deliberately not automated
    here.
    """
    if op.get_bind().dialect.name != "postgresql":
        return
    print(
        "WARNING: downgrade of 0004_convert_split_results_to_hypertable is a "
        "no-op -- TimescaleDB does not support un-hypertabling a table. "
        "split_results remains a hypertable partitioned on test_start; the "
        "widened (id, test_start) primary key added by this migration's "
        "upgrade() is also left in place. See this migration's downgrade() "
        "docstring for the manual rebuild procedure if one is ever needed."
    )
