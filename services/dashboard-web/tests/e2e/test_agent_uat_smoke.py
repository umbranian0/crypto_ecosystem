"""Smoke test for scripts/agent_uat/run_scenario.py's driver logic, run against
the existing stub_gateway_api/live_server fixtures (conftest.py) -- so the
driver's selector/form-handling logic (HTMX button-click submit, <select>
handling, run_id extraction) is proven correct in CI without needing the real
docker-compose stack. Does NOT smoke-test scenarios/admin.json -- the stub
fixture only covers DASH-009's core PoC loop (login/submit/view), not
/ingestion/datasets, /monitoring, /tenants -- see stub_gateway_api.py's own
route list. scenarios/tenant.json's dataset_reference_source step is also not
exercised here for the same reason (no stub /ingestion/datasets endpoint);
this smoke test uses the plain dataset_reference_path field instead, same as
test_core_loop.py's own _VALID_RUN_FORM.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "agent_uat"))
import run_scenario  # noqa: E402  (path must be extended first)

from tests.e2e.stub_gateway_api import VALID_API_KEY

_SMOKE_STEPS = [
    {"name": "login_page", "action": "get", "path": "/login", "screenshot": True},
    {
        "name": "login_submit",
        "action": "fill_and_submit",
        "form_selector": "form[action='/login']",
        "fields": {"api_key": "{api_key}"},
        "screenshot": True,
        "follow_redirect": True,
    },
    {
        "name": "run_new_submit",
        "action": "fill_and_submit",
        "form_selector": "form[action='/runs/new']",
        "fields": {
            "dataset_id": "agent-uat-smoke",
            "dataset_reference_path": "e2e-sample.csv",
            "horizon": "24",
            "purge_gap_hours": "1",
            "train_window": "50",
            "test_window": "10",
            "step": "10",
        },
        "screenshot": True,
        "follow_redirect": True,
    },
    {
        "name": "run_detail",
        "action": "current_page",
        "screenshot": True,
        "verify_against": {
            "method": "GET",
            "path": "/runs/{run_id}",
            "extract_fields": ["status"],
        },
    },
]


def test_driver_runs_login_submit_view_against_stub(driver, live_server, stub_gateway_api, tmp_path) -> None:
    driver.get(f"{live_server}/login")
    driver.delete_all_cookies()

    context = {"api_key": VALID_API_KEY}
    records = []
    for step in _SMOKE_STEPS:
        records.append(
            run_scenario.run_step(
                driver,
                step,
                live_server,
                stub_gateway_api,
                context,
                tmp_path,
                VALID_API_KEY,
                None,
            )
        )

    assert "run_id" in context, "run_new_submit did not redirect to a run detail page"
    run_detail = records[-1]
    assert run_detail.get("verify_error") is None, run_detail.get("verify_error")
    assert run_detail["field_diffs"] == [], run_detail["field_diffs"]
    for record in records:
        if record["screenshot"]:
            assert (tmp_path / record["screenshot"]).exists()
