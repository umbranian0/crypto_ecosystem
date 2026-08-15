"""Repository interfaces (implementation-plan.md section 7): `ValidationRunRepository`,
`SplitResultRepository`.

Single responsibility: declare the data-access seam between route handlers and
storage, with no storage-driver dependency of any kind, so schema-per-service
can later become DB-per-service (README.md's "Repository layer" bullet)
without any call site changing. Implementation is VS-004; this ticket (VS-003)
only defines the shape.

Record types (design decision, VS-003 ticket Design section): `RunRecord` and
`SplitResultRecord` below are plain `@dataclass(frozen=True)` types local to
this module, field-for-field mirrors of VS-002's `Run`/`SplitResult`
SQLAlchemy models (`app.models`), rather than reusing those SQLAlchemy models
directly. Reusing them would pull `sqlalchemy` into this module's import graph
transitively, which defeats AC3's "no storage-driver import" requirement even
if no SQLAlchemy name is used directly in a method signature here. Plain
dataclasses keep `interfaces.py` importable with zero storage dependencies,
which is exactly the property the Repository pattern is meant to buy
(implementation-plan.md section 7). VS-004's implementation is responsible for
converting between these records and `app.models.Run`/`SplitResult` rows.

Protocol vs ABC (design decision): both interfaces are `typing.Protocol`
(matching `naive_first_engine.baselines.Baseline`'s style), not `abc.ABC` --
neither interface needs a shared default method, so there is nothing an ABC
would buy over a Protocol here.

Ordering decision (VS-003 ticket Design section, binding on VS-004/VS-008):
`SplitResultRepository.get_splits` returns splits already ordered by
`split_index`. This is the repository's job, not the caller's -- every caller
(including VS-008) gets correct ordering by construction instead of having to
remember to sort. VS-022 extends this same decision to
`ValidationRunRepository.list_runs`, which returns runs ordered by
`created_at` descending.

Every method's first parameter after `self` is `tenant_id` (AC2, no
exceptions): both interfaces are tenant-scoped at the method-signature level,
not just by convention at the implementation.

VS-022 (`GET /runs` list endpoint): `list_runs(tenant_id, limit, offset)`
returns a `tenant_id`-scoped page of `RunRecord`s ordered by `created_at`
descending -- the repository's job, not the router's, per the ordering
decision above. `count_runs(tenant_id)` returns the total number of runs for
that tenant (unpaginated), the total-count method the router's response
envelope's `total` field needs; a separate method rather than folding the
count into `list_runs`'s return value keeps `list_runs`'s signature
unchanged from a plain `list[RunRecord]` and mirrors `get_splits`'s existing
"one query concept, one method" style.
"""

from __future__ import annotations

import typing
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RunRecord:
    """Mirrors `app.models.Run`'s columns exactly (see that module's docstring
    for field rationale); kept as a separate type so this module never imports
    `app.models` (and therefore never imports `sqlalchemy`).
    """

    id: str
    tenant_id: str
    dataset_id: str
    horizon: int
    purge_gap_hours: float
    split_config: dict
    status: str
    created_at: datetime
    completed_at: datetime | None
    failure_reason: str | None


@dataclass(frozen=True)
class SplitResultRecord:
    """Mirrors `app.models.SplitResult`'s columns exactly, including the
    flattened `model_*`/`naive0_*`/`dm_*` column groups (see that module's
    docstring for the baseline-to-column mapping rationale).
    """

    id: str
    run_id: str
    tenant_id: str
    split_index: int

    train_start: datetime
    train_end: datetime
    purge_start: datetime | None
    purge_end: datetime | None
    test_start: datetime
    test_end: datetime

    model_mae: float
    model_rmse: float
    model_smape: float
    model_mase: float
    model_da: float
    model_f1: float
    model_oos_r2: float

    naive0_mae: float
    naive0_rmse: float
    naive0_smape: float
    naive0_mase: float
    naive0_da: float
    naive0_f1: float
    naive0_oos_r2: float

    dm_statistic: float
    dm_pvalue: float
    dm_verdict: str


@typing.runtime_checkable
class ValidationRunRepository(typing.Protocol):
    """Repository for the `runs` table (backlog AC1 method set)."""

    def create_run(
        self,
        tenant_id: str,
        dataset_id: str,
        horizon: int,
        purge_gap_hours: float,
        split_config: dict,
    ) -> RunRecord: ...

    def get_run(self, tenant_id: str, run_id: str) -> RunRecord | None: ...

    def update_run_status(
        self,
        tenant_id: str,
        run_id: str,
        status: str,
        *,
        completed_at: datetime | None = None,
        failure_reason: str | None = None,
    ) -> None: ...

    def list_runs(self, tenant_id: str, limit: int, offset: int) -> list[RunRecord]:
        """Returns this tenant's runs ordered by `created_at` descending
        (VS-022 AC3) -- ordering is this method's responsibility, not the
        caller's (see module docstring), mirroring `get_splits`'s precedent.
        """
        ...

    def count_runs(self, tenant_id: str) -> int:
        """Total number of runs for this tenant (unpaginated) -- backs the
        `GET /runs` response envelope's `total` field (VS-022).
        """
        ...


@typing.runtime_checkable
class SplitResultRepository(typing.Protocol):
    """Repository for the `split_results` table (backlog AC1 method set)."""

    def add_splits(self, tenant_id: str, run_id: str, splits: list[SplitResultRecord]) -> None: ...

    def get_splits(self, tenant_id: str, run_id: str) -> list[SplitResultRecord]:
        """Returns splits ordered by `split_index` (VS-008 AC3) -- ordering is
        this method's responsibility, not the caller's (see module docstring).
        """
        ...
