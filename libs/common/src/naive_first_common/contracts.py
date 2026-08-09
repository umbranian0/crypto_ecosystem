"""Shared wire-contract Pydantic models for the run/split HTTP boundary
(ARCH-003).

Canonical source of truth: `services/validation-service`'s own
`RunRequest`/`RunResponse`/`RunDetailResponse` (`routers/runs.py`) and
`SplitResultResponse` (`routers/splits.py`) -- copied verbatim here per the
ticket's binding decision (grooming, #5). `gateway-api` and
`validation-service` both import from this module instead of hand-copying
the field list; neither service defines its own copy anymore.
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
