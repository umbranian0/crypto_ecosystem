"""add crawl_runs.rows_fetched_so_far / updated_at progress columns

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-03 00:00:00.000000

INGEST-024 (`docs/product/backlog-crawl-lifecycle-control.md`): adds two
nullable columns to `crawl_runs` supporting mid-fetch progress reporting and
cancellation. Additive, backward-compatible -- no existing column
removed/renamed, no backfill needed for pre-existing rows, same precedent as
INGEST-016/017/018's own additive migrations.

`rows_fetched_so_far` (nullable int): the running row count reported by
`ConnectorRecordRepository.record_crawl_progress`, which UPDATEs the most
recent `status="running"` row in place rather than inserting a new row per
checkpoint -- see `postgres_repository.py`'s own docstring for why (bounded
table growth regardless of fetch granularity).

`updated_at` (nullable timestamp): a new "last touched" field, separate from
`fetched_at`'s existing meaning/ordering role (`latest_crawl_run`'s `ORDER BY
fetched_at DESC` is unchanged by this migration).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0008'
down_revision: Union[str, Sequence[str], None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Postgres-only, same guard idiom as every other migration in this service.
    Plain additive `ADD COLUMN`s on a non-hypertable table (`crawl_runs` has
    no partitioning column), so no `ALTER TABLE` restrictions apply here.
    """
    if op.get_bind().dialect.name != "postgresql":
        return
    op.add_column(
        "crawl_runs",
        sa.Column("rows_fetched_so_far", sa.Integer(), nullable=True),
        schema="ingestion",
    )
    op.add_column(
        "crawl_runs",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        schema="ingestion",
    )


def downgrade() -> None:
    """Downgrade schema."""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.drop_column("crawl_runs", "updated_at", schema="ingestion")
    op.drop_column("crawl_runs", "rows_fetched_so_far", schema="ingestion")
