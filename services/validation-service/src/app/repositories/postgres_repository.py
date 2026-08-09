"""VS-013: Postgres-backed implementations of VS-003's repository interfaces
(`ValidationRunRepository`, `SplitResultRepository`), sibling to VS-004's
`SQLiteValidationRunRepository`/`SQLiteSplitResultRepository`
(sqlite_repository.py) behind the same DI seam
(`app.dependencies.repositories`) -- swapped in via `DATABASE_URL`, no
route-handler changes (Design section, binding decision).

Driver: `psycopg` v3, synchronous (`postgresql+psycopg://` URLs, binding
decision #3) -- keeps the existing `Session`-based method signatures VS-004
already established.

Engine construction: `naive_first_common.db.build_engine` (ARCH-001) via the
memoized-by-URL `_get_engine` seam ARCH-002 introduced in
`app.dependencies.repositories` -- no local `create_engine` call here.

Row-tenant scoping mechanism (RLS, binding decision #7 -- matches GW-012):
migrations/versions/0002_add_row_level_security.py enables and *forces*
Postgres row-level security on `runs`/`split_results`, with a
`tenant_isolation` policy that compares each row's `tenant_id` column against
`current_setting('app.tenant_id')`. That `current_setting` is a per-session
GUC with no value until something sets it -- if nothing sets it, the policy
raises rather than silently passing every row through, so a caller can never
accidentally see cross-tenant rows by skipping the setting.

Every transaction opened by the two classes below issues
`SELECT set_config('app.tenant_id', :tenant_id, true)` -- `SET LOCAL`'s
parameter-bindable equivalent (plain `SET LOCAL ... = :param` is not valid
Postgres syntax; `set_config`'s third argument `true` means "for this
transaction only", the same semantics) -- as the *first* statement, before
any other query, scoping `current_setting('app.tenant_id')` to that one
transaction only (reverts at COMMIT/ROLLBACK, so it can never leak into a
pooled connection's next, differently-tenanted, transaction). This is what
makes the RLS policy actually scope queries to the calling tenant; the
`.where(Model.tenant_id == tenant_id)` clauses below are retained anyway
(matching VS-004's existing style) as defense in depth, not
as the enforcement mechanism -- RLS is.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Engine, select, text, update
from sqlalchemy.orm import Session

from app.models import Base, Run, SplitResult
from app.repositories.interfaces import RunRecord, SplitResultRecord
from app.repositories.sqlite_repository import _run_to_record, _split_result_to_record
from naive_first_common.db import build_engine


def _tenant_scoped_session(engine: Engine, tenant_id: str) -> Session:
    session = Session(engine)
    # `SET LOCAL app.tenant_id = :tenant_id` is not valid Postgres syntax --
    # SET does not accept a bind parameter, only a literal, which would mean
    # string-formatting tenant_id directly into SQL. set_config(..., true)
    # is SET LOCAL's parameter-bindable equivalent (third arg `true` = "for
    # this transaction only", i.e. the exact SET LOCAL revert-at-commit
    # semantics this docstring/the ticket's Design section call for).
    session.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"), {"tenant_id": tenant_id}
    )
    return session


class PostgresValidationRunRepository:
    """Postgres implementation of `ValidationRunRepository` (VS-003)."""

    def __init__(self, url: str, engine: Engine | None = None) -> None:
        self._engine = engine if engine is not None else build_engine(url, Base)

    def create_run(
        self,
        tenant_id: str,
        dataset_id: str,
        horizon: int,
        purge_gap_hours: float,
        split_config: dict,
    ) -> RunRecord:
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
        with _tenant_scoped_session(self._engine, tenant_id) as session:
            session.add(run)
            session.commit()
            session.refresh(run)
            return _run_to_record(run)

    def get_run(self, tenant_id: str, run_id: str) -> RunRecord | None:
        with _tenant_scoped_session(self._engine, tenant_id) as session:
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
        with _tenant_scoped_session(self._engine, tenant_id) as session:
            session.execute(
                update(Run)
                .where(Run.id == run_id, Run.tenant_id == tenant_id)
                .values(status=status, completed_at=completed_at, failure_reason=failure_reason)
            )
            session.commit()


class PostgresSplitResultRepository:
    """Postgres implementation of `SplitResultRepository` (VS-003)."""

    def __init__(self, url: str, engine: Engine | None = None) -> None:
        self._engine = engine if engine is not None else build_engine(url, Base)

    def add_splits(self, tenant_id: str, run_id: str, splits: list[SplitResultRecord]) -> None:
        rows = [
            SplitResult(
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
            for s in splits
        ]
        with _tenant_scoped_session(self._engine, tenant_id) as session:
            session.add_all(rows)
            session.commit()

    def get_splits(self, tenant_id: str, run_id: str) -> list[SplitResultRecord]:
        with _tenant_scoped_session(self._engine, tenant_id) as session:
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
