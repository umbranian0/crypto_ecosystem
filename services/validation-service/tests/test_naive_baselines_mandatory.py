"""VS-017 AC (non-tautological): naive baselines cannot be made
skippable/conditional by this ticket's new client-prediction branch.

Mirrors test_repository_interfaces.py's/VS-012's "structurally unreachable"
test style: instead of only exercising the HTTP surface (which could pass by
coincidence even if a future edit added a way to skip Naive0/NaiveLast),
this inspects `runs.py`'s actual source via `ast` and asserts, mechanically,
that:
  - `run_validation_protocol` is called exactly once in `create_run`.
  - `NAIVE0_KEY`/`NAIVE_LAST_KEY` lookups on `split.baseline_results` are
    unconditional statements in the `for split in results:` loop body (not
    inside an `if`/`try` that could skip them), so there is no code path
    that reaches the persistence step without having read both.
  - The only `if` branching on `request.client_prediction_reference` in the
    whole file affects `extra_baselines`/`client_baseline_results`, never the
    NAIVE0_KEY/NAIVE_LAST_KEY lookups themselves or the call shape of
    `run_validation_protocol`.
"""

from __future__ import annotations

import ast
import inspect

from app.routers import runs


def _create_run_function_node() -> ast.FunctionDef:
    source = inspect.getsource(runs)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "create_run":
            return node
    raise AssertionError("create_run function not found in app.routers.runs")


def _calls_to(node: ast.AST, name: str) -> list[ast.Call]:
    calls = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            func = n.func
            if isinstance(func, ast.Name) and func.id == name:
                calls.append(n)
    return calls


def test_run_validation_protocol_called_exactly_once_in_create_run() -> None:
    create_run_node = _create_run_function_node()
    calls = _calls_to(create_run_node, "run_validation_protocol")
    assert len(calls) == 1, (
        "create_run must call run_validation_protocol exactly once, unconditionally -- "
        f"found {len(calls)} call site(s)"
    )


def _subscript_keys_of(node: ast.AST, base_attr_chain: tuple[str, ...]) -> set[str]:
    """Collects the constant string keys used in `split.baseline_results[<key>]`
    -style subscripts anywhere under `node`.
    """
    keys: set[str] = set()
    for n in ast.walk(node):
        if not isinstance(n, ast.Subscript):
            continue
        value = n.value
        if not (isinstance(value, ast.Attribute) and value.attr == base_attr_chain[-1]):
            continue
        key_node = n.slice
        if isinstance(key_node, ast.Name):
            keys.add(key_node.id)
    return keys


def test_naive0_and_naive_last_keys_are_always_read_from_baseline_results() -> None:
    """`split.baseline_results[NAIVE0_KEY]`/`[NAIVE_LAST_KEY]` must both be
    read as plain statements in the loop body -- not nested inside any `if`
    that could be false, which would prove they're skippable.
    """
    create_run_node = _create_run_function_node()

    for_node = None
    for n in ast.walk(create_run_node):
        if isinstance(n, ast.For):
            for_node = n
            break
    assert for_node is not None, "create_run must contain a `for split in results:` loop"

    # The first two statements of the loop body must be the unconditional
    # NAIVE_LAST_KEY/NAIVE0_KEY assignments -- not wrapped in an `if`/`try`.
    top_level_statement_types = [type(stmt) for stmt in for_node.body[:2]]
    assert all(t is ast.Assign for t in top_level_statement_types), (
        "the first statements in the split loop must be unconditional "
        "assignments reading NAIVE_LAST_KEY/NAIVE0_KEY -- found "
        f"{top_level_statement_types}, which would let a conditional "
        "skip them"
    )

    keys_read = _subscript_keys_of(for_node.body[0], ("split", "baseline_results")) | \
        _subscript_keys_of(for_node.body[1], ("split", "baseline_results"))
    assert keys_read == {"NAIVE_LAST_KEY", "NAIVE0_KEY"}


def test_client_prediction_reference_branch_only_touches_extra_baselines_variables() -> None:
    """The only `if` in `create_run` that branches on
    `request.client_prediction_reference` must assign to
    `run_config`/`client_baseline_key`/`client_series`/`client_baseline`
    only -- never reassign `config` itself, never touch NAIVE0_KEY/
    NAIVE_LAST_KEY, and never wrap the run_validation_protocol call itself.
    """
    create_run_node = _create_run_function_node()

    branch_node = None
    for n in ast.walk(create_run_node):
        if isinstance(n, ast.If):
            test = n.test
            if (
                isinstance(test, ast.Compare)
                and isinstance(test.left, ast.Attribute)
                and test.left.attr == "client_prediction_reference"
            ):
                branch_node = n
                break
    assert branch_node is not None, (
        "expected exactly one `if request.client_prediction_reference is not "
        "None:` branch in create_run"
    )

    assigned_names: set[str] = set()
    for stmt in ast.walk(branch_node):
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    assigned_names.add(target.id)

    assert assigned_names <= {"client_series", "client_baseline", "client_baseline_key", "run_config"}
    assert "config" not in assigned_names

    # run_validation_protocol must not be called from inside this branch.
    assert _calls_to(branch_node, "run_validation_protocol") == []
