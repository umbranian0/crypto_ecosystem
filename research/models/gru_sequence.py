"""MR-015 -- GRU sequence-model candidate `Baseline` (Strategy) implementation,
CPU-only, research-only.

This is a candidate research model run through `naive_first_engine`'s
existing, unmodified leakage-aware protocol (`run_validation_protocol`) and
scored against the mandatory Naive0 baseline via Diebold-Mariano test, exactly
like every other baseline in `research/models/`. It is NOT a price-prediction
or trading-signal product feature -- it is a research baseline testing
whether a small GRU sequence model helps or not; whether it beats Naive0 is
an open, honestly-reported question, not an assumed or claimed outcome (see
docs/tickets/MR-015.md and CLAUDE.md's positioning rules).

`GRUSequenceBaseline.predict` only ever reads from its own `train`/`test`
arguments (the `Baseline` Protocol's own structural leakage-safety guarantee,
`libs/naive_first_engine/src/naive_first_engine/baselines.py`) -- no
module-level state, no closure over a full series. A fresh `torch.nn.GRU` +
linear head, a fresh `torch.optim.Adam` optimizer, and a fresh scaler are
constructed and fit inside every `predict()` call, never reused/cached across
splits, matching every other `research/models/*.py` baseline's own
structural invariant.

**The leakage guard (binding, docs/tickets/MR-015.md "The leakage guard"
section)**: for a target at position `i` in the time-ordered
`pd.concat([train, test])` context, the input window is exactly
`values[i-window:i]` -- never including `values[i]` itself. Fitting windows
are built from `train` only; `test` windows may reach back into `train`'s
own tail (legitimate train-fold information, available before `test` starts,
the same convention `RegimeHMMBaseline` already uses for its lagged state
routing) but never into `test`'s own future rows. Scaling, if used, is fit on
`train`'s own values only, then applied to both `train`- and `test`-derived
windows.

**Deliberate DRY exception (docs/tickets/MR-015.md Design section)**: this
file does NOT reuse `research/features.py::lagged_returns` for its windowing.
`lagged_returns` produces a flat lag-feature `DataFrame` (one column per lag,
one row per timestamp); a GRU needs a 3D tensor of shape
`(n_samples, window, 1)` -- a structurally different operation. Forcing the
GRU's windowing through `lagged_returns` would also obscure the exact
off-by-one boundary this ticket's leakage guard exists to prove correct.
Instead, a single small, dedicated, well-tested `_build_windows(series,
window)` helper is defined locally below.

Light-compute scoping (docs/tickets/MR-015.md "Compute-ceiling scoping
decision", Tech-Lead-fixed, not this file's to vary): hidden_size=16,
epochs=10, window=12, single-layer GRU(input_size=1, hidden_size=16,
num_layers=1, batch_first=True) + Linear(16, 1) head, Adam(lr=1e-3),
MSELoss, device="cpu" hardcoded with no CUDA check of any kind,
`torch.manual_seed(42)` set inside `predict()` for reproducibility.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import torch
from torch import nn

_HIDDEN_SIZE = 16
_EPOCHS = 10
_WINDOW = 12
_RANDOM_SEED = 42
_DEVICE = torch.device("cpu")


def _build_windows(series: pd.Series, window: int) -> tuple[np.ndarray, np.ndarray]:
    """Builds `(X, y)` sliding windows from a single time-ordered series.

    For each valid target position `i` (`i >= window`), `X[k] =
    values[i-window:i]` and `y[k] = values[i]` -- the target's own value at
    position `i` is never included in its own window. Rows before `window`
    have no valid window and are dropped entirely (no zero-padding, which
    could otherwise look like a real observed value to the model).

    `series` is whatever context the caller passes (`train` alone for
    fitting windows, or `pd.concat([train.tail(window), test])` for test
    windows that are allowed to reach into `train`'s own tail) -- this
    function has no opinion on where `series` came from and performs no I/O
    or leakage-relevant slicing of its own; the caller (`predict`, below) is
    responsible for the leakage guard's boundary between `train` and `test`.
    """
    values = series.to_numpy(dtype="float64")
    n = len(values)
    if n <= window:
        return np.empty((0, window), dtype="float64"), np.empty((0,), dtype="float64")

    X = np.empty((n - window, window), dtype="float64")
    y = np.empty((n - window,), dtype="float64")
    for k, i in enumerate(range(window, n)):
        X[k] = values[i - window : i]
        y[k] = values[i]
    return X, y


class _GRURegressor(nn.Module):
    """Single-layer GRU + linear head on the final hidden state.

    Fixed architecture per the ticket's compute-ceiling scoping decision --
    no bidirectionality, no attention, no dropout (dataset/window too small
    to need regularization at this scale, and dropout would add
    nondeterminism this baseline would then have to separately control for).
    """

    def __init__(self, hidden_size: int) -> None:
        super().__init__()
        self.gru = nn.GRU(input_size=1, hidden_size=hidden_size, num_layers=1, batch_first=True)
        self.head = nn.Linear(hidden_size, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        _, hidden = self.gru(x)
        return self.head(hidden[-1]).squeeze(-1)


class GRUSequenceBaseline:
    """`Baseline`-protocol-conforming single-layer GRU sequence model.

    `.name` requirement: mirrors MR-004/MR-005/MR-013's same reasoning --
    `naive_first_engine.protocol._baseline_key` keys `config.extra_baselines`
    entries by `type(baseline).__name__`, which this class's name already
    satisfies without any extra attribute. A `.name` property is added
    anyway, set to the class name, so both the literal backlog wording and
    the engine's own convention are satisfied by the same value.
    """

    name = "GRUSequenceBaseline"

    def predict(self, train: pd.Series, test: pd.Series) -> pd.Series:
        """Fits a brand-new GRU on `train`-only windows, predicts `test`.

        A fresh model, optimizer, and scaler are constructed here on every
        call -- nothing is stored on `self` or reused across calls.
        `torch.manual_seed(42)` is set inside this call (not at module
        import time) so each `predict()` call is independently
        reproducible, matching `RegimeHMMBaseline`'s `random_state=42`
        precedent.
        """
        torch.manual_seed(_RANDOM_SEED)

        train_values = train.to_numpy(dtype="float64")
        train_mean = float(train_values.mean()) if len(train_values) else 0.0
        train_std = float(train_values.std())
        if train_std == 0.0:
            train_std = 1.0  # degenerate constant-train guard, never derived from test

        scaled_train = pd.Series((train_values - train_mean) / train_std, index=train.index)

        X_train, y_train = _build_windows(scaled_train, _WINDOW)

        model = _GRURegressor(hidden_size=_HIDDEN_SIZE).to(_DEVICE)
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
        loss_fn = nn.MSELoss()

        if len(X_train) > 0:
            X_train_t = torch.tensor(X_train, dtype=torch.float32, device=_DEVICE).unsqueeze(-1)
            y_train_t = torch.tensor(y_train, dtype=torch.float32, device=_DEVICE)

            model.train()
            for _ in range(_EPOCHS):
                optimizer.zero_grad()
                predictions = model(X_train_t)
                loss = loss_fn(predictions, y_train_t)
                loss.backward()
                optimizer.step()

        # `test`'s windows may reach back into `train`'s own tail (legitimate
        # train-fold information, available before `test` starts) but never
        # into `test`'s own future rows -- concatenating only `train`'s last
        # `_WINDOW` values with the full `test` series gives every `test` row
        # a window built exclusively from data at or before its own position,
        # never past it.
        context = pd.concat([train.tail(_WINDOW), test])
        scaled_context = pd.Series((context.to_numpy(dtype="float64") - train_mean) / train_std, index=context.index)
        X_test, _ = _build_windows(scaled_context, _WINDOW)

        model.eval()
        if len(X_test) == 0:
            return pd.Series(train_mean, index=test.index)

        with torch.no_grad():
            X_test_t = torch.tensor(X_test, dtype=torch.float32, device=_DEVICE).unsqueeze(-1)
            scaled_predictions = model(X_test_t).numpy()

        predictions = scaled_predictions * train_std + train_mean
        return pd.Series(predictions, index=test.index)
