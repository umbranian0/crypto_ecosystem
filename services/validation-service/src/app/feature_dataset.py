"""VS-030 (MDF-003): multi-source feature-set assembly, sitting one layer
above `dataset_source.py`'s `CompositeDatasetSource`, not inside it (ADR-0008
(a)) -- calls `CompositeDatasetSource.load()` once per `{source, field}`
reference (reuse, not reimplementation of the four existing dispatch
branches) and aligns the resulting series onto the target's own
`DatetimeIndex`, per ADR-0009's forward-fill rule.

Per-connector lag table (ADR-0008 (b), worked-example numbers repeated in
ADR-0009's own worked example): price-onto-price carries zero *additional*
lag beyond the run's own `purge_gap_hours` (same connector as the target in
every real dataset today); on-chain (`blockchain_info_*`) carries a 24h
conservative floor keyed off `fetched_at` (this connector's cadence is
daily-or-coarser and its confirmation-lag is unverified/plausibly revisable,
per ADR-0008's table); sentiment (`reddit_*`) carries zero *separate* buffer
beyond substituting `fetched_at` for `created_utc` (the substitution itself
*is* the buffer -- `fetched_at` already is the "known-at" instant).
`FEATURE_SOURCE_LAG_HOURS` below is the single dispatch table this module
consults for that mapping -- both the on-chain-24h and the price/sentiment-0h
rows are disclosed here, not re-derived at call time.

Ordering (ADR-0009, binding, leakage-critical): `assemble()` must be called,
and must run to completion, *before* `generate_splits`/RSS-004's guardrail
in `routers/runs.py` -- see that module's own docstring for the exact call
sequence. This module has no dependency on `naive_first_engine` and performs
no splitting itself; it only ever produces an aligned `DataFrame`/`index` for
the caller to hand to `generate_splits` afterward.

`IngestionServiceDatasetSource`, disclosed gap (ticket Analysis section):
`ingestion-service`'s `GET /datasets/{source}/series` does not expose each
row's `fetched_at` today, even though it is stored per-row in that service's
own tables -- extending that response shape is a different module's change,
out of this ticket's scope. A feature reference that resolves to
`IngestionServiceDatasetSource` therefore always has `loaded.fetched_at is
None`, and this module fails closed on that case (`FeatureDatasetError`)
rather than silently approximating alignment using the series' own nominal
index -- see `FeatureDatasetAssembler.assemble`'s per-reference step (c).

Per-fold preprocessing fit (`FeatureFoldScaler`): the leakage-safety surface
CLAUDE.md's rule and MDF-003's own AC require -- `fit(train_df)` computes
mean/std *only* over the rows passed in, never over the full assembled
`feature_dataframe`. Not yet wired into any candidate-model inference call
(no such consumer interface exists yet -- MDF-004's explicit, deferred
question) but directly callable against `generate_splits`'s own output.
"""

from __future__ import annotations

import dataclasses

import httpx
import pandas as pd

from app.dataset_source import DatasetSource, DatasetSourceError


class FeatureDatasetError(ValueError):
    """Raised for any feature-assembly failure -- same hard-fail shape
    `DatasetSourceError` already uses in `dataset_source.py` (this module
    does not subclass it: `feature_dataset.py` does not otherwise import
    from `dataset_source` by class hierarchy, only by composition, per the
    ticket's Design section), so `routers/runs.py`'s existing
    `try/except Exception` catch-and-fail-closed convention handles this
    with no second error-handling path.
    """


# ADR-0009's three literal missing_timestamp_policy values -- re-declared
# here (rather than importing naive_first_common.contracts' private literal
# back into this module) since this module has no dependency on
# libs/common today and MDF-003's ticket scope does not add one; kept
# byte-identical to naive_first_common.contracts.MISSING_TIMESTAMP_POLICIES.
MISSING_TIMESTAMP_POLICIES = frozenset(
    {"drop_row", "forward_fill_exhausted_as_null_then_drop", "exclude_source"}
)

# ADR-0008(b): per-connector-type lag table, keyed by source-name prefix.
# `blockchain_info_*` carries the 24h conservative floor (unverified,
# plausibly-revisable on-chain confirmation lag); every other prefix
# (`binance_price_*`, `reddit_*`, and anything unrecognized) carries 0 --
# price's "zero additional lag beyond the run's own purge_gap_hours" and
# sentiment's "no separate buffer beyond the fetched_at substitution" both
# collapse to the same 0-hour constant, per ADR-0008/ADR-0009.
_ON_CHAIN_LAG_HOURS = 24
_DEFAULT_LAG_HOURS = 0
FEATURE_SOURCE_LAG_HOURS: dict[str, int] = {
    "blockchain_info_": _ON_CHAIN_LAG_HOURS,
}


def _lag_hours_for_source(source: str) -> int:
    for prefix, lag_hours in FEATURE_SOURCE_LAG_HOURS.items():
        if source.startswith(prefix):
            return lag_hours
    return _DEFAULT_LAG_HOURS


