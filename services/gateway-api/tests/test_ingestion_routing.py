"""GW-019: `app.routers.ingestion` (`POST /ingestion/connectors/{source}/run`).

Fakes `ingestion-service` with `httpx.MockTransport` (same pattern
`test_reports_routing.py`/`test_operator_routing.py` already use), mirroring
`GW-016`'s test shape: happy path (202, response forwarded unmodified),
downstream timeout (504), downstream connection refused (502). Unlike
`test_operator_routing.py`'s `operator`-gated route, this route is
tenant-authenticated (`get_authenticated_tenant`, GW-006) -- proven here via
the same API-key fixture pattern `test_reports_routing.py` uses, not
`test_operator_auth.py`'s operator-token one.

GW-020: extends `FakeIngestionService.handler` with `GET /datasets`/
`GET /datasets/{source}/series` branches and adds a parallel set of test
functions for those two new routes, mirroring this same test shape (happy
path, downstream 404, downstream timeout/connection-refused, tenant-identity
forwarding, 401-before-any-downstream-call) rather than a second test module.

GW-023: extends `FakeIngestionService.handler` with a `since=1900-01-01`
branch simulating `INGEST-013`'s downstream rejection, and adds tests proving
`run_connector`'s new `since` query parameter is forwarded unmodified when
supplied, omitted entirely when absent, and that the downstream `422` is
forwarded as-is. Generic 401/502/504/tenant-header cases for this route are
already covered above and are not duplicated here.

GW-024: `INGEST-015` changes the downstream `POST /connectors/{source}/run`
contract to `202` immediately with `{source, status: "queued", since,
queued_at}` instead of blocking for the crawl's final outcome, and adds a
`409` ("crawl already in progress") outcome. `FakeIngestionService`'s main
success branch is updated to return the new `queued` shape (replacing the old
`status: "completed"`/`row_count`/`fetched_at` body, so no stale expectation
of that shape lingers anywhere in this file), and gains a
`simulate_conflict` flag returning `409` for the same route, checked ahead of
the success branch. Proves -- rather than assumes -- that `run_connector`'s
generic pass-through already forwards both outcomes unmodified with zero
code change (ticket GW-024's own Analysis claim).

GW-027: `FakeIngestionService.handler` gains `POST /connectors/{source}/
cancel` branches (`202` success with `{source, status: "cancelling"}`, `404`
unknown source, `409` nothing in flight to cancel via a `simulate_cancel_
conflict` flag) and adds a parallel set of test functions for the new
`cancel_connector` route, mirroring this same test shape (happy path,
downstream `404`/`409` forwarded unmodified, tenant-identity forwarding) --
generic 401/502/504 cases for this route are not duplicated here, matching
GW-023's own precedent of not re-covering ground already proven above.

GW-028: `INGEST-021`/`INGEST-024` extend the downstream `GET /connectors/
{source}/status` contract with a six-value status vocabulary (`queued`/
`running`/`cancelling`/`cancelled`/`completed`/`failed`) and two new fields,
`rows_fetched_so_far`/`updated_at`. `FakeIngestionService.handler` gains four
new source-specific branches -- `running`, `cancelling`, and `cancelled`
status values (each a distinct mocked response, not the same body reused
under different test names), plus a `blockchain_onchain_btc_midcrawl` branch
whose `rows_fetched_so_far`/`updated_at` are `null`, mirroring the real
shape difference between Binance/Reddit (which track row progress) and
blockchain.info (`INGEST-024`/`INGEST-027`, which does not). Proves --
rather than assumes -- that `connector_status`'s existing `-> dict`
pass-through already forwards the new status values and fields unmodified
with zero code change (ticket GW-028's own Analysis claim).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies.auth import get_authenticated_tenant
from app.dependencies.http_client import get_ingestion_service_client
from app.dependencies.repositories import get_api_key_repository
from app.repositories.interfaces import ApiKeyRecord
from app.routers import ingestion

RAW_KEY_A = "tenant-a-raw-key"
TENANT_A = "tenant-a"


@dataclass
class FakeIngestionService:
    seen_requests: list[httpx.Request]
    simulate_connect_error: bool = False
    simulate_timeout: bool = False
    simulate_conflict: bool = False
    simulate_cancel_conflict: bool = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.simulate_connect_error:
            raise httpx.ConnectError("connection refused", request=request)
        if self.simulate_timeout:
            raise httpx.TimeoutException("timed out", request=request)

        self.seen_requests.append(request)
        path = request.url.path

        if (
            request.method == "POST"
            and path == "/connectors/binance_price_btcusdt_1h/run"
            and request.url.params.get("since") == "1900-01-01"
        ):
            return httpx.Response(
                422,
                json={
                    "detail": "since='1900-01-01' predates this connector's verified earliest-available date"
                },
            )
        if (
            request.method == "POST"
            and path == "/connectors/binance_price_btcusdt_1h/run"
            and self.simulate_conflict
        ):
            return httpx.Response(
                409,
                json={
                    "detail": "crawl already in progress for connector 'binance_price_btcusdt_1h'"
                },
            )
        if request.method == "POST" and path == "/connectors/binance_price_btcusdt_1h/run":
            return httpx.Response(
                202,
                json={
                    "source": "binance_price_btcusdt_1h",
                    "status": "queued",
                    "since": None,
                    "queued_at": "2026-01-02T00:00:00",
                },
            )
        if request.method == "POST" and path == "/connectors/unknown_source/run":
            return httpx.Response(404, json={"detail": "unknown connector source 'unknown_source'"})
        if request.method == "POST" and path == "/connectors/reddit_vader_sentiment/run":
            return httpx.Response(
                422,
                json={"detail": "no credentials stored for connector 'reddit_vader_sentiment' and this tenant"},
            )
        if request.method == "GET" and path == "/datasets":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "source": "binance_price_btcusdt_1h",
                            "earliest_timestamp": "2026-01-01T00:00:00",
                            "latest_timestamp": "2026-01-02T00:00:00",
                            "row_count": 24,
                        }
                    ]
                },
            )
        if (
            request.method == "GET"
            and path == "/datasets/binance_price_btcusdt_1h/series"
            and request.url.params.get("field") == "bogus"
        ):
            return httpx.Response(400, json={"detail": "unknown field 'bogus'"})
        if request.method == "GET" and path == "/datasets/binance_price_btcusdt_1h/series":
            return httpx.Response(
                200,
                json={
                    "timestamps": ["2026-01-01T00:00:00", "2026-01-01T01:00:00"],
                    "values": [42000.0, 42100.0],
                },
            )
        if request.method == "GET" and path == "/datasets/unknown_source/series":
            return httpx.Response(404, json={"detail": "dataset not found"})
        if request.method == "GET" and path == "/connectors/binance_price_btcusdt_1h/status":
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "timestamp": "2026-01-02T00:00:00",
                    "row_count": 24,
                },
            )
        if request.method == "GET" and path == "/connectors/no_crawl_yet/status":
            return httpx.Response(404, json={"detail": "no crawl runs recorded for this source"})
        if request.method == "GET" and path == "/connectors/binance_price_btcusdt_1h_midcrawl/status":
            return httpx.Response(
                200,
                json={
                    "status": "running",
                    "timestamp": "2026-01-02T00:05:00",
                    "row_count": 4200,
                    "rows_fetched_so_far": 4200,
                    "updated_at": "2026-01-02T00:05:00",
                },
            )
        if request.method == "GET" and path == "/connectors/binance_price_btcusdt_1h_cancelling/status":
            return httpx.Response(
                200,
                json={
                    "status": "cancelling",
                    "timestamp": "2026-01-02T00:06:00",
                    "row_count": 5000,
                    "rows_fetched_so_far": 5000,
                    "updated_at": "2026-01-02T00:06:00",
                },
            )
        if request.method == "GET" and path == "/connectors/binance_price_btcusdt_1h_cancelled/status":
            return httpx.Response(
                200,
                json={
                    "status": "cancelled",
                    "timestamp": "2026-01-02T00:07:00",
                    "row_count": 5000,
                    "rows_fetched_so_far": 5000,
                    "updated_at": "2026-01-02T00:07:00",
                },
            )
        if request.method == "GET" and path == "/connectors/blockchain_onchain_btc_midcrawl/status":
            return httpx.Response(
                200,
                json={
                    "status": "running",
                    "timestamp": "2026-01-02T00:05:00",
                    "row_count": None,
                    "rows_fetched_so_far": None,
                    "updated_at": None,
                },
            )
        if (
            request.method == "POST"
            and path == "/connectors/binance_price_btcusdt_1h/cancel"
            and self.simulate_cancel_conflict
        ):
            return httpx.Response(
                409,
                json={"detail": "nothing in flight to cancel for connector 'binance_price_btcusdt_1h'"},
            )
        if request.method == "POST" and path == "/connectors/binance_price_btcusdt_1h/cancel":
            return httpx.Response(
                202,
                json={"source": "binance_price_btcusdt_1h", "status": "cancelling"},
            )
        if request.method == "POST" and path == "/connectors/unknown_source/cancel":
            return httpx.Response(404, json={"detail": "unknown connector source 'unknown_source'"})

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
def fake_ingestion_service() -> FakeIngestionService:
    return FakeIngestionService(seen_requests=[])


def _build_client(fake_ingestion_service: FakeIngestionService) -> TestClient:
    app = FastAPI()
    app.include_router(ingestion.router)

    key_repo = FakeApiKeyRepository(
        {hashlib.sha256(RAW_KEY_A.encode()).hexdigest(): _api_key_record(RAW_KEY_A, TENANT_A)}
    )
    mock_client = httpx.Client(
        transport=httpx.MockTransport(fake_ingestion_service.handler),
        base_url="http://internal-ingestion-service.example",
    )

    app.dependency_overrides[get_api_key_repository] = lambda: key_repo
    app.dependency_overrides[get_ingestion_service_client] = lambda: mock_client

    return TestClient(app)


@pytest.fixture()
def client(fake_ingestion_service: FakeIngestionService) -> TestClient:
    return _build_client(fake_ingestion_service)


def test_run_connector_forwards_queued_202_response_shape(client: TestClient) -> None:
    response = client.post(
        "/ingestion/connectors/binance_price_btcusdt_1h/run",
        headers={"Authorization": f"Bearer {RAW_KEY_A}"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body == {
        "source": "binance_price_btcusdt_1h",
        "status": "queued",
        "since": None,
        "queued_at": "2026-01-02T00:00:00",
    }


def test_run_connector_conflict_returns_409_forwarded_unmodified() -> None:
    fake = FakeIngestionService(seen_requests=[], simulate_conflict=True)
    client = _build_client(fake)

    response = client.post(
        "/ingestion/connectors/binance_price_btcusdt_1h/run",
        headers={"Authorization": f"Bearer {RAW_KEY_A}"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "crawl already in progress for connector 'binance_price_btcusdt_1h'"
    )


def test_unknown_source_returns_404_forwarded_unmodified(client: TestClient) -> None:
    response = client.post(
        "/ingestion/connectors/unknown_source/run",
        headers={"Authorization": f"Bearer {RAW_KEY_A}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "unknown connector source 'unknown_source'"


def test_missing_credentials_returns_422_forwarded_unmodified(client: TestClient) -> None:
    response = client.post(
        "/ingestion/connectors/reddit_vader_sentiment/run",
        headers={"Authorization": f"Bearer {RAW_KEY_A}"},
    )

    assert response.status_code == 422
    assert "no credentials stored" in response.json()["detail"]


def test_outbound_request_carries_authenticated_tenant_x_tenant_id_header(
    client: TestClient, fake_ingestion_service: FakeIngestionService
) -> None:
    client.post(
        "/ingestion/connectors/binance_price_btcusdt_1h/run",
        headers={"Authorization": f"Bearer {RAW_KEY_A}"},
    )

    assert len(fake_ingestion_service.seen_requests) == 1
    assert fake_ingestion_service.seen_requests[0].headers["x-tenant-id"] == TENANT_A


def test_missing_auth_returns_401_before_any_downstream_call(
    client: TestClient, fake_ingestion_service: FakeIngestionService
) -> None:
    response = client.post("/ingestion/connectors/binance_price_btcusdt_1h/run")

    assert response.status_code == 401
    assert fake_ingestion_service.seen_requests == []


def test_connection_failure_returns_502() -> None:
    fake = FakeIngestionService(seen_requests=[], simulate_connect_error=True)
    client = _build_client(fake)

    response = client.post(
        "/ingestion/connectors/binance_price_btcusdt_1h/run",
        headers={"Authorization": f"Bearer {RAW_KEY_A}"},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "downstream service unavailable"
    assert "internal-ingestion-service" not in response.text


def test_timeout_returns_504() -> None:
    fake = FakeIngestionService(seen_requests=[], simulate_timeout=True)
    client = _build_client(fake)

    response = client.post(
        "/ingestion/connectors/binance_price_btcusdt_1h/run",
        headers={"Authorization": f"Bearer {RAW_KEY_A}"},
    )

    assert response.status_code == 504
    assert response.json()["detail"] == "downstream service timed out"


# GW-023: `POST /ingestion/connectors/{source}/run` `since` forwarding


def test_run_connector_forwards_since_query_param_unmodified(
    client: TestClient, fake_ingestion_service: FakeIngestionService
) -> None:
    response = client.post(
        "/ingestion/connectors/binance_price_btcusdt_1h/run",
        params={"since": "2020-01-01"},
        headers={"Authorization": f"Bearer {RAW_KEY_A}"},
    )

    assert response.status_code == 202
    assert len(fake_ingestion_service.seen_requests) == 1
    assert fake_ingestion_service.seen_requests[0].url.params["since"] == "2020-01-01"


def test_run_connector_omits_since_query_param_when_not_supplied(
    client: TestClient, fake_ingestion_service: FakeIngestionService
) -> None:
    response = client.post(
        "/ingestion/connectors/binance_price_btcusdt_1h/run",
        headers={"Authorization": f"Bearer {RAW_KEY_A}"},
    )

    assert response.status_code == 202
    assert len(fake_ingestion_service.seen_requests) == 1
    assert "since" not in fake_ingestion_service.seen_requests[0].url.params


def test_run_connector_since_predates_earliest_available_returns_422_forwarded_unmodified(
    client: TestClient,
) -> None:
    response = client.post(
        "/ingestion/connectors/binance_price_btcusdt_1h/run",
        params={"since": "1900-01-01"},
        headers={"Authorization": f"Bearer {RAW_KEY_A}"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "since='1900-01-01' predates this connector's verified earliest-available date"
    )


# GW-020: `GET /ingestion/datasets`


def test_list_datasets_forwards_and_returns_response_shape(client: TestClient) -> None:
    response = client.get(
        "/ingestion/datasets",
        headers={"Authorization": f"Bearer {RAW_KEY_A}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "source": "binance_price_btcusdt_1h",
                "earliest_timestamp": "2026-01-01T00:00:00",
                "latest_timestamp": "2026-01-02T00:00:00",
                "row_count": 24,
            }
        ]
    }


def test_list_datasets_outbound_request_carries_tenant_id_header(
    client: TestClient, fake_ingestion_service: FakeIngestionService
) -> None:
    client.get("/ingestion/datasets", headers={"Authorization": f"Bearer {RAW_KEY_A}"})

    assert len(fake_ingestion_service.seen_requests) == 1
    assert fake_ingestion_service.seen_requests[0].headers["x-tenant-id"] == TENANT_A


def test_list_datasets_missing_auth_returns_401_before_any_downstream_call(
    client: TestClient, fake_ingestion_service: FakeIngestionService
) -> None:
    response = client.get("/ingestion/datasets")

    assert response.status_code == 401
    assert fake_ingestion_service.seen_requests == []


def test_list_datasets_connection_failure_returns_502() -> None:
    fake = FakeIngestionService(seen_requests=[], simulate_connect_error=True)
    client = _build_client(fake)

    response = client.get("/ingestion/datasets", headers={"Authorization": f"Bearer {RAW_KEY_A}"})

    assert response.status_code == 502
    assert response.json()["detail"] == "downstream service unavailable"
    assert "internal-ingestion-service" not in response.text


def test_list_datasets_timeout_returns_504() -> None:
    fake = FakeIngestionService(seen_requests=[], simulate_timeout=True)
    client = _build_client(fake)

    response = client.get("/ingestion/datasets", headers={"Authorization": f"Bearer {RAW_KEY_A}"})

    assert response.status_code == 504
    assert response.json()["detail"] == "downstream service timed out"


# GW-020: `GET /ingestion/datasets/{source}/series`


def test_read_series_forwards_query_params_and_returns_response_shape(
    client: TestClient, fake_ingestion_service: FakeIngestionService
) -> None:
    response = client.get(
        "/ingestion/datasets/binance_price_btcusdt_1h/series",
        params={"start": "2026-01-01T00:00:00", "end": "2026-01-01T02:00:00", "field": "close"},
        headers={"Authorization": f"Bearer {RAW_KEY_A}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "timestamps": ["2026-01-01T00:00:00", "2026-01-01T01:00:00"],
        "values": [42000.0, 42100.0],
    }
    assert len(fake_ingestion_service.seen_requests) == 1
    forwarded = fake_ingestion_service.seen_requests[0]
    assert forwarded.url.params["start"] == "2026-01-01T00:00:00"
    assert forwarded.url.params["end"] == "2026-01-01T02:00:00"
    assert forwarded.url.params["field"] == "close"


def test_read_series_unknown_or_cross_tenant_source_returns_404_forwarded_unmodified(
    client: TestClient,
) -> None:
    response = client.get(
        "/ingestion/datasets/unknown_source/series",
        headers={"Authorization": f"Bearer {RAW_KEY_A}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "dataset not found"


def test_read_series_bad_field_returns_400_forwarded_unmodified(client: TestClient) -> None:
    response = client.get(
        "/ingestion/datasets/binance_price_btcusdt_1h/series",
        params={"field": "bogus"},
        headers={"Authorization": f"Bearer {RAW_KEY_A}"},
    )

    assert response.status_code == 400
    assert "unknown field" in response.json()["detail"]


def test_read_series_outbound_request_carries_tenant_id_header(
    client: TestClient, fake_ingestion_service: FakeIngestionService
) -> None:
    client.get(
        "/ingestion/datasets/binance_price_btcusdt_1h/series",
        headers={"Authorization": f"Bearer {RAW_KEY_A}"},
    )

    assert len(fake_ingestion_service.seen_requests) == 1
    assert fake_ingestion_service.seen_requests[0].headers["x-tenant-id"] == TENANT_A


def test_read_series_missing_auth_returns_401_before_any_downstream_call(
    client: TestClient, fake_ingestion_service: FakeIngestionService
) -> None:
    response = client.get("/ingestion/datasets/binance_price_btcusdt_1h/series")

    assert response.status_code == 401
    assert fake_ingestion_service.seen_requests == []


def test_read_series_connection_failure_returns_502() -> None:
    fake = FakeIngestionService(seen_requests=[], simulate_connect_error=True)
    client = _build_client(fake)

    response = client.get(
        "/ingestion/datasets/binance_price_btcusdt_1h/series",
        headers={"Authorization": f"Bearer {RAW_KEY_A}"},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "downstream service unavailable"
    assert "internal-ingestion-service" not in response.text


def test_read_series_timeout_returns_504() -> None:
    fake = FakeIngestionService(seen_requests=[], simulate_timeout=True)
    client = _build_client(fake)

    response = client.get(
        "/ingestion/datasets/binance_price_btcusdt_1h/series",
        headers={"Authorization": f"Bearer {RAW_KEY_A}"},
    )

    assert response.status_code == 504
    assert response.json()["detail"] == "downstream service timed out"


# DASH-109: `GET /ingestion/connectors/{source}/status`


def test_connector_status_forwards_and_returns_response_shape(client: TestClient) -> None:
    response = client.get(
        "/ingestion/connectors/binance_price_btcusdt_1h/status",
        headers={"Authorization": f"Bearer {RAW_KEY_A}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "completed",
        "timestamp": "2026-01-02T00:00:00",
        "row_count": 24,
    }


def test_connector_status_no_crawl_runs_returns_404_forwarded_unmodified(
    client: TestClient,
) -> None:
    response = client.get(
        "/ingestion/connectors/no_crawl_yet/status",
        headers={"Authorization": f"Bearer {RAW_KEY_A}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "no crawl runs recorded for this source"


def test_connector_status_outbound_request_carries_tenant_id_header(
    client: TestClient, fake_ingestion_service: FakeIngestionService
) -> None:
    client.get(
        "/ingestion/connectors/binance_price_btcusdt_1h/status",
        headers={"Authorization": f"Bearer {RAW_KEY_A}"},
    )

    assert len(fake_ingestion_service.seen_requests) == 1
    assert fake_ingestion_service.seen_requests[0].headers["x-tenant-id"] == TENANT_A


def test_connector_status_missing_auth_returns_401_before_any_downstream_call(
    client: TestClient, fake_ingestion_service: FakeIngestionService
) -> None:
    response = client.get("/ingestion/connectors/binance_price_btcusdt_1h/status")

    assert response.status_code == 401
    assert fake_ingestion_service.seen_requests == []


def test_connector_status_connection_failure_returns_502() -> None:
    fake = FakeIngestionService(seen_requests=[], simulate_connect_error=True)
    client = _build_client(fake)

    response = client.get(
        "/ingestion/connectors/binance_price_btcusdt_1h/status",
        headers={"Authorization": f"Bearer {RAW_KEY_A}"},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "downstream service unavailable"
    assert "internal-ingestion-service" not in response.text


def test_connector_status_timeout_returns_504() -> None:
    fake = FakeIngestionService(seen_requests=[], simulate_timeout=True)
    client = _build_client(fake)

    response = client.get(
        "/ingestion/connectors/binance_price_btcusdt_1h/status",
        headers={"Authorization": f"Bearer {RAW_KEY_A}"},
    )

    assert response.status_code == 504
    assert response.json()["detail"] == "downstream service timed out"


# GW-028: new six-value status vocabulary + `rows_fetched_so_far`/`updated_at`


def test_connector_status_forwards_running_status_with_progress_unmodified(
    client: TestClient,
) -> None:
    response = client.get(
        "/ingestion/connectors/binance_price_btcusdt_1h_midcrawl/status",
        headers={"Authorization": f"Bearer {RAW_KEY_A}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "running",
        "timestamp": "2026-01-02T00:05:00",
        "row_count": 4200,
        "rows_fetched_so_far": 4200,
        "updated_at": "2026-01-02T00:05:00",
    }


def test_connector_status_forwards_cancelling_status_unmodified(client: TestClient) -> None:
    response = client.get(
        "/ingestion/connectors/binance_price_btcusdt_1h_cancelling/status",
        headers={"Authorization": f"Bearer {RAW_KEY_A}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "cancelling",
        "timestamp": "2026-01-02T00:06:00",
        "row_count": 5000,
        "rows_fetched_so_far": 5000,
        "updated_at": "2026-01-02T00:06:00",
    }


def test_connector_status_forwards_cancelled_status_unmodified(client: TestClient) -> None:
    response = client.get(
        "/ingestion/connectors/binance_price_btcusdt_1h_cancelled/status",
        headers={"Authorization": f"Bearer {RAW_KEY_A}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "cancelled",
        "timestamp": "2026-01-02T00:07:00",
        "row_count": 5000,
        "rows_fetched_so_far": 5000,
        "updated_at": "2026-01-02T00:07:00",
    }


def test_connector_status_forwards_null_progress_fields_unmodified(client: TestClient) -> None:
    """`blockchain.info` connectors (`INGEST-024`/`INGEST-027`) don't track row
    progress, so `rows_fetched_so_far`/`updated_at` come back `null` -- unlike
    the Binance/Reddit shape asserted above, which carries real values."""
    response = client.get(
        "/ingestion/connectors/blockchain_onchain_btc_midcrawl/status",
        headers={"Authorization": f"Bearer {RAW_KEY_A}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "running",
        "timestamp": "2026-01-02T00:05:00",
        "row_count": None,
        "rows_fetched_so_far": None,
        "updated_at": None,
    }


# GW-027: `POST /ingestion/connectors/{source}/cancel`


def test_cancel_connector_forwards_202_response_shape(client: TestClient) -> None:
    response = client.post(
        "/ingestion/connectors/binance_price_btcusdt_1h/cancel",
        headers={"Authorization": f"Bearer {RAW_KEY_A}"},
    )

    assert response.status_code == 202
    assert response.json() == {"source": "binance_price_btcusdt_1h", "status": "cancelling"}


def test_cancel_connector_nothing_in_flight_returns_409_forwarded_unmodified() -> None:
    fake = FakeIngestionService(seen_requests=[], simulate_cancel_conflict=True)
    client = _build_client(fake)

    response = client.post(
        "/ingestion/connectors/binance_price_btcusdt_1h/cancel",
        headers={"Authorization": f"Bearer {RAW_KEY_A}"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "nothing in flight to cancel for connector 'binance_price_btcusdt_1h'"
    )


def test_cancel_connector_unknown_source_returns_404_forwarded_unmodified(
    client: TestClient,
) -> None:
    response = client.post(
        "/ingestion/connectors/unknown_source/cancel",
        headers={"Authorization": f"Bearer {RAW_KEY_A}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "unknown connector source 'unknown_source'"


def test_cancel_connector_outbound_request_carries_tenant_id_header(
    client: TestClient, fake_ingestion_service: FakeIngestionService
) -> None:
    client.post(
        "/ingestion/connectors/binance_price_btcusdt_1h/cancel",
        headers={"Authorization": f"Bearer {RAW_KEY_A}"},
    )

    assert len(fake_ingestion_service.seen_requests) == 1
    assert fake_ingestion_service.seen_requests[0].headers["x-tenant-id"] == TENANT_A


def test_cancel_connector_missing_auth_returns_401_before_any_downstream_call(
    client: TestClient, fake_ingestion_service: FakeIngestionService
) -> None:
    response = client.post("/ingestion/connectors/binance_price_btcusdt_1h/cancel")

    assert response.status_code == 401
    assert fake_ingestion_service.seen_requests == []
