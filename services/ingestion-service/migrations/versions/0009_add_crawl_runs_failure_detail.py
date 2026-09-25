"""add crawl_runs.failure_detail column

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-25 00:00:00.000000

ADMIN-003 (`docs/product/backlog-trust-and-admin-ops.md`): adds one nullable
column to `crawl_runs` so a `"failed"` crawl's row carries a redacted,
readable reason (`connectors.base.describe_crawl_failure`) instead of only
the bare `"failed"` status string. Additive, backward-compatible -- no
existing column removed/renamed, no backfill needed for pre-existing rows,
same precedent as `0008`'s own additive migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0009'
down_revision: Union[str, Sequence[str], None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Postgres-only, same guard idiom as every other migration in this service.
    Plain additive `ADD COLUMN` on a non-hypertable table (`crawl_runs` has
    no partitioning column), so no `ALTER TABLE` restrictions apply here.
    """
    if op.get_bind().dialect.name != "postgresql":
        return
    op.add_column(
        "crawl_runs",
        sa.Column("failure_detail", sa.String(), nullable=True),
        schema="ingestion",
    )


def downgrade() -> None:
    """Downgrade schema."""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.drop_column("crawl_runs", "failure_detail", schema="ingestion")
