"""DI seam (implementation-plan.md section 7) for GW-003's three repository
interfaces.

Single responsibility: give route handlers a `Depends()`-injectable provider
typed against `TenantRepository`/`UserRepository`/`ApiKeyRepository` (GW-003),
so handlers depend on the interface, never a concrete class, and tests can
override these providers with fakes via `app.dependency_overrides`.

GW-004 wires the repository providers to its SQLite implementation -- this
remains the only module that imports `app.repositories.sqlite_repository`
(AC2); no router/business-logic code should import it directly.

DB path: `GATEWAY_API_DB_PATH` env var, defaulting to `./gateway.db` (a local
file so tenant/user/api-key state survives a process restart). Swapping to
Postgres (GW-012) means changing only this module's provider bodies, not any
call site (backlog decision 2).

ARCH-002: `_get_engine` is the memoized-by-URL `Engine` provider -- one
`Engine` per distinct db_path/URL for the life of the process, instead of a
fresh `create_engine` on every `Depends()` resolution. Keyed by the URL
string (`functools.lru_cache`), never zero-arg, so tests that
`monkeypatch.setenv` the DB path per test still get an isolated engine per
path. This is the shared engine/session-factory seam GW-012's Postgres +
RLS `SET LOCAL` work extends, not replaces.

GW-012: when `DATABASE_URL` is set to a `postgresql://`/`postgresql+psycopg://`
URL, the three providers below return `app.repositories.postgres_repository`'s
implementations (targeting the `identity` schema, RLS-scoped) instead of the
SQLite ones -- still through this exact same `_get_engine` seam, still a
DI-only swap (backlog decision 2), no call site anywhere else changes. No
`DATABASE_URL` (or a non-Postgres one) keeps the existing SQLite behavior
unmodified, so local/unit-test runs are unaffected.
"""

from __future__ import annotations

import functools
import os
from typing import Annotated
from urllib.parse import quote

from fastapi import Depends
from sqlalchemy import Engine

from app.models import Base
from app.repositories.interfaces import ApiKeyRepository, TenantRepository, UserRepository
from app.repositories.postgres_repository import (
    PostgresApiKeyRepository,
    PostgresTenantRepository,
    PostgresUserRepository,
)
from app.repositories.sqlite_repository import (
    SQLiteApiKeyRepository,
    SQLiteTenantRepository,
    SQLiteUserRepository,
)
from naive_first_common.db import build_engine

_DB_PATH_ENV_VAR = "GATEWAY_API_DB_PATH"
_DEFAULT_DB_PATH = "./gateway.db"
_DATABASE_URL_ENV_VAR = "DATABASE_URL"


def _db_path() -> str:
    return os.environ.get(_DB_PATH_ENV_VAR, _DEFAULT_DB_PATH)


def _database_url() -> str | None:
    return os.environ.get(_DATABASE_URL_ENV_VAR)


def _is_postgres_url(url: str) -> bool:
    return url.startswith("postgresql://") or url.startswith("postgresql+psycopg://")


def _postgres_engine_url(url: str) -> str:
    # Binding decision #3: psycopg v3, not psycopg2 -- force the
    # `+psycopg` driver regardless of which bare `postgresql://` scheme
    # DATABASE_URL uses (infra/.env.example's default has no driver suffix).
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    # `identity` schema targeting (GW-012 hard requirement, same reasoning
    # as migrations/env.py's `search_path` set): this is a connection-level
    # schema default, not a tenant-scoping concern -- app.tenant_id's
    # per-transaction SET LOCAL/set_config (postgres_repository.py) is the
    # actual tenant boundary.
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}options={quote('-c search_path=identity')}"


@functools.lru_cache(maxsize=None)
def _get_engine(url: str) -> Engine:
    # Keyed on `url`, not zero-arg (ARCH-002 grooming decision #2): a
    # zero-arg cache would return the same engine after
    # monkeypatch.setenv(GATEWAY_API_DB_PATH, ...) swaps the path mid-suite,
    # silently pointing tests at the wrong file.
    return build_engine(url, Base)


def get_tenant_repository() -> TenantRepository:
    url = _database_url()
    if url and _is_postgres_url(url):
        return PostgresTenantRepository(engine=_get_engine(_postgres_engine_url(url)))
    db_path = _db_path()
    return SQLiteTenantRepository(db_path, engine=_get_engine(f"sqlite:///{db_path}"))


def get_user_repository() -> UserRepository:
    url = _database_url()
    if url and _is_postgres_url(url):
        return PostgresUserRepository(engine=_get_engine(_postgres_engine_url(url)))
    db_path = _db_path()
    return SQLiteUserRepository(db_path, engine=_get_engine(f"sqlite:///{db_path}"))


def get_api_key_repository() -> ApiKeyRepository:
    url = _database_url()
    if url and _is_postgres_url(url):
        return PostgresApiKeyRepository(engine=_get_engine(_postgres_engine_url(url)))
    db_path = _db_path()
    return SQLiteApiKeyRepository(db_path, engine=_get_engine(f"sqlite:///{db_path}"))


TenantRepositoryDep = Annotated[TenantRepository, Depends(get_tenant_repository)]
UserRepositoryDep = Annotated[UserRepository, Depends(get_user_repository)]
ApiKeyRepositoryDep = Annotated[ApiKeyRepository, Depends(get_api_key_repository)]
