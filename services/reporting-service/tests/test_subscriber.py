"""RS-006: `app.subscriber` tests against real Redis (VS-014's own
integration-test precedent -- skip-guarded, not mocked) plus a faked
validation-service (`httpx.MockTransport`, RS-004's own `test_generate_
endpoint.py` precedent) and an in-memory fake `ReportRepository`.

Requires a reachable Redis at `REDIS_URL` (default `redis://localhost:6379/0`).
Real Postgres is deliberately not exercised here -- RS-002's own
`test_postgres_repository.py` already proves `PostgresReportRepository`
end-to-end; this suite's job is proving the subscriber's Redis-consumption
and defense-in-depth logic, with `ReportRepository`'s `typing.Protocol`
contract satisfied by a plain fake (same precedent RS-004/RS-005's own tests
already use).
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
import pytest

redis = pytest.importorskip("redis")

import app.routers.report_generation as report_generation
import app.subscriber as subscriber
from app.repositories.interfaces import ReportRecord

_TEST_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


def _make_redis_client():
    client = subscriber.get_redis_client(_TEST_REDIS_URL)
    try:
        client.ping()
    except redis.exceptions.ConnectionError:
        pytest.skip(f"Redis not reachable at {_TEST_REDIS_URL}")
    # Consumer group is created fresh (id="$") before each test publishes,
    # so the group only ever sees this test's own entries -- not the years
    # of unrelated `run.completed` history VS-014's own producer-side tests
    # (and prior sprints) have already left on this shared stream.
    try:
        client.xgroup_destroy("run.completed", "reporting-service")
    except redis.exceptions.ResponseError:
        pass
    subscriber._ensure_consumer_group(client)
    return client


@pytest.fixture()
def redis_client():
    client = _make_redis_client()
    yield client
    client.close()


@dataclass
class FakeValidationService:
    """Serves `GET /runs/{id}` (+ `/splits`) for whatever runs are seeded in
    `self.runs`, mirroring RS-004's own `FakeValidationService` precedent.
    """

    runs: dict[str, dict] = field(default_factory=dict)
    splits: dict[str, list[dict]] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append(path)

        if path.endswith("/splits"):
            run_id = path.removeprefix("/runs/").removesuffix("/splits")
            run = self.runs.get(run_id)
            if run is None:
                return httpx.Response(404, json={"detail": "run not found"})
            return httpx.Response(200, json=self.splits.get(run_id, []))

        run_id = path.removeprefix("/runs/")
        run = self.runs.get(run_id)
        if run is None:
            return httpx.Response(404, json={"detail": "run not found"})
        return httpx.Response(200, json=run)


@dataclass
class FakeReportRepository:
    created: list[ReportRecord] = field(default_factory=list)

    def create_report(
        self, tenant_id: str, run_id: str, report_kind: str, content: str, status: str
    ) -> ReportRecord:
        record = ReportRecord(
            id=f"report-{len(self.created)}",
            tenant_id=tenant_id,
            run_id=run_id,
            report_kind=report_kind,
            generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            content=content,
            status=status,
        )
        self.created.append(record)
        return record

    def get_report(self, tenant_id: str, report_id: str) -> ReportRecord | None:  # pragma: no cover
        raise NotImplementedError


def _run_detail(run_id: str, tenant_id: str, status: str = "completed") -> dict:
    return {
        "id": run_id,
        "tenant_id": tenant_id,
        "dataset_id": "dataset-1",
        "horizon": 5,
        "purge_gap_hours": 2.0,
        "split_config": {"train_window": 30, "test_window": 7, "step": 7},
        "status": status,
        "created_at": "2026-01-01T00:00:00",
        "completed_at": "2026-01-01T00:05:00" if status == "completed" else None,
        "failure_reason": None if status == "completed" else "run did not complete",
    }


def _mock_client(fake_service: FakeValidationService) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(fake_service.handler),
        base_url="http://validation-service",
    )


def test_subscriber_imports_the_same_generation_function_as_the_route_handler() -> None:
    assert subscriber.generate_validation_audit_report is report_generation.generate_validation_audit_report


def test_publish_and_consume_real_completed_event_generates_report(redis_client) -> None:
    run_id = str(uuid.uuid4())
    tenant_id = "tenant-real-redis"
    fake_service = FakeValidationService(runs={run_id: _run_detail(run_id, tenant_id)}, splits={run_id: []})
    repository = FakeReportRepository()
    client = _mock_client(fake_service)

    redis_client.xadd(
        "run.completed",
        {
            "run_id": run_id,
            "tenant_id": tenant_id,
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    subscriber.run_subscriber(redis_client, client, repository, max_events=1)

    assert len(repository.created) == 1
    persisted = repository.created[0]
    assert persisted.run_id == run_id
    assert persisted.tenant_id == tenant_id
    assert persisted.report_kind == "validation_audit"


def test_malformed_event_is_skipped_and_loop_still_processes_next_event(redis_client, caplog) -> None:
    malformed_run_id = str(uuid.uuid4())
    good_run_id = str(uuid.uuid4())
    tenant_id = "tenant-malformed-test"
    fake_service = FakeValidationService(
        runs={good_run_id: _run_detail(good_run_id, tenant_id)}, splits={good_run_id: []}
    )
    repository = FakeReportRepository()
    client = _mock_client(fake_service)

    # Missing tenant_id -- malformed per the ticket's own example.
    redis_client.xadd(
        "run.completed",
        {
            "run_id": malformed_run_id,
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    redis_client.xadd(
        "run.completed",
        {
            "run_id": good_run_id,
            "tenant_id": tenant_id,
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    with caplog.at_level("WARNING"):
        subscriber.run_subscriber(redis_client, client, repository, max_events=2)

    assert len(repository.created) == 1
    assert repository.created[0].run_id == good_run_id
    assert any("missing field" in message for message in caplog.messages)


def test_status_recheck_blocks_generation_when_fetched_run_is_not_completed(redis_client) -> None:
    run_id = str(uuid.uuid4())
    tenant_id = "tenant-status-recheck"
    # Fetched run detail says "failed" even though the event payload claims
    # "completed" -- proves the re-check queries the fetched RunDetailResponse,
    # not the event payload's own status field.
    fake_service = FakeValidationService(runs={run_id: _run_detail(run_id, tenant_id, status="failed")})
    repository = FakeReportRepository()
    client = _mock_client(fake_service)

    redis_client.xadd(
        "run.completed",
        {
            "run_id": run_id,
            "tenant_id": tenant_id,
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    subscriber.run_subscriber(redis_client, client, repository, max_events=1)

    assert repository.created == []
