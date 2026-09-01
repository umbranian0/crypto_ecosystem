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
    """Creates an `Engine` for `url` and runs `base.metadata.create_all` against it."""
    engine = create_engine(url)
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
