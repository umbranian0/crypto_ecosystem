"""RS-006: Redis Streams subscriber for validation-service's `run.completed`
event -- Observer pattern (implementation-plan.md section 7), the
"`run.completed` -> `reporting-service`" instance the pattern table names
explicitly.

Single responsibility: consume `run.completed` entries (VS-014's exact
documented wire format -- flattened string fields, stream key is the event
name) via `XREADGROUP` consumer-group semantics, and for each valid
`status == "completed"` event, call RS-004's own
`generate_validation_audit_report` (`app.generation`) -- the same fetch ->
render -> persist sequence `POST /reports/generate`'s route handler calls, not
a second copy of it. This module owns none of that sequence; it only decides
*when* to trigger it and re-verifies the run's real status first (defense in
depth, ticket Design section) rather than trusting the event payload's own
`status` field.

Not wired into `infra/docker-compose.yml` this ticket (RS-GAP) -- runnable
standalone via `python -m app.subscriber` from this service's `src`
directory, mirroring the working-directory convention `uvicorn app.main:app`
already uses (see this service's README/Dockerfile).
"""

from __future__ import annotations

import logging
import os

import httpx
import redis

from app.dependencies.http_client import get_validation_service_client
from app.dependencies.repositories import get_report_repository
from app.generation import GenerationError, generate_validation_audit_report
from app.repositories.interfaces import ReportRepository

logger = logging.getLogger(__name__)

_REDIS_URL_ENV_VAR = "REDIS_URL"
_DEFAULT_REDIS_URL = "redis://localhost:6379/0"

_STREAM_KEY = "run.completed"
_GROUP_NAME = "reporting-service"
_CONSUMER_NAME = "reporting-service-subscriber"
_BLOCK_MS = 5000
_READ_COUNT = 10

_REQUIRED_FIELDS = ("run_id", "tenant_id", "status")


def get_redis_client(redis_url: str | None = None) -> redis.Redis:
    url = redis_url or os.environ.get(_REDIS_URL_ENV_VAR, _DEFAULT_REDIS_URL)
    # `socket_timeout` must exceed `_BLOCK_MS`'s own wait window -- otherwise
    # the client-side socket read times out before the server's own
    # `XREADGROUP ... BLOCK` unblocks, surfacing a spurious
    # `redis.exceptions.TimeoutError` on every idle poll.
    return redis.from_url(url, decode_responses=True, socket_timeout=(_BLOCK_MS / 1000) + 5)


def _ensure_consumer_group(redis_client: redis.Redis) -> None:
    # `id="$"`: a freshly created group only delivers entries added *after*
    # group creation, not the stream's full history -- this stream is shared
    # with validation-service's own producer-side tests (VS-014), so
    # replaying from "0" would hand this subscriber years of unrelated test
    # fixture entries on first run. MKSTREAM so the group can be created
    # before validation-service has ever published anything.
    try:
        redis_client.xgroup_create(_STREAM_KEY, _GROUP_NAME, id="$", mkstream=True)
    except redis.exceptions.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def _missing_fields(fields: dict[str, str]) -> list[str]:
    return [name for name in _REQUIRED_FIELDS if not fields.get(name)]


def _fetch_run_status(
    client: httpx.Client, tenant_id: str, run_id: str
) -> str | None:
    """One extra `GET /runs/{id}` call, deliberately separate from
    `generate_validation_audit_report`'s own internal fetch (ticket Design
    section) -- this is the defense-in-depth re-check against the event
    payload's own (untrusted) `status` field, not a duplication of the
    fetch -> render -> persist sequence itself, since it never renders or
    persists anything.
    """
    try:
        response = client.get(f"/runs/{run_id}", headers={"X-Tenant-Id": tenant_id})
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        logger.warning("run.completed re-check: validation-service unreachable for run %s: %s", run_id, exc)
        return None
    if response.status_code != 200:
        logger.warning(
            "run.completed re-check: unexpected status %s fetching run %s",
            response.status_code,
            run_id,
        )
        return None
    return response.json().get("status")


def handle_event(
    fields: dict[str, str],
    client: httpx.Client,
    repository: ReportRepository,
) -> None:
    """Processes one `run.completed` stream entry's already-decoded field
    dict. Never raises -- every failure mode (malformed event, defense-in-
    depth re-check mismatch, generation failure) is logged and the event is
    skipped, so one bad/failing event never kills the subscriber loop.
    """
    missing = _missing_fields(fields)
    if missing:
        logger.warning("run.completed event missing field(s) %s, skipping: %s", missing, fields)
        return

    run_id = fields["run_id"]
    tenant_id = fields["tenant_id"]

    if fields["status"] != "completed":
        return

    actual_status = _fetch_run_status(client, tenant_id, run_id)
    if actual_status != "completed":
        logger.warning(
            "run.completed event for run %s claimed status=completed but fetched run detail "
            "has status=%r; skipping report generation (defense-in-depth re-check)",
            run_id,
            actual_status,
        )
        return

    try:
        generate_validation_audit_report(
            tenant_id=tenant_id,
            run_id=run_id,
            client=client,
            repository=repository,
        )
    except GenerationError as exc:
        logger.warning("report generation failed for run %s (tenant %s): %s", run_id, tenant_id, exc)


def run_subscriber(
    redis_client: redis.Redis,
    client: httpx.Client,
    repository: ReportRepository,
    *,
    max_events: int | None = None,
) -> None:
    """Blocking consume loop. `max_events` (test-only seam) stops the loop
    after that many stream entries have been read and processed, so tests
    can drive a bounded number of iterations of the *same* running loop
    instead of looping forever.
    """
    _ensure_consumer_group(redis_client)
    processed = 0
    while max_events is None or processed < max_events:
        response = redis_client.xreadgroup(
            _GROUP_NAME,
            _CONSUMER_NAME,
            {_STREAM_KEY: ">"},
            count=_READ_COUNT,
            block=_BLOCK_MS,
        )
        if not response:
            continue
        for _stream_key, entries in response:
            for entry_id, fields in entries:
                try:
                    handle_event(fields, client, repository)
                finally:
                    redis_client.xack(_STREAM_KEY, _GROUP_NAME, entry_id)
                    processed += 1
                    if max_events is not None and processed >= max_events:
                        return


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    redis_client = get_redis_client()
    client = get_validation_service_client()
    repository = get_report_repository()
    logger.info("reporting-service subscriber: listening on stream %r", _STREAM_KEY)
    run_subscriber(redis_client, client, repository)


if __name__ == "__main__":
    main()
