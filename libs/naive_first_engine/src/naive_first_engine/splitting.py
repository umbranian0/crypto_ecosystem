"""Rolling-origin walk-forward splitter with a configurable, enforced purge gap.

Single responsibility: given a time-ordered index, produce chronologically
ordered, non-overlapping train/purge/test `Split` boundaries. No baseline,
metric, or DM-test logic belongs in this module.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# Thesis default (da-tese-ao-produto.md section 1.2): 24h purge gap between
# train and test. generate_splits must never default to an unpurged split.
DEFAULT_PURGE_GAP = pd.Timedelta(hours=24)


@dataclass
class Split:
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    purge_start: pd.Timestamp | None
    purge_end: pd.Timestamp | None
    test_start: pd.Timestamp
    test_end: pd.Timestamp


def generate_splits(
    index: pd.DatetimeIndex,
    train_window: int | pd.Timedelta,
    test_window: int | pd.Timedelta,
    step: int | pd.Timedelta,
    purge_gap: int | pd.Timedelta = DEFAULT_PURGE_GAP,
) -> list[Split]:
    """Rolling-origin walk-forward split boundaries over `index`.

    `train_window`/`test_window`/`step` are either row counts (int, position-based)
    or `pd.Timedelta` (calendar-time based, tolerant of gaps/irregular spacing).
    All three must use the same kind. `index` is assumed sorted ascending.

    `purge_gap` is the enforced, non-overlapping gap between `train_end` and
    `test_start` (row count or `pd.Timedelta`, independent of which kind
    `train_window`/`test_window`/`step` use). Defaults to the thesis's 24h
    gap; pass `purge_gap=0` (or `pd.Timedelta(0)`) explicitly for adjacent
    train/test with no gap.
    """
    if isinstance(step, pd.Timedelta):
        return _generate_splits_by_time(index, train_window, test_window, step, purge_gap)
    return _generate_splits_by_position(index, train_window, test_window, step, purge_gap)


def _generate_splits_by_position(
    index: pd.DatetimeIndex,
    train_window: int,
    test_window: int,
    step: int,
    purge_gap: int | pd.Timedelta,
) -> list[Split]:
    splits: list[Split] = []
    n = len(index)
    train_start_pos = 0
    while True:
        train_end_pos = train_start_pos + train_window
        if train_end_pos > n:
            break
        train_end_time = index[train_end_pos - 1]
        if isinstance(purge_gap, pd.Timedelta):
            test_start_pos = index.searchsorted(train_end_time + purge_gap, side="left")
        else:
            test_start_pos = train_end_pos + purge_gap
        test_end_pos = test_start_pos + test_window
        if test_end_pos > n:
            break
        has_purge_rows = test_start_pos > train_end_pos
        splits.append(
            Split(
                train_start=index[train_start_pos],
                train_end=train_end_time,
                purge_start=index[train_end_pos] if has_purge_rows else None,
                purge_end=index[test_start_pos - 1] if has_purge_rows else None,
                test_start=index[test_start_pos],
                test_end=index[test_end_pos - 1],
            )
        )
        train_start_pos += step
    return splits


def _generate_splits_by_time(
    index: pd.DatetimeIndex,
    train_window: pd.Timedelta,
    test_window: pd.Timedelta,
    step: pd.Timedelta,
    purge_gap: int | pd.Timedelta,
) -> list[Split]:
    splits: list[Split] = []
    if len(index) == 0:
        return splits
    train_start_time = index[0]
    while True:
        train_end_time = train_start_time + train_window
        train_mask = (index >= train_start_time) & (index < train_end_time)
        if not train_mask.any():
            break
        actual_train_end = index[train_mask].max()
        # purge_gap is measured from the last *actual* train row, not the
        # nominal train_window boundary, so it matches the position-based
        # branch's semantics regardless of index spacing/gaps.
        if isinstance(purge_gap, pd.Timedelta):
            test_start_time = actual_train_end + purge_gap
        else:
            train_end_pos = index.get_loc(actual_train_end)
            test_start_pos = train_end_pos + 1 + purge_gap
            if test_start_pos >= len(index):
                break
            test_start_time = index[test_start_pos]
        test_end_time = test_start_time + test_window
        test_mask = (index >= test_start_time) & (index < test_end_time)
        # index is sorted ascending, so once the test window runs past the end
        # of the data it will stay empty on every later, further-forward step.
        if not test_mask.any():
            break
        purge_mask = (index > actual_train_end) & (index < test_start_time)
        splits.append(
            Split(
                train_start=index[train_mask].min(),
                train_end=index[train_mask].max(),
                purge_start=index[purge_mask].min() if purge_mask.any() else None,
                purge_end=index[purge_mask].max() if purge_mask.any() else None,
                test_start=index[test_mask].min(),
                test_end=index[test_mask].max(),
            )
        )
        train_start_time += step
    return splits
