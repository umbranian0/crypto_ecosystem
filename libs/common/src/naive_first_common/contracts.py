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
from typing import Annotated

from pydantic import BaseModel, Field, WithJsonSchema, model_validator

# VS-030/ADR-0009: the three literal missing_timestamp_policy values -- a
# single shared constant so RunRequest's validator and
# validation-service's app.feature_dataset (which cannot import this
# libs/common module's private literal back, so it re-declares the same
# three strings as its own MISSING_TIMESTAMP_POLICIES set) never drift.
MISSING_TIMESTAMP_POLICIES = frozenset(
    {"drop_row", "forward_fill_exhausted_as_null_then_drop", "exclude_source"}
)


# UAT-007: schema-only typing for RunRequest.dataset_reference. Each class
# below mirrors one of the reference shapes
# services/validation-service/src/app/dataset_source.py's
# CompositeDatasetSource already dispatches on at `load()` time (grepped and
# cross-checked against dataset_source.py/dashboard-web's run_new_submit
# before writing this -- these are not invented shapes).
class PathDatasetReference(BaseModel):
    """`InlineOrLocalFileDatasetSource`'s "path" mode -- a local filesystem
    path to a two-column CSV (timestamp, value)."""

    path: str = Field(examples=["/data/btc_1h.csv"])


class InlineDatasetReference(BaseModel):
    """`InlineOrLocalFileDatasetSource`'s "inline" mode. The inline payload's
    own internal shape (a list of [timestamp, value] pairs, or a
    {"timestamps": [...], "values": [...]} dict, optionally with a third
    "fetched_at" element/key) is validated by dataset_source.py at load time,
    not re-modeled here."""

    inline: dict = Field(
        examples=[{"timestamps": ["2026-01-01T00:00:00"], "values": [42000.0]}]
    )


class StoredDatasetReference(BaseModel):
    """`IngestionServiceDatasetSource`'s "source" mode (ADR-0005, DASH-108) --
    a tenant's continuously-growing per-source table exposed by
    ingestion-service's `GET /datasets/{source}/series`."""

    source: str = Field(examples=["binance_btcusdt_1h"])
    start: str | None = Field(default=None, examples=["2026-01-01T00:00:00"])
    end: str | None = Field(default=None, examples=["2026-02-01T00:00:00"])
    field: str | None = Field(default=None, examples=["close"])


class ObjectKeyDatasetReference(BaseModel):
    """`ObjectStorageDatasetSource`'s "object_key" mode (VS-015). A fourth
    shape not named in UAT-007's own Analysis/Design (which enumerated only
    the three classes above) -- included anyway because `dataset_reference`
    is validated against this exact field in both `gateway-api` and
    `validation-service` (this is the single shared `RunRequest`, ARCH-003);
    omitting it would misrepresent a shape `dataset_source.py` already
    accepts today as unsupported in the published schema. Disclosed here as
    a deliberate documentation-completeness addition -- see
    `services/validation-service/README.md`'s VS-015 section for this mode's
    own scope caveats."""

    object_key: str = Field(examples=["processed/tenant-1/dataset-1.csv"])


_DATASET_REFERENCE_SHAPES = (
    PathDatasetReference,
    InlineDatasetReference,
    StoredDatasetReference,
    ObjectKeyDatasetReference,
)

# The field's actual runtime/validation type stays `dict` -- unchanged from
# before this ticket, so every existing call site (dataset_source.py's own
# `isinstance(reference, dict)` checks, validation-service's runs.py,
# dashboard-web's run_new_submit) keeps working with zero code change and
# zero behavior change. `WithJsonSchema` only replaces the *published*
# OpenAPI schema for this field with a real `anyOf` over the four named
# shapes above (each self-contained, no `$ref`/`$defs` needed since none of
# them nests another model), instead of pydantic's default bare
# `additionalProperties: true` for a plain `dict` field.
DatasetReferenceType = Annotated[
    dict,
    WithJsonSchema(
        {
            "title": "DatasetReference",
            "anyOf": [shape.model_json_schema() for shape in _DATASET_REFERENCE_SHAPES],
        }
    ),
]


