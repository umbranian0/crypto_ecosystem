"""Tests for ECON-003's economic-service contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.contracts import (
    EligibleSimulationResult,
    NotEligibleForSimulation,
    SimulationRequest,
    UpstreamValidationResult,
)


def _upstream_verdict(**overrides) -> dict:
    payload = {
        "source": "mock_fixture",
        "dm_statistic": -1.23,
        "dm_pvalue": 0.87,
        "dm_verdict": "not_significant",
    }
    payload.update(overrides)
    return payload


def test_simulation_request_valid():
    req = SimulationRequest(
        run_id="run-1",
        fee_schedule_id="fee-standard",
        slippage_model_id="slippage-linear",
    )
    assert req.run_id == "run-1"


def test_upstream_validation_result_rejects_bare_string_source():
    with pytest.raises(ValidationError):
        UpstreamValidationResult(**_upstream_verdict(source="not_a_real_source"))


def test_eligible_simulation_result_valid():
    result = EligibleSimulationResult(
        run_id="run-1",
        cost_adjusted_return=0.041,
        slippage_adjusted_return=0.037,
        total_cost_bps=12.5,
        upstream_verdict=_upstream_verdict(),
    )
    assert result.total_cost_bps == 12.5


def test_not_eligible_for_simulation_valid_without_upstream_verdict():
    result = NotEligibleForSimulation(
        reason_code="no_upstream_verdict",
        message="No validation-service run has been provided.",
    )
    assert result.upstream_verdict is None


def test_not_eligible_for_simulation_valid_with_upstream_verdict():
    result = NotEligibleForSimulation(
        reason_code="not_significant",
        message="Upstream DM verdict did not show significant outperformance.",
        upstream_verdict=_upstream_verdict(),
    )
    assert result.upstream_verdict.dm_verdict == "not_significant"


def test_eligible_simulation_result_rejects_not_eligible_shape():
    with pytest.raises(ValidationError):
        EligibleSimulationResult(
            reason_code="not_significant",
            message="Upstream DM verdict did not show significant outperformance.",
        )


def test_not_eligible_for_simulation_rejects_eligible_shape():
    with pytest.raises(ValidationError):
        NotEligibleForSimulation(
            run_id="run-1",
            cost_adjusted_return=0.041,
            slippage_adjusted_return=0.037,
            total_cost_bps=12.5,
        )


def test_eligible_and_not_eligible_schemas_have_disjoint_numeric_fields():
    def numeric_field_names(schema: dict) -> set[str]:
        names = set()
        for name, prop in schema["properties"].items():
            prop_type = prop.get("type")
            any_of_types = {entry.get("type") for entry in prop.get("anyOf", [])}
            if prop_type in {"number", "integer"} or any_of_types & {
                "number",
                "integer",
            }:
                names.add(name)
        return names

    eligible_numeric = numeric_field_names(EligibleSimulationResult.model_json_schema())
    not_eligible_numeric = numeric_field_names(
        NotEligibleForSimulation.model_json_schema()
    )

    assert eligible_numeric == {
        "cost_adjusted_return",
        "slippage_adjusted_return",
        "total_cost_bps",
    }
    assert not_eligible_numeric == set()
    assert eligible_numeric.isdisjoint(not_eligible_numeric)
