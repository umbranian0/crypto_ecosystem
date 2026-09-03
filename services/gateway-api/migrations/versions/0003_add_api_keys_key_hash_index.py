"""add unique index on identity.api_keys.key_hash (GW-025/DBOPT-001)

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-02 00:00:00.000000

Postgres-only (guarded on dialect, see below): the DBA's live `EXPLAIN
(ANALYZE, BUFFERS)` against the real running Postgres container
(`docs/product/backlog-db-optimization.md` DBOPT-001) showed `Seq Scan on
api_keys ... Filter: (key_hash = ...)` for the exact query
`PostgresApiKeyRepository.get_by_hash` (`src/app/repositories/
postgres_repository.py`) runs on every single authenticated request, via
`app.dependencies.auth.get_authenticated_tenant` -- the auth hot path.
`get_by_hash` is one of GW-003's documented tenant-agnostic exceptions (it
runs before a tenant is known, per 0002_add_identity_rls.py's own docstring),
so this table can never be scoped to a per-tenant slice; a full scan is
today's only plan, cheap only because the table is small platform-wide, not
per-tenant.

`UNIQUE`, not a plain btree: matches `get_by_hash`'s existing
`scalar_one_or_none()` assumption that at most one row exists per
`key_hash`, and gives Postgres a cheaper index-only-scan path than a
non-unique index would.

Zero application-code change accompanies this migration -- `get_by_hash`'s
query text (`WHERE key_hash = :key_hash`) is unchanged; the index only makes
the existing plan cheaper.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX_NAME = "ix_api_keys_key_hash"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # This service's own tests/test_models.py runs `alembic upgrade
        # head` against a real sqlite file as a schema-parity check -- that
        # run must stay a no-op here rather than error.
        return

    op.execute(
        f"CREATE UNIQUE INDEX {_INDEX_NAME} ON identity.api_keys (key_hash)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(f"DROP INDEX IF EXISTS identity.{_INDEX_NAME}")