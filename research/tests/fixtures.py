"""Shared seeded synthetic fixture for `research/` model tests (MR-004/MR-005).

============================== DISCLOSURE ==================================
`synthetic_hourly_returns` is a SEEDED, DETERMINISTIC SYNTHETIC series of
exactly 3,000 hourly "returns" (`numpy.random.default_rng` with a fixed
seed), generated only to exercise candidate-model pipelines at the bounded,
light-compute scale sprint-41.md's MR-004 scoping note (and sprint-42.md's
MR-005 scoping note) require. It is NOT the thesis's real BTC dataset, and
no number produced from it is claimed to reproduce, or even approximate,
any of the thesis's published results (compare
`libs/naive_first_engine/tests/test_regression_1h.py`'s own disclosure
block, which this file's convention follows).
==============================================================================

Extracted here (per MR-005's Design section) so a second `Baseline`
implementation's tests (`test_regime_hmm.py`) can reuse the exact same
generator MR-004's `test_gradient_boosting.py` already built, rather than
duplicating a second synthetic-data generator inline in a second file.
`test_gradient_boosting.py` itself now imports from here too.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

N_ROWS = 3_000
SEED = 42


def synthetic_hourly_returns() -> pd.Series:
    """Exactly 3,000 seeded synthetic hourly "returns" -- see module DISCLOSURE.

    Not the thesis's real dataset; not claimed to reproduce its published
    numbers. Exists only to exercise candidate-model pipelines at a bounded,
    light-compute scale (sprint-41.md, sprint-42.md).
    """
    rng = np.random.default_rng(SEED)
    values = rng.normal(loc=0.0, scale=0.01, size=N_ROWS)
    index = pd.date_range("2020-01-01", periods=N_ROWS, freq="h")
    return pd.Series(values, index=index, name="return")
