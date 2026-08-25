"""GW-008: `app.routers.runs` (POST /runs, GET /runs/{id}, GET /runs/{id}/
splits). GW-016: `GET /runs` (list, proxying VS-022's tenant-scoped list
endpoint).

Fakes `validation-service` with `httpx.MockTransport` (ticket Test AC1) whose
handler mimics the real response shapes read directly from
`services/validation-service/src/app/routers/runs.py`/`splits.py` --
including returning a `404` when the requested `run_id` belongs to a
different tenant than the one in the inbound `X-Tenant-Id` header, exactly
as validation-service's own `get_run` (VS-004/007/008) behaves. `httpx.Client`
is used in production code (`app.dependencies.http_client`), so the fake
is wired in via `MockTransport` rather than `ASGITransport` (which only
implements the async transport interface, not the sync one this service's
client needs).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies.auth import get_authenticated_tenant
from app.dependencies.http_client import get_validation_service_client
from app.dependencies.repositories import get_api_key_repository
from app.repositories.interfaces import ApiKeyRecord
from naive_first_common.logging import CorrelationIdMiddleware
from app.routers import runs

RAW_KEY_A = "tenant-a-raw-key"
TENANT_A = "tenant-a"
RAW_KEY_B = "tenant-b-raw-key"
TENANT_B = "tenant-b"

# Seeded directly into the fake backend, owned by TENANT_B -- used by the
# cross-tenant test to prove TENANT_A can never see it (ticket Test AC2).
RUN_OWNED_BY_B = "run-owned-by-b"
RUN_OWNED_BY_A = "run-owned-by-a"

_SEED_RUNS: dict[str, dict] = {
    RUN_OWNED_BY_A: {
        "id": RUN_OWNED_BY_A,
        "tenant_id": TENANT_A,
        "dataset_id": "dataset-a",
        "horizon": 5,
        "purge_gap_hours": 2.0,
        "split_config": {"train_window": 30, "test_window": 7, "step": 7},
        "status": "completed",
        "created_at": "2026-01-01T00:00:00",
        "completed_at": "2026-01-01T00:05:00",
        "failure_reason": None,
    },
    RUN_OWNED_BY_B: {
        "id": RUN_OWNED_BY_B,
        "tenant_id": TENANT_B,
        "dataset_id": "dataset-b",
        "horizon": 3,
        "purge_gap_hours": 1.0,
        "split_config": {"train_window": 20, "test_window": 5, "step": 5},
        "status": "completed",
        "created_at": "2026-01-02T00:00:00",
        "completed_at": "2026-01-02T00:05:00",
        "failure_reason": None,
    },
}

_SPLIT_RECORD = {
    "split_index": 0,
    "train_start": "2026-01-01T00:00:00",
    "train_end": "2026-01-08T00:00:00",
    "purge_start": "2026-01-08T00:00:00",
    "purge_end": "2026-01-08T02:00:00",
    "test_start": "2026-01-08T02:00:00",
    "test_end": "2026-01-15T02:00:00",
    "model_mae": 1.1,
    "model_rmse": 1.2,
    "model_smape": 1.3,
    "model_mase": 1.4,
    "model_da": 0.5,
    "model_f1": 0.6,
    "model_oos_r2": 0.7,
    "naive0_mae": 2.1,
    "naive0_rmse": 2.2,
    "naive0_smape": 2.3,
    "naive0_mase": 2.4,
    "naive0_da": 0.4,
    "naive0_f1": 0.3,
    "naive0_oos_r2": 0.2,
    "dm_statistic": 3.1,
    "dm_pvalue": 0.02,
    "dm_verdict": "model_better",
    "client_baseline": None,
}

_SEED_SPLITS: dict[str, list[dict]] = {RUN_OWNED_BY_A: [_SPLIT_RECORD]}


@dataclass
class FakeValidationService:
    """Records every request it handles (ticket Test AC3: proving the
    outbound call actually carries `X-Tenant-Id`), and mimics
    validation-service's real create/get/get-splits/list behavior, including
    its 404-collapses-both-cases tenant-ownership rule (VS-007/VS-008) and
    VS-022's tenant-scoped `GET /runs` list.
    """

    seen_requests: list[httpx.Request]
    created_runs: dict[str, dict]

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.seen_requests.append(request)
        tenant_id = request.headers.get("x-tenant-id")
        path = request.url.path

        if request.method == "POST" and path == "/runs":
            body = json.loads(request.content)
            new_id = f"run-created-{len(self.created_runs)}"
            record = {
                "id": new_id,
                "tenant_id": tenant_id,
                "dataset_id": body["dataset_id"],
                "horizon": body["horizon"],
                "purge_gap_hours": float(body["purge_gap_hours"]),
                "split_config": {
                    "train_window": body["train_window"],
                    "test_window": body["test_window"],
                    "step": body["step"],
                },
                "status": "completed",
                "created_at": "2026-01-03T00:00:00",
                "completed_at": "2026-01-03T00:05:00",
                "failure_reason": None,
            }
            self.created_runs[new_id] = record
            return httpx.Response(201, json={"id": new_id, "status": "completed"})

        if request.method == "GET" and path == "/runs":
            # Mimics VS-022's own `Query(ge=1, le=100)` 422 for an
            # out-of-range `limit`, forwarded unmodified by GW-016.
            raw_limit = request.url.params.get("limit")
            if raw_limit is not None and int(raw_limit) < 1:
                return httpx.Response(
                    422,
                    json={
                        "detail": [
                            {
                                "type": "greater_than_equal",
                                "loc": ["query", "limit"],
                                "msg": "Input should be greater than or equal to 1",
                            }
                        ]
                    },
                )

            limit = int(raw_limit) if raw_limit is not None else 20
            offset = int(request.url.params.get("offset", 0))

            tenant_runs = [
                run
                for run in {**_SEED_RUNS, **self.created_runs}.values()
                if run["tenant_id"] == tenant_id
            ]
            tenant_runs.sort(key=lambda run: run["created_at"], reverse=True)
            page = tenant_runs[offset : offset + limit]

            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": run["id"],
                            "dataset_id": run["dataset_id"],
                            "horizon": run["horizon"],
                            "status": run["status"],
                            "created_at": run["created_at"],
                            "completed_at": run["completed_at"],
                        }
                        for run in page
                    ],
                    "limit": limit,
                    "offset": offset,
                    "total": len(tenant_runs),
                },
            )

        if request.method == "GET" and path.endswith("/splits"):
            run_id = path.removeprefix("/runs/").removesuffix("/splits")
            run = _SEED_RUNS.get(run_id) or self.created_runs.get(run_id)
            if run is None or run["tenant_id"] != tenant_id:
                return httpx.Response(404, json={"detail": "run not found"})
            return httpx.Response(200, json=_SEED_SPLITS.get(run_id, []))

        if request.method == "GET":
            run_id = path.removeprefix("/runs/")
            run = _SEED_RUNS.get(run_id) or self.created_runs.get(run_id)
            if run is None or run["tenant_id"] != tenant_id:
                return httpx.Response(404, json={"detail": "run not found"})
            return httpx.Response(200, json=run)

        raise AssertionError(f"unexpected request: {request.method} {path}")  # pragma: no cover


@dataclass
class FakeApiKeyRepository:
    records_by_hash: dict[str, ApiKeyRecord]

    def create_key(self, tenant_id: str, key_hash: str) -> ApiKeyRecord:  # pragma: no cover
        raise NotImplementedError

    def get_by_hash(self, key_hash: str) -> ApiKeyRecord | None:
        return self.records_by_hash.get(key_hash)

    def revoke_key(self, tenant_id: str, key_id: str) -> None:  # pragma: no cover
        raise NotImplementedError


def _api_key_record(raw_key: str, tenant_id: str) -> ApiKeyRecord:
    return ApiKeyRecord(
        id=f"key-{tenant_id}",
        tenant_id=tenant_id,
        key_hash=hashlib.sha256(raw_key.encode()).hexdigest(),
        created_at=datetime.now(timezone.utc),
        revoked_at=None,
    )


@pytest.fixture()
def fake_validation_service() -> FakeValidationService:
    return FakeValidationService(seen_requests=[], created_runs={})


@pytest.fixture()
def client(fake_validation_service: FakeValidationService) -> TestClient:
    app = FastAPI()
    app.include_router(runs.router)
    app.add_middleware(CorrelationIdMiddleware)

    key_repo = FakeApiKeyRepository(
        {
            hashlib.sha256(RAW_KEY_A.encode()).hexdigest(): _api_key_record(RAW_KEY_A, TENANT_A),
            hashlib.sha256(RAW_KEY_B.encode()).hexdigest(): _api_key_record(RAW_KEY_B, TENANT_B),
        }
    )
    mock_client = httpx.Client(
        transport=httpx.MockTransport(fake_validation_service.handler),
        base_url="http://validation-service",
    )

    app.dependency_overrides[get_api_key_repository] = lambda: key_repo
    app.dependency_overrides[get_validation_service_client] = lambda: mock_client

    return TestClient(app)


_VALID_RUN_REQUEST = {
    "dataset_id": "dataset-a",
    "dataset_reference": {"kind": "inline", "values": [1, 2, 3]},
    "horizon": 5,
    "purge_gap_hours": 2,
    "train_window": 30,
    "test_window": 7,
    "step": 7,
}


def test_post_runs_forwards_and_returns_response_shape(client: TestClient) -> None:
    response = client.post(
        "/runs", json=_VALID_RUN_REQUEST, headers={"Authorization": f"Bearer {RAW_KEY_A}"}
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body.keys()) == {"id", "status"}
    assert body["status"] == "completed"


def test_get_run_forwards_and_returns_full_detail_shape(client: TestClient) -> None:
    response = client.get(
        f"/runs/{RUN_OWNED_BY_A}", headers={"Authorization": f"Bearer {RAW_KEY_A}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {
        "id",
        "tenant_id",
        "dataset_id",
        "horizon",
        "purge_gap_hours",
        "split_config",
        "status",
        "created_at",
        "completed_at",
        "failure_reason",
    }
    assert body["id"] == RUN_OWNED_BY_A
    assert body["tenant_id"] == TENANT_A


def test_get_splits_forwards_and_returns_full_shape(client: TestClient) -> None:
    response = client.get(
        f"/runs/{RUN_OWNED_BY_A}/splits", headers={"Authorization": f"Bearer {RAW_KEY_A}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert set(body[0].keys()) == set(_SPLIT_RECORD.keys())


def test_cross_tenant_get_run_returns_404(client: TestClient) -> None:
    """Tenant A authenticated, requesting a run_id seeded as owned by tenant
    B -- ticket Test AC2/GW-006's deferred cross-tenant proof. Must get the
    same 404 a nonexistent run would, with no gateway-side branch
    distinguishing the two cases (none exists in this router at all).
    """
    response = client.get(
        f"/runs/{RUN_OWNED_BY_B}", headers={"Authorization": f"Bearer {RAW_KEY_A}"}
    )

    assert response.status_code == 404

    nonexistent_response = client.get(
        "/runs/does-not-exist", headers={"Authorization": f"Bearer {RAW_KEY_A}"}
    )
    assert nonexistent_response.status_code == 404
    assert nonexistent_response.json()["detail"] == response.json()["detail"]


def test_cross_tenant_get_splits_returns_404(client: TestClient) -> None:
    response = client.get(
        f"/runs/{RUN_OWNED_BY_B}/splits", headers={"Authorization": f"Bearer {RAW_KEY_A}"}
    )

    assert response.status_code == 404


def test_same_run_visible_to_owning_tenant(client: TestClient) -> None:
    response = client.get(
        f"/runs/{RUN_OWNED_BY_B}", headers={"Authorization": f"Bearer {RAW_KEY_B}"}
    )

    assert response.status_code == 200
    assert response.json()["tenant_id"] == TENANT_B


def test_outbound_request_carries_authenticated_tenant_x_tenant_id_header(
    client: TestClient, fake_validation_service: FakeValidationService
) -> None:
    client.get(f"/runs/{RUN_OWNED_BY_A}", headers={"Authorization": f"Bearer {RAW_KEY_A}"})

    assert len(fake_validation_service.seen_requests) == 1
    assert fake_validation_service.seen_requests[0].headers["x-tenant-id"] == TENANT_A


def test_missing_auth_returns_401_before_any_downstream_call(
    client: TestClient, fake_validation_service: FakeValidationService
) -> None:
    response = client.get(f"/runs/{RUN_OWNED_BY_A}")

    assert response.status_code == 401
    assert fake_validation_service.seen_requests == []


# --- GW-016: GET /runs (list) ---


def test_get_runs_forwards_and_returns_response_shape(client: TestClient) -> None:
    response = client.get("/runs", headers={"Authorization": f"Bearer {RAW_KEY_A}"})

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"items", "limit", "offset", "total"}
    assert body["limit"] == 20
    assert body["offset"] == 0
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert set(body["items"][0].keys()) == {
        "id",
        "dataset_id",
        "horizon",
        "status",
        "created_at",
        "completed_at",
    }
    assert body["items"][0]["id"] == RUN_OWNED_BY_A


def test_get_runs_forwards_limit_and_offset_unmodified(
    client: TestClient, fake_validation_service: FakeValidationService
) -> None:
    response = client.get(
        "/runs?limit=5&offset=10", headers={"Authorization": f"Bearer {RAW_KEY_A}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 5
    assert body["offset"] == 10

    seen = fake_validation_service.seen_requests[-1]
    assert seen.url.params["limit"] == "5"
    assert seen.url.params["offset"] == "10"


def test_cross_tenant_get_runs_never_returns_other_tenants_run(client: TestClient) -> None:
    """Non-tautological cross-tenant proof (ticket Test AC): tenant A's
    list never contains tenant B's seeded run, asserted by id -- not just a
    count check.
    """
    response = client.get("/runs", headers={"Authorization": f"Bearer {RAW_KEY_A}"})

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["items"]}
    assert ids == {RUN_OWNED_BY_A}
    assert RUN_OWNED_BY_B not in ids


def test_get_runs_downstream_422_passes_through_unmodified(client: TestClient) -> None:
    response = client.get(
        "/runs?limit=0", headers={"Authorization": f"Bearer {RAW_KEY_A}"}
    )

    assert response.status_code == 422


def test_correlation_id_on_inbound_request_is_forwarded_downstream(
    client: TestClient, fake_validation_service: FakeValidationService
) -> None:
    """OPS-006: the correlation id CorrelationIdMiddleware assigns to the
    inbound gateway-api request must be the exact same id forwarded to
    validation-service via build_downstream_headers -- proven end to end
    through the real proxying path, not asserted against a mocked constant.
    """
    response = client.get(
        f"/runs/{RUN_OWNED_BY_A}",
        headers={"Authorization": f"Bearer {RAW_KEY_A}", "X-Correlation-Id": "caller-supplied-id"},
    )

    assert response.status_code == 200
    assert response.headers["X-Correlation-Id"] == "caller-supplied-id"

    assert len(fake_validation_service.seen_requests) == 1
    forwarded = fake_validation_service.seen_requests[0].headers["x-correlation-id"]
    assert forwarded == "caller-supplied-id"


def test_correlation_id_generated_when_absent_is_forwarded_downstream(
    client: TestClient, fake_validation_service: FakeValidationService
) -> None:
    response = client.get(
        f"/runs/{RUN_OWNED_BY_A}", headers={"Authorization": f"Bearer {RAW_KEY_A}"}
    )

    assert response.status_code == 200
    inbound_generated = response.headers["X-Correlation-Id"]
    assert inbound_generated

    assert len(fake_validation_service.seen_requests) == 1
    forwarded = fake_validation_service.seen_requests[0].headers["x-correlation-id"]
    assert forwarded == inbound_generated
