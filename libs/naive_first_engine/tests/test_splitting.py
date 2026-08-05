"""Tests for the rolling-origin walk-forward splitter (NFE-002)."""

import pandas as pd

from naive_first_engine.splitting import Split, generate_splits


def test_splits_are_non_overlapping_and_chronologically_ordered():
    index = pd.date_range("2024-01-01", periods=200, freq="h")
    splits = generate_splits(index, train_window=48, test_window=12, step=12, purge_gap=0)

    assert len(splits) > 1
    for split in splits:
        assert split.train_start <= split.train_end < split.test_start <= split.test_end

    for prev, nxt in zip(splits, splits[1:]):
        assert prev.train_start < nxt.train_start
        assert prev.test_start < nxt.test_start


def test_generate_splits_reproduces_thesis_1h_split_count():
    # Out-of-sample window from da-tese-ao-produto.md section 1.2: 2024-01-09
    # to 2025-01-08 (365 days), 1h horizon. Section 1.3's ARIMA/1h row reports
    # "0/53" DM splits, i.e. 53 splits for the 1h horizon over that window.
    #
    # This is a sized-to-match regression anchor (not a byte-for-byte
    # reproduction of the thesis's own split generation): a full hourly index
    # over the published window, with a 1-day train window, 1-day test
    # window, and a 1-week step (matching the 1h horizon's daily test
    # cadence) lands on exactly 53 splits. purge_gap=0 here because this test
    # is about split *count/cadence*, not the purge gap itself (covered by
    # the dedicated purge tests below).
    index = pd.date_range("2024-01-09", "2025-01-08 23:00", freq="h")

    splits = generate_splits(
        index,
        train_window=24,
        test_window=24,
        step=24 * 7,
        purge_gap=0,
    )

    assert len(splits) == 53
    assert splits[0].train_start == index[0]
    assert splits[-1].test_end == index[-1]


def test_split_exposes_required_fields():
    index = pd.date_range("2024-01-01", periods=10, freq="h")
    [split] = generate_splits(index, train_window=5, test_window=5, step=5, purge_gap=0)

    assert isinstance(split, Split)
    assert split.train_start == index[0]
    assert split.train_end == index[4]
    assert split.test_start == index[5]
    assert split.test_end == index[9]


def test_purge_gap_defaults_to_nonzero_thesis_value():
    index = pd.date_range("2024-01-01", periods=200, freq="h")
    [split] = generate_splits(index, train_window=48, test_window=12, step=200)

    assert split.purge_start is not None
    assert split.purge_end is not None
    assert split.purge_end - split.purge_start == pd.Timedelta(hours=22)
    assert split.test_start - split.train_end == pd.Timedelta(hours=24)


def test_purge_gap_excludes_rows_from_both_train_and_test_position_based():
    index = pd.date_range("2024-01-01", periods=200, freq="h")
    splits = generate_splits(index, train_window=48, test_window=12, step=12, purge_gap=24)

    for split in splits:
        purged = index[(index > split.train_end) & (index < split.test_start)]
        assert len(purged) == 24
        assert split.purge_start == purged.min()
        assert split.purge_end == purged.max()


def test_purge_gap_excludes_rows_from_both_train_and_test_time_based():
    index = pd.date_range("2024-01-01", periods=200, freq="h")
    splits = generate_splits(
        index,
        train_window=pd.Timedelta(hours=48),
        test_window=pd.Timedelta(hours=12),
        step=pd.Timedelta(hours=12),
        purge_gap=pd.Timedelta(hours=24),
    )

    assert len(splits) > 1
    for split in splits:
        purged = index[(index > split.train_end) & (index < split.test_start)]
        # A 24h Timedelta purge_gap places test_start exactly 24h after the
        # last actual train row; on an hourly grid that leaves 23 excluded
        # rows strictly between them (unlike the int/row-count convention,
        # which purges exactly N rows -- see the position-based test above).
        assert len(purged) == 23
        assert split.test_start - split.train_end == pd.Timedelta(hours=24)
        assert split.purge_start == purged.min()
        assert split.purge_end == purged.max()


def test_purge_gap_zero_leaves_train_and_test_adjacent():
    index = pd.date_range("2024-01-01", periods=200, freq="h")
    splits = generate_splits(index, train_window=48, test_window=12, step=12, purge_gap=0)

    assert len(splits) > 1
    for split in splits:
        assert split.purge_start is None
        assert split.purge_end is None
        assert index.get_loc(split.test_start) == index.get_loc(split.train_end) + 1


def test_purge_gap_zero_leaves_train_and_test_adjacent_time_based():
    # Regression test: the time-based branch (train_window/test_window/step
    # all pd.Timedelta) previously included the last train timestamp in the
    # test set too when purge_gap=pd.Timedelta(0), since test_start_time ==
    # actual_train_end and the mask used `>=` with no `>` guard. Mirrors
    # test_purge_gap_zero_leaves_train_and_test_adjacent above, but for the
    # time-based branch specifically.
    index = pd.date_range("2024-01-01", periods=200, freq="h")
    splits = generate_splits(
        index,
        train_window=pd.Timedelta(hours=48),
        test_window=pd.Timedelta(hours=12),
        step=pd.Timedelta(hours=12),
        purge_gap=pd.Timedelta(0),
    )

    assert len(splits) > 1
    for split in splits:
        assert split.purge_start is None
        assert split.purge_end is None
        assert split.test_start > split.train_end
        assert index.get_loc(split.test_start) == index.get_loc(split.train_end) + 1


def test_thesis_config_purge_gap_matches_1h_6h_24h_horizons():
    # da-tese-ao-produto.md section 1.2: 24h purge gap between train and
    # test, across all three horizons (1h, 6h, 24h). The purge gap itself is
    # horizon-independent -- what matters is that the returned gap width is
    # exactly 24h regardless of which horizon's train/test windows are used.
    index = pd.date_range("2024-01-09", "2025-01-08 23:00", freq="h")

    for horizon_hours in (1, 6, 24):
        [split] = generate_splits(
            index,
            train_window=24 * 30,
            test_window=horizon_hours,
            step=len(index),
            purge_gap=pd.Timedelta(hours=24),
        )
        assert split.test_start - split.train_end == pd.Timedelta(hours=24)
        assert split.purge_end - split.purge_start == pd.Timedelta(hours=22)
