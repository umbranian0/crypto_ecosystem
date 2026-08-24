"""ECON-012 tests: batched equivalents of ECON-005's own four required
tests, applied to `POST /backtests` -- none compressed, per ECON-012.md.

Test 4 lives in this same file (documented choice: the ticket only requires
the four tests exist, not a particular file split; keeping all of them
together here since this is the first and only test module for this
endpoint).
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.contracts import (
    EligibleSimulationResult,
    NotEligibleForSimulation,
    UpstreamValidationResult,
)
from app.dependencies.upstream import get_upstream_client
from app.eligibility import EligibilityDecision, EligibilityReason
from app.main import app

APP_SRC_DIR = Path(__file__).resolve().parent.parent / "src" / "app"

# The exact numeric/profitability field names that must never appear on a
# refusal body -- EligibleSimulationResult's own field names (ECON-003),
# reused unmodified from test_eligibility.py's own precedent.
_PROFITABILITY_FIELD_NAMES = {
    "cost_adjusted_return",
    "slippage_adjusted_return",
    "total_cost_bps",
}


def _assert_refusal_shape(entry: dict) -> None:
    assert set(entry.keys()) & _PROFITABILITY_FIELD_NAMES == set(), (
        f"refusal entry must not carry any EligibleSimulationResult field "
        f"name at its own top level, found: {entry.keys()}"
    )
    assert "reason_code" in entry
    assert "message" in entry
    assert "run_id" in entry
    for key, value in entry.items():
        if key == "upstream_verdict":
            continue
        assert not isinstance(value, (int, float)), (
            f"top-level refusal field {key!r} must not be numeric, got {value!r}"
        )
    NotEligibleForSimulation.model_validate(entry)


def test_1_all_mock_fixture_batch_through_real_endpoint_all_refuse() -> None:
    """Test 1 (batched equivalent of ECON-005's own Test 1): a 3-run-id
    batch, no dependency override, submitted through the real running
    endpoint (ECON-004's real MockValidationResultClient fixture,
    source="mock_fixture" for every run id) -> every entry in the response
    is NotEligibleForSimulation, verified by iterating the actual parsed
    response JSON per entry, not just the outer status code.
    """
    client = TestClient(app)

    response = client.post(
        "/backtests",
        json={
            "run_ids": ["run-1", "run-2", "run-3"],
            "fee_schedule_id": "fee-1",
            "slippage_model_id": "slip-1",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 3
    for entry, expected_run_id in zip(body, ["run-1", "run-2", "run-3"]):
        _assert_refusal_shape(entry)
        assert entry["reason_code"] == EligibilityReason.NO_REAL_UPSTREAM_RESULT.value
        assert entry["upstream_verdict"]["source"] == "mock_fixture"
        assert entry["run_id"] == expected_run_id


def test_2_live_source_but_not_significant_verdict_refuses_in_batch() -> None:
    """Test 2 (batched equivalent): a batch where every run id resolves to
    a hand-constructed UpstreamValidationResult with source="live" but a DM
    verdict that still fails the significance check (dm_verdict != "better")
    -> each entry refuses with the same shape, injected via
    app.dependency_overrides, mirroring ECON-005's Test 2 pattern.
    """
    not_beating_naive = UpstreamValidationResult(
        source="live",
        dm_statistic=0.4,
        dm_pvalue=0.87,
        dm_verdict="no significant difference",
    )

    class _LiveButNotSignificantClient:
        def get_result(self, tenant_id: str, validation_run_id: str) -> UpstreamValidationResult:
            return not_beating_naive

    client = TestClient(app)
    app.dependency_overrides[get_upstream_client] = lambda: _LiveButNotSignificantClient()
    try:
        response = client.post(
            "/backtests",
            json={
                "run_ids": ["run-a", "run-b"],
                "fee_schedule_id": "fee-1",
                "slippage_model_id": "slip-1",
            },
        )
    finally:
        app.dependency_overrides.pop(get_upstream_client, None)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    for entry, expected_run_id in zip(body, ["run-a", "run-b"]):
        _assert_refusal_shape(entry)
        assert entry["reason_code"] == EligibilityReason.UPSTREAM_RESULT_DID_NOT_BEAT_NAIVE.value
        assert entry["upstream_verdict"]["dm_verdict"] == "no significant difference"
        assert entry["run_id"] == expected_run_id


def test_3_positive_control_one_eligible_entry_alongside_refused_entries() -> None:
    """Test 3 (positive control, batched equivalent of ECON-005's own Test
    3). This is reachable ONLY via direct construction/dependency override
    inside this test suite -- no code path in the real running service can
    produce source="live" today (ECON-004: MockValidationResultClient always
    returns source="mock_fixture", and
    app.dependencies.upstream.get_upstream_client -- the only real
    Depends() default wired into the running app -- never returns anything
    else).

    Proves independent per-entry gating, not all-or-nothing: a batch
    containing one eligible run id (hand-constructed source="live" AND
    dm_verdict="better") alongside refused run ids returns the eligible
    entry as a real EligibleSimulationResult with a real numeric value,
    while the refused entries in the same batch still refuse.
    """
    beats_naive_significantly = UpstreamValidationResult(
        source="live",
        dm_statistic=3.21,
        dm_pvalue=0.004,
        dm_verdict="better",
    )
    not_beating_naive = UpstreamValidationResult(
        source="live",
        dm_statistic=0.4,
        dm_pvalue=0.87,
        dm_verdict="no significant difference",
    )
    mock_only = UpstreamValidationResult(
        source="mock_fixture",
        dm_statistic=0.0,
        dm_pvalue=1.0,
        dm_verdict="no significant difference",
    )

    verdicts_by_run_id = {
        "eligible-run": beats_naive_significantly,
        "refused-run-not-significant": not_beating_naive,
        "refused-run-no-live-source": mock_only,
    }

    class _MixedFixtureClient:
        def get_result(self, tenant_id: str, validation_run_id: str) -> UpstreamValidationResult:
            return verdicts_by_run_id[validation_run_id]

    client = TestClient(app)
    app.dependency_overrides[get_upstream_client] = lambda: _MixedFixtureClient()
    try:
        response = client.post(
            "/backtests",
            json={
                "run_ids": list(verdicts_by_run_id.keys()),
                "fee_schedule_id": "fee-1",
                "slippage_model_id": "slip-1",
            },
        )
    finally:
        app.dependency_overrides.pop(get_upstream_client, None)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 3

    eligible_entry, refused_entry_1, refused_entry_2 = body

    EligibleSimulationResult.model_validate(eligible_entry)
    assert eligible_entry["run_id"] == "eligible-run"
    assert isinstance(eligible_entry["cost_adjusted_return"], float)
    assert isinstance(eligible_entry["slippage_adjusted_return"], float)
    assert eligible_entry["total_cost_bps"] >= 0

    _assert_refusal_shape(refused_entry_1)
    assert refused_entry_1["run_id"] == "refused-run-not-significant"
    assert refused_entry_1["reason_code"] == EligibilityReason.UPSTREAM_RESULT_DID_NOT_BEAT_NAIVE.value

    _assert_refusal_shape(refused_entry_2)
    assert refused_entry_2["run_id"] == "refused-run-no-live-source"
    assert refused_entry_2["reason_code"] == EligibilityReason.NO_REAL_UPSTREAM_RESULT.value


def test_4_every_real_request_through_the_actual_running_service_refuses() -> None:
    """Test 4 (batched equivalent of ECON-005's own Test 4) -- exactly as
    load-bearing as that test, not a lesser check. Proves that, as the
    service is actually wired end-to-end (ECON-004's mock-only client, real
    TestClient(app), no dependency override), every real HTTP call to
    POST /backtests returns an all-refused batch. Makes 3 distinct real
    requests (varying run_ids lists) and asserts every entry in every
    response refuses with the same shape.
    """
    assert app.dependency_overrides == {}, (
        "Test 4 must run against the real, unmodified DI wiring -- no "
        "dependency override may be present"
    )

    client = TestClient(app)

    request_bodies = [
        {
            "run_ids": ["run-A"],
            "fee_schedule_id": "fee-1",
            "slippage_model_id": "slip-1",
        },
        {
            "run_ids": ["run-B-1", "run-B-2", "run-B-3"],
            "fee_schedule_id": "fee-2",
            "slippage_model_id": "slip-2",
        },
        {
            "run_ids": ["run-C-only-different"],
            "fee_schedule_id": "fee-3",
            "slippage_model_id": "slip-3",
        },
    ]

    for body in request_bodies:
        response = client.post("/backtests", json=body)

        assert response.status_code == 200, (
            f"request {body} unexpectedly did not succeed with an "
            f"all-refused batch: {response.status_code} {response.text}"
        )
        parsed = response.json()
        assert len(parsed) == len(body["run_ids"])
        for entry, expected_run_id in zip(parsed, body["run_ids"]):
            _assert_refusal_shape(entry)
            assert entry["reason_code"] == EligibilityReason.NO_REAL_UPSTREAM_RESULT.value
            assert entry["upstream_verdict"]["source"] == "mock_fixture"
            assert entry["run_id"] == expected_run_id

    assert app.dependency_overrides == {}, (
        "no dependency override should have leaked in during this test"
    )


def test_batch_handler_calls_check_economic_eligibility_once_per_run_id() -> None:
    """Proves the batch handler calls the exact check_economic_eligibility
    function object (not a reimplementation), by patching it at its import
    site inside app.routers.backtests and asserting it was called once per
    run id, in order.
    """
    call_run_ids: list[str] = []

    def _fake_check(result, request):
        call_run_ids.append(request.run_id)
        return EligibilityDecision(reason=EligibilityReason.NO_REAL_UPSTREAM_RESULT)

    client = TestClient(app)
    with patch(
        "app.routers.backtests.check_economic_eligibility", side_effect=_fake_check
    ) as mocked:
        response = client.post(
            "/backtests",
            json={
                "run_ids": ["run-x", "run-y", "run-z"],
                "fee_schedule_id": "fee-1",
                "slippage_model_id": "slip-1",
            },
        )

    assert response.status_code == 200
    assert mocked.call_count == 3
    assert call_run_ids == ["run-x", "run-y", "run-z"]


def test_backtests_router_imports_check_economic_eligibility_by_name() -> None:
    """AST-based check, belt-and-suspenders alongside the unittest.mock.patch
    test above: routers/backtests.py must import check_economic_eligibility
    from app.eligibility by name (never a parallel reimplementation of its
    two-condition logic), and must never reference
    compute_economic_simulation at all -- mirroring test_eligibility.py's
    own guard structural check for simulations.py.
    """
    source = (APP_SRC_DIR / "routers" / "backtests.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported_from_eligibility: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "app.eligibility":
            imported_from_eligibility.update(alias.name for alias in node.names)

    assert "check_economic_eligibility" in imported_from_eligibility, (
        "routers/backtests.py must import check_economic_eligibility from "
        "app.eligibility by name"
    )
    assert "compute_economic_simulation" not in imported_from_eligibility

    names_referenced: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names_referenced.add(node.id)
        elif isinstance(node, ast.Attribute):
            names_referenced.add(node.attr)

    assert "compute_economic_simulation" not in names_referenced, (
        "routers/backtests.py must never reference compute_economic_simulation "
        "at all -- only check_economic_eligibility's own success branch in "
        "eligibility.py may call it"
    )
