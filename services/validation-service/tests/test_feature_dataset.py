"""VS-030 (MDF-003) unit tests for `app.feature_dataset`.

Uses hand-rolled `DatasetSource`/`ConnectorStatusChecker` test doubles (not a
real `CompositeDatasetSource`/HTTP call) so these tests isolate
`FeatureDatasetAssembler.assemble`'s own alignment/policy logic -- the four
`DatasetSource` dispatch branches themselves are already covered by
`test_dataset_source.py`, and the real HTTP round trip is covered by
`test_multimodal_runs.py`'s integration test.

Worked-example fixture note: ADR-0009's own worked-example table (hourly
price target vs. daily-or-coarser on-chain feature, 24h lag, "drop_row")
states the alignment *rule* (`fetched_at <= row_timestamp - lag`) but its own
illustrative numbers do not self-consistently satisfy that rule (row
`2024-01-02T01:00:00Z`'s stated eligibility window is `2024-01-01T01:00:00Z`,
but the table's own hash-rate `fetched_at` of `2024-01-01T06:00:00Z` is later
than that window, so the rule as literally stated would *not* consider that
row eligible, despite the table calling it "satisfied"). This test
reproduces the ADR's stated *rule* and the *qualitative pattern* the table
illustrates (first row dropped because no eligible on-chain value yet exists;
later rows kept, and forward-fill onto an hourly target repeats the same
on-chain value) with a fetched_at value that is internally consistent with
the rule text, rather than the table's own inconsistent literal numbers.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.feature_dataset import (
    FEATURE_SOURCE_LAG_HOURS,
    FeatureDatasetAssembler,
    FeatureDatasetError,
    FeatureFoldScaler,
)
from app.dataset_source import LoadedSeries


class _FakeDatasetSource:
    """`DatasetSource` test double: `references_by_key` maps a stable dict
    key (built from `reference["field"]`) to the `LoadedSeries` `.load()`
    should return for that reference -- lets each test control exactly what
    `fetched_at` (if any) a given feature reference resolves to, without
    going through a real `CompositeDatasetSource` dispatch.
    """

    def __init__(self, series_by_field: dict[str, LoadedSeries]) -> None:
        self._series_by_field = series_by_field

    def load(self, reference: object) -> LoadedSeries:
        field = reference["field"]
        return self._series_by_field[field]


class _FakeConnectorStatusChecker:
    def __init__(self, status: str = "completed", raise_error: bool = False) -> None:
        self._status = status
        self.calls: list[tuple[str, str]] = []

    def check(self, tenant_id: str, source: str) -> None:
        self.calls.append((tenant_id, source))
        if self._status != "completed":
            raise FeatureDatasetError(
                f"connector {source!r} is not ready for feature assembly (status: "
                f"{self._status!r}, expected 'completed')"
            )


def _hourly_index(start: str, n: int) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.date_range(start, periods=n, freq="h"))


def test_worked_example_on_chain_24h_lag_forward_fill_policy():
    """ADR-0009 worked example pattern: hourly price target, on-chain
    feature with a 24h lag, `"forward_fill_exhausted_as_null_then_drop"`
    policy (the policy that actually bridges a gap using the last known
    value, per that policy's own definition -- "a later gap was bridged by
    forward-fill") -- the first target row (no eligible on-chain value yet)
    is dropped; the remaining rows are kept and forward-filled with the same
    on-chain value (its cadence is coarser than the hourly target). Note:
    `"drop_row"` in this module never bridges a gap at all (only an exact
    eligibility-instant match counts, per that policy's own "or after gaps"
    clause) -- see `test_missing_timestamp_policy_drop_row_only_keeps_exact_
    eligibility_matches` below for that stricter policy's own behavior.
    """
    target_index = _hourly_index("2024-01-02T00:00:00", 4)

    # A single on-chain row, fetched_at chosen so it is eligible for target
    # rows T1/T2/T3 (eligibility window >= 2024-01-01T01:00:00) but not T0
    # (eligibility window 2024-01-01T00:00:00).
    on_chain_loaded = LoadedSeries(
        series=pd.Series([100.0], index=pd.DatetimeIndex(["2024-01-01T00:30:00"])),
        warnings=[],
        fetched_at=pd.DatetimeIndex(["2024-01-01T00:30:00"]),
    )
    dataset_source = _FakeDatasetSource({"value": on_chain_loaded})

    assembler = FeatureDatasetAssembler()
    result = assembler.assemble(
        target_index=target_index,
        feature_references=[{"source": "blockchain_info_hash-rate", "field": "value"}],
        missing_timestamp_policy="forward_fill_exhausted_as_null_then_drop",
        dataset_source=dataset_source,
        connector_status_checker=_FakeConnectorStatusChecker(),
    )

    assert list(result.index) == list(target_index[1:])
    assert len(result.feature_dataframe) == 3
    column = "blockchain_info_hash-rate.value"
    assert list(result.feature_dataframe[column]) == [100.0, 100.0, 100.0]
    assert result.lineage == [
        {"source": "blockchain_info_hash-rate", "field": "value", "lag_hours": 24}
    ]


def test_on_chain_lag_table_value():
    assert FEATURE_SOURCE_LAG_HOURS["blockchain_info_"] == 24


def _sentiment_and_price_fixture():
    """Fixture shared by the three missing_timestamp_policy tests: an hourly
    target index of 5 rows, and one feature source whose `fetched_at` values
    leave a leading gap (rows 0-1 have no eligible value) and then a mid-
    series update gap (no new fetched_at between rows 2 and 4, so only an
    *exact* eligibility match exists at row 2).
    """
    target_index = _hourly_index("2024-01-01T00:00:00", 5)
    # Zero additional lag (sentiment/price prefix), so eligibility windows
    # equal the target timestamps themselves.
    feature_loaded = LoadedSeries(
        series=pd.Series([1.0, 2.0], index=pd.DatetimeIndex(
            ["2024-01-01T02:00:00", "2024-01-01T04:00:00"]
        )),
        warnings=[],
        fetched_at=pd.DatetimeIndex(["2024-01-01T02:00:00", "2024-01-01T04:00:00"]),
    )
    dataset_source = _FakeDatasetSource({"sentiment": feature_loaded})
    return target_index, dataset_source


def test_missing_timestamp_policy_drop_row_only_keeps_exact_eligibility_matches():
    target_index, dataset_source = _sentiment_and_price_fixture()
    assembler = FeatureDatasetAssembler()

    result = assembler.assemble(
        target_index=target_index,
        feature_references=[{"source": "reddit_vader_sentiment", "field": "sentiment"}],
        missing_timestamp_policy="drop_row",
        dataset_source=dataset_source,
        connector_status_checker=_FakeConnectorStatusChecker(),
    )

    # Only rows 2 (02:00, exact match on 1.0) and 4 (04:00, exact match on
    # 2.0) have an *exact* eligibility-instant match; rows 0/1/3 have none
    # under the zero-tolerance drop_row rule.
    assert list(result.index) == [target_index[2], target_index[4]]


def test_missing_timestamp_policy_forward_fill_exhausted_bridges_the_gap():
    target_index, dataset_source = _sentiment_and_price_fixture()
    assembler = FeatureDatasetAssembler()

    result = assembler.assemble(
        target_index=target_index,
        feature_references=[{"source": "reddit_vader_sentiment", "field": "sentiment"}],
        missing_timestamp_policy="forward_fill_exhausted_as_null_then_drop",
        dataset_source=dataset_source,
        connector_status_checker=_FakeConnectorStatusChecker(),
    )

    # Rows 0/1 are genuinely unfillable (before the first fetched_at) and
    # are dropped; rows 2/3/4 are all fillable (2/4 exact, 3 bridged from
    # row 2's value via backward asof) -- a strictly larger surviving set
    # than "drop_row"'s exact-match-only result above.
    assert list(result.index) == list(target_index[2:])
    column = "reddit_vader_sentiment.sentiment"
    assert list(result.feature_dataframe[column]) == [1.0, 1.0, 2.0]


def test_missing_timestamp_policy_exclude_source_drops_column_not_rows():
    target_index, dataset_source = _sentiment_and_price_fixture()
    assembler = FeatureDatasetAssembler()

    result = assembler.assemble(
        target_index=target_index,
        feature_references=[{"source": "reddit_vader_sentiment", "field": "sentiment"}],
        missing_timestamp_policy="exclude_source",
        dataset_source=dataset_source,
        connector_status_checker=_FakeConnectorStatusChecker(),
    )

    # No rows dropped -- the column itself is excluded because it has at
    # least one alignment gap.
    assert list(result.index) == list(target_index)
    assert list(result.feature_dataframe.columns) == []
    assert any("excluded" in w for w in result.warnings)


def test_three_policies_produce_three_different_row_or_column_counts():
    """Hard requirement (Test acceptance criteria): each of the three
    policies must differ from the others in output shape for the same input
    -- not merely be individually accepted.
    """
    target_index, dataset_source = _sentiment_and_price_fixture()
    assembler = FeatureDatasetAssembler()

    drop_row = assembler.assemble(
        target_index=target_index,
        feature_references=[{"source": "reddit_vader_sentiment", "field": "sentiment"}],
        missing_timestamp_policy="drop_row",
        dataset_source=dataset_source,
        connector_status_checker=_FakeConnectorStatusChecker(),
    )
    forward_fill = assembler.assemble(
        target_index=target_index,
        feature_references=[{"source": "reddit_vader_sentiment", "field": "sentiment"}],
        missing_timestamp_policy="forward_fill_exhausted_as_null_then_drop",
        dataset_source=dataset_source,
        connector_status_checker=_FakeConnectorStatusChecker(),
    )
    exclude_source = assembler.assemble(
        target_index=target_index,
        feature_references=[{"source": "reddit_vader_sentiment", "field": "sentiment"}],
        missing_timestamp_policy="exclude_source",
        dataset_source=dataset_source,
        connector_status_checker=_FakeConnectorStatusChecker(),
    )

    shapes = {
        (len(drop_row.index), len(drop_row.feature_dataframe.columns)),
        (len(forward_fill.index), len(forward_fill.feature_dataframe.columns)),
        (len(exclude_source.index), len(exclude_source.feature_dataframe.columns)),
    }
    assert len(shapes) == 3, shapes


def test_missing_fetched_at_from_ingestion_service_backed_reference_fails_closed():
    """AC5: a reference whose loaded series has `fetched_at is None` (the
    disclosed IngestionServiceDatasetSource gap) must raise, never silently
    align on the series' own nominal index.
    """
    target_index = _hourly_index("2024-01-01T00:00:00", 3)
    loaded_without_fetched_at = LoadedSeries(
        series=pd.Series([1.0, 2.0, 3.0], index=target_index), warnings=[], fetched_at=None
    )
    dataset_source = _FakeDatasetSource({"close": loaded_without_fetched_at})
    assembler = FeatureDatasetAssembler()

    with pytest.raises(FeatureDatasetError, match="fetched_at"):
        assembler.assemble(
            target_index=target_index,
            feature_references=[{"source": "binance_price_btcusdt_1h", "field": "close"}],
            missing_timestamp_policy="drop_row",
            dataset_source=dataset_source,
            connector_status_checker=_FakeConnectorStatusChecker(),
        )


def test_connector_not_completed_rejected_before_alignment():
    """AC6: a still-running/queued/failed connector is rejected before any
    load/alignment is attempted.
    """
    target_index = _hourly_index("2024-01-01T00:00:00", 3)

    class _NeverLoadDatasetSource:
        def load(self, reference: object) -> LoadedSeries:
            raise AssertionError("dataset_source.load must not be reached")

    assembler = FeatureDatasetAssembler()
    checker = _FakeConnectorStatusChecker(status="running")

    with pytest.raises(FeatureDatasetError, match="running"):
        assembler.assemble(
            target_index=target_index,
            feature_references=[{"source": "blockchain_info_hash-rate", "field": "value"}],
            missing_timestamp_policy="drop_row",
            dataset_source=_NeverLoadDatasetSource(),
            connector_status_checker=checker,
        )


def test_invalid_missing_timestamp_policy_rejected():
    target_index = _hourly_index("2024-01-01T00:00:00", 3)
    assembler = FeatureDatasetAssembler()

    with pytest.raises(FeatureDatasetError):
        assembler.assemble(
            target_index=target_index,
            feature_references=[],
            missing_timestamp_policy="not-a-real-policy",
            dataset_source=_FakeDatasetSource({}),
            connector_status_checker=None,
        )


# --- Hard gate: FeatureFoldScaler is fit per-fold, never globally ----------


def test_feature_fold_scaler_parameters_differ_fold_to_fold():
    """Hard gate (Test acceptance criteria): fitting on two different
    folds' train windows of the same feature DataFrame must produce
    different fitted parameters -- proves the fit is genuinely per-fold, not
    a memoized/global computation reused across folds.
    """
    df = pd.DataFrame(
        {"a": [1.0, 2.0, 3.0, 100.0, 200.0, 300.0], "b": [0.1, 0.2, 0.3, 10.0, 20.0, 30.0]}
    )
    fold_1_train = df.iloc[0:3]
    fold_2_train = df.iloc[3:6]

    scaler = FeatureFoldScaler()
    fitted_1 = scaler.fit(fold_1_train)
    fitted_2 = scaler.fit(fold_2_train)

    assert not fitted_1.means.equals(fitted_2.means)
    assert not fitted_1.stds.equals(fitted_2.stds)

    # And each fitted scaler transforms consistently with its own fold's
    # parameters, not the other fold's or the full frame's.
    transformed_1 = fitted_1.transform(fold_1_train)
    assert transformed_1["a"].mean() == pytest.approx(0.0, abs=1e-9)


def test_feature_fold_scaler_fit_never_computes_over_the_full_unsplit_frame():
    """Structural check (Test acceptance criteria, hard gate): a source-level
    scan proving no function in `feature_dataset.py` computes a mean/std/
    scaler parameter over anything other than the `train_df` argument
    `FeatureFoldScaler.fit` receives -- same doc-sync-style structural-check
    precedent as NFE-018/LC-005/VS-016 (grep/AST scan, not just a passing
    test). Verified two ways: (1) `fit`'s own body only ever references its
    `train_df` parameter when computing `.mean()`/`.std()` (AST inspection);
    (2) no other function/module-level statement in this file calls
    `.mean()`/`.std()` at all -- `FeatureFoldScaler.fit` is the only such
    call site in the module.
    """
    import ast
    import inspect

    import app.feature_dataset as feature_dataset_module

    source = inspect.getsource(feature_dataset_module)
    tree = ast.parse(source)

    mean_or_std_call_sites = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("mean", "std")
        ):
            mean_or_std_call_sites.append(node)

    assert len(mean_or_std_call_sites) == 2, (
        "expected exactly the two calls inside FeatureFoldScaler.fit "
        f"(train_df.mean(), train_df.std()), found {len(mean_or_std_call_sites)}"
    )
    for node in mean_or_std_call_sites:
        # Each call must be `<name>.mean()`/`<name>.std()` where <name> is
        # the literal `train_df` parameter -- never a module-level
        # `feature_dataframe`/`aligned_columns`/any other assembled-table
        # name.
        assert isinstance(node.func.value, ast.Name)
        assert node.func.value.id == "train_df", node.func.value.id

    # Locate FeatureFoldScaler.fit's own function node and confirm both
    # call sites are lexically inside its body (not at module level or
    # inside FeatureDatasetAssembler.assemble).
    fit_function_node = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "FeatureFoldScaler":
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == "fit":
                    fit_function_node = child
    assert fit_function_node is not None
    fit_body_source = ast.dump(fit_function_node)
    for node in mean_or_std_call_sites:
        assert ast.dump(node) in fit_body_source
