"""add client_baseline_results column

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-24 00:00:00.000000

VS-017: adds `split_results.client_baseline_results`, a nullable JSON column
storing the optional third (client-supplied) baseline's full result. Plain
`ADD COLUMN` needs no dialect guard (unlike 0002's RLS DDL, which has no
SQLite equivalent) -- SQLAlchemy's `JSON` type compiles to a portable JSON
column on Postgres and a TEXT-serialized-JSON column on SQLite either way, so
this migration runs unchanged against `test_alembic_upgrade_head_creates_
matching_schema`'s sqlite:/// target and a real Postgres `DATABASE_URL`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('split_results', sa.Column('client_baseline_results', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('split_results', 'client_baseline_results')
