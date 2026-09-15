"""add split_points table

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-15 00:00:00.000000

VS-031: `split_points` holds one row per (split, baseline, test-window
timestamp) triple -- the raw predicted/actual values already computed as a
side effect of `run_validation_protocol`'s existing baseline predictions
(see naive_first_engine.report_schema.BaselineResult.predictions, additive
in this same ticket). A new table, not a JSON column on `split_results` --
see this ticket's Design section for the retention/pagination rationale.

RLS is enabled/forced on this table too (this table holds tenant data,
same as `runs`/`split_results` -- matches
0002_add_row_level_security.py's exact policy shape).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0011'
down_revision: Union[str, Sequence[str], None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'split_points',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('run_id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('split_index', sa.Integer(), nullable=False),
        sa.Column('baseline_key', sa.String(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('predicted', sa.Float(), nullable=False),
        sa.Column('actual', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['runs.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    # Postgres-only DDL, same guard as 0002_add_row_level_security.py -- no
    # SQLite equivalent, no-op there.
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE split_points ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE split_points FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON split_points "
        "USING (tenant_id = current_setting('app.tenant_id')::text)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY tenant_isolation ON split_points")
        op.execute("ALTER TABLE split_points DISABLE ROW LEVEL SECURITY")
    op.drop_table('split_points')
