"""add row-level security

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-25 00:00:00.000001

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = (
    "price_ohlcv",
    "onchain_metric",
    "sentiment_score",
    "connector_credentials",
    "crawl_runs",
)


def upgrade() -> None:
    """Upgrade schema.

    INGEST-002 (Design section): byte-identical in shape to
    `validation-service`'s `migrations/versions/0002_add_row_level_security.py`
    and `gateway-api`'s `migrations/versions/0002_add_identity_rls.py` --
    copied with attribution, not re-derived. Real Postgres RLS, not an
    application-side `WHERE tenant_id = ...` clause; the eventual
    repository layer (`INGEST-003`/`INGEST-004`/`INGEST-005`) is expected to
    issue `SET LOCAL app.tenant_id = :tenant_id` as the first statement of
    every transaction, which is what `current_setting('app.tenant_id')`
    below reads.

    Postgres-only DDL (`ENABLE`/`FORCE ROW LEVEL SECURITY`, `CREATE POLICY`)
    has no SQLite equivalent -- same guard idiom as the precedents above.
    """
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        # FORCE, not just ENABLE: there is no separate non-owner app role
        # provisioned for the `ingestion` schema yet (that's INF-014-shaped
        # infra scope) -- the app is expected to eventually connect as the
        # same role that owns these tables, and Postgres exempts table
        # owners from ENABLE-only RLS by default. Without FORCE, a future
        # tenant-isolation test would pass for any other role but silently
        # not apply to the app itself.
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            "USING (tenant_id = current_setting('app.tenant_id')::text)"
        )


def downgrade() -> None:
    """Downgrade schema."""
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in reversed(_TABLES):
        op.execute(f"DROP POLICY tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