class ConnectorStatusChecker:
    """Protocol: `check(tenant_id, source)` raises `FeatureDatasetError` if
    the named connector is not ready (AC6) -- a plain duck-typed protocol
    (not `typing.Protocol`, matching this module's small-surface style) so a
    test fake needs only implement `check`.
    """

    def check(self, tenant_id: str, source: str) -> None:  # pragma: no cover - interface
        raise NotImplementedError


# A connector must be in this terminal, successful state before any feature
# reference naming it can be aligned -- "running"/"queued"/"failed" (any
# other status) is rejected fail-closed (AC6), naming the concrete status.
_READY_CONNECTOR_STATUS = "completed"


class IngestionServiceConnectorStatusChecker:
    """Real `ConnectorStatusChecker`: calls `ingestion-service`'s
    `GET /connectors/{source}/status`, reusing the same
    `httpx.Client`/`base_url`/tenant-header pattern
    `IngestionServiceDatasetSource` (`dataset_source.py`) already
    establishes -- not a second HTTP client convention.
    """

    def __init__(self, http_client: httpx.Client, base_url: str, tenant_id: str) -> None:
        self._http_client = http_client
        self._base_url = base_url
        self._tenant_id = tenant_id

    def check(self, tenant_id: str, source: str) -> None:
        try:
            response = self._http_client.get(
                f"{self._base_url}/connectors/{source}/status",
                headers={"X-Tenant-Id": self._tenant_id},
            )
        except httpx.TimeoutException as exc:
            raise FeatureDatasetError(
                f"timed out checking connector status for {source!r}: {exc}"
            ) from exc
        except httpx.HTTPError as exc:
            raise FeatureDatasetError(
                f"could not reach ingestion-service to check connector status for "
                f"{source!r}: {exc}"
            ) from exc

        if response.status_code >= 400:
            raise FeatureDatasetError(
                f"ingestion-service returned {response.status_code} checking connector "
                f"status for {source!r}"
            )

        try:
            status = response.json()["status"]
        except (ValueError, KeyError, TypeError) as exc:
            raise FeatureDatasetError(
                f"malformed connector-status response from ingestion-service for "
                f"{source!r}: {exc}"
            ) from exc

        if status != _READY_CONNECTOR_STATUS:
            raise FeatureDatasetError(
                f"connector {source!r} is not ready for feature assembly (status: "
                f"{status!r}, expected {_READY_CONNECTOR_STATUS!r})"
            )


@dataclasses.dataclass(frozen=True)
class AssembledFeatures:
    """`FeatureDatasetAssembler.assemble`'s return shape."""

    # The target's own index, minus any rows dropped by
    # missing_timestamp_policy -- never a superset of the original target
    # index (ADR-0009's authoritative-clock decision).
    index: pd.DatetimeIndex
    # Columns named f"{source}.{field}", aligned to `index`.
    feature_dataframe: pd.DataFrame
    # {"source", "field", "lag_hours"} per reference, persisted verbatim.
    lineage: list[dict]
    warnings: list[str]


