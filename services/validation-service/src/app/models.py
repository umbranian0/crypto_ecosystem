"""SQLAlchemy 2.0 declarative models for the `validation` schema: `Run`, `SplitResult`.

Backend-agnostic (portable SQLAlchemy types only) so VS-004's SQLite
implementation and a future VS-013 Postgres implementation share these exact
model classes -- no per-backend model duplication (solution-design.md
section 5, this ticket's AC3). Defined once here and imported by both the
repository layer (VS-003/VS-004) and the Alembic migration
(migrations/versions/0001_create_validation_schema.py) so the schema has a
single source of truth.

Field list is solution-design.md section 4's `runs`/`split_results` sketch,
field-for-field, plus `runs.failure_reason` (needed by VS-012, added now per
this ticket's Design section rather than altering the schema later).

Baseline-to-column mapping (binding design decision, VS-002):
`naive_first_engine.protocol.run_validation_protocol` returns
`SplitResult.baseline_results`, a dict keyed by baseline name ("naive0",
"naive_last", plus any `extra_baselines`). This sprint only ever produces
"naive0" and "naive_last" (VS-006's `POST /runs` never passes
`extra_baselines`; VS-017's client-supplied prediction baseline is
deferred). This schema designates a single "the model" baseline:

    model_*  columns <- baseline_results["naive_last"].metrics
                         (the persistence-floor benchmark, paired with
                         Naive0 per da-tese-ao-produto.md section 2.3.1)
    dm_*     columns <- baseline_results["naive_last"].dm_result
                         (never "naive0"'s, which is always None --
                         run_validation_protocol never DM-tests Naive0
                         against itself)
    naive0_* columns <- baseline_results["naive0"].metrics directly

When VS-017 adds a client-model Strategy, `model_*`/`dm_*` stop meaning
"naive_last" and start meaning "the client model" -- update this docstring
and README.md's Data model note at that point.

`naive_first_engine.report_schema.MetricSet` has seven fields (mae, rmse,
smape, mase, da, f1, oos_r2). solution-design.md section 4's sketch only
spells out mae/rmse/da/f1 before its `...` shorthand; per this ticket's
Design section, `naive0_*` gets full parity with `model_*`, so both baseline
column groups carry all seven MetricSet fields.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, JSON, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Run(Base):
    __tablename__ = "runs"

    # Reuses naive_first_engine's own deterministic run_id (SplitResult.run_id)
    # as the primary key rather than inventing a second ID (Design section).
    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    dataset_id: Mapped[str] = mapped_column(String, nullable=False)
    horizon: Mapped[int] = mapped_column(Integer, nullable=False)
    purge_gap_hours: Mapped[float] = mapped_column(Float, nullable=False)
    # Everything ValidationConfig needs beyond horizon/purge_gap
    # (train_window, test_window, step) -- one JSON column instead of a
    # column per ValidationConfig field.
    split_config: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # VS-012 AC1: a stored error message/reason, nullable until a run fails.
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class SplitResult(Base):
    __tablename__ = "split_results"

    # Surrogate PK -- report_schema.py's own docstring says the row's DB id
    # is deliberately not modeled in the engine's domain object and is
    # assigned at persistence time.
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: uuid.uuid4().hex)
    run_id: Mapped[str] = mapped_column(String, ForeignKey("runs.id"), nullable=False)
    # Denormalized onto this table (AC2): lets SplitResultRepository filter
    # by tenant without a join back to runs, and stops a leaked/misrouted
    # run_id from being used to read another tenant's splits.
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    split_index: Mapped[int] = mapped_column(Integer, nullable=False)

    train_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    train_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # Nullable: SplitBoundaries.purge_start/end are pd.Timestamp | None.
    purge_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    purge_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    test_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    test_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # model_* <- baseline_results["naive_last"].metrics (see module docstring)
    model_mae: Mapped[float] = mapped_column(Float, nullable=False)
    model_rmse: Mapped[float] = mapped_column(Float, nullable=False)
    model_smape: Mapped[float] = mapped_column(Float, nullable=False)
    model_mase: Mapped[float] = mapped_column(Float, nullable=False)
    model_da: Mapped[float] = mapped_column(Float, nullable=False)
    model_f1: Mapped[float] = mapped_column(Float, nullable=False)
    model_oos_r2: Mapped[float] = mapped_column(Float, nullable=False)

    # naive0_* <- baseline_results["naive0"].metrics (full parity with model_*)
    naive0_mae: Mapped[float] = mapped_column(Float, nullable=False)
    naive0_rmse: Mapped[float] = mapped_column(Float, nullable=False)
    naive0_smape: Mapped[float] = mapped_column(Float, nullable=False)
    naive0_mase: Mapped[float] = mapped_column(Float, nullable=False)
    naive0_da: Mapped[float] = mapped_column(Float, nullable=False)
    naive0_f1: Mapped[float] = mapped_column(Float, nullable=False)
    naive0_oos_r2: Mapped[float] = mapped_column(Float, nullable=False)

    # dm_* <- baseline_results["naive_last"].dm_result (never naive0's, which
    # is always None -- run_validation_protocol never DM-tests Naive0
    # against itself).
    dm_statistic: Mapped[float] = mapped_column(Float, nullable=False)
    dm_pvalue: Mapped[float] = mapped_column(Float, nullable=False)
    # One of dm_test.Verdict: "better" | "worse" | "no significant difference"
    dm_verdict: Mapped[str] = mapped_column(String, nullable=False)
