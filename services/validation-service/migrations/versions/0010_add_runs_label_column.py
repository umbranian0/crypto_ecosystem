"""add runs.label column

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-14 00:00:00.000000

UAT-008: adds `runs.label`, a nullable String column storing the optional,
freeform label a tenant may attach at submission time (`RunRequest.label`,
`libs/common`'s `contracts.py`, max 200 chars). Nullable, no server default
-- unlike `0008`/`0009`'s `warnings`/`feature_lineage` JSON columns (which
needed a non-null default to backfill existing rows with an empty list),
`label`'s honest default for an existing row is simply "no label was ever
supplied," i.e. `NULL`, not a fabricated empty string.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0010'
down_revision: Union[str, Sequence[str], None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'runs',
        sa.Column('label', sa.String(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('runs', 'label')
