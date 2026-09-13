"""add runs.feature_lineage column

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-13 00:00:00.000000

VS-030 (MDF-003): adds `runs.feature_lineage`, a `nullable=False,
server_default='[]'` JSON column storing `{"source", "field", "lag_hours"}`
per feature reference that composed a multi-source run's assembled feature
table -- `[]` for a single-series run. `server_default='[]'` backfills
existing rows with an empty list with no manual data migration step, same
"plain ADD COLUMN, portable JSON type" idiom `0008_add_runs_warnings_column.py`
already established for `runs.warnings`.
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
    """Upgrade schema."""
    op.add_column(
        'runs',
        sa.Column('feature_lineage', sa.JSON(), nullable=False, server_default='[]'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('runs', 'feature_lineage')
