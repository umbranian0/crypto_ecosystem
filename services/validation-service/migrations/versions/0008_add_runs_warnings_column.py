"""add runs.warnings column

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-08 00:00:00.000000

DH-001: adds `runs.warnings`, a `nullable=False, server_default='[]'` JSON
column storing any non-fatal, disclosed condition `DatasetSource.load`
produced for that run's dataset load (e.g. the reordering-on-load notice) --
`server_default='[]'` backfills existing rows with an empty list with no
manual data migration step, same "plain ADD COLUMN, portable JSON type"
idiom `0003_add_client_baseline_results.py` already established (SQLAlchemy's
`JSON` type compiles to a native JSON column on Postgres and a
TEXT-serialized-JSON column on SQLite either way, so this migration runs
unchanged against `test_alembic_upgrade_head_creates_matching_schema`'s
sqlite:/// target and a real Postgres `DATABASE_URL`).
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
    """Upgrade schema."""
    op.add_column(
        'runs',
        sa.Column('warnings', sa.JSON(), nullable=False, server_default='[]'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('runs', 'warnings')