class RunRequest(BaseModel):
    """Request shape for `POST /runs`. Field constraints mirror the config
    `naive_first_engine.splitting.generate_splits` implicitly relies on (it
    does not raise on bad input, it silently produces zero splits) --
    enforcing them here makes FastAPI return 422 before any downstream call.
    """

    dataset_id: str
    dataset_reference: DatasetReferenceType
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
    # VS-030/ADR-0008/ADR-0009: optional list of {"source", "field"}
    # references assembled into the candidate model's feature DataFrame --
    # never what run_validation_protocol/Naive0/NaiveLast see (those still
    # take the target series alone). None/empty (the default) is
    # byte-identical to pre-VS-030 behavior.
    feature_references: list[dict] | None = None
    # VS-030/ADR-0009: required (no default) whenever feature_references is
    # non-empty -- the model_validator below is the primary enforcement
    # point for the "no silent default" hard AC (runs.py's own check is
    # defense in depth, not the primary gate).
    missing_timestamp_policy: str | None = None
    # UAT-008: optional, freeform label a tenant may attach at submission
    # time. Pass-through only -- never consulted by the leakage-aware
    # validation/split logic above. None (the default) renders byte-identical
    # to pre-UAT-008 behavior.
    label: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _require_missing_timestamp_policy_when_features_requested(self) -> "RunRequest":
        if self.feature_references:
            if self.missing_timestamp_policy is None:
                raise ValueError(
                    "missing_timestamp_policy is required whenever feature_references "
                    "is non-empty -- no default is applied (one of: "
                    + ", ".join(sorted(MISSING_TIMESTAMP_POLICIES))
                    + ")"
                )
            if self.missing_timestamp_policy not in MISSING_TIMESTAMP_POLICIES:
                raise ValueError(
                    f"missing_timestamp_policy must be one of "
                    f"{sorted(MISSING_TIMESTAMP_POLICIES)}, got "
                    f"{self.missing_timestamp_policy!r}"
                )
        return self


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
    # DH-001: any non-fatal, disclosed condition the dataset load produced
    # for this run (e.g. a reordering-on-load notice). Defaulted to `[]`,
    # not required -- both gateway-api's and dashboard-web's own
    # `RunDetailResponse(**response.json())` reconstruction sites must stay
    # safe against a validation-service response that temporarily omits this
    # field during a rolling deploy (same defensive-default precedent as
    # `client_baseline` on `SplitResultResponse` below).
    warnings: list[str] = Field(default_factory=list)
    # VS-029: derived, not a new persisted fact -- True iff any of this run's
    # splits has a non-None `client_baseline_results` (VS-017's own existing
    # signal, single source of truth). `GET /runs/{id}`'s handler computes
    # this via `any()` over the run's splits before constructing this model.
    has_client_model: bool = False
    # VS-030: {"source", "field", "lag_hours"} per feature reference that
    # composed this run's assembled feature table, `[]` for a single-series
    # run (byte-identical default to pre-VS-030 responses).
    feature_lineage: list[dict] = Field(default_factory=list)
    # VS-030: derived, not a second independent flag -- bool(feature_lineage),
    # same one-source-of-truth precedent VS-029 established for
    # has_client_model (runs.py::get_run computes this, not a stored column).
    has_multimodal_features: bool = False
    # UAT-008: optional, freeform label a tenant attached at submission time.
    # None whenever no label was supplied -- never a fabricated default.
    label: str | None = None


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
    # UAT-008: optional, freeform label a tenant attached at submission time.
    label: str | None = None


class DatasetSummaryResponse(BaseModel):
    """One dataset's summary row (GW-020): source, {earliest,latest}_timestamp,
    row_count -- field-for-field mirror of `ingestion-service`'s own
    `DatasetSummaryResponse` (`services/ingestion-service/src/app/routers/
    datasets.py`, INGEST-009). That module defines its own local copy rather
    than importing this one (`ingestion-service` does not currently depend on
    `naive_first_common.contracts`, and adding that dependency is out of this
    ticket's scope) -- this class is the single canonical definition for any
    *new* consumer, per ARCH-003's convention; `gateway-api`'s proxy of
    `GET /ingestion/datasets` (GW-020) is that first new consumer.
    """

    source: str
    earliest_timestamp: datetime
    latest_timestamp: datetime
    row_count: int


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
    # VS-029: same derivation as RunDetailResponse.has_client_model above,
    # but per-split -- `client_baseline_results is not None` for this split,
    # the same condition `_client_baseline_response` already branches on.
    has_client_model: bool = False


class SplitPointResponse(BaseModel):
    """One `split_points` row (VS-031/VS-032/VS-033): a single per-timestamp
    prediction/actual pair for one baseline within one split. The single
    canonical shape for `GET /runs/{run_id}/splits/{split_index}/points`
    (VS-033) -- `validation-service`'s router imports this rather than
    hand-duplicating the field list (ARCH-003).

    `baseline_key` identifies which baseline this point belongs to (e.g.
    `"naive_last"`, `"naive0"`, or a client-supplied baseline's key) -- the
    same string values `SplitResultRecord`'s `dm_verdict`-adjacent baseline
    keys already use (`naive_first_engine.protocol.NAIVE0_KEY`/
    `NAIVE_LAST_KEY`), not re-declared here since this is a wire contract,
    not an engine-internal enum.
    """

    timestamp: datetime
    predicted: float
    actual: float
    baseline_key: str
