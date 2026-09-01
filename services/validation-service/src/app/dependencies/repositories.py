"""DI seam (implementation-plan.md section 7) for the two repository interfaces,
plus (VS-006) the `DatasetSource` provider -- kept in this module rather than a
new one since it is the service's only DI-seam module so far and VS-006's
Design section says to add it "alongside the existing repository providers".

Single responsibility: give route handlers a `Depends()`-injectable provider
typed against `ValidationRunRepository`/`SplitResultRepository` (VS-003)/
`DatasetSource` (VS-005), so handlers depend on the interface, never a
concrete class, and tests can override these providers with fakes via
`app.dependency_overrides`. VS-004 wires the repository providers to its
SQLite implementation -- this remains the only module that imports
`app.repositories.sqlite_repository` (AC2); no router/business-logic code
should import it directly.

DB path: `VALIDATION_SERVICE_DB_PATH` env var, defaulting to `./validation.db`
(a local file so run/split state survives a process restart -- VS-004 AC1).
Swapping to Postgres (VS-013) means changing only this module's provider
bodies, not any call site (backlog decision 2).

ARCH-002: `_get_engine` is the memoized-by-URL `Engine` provider -- one
`Engine` per distinct db_path/URL for the life of the process, instead of a
fresh `create_engine` on every `Depends()` resolution. Keyed by the URL
string (`functools.lru_cache`), never zero-arg, so tests that
`monkeypatch.setenv` the DB path per test still get an isolated engine per
path. This is the shared engine/session-factory seam VS-013's Postgres
work extends, not replaces.

VS-013: when `DATABASE_URL` is set to a `postgresql://`/`postgresql+psycopg://`
URL, the two repository providers below return `PostgresValidationRunRepository`/
`PostgresSplitResultRepository` (postgres_repository.py) instead of the
SQLite classes; otherwise they fall back to the existing
`VALIDATION_SERVICE_DB_PATH`-driven SQLite behavior unchanged. `_get_engine`
is reused as-is (same memoized-by-URL cache) for both backends -- the
Postgres URL is just another key into it.

VS-024: `get_dataset_source` now also depends on `get_tenant_context`
(`naive_first_common`) so it can construct a per-request
`IngestionServiceDatasetSource` carrying the *calling* request's own
`tenant_id` -- this is the actual tenant-forwarding fix, not left for
`POST /runs`'s handler to pass a second time (that handler still only ever
calls `dataset_source.load(reference)`, unchanged). The outbound
`httpx.Client` this provider builds is a fresh instance per resolution,
pointed at `INGESTION_SERVICE_URL` (env var, default
`http://localhost:8003` -- same convention as `gateway-api`'s
`dependencies/http_client.py`), not memoized like `_get_engine`/
`_get_s3_client`: matching the existing downstream-HTTP-client precedent in
this codebase (`gateway-api`/`reporting-service`'s own `http_client.py`
modules), where none of those providers cache across requests either.
"""

from __future__ import annotations

import functools
import os
from typing import Annotated

from fastapi import Depends
from sqlalchemy import Engine

import redis as redis_lib

import boto3
import httpx

from app.dataset_source import (
    CompositeDatasetSource,
    DatasetSource,
    IngestionServiceDatasetSource,
    InlineOrLocalFileDatasetSource,
    ObjectStorageDatasetSource,
)
from app.events import EventPublisher, InProcessLogEventPublisher, RedisStreamsEventPublisher
from app.models import Base
from app.repositories.interfaces import SplitResultRepository, ValidationRunRepository
from app.repositories.postgres_repository import (
    PostgresSplitResultRepository,
    PostgresValidationRunRepository,
)
from app.repositories.sqlite_repository import (
    SQLiteSplitResultRepository,
    SQLiteValidationRunRepository,
)
from naive_first_common import TenantContext, get_tenant_context
from naive_first_common.db import build_engine

_DB_PATH_ENV_VAR = "VALIDATION_SERVICE_DB_PATH"
_DEFAULT_DB_PATH = "./validation.db"
_DATABASE_URL_ENV_VAR = "DATABASE_URL"

