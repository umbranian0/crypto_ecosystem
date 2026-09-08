"""Shared SQLAlchemy engine-building scaffolding (ARCH-001) and tenant-scoped
transaction helper (LC-010).

Extracted from validation-service's and gateway-api's `sqlite_repository.py`
modules, which each defined a byte-for-byte identical `_build_engine`. Generic
over `url` and `base` so the same helper covers `sqlite:///...` today and
`postgresql+psycopg://...` later (VS-013/GW-012) without a second helper.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session


def build_engine(url: str, base: type[DeclarativeBase]) -> Engine:
    """Creates an `Engine` for `url`. Runs `base.metadata.create_all` against
    it only for a non-Postgres (SQLite dev-convenience) URL.

    Found live during Sprint 29 (SETUP-004's own fresh-Postgres-volume dry
    run, not hypothetical): against a genuinely fresh Postgres volume where
    Alembic migrations (INF-016) have already created every table under a
    non-`public` schema (`identity`/`validation`/`reporting`) via a
    connection-string `-c search_path=<schema>` option,
    `base.metadata.create_all`'s own DDL-issuing connection does not reliably
    see that same `search_path`, and raises `InvalidSchemaName: no schema
    has been selected to create in` on every first request touching a
    memoized `Engine` -- even though the tables already exist. Every caller
    of this function (`gateway-api`/`validation-service`/`reporting-service`)
    already runs Alembic migrations as a required, separate step before the
    app starts against Postgres (`infra/bootstrap.sh`/`.ps1` step 3,
    INF-015/016) -- `create_all` was only ever load-bearing for the
    no-separate-migration-step SQLite local-dev path, so skipping it for
    Postgres removes a genuinely broken, redundant code path rather than any
    real schema-creation responsibility.
    """
    engine = create_engine(url)
    if engine.dialect.name != "postgresql":
        base.metadata.create_all(engine)
    return engine


def tenant_scope(session: Session, tenant_id: str) -> None:
    """Must be the first statement executed in `session`'s transaction: sets
    the Postgres RLS-scoping GUC for exactly this transaction.

    Extracted from gateway-api's `_set_tenant_scope` and validation-service's
    `_tenant_scoped_session` (LC-010), which each independently implemented
    this same statement. `set_config(..., true)` is `SET LOCAL`'s
    parameterizable equivalent (plain `SET LOCAL app.tenant_id = :tenant_id`
    is not valid Postgres syntax -- `SET`/`SET LOCAL` do not accept a bind
    parameter, only a literal); its third argument `true` scopes the setting
    to this transaction only, so it reverts at COMMIT/ROLLBACK and can never
    leak into a pooled connection's next, differently-tenanted, transaction.
    """
    session.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": tenant_id},
    )
