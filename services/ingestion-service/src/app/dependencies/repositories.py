"""DI seam (implementation-plan.md section 7) for this service's `Engine`
and repository providers.

Single responsibility at INGEST-007: give `GET /health` a `Depends()`-
injectable `Engine`, built the same way validation-service's/gateway-api's
own `dependencies/repositories.py` build theirs (via
`naive_first_common.db.build_engine`) -- no third derivation of the DB-URL
resolution logic.

INGEST-008 adds `get_connector_record_repository`/`get_credential_repository`,
reusing the exact same URL-resolution helpers (`_database_url`/
`_is_postgres_url`/`_postgres_engine_url`/`_db_path`/`_get_engine`)
`get_health_check_engine` already established, mirroring validation-service's
`dependencies/repositories.py` "one set of URL helpers, several providers"
precedent -- both providers return the Postgres-backed implementations
(`app.repositories.postgres_repository`), the only ones that exist so far
(INGEST-003/INGEST-004); there is no SQLite counterpart yet to fall back to
for a plain local `INGESTION_SERVICE_DB_PATH` run (tenant-scoped RLS session
setup is Postgres-specific), so `POST /connectors/{source}/run` needs a real
`DATABASE_URL` to write successfully outside of tests -- tests override both
providers with `tests/fake_repository.py`'s fakes via
`app.dependency_overrides`, never exercising this fallback.

DB path: `INGESTION_SERVICE_DB_PATH` env var, defaulting to `./ingestion.db`
(mirrors `GATEWAY_API_DB_PATH`/`VALIDATION_SERVICE_DB_PATH`'s own convention)
for local/test runs with no Postgres available. `DATABASE_URL` set to a
`postgresql://`/`postgresql+psycopg://` URL switches to Postgres, scoped to
the `ingestion` schema via the `search_path` connection option -- same
approach as validation-service's/gateway-api's own `_postgres_engine_url`.

ARCH-002: `_get_engine` is the memoized-by-URL `Engine` provider -- one
`Engine` per distinct db_path/URL for the life of the process, keyed by the
URL string (`functools.lru_cache`), never zero-arg, so a test that
`monkeypatch.setenv`s the DB path/URL mid-suite still gets an isolated engine
per value.

INGEST-014 adds `get_crawl_registry`/`CrawlRegistryDep`, one more
process-lifetime singleton alongside `_get_engine`'s `Engine` -- but a plain
module-level instance, not `functools.lru_cache`-memoized, since
`app.crawl_registry.CrawlRegistry` takes no constructor argument to key on
(unlike `_get_engine`, which is memoized per db_path/URL).
"""

from __future__ import annotations

import functools
import os
from typing import Annotated

from fastapi import Depends
from sqlalchemy import Engine

from app.crawl_registry import CrawlRegistry
from app.models import Base
from app.repositories.interfaces import ConnectorRecordRepository, CredentialRepository
from app.repositories.postgres_repository import (
    PostgresConnectorRecordRepository,
    PostgresCredentialRepository,
)
from naive_first_common.db import build_engine

_DB_PATH_ENV_VAR = "INGESTION_SERVICE_DB_PATH"
_DEFAULT_DB_PATH = "./ingestion.db"
_DATABASE_URL_ENV_VAR = "DATABASE_URL"

# `ingestion` schema targeting (README's "Postgres schema" contract, same
# reasoning as migrations/env.py's own `search_path` set) -- a
# connection-level schema default, not a tenant-scoping concern.
_POSTGRES_SCHEMA = "ingestion"
_SEARCH_PATH_OPTION = f"options=-csearch_path%3D{_POSTGRES_SCHEMA}"


def _db_path() -> str:
    return os.environ.get(_DB_PATH_ENV_VAR, _DEFAULT_DB_PATH)


def _database_url() -> str | None:
    return os.environ.get(_DATABASE_URL_ENV_VAR)


def _is_postgres_url(url: str) -> bool:
    return url.startswith("postgresql://") or url.startswith("postgresql+psycopg://")


def _postgres_engine_url(url: str) -> str:
    # psycopg v3, synchronous (binding decision #3, same as
    # validation-service/gateway-api) -- normalize the plain "postgresql://"
    # scheme infra/docker-compose.yml's DATABASE_URL uses to the
    # SQLAlchemy-explicit "postgresql+psycopg://" driver.
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{_SEARCH_PATH_OPTION}"


@functools.lru_cache(maxsize=None)
def _get_engine(url: str) -> Engine:
    return build_engine(url, Base)


def _resolved_engine_url() -> str:
    database_url = _database_url()
    if database_url and _is_postgres_url(database_url):
        return _postgres_engine_url(database_url)
    return f"sqlite:///{_db_path()}"


def get_health_check_engine() -> Engine:
    # OPS-005-01 pattern: `/health` only needs the Engine to run a cheap
    # `SELECT 1`, not a repository instance.
    return _get_engine(_resolved_engine_url())


def get_connector_record_repository() -> ConnectorRecordRepository:
    url = _resolved_engine_url()
    return PostgresConnectorRecordRepository(url, engine=_get_engine(url))


def get_credential_repository() -> CredentialRepository:
    url = _resolved_engine_url()
    return PostgresCredentialRepository(url, engine=_get_engine(url))


# Module-level singleton (not `functools.lru_cache`-memoized -- `CrawlRegistry`
# takes no constructor argument to key on) -- must be the *same* instance
# across concurrent requests to actually serialize them.
_crawl_registry = CrawlRegistry()


def get_crawl_registry() -> CrawlRegistry:
    return _crawl_registry


HealthCheckEngineDep = Annotated[Engine, Depends(get_health_check_engine)]
ConnectorRecordRepositoryDep = Annotated[
    ConnectorRecordRepository, Depends(get_connector_record_repository)
]
CredentialRepositoryDep = Annotated[CredentialRepository, Depends(get_credential_repository)]
CrawlRegistryDep = Annotated[CrawlRegistry, Depends(get_crawl_registry)]
