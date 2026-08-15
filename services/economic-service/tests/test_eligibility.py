"""ECON-005 tests: the structural eligibility gate.

Contains the four required tests (sprint-13.md/ECON-005.md's own
non-negotiable list) plus the guard structural-check test. Test 4 (real
end-to-end HTTP, no dependency override) lives in
`tests/test_simulations_endpoint.py` -- documented split, per ECON-005.md's
own "implementer's choice, document which".
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.contracts import (
    EligibleSimulationResult,
    NotEligibleForSimulation,
    SimulationRequest,
    UpstreamValidationResult,
)
from app.dependencies.upstream import get_upstream_client
from app.eligibility import (
    EligibilityReason,
    check_economic_eligibility,
    compute_economic_simulation,
)
from app.main import app

APP_SRC_DIR = Path(__file__).resolve().parent.parent / "src" / "app"

# The exact numeric/profitability field names that must never appear on a
# refusal body -- `EligibleSimulationResult`'s own field names (ECON-003).
_PROFITABILITY_FIELD_NAMES = {
    "cost_adjusted_return",
    "slippage_adjusted_return",
    "total_cost_bps",
}


def _assert_refusal_shape(body: dict) -> None:
    """Shared assertion for Test 1 and Test 2: the parsed response JSON must
    have none of `EligibleSimulationResult`'s own numeric field names at its
    own top level, and must structurally match `NotEligibleForSimulation`
    (which legitimately nests `upstream_verdict.dm_statistic`/`dm_pvalue` --
    DM-test evidence for the refusal, not a profitability figure, per
    ECON-003's own docstring). We iterate the actual parsed JSON's keys and
    types, not just the status code.
    """
    assert set(body.keys()) & _PROFITABILITY_FIELD_NAMES == set(), (
        f"refusal body must not carry any EligibleSimulationResult field "
        f"name at its own top level, found: {body.keys()}"
    )
    assert "reason_code" in body
    assert "message" in body
    # NotEligibleForSimulation itself has zero numeric fields (ECON-003) --
    # confirm no bare int/float leaked in at the top level either, not just
    # the three named profitability fields above. `upstream_verdict` is
    # explicitly excluded: its nested dm_statistic/dm_pvalue are allowed
    # DM-test evidence, not a profitability figure (see docstring above).
    for key, value in body.items():
        if key == "upstream_verdict":
            continue
        assert not isinstance(value, (int, float)), (
            f"top-level refusal field {key!r} must not be numeric, got {value!r}"
        )
    NotEligibleForSimulation.model_validate(body)


def test_1_mock_fixture_result_through_real_endpoint_refuses() -> None:
    """Test 1 (ECON-005.md): ECON-004's real `MockValidationResultClient`
    fixture (`source="mock_fixture"`) submitted through the real endpoint ->
    409/422 `NotEligibleForSimulation`. Asserted by iterating the actual
    parsed response JSON's keys/types, not merely the status code.
    """
    client = TestClient(app)

    response = client.post(
        "/simulations",
        json={
            "run_id": "run-1",
            "fee_schedule_id": "fee-1",
            "slippage_model_id": "slip-1",
        },
    )

    assert response.status_code in (409, 422)
    body = response.json()
    _assert_refusal_shape(body)
    assert body["reason_code"] == EligibilityReason.NO_REAL_UPSTREAM_RESULT.value
    assert body["upstream_verdict"]["source"] == "mock_fixture"


def test_2_live_source_but_not_significant_verdict_refuses() -> None:
    """Test 2 (ECON-005.md): a hand-constructed `UpstreamValidationResult`
    with `source="live"` but a DM verdict indicating the model did NOT beat
    Naive0 -> same refusal shape as Test 1, same key/type assertion.
    """
    not_beating_naive = UpstreamValidationResult(
        source="live",
        dm_statistic=0.4,
        dm_pvalue=0.87,
        dm_verdict="not_significant",
    )
    request = SimulationRequest(run_id="run-2", fee_schedule_id="fee-1", slippage_model_id="slip-1")

    decision = check_economic_eligibility(not_beating_naive, request)

    assert not decision.is_eligible
    assert decision.reason is EligibilityReason.UPSTREAM_RESULT_DID_NOT_BEAT_NAIVE
    assert decision.simulation is None

    # Also exercise the same refusal shape through the real endpoint, with
    # this hand-built result injected via a test-only dependency override --
    # ECON-005.md's own permitted mechanism for reaching a source="live"
    # case ("inject it via a test-only override of the upstream-client
    # dependency -- either is acceptable").
    class _LiveButNotSignificantClient:
        def get_result(self, tenant_id: str, validation_run_id: str) -> UpstreamValidationResult:
            return not_beating_naive

    client = TestClient(app)
    app.dependency_overrides[get_upstream_client] = lambda: _LiveButNotSignificantClient()
    try:
        response = client.post(
            "/simulations",
            json={
                "run_id": "run-2",
                "fee_schedule_id": "fee-1",
                "slippage_model_id": "slip-1",
            },
        )
    finally:
        app.dependency_overrides.pop(get_upstream_client, None)

    assert response.status_code in (409, 422)
    body = response.json()
    _assert_refusal_shape(body)
    assert body["reason_code"] == EligibilityReason.UPSTREAM_RESULT_DID_NOT_BEAT_NAIVE.value
    assert body["upstream_verdict"]["dm_verdict"] == "not_significant"


def test_3_positive_control_live_and_significant_verdict_is_eligible() -> None:
    """Test 3 (positive control, ECON-005.md).

    This is the only place in this sprint's scope where a `source="live"`
    result exists; no code path in the running service can produce one
    today (see ECON-004: `MockValidationResultClient` always returns
    `source="mock_fixture"`, and `app.dependencies.upstream.get_upstream_client`
    -- the only real `Depends()` default wired into the running app -- never
    returns anything else). This object is hand-constructed directly inside
    this test and passed straight into `check_economic_eligibility`/
    `compute_economic_simulation`; it is never reachable through the real
    running service's default wiring.
    """
    beats_naive_significantly = UpstreamValidationResult(
        source="live",
        dm_statistic=3.21,
        dm_pvalue=0.004,
        dm_verdict="significant_outperformance_harvey_corrected",
    )
    request = SimulationRequest(run_id="run-3", fee_schedule_id="fee-1", slippage_model_id="slip-1")

    decision = check_economic_eligibility(beats_naive_significantly, request)

    assert decision.is_eligible
    assert decision.reason is EligibilityReason.ELIGIBLE
    assert isinstance(decision.simulation, EligibleSimulationResult)
    assert decision.simulation.run_id == "run-3"
    assert isinstance(decision.simulation.cost_adjusted_return, float)
    assert isinstance(decision.simulation.slippage_adjusted_return, float)
    assert decision.simulation.total_cost_bps >= 0
    assert decision.simulation.upstream_verdict == beats_naive_significantly

    # Also exercise compute_economic_simulation directly, per ECON-005.md's
    # "call check_economic_eligibility/compute_economic_simulation directly
    # with the hand-built object" wording.
    direct_result = compute_economic_simulation(beats_naive_significantly, request)
    assert isinstance(direct_result, EligibleSimulationResult)
    assert direct_result.run_id == "run-3"


def test_guard_structural_check_computation_function_name_never_appears_in_router() -> None:
    """Guard structural check (ECON-005.md, option (a)): AST-parse
    `src/app/routers/simulations.py` and assert `compute_economic_simulation`
    (the profitability-computation function's exact name) never appears in
    it at all -- neither imported nor called -- proving
    `check_economic_eligibility` is the only path to it. Also confirms
    `compute_economic_simulation` genuinely IS called somewhere in
    `eligibility.py` (the guard's own success branch), so this isn't a
    trivial pass caused by the function being dead code nobody calls at all.
    """
    router_source = (APP_SRC_DIR / "routers" / "simulations.py").read_text(encoding="utf-8")
    router_tree = ast.parse(router_source)

    names_referenced_in_router: set[str] = set()
    for node in ast.walk(router_tree):
        if isinstance(node, ast.Name):
            names_referenced_in_router.add(node.id)
        elif isinstance(node, ast.Attribute):
            names_referenced_in_router.add(node.attr)
        elif isinstance(node, (ast.ImportFrom, ast.Import)):
            for alias in node.names:
                # Track the real imported name (alias.name), never only the
                # asname -- an `import compute_economic_simulation as _x`
                # would otherwise dodge this check by aliasing the name
                # away. asname is tracked too (separately) since call sites
                # would use it, but it must never substitute for the real
                # name.
                names_referenced_in_router.add(alias.name.split(".")[-1])
                if alias.asname:
                    names_referenced_in_router.add(alias.asname)

    assert "compute_economic_simulation" not in names_referenced_in_router, (
        "routers/simulations.py must never reference compute_economic_simulation "
        "at all (import or call) -- only check_economic_eligibility's own "
        "success branch in eligibility.py may call it"
    )
    # Belt-and-suspenders raw substring check directly against the source
    # text (not just the AST-derived name set), so an aliasing trick this
    # AST walk hasn't anticipated still can't slip through. Scoped to
    # non-docstring code only, mirroring test_upstream_client.py's own
    # precedent (`code_without_docstrings`) -- a docstring is allowed to
    # explain in prose that this function is intentionally absent from this
    # module (as this router's own module docstring does) without that
    # explanation triggering a false positive on itself.
    code_without_docstrings = re.sub(r'"""[\s\S]*?"""', "", router_source)
    assert "compute_economic_simulation" not in code_without_docstrings, (
        "the literal string 'compute_economic_simulation' must not appear "
        "in routers/simulations.py's real code (outside docstrings)"
    )
    assert "check_economic_eligibility" in names_referenced_in_router, (
        "routers/simulations.py must call check_economic_eligibility -- it "
        "did not appear as a referenced name at all"
    )

    eligibility_source = (APP_SRC_DIR / "eligibility.py").read_text(encoding="utf-8")
    eligibility_tree = ast.parse(eligibility_source)
    guard_function = next(
        node
        for node in ast.walk(eligibility_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "check_economic_eligibility"
    )
    guard_body_call_names = {
        node.func.id
        for node in ast.walk(guard_function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "compute_economic_simulation" in guard_body_call_names, (
        "check_economic_eligibility's own body must call "
        "compute_economic_simulation on its eligible branch -- it did not, "
        "so this test would pass trivially even if the function were "
        "unreachable from anywhere"
    )
