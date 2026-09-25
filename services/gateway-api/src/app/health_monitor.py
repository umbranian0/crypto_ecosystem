"""ADMIN-001: gateway-api's first recurring in-process background task.

Fires a single, best-effort outbound webhook POST when the aggregate
`GET /system/health` status (see `app.routers.system.compute_system_health`)
flips between `"healthy"` and `"non-healthy"` -- a deliberately minimal
notification primitive, not a monitoring/alerting subsystem, matching the
same "revisit when a real trigger fires" framing `SETUP-023`/`OPS-007`
already use for the fuller, still-declined version (see
`docs/product/backlog-trust-and-admin-ops.md` ADMIN-001,
`docs/product/backlog-first-run-setup-and-ops.md` SETUP-023).

Mechanism -- `lifespan` + `asyncio.Task`, not an external-cron-hits-an-
endpoint shape: the webhook's own transition-comparison state
(`previous_status`) needs to live somewhere in-process regardless, so a
self-contained in-process task is the better fit than adding a new
`infra/`-level moving part for no benefit (see `docs/sprints/sprint-59.md`'s
scope-decision section, decided there so this ticket doesn't reopen it).

State scope: single-instance, in-memory `previous_status` only -- no
Redis/DB-backed store. A process restart simply resets the baseline rather
than misfiring a spurious transition; this is a deliberate scope call for
this platform's current single-instance deployment (see sprint-59.md), not
an oversight. Revisit only if `gateway-api` ever moves to a multi-replica
deployment (not currently planned or triggered).

Explicitly out of scope: no escalation policy, no multiple channels/
recipients, no acknowledgement/snooze mechanism, no paging-service
integration (PagerDuty/Opsgenie/etc.). One URL, one event shape, fire and
forget.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Callable

import httpx

from app.dependencies.http_client import (
    get_ingestion_service_client,
    get_reporting_service_client,
    get_validation_service_client,
)
from app.dependencies.repositories import get_health_check_engine
from app.routers.system import compute_system_health

logger = logging.getLogger(__name__)

_WEBHOOK_URL_ENV_VAR = "MONITORING_WEBHOOK_URL"
_POLL_INTERVAL_ENV_VAR = "HEALTH_MONITOR_POLL_INTERVAL_SECONDS"
_DEFAULT_POLL_INTERVAL_SECONDS = 60.0
_WEBHOOK_TIMEOUT_SECONDS = 5.0

_HEALTHY = "healthy"
_NON_HEALTHY = "non-healthy"

# Sentinel distinguishing "not overridden, read MONITORING_WEBHOOK_URL at
# call time" from an explicit `None`/URL override in tests.
_UNSET = object()


def _collapse_status(status: dict[str, str]) -> str:
    """All four sub-checks `"ok"` -> `"healthy"`; any `"degraded"`/
    `"unhealthy"`/`"unreachable"` -> `"non-healthy"` (the AC's two-way
    collapse of `compute_system_health`'s existing three-way per-sub-check
    vocabulary).
    """
    return _HEALTHY if all(value == "ok" for value in status.values()) else _NON_HEALTHY


def _compute_current_status() -> str:
    engine = get_health_check_engine()
    validation_client = get_validation_service_client()
    reporting_client = get_reporting_service_client()
    ingestion_client = get_ingestion_service_client()
    try:
        status = compute_system_health(engine, validation_client, reporting_client, ingestion_client)
    finally:
        validation_client.close()
        reporting_client.close()
        ingestion_client.close()
    return _collapse_status(status)


def _send_webhook(webhook_url: str, previous_status: str, current_status: str) -> None:
    payload = {
        "event": "health_transition",
        "previous_status": previous_status,
        "current_status": current_status,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        response = httpx.post(webhook_url, json=payload, timeout=_WEBHOOK_TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        # OPS-006 structured logging (plain logging.getLogger(__name__),
        # picked up by the already-configured JSON formatter) -- log and
        # drop, never re-raise: a bad webhook receiver must never affect the
        # health-evaluation path itself.
        logger.warning(
            "health_monitor: webhook delivery failed for health_transition %s->%s: %s",
            previous_status,
            current_status,
            exc,
        )
        return
    if response.status_code >= 400:
        logger.warning(
            "health_monitor: webhook receiver returned %s for health_transition %s->%s",
            response.status_code,
            previous_status,
            current_status,
        )


async def evaluate_and_notify(
    previous_status: str | None,
    *,
    compute_status: Callable[[], str] = _compute_current_status,
    webhook_url=_UNSET,
) -> str:
    """One evaluation cycle. Returns the new `previous_status` for the
    caller to remember (single-instance, in-memory only -- no external
    store, per the sprint's disclosed scope decision).

    `previous_status=None` means "no real baseline yet" (first-ever
    evaluation, or a just-restarted process) -- never fires a webhook on
    this cycle regardless of the computed status, since there is nothing
    genuine to compare against yet (a restart resets the baseline rather
    than misfiring a spurious transition, per the sprint plan).
    """
    current = compute_status()

    if previous_status is not None and current != previous_status:
        url = os.environ.get(_WEBHOOK_URL_ENV_VAR) if webhook_url is _UNSET else webhook_url
        if url:
            _send_webhook(url, previous_status, current)

    return current


async def run_health_monitor(*, max_iterations: int | None = None) -> None:
    """Sleeps/wakes on `HEALTH_MONITOR_POLL_INTERVAL_SECONDS` (default 60s,
    disclosed in README). `max_iterations` is a test-only seam (same shape
    as `subscriber.py`'s `max_events`) letting tests drive a bounded number
    of iterations of the same loop instead of looping forever.

    Never lets one bad evaluation cycle (e.g. a DB hiccup) kill the loop --
    caught, logged, `previous_status` left unchanged, retried next interval.
    """
    interval = float(os.environ.get(_POLL_INTERVAL_ENV_VAR, _DEFAULT_POLL_INTERVAL_SECONDS))
    previous_status: str | None = None
    iterations = 0
    while max_iterations is None or iterations < max_iterations:
        try:
            previous_status = await evaluate_and_notify(previous_status)
        except Exception:
            logger.exception("health_monitor: evaluation cycle failed, retrying next interval")
        iterations += 1
        if max_iterations is not None and iterations >= max_iterations:
            break
        await asyncio.sleep(interval)
