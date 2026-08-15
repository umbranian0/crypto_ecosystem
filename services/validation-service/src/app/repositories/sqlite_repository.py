"""VS-004: interim SQLite-backed implementations of VS-003's repository
interfaces (`ValidationRunRepository`, `SplitResultRepository`), storing
VS-002's `app.models.Run`/`SplitResult` rows in a file-based SQLite database
so state survives a process restart (AC1). Postgres (VS-013) replaces this
class-for-class behind the same DI seam (backlog decision 2) -- see
README.md's "Storage backend" note.

Conversion between VS-002's SQLAlchemy models and VS-003's `RunRecord`/
`SplitResultRecord` dataclasses happens once here (`_run_to_record`,
`_split_result_to_record`), per interfaces.py's docstring instruction that
VS-004 owns this conversion -- callers never build these dataclasses by hand.

Tenant isolation: every query filters by `tenant_id` in the SQL `WHERE`
clause itself (`.where(Model.tenant_id == tenant_id)`), never "fetch, then
check tenant_id in Python" -- the Design section's explicit ban on that
pattern, since it is exactly the kind of check a future edit could silently
drop.

Engine construction (file-based, not `:memory:`, so a run created before a
process restart is still there after -- AC1) uses the shared
`naive_first_common.db.build_engine` helper (ARCH-001); this is the seam
VS-013 must extend for Postgres.

ARCH-002: callers going through `app.dependencies.repositories`'s providers
pass an already-memoized `engine` (one per db_path/URL, process-wide) so a
request no longer pays for a fresh `create_engine` call. The `engine=None`
fallback below builds one directly and stays in place only so this module's
own tests (`tests/test_sqlite_repository.py`), which construct these classes
straight from a `db_path`, keep working unmodified.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from naive_first_common.db import build_engine
from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session

from app.models import Base, Run, SplitResult
from app.repositories.interfaces import RunRecord, SplitResultRecord


def _run_to_record(run: Run) -> RunRecord:
    return RunRecord(
        id=run.id,
        tenant_id=run.tenant_id,
        dataset_id=run.dataset_id,
        horizon=run.horizon,
        purge_gap_hours=run.purge_gap_hours,
        split_config=run.split_config,
        status=run.status,
        created_at=run.created_at,
        completed_at=run.completed_at,
        failure_reason=run.failure_reason,
    )


def _split_result_to_record(split: SplitResult) -> SplitResultRecord:
    return SplitResultRecord(
        id=split.id,
        run_id=split.run_id,
        tenant_id=split.tenant_id,
        split_index=split.split_index,
        train_start=split.train_start,
        train_end=split.train_end,
        purge_start=split.purge_start,
        purge_end=split.purge_end,
        test_start=split.test_start,
        test_end=split.test_end,
        model_mae=split.model_mae,
        model_rmse=split.model_rmse,
        model_smape=split.model_smape,
        model_mase=split.model_mase,
        model_da=split.model_da,
        model_f1=split.model_f1,
        model_oos_r2=split.model_oos_r2,
        naive0_mae=split.naive0_mae,
        naive0_rmse=split.naive0_rmse,
        naive0_smape=split.naive0_smape,
        naive0_mase=split.naive0_mase,
        naive0_da=split.naive0_da,
        naive0_f1=split.naive0_f1,
        naive0_oos_r2=split.naive0_oos_r2,
        dm_statistic=split.dm_statistic,
        dm_pvalue=split.dm_pvalue,
        dm_verdict=split.dm_verdict,
    )


def _record_to_split_result(tenant_id: str, run_id: str, s: SplitResultRecord) -> SplitResult:
    """Inverse of `_split_result_to_record` -- builds the SQLAlchemy row
    `add_splits` persists. Shared with `postgres_repository.py` (same 21-field
    shape), same reasoning as `_run_to_record`/`_split_result_to_record`
    already being the single source for the read-path conversion.
    """
    return SplitResult(
        id=s.id,
        run_id=run_id,
        tenant_id=tenant_id,
        split_index=s.split_index,
        train_start=s.train_start,
        train_end=s.train_end,
        purge_start=s.purge_start,
        purge_end=s.purge_end,
        test_start=s.test_start,
        test_end=s.test_end,
        model_mae=s.model_mae,
        model_rmse=s.model_rmse,
        model_smape=s.model_smape,
        model_mase=s.model_mase,
        model_da=s.model_da,
        model_f1=s.model_f1,
        model_oos_r2=s.model_oos_r2,
        naive0_mae=s.naive0_mae,
        naive0_rmse=s.naive0_rmse,
        naive0_smape=s.naive0_smape,
        naive0_mase=s.naive0_mase,
        naive0_da=s.naive0_da,
        naive0_f1=s.naive0_f1,
        naive0_oos_r2=s.naive0_oos_r2,
        dm_statistic=s.dm_statistic,
        dm_pvalue=s.dm_pvalue,
        dm_verdict=s.dm_verdict,
    )


class SQLiteValidationRunRepository:
    """SQLite implementation of `ValidationRunRepository` (VS-003)."""

    def __init__(self, db_path: str, engine: Engine | None = None) -> None:
        self._engine = engine if engine is not None else build_engine(f"sqlite:///{db_path}", Base)

    def create_run(
        self,
        tenant_id: str,
        dataset_id: str,
        horizon: int,
        purge_gap_hours: float,
        split_config: dict,
    ) -> RunRecord:
        # Deterministic engine-side run_id (models.py's PK doc note) isn't
        # available at this signature -- naive_first_engine.protocol computes
        # it from run inputs the engine hasn't executed yet at creation time --
        # so a fresh id is minted here, matching SplitResult.id's own
        # default-uuid4 precedent in models.py.
        run = Run(
            id=uuid4().hex,
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            horizon=horizon,
            purge_gap_hours=purge_gap_hours,
            split_config=split_config,
            status="pending",
            created_at=datetime.utcnow(),
            completed_at=None,
            failure_reason=None,
        )
        with Session(self._engine) as session:
            session.add(run)
            session.commit()
            session.refresh(run)
            return _run_to_record(run)

    def get_run(self, tenant_id: str, run_id: str) -> RunRecord | None:
        with Session(self._engine) as session:
            run = session.execute(
                select(Run).where(Run.id == run_id, Run.tenant_id == tenant_id)
            ).scalar_one_or_none()
            return _run_to_record(run) if run is not None else None

    def update_run_status(
        self,
        tenant_id: str,
        run_id: str,
        status: str,
        *,
        completed_at: datetime | None = None,
        failure_reason: str | None = None,
    ) -> None:
        with Session(self._engine) as session:
            session.execute(
                update(Run)
                .where(Run.id == run_id, Run.tenant_id == tenant_id)
                .values(status=status, completed_at=completed_at, failure_reason=failure_reason)
            )
            session.commit()

    def list_runs(self, tenant_id: str, limit: int, offset: int) -> list[RunRecord]:
        with Session(self._engine) as session:
            rows = (
                session.execute(
                    select(Run)
                    .where(Run.tenant_id == tenant_id)
                    .order_by(Run.created_at.desc())
                    .limit(limit)
                    .offset(offset)
                )
                .scalars()
                .all()
            )
            return [_run_to_record(row) for row in rows]

    def count_runs(self, tenant_id: str) -> int:
        with Session(self._engine) as session:
            return session.execute(
                select(func.count()).select_from(Run).where(Run.tenant_id == tenant_id)
            ).scalar_one()


class SQLiteSplitResultRepository:
    """SQLite implementation of `SplitResultRepository` (VS-003)."""

    def __init__(self, db_path: str, engine: Engine | None = None) -> None:
        self._engine = engine if engine is not None else build_engine(f"sqlite:///{db_path}", Base)

    def add_splits(self, tenant_id: str, run_id: str, splits: list[SplitResultRecord]) -> None:
        rows = [_record_to_split_result(tenant_id, run_id, s) for s in splits]
        with Session(self._engine) as session:
            session.add_all(rows)
            session.commit()

    def get_splits(self, tenant_id: str, run_id: str) -> list[SplitResultRecord]:
        with Session(self._engine) as session:
            rows = (
                session.execute(
                    select(SplitResult)
                    .where(SplitResult.run_id == run_id, SplitResult.tenant_id == tenant_id)
                    .order_by(SplitResult.split_index)
                )
                .scalars()
                .all()
            )
            return [_split_result_to_record(row) for row in rows]
