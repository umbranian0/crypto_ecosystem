"""create ingestion schema

Revision ID: 0001
Revises:
Create Date: 2026-08-25 00:00:00.000000

INGEST-002: the five `ingestion` tables from solution-design.md section 8.2's
schema sketch, column-for-column -- `price_ohlcv`, `onchain_metric`,
`sentiment_score`, `connector_credentials`, `crawl_runs`. Primary keys here
are already widened to include each time-series table's future hypertable
partitioning column (`open_time`/`timestamp`/`created_utc`) so
0003_convert_to_hypertables.py does not need its own separate
DROP/ADD CONSTRAINT step the way INF-010's `split_results` migration did --
that fix-up was only needed there because `split_results` predated its own
hypertable conversion with a narrower, already-shipped PK.
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
    """Upgrade schema."""
    op.create_table(
        'price_ohlcv',
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('open_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('open', sa.Float(), nullable=False),
        sa.Column('high', sa.Float(), nullable=False),
        sa.Column('low', sa.Float(), nullable=False),
        sa.Column('close', sa.Float(), nullable=False),
        sa.Column('volume', sa.Float(), nullable=False),
        sa.Column('close_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('quote_volume', sa.Float(), nullable=True),
        sa.Column('trades', sa.Float(), nullable=True),
        sa.Column('taker_buy_base', sa.Float(), nullable=True),
        sa.Column('taker_buy_quote', sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint('tenant_id', 'source', 'open_time'),
    )
    op.create_table(
        'onchain_metric',
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('value', sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint('tenant_id', 'source', 'timestamp'),
    )
    op.create_table(
        'sentiment_score',
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('created_utc', sa.DateTime(timezone=True), nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('subreddit', sa.Text(), nullable=True),
        sa.Column('post_id', sa.String(), nullable=False),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('score', sa.Integer(), nullable=True),
        sa.Column('num_comments', sa.Integer(), nullable=True),
        sa.Column('reddit_sid_pos', sa.Float(), nullable=False),
        sa.Column('reddit_sid_neg', sa.Float(), nullable=False),
        sa.Column('reddit_sid_neu', sa.Float(), nullable=False),
        sa.Column('reddit_sid_com', sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint('tenant_id', 'source', 'created_utc', 'post_id'),
    )
    op.create_table(
        'connector_credentials',
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('client_id', sa.LargeBinary(), nullable=False),
        sa.Column('client_secret', sa.LargeBinary(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('tenant_id', 'source'),
    )
    op.create_table(
        'crawl_runs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('since_watermark', sa.DateTime(timezone=True), nullable=True),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('row_count', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('crawl_runs')
    op.drop_table('connector_credentials')
    op.drop_table('sentiment_score')
    op.drop_table('onchain_metric')
    op.drop_table('price_ohlcv')
