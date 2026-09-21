"""add runs.engine_version and runs.config_fingerprint columns

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-21 00:00:00.000000

TRUST-003: adds `runs.engine_version` (the installed `naive_first_engine`
distribution version, e.g. "0.1.0") and `runs.config_fingerprint` (a SHA-256
hash of the run's canonicalized `split_config`) -- both `nullable=True`, with
deliberately **no** `server_default`, unlike `0008_add_runs_warnings_column.py`/
`0009_add_runs_feature_lineage_column.py`'s `nullable=False, server_default='[]'`
shape. A `server_default` here would silently backfill every pre-migration row
with a fabricated engine version/fingerprint it never actually ran with -- the
exact fabrication this story exists to prevent. Every row created from this
migration forward gets both fields populated at `create_run` time
(`app/fingerprint.py`, `app/routers/runs.py::_persist_new_run`); rows that
predate this migration stay genuinely `NULL`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0012'
down_revision: Union[str, Sequence[str], None] = '0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('runs', sa.Column('engine_version', sa.String(), nullable=True))
    op.add_column('runs', sa.Column('config_fingerprint', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('runs', 'config_fingerprint')
    op.drop_column('runs', 'engine_version')
