"""DASH-009: minimal stub `gateway-api` used only by the Selenium E2E suite.

Design section's option (a), chosen over option (b) (real gateway-api +
validation-service + Postgres/Redis via `infra/docker-compose.yml`): this
suite must not require the full Compose stack to be running to pass, matching
the spirit of the rest of this sprint's mocked-gateway-api unit tests -- just
one hop further down (a real subprocess instead of `httpx.MockTransport`,
since the ticket is explicit "not in-process TestClient" for `dashboard-web`
itself; nothing forbids the *fixture* gateway-api from being a real, small,
separately-run process too).

Implements only the four `gateway-api` endpoints DASH-009's three flows
actually exercise: `GET /health`, `POST /runs`, `GET /runs/{id}`,
`GET /runs/{id}/splits` -- not gateway-api's full contract (GW-006's
X-Api-Key fallback, tenant provisioning, etc. are out of scope for driving
just these three flows). A run is marked `status: "completed"` with fake
per-split results synchronously at creation time (no real validation-service
call), per the ticket Design section's explicit allowance, to keep flow 3
fast and deterministic instead of simulating a real run duration.

Run as its own subprocess by `conftest.py`'s `stub_gateway_api` fixture
(`python -m uvicorn tests.e2e.stub_gateway_api:app`), not imported/executed
in-process by any test.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException, Request

VALID_API_KEY = "e2e-valid-api-key-do-not-use-elsewhere"

app = FastAPI()

_runs: dict[str, dict] = {}


def _require_valid_key(authorization: str | None) -> None:
    if authorization != f"Bearer {VALID_API_KEY}":
        raise HTTPException(status_code=401, detail="invalid api key")


def _fake_split(split_index: int) -> dict:
    return {
        "split_index": split_index,
        "train_start": "2026-01-01T00:00:00Z",
        "train_end": "2026-01-10T00:00:00Z",
        "purge_start": "2026-01-10T00:00:00Z",
        "purge_end": "2026-01-10T01:00:00Z",
        "test_start": "2026-01-10T01:00:00Z",
        "test_end": "2026-01-11T00:00:00Z",
        "model_mae": 1.1,
        "model_rmse": 2.2,
        "model_smape": 3.3,
        "model_mase": 4.4,
        "model_da": 0.5,
        "model_f1": 0.6,
        "model_oos_r2": 0.1,
        "naive0_mae": 1.0,
        "naive0_rmse": 2.0,
        "naive0_smape": 3.0,
        "naive0_mase": 4.0,
        "naive0_da": 0.51,
        "naive0_f1": 0.61,
        "naive0_oos_r2": 0.12,
        "dm_statistic": -0.9,
        "dm_pvalue": 0.42,
        "dm_verdict": "no significant difference",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/runs", status_code=201)
async def create_run(request: Request, authorization: str | None = Header(default=None)) -> dict:
    _require_valid_key(authorization)
    body = await request.json()

    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    _runs[run_id] = {
        "id": run_id,
        "tenant_id": "e2e-tenant",
        "dataset_id": body.get("dataset_id", "e2e-dataset"),
        "horizon": body.get("horizon", 1),
        "purge_gap_hours": body.get("purge_gap_hours", 0),
        "split_config": {
            "train_window": body.get("train_window", 1),
            "test_window": body.get("test_window", 1),
            "step": body.get("step", 1),
        },
        "status": "completed",
        "created_at": now,
        "completed_at": now,
        "failure_reason": None,
        "splits": [_fake_split(0)],
    }
    return {"id": run_id, "status": "completed"}


@app.get("/runs/{run_id}")
def get_run(run_id: str, authorization: str | None = Header(default=None)) -> dict:
    _require_valid_key(authorization)
    run = _runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return {key: value for key, value in run.items() if key != "splits"}


@app.get("/runs/{run_id}/splits")
def get_splits(run_id: str, authorization: str | None = Header(default=None)) -> list[dict]:
    _require_valid_key(authorization)
    run = _runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run["splits"]
