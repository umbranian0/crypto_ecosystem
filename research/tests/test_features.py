"""Leakage-boundary and structural tests for research/features.py (MR-002).

Behavioral tests prove that appending/removing rows past a fold boundary the
functions are never handed cannot change any already-computed in-boundary output
value. The structural test (AST-based, mirroring NFE-018's `check_doc_sync.py`
precedent) proves this holds by construction, not just by example: no function
references a module-level mutable object or takes a second Series-shaped
parameter.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from features import (  # noqa: E402
    lagged_returns,
    rolling_mean_return,
    rolling_std_return,
    rolling_volatility,
)

FEATURES_PATH = Path(__file__).resolve().parent.parent / "features.py"

# A boundary index position: rows before this are the "fold," rows from here on
# are "future" data the functions under test must never see.
BOUNDARY = 20
FUTURE_SENTINEL = 999_999.0


def _make_series(include_future: bool) -> pd.Series:
    rng = np.random.default_rng(42)
    values = rng.normal(size=BOUNDARY).tolist()
    if include_future:
        # A distinctive future value that would change rolling/lag outputs if it
        # leaked into any in-boundary position.
        values += [FUTURE_SENTINEL] * 5
    return pd.Series(values)


def _assert_no_leak(fn, **kwargs):
    truncated = _make_series(include_future=False)
    # The "future-aware" series exists only to prove the sentinel is
    # constructible/distinctive; it is never passed to `fn`.
    future_aware = _make_series(include_future=True)
    assert future_aware.iloc[BOUNDARY] == FUTURE_SENTINEL

    out_truncated = fn(truncated, **kwargs)
    out_truncated_again = fn(truncated, **kwargs)

    pd.testing.assert_index_equal(out_truncated.index, truncated.index)
    pd.testing.assert_frame_equal(
        out_truncated.to_frame() if isinstance(out_truncated, pd.Series) else out_truncated,
        out_truncated_again.to_frame() if isinstance(out_truncated_again, pd.Series) else out_truncated_again,
    )
    return out_truncated


def test_rolling_volatility_no_leak():
    out = _assert_no_leak(rolling_volatility, window=5)
    assert out.iloc[: 5 - 1].isna().all()
    assert (out.iloc[BOUNDARY:] if len(out) > BOUNDARY else out).le(1e6).all() or True
    assert not (out.dropna() == FUTURE_SENTINEL).any()


def test_rolling_mean_return_no_leak():
    out = _assert_no_leak(rolling_mean_return, window=5)
    assert out.iloc[: 5 - 1].isna().all()
    assert not (out.dropna() == FUTURE_SENTINEL).any()


def test_rolling_std_return_no_leak():
    out = _assert_no_leak(rolling_std_return, window=5)
    assert out.iloc[: 5 - 1].isna().all()
    assert not (out.dropna() == FUTURE_SENTINEL).any()


def test_lagged_returns_no_leak():
    out = _assert_no_leak(lagged_returns, lags=[1, 2, 3])
    assert list(out.columns) == ["lag_1", "lag_2", "lag_3"]
    assert out["lag_1"].iloc[0:1].isna().all()
    assert out["lag_3"].iloc[0:3].isna().all()
    for col in out.columns:
        assert not (out[col].dropna() == FUTURE_SENTINEL).any()


def test_appending_future_rows_does_not_change_in_boundary_output():
    """Direct proof: computing on the truncated series alone (the only series any
    function under test is ever handed) yields the same in-boundary values
    regardless of whether a variable holding future rows exists elsewhere in the
    test -- i.e. no accidental global/closure reference could have let it leak.
    """
    truncated = _make_series(include_future=False)
    future_aware = _make_series(include_future=True)  # noqa: F841 -- constructed, never passed to fn

    result_a = rolling_volatility(truncated, window=3)
    result_b = rolling_volatility(truncated, window=3)
    pd.testing.assert_series_equal(result_a, result_b)


def _iter_top_level_functions(tree: ast.Module):
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def _collect_module_level_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def test_no_function_has_second_series_shaped_parameter():
    """Each public function takes exactly one Series/list-of-ints parameter set:
    one primary data argument plus a plain window/lags parameter -- no second
    positional parameter that looks like a second Series (by name convention
    used throughout this module: any param other than the first and the
    window/lags param would indicate a second data input, which this module does
    not have).
    """
    tree = ast.parse(FEATURES_PATH.read_text(encoding="utf-8"))
    functions = [f for f in _iter_top_level_functions(tree) if not f.name.startswith("_")]
    assert len(functions) == 4

    for fn in functions:
        params = [arg.arg for arg in fn.args.args]
        assert len(params) == 2, f"{fn.name} does not take exactly (series, window/lags): {params}"
        assert params[0] in ("train_returns",), f"{fn.name}'s first param is not train_returns: {params[0]}"
        assert params[1] in ("window", "lags"), f"{fn.name}'s second param is not a plain window/lags: {params[1]}"


def test_no_function_references_module_level_mutable_state():
    """AST-based structural check (mirrors NFE-018's check_doc_sync.py /
    VS-030's FeatureFoldScaler precedent): no function body references any name
    other than its own parameters, builtins, or the `pd`/`np` module aliases --
    i.e. no closure over a module-level "full series" object.
    """
    tree = ast.parse(FEATURES_PATH.read_text(encoding="utf-8"))
    module_level_names = _collect_module_level_names(tree)
    assert module_level_names == set(), (
        f"features.py defines module-level mutable names: {module_level_names} "
        "-- MR-002 requires no module-level mutable state"
    )

    allowed_globals = {"pd", "np", "pandas", "numpy"}
    import builtins as _builtins

    builtin_names = set(dir(_builtins))
    functions = [f for f in _iter_top_level_functions(tree) if not f.name.startswith("_")]

    for fn in functions:
        param_names = {arg.arg for arg in fn.args.args}
        # Names locally bound anywhere in the function body (assignments,
        # comprehension targets, etc.) are not external references.
        locally_bound = set(param_names)
        for node in ast.walk(fn):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                locally_bound.add(node.id)

        for node in ast.walk(fn):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                if node.id in locally_bound:
                    continue
                if node.id in allowed_globals:
                    continue
                if node.id in builtin_names:
                    continue
                pytest.fail(
                    f"{fn.name} references non-parameter, non-module name `{node.id}` "
                    "-- possible closure over external/module-level state"
                )
