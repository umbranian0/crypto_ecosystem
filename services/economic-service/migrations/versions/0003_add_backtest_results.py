"""add backtest_results

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-23 00:00:00.000000

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
    """Upgrade schema.

    ECON-013: `backtest_results` is the first, narrowly-scoped, separately-
    authorized exception to ECON-002/ECON-010's "inputs-only, never a
    computed-output table" rule (see models.py's module docstring and
    tests/test_no_profitability_columns.py) -- it persists only rows that
    already passed ECON-005's unmodified structural eligibility gate, never a
    row for a refused entry. FK constraints target `fee_schedules`/
    `slippage_models` within this same schema (implementation-plan.md
    section 5 only forbids cross-*service* FKs).
    """
    op.create_table('backtest_results',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('tenant_id', sa.String(), nullable=False),
    sa.Column('backtest_id', sa.String(), nullable=False),
    sa.Column('run_id', sa.String(), nullable=False),
    sa.Column('fee_schedule_id', sa.String(), nullable=False),
    sa.Column('slippage_model_id', sa.String(), nullable=False),
    sa.Column('cost_adjusted_return', sa.Float(), nullable=False),
    sa.Column('slippage_adjusted_return', sa.Float(), nullable=False),
    sa.Column('total_cost_bps', sa.Float(), nullable=False),
    sa.Column('upstream_dm_statistic', sa.Float(), nullable=False),
    sa.Column('upstream_dm_pvalue', sa.Float(), nullable=False),
    sa.Column('upstream_dm_verdict', sa.String(), nullable=False),
    sa.Column('computed_at', sa.DateTime(), nullable=False),
    sa.Column('result_kind', sa.String(), nullable=False),
    sa.ForeignKeyConstraint(['fee_schedule_id'], ['fee_schedules.id'], ),
    sa.ForeignKeyConstraint(['slippage_model_id'], ['slippage_models.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('backtest_results')
