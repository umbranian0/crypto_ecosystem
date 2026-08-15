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


class SplitResultResponse(BaseModel):
    """One `split_results` row, full field set."""

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
