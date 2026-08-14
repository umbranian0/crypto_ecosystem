"""DI seam (implementation-plan.md section 7) for `ReportRepository` -- the
service's only repository interface this sprint.

Single responsibility: give route handlers a `Depends()`-injectable provider
typed against `ReportRepository` (RS-002), so handlers depend on the
interface, never a concrete class. This remains the only module that imports
`app.repositories.postgres_repository` -- no router/business-logic code
should import it directly.

Postgres-only from the start (backlog decision 4, no SQLite fallback branch
-- a deliberate scope decision, not an oversight, unlike
validation-service/gateway-api's original SQLite-then-Postgres build order):
`get_report_repository` always resolves a Postgres URL from `DATABASE_URL`.

ARCH-002: `_get_engine` is the memoized-by-URL `Engine` provider -- one
`Engine` per distinct URL for the life of the process, instead of a fresh
`create_engine` on every `Depends()` resolution. Keyed by the URL string
(`functools.lru_cache`), same seam validation-service's/gateway-api's own
`_get_engine` already established (ARCH-002).
"""

from __future__ import annotations

import functools
import os
from typing import Annotated

from fastapi import Depends
from sqlalchemy import Engine

from app.models import Base
from app.repositories.interfaces import ReportRepository
from app.repositories.postgres_repository import PostgresReportRepository
from naive_first_common.db import build_engine

_DATABASE_URL_ENV_VAR = "DATABASE_URL"

# Table creation (via build_engine's create_all, same as migrations/env.py's
# own `SET search_path`) must land in `reporting`, never `public` -- encoded
# on the URL itself (libpq `options` connection parameter), not via a
# post-connect statement, because build_engine (ARCH-001) only takes a URL --
# it opens its own connection and runs create_all before this module ever
# sees the Engine it returns, so anything set *after* build_engine runs would
# be too late for that first connection. Same mechanism as
# validation-service's/gateway-api's own `_POSTGRES_SCHEMA`/
# `_SEARCH_PATH_OPTION` (RS-002 ticket DRY check note).
_POSTGRES_SCHEMA = "reporting"
_SEARCH_PATH_OPTION = f"options=-csearch_path%3D{_POSTGRES_SCHEMA}"


def _database_url() -> str:
    url = os.environ.get(_DATABASE_URL_ENV_VAR)
    if not url:
        raise RuntimeError(
            f"{_DATABASE_URL_ENV_VAR} is required (reporting-service is Postgres-only, "
            "backlog decision 4 -- no SQLite fallback)."
        )
    return url


def _postgres_engine_url(url: str) -> str:
    # psycopg v3, synchronous -- normalize the plain "postgresql://" scheme
    # INF-003-style Compose wiring produces to the SQLAlchemy-explicit
    # "postgresql+psycopg://" driver.
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{_SEARCH_PATH_OPTION}"


@functools.lru_cache(maxsize=None)
def _get_engine(url: str) -> Engine:
    # Keyed on `url`, not zero-arg (ARCH-002): a zero-arg cache would return
    # the same engine after monkeypatch.setenv(DATABASE_URL, ...) swaps the
    # URL mid-suite, silently pointing tests at the wrong database.
    return build_engine(url, Base)


def get_report_repository() -> ReportRepository:
    engine_url = _postgres_engine_url(_database_url())
    return PostgresReportRepository(engine_url, engine=_get_engine(engine_url))


def get_health_check_engine() -> Engine:
    # RS-007, mirrors validation-service's own `get_health_check_engine`
    # (OPS-005-01): reuses the same URL-resolution helper and the memoized
    # `_get_engine` the repository provider above already uses -- no third
    # derivation of the DB URL. `/health` only needs the Engine to run a
    # cheap `SELECT 1` against the `reporting` schema, not a repository
    # instance. Redis connectivity (RS-006's subscriber) is explicitly out
    # of scope for this check.
    engine_url = _postgres_engine_url(_database_url())
    return _get_engine(engine_url)


ReportRepositoryDep = Annotated[ReportRepository, Depends(get_report_repository)]
HealthCheckEngineDep = Annotated[Engine, Depends(get_health_check_engine)]
