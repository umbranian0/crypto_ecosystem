"""ECON-005 Test 4: real end-to-end HTTP proof that the service, as actually
wired today (ECON-004's mock-only client, no dependency override), can never
return an eligible simulation -- documented split from `test_eligibility.py`
per ECON-005.md's "implementer's choice, document which".
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.contracts import NotEligibleForSimulation
from app.eligibility import EligibilityReason
from app.main import app

_PROFITABILITY_FIELD_NAMES = {
    "cost_adjusted_return",
    "slippage_adjusted_return",
    "total_cost_bps",
}


def test_4_every_real_request_through_the_actual_running_service_refuses() -> None:
    """Test 4 (ECON-005.md): proves that, as the service is actually wired
    end-to-end (through ECON-004's mock-only client, real `TestClient(app)`,
    no dependency override), every real HTTP call to `POST /simulations`
    returns the refusal shape. Makes 3 distinct real requests (varying
    request bodies) and asserts every one refuses with the same shape --
    Test 3's positive path is reachable only in isolation (direct
    construction inside the test suite), never through this real running
    configuration.
    """
    assert app.dependency_overrides == {}, (
        "Test 4 must run against the real, unmodified DI wiring -- no "
        "dependency override may be present"
    )

    client = TestClient(app)

    request_bodies = [
        {"run_id": "run-A", "fee_schedule_id": "fee-1", "slippage_model_id": "slip-1"},
        {"run_id": "run-B-different", "fee_schedule_id": "fee-2", "slippage_model_id": "slip-2"},
        {"run_id": "run-C-also-different", "fee_schedule_id": "fee-3", "slippage_model_id": "slip-3"},
    ]

    for body in request_bodies:
        response = client.post("/simulations", json=body)

        assert response.status_code in (409, 422), (
            f"request {body} unexpectedly did not refuse: "
            f"{response.status_code} {response.text}"
        )
        parsed = response.json()
        assert set(parsed.keys()) & _PROFITABILITY_FIELD_NAMES == set(), (
            f"refusal body for {body} must not carry any profitability "
            f"field name, found: {parsed.keys()}"
        )
        for key, value in parsed.items():
            if key == "upstream_verdict":
                continue
            assert not isinstance(value, (int, float)), (
                f"top-level refusal field {key!r} must not be numeric for "
                f"request {body}, got {value!r}"
            )
        NotEligibleForSimulation.model_validate(parsed)
        assert parsed["reason_code"] == EligibilityReason.NO_REAL_UPSTREAM_RESULT.value
        assert parsed["upstream_verdict"]["source"] == "mock_fixture"

    assert app.dependency_overrides == {}, (
        "no dependency override should have leaked in during this test"
    )
