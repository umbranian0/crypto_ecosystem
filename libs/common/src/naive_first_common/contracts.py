"""Shared wire-contract Pydantic models for the run/split HTTP boundary
(ARCH-003).

This module is the sole, canonical definition of `RunRequest`/`RunResponse`/
`RunDetailResponse`/`SplitResultResponse`/`RunSummaryResponse` -- both
`gateway-api` and `validation-service` import these classes from here;
neither service defines its own copy. (Originally created by copying
validation-service's pre-ARCH-003 field lists verbatim, per the ticket's
binding decision, grooming #5 -- but that was a one-time bootstrapping step,
not a standing description of where the field lists live now.)
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    """Request shape for `POST /runs`. Field constraints mirror the config
    `naive_first_engine.splitting.generate_splits` implicitly relies on (it
    does not raise on bad input, it silently produces zero splits) --
    enforcing them here makes FastAPI return 422 before any downstream call.
    """

    dataset_id: str
    dataset_reference: dict
    horizon: int = Field(ge=1)
    purge_gap_hours: int = Field(ge=0)
    train_window: int = Field(gt=0)
    test_window: int = Field(gt=0)
    step: int = Field(gt=0)
    # VS-017: optional client-supplied prediction reference, same
    # DatasetSource-compatible shape as dataset_reference. None (the
    # default) is byte-identical to pre-VS-017 behavior -- naive baselines
    # remain structurally mandatory regardless of this field.
    client_prediction_reference: dict | None = None


class RunResponse(BaseModel):
    id: str
    status: str


class RunDetailResponse(BaseModel):
    """Full `runs` row shape."""

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


class RunSummaryResponse(BaseModel):
    """One `runs` row, list-view shape (VS-022): a strict subset of
    `RunDetailResponse`'s fields -- `split_config`/`tenant_id`/`failure_reason`
    are deliberately omitted (list rows don't need the full split config, the
    tenant is already implied by the caller's own auth context, and a failed
    run's reason is a detail-view concern, `GET /runs/{id}`'s job, not this
    list endpoint's). Field names/types are cross-checked against
    `RunDetailResponse` above rather than hand-copied, per ARCH-003's "single
    canonical definition" convention -- both `validation-service`'s `GET /runs`
    (VS-022) and, later, `gateway-api`'s proxy of it (GW-016) import this same
    class rather than redefining it.
    """

    id: str
    dataset_id: str
    horizon: int
    status: str
    created_at: datetime
    completed_at: datetime | None


class ClientBaselineResult(BaseModel):
    """VS-017: the optional third (client-supplied) baseline's result for one
    split -- same 7 `MetricSet` fields as the `model_*`/`naive0_*` groups,
    nested rather than flattened (avoids a fifth near-duplicate set of 10
    top-level fields on `SplitResultResponse`). `disclaimer` carries the
    mandatory positioning text (`app.client_baseline.CLIENT_PREDICTION_AUDIT_
    DISCLAIMER`) so it appears in the actual response body, not only in a
    Python string constant unused by any response path.

    `dm_statistic`/`dm_pvalue` are **optional** (`float | None`), not
    always-present numbers -- found live, not hypothetical: a single-test-point
    split has zero variance in its error differences, so the underlying DM
    test is genuinely undefined (`NaN`), and `NaN` is not valid JSON (Postgres's
    `json` column type rejects the literal token). `runs.py`'s persistence
    layer maps `NaN`/`Infinity` to `None` before writing the `client_baseline_
    results` JSON column (see `_json_safe_float`); `None` is therefore an
    honest "undefined for this split," not a placeholder for zero or a
    fabricated number -- consistent with this platform's own commitment to
    honest instability reporting (CLAUDE.md) rather than a convenient default.
    """

    key: str

    mae: float
    rmse: float
    smape: float
    mase: float
    da: float
    f1: float
    oos_r2: float

    dm_statistic: float | None
    dm_pvalue: float | None
    dm_verdict: str

    disclaimer: str



class SplitResultResponse(BaseModel):
    """One `split_results` row, full field set.

    `dm_statistic`/`dm_pvalue` are optional (`float | None`) -- a real,
    disclosed, pre-existing bug found live during Sprint 17 verification (not
    introduced by this sprint), present since VS-007/VS-008/GW-008 originally
    shipped: a single-test-point split has zero variance in the DM test's
    error differences, making the statistic genuinely undefined (NaN).
    Pydantic's own JSON serialization already rendered that NaN as JSON null
    on output (via validation-service's SplitResultResponse), but gateway-api's
    proxy layer (runs.py, SplitResultResponse(**item)) then failed
    reconstructing the model from that null against a required float field, a
    real 500 -- found and fixed opportunistically while verifying VS-017's
    adjacent ClientBaselineResult (same root cause), not caused by VS-017
    itself.
    """

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

    dm_statistic: float | None
    dm_pvalue: float | None
    dm_verdict: str

    # VS-017: populated only when a client_prediction_reference was supplied
    # for this run's POST /runs call; None otherwise (byte-identical to
    # pre-ticket responses).
    client_baseline: ClientBaselineResult | None = None
