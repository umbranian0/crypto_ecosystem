"""VS-014: `RedisStreamsEventPublisher` integration tests against real Redis.

Requires a reachable Redis at `REDIS_URL` (default `redis://localhost:6379/0`,
matching this ticket's Design section). Not mocked -- these tests skip
(rather than fail) if no Redis is reachable, so the suite stays runnable in
environments without a broker, while still satisfying the ticket's "at least
one integration-style test against real Redis" acceptance criterion whenever
Redis is up (as it is in this dev environment).
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest

redis = pytest.importorskip("redis")

from app.events import RedisStreamsEventPublisher

_TEST_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


def _make_client():
    client = redis.from_url(_TEST_REDIS_URL, decode_responses=True)
    try:
        client.ping()
    except redis.exceptions.ConnectionError:
        pytest.skip(f"Redis not reachable at {_TEST_REDIS_URL}")
    return client


@pytest.fixture
def redis_client():
    client = _make_client()
    yield client
    client.close()


def test_publish_xadds_run_completed_with_flattened_fields(redis_client):
    stream_key = "run.completed"
    # Unique run_id per test run so xrange's tail-read can unambiguously
    # locate this test's own entry even if the stream already has history
    # from prior test runs against the same Redis instance.
    run_id = str(uuid.uuid4())
    completed_at = datetime.now(timezone.utc).isoformat()

    publisher = RedisStreamsEventPublisher(redis_client)
    payload = {
        "run_id": run_id,
        "tenant_id": "tenant-1",
        "status": "completed",
        "completed_at": completed_at,
    }

    publisher.publish(stream_key, payload)

    entries = redis_client.xrange(stream_key, "-", "+")
    matching = [fields for _, fields in entries if fields.get("run_id") == run_id]
    assert len(matching) == 1

    fields = matching[0]
    assert fields["run_id"] == run_id
    assert fields["tenant_id"] == "tenant-1"
    assert fields["status"] == "completed"
    assert fields["completed_at"] == completed_at

    # completed_at must be ISO-8601 parseable, per binding decision #9.
    datetime.fromisoformat(fields["completed_at"])


def test_get_event_publisher_returns_redis_publisher_when_env_var_set(monkeypatch):
    _make_client()  # confirm Redis reachable before exercising the DI seam
    monkeypatch.setenv("REDIS_URL", _TEST_REDIS_URL)
    import app.dependencies.repositories as repositories

    repositories._get_redis_publisher.cache_clear()
    try:
        publisher = repositories.get_event_publisher()
        assert isinstance(publisher, RedisStreamsEventPublisher)
    finally:
        repositories._get_redis_publisher.cache_clear()


def test_get_event_publisher_falls_back_to_in_process_without_env_var(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    import app.dependencies.repositories as repositories
    from app.events import InProcessLogEventPublisher

    publisher = repositories.get_event_publisher()
    assert isinstance(publisher, InProcessLogEventPublisher)
