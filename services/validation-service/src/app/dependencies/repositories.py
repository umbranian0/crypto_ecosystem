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
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import Depends

from app.dataset_source import DatasetSource, InlineOrLocalFileDatasetSource
from app.events import EventPublisher, InProcessLogEventPublisher
from app.repositories.interfaces import SplitResultRepository, ValidationRunRepository
from app.repositories.sqlite_repository import (
    SQLiteSplitResultRepository,
    SQLiteValidationRunRepository,
)

_DB_PATH_ENV_VAR = "VALIDATION_SERVICE_DB_PATH"
_DEFAULT_DB_PATH = "./validation.db"


def _db_path() -> str:
    return os.environ.get(_DB_PATH_ENV_VAR, _DEFAULT_DB_PATH)


def get_validation_run_repository() -> ValidationRunRepository:
    return SQLiteValidationRunRepository(_db_path())


def get_split_result_repository() -> SplitResultRepository:
    return SQLiteSplitResultRepository(_db_path())


def get_dataset_source() -> DatasetSource:
    # Interim implementation (VS-005); a durable, remotely-backed source
    # (VS-015) replaces this provider body only, same DI seam.
    return InlineOrLocalFileDatasetSource()


# Module-level singleton (VS-009): unlike the other providers, this one must
# return the *same* instance across requests within a process so tests (and,
# later, any in-process consumer) can inspect what was published across a
# request/response cycle. `app.dependency_overrides` still lets tests swap in
# their own instance per-test.
_event_publisher = InProcessLogEventPublisher()


def get_event_publisher() -> EventPublisher:
    # Interim implementation (VS-009); a durable, Redis Streams-backed
    # publisher (VS-014) replaces this provider body only, same DI seam.
    return _event_publisher


ValidationRunRepositoryDep = Annotated[ValidationRunRepository, Depends(get_validation_run_repository)]
SplitResultRepositoryDep = Annotated[SplitResultRepository, Depends(get_split_result_repository)]
DatasetSourceDep = Annotated[DatasetSource, Depends(get_dataset_source)]
EventPublisherDep = Annotated[EventPublisher, Depends(get_event_publisher)]
