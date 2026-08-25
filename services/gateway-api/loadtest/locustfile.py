"""GW-017: Locust load-test suite driving `gateway-api`'s key endpoints
against a real running Compose stack, so latency/throughput/error-rate
behavior is observable before a real pilot client generates it.

This is observability tooling for a human to read the Locust request-stats
output -- explicitly not a CI gate. No hard SLA/threshold is asserted or
gated on anywhere in this file (no `fail_ratio`/`response_time` assertion,
no custom `LoadTestShape`, no failure-exit-code logic), and none of this
platform's committed CI config invokes this suite.

Authentication for the valid-path tasks is read from the `LOCUST_API_KEY`
env var, set by the operator after running `scripts/provision_tenant.py`
against the target stack (see `loadtest/README.md`) -- never hardcoded here,
and never auto-provisioned by this file itself; provisioning fixture data is
a separate concern owned by GW-005's script.

Run, e.g.:
    locust -f loadtest/locustfile.py --headless -u 5 -r 1 --run-time 30s \
        --host http://localhost:8000
"""

from __future__ import annotations

import os

from locust import HttpUser, task

API_KEY = os.environ.get("LOCUST_API_KEY", "")

DATASET_REFERENCE_PAYLOAD = {
    "dataset_id": "smoke-test",
    "dataset_reference": {"type": "inline", "rows": []},
    "horizon": 1,
    "purge_gap_hours": 0,
    "train_window": 1,
    "test_window": 1,
    "step": 1,
}


class GatewayApiUser(HttpUser):
    """Drives the authenticated `runs` proxy surface (GW-008/GW-016) plus
    one deliberately-unauthenticated request path, so both the "real
    traffic" and "rejected traffic" profiles are visible in the same run.
    """

    def on_start(self) -> None:
        self._auth_headers = {"Authorization": f"Bearer {API_KEY}"}
        response = self.client.post(
            "/runs",
            json=DATASET_REFERENCE_PAYLOAD,
            headers=self._auth_headers,
            name="/runs [seed]",
        )
        body = response.json() if response.ok else {}
        self._run_id = body.get("id", "")

    @task
    def create_run(self) -> None:
        self.client.post(
            "/runs",
            json=DATASET_REFERENCE_PAYLOAD,
            headers=self._auth_headers,
            name="/runs",
        )

    @task
    def get_run(self) -> None:
        if not self._run_id:
            return
        self.client.get(
            f"/runs/{self._run_id}",
            headers=self._auth_headers,
            name="/runs/[id]",
        )

    @task
    def get_run_splits(self) -> None:
        if not self._run_id:
            return
        self.client.get(
            f"/runs/{self._run_id}/splits",
            headers=self._auth_headers,
            name="/runs/[id]/splits",
        )

    @task
    def get_run_unauthenticated(self) -> None:
        """Distinct task, deliberately omitting/mangling the API key, so the
        `401` path (GW-006) is exercised under load alongside the
        authenticated traffic above.
        """
        run_id = self._run_id or "nonexistent"
        self.client.get(
            f"/runs/{run_id}",
            headers={"Authorization": "Bearer invalid-key"},
            name="/runs/[id] [invalid auth]",
        )
