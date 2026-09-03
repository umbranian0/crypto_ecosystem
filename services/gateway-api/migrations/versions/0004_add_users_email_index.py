"""add unique index on identity.users.email (GW-026/DBOPT-005)

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-03 00:00:00.000000

Postgres-only (guarded on dialect, see below): the DBA's live `EXPLAIN
(ANALYZE, BUFFERS)` against the real running Postgres container
(`docs/product/backlog-db-optimization.md` DBOPT-005) showed `Seq Scan on
users ... Filter: (email = ...)` for the exact query
`PostgresUserRepository.get_user_by_email` (`src/app/repositories/
postgres_repository.py`) runs on the login-time resolution path -- another of
GW-003's documented tenant-agnostic exceptions (it runs before a tenant is
known, alongside `get_by_hash`), so this table can never be scoped to a
per-tenant slice; a full scan is today's only plan, cheap only because the
table is small platform-wide, not per-tenant.

`UNIQUE`, not a plain btree: matches `get_user_by_email`'s existing
`scalar_one_or_none()` assumption that at most one row exists per `email`,
per the binding user decision that `email` is meant to be globally unique
across tenants, not merely per-tenant.

Zero application-code change accompanies this migration --
`get_user_by_email`'s query text (`WHERE email = :email`) is unchanged; the
index only makes the existing plan cheaper and adds the uniqueness guarantee
at the DB level.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX_NAME = "ix_users_email"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # This service's own tests/test_models.py runs `alembic upgrade
        # head` against a real sqlite file as a schema-parity check -- that
        # run must stay a no-op here rather than error.
        return

    op.execute(
        f"CREATE UNIQUE INDEX {_INDEX_NAME} ON identity.users (email)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(f"DROP INDEX IF EXISTS identity.{_INDEX_NAME}")