# VS-013 AC1/hard requirement: table creation (via build_engine's
# create_all, same as migrations/env.py's own `SET search_path`) must land
# in `validation`, never `public`. Encoded on the URL itself (libpq
# `options` connection parameter), not via a post-connect statement,
# because build_engine (ARCH-001) only takes a URL -- it opens its own
# connection and runs create_all before this module ever sees the Engine
# it returns, so anything set *after* build_engine runs would be too late
# for that first connection.
_POSTGRES_SCHEMA = "validation"
_SEARCH_PATH_OPTION = f"options=-csearch_path%3D{_POSTGRES_SCHEMA}"


def _db_path() -> str:
    return os.environ.get(_DB_PATH_ENV_VAR, _DEFAULT_DB_PATH)


def _database_url() -> str | None:
    return os.environ.get(_DATABASE_URL_ENV_VAR)


def _is_postgres_url(url: str) -> bool:
    return url.startswith("postgresql://") or url.startswith("postgresql+psycopg://")


def _postgres_engine_url(url: str) -> str:
    # psycopg v3, synchronous (binding decision #3) -- normalize the plain
    # "postgresql://" scheme INF-003 wires through Compose to the
    # SQLAlchemy-explicit "postgresql+psycopg://" driver.
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{_SEARCH_PATH_OPTION}"


@functools.lru_cache(maxsize=None)
def _get_engine(url: str) -> Engine:
    # Keyed on `url`, not zero-arg (ARCH-002 grooming decision #2): a
    # zero-arg cache would return the same engine after
    # monkeypatch.setenv(VALIDATION_SERVICE_DB_PATH, ...) swaps the path
    # mid-suite, silently pointing tests at the wrong file.
    return build_engine(url, Base)


def get_validation_run_repository() -> ValidationRunRepository:
    database_url = _database_url()
    if database_url and _is_postgres_url(database_url):
        engine_url = _postgres_engine_url(database_url)
        return PostgresValidationRunRepository(engine_url, engine=_get_engine(engine_url))
    db_path = _db_path()
    return SQLiteValidationRunRepository(db_path, engine=_get_engine(f"sqlite:///{db_path}"))


def get_split_result_repository() -> SplitResultRepository:
    database_url = _database_url()
    if database_url and _is_postgres_url(database_url):
        engine_url = _postgres_engine_url(database_url)
        return PostgresSplitResultRepository(engine_url, engine=_get_engine(engine_url))
    db_path = _db_path()
    return SQLiteSplitResultRepository(db_path, engine=_get_engine(f"sqlite:///{db_path}"))


def get_health_check_engine() -> Engine:
    # OPS-005-01: reuses the exact same URL-resolution helpers the two
    # repository providers above already call -- no third derivation of the
    # DB URL. `/health` only needs the Engine to run a cheap `SELECT 1`, not
    # a repository instance.
    database_url = _database_url()
    if database_url and _is_postgres_url(database_url):
        engine_url = _postgres_engine_url(database_url)
        return _get_engine(engine_url)
    db_path = _db_path()
    return _get_engine(f"sqlite:///{db_path}")


_OBJECT_STORAGE_ENDPOINT_URL_ENV_VAR = "OBJECT_STORAGE_ENDPOINT_URL"
_OBJECT_STORAGE_ACCESS_KEY_ENV_VAR = "OBJECT_STORAGE_ACCESS_KEY"
_OBJECT_STORAGE_SECRET_KEY_ENV_VAR = "OBJECT_STORAGE_SECRET_KEY"
_OBJECT_STORAGE_BUCKET_ENV_VAR = "OBJECT_STORAGE_BUCKET"
_DEFAULT_OBJECT_STORAGE_BUCKET = "naive-first"

# VS-023/VS-024: same env var name gateway-api's own dependencies/http_client.py
# already uses for its ingestion-service client (naming convention, not a
# shared value -- each service resolves its own INGESTION_SERVICE_URL).
_INGESTION_SERVICE_URL_ENV_VAR = "INGESTION_SERVICE_URL"
_DEFAULT_INGESTION_SERVICE_URL = "http://localhost:8003"
_DOWNSTREAM_TIMEOUT_ENV_VAR = "VALIDATION_SERVICE_DOWNSTREAM_TIMEOUT_SECONDS"
_DEFAULT_DOWNSTREAM_TIMEOUT_SECONDS = 30.0


@functools.lru_cache(maxsize=None)
def _get_s3_client(endpoint_url: str | None, access_key: str | None, secret_key: str | None):
    # Keyed on the connection params (not zero-arg), same rationale as
    # `_get_engine`/`_get_redis_publisher`: a monkeypatch.setenv of any
    # OBJECT_STORAGE_* var mid-suite must not silently reuse a stale client.
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )


