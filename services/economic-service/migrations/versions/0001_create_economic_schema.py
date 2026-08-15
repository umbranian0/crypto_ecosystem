"""create economic schema

Revision ID: 0001
Revises:
Create Date: 2026-08-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Inputs-only, permanently (ECON-002 Design section, restated here so the
    migration itself carries the constraint, not only models.py): no column
    on any of these three tables may ever be a computed return/P&L/
    profitability figure. See tests/test_no_profitability_columns.py for the
    permanent, introspection-based regression guard.
    """
    op.create_table('fee_schedules',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('tenant_id', sa.String(), nullable=False),
    sa.Column('venue', sa.String(), nullable=False),
    sa.Column('fee_tiers', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('slippage_models',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('tenant_id', sa.String(), nullable=False),
    sa.Column('model_kind', sa.String(), nullable=False),
    sa.Column('parameters', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('simulation_configs',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('tenant_id', sa.String(), nullable=False),
    sa.Column('validation_run_id', sa.String(), nullable=False),
    sa.Column('fee_schedule_id', sa.String(), nullable=False),
    sa.Column('slippage_model_id', sa.String(), nullable=False),
    sa.Column('turnover_assumptions', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['fee_schedule_id'], ['fee_schedules.id'], ),
    sa.ForeignKeyConstraint(['slippage_model_id'], ['slippage_models.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('simulation_configs')
    op.drop_table('slippage_models')
    op.drop_table('fee_schedules')
