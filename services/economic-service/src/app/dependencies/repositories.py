"""DI seam (implementation-plan.md section 7) for ECON-002's
`EconomicInputRepository` and ECON-013's `BacktestResultRepository`, plus the
`/health` engine provider (OPS-005-01/02 precedent, ECON-001 AC3).

Single responsibility: give route handlers a `Depends()`-injectable provider
typed against `EconomicInputRepository`/`BacktestResultRepository`, so
handlers depend on the interface, never a concrete class, and tests can
override this provider with a fake via `app.dependency_overrides`. This
remains the only module that imports `app.repositories.sqlite_repository` --
no router/business-logic code should import it directly (mirrors
`validation-service`'s own precedent).

DB path: `ECONOMIC_SERVICE_DB_PATH` env var, defaulting to `./economic.db` (a
local file so state survives a process restart, matching VS-004's own AC1).
Both repository providers below share this same DB path/engine -- one SQLite
file backs the whole `economic` schema, same as `app.models.Base`'s single
`MetaData`.

`_get_engine` is a memoized-by-URL `Engine` provider (ARCH-002 precedent) --
one `Engine` per distinct db_path for the life of the process, instead of a
fresh `create_engine` on every `Depends()` resolution. Keyed by the URL
string (`functools.lru_cache`), never zero-arg, so tests that
`monkeypatch.setenv` the DB path per test still get an isolated engine per
path.
"""

from __future__ import annotations

import functools
import os
from typing import Annotated

from fastapi import Depends
from sqlalchemy import Engine

from naive_first_common.db import build_engine

from app.models import Base
from app.repositories.interfaces import BacktestResultRepository, EconomicInputRepository
from app.repositories.sqlite_repository import (
    SQLiteBacktestResultRepository,
    SQLiteEconomicInputRepository,
)

_DB_PATH_ENV_VAR = "ECONOMIC_SERVICE_DB_PATH"
_DEFAULT_DB_PATH = "./economic.db"


def _db_path() -> str:
    return os.environ.get(_DB_PATH_ENV_VAR, _DEFAULT_DB_PATH)


@functools.lru_cache(maxsize=None)
def _get_engine(url: str) -> Engine:
    return build_engine(url, Base)


def get_economic_input_repository() -> EconomicInputRepository:
    db_path = _db_path()
    return SQLiteEconomicInputRepository(db_path, engine=_get_engine(f"sqlite:///{db_path}"))


def get_backtest_result_repository() -> BacktestResultRepository:
    db_path = _db_path()
    return SQLiteBacktestResultRepository(db_path, engine=_get_engine(f"sqlite:///{db_path}"))


def get_health_check_engine() -> Engine:
    # OPS-005-01: reuses the exact same URL-resolution helper the repository
    # providers above already call -- no second derivation of the DB URL.
    # `/health` only needs the Engine to run a cheap `SELECT 1`, not a
    # repository instance.
    db_path = _db_path()
    return _get_engine(f"sqlite:///{db_path}")


EconomicInputRepositoryDep = Annotated[
    EconomicInputRepository, Depends(get_economic_input_repository)
]
BacktestResultRepositoryDep = Annotated[
    BacktestResultRepository, Depends(get_backtest_result_repository)
]
HealthCheckEngineDep = Annotated[Engine, Depends(get_health_check_engine)]