def get_dataset_source(
    tenant: TenantContext = Depends(get_tenant_context),
) -> DatasetSource:
    # VS-015: always returns a CompositeDatasetSource wrapping the
    # interim (VS-005), object-storage (VS-015), and ingestion-service
    # (VS-023/VS-024) implementations -- AC2's "no change to POST /runs's
    # handler code" is satisfied by this provider dispatching internally, not
    # by one implementation replacing the other. Unset OBJECT_STORAGE_* env
    # vars still construct a client (fail loudly on the first real `load()`
    # call against it, not a silent no-op here).
    endpoint_url = os.environ.get(_OBJECT_STORAGE_ENDPOINT_URL_ENV_VAR)
    access_key = os.environ.get(_OBJECT_STORAGE_ACCESS_KEY_ENV_VAR)
    secret_key = os.environ.get(_OBJECT_STORAGE_SECRET_KEY_ENV_VAR)
    bucket = os.environ.get(_OBJECT_STORAGE_BUCKET_ENV_VAR, _DEFAULT_OBJECT_STORAGE_BUCKET)
    s3_client = _get_s3_client(endpoint_url, access_key, secret_key)

    # VS-024: built fresh per request (this provider's `tenant` param comes
    # from Depends(get_tenant_context), which is itself resolved per request),
    # never memoized like _get_engine/_get_s3_client -- an
    # IngestionServiceDatasetSource is only ever safe to reuse for the one
    # tenant it was built for, so caching it across requests by anything less
    # than the full (url, tenant_id) pair would risk serving one tenant's
    # outbound calls under another tenant's already-built instance.
    ingestion_service_base_url = os.environ.get(
        _INGESTION_SERVICE_URL_ENV_VAR, _DEFAULT_INGESTION_SERVICE_URL
    )
    ingestion_service_timeout = float(
        os.environ.get(_DOWNSTREAM_TIMEOUT_ENV_VAR, _DEFAULT_DOWNSTREAM_TIMEOUT_SECONDS)
    )
    ingestion_service_http_client = httpx.Client(
        base_url=ingestion_service_base_url, timeout=ingestion_service_timeout
    )
    ingestion_service_source = IngestionServiceDatasetSource(
        ingestion_service_http_client, ingestion_service_base_url, tenant.tenant_id
    )

    return CompositeDatasetSource(
        InlineOrLocalFileDatasetSource(),
        ObjectStorageDatasetSource(s3_client, bucket),
        ingestion_service_source,
    )


# Module-level singleton (VS-009): unlike the other providers, this one must
# return the *same* instance across requests within a process so tests (and,
# later, any in-process consumer) can inspect what was published across a
# request/response cycle. `app.dependency_overrides` still lets tests swap in
# their own instance per-test.
_event_publisher = InProcessLogEventPublisher()

# REDIS_URL env var (VS-014 binding decision #10, mirrors DATABASE_URL's
# convention): memoized by URL for the same reason `_get_engine` is (a
# monkeypatch.setenv mid-suite must not silently reuse a stale client).
_REDIS_URL_ENV_VAR = "REDIS_URL"


@functools.lru_cache(maxsize=None)
def _get_redis_publisher(url: str) -> RedisStreamsEventPublisher:
    return RedisStreamsEventPublisher(redis_lib.from_url(url))


def get_event_publisher() -> EventPublisher:
    # VS-014: swap to the durable Redis Streams publisher when REDIS_URL is
    # set; otherwise fall back to VS-009's in-process singleton unmodified.
    redis_url = os.environ.get(_REDIS_URL_ENV_VAR)
    if redis_url:
        return _get_redis_publisher(redis_url)
    return _event_publisher


ValidationRunRepositoryDep = Annotated[ValidationRunRepository, Depends(get_validation_run_repository)]
SplitResultRepositoryDep = Annotated[SplitResultRepository, Depends(get_split_result_repository)]
DatasetSourceDep = Annotated[DatasetSource, Depends(get_dataset_source)]
EventPublisherDep = Annotated[EventPublisher, Depends(get_event_publisher)]
HealthCheckEngineDep = Annotated[Engine, Depends(get_health_check_engine)]