class FeatureDatasetAssembler:
    """Resolves a list of `{source, field}` references into one
    `AssembledFeatures`, calling `dataset_source.load()` once per reference
    (ADR-0008 reuse rule) and aligning each resulting series onto
    `target_index` per ADR-0009's forward-fill rule.
    """

    def assemble(
        self,
        target_index: pd.DatetimeIndex,
        feature_references: list[dict],
        missing_timestamp_policy: str,
        dataset_source: DatasetSource,
        connector_status_checker: ConnectorStatusChecker | None,
    ) -> AssembledFeatures:
        if missing_timestamp_policy not in MISSING_TIMESTAMP_POLICIES:
            raise FeatureDatasetError(
                f"missing_timestamp_policy must be one of "
                f"{sorted(MISSING_TIMESTAMP_POLICIES)}, got "
                f"{missing_timestamp_policy!r}"
            )

        warnings: list[str] = []
        lineage: list[dict] = []
        aligned_columns: dict[str, pd.Series] = {}

        for reference in feature_references:
            if not isinstance(reference, dict) or "field" not in reference:
                raise FeatureDatasetError(
                    f"feature reference must be a dict with a 'field' key, got {reference!r}"
                )

            field = reference["field"]
            source = reference.get("source")

            # (a) connector-status check first, before any loading/alignment
            # is attempted (AC6) -- only meaningful for a "source"-shaped
            # (ingestion-service-backed) reference; other reference shapes
            # (inline/path/object_key) have no crawl-status concept.
            if source is not None and connector_status_checker is not None:
                connector_status_checker.check(tenant_id="", source=source)

            column_name = f"{source}.{field}" if source is not None else f"<inline>.{field}"

            # (b) load exactly once via the existing DatasetSource contract
            # -- no reimplementation of any of the four dispatch branches.
            loaded = dataset_source.load(reference)

            # (c) fail closed rather than silently approximate using the
            # series' own nominal timestamp -- the disclosed
            # IngestionServiceDatasetSource gap (ticket Analysis section)
            # surfaces here verbatim for that source type.
            if loaded.fetched_at is None:
                raise FeatureDatasetError(
                    f"feature reference {reference!r} resolved to a DatasetSource "
                    "implementation that cannot supply a per-row fetched_at clock "
                    "(e.g. IngestionServiceDatasetSource's GET /datasets/{source}/series "
                    "does not currently expose fetched_at). Per ADR-0009, a value's "
                    "nominal timestamp may never stand in for when it became knowable "
                    "-- this reference cannot be safely aligned and is rejected rather "
                    "than silently approximated."
                )

            lag_hours = _lag_hours_for_source(source) if source is not None else _DEFAULT_LAG_HOURS
            lineage.append({"source": source, "field": field, "lag_hours": lag_hours})

            # (d) merge_asof(direction="backward") the feature series (sorted
            # by fetched_at) onto target_index - lag_hours -- structurally
            # cannot look forward (AC3). `"drop_row"` uses a zero-tolerance
            # asof match (only an *exact* eligible-instant hit counts -- no
            # bridging across a gap in the source's own update cadence,
            # ADR-0009's "or after gaps" clause); `"forward_fill_exhausted_
            # as_null_then_drop"`/`"exclude_source"` use an unbounded asof
            # match (bridge any gap using the last known value, dropping/
            # excluding only the genuinely-unfillable leading window) -- this
            # is the one place the three policies genuinely diverge in row/
            # column count, not merely in acceptance.
            feature_frame = pd.DataFrame(
                {"fetched_at": loaded.fetched_at, "value": loaded.series.to_numpy()}
            ).sort_values("fetched_at")

            eligibility_index = pd.DataFrame(
                {"eligible_at": target_index - pd.Timedelta(hours=lag_hours)}
            ).sort_values("eligible_at")

            merge_kwargs = {}
            if missing_timestamp_policy == "drop_row":
                merge_kwargs["tolerance"] = pd.Timedelta(0)

            merged = pd.merge_asof(
                eligibility_index,
                feature_frame,
                left_on="eligible_at",
                right_on="fetched_at",
                direction="backward",
                **merge_kwargs,
            )
            # merge_asof requires the left frame sorted by its "on" column;
            # restore target_index's own row order before attaching values.
            merged = merged.set_index(eligibility_index.index).sort_index()
            aligned = pd.Series(merged["value"].to_numpy(), index=target_index)

            aligned_columns[column_name] = aligned

        # (e) apply missing_timestamp_policy.
        exclude_columns: list[str] = []
        for column_name, series in list(aligned_columns.items()):
            if missing_timestamp_policy == "exclude_source" and series.isna().any():
                exclude_columns.append(column_name)
                warnings.append(
                    f"excluded feature column {column_name!r}: at least one alignment "
                    "gap under missing_timestamp_policy='exclude_source'"
                )
        for column_name in exclude_columns:
            del aligned_columns[column_name]

        if aligned_columns:
            feature_dataframe = pd.DataFrame(aligned_columns, index=target_index)
        else:
            feature_dataframe = pd.DataFrame(index=target_index)

        if missing_timestamp_policy in (
            "drop_row",
            "forward_fill_exhausted_as_null_then_drop",
        ):
            # Rows still null after all columns are aligned are dropped --
            # target and features drop in lockstep, never independently
            # (ADR-0009's authoritative-clock decision).
            keep_mask = ~feature_dataframe.isna().any(axis=1) if not feature_dataframe.empty else pd.Series(
                True, index=target_index
            )
        else:
            keep_mask = pd.Series(True, index=target_index)

        final_index = target_index[keep_mask.to_numpy()]
        final_feature_dataframe = feature_dataframe.loc[final_index]

        return AssembledFeatures(
            index=final_index,
            feature_dataframe=final_feature_dataframe,
            lineage=lineage,
            warnings=warnings,
        )


@dataclasses.dataclass(frozen=True)
class FittedScaler:
    """`FeatureFoldScaler.fit`'s return value -- per-column mean/std computed
    over exactly the rows passed to `fit`, nothing else.
    """

    means: pd.Series
    stds: pd.Series

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        # Guard against a zero-variance column (std == 0) producing inf/NaN
        # rather than silently propagating either -- same "never divide by
        # zero silently" posture as this codebase's other numeric edge cases
        # (e.g. dm_test.py's zero-variance handling).
        safe_stds = self.stds.replace(0.0, 1.0)
        return (df[self.means.index] - self.means) / safe_stds


@dataclasses.dataclass
class FeatureFoldScaler:
    """The per-fold-fit preprocessing surface CLAUDE.md's leakage rule
    requires and MDF-003's own AC names: `fit(train_df)` computes per-column
    mean/std **only** over the rows passed in -- no function anywhere in
    this module ever computes a mean/std/scaler parameter over the full,
    unsplit `feature_dataframe`. Not yet wired into any candidate-model
    inference call (MDF-004's deferred question) -- callable directly
    against `generate_splits`'s own output today.
    """

    def fit(self, train_df: pd.DataFrame) -> FittedScaler:
        return FittedScaler(means=train_df.mean(), stds=train_df.std())
